"""
Manual test script to demonstrate VoteModal parsing functionality.
Run this to see how the VoteModal parses dates and times.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from datetime import datetime
from cogs.events import VoteModal
from unittest.mock import Mock


class MockVoteModal:
    """Mock VoteModal that only has the parsing methods."""
    
    def __init__(self):
        # Create a mock instance with just the parsing methods
        self._parse_dates = VoteModal._parse_dates.__get__(self)
        self._parse_times = VoteModal._parse_times.__get__(self)


def test_date_parsing():
    """Test date parsing with various inputs."""
    print("=" * 60)
    print("TESTING DATE PARSING")
    print("=" * 60)
    
    modal = MockVoteModal()
    
    # Get current date info for testing
    now = datetime.utcnow()
    future_day = now.day + 1 if now.day < 28 else now.day
    
    test_cases = [
        (f"{future_day}", "Single valid date"),
        (f"{future_day},{future_day+1 if future_day < 28 else future_day}", "Multiple valid dates"),
        (f" {future_day} , {future_day+1 if future_day < 28 else future_day} ", "Dates with spaces"),
        ("", "Empty input (should fail)"),
        ("abc", "Invalid text (should fail)"),
        ("32", "Invalid day number (should fail)"),
    ]
    
    for input_str, description in test_cases:
        print(f"\nTest: {description}")
        print(f"Input: '{input_str}'")
        try:
            result = modal._parse_dates(input_str)
            print(f"✅ Result: {result}")
        except ValueError as e:
            print(f"❌ Error: {e}")


def test_time_parsing():
    """Test time parsing with various inputs."""
    print("\n" + "=" * 60)
    print("TESTING TIME PARSING")
    print("=" * 60)
    
    modal = MockVoteModal()
    
    test_cases = [
        ("5pm", "Single valid time"),
        ("5pm,6pm,7pm", "Multiple valid times"),
        (" 5pm , 6pm , 7pm ", "Times with spaces"),
        ("5PM,6Pm,7pM", "Mixed case"),
        ("5pm,6pm,7pm,8pm,9pm,10pm,11pm", "All valid times"),
        ("", "Empty input (should fail)"),
        ("5", "Missing am/pm (should fail)"),
        ("3pm", "Outside range (should fail)"),
        ("1am", "Outside range (should fail)"),
        ("abcpm", "Invalid format (should fail)"),
    ]
    
    for input_str, description in test_cases:
        print(f"\nTest: {description}")
        print(f"Input: '{input_str}'")
        try:
            result = modal._parse_times(input_str)
            print(f"✅ Result: {result}")
        except ValueError as e:
            print(f"❌ Error: {e}")


def main():
    """Run all manual tests."""
    print("\n" + "=" * 60)
    print("VOTEMMODAL PARSING DEMONSTRATION")
    print("=" * 60)
    print(f"Current date: {datetime.utcnow().strftime('%Y-%m-%d')}")
    print(f"Current time: {datetime.utcnow().strftime('%H:%M:%S')} UTC")
    
    test_date_parsing()
    test_time_parsing()
    
    print("\n" + "=" * 60)
    print("DEMONSTRATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
