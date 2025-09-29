"""
Tests for the Users cog functionality.
"""

import pytest
import asyncio
from datetime import time
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from cogs.users import UsersCog
from models.user import User, DayOfWeek, NotificationChannel, NotificationTiming
from models.repositories import RepositoryManager
from core.event_bus import EventBus
from core.validation_manager import ValidationManager


class TestUsersCog:
    """Test cases for Users cog."""
    
    @pytest.fixture
    def mock_bot(self):
        """Create a mock bot instance."""
        bot = MagicMock()
        bot.validation = ValidationManager()
        bot.event_bus = EventBus()
        bot.database = MagicMock()
        return bot
    
    @pytest.fixture
    def users_cog(self, mock_bot):
        """Create a Users cog instance."""
        return UsersCog(mock_bot)
    
    @pytest.fixture
    def sample_user(self):
        """Create a sample user for testing."""
        return User(
            user_id="123456789",
            guild_id="987654321",
            display_name="TestUser",
            timezone="America/New_York"
        )
    
    def test_parse_time_24_hour(self, users_cog):
        """Test parsing 24-hour time format."""
        result = users_cog.parse_time("18:30")
        assert result == time(18, 30)
    
    def test_parse_time_12_hour(self, users_cog):
        """Test parsing 12-hour time format."""
        result = users_cog.parse_time("6:30 PM")
        assert result == time(18, 30)
    
    def test_parse_time_invalid(self, users_cog):
        """Test parsing invalid time format."""
        result = users_cog.parse_time("invalid")
        assert result is None
    
    def test_create_profile_embed(self, users_cog, sample_user):
        """Test creating profile embed."""
        mock_discord_user = MagicMock()
        mock_discord_user.display_name = "TestUser"
        mock_discord_user.display_avatar.url = "https://example.com/avatar.png"
        
        embed = users_cog.create_profile_embed(sample_user, mock_discord_user)
        
        assert embed.title == "🎮 TestUser's Profile"
        assert any(field.name == "🌍 Timezone" for field in embed.fields)
        assert any(field.value == "America/New_York" for field in embed.fields)
    
    def test_create_statistics_embed(self, users_cog, sample_user):
        """Test creating statistics embed."""
        mock_discord_user = MagicMock()
        mock_discord_user.display_name = "TestUser"
        mock_discord_user.display_avatar.url = "https://example.com/avatar.png"
        
        # Add some statistics
        sample_user.statistics.events_created = 5
        sample_user.statistics.events_attended = 3
        sample_user.statistics.events_rsvp_yes = 4
        sample_user.statistics.attendance_rate = 0.75
        
        embed = users_cog.create_statistics_embed(sample_user, mock_discord_user)
        
        assert embed.title == "📊 TestUser's Statistics"
        assert any("Created:** 5" in field.value for field in embed.fields)
        assert any("Attended:** 3" in field.value for field in embed.fields)
    
    def test_create_availability_embed_empty(self, users_cog, sample_user):
        """Test creating availability embed with no availability."""
        embed = users_cog.create_availability_embed(sample_user)
        
        assert embed.title == "📅 Your Availability"
        assert any(field.name == "No Availability Set" for field in embed.fields)
    
    def test_create_availability_embed_with_slots(self, users_cog, sample_user):
        """Test creating availability embed with availability slots."""
        # Add availability slot
        sample_user.add_availability_slot(DayOfWeek.MONDAY, time(18, 0), time(22, 0))
        
        embed = users_cog.create_availability_embed(sample_user)
        
        assert embed.title == "📅 Your Availability"
        assert any(field.name == "Monday" for field in embed.fields)
        assert any("18:00 - 22:00" in field.value for field in embed.fields)
    
    def test_create_games_embed_empty(self, users_cog, sample_user):
        """Test creating games embed with no interests."""
        mock_discord_user = MagicMock()
        mock_discord_user.display_name = "TestUser"
        mock_discord_user.display_avatar.url = "https://example.com/avatar.png"
        
        embed = users_cog.create_games_embed(sample_user, mock_discord_user)
        
        assert embed.title == "🎮 TestUser's Game Interests"
        assert embed.description == "No game interests added yet."
    
    def test_create_games_embed_with_interests(self, users_cog, sample_user):
        """Test creating games embed with game interests."""
        mock_discord_user = MagicMock()
        mock_discord_user.display_name = "TestUser"
        mock_discord_user.display_avatar.url = "https://example.com/avatar.png"
        
        # Add game interests
        sample_user.add_game_interest("Chess", 8)
        sample_user.add_game_interest("Monopoly", 6)
        
        embed = users_cog.create_games_embed(sample_user, mock_discord_user)
        
        assert embed.title == "🎮 TestUser's Game Interests"
        assert "Chess" in embed.description
        assert "Monopoly" in embed.description
        assert "Level 8/10" in embed.description
        assert "Level 6/10" in embed.description
    
    @pytest.mark.asyncio
    async def test_update_user_timezone(self, users_cog, sample_user):
        """Test updating user timezone."""
        with patch.object(users_cog.repositories, 'ensure_user_profile', return_value=sample_user) as mock_ensure, \
             patch.object(users_cog.repositories.users, 'update', return_value=True) as mock_update, \
             patch.object(users_cog.event_bus, 'emit') as mock_emit:
            
            await users_cog.update_user_timezone("123456789", "987654321", "Europe/London")
            
            assert sample_user.timezone == "Europe/London"
            mock_ensure.assert_called_once_with("123456789", "987654321")
            mock_update.assert_called_once()
            mock_emit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_add_availability_slot_success(self, users_cog, sample_user):
        """Test successfully adding availability slot."""
        with patch.object(users_cog.repositories, 'ensure_user_profile', return_value=sample_user) as mock_ensure, \
             patch.object(users_cog.repositories.users, 'update', return_value=True) as mock_update, \
             patch.object(users_cog.event_bus, 'emit') as mock_emit:
            
            result = await users_cog.add_availability_slot(
                "123456789", "987654321", 
                DayOfWeek.TUESDAY, time(19, 0), time(23, 0)
            )
            
            assert result is True
            assert len(sample_user.availability) == 1
            assert sample_user.availability[0].day == DayOfWeek.TUESDAY
            mock_ensure.assert_called_once()
            mock_update.assert_called_once()
            mock_emit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_add_availability_slot_overlap(self, users_cog, sample_user):
        """Test adding overlapping availability slot."""
        # Add initial slot
        sample_user.add_availability_slot(DayOfWeek.TUESDAY, time(18, 0), time(22, 0))
        
        with patch.object(users_cog.repositories, 'ensure_user_profile', return_value=sample_user):
            result = await users_cog.add_availability_slot(
                "123456789", "987654321", 
                DayOfWeek.TUESDAY, time(20, 0), time(23, 59)  # Overlaps with existing
            )
            
            assert result is False
            assert len(sample_user.availability) == 1  # No new slot added
    
    @pytest.mark.asyncio
    async def test_update_notification_preferences(self, users_cog, sample_user):
        """Test updating notification preferences."""
        with patch.object(users_cog.repositories, 'ensure_user_profile', return_value=sample_user) as mock_ensure, \
             patch.object(users_cog.repositories.users, 'update', return_value=True) as mock_update, \
             patch.object(users_cog.event_bus, 'emit') as mock_emit:
            
            await users_cog.update_notification_preferences(
                "123456789", "987654321",
                NotificationChannel.DM,
                NotificationTiming.HOUR_BEFORE,
                time(22, 0),  # quiet start
                time(8, 0)    # quiet end
            )
            
            assert sample_user.notification_preferences.channel == NotificationChannel.DM
            assert sample_user.notification_preferences.reminder_timing == NotificationTiming.HOUR_BEFORE
            assert sample_user.notification_preferences.quiet_hours_start == time(22, 0)
            assert sample_user.notification_preferences.quiet_hours_end == time(8, 0)
            
            mock_ensure.assert_called_once()
            mock_update.assert_called_once()
            mock_emit.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])