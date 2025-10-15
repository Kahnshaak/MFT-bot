"""
Notification model for managing scheduled reminders and alerts.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import Field, field_validator

from .base import BaseDocument


class NotificationType(str, Enum):
    """Types of notifications."""
    EVENT_REMINDER = "EVENT_REMINDER"
    GAME_PING = "GAME_PING"
    POLL_CLOSING = "POLL_CLOSING"
    EVENT_CANCELLED = "EVENT_CANCELLED"


class NotificationStatus(str, Enum):
    """Notification delivery status."""
    SCHEDULED = "SCHEDULED"
    SENT = "SENT"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class NotificationChannel(str, Enum):
    """Notification delivery channels."""
    DM = "DM"
    SERVER = "SERVER"
    BOTH = "BOTH"


class Notification(BaseDocument):
    """
    Simple notification model for scheduled reminders.
    """
    
    guild_id: str = Field(..., description="Discord guild ID")
    notification_type: NotificationType = Field(..., description="Type of notification")
    
    # Scheduling
    scheduled_for: datetime = Field(..., description="When to send the notification")
    
    # Recipients
    recipient_user_ids: List[str] = Field(default_factory=list, description="Target user IDs")
    
    # Content
    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Notification message")
    
    # Context
    event_id: Optional[str] = Field(None, description="Related event ID")
    
    # Status
    status: NotificationStatus = Field(default=NotificationStatus.SCHEDULED)
    
    @field_validator('guild_id')
    @classmethod
    def validate_guild_id(cls, v):
        if not v or not v.isdigit():
            raise ValueError("Guild ID must be a valid Discord snowflake")
        return v
    
    @field_validator('recipient_user_ids')
    @classmethod
    def validate_user_ids(cls, v):
        for uid in v:
            if not uid or not uid.isdigit():
                raise ValueError("User ID must be a valid Discord snowflake")
        return v
    
    @field_validator('title', 'message')
    @classmethod
    def validate_content(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Content cannot be empty")
        return v.strip()[:2000]
    
    def validate_data(self) -> None:
        """Basic validation."""
        pass
    
    def is_due(self) -> bool:
        """Check if notification is due for delivery."""
        return (
            self.status == NotificationStatus.SCHEDULED and
            self.scheduled_for <= datetime.utcnow()
        )