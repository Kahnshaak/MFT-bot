"""
Tests for Discord scheduled events integration.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, date, time, timezone, timedelta

import discord

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.discord_events_manager import DiscordEventsManager, DiscordEventSyncStatus
from core.event_bus import EventBus, EventType
from models.event import Event, EventState, EventSchedule, RSVPStatus
from utils.exceptions import ErrorCode


@pytest.fixture
def mock_bot():
    """Create a mock bot instance."""
    bot = MagicMock()
    bot.get_guild.return_value = None
    return bot


@pytest.fixture
def mock_database():
    """Create a mock database manager."""
    db = MagicMock()
    db.events = MagicMock()
    return db


@pytest.fixture
def event_bus():
    """Create an event bus instance."""
    return EventBus()


@pytest.fixture
def discord_events_manager(mock_bot, event_bus, mock_database):
    """Create a Discord events manager instance."""
    manager = DiscordEventsManager(mock_bot, event_bus, mock_database)
    # Stop background tasks for testing
    manager.sync_rsvps_task.cancel()
    manager.cleanup_failed_events_task.cancel()
    return manager


@pytest.fixture
def sample_event():
    """Create a sample scheduled event."""
    event = Event(
        guild_id="123456789",
        title="Test Game Night",
        description="A test game night event",
        creator_id="987654321",
        state=EventState.SCHEDULED
    )
    
    # Set up schedule
    event.schedule = EventSchedule(
        selected_date=date.today() + timedelta(days=1),
        selected_time=time(19, 0),  # 7 PM
        timezone="UTC",
        duration_minutes=180
    )
    
    return event


class TestDiscordEventsManager:
    """Test cases for Discord events manager."""
    
    @pytest.mark.asyncio
    async def test_create_discord_event_success(self, discord_events_manager, sample_event):
        """Test successful Discord event creation."""
        # Mock guild and Discord event
        mock_guild = MagicMock()
        mock_discord_event = MagicMock()
        mock_discord_event.id = 555666777
        
        with patch('core.discord_events_manager.get_guild_safely', return_value=mock_guild):
            mock_guild.create_scheduled_event = AsyncMock(return_value=mock_discord_event)
            discord_events_manager._update_event_discord_id = AsyncMock()
            
            # Create Discord event
            result = await discord_events_manager.create_discord_event(sample_event)
            
            # Verify result
            assert result == "555666777"
            assert discord_events_manager.sync_status[str(sample_event.id)] == DiscordEventSyncStatus.SYNCED
            
            # Verify Discord event was created with correct parameters
            mock_guild.create_scheduled_event.assert_called_once()
            call_args = mock_guild.create_scheduled_event.call_args[1]
            assert call_args['name'] == sample_event.title
            assert call_args['privacy_level'] == discord.ScheduledEventPrivacyLevel.guild_only
            assert call_args['entity_type'] == discord.ScheduledEventLocationType.external
    
    @pytest.mark.asyncio
    async def test_create_discord_event_guild_not_found(self, discord_events_manager, sample_event):
        """Test Discord event creation when guild is not found."""
        with patch('core.discord_events_manager.get_guild_safely', return_value=None):
            with pytest.raises(Exception) as exc_info:
                await discord_events_manager.create_discord_event(sample_event)
            
            assert "Guild" in str(exc_info.value)
            assert "not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_discord_event_unscheduled(self, discord_events_manager):
        """Test Discord event creation for unscheduled event."""
        unscheduled_event = Event(
            guild_id="123456789",
            title="Unscheduled Event",
            creator_id="987654321",
            state=EventState.DRAFT
        )
        
        with pytest.raises(Exception) as exc_info:
            await discord_events_manager.create_discord_event(unscheduled_event)
        
        assert "unscheduled" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_update_discord_event_success(self, discord_events_manager, sample_event):
        """Test successful Discord event update."""
        sample_event.discord_event_id = "555666777"
        
        # Mock guild and Discord event
        mock_guild = MagicMock()
        mock_discord_event = MagicMock()
        mock_discord_event.name = "Old Name"
        mock_discord_event.description = "Old Description"
        mock_discord_event.edit = AsyncMock()
        
        with patch('core.discord_events_manager.get_guild_safely', return_value=mock_guild):
            with patch('core.discord_events_manager.get_scheduled_event_safely', return_value=mock_discord_event):
                
                # Update Discord event
                result = await discord_events_manager.update_discord_event(sample_event)
                
                # Verify result
                assert result is True
                mock_discord_event.edit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cancel_discord_event_success(self, discord_events_manager, sample_event):
        """Test successful Discord event cancellation."""
        sample_event.discord_event_id = "555666777"
        
        # Mock guild and Discord event
        mock_guild = MagicMock()
        mock_discord_event = MagicMock()
        mock_discord_event.cancel = AsyncMock()
        
        with patch('core.discord_events_manager.get_guild_safely', return_value=mock_guild):
            with patch('core.discord_events_manager.get_scheduled_event_safely', return_value=mock_discord_event):
                
                # Cancel Discord event
                result = await discord_events_manager.cancel_discord_event(sample_event)
                
                # Verify result
                assert result is True
                mock_discord_event.cancel.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_sync_rsvps_from_discord(self, discord_events_manager, sample_event):
        """Test RSVP synchronization from Discord event."""
        sample_event.discord_event_id = "555666777"
        
        # Mock guild, Discord event, and subscribers
        mock_guild = MagicMock()
        mock_discord_event = MagicMock()
        
        # Mock subscribers
        mock_user1 = MagicMock()
        mock_user1.id = 111111111
        mock_user2 = MagicMock()
        mock_user2.id = 222222222
        
        async def mock_subscribers():
            for user in [mock_user1, mock_user2]:
                yield user
        
        mock_discord_event.subscribers.return_value = mock_subscribers()
        
        with patch('core.discord_events_manager.get_guild_safely', return_value=mock_guild):
            with patch('core.discord_events_manager.get_scheduled_event_safely', return_value=mock_discord_event):
                discord_events_manager._save_event = AsyncMock()
                
                # Sync RSVPs
                result = await discord_events_manager.sync_rsvps_from_discord(sample_event)
                
                # Verify result
                assert result == 2
                assert "111111111" in sample_event.rsvp_data
                assert "222222222" in sample_event.rsvp_data
                assert sample_event.rsvp_data["111111111"].status == RSVPStatus.YES
                assert sample_event.rsvp_data["222222222"].status == RSVPStatus.YES
    
    def test_calculate_event_datetime(self, discord_events_manager, sample_event):
        """Test event datetime calculation."""
        result = discord_events_manager._calculate_event_datetime(sample_event)
        
        # Should combine date and time with timezone
        assert result.date() == sample_event.schedule.selected_date
        assert result.time() == sample_event.schedule.selected_time
        assert result.tzinfo is not None
    
    def test_format_event_description(self, discord_events_manager, sample_event):
        """Test event description formatting."""
        # Add some RSVP data
        sample_event.add_rsvp("111111111", RSVPStatus.YES)
        sample_event.add_rsvp("222222222", RSVPStatus.MAYBE)
        
        result = discord_events_manager._format_event_description(sample_event)
        
        assert sample_event.description in result
        assert "1 Yes" in result
        assert "1 Maybe" in result
        assert "Game Night Bot" in result
    
    def test_generate_calendar_export(self, discord_events_manager, sample_event):
        """Test calendar export generation."""
        events = [sample_event]
        
        result = discord_events_manager.generate_calendar_export(events)
        
        # Should be valid iCalendar format
        assert result.startswith("BEGIN:VCALENDAR")
        assert result.endswith("END:VCALENDAR")
        assert "BEGIN:VEVENT" in result
        assert "END:VEVENT" in result
        assert sample_event.title in result
    
    def test_escape_ics_text(self, discord_events_manager):
        """Test iCalendar text escaping."""
        test_text = "Test, with; special\ncharacters"
        result = discord_events_manager._escape_ics_text(test_text)
        
        assert "\\," in result
        assert "\\;" in result
        assert "\\n" in result
    
    @pytest.mark.asyncio
    async def test_event_scheduled_handler(self, discord_events_manager, sample_event, mock_database):
        """Test handling of EVENT_SCHEDULED events."""
        # Mock database response
        mock_database.events.find_one = AsyncMock(return_value=sample_event.model_dump(by_alias=True))
        discord_events_manager.create_discord_event = AsyncMock(return_value="555666777")
        
        # Create event data
        event_data = MagicMock()
        event_data.data = {'event_id': str(sample_event.id)}
        
        # Handle the event
        await discord_events_manager._on_event_scheduled(event_data)
        
        # Verify Discord event creation was attempted
        discord_events_manager.create_discord_event.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_event_cancelled_handler(self, discord_events_manager, sample_event, mock_database):
        """Test handling of EVENT_CANCELLED events."""
        sample_event.discord_event_id = "555666777"
        
        # Mock database response
        mock_database.events.find_one = AsyncMock(return_value=sample_event.model_dump(by_alias=True))
        discord_events_manager.cancel_discord_event = AsyncMock(return_value=True)
        
        # Create event data
        event_data = MagicMock()
        event_data.data = {'event_id': str(sample_event.id)}
        
        # Handle the event
        await discord_events_manager._on_event_cancelled(event_data)
        
        # Verify Discord event cancellation was attempted
        discord_events_manager.cancel_discord_event.assert_called_once()


class TestDiscordAPIUtils:
    """Test cases for Discord API utilities."""
    
    @pytest.mark.asyncio
    async def test_safe_discord_request_success(self):
        """Test successful Discord API request."""
        from utils.discord_api_utils import safe_discord_request
        
        mock_func = AsyncMock(return_value="success")
        
        result = await safe_discord_request(mock_func, "arg1", kwarg1="value1")
        
        assert result == "success"
        mock_func.assert_called_once_with("arg1", kwarg1="value1")
    
    @pytest.mark.asyncio
    async def test_safe_discord_request_rate_limit(self):
        """Test Discord API request with rate limiting."""
        from utils.discord_api_utils import safe_discord_request
        
        # Mock rate limited response
        rate_limit_error = discord.HTTPException(MagicMock(), "Rate limited")
        rate_limit_error.status = 429
        rate_limit_error.retry_after = 0.1
        
        mock_func = AsyncMock(side_effect=[rate_limit_error, "success"])
        
        with patch('asyncio.sleep') as mock_sleep:
            result = await safe_discord_request(mock_func, "arg1")
            
            assert result == "success"
            assert mock_func.call_count == 2
            mock_sleep.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_guild_safely_success(self):
        """Test safe guild retrieval."""
        from utils.discord_api_utils import get_guild_safely
        
        mock_bot = MagicMock()
        mock_guild = MagicMock()
        mock_bot.get_guild.return_value = mock_guild
        
        result = await get_guild_safely(mock_bot, "123456789")
        
        assert result == mock_guild
        mock_bot.get_guild.assert_called_once_with(123456789)
    
    @pytest.mark.asyncio
    async def test_get_scheduled_event_safely_success(self):
        """Test safe scheduled event retrieval."""
        from utils.discord_api_utils import get_scheduled_event_safely
        
        mock_guild = MagicMock()
        mock_event = MagicMock()
        mock_event.id = 555666777
        mock_guild.scheduled_events = [mock_event]
        
        result = await get_scheduled_event_safely(mock_guild, "555666777")
        
        assert result == mock_event