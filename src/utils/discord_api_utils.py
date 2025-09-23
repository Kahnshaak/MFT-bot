"""
Utilities for Discord API interaction with rate limiting and error handling.
"""

import asyncio
from typing import Any, Callable, Optional, TypeVar, Union
from functools import wraps
import logging

import discord
from discord.ext import commands

from utils.exceptions import GameNightBotException, ErrorCode
from utils.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


class DiscordAPIError(GameNightBotException):
    """Errors related to Discord API interactions."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, 
                 retry_after: Optional[float] = None):
        super().__init__(message, ErrorCode.DISCORD_API_ERROR)
        self.status_code = status_code
        self.retry_after = retry_after


def with_discord_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0
):
    """
    Decorator to add retry logic for Discord API calls with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff calculation
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                
                except discord.HTTPException as e:
                    last_exception = e
                    
                    # Handle rate limiting
                    if e.status == 429:
                        retry_after = getattr(e, 'retry_after', None) or base_delay
                        
                        if attempt < max_retries:
                            logger.warning(
                                f"Rate limited on {func.__name__}, retrying after {retry_after}s "
                                f"(attempt {attempt + 1}/{max_retries})"
                            )
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            raise DiscordAPIError(
                                f"Rate limited after {max_retries} attempts",
                                status_code=429,
                                retry_after=retry_after
                            )
                    
                    # Handle server errors (5xx)
                    elif 500 <= e.status < 600:
                        if attempt < max_retries:
                            delay = min(base_delay * (exponential_base ** attempt), max_delay)
                            logger.warning(
                                f"Server error {e.status} on {func.__name__}, retrying after {delay}s "
                                f"(attempt {attempt + 1}/{max_retries})"
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            raise DiscordAPIError(
                                f"Server error {e.status} after {max_retries} attempts: {e}",
                                status_code=e.status
                            )
                    
                    # Handle client errors (4xx) - don't retry these
                    elif 400 <= e.status < 500:
                        raise DiscordAPIError(
                            f"Client error {e.status}: {e}",
                            status_code=e.status
                        )
                    
                    # Other HTTP exceptions
                    else:
                        if attempt < max_retries:
                            delay = min(base_delay * (exponential_base ** attempt), max_delay)
                            logger.warning(
                                f"HTTP error on {func.__name__}, retrying after {delay}s "
                                f"(attempt {attempt + 1}/{max_retries}): {e}"
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            raise DiscordAPIError(f"HTTP error after {max_retries} attempts: {e}")
                
                except (discord.ConnectionClosed, discord.GatewayNotFound, 
                        discord.DiscordServerError) as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        delay = min(base_delay * (exponential_base ** attempt), max_delay)
                        logger.warning(
                            f"Connection error on {func.__name__}, retrying after {delay}s "
                            f"(attempt {attempt + 1}/{max_retries}): {e}"
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        raise DiscordAPIError(f"Connection error after {max_retries} attempts: {e}")
                
                except Exception as e:
                    # Don't retry unexpected exceptions
                    logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
                    raise
            
            # This should never be reached, but just in case
            if last_exception:
                raise DiscordAPIError(f"Failed after {max_retries} attempts") from last_exception
            
        return wrapper
    return decorator


class RateLimitManager:
    """
    Manager for Discord API rate limits with bucket tracking.
    """
    
    def __init__(self):
        self._buckets = {}
        self._global_rate_limit = None
        self._global_rate_limit_reset = None
    
    async def wait_for_rate_limit(self, bucket: str) -> None:
        """
        Wait for rate limit to reset for a specific bucket.
        
        Args:
            bucket: Rate limit bucket identifier
        """
        # Check global rate limit first
        if self._global_rate_limit and self._global_rate_limit_reset:
            import time
            if time.time() < self._global_rate_limit_reset:
                wait_time = self._global_rate_limit_reset - time.time()
                logger.warning(f"Global rate limit active, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                self._global_rate_limit = None
                self._global_rate_limit_reset = None
        
        # Check bucket-specific rate limit
        if bucket in self._buckets:
            bucket_info = self._buckets[bucket]
            if bucket_info['reset_time'] and time.time() < bucket_info['reset_time']:
                wait_time = bucket_info['reset_time'] - time.time()
                logger.warning(f"Bucket {bucket} rate limited, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                del self._buckets[bucket]
    
    def handle_rate_limit_response(self, response: discord.HTTPException, bucket: str) -> None:
        """
        Handle rate limit response and update bucket information.
        
        Args:
            response: HTTP exception from Discord API
            bucket: Rate limit bucket identifier
        """
        if response.status == 429:
            retry_after = getattr(response, 'retry_after', 1.0)
            
            # Check if it's a global rate limit
            if hasattr(response, 'response') and response.response:
                headers = response.response.headers
                if headers.get('X-RateLimit-Global'):
                    import time
                    self._global_rate_limit = True
                    self._global_rate_limit_reset = time.time() + retry_after
                    logger.warning(f"Global rate limit hit, reset in {retry_after}s")
                else:
                    # Bucket-specific rate limit
                    import time
                    self._buckets[bucket] = {
                        'reset_time': time.time() + retry_after,
                        'retry_after': retry_after
                    }
                    logger.warning(f"Bucket {bucket} rate limited, reset in {retry_after}s")


# Global rate limit manager instance
rate_limit_manager = RateLimitManager()


async def safe_discord_request(
    func: Callable[..., T],
    *args,
    bucket: str = "default",
    **kwargs
) -> Optional[T]:
    """
    Safely execute a Discord API request with rate limit handling.
    
    Args:
        func: The Discord API function to call
        *args: Arguments to pass to the function
        bucket: Rate limit bucket identifier
        **kwargs: Keyword arguments to pass to the function
        
    Returns:
        Result of the function call, or None if it failed
    """
    try:
        # Wait for any active rate limits
        await rate_limit_manager.wait_for_rate_limit(bucket)
        
        # Execute the request
        return await func(*args, **kwargs)
    
    except discord.HTTPException as e:
        # Handle rate limit response
        rate_limit_manager.handle_rate_limit_response(e, bucket)
        
        if e.status == 429:
            # Rate limited, wait and retry once
            retry_after = getattr(e, 'retry_after', 1.0)
            logger.warning(f"Rate limited, waiting {retry_after}s before retry")
            await asyncio.sleep(retry_after)
            
            try:
                return await func(*args, **kwargs)
            except Exception as retry_e:
                logger.error(f"Retry failed for {func.__name__}: {retry_e}")
                return None
        else:
            logger.error(f"Discord API error in {func.__name__}: {e}")
            return None
    
    except Exception as e:
        logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
        return None


async def get_guild_safely(bot: commands.Bot, guild_id: Union[int, str]) -> Optional[discord.Guild]:
    """
    Safely get a guild by ID with error handling.
    
    Args:
        bot: Discord bot instance
        guild_id: Guild ID to fetch
        
    Returns:
        Guild object if found, None otherwise
    """
    try:
        guild_id = int(guild_id)
        guild = bot.get_guild(guild_id)
        
        if guild:
            return guild
        
        # Try fetching if not in cache
        return await safe_discord_request(bot.fetch_guild, guild_id, bucket=f"guild_{guild_id}")
    
    except Exception as e:
        logger.error(f"Error getting guild {guild_id}: {e}")
        return None


async def get_scheduled_event_safely(
    guild: discord.Guild, 
    event_id: Union[int, str]
) -> Optional[discord.ScheduledEvent]:
    """
    Safely get a scheduled event by ID with error handling.
    
    Args:
        guild: Guild to fetch event from
        event_id: Scheduled event ID to fetch
        
    Returns:
        ScheduledEvent object if found, None otherwise
    """
    try:
        event_id = int(event_id)
        
        # Try getting from cache first
        for event in guild.scheduled_events:
            if event.id == event_id:
                return event
        
        # Fetch if not in cache
        return await safe_discord_request(
            guild.fetch_scheduled_event, 
            event_id, 
            bucket=f"scheduled_event_{guild.id}"
        )
    
    except Exception as e:
        logger.error(f"Error getting scheduled event {event_id}: {e}")
        return None


def is_discord_api_available() -> bool:
    """
    Check if Discord API is currently available.
    
    Returns:
        True if API appears to be available, False otherwise
    """
    import time
    # This is a simple check - in a real implementation you might
    # want to make a lightweight API call to test connectivity
    return not (rate_limit_manager._global_rate_limit and 
                rate_limit_manager._global_rate_limit_reset and
                time.time() < rate_limit_manager._global_rate_limit_reset)