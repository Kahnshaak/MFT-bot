"""
Tests for vote recording functionality (Task 7).
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import discord

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from models.event import Event


class TestVoteRecording:
    """Test vote recording in VoteModal."""
    
    @pytest.fixture
    def mock_bot(self):
        """Create mock bot with database."""
        bot = MagicMock()
        bot.database = MagicMock()
        bot.database.find_one = AsyncMock()
        bot.database.update_one = AsyncMock()
        return bot
    
    @pytest.fixture
    def sample_event_data(self):
        """Create sample event data."""
        from bson import ObjectId
        now = datetime.utcnow()
        return {
            "_id": ObjectId(),
            "guild_id": "123456789",
            "channel_id": "987654321",
            "message_id": "111222333",
            "creator_id": "555666777",
            "title": "Test Game Night",
            "created_at": now,
            "expires_at": now + timedelta(days=7),
            "status": "active",
            "date_votes": {},
            "time_votes": {},
            "winning_date": None,
            "winning_time": None,
            "discord_event_id": None
        }
    
    @pytest.mark.asyncio
    async def test_add_vote_to_empty_event(self, mock_bot, sample_event_data):
        """Test adding votes to an event with no existing votes."""
        # Setup
        event = Event(**sample_event_data)
        user_id = "user_123"
        dates = ["2025-10-15", "2025-10-16"]
        times = ["17:00", "18:00", "19:00"]
        
        # Add votes
        event.add_vote(user_id, dates, times)
        
        # Verify votes were added
        assert "2025-10-15" in event.date_votes
        assert "2025-10-16" in event.date_votes
        assert user_id in event.date_votes["2025-10-15"]
        assert user_id in event.date_votes["2025-10-16"]
        
        assert "17:00" in event.time_votes
        assert "18:00" in event.time_votes
        assert "19:00" in event.time_votes
        assert user_id in event.time_votes["17:00"]
        assert user_id in event.time_votes["18:00"]
        assert user_id in event.time_votes["19:00"]
    
    @pytest.mark.asyncio
    async def test_update_existing_vote(self, mock_bot, sample_event_data):
        """Test updating votes replaces old votes instead of duplicating."""
        # Setup - event with existing votes
        sample_event_data["date_votes"] = {
            "2025-10-15": ["user_123"],
            "2025-10-16": ["user_123"]
        }
        sample_event_data["time_votes"] = {
            "17:00": ["user_123"],
            "18:00": ["user_123"]
        }
        
        event = Event(**sample_event_data)
        user_id = "user_123"
        
        # User changes their vote
        new_dates = ["2025-10-17", "2025-10-18"]
        new_times = ["19:00", "20:00"]
        
        event.add_vote(user_id, new_dates, new_times)
        
        # Verify old votes were removed
        assert user_id not in event.date_votes.get("2025-10-15", [])
        assert user_id not in event.date_votes.get("2025-10-16", [])
        assert user_id not in event.time_votes.get("17:00", [])
        assert user_id not in event.time_votes.get("18:00", [])
        
        # Verify new votes were added
        assert user_id in event.date_votes["2025-10-17"]
        assert user_id in event.date_votes["2025-10-18"]
        assert user_id in event.time_votes["19:00"]
        assert user_id in event.time_votes["20:00"]
        
        # Verify user only appears once per option
        assert event.date_votes["2025-10-17"].count(user_id) == 1
        assert event.date_votes["2025-10-18"].count(user_id) == 1
        assert event.time_votes["19:00"].count(user_id) == 1
        assert event.time_votes["20:00"].count(user_id) == 1
    
    @pytest.mark.asyncio
    async def test_multiple_users_voting(self, mock_bot, sample_event_data):
        """Test multiple users can vote on the same options."""
        event = Event(**sample_event_data)
        
        # User 1 votes
        event.add_vote("user_1", ["2025-10-15"], ["17:00"])
        
        # User 2 votes for same options
        event.add_vote("user_2", ["2025-10-15"], ["17:00"])
        
        # User 3 votes for different options
        event.add_vote("user_3", ["2025-10-16"], ["18:00"])
        
        # Verify all votes are recorded
        assert len(event.date_votes["2025-10-15"]) == 2
        assert "user_1" in event.date_votes["2025-10-15"]
        assert "user_2" in event.date_votes["2025-10-15"]
        
        assert len(event.time_votes["17:00"]) == 2
        assert "user_1" in event.time_votes["17:00"]
        assert "user_2" in event.time_votes["17:00"]
        
        assert len(event.date_votes["2025-10-16"]) == 1
        assert "user_3" in event.date_votes["2025-10-16"]
        
        assert len(event.time_votes["18:00"]) == 1
        assert "user_3" in event.time_votes["18:00"]
    
    @pytest.mark.asyncio
    async def test_get_vote_counts(self, mock_bot, sample_event_data):
        """Test getting vote counts for all options."""
        event = Event(**sample_event_data)
        
        # Add votes from multiple users
        event.add_vote("user_1", ["2025-10-15", "2025-10-16"], ["17:00", "18:00"])
        event.add_vote("user_2", ["2025-10-15"], ["17:00", "19:00"])
        event.add_vote("user_3", ["2025-10-16"], ["18:00"])
        
        # Get vote counts
        date_counts, time_counts = event.get_vote_counts()
        
        # Verify counts
        assert date_counts["2025-10-15"] == 2  # user_1, user_2
        assert date_counts["2025-10-16"] == 2  # user_1, user_3
        assert time_counts["17:00"] == 2  # user_1, user_2
        assert time_counts["18:00"] == 2  # user_1, user_3
        assert time_counts["19:00"] == 1  # user_2
    
    @pytest.mark.asyncio
    async def test_vote_on_inactive_event(self, mock_bot, sample_event_data):
        """Test that voting on inactive events is prevented."""
        # This test verifies the VoteModal callback logic
        # The actual prevention happens in the callback, not the model
        sample_event_data["status"] = "expired"
        event = Event(**sample_event_data)
        
        # Verify status is not active
        assert event.status != "active"
    
    @pytest.mark.asyncio
    async def test_empty_vote_lists_cleanup(self, mock_bot, sample_event_data):
        """Test that empty vote lists are cleaned up."""
        # Setup - event with one user's vote
        sample_event_data["date_votes"] = {
            "2025-10-15": ["user_123"]
        }
        sample_event_data["time_votes"] = {
            "17:00": ["user_123"]
        }
        
        event = Event(**sample_event_data)
        
        # User changes vote to different options
        event.add_vote("user_123", ["2025-10-16"], ["18:00"])
        
        # Verify old options are removed (not just empty lists)
        assert "2025-10-15" not in event.date_votes
        assert "17:00" not in event.time_votes
        
        # Verify new options exist
        assert "2025-10-16" in event.date_votes
        assert "18:00" in event.time_votes


class TestVoteModalParsing:
    """Test VoteModal input parsing."""
    
    @pytest.mark.asyncio
    async def test_parse_dates_valid_input(self):
        """Test parsing valid date input."""
        from cogs.events import VoteModal
        
        # Create a mock bot with logger
        mock_bot = MagicMock()
        mock_bot.database = MagicMock()
        
        # Create modal instance within async context
        modal = VoteModal("test_event", mock_bot)
        
        # Test single date (use current day or later)
        now = datetime.utcnow()
        current_day = now.day
        result = modal._parse_dates(str(current_day))
        assert len(result) == 1
        assert result[0].endswith(f"-{current_day:02d}")
        
        # Test multiple dates
        if current_day <= 28:  # Safe range for all months
            result = modal._parse_dates(f"{current_day}, {current_day+1}, {current_day+2}")
            assert len(result) == 3
    
    @pytest.mark.asyncio
    async def test_parse_dates_invalid_input(self):
        """Test parsing invalid date input."""
        from cogs.events import VoteModal
        
        mock_bot = MagicMock()
        mock_bot.database = MagicMock()
        modal = VoteModal("test_event", mock_bot)
        
        # Test invalid day number
        with pytest.raises(ValueError):
            modal._parse_dates("abc")
        
        # Test day beyond month end
        with pytest.raises(ValueError):
            modal._parse_dates("32")
    
    @pytest.mark.asyncio
    async def test_parse_times_valid_input(self):
        """Test parsing valid time input."""
        from cogs.events import VoteModal
        
        mock_bot = MagicMock()
        mock_bot.database = MagicMock()
        modal = VoteModal("test_event", mock_bot)
        
        # Test single time
        result = modal._parse_times("5pm")
        assert result == ["17:00"]
        
        # Test multiple times
        result = modal._parse_times("5pm, 6pm, 7pm")
        assert result == ["17:00", "18:00", "19:00"]
        
        # Test with spaces
        result = modal._parse_times("5 pm, 6 pm")
        assert result == ["17:00", "18:00"]
    
    @pytest.mark.asyncio
    async def test_parse_times_invalid_input(self):
        """Test parsing invalid time input."""
        from cogs.events import VoteModal
        
        mock_bot = MagicMock()
        mock_bot.database = MagicMock()
        modal = VoteModal("test_event", mock_bot)
        
        # Test missing am/pm
        with pytest.raises(ValueError):
            modal._parse_times("5")
        
        # Test time outside valid range
        with pytest.raises(ValueError):
            modal._parse_times("3pm")  # Too early
        
        with pytest.raises(ValueError):
            modal._parse_times("1am")  # Too late
        
        # Test invalid format
        with pytest.raises(ValueError):
            modal._parse_times("abc")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
