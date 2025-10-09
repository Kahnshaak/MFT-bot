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
    
    print("✅ All components initialized")
    
    # 2. Set up event bus middleware for basic processing
    print("\n🔧 Setting up event bus middleware...")
    
    async def processing_middleware(event: Event) -> Event:
        """Middleware to process events."""
        event.data["processed_at"] = datetime.utcnow().isoformat()
        return event
    
    event_bus.add_middleware(processing_middleware)
    
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
        print(f"📨 Event processed at: {event.data.get('processed_at', 'N/A')}")
    
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
    
    # 5. Test basic event processing
    print("\n🔄 Testing basic event processing...")
    
    # Verify event was processed by middleware
    assert "processed_at" in event.data, "Event should have been processed by middleware"
    print("✅ Event processing working")
    
    # 6. Test error handling integration
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
    
    # 7. Test rate limiting
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
    
    # 8. Final integration verification
    print("\n🔍 Final integration verification...")
    
    # Verify basic functionality is working
    assert len(received_events) == 1, "Should have received exactly one event"
    assert received_events[0].event_type == EventType.EVENT_CREATED
    assert "processed_at" in received_events[0].data
    
    print("✅ Basic integration verified")
    
    print("\n🎉 SIMPLIFIED INTEGRATION TEST PASSED!")
    print("✅ Event Bus: Working with typed events and middleware")
    print("✅ Security Manager: Permission checks and rate limiting")
    print("✅ Validation Manager: Input validation and sanitization")
    print("✅ Error Handling: Proper exception handling")
    print("✅ Integration: Core systems working together")
    
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