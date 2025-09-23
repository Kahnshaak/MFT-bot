"""
Utilities package for the Discord Game Night Bot.

This package contains utility functions, exception classes,
logging configuration, and error handling.
"""

from .exceptions import (
    GameNightBotException, ValidationError, PermissionDeniedError,
    RateLimitedError, DatabaseError, DatabaseConnectionError,
    DocumentNotFoundError, DiscordAPIError, EventError,
    EventNotFoundError, EventInvalidStateError, PollError,
    PollNotFoundError, PollExpiredError, ConfigurationError,
    ErrorCode
)
from .logging_config import (
    setup_logging, get_logger, LoggerMixin
)
from .error_handler import ErrorHandler

__all__ = [
    # Exceptions
    'GameNightBotException', 'ValidationError', 'PermissionDeniedError',
    'RateLimitedError', 'DatabaseError', 'DatabaseConnectionError',
    'DocumentNotFoundError', 'DiscordAPIError', 'EventError',
    'EventNotFoundError', 'EventInvalidStateError', 'PollError',
    'PollNotFoundError', 'PollExpiredError', 'ConfigurationError',
    'ErrorCode',
    
    # Logging
    'setup_logging', 'get_logger', 'LoggerMixin',
    
    # Error handling
    'ErrorHandler'
]