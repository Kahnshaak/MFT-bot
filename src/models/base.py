"""
Base model classes and utilities for data validation and serialization.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Type, TypeVar, Union
from bson import ObjectId
from pydantic import BaseModel, Field, ConfigDict, field_validator
from pydantic.alias_generators import to_camel

T = TypeVar('T', bound='BaseDocument')


class PyObjectId(ObjectId):
    """Custom ObjectId type for Pydantic models."""
    
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        from pydantic_core import core_schema
        return core_schema.no_info_plain_validator_function(cls.validate)
    
    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str):
            if ObjectId.is_valid(v):
                return ObjectId(v)
            # For testing, allow None or empty string
            if v in [None, ""]:
                return None
        raise ValueError('Invalid ObjectId')
    
    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema, handler):
        field_schema.update(type='string', format='objectid')
        return field_schema


class BaseDocument(BaseModel, ABC):
    """
    Base class for all database documents.
    
    Provides common functionality for validation, serialization,
    and database operations.
    """
    
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        alias_generator=to_camel,
        json_encoders={
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }
    )
    
    id: Optional[PyObjectId] = Field(default=None, alias='_id')
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    @field_validator('created_at', 'updated_at', mode='before')
    @classmethod
    def validate_datetime(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace('Z', '+00:00'))
        return v
    
    def to_dict(self, exclude_none: bool = True) -> Dict[str, Any]:
        """Convert model to dictionary for database storage."""
        data = self.model_dump(
            by_alias=True,
            exclude_none=exclude_none,
            mode='json'
        )
        
        # Convert ObjectId to string for JSON serialization
        if 'id' in data and data['id']:
            data['_id'] = ObjectId(data.pop('id'))
        
        return data
    
    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
        """Create model instance from dictionary."""
        if '_id' in data:
            data['id'] = str(data.pop('_id'))
        
        return cls(**data)
    
    def update_timestamp(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc)
    
    @abstractmethod
    def validate_data(self) -> None:
        """Validate model-specific business rules."""
        pass


class ValidationMixin:
    """Mixin for common validation utilities."""
    
    @staticmethod
    def validate_guild_id(guild_id: str) -> str:
        """Validate Discord guild ID format."""
        if not guild_id or not guild_id.isdigit():
            raise ValueError("Guild ID must be a valid Discord snowflake")
        return guild_id
    
    @staticmethod
    def validate_user_id(user_id: str) -> str:
        """Validate Discord user ID format."""
        if not user_id or not user_id.isdigit():
            raise ValueError("User ID must be a valid Discord snowflake")
        return user_id
    
    @staticmethod
    def validate_timezone(timezone_str: str) -> str:
        """Validate timezone string."""
        import pytz
        try:
            pytz.timezone(timezone_str)
            return timezone_str
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValueError(f"Invalid timezone: {timezone_str}")
    
    @staticmethod
    def sanitize_text(text: str, max_length: int = 2000) -> str:
        """Sanitize text input for Discord compatibility."""
        if not text:
            return ""
        
        # Remove or escape problematic characters
        forbidden_patterns = ['@everyone', '@here']
        for pattern in forbidden_patterns:
            text = text.replace(pattern, pattern.replace('@', '@\u200b'))
        
        # Limit length
        if len(text) > max_length:
            text = text[:max_length-3] + "..."
        
        return text.strip()


class TimestampMixin:
    """Mixin for timestamp-related utilities."""
    
    @staticmethod
    def utc_now() -> datetime:
        """Get current UTC datetime."""
        return datetime.now(timezone.utc)
    
    @staticmethod
    def to_utc(dt: datetime) -> datetime:
        """Convert datetime to UTC."""
        if dt.tzinfo is None:
            # Assume naive datetime is UTC
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    
    @staticmethod
    def from_timestamp(timestamp: Union[int, float]) -> datetime:
        """Create datetime from Unix timestamp."""
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)