"""
Event bus system for inter-cog communication with typed event handling.
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum

from utils.logging_config import get_logger, LoggerMixin
from utils.exceptions import GameNightBotException, ErrorCode

logger = get_logger(__name__)


class EventType(Enum):
    """Enumeration of all event types in the system."""
    
    # Event lifecycle events
    EVENT_CREATED = "event_created"
    EVENT_UPDATED = "event_updated"
    EVENT_CANCELLED = "event_cancelled"
    EVENT_COMPLETED = "event_completed"
    EVENT_STATE_CHANGED = "event_state_changed"
    
    # Poll events
    POLL_CREATED = "poll_created"
    POLL_VOTE_CAST = "poll_vote_cast"
    POLL_COMPLETED = "poll_completed"
    POLL_EXPIRED = "poll_expired"
    POLL_UPDATED = "poll_updated"
    
    # User events
    USER_JOINED_GUILD = "user_joined_guild"
    USER_LEFT_GUILD = "user_left_guild"
    USER_PREFERENCES_UPDATED = "user_preferences_updated"
    USER_GAME_INTEREST_ADDED = "user_game_interest_added"
    USER_GAME_INTEREST_REMOVED = "user_game_interest_removed"
    
    # Notification events
    NOTIFICATION_SCHEDULED = "notification_scheduled"
    NOTIFICATION_SENT = "notification_sent"
    NOTIFICATION_FAILED = "notification_failed"
    
    # System events
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    HEALTH_CHECK_FAILED = "health_check_failed"
    ERROR_OCCURRED = "error_occurred"


@dataclass
class Event:
    """Represents an event in the system."""
    
    event_type: EventType
    data: Dict[str, Any]
    source: Optional[str] = None
    guild_id: Optional[str] = None
    user_id: Optional[str] = None
    timestamp: Optional[float] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            import time
            self.timestamp = time.time()


class EventBus(LoggerMixin):
    """
    Central event bus for inter-component communication.
    
    Provides a publish-subscribe pattern for loose coupling between
    different parts of the bot system.
    """
    
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._middleware: List[Callable] = []
        self._event_history: List[Event] = []
        self._max_history_size = 1000
        self._processing_lock = asyncio.Lock()
    
    def subscribe(
        self, 
        event_type: EventType, 
        callback: Callable[[Event], Any],
        priority: int = 0
    ) -> None:
        """
        Subscribe to an event type.
        
        Args:
            event_type: The type of event to subscribe to
            callback: Async function to call when event occurs
            priority: Priority for callback execution (higher = earlier)
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        
        # Insert callback based on priority
        inserted = False
        for i, (existing_callback, existing_priority) in enumerate(self._subscribers[event_type]):
            if priority > existing_priority:
                self._subscribers[event_type].insert(i, (callback, priority))
                inserted = True
                break
        
        if not inserted:
            self._subscribers[event_type].append((callback, priority))
        
        self.logger.debug(
            "Subscribed to event",
            event_type=event_type.value,
            callback=callback.__name__,
            priority=priority
        )
    
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
        
        original_length = len(self._subscribers[event_type])
        self._subscribers[event_type] = [
            (cb, priority) for cb, priority in self._subscribers[event_type]
            if cb != callback
        ]
        
        removed = len(self._subscribers[event_type]) < original_length
        if removed:
            self.logger.debug(
                "Unsubscribed from event",
                event_type=event_type.value,
                callback=callback.__name__
            )
        
        return removed
    
    def add_middleware(self, middleware: Callable[[Event], Event]) -> None:
        """
        Add middleware to process events before they're dispatched.
        
        Args:
            middleware: Function that takes an Event and returns an Event
        """
        self._middleware.append(middleware)
        self.logger.debug("Added middleware", middleware=middleware.__name__)
    
    async def emit(
        self, 
        event_type: EventType, 
        data: Dict[str, Any],
        source: Optional[str] = None,
        guild_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> None:
        """
        Emit an event to all subscribers.
        
        Args:
            event_type: Type of event to emit
            data: Event data
            source: Source component that emitted the event
            guild_id: Guild ID if event is guild-specific
            user_id: User ID if event is user-specific
        """
        event = Event(
            event_type=event_type,
            data=data,
            source=source,
            guild_id=guild_id,
            user_id=user_id
        )
        
        # Process through middleware
        for middleware in self._middleware:
            try:
                if asyncio.iscoroutinefunction(middleware):
                    event = await middleware(event)
                else:
                    event = middleware(event)
            except Exception as e:
                self.logger.error(
                    "Middleware error",
                    middleware=middleware.__name__,
                    error=str(e)
                )
                # Emit error event for middleware failures
                await self._emit_error_event(e, middleware.__name__, event)
        
        # Add to history
        self._add_to_history(event)
        
        # Get subscribers for this event type
        subscribers = self._subscribers.get(event_type, [])
        
        if not subscribers:
            self.logger.debug(
                "No subscribers for event",
                event_type=event_type.value
            )
            return
        
        self.logger.debug(
            "Emitting event",
            event_type=event_type.value,
            subscriber_count=len(subscribers),
            source=source,
            guild_id=guild_id
        )
        
        # Process subscribers concurrently but with error isolation
        async with self._processing_lock:
            tasks = []
            for callback, priority in subscribers:
                task = asyncio.create_task(
                    self._safe_callback_execution(callback, event)
                )
                tasks.append(task)
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _safe_callback_execution(self, callback: Callable, event: Event) -> None:
        """
        Execute a callback safely with error handling.
        
        Args:
            callback: The callback function to execute
            event: The event to pass to the callback
        """
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(event)
            else:
                callback(event)
        except Exception as e:
            self.logger.error(
                "Event callback error",
                callback=callback.__name__,
                event_type=event.event_type.value,
                error=str(e),
                exc_info=True
            )
            
            # Emit error event (avoid recursion by calling _emit_error_event directly)
            await self._emit_error_event(e, callback.__name__, event)
    
    def _add_to_history(self, event: Event) -> None:
        """Add event to history with size management."""
        self._event_history.append(event)
        
        # Trim history if it gets too large
        if len(self._event_history) > self._max_history_size:
            self._event_history = self._event_history[-self._max_history_size:]
    
    async def _emit_error_event(self, error: Exception, source_name: str, original_event: Event) -> None:
        """
        Emit an error event without going through middleware to avoid recursion.
        
        Args:
            error: The exception that occurred
            source_name: Name of the component that caused the error
            original_event: The original event being processed
        """
        error_event = Event(
            event_type=EventType.ERROR_OCCURRED,
            data={
                "error_type": type(error).__name__,
                "error_message": str(error),
                "source_name": source_name,
                "original_event_type": original_event.event_type.value
            },
            source="event_bus",
            guild_id=original_event.guild_id,
            user_id=original_event.user_id
        )
        
        # Add to history
        self._add_to_history(error_event)
        
        # Get subscribers for error events
        subscribers = self._subscribers.get(EventType.ERROR_OCCURRED, [])
        
        if subscribers:
            # Process subscribers directly without middleware to avoid recursion
            tasks = []
            for callback, priority in subscribers:
                task = asyncio.create_task(
                    self._safe_callback_execution(callback, error_event)
                )
                tasks.append(task)
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    def get_recent_events(
        self, 
        event_type: Optional[EventType] = None,
        guild_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Event]:
        """
        Get recent events from history.
        
        Args:
            event_type: Filter by event type
            guild_id: Filter by guild ID
            limit: Maximum number of events to return
            
        Returns:
            List of recent events matching criteria
        """
        events = self._event_history
        
        # Apply filters
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        
        if guild_id:
            events = [e for e in events if e.guild_id == guild_id]
        
        # Return most recent events
        return events[-limit:] if limit else events
    
    def get_subscriber_count(self, event_type: EventType) -> int:
        """Get the number of subscribers for an event type."""
        return len(self._subscribers.get(event_type, []))
    
    def get_all_event_types(self) -> Set[EventType]:
        """Get all event types that have subscribers."""
        return set(self._subscribers.keys())
    
    async def wait_for_event(
        self, 
        event_type: EventType,
        timeout: Optional[float] = None,
        condition: Optional[Callable[[Event], bool]] = None
    ) -> Optional[Event]:
        """
        Wait for a specific event to occur.
        
        Args:
            event_type: Type of event to wait for
            timeout: Maximum time to wait in seconds
            condition: Optional condition function to filter events
            
        Returns:
            The event if it occurs within timeout, None otherwise
        """
        future = asyncio.Future()
        
        def callback(event: Event):
            if condition is None or condition(event):
                if not future.done():
                    future.set_result(event)
        
        # Subscribe temporarily
        self.subscribe(event_type, callback, priority=1000)  # High priority
        
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            # Clean up subscription
            self.unsubscribe(event_type, callback)