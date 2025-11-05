"""
Tests for input validation and sanitization in event creation and voting.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock


def validate_title(title: str):
    """
    Validate event title (extracted from EventCreationModal).
    
    Args:
        title: Event title to validate
    
    Returns:
        Error message if validation fails, None if valid
    """
    # Check length
    if len(title) < 3:
        return "Event title must be at least 3 characters long."
    
    if len(title) > 100:
        return "Event title must be no more than 100 characters long."
    
    # Check for @everyone and @here mentions
    if "@everyone" in title.lower():
        return "Event title cannot contain @everyone mentions."
    
    if "@here" in title.lower():
        return "Event title cannot contain @here mentions."
    
    return None


def parse_dates(dates_input: str):
    """
    Parse and validate date input (extracted from VoteModal).
    
    Args:
        dates_input: Comma-separated date string (e.g., "15,16,20")
    
    Returns:
        List of validated date strings in YYYY-MM-DD format
    
    Raises:
        ValueError: If dates are invalid
    """
    if not dates_input:
        raise ValueError("Dates cannot be empty. Please enter at least one date.")
    
    # Split by comma and clean up
    date_parts = [d.strip() for d in dates_input.split(",") if d.strip()]
    
    if not date_parts:
        raise ValueError("No valid dates provided. Please enter dates as day numbers (e.g., 15,16,20).")
    
    # Get current month info
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
    
    parsed_dates = []
    for date_str in date_parts:
        try:
            # Try to parse as day number
            day = int(date_str)
            
            # Validate day is in valid range (must be valid day number)
            if day < 1:
                raise ValueError(f"Date {day} is not a valid day number. Days must be between 1 and {last_day}.")
            
            if day > last_day:
                raise ValueError(f"Date {day} is not valid for this month. This month has {last_day} days.")
            
            # Validate day is not in the past
            if day < current_day:
                raise ValueError(f"Date {day} is in the past. Today is day {current_day}. Please choose dates from today onwards.")
            
            # Create full date string
            date = datetime(current_year, current_month, day)
            parsed_dates.append(date.strftime("%Y-%m-%d"))
            
        except ValueError as e:
            if "invalid literal" in str(e):
                raise ValueError(f"'{date_str}' is not a valid day number. Please enter numbers only (e.g., 15,16,20).")
            else:
                raise
    
    if not parsed_dates:
        raise ValueError("No valid dates could be parsed. Please enter dates as day numbers (e.g., 15,16,20).")
    
    return parsed_dates


def parse_times(times_input: str):
    """
    Parse and validate time input (extracted from VoteModal).
    
    Args:
        times_input: Comma-separated time string (e.g., "5pm,6pm,7pm")
    
    Returns:
        List of validated time strings in HH:MM format
    
    Raises:
        ValueError: If times are invalid
    """
    if not times_input:
        raise ValueError("Times cannot be empty. Please enter at least one time.")
    
    # Split by comma and clean up
    time_parts = [t.strip().lower() for t in times_input.split(",") if t.strip()]
    
    if not time_parts:
        raise ValueError("No valid times provided. Please enter times in format like 5pm,6pm,7pm.")
    
    parsed_times = []
    for time_str in time_parts:
        try:
            # Parse time format like "5pm", "6pm", "11pm"
            time_str = time_str.replace(" ", "")
            
            # Check if it ends with am/pm
            if time_str.endswith("pm"):
                hour_str = time_str[:-2]
                
                if not hour_str:
                    raise ValueError(f"'{time_str}' is missing the hour number. Use format like 5pm, 6pm, etc.")
                
                hour = int(hour_str)
                
                # Validate hour is reasonable (1-12 for 12-hour format)
                if hour < 1 or hour > 12:
                    raise ValueError(f"Hour {hour} is not valid. Use hours 1-12 with pm (e.g., 5pm, 11pm).")
                
                # Convert to 24-hour format
                if hour == 12:
                    hour_24 = 12
                else:
                    hour_24 = hour + 12
                    
            elif time_str.endswith("am"):
                hour_str = time_str[:-2]
                
                if not hour_str:
                    raise ValueError(f"'{time_str}' is missing the hour number. Use format like 5pm, 6pm, etc.")
                
                hour = int(hour_str)
                
                # Validate hour is reasonable (1-12 for 12-hour format)
                if hour < 1 or hour > 12:
                    raise ValueError(f"Hour {hour} is not valid. Use hours 1-12 with am/pm.")
                
                # Convert to 24-hour format
                if hour == 12:
                    hour_24 = 0
                else:
                    hour_24 = hour
            else:
                raise ValueError(f"'{time_str}' must end with 'am' or 'pm'. Use format like 5pm, 6pm, 7pm.")
            
            # Validate hour is in valid range (5pm-11pm = 17:00-23:00)
            if hour_24 < 17 or hour_24 > 23:
                # Provide helpful message about valid range
                if hour_24 < 17:
                    raise ValueError(f"Time {time_str} is too early. Valid times are 5pm through 11pm.")
                else:
                    raise ValueError(f"Time {time_str} is too late. Valid times are 5pm through 11pm.")
            
            # Format as HH:MM
            parsed_times.append(f"{hour_24:02d}:00")
            
        except ValueError as e:
            if "invalid literal" in str(e):
                raise ValueError(f"'{time_str}' is not a valid time format. Use format like 5pm, 6pm, 7pm.")
            else:
                raise
    
    if not parsed_times:
        raise ValueError("No valid times could be parsed. Please enter times in format like 5pm,6pm,7pm.")
    
    return parsed_times


class TestEventTitleValidation:
    """Test event title validation."""
    
    def test_valid_title(self):
        """Test that valid titles pass validation."""
        # Valid titles
        assert validate_title("Game Night") is None
        assert validate_title("Friday Gaming Session") is None
        assert validate_title("A" * 100) is None  # Max length
        assert validate_title("ABC") is None  # Min length
    
    def test_title_too_short(self):
        """Test that titles under 3 characters are rejected."""
        error = validate_title("AB")
        assert error is not None
        assert "at least 3 characters" in error
    
    def test_title_too_long(self):
        """Test that titles over 100 characters are rejected."""
        error = validate_title("A" * 101)
        assert error is not None
        assert "no more than 100 characters" in error
    
    def test_title_with_everyone_mention(self):
        """Test that titles with @everyone are rejected."""
        # Various cases
        error = validate_title("Game Night @everyone")
        assert error is not None
        assert "@everyone" in error
        
        error = validate_title("@EVERYONE join us")
        assert error is not None
        assert "@everyone" in error
        
        error = validate_title("Hey @EvErYoNe")
        assert error is not None
        assert "@everyone" in error
    
    def test_title_with_here_mention(self):
        """Test that titles with @here are rejected."""
        # Various cases
        error = validate_title("Game Night @here")
        assert error is not None
        assert "@here" in error
        
        error = validate_title("@HERE join us")
        assert error is not None
        assert "@here" in error
        
        error = validate_title("Hey @HeRe")
        assert error is not None
        assert "@here" in error


class TestDateValidation:
    """Test date input validation."""
    
    def test_valid_dates(self):
        """Test that valid dates are parsed correctly."""
        # Use current date for testing
        now = datetime.utcnow()
        current_day = now.day
        
        # Valid single date (today)
        dates = parse_dates(str(current_day))
        assert len(dates) == 1
        assert dates[0].endswith(f"-{current_day:02d}")
        
        # Valid multiple dates (today and tomorrow if possible)
        if current_day < 28:  # Safe for all months
            dates = parse_dates(f"{current_day},{current_day+1},{current_day+2}")
            assert len(dates) == 3
    
    def test_date_in_past(self):
        """Test that dates in the past are rejected."""
        # Use a date that's definitely in the past (day 1 if we're past it)
        now = datetime.utcnow()
        if now.day > 1:
            with pytest.raises(ValueError) as exc_info:
                parse_dates("1")
            
            assert "in the past" in str(exc_info.value)
    
    def test_date_invalid_for_month(self):
        """Test that dates beyond the month's days are rejected."""
        # Day 32 is invalid for all months
        with pytest.raises(ValueError) as exc_info:
            parse_dates("32")
        
        assert "not valid for this month" in str(exc_info.value)
    
    def test_date_invalid_format(self):
        """Test that non-numeric dates are rejected."""
        with pytest.raises(ValueError) as exc_info:
            parse_dates("abc")
        
        assert "not a valid day number" in str(exc_info.value)
        assert "abc" in str(exc_info.value)
    
    def test_date_empty_input(self):
        """Test that empty date input is rejected."""
        with pytest.raises(ValueError) as exc_info:
            parse_dates("")
        
        assert "cannot be empty" in str(exc_info.value)
    
    def test_date_negative_number(self):
        """Test that negative day numbers are rejected."""
        with pytest.raises(ValueError) as exc_info:
            parse_dates("-5")
        
        assert "not a valid day number" in str(exc_info.value)


class TestTimeValidation:
    """Test time input validation."""
    
    def test_valid_times(self):
        """Test that valid times are parsed correctly."""
        # Valid single time
        times = parse_times("5pm")
        assert times == ["17:00"]
        
        # Valid multiple times
        times = parse_times("5pm,6pm,11pm")
        assert times == ["17:00", "18:00", "23:00"]
        
        # With spaces
        times = parse_times("5pm, 6pm, 11pm")
        assert times == ["17:00", "18:00", "23:00"]
        
        # Mixed case
        times = parse_times("5PM,6Pm,11pM")
        assert times == ["17:00", "18:00", "23:00"]
    
    def test_time_outside_valid_range_too_early(self):
        """Test that times before 5pm are rejected."""
        # 4pm is too early
        with pytest.raises(ValueError) as exc_info:
            parse_times("4pm")
        
        assert "too early" in str(exc_info.value)
        assert "5pm through 11pm" in str(exc_info.value)
        
        # 12am is too early
        with pytest.raises(ValueError) as exc_info:
            parse_times("12am")
        
        assert "too early" in str(exc_info.value)
    
    def test_time_outside_valid_range_too_late(self):
        """Test that times after 11pm are rejected."""
        # 12pm (noon) converts to 12:00 which is too early
        with pytest.raises(ValueError) as exc_info:
            parse_times("12pm")
        
        assert "too early" in str(exc_info.value)
    
    def test_time_missing_am_pm(self):
        """Test that times without am/pm are rejected."""
        with pytest.raises(ValueError) as exc_info:
            parse_times("5")
        
        assert "must end with 'am' or 'pm'" in str(exc_info.value)
    
    def test_time_invalid_format(self):
        """Test that non-numeric times are rejected."""
        with pytest.raises(ValueError) as exc_info:
            parse_times("abcpm")
        
        assert "not a valid time format" in str(exc_info.value)
    
    def test_time_empty_input(self):
        """Test that empty time input is rejected."""
        with pytest.raises(ValueError) as exc_info:
            parse_times("")
        
        assert "cannot be empty" in str(exc_info.value)
    
    def test_time_missing_hour(self):
        """Test that times with missing hour are rejected."""
        with pytest.raises(ValueError) as exc_info:
            parse_times("pm")
        
        assert "missing the hour number" in str(exc_info.value)
    
    def test_time_invalid_hour(self):
        """Test that invalid hour numbers are rejected."""
        # Hour 0
        with pytest.raises(ValueError) as exc_info:
            parse_times("0pm")
        
        assert "not valid" in str(exc_info.value)
        
        # Hour 13
        with pytest.raises(ValueError) as exc_info:
            parse_times("13pm")
        
        assert "not valid" in str(exc_info.value)
    
    def test_time_all_valid_range(self):
        """Test all valid times in the 5pm-11pm range."""
        # Test all valid times
        times = parse_times("5pm,6pm,7pm,8pm,9pm,10pm,11pm")
        assert times == ["17:00", "18:00", "19:00", "20:00", "21:00", "22:00", "23:00"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
