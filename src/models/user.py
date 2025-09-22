"""
User model for Discord user profiles and preferences.
"""

from datetime import datetime, time
from enum import Enum
from typing import Dict, List, Optional, Set
from pydantic import Field, field_validator

from .base import BaseDocument, ValidationMixin, TimestampMixin


class NotificationChannel(str, Enum):
    """Notification delivery channels."""
    DM = "DM"
    SERVER = "SERVER"
    BOTH = "BOTH"
    NONE = "NONE"


class NotificationTiming(str, Enum):
    """Notification timing options."""
    IMMEDIATE = "IMMEDIATE"
    HOUR_BEFORE = "HOUR_BEFORE"
    DAY_BEFORE = "DAY_BEFORE"
    WEEK_BEFORE = "WEEK_BEFORE"
    CUSTOM = "CUSTOM"


class DayOfWeek(str, Enum):
    """Days of the week."""
    MONDAY = "MONDAY"
    TUESDAY = "TUESDAY"
    WEDNESDAY = "WEDNESDAY"
    THURSDAY = "THURSDAY"
    FRIDAY = "FRIDAY"
    SATURDAY = "SATURDAY"
    SUNDAY = "SUNDAY"


class AvailabilitySlot(BaseDocument):
    """Time slot when user is available."""
    
    day: DayOfWeek = Field(..., description="Day of the week")
    start_time: time = Field(..., description="Start time")
    end_time: time = Field(..., description="End time")
    
    def validate_data(self) -> None:
        """Validate availability slot."""
        if self.start_time >= self.end_time:
            raise ValueError("Start time must be before end time")
    
    def overlaps_with(self, other: 'AvailabilitySlot') -> bool:
        """Check if this slot overlaps with another."""
        if self.day != other.day:
            return False
        
        return (
            self.start_time < other.end_time and
            self.end_time > other.start_time
        )
    
    def contains_time(self, check_time: time) -> bool:
        """Check if a time falls within this slot."""
        return self.start_time <= check_time <= self.end_time


class NotificationPreferences(BaseDocument):
    """User notification preferences."""
    
    channel: NotificationChannel = Field(default=NotificationChannel.BOTH)
    event_reminders: bool = Field(default=True, description="Receive event reminders")
    poll_notifications: bool = Field(default=True, description="Receive poll notifications")
    game_pings: bool = Field(default=True, description="Receive game ping notifications")
    
    # Timing preferences
    reminder_timing: NotificationTiming = Field(default=NotificationTiming.DAY_BEFORE)
    custom_reminder_minutes: Optional[int] = Field(
        None, 
        ge=5, 
        le=10080,  # 1 week in minutes
        description="Custom reminder time in minutes before event"
    )
    
    # Frequency limits
    max_game_pings_per_day: int = Field(default=5, ge=0, le=50)
    quiet_hours_start: Optional[time] = Field(None, description="Start of quiet hours")
    quiet_hours_end: Optional[time] = Field(None, description="End of quiet hours")
    
    def validate_data(self) -> None:
        """Validate notification preferences."""
        if self.reminder_timing == NotificationTiming.CUSTOM:
            if self.custom_reminder_minutes is None:
                raise ValueError("Custom reminder minutes required for CUSTOM timing")
        
        if self.quiet_hours_start and self.quiet_hours_end:
            # Allow overnight quiet hours (e.g., 22:00 to 08:00)
            pass  # No validation needed for overnight periods
    
    def is_in_quiet_hours(self, check_time: time) -> bool:
        """Check if a time falls within quiet hours."""
        if not self.quiet_hours_start or not self.quiet_hours_end:
            return False
        
        if self.quiet_hours_start <= self.quiet_hours_end:
            # Same day quiet hours (e.g., 12:00 to 14:00)
            return self.quiet_hours_start <= check_time <= self.quiet_hours_end
        else:
            # Overnight quiet hours (e.g., 22:00 to 08:00)
            return check_time >= self.quiet_hours_start or check_time <= self.quiet_hours_end


class GameInterest(BaseDocument):
    """User interest in a specific game."""
    
    game_name: str = Field(..., min_length=1, max_length=100)
    interest_level: int = Field(default=5, ge=1, le=10, description="Interest level 1-10")
    added_at: datetime = Field(default_factory=TimestampMixin.utc_now)
    last_played: Optional[datetime] = Field(None, description="Last time played this game")
    notification_enabled: bool = Field(default=True, description="Receive pings for this game")
    
    @field_validator('game_name')
    @classmethod
    def validate_game_name(cls, v):
        return ValidationMixin.sanitize_text(v, 100)
    
    def validate_data(self) -> None:
        """Validate game interest."""
        if not self.game_name.strip():
            raise ValueError("Game name cannot be empty")


class UserStatistics(BaseDocument):
    """User participation statistics."""
    
    events_created: int = Field(default=0, ge=0)
    events_attended: int = Field(default=0, ge=0)
    events_rsvp_yes: int = Field(default=0, ge=0)
    events_rsvp_no: int = Field(default=0, ge=0)
    events_rsvp_maybe: int = Field(default=0, ge=0)
    
    # Attendance tracking
    total_rsvps: int = Field(default=0, ge=0)
    attendance_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # Game preferences
    favorite_games: List[str] = Field(default_factory=list)
    games_played_count: Dict[str, int] = Field(default_factory=dict)
    
    # Activity tracking
    last_event_created: Optional[datetime] = Field(None)
    last_event_attended: Optional[datetime] = Field(None)
    last_active: datetime = Field(default_factory=TimestampMixin.utc_now)
    
    def validate_data(self) -> None:
        """Validate user statistics."""
        # Ensure total RSVPs matches sum of individual RSVP counts
        calculated_total = self.events_rsvp_yes + self.events_rsvp_no + self.events_rsvp_maybe
        if self.total_rsvps != calculated_total:
            self.total_rsvps = calculated_total
        
        # Recalculate attendance rate
        if self.events_rsvp_yes > 0:
            self.attendance_rate = min(self.events_attended / self.events_rsvp_yes, 1.0)
        else:
            self.attendance_rate = 0.0
    
    def update_event_created(self) -> None:
        """Update statistics for event creation."""
        self.events_created += 1
        self.last_event_created = TimestampMixin.utc_now()
        self.last_active = TimestampMixin.utc_now()
    
    def update_rsvp(self, status: str) -> None:
        """Update RSVP statistics."""
        if status == "YES":
            self.events_rsvp_yes += 1
        elif status == "NO":
            self.events_rsvp_no += 1
        elif status == "MAYBE":
            self.events_rsvp_maybe += 1
        
        self.total_rsvps += 1
        self.last_active = TimestampMixin.utc_now()
        self.validate_data()  # Recalculate derived fields
    
    def update_attendance(self, attended: bool) -> None:
        """Update attendance statistics."""
        if attended:
            self.events_attended += 1
            self.last_event_attended = TimestampMixin.utc_now()
        
        self.last_active = TimestampMixin.utc_now()
        self.validate_data()  # Recalculate attendance rate
    
    def update_game_played(self, game_name: str) -> None:
        """Update game play statistics."""
        game_name = ValidationMixin.sanitize_text(game_name, 100)
        self.games_played_count[game_name] = self.games_played_count.get(game_name, 0) + 1
        
        # Update favorite games list (top 10 most played)
        sorted_games = sorted(
            self.games_played_count.items(),
            key=lambda x: x[1],
            reverse=True
        )
        self.favorite_games = [game for game, _ in sorted_games[:10]]
        
        self.last_active = TimestampMixin.utc_now()


class User(BaseDocument, ValidationMixin, TimestampMixin):
    """
    User profile model for Discord users.
    
    Stores preferences, availability, game interests, and statistics.
    """
    
    user_id: str = Field(..., description="Discord user ID")
    guild_id: str = Field(..., description="Discord guild ID")
    
    # Profile information
    display_name: Optional[str] = Field(None, max_length=100, description="Display name")
    timezone: str = Field(default="UTC", description="User's timezone")
    
    # Availability
    availability: List[AvailabilitySlot] = Field(
        default_factory=list,
        description="Weekly availability schedule"
    )
    
    # Preferences
    notification_preferences: NotificationPreferences = Field(
        default_factory=NotificationPreferences
    )
    
    # Game interests
    game_interests: List[GameInterest] = Field(
        default_factory=list,
        description="Games the user is interested in"
    )
    
    # Statistics
    statistics: UserStatistics = Field(default_factory=UserStatistics)
    
    # Privacy settings
    profile_public: bool = Field(default=True, description="Whether profile is public")
    stats_public: bool = Field(default=True, description="Whether stats are public")
    
    # Data export
    data_export_requested: Optional[datetime] = Field(None)
    
    @field_validator('user_id')
    @classmethod
    def validate_user_id(cls, v):
        return ValidationMixin.validate_user_id(v)
    
    @field_validator('guild_id')
    @classmethod
    def validate_guild_id(cls, v):
        return ValidationMixin.validate_guild_id(v)
    
    @field_validator('timezone')
    @classmethod
    def validate_timezone(cls, v):
        return ValidationMixin.validate_timezone(v)
    
    @field_validator('display_name')
    @classmethod
    def validate_display_name(cls, v):
        if v:
            return ValidationMixin.sanitize_text(v, 100)
        return v
    
    def validate_data(self) -> None:
        """Validate user data and business rules."""
        # Validate availability slots don't overlap
        for i, slot1 in enumerate(self.availability):
            for j, slot2 in enumerate(self.availability[i+1:], i+1):
                if slot1.overlaps_with(slot2):
                    raise ValueError(f"Availability slots {i} and {j} overlap")
        
        # Validate game interests are unique
        game_names = [interest.game_name.lower() for interest in self.game_interests]
        if len(game_names) != len(set(game_names)):
            raise ValueError("Duplicate game interests not allowed")
    
    def add_game_interest(
        self, 
        game_name: str, 
        interest_level: int = 5,
        notification_enabled: bool = True
    ) -> bool:
        """Add interest in a game. Returns True if added, False if already exists."""
        game_name = ValidationMixin.sanitize_text(game_name, 100)
        
        # Check if already interested
        for interest in self.game_interests:
            if interest.game_name.lower() == game_name.lower():
                return False
        
        self.game_interests.append(GameInterest(
            game_name=game_name,
            interest_level=interest_level,
            notification_enabled=notification_enabled
        ))
        self.update_timestamp()
        return True
    
    def remove_game_interest(self, game_name: str) -> bool:
        """Remove interest in a game. Returns True if removed, False if not found."""
        for i, interest in enumerate(self.game_interests):
            if interest.game_name.lower() == game_name.lower():
                del self.game_interests[i]
                self.update_timestamp()
                return True
        return False
    
    def get_game_interest(self, game_name: str) -> Optional[GameInterest]:
        """Get game interest by name."""
        for interest in self.game_interests:
            if interest.game_name.lower() == game_name.lower():
                return interest
        return None
    
    def is_interested_in_game(self, game_name: str) -> bool:
        """Check if user is interested in a game and wants notifications."""
        interest = self.get_game_interest(game_name)
        return interest is not None and interest.notification_enabled
    
    def add_availability_slot(
        self, 
        day: DayOfWeek, 
        start_time: time, 
        end_time: time
    ) -> bool:
        """Add availability slot. Returns True if added successfully."""
        new_slot = AvailabilitySlot(
            day=day,
            start_time=start_time,
            end_time=end_time
        )
        
        # Check for overlaps
        for existing_slot in self.availability:
            if new_slot.overlaps_with(existing_slot):
                return False
        
        self.availability.append(new_slot)
        self.update_timestamp()
        return True
    
    def remove_availability_slot(self, day: DayOfWeek, start_time: time) -> bool:
        """Remove availability slot. Returns True if removed."""
        for i, slot in enumerate(self.availability):
            if slot.day == day and slot.start_time == start_time:
                del self.availability[i]
                self.update_timestamp()
                return True
        return False
    
    def is_available_at(self, day: DayOfWeek, check_time: time) -> bool:
        """Check if user is available at a specific day and time."""
        for slot in self.availability:
            if slot.day == day and slot.contains_time(check_time):
                return True
        return False
    
    def get_available_days(self) -> Set[DayOfWeek]:
        """Get set of days when user has availability."""
        return {slot.day for slot in self.availability}
    
    def update_last_active(self) -> None:
        """Update last active timestamp."""
        self.statistics.last_active = TimestampMixin.utc_now()
        self.update_timestamp()
    
    def request_data_export(self) -> None:
        """Request data export for privacy compliance."""
        self.data_export_requested = TimestampMixin.utc_now()
        self.update_timestamp()
    
    def get_export_data(self) -> Dict[str, any]:
        """Get user data for export."""
        return {
            "user_id": self.user_id,
            "guild_id": self.guild_id,
            "profile": {
                "display_name": self.display_name,
                "timezone": self.timezone,
                "created_at": self.created_at.isoformat(),
                "updated_at": self.updated_at.isoformat()
            },
            "availability": [
                {
                    "day": slot.day,
                    "start_time": slot.start_time.isoformat(),
                    "end_time": slot.end_time.isoformat()
                }
                for slot in self.availability
            ],
            "game_interests": [
                {
                    "game_name": interest.game_name,
                    "interest_level": interest.interest_level,
                    "added_at": interest.added_at.isoformat(),
                    "last_played": interest.last_played.isoformat() if interest.last_played else None
                }
                for interest in self.game_interests
            ],
            "statistics": self.statistics.to_dict(),
            "notification_preferences": self.notification_preferences.to_dict()
        }