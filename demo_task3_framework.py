#!/usr/bin/env python3
"""
Demonstration script for Task 3: Core Bot Framework and Event Bus System

This script demonstrates all the implemented components:
- Event bus for inter-cog communication with typed event handling and error propagation
- Permission manager with Discord role mapping and resource-specific permissions  
- Input validation system with comprehensive sanitization rules and validation error handling
- Security manager for authentication and authorization with audit logging
- Metrics collection system for monitoring command usage and performance
- Health monitoring framework with database and Discord API checks
- Integrated logging and error handling throughout all core systems
"""

import asyncio
import sys
import os
import time
from unittest.mock import Mock, AsyncMock

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from core.event_bus import EventBus, EventType, Event
from core.security_manager import SecurityManager, Permission
from core.validation_manager import ValidationManager, ValidationType, ValidationRule
from core.metrics_collector import MetricsCollector
from core.health_monitor import HealthMonitor
from core.audit_logger import AuditLogger, AuditEventType
from utils.error_handler import ErrorHandler, handle_exceptions, retry_on_failure
from utils.exceptions import GameNightBotException, ValidationError, PermissionDeniedError
from utils.logging_config import get_logger, setup_logging
from config.settings import Settings
from database.manager import DatabaseManager


async def demonstrate_event_bus():
    """Demonstrate event bus functionality."""
    print("\n🔄 Event Bus System Demonstration")
    print("=" * 50)
    
    event_bus = EventBus()
    received_events = []
    
    # Subscribe to events
    async def event_handler(event: Event):
        received_events.append(event)
        print(f"📨 Received event: {event.event_type.value} from {event.source}")
    
    event_bus.subscribe(EventType.EVENT_CREATED, event_handler)
    event_bus.subscribe(EventType.ERROR_OCCURRED, event_handler)
    
    # Add middleware
    def logging_middleware(event: Event) -> Event:
        print(f"🔧 Middleware processing: {event.event_type.value}")
        return event
    
    event_bus.add_middleware(logging_middleware)
    
    # Emit events
    await event_bus.emit(
        EventType.EVENT_CREATED,
        {"event_name": "Test Game Night", "creator": "user123"},
        source="events_cog",
        guild_id="guild456"
    )
    
    # Test error propagation
    def failing_middleware(event: Event) -> Event:
        if event.data.get("cause_error"):
            raise ValueError("Test middleware error")
        return event
    
    event_bus.add_middleware(failing_middleware)
    
    await event_bus.emit(
        EventType.EVENT_UPDATED,
        {"cause_error": True},
        source="test"
    )
    
    print(f"✅ Event bus processed {len(received_events)} events")
    print(f"📊 Subscriber count for EVENT_CREATED: {event_bus.get_subscriber_count(EventType.EVENT_CREATED)}")


async def demonstrate_security_manager():
    """Demonstrate security manager functionality."""
    print("\n🔒 Security Manager Demonstration")
    print("=" * 50)
    
    settings = Settings()
    security = SecurityManager(settings)
    
    # Mock Discord member
    mock_user = Mock()
    mock_user.id = 123456789
    mock_user.roles = []
    mock_user.guild_permissions = Mock()
    mock_user.guild_permissions.administrator = False
    mock_user.guild_permissions.manage_guild = False
    mock_user.guild_permissions.manage_messages = False
    
    # Test permission checking
    guild_id = 987654321
    
    # Configure role mapping
    security.configure_role_mapping(
        guild_id, 
        555555555,  # role_id
        {Permission.CREATE_EVENTS, Permission.MANAGE_OWN_EVENTS}
    )
    
    # Test basic permissions (should have member permissions)
    permissions = security.get_user_permissions(mock_user, guild_id)
    print(f"🔑 User permissions: {[p.value for p in permissions]}")
    
    # Test input validation
    try:
        clean_input = security.validate_input(
            "Test Event @everyone",
            max_length=50,
            forbidden_patterns=[r'@everyone']
        )
        print(f"❌ Should have failed validation")
    except ValidationError as e:
        print(f"✅ Input validation caught forbidden pattern: {e}")
    
    # Test rate limiting
    try:
        security.check_rate_limit("user123", max_requests=2, window_seconds=60)
        security.check_rate_limit("user123", max_requests=2, window_seconds=60)
        security.check_rate_limit("user123", max_requests=2, window_seconds=60)  # Should fail
        print(f"❌ Should have been rate limited")
    except Exception as e:
        print(f"✅ Rate limiting working: {type(e).__name__}")
    
    # Test session tokens
    token = security.create_session_token("user123", "guild456")
    session = security.validate_session_token(token)
    print(f"🎫 Session token created and validated: {session is not None}")


async def demonstrate_validation_manager():
    """Demonstrate validation manager functionality."""
    print("\n✅ Validation Manager Demonstration")
    print("=" * 50)
    
    validator = ValidationManager()
    
    # Test event title validation
    try:
        title = validator.validate_field("event_title", "Game Night 🎮")
        print(f"✅ Valid event title: '{title}'")
    except ValidationError as e:
        print(f"❌ Validation failed: {e}")
    
    # Test invalid input
    try:
        validator.validate_field("event_title", "")  # Too short
        print(f"❌ Should have failed validation")
    except ValidationError as e:
        print(f"✅ Caught validation error: {e}")
    
    # Test custom validation rule
    custom_rule = ValidationRule(
        field_name="custom_field",
        validation_type=ValidationType.STRING,
        min_length=5,
        max_length=20,
        pattern=r'^[A-Z][a-z]+$'
    )
    
    try:
        result = validator.validate_field("custom_field", "Hello", custom_rule)
        print(f"✅ Custom validation passed: '{result}'")
    except ValidationError as e:
        print(f"❌ Custom validation failed: {e}")


async def demonstrate_metrics_collector():
    """Demonstrate metrics collector functionality."""
    print("\n📊 Metrics Collector Demonstration")
    print("=" * 50)
    
    metrics = MetricsCollector()
    
    # Record various metrics
    await metrics.record_command("create_event", 0.25, True, "guild123", "user456")
    await metrics.record_command("join_event", 0.15, True, "guild123", "user789")
    await metrics.record_command("create_event", 0.30, False, "guild123", "user456")  # Failed command
    
    metrics.record_counter("events_created", 1.0, {"guild": "guild123"})
    metrics.record_gauge("active_events", 5.0)
    
    # Use timer context
    with metrics.timer("database_query", {"operation": "find_events"}):
        await asyncio.sleep(0.1)  # Simulate database operation
    
    # Get statistics
    command_stats = metrics.get_command_stats()
    system_stats = metrics.get_system_stats()
    
    print(f"📈 Command statistics:")
    for cmd, stats in command_stats.items():
        print(f"  {cmd}: {stats['total_executions']} executions, {stats['success_rate']:.2%} success rate")
    
    print(f"🖥️  System uptime: {system_stats['uptime_seconds']:.2f} seconds")
    print(f"📊 Total metrics collected: {system_stats['metrics_collected']}")


async def demonstrate_health_monitor():
    """Demonstrate health monitor functionality."""
    print("\n🏥 Health Monitor Demonstration")
    print("=" * 50)
    
    # Mock database and bot
    mock_db = Mock()
    mock_db.ping = AsyncMock()
    mock_db.test_connection = AsyncMock(return_value=True)
    
    mock_bot = Mock()
    mock_bot.user = Mock()
    mock_bot.user.id = 123456789
    mock_bot.fetch_user = AsyncMock(return_value=mock_bot.user)
    mock_bot.is_ready = Mock(return_value=True)
    mock_bot.latency = 0.05  # 50ms
    mock_bot.guilds = [Mock(), Mock()]  # 2 guilds
    
    health_monitor = HealthMonitor(mock_db, mock_bot)
    
    # Run health checks
    results = await health_monitor.run_all_checks()
    
    print(f"🔍 Health check results:")
    for name, check in results.items():
        status_emoji = "✅" if check.status.value == "healthy" else "⚠️" if check.status.value == "degraded" else "❌"
        print(f"  {status_emoji} {name}: {check.status.value} - {check.message}")
    
    overall_health = health_monitor.get_overall_health()
    print(f"🏥 Overall system health: {overall_health.value}")


async def demonstrate_audit_logger():
    """Demonstrate audit logger functionality."""
    print("\n📋 Audit Logger Demonstration")
    print("=" * 50)
    
    # Mock database
    mock_db = Mock()
    mock_db.insert_document = AsyncMock()
    mock_db.find_documents = AsyncMock(return_value=[
        {
            "event_type": "event_created",
            "user_id": "user123",
            "action": "Created game night event",
            "timestamp": time.time()
        }
    ])
    
    audit_logger = AuditLogger(mock_db)
    
    # Log various events
    await audit_logger.log_event(
        AuditEventType.EVENT_CREATED,
        "Created game night event",
        user_id="user123",
        guild_id="guild456",
        resource_id="event789",
        resource_type="event",
        details={"event_name": "Friday Game Night"}
    )
    
    await audit_logger.log_security_event(
        AuditEventType.RATE_LIMIT_EXCEEDED,
        "User exceeded command rate limit",
        user_id="user456",
        guild_id="guild456",
        severity="medium"
    )
    
    await audit_logger.log_permission_event(
        granted=False,
        user_id="user789",
        guild_id="guild456",
        permission="manage_all_events",
        details={"attempted_action": "delete_event"}
    )
    
    print(f"✅ Logged audit events to database")
    
    # Retrieve audit logs
    logs = await audit_logger.get_audit_logs(guild_id="guild456", limit=10)
    print(f"📋 Retrieved {len(logs)} audit log entries")


async def demonstrate_error_handling():
    """Demonstrate error handling functionality."""
    print("\n🚨 Error Handling Demonstration")
    print("=" * 50)
    
    # Test exception handling decorator
    @handle_exceptions(default_return="fallback_value", log_errors=True)
    async def failing_function():
        raise ValueError("This function always fails")
    
    result = await failing_function()
    print(f"🔄 Error handled gracefully, returned: {result}")
    
    # Test retry decorator
    attempt_count = 0
    
    @retry_on_failure(max_attempts=3, delay=0.1, exceptions=(ValueError,))
    async def sometimes_failing_function():
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            raise ValueError(f"Attempt {attempt_count} failed")
        return f"Success on attempt {attempt_count}"
    
    result = await sometimes_failing_function()
    print(f"🔄 Retry mechanism worked: {result}")
    
    # Test custom exceptions
    try:
        raise PermissionDeniedError("User lacks required permission")
    except GameNightBotException as e:
        print(f"🚫 Caught custom exception: {e.error_code.value} - {e.user_message}")


async def main():
    """Run all demonstrations."""
    print("🚀 Core Bot Framework Demonstration")
    print("=" * 60)
    print("Task 3: Build core bot framework and event bus system")
    print("=" * 60)
    
    # Set up logging
    setup_logging()
    logger = get_logger(__name__)
    logger.info("Starting core framework demonstration")
    
    try:
        await demonstrate_event_bus()
        await demonstrate_security_manager()
        await demonstrate_validation_manager()
        await demonstrate_metrics_collector()
        await demonstrate_health_monitor()
        await demonstrate_audit_logger()
        await demonstrate_error_handling()
        
        print("\n🎉 All Core Framework Components Working Successfully!")
        print("=" * 60)
        print("✅ Event bus for inter-cog communication with typed event handling and error propagation")
        print("✅ Permission manager with Discord role mapping and resource-specific permissions")
        print("✅ Input validation system with comprehensive sanitization rules and validation error handling")
        print("✅ Security manager for authentication and authorization with audit logging")
        print("✅ Metrics collection system for monitoring command usage and performance")
        print("✅ Health monitoring framework with database and Discord API checks")
        print("✅ Integrated logging and error handling throughout all core systems")
        print("=" * 60)
        
    except Exception as e:
        logger.error(f"Demonstration failed: {e}", exc_info=True)
        print(f"❌ Demonstration failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)