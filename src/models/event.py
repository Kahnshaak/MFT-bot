"""
Event model for game night events with polls and RSVP tracking.
"""

from datetime import datetime, date, time
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import Field, field_validator

from .base import BaseDocument


class EventState(str, Enum):
    """Event lifecycle states."""
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class RSVPStatus(str, Enum):
    """RSVP response options."""
    YES = "YES"
    NO = "NO"
    MAYBE = "MAYBE"


class Poll(BaseDocument):
    """Simple poll for event decisions."""
    
    title: str = Field(..., description="Poll title")
    options: List[str] = Field(default_factory=list, description="Poll options")
    votes: Dict[str, str] = Field(default_factory=dict, description="User votes (user_id -> option)")
    is_active: bool = Field(default=True, description="Whether poll is accepting votes")
    
    def validate_data(self) -> None:
        """Basic validation."""
        pass


class RSVPResponse(BaseDocument):
    """Individual RSVP response."""
    
    user_id: str = Field(..., description="Discord user ID")
    status: RSVPStatus = Field(..., description="RSVP status")
    
    def validate_data(self) -> None:
        """Basic validation."""
        pass


class Event(BaseDocument):
    """
    Main event model for game night events.
    """
    
    guild_id: str = Field(..., description="Discord guild ID")
    title: str = Field(..., description="Event title")
    description: Optional[str] = Field(None, description="Event description")
    creator_id: str = Field(..., description="Discord user ID of event creator")
    state: EventState = Field(default=EventState.DRAFT, description="Current event state")
    
    # Scheduling
    scheduled_date: Optional[date] = Field(None, description="Event date")
    scheduled_time: Optional[time] = Field(None, description="Event time")
    timezone: str = Field(default="UTC", description="Event timezone")
    
    # Polls
    polls: List[Poll] = Field(default_factory=list, description="Event polls")
    
    # RSVP tracking
    rsvps: Dict[str, RSVPResponse] = Field(default_factory=dict, description="RSVP responses by user ID")
    
    @field_validator('guild_id', 'creator_id')
    @classmethod
    def validate_ids(cls, v):
        if not v or not v.isdigit():
            raise ValueError("ID must be a valid Discord snowflake")
        return v
    
    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        if not v or len(v.strip()) < 3:
            raise ValueError("Title must be at least 3 characters")
        return v.strip()[:100]
    
    def validate_data(self) -> None:
        """Basic validation."""
        pass
    
    def add_rsvp(self, user_id: str, status: RSVPStatus) -> None:
        """Add or update RSVP response."""
        self.rsvps[user_id] = RSVPResponse(user_id=user_id, status=status)
    
    def get_rsvp_count(self, status: RSVPStatus) -> int:
        """Get count of RSVPs with specific status."""
        return sum(1 for rsvp in self.rsvps.values() if rsvp.status == status)
    
    def get_attendee_list(self) -> List[str]:
        """Get list of user IDs who RSVP'd yes."""
        return [user_id for user_id, rsvp in self.rsvps.items() if rsvp.status == RSVPStatus.YES]