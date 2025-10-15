"""
Simple event bus system for inter-cog communication.
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

from utils.logging_config import get_logger

logger = get_logger(__name__)


class EventType(Enum):
    """Core event types for the system."""
    
    # System events
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_ERROR = "system_error"
    
    # Event lifecycle events
    EVENT_CREATED = "event_created"
    EVENT_UPDATED = "event_updated"
    EVENT_CANCELLED = "event_cancelled"
    
    # Poll events
    POLL_CREATED = "poll_created"
    POLL_VOTE_CAST = "poll_vote_cast"
    POLL_COMPLETED = "poll_completed"
    POLL_EXPIRED = "poll_expired"
    
    # Event state changes
    EVENT_STATE_CHANGED = "event_state_changed"
    EVENT_SCHEDULED = "event_scheduled"
    
    # User events
    USER_PREFERENCES_UPDATED = "user_preferences_updated"
    USER_GAME_INTEREST_ADDED = "user_game_interest_added"
    USER_GAME_INTEREST_REMOVED = "user_game_interest_removed"
    
    # RSVP events
    EVENT_RSVP_UPDATED = "event_rsvp_updated"
    
    # Game events
    GAME_PING_SENT = "game_ping_sent"
    
    # Notification events
    NOTIFICATION_SCHEDULED = "notification_scheduled"


@dataclass
class Event:
    """Represents an event in the system."""
    
    event_type: EventType
    data: Dict[str, Any]
    guild_id: Optional[str] = None
    user_id: Optional[str] = None


class EventBus:
    """
    Simple event bus for inter-component communication.
    
    Provides basic publish-subscribe pattern for loose coupling between
    different parts of the bot system.
    """
    
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}
    
    def subscribe(self, event_type: EventType, callback: Callable[[Event], Any]) -> None:
        """
        Subscribe to an event type.
        
        Args:
            event_type: The type of event to subscribe to
            callback: Function to call when event occurs
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        
        self._subscribers[event_type].append(callback)
        logger.debug(f"Subscribed to {event_type.value}")
    
    def unsubscribe(self, event_type: EventType, callback: Callable) -> bool:
        """
        Unsubscribe from an event type.
        
        Args:
            event_type: The type of event to unsubscribe from
            callback: The callback function to remove
            
        Returns:
            True if callback was found and removed, False otherwise
        """
        if event_type not in self._subscribers:
            return False
        
        try:
            self._subscribers[event_type].remove(callback)
            logger.debug(f"Unsubscribed from {event_type.value}")
            return True
        except ValueError:
            return False
    
    async def emit(
        self, 
        event_type: EventType, 
        data: Dict[str, Any],
        guild_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> None:
        """
        Emit an event to all subscribers.
        
        Args:
            event_type: Type of event to emit
            data: Event data
            guild_id: Guild ID if event is guild-specific
            user_id: User ID if event is user-specific
        """
        event = Event(
            event_type=event_type,
            data=data,
            guild_id=guild_id,
            user_id=user_id
        )
        
        # Get subscribers for this event type
        subscribers = self._subscribers.get(event_type, [])
        
        if not subscribers:
            return
        
        logger.debug(f"Emitting {event_type.value} to {len(subscribers)} subscribers")
        
        # Call all subscribers
        for callback in subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Error in event callback: {e}", exc_info=True)