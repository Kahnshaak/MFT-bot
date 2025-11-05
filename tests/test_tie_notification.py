"""
Tests for admin notification when polls end in a tie.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
import discord

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
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    guild.system_channel = None
    guild.me = MagicMock()
    return guild


@pytest.fixture
def mock_text_channel():
    """Create a mock text channel."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 987654321
    channel.send = AsyncMock()
    channel.permissions_for = MagicMock(return_value=MagicMock(send_messages=True))
    return channel


@pytest.fixture
def sample_event():
    """Create a sample event for testing."""
    event_id = str(ObjectId())
    return Event(
        id=event_id,
        guild_id="123456789",
        channel_id="987654321",
        message_id="111222333",
        creator_id="555666777",
        title="Test Game Night",
        created_at=datetime.utcnow() - timedelta(days=7),
        expires_at=datetime.utcnow() - timedelta(minutes=1),
        status="active",
        date_votes={
            "2025-10-15": ["user1", "user2"],
            "2025-10-16": ["user3", "user4"]
        },
        time_votes={
            "17:00": ["user1"],
            "18:00": ["user2"]
        }
    )


@pytest.mark.asyncio
async def test_handle_poll_tie_with_system_channel(mock_bot, mock_guild, sample_event):
    """Test tie notification is sent to system channel when available."""
    # Setup
    system_channel = MagicMock(spec=discord.TextChannel)
    system_channel.id = 111111111
    system_channel.send = AsyncMock()
    mock_guild.system_channel = system_channel
    
    mock_bot.get_guild = MagicMock(return_value=mock_guild)
    
    cog = EventsCog(mock_bot)
    cog.check_expired_polls.cancel()  # Stop background task
    
    tied_dates = ["2025-10-15", "2025-10-16"]
    tied_times = []
    
    # Execute
    await cog._handle_poll_tie(sample_event, tied_dates, tied_times)
    
    # Verify
    system_channel.send.assert_called_once()
    call_args = system_channel.send.call_args[0][0]
    
    assert "⚠️" in call_args
    assert "Poll tie for event 'Test Game Night'!" in call_args
    assert "Oct 15" in call_args
    assert "Oct 16" in call_args
    assert str(sample_event.id) in call_args
    assert f"https://discord.com/channels/{sample_event.guild_id}/{sample_event.channel_id}/{sample_event.message_id}" in call_args
    
    # Verify status update
    mock_bot.database.update_one.assert_called_once_with(
        "events",
        {"_id": sample_event.id},
        {"$set": {"status": "tie"}}
    )


@pytest.mark.asyncio
async def test_handle_poll_tie_with_first_text_channel(mock_bot, mock_guild, mock_text_channel, sample_event):
    """Test tie notification is sent to first text channel when no system channel."""
    # Setup
    mock_guild.system_channel = None
    mock_guild.text_channels = [mock_text_channel]
    
    mock_bot.get_guild = MagicMock(return_value=mock_guild)
    
    cog = EventsCog(mock_bot)
    cog.check_expired_polls.cancel()  # Stop background task
    
    tied_dates = []
    tied_times = ["17:00", "18:00"]
    
    # Execute
    await cog._handle_poll_tie(sample_event, tied_dates, tied_times)
    
    # Verify
    mock_text_channel.send.assert_called_once()
    call_args = mock_text_channel.send.call_args[0][0]
    
    assert "⚠️" in call_args
    assert "Poll tie for event 'Test Game Night'!" in call_args
    assert "5pm" in call_args
    assert "6pm" in call_args
    assert str(sample_event.id) in call_args
    
    # Verify status update
    mock_bot.database.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_handle_poll_tie_with_both_dates_and_times(mock_bot, mock_guild, mock_text_channel, sample_event):
    """Test tie notification with both dates and times tied."""
    # Setup
    mock_guild.system_channel = None
    mock_guild.text_channels = [mock_text_channel]
    
    mock_bot.get_guild = MagicMock(return_value=mock_guild)
    
    cog = EventsCog(mock_bot)
    cog.check_expired_polls.cancel()  # Stop background task
    
    tied_dates = ["2025-10-15", "2025-10-16"]
    tied_times = ["17:00", "18:00", "19:00"]
    
    # Execute
    await cog._handle_poll_tie(sample_event, tied_dates, tied_times)
    
    # Verify
    mock_text_channel.send.assert_called_once()
    call_args = mock_text_channel.send.call_args[0][0]
    
    assert "⚠️" in call_args
    assert "Tied dates:" in call_args
    assert "Oct 15" in call_args
    assert "Oct 16" in call_args
    assert "Tied times:" in call_args
    assert "5pm" in call_args
    assert "6pm" in call_args
    assert "7pm" in call_args


@pytest.mark.asyncio
async def test_handle_poll_tie_no_votes(mock_bot, mock_guild, mock_text_channel, sample_event):
    """Test tie notification when no votes were cast."""
    # Setup
    mock_guild.system_channel = None
    mock_guild.text_channels = [mock_text_channel]
    
    mock_bot.get_guild = MagicMock(return_value=mock_guild)
    
    cog = EventsCog(mock_bot)
    cog.check_expired_polls.cancel()  # Stop background task
    
    tied_dates = []
    tied_times = []
    
    # Execute
    await cog._handle_poll_tie(sample_event, tied_dates, tied_times)
    
    # Verify
    mock_text_channel.send.assert_called_once()
    call_args = mock_text_channel.send.call_args[0][0]
    
    assert "⚠️" in call_args
    assert "No votes were cast on this poll" in call_args


@pytest.mark.asyncio
async def test_handle_poll_tie_guild_not_found(mock_bot, sample_event):
    """Test tie handling when guild is not found."""
    # Setup
    mock_bot.get_guild = MagicMock(return_value=None)
    
    cog = EventsCog(mock_bot)
    cog.check_expired_polls.cancel()  # Stop background task
    
    tied_dates = ["2025-10-15"]
    tied_times = []
    
    # Execute
    await cog._handle_poll_tie(sample_event, tied_dates, tied_times)
    
    # Verify status is still updated even if guild not found
    mock_bot.database.update_one.assert_called_once_with(
        "events",
        {"_id": sample_event.id},
        {"$set": {"status": "tie"}}
    )


@pytest.mark.asyncio
async def test_handle_poll_tie_no_suitable_channel(mock_bot, mock_guild, sample_event):
    """Test tie handling when no suitable channel is found."""
    # Setup
    mock_guild.system_channel = None
    mock_guild.text_channels = []
    
    mock_bot.get_guild = MagicMock(return_value=mock_guild)
    
    cog = EventsCog(mock_bot)
    cog.check_expired_polls.cancel()  # Stop background task
    
    tied_dates = ["2025-10-15"]
    tied_times = []
    
    # Execute
    await cog._handle_poll_tie(sample_event, tied_dates, tied_times)
    
    # Verify status is still updated even if no channel found
    mock_bot.database.update_one.assert_called_once_with(
        "events",
        {"_id": sample_event.id},
        {"$set": {"status": "tie"}}
    )


@pytest.mark.asyncio
async def test_handle_poll_tie_permission_error(mock_bot, mock_guild, mock_text_channel, sample_event):
    """Test tie handling when bot lacks permission to send message."""
    # Setup
    mock_guild.system_channel = None
    mock_guild.text_channels = [mock_text_channel]
    mock_text_channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Missing permissions"))
    
    mock_bot.get_guild = MagicMock(return_value=mock_guild)
    
    cog = EventsCog(mock_bot)
    cog.check_expired_polls.cancel()  # Stop background task
    
    tied_dates = ["2025-10-15"]
    tied_times = []
    
    # Execute
    await cog._handle_poll_tie(sample_event, tied_dates, tied_times)
    
    # Verify status is still updated even if send fails
    mock_bot.database.update_one.assert_called_once_with(
        "events",
        {"_id": sample_event.id},
        {"$set": {"status": "tie"}}
    )
