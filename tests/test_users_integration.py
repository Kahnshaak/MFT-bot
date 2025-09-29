"""
Integration tests for Users cog with bot loading.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from bot import GameNightBot
from cogs.users import UsersCog


class TestUsersIntegration:
    """Integration tests for Users cog."""
    
    @pytest.mark.asyncio
    async def test_users_cog_loads_successfully(self):
        """Test that the Users cog can be loaded by the bot."""
        # Mock the bot's dependencies
        with patch('bot.DatabaseManager') as mock_db_manager, \
             patch('bot.Settings') as mock_settings, \
             patch('discord.Bot.__init__') as mock_bot_init:
            
            # Configure mocks
            mock_bot_init.return_value = None
            mock_settings.return_value.database_url = "mongodb://test"
            mock_settings.return_value.discord_token = "test_token"
            
            mock_db = MagicMock()
            mock_db.connect = AsyncMock()
            mock_db_manager.return_value = mock_db
            
            # Create bot instance
            bot = GameNightBot()
            
            # Mock the required attributes
            bot.database = mock_db
            bot.validation = MagicMock()
            bot.event_bus = MagicMock()
            
            # Test loading the Users cog
            users_cog = UsersCog(bot)
            
            # Verify the cog was created successfully
            assert users_cog is not None
            assert users_cog.bot == bot
            assert users_cog.repositories is not None
            
            # Verify command methods exist
            assert hasattr(users_cog, 'profile_command')
            assert hasattr(users_cog, 'stats_command')
            assert hasattr(users_cog, 'set_timezone_command')
            assert hasattr(users_cog, 'availability_command')
            assert hasattr(users_cog, 'notifications_command')
            assert hasattr(users_cog, 'add_game_command')
            assert hasattr(users_cog, 'remove_game_command')
            assert hasattr(users_cog, 'list_games_command')
            
            # Verify helper methods exist
            assert hasattr(users_cog, 'create_profile_embed')
            assert hasattr(users_cog, 'create_statistics_embed')
            assert hasattr(users_cog, 'create_availability_embed')
            assert hasattr(users_cog, 'create_games_embed')
            assert hasattr(users_cog, 'parse_time')
            
            # Verify event handlers exist
            assert hasattr(users_cog, '_on_user_joined')
            assert hasattr(users_cog, '_on_rsvp_updated')
            assert hasattr(users_cog, '_on_event_completed')
    
    def test_users_cog_command_decorators(self):
        """Test that commands have proper decorators."""
        # Create a mock bot
        mock_bot = MagicMock()
        mock_bot.validation = MagicMock()
        mock_bot.event_bus = MagicMock()
        mock_bot.database = MagicMock()
        
        # Create cog
        users_cog = UsersCog(mock_bot)
        
        # Check that commands are properly decorated
        # Note: This is a basic check - in a real Discord bot, these would be registered as slash commands
        assert callable(users_cog.profile_command)
        assert callable(users_cog.stats_command)
        assert callable(users_cog.set_timezone_command)
        assert callable(users_cog.availability_command)
        assert callable(users_cog.notifications_command)
        assert callable(users_cog.add_game_command)
        assert callable(users_cog.remove_game_command)
        assert callable(users_cog.list_games_command)


if __name__ == "__main__":
    pytest.main([__file__])