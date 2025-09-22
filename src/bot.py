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
from core.validation_manager import ValidationManager
from core.audit_logger import AuditLogger
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
        self.validation: Optional[ValidationManager] = None
        self.audit_logger: Optional[AuditLogger] = None
        
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
            self.validation = ValidationManager()
            self.audit_logger = AuditLogger(self.database)
            self.health_monitor = HealthMonitor(self.database, self)
            
            # Set up event bus middleware for metrics and audit logging
            self.event_bus.add_middleware(self._metrics_middleware)
            self.event_bus.add_middleware(self._audit_middleware)
            
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
        
        # Log security event for critical errors
        if self.audit_logger and event in ['command_error', 'application_command_error']:
            await self.audit_logger.log_security_event(
                event_type=self.audit_logger.AuditEventType.SECURITY_VIOLATION,
                action=f"Unhandled error in {event}",
                severity="medium",
                details={"event": event, "args": str(args)[:500]}
            )
    
    async def _metrics_middleware(self, event):
        """Middleware to record metrics for events."""
        if self.metrics:
            # Record event metrics (non-async call)
            self.metrics.record_counter(
                "event_bus_events_total",
                1.0,
                {"event_type": event.event_type.value, "source": event.source or "unknown"}
            )
        return event
    
    async def _audit_middleware(self, event):
        """Middleware to log audit events."""
        if self.audit_logger:
            # Log certain events to audit log
            audit_worthy_events = [
                "EVENT_CREATED", "EVENT_UPDATED", "EVENT_CANCELLED",
                "USER_PREFERENCES_UPDATED", "ERROR_OCCURRED"
            ]
            
            if event.event_type.value.upper() in audit_worthy_events:
                from core.audit_logger import AuditEventType
                event_type_mapping = {
                    "EVENT_CREATED": AuditEventType.EVENT_CREATED,
                    "EVENT_UPDATED": AuditEventType.EVENT_UPDATED,
                    "EVENT_CANCELLED": AuditEventType.EVENT_CANCELLED,
                    "USER_PREFERENCES_UPDATED": AuditEventType.USER_PROFILE_UPDATED,
                    "ERROR_OCCURRED": AuditEventType.SECURITY_VIOLATION
                }
                
                audit_event_type = event_type_mapping.get(
                    event.event_type.value.upper(),
                    AuditEventType.USER_PROFILE_UPDATED
                )
                
                await self.audit_logger.log_event(
                    event_type=audit_event_type,
                    action=f"Event bus: {event.event_type.value}",
                    user_id=event.user_id,
                    guild_id=event.guild_id,
                    details={"source": event.source, "data": event.data}
                )
        return event
    
    async def on_command_error(self, ctx, error):
        """Handle command errors with proper logging and metrics."""
        command_name = ctx.command.name if ctx.command else "unknown"
        
        # Record metrics
        if self.metrics:
            await self.metrics.record_command(
                command_name=command_name,
                duration=0,  # Error occurred, no meaningful duration
                success=False,
                guild_id=str(ctx.guild.id) if ctx.guild else None,
                user_id=str(ctx.author.id)
            )
        
        # Log to audit system
        if self.audit_logger:
            from core.audit_logger import AuditEventType
            await self.audit_logger.log_security_event(
                event_type=AuditEventType.SECURITY_VIOLATION,
                action=f"Command error: {command_name}",
                user_id=str(ctx.author.id),
                guild_id=str(ctx.guild.id) if ctx.guild else None,
                severity="low",
                details={
                    "command": command_name,
                    "error_type": type(error).__name__,
                    "error_message": str(error)
                }
            )
        
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
            self.logger.error(
                "Unexpected command error",
                command=command_name,
                error=str(error),
                user_id=ctx.author.id,
                guild_id=ctx.guild.id if ctx.guild else None,
                exc_info=True
            )
            await ctx.send("❌ An unexpected error occurred. Please try again later.", ephemeral=True)
    
    async def on_application_command_error(self, interaction, error):
        """Handle application command (slash command) errors."""
        command_name = interaction.command.name if interaction.command else "unknown"
        
        # Record metrics
        if self.metrics:
            await self.metrics.record_command(
                command_name=command_name,
                duration=0,
                success=False,
                guild_id=str(interaction.guild.id) if interaction.guild else None,
                user_id=str(interaction.user.id)
            )
        
        # Similar error handling as regular commands
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
                self.logger.error(
                    "Unexpected application command error",
                    command=command_name,
                    error=str(error),
                    user_id=interaction.user.id,
                    guild_id=interaction.guild.id if interaction.guild else None,
                    exc_info=True
                )
                
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