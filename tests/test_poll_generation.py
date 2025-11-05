"""
Tests for poll generation functionality (Task 5).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from models.event import Event


# Helper class to test the date/time generation logic without Discord UI
class PollGeneratorHelper:
    """Helper class to test poll generation logic."""
    
    @staticmethod
    def generate_date_options():
        """Generate list of date options: all remaining days in current month."""
        now = datetime.utcnow()
        current_year = now.year
        current_month = now.month
        current_day = now.day
        
        # Get the last day of the current month
        if current_month == 12:
            next_month = datetime(current_year + 1, 1, 1)
        else:
            next_month = datetime(current_year, current_month + 1, 1)
        
        last_day = (next_month - timedelta(days=1)).day
        
        # Generate dates from today through end of month
        date_options = []
        for day in range(current_day, last_day + 1):
            date = datetime(current_year, current_month, day)
            date_options.append(date.strftime("%Y-%m-%d"))
        
        return date_options
    
    @staticmethod
    def generate_time_options():
        """Generate list of time options: 5pm through 11pm in 1-hour increments."""
        time_options = []
        for hour in range(17, 24):  # 17:00 (5pm) through 23:00 (11pm)
            time_options.append(f"{hour:02d}:00")
        
        return time_options


class TestDateGeneration:
    """Test date option generation."""
    
    def test_generate_date_options_returns_list(self):
        """Test that date generation returns a list of dates."""
        date_options = PollGeneratorHelper.generate_date_options()
        
        # Should return a list
        assert isinstance(date_options, list)
        
        # Should have at least one date (today)
        assert len(date_options) >= 1
        
        # All dates should be in YYYY-MM-DD format
        for date_str in date_options:
            # Should be able to parse as date
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            assert date_obj is not None
    
    def test_generate_date_options_includes_today(self):
        """Test that date generation includes today."""
        date_options = PollGeneratorHelper.generate_date_options()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        # First date should be today
        assert date_options[0] == today
    
    def test_generate_date_options_sequential(self):
        """Test that dates are sequential."""
        date_options = PollGeneratorHelper.generate_date_options()
        
        # Convert to date objects
        dates = [datetime.strptime(d, "%Y-%m-%d") for d in date_options]
        
        # Check that each date is one day after the previous
        for i in range(1, len(dates)):
            diff = (dates[i] - dates[i-1]).days
            assert diff == 1, f"Dates should be sequential, but {dates[i-1]} to {dates[i]} is {diff} days"


class TestTimeGeneration:
    """Test time option generation."""
    
    def test_generate_time_options(self):
        """Test that time options are generated correctly."""
        time_options = PollGeneratorHelper.generate_time_options()
        
        # Should have 7 time slots: 17:00 through 23:00
        assert len(time_options) == 7
        assert time_options[0] == "17:00"
        assert time_options[-1] == "23:00"
        
        # Verify all times are in correct format
        expected_times = ["17:00", "18:00", "19:00", "20:00", "21:00", "22:00", "23:00"]
        assert time_options == expected_times


class TestPollEmbedFormat:
    """Test poll embed formatting logic."""
    
    def test_date_formatting(self):
        """Test that dates are formatted correctly for display."""
        date_options = ["2025-10-14", "2025-10-15", "2025-10-16"]
        
        date_display = []
        for date_str in date_options:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            date_display.append(date_obj.strftime("%b %d"))
        
        assert date_display == ["Oct 14", "Oct 15", "Oct 16"]
    
    def test_time_formatting(self):
        """Test that times are formatted correctly for display."""
        time_options = ["17:00", "18:00", "19:00", "20:00", "21:00", "22:00", "23:00"]
        
        time_display = []
        for time_str in time_options:
            hour = int(time_str.split(":")[0])
            if hour >= 12:
                time_12hr = f"{hour - 12 if hour > 12 else 12}pm"
            else:
                time_12hr = f"{hour}am"
            time_display.append(time_12hr)
        
        assert time_display == ["5pm", "6pm", "7pm", "8pm", "9pm", "10pm", "11pm"]


class TestEventModel:
    """Test Event model integration with poll generation."""
    
    def test_event_creation_for_poll(self):
        """Test that Event model can be created with poll data."""
        event = Event(
            guild_id="123456789",
            channel_id="987654321",
            creator_id="111222333",
            title="Test Game Night",
            created_at=datetime(2025, 10, 14, 12, 0, 0),
            expires_at=datetime(2025, 10, 21, 12, 0, 0),
            status="active",
            date_votes={},
            time_votes={}
        )
        
        assert event.title == "Test Game Night"
        assert event.status == "active"
        assert event.expires_at > event.created_at
        assert event.date_votes == {}
        assert event.time_votes == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
