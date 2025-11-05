"""
Tests for poll embed update functionality.
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
from src.cogs.events import update_poll_embed


@pytest.fixture
def mock_bot():
    """Create a mock bot instance."""
    bot = MagicMock()
    bot.database = MagicMock()
    return bot


@pytest.fixture
def mock_channel():
    """Create a mock Discord channel."""
    channel = AsyncMock(spec=discord.TextChannel)
    channel.id = 123456789
    return channel


@pytest.fixture
def sample_event():
    """Create a sample event with votes."""
    now = datetime.utcnow()
    event = Event(
        guild_id="111111111",
        channel_id="222222222",
        message_id="333333333",
        creator_id="444444444",
        title="Test Game Night",
        created_at=now,
        expires_at=now + timedelta(days=7),
        status="active",
        date_votes={
            "2025-10-15": ["user1", "user2", "user3"],
            "2025-10-16": ["user1", "user4"],
            "2025-10-20": ["user2"]
        },
        time_votes={
            "17:00": ["user1"],
            "18:00": ["user2", "user3", "user4"],
            "19:00": ["user1", "user2"]
        }
    )
    return event


@pytest.fixture
def sample_event_no_votes():
    """Create a sample event with no votes."""
    now = datetime.utcnow()
    event = Event(
        guild_id="111111111",
        channel_id="222222222",
        message_id="333333333",
        creator_id="444444444",
        title="Test Game Night",
        created_at=now,
        expires_at=now + timedelta(days=7),
        status="active",
        date_votes={},
        time_votes={}
    )
    return event


@pytest.mark.asyncio
async def test_update_poll_embed_success(mock_bot, mock_channel, sample_event):
    """Test successful poll embed update with votes."""
    # Create mock message
    mock_message = AsyncMock(spec=discord.Message)
    mock_message.id = int(sample_event.message_id)
    mock_message.edit = AsyncMock()
    
    # Mock channel.fetch_message to return our mock message
    mock_channel.fetch_message = AsyncMock(return_value=mock_message)
    
    # Call the function
    result = await update_poll_embed(mock_bot, mock_channel, sample_event)
    
    # Verify success
    assert result is True
    
    # Verify message was fetched
    mock_channel.fetch_message.assert_called_once_with(int(sample_event.message_id))
    
    # Verify message was edited
    mock_message.edit.assert_called_once()
    
    # Get the embed that was passed to edit
    call_args = mock_message.edit.call_args
    embed = call_args.kwargs['embed']
    
    # Verify embed properties
    assert isinstance(embed, discord.Embed)
    assert sample_event.title in embed.title
    assert embed.color == discord.Color.blue()
    
    # Verify embed has the expected fields
    field_names = [field.name for field in embed.fields]
    assert "📆 Date Votes" in field_names
    assert "🕐 Time Votes" in field_names
    assert "⏰ Poll Expires" in field_names
    assert "📝 How to Vote" in field_names
    
    # Verify date votes field contains vote counts
    date_field = next(f for f in embed.fields if f.name == "📆 Date Votes")
    assert "3 votes" in date_field.value  # Oct 15 has 3 votes
    assert "⭐" in date_field.value  # Should have stars
    
    # Verify time votes field contains vote counts
    time_field = next(f for f in embed.fields if f.name == "🕐 Time Votes")
    assert "3 votes" in time_field.value  # 6pm (18:00) has 3 votes
    assert "⭐" in time_field.value  # Should have stars


@pytest.mark.asyncio
async def test_update_poll_embed_no_votes(mock_bot, mock_channel, sample_event_no_votes):
    """Test poll embed update with no votes."""
    # Create mock message
    mock_message = AsyncMock(spec=discord.Message)
    mock_message.id = int(sample_event_no_votes.message_id)
    mock_message.edit = AsyncMock()
    
    # Mock channel.fetch_message to return our mock message
    mock_channel.fetch_message = AsyncMock(return_value=mock_message)
    
    # Call the function
    result = await update_poll_embed(mock_bot, mock_channel, sample_event_no_votes)
    
    # Verify success
    assert result is True
    
    # Verify message was edited
    mock_message.edit.assert_called_once()
    
    # Get the embed
    call_args = mock_message.edit.call_args
    embed = call_args.kwargs['embed']
    
    # Verify date votes field shows 0 votes
    date_field = next(f for f in embed.fields if f.name == "📆 Date Votes")
    assert "0 votes" in date_field.value
    assert "⭐" not in date_field.value  # No stars for 0 votes
    
    # Verify time votes field shows 0 votes
    time_field = next(f for f in embed.fields if f.name == "🕐 Time Votes")
    assert "0 votes" in time_field.value
    assert "⭐" not in time_field.value  # No stars for 0 votes


@pytest.mark.asyncio
async def test_update_poll_embed_no_message_id(mock_bot, mock_channel, sample_event):
    """Test poll embed update when event has no message_id."""
    # Remove message_id
    sample_event.message_id = None
    
    # Call the function
    result = await update_poll_embed(mock_bot, mock_channel, sample_event)
    
    # Verify failure
    assert result is False


@pytest.mark.asyncio
async def test_update_poll_embed_message_not_found(mock_bot, mock_channel, sample_event):
    """Test poll embed update when message is not found."""
    # Mock channel.fetch_message to raise NotFound
    mock_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), MagicMock()))
    
    # Call the function
    result = await update_poll_embed(mock_bot, mock_channel, sample_event)
    
    # Verify failure
    assert result is False


@pytest.mark.asyncio
async def test_update_poll_embed_forbidden(mock_bot, mock_channel, sample_event):
    """Test poll embed update when bot lacks permissions."""
    # Mock channel.fetch_message to raise Forbidden
    mock_channel.fetch_message = AsyncMock(side_effect=discord.Forbidden(MagicMock(), MagicMock()))
    
    # Call the function
    result = await update_poll_embed(mock_bot, mock_channel, sample_event)
    
    # Verify failure
    assert result is False


@pytest.mark.asyncio
async def test_update_poll_embed_star_display(mock_bot, mock_channel):
    """Test that star display is capped at 5 stars."""
    now = datetime.utcnow()
    
    # Create event with many votes
    event = Event(
        guild_id="111111111",
        channel_id="222222222",
        message_id="333333333",
        creator_id="444444444",
        title="Popular Event",
        created_at=now,
        expires_at=now + timedelta(days=7),
        status="active",
        date_votes={
            "2025-10-15": ["user1", "user2", "user3", "user4", "user5", "user6", "user7"]  # 7 votes
        },
        time_votes={
            "18:00": ["user1", "user2", "user3"]  # 3 votes
        }
    )
    
    # Create mock message
    mock_message = AsyncMock(spec=discord.Message)
    mock_message.id = int(event.message_id)
    mock_message.edit = AsyncMock()
    
    # Mock channel.fetch_message
    mock_channel.fetch_message = AsyncMock(return_value=mock_message)
    
    # Call the function
    result = await update_poll_embed(mock_bot, mock_channel, event)
    
    # Verify success
    assert result is True
    
    # Get the embed
    call_args = mock_message.edit.call_args
    embed = call_args.kwargs['embed']
    
    # Verify date field has max 5 stars (even though there are 7 votes)
    date_field = next(f for f in embed.fields if f.name == "📆 Date Votes")
    assert "7 votes" in date_field.value
    assert "⭐⭐⭐⭐⭐" in date_field.value  # Exactly 5 stars
    assert "⭐⭐⭐⭐⭐⭐" not in date_field.value  # Not 6 stars
    
    # Verify time field has 3 stars
    time_field = next(f for f in embed.fields if f.name == "🕐 Time Votes")
    assert "3 votes" in time_field.value
    assert "⭐⭐⭐" in time_field.value


@pytest.mark.asyncio
async def test_update_poll_embed_date_formatting(mock_bot, mock_channel):
    """Test that dates are formatted correctly (e.g., 'Oct 15')."""
    now = datetime.utcnow()
    
    # Create event with specific date
    event = Event(
        guild_id="111111111",
        channel_id="222222222",
        message_id="333333333",
        creator_id="444444444",
        title="Test Event",
        created_at=now,
        expires_at=now + timedelta(days=7),
        status="active",
        date_votes={
            "2025-10-15": ["user1"]
        },
        time_votes={
            "17:00": ["user1"]
        }
    )
    
    # Create mock message
    mock_message = AsyncMock(spec=discord.Message)
    mock_message.id = int(event.message_id)
    mock_message.edit = AsyncMock()
    
    # Mock channel.fetch_message
    mock_channel.fetch_message = AsyncMock(return_value=mock_message)
    
    # Call the function
    result = await update_poll_embed(mock_bot, mock_channel, event)
    
    # Verify success
    assert result is True
    
    # Get the embed
    call_args = mock_message.edit.call_args
    embed = call_args.kwargs['embed']
    
    # Verify date is formatted as "Oct 15"
    date_field = next(f for f in embed.fields if f.name == "📆 Date Votes")
    assert "Oct 15" in date_field.value


@pytest.mark.asyncio
async def test_update_poll_embed_time_formatting(mock_bot, mock_channel):
    """Test that times are formatted correctly (e.g., '5pm', '6pm')."""
    now = datetime.utcnow()
    
    # Create event with specific times
    event = Event(
        guild_id="111111111",
        channel_id="222222222",
        message_id="333333333",
        creator_id="444444444",
        title="Test Event",
        created_at=now,
        expires_at=now + timedelta(days=7),
        status="active",
        date_votes={
            "2025-10-15": ["user1"]
        },
        time_votes={
            "17:00": ["user1"],  # 5pm
            "18:00": ["user2"],  # 6pm
            "23:00": ["user3"]   # 11pm
        }
    )
    
    # Create mock message
    mock_message = AsyncMock(spec=discord.Message)
    mock_message.id = int(event.message_id)
    mock_message.edit = AsyncMock()
    
    # Mock channel.fetch_message
    mock_channel.fetch_message = AsyncMock(return_value=mock_message)
    
    # Call the function
    result = await update_poll_embed(mock_bot, mock_channel, event)
    
    # Verify success
    assert result is True
    
    # Get the embed
    call_args = mock_message.edit.call_args
    embed = call_args.kwargs['embed']
    
    # Verify times are formatted correctly
    time_field = next(f for f in embed.fields if f.name == "🕐 Time Votes")
    assert "5pm" in time_field.value
    assert "6pm" in time_field.value
    assert "11pm" in time_field.value
