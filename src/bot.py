"""
Main bot entry point for the Discord Game Night Scheduling Bot.
"""

import asyncio
import logging
import os
import sys
import signal
import time
from typing import Optional

import discord
from discord.ext import commands

# Add src directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.settings import Settings
from core.event_bus import EventBus
from core.security_manager import SecurityManager
from core.validation_manager import ValidationManager
from core.poll_manager import PollManager
from database.manager import DatabaseManager
from database.migrations import initialize_database
from utils.logging_config import setup_logging


class GameNightBot(commands.Bot):
    """Main bot class for the Discord Game Night Scheduling Bot."""
    
    def __init__(self):
        # Set up intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.guild_messages = True
        intents.guild_reactions = True
        
        super().__init__(
            command_prefix='!',  # Fallback prefix, mainly using slash commands
            intents=intents,
            help_command=None
        )
        
        # Initialize core components - only essential ones
        self.settings = Settings()
        self.database: Optional[DatabaseManager] = None
        self.event_bus: Optional[EventBus] = None
        self.security: Optional[SecurityManager] = None
        self.validation: Optional[ValidationManager] = None
        self.poll_manager: Optional[PollManager] = None
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
    
    async def setup_hook(self):
        """Initialize bot components and load cogs."""
        try:
            self.logger.info("Starting bot setup...")
            
            # Initialize database connection
            self.database = DatabaseManager(self.settings.database_url)
            await self.database.connect()
            
            # Initialize database schema and run migrations
            self.logger.info("Initializing database schema...")
            await initialize_database(self.database)
            
            # Initialize core systems - only essential ones
            self.event_bus = EventBus()
            self.security = SecurityManager(self.settings)
            self.validation = ValidationManager()
            self.poll_manager = PollManager(self.event_bus, self.database)
            
            # Load cogs with error handling
            cogs_to_load = [
                'cogs.events',
                'cogs.users', 
                'cogs.games',
                'cogs.notifications',
                'cogs.timestamps',
                'cogs.admin',
                'cogs.recurring'
            ]
            
            for cog in cogs_to_load:
                try:
                    await self.load_extension(cog)
                    self.logger.info(f"Loaded cog: {cog}")
                except Exception as e:
                    self.logger.error(f"Failed to load cog {cog}: {e}")
                    # Continue loading other cogs
            
            self.logger.info("Bot setup completed successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to setup bot: {e}")
            raise
    
    async def on_ready(self):
        """Called when the bot is ready."""
        self.logger.info(f'{self.user} has connected to Discord!')
        self.logger.info(f'Bot is in {len(self.guilds)} guilds')
    
    async def on_error(self, event, *args, **kwargs):
        """Basic global error handler."""
        self.logger.error(f"Error in event {event}", exc_info=True)

    async def on_command_error(self, ctx, error):
        """Handle command errors with basic logging and user-friendly responses."""
        # Handle specific error types
        from utils.exceptions import (
            PermissionDeniedError, ValidationError, RateLimitedError,
            GameNightBotException
        )
        
        if isinstance(error, commands.CommandNotFound):
            # Ignore command not found errors
            return
        
        elif isinstance(error, PermissionDeniedError):
            await ctx.send(f"❌ {error.user_message}", ephemeral=True)
            
        elif isinstance(error, ValidationError):
            await ctx.send(f"❌ Invalid input: {error.user_message}", ephemeral=True)
            
        elif isinstance(error, RateLimitedError):
            await ctx.send(f"⏰ {error.user_message}", ephemeral=True)
            
        elif isinstance(error, GameNightBotException):
            await ctx.send(f"❌ {error.user_message}", ephemeral=True)
            
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command.", ephemeral=True)
            
        elif isinstance(error, commands.BotMissingPermissions):
            missing_perms = ", ".join(error.missing_permissions)
            await ctx.send(f"❌ I need the following permissions: {missing_perms}", ephemeral=True)
            
        else:
            # Log unexpected errors
            self.logger.error(f"Command error in {ctx.command}: {error}", exc_info=True)
            await ctx.send("❌ An unexpected error occurred. Please try again later.", ephemeral=True)
    
    async def on_application_command_error(self, interaction, error):
        """Handle application command (slash command) errors."""
        from utils.exceptions import (
            PermissionDeniedError, ValidationError, RateLimitedError,
            GameNightBotException
        )
        
        try:
            if isinstance(error, PermissionDeniedError):
                await interaction.response.send_message(f"❌ {error.user_message}", ephemeral=True)
                
            elif isinstance(error, ValidationError):
                await interaction.response.send_message(f"❌ Invalid input: {error.user_message}", ephemeral=True)
                
            elif isinstance(error, RateLimitedError):
                await interaction.response.send_message(f"⏰ {error.user_message}", ephemeral=True)
                
            elif isinstance(error, GameNightBotException):
                await interaction.response.send_message(f"❌ {error.user_message}", ephemeral=True)
                
            else:
                self.logger.error(f"Application command error in {interaction.command}: {error}", exc_info=True)
                
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An unexpected error occurred. Please try again later.", 
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ An unexpected error occurred. Please try again later.", 
                        ephemeral=True
                    )
        except Exception as e:
            self.logger.error(f"Error handling application command error: {e}", exc_info=True)
    



async def main():
    """Main entry point."""
    # Initialize settings
    try:
        settings = Settings()
    except Exception as e:
        print(f"❌ Failed to load settings: {e}")
        print("Please check your .env file and environment variables.")
        sys.exit(1)
    
    # Set up logging
    try:
        setup_logging(settings)
        logger = logging.getLogger(__name__)
    except Exception as e:
        print(f"❌ Failed to setup logging: {e}")
        sys.exit(1)
    
    logger.info("🚀 Starting Discord Game Night Bot...")
    
    # Initialize and start bot
    bot = None
    try:
        bot = GameNightBot()
        
        # Set up graceful shutdown handlers
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            asyncio.create_task(shutdown_bot(bot))
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start the bot
        logger.info("🎮 Bot starting up...")
        await bot.start(settings.discord_token)
        
    except discord.LoginFailure:
        logger.error("❌ Invalid Discord token. Please check your DISCORD_TOKEN environment variable.")
        sys.exit(1)
    except discord.HTTPException as e:
        logger.error(f"❌ Discord HTTP error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"❌ Bot crashed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await shutdown_bot(bot)


async def shutdown_bot(bot: Optional[GameNightBot]) -> None:
    """Gracefully shutdown the bot and cleanup resources."""
    logger = logging.getLogger(__name__)
    
    if bot:
        try:
            logger.info("Shutting down bot...")
            
            # Close database connection
            if hasattr(bot, 'database') and bot.database:
                await bot.database.disconnect()
                logger.info("Database connection closed")
            
            # Close bot connection
            if not bot.is_closed():
                await bot.close()
                logger.info("Bot connection closed")
                
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    logger.info("🛑 Bot shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)