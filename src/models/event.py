"""
Event model for game night events with polls and RSVP tracking.
"""

from datetime import datetime, date, time
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import Field, field_validator

from .base import BaseDocument, ValidationMixin, TimestampMixin


class EventState(str, Enum):
    """Event lifecycle states."""
    DRAFT = "DRAFT"
    DATE_POLLING = "DATE_POLLING"
    TIME_POLLING = "TIME_POLLING"
    GAME_POLLING = "GAME_POLLING"
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class PollType(str, Enum):
    """Types of polls within an event."""
    DATE = "DATE"
    TIME = "TIME"
    GAME = "GAME"


class RSVPStatus(str, Enum):
    """RSVP response options."""
    YES = "YES"
    NO = "NO"
    MAYBE = "MAYBE"


class PollOption(BaseDocument):
    """Individual poll option with vote tracking."""
    
    option_id: str = Field(..., description="Unique identifier for this option")
    label: str = Field(..., max_length=100, description="Display text for the option")
    value: Any = Field(..., description="The actual value (date, time, game name)")
    votes: List[str] = Field(default_factory=list, description="List of user IDs who voted")
    vote_count: int = Field(default=0, description="Cached vote count")
    
    def validate_data(self) -> None:
        """Validate poll option data."""
        if not self.label.strip():
            raise ValueError("Poll option label cannot be empty")
        
        # Sync vote count with votes list
        self.vote_count = len(self.votes)
    
    def add_vote(self, user_id: str) -> bool:
        """Add a vote from a user. Returns True if vote was added."""
        if user_id not in self.votes:
            self.votes.append(user_id)
            self.vote_count = len(self.votes)
            return True
        return False
    
    def remove_vote(self, user_id: str) -> bool:
        """Remove a vote from a user. Returns True if vote was removed."""
        if user_id in self.votes:
            self.votes.remove(user_id)
            self.vote_count = len(self.votes)
            return True
        return False


class Poll(BaseDocument):
    """Poll within an event for date, time, or game selection."""
    
    poll_type: PollType = Field(..., description="Type of poll")
    title: str = Field(..., max_length=200, description="Poll title")
    description: Optional[str] = Field(None, max_length=1000, description="Poll description")
    options: List[PollOption] = Field(default_factory=list, description="Poll options")
    is_active: bool = Field(default=True, description="Whether poll is accepting votes")
    is_multiple_choice: bool = Field(default=False, description="Allow multiple selections")
    closes_at: Optional[datetime] = Field(None, description="When poll closes")
    winner_option_id: Optional[str] = Field(None, description="ID of winning option")
    
    def validate_data(self) -> None:
        """Validate poll data."""
        if not self.title.strip():
            raise ValueError("Poll title cannot be empty")
        
        if len(self.options) < 2:
            raise ValueError("Poll must have at least 2 options")
        
        # Validate unique option IDs
        option_ids = [opt.option_id for opt in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("Poll option IDs must be unique")
    
    def get_option_by_id(self, option_id: str) -> Optional[PollOption]:
        """Get poll option by ID."""
        return next((opt for opt in self.options if opt.option_id == option_id), None)
    
    def add_vote(self, user_id: str, option_id: str) -> bool:
        """Add a vote to an option. Returns True if successful."""
        option = self.get_option_by_id(option_id)
        if not option or not self.is_active:
            return False
        
        # For single-choice polls, remove existing votes
        if not self.is_multiple_choice:
            for opt in self.options:
                opt.remove_vote(user_id)
        
        return option.add_vote(user_id)
    
    def remove_vote(self, user_id: str, option_id: str) -> bool:
        """Remove a vote from an option. Returns True if successful."""
        option = self.get_option_by_id(option_id)
        if not option:
            return False
        
        return option.remove_vote(user_id)
    
    def get_winning_option(self) -> Optional[PollOption]:
        """Get the option with the most votes."""
        if not self.options:
            return None
        
        return max(self.options, key=lambda opt: opt.vote_count)
    
    def close_poll(self) -> Optional[str]:
        """Close the poll and determine winner. Returns winner option ID."""
        self.is_active = False
        winner = self.get_winning_option()
        if winner and winner.vote_count > 0:
            self.winner_option_id = winner.option_id
            return winner.option_id
        return None


class EventSchedule(BaseDocument):
    """Event scheduling information."""
    
    selected_date: Optional[date] = Field(None, description="Selected event date")
    selected_time: Optional[time] = Field(None, description="Selected event time")
    timezone: str = Field(default="UTC", description="Event timezone")
    duration_minutes: Optional[int] = Field(None, ge=15, le=1440, description="Event duration")
    
    @field_validator('timezone')
    @classmethod
    def validate_timezone(cls, v):
        return ValidationMixin.validate_timezone(v)
    
    def validate_data(self) -> None:
        """Validate schedule data."""
        if self.selected_date and self.selected_date < date.today():
            raise ValueError("Event date cannot be in the past")


class RSVPResponse(BaseDocument):
    """Individual RSVP response."""
    
    user_id: str = Field(..., description="Discord user ID")
    status: RSVPStatus = Field(..., description="RSVP status")
    response_time: datetime = Field(default_factory=TimestampMixin.utc_now)
    notes: Optional[str] = Field(None, max_length=500, description="Optional notes")
    
    @field_validator('user_id')
    @classmethod
    def validate_user_id(cls, v):
        return ValidationMixin.validate_user_id(v)
    
    def validate_data(self) -> None:
        """Validate RSVP response."""
        if self.notes:
            self.notes = ValidationMixin.sanitize_text(self.notes, 500)


class Event(BaseDocument, ValidationMixin, TimestampMixin):
    """
    Main event model for game night events.
    
    Manages the complete lifecycle from creation through polls to completion.
    """
    
    guild_id: str = Field(..., description="Discord guild ID")
    discord_event_id: Optional[str] = Field(None, description="Discord scheduled event ID")
    title: str = Field(..., min_length=3, max_length=100, description="Event title")
    description: Optional[str] = Field(None, max_length=2000, description="Event description")
    creator_id: str = Field(..., description="Discord user ID of event creator")
    state: EventState = Field(default=EventState.DRAFT, description="Current event state")
    
    # Scheduling
    schedule: EventSchedule = Field(default_factory=EventSchedule)
    
    # Polls
    polls: Dict[str, Poll] = Field(default_factory=dict, description="Event polls by type")
    
    # RSVP tracking
    rsvp_data: Dict[str, RSVPResponse] = Field(
        default_factory=dict, 
        description="RSVP responses by user ID"
    )
    
    # Attendance tracking (post-event)
    attendance: Dict[str, bool] = Field(
        default_factory=dict,
        description="Actual attendance by user ID"
    )
    
    # Metadata
    tags: List[str] = Field(default_factory=list, description="Event tags")
    is_recurring: bool = Field(default=False, description="Whether this is a recurring event")
    recurring_schedule_id: Optional[str] = Field(None, description="ID of recurring schedule")
    
    @field_validator('guild_id')
    @classmethod
    def validate_guild_id(cls, v):
        return ValidationMixin.validate_guild_id(v)
    
    @field_validator('creator_id')
    @classmethod
    def validate_creator_id(cls, v):
        return ValidationMixin.validate_user_id(v)
    
    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        return ValidationMixin.sanitize_text(v, 100)
    
    @field_validator('description')
    @classmethod
    def validate_description(cls, v):
        if v:
            return ValidationMixin.sanitize_text(v, 2000)
        return v
    
    def validate_data(self) -> None:
        """Validate event data and business rules."""
        # Validate state transitions
        valid_transitions = {
            EventState.DRAFT: [EventState.DATE_POLLING, EventState.CANCELLED],
            EventState.DATE_POLLING: [EventState.TIME_POLLING, EventState.CANCELLED],
            EventState.TIME_POLLING: [EventState.GAME_POLLING, EventState.CANCELLED],
            EventState.GAME_POLLING: [EventState.SCHEDULED, EventState.CANCELLED],
            EventState.SCHEDULED: [EventState.COMPLETED, EventState.CANCELLED],
            EventState.COMPLETED: [],
            EventState.CANCELLED: []
        }
        
        # Validate polls exist for current state
        if self.state == EventState.DATE_POLLING and 'DATE' not in self.polls:
            raise ValueError("Date poll required for DATE_POLLING state")
        elif self.state == EventState.TIME_POLLING and 'TIME' not in self.polls:
            raise ValueError("Time poll required for TIME_POLLING state")
        elif self.state == EventState.GAME_POLLING and 'GAME' not in self.polls:
            raise ValueError("Game poll required for GAME_POLLING state")
        
        # Validate schedule completeness for SCHEDULED state
        if self.state == EventState.SCHEDULED:
            if not self.schedule.selected_date or not self.schedule.selected_time:
                raise ValueError("Complete schedule required for SCHEDULED state")
    
    def can_transition_to(self, new_state: EventState) -> bool:
        """Check if event can transition to new state."""
        valid_transitions = {
            EventState.DRAFT: [EventState.DATE_POLLING, EventState.CANCELLED],
            EventState.DATE_POLLING: [EventState.TIME_POLLING, EventState.CANCELLED],
            EventState.TIME_POLLING: [EventState.GAME_POLLING, EventState.CANCELLED],
            EventState.GAME_POLLING: [EventState.SCHEDULED, EventState.CANCELLED],
            EventState.SCHEDULED: [EventState.COMPLETED, EventState.CANCELLED],
            EventState.COMPLETED: [],
            EventState.CANCELLED: []
        }
        
        return new_state in valid_transitions.get(self.state, [])
    
    def transition_to(self, new_state: EventState) -> bool:
        """Transition event to new state if valid."""
        if self.can_transition_to(new_state):
            self.state = new_state
            self.update_timestamp()
            return True
        return False
    
    def get_poll(self, poll_type: PollType) -> Optional[Poll]:
        """Get poll by type."""
        return self.polls.get(poll_type.value)
    
    def add_poll(self, poll: Poll) -> None:
        """Add a poll to the event."""
        self.polls[poll.poll_type.value] = poll
        self.update_timestamp()
    
    def add_rsvp(self, user_id: str, status: RSVPStatus, notes: Optional[str] = None) -> None:
        """Add or update RSVP response."""
        self.rsvp_data[user_id] = RSVPResponse(
            user_id=user_id,
            status=status,
            notes=notes
        )
        self.update_timestamp()
    
    def get_rsvp_count(self, status: RSVPStatus) -> int:
        """Get count of RSVPs with specific status."""
        return sum(1 for rsvp in self.rsvp_data.values() if rsvp.status == status)
    
    def get_attendee_list(self) -> List[str]:
        """Get list of user IDs who RSVP'd yes."""
        return [
            user_id for user_id, rsvp in self.rsvp_data.items()
            if rsvp.status == RSVPStatus.YES
        ]
    
    def record_attendance(self, user_id: str, attended: bool) -> None:
        """Record actual attendance for a user."""
        self.attendance[user_id] = attended
        self.update_timestamp()
    
    def get_attendance_rate(self) -> float:
        """Calculate attendance rate (attended / RSVP'd yes)."""
        yes_rsvps = self.get_rsvp_count(RSVPStatus.YES)
        if yes_rsvps == 0:
            return 0.0
        
        attended_count = sum(1 for attended in self.attendance.values() if attended)
        return attended_count / yes_rsvps
    
    def is_active(self) -> bool:
        """Check if event is in an active state."""
        return self.state not in [EventState.COMPLETED, EventState.CANCELLED]
    
    def is_scheduled(self) -> bool:
        """Check if event is scheduled with complete details."""
        return (
            self.state == EventState.SCHEDULED and
            self.schedule.selected_date is not None and
            self.schedule.selected_time is not None
        )