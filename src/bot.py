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
        
        # Set up logging first
        self.logger = logging.getLogger(__name__)
        self.logger.info("Bot instance created")
        
        # Initialize core components - only essential ones
        self.settings = Settings()
        self.database: Optional[DatabaseManager] = None
        self.event_bus: Optional[EventBus] = None
        self.security: Optional[SecurityManager] = None
        self.validation: Optional[ValidationManager] = None
        self.poll_manager: Optional[PollManager] = None
        self._initialized = False
    
    async def setup_hook(self):
        """Initialize bot components and load cogs."""
        print("🔧 setup_hook called!")  # Simple print to see if this is called
        try:
            self.logger.info("🔧 setup_hook called - starting bot setup...")
        except Exception as e:
            print(f"Error in setup_hook logging: {e}")
            return
        
        try:
            self.logger.info("Starting bot setup...")
            
            # Initialize database connection
            self.database = DatabaseManager(self.settings.database_url)
            self.logger.info("Connecting to database...")
            await self.database.connect()
            self.logger.info("Database connected successfully")
            
            # Initialize database schema and run migrations
            self.logger.info("Initializing database schema...")
            await initialize_database(self.database)
            self.logger.info("Database schema initialized")
            
            # Initialize core systems - only essential ones
            self.logger.info("Initializing core systems...")
            self.event_bus = EventBus()
            self.security = SecurityManager(self.settings)
            self.validation = ValidationManager()
            self.poll_manager = PollManager(self.event_bus, self.database)
            self.logger.info("Core systems initialized")
            
            # Load cogs with error handling
            self.logger.info("Loading cogs...")
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
                    self.logger.info(f"Loading cog: {cog}")
                    await self.load_extension(cog)
                    self.logger.info(f"✅ Loaded cog: {cog}")
                except Exception as e:
                    self.logger.error(f"❌ Failed to load cog {cog}: {e}", exc_info=True)
                    # Continue loading other cogs
            
            self.logger.info("Bot setup completed successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to setup bot: {e}")
            raise
    
    async def _initialize_bot(self):
        """Initialize bot components and load cogs."""
        print("🔧 _initialize_bot called!")  # Simple print to see if this is called
        try:
            self.logger.info("🔧 Initializing bot components...")
            
            # Initialize database connection
            self.database = DatabaseManager(self.settings.database_url)
            self.logger.info("Connecting to database...")
            await self.database.connect()
            self.logger.info("Database connected successfully")
            
            # Initialize database schema and run migrations
            self.logger.info("Initializing database schema...")
            await initialize_database(self.database)
            self.logger.info("Database schema initialized")
            
            # Initialize core systems - only essential ones
            self.logger.info("Initializing core systems...")
            self.event_bus = EventBus()
            self.security = SecurityManager(self.settings)
            self.validation = ValidationManager()
            self.poll_manager = PollManager(self.event_bus, self.database)
            self.logger.info("Core systems initialized")
            
            # Load cogs with error handling
            self.logger.info("Loading cogs...")
            cogs_to_load = [
                'cogs.events',  # Only load events cog for now
                # 'cogs.users', 
                # 'cogs.games',
                # 'cogs.notifications',
                # 'cogs.timestamps',
                # 'cogs.admin',
                # 'cogs.recurring'
            ]
            
            # Load events cog manually for now
            try:
                self.logger.info("Loading EventsCog manually...")
                from cogs.events import EventsCog
                cog_instance = EventsCog(self)
                self.logger.info("EventsCog instance created")
                result = self.add_cog(cog_instance)
                self.logger.info(f"add_cog returned: {result}")
                if result is not None:
                    await result
                self.logger.info("✅ Loaded EventsCog successfully")
            except Exception as e:
                self.logger.error(f"❌ Failed to load EventsCog: {e}", exc_info=True)
            
            self.logger.info("Bot initialization completed successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize bot: {e}", exc_info=True)
            raise
    
    async def on_modal_error(self, interaction, error):
        """Handle modal errors."""
        self.logger.error("=" * 80)
        self.logger.error("MODAL ERROR DETECTED")
        self.logger.error("=" * 80)
        self.logger.error(f"Modal: {interaction.data.get('custom_id', 'Unknown')}")
        self.logger.error(f"User: {interaction.user.id}")
        self.logger.error(f"Guild: {interaction.guild.id if interaction.guild else 'None'}")
        self.logger.error(f"Error: {error}")
        self.logger.error(f"Error type: {type(error)}")
        
        import traceback
        self.logger.error("Full traceback:")
        self.logger.error(traceback.format_exc())
        self.logger.error("=" * 80)
    
    # Removed on_interaction handler as it might be interfering with command processing
    
    async def on_ready(self):
        """Called when the bot is ready."""
        self.logger.info(f'{self.user} has connected to Discord!')
        self.logger.info(f'Bot is in {len(self.guilds)} guilds')
        
        # Initialize bot components if not already done
        if not self._initialized:
            self.logger.info("Starting bot initialization...")
            await self._initialize_bot()
            self._initialized = True
        else:
            self.logger.info("Bot already initialized, skipping...")
        
        # Check what commands are available
        self.logger.info(f"Available commands: {[cmd.name for cmd in self.commands]}")
        self.logger.info(f"Available slash commands: {[cmd.name for cmd in self.pending_application_commands]}")
        
        # Sync slash commands
        try:
            self.logger.info("Syncing slash commands...")
            self.logger.info(f"Bot has {len(self.pending_application_commands)} pending commands")
            
            # Debug: Print command details
            for cmd in self.pending_application_commands:
                self.logger.info(f"Command: {cmd.name} - Type: {type(cmd)} - Guild IDs: {getattr(cmd, 'guild_ids', 'None')}")
            
            # Try the basic sync_commands method
            self.logger.info("Calling sync_commands()...")
            synced = await self.sync_commands()
            
            self.logger.info(f"sync_commands() returned: {synced} (type: {type(synced)})")
            
            if synced is not None:
                if isinstance(synced, list):
                    self.logger.info(f"Successfully synced {len(synced)} commands")
                    for cmd in synced:
                        self.logger.info(f"  - Synced: {cmd.name}")
                else:
                    self.logger.info(f"Sync returned non-list: {synced}")
            else:
                self.logger.info("✅ Commands sync initiated (py-cord returns None on success)")
                self.logger.info("Guild-specific commands should appear in Discord within 1-2 minutes")
                self.logger.info("If commands don't appear, check bot permissions and try restarting Discord")
                
        except Exception as e:
            self.logger.error(f"Failed to sync commands: {e}", exc_info=True)
    
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
        import traceback
        import sys
        
        self.logger.error("=" * 80)
        self.logger.error("APPLICATION COMMAND ERROR - DETAILED ANALYSIS")
        self.logger.error("=" * 80)
        
        # Command information
        self.logger.error(f"Command Name: {interaction.command.name if interaction.command else 'Unknown'}")
        self.logger.error(f"Command Qualified Name: {interaction.command.qualified_name if interaction.command else 'Unknown'}")
        self.logger.error(f"Command Module: {interaction.command.callback.__module__ if interaction.command and hasattr(interaction.command, 'callback') else 'Unknown'}")
        self.logger.error(f"Command Function: {interaction.command.callback.__name__ if interaction.command and hasattr(interaction.command, 'callback') else 'Unknown'}")
        
        # User and guild information
        self.logger.error(f"User ID: {interaction.user.id}")
        self.logger.error(f"User Name: {interaction.user.name}")
        self.logger.error(f"User Type: {type(interaction.user)}")
        self.logger.error(f"Guild ID: {interaction.guild.id if interaction.guild else 'None'}")
        self.logger.error(f"Guild Name: {interaction.guild.name if interaction.guild else 'None'}")
        
        # Error details
        self.logger.error(f"Error Message: {str(error)}")
        self.logger.error(f"Error Type: {type(error).__name__}")
        self.logger.error(f"Error Module: {type(error).__module__}")
        self.logger.error(f"Error Args: {error.args}")
        
        # Check for nested errors
        if hasattr(error, 'original'):
            self.logger.error(f"Original Error: {error.original}")
            self.logger.error(f"Original Error Type: {type(error.original).__name__}")
            self.logger.error(f"Original Error Module: {type(error.original).__module__}")
        
        if hasattr(error, '__cause__') and error.__cause__:
            self.logger.error(f"Error Cause: {error.__cause__}")
            self.logger.error(f"Cause Type: {type(error.__cause__).__name__}")
        
        if hasattr(error, '__context__') and error.__context__:
            self.logger.error(f"Error Context: {error.__context__}")
            self.logger.error(f"Context Type: {type(error.__context__).__name__}")
        
        # Full stack trace
        self.logger.error("FULL STACK TRACE:")
        if hasattr(error, '__traceback__') and error.__traceback__:
            tb_lines = traceback.format_exception(type(error), error, error.__traceback__)
            for line in tb_lines:
                self.logger.error(line.rstrip())
        else:
            self.logger.error("No traceback available")
        
        # Additional debugging for PermissionDeniedError
        if isinstance(error, Exception) and "PermissionDeniedError" in str(type(error)):
            self.logger.error("PERMISSION ERROR ANALYSIS:")
            self.logger.error(f"Error string contains: {str(error)}")
            if hasattr(error, 'user_message'):
                self.logger.error(f"User message: {error.user_message}")
        
        self.logger.error("=" * 80)
        
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
                self.logger.error(f"Error type: {type(error)}")
                self.logger.error(f"Error args: {error.args}")
                if hasattr(error, '__cause__'):
                    self.logger.error(f"Error cause: {error.__cause__}")
                if hasattr(error, '__traceback__'):
                    import traceback
                    self.logger.error(f"Full traceback: {''.join(traceback.format_tb(error.__traceback__))}")
                
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