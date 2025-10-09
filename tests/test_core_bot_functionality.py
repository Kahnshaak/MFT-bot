"""
Test core bot functionality after cleanup.
Tests the essential features to ensure they work correctly.
"""

import asyncio
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, date, time

# Add src directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from models.event import Event, EventState, Poll, RSVPStatus
from models.user import User, GameInterest
from models.recurring import RecurringSchedule, ScheduleStatus
from core.event_bus import EventBus
from core.notification_manager import NotificationManager
from core.poll_manager import PollManager
from core.security_manager import SecurityManager
from core.validation_manager import ValidationManager
from database.manager import DatabaseManager


class TestCoreEventFunctionality:
    """Test event creation, polling, and scheduling workflows."""
    
    @pytest.fixture
    def mock_database(self):
        """Mock database manager."""
        db = AsyncMock(spec=DatabaseManager)
        db.is_connected.return_value = True
        return db
    
    @pytest.fixture
    def event_bus(self):
        """Create event bus instance."""
        return EventBus()
    
    @pytest.fixture
    def poll_manager(self, event_bus, mock_database):
        """Create poll manager instance."""
        return PollManager(event_bus, mock_database)
    
    def test_event_creation(self):
        """Test basic event creation."""
        event = Event(
            guild_id="123456789012345678",
            title="Test Game Night",
            description="A test event for validation",
            creator_id="987654321098765432"
        )
        
        assert event.guild_id == "123456789012345678"
        assert event.title == "Test Game Night"
        assert event.description == "A test event for validation"
        assert event.creator_id == "987654321098765432"
        assert event.state == EventState.DRAFT
        assert len(event.polls) == 0
        assert len(event.rsvps) == 0
    
    def test_event_state_management(self):
        """Test event state transitions."""
        event = Event(
            guild_id="123456789012345678",
            title="Test Event",
            creator_id="987654321098765432"
        )
        
        # Test initial state
        assert event.state == EventState.DRAFT
        
        # Test state transitions
        event.state = EventState.DATE_POLLING
        assert event.state == EventState.DATE_POLLING
        
        event.state = EventState.TIME_POLLING
        assert event.state == EventState.TIME_POLLING
        
        event.state = EventState.GAME_POLLING
        assert event.state == EventState.GAME_POLLING
        
        event.state = EventState.SCHEDULED
        assert event.state == EventState.SCHEDULED
    
    def test_rsvp_functionality(self):
        """Test RSVP functionality."""
        event = Event(
            guild_id="123456789012345678",
            title="Test Event",
            creator_id="987654321098765432"
        )
        
        # Test adding RSVPs
        user_id = "111111111111111111"
        event.add_rsvp(user_id, RSVPStatus.YES)
        
        assert user_id in event.rsvps
        assert event.rsvps[user_id].status == RSVPStatus.YES
        
        # Test updating RSVP
        event.add_rsvp(user_id, RSVPStatus.MAYBE)
        assert event.rsvps[user_id].status == RSVPStatus.MAYBE
    
    @pytest.mark.asyncio
    async def test_poll_creation(self, poll_manager):
        """Test poll creation and management."""
        event = Event(
            guild_id="123456789012345678",
            title="Test Event",
            creator_id="987654321098765432"
        )
        
        # Create a simple poll
        poll_title = "Choose a date"
        date_options = [
            "December 15, 2024",
            "December 16, 2024", 
            "December 17, 2024"
        ]
        
        poll = await poll_manager.create_poll(event, poll_title, date_options)
        
        assert poll.title == poll_title
        assert len(poll.options) == 3
        assert poll.is_active is True
        assert len(event.polls) == 1
    
    @pytest.mark.asyncio
    async def test_event_bus_functionality(self, event_bus):
        """Test event bus for decoupling components."""
        received_events = []
        
        async def test_handler(event_data):
            received_events.append(event_data)
        
        # Subscribe to events
        await event_bus.subscribe("test_event", test_handler)
        
        # Emit event
        test_data = {"message": "test"}
        await event_bus.emit("test_event", test_data)
        
        # Verify event was received
        assert len(received_events) == 1
        assert received_events[0].data == test_data


class TestUserProfileAndPreferences:
    """Test user profile and preference management."""
    
    def test_user_creation(self):
        """Test basic user creation."""
        user = User(
            user_id="123456789012345678",
            guild_id="987654321098765432"
        )
        
        assert user.user_id == "123456789012345678"
        assert user.guild_id == "987654321098765432"
        assert user.timezone == "UTC"
        assert user.event_reminders is True
        assert user.game_pings is True
        assert len(user.game_interests) == 0
    
    def test_game_interest_management(self):
        """Test game interest functionality."""
        user = User(
            user_id="123456789012345678",
            guild_id="987654321098765432"
        )
        
        # Add game interest
        result = user.add_game_interest("Dungeons & Dragons", True)
        assert result is True
        assert len(user.game_interests) == 1
        assert user.game_interests[0].game_name == "Dungeons & Dragons"
        assert user.game_interests[0].notification_enabled is True
        
        # Try to add duplicate
        result = user.add_game_interest("Dungeons & Dragons", False)
        assert result is False
        assert len(user.game_interests) == 1
        
        # Remove game interest
        result = user.remove_game_interest("Dungeons & Dragons")
        assert result is True
        assert len(user.game_interests) == 0
        
        # Try to remove non-existent
        result = user.remove_game_interest("Non-existent Game")
        assert result is False
    
    def test_user_preferences(self):
        """Test user preference management."""
        user = User(
            user_id="123456789012345678",
            guild_id="987654321098765432",
            timezone="America/New_York",
            event_reminders=False,
            game_pings=False
        )
        
        assert user.timezone == "America/New_York"
        assert user.event_reminders is False
        assert user.game_pings is False


class TestRecurringEventAutomation:
    """Test recurring event automation."""
    
    def test_recurring_schedule_creation(self):
        """Test creating recurring schedules."""
        schedule = RecurringSchedule(
            guild_id="123456789012345678",
            name="Weekly Game Night",
            description="Every Friday game night",
            creator_id="987654321098765432",
            day_of_week=4,  # Friday
            trigger_time=time(19, 0),  # 7 PM
            event_title="Friday Game Night",
            event_description="Weekly game night event"
        )
        
        assert schedule.guild_id == "123456789012345678"
        assert schedule.name == "Weekly Game Night"
        assert schedule.day_of_week == 4
        assert schedule.trigger_time == time(19, 0)
        assert schedule.status == ScheduleStatus.ACTIVE
        assert schedule.event_title == "Friday Game Night"
    
    def test_schedule_status_management(self):
        """Test schedule status changes."""
        schedule = RecurringSchedule(
            guild_id="123456789012345678",
            name="Test Schedule",
            creator_id="987654321098765432",
            day_of_week=0,
            trigger_time=time(18, 0),
            event_title="Test Event"
        )
        
        # Test initial status
        assert schedule.status == ScheduleStatus.ACTIVE
        
        # Test status changes
        schedule.status = ScheduleStatus.PAUSED
        assert schedule.status == ScheduleStatus.PAUSED
        
        schedule.status = ScheduleStatus.DISABLED
        assert schedule.status == ScheduleStatus.DISABLED


class TestNotificationSystem:
    """Test notification and reminder functionality."""
    
    @pytest.fixture
    def mock_database(self):
        """Mock database manager."""
        db = AsyncMock(spec=DatabaseManager)
        db.is_connected.return_value = True
        return db
    
    @pytest.fixture
    def event_bus(self):
        """Create event bus instance."""
        return EventBus()
    
    @pytest.fixture
    def notification_manager(self, event_bus, mock_database):
        """Create notification manager instance."""
        return NotificationManager(event_bus, mock_database)
    
    @pytest.mark.asyncio
    async def test_notification_scheduling(self, notification_manager):
        """Test scheduling notifications."""
        event_id = "test_event_123"
        remind_at = datetime.now()
        
        # Mock the database operations
        notification_manager.db.notifications.insert_one = AsyncMock()
        
        await notification_manager.schedule_reminder(event_id, remind_at)
        
        # Verify database was called
        notification_manager.db.notifications.insert_one.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_notification_sending(self, notification_manager):
        """Test sending notifications."""
        user_id = "123456789012345678"
        message = "Test notification message"
        
        # Mock the notification sending
        notification_manager.db.notifications.insert_one = AsyncMock()
        
        await notification_manager.send_notification(user_id, message)
        
        # Verify database was called
        notification_manager.db.notifications.insert_one.assert_called_once()


class TestSecurityAndValidation:
    """Test security and validation functionality."""
    
    @pytest.fixture
    def security_manager(self):
        """Create security manager instance."""
        from config.settings import Settings
        settings = Settings()
        return SecurityManager(settings)
    
    @pytest.fixture
    def validation_manager(self):
        """Create validation manager instance."""
        return ValidationManager()
    
    def test_input_validation(self, validation_manager):
        """Test input validation."""
        # Test valid inputs
        assert validation_manager.validate_string("Valid Title", min_length=3, max_length=100) == "Valid Title"
        assert validation_manager.validate_discord_id("123456789012345678") == "123456789012345678"
        
        # Test invalid inputs
        with pytest.raises(Exception):
            validation_manager.validate_string("", min_length=3)
        
        with pytest.raises(Exception):
            validation_manager.validate_discord_id("invalid_id")
    
    def test_permission_validation(self, security_manager):
        """Test permission validation."""
        # Mock user with admin permissions
        mock_user = MagicMock()
        mock_user.guild_permissions.administrator = True
        
        # Test admin permission
        result = security_manager.has_permission(mock_user, "admin")
        assert result is True
        
        # Mock user without admin permissions
        mock_user.guild_permissions.administrator = False
        result = security_manager.has_permission(mock_user, "admin")
        assert result is False


class TestIntegrationWorkflows:
    """Test complete user workflows."""
    
    @pytest.mark.asyncio
    async def test_complete_event_workflow(self):
        """Test complete event creation to scheduling workflow."""
        # Create event
        event = Event(
            guild_id="123456789012345678",
            title="Integration Test Event",
            description="Testing complete workflow",
            creator_id="987654321098765432"
        )
        
        # Verify initial state
        assert event.state == EventState.DRAFT
        
        # Simulate state progression
        event.state = EventState.DATE_POLLING
        assert event.state == EventState.DATE_POLLING
        
        event.state = EventState.TIME_POLLING
        assert event.state == EventState.TIME_POLLING
        
        event.state = EventState.GAME_POLLING
        assert event.state == EventState.GAME_POLLING
        
        # Add some RSVPs
        event.add_rsvp("user1", RSVPStatus.YES)
        event.add_rsvp("user2", RSVPStatus.MAYBE)
        event.add_rsvp("user3", RSVPStatus.NO)
        
        assert len(event.rsvps) == 3
        
        # Schedule event
        event.state = EventState.SCHEDULED
        event.scheduled_date = date(2024, 12, 15)
        event.scheduled_time = time(19, 0)
        
        assert event.state == EventState.SCHEDULED
        assert event.scheduled_date == date(2024, 12, 15)
        assert event.scheduled_time == time(19, 0)
    
    @pytest.mark.asyncio
    async def test_user_game_interest_workflow(self):
        """Test user game interest registration workflow."""
        user = User(
            user_id="123456789012345678",
            guild_id="987654321098765432"
        )
        
        # Register interests
        games = ["Dungeons & Dragons", "Pathfinder", "Board Games", "Video Games"]
        
        for game in games:
            result = user.add_game_interest(game, True)
            assert result is True
        
        assert len(user.game_interests) == 4
        
        # Verify all games are registered
        registered_games = [interest.game_name for interest in user.game_interests]
        for game in games:
            assert game in registered_games
        
        # Remove some interests
        user.remove_game_interest("Video Games")
        assert len(user.game_interests) == 3
        
        # Verify removal
        registered_games = [interest.game_name for interest in user.game_interests]
        assert "Video Games" not in registered_games


if __name__ == "__main__":
    pytest.main([__file__, "-v"])