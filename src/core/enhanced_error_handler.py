"""
Enhanced error handler that integrates with the recovery system.
"""

import asyncio
import traceback
from typing import Any, Callable, Dict, Optional, Type, Union
from datetime import datetime

import discord
from discord.ext import commands

from core.recovery_manager import RecoveryManager, FailureContext, FailureType
from core.event_bus import EventBus, EventType
from utils.logging_config import get_logger, LoggerMixin
from utils.exceptions import (
    GameNightBotException, 
    ErrorCode, 
    DiscordAPIError, 
    RateLimitedError,
    PermissionDeniedError,
    DatabaseError,
    EventError,
    PollError
)


class EnhancedErrorHandler(LoggerMixin):
    """
    Enhanced error handler that integrates with recovery systems.
    """
    
    def __init__(
        self, 
        recovery_manager: RecoveryManager,
        event_bus: EventBus
    ):
        self.recovery_manager = recovery_manager
        self.event_bus = event_bus
        self._error_counts: Dict[str, int] = {}
        self._last_errors: Dict[str, datetime] = {}
    
    async def handle_command_error(
        self, 
        ctx: commands.Context, 
        error: commands.CommandError,
        operation_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Enhanced command error handling with recovery integration.
        
        Args:
            ctx: Command context
            error: The error that occurred
            operation_data: Additional data about the operation that failed
        """
        # Extract original exception if wrapped
        original_error = getattr(error, 'original', error)
        command_name = ctx.command.name if ctx.command else "unknown"
        
        # Track error frequency
        error_key = f"{command_name}:{type(original_error).__name__}"
        self._error_counts[error_key] = self._error_counts.get(error_key, 0) + 1
        self._last_errors[error_key] = datetime.now()
        
        # Determine failure type and create context
        failure_context = self._create_failure_context(original_error, command_name)
        
        # Handle specific error types with recovery
        if isinstance(original_error, DatabaseError):
            await self._handle_database_error(ctx, original_error, failure_context, operation_data)
        elif isinstance(original_error, EventError):
            await self._handle_event_error(ctx, original_error, failure_context, operation_data)
        elif isinstance(original_error, PollError):
            await self._handle_poll_error(ctx, original_error, failure_context, operation_data)
        elif isinstance(original_error, DiscordAPIError):
            await self._handle_discord_api_error(ctx, original_error, failure_context, operation_data)
        elif isinstance(original_error, GameNightBotException):
            await self._handle_bot_exception(ctx, original_error)
        elif isinstance(error, commands.CommandNotFound):
            # Ignore command not found errors for slash commands
            return
        elif isinstance(error, commands.MissingRequiredArgument):
            await self._send_error_embed(
                ctx,
                "Missing Required Argument",
                f"Missing required argument: `{error.param.name}`"
            )
        elif isinstance(error, commands.BadArgument):
            await self._send_error_embed(
                ctx,
                "Invalid Argument",
                str(error)
            )
        elif isinstance(error, commands.MissingPermissions):
            await self._send_error_embed(
                ctx,
                "Missing Permissions",
                "You don't have permission to use this command."
            )
        elif isinstance(error, commands.BotMissingPermissions):
            await self._send_error_embed(
                ctx,
                "Bot Missing Permissions",
                f"I need the following permissions: {', '.join(error.missing_permissions)}"
            )
        elif isinstance(error, commands.CommandOnCooldown):
            await self._send_error_embed(
                ctx,
                "Command on Cooldown",
                f"This command is on cooldown. Try again in {error.retry_after:.1f} seconds."
            )
        else:
            # Handle unexpected errors with recovery
            await self._handle_unexpected_error(ctx, original_error, failure_context, operation_data)
        
        # Emit error event for monitoring
        await self.event_bus.emit(
            EventType.ERROR_OCCURRED,
            {
                "error_type": type(original_error).__name__,
                "command": command_name,
                "user_id": str(ctx.author.id),
                "guild_id": str(ctx.guild.id) if ctx.guild else None,
                "error_message": str(original_error),
                "error_count": self._error_counts.get(error_key, 0)
            }
        )
    
    async def handle_interaction_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        operation_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Enhanced interaction error handling.
        
        Args:
            interaction: Discord interaction
            error: The error that occurred
            operation_data: Additional data about the operation that failed
        """
        command_name = interaction.command.name if interaction.command else "unknown"
        
        # Track error frequency
        error_key = f"{command_name}:{type(error).__name__}"
        self._error_counts[error_key] = self._error_counts.get(error_key, 0) + 1
        self._last_errors[error_key] = datetime.now()
        
        # Create failure context
        failure_context = self._create_failure_context(error, command_name)
        
        # Handle specific error types
        if isinstance(error, DatabaseError):
            await self._handle_database_error_interaction(interaction, error, failure_context, operation_data)
        elif isinstance(error, EventError):
            await self._handle_event_error_interaction(interaction, error, failure_context, operation_data)
        elif isinstance(error, PollError):
            await self._handle_poll_error_interaction(interaction, error, failure_context, operation_data)
        elif isinstance(error, DiscordAPIError):
            await self._handle_discord_api_error_interaction(interaction, error, failure_context, operation_data)
        elif isinstance(error, GameNightBotException):
            await self._handle_bot_exception_interaction(interaction, error)
        else:
            await self._handle_unexpected_error_interaction(interaction, error, failure_context, operation_data)
    
    def _create_failure_context(self, error: Exception, operation: str) -> FailureContext:
        """Create a failure context from an error."""
        failure_type = FailureType.SYSTEM_CRASH  # Default
        
        if isinstance(error, DatabaseError):
            failure_type = FailureType.DATABASE_CONNECTIVITY
        elif isinstance(error, EventError):
            failure_type = FailureType.EVENT_CREATION
        elif isinstance(error, PollError):
            failure_type = FailureType.POLL_MANAGEMENT
        elif isinstance(error, DiscordAPIError):
            failure_type = FailureType.DISCORD_API
        
        return FailureContext(
            failure_type=failure_type,
            operation=operation,
            error_message=str(error),
            error_details={
                "error_type": type(error).__name__,
                "traceback": traceback.format_exc()
            },
            timestamp=datetime.now().timestamp()
        )
    
    # Database error handlers
    
    async def _handle_database_error(
        self,
        ctx: commands.Context,
        error: DatabaseError,
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]]
    ) -> None:
        """Handle database errors with recovery."""
        self.logger.error(
            "Database error in command",
            command=ctx.command.name if ctx.command else "unknown",
            error=str(error),
            user_id=ctx.author.id,
            guild_id=ctx.guild.id if ctx.guild else None
        )
        
        # Attempt recovery
        recovery_success = await self.recovery_manager.handle_failure(
            failure_context, operation_data
        )
        
        if recovery_success:
            await self._send_error_embed(
                ctx,
                "Temporary Issue Resolved",
                "There was a temporary database issue, but it has been resolved. Please try your command again."
            )
        else:
            await self._send_error_embed(
                ctx,
                "Database Error",
                "There's currently a database issue. Please try again in a few moments."
            )
    
    async def _handle_event_error(
        self,
        ctx: commands.Context,
        error: EventError,
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]]
    ) -> None:
        """Handle event-related errors with recovery."""
        self.logger.error(
            "Event error in command",
            command=ctx.command.name if ctx.command else "unknown",
            error=str(error),
            event_id=getattr(error, 'event_id', None)
        )
        
        # Attempt recovery
        recovery_success = await self.recovery_manager.handle_failure(
            failure_context, operation_data
        )
        
        if recovery_success:
            await self._send_error_embed(
                ctx,
                "Event Issue Resolved",
                "There was an issue with the event, but it has been resolved. You can continue."
            )
        else:
            await self._send_error_embed(
                ctx,
                "Event Error",
                error.user_message
            )
    
    async def _handle_poll_error(
        self,
        ctx: commands.Context,
        error: PollError,
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]]
    ) -> None:
        """Handle poll-related errors with recovery."""
        self.logger.error(
            "Poll error in command",
            command=ctx.command.name if ctx.command else "unknown",
            error=str(error)
        )
        
        # Attempt recovery
        recovery_success = await self.recovery_manager.handle_failure(
            failure_context, operation_data
        )
        
        if recovery_success:
            await self._send_error_embed(
                ctx,
                "Poll Issue Resolved",
                "There was an issue with the poll, but it has been resolved."
            )
        else:
            await self._send_error_embed(
                ctx,
                "Poll Error",
                error.user_message
            )
    
    async def _handle_discord_api_error(
        self,
        ctx: commands.Context,
        error: DiscordAPIError,
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]]
    ) -> None:
        """Handle Discord API errors with recovery."""
        self.logger.error(
            "Discord API error in command",
            command=ctx.command.name if ctx.command else "unknown",
            error=str(error),
            status_code=getattr(error, 'status_code', None)
        )
        
        # Attempt recovery
        recovery_success = await self.recovery_manager.handle_failure(
            failure_context, operation_data
        )
        
        if isinstance(error, RateLimitedError):
            retry_after = error.details.get('retry_after', 60)
            await self._send_error_embed(
                ctx,
                "Rate Limited",
                f"Discord is rate limiting requests. Please try again in {retry_after} seconds."
            )
        elif recovery_success:
            await self._send_error_embed(
                ctx,
                "Discord Issue Resolved",
                "There was a temporary Discord API issue, but it has been resolved."
            )
        else:
            await self._send_error_embed(
                ctx,
                "Discord API Error",
                "There's currently an issue with Discord's API. Please try again later."
            )
    
    async def _handle_bot_exception(
        self,
        ctx: commands.Context,
        error: GameNightBotException
    ) -> None:
        """Handle known bot exceptions."""
        self.logger.error(
            "Bot exception in command",
            command=ctx.command.name if ctx.command else "unknown",
            error_code=error.error_code.value,
            error_message=str(error),
            details=error.details
        )
        
        await self._send_error_embed(
            ctx,
            "Error",
            error.user_message
        )
    
    async def _handle_unexpected_error(
        self,
        ctx: commands.Context,
        error: Exception,
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]]
    ) -> None:
        """Handle unexpected errors with recovery."""
        self.logger.error(
            "Unexpected error in command",
            command=ctx.command.name if ctx.command else "unknown",
            error_type=type(error).__name__,
            error_message=str(error),
            traceback=traceback.format_exc()
        )
        
        # Attempt recovery
        recovery_success = await self.recovery_manager.handle_failure(
            failure_context, operation_data
        )
        
        if recovery_success:
            await self._send_error_embed(
                ctx,
                "Issue Resolved",
                "There was an unexpected issue, but it has been resolved. Please try again."
            )
        else:
            await self._send_error_embed(
                ctx,
                "Unexpected Error",
                "An unexpected error occurred. Please try again later."
            )
    
    # Interaction error handlers (similar to command handlers but for interactions)
    
    async def _handle_database_error_interaction(
        self,
        interaction: discord.Interaction,
        error: DatabaseError,
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]]
    ) -> None:
        """Handle database errors in interactions."""
        recovery_success = await self.recovery_manager.handle_failure(
            failure_context, operation_data
        )
        
        message = ("There was a temporary database issue, but it has been resolved. Please try again." 
                  if recovery_success else 
                  "There's currently a database issue. Please try again in a few moments.")
        
        await self._send_interaction_error(interaction, "Database Error", message)
    
    async def _handle_event_error_interaction(
        self,
        interaction: discord.Interaction,
        error: EventError,
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]]
    ) -> None:
        """Handle event errors in interactions."""
        recovery_success = await self.recovery_manager.handle_failure(
            failure_context, operation_data
        )
        
        message = ("There was an issue with the event, but it has been resolved." 
                  if recovery_success else error.user_message)
        
        await self._send_interaction_error(interaction, "Event Error", message)
    
    async def _handle_poll_error_interaction(
        self,
        interaction: discord.Interaction,
        error: PollError,
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]]
    ) -> None:
        """Handle poll errors in interactions."""
        recovery_success = await self.recovery_manager.handle_failure(
            failure_context, operation_data
        )
        
        message = ("There was an issue with the poll, but it has been resolved." 
                  if recovery_success else error.user_message)
        
        await self._send_interaction_error(interaction, "Poll Error", message)
    
    async def _handle_discord_api_error_interaction(
        self,
        interaction: discord.Interaction,
        error: DiscordAPIError,
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]]
    ) -> None:
        """Handle Discord API errors in interactions."""
        recovery_success = await self.recovery_manager.handle_failure(
            failure_context, operation_data
        )
        
        if isinstance(error, RateLimitedError):
            retry_after = error.details.get('retry_after', 60)
            message = f"Discord is rate limiting requests. Please try again in {retry_after} seconds."
        elif recovery_success:
            message = "There was a temporary Discord API issue, but it has been resolved."
        else:
            message = "There's currently an issue with Discord's API. Please try again later."
        
        await self._send_interaction_error(interaction, "Discord API Error", message)
    
    async def _handle_bot_exception_interaction(
        self,
        interaction: discord.Interaction,
        error: GameNightBotException
    ) -> None:
        """Handle bot exceptions in interactions."""
        await self._send_interaction_error(interaction, "Error", error.user_message)
    
    async def _handle_unexpected_error_interaction(
        self,
        interaction: discord.Interaction,
        error: Exception,
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]]
    ) -> None:
        """Handle unexpected errors in interactions."""
        recovery_success = await self.recovery_manager.handle_failure(
            failure_context, operation_data
        )
        
        message = ("There was an unexpected issue, but it has been resolved. Please try again." 
                  if recovery_success else 
                  "An unexpected error occurred. Please try again later.")
        
        await self._send_interaction_error(interaction, "Unexpected Error", message)
    
    # Utility methods
    
    async def _send_error_embed(
        self, 
        ctx: commands.Context, 
        title: str, 
        description: str
    ) -> None:
        """Send an error embed to the user."""
        embed = discord.Embed(
            title=f"❌ {title}",
            description=description,
            color=discord.Color.red()
        )
        
        try:
            if ctx.interaction and not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
            elif ctx.interaction:
                await ctx.interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await ctx.send(embed=embed)
        except Exception as e:
            self.logger.error(
                "Failed to send error message",
                error=str(e)
            )
    
    async def _send_interaction_error(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str
    ) -> None:
        """Send an error message for an interaction."""
        embed = discord.Embed(
            title=f"❌ {title}",
            description=description,
            color=discord.Color.red()
        )
        
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            self.logger.error(
                "Failed to send interaction error message",
                error=str(e)
            )
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics for monitoring."""
        return {
            "total_errors": sum(self._error_counts.values()),
            "error_types": dict(self._error_counts),
            "recent_errors": {
                error_key: last_time.isoformat()
                for error_key, last_time in self._last_errors.items()
            }
        }