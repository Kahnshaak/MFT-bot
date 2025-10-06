"""
Custom exception classes and standardized error responses for the Discord Game Night Bot.
"""

from typing import Optional, Dict, Any, List
from enum import Enum


class ErrorCode(Enum):
    """Standardized error codes for the application."""
    
    # General errors
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    GRACEFUL_DEGRADATION = "GRACEFUL_DEGRADATION"
    
    # Database errors
    DATABASE_CONNECTION_ERROR = "DATABASE_CONNECTION_ERROR"
    DATABASE_OPERATION_ERROR = "DATABASE_OPERATION_ERROR"
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    DUPLICATE_ENTRY = "DUPLICATE_ENTRY"
    DATA_CORRUPTION = "DATA_CORRUPTION"
    ORPHANED_DATA = "ORPHANED_DATA"
    
    # Discord API errors
    DISCORD_API_ERROR = "DISCORD_API_ERROR"
    DISCORD_RATE_LIMITED = "DISCORD_RATE_LIMITED"
    DISCORD_FORBIDDEN = "DISCORD_FORBIDDEN"
    DISCORD_NOT_FOUND = "DISCORD_NOT_FOUND"
    DISCORD_CONNECTION_FAILED = "DISCORD_CONNECTION_FAILED"
    DISCORD_SERVICE_UNAVAILABLE = "DISCORD_SERVICE_UNAVAILABLE"
    GUILD_NOT_FOUND = "GUILD_NOT_FOUND"
    
    # Event management errors
    EVENT_NOT_FOUND = "EVENT_NOT_FOUND"
    EVENT_INVALID_STATE = "EVENT_INVALID_STATE"
    EVENT_CREATION_FAILED = "EVENT_CREATION_FAILED"
    EVENT_PARTIAL_FAILURE = "EVENT_PARTIAL_FAILURE"
    POLL_ALREADY_EXISTS = "POLL_ALREADY_EXISTS"
    POLL_NOT_FOUND = "POLL_NOT_FOUND"
    POLL_EXPIRED = "POLL_EXPIRED"
    POLL_USER_DEPARTED = "POLL_USER_DEPARTED"
    POLL_DUPLICATE_VOTE = "POLL_DUPLICATE_VOTE"
    POLL_EDGE_CASE = "POLL_EDGE_CASE"
    
    # User management errors
    USER_NOT_FOUND = "USER_NOT_FOUND"
    USER_LEFT_SERVER = "USER_LEFT_SERVER"
    INVALID_TIMEZONE = "INVALID_TIMEZONE"
    DEPRECATED_TIMEZONE = "DEPRECATED_TIMEZONE"
    TIMEZONE_CONVERSION_ERROR = "TIMEZONE_CONVERSION_ERROR"
    INVALID_GAME_NAME = "INVALID_GAME_NAME"
    
    # Configuration errors
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    MISSING_PERMISSIONS = "MISSING_PERMISSIONS"
    
    # Web dashboard errors
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    CSRF_TOKEN_INVALID = "CSRF_TOKEN_INVALID"


class GameNightBotException(Exception):
    """Base exception class for all bot-related errors."""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        details: Optional[Dict[str, Any]] = None,
        user_message: Optional[str] = None
    ):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}
        self.user_message = user_message or message
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/API responses."""
        return {
            "error_code": self.error_code.value,
            "message": str(self),
            "user_message": self.user_message,
            "details": self.details
        }


class ValidationError(GameNightBotException):
    """Raised when input validation fails."""
    
    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.VALIDATION_ERROR,
            details={"field": field} if field else {},
            **kwargs
        )


class PermissionDeniedError(GameNightBotException):
    """Raised when user lacks required permissions."""
    
    def __init__(self, message: str = "Permission denied", **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.PERMISSION_DENIED,
            user_message="You don't have permission to perform this action.",
            **kwargs
        )


class RateLimitedError(GameNightBotException):
    """Raised when rate limits are exceeded."""
    
    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None, **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.RATE_LIMITED,
            details={"retry_after": retry_after} if retry_after else {},
            user_message="You're doing that too fast. Please try again later.",
            **kwargs
        )


class DatabaseError(GameNightBotException):
    """Base class for database-related errors."""
    
    def __init__(self, message: str, operation: Optional[str] = None, **kwargs):
        # Remove error_code from kwargs if present to avoid conflict
        kwargs.pop('error_code', None)
        super().__init__(
            message,
            error_code=ErrorCode.DATABASE_OPERATION_ERROR,
            details={"operation": operation} if operation else {},
            user_message="A database error occurred. Please try again later.",
            **kwargs
        )


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""
    
    def __init__(self, message: str = "Database connection failed", **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.DATABASE_CONNECTION_ERROR,
            **kwargs
        )


class DocumentNotFoundError(DatabaseError):
    """Raised when a requested document is not found."""
    
    def __init__(self, message: str, document_type: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.DOCUMENT_NOT_FOUND,
            details={"document_type": document_type} if document_type else {},
            user_message="The requested item was not found.",
            **kwargs
        )


class DiscordAPIError(GameNightBotException):
    """Base class for Discord API errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.DISCORD_API_ERROR,
            details={"status_code": status_code} if status_code else {},
            user_message="Discord API error occurred. Please try again later.",
            **kwargs
        )


class EventError(GameNightBotException):
    """Base class for event-related errors."""
    
    def __init__(self, message: str, event_id: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            details={"event_id": event_id} if event_id else {},
            **kwargs
        )


class EventNotFoundError(EventError):
    """Raised when an event is not found."""
    
    def __init__(self, message: str = "Event not found", **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.EVENT_NOT_FOUND,
            user_message="The requested event was not found.",
            **kwargs
        )


class EventInvalidStateError(EventError):
    """Raised when an operation is invalid for the current event state."""
    
    def __init__(self, message: str, current_state: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.EVENT_INVALID_STATE,
            details={"current_state": current_state} if current_state else {},
            user_message="This action cannot be performed on the event in its current state.",
            **kwargs
        )


class PollError(GameNightBotException):
    """Base class for poll-related errors."""
    
    def __init__(self, message: str, poll_type: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            details={"poll_type": poll_type} if poll_type else {},
            **kwargs
        )


class PollNotFoundError(PollError):
    """Raised when a poll is not found."""
    
    def __init__(self, message: str = "Poll not found", **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.POLL_NOT_FOUND,
            user_message="The requested poll was not found.",
            **kwargs
        )


class PollExpiredError(PollError):
    """Raised when attempting to interact with an expired poll."""
    
    def __init__(self, message: str = "Poll has expired", **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.POLL_EXPIRED,
            user_message="This poll has expired and can no longer accept votes.",
            **kwargs
        )


class ConfigurationError(GameNightBotException):
    """Raised when configuration is invalid or missing."""
    
    def __init__(self, message: str, config_key: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.INVALID_CONFIGURATION,
            details={"config_key": config_key} if config_key else {},
            user_message="Configuration error. Please contact an administrator.",
            **kwargs
        )


class ServiceUnavailableError(GameNightBotException):
    """Raised when external services are unavailable."""
    
    def __init__(self, message: str, service: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            details={"service": service} if service else {},
            user_message="A required service is temporarily unavailable. Please try again later.",
            **kwargs
        )


class GracefulDegradationError(GameNightBotException):
    """Raised when system is operating in degraded mode."""
    
    def __init__(self, message: str, degraded_features: Optional[List[str]] = None, **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.GRACEFUL_DEGRADATION,
            details={"degraded_features": degraded_features or []},
            user_message="Some features are temporarily limited. Core functionality remains available.",
            **kwargs
        )


class TimezoneError(GameNightBotException):
    """Raised when timezone operations fail."""
    
    def __init__(self, message: str, timezone: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.TIMEZONE_CONVERSION_ERROR,
            details={"timezone": timezone} if timezone else {},
            user_message="There was an issue with timezone conversion. Please check your timezone settings.",
            **kwargs
        )


class DeprecatedTimezoneError(TimezoneError):
    """Raised when using deprecated timezone identifiers."""
    
    def __init__(self, message: str, deprecated_tz: str, suggested_tz: Optional[str] = None, **kwargs):
        # Remove error_code from kwargs to avoid conflict
        kwargs.pop('error_code', None)
        super().__init__(
            message,
            timezone=deprecated_tz,
            **kwargs
        )
        # Override the error code and details after initialization
        self.error_code = ErrorCode.DEPRECATED_TIMEZONE
        self.details.update({
            "deprecated_timezone": deprecated_tz, 
            "suggested_timezone": suggested_tz
        })
        self.user_message = f"The timezone '{deprecated_tz}' is deprecated. Please use '{suggested_tz}' instead." if suggested_tz else f"The timezone '{deprecated_tz}' is deprecated."


class PollEdgeCaseError(PollError):
    """Raised when poll encounters edge cases."""
    
    def __init__(self, message: str, edge_case_type: str, **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.POLL_EDGE_CASE,
            details={"edge_case_type": edge_case_type},
            user_message="An unusual situation occurred with the poll. It has been handled automatically.",
            **kwargs
        )


class UserDepartedError(GameNightBotException):
    """Raised when user leaves server during operations."""
    
    def __init__(self, message: str, user_id: str, **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.USER_LEFT_SERVER,
            details={"user_id": user_id},
            user_message="A user left the server during this operation. The system has been updated accordingly.",
            **kwargs
        )