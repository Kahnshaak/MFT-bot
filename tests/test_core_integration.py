"""
Integration tests for core bot framework components.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.event_bus import EventBus, EventType, Event
from core.security_manager import SecurityManager, Permission
from core.validation_manager import ValidationManager
from config.settings import Settings
from utils.exceptions import ValidationError, PermissionDeniedError


class TestCoreFrameworkIntegration:
    """Test integration between core framework components."""
    
    @pytest.fixture
    async def mock_database(self):
        """Mock database manager."""
        db = AsyncMock()
        db.ping = AsyncMock()
        db.test_connection = AsyncMock(return_value=True)
        db.insert_document = AsyncMock()
        db.find_documents = AsyncMock(return_value=[])
        return db
    
    @pytest.fixture
    def mock_bot(self):
        """Mock Discord bot."""
        bot = MagicMock()
        bot.user = MagicMock()
        bot.user.id = 12345
        bot.is_ready = MagicMock(return_value=True)
        bot.latency = 0.1
        bot.guilds = []
        bot.fetch_user = AsyncMock()
        return bot
    
    @pytest.fixture
    def settings(self):
        """Test settings."""
        return Settings(
            discord_token="test_token",
            discord_client_id="test_client_id",
            discord_client_secret="test_secret",
            jwt_secret="test_jwt_secret",
            database_url="mongodb://test:27017/test"
        )
    
    @pytest.fixture
    def event_bus(self):
        """Event bus instance."""
        return EventBus()
    
    @pytest.fixture
    def security_manager(self, settings):
        """Security manager instance."""
        return SecurityManager(settings)
    
    @pytest.fixture
    def validation_manager(self):
        """Validation manager instance."""
        return ValidationManager()
    

    
    @pytest.mark.asyncio
    async def test_event_bus_basic_functionality(self, event_bus):
        """Test basic event bus functionality."""
        # Test event subscription and emission
        received_events = []
        
        async def event_handler(event: Event):
            received_events.append(event)
        
        # Subscribe to event
        event_bus.subscribe(EventType.EVENT_CREATED, event_handler)
        
        # Emit event
        await event_bus.emit(
            EventType.EVENT_CREATED,
            {"event_id": "test_123", "title": "Test Event"},
            guild_id="guild_123",
            user_id="user_456"
        )
        
        # Verify event was received
        assert len(received_events) == 1
        event = received_events[0]
        assert event.event_type == EventType.EVENT_CREATED
        assert event.data["event_id"] == "test_123"
        assert event.guild_id == "guild_123"
        assert event.user_id == "user_456"
    
    @pytest.mark.asyncio
    async def test_event_bus_multiple_subscribers(self, event_bus):
        """Test event bus with multiple subscribers."""
        received_events_1 = []
        received_events_2 = []
        
        async def event_handler_1(event: Event):
            received_events_1.append(event)
        
        async def event_handler_2(event: Event):
            received_events_2.append(event)
        
        event_bus.subscribe(EventType.EVENT_CREATED, event_handler_1)
        event_bus.subscribe(EventType.EVENT_CREATED, event_handler_2)
        
        await event_bus.emit(
            EventType.EVENT_CREATED,
            {"user_id": "user_123"}
        )
        
        # Verify both handlers received the event
        assert len(received_events_1) == 1
        assert len(received_events_2) == 1
        assert received_events_1[0].data["user_id"] == "user_123"
        assert received_events_2[0].data["user_id"] == "user_123"
    
    @pytest.mark.asyncio
    async def test_security_manager_permissions(self, security_manager):
        """Test security manager permission system."""
        # Create mock Discord member
        mock_member = MagicMock()
        mock_member.id = 12345
        mock_member.roles = []
        mock_member.guild_permissions = MagicMock()
        mock_member.guild_permissions.administrator = False
        mock_member.guild_permissions.manage_guild = False
        mock_member.guild_permissions.manage_messages = False
        
        guild_id = 67890
        
        # Test basic member permissions
        permissions = security_manager.get_user_permissions(mock_member)
        assert Permission.VIEW_EVENTS in permissions
        assert Permission.CREATE_EVENTS in permissions
        assert Permission.MANAGE_ALL_EVENTS not in permissions
        
        # Test admin permissions
        mock_member.guild_permissions.administrator = True
        admin_permissions = security_manager.get_user_permissions(mock_member)
        assert Permission.MANAGE_ALL_EVENTS in admin_permissions
        assert len(admin_permissions) > len(permissions)
    
    @pytest.mark.asyncio
    async def test_validation_manager_input_validation(self, validation_manager):
        """Test validation manager input validation."""
        # Test valid string
        valid_title = validation_manager.validate_string(
            "My Game Night Event",
            min_length=3,
            max_length=100
        )
        assert valid_title == "My Game Night Event"
        
        # Test invalid string (too short)
        with pytest.raises(ValidationError):
            validation_manager.validate_string("Hi", min_length=3)
        
        # Test string sanitization (Discord mentions)
        sanitized = validation_manager.validate_string("Test @everyone")
        assert "@everyone" not in sanitized
        assert "@\u200beveryone" in sanitized
    
    @pytest.mark.asyncio
    async def test_event_error_handling(self, event_bus):
        """Test error handling in event callbacks."""
        received_events = []
        error_occurred = False
        
        async def failing_handler(event: Event):
            nonlocal error_occurred
            error_occurred = True
            raise ValueError("Test handler error")
        
        async def working_handler(event: Event):
            received_events.append(event)
        
        # Subscribe both handlers
        event_bus.subscribe(EventType.EVENT_CREATED, failing_handler)
        event_bus.subscribe(EventType.EVENT_CREATED, working_handler)
        
        # Emit event - should not crash despite failing handler
        await event_bus.emit(
            EventType.EVENT_CREATED,
            {"test": "data"}
        )
        
        # Working handler should still receive the event
        assert len(received_events) == 1
        assert error_occurred is True
    
    @pytest.mark.asyncio
    async def test_permission_checking_integration(self, security_manager):
        """Test permission checking functionality."""
        # Create mock member with admin permissions
        mock_admin = MagicMock()
        mock_admin.guild_permissions = MagicMock()
        mock_admin.guild_permissions.administrator = True
        mock_admin.guild_permissions.manage_guild = False
        
        # Admin should have all permissions
        permissions = security_manager.get_user_permissions(mock_admin)
        assert Permission.MANAGE_ALL_EVENTS in permissions
        assert Permission.CONFIGURE_BOT in permissions
        
        # Test permission requirement
        try:
            security_manager.require_permission(mock_admin, Permission.MANAGE_ALL_EVENTS)
            # Should not raise exception
        except PermissionDeniedError:
            pytest.fail("Admin should have required permission")
    
    @pytest.mark.asyncio
    async def test_permission_and_validation_integration(self, security_manager, validation_manager):
        """Test integration between permission and validation systems."""
        # Create mock member with basic permissions
        mock_member = MagicMock()
        mock_member.id = 12345
        mock_member.guild_permissions = MagicMock()
        mock_member.guild_permissions.administrator = False
        mock_member.guild_permissions.manage_guild = False
        
        # Test permission check
        has_create_permission = security_manager.check_permission(
            mock_member, Permission.CREATE_EVENTS
        )
        assert has_create_permission is True
        
        # Test validation of event data
        event_data = {
            "title": "Valid Event Title",
            "description": "This is a valid event description"
        }
        
        validation_rules = {
            "title": {"type": "string", "min_length": 3, "max_length": 100},
            "description": {"type": "string", "max_length": 2000}
        }
        
        validated_data = validation_manager.validate_data(event_data, validation_rules)
        assert validated_data["title"] == "Valid Event Title"
        assert "description" in validated_data


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])