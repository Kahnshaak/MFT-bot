"""
Standardized error handling utilities and decorators.
"""

import asyncio
import functools
import traceback
from typing import Any, Callable, Optional, Type, Union, Dict

import discord
from discord.ext import commands

from utils.exceptions import (
    GameNightBotException, 
    ErrorCode, 
    DiscordAPIError, 
    RateLimitedError,
    PermissionDeniedError
)
from utils.logging_config import get_logger

logger = get_logger(__name__)


def handle_exceptions(
    default_return: Any = None,
    reraise: bool = False,
    log_errors: bool = True
):
    """
    Decorator to handle exceptions in async functions.
    
    Args:
        default_return: Value to return if an exception occurs
        reraise: Whether to reraise the exception after handling
        log_errors: Whether to log errors
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except GameNightBotException as e:
                if log_errors:
                    logger.error(
                        "Bot exception occurred",
                        function=func.__name__,
                        error_code=e.error_code.value,
                        error_message=str(e),
                        details=e.details
                    )
                if reraise:
                    raise
                return default_return
            except Exception as e:
                if log_errors:
                    logger.error(
                        "Unexpected exception occurred",
                        function=func.__name__,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        traceback=traceback.format_exc()
                    )
                if reraise:
                    raise
                return default_return
        return wrapper
    return decorator


def discord_error_handler(func: Callable) -> Callable:
    """
    Decorator specifically for handling Discord API errors.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except discord.HTTPException as e:
            logger.error(
                "Discord HTTP exception",
                function=func.__name__,
                status=e.status,
                code=e.code,
                text=e.text
            )
            
            if e.status == 429:  # Rate limited
                raise RateLimitedError(
                    f"Discord API rate limited: {e.text}",
                    retry_after=getattr(e, 'retry_after', None)
                )
            elif e.status == 403:  # Forbidden
                raise PermissionDeniedError(
                    "Bot lacks required Discord permissions"
                )
            else:
                raise DiscordAPIError(
                    f"Discord API error: {e.text}",
                    status_code=e.status
                )
        except discord.Forbidden as e:
            logger.error(
                "Discord forbidden error",
                function=func.__name__,
                code=e.code,
                text=e.text
            )
            raise PermissionDeniedError(
                "Bot lacks required Discord permissions"
            )
        except discord.NotFound as e:
            logger.error(
                "Discord not found error",
                function=func.__name__,
                code=e.code,
                text=e.text
            )
            raise DiscordAPIError(
                f"Discord resource not found: {e.text}",
                status_code=404
            )
    return wrapper


class ErrorHandler:
    """Centralized error handling for the bot."""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = get_logger(__name__)
    
    async def handle_command_error(
        self, 
        ctx: commands.Context, 
        error: commands.CommandError
    ) -> None:
        """
        Handle command errors and send appropriate responses.
        
        Args:
            ctx: Command context
            error: The error that occurred
        """
        # Extract original exception if wrapped
        original_error = getattr(error, 'original', error)
        
        if isinstance(original_error, GameNightBotException):
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
            # Log unexpected errors
            self.logger.error(
                "Unexpected command error",
                command=ctx.command.name if ctx.command else "unknown",
                error_type=type(error).__name__,
                error_message=str(error),
                traceback=traceback.format_exc()
            )
            
            await self._send_error_embed(
                ctx,
                "Unexpected Error",
                "An unexpected error occurred. Please try again later."
            )
    
    async def _handle_bot_exception(
        self, 
        ctx: commands.Context, 
        error: GameNightBotException
    ) -> None:
        """Handle GameNightBotException instances."""
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


# Retry decorator for operations that might fail temporarily
def retry_on_failure(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Decorator to retry operations on failure.
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff_factor: Factor to multiply delay by after each attempt
        exceptions: Tuple of exception types to retry on
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts - 1:
                        # Last attempt, reraise the exception
                        raise
                    
                    logger.warning(
                        "Operation failed, retrying",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                        error=str(e),
                        retry_delay=current_delay
                    )
                    
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff_factor
            
        return wrapper
    return decorator