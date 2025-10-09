"""
Tests for the notification system.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from models.notification import (
    Notification, NotificationType, NotificationStatus
)
from core.notification_manager import NotificationManager
from core.event_bus import EventBus


class TestNotificationModel:
    """Test notification model functionality."""
    
    def test_notification_creation(self):
        """Test creating a notification."""
        notification = Notification(
            guild_id="123456789012345678",
            notification_type=NotificationType.EVENT_REMINDER,
            scheduled_for=datetime.utcnow() + timedelta(hours=1),
            recipient_user_ids=["987654321098765432"],
            title="Test Notification",
            message="This is a test notification"
        )
        
        assert notification.guild_id == "123456789012345678"
        assert notification.notification_type == NotificationType.EVENT_REMINDER
        assert notification.status == NotificationStatus.SCHEDULED
        assert len(notification.recipient_user_ids) == 1
    
    def test_notification_validation(self):
        """Test notification validation."""
        # Test empty title
        with pytest.raises(ValueError, match="Notification title cannot be empty"):
            notification = Notification(
                guild_id="123456789012345678",
                notification_type=NotificationType.EVENT_REMINDER,
                scheduled_for=datetime.utcnow() + timedelta(hours=1),
                recipient_user_ids=["987654321098765432"],
                title="",
                message="This is a test notification"
            )
            notification.validate_data()
        
        # Test no recipients
        with pytest.raises(ValueError, match="At least one recipient"):
            notification = Notification(
                guild_id="123456789012345678",
                notification_type=NotificationType.EVENT_REMINDER,
                scheduled_for=datetime.utcnow() + timedelta(hours=1),
                recipient_user_ids=[],
                title="Test",
                message="This is a test notification"
            )
            notification.validate_data()
    
    def test_notification_due_check(self):
        """Test checking if notification is due."""
        from models.base import TimestampMixin
        
        # Future notification
        future_notification = Notification(
            guild_id="123456789012345678",
            notification_type=NotificationType.EVENT_REMINDER,
            scheduled_for=TimestampMixin.utc_now() + timedelta(hours=1),
            recipient_user_ids=["987654321098765432"],
            title="Future Notification",
            message="This is scheduled for later"
        )
        assert not future_notification.is_due()
        
        # Past notification
        past_notification = Notification(
            guild_id="123456789012345678",
            notification_type=NotificationType.EVENT_REMINDER,
            scheduled_for=TimestampMixin.utc_now() - timedelta(minutes=1),
            recipient_user_ids=["987654321098765432"],
            title="Past Notification",
            message="This should be due"
        )
        assert past_notification.is_due()
    
    def test_delivery_tracking(self):
        """Test delivery attempt tracking."""
        from models.base import TimestampMixin
        
        notification = Notification(
            guild_id="123456789012345678",
            notification_type=NotificationType.EVENT_REMINDER,
            scheduled_for=TimestampMixin.utc_now(),
            recipient_user_ids=["987654321098765432"],
            title="Test Notification",
            message="Test message"
        )
        
        # Add successful delivery
        notification.add_delivery_attempt(
            channel_type=NotificationChannel.DM,
            channel_id="987654321098765432",
            success=True
        )
        
        assert len(notification.deliveries) == 1
        assert notification.deliveries[0].status == NotificationStatus.SENT
        assert notification.status == NotificationStatus.SENT
        
        # Add failed delivery
        notification.add_delivery_attempt(
            channel_type=NotificationChannel.SERVER,
            channel_id="123456789012345678",
            success=False,
            error_message="Channel not found"
        )
        
        assert len(notification.deliveries) == 2
        assert notification.deliveries[1].status == NotificationStatus.FAILED


class TestNotificationTemplate:
    """Test notification template functionality."""
    
    def test_template_rendering(self):
        """Test template rendering with context."""
        template = NotificationTemplate(
            notification_type=NotificationType.EVENT_REMINDER,
            title_template="Event: {event_title}",
            message_template="Don't forget about {event_title} on {event_date}!"
        )
        
        context = {
            "event_title": "Game Night",
            "event_date": "Tomorrow"
        }
        
        rendered = template.render(context)
        
        assert rendered["title"] == "Event: Game Night"
        assert rendered["message"] == "Don't forget about Game Night on Tomorrow!"
    
    def test_template_missing_variable(self):
        """Test template rendering with missing variables."""
        template = NotificationTemplate(
            notification_type=NotificationType.EVENT_REMINDER,
            title_template="Event: {event_title}",
            message_template="Don't forget about {event_title} on {missing_var}!"
        )
        
        context = {"event_title": "Game Night"}
        
        with pytest.raises(ValueError, match="Missing template variable"):
            template.render(context)
    
    def test_default_templates(self):
        """Test that default templates are available."""
        assert NotificationType.EVENT_REMINDER in DEFAULT_TEMPLATES
        assert NotificationType.POLL_REMINDER in DEFAULT_TEMPLATES
        assert NotificationType.EVENT_CANCELLED in DEFAULT_TEMPLATES
        
        # Test rendering a default template
        template = DEFAULT_TEMPLATES[NotificationType.EVENT_REMINDER]
        context = {
            "event_title": "Test Event",
            "event_date": "Tomorrow",
            "event_time": "8:00 PM",
            "selected_game": "Test Game"
        }
        
        rendered = template.render(context)
        assert "Test Event" in rendered["title"]
        assert "Tomorrow" in rendered["message"]


@pytest.mark.asyncio
class TestNotificationManager:
    """Test notification manager functionality."""
    
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
        return NotificationManager(mock_bot, mock_database, event_bus)
    
    async def test_schedule_event_reminder(self, notification_manager, mock_database):
        """Test scheduling an event reminder."""
        # Mock database insert
        mock_result = AsyncMock()
        mock_result.inserted_id = "notification_id"
        mock_database.notifications.insert_one = AsyncMock(return_value=mock_result)
        
        reminder_time = datetime.utcnow() + timedelta(hours=1)
        context_data = {
            "event_title": "Test Event",
            "event_date": "Tomorrow",
            "event_time": "8:00 PM",
            "selected_game": "Test Game"
        }
        
        notification_id = await notification_manager.schedule_event_reminder(
            event_id="event_123",
            guild_id="123456789012345678",
            recipient_user_ids=["987654321098765432"],
            reminder_time=reminder_time,
            context_data=context_data
        )
        
        assert notification_id == "notification_id"
        mock_database.notifications.insert_one.assert_called_once()
    
    async def test_send_immediate_notification(self, notification_manager, mock_database):
        """Test sending an immediate notification."""
        # Mock database insert
        mock_result = AsyncMock()
        mock_result.inserted_id = "notification_id"
        mock_database.notifications.insert_one = AsyncMock(return_value=mock_result)
        
        context_data = {
            "event_title": "Test Event",
            "event_date": "Tomorrow",
            "event_time": "8:00 PM",
            "selected_game": "Test Game"
        }
        
        success = await notification_manager.send_immediate_notification(
            notification_type=NotificationType.EVENT_REMINDER,
            guild_id="123456789012345678",
            recipient_user_ids=["987654321098765432"],
            context_data=context_data
        )
        
        assert success is True
        mock_database.notifications.insert_one.assert_called_once()
    
    async def test_cancel_notifications(self, notification_manager, mock_database):
        """Test cancelling notifications."""
        # Mock database update
        mock_result = MagicMock()
        mock_result.modified_count = 2
        mock_database.notifications.update_many = AsyncMock(return_value=mock_result)
        
        cancelled_count = await notification_manager.cancel_notifications(
            event_id="event_123"
        )
        
        assert cancelled_count == 2
        mock_database.notifications.update_many.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])