"""
Game models for game interest tracking and notification system.
"""

from typing import List, Optional
from pydantic import Field, field_validator

from .base import BaseDocument


class Game(BaseDocument):
    """
    Simple game model for tracking games.
    """
    
    guild_id: str = Field(..., description="Discord guild ID")
    name: str = Field(..., description="Game name")
    description: Optional[str] = Field(None, description="Game description")
    is_active: bool = Field(default=True, description="Whether game is active for pings")
    
    @field_validator('guild_id')
    @classmethod
    def validate_guild_id(cls, v):
        if not v or not v.isdigit():
            raise ValueError("Guild ID must be a valid Discord snowflake")
        return v
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Game name cannot be empty")
        return v.strip()[:100]
    
    @field_validator('description')
    @classmethod
    def validate_description(cls, v):
        if v:
            return v.strip()[:500]
        return v
    
    def validate_data(self) -> None:
        """Basic validation."""
        pass