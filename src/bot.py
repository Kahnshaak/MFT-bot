"""
Main bot entry point for the Discord Game Night Scheduling Bot.
"""

import asyncio
import logging
import os
from typing import Optional

import discord
from discord.ext import commands

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.settings import Settings
from core.event_bus import EventBus
from core.security_manager import SecurityManager
from core.metrics_collector import MetricsCollector
from core.health_monitor import HealthMonitor
from database.manager import DatabaseManager
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
        
        # Initialize core components
        self.settings = Settings()
        self.database: Optional[DatabaseManager] = None
        self.event_bus: Optional[EventBus] = None
        self.security: Optional[SecurityManager] = None
        self.metrics: Optional[MetricsCollector] = None
        self.health_monitor: Optional[HealthMonitor] = None
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
    
    async def setup_hook(self):
        """Initialize bot components and load cogs."""
        try:
            self.logger.info("Starting bot setup...")
            
            # Initialize database connection
            self.database = DatabaseManager(self.settings.database_url)
            await self.database.connect()
            
            # Initialize core systems
            self.event_bus = EventBus()
            self.security = SecurityManager(self.settings)
            self.metrics = MetricsCollector()
            self.health_monitor = HealthMonitor(self.database, self)
            
            # Load cogs (will be implemented in later tasks)
            # await self.load_extension('cogs.events')
            # await self.load_extension('cogs.users')
            # etc.
            
            self.logger.info("Bot setup completed successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to setup bot: {e}")
            raise
    
    async def on_ready(self):
        """Called when the bot is ready."""
        self.logger.info(f'{self.user} has connected to Discord!')
        self.logger.info(f'Bot is in {len(self.guilds)} guilds')
        
        # Start health monitoring
        if self.health_monitor:
            await self.health_monitor.start_monitoring()
    
    async def on_error(self, event, *args, **kwargs):
        """Global error handler."""
        self.logger.error(f"Error in event {event}", exc_info=True)
        if self.metrics:
            await self.metrics.record_error(event)


async def main():
    """Main entry point."""
    # Set up logging
    setup_logging()
    
    bot = GameNightBot()
    
    try:
        await bot.start(bot.settings.discord_token)
    except KeyboardInterrupt:
        logging.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logging.error(f"Bot crashed: {e}")
        raise
    finally:
        if bot.database:
            await bot.database.disconnect()


if __name__ == "__main__":
    asyncio.run(main())