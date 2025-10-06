"""
System state manager for handling bot restarts and crashes with state restoration.
"""

import asyncio
import json
import pickle
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import os
import tempfile

from database.manager import DatabaseManager
from core.event_bus import EventBus, EventType, Event
from utils.logging_config import get_logger, LoggerMixin
from utils.exceptions import GameNightBotException


class StateType(str, Enum):
    """Types of state that can be persisted."""
    ACTIVE_POLLS = "ACTIVE_POLLS"
    USER_SESSIONS = "USER_SESSIONS"
    PENDING_NOTIFICATIONS = "PENDING_NOTIFICATIONS"
    ACTIVE_VIEWS = "ACTIVE_VIEWS"
    RECURRING_SCHEDULES = "RECURRING_SCHEDULES"
    SYSTEM_CONFIG = "SYSTEM_CONFIG"
    ERROR_CONTEXTS = "ERROR_CONTEXTS"


@dataclass
class StateSnapshot:
    """Represents a snapshot of system state."""
    state_type: StateType
    state_id: str
    data: Dict[str, Any]
    created_at: float
    expires_at: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StateSnapshot':
        return cls(**data)
    
    def is_expired(self) -> bool:
        """Check if this state snapshot has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


class SystemStateManager(LoggerMixin):
    """
    Manages system state persistence and restoration for crash recovery.
    """
    
    def __init__(self, database: DatabaseManager, event_bus: EventBus):
        self.database = database
        self.event_bus = event_bus
        self._state_snapshots: Dict[str, StateSnapshot] = {}
        self._state_handlers: Dict[StateType, Dict[str, Callable]] = {}
        self._persistence_enabled = True
        self._state_file_path = None
        self._auto_save_interval = 60  # seconds
        self._auto_save_task = None
        
        # Initialize state handlers
        self._initialize_state_handlers()
        
        # Register event listeners
        self._register_event_listeners()
    
    def _initialize_state_handlers(self) -> None:
        """Initialize state save/restore handlers."""
        self._state_handlers = {
            StateType.ACTIVE_POLLS: {
                'save': self._save_active_polls,
                'restore': self._restore_active_polls
            },
            StateType.USER_SESSIONS: {
                'save': self._save_user_sessions,
                'restore': self._restore_user_sessions
            },
            StateType.PENDING_NOTIFICATIONS: {
                'save': self._save_pending_notifications,
                'restore': self._restore_pending_notifications
            },
            StateType.ACTIVE_VIEWS: {
                'save': self._save_active_views,
                'restore': self._restore_active_views
            },
            StateType.RECURRING_SCHEDULES: {
                'save': self._save_recurring_schedules,
                'restore': self._restore_recurring_schedules
            },
            StateType.SYSTEM_CONFIG: {
                'save': self._save_system_config,
                'restore': self._restore_system_config
            },
            StateType.ERROR_CONTEXTS: {
                'save': self._save_error_contexts,
                'restore': self._restore_error_contexts
            }
        }
    
    def _register_event_listeners(self) -> None:
        """Register event bus listeners."""
        self.event_bus.subscribe(EventType.SYSTEM_STARTUP, self._on_system_startup)
        self.event_bus.subscribe(EventType.SYSTEM_SHUTDOWN, self._on_system_shutdown)
        self.event_bus.subscribe(EventType.POLL_CREATED, self._on_poll_created)
        self.event_bus.subscribe(EventType.POLL_COMPLETED, self._on_poll_completed)
        self.event_bus.subscribe(EventType.EVENT_STATE_CHANGED, self._on_event_state_changed)
    
    async def start_state_management(
        self, 
        state_file_path: Optional[str] = None,
        auto_save_interval: int = 60
    ) -> None:
        """
        Start state management with automatic persistence.
        
        Args:
            state_file_path: Path to state file (optional)
            auto_save_interval: Auto-save interval in seconds
        """
        if state_file_path:
            self._state_file_path = state_file_path
        else:
            # Use temporary file
            temp_dir = tempfile.gettempdir()
            self._state_file_path = os.path.join(temp_dir, "gamenight_bot_state.json")
        
        self._auto_save_interval = auto_save_interval
        
        # Start auto-save task
        if self._auto_save_task is None:
            self._auto_save_task = asyncio.create_task(self._auto_save_loop())
        
        self.logger.info(
            "State management started",
            state_file_path=self._state_file_path,
            auto_save_interval=auto_save_interval
        )
    
    async def stop_state_management(self) -> None:
        """Stop state management and save final state."""
        if self._auto_save_task:
            self._auto_save_task.cancel()
            try:
                await self._auto_save_task
            except asyncio.CancelledError:
                pass
            self._auto_save_task = None
        
        # Save final state
        await self.save_all_state()
        
        self.logger.info("State management stopped")
    
    async def save_state(
        self, 
        state_type: StateType,
        state_id: str,
        data: Dict[str, Any],
        expires_in_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Save a state snapshot.
        
        Args:
            state_type: Type of state
            state_id: Unique identifier for this state
            data: State data to save
            expires_in_seconds: Expiration time in seconds
            metadata: Additional metadata
        """
        expires_at = None
        if expires_in_seconds:
            expires_at = time.time() + expires_in_seconds
        
        snapshot = StateSnapshot(
            state_type=state_type,
            state_id=state_id,
            data=data,
            created_at=time.time(),
            expires_at=expires_at,
            metadata=metadata or {}
        )
        
        self._state_snapshots[f"{state_type.value}:{state_id}"] = snapshot
        
        # Also save to database for persistence across restarts
        if self._persistence_enabled:
            try:
                await self.database.update_one(
                    "system_state",
                    {"state_key": f"{state_type.value}:{state_id}"},
                    {"$set": {
                        "state_type": state_type.value,
                        "state_id": state_id,
                        "data": data,
                        "created_at": snapshot.created_at,
                        "expires_at": expires_at,
                        "metadata": metadata or {}
                    }},
                    upsert=True
                )
            except Exception as e:
                self.logger.error(
                    "Failed to persist state to database",
                    state_type=state_type.value,
                    state_id=state_id,
                    error=str(e)
                )
        
        self.logger.debug(
            "State saved",
            state_type=state_type.value,
            state_id=state_id,
            expires_at=expires_at
        )
    
    async def restore_state(
        self, 
        state_type: StateType,
        state_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Restore a state snapshot.
        
        Args:
            state_type: Type of state
            state_id: State identifier
            
        Returns:
            State data if found and not expired, None otherwise
        """
        state_key = f"{state_type.value}:{state_id}"
        
        # Check in-memory cache first
        if state_key in self._state_snapshots:
            snapshot = self._state_snapshots[state_key]
            if not snapshot.is_expired():
                return snapshot.data
            else:
                # Remove expired snapshot
                del self._state_snapshots[state_key]
        
        # Check database
        try:
            state_doc = await self.database.find_one(
                "system_state",
                {"state_key": state_key}
            )
            
            if state_doc:
                snapshot = StateSnapshot(
                    state_type=StateType(state_doc['state_type']),
                    state_id=state_doc['state_id'],
                    data=state_doc['data'],
                    created_at=state_doc['created_at'],
                    expires_at=state_doc.get('expires_at'),
                    metadata=state_doc.get('metadata', {})
                )
                
                if not snapshot.is_expired():
                    # Cache it
                    self._state_snapshots[state_key] = snapshot
                    return snapshot.data
                else:
                    # Remove expired state from database
                    await self.database.delete_one(
                        "system_state",
                        {"state_key": state_key}
                    )
        
        except Exception as e:
            self.logger.error(
                "Failed to restore state from database",
                state_type=state_type.value,
                state_id=state_id,
                error=str(e)
            )
        
        return None
    
    async def delete_state(self, state_type: StateType, state_id: str) -> bool:
        """
        Delete a state snapshot.
        
        Args:
            state_type: Type of state
            state_id: State identifier
            
        Returns:
            True if state was deleted, False if not found
        """
        state_key = f"{state_type.value}:{state_id}"
        
        # Remove from memory
        deleted_from_memory = state_key in self._state_snapshots
        if deleted_from_memory:
            del self._state_snapshots[state_key]
        
        # Remove from database
        deleted_from_db = False
        try:
            result = await self.database.delete_one(
                "system_state",
                {"state_key": state_key}
            )
            deleted_from_db = result
        except Exception as e:
            self.logger.error(
                "Failed to delete state from database",
                state_type=state_type.value,
                state_id=state_id,
                error=str(e)
            )
        
        if deleted_from_memory or deleted_from_db:
            self.logger.debug(
                "State deleted",
                state_type=state_type.value,
                state_id=state_id
            )
            return True
        
        return False
    
    async def save_all_state(self) -> None:
        """Save all current state using registered handlers."""
        self.logger.info("Saving all system state")
        
        for state_type, handlers in self._state_handlers.items():
            save_handler = handlers.get('save')
            if save_handler:
                try:
                    await save_handler()
                except Exception as e:
                    self.logger.error(
                        "Failed to save state",
                        state_type=state_type.value,
                        error=str(e)
                    )
        
        # Also save to file for additional persistence
        await self._save_to_file()
    
    async def restore_all_state(self) -> None:
        """Restore all state using registered handlers."""
        self.logger.info("Restoring all system state")
        
        # First try to restore from file
        await self._restore_from_file()
        
        # Then restore from database and run handlers
        for state_type, handlers in self._state_handlers.items():
            restore_handler = handlers.get('restore')
            if restore_handler:
                try:
                    await restore_handler()
                except Exception as e:
                    self.logger.error(
                        "Failed to restore state",
                        state_type=state_type.value,
                        error=str(e)
                    )
    
    async def cleanup_expired_state(self) -> int:
        """
        Clean up expired state snapshots.
        
        Returns:
            Number of expired snapshots cleaned up
        """
        current_time = time.time()
        expired_keys = []
        
        # Check in-memory snapshots
        for key, snapshot in self._state_snapshots.items():
            if snapshot.is_expired():
                expired_keys.append(key)
        
        # Remove expired snapshots
        for key in expired_keys:
            del self._state_snapshots[key]
        
        # Clean up database
        try:
            result = await self.database.database.system_state.delete_many({
                "expires_at": {"$lt": current_time, "$ne": None}
            })
            db_deleted = result.deleted_count if hasattr(result, 'deleted_count') else 0
        except Exception as e:
            self.logger.error(
                "Failed to cleanup expired state from database",
                error=str(e)
            )
            db_deleted = 0
        
        total_cleaned = len(expired_keys) + db_deleted
        
        if total_cleaned > 0:
            self.logger.info(
                "Cleaned up expired state",
                memory_cleaned=len(expired_keys),
                database_cleaned=db_deleted,
                total_cleaned=total_cleaned
            )
        
        return total_cleaned
    
    async def get_state_summary(self) -> Dict[str, Any]:
        """Get a summary of current state."""
        summary = {
            'total_snapshots': len(self._state_snapshots),
            'by_type': {},
            'expired_count': 0,
            'oldest_snapshot': None,
            'newest_snapshot': None
        }
        
        oldest_time = float('inf')
        newest_time = 0
        
        for snapshot in self._state_snapshots.values():
            state_type = snapshot.state_type.value
            
            if state_type not in summary['by_type']:
                summary['by_type'][state_type] = 0
            summary['by_type'][state_type] += 1
            
            if snapshot.is_expired():
                summary['expired_count'] += 1
            
            if snapshot.created_at < oldest_time:
                oldest_time = snapshot.created_at
                summary['oldest_snapshot'] = snapshot.created_at
            
            if snapshot.created_at > newest_time:
                newest_time = snapshot.created_at
                summary['newest_snapshot'] = snapshot.created_at
        
        return summary
    
    # Event handlers
    
    async def _on_system_startup(self, event: Event) -> None:
        """Handle system startup."""
        await self.restore_all_state()
    
    async def _on_system_shutdown(self, event: Event) -> None:
        """Handle system shutdown."""
        await self.save_all_state()
    
    async def _on_poll_created(self, event: Event) -> None:
        """Handle poll creation."""
        poll_data = event.data
        event_id = poll_data.get('event_id')
        poll_type = poll_data.get('poll_type')
        
        if event_id and poll_type:
            await self.save_state(
                StateType.ACTIVE_POLLS,
                f"{event_id}_{poll_type}",
                poll_data,
                expires_in_seconds=86400  # 24 hours
            )
    
    async def _on_poll_completed(self, event: Event) -> None:
        """Handle poll completion."""
        poll_data = event.data
        event_id = poll_data.get('event_id')
        poll_type = poll_data.get('poll_type')
        
        if event_id and poll_type:
            await self.delete_state(
                StateType.ACTIVE_POLLS,
                f"{event_id}_{poll_type}"
            )
    
    async def _on_event_state_changed(self, event: Event) -> None:
        """Handle event state changes."""
        event_data = event.data
        event_id = event_data.get('event_id')
        
        if event_id:
            # Save current event state
            await self.save_state(
                StateType.ACTIVE_POLLS,
                f"event_state_{event_id}",
                event_data,
                expires_in_seconds=86400  # 24 hours
            )
    
    # Auto-save loop
    
    async def _auto_save_loop(self) -> None:
        """Automatic state saving loop."""
        while True:
            try:
                await asyncio.sleep(self._auto_save_interval)
                await self.save_all_state()
                await self.cleanup_expired_state()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    "Error in auto-save loop",
                    error=str(e)
                )
    
    # File persistence
    
    async def _save_to_file(self) -> None:
        """Save state to file."""
        if not self._state_file_path:
            return
        
        try:
            state_data = {
                'snapshots': {
                    key: snapshot.to_dict() 
                    for key, snapshot in self._state_snapshots.items()
                },
                'saved_at': time.time()
            }
            
            # Write to temporary file first, then rename for atomicity
            temp_path = f"{self._state_file_path}.tmp"
            
            with open(temp_path, 'w') as f:
                json.dump(state_data, f, indent=2)
            
            os.rename(temp_path, self._state_file_path)
            
            self.logger.debug(
                "State saved to file",
                file_path=self._state_file_path,
                snapshot_count=len(self._state_snapshots)
            )
            
        except Exception as e:
            self.logger.error(
                "Failed to save state to file",
                file_path=self._state_file_path,
                error=str(e)
            )
    
    async def _restore_from_file(self) -> None:
        """Restore state from file."""
        if not self._state_file_path or not os.path.exists(self._state_file_path):
            return
        
        try:
            with open(self._state_file_path, 'r') as f:
                state_data = json.load(f)
            
            snapshots_data = state_data.get('snapshots', {})
            restored_count = 0
            
            for key, snapshot_data in snapshots_data.items():
                try:
                    snapshot = StateSnapshot.from_dict(snapshot_data)
                    if not snapshot.is_expired():
                        self._state_snapshots[key] = snapshot
                        restored_count += 1
                except Exception as e:
                    self.logger.warning(
                        "Failed to restore snapshot from file",
                        key=key,
                        error=str(e)
                    )
            
            self.logger.info(
                "State restored from file",
                file_path=self._state_file_path,
                restored_count=restored_count
            )
            
        except Exception as e:
            self.logger.error(
                "Failed to restore state from file",
                file_path=self._state_file_path,
                error=str(e)
            )
    
    # State-specific save/restore handlers
    
    async def _save_active_polls(self) -> None:
        """Save active polls state."""
        try:
            # Get active events with polls
            active_events = await self.database.find_many(
                "events",
                {
                    "state": {"$in": ["DATE_POLLING", "TIME_POLLING", "GAME_POLLING"]},
                    "$or": [
                        {"polls.date_poll.is_active": True},
                        {"polls.time_poll.is_active": True},
                        {"polls.game_poll.is_active": True}
                    ]
                }
            )
            
            for event in active_events:
                event_id = str(event['_id'])
                await self.save_state(
                    StateType.ACTIVE_POLLS,
                    f"event_{event_id}",
                    event,
                    expires_in_seconds=86400  # 24 hours
                )
            
        except Exception as e:
            self.logger.error(
                "Failed to save active polls state",
                error=str(e)
            )
    
    async def _restore_active_polls(self) -> None:
        """Restore active polls state."""
        # This will be handled by the events cog when it starts up
        # and checks for active polls in the database
        pass
    
    async def _save_user_sessions(self) -> None:
        """Save user sessions state."""
        # Implementation depends on how user sessions are managed
        pass
    
    async def _restore_user_sessions(self) -> None:
        """Restore user sessions state."""
        # Implementation depends on how user sessions are managed
        pass
    
    async def _save_pending_notifications(self) -> None:
        """Save pending notifications state."""
        try:
            # Get pending notifications
            pending_notifications = await self.database.find_many(
                "notifications",
                {
                    "processed": False,
                    "scheduled_for": {"$gte": datetime.now()}
                }
            )
            
            if pending_notifications:
                await self.save_state(
                    StateType.PENDING_NOTIFICATIONS,
                    "all_pending",
                    {"notifications": pending_notifications},
                    expires_in_seconds=86400  # 24 hours
                )
            
        except Exception as e:
            self.logger.error(
                "Failed to save pending notifications state",
                error=str(e)
            )
    
    async def _restore_pending_notifications(self) -> None:
        """Restore pending notifications state."""
        # Notifications will be restored by the notification system
        # when it starts up and checks the database
        pass
    
    async def _save_active_views(self) -> None:
        """Save active Discord views state."""
        # This would save information about active Discord UI views
        # so they can be recreated after a restart
        pass
    
    async def _restore_active_views(self) -> None:
        """Restore active Discord views."""
        # This would recreate Discord UI views that were active
        # before the restart
        pass
    
    async def _save_recurring_schedules(self) -> None:
        """Save recurring schedules state."""
        try:
            # Get active recurring schedules
            active_schedules = await self.database.find_many(
                "recurring_schedules",
                {"status.is_active": True}
            )
            
            if active_schedules:
                await self.save_state(
                    StateType.RECURRING_SCHEDULES,
                    "all_active",
                    {"schedules": active_schedules},
                    expires_in_seconds=86400  # 24 hours
                )
            
        except Exception as e:
            self.logger.error(
                "Failed to save recurring schedules state",
                error=str(e)
            )
    
    async def _restore_recurring_schedules(self) -> None:
        """Restore recurring schedules state."""
        # Recurring schedules will be restored by the recurring cog
        # when it starts up and checks the database
        pass
    
    async def _save_system_config(self) -> None:
        """Save system configuration state."""
        try:
            # Get guild configurations
            guild_configs = await self.database.find_many("guild_configs", {})
            
            if guild_configs:
                await self.save_state(
                    StateType.SYSTEM_CONFIG,
                    "guild_configs",
                    {"configs": guild_configs}
                )
            
        except Exception as e:
            self.logger.error(
                "Failed to save system config state",
                error=str(e)
            )
    
    async def _restore_system_config(self) -> None:
        """Restore system configuration state."""
        # System config is already in the database
        pass
    
    async def _save_error_contexts(self) -> None:
        """Save error contexts for recovery."""
        # This would save information about errors that occurred
        # so recovery can continue after restart
        pass
    
    async def _restore_error_contexts(self) -> None:
        """Restore error contexts."""
        # This would restore error recovery contexts
        pass