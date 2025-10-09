"""
Data models package for the Discord Game Night Bot.

This package contains all data models, repositories, and database utilities.
"""

# Base classes
from .base import BaseDocument, ValidationMixin, TimestampMixin, PyObjectId

# Event models
from .event import (
    Event, EventState, Poll, RSVPResponse, RSVPStatus
)

# User models
from .user import (
    User, GameInterest
)

# Recurring schedule models
from .recurring import (
    RecurringSchedule, ScheduleStatus
)

# Guild configuration models
from .guild import (
    GuildConfig
)

# Notification models
from .notification import (
    Notification, NotificationType, NotificationStatus
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
    'Event', 'EventState', 'Poll', 'RSVPResponse', 'RSVPStatus',
    
    # User models
    'User', 'GameInterest',
    
    # Recurring schedule models
    'RecurringSchedule', 'ScheduleStatus',
    
    # Guild configuration models
    'GuildConfig',
    
    # Notification models
    'Notification', 'NotificationType', 'NotificationStatus',
    
    # Repositories
    'BaseRepository', 'EventRepository', 'UserRepository',
    'RecurringScheduleRepository', 'GuildConfigRepository', 'RepositoryManager'
]