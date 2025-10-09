#!/usr/bin/env python3
"""
Simple test to verify bot can start up without errors.
"""

import asyncio
import os
import sys
from unittest.mock import patch, MagicMock

# Add src directory to Python path
sys.path.append('src')

async def test_bot_startup():
    """Test that the bot can initialize without errors."""
    print("Testing bot startup...")
    
    # Mock Discord token and database URL
    with patch.dict(os.environ, {
        'DISCORD_TOKEN': 'fake_token_for_testing',
        'DATABASE_URL': 'mongodb://localhost:27017/test_db'
    }):
        try:
            from src.bot import GameNightBot
            
            # Create bot instance
            bot = GameNightBot()
            
            # Verify bot was created successfully
            assert bot is not None
            assert hasattr(bot, 'database')
            assert hasattr(bot, 'event_bus')
            assert hasattr(bot, 'security')
            assert hasattr(bot, 'validation')
            assert hasattr(bot, 'poll_manager')
            
            print("✅ Bot initialization successful")
            
            # Test that essential components are initialized
            assert bot.database is None  # Not connected yet
            assert bot.event_bus is None  # Not initialized yet
            assert bot.security is None  # Not initialized yet
            assert bot.validation is None  # Not initialized yet
            assert bot.poll_manager is None  # Not initialized yet
            
            print("✅ Bot components properly initialized as None before setup")
            
        except Exception as e:
            print(f"❌ Bot startup failed: {e}")
            raise

async def test_core_components():
    """Test that core components can be created."""
    print("Testing core components...")
    
    try:
        from core.event_bus import EventBus
        from core.security_manager import SecurityManager
        from core.validation_manager import ValidationManager
        from core.poll_manager import PollManager
        from database.manager import DatabaseManager
        from config.settings import Settings
        
        # Test EventBus
        event_bus = EventBus()
        assert event_bus is not None
        print("✅ EventBus created successfully")
        
        # Test ValidationManager
        validation = ValidationManager()
        assert validation is not None
        print("✅ ValidationManager created successfully")
        
        # Test Settings (with mocked environment)
        with patch.dict(os.environ, {
            'DISCORD_TOKEN': 'fake_token',
            'DATABASE_URL': 'mongodb://localhost:27017/test'
        }):
            settings = Settings()
            assert settings is not None
            print("✅ Settings loaded successfully")
            
            # Test SecurityManager
            security = SecurityManager(settings)
            assert security is not None
            print("✅ SecurityManager created successfully")
        
        # Test DatabaseManager (without connecting)
        db = DatabaseManager("mongodb://localhost:27017/test")
        assert db is not None
        print("✅ DatabaseManager created successfully")
        
        # Test PollManager
        poll_manager = PollManager(event_bus, db)
        assert poll_manager is not None
        print("✅ PollManager created successfully")
        
    except Exception as e:
        print(f"❌ Core component test failed: {e}")
        raise

async def test_models():
    """Test that models can be created."""
    print("Testing models...")
    
    try:
        from models.event import Event, EventState, RSVPStatus
        from models.user import User
        from models.recurring import RecurringSchedule, ScheduleStatus
        from datetime import time
        
        # Test Event model
        event = Event(
            guild_id="123456789012345678",
            title="Test Event",
            description="Test Description",
            creator_id="987654321098765432"
        )
        assert event.guild_id == "123456789012345678"
        assert event.state == EventState.DRAFT
        print("✅ Event model created successfully")
        
        # Test User model
        user = User(
            user_id="123456789012345678",
            guild_id="987654321098765432"
        )
        assert user.user_id == "123456789012345678"
        assert user.timezone == "UTC"
        print("✅ User model created successfully")
        
        # Test RecurringSchedule model
        schedule = RecurringSchedule(
            guild_id="123456789012345678",
            name="Test Schedule",
            creator_id="987654321098765432",
            day_of_week=0,
            trigger_time=time(18, 0),
            event_title="Test Event"
        )
        assert schedule.status == ScheduleStatus.ACTIVE
        print("✅ RecurringSchedule model created successfully")
        
        # Test RSVP functionality
        event.add_rsvp("user123", RSVPStatus.YES)
        assert len(event.rsvps) == 1
        assert event.rsvps["user123"].status == RSVPStatus.YES
        print("✅ RSVP functionality working")
        
        # Test game interests
        result = user.add_game_interest("Test Game", True)
        assert result is True
        assert len(user.game_interests) == 1
        print("✅ Game interest functionality working")
        
    except Exception as e:
        print(f"❌ Model test failed: {e}")
        raise

async def main():
    """Run all tests."""
    print("🚀 Starting core bot functionality tests...\n")
    
    try:
        await test_core_components()
        print()
        
        await test_models()
        print()
        
        await test_bot_startup()
        print()
        
        print("🎉 All tests passed! Core functionality is working correctly.")
        return True
        
    except Exception as e:
        print(f"\n💥 Tests failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)