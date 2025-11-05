"""
Tests for Discord API error handling with retry logic in scheduled event creation.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from src.cogs.events import EventsCog
from src.models.event import Event


@pytest.fixture
def mock_bot():
    """Create a mock bot instance."""
    bot = MagicMock()
    bot.database = MagicMock()
    bot.database.update_one = AsyncMock()
    bot.get_guild = MagicMock()
    bot.get_channel = MagicMock()
    return bot


@pytest.fixture
def events_cog(mock_bot):
    """Create an EventsCog instance with mocked bot."""
    # Mock the tasks.loop decorator to prevent background task from starting
    with patch('src.cogs.events.tasks'):
        cog = EventsCog(mock_bot)
        # Stop the background task if it started
        if hasattr(cog, 'check_expired_polls'):
            cog.check_expired_polls.cancel()
    return cog


@pytest.fixture
def sample_event():
    """Create a sample event for testing."""
    return Event(
        guild_id="123456789",
        channel_id="987654321",
        message_id="111222333",
        creator_id="555666777",
        title="Test Game Night",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=7),
        status="active",
        date_votes={
            "2025-10-15": ["user1", "user2"],
            "2025-10-16": ["user1"]
        },
        time_votes={
            "17:00": ["user1"],
            "18:00": ["user1", "user2"]
        }
    )


@pytest.mark.asyncio
async def test_create_scheduled_event_success_first_attempt(events_cog, mock_bot, sample_event):
    """Test successful scheduled event creation on first attempt."""
    # Setup
    mock_guild = MagicMock()
    mock_scheduled_event = MagicMock()
    mock_scheduled_event.id = "scheduled_event_123"
    mock_guild.create_scheduled_event = AsyncMock(return_value=mock_scheduled_event)
    
    event_datetime = datetime(2025, 10, 15, 18, 0)
    
    # Execute
    result = await events_cog._create_scheduled_event_with_retry(
        mock_guild, sample_event, event_datetime
    )
    
    # Verify
    assert result == mock_scheduled_event
    assert mock_guild.create_scheduled_event.call_count == 1
    mock_guild.create_scheduled_event.assert_called_once_with(
        name=sample_event.title,
        start_time=event_datetime,
        location="Discord",
        description="Game night event created via poll",
        privacy_level=discord.ScheduledEventPrivacyLevel.guild_only
    )


@pytest.mark.asyncio
async def test_create_scheduled_event_retry_on_http_exception(events_cog, mock_bot, sample_event):
    """Test retry logic when HTTPException occurs."""
    # Setup
    mock_guild = MagicMock()
    mock_scheduled_event = MagicMock()
    mock_scheduled_event.id = "scheduled_event_123"
    
    # Fail twice, then succeed
    mock_guild.create_scheduled_event = AsyncMock(
        side_effect=[
            discord.HTTPException(MagicMock(), "Rate limited"),
            discord.HTTPException(MagicMock(), "Server error"),
            mock_scheduled_event
        ]
    )
    
    event_datetime = datetime(2025, 10, 15, 18, 0)
    
    # Execute
    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        result = await events_cog._create_scheduled_event_with_retry(
            mock_guild, sample_event, event_datetime
        )
    
    # Verify
    assert result == mock_scheduled_event
    assert mock_guild.create_scheduled_event.call_count == 3
    
    # Verify exponential backoff was used
    assert mock_sleep.call_count == 2
    # First retry: 2^0 = 1 second
    mock_sleep.assert_any_call(1)
    # Second retry: 2^1 = 2 seconds
    mock_sleep.assert_any_call(2)


@pytest.mark.asyncio
async def test_create_scheduled_event_all_retries_fail(events_cog, mock_bot, sample_event):
    """Test that None is returned when all retries fail."""
    # Setup
    mock_guild = MagicMock()
    
    # Fail all 3 attempts
    mock_guild.create_scheduled_event = AsyncMock(
        side_effect=discord.HTTPException(MagicMock(), "Server error")
    )
    
    event_datetime = datetime(2025, 10, 15, 18, 0)
    
    # Execute
    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        result = await events_cog._create_scheduled_event_with_retry(
            mock_guild, sample_event, event_datetime, max_retries=3
        )
    
    # Verify
    assert result is None
    assert mock_guild.create_scheduled_event.call_count == 3
    
    # Verify exponential backoff was used (2 sleeps for 3 attempts)
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1)  # 2^0
    mock_sleep.assert_any_call(2)  # 2^1


@pytest.mark.asyncio
async def test_create_scheduled_event_forbidden_no_retry(events_cog, mock_bot, sample_event):
    """Test that Forbidden errors are not retried."""
    # Setup
    mock_guild = MagicMock()
    mock_guild.create_scheduled_event = AsyncMock(
        side_effect=discord.Forbidden(MagicMock(), "Missing permissions")
    )
    
    event_datetime = datetime(2025, 10, 15, 18, 0)
    
    # Execute and verify exception is raised
    with pytest.raises(discord.Forbidden):
        await events_cog._create_scheduled_event_with_retry(
            mock_guild, sample_event, event_datetime
        )
    
    # Verify only one attempt was made
    assert mock_guild.create_scheduled_event.call_count == 1


@pytest.mark.asyncio
async def test_send_scheduled_event_failure_message(events_cog, mock_bot, sample_event):
    """Test sending failure message to channel."""
    # Setup
    mock_channel = MagicMock()
    mock_channel.send = AsyncMock()
    mock_bot.get_channel.return_value = mock_channel
    
    winning_date = "2025-10-15"
    winning_time = "18:00"
    
    # Execute
    await events_cog._send_scheduled_event_failure_message(
        sample_event, winning_date, winning_time
    )
    
    # Verify
    mock_bot.get_channel.assert_called_once_with(int(sample_event.channel_id))
    assert mock_channel.send.call_count == 1
    
    # Verify embed was sent
    call_args = mock_channel.send.call_args
    assert 'embed' in call_args.kwargs
    embed = call_args.kwargs['embed']
    assert isinstance(embed, discord.Embed)
    assert "Failed to Create Scheduled Event" in embed.description
    assert sample_event.title in embed.title


@pytest.mark.asyncio
async def test_send_scheduled_event_failure_message_with_custom_error(events_cog, mock_bot, sample_event):
    """Test sending failure message with custom error text."""
    # Setup
    mock_channel = MagicMock()
    mock_channel.send = AsyncMock()
    mock_bot.get_channel.return_value = mock_channel
    
    winning_date = "2025-10-15"
    winning_time = "18:00"
    custom_error = "Missing permissions to create scheduled events"
    
    # Execute
    await events_cog._send_scheduled_event_failure_message(
        sample_event, winning_date, winning_time, error_msg=custom_error
    )
    
    # Verify
    assert mock_channel.send.call_count == 1
    
    # Verify custom error message is in embed
    call_args = mock_channel.send.call_args
    embed = call_args.kwargs['embed']
    
    # Check that custom error is in one of the fields
    error_field = next((f for f in embed.fields if "Error" in f.name), None)
    assert error_field is not None
    assert custom_error in error_field.value


@pytest.mark.asyncio
async def test_create_scheduled_event_integration_with_retry_success(events_cog, mock_bot, sample_event):
    """Test full _create_scheduled_event method with retry success."""
    # Setup
    mock_guild = MagicMock()
    mock_guild.id = 123456789
    mock_bot.get_guild.return_value = mock_guild
    
    mock_scheduled_event = MagicMock()
    mock_scheduled_event.id = "scheduled_event_123"
    
    # Fail once, then succeed
    mock_guild.create_scheduled_event = AsyncMock(
        side_effect=[
            discord.HTTPException(MagicMock(), "Temporary error"),
            mock_scheduled_event
        ]
    )
    
    # Mock the update_poll_with_results method
    events_cog._update_poll_with_results = AsyncMock()
    
    winning_date = "2025-10-15"
    winning_time = "18:00"
    
    # Execute
    with patch('asyncio.sleep', new_callable=AsyncMock):
        await events_cog._create_scheduled_event(sample_event, winning_date, winning_time)
    
    # Verify
    assert mock_guild.create_scheduled_event.call_count == 2
    assert mock_bot.database.update_one.call_count == 1
    
    # Verify database was updated with scheduled status
    update_call = mock_bot.database.update_one.call_args
    assert update_call[0][0] == "events"
    assert update_call[0][1] == {"_id": sample_event.id}
    assert update_call[0][2]["$set"]["status"] == "scheduled"
    assert update_call[0][2]["$set"]["discord_event_id"] == str(mock_scheduled_event.id)


@pytest.mark.asyncio
async def test_create_scheduled_event_integration_all_retries_fail(events_cog, mock_bot, sample_event):
    """Test full _create_scheduled_event method when all retries fail."""
    # Setup
    mock_guild = MagicMock()
    mock_guild.id = 123456789
    mock_bot.get_guild.return_value = mock_guild
    
    # Fail all attempts
    mock_guild.create_scheduled_event = AsyncMock(
        side_effect=discord.HTTPException(MagicMock(), "Persistent error")
    )
    
    # Mock the failure message method
    events_cog._send_scheduled_event_failure_message = AsyncMock()
    
    winning_date = "2025-10-15"
    winning_time = "18:00"
    
    # Execute
    with patch('asyncio.sleep', new_callable=AsyncMock):
        await events_cog._create_scheduled_event(sample_event, winning_date, winning_time)
    
    # Verify
    assert mock_guild.create_scheduled_event.call_count == 3
    
    # Verify database was updated with expired status (not scheduled)
    update_call = mock_bot.database.update_one.call_args
    assert update_call[0][2]["$set"]["status"] == "expired"
    
    # Verify failure message was sent
    assert events_cog._send_scheduled_event_failure_message.call_count == 1
