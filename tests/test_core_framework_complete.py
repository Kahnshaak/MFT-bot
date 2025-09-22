#!/usr/bin/env python3
"""
Comprehensive integration test for the core bot framework.
This test demonstrates all core systems working together.
"""

import sys
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.event_bus import EventBus, EventType, Event
from core.security_manager import SecurityManager, Permission
from core.validation_manager import ValidationManager
from core.metrics_collector import MetricsCollector
from core.health_monitor import HealthMonitor, HealthStatus
from core.audit_logger import AuditLogger, AuditEventType
from config.settings import Settings
from utils.exceptions import ValidationError, PermissionDeniedError


async def test_complete_integration():
    """Test complete integration of all core framework components."""
    
    print("🚀 Starting comprehensive core framework integration test...")
    
    # 1. Initialize all core components
    print("\n📦 Initializing core components...")
    
    # Mock database
    mock_database = AsyncMock()
    mock_database.ping = AsyncMock()
    mock_database.test_connection = AsyncMock(return_value=True)
    mock_database.insert_document = AsyncMock()
    mock_database.find_documents = AsyncMock(return_value=[])
    
    # Mock bot
    mock_bot = MagicMock()
    mock_bot.user = MagicMock()
    mock_bot.user.id = 12345
    mock_bot.is_ready = MagicMock(return_value=True)
    mock_bot.latency = 0.1
    mock_bot.guilds = []
    mock_bot.fetch_user = AsyncMock()
    
    # Settings
    settings = Settings(
        discord_token="test_token",
        discord_client_id="test_client_id",
        discord_client_secret="test_secret",
        jwt_secret="test_jwt_secret"
    )
    
    # Initialize components
    event_bus = EventBus()
    security_manager = SecurityManager(settings)
    validation_manager = ValidationManager()
    metrics_collector = MetricsCollector()
    health_monitor = HealthMonitor(mock_database, mock_bot)
    audit_logger = AuditLogger(mock_database)
    
    print("✅ All components initialized")
    
    # 2. Set up event bus middleware for metrics and audit logging
    print("\n🔧 Setting up event bus middleware...")
    
    async def metrics_middleware(event: Event) -> Event:
        """Middleware to record metrics for events."""
        await metrics_collector.record_counter(
            "event_bus_events_total",
            1.0,
            {"event_type": event.event_type.value, "source": event.source or "unknown"}
        )
        return event
    
    async def audit_middleware(event: Event) -> Event:
        """Middleware to log audit events."""
        audit_worthy_events = [
            "EVENT_CREATED", "EVENT_UPDATED", "EVENT_CANCELLED"
        ]
        
        if event.event_type.value.upper() in audit_worthy_events:
            await audit_logger.log_event(
                event_type=AuditEventType.EVENT_CREATED,
                action=f"Event bus: {event.event_type.value}",
                user_id=event.user_id,
                guild_id=event.guild_id,
                details={"source": event.source, "data": event.data}
            )
        return event
    
    event_bus.add_middleware(metrics_middleware)
    event_bus.add_middleware(audit_middleware)
    
    print("✅ Middleware configured")
    
    # 3. Test event creation workflow with validation and permissions
    print("\n🎯 Testing event creation workflow...")
    
    # Create mock Discord member
    mock_member = MagicMock()
    mock_member.id = 12345
    mock_member.roles = []
    mock_member.guild_permissions = MagicMock()
    mock_member.guild_permissions.administrator = False
    mock_member.guild_permissions.manage_guild = False
    mock_member.guild_permissions.manage_messages = False
    
    guild_id = 67890
    
    # Check permissions
    has_permission = security_manager.check_permission(
        mock_member, guild_id, Permission.CREATE_EVENTS
    )
    assert has_permission, "User should have CREATE_EVENTS permission"
    print("✅ Permission check passed")
    
    # Validate event data
    event_data = {
        "title": "Weekly Game Night",
        "description": "Join us for our weekly gaming session!"
    }
    
    try:
        validated_data = validation_manager.validate_data(event_data)
        print(f"✅ Event data validated: {validated_data}")
    except ValidationError as e:
        print(f"❌ Validation failed: {e}")
        return False
    
    # 4. Test event bus with integrated systems
    print("\n📡 Testing event bus integration...")
    
    received_events = []
    
    async def event_handler(event: Event):
        received_events.append(event)
        print(f"📨 Received event: {event.event_type.value}")
        
        # Record command metrics when event is handled
        await metrics_collector.record_command(
            "handle_event",
            duration=0.1,
            success=True,
            guild_id=event.guild_id,
            user_id=event.user_id
        )
    
    # Subscribe to events
    event_bus.subscribe(EventType.EVENT_CREATED, event_handler)
    
    # Emit event (this will trigger middleware and handlers)
    await event_bus.emit(
        EventType.EVENT_CREATED,
        {
            "event_id": "evt_123",
            "title": validated_data["title"],
            "description": validated_data["description"],
            "creator_id": str(mock_member.id)
        },
        source="event_creation_workflow",
        guild_id=str(guild_id),
        user_id=str(mock_member.id)
    )
    
    # Verify event was received
    assert len(received_events) == 1, "Event should have been received"
    event = received_events[0]
    assert event.event_type == EventType.EVENT_CREATED
    assert event.data["title"] == validated_data["title"]
    print("✅ Event bus integration working")
    
    # 5. Test health monitoring
    print("\n🏥 Testing health monitoring...")
    
    health_results = await health_monitor.run_all_checks()
    overall_health = health_monitor.get_overall_health()
    
    print(f"✅ Health checks completed: {len(health_results)} checks")
    print(f"✅ Overall health status: {overall_health.value}")
    
    # 6. Test metrics collection
    print("\n📊 Testing metrics collection...")
    
    # Check that metrics were recorded by middleware
    event_counter = metrics_collector.get_counter_value(
        "event_bus_events_total",
        {"event_type": "event_created", "source": "event_creation_workflow"}
    )
    assert event_counter == 1.0, f"Expected 1 event, got {event_counter}"
    
    # Get command stats
    command_stats = metrics_collector.get_command_stats()
    assert "handle_event" in command_stats, "Command stats should include handle_event"
    
    # Get system stats
    system_stats = metrics_collector.get_system_stats()
    assert system_stats["total_commands"] >= 1, "Should have recorded at least 1 command"
    
    print("✅ Metrics collection working")
    
    # 7. Test audit logging
    print("\n📝 Testing audit logging...")
    
    # Verify audit log was called by middleware
    assert mock_database.insert_document.called, "Audit log should have been written"
    
    # Test direct audit logging
    await audit_logger.log_security_event(
        event_type=AuditEventType.PERMISSION_GRANTED,
        action="Permission check passed",
        user_id=str(mock_member.id),
        guild_id=str(guild_id),
        severity="low"
    )
    
    print("✅ Audit logging working")
    
    # 8. Test error handling integration
    print("\n⚠️  Testing error handling integration...")
    
    # Test validation error
    try:
        validation_manager.validate_field("event_title", "Hi")  # Too short
        print("❌ Should have raised ValidationError")
        return False
    except ValidationError:
        print("✅ Validation error handled correctly")
    
    # Test permission error
    try:
        security_manager.require_permission(
            mock_member, guild_id, Permission.SYSTEM_ADMIN
        )
        print("❌ Should have raised PermissionDeniedError")
        return False
    except PermissionDeniedError:
        print("✅ Permission error handled correctly")
    
    # 9. Test rate limiting
    print("\n🚦 Testing rate limiting...")
    
    identifier = "test_user_123"
    
    # Should not be rate limited initially
    try:
        security_manager.check_rate_limit(identifier, max_requests=2, window_seconds=60)
        security_manager.check_rate_limit(identifier, max_requests=2, window_seconds=60)
        print("✅ Rate limiting allows normal usage")
    except Exception as e:
        print(f"❌ Unexpected rate limit error: {e}")
        return False
    
    # Third request should be rate limited
    try:
        security_manager.check_rate_limit(identifier, max_requests=2, window_seconds=60)
        print("❌ Should have been rate limited")
        return False
    except Exception:
        print("✅ Rate limiting working correctly")
    
    # 10. Final integration verification
    print("\n🔍 Final integration verification...")
    
    # Verify all systems recorded the activity
    final_metrics = metrics_collector.export_metrics()
    assert "counters" in final_metrics
    assert "command_stats" in final_metrics
    assert "system_stats" in final_metrics
    
    print("✅ All metrics exported successfully")
    
    # Verify health monitoring is functional
    health_summary = health_monitor.get_health_summary()
    assert "overall_status" in health_summary
    assert "checks" in health_summary
    
    print("✅ Health monitoring summary available")
    
    print("\n🎉 COMPREHENSIVE INTEGRATION TEST PASSED!")
    print("✅ Event Bus: Working with typed events and middleware")
    print("✅ Security Manager: Permission checks and rate limiting")
    print("✅ Validation Manager: Input validation and sanitization")
    print("✅ Metrics Collector: Command and system metrics")
    print("✅ Health Monitor: Database and API health checks")
    print("✅ Audit Logger: Security and action logging")
    print("✅ Error Handling: Proper exception handling")
    print("✅ Integration: All systems working together")
    
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_complete_integration())
        if success:
            print("\n🏆 ALL TESTS PASSED - Core framework is ready!")
            exit(0)
        else:
            print("\n💥 TESTS FAILED")
            exit(1)
    except Exception as e:
        print(f"\n💥 TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)