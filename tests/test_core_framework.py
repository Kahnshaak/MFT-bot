"""
Tests for the core bot framework and event bus system.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.event_bus import EventBus, EventType, Event
from core.security_manager import SecurityManager, Permission
from core.validation_manager import ValidationManager
from config.settings import Settings


class TestEventBus:
    """Test the event bus system."""
    
    @pytest.fixture
    def event_bus(self):
        return EventBus()
    
    def test_event_bus_initialization(self, event_bus):
        """Test event bus initializes correctly."""
        assert event_bus is not None
        assert len(event_bus._subscribers) == 0
    
    def test_subscribe_and_emit(self, event_bus):
        """Test subscribing to events and emitting them."""
        callback_called = False
        received_event = None
        
        def callback(event):
            nonlocal callback_called, received_event
            callback_called = True
            received_event = event
        
        # Subscribe to event
        event_bus.subscribe(EventType.EVENT_CREATED, callback)
        
        # Emit event
        asyncio.run(event_bus.emit(
            EventType.EVENT_CREATED,
            {"test": "data"}
        ))
        
        assert callback_called
        assert received_event is not None
        assert received_event.event_type == EventType.EVENT_CREATED
        assert received_event.data == {"test": "data"}
        assert received_event.guild_id is None
    
    def test_unsubscribe(self, event_bus):
        """Test unsubscribing from events."""
        callback_called = False
        
        def callback(event):
            nonlocal callback_called
            callback_called = True
        
        # Subscribe and then unsubscribe
        event_bus.subscribe(EventType.EVENT_CREATED, callback)
        success = event_bus.unsubscribe(EventType.EVENT_CREATED, callback)
        
        assert success is True
        
        # Emit event - callback should not be called
        asyncio.run(event_bus.emit(
            EventType.EVENT_CREATED,
            {"test": "data"}
        ))
        
        assert callback_called is False


class TestSecurityManager:
    """Test the security manager."""
    
    @pytest.fixture
    def settings(self):
        return Settings(
            discord_token="test_token",
            discord_client_id="test_client_id",
            discord_client_secret="test_client_secret",
            jwt_secret="test_jwt_secret"
        )
    
    @pytest.fixture
    def security_manager(self, settings):
        return SecurityManager(settings)
    
    def test_security_manager_initialization(self, security_manager):
        """Test security manager initializes correctly."""
        assert security_manager is not None
        assert security_manager.settings is not None
    
    def test_user_permissions(self, security_manager):
        """Test getting user permissions."""
        # Mock Discord member
        mock_member = MagicMock()
        mock_member.guild_permissions = MagicMock()
        mock_member.guild_permissions.administrator = False
        mock_member.guild_permissions.manage_guild = False
        
        permissions = security_manager.get_user_permissions(mock_member)
        
        # Basic permissions should be included
        assert Permission.VIEW_EVENTS in permissions
        assert Permission.CREATE_EVENTS in permissions
        assert Permission.MANAGE_OWN_EVENTS in permissions
        
        # Admin permissions should not be included
        assert Permission.MANAGE_ALL_EVENTS not in permissions
    
    def test_input_validation(self, security_manager):
        """Test input validation."""
        # Valid input
        result = security_manager.validate_input("Hello World", max_length=20)
        assert result == "Hello World"
        
        # Input too long (should be truncated, not raise exception)
        result = security_manager.validate_input("x" * 100, max_length=10)
        assert len(result) == 10
        
        # Forbidden characters (should be sanitized)
        result = security_manager.validate_input("test@everyone")
        assert "@everyone" not in result
        assert "@\u200beveryone" in result


class TestValidationManager:
    """Test the validation manager."""
    
    @pytest.fixture
    def validation_manager(self):
        return ValidationManager()
    
    def test_validation_manager_initialization(self, validation_manager):
        """Test validation manager initializes correctly."""
        assert validation_manager is not None
        assert hasattr(validation_manager, 'PATTERNS')
    
    def test_string_validation(self, validation_manager):
        """Test string validation."""
        # Valid string
        result = validation_manager.validate_string("hello", min_length=3, max_length=10)
        assert result == "hello"
        
        # Too short
        with pytest.raises(Exception):  # ValidationError
            validation_manager.validate_string("hi", min_length=3)
        
        # Too long
        with pytest.raises(Exception):  # ValidationError
            validation_manager.validate_string("this is too long", max_length=10)
    
    def test_discord_id_validation(self, validation_manager):
        """Test Discord ID validation."""
        # Valid Discord ID
        result = validation_manager.validate_discord_id("123456789012345678")
        assert result == "123456789012345678"
        
        # Invalid Discord ID
        with pytest.raises(Exception):  # ValidationError
            validation_manager.validate_discord_id("invalid")





class TestIntegration:
    """Test integration between core components."""
    
    @pytest.mark.asyncio
    async def test_event_bus_basic_integration(self):
        """Test basic event bus integration."""
        event_bus = EventBus()
        
        received_events = []
        
        def event_handler(event):
            received_events.append(event)
        
        event_bus.subscribe(EventType.EVENT_CREATED, event_handler)
        
        # Emit event
        await event_bus.emit(EventType.EVENT_CREATED, {"test": "data"})
        
        # Check that event was received
        assert len(received_events) == 1
        assert received_events[0].data["test"] == "data"
    
    @pytest.mark.asyncio
    async def test_validation_with_security(self):
        """Test validation manager integration with security manager."""
        settings = Settings(
            discord_token="test_token",
            discord_client_id="test_client_id", 
            discord_client_secret="test_client_secret",
            jwt_secret="test_jwt_secret"
        )
        
        validation = ValidationManager()
        security = SecurityManager(settings)
        
        # Test that validation catches security issues
        with pytest.raises(Exception):  # ValidationError
            validation.validate_field("event_title", "Test @everyone event")
        
        # Test that security validation also works
        with pytest.raises(Exception):  # ValidationError
            security.validate_input("Test @everyone", forbidden_patterns=["@everyone"])


if __name__ == "__main__":
    pytest.main([__file__])