"""
Tests for EventCreationModal implementation (Task 4).
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import discord

from models.event import Event


@pytest.mark.asyncio
async def test_event_creation_modal_initialization():
    """Test that EventCreationModal initializes correctly."""
    from cogs.events import EventCreationModal
    
    # Create mock bot
    mock_bot = MagicMock()
    
    # Create modal
    modal = EventCreationModal(mock_bot)
    
    # Verify modal properties
    assert modal.title == "Create Game Night Event"
    assert modal.bot == mock_bot
    assert len(modal.children) == 1
    
    # Verify input field
    input_field = modal.children[0]
    assert input_field.label == "Event Title"
    assert input_field.min_length == 3
    assert input_field.max_length == 100
    assert input_field.required is True


@pytest.mark.asyncio
async def test_event_data_structure():
    """Test that event data structure is correct when created."""
    # This test verifies the data structure without mocking Discord components
    event_data = {
        "guild_id": "123456789",
        "channel_id": "987654321",
        "creator_id": "111222333",
        "title": "Test Game Night",
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=7),
        "status": "active",
        "date_votes": {},
        "time_votes": {},
        "message_id": None,
        "winning_date": None,
        "winning_time": None,
        "discord_event_id": None
    }
    
    # Verify Event model accepts this structure
    event = Event(**event_data)
    event.validate_data()
    
    # Verify expires_at is 7 days from created_at
    created_at = event_data["created_at"]
    expires_at = event_data["expires_at"]
    time_diff = expires_at - created_at
    assert abs(time_diff.total_seconds() - (7 * 24 * 60 * 60)) < 1  # Within 1 second
    
    # Verify all required fields are present
    assert event.guild_id == "123456789"
    assert event.channel_id == "987654321"
    assert event.creator_id == "111222333"
    assert event.title == "Test Game Night"
    assert event.status == "active"
    assert event.date_votes == {}
    assert event.time_votes == {}
    assert event.message_id is None
    assert event.winning_date is None
    assert event.winning_time is None
    assert event.discord_event_id is None


@pytest.mark.asyncio
async def test_event_title_sanitization():
    """Test that Event model sanitizes @everyone and @here mentions."""
    # Test @everyone sanitization
    event_data = {
        "guild_id": "123456789",
        "channel_id": "987654321",
        "creator_id": "111222333",
        "title": "Test @everyone Game",
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=7),
        "status": "active"
    }
    
    event = Event(**event_data)
    assert "@everyone" not in event.title
    assert "everyone" in event.title
    
    # Test @here sanitization
    event_data2 = {
        "guild_id": "123456789",
        "channel_id": "987654321",
        "creator_id": "111222333",
        "title": "Test @here Game",
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=7),
        "status": "active"
    }
    
    event2 = Event(**event_data2)
    assert "@here" not in event2.title
    assert "here" in event2.title


@pytest.mark.asyncio
async def test_event_creation_with_valid_data():
    """Test that valid event data passes all validations."""
    event_data = {
        "guild_id": "123456789",
        "channel_id": "987654321",
        "creator_id": "111222333",
        "title": "Valid Game Night Title",
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=7),
        "status": "active",
        "date_votes": {},
        "time_votes": {},
        "message_id": None,
        "winning_date": None,
        "winning_time": None,
        "discord_event_id": None
    }
    
    # Should not raise any exceptions
    event = Event(**event_data)
    event.validate_data()
    
    # Verify model_dump works for database insertion
    dumped = event.model_dump()
    assert dumped["title"] == "Valid Game Night Title"
    assert dumped["status"] == "active"


@pytest.mark.asyncio
async def test_event_model_validation():
    """Test that Event model validates data correctly."""
    # Test valid event
    event_data = {
        "guild_id": "123456789",
        "channel_id": "987654321",
        "creator_id": "111222333",
        "title": "Test Game Night",
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=7),
        "status": "active",
        "date_votes": {},
        "time_votes": {}
    }
    
    event = Event(**event_data)
    event.validate_data()  # Should not raise
    
    # Test title too short
    with pytest.raises(ValueError, match="at least 3 characters"):
        Event(**{**event_data, "title": "ab"})
    
    # Test title too long
    with pytest.raises(ValueError, match="at most 100 characters"):
        Event(**{**event_data, "title": "a" * 101})
    
    # Test invalid status
    with pytest.raises(ValueError, match="Status must be one of"):
        Event(**{**event_data, "status": "invalid_status"})
    
    # Test expires_at before created_at
    event_with_bad_expiry = Event(**{
        **event_data,
        "expires_at": datetime.utcnow() - timedelta(days=1)
    })
    with pytest.raises(ValueError, match="expires_at must be after created_at"):
        event_with_bad_expiry.validate_data()


@pytest.mark.asyncio
async def test_event_expiry_calculation():
    """Test that event expiry is calculated correctly as 7 days from creation."""
    created_at = datetime.utcnow()
    expires_at = created_at + timedelta(days=7)
    
    event_data = {
        "guild_id": "123456789",
        "channel_id": "987654321",
        "creator_id": "111222333",
        "title": "Test Game Night",
        "created_at": created_at,
        "expires_at": expires_at,
        "status": "active"
    }
    
    event = Event(**event_data)
    
    # Calculate difference in days
    time_diff = event.expires_at - event.created_at
    days_diff = time_diff.total_seconds() / (24 * 60 * 60)
    
    # Should be exactly 7 days
    assert abs(days_diff - 7.0) < 0.00002  # Less than 1 second difference
    
    # Verify validation passes
    event.validate_data()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
