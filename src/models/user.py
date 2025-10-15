"""
User model for Discord user profiles and preferences.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from pydantic import Field, field_validator

from .base import BaseDocument


class NotificationTiming(str, Enum):
    """Notification timing preferences."""
    IMMEDIATE = "IMMEDIATE"
    HOUR_BEFORE = "HOUR_BEFORE"
    DAY_BEFORE = "DAY_BEFORE"
    BOTH_REMINDERS = "BOTH_REMINDERS"


class GameInterest(BaseDocument):
    """User interest in a specific game."""
    
    game_name: str = Field(..., description="Game name")
    notification_enabled: bool = Field(default=True, description="Receive pings for this game")
    
    @field_validator('game_name')
    @classmethod
    def validate_game_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Game name cannot be empty")
        return v.strip()[:100]
    
    def validate_data(self) -> None:
        """Basic validation."""
        pass


class User(BaseDocument):
    """
    User profile model for Discord users.
    """
    
    user_id: str = Field(..., description="Discord user ID")
    guild_id: str = Field(..., description="Discord guild ID")
    
    # Profile information
    display_name: Optional[str] = Field(None, description="Display name")
    timezone: str = Field(default="UTC", description="User's timezone")
    
    # Preferences
    event_reminders: bool = Field(default=True, description="Receive event reminders")
    game_pings: bool = Field(default=True, description="Receive game ping notifications")
    
    # Game interests
    game_interests: List[GameInterest] = Field(default_factory=list, description="Games the user is interested in")
    
    @field_validator('user_id', 'guild_id')
    @classmethod
    def validate_ids(cls, v):
        if not v or not v.isdigit():
            raise ValueError("ID must be a valid Discord snowflake")
        return v
    
    @field_validator('display_name')
    @classmethod
    def validate_display_name(cls, v):
        if v:
            return v.strip()[:100]
        return v
    
    def validate_data(self) -> None:
        """Basic validation."""
        pass
    
    def add_game_interest(self, game_name: str, notification_enabled: bool = True) -> bool:
        """Add interest in a game. Returns True if added, False if already exists."""
        game_name = game_name.strip()[:100]
        
        # Check if already interested
        for interest in self.game_interests:
            if interest.game_name.lower() == game_name.lower():
                return False
        
        self.game_interests.append(GameInterest(
            game_name=game_name,
            notification_enabled=notification_enabled
        ))
        return True
    
    def remove_game_interest(self, game_name: str) -> bool:
        """Remove interest in a game. Returns True if removed, False if not found."""
        for i, interest in enumerate(self.game_interests):
            if interest.game_name.lower() == game_name.lower():
                del self.game_interests[i]
                return True
        return False
    
    def is_interested_in_game(self, game_name: str) -> bool:
        """Check if user is interested in a game and wants notifications."""
        for interest in self.game_interests:
            if interest.game_name.lower() == game_name.lower():
                return interest.notification_enabled
        return False