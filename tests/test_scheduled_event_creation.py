"""
Tests for Discord Scheduled Event creation (Task 11).
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.models.event import Event


@pytest.fixture
def mock_bot():
    """Create a mock bot instance."""
    bot = MagicMock()
    bot.database = MagicMock()
    bot.database.update_one = AsyncMock()
    bot.wait_until_ready = AsyncMock()
    return bot


@pytest.fixture
def mock_guild():
    """Create a mock Discord guild."""
    guild = MagicMock()
    guild.id = 123456789
    
    # Mock scheduled event
    mock_scheduled_event = MagicMock()
    mock_scheduled_event.id = 999888777
    
    guild.create_scheduled_event = AsyncMock(return_value=mock_scheduled_event)
    
    return guild


@pytest.fixture
def sample_event():
    """Create a sample event instance."""
    now = datetime.utcnow()
    event_id = ObjectId()
    
    event_data = {
        "_id": event_id,
        "guild_id": "123456789",
        "channel_id": "987654321",
        "message_id": "111222333",
        "creator_id": "555666777",
        "title": "Test Game Night",
        "created_at": now - timedelta(days=7),
        "expires_at": now - timedelta(minutes=10),
        "status": "active",
        "date_votes": {
            "2025-10-15": ["user1", "user2", "user3"],
            "2025-10-16": ["user4", "user5"]
        },
        "time_votes": {
            "17:00": ["user1", "user2"],
            "18:00": ["user3", "user4", "user5"]
        },
        "winning_date": None,
        "winning_time": None,
        "discord_event_id": None
    }
    
    return Event(**event_data)


@pytest.mark.asyncio
async def test_create_scheduled_event_success(mock_bot, mock_guild, sample_event):
    """Test successful creation of Discord Scheduled Event."""
    from src.cogs.events import EventsCog
    import discord
    
    # Setup bot to return mock guild
    mock_bot.get_guild = MagicMock(return_value=mock_guild)
    
    # Create cog instance
    cog = EventsCog(mock_bot)
    cog.check_expired_polls.cancel()
    
    # Call the method
    winning_date = "2025-10-15"
    winning_time = "18:00"
    
    await cog._create_scheduled_event(sample_event, winning_date, winning_time)
    
    # Verify guild.create_scheduled_event was called with correct parameters
    mock_guild.create_scheduled_event.assert_called_once()
    call_kwargs = mock_guild.create_scheduled_event.call_args[1]
    
    assert call_kwargs["name"] == "Test Game Night"
    assert call_kwargs["location"] == "Discord"
    assert call_kwargs["privacy_level"] == discord.ScheduledEventPrivacyLevel.guild_only
    
    # Verify the start_time is correct
    expected_datetime = datetime(2025, 10, 15, 18, 0)
    assert call_kwargs["start_time"] == expected_datetime
    
    # Verify database was updated with discord_event_id and status
    mock_bot.database.update_one.assert_called_once()
    update_call = mock_bot.database.update_one.call_args
    
    assert update_call[0][0] == "events"
    assert update_call[0][1] == {"_id": sample_event.id}
    
    update_data = update_call[0][2]["$set"]
    assert update_data["winning_date"] == winning_date
    assert update_data["winning_time"] == winning_time
    assert update_data["discord_event_id"] == "999888777"
    assert update_data["status"] == "scheduled"


@pytest.mark.asyncio
async def test_create_scheduled_event_combines_datetime_correctly(mock_bot, mock_guild, sample_event):
    """Test that date and time are correctly combined into datetime object."""
    from src.cogs.events import EventsCog
    
    # Setup bot to return mock guild
    mock_bot.get_guild = MagicMock(return_value=mock_guild)
    
    # Create cog instance
    cog = EventsCog(mock_bot)
    cog.check_expired_polls.cancel()
    
    # Test various date/time combinations
    test_cases = [
        ("2025-10-15", "17:00", datetime(2025, 10, 15, 17, 0)),
        ("2025-10-31", "23:00", datetime(2025, 10, 31, 23, 0)),
        ("2025-11-01", "19:30", datetime(2025, 11, 1, 19, 30)),
    ]
    
    for winning_date, winning_time, expected_datetime in test_cases:
        mock_guild.create_scheduled_event.reset_mock()
        mock_bot.database.update_one.reset_mock()
        
        await cog._create_scheduled_event(sample_event, winning_date, winning_time)
        
        # Verify the start_time is correct
        call_kwargs = mock_guild.create_scheduled_event.call_args[1]
        assert call_kwargs["start_time"] == expected_datetime, \
            f"Failed for {winning_date} {winning_time}"


@pytest.mark.asyncio
async def test_create_scheduled_event_guild_not_found(mock_bot, sample_event):
    """Test handling when guild is not found."""
    from src.cogs.events import EventsCog
    
    # Setup bot to return None for guild
    mock_bot.get_guild = MagicMock(return_value=None)
    
    # Create cog instance
    cog = EventsCog(mock_bot)
    cog.check_expired_polls.cancel()
    
    # Call the method
    winning_date = "2025-10-15"
    winning_time = "18:00"
    
    await cog._create_scheduled_event(sample_event, winning_date, winning_time)
    
    # Verify database was updated with winning date/time but status is "expired"
    mock_bot.database.update_one.assert_called_once()
    update_call = mock_bot.database.update_one.call_args
    
    update_data = update_call[0][2]["$set"]
    assert update_data["winning_date"] == winning_date
    assert update_data["winning_time"] == winning_time
    assert update_data["status"] == "expired"
    assert "discord_event_id" not in update_data


@pytest.mark.asyncio
async def test_create_scheduled_event_permission_error(mock_bot, mock_guild, sample_event):
    """Test handling when bot lacks permission to create scheduled events."""
    from src.cogs.events import EventsCog
    import discord
    
    # Setup guild to raise Forbidden error
    mock_guild.create_scheduled_event = AsyncMock(
        side_effect=discord.Forbidden(MagicMock(), "Missing permissions")
    )
    
    # Setup bot to return mock guild
    mock_bot.get_guild = MagicMock(return_value=mock_guild)
    
    # Create cog instance
    cog = EventsCog(mock_bot)
    cog.check_expired_polls.cancel()
    
    # Call the method
    winning_date = "2025-10-15"
    winning_time = "18:00"
    
    await cog._create_scheduled_event(sample_event, winning_date, winning_time)
    
    # Verify database was updated with winning date/time but status is "expired"
    mock_bot.database.update_one.assert_called_once()
    update_call = mock_bot.database.update_one.call_args
    
    update_data = update_call[0][2]["$set"]
    assert update_data["winning_date"] == winning_date
    assert update_data["winning_time"] == winning_time
    assert update_data["status"] == "expired"
    assert "discord_event_id" not in update_data


@pytest.mark.asyncio
async def test_create_scheduled_event_generic_error(mock_bot, mock_guild, sample_event):
    """Test handling of generic errors during scheduled event creation."""
    from src.cogs.events import EventsCog
    
    # Setup guild to raise generic error
    mock_guild.create_scheduled_event = AsyncMock(
        side_effect=Exception("Something went wrong")
    )
    
    # Setup bot to return mock guild
    mock_bot.get_guild = MagicMock(return_value=mock_guild)
    
    # Create cog instance
    cog = EventsCog(mock_bot)
    cog.check_expired_polls.cancel()
    
    # Call the method
    winning_date = "2025-10-15"
    winning_time = "18:00"
    
    await cog._create_scheduled_event(sample_event, winning_date, winning_time)
    
    # Verify database was updated with winning date/time but status is "expired"
    mock_bot.database.update_one.assert_called_once()
    update_call = mock_bot.database.update_one.call_args
    
    update_data = update_call[0][2]["$set"]
    assert update_data["winning_date"] == winning_date
    assert update_data["winning_time"] == winning_time
    assert update_data["status"] == "expired"
    assert "discord_event_id" not in update_data


@pytest.mark.asyncio
async def test_create_scheduled_event_with_special_characters_in_title(mock_bot, mock_guild):
    """Test that event titles with special characters are handled correctly."""
    from src.cogs.events import EventsCog
    
    # Create event with special characters in title
    now = datetime.utcnow()
    event_data = {
        "_id": ObjectId(),
        "guild_id": "123456789",
        "channel_id": "987654321",
        "message_id": "111222333",
        "creator_id": "555666777",
        "title": "Game Night: D&D Session #5 (Epic!)",
        "created_at": now - timedelta(days=7),
        "expires_at": now - timedelta(minutes=10),
        "status": "active",
        "date_votes": {"2025-10-15": ["user1"]},
        "time_votes": {"18:00": ["user1"]},
        "winning_date": None,
        "winning_time": None,
        "discord_event_id": None
    }
    event = Event(**event_data)
    
    # Setup bot to return mock guild
    mock_bot.get_guild = MagicMock(return_value=mock_guild)
    
    # Create cog instance
    cog = EventsCog(mock_bot)
    cog.check_expired_polls.cancel()
    
    # Call the method
    await cog._create_scheduled_event(event, "2025-10-15", "18:00")
    
    # Verify the title was passed correctly
    call_kwargs = mock_guild.create_scheduled_event.call_args[1]
    assert call_kwargs["name"] == "Game Night: D&D Session #5 (Epic!)"
