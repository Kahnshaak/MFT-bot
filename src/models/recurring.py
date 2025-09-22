"""
Recurring event schedule model for automated event creation.
"""

from datetime import datetime, time, date
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import Field, field_validator

from .base import BaseDocument, ValidationMixin, TimestampMixin


class TriggerType(str, Enum):
    """Types of recurring triggers."""
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    CUSTOM = "CUSTOM"


class ScheduleStatus(str, Enum):
    """Status of recurring schedule."""
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"


class ExecutionStatus(str, Enum):
    """Status of schedule execution."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class EventTemplate(BaseDocument):
    """Template for generating recurring events."""
    
    title_template: str = Field(..., max_length=100, description="Event title template")
    description_template: Optional[str] = Field(
        None, 
        max_length=2000, 
        description="Event description template"
    )
    default_games: List[str] = Field(
        default_factory=list,
        description="Default games to include in polls"
    )
    duration_minutes: Optional[int] = Field(
        None,
        ge=15,
        le=1440,
        description="Default event duration"
    )
    tags: List[str] = Field(default_factory=list, description="Event tags")
    
    # Template variables that can be substituted
    variables: Dict[str, str] = Field(
        default_factory=dict,
        description="Template variables for substitution"
    )
    
    @field_validator('title_template')
    @classmethod
    def validate_title_template(cls, v):
        return ValidationMixin.sanitize_text(v, 100)
    
    @field_validator('description_template')
    @classmethod
    def validate_description_template(cls, v):
        if v:
            return ValidationMixin.sanitize_text(v, 2000)
        return v
    
    def validate_data(self) -> None:
        """Validate event template."""
        if not self.title_template.strip():
            raise ValueError("Title template cannot be empty")
        
        # Validate game names
        for i, game in enumerate(self.default_games):
            self.default_games[i] = ValidationMixin.sanitize_text(game, 100)
    
    def render_title(self, context: Dict[str, Any] = None) -> str:
        """Render title template with context variables."""
        title = self.title_template
        
        # Merge template variables with context
        variables = {**self.variables}
        if context:
            variables.update(context)
        
        # Simple template substitution
        for key, value in variables.items():
            placeholder = f"{{{key}}}"
            title = title.replace(placeholder, str(value))
        
        return ValidationMixin.sanitize_text(title, 100)
    
    def render_description(self, context: Dict[str, Any] = None) -> Optional[str]:
        """Render description template with context variables."""
        if not self.description_template:
            return None
        
        description = self.description_template
        
        # Merge template variables with context
        variables = {**self.variables}
        if context:
            variables.update(context)
        
        # Simple template substitution
        for key, value in variables.items():
            placeholder = f"{{{key}}}"
            description = description.replace(placeholder, str(value))
        
        return ValidationMixin.sanitize_text(description, 2000)


class ScheduleTrigger(BaseDocument):
    """Trigger configuration for recurring schedules."""
    
    trigger_type: TriggerType = Field(..., description="Type of trigger")
    
    # Weekly triggers
    day_of_week: Optional[int] = Field(
        None,
        ge=0,
        le=6,
        description="Day of week (0=Monday, 6=Sunday)"
    )
    
    # Monthly triggers
    day_of_month: Optional[int] = Field(
        None,
        ge=1,
        le=31,
        description="Day of month"
    )
    
    # Time configuration
    trigger_time: time = Field(..., description="Time to trigger")
    timezone: str = Field(default="UTC", description="Timezone for trigger")
    
    # Advanced scheduling
    weeks_between: int = Field(default=1, ge=1, le=52, description="Weeks between triggers")
    months_between: int = Field(default=1, ge=1, le=12, description="Months between triggers")
    
    @field_validator('timezone')
    @classmethod
    def validate_timezone(cls, v):
        return ValidationMixin.validate_timezone(v)
    
    def validate_data(self) -> None:
        """Validate trigger configuration."""
        if self.trigger_type == TriggerType.WEEKLY:
            if self.day_of_week is None:
                raise ValueError("day_of_week required for WEEKLY triggers")
        elif self.trigger_type == TriggerType.MONTHLY:
            if self.day_of_month is None:
                raise ValueError("day_of_month required for MONTHLY triggers")
    
    def get_next_trigger_date(self, after_date: date = None) -> date:
        """Calculate next trigger date after given date."""
        if after_date is None:
            after_date = date.today()
        
        if self.trigger_type == TriggerType.WEEKLY:
            return self._get_next_weekly_date(after_date)
        elif self.trigger_type == TriggerType.MONTHLY:
            return self._get_next_monthly_date(after_date)
        else:
            raise ValueError(f"Unsupported trigger type: {self.trigger_type}")
    
    def _get_next_weekly_date(self, after_date: date) -> date:
        """Calculate next weekly trigger date."""
        from datetime import timedelta
        
        # Find next occurrence of target day
        days_ahead = self.day_of_week - after_date.weekday()
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7 * self.weeks_between
        
        return after_date + timedelta(days=days_ahead)
    
    def _get_next_monthly_date(self, after_date: date) -> date:
        """Calculate next monthly trigger date."""
        from calendar import monthrange
        
        # Start with next month
        year = after_date.year
        month = after_date.month + self.months_between
        
        # Handle year rollover
        while month > 12:
            month -= 12
            year += 1
        
        # Handle day of month that doesn't exist in target month
        max_day = monthrange(year, month)[1]
        day = min(self.day_of_month, max_day)
        
        next_date = date(year, month, day)
        
        # If the calculated date is not after the given date, try next month
        if next_date <= after_date:
            month += self.months_between
            if month > 12:
                month -= 12
                year += 1
            max_day = monthrange(year, month)[1]
            day = min(self.day_of_month, max_day)
            next_date = date(year, month, day)
        
        return next_date


class ExecutionHistory(BaseDocument):
    """History of schedule execution attempts."""
    
    execution_time: datetime = Field(default_factory=TimestampMixin.utc_now)
    status: ExecutionStatus = Field(..., description="Execution status")
    event_id: Optional[str] = Field(None, description="Created event ID if successful")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Execution context and variables"
    )
    
    def validate_data(self) -> None:
        """Validate execution history."""
        if self.status == ExecutionStatus.FAILED and not self.error_message:
            raise ValueError("Error message required for failed executions")
        
        if self.status == ExecutionStatus.SUCCESS and not self.event_id:
            raise ValueError("Event ID required for successful executions")


class RecurringSchedule(BaseDocument, ValidationMixin, TimestampMixin):
    """
    Recurring event schedule configuration.
    
    Manages automated creation of events based on configured triggers and templates.
    """
    
    guild_id: str = Field(..., description="Discord guild ID")
    name: str = Field(..., min_length=1, max_length=100, description="Schedule name")
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Schedule description"
    )
    creator_id: str = Field(..., description="Discord user ID of creator")
    
    # Schedule configuration
    trigger: ScheduleTrigger = Field(..., description="Trigger configuration")
    template: EventTemplate = Field(..., description="Event template")
    
    # Status and control
    status: ScheduleStatus = Field(default=ScheduleStatus.ACTIVE)
    next_trigger: Optional[datetime] = Field(None, description="Next scheduled trigger")
    
    # Execution tracking
    execution_history: List[ExecutionHistory] = Field(
        default_factory=list,
        description="History of executions"
    )
    
    # Limits and controls
    max_executions: Optional[int] = Field(
        None,
        ge=1,
        description="Maximum number of executions (None for unlimited)"
    )
    execution_count: int = Field(default=0, ge=0, description="Number of executions")
    
    # Advanced options
    skip_holidays: bool = Field(default=False, description="Skip execution on holidays")
    advance_notice_days: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Days in advance to create events"
    )
    
    @field_validator('guild_id')
    @classmethod
    def validate_guild_id(cls, v):
        return ValidationMixin.validate_guild_id(v)
    
    @field_validator('creator_id')
    @classmethod
    def validate_creator_id(cls, v):
        return ValidationMixin.validate_user_id(v)
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        return ValidationMixin.sanitize_text(v, 100)
    
    @field_validator('description')
    @classmethod
    def validate_description(cls, v):
        if v:
            return ValidationMixin.sanitize_text(v, 500)
        return v
    
    def validate_data(self) -> None:
        """Validate recurring schedule data."""
        if not self.name.strip():
            raise ValueError("Schedule name cannot be empty")
        
        if self.max_executions and self.execution_count >= self.max_executions:
            if self.status == ScheduleStatus.ACTIVE:
                self.status = ScheduleStatus.DISABLED
    
    def calculate_next_trigger(self) -> datetime:
        """Calculate next trigger datetime."""
        from datetime import datetime, timedelta
        
        # Get next trigger date
        next_date = self.trigger.get_next_trigger_date()
        
        # Combine with trigger time
        next_datetime = datetime.combine(next_date, self.trigger.trigger_time)
        
        # Convert to UTC if needed
        if self.trigger.timezone != "UTC":
            import pytz
            tz = pytz.timezone(self.trigger.timezone)
            next_datetime = tz.localize(next_datetime).astimezone(pytz.UTC)
        
        return next_datetime
    
    def update_next_trigger(self) -> None:
        """Update next trigger time."""
        if self.status == ScheduleStatus.ACTIVE:
            self.next_trigger = self.calculate_next_trigger()
        else:
            self.next_trigger = None
        self.update_timestamp()
    
    def is_due_for_execution(self, current_time: datetime = None) -> bool:
        """Check if schedule is due for execution."""
        if current_time is None:
            current_time = TimestampMixin.utc_now()
        
        return (
            self.status == ScheduleStatus.ACTIVE and
            self.next_trigger is not None and
            current_time >= self.next_trigger and
            (self.max_executions is None or self.execution_count < self.max_executions)
        )
    
    def record_execution(
        self,
        status: ExecutionStatus,
        event_id: Optional[str] = None,
        error_message: Optional[str] = None,
        context: Dict[str, Any] = None
    ) -> None:
        """Record execution attempt."""
        execution = ExecutionHistory(
            status=status,
            event_id=event_id,
            error_message=error_message,
            context=context or {}
        )
        
        self.execution_history.append(execution)
        
        if status == ExecutionStatus.SUCCESS:
            self.execution_count += 1
        
        # Update next trigger for successful executions
        if status == ExecutionStatus.SUCCESS:
            self.update_next_trigger()
        
        self.update_timestamp()
    
    def pause(self) -> bool:
        """Pause the schedule. Returns True if paused."""
        if self.status == ScheduleStatus.ACTIVE:
            self.status = ScheduleStatus.PAUSED
            self.next_trigger = None
            self.update_timestamp()
            return True
        return False
    
    def resume(self) -> bool:
        """Resume the schedule. Returns True if resumed."""
        if self.status == ScheduleStatus.PAUSED:
            self.status = ScheduleStatus.ACTIVE
            self.update_next_trigger()
            return True
        return False
    
    def disable(self) -> None:
        """Permanently disable the schedule."""
        self.status = ScheduleStatus.DISABLED
        self.next_trigger = None
        self.update_timestamp()
    
    def get_recent_executions(self, limit: int = 10) -> List[ExecutionHistory]:
        """Get recent execution history."""
        return sorted(
            self.execution_history,
            key=lambda x: x.execution_time,
            reverse=True
        )[:limit]
    
    def get_success_rate(self) -> float:
        """Calculate execution success rate."""
        if not self.execution_history:
            return 0.0
        
        successful = sum(
            1 for exec in self.execution_history
            if exec.status == ExecutionStatus.SUCCESS
        )
        
        return successful / len(self.execution_history)
    
    def get_template_context(self) -> Dict[str, Any]:
        """Get context variables for template rendering."""
        now = TimestampMixin.utc_now()
        
        return {
            "schedule_name": self.name,
            "execution_count": self.execution_count + 1,
            "current_date": now.strftime("%Y-%m-%d"),
            "current_month": now.strftime("%B"),
            "current_year": now.strftime("%Y"),
            "next_trigger": self.next_trigger.strftime("%Y-%m-%d") if self.next_trigger else ""
        }