"""
Simplified Event model for game night scheduling with automatic poll-based date/time selection.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pydantic import Field, field_validator

from .base import BaseDocument


class Event(BaseDocument):
    """
    Simplified event model for poll-based game night scheduling.
    
    Flow:
    1. User creates event with title
    2. Poll is generated with date/time options (status="active")
    3. Users vote on dates and times
    4. After 7 days, poll expires and winner is calculated
    5. Discord Scheduled Event is created (status="scheduled")
    """
    
    # Core identifiers
    guild_id: str = Field(..., description="Discord guild ID")
    channel_id: str = Field(..., description="Channel where poll was posted")
    message_id: Optional[str] = Field(None, description="Poll message ID")
    creator_id: str = Field(..., description="Discord user ID of event creator")
    
    # Event details
    title: str = Field(..., description="Event title")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When event was created")
    expires_at: datetime = Field(..., description="When poll expires (7 days from creation)")
    
    # Status tracking
    status: str = Field(default="active", description="Event status: active, expired, scheduled, tie")
    
    # Vote tracking
    # Format: {"2025-10-15": ["user_id_1", "user_id_2"], "2025-10-16": ["user_id_3"]}
    date_votes: Dict[str, List[str]] = Field(default_factory=dict, description="Date votes by option")
    time_votes: Dict[str, List[str]] = Field(default_factory=dict, description="Time votes by option")
    
    # Results
    winning_date: Optional[str] = Field(None, description="Winning date (YYYY-MM-DD format)")
    winning_time: Optional[str] = Field(None, description="Winning time (HH:MM format)")
    discord_event_id: Optional[str] = Field(None, description="Discord scheduled event ID")
    
    @field_validator('guild_id', 'channel_id', 'creator_id')
    @classmethod
    def validate_ids(cls, v):
        """Validate Discord IDs are valid snowflakes."""
        if not v or not v.isdigit():
            raise ValueError("ID must be a valid Discord snowflake")
        return v
    
    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        """Validate event title is between 3-100 characters."""
        if not v or len(v.strip()) < 3:
            raise ValueError("Title must be at least 3 characters")
        if len(v.strip()) > 100:
            raise ValueError("Title must be at most 100 characters")
        # Sanitize @everyone and @here mentions
        sanitized = v.strip().replace('@everyone', '@\u200beveryone').replace('@here', '@\u200bhere')
        return sanitized
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        """Validate status is one of the allowed values."""
        allowed_statuses = ["active", "expired", "scheduled", "tie"]
        if v not in allowed_statuses:
            raise ValueError(f"Status must be one of: {', '.join(allowed_statuses)}")
        return v
    
    def add_vote(self, user_id: str, dates: List[str], times: List[str]) -> None:
        """
        Add or update votes for a user.
        Replaces any existing votes from this user.
        
        Args:
            user_id: Discord user ID
            dates: List of date strings (YYYY-MM-DD format)
            times: List of time strings (HH:MM format)
        """
        # Remove user's existing votes
        for date_option in list(self.date_votes.keys()):
            if user_id in self.date_votes[date_option]:
                self.date_votes[date_option].remove(user_id)
                # Clean up empty lists
                if not self.date_votes[date_option]:
                    del self.date_votes[date_option]
        
        for time_option in list(self.time_votes.keys()):
            if user_id in self.time_votes[time_option]:
                self.time_votes[time_option].remove(user_id)
                # Clean up empty lists
                if not self.time_votes[time_option]:
                    del self.time_votes[time_option]
        
        # Add new votes
        for date in dates:
            if date not in self.date_votes:
                self.date_votes[date] = []
            self.date_votes[date].append(user_id)
        
        for time in times:
            if time not in self.time_votes:
                self.time_votes[time] = []
            self.time_votes[time].append(user_id)
    
    def get_vote_counts(self) -> Tuple[Dict[str, int], Dict[str, int]]:
        """
        Get vote counts for all options.
        
        Returns:
            Tuple of (date_counts, time_counts) where each is a dict mapping option to count
        """
        date_counts = {date: len(voters) for date, voters in self.date_votes.items()}
        time_counts = {time: len(voters) for time, voters in self.time_votes.items()}
        return date_counts, time_counts
    
    def calculate_winner(self) -> Tuple[Optional[str], Optional[str], bool, List[str], List[str]]:
        """
        Calculate winning date and time based on vote counts.
        
        Returns:
            Tuple of (winning_date, winning_time, is_tie, tied_dates, tied_times)
            - winning_date: Winning date string or None if tie/no votes
            - winning_time: Winning time string or None if tie/no votes
            - is_tie: True if there's a tie that needs admin resolution
            - tied_dates: List of tied date options (empty if no tie)
            - tied_times: List of tied time options (empty if no tie)
        """
        date_counts, time_counts = self.get_vote_counts()
        
        # Handle no votes case
        if not date_counts or not time_counts:
            return None, None, True, [], []
        
        # Find winning date(s)
        max_date_votes = max(date_counts.values())
        winning_dates = [date for date, count in date_counts.items() if count == max_date_votes]
        
        # Find winning time(s)
        max_time_votes = max(time_counts.values())
        winning_times = [time for time, count in time_counts.items() if count == max_time_votes]
        
        # Check for ties
        date_tie = len(winning_dates) > 1
        time_tie = len(winning_times) > 1
        is_tie = date_tie or time_tie
        
        # Return results
        if is_tie:
            return None, None, True, winning_dates if date_tie else [], winning_times if time_tie else []
        else:
            return winning_dates[0], winning_times[0], False, [], []
    
    def validate_data(self) -> None:
        """
        Validate event data consistency.
        
        Raises:
            ValueError: If data is invalid
        """
        # Validate status transitions
        if self.status == "scheduled" and not self.discord_event_id:
            raise ValueError("Scheduled events must have a discord_event_id")
        
        if self.status == "scheduled" and (not self.winning_date or not self.winning_time):
            raise ValueError("Scheduled events must have winning_date and winning_time")
        
        # Validate expires_at is after created_at
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")