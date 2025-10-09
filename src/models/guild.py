"""
Guild configuration model for server-specific settings.
"""

from typing import List, Optional
from pydantic import Field, field_validator

from .base import BaseDocument


class GuildConfig(BaseDocument):
    """
    Simple guild configuration model for server-specific settings.
    """
    
    guild_id: str = Field(..., description="Discord guild ID")
    guild_name: Optional[str] = Field(None, description="Guild name")
    
    # Basic settings
    default_timezone: str = Field(default="UTC", description="Default timezone for events")
    events_channel_id: Optional[str] = Field(None, description="Channel for event notifications")
    
    # Administrative settings
    admin_user_ids: List[str] = Field(default_factory=list, description="User IDs with admin privileges")
    
    @field_validator('guild_id')
    @classmethod
    def validate_guild_id(cls, v):
        if not v or not v.isdigit():
            raise ValueError("Guild ID must be a valid Discord snowflake")
        return v
    
    @field_validator('guild_name')
    @classmethod
    def validate_guild_name(cls, v):
        if v:
            return v.strip()[:100]
        return v
    
    @field_validator('events_channel_id')
    @classmethod
    def validate_channel_id(cls, v):
        if v and not v.isdigit():
            raise ValueError("Channel ID must be a valid Discord snowflake")
        return v
    
    @field_validator('admin_user_ids')
    @classmethod
    def validate_admin_user_ids(cls, v):
        for user_id in v:
            if not user_id or not user_id.isdigit():
                raise ValueError("User ID must be a valid Discord snowflake")
        return v
    
    def validate_data(self) -> None:
        """Basic validation."""
        pass
    
    def is_admin(self, user_id: str) -> bool:
        """Check if user is admin."""
        return user_id in self.admin_user_ids
    
    def add_admin_user(self, user_id: str) -> bool:
        """Add admin user. Returns True if added."""
        if user_id not in self.admin_user_ids:
            self.admin_user_ids.append(user_id)
            return True
        return False
    
    def remove_admin_user(self, user_id: str) -> bool:
        """Remove admin user. Returns True if removed."""
        if user_id in self.admin_user_ids:
            self.admin_user_ids.remove(user_id)
            return True
        return False