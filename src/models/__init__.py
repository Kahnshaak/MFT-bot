"""
Data models package for the Discord Game Night Bot.

This package contains all data models, repositories, and database utilities.
"""

# Base classes
from .base import BaseDocument, ValidationMixin, TimestampMixin, PyObjectId

# Event models
from .event import (
    Event, EventState, EventSchedule, Poll, PollOption, PollType,
    RSVPResponse, RSVPStatus
)

# User models
from .user import (
    User, UserStatistics, GameInterest, NotificationPreferences,
    AvailabilitySlot, NotificationChannel, NotificationTiming, DayOfWeek
)

# Recurring schedule models
from .recurring import (
    RecurringSchedule, ScheduleTrigger, EventTemplate, ExecutionHistory,
    TriggerType, ScheduleStatus, ExecutionStatus
)

# Guild configuration models
from .guild import (
    GuildConfig, RoleMapping, NotificationChannel as GuildNotificationChannel,
    EventDefaults, FeatureFlags, GuildStatistics,
    PermissionLevel, NotificationChannelType
)

# Repositories
from .repositories import (
    BaseRepository, EventRepository, UserRepository,
    RecurringScheduleRepository, GuildConfigRepository, RepositoryManager
)

__all__ = [
    # Base classes
    'BaseDocument', 'ValidationMixin', 'TimestampMixin', 'PyObjectId',
    
    # Event models
    'Event', 'EventState', 'EventSchedule', 'Poll', 'PollOption', 'PollType',
    'RSVPResponse', 'RSVPStatus',
    
    # User models
    'User', 'UserStatistics', 'GameInterest', 'NotificationPreferences',
    'AvailabilitySlot', 'NotificationChannel', 'NotificationTiming', 'DayOfWeek',
    
    # Recurring schedule models
    'RecurringSchedule', 'ScheduleTrigger', 'EventTemplate', 'ExecutionHistory',
    'TriggerType', 'ScheduleStatus', 'ExecutionStatus',
    
    # Guild configuration models
    'GuildConfig', 'RoleMapping', 'GuildNotificationChannel',
    'EventDefaults', 'FeatureFlags', 'GuildStatistics',
    'PermissionLevel', 'NotificationChannelType',
    
    # Repositories
    'BaseRepository', 'EventRepository', 'UserRepository',
    'RecurringScheduleRepository', 'GuildConfigRepository', 'RepositoryManager'
]