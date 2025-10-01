#!/usr/bin/env python3
"""
Test script to verify the timestamps cog can be loaded and basic functionality works.
"""

import sys
import os
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

async def test_timestamps_cog():
    """Test the timestamps cog functionality."""
    print("🧪 Testing Timestamps Cog...")
    
    try:
        # Import required modules
        from cogs.timestamps import TimestampsCog
        from core.validation_manager import ValidationManager
        from core.event_bus import EventBus
        
        # Create mock bot
        class MockBot:
            def __init__(self):
                self.validation = ValidationManager()
                self.event_bus = EventBus()
        
        bot = MockBot()
        cog = TimestampsCog(bot)
        
        print("✅ TimestampsCog instantiated successfully")
        
        # Test timezone lookup
        result = await cog.lookup_timezone('EST')
        assert result is not None, "Timezone lookup failed"
        assert result['name'] == 'America/New_York', f"Expected America/New_York, got {result['name']}"
        print("✅ Timezone lookup works")
        
        # Test time parsing
        parsed = await cog.parse_time_input('2:30 PM')
        assert parsed is not None, "Time parsing failed"
        assert parsed.hour == 14 and parsed.minute == 30, f"Expected 14:30, got {parsed.hour}:{parsed.minute}"
        print("✅ Time parsing works")
        
        # Test timezone conversion
        test_time = datetime(2024, 1, 15, 20, 30, tzinfo=ZoneInfo('UTC'))
        converted = cog.convert_time_to_timezone(test_time, 'UTC', 'America/New_York')
        assert converted.hour == 15, f"Expected hour 15, got {converted.hour}"
        print("✅ Timezone conversion works")
        
        # Test embed creation
        embed = cog.create_timestamp_formats_embed(test_time)
        assert embed.title == "📅 Discord Timestamp Formats", f"Unexpected embed title: {embed.title}"
        assert len(embed.fields) == 7, f"Expected 7 fields, got {len(embed.fields)}"
        print("✅ Embed creation works")
        
        # Test command methods exist
        commands = ['convert_time', 'timezone_info', 'format_timestamp', 'current_time']
        for cmd in commands:
            assert hasattr(cog, cmd), f"Missing command method: {cmd}"
        print("✅ All command methods exist")
        
        print("\n🎉 All tests passed! Timestamps cog is ready for use.")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure all dependencies are installed and the bot structure is correct.")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_timestamps_cog())
    sys.exit(0 if result else 1)