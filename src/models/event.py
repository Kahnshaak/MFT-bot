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
    DATE_POLLING = "DATE_POLLING"
    TIME_POLLING = "TIME_POLLING"
    GAME_POLLING = "GAME_POLLING"
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class RSVPStatus(str, Enum):
    """RSVP response options."""
    YES = "YES"
    NO = "NO"
    MAYBE = "MAYBE"


class PollType(str, Enum):
    """Types of polls for events."""
    DATE = "DATE"
    TIME = "TIME"
    GAME = "GAME"


class PollOption(BaseDocument):
    """Individual poll option with vote tracking."""
    
    option_id: str = Field(..., description="Unique option identifier")
    label: str = Field(..., description="Display label for option")
    value: Optional[str] = Field(None, description="Underlying value (e.g., ISO date string)")
    votes: List[str] = Field(default_factory=list, description="List of user IDs who voted for this option")
    vote_count: int = Field(default=0, description="Number of votes")
    
    def add_vote(self, user_id: str) -> bool:
        """Add a vote from a user."""
        if user_id not in self.votes:
            self.votes.append(user_id)
            self.vote_count = len(self.votes)
            return True
        return False
    
    def remove_vote(self, user_id: str) -> bool:
        """Remove a vote from a user."""
        if user_id in self.votes:
            self.votes.remove(user_id)
            self.vote_count = len(self.votes)
            return True
        return False
    
    def validate_data(self) -> None:
        """Basic validation."""
        pass


class Poll(BaseDocument):
    """Poll for event decisions with options and vote tracking."""
    
    poll_type: PollType = Field(..., description="Type of poll")
    title: str = Field(..., description="Poll title")
    description: Optional[str] = Field(None, description="Poll description")
    options: List[PollOption] = Field(default_factory=list, description="Poll options")
    is_active: bool = Field(default=True, description="Whether poll is accepting votes")
    is_multiple_choice: bool = Field(default=False, description="Whether multiple options can be selected")
    closes_at: Optional[datetime] = Field(None, description="When poll closes")
    
    def add_vote(self, user_id: str, option_id: str) -> bool:
        """Add a vote for an option."""
        # Remove any existing votes from this user
        for option in self.options:
            option.remove_vote(user_id)
        
        # Add vote to selected option
        for option in self.options:
            if option.option_id == option_id:
                return option.add_vote(user_id)
        return False
    
    def get_option_by_id(self, option_id: str) -> Optional[PollOption]:
        """Get option by ID."""
        for option in self.options:
            if option.option_id == option_id:
                return option
        return None
    
    def get_winning_options(self) -> List[PollOption]:
        """Get options with the highest vote count."""
        if not self.options:
            return []
        
        max_votes = max(option.vote_count for option in self.options)
        return [option for option in self.options if option.vote_count == max_votes]
    
    def close_poll(self) -> Optional[str]:
        """
        Close the poll and return the winning option ID.
        Returns None if there are no votes or if there's a tie requiring admin resolution.
        """
        if not self.is_active:
            return None
        
        # Mark poll as closed
        self.is_active = False
        
        # Get winning options
        winning_options = self.get_winning_options()
        
        # No votes case
        if not winning_options or all(opt.vote_count == 0 for opt in winning_options):
            return None
        
        # Single winner case
        if len(winning_options) == 1:
            return winning_options[0].option_id
        
        # Tie case - return None to indicate admin resolution needed
        return None
    
    def admin_select_winner(self, option_id: str) -> bool:
        """
        Admin manually selects a winner from tied options.
        Returns True if successful, False otherwise.
        """
        option = self.get_option_by_id(option_id)
        if not option:
            return False
        
        # Mark poll as closed if not already
        self.is_active = False
        
        return True
    
    def validate_data(self) -> None:
        """Basic validation."""
        pass


class RSVPResponse(BaseDocument):
    """Individual RSVP response."""
    
    user_id: str = Field(..., description="Discord user ID")
    status: RSVPStatus = Field(..., description="RSVP status")
    notes: Optional[str] = Field(None, description="Optional notes from user")
    responded_at: datetime = Field(default_factory=datetime.utcnow, description="When RSVP was submitted")
    
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
    
    # Discord integration
    discord_event_id: Optional[str] = Field(None, description="Discord scheduled event ID")
    
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
    
    def add_rsvp(self, user_id: str, status: RSVPStatus, notes: Optional[str] = None) -> None:
        """Add or update RSVP response."""
        self.rsvps[user_id] = RSVPResponse(user_id=user_id, status=status, notes=notes)
    
    def get_rsvp_count(self, status: RSVPStatus) -> int:
        """Get count of RSVPs with specific status."""
        return sum(1 for rsvp in self.rsvps.values() if rsvp.status == status)
    
    def get_attendee_list(self) -> List[str]:
        """Get list of user IDs who RSVP'd yes."""
        return [user_id for user_id, rsvp in self.rsvps.items() if rsvp.status == RSVPStatus.YES]
    
    def get_poll(self, poll_type: PollType) -> Optional[Poll]:
        """Get poll by type."""
        for poll in self.polls:
            if poll.poll_type == poll_type:
                return poll
        return None
    
    def add_poll(self, poll: Poll) -> None:
        """Add a poll to the event."""
        # Remove existing poll of same type
        self.polls = [p for p in self.polls if p.poll_type != poll.poll_type]
        self.polls.append(poll)
    
    def can_transition_to(self, new_state: EventState) -> bool:
        """Check if event can transition to new state."""
        valid_transitions = {
            EventState.DRAFT: [EventState.DATE_POLLING, EventState.SCHEDULED, EventState.CANCELLED],
            EventState.DATE_POLLING: [EventState.TIME_POLLING, EventState.CANCELLED],
            EventState.TIME_POLLING: [EventState.GAME_POLLING, EventState.CANCELLED],
            EventState.GAME_POLLING: [EventState.SCHEDULED, EventState.CANCELLED],
            EventState.SCHEDULED: [EventState.COMPLETED, EventState.CANCELLED],
            EventState.COMPLETED: [],
            EventState.CANCELLED: []
        }
        return new_state in valid_transitions.get(self.state, [])
    
    def transition_to(self, new_state: EventState) -> None:
        """Transition event to new state."""
        if not self.can_transition_to(new_state):
            raise ValueError(f"Cannot transition from {self.state} to {new_state}")
        self.state = new_state
    
    def is_active(self) -> bool:
        """Check if event is active (not cancelled or completed)."""
        return self.state in [
            EventState.DRAFT, 
            EventState.DATE_POLLING, 
            EventState.TIME_POLLING, 
            EventState.GAME_POLLING, 
            EventState.SCHEDULED
        ]