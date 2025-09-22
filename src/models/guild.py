"""
Guild configuration model for server-specific settings.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import Field, field_validator

from .base import BaseDocument, ValidationMixin, TimestampMixin


class PermissionLevel(str, Enum):
    """Permission levels for bot operations."""
    ADMIN = "ADMIN"
    ORGANIZER = "ORGANIZER"
    MEMBER = "MEMBER"
    RESTRICTED = "RESTRICTED"


class NotificationChannelType(str, Enum):
    """Types of notification channels."""
    EVENTS = "EVENTS"
    POLLS = "POLLS"
    REMINDERS = "REMINDERS"
    ADMIN = "ADMIN"
    GENERAL = "GENERAL"


class RoleMapping(BaseDocument):
    """Mapping of Discord roles to bot permissions."""
    
    role_id: str = Field(..., description="Discord role ID")
    permission_level: PermissionLevel = Field(..., description="Permission level")
    can_create_events: bool = Field(default=True, description="Can create events")
    can_manage_own_events: bool = Field(default=True, description="Can manage own events")
    can_manage_all_events: bool = Field(default=False, description="Can manage all events")
    can_create_recurring: bool = Field(default=False, description="Can create recurring schedules")
    can_manage_guild_config: bool = Field(default=False, description="Can modify guild settings")
    can_view_analytics: bool = Field(default=False, description="Can view server analytics")
    
    @field_validator('role_id')
    @classmethod
    def validate_role_id(cls, v):
        if not v or not v.isdigit():
            raise ValueError("Role ID must be a valid Discord snowflake")
        return v
    
    def validate_data(self) -> None:
        """Validate role mapping configuration."""
        # Admin level should have all permissions
        if self.permission_level == PermissionLevel.ADMIN:
            self.can_create_events = True
            self.can_manage_own_events = True
            self.can_manage_all_events = True
            self.can_create_recurring = True
            self.can_manage_guild_config = True
            self.can_view_analytics = True
        
        # Organizer level should have event management permissions
        elif self.permission_level == PermissionLevel.ORGANIZER:
            self.can_create_events = True
            self.can_manage_own_events = True
            self.can_create_recurring = True
        
        # Restricted level should have minimal permissions
        elif self.permission_level == PermissionLevel.RESTRICTED:
            self.can_create_events = False
            self.can_manage_all_events = False
            self.can_create_recurring = False
            self.can_manage_guild_config = False
            self.can_view_analytics = False


class NotificationChannel(BaseDocument):
    """Configuration for notification channels."""
    
    channel_id: str = Field(..., description="Discord channel ID")
    channel_type: NotificationChannelType = Field(..., description="Type of notifications")
    is_active: bool = Field(default=True, description="Whether channel is active")
    
    # Filtering options
    event_types: List[str] = Field(
        default_factory=list,
        description="Event types to notify about (empty = all)"
    )
    mention_roles: List[str] = Field(
        default_factory=list,
        description="Role IDs to mention in notifications"
    )
    
    @field_validator('channel_id')
    @classmethod
    def validate_channel_id(cls, v):
        if not v or not v.isdigit():
            raise ValueError("Channel ID must be a valid Discord snowflake")
        return v
    
    def validate_data(self) -> None:
        """Validate notification channel configuration."""
        # Validate mention role IDs
        for role_id in self.mention_roles:
            if not role_id.isdigit():
                raise ValueError(f"Invalid role ID: {role_id}")


class EventDefaults(BaseDocument):
    """Default settings for new events."""
    
    default_timezone: str = Field(default="UTC", description="Default timezone for events")
    default_duration_minutes: int = Field(
        default=180,
        ge=15,
        le=1440,
        description="Default event duration"
    )
    
    # Poll settings
    date_poll_duration_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Default date poll duration"
    )
    time_poll_duration_hours: int = Field(
        default=12,
        ge=1,
        le=72,
        description="Default time poll duration"
    )
    game_poll_duration_hours: int = Field(
        default=6,
        ge=1,
        le=48,
        description="Default game poll duration"
    )
    
    # Game options
    default_games: List[str] = Field(
        default_factory=list,
        description="Default games to include in polls"
    )
    max_game_options: int = Field(
        default=10,
        ge=3,
        le=25,
        description="Maximum game options in polls"
    )
    
    # RSVP settings
    auto_rsvp_creator: bool = Field(
        default=True,
        description="Automatically RSVP event creator as 'Yes'"
    )
    
    @field_validator('default_timezone')
    @classmethod
    def validate_timezone(cls, v):
        return ValidationMixin.validate_timezone(v)
    
    def validate_data(self) -> None:
        """Validate event defaults."""
        # Sanitize game names
        for i, game in enumerate(self.default_games):
            self.default_games[i] = ValidationMixin.sanitize_text(game, 100)


class FeatureFlags(BaseDocument):
    """Feature flags for enabling/disabling bot features."""
    
    events_enabled: bool = Field(default=True, description="Enable event creation")
    recurring_events_enabled: bool = Field(default=True, description="Enable recurring events")
    game_pings_enabled: bool = Field(default=True, description="Enable game ping system")
    web_dashboard_enabled: bool = Field(default=True, description="Enable web dashboard")
    analytics_enabled: bool = Field(default=True, description="Enable analytics collection")
    
    # Advanced features
    discord_events_integration: bool = Field(
        default=True,
        description="Integrate with Discord scheduled events"
    )
    calendar_export_enabled: bool = Field(
        default=True,
        description="Enable calendar export (.ics files)"
    )
    user_profiles_enabled: bool = Field(
        default=True,
        description="Enable user profile system"
    )
    
    def validate_data(self) -> None:
        """Validate feature flags."""
        # If events are disabled, disable related features
        if not self.events_enabled:
            self.recurring_events_enabled = False
            self.discord_events_integration = False
            self.calendar_export_enabled = False


class GuildStatistics(BaseDocument):
    """Guild-level statistics and metrics."""
    
    total_events_created: int = Field(default=0, ge=0)
    total_events_completed: int = Field(default=0, ge=0)
    total_users_registered: int = Field(default=0, ge=0)
    
    # Activity metrics
    events_this_month: int = Field(default=0, ge=0)
    active_users_this_month: int = Field(default=0, ge=0)
    
    # Popular games
    popular_games: Dict[str, int] = Field(
        default_factory=dict,
        description="Game popularity counts"
    )
    
    # Engagement metrics
    average_attendance_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    average_rsvp_count: float = Field(default=0.0, ge=0.0)
    
    # Last updated
    last_calculated: datetime = Field(default_factory=TimestampMixin.utc_now)
    
    def validate_data(self) -> None:
        """Validate guild statistics."""
        # Ensure completion rate doesn't exceed 100%
        if self.total_events_created > 0:
            completion_rate = self.total_events_completed / self.total_events_created
            if completion_rate > 1.0:
                self.total_events_completed = self.total_events_created
    
    def update_event_created(self) -> None:
        """Update statistics for new event."""
        self.total_events_created += 1
        self.events_this_month += 1
        self.last_calculated = TimestampMixin.utc_now()
    
    def update_event_completed(self, attendance_rate: float, rsvp_count: int) -> None:
        """Update statistics for completed event."""
        self.total_events_completed += 1
        
        # Update running averages
        total_completed = self.total_events_completed
        self.average_attendance_rate = (
            (self.average_attendance_rate * (total_completed - 1) + attendance_rate) /
            total_completed
        )
        self.average_rsvp_count = (
            (self.average_rsvp_count * (total_completed - 1) + rsvp_count) /
            total_completed
        )
        
        self.last_calculated = TimestampMixin.utc_now()
    
    def update_game_popularity(self, game_name: str) -> None:
        """Update game popularity statistics."""
        game_name = ValidationMixin.sanitize_text(game_name, 100)
        self.popular_games[game_name] = self.popular_games.get(game_name, 0) + 1
        self.last_calculated = TimestampMixin.utc_now()


class GuildConfig(BaseDocument, ValidationMixin, TimestampMixin):
    """
    Guild configuration model for server-specific settings.
    
    Manages permissions, channels, defaults, and feature flags for each Discord server.
    """
    
    guild_id: str = Field(..., description="Discord guild ID")
    guild_name: Optional[str] = Field(None, max_length=100, description="Guild name")
    
    # Permission system
    role_mappings: List[RoleMapping] = Field(
        default_factory=list,
        description="Role to permission mappings"
    )
    default_permission_level: PermissionLevel = Field(
        default=PermissionLevel.MEMBER,
        description="Default permission level for users"
    )
    
    # Notification channels
    notification_channels: List[NotificationChannel] = Field(
        default_factory=list,
        description="Configured notification channels"
    )
    
    # Event defaults
    event_defaults: EventDefaults = Field(default_factory=EventDefaults)
    
    # Feature flags
    features: FeatureFlags = Field(default_factory=FeatureFlags)
    
    # Statistics
    statistics: GuildStatistics = Field(default_factory=GuildStatistics)
    
    # Administrative settings
    admin_user_ids: List[str] = Field(
        default_factory=list,
        description="User IDs with admin privileges"
    )
    
    # Backup and maintenance
    last_backup: Optional[datetime] = Field(None, description="Last backup timestamp")
    maintenance_mode: bool = Field(default=False, description="Maintenance mode flag")
    
    @field_validator('guild_id')
    @classmethod
    def validate_guild_id(cls, v):
        return ValidationMixin.validate_guild_id(v)
    
    @field_validator('guild_name')
    @classmethod
    def validate_guild_name(cls, v):
        if v:
            return ValidationMixin.sanitize_text(v, 100)
        return v
    
    def validate_data(self) -> None:
        """Validate guild configuration."""
        # Validate admin user IDs
        for user_id in self.admin_user_ids:
            ValidationMixin.validate_user_id(user_id)
        
        # Ensure unique role mappings
        role_ids = [mapping.role_id for mapping in self.role_mappings]
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("Duplicate role mappings not allowed")
        
        # Ensure unique notification channels per type
        channel_types = {}
        for channel in self.notification_channels:
            if channel.channel_type in channel_types:
                if channel_types[channel.channel_type] != channel.channel_id:
                    # Multiple channels of same type is allowed, just track for validation
                    pass
            channel_types[channel.channel_type] = channel.channel_id
    
    def get_user_permissions(self, user_id: str, user_roles: List[str]) -> RoleMapping:
        """Get effective permissions for a user based on their roles."""
        # Check if user is admin
        if user_id in self.admin_user_ids:
            return RoleMapping(
                role_id="admin",
                permission_level=PermissionLevel.ADMIN,
                can_create_events=True,
                can_manage_own_events=True,
                can_manage_all_events=True,
                can_create_recurring=True,
                can_manage_guild_config=True,
                can_view_analytics=True
            )
        
        # Find highest permission level from user's roles
        highest_mapping = None
        permission_hierarchy = {
            PermissionLevel.RESTRICTED: 0,
            PermissionLevel.MEMBER: 1,
            PermissionLevel.ORGANIZER: 2,
            PermissionLevel.ADMIN: 3
        }
        
        for mapping in self.role_mappings:
            if mapping.role_id in user_roles:
                if (highest_mapping is None or 
                    permission_hierarchy[mapping.permission_level] > 
                    permission_hierarchy[highest_mapping.permission_level]):
                    highest_mapping = mapping
        
        # Return highest mapping or default
        if highest_mapping:
            return highest_mapping
        else:
            return RoleMapping(
                role_id="default",
                permission_level=self.default_permission_level
            )
    
    def add_role_mapping(
        self,
        role_id: str,
        permission_level: PermissionLevel,
        **permissions
    ) -> bool:
        """Add or update role mapping. Returns True if added/updated."""
        # Remove existing mapping for this role
        self.role_mappings = [
            mapping for mapping in self.role_mappings
            if mapping.role_id != role_id
        ]
        
        # Add new mapping
        mapping = RoleMapping(
            role_id=role_id,
            permission_level=permission_level,
            **permissions
        )
        self.role_mappings.append(mapping)
        self.update_timestamp()
        return True
    
    def remove_role_mapping(self, role_id: str) -> bool:
        """Remove role mapping. Returns True if removed."""
        original_count = len(self.role_mappings)
        self.role_mappings = [
            mapping for mapping in self.role_mappings
            if mapping.role_id != role_id
        ]
        
        if len(self.role_mappings) < original_count:
            self.update_timestamp()
            return True
        return False
    
    def get_notification_channel(
        self,
        channel_type: NotificationChannelType
    ) -> Optional[NotificationChannel]:
        """Get notification channel by type."""
        for channel in self.notification_channels:
            if channel.channel_type == channel_type and channel.is_active:
                return channel
        return None
    
    def add_notification_channel(
        self,
        channel_id: str,
        channel_type: NotificationChannelType,
        **options
    ) -> bool:
        """Add notification channel. Returns True if added."""
        # Check if channel already exists
        for channel in self.notification_channels:
            if channel.channel_id == channel_id and channel.channel_type == channel_type:
                return False
        
        channel = NotificationChannel(
            channel_id=channel_id,
            channel_type=channel_type,
            **options
        )
        self.notification_channels.append(channel)
        self.update_timestamp()
        return True
    
    def remove_notification_channel(
        self,
        channel_id: str,
        channel_type: NotificationChannelType = None
    ) -> bool:
        """Remove notification channel(s). Returns True if any removed."""
        original_count = len(self.notification_channels)
        
        if channel_type:
            self.notification_channels = [
                channel for channel in self.notification_channels
                if not (channel.channel_id == channel_id and channel.channel_type == channel_type)
            ]
        else:
            self.notification_channels = [
                channel for channel in self.notification_channels
                if channel.channel_id != channel_id
            ]
        
        if len(self.notification_channels) < original_count:
            self.update_timestamp()
            return True
        return False
    
    def is_feature_enabled(self, feature_name: str) -> bool:
        """Check if a feature is enabled."""
        return getattr(self.features, feature_name, False)
    
    def enable_feature(self, feature_name: str) -> bool:
        """Enable a feature. Returns True if successful."""
        if hasattr(self.features, feature_name):
            setattr(self.features, feature_name, True)
            self.update_timestamp()
            return True
        return False
    
    def disable_feature(self, feature_name: str) -> bool:
        """Disable a feature. Returns True if successful."""
        if hasattr(self.features, feature_name):
            setattr(self.features, feature_name, False)
            self.update_timestamp()
            return True
        return False
    
    def add_admin_user(self, user_id: str) -> bool:
        """Add admin user. Returns True if added."""
        ValidationMixin.validate_user_id(user_id)
        if user_id not in self.admin_user_ids:
            self.admin_user_ids.append(user_id)
            self.update_timestamp()
            return True
        return False
    
    def remove_admin_user(self, user_id: str) -> bool:
        """Remove admin user. Returns True if removed."""
        if user_id in self.admin_user_ids:
            self.admin_user_ids.remove(user_id)
            self.update_timestamp()
            return True
        return False
    
    def enter_maintenance_mode(self) -> None:
        """Enter maintenance mode."""
        self.maintenance_mode = True
        self.update_timestamp()
    
    def exit_maintenance_mode(self) -> None:
        """Exit maintenance mode."""
        self.maintenance_mode = False
        self.update_timestamp()
    
    def record_backup(self) -> None:
        """Record successful backup."""
        self.last_backup = TimestampMixin.utc_now()
        self.update_timestamp()