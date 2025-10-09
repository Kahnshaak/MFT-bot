"""
Tests for the Events cog functionality.
"""

import pytest
import asyncio
from datetime import datetime, date, time
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord.ext import commands

from src.cogs.events import EventsCog
from src.models.event import Event, EventState, RSVPStatus
from src.core.event_bus import EventBus, EventType
from src.core.validation_manager import ValidationManager


class MockBot:
    """Mock bot for testing."""
    
    def __init__(self):
        self.database = MagicMock()
        self.database.events = AsyncMock()
        self.event_bus = EventBus()
        self.validation = ValidationManager()
        self.security = MagicMock()


class MockGuild:
    """Mock Discord guild."""
    
    def __init__(self, guild_id: int = 12345):
        self.id = guild_id


class MockUser:
    """Mock Discord user."""
    
    def __init__(self, user_id: int = 67890):
        self.id = user_id
        self.guild_permissions = MagicMock()
        self.guild_permissions.administrator = True


@pytest.fixture
def mock_bot():
    """Create a mock bot instance."""
    return MockBot()


@pytest.fixture
def events_cog(mock_bot):
    """Create an Events cog instance."""
    return EventsCog(mock_bot)


@pytest.fixture
def sample_event():
    """Create a sample event for testing."""
    return Event(
        guild_id="12345",
        creator_id="67890",
        title="Test Game Night",
        description="A test event",
        state=EventState.DRAFT
    )


@pytest.mark.asyncio
async def test_create_event(events_cog, mock_bot):
    """Test event creation."""
    # Mock database insert
    mock_bot.database.events.insert_one = AsyncMock()
    
    # Create event
    event = await events_cog.create_event(
        guild_id="12345",
        creator_id="67890",
        title="Test Event",
        description="Test Description"
    )
    
    # Verify event properties
    assert event.guild_id == "12345"
    assert event.creator_id == "67890"
    assert event.title == "Test Event"
    assert event.description == "Test Description"
    assert event.state == EventState.DRAFT
    
    # Verify database call
    mock_bot.database.events.insert_one.assert_called_once()


@pytest.mark.asyncio
async def test_start_date_poll(events_cog, sample_event):
    """Test starting a date poll."""
    # Mock update_event
    events_cog.update_event = AsyncMock(return_value=True)
    
    # Start date poll
    await events_cog.start_date_poll(sample_event)
    
    # Verify state transition
    assert sample_event.state == EventState.DATE_POLLING
    
    # Verify poll exists
    assert len(sample_event.polls) > 0
    poll = sample_event.polls[0]
    assert poll.is_active
    assert len(poll.options) > 0
    
    # Verify update was called
    events_cog.update_event.assert_called_once_with(sample_event)


@pytest.mark.asyncio
async def test_add_rsvp(events_cog, sample_event):
    """Test adding RSVP to event."""
    # Mock update_event
    events_cog.update_event = AsyncMock(return_value=True)
    
    # Add RSVP
    await events_cog.add_rsvp(
        sample_event,
        "12345",
        RSVPStatus.YES,
        "Looking forward to it!"
    )
    
    # Verify RSVP was added
    assert "12345" in sample_event.rsvp_data
    rsvp = sample_event.rsvp_data["12345"]
    assert rsvp.status == RSVPStatus.YES
    assert rsvp.notes == "Looking forward to it!"
    
    # Verify update was called
    events_cog.update_event.assert_called_once_with(sample_event)


@pytest.mark.asyncio
async def test_cancel_event(events_cog, sample_event):
    """Test event cancellation."""
    # Mock update_event
    events_cog.update_event = AsyncMock(return_value=True)
    
    # Cancel event
    await events_cog.cancel_event(sample_event)
    
    # Verify state transition
    assert sample_event.state == EventState.CANCELLED
    
    # Verify update was called
    events_cog.update_event.assert_called_once_with(sample_event)


def test_create_event_embed(events_cog, sample_event):
    """Test event embed creation."""
    embed = events_cog.create_event_embed(sample_event)
    
    # Verify embed properties
    assert isinstance(embed, discord.Embed)
    assert sample_event.title in embed.title
    assert embed.description == sample_event.description
    
    # Verify fields exist
    field_names = [field.name for field in embed.fields]
    assert "Status" in field_names
    assert "Organizer" in field_names
    assert "RSVPs" in field_names


def test_can_manage_event(events_cog):
    """Test event management permission check."""
    # Create mock event and user
    event = Event(
        guild_id="12345",
        creator_id="67890",
        title="Test Event"
    )
    
    # Test creator can manage
    creator = MockUser(67890)
    result = asyncio.run(events_cog.can_manage_event(creator, event))
    assert result is True
    
    # Test admin can manage
    admin = MockUser(11111)
    admin.guild_permissions.administrator = True
    result = asyncio.run(events_cog.can_manage_event(admin, event))
    assert result is True
    
    # Test regular user cannot manage
    regular_user = MockUser(22222)
    regular_user.guild_permissions = MagicMock()
    regular_user.guild_permissions.administrator = False
    result = asyncio.run(events_cog.can_manage_event(regular_user, event))
    assert result is False


if __name__ == "__main__":
    pytest.main([__file__])