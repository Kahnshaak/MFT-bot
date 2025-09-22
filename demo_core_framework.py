#!/usr/bin/env python3
"""
Demonstration of the Discord Game Night Bot Core Framework.

This script demonstrates all the core framework components working together:
- Event Bus with typed event handling and error propagation
- Permission Manager with Discord role mapping and resource-specific permissions
- Input Validation System with comprehensive sanitization rules
- Security Manager for authentication and authorization with audit logging
- Metrics Collection System for monitoring command usage and performance
- Health Monitoring Framework with database and Discord API checks
- Integrated logging and error handling throughout all core systems
"""

import sys
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from core.event_bus import EventBus, EventType, Event
from core.security_manager import SecurityManager, Permission
from core.validation_manager import ValidationManager
from core.metrics_collector import MetricsCollector
from core.health_monitor import HealthMonitor
from core.audit_logger import AuditLogger, AuditEventType
from config.settings import Settings
from utils.exceptions import ValidationError, PermissionDeniedError


async def demonstrate_core_framework():
    """Demonstrate the complete core framework functionality."""
    
    print("🎮 Discord Game Night Bot - Core Framework Demo")
    print("=" * 60)
    
    # Initialize mock dependencies
    print("\n🔧 Setting up mock dependencies...")
    mock_database = AsyncMock()
    mock_database.ping = AsyncMock()
    mock_database.test_connection = AsyncMock(return_value=True)
    mock_database.insert_document = AsyncMock()
    
    mock_bot = MagicMock()
    mock_bot.user = MagicMock()
    mock_bot.user.id = 12345
    mock_bot.is_ready = MagicMock(return_value=True)
    mock_bot.latency = 0.05
    mock_bot.guilds = []
    mock_bot.fetch_user = AsyncMock()
    
    settings = Settings(
        discord_token="demo_token",
        discord_client_id="demo_client_id",
        discord_client_secret="demo_secret",
        jwt_secret="demo_jwt_secret"
    )
    
    # Initialize core framework components
    print("\n📦 Initializing Core Framework Components...")
    
    event_bus = EventBus()
    print("  ✅ Event Bus - Inter-cog communication with typed events")
    
    security_manager = SecurityManager(settings)
    print("  ✅ Security Manager - Authentication, authorization, and rate limiting")
    
    validation_manager = ValidationManager()
    print("  ✅ Validation Manager - Input sanitization and validation")
    
    metrics_collector = MetricsCollector()
    print("  ✅ Metrics Collector - Performance and usage monitoring")
    
    health_monitor = HealthMonitor(mock_database, mock_bot)
    print("  ✅ Health Monitor - System health checks")
    
    audit_logger = AuditLogger(mock_database)
    print("  ✅ Audit Logger - Security and action logging")
    
    # Set up integrated middleware
    print("\n🔗 Setting up Event Bus Middleware...")
    
    async def metrics_middleware(event: Event) -> Event:
        """Record metrics for all events."""
        metrics_collector.record_counter(
            "events_processed",
            1.0,
            {"type": event.event_type.value, "source": event.source or "unknown"}
        )
        return event
    
    async def audit_middleware(event: Event) -> Event:
        """Log important events to audit system."""
        important_events = ["event_created", "event_cancelled", "user_banned"]
        if event.event_type.value in important_events:
            await audit_logger.log_event(
                event_type=AuditEventType.EVENT_CREATED,
                action=f"System event: {event.event_type.value}",
                user_id=event.user_id,
                guild_id=event.guild_id,
                details=event.data
            )
        return event
    
    event_bus.add_middleware(metrics_middleware)
    event_bus.add_middleware(audit_middleware)
    print("  ✅ Metrics and Audit middleware configured")
    
    # Demonstrate Permission System
    print("\n🔐 Demonstrating Permission System...")
    
    # Create mock Discord members with different permission levels
    regular_member = MagicMock()
    regular_member.id = 11111
    regular_member.roles = []
    regular_member.guild_permissions = MagicMock()
    regular_member.guild_permissions.administrator = False
    regular_member.guild_permissions.manage_guild = False
    regular_member.guild_permissions.manage_messages = False
    
    admin_member = MagicMock()
    admin_member.id = 22222
    admin_member.roles = []
    admin_member.guild_permissions = MagicMock()
    admin_member.guild_permissions.administrator = True
    admin_member.guild_permissions.manage_guild = True
    admin_member.guild_permissions.manage_messages = True
    
    guild_id = 99999
    
    # Test regular member permissions
    regular_perms = security_manager.get_user_permissions(regular_member, guild_id)
    print(f"  👤 Regular Member Permissions: {[p.value for p in regular_perms]}")
    
    # Test admin permissions
    admin_perms = security_manager.get_user_permissions(admin_member, guild_id)
    print(f"  👑 Admin Permissions: {len(admin_perms)} total permissions")
    
    # Demonstrate permission checks
    can_create = security_manager.check_permission(regular_member, guild_id, Permission.CREATE_EVENTS)
    can_admin = security_manager.check_permission(regular_member, guild_id, Permission.SYSTEM_ADMIN)
    print(f"  ✅ Regular member can create events: {can_create}")
    print(f"  ❌ Regular member can admin system: {can_admin}")
    
    # Demonstrate Input Validation
    print("\n🛡️  Demonstrating Input Validation...")
    
    # Valid inputs
    valid_title = validation_manager.validate_field("event_title", "Weekly Game Night")
    valid_game = validation_manager.validate_field("game_name", "  among us  ")
    print(f"  ✅ Valid event title: '{valid_title}'")
    print(f"  ✅ Sanitized game name: '{valid_game}'")
    
    # Invalid inputs
    try:
        validation_manager.validate_field("event_title", "Hi")  # Too short
        print("  ❌ Should have failed!")
    except ValidationError as e:
        print(f"  ✅ Correctly rejected short title: {e.user_message}")
    
    try:
        validation_manager.validate_field("event_title", "Test @everyone ping")  # Forbidden content
        print("  ❌ Should have failed!")
    except ValidationError as e:
        print(f"  ✅ Correctly rejected forbidden content: {e.user_message}")
    
    # Demonstrate Event Bus with Real Workflow
    print("\n📡 Demonstrating Event Bus Integration...")
    
    workflow_events = []
    
    async def event_workflow_handler(event: Event):
        """Handle events in a realistic workflow."""
        workflow_events.append(event)
        
        if event.event_type == EventType.EVENT_CREATED:
            print(f"  📅 Event Created: {event.data.get('title', 'Unknown')}")
            
            # Simulate validation and processing
            await metrics_collector.record_command(
                "process_event_creation",
                duration=0.15,
                success=True,
                guild_id=event.guild_id,
                user_id=event.user_id
            )
            
            # Trigger follow-up event
            await event_bus.emit(
                EventType.POLL_CREATED,
                {"poll_type": "date_selection", "event_id": event.data.get("event_id")},
                source="event_workflow",
                guild_id=event.guild_id,
                user_id=event.user_id
            )
        
        elif event.event_type == EventType.POLL_CREATED:
            print(f"  🗳️  Poll Created: {event.data.get('poll_type', 'Unknown')}")
    
    # Subscribe to workflow events
    event_bus.subscribe(EventType.EVENT_CREATED, event_workflow_handler)
    event_bus.subscribe(EventType.POLL_CREATED, event_workflow_handler)
    
    # Simulate event creation workflow
    await event_bus.emit(
        EventType.EVENT_CREATED,
        {
            "event_id": "evt_demo_123",
            "title": "Friday Night Gaming",
            "description": "Join us for some multiplayer fun!",
            "creator_id": str(regular_member.id)
        },
        source="demo_workflow",
        guild_id=str(guild_id),
        user_id=str(regular_member.id)
    )
    
    print(f"  ✅ Processed {len(workflow_events)} events in workflow")
    
    # Demonstrate Health Monitoring
    print("\n🏥 Demonstrating Health Monitoring...")
    
    health_results = await health_monitor.run_all_checks()
    overall_health = health_monitor.get_overall_health()
    
    print(f"  🔍 Ran {len(health_results)} health checks")
    print(f"  💚 Overall system health: {overall_health.value.upper()}")
    
    for check_name, result in health_results.items():
        status_emoji = {"healthy": "✅", "degraded": "⚠️", "unhealthy": "❌"}.get(result.status.value, "❓")
        print(f"    {status_emoji} {check_name}: {result.message}")
    
    # Demonstrate Metrics Collection
    print("\n📊 Demonstrating Metrics Collection...")
    
    # Record some sample metrics
    metrics_collector.record_counter("demo_counter", 5.0, {"type": "demo"})
    metrics_collector.record_gauge("active_users", 42.0)
    
    with metrics_collector.timer("demo_operation"):
        await asyncio.sleep(0.1)  # Simulate work
    
    # Get metrics summary
    system_stats = metrics_collector.get_system_stats()
    command_stats = metrics_collector.get_command_stats()
    
    print(f"  📈 Total commands recorded: {system_stats['total_commands']}")
    print(f"  ⏱️  Average command duration: {command_stats.get('process_event_creation', {}).get('avg_duration', 0):.3f}s")
    print(f"  🔢 Metrics collected: {system_stats['metrics_collected']}")
    
    # Demonstrate Rate Limiting
    print("\n🚦 Demonstrating Rate Limiting...")
    
    user_id = "demo_user_123"
    
    # Normal usage
    try:
        security_manager.check_rate_limit(user_id, max_requests=3, window_seconds=60)
        security_manager.check_rate_limit(user_id, max_requests=3, window_seconds=60)
        print("  ✅ Normal usage allowed")
    except Exception as e:
        print(f"  ❌ Unexpected rate limit: {e}")
    
    # Rate limit exceeded
    try:
        security_manager.check_rate_limit(user_id, max_requests=3, window_seconds=60)
        security_manager.check_rate_limit(user_id, max_requests=3, window_seconds=60)  # Should fail
        print("  ❌ Should have been rate limited!")
    except Exception:
        print("  ✅ Rate limiting working correctly")
    
    # Demonstrate Error Handling Integration
    print("\n⚠️  Demonstrating Error Handling...")
    
    error_events = []
    
    async def error_handler(event: Event):
        error_events.append(event)
        print(f"  🚨 Error Event: {event.data.get('error_type', 'Unknown')}")
    
    event_bus.subscribe(EventType.ERROR_OCCURRED, error_handler)
    
    # Add middleware that causes an error
    def failing_middleware(event: Event) -> Event:
        if event.data.get("cause_error"):
            raise ValueError("Demo middleware error")
        return event
    
    event_bus.add_middleware(failing_middleware)
    
    # Emit event that will cause error
    await event_bus.emit(
        EventType.USER_JOINED_GUILD,
        {"user_id": "demo_user", "cause_error": True},
        source="error_demo"
    )
    
    print(f"  ✅ Error handling captured {len(error_events)} error events")
    
    # Final Summary
    print("\n🎉 Core Framework Demonstration Complete!")
    print("=" * 60)
    print("✅ Event Bus: Typed events, middleware, error propagation")
    print("✅ Security Manager: Permissions, rate limiting, input validation")
    print("✅ Validation Manager: Sanitization, forbidden content detection")
    print("✅ Metrics Collector: Performance monitoring, usage tracking")
    print("✅ Health Monitor: System health checks, status reporting")
    print("✅ Audit Logger: Security events, action logging")
    print("✅ Error Handling: Graceful error recovery, logging")
    print("✅ Integration: All systems working together seamlessly")
    print("\n🚀 The core framework is ready for cog development!")


if __name__ == "__main__":
    try:
        asyncio.run(demonstrate_core_framework())
    except KeyboardInterrupt:
        print("\n👋 Demo interrupted by user")
    except Exception as e:
        print(f"\n💥 Demo error: {e}")
        import traceback
        traceback.print_exc()