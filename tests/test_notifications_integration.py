"""
Integration tests for the notification system.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from cogs.notifications import NotificationsCog
from core.notification_manager import NotificationManager
from core.event_bus import EventBus
from models.notification import NotificationType


@pytest.mark.asyncio
class TestNotificationIntegration:
    """Test notification system integration."""
    
    @pytest.fixture
    def mock_bot(self):
        """Create a mock bot with required attributes."""
        bot = MagicMock()
        bot.database = MagicMock()
        bot.event_bus = EventBus()
        
        # Mock database collections
        bot.database.notifications = MagicMock()
        bot.database.users = MagicMock()
        bot.database.events = MagicMock()
        
        return bot
    
    @pytest.fixture
    async def notifications_cog(self, mock_bot):
        """Create a notifications cog."""
        cog = NotificationsCog(mock_bot)
        
        # Mock the notification manager to avoid starting background tasks
        cog.notification_manager = MagicMock()
        cog.notification_manager.start = AsyncMock()
        cog.notification_manager.stop = AsyncMock()
        cog.notification_manager.send_immediate_notification = AsyncMock(return_value=True)
        
        await cog.cog_load()
        return cog
    
    async def test_cog_loading(self, notifications_cog):
        """Test that the notifications cog loads successfully."""
        assert notifications_cog is not None
        assert notifications_cog.notification_manager is not None
        notifications_cog.notification_manager.start.assert_called_once()
    
    async def test_cog_unloading(self, notifications_cog):
        """Test that the notifications cog unloads successfully."""
        await notifications_cog.cog_unload()
        notifications_cog.notification_manager.stop.assert_called_once()
    
    async def test_notification_preferences_command(self, notifications_cog, mock_bot):
        """Test the notification preferences command."""
        # Mock interaction
        interaction = MagicMock()
        interaction.user.id = 123456789012345678
        interaction.guild.id = 987654321098765432
        interaction.response.send_message = AsyncMock()
        
        # Mock database response
        mock_bot.database.users.find_one = AsyncMock(return_value=None)
        
        # Execute command
        await notifications_cog.notifications_preferences(interaction)
        
        # Verify response was sent
        interaction.response.send_message.assert_called_once()
        args, kwargs = interaction.response.send_message.call_args
        
        # Check that embed was sent
        assert 'embed' in kwargs
        assert kwargs['ephemeral'] is True
    
    async def test_test_notification_command(self, notifications_cog):
        """Test the test notification command."""
        # Mock interaction
        interaction = MagicMock()
        interaction.user.id = 123456789012345678
        interaction.guild.id = 987654321098765432
        interaction.response.send_message = AsyncMock()
        
        # Execute command
        await notifications_cog.test_notification(interaction)
        
        # Verify notification manager was called
        notifications_cog.notification_manager.send_immediate_notification.assert_called_once()
        
        # Verify response
        interaction.response.send_message.assert_called_once()
        args, kwargs = interaction.response.send_message.call_args
        assert "✅ Test notification sent!" in args[0]
    
    async def test_update_notification_channel(self, notifications_cog, mock_bot):
        """Test updating notification channel preference."""
        from models.notification import NotificationChannel
        
        # Mock database update
        mock_bot.database.users.update_one = AsyncMock()
        
        # Mock event bus emit
        mock_bot.event_bus.emit = AsyncMock()
        
        # Execute update
        await notifications_cog.update_notification_channel(
            "123456789012345678",
            "987654321098765432", 
            NotificationChannel.DM
        )
        
        # Verify database update
        mock_bot.database.users.update_one.assert_called_once()
        
        # Verify event emission
        mock_bot.event_bus.emit.assert_called_once()
    
    async def test_toggle_event_reminders(self, notifications_cog, mock_bot):
        """Test toggling event reminders."""
        # Mock database operations
        mock_bot.database.users.find_one = AsyncMock(return_value=None)
        mock_bot.database.users.update_one = AsyncMock()
        mock_bot.event_bus.emit = AsyncMock()
        
        # Execute toggle (should enable since no existing preference)
        result = await notifications_cog.toggle_event_reminders(
            "123456789012345678",
            "987654321098765432"
        )
        
        # Should return True (enabled) since default is True and we're toggling
        assert result is False  # Toggled from default True to False
        
        # Verify database update
        mock_bot.database.users.update_one.assert_called_once()
        
        # Verify event emission
        mock_bot.event_bus.emit.assert_called_once()


@pytest.mark.asyncio
class TestNotificationManagerIntegration:
    """Test notification manager integration with event bus."""
    
    @pytest.fixture
    def mock_bot(self):
        """Create a mock bot."""
        bot = MagicMock()
        bot.get_guild.return_value = MagicMock()
        bot.get_user.return_value = MagicMock()
        return bot
    
    @pytest.fixture
    def mock_database(self):
        """Create a mock database."""
        database = MagicMock()
        database.notifications = MagicMock()
        database.users = MagicMock()
        database.events = MagicMock()
        return database
    
    @pytest.fixture
    def event_bus(self):
        """Create an event bus."""
        return EventBus()
    
    @pytest.fixture
    def notification_manager(self, mock_bot, mock_database, event_bus):
        """Create a notification manager."""
        manager = NotificationManager(mock_bot, mock_database, event_bus)
        # Don't start background tasks for testing
        manager.is_running = False
        return manager
    
    async def test_event_bus_integration(self, notification_manager, event_bus):
        """Test that notification manager subscribes to event bus events."""
        from core.event_bus import EventType
        
        # Check that manager subscribed to relevant events
        event_types = event_bus.get_all_event_types()
        
        expected_events = [
            EventType.EVENT_SCHEDULED,
            EventType.EVENT_CANCELLED,
            EventType.EVENT_UPDATED,
            EventType.POLL_CREATED,
            EventType.USER_PREFERENCES_UPDATED
        ]
        
        for event_type in expected_events:
            assert event_type in event_types
            assert event_bus.get_subscriber_count(event_type) > 0
    
    async def test_event_scheduled_handler(self, notification_manager, mock_database):
        """Test handling of event scheduled events."""
        # Mock database responses
        mock_event = {
            "_id": "event_123",
            "title": "Test Event",
            "schedule": {
                "selected_date": datetime.now().date(),
                "selected_time": datetime.now().time()
            },
            "rsvp_data": {
                "123456789012345678": {"status": "YES"}
            }
        }
        mock_database.events.find_one = AsyncMock(return_value=mock_event)
        
        # Mock notification scheduling
        notification_manager.schedule_event_reminder = AsyncMock()
        
        # Create event data
        from core.event_bus import Event, EventType
        event_data = Event(
            event_type=EventType.EVENT_SCHEDULED,
            data={
                "event_id": "event_123",
                "guild_id": "987654321098765432",
                "selected_game": "Test Game"
            }
        )
        
        # Handle event
        await notification_manager._on_event_scheduled(event_data)
        
        # Verify reminder was scheduled
        assert notification_manager.schedule_event_reminder.call_count >= 1


if __name__ == "__main__":
    pytest.main([__file__])