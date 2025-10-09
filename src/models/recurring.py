"""
Recurring event schedule model for automated event creation.
"""

from datetime import datetime, time
from enum import Enum
from typing import List, Optional
from pydantic import Field, field_validator

from .base import BaseDocument


class ScheduleStatus(str, Enum):
    """Status of recurring schedule."""
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"


class RecurringSchedule(BaseDocument):
    """
    Simple recurring event schedule.
    """
    
    guild_id: str = Field(..., description="Discord guild ID")
    name: str = Field(..., description="Schedule name")
    description: Optional[str] = Field(None, description="Schedule description")
    creator_id: str = Field(..., description="Discord user ID of creator")
    
    # Basic scheduling
    day_of_week: int = Field(..., ge=0, le=6, description="Day of week (0=Monday, 6=Sunday)")
    trigger_time: time = Field(..., description="Time to trigger")
    
    # Event template
    event_title: str = Field(..., description="Event title template")
    event_description: Optional[str] = Field(None, description="Event description template")
    
    # Status
    status: ScheduleStatus = Field(default=ScheduleStatus.ACTIVE)
    next_trigger: Optional[datetime] = Field(None, description="Next scheduled trigger")
    
    @field_validator('guild_id', 'creator_id')
    @classmethod
    def validate_ids(cls, v):
        if not v or not v.isdigit():
            raise ValueError("ID must be a valid Discord snowflake")
        return v
    
    @field_validator('name', 'event_title')
    @classmethod
    def validate_text_fields(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Field cannot be empty")
        return v.strip()[:100]
    
    @field_validator('description', 'event_description')
    @classmethod
    def validate_description_fields(cls, v):
        if v:
            return v.strip()[:500]
        return v
    
    def validate_data(self) -> None:
        """Basic validation."""
        pass