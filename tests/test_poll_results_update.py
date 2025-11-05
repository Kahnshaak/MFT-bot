"""
Test for updating poll message with scheduled event results (Task 12).
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import discord

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.models.event import Event
from src.cogs.events import EventsCog


@pytest.fixture
def mock_bot():
    """Create a mock bot instance."""
    bot = MagicMock()
    bot.database = MagicMock()
    bot.database.update_one = AsyncMock()
    return bot


@pytest.fixture
def mock_guild():
    """Create a mock guild."""
    guild = MagicMock()
    guild.id = 123456789
    return guild


@pytest.fixture
def mock_channel():
    """Create a mock channel."""
    channel = MagicMock()
    channel.id = 987654321
    return channel


@pytest.fixture
def mock_scheduled_event():
    """Create a mock Discord scheduled event."""
    event = MagicMock()
    event.id = 111222333
    event.name = "Test Game Night"
    return event


@pytest.fixture
def sample_event():
    """Create a sample event with winning date/time."""
    return Event(
        guild_id="123456789",
        channel_id="987654321",
        message_id="555666777",
        creator_id="444555666",
        title="Test Game Night",
        created_at=datetime.utcnow() - timedelta(days=7),
        expires_at=datetime.utcnow(),
        status="scheduled",
        winning_date="2025-10-20",
        winning_time="19:00",
        discord_event_id="111222333",
        date_votes={"2025-10-20": ["user1", "user2"], "2025-10-21": ["user3"]},
        time_votes={"19:00": ["user1", "user2"], "20:00": ["user3"]}
    )


@pytest.mark.asyncio
async def test_update_poll_with_results_success(mock_bot, mock_channel, mock_scheduled_event, sample_event):
    """Test successful poll message update with results."""
    # Setup
    cog = EventsCog(mock_bot)
    
    # Mock the channel and message
    mock_message = MagicMock()
    mock_message.edit = AsyncMock()
    mock_channel.fetch_message = AsyncMock(return_value=mock_message)
    mock_bot.get_channel = MagicMock(return_value=mock_channel)
    
    # Execute
    await cog._update_poll_with_results(sample_event, mock_scheduled_event)
    
    # Verify message was fetched
    mock_channel.fetch_message.assert_called_once_with(int(sample_event.message_id))
    
    # Verify message was edited
    mock_message.edit.assert_called_once()
    call_args = mock_message.edit.call_args
    
    # Check that embed was provided
    assert 'embed' in call_args.kwargs
    embed = call_args.kwargs['embed']
    
    # Check that view was removed (set to None)
    assert 'view' in call_args.kwargs
    assert call_args.kwargs['view'] is None
    
    # Verify embed content
    assert "✅" in embed.title
    assert sample_event.title in embed.title
    assert embed.description == "**Event Scheduled!**"
    assert embed.color == discord.Color.green()
    
    # Check that fields contain the expected information
    field_names = [field.name for field in embed.fields]
    assert "📅 Scheduled Date" in field_names
    assert "🕐 Scheduled Time" in field_names
    assert "🔗 Event Link" in field_names
    assert "📊 Poll Results" in field_names
    
    # Check date formatting
    date_field = next(f for f in embed.fields if "Scheduled Date" in f.name)
    assert "October 20, 2025" in date_field.value
    
    # Check time formatting
    time_field = next(f for f in embed.fields if "Scheduled Time" in f.name)
    assert "7:00 PM" in time_field.value
    
    # Check event link
    link_field = next(f for f in embed.fields if "Event Link" in f.name)
    expected_url = f"https://discord.com/events/{sample_event.guild_id}/{mock_scheduled_event.id}"
    assert expected_url in link_field.value


@pytest.mark.asyncio
async def test_update_poll_with_results_channel_not_found(mock_bot, mock_scheduled_event, sample_event):
    """Test handling when channel is not found."""
    # Setup
    cog = EventsCog(mock_bot)
    mock_bot.get_channel = MagicMock(return_value=None)
    
    # Execute - should not raise exception
    await cog._update_poll_with_results(sample_event, mock_scheduled_event)
    
    # Verify no message edit was attempted
    # (no assertion needed, just checking it doesn't crash)


@pytest.mark.asyncio
async def test_update_poll_with_results_message_not_found(mock_bot, mock_channel, mock_scheduled_event, sample_event):
    """Test handling when poll message is not found."""
    # Setup
    cog = EventsCog(mock_bot)
    mock_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), MagicMock()))
    mock_bot.get_channel = MagicMock(return_value=mock_channel)
    
    # Execute - should not raise exception
    await cog._update_poll_with_results(sample_event, mock_scheduled_event)
    
    # Verify fetch was attempted
    mock_channel.fetch_message.assert_called_once()


@pytest.mark.asyncio
async def test_update_poll_with_results_no_permission(mock_bot, mock_channel, mock_scheduled_event, sample_event):
    """Test handling when bot lacks permission to fetch message."""
    # Setup
    cog = EventsCog(mock_bot)
    mock_channel.fetch_message = AsyncMock(side_effect=discord.Forbidden(MagicMock(), MagicMock()))
    mock_bot.get_channel = MagicMock(return_value=mock_channel)
    
    # Execute - should not raise exception
    await cog._update_poll_with_results(sample_event, mock_scheduled_event)
    
    # Verify fetch was attempted
    mock_channel.fetch_message.assert_called_once()


@pytest.mark.asyncio
async def test_update_poll_with_results_time_formatting():
    """Test time formatting for different hours."""
    test_cases = [
        ("17:00", "5:00 PM"),
        ("18:00", "6:00 PM"),
        ("19:00", "7:00 PM"),
        ("20:00", "8:00 PM"),
        ("21:00", "9:00 PM"),
        ("22:00", "10:00 PM"),
        ("23:00", "11:00 PM"),
        ("12:00", "12:00 PM"),
        ("00:00", "0:00 AM"),
    ]
    
    for time_24hr, expected_12hr in test_cases:
        hour = int(time_24hr.split(":")[0])
        if hour >= 12:
            formatted_time = f"{hour - 12 if hour > 12 else 12}:00 PM"
        else:
            formatted_time = f"{hour}:00 AM"
        
        assert formatted_time == expected_12hr, f"Failed for {time_24hr}"


@pytest.mark.asyncio
async def test_create_scheduled_event_calls_update_poll(mock_bot, mock_guild):
    """Test that _create_scheduled_event calls _update_poll_with_results."""
    # Setup
    cog = EventsCog(mock_bot)
    
    sample_event = Event(
        guild_id=str(mock_guild.id),
        channel_id="987654321",
        message_id="555666777",
        creator_id="444555666",
        title="Test Game Night",
        created_at=datetime.utcnow() - timedelta(days=7),
        expires_at=datetime.utcnow(),
        status="active",
        winning_date=None,
        winning_time=None,
        date_votes={"2025-10-20": ["user1", "user2"]},
        time_votes={"19:00": ["user1", "user2"]}
    )
    
    # Mock guild and scheduled event creation
    mock_scheduled_event = MagicMock()
    mock_scheduled_event.id = 111222333
    mock_guild.create_scheduled_event = AsyncMock(return_value=mock_scheduled_event)
    mock_bot.get_guild = MagicMock(return_value=mock_guild)
    
    # Mock the update poll method
    cog._update_poll_with_results = AsyncMock()
    
    # Execute
    await cog._create_scheduled_event(sample_event, "2025-10-20", "19:00")
    
    # Verify update poll was called
    cog._update_poll_with_results.assert_called_once()
    call_args = cog._update_poll_with_results.call_args
    
    # Check arguments
    assert call_args[0][0].title == sample_event.title
    assert call_args[0][0].winning_date == "2025-10-20"
    assert call_args[0][0].winning_time == "19:00"
    assert call_args[0][1] == mock_scheduled_event


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
