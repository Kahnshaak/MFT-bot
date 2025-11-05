"""
Tests for the simplified Event model.
"""

import pytest
from datetime import datetime, timedelta
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models.event import Event


class TestSimplifiedEventModel:
    """Test suite for simplified Event model."""
    
    def test_event_creation(self):
        """Test basic event creation with required fields."""
        now = datetime.utcnow()
        expires = now + timedelta(days=7)
        
        event = Event(
            guild_id="123456789",
            channel_id="987654321",
            creator_id="111222333",
            title="Game Night",
            expires_at=expires
        )
        
        assert event.guild_id == "123456789"
        assert event.channel_id == "987654321"
        assert event.creator_id == "111222333"
        assert event.title == "Game Night"
        assert event.status == "active"
        assert event.date_votes == {}
        assert event.time_votes == {}
        assert event.winning_date is None
        assert event.winning_time is None
        assert event.discord_event_id is None
    
    def test_title_validation(self):
        """Test title validation (3-100 chars, sanitize mentions)."""
        now = datetime.utcnow()
        expires = now + timedelta(days=7)
        
        # Too short
        with pytest.raises(ValueError, match="at least 3 characters"):
            Event(
                guild_id="123456789",
                channel_id="987654321",
                creator_id="111222333",
                title="ab",
                expires_at=expires
            )
        
        # Too long
        with pytest.raises(ValueError, match="at most 100 characters"):
            Event(
                guild_id="123456789",
                channel_id="987654321",
                creator_id="111222333",
                title="a" * 101,
                expires_at=expires
            )
        
        # Sanitize @everyone and @here
        event = Event(
            guild_id="123456789",
            channel_id="987654321",
            creator_id="111222333",
            title="Game Night @everyone @here",
            expires_at=expires
        )
        assert "@everyone" not in event.title
        assert "@here" not in event.title
    
    def test_add_vote(self):
        """Test adding votes for a user."""
        now = datetime.utcnow()
        expires = now + timedelta(days=7)
        
        event = Event(
            guild_id="123456789",
            channel_id="987654321",
            creator_id="111222333",
            title="Game Night",
            expires_at=expires
        )
        
        # Add votes for user
        event.add_vote(
            user_id="user1",
            dates=["2025-10-15", "2025-10-16"],
            times=["17:00", "18:00"]
        )
        
        assert "2025-10-15" in event.date_votes
        assert "user1" in event.date_votes["2025-10-15"]
        assert "2025-10-16" in event.date_votes
        assert "user1" in event.date_votes["2025-10-16"]
        assert "17:00" in event.time_votes
        assert "user1" in event.time_votes["17:00"]
        assert "18:00" in event.time_votes
        assert "user1" in event.time_votes["18:00"]
    
    def test_update_vote(self):
        """Test updating votes replaces previous votes."""
        now = datetime.utcnow()
        expires = now + timedelta(days=7)
        
        event = Event(
            guild_id="123456789",
            channel_id="987654321",
            creator_id="111222333",
            title="Game Night",
            expires_at=expires
        )
        
        # Initial vote
        event.add_vote(
            user_id="user1",
            dates=["2025-10-15"],
            times=["17:00"]
        )
        
        # Update vote
        event.add_vote(
            user_id="user1",
            dates=["2025-10-16"],
            times=["18:00"]
        )
        
        # Old votes should be removed
        assert "2025-10-15" not in event.date_votes or "user1" not in event.date_votes.get("2025-10-15", [])
        assert "17:00" not in event.time_votes or "user1" not in event.time_votes.get("17:00", [])
        
        # New votes should be present
        assert "user1" in event.date_votes["2025-10-16"]
        assert "user1" in event.time_votes["18:00"]
    
    def test_get_vote_counts(self):
        """Test getting vote counts for all options."""
        now = datetime.utcnow()
        expires = now + timedelta(days=7)
        
        event = Event(
            guild_id="123456789",
            channel_id="987654321",
            creator_id="111222333",
            title="Game Night",
            expires_at=expires
        )
        
        # Add votes from multiple users
        event.add_vote("user1", ["2025-10-15"], ["17:00"])
        event.add_vote("user2", ["2025-10-15"], ["18:00"])
        event.add_vote("user3", ["2025-10-16"], ["17:00"])
        
        date_counts, time_counts = event.get_vote_counts()
        
        assert date_counts["2025-10-15"] == 2
        assert date_counts["2025-10-16"] == 1
        assert time_counts["17:00"] == 2
        assert time_counts["18:00"] == 1
    
    def test_calculate_winner_clear_winner(self):
        """Test calculating winner with clear winner."""
        now = datetime.utcnow()
        expires = now + timedelta(days=7)
        
        event = Event(
            guild_id="123456789",
            channel_id="987654321",
            creator_id="111222333",
            title="Game Night",
            expires_at=expires
        )
        
        # Add votes with clear winner
        event.add_vote("user1", ["2025-10-15"], ["17:00"])
        event.add_vote("user2", ["2025-10-15"], ["17:00"])
        event.add_vote("user3", ["2025-10-16"], ["18:00"])
        
        winning_date, winning_time, is_tie, tied_dates, tied_times = event.calculate_winner()
        
        assert winning_date == "2025-10-15"
        assert winning_time == "17:00"
        assert is_tie is False
        assert tied_dates == []
        assert tied_times == []
    
    def test_calculate_winner_tie(self):
        """Test calculating winner with tie."""
        now = datetime.utcnow()
        expires = now + timedelta(days=7)
        
        event = Event(
            guild_id="123456789",
            channel_id="987654321",
            creator_id="111222333",
            title="Game Night",
            expires_at=expires
        )
        
        # Add votes with tie
        event.add_vote("user1", ["2025-10-15"], ["17:00"])
        event.add_vote("user2", ["2025-10-16"], ["18:00"])
        
        winning_date, winning_time, is_tie, tied_dates, tied_times = event.calculate_winner()
        
        assert winning_date is None
        assert winning_time is None
        assert is_tie is True
        assert set(tied_dates) == {"2025-10-15", "2025-10-16"}
        assert set(tied_times) == {"17:00", "18:00"}
    
    def test_calculate_winner_no_votes(self):
        """Test calculating winner with no votes."""
        now = datetime.utcnow()
        expires = now + timedelta(days=7)
        
        event = Event(
            guild_id="123456789",
            channel_id="987654321",
            creator_id="111222333",
            title="Game Night",
            expires_at=expires
        )
        
        winning_date, winning_time, is_tie, tied_dates, tied_times = event.calculate_winner()
        
        assert winning_date is None
        assert winning_time is None
        assert is_tie is True
        assert tied_dates == []
        assert tied_times == []
    
    def test_validate_data_scheduled_event(self):
        """Test data validation for scheduled events."""
        now = datetime.utcnow()
        expires = now + timedelta(days=7)
        
        # Scheduled event without discord_event_id should fail
        event = Event(
            guild_id="123456789",
            channel_id="987654321",
            creator_id="111222333",
            title="Game Night",
            expires_at=expires,
            status="scheduled"
        )
        
        with pytest.raises(ValueError, match="discord_event_id"):
            event.validate_data()
        
        # Scheduled event without winning date/time should fail
        event = Event(
            guild_id="123456789",
            channel_id="987654321",
            creator_id="111222333",
            title="Game Night",
            expires_at=expires,
            status="scheduled",
            discord_event_id="999888777"
        )
        
        with pytest.raises(ValueError, match="winning_date and winning_time"):
            event.validate_data()
        
        # Valid scheduled event
        event = Event(
            guild_id="123456789",
            channel_id="987654321",
            creator_id="111222333",
            title="Game Night",
            expires_at=expires,
            status="scheduled",
            discord_event_id="999888777",
            winning_date="2025-10-15",
            winning_time="17:00"
        )
        
        event.validate_data()  # Should not raise
    
    def test_status_validation(self):
        """Test status field validation."""
        now = datetime.utcnow()
        expires = now + timedelta(days=7)
        
        # Invalid status
        with pytest.raises(ValueError, match="Status must be one of"):
            Event(
                guild_id="123456789",
                channel_id="987654321",
                creator_id="111222333",
                title="Game Night",
                expires_at=expires,
                status="invalid_status"
            )
        
        # Valid statuses
        for status in ["active", "expired", "scheduled", "tie"]:
            event = Event(
                guild_id="123456789",
                channel_id="987654321",
                creator_id="111222333",
                title="Game Night",
                expires_at=expires,
                status=status
            )
            assert event.status == status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
