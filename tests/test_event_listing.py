"""
Tests for event listing and viewing commands.
"""

import pytest
from datetime import datetime, date, time
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord.ext import commands

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.cogs.events import EventsCog
from src.models.event import Event, EventState, RSVPStatus, Poll, PollType, PollOption


class MockBot:
    """Mock bot for testing."""
    
    def __init__(self):
        self.database = MagicMock()
        self.database.find_many = AsyncMock()
        self.database.find_one = AsyncMock()
        self.event_bus = MagicMock()
        self.event_bus.emit = AsyncMock()
        self.validation = MagicMock()


class MockGuild:
    """Mock Discord guild."""
    
    def __init__(self, guild_id: int = 12345):
        self.id = guild_id


class MockUser:
    """Mock Discord user."""
    
    def __init__(self, user_id: int = 67890):
        self.id = user_id
        self.guild_permissions = MagicMock()
        self.guild_permissions.administrator = False


class MockInteraction:
    """Mock Discord interaction."""
    
    def __init__(self, guild_id: int = 12345, user_id: int = 67890):
        self.guild = MockGuild(guild_id)
        self.user = MockUser(user_id)
        self.response = MagicMock()
        self.response.defer = AsyncMock()
        self.followup = MagicMock()
        self.followup.send = AsyncMock()


@pytest.fixture
def mock_bot():
    """Create a mock bot instance."""
    return MockBot()


@pytest.fixture
def events_cog(mock_bot):
    """Create an Events cog instance."""
    return EventsCog(mock_bot)


@pytest.fixture
def sample_events():
    """Create sample events for testing."""
    events = []
    
    # Draft event
    event1 = Event(
        guild_id="12345",
        creator_id="67890",
        title="Draft Event",
        description="A draft event",
        state=EventState.DRAFT
    )
    event1.id = "event1"
    events.append(event1)
    
    # Scheduled event with date and time
    event2 = Event(
        guild_id="12345",
        creator_id="67890",
        title="Scheduled Event",
        description="A scheduled event",
        state=EventState.SCHEDULED,
        scheduled_date=date(2025, 10, 20),
        scheduled_time=time(19, 0)
    )
    event2.id = "event2"
    event2.add_rsvp("user1", RSVPStatus.YES)
    event2.add_rsvp("user2", RSVPStatus.YES)
    event2.add_rsvp("user3", RSVPStatus.MAYBE)
    events.append(event2)
    
    # Event with polls
    event3 = Event(
        guild_id="12345",
        creator_id="67890",
        title="Polling Event",
        description="An event with active polls",
        state=EventState.DATE_POLLING
    )
    event3.id = "event3"
    
    # Add a date poll
    date_poll = Poll(
        poll_type=PollType.DATE,
        title="Select Date",
        options=[
            PollOption(option_id="opt1", label="Monday", value="2025-10-20", votes=["user1", "user2"], vote_count=2),
            PollOption(option_id="opt2", label="Tuesday", value="2025-10-21", votes=["user3"], vote_count=1),
        ],
        is_active=True
    )
    event3.add_poll(date_poll)
    events.append(event3)
    
    return events


@pytest.mark.asyncio
async def test_event_list_command_with_events(events_cog, mock_bot, sample_events):
    """Test listing events when events exist."""
    # Mock get_guild_events to return sample events
    events_cog.get_guild_events = AsyncMock(return_value=sample_events)
    
    # Create mock interaction
    interaction = MockInteraction()
    
    # Call the command
    await events_cog.event_list_command(interaction, show_all=False)
    
    # Verify defer was called
    interaction.response.defer.assert_called_once()
    
    # Verify get_guild_events was called
    events_cog.get_guild_events.assert_called_once_with("12345", active_only=True)
    
    # Verify followup.send was called with an embed
    interaction.followup.send.assert_called_once()
    call_args = interaction.followup.send.call_args
    assert 'embed' in call_args.kwargs
    
    # Verify embed contains event information
    embed = call_args.kwargs['embed']
    assert isinstance(embed, discord.Embed)
    assert "Game Night Events" in embed.title
    assert len(embed.fields) == 3  # Should have 3 events


@pytest.mark.asyncio
async def test_event_list_command_no_events(events_cog, mock_bot):
    """Test listing events when no events exist."""
    # Mock get_guild_events to return empty list
    events_cog.get_guild_events = AsyncMock(return_value=[])
    
    # Create mock interaction
    interaction = MockInteraction()
    
    # Call the command
    await events_cog.event_list_command(interaction, show_all=False)
    
    # Verify defer was called
    interaction.response.defer.assert_called_once()
    
    # Verify followup.send was called with no events message
    interaction.followup.send.assert_called_once()
    call_args = interaction.followup.send.call_args
    assert "No active events found" in call_args.args[0]


@pytest.mark.asyncio
async def test_event_view_command_success(events_cog, mock_bot, sample_events):
    """Test viewing a specific event."""
    # Mock get_event to return a sample event
    event = sample_events[1]  # Scheduled event with RSVPs
    events_cog.get_event = AsyncMock(return_value=event)
    events_cog.can_manage_event = AsyncMock(return_value=False)
    
    # Create mock interaction
    interaction = MockInteraction()
    
    # Call the command
    await events_cog.event_view_command(interaction, event_id="event2")
    
    # Verify defer was called
    interaction.response.defer.assert_called_once()
    
    # Verify get_event was called
    events_cog.get_event.assert_called_once_with("event2")
    
    # Verify followup.send was called with an embed
    interaction.followup.send.assert_called_once()
    call_args = interaction.followup.send.call_args
    assert 'embed' in call_args.kwargs
    
    # Verify embed contains event details
    embed = call_args.kwargs['embed']
    assert isinstance(embed, discord.Embed)
    assert "Scheduled Event" in embed.title


@pytest.mark.asyncio
async def test_event_view_command_not_found(events_cog, mock_bot):
    """Test viewing a non-existent event."""
    # Mock get_event to return None
    events_cog.get_event = AsyncMock(return_value=None)
    
    # Create mock interaction
    interaction = MockInteraction()
    
    # Call the command
    await events_cog.event_view_command(interaction, event_id="nonexistent")
    
    # Verify defer was called
    interaction.response.defer.assert_called_once()
    
    # Verify followup.send was called with error message
    interaction.followup.send.assert_called_once()
    call_args = interaction.followup.send.call_args
    assert "Event not found" in call_args.args[0]


@pytest.mark.asyncio
async def test_event_view_command_wrong_guild(events_cog, mock_bot, sample_events):
    """Test viewing an event from a different guild."""
    # Mock get_event to return an event from a different guild
    event = sample_events[0]
    event.guild_id = "99999"  # Different guild
    events_cog.get_event = AsyncMock(return_value=event)
    
    # Create mock interaction
    interaction = MockInteraction(guild_id=12345)
    
    # Call the command
    await events_cog.event_view_command(interaction, event_id="event1")
    
    # Verify defer was called
    interaction.response.defer.assert_called_once()
    
    # Verify followup.send was called with error message
    interaction.followup.send.assert_called_once()
    call_args = interaction.followup.send.call_args
    assert "Event not found in this server" in call_args.args[0]


def test_create_detailed_event_embed(events_cog, sample_events):
    """Test creating a detailed event embed."""
    event = sample_events[1]  # Scheduled event with RSVPs
    
    # Create embed
    embed = events_cog.create_detailed_event_embed(event)
    
    # Verify embed properties
    assert isinstance(embed, discord.Embed)
    assert "Scheduled Event" in embed.title
    assert event.description in embed.description
    
    # Verify fields exist
    field_names = [field.name for field in embed.fields]
    assert "📋 Event Info" in field_names
    assert "📅 Schedule" in field_names
    assert "✋ RSVPs" in field_names


def test_create_detailed_event_embed_with_polls(events_cog, sample_events):
    """Test creating a detailed event embed with poll information."""
    event = sample_events[2]  # Event with date poll
    
    # Create embed
    embed = events_cog.create_detailed_event_embed(event)
    
    # Verify embed properties
    assert isinstance(embed, discord.Embed)
    
    # Verify poll field exists
    field_names = [field.name for field in embed.fields]
    assert "📅 Date Poll" in field_names


def test_get_state_color(events_cog):
    """Test getting color for event states."""
    # Test different states
    assert events_cog._get_state_color(EventState.DRAFT) == discord.Color.light_gray()
    assert events_cog._get_state_color(EventState.DATE_POLLING) == discord.Color.blue()
    assert events_cog._get_state_color(EventState.SCHEDULED) == discord.Color.green()
    assert events_cog._get_state_color(EventState.CANCELLED) == discord.Color.red()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
