"""
Tests for VoteModal date and time parsing.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Import the parsing methods - we'll test them directly
import cogs.events as events_module


class MockVoteModal:
    """Mock VoteModal that only has the parsing methods."""
    
    def __init__(self):
        # Create a mock instance with just the parsing methods
        self._parse_dates = events_module.VoteModal._parse_dates.__get__(self)
        self._parse_times = events_module.VoteModal._parse_times.__get__(self)


class TestVoteModalParsing:
    """Test VoteModal date and time parsing logic."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.modal = MockVoteModal()
    
    def test_parse_dates_valid_single(self):
        """Test parsing a single valid date."""
        # Get a valid future date
        now = datetime.utcnow()
        future_day = now.day + 1 if now.day < 28 else now.day
        
        result = self.modal._parse_dates(str(future_day))
        
        assert len(result) == 1
        assert isinstance(result[0], str)
        assert result[0].startswith(f"{now.year}-{now.month:02d}-")
    
    def test_parse_dates_valid_multiple(self):
        """Test parsing multiple valid dates."""
        now = datetime.utcnow()
        
        # Get valid future days
        if now.day <= 25:
            dates_input = f"{now.day + 1},{now.day + 2},{now.day + 3}"
            result = self.modal._parse_dates(dates_input)
            assert len(result) == 3
        else:
            # Near end of month, just test with current day
            result = self.modal._parse_dates(str(now.day))
            assert len(result) == 1
    
    def test_parse_dates_with_spaces(self):
        """Test parsing dates with extra spaces."""
        now = datetime.utcnow()
        future_day = now.day + 1 if now.day < 28 else now.day
        
        result = self.modal._parse_dates(f" {future_day} , {future_day} ")
        
        assert len(result) >= 1
    
    def test_parse_dates_empty_raises_error(self):
        """Test that empty dates input raises ValueError."""
        with pytest.raises(ValueError, match="Dates cannot be empty"):
            self.modal._parse_dates("")
    
    def test_parse_dates_invalid_number_raises_error(self):
        """Test that invalid day number raises ValueError."""
        with pytest.raises(ValueError, match="not a valid day number"):
            self.modal._parse_dates("abc")
    
    def test_parse_dates_past_date_raises_error(self):
        """Test that past dates raise ValueError."""
        now = datetime.utcnow()
        if now.day > 1:
            past_day = now.day - 1
            with pytest.raises(ValueError, match="is in the past"):
                self.modal._parse_dates(str(past_day))
    
    def test_parse_dates_invalid_day_raises_error(self):
        """Test that invalid day (e.g., 32) raises ValueError."""
        with pytest.raises(ValueError, match="not valid for this month"):
            self.modal._parse_dates("32")
    
    def test_parse_times_valid_single(self):
        """Test parsing a single valid time."""
        result = self.modal._parse_times("5pm")
        
        assert len(result) == 1
        assert result[0] == "17:00"
    
    def test_parse_times_valid_multiple(self):
        """Test parsing multiple valid times."""
        result = self.modal._parse_times("5pm,6pm,7pm")
        
        assert len(result) == 3
        assert result[0] == "17:00"
        assert result[1] == "18:00"
        assert result[2] == "19:00"
    
    def test_parse_times_all_valid_range(self):
        """Test parsing all valid times in range."""
        result = self.modal._parse_times("5pm,6pm,7pm,8pm,9pm,10pm,11pm")
        
        assert len(result) == 7
        assert result[0] == "17:00"
        assert result[6] == "23:00"
    
    def test_parse_times_with_spaces(self):
        """Test parsing times with extra spaces."""
        result = self.modal._parse_times(" 5pm , 6pm , 7pm ")
        
        assert len(result) == 3
        assert result[0] == "17:00"
    
    def test_parse_times_case_insensitive(self):
        """Test that time parsing is case insensitive."""
        result = self.modal._parse_times("5PM,6Pm,7pM")
        
        assert len(result) == 3
        assert result[0] == "17:00"
    
    def test_parse_times_empty_raises_error(self):
        """Test that empty times input raises ValueError."""
        with pytest.raises(ValueError, match="Times cannot be empty"):
            self.modal._parse_times("")
    
    def test_parse_times_invalid_format_raises_error(self):
        """Test that invalid time format raises ValueError."""
        with pytest.raises(ValueError, match="must end with 'am' or 'pm'"):
            self.modal._parse_times("5")
    
    def test_parse_times_outside_range_raises_error(self):
        """Test that times outside valid range raise ValueError."""
        with pytest.raises(ValueError, match="outside valid range"):
            self.modal._parse_times("3pm")
        
        with pytest.raises(ValueError, match="outside valid range"):
            self.modal._parse_times("1am")
    
    def test_parse_times_invalid_number_raises_error(self):
        """Test that invalid time number raises ValueError."""
        with pytest.raises(ValueError, match="not a valid time format"):
            self.modal._parse_times("abcpm")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
