"""
Event recovery manager for handling partial event creation failures.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from enum import Enum
from dataclasses import dataclass, asdict

from database.manager import DatabaseManager
from core.event_bus import EventBus, EventType
from utils.logging_config import get_logger, LoggerMixin
from utils.exceptions import (
    EventError, EventInvalidStateError, GameNightBotException,
    ErrorCode
)


class EventRecoveryType(str, Enum):
    """Types of event recovery operations."""
    PARTIAL_CREATION_FAILURE = "partial_creation_failure"
    POLL_CREATION_FAILURE = "poll_creation_failure"
    DISCORD_EVENT_FAILURE = "discord_event_failure"
    NOTIFICATION_FAILURE = "notification_failure"
    STATE_CORRUPTION = "state_corruption"
    DATA_INCONSISTENCY = "data_inconsistency"


class RecoveryAction(str, Enum):
    """Actions that can be taken during recovery."""
    RETRY_OPERATION = "retry_operation"
    ROLLBACK_CHANGES = "rollback_changes"
    MANUAL_INTERVENTION = "manual_intervention"
    PARTIAL_RECOVERY = "partial_recovery"
    MARK_FAILED = "mark_failed"


@dataclass
class EventRecoveryContext:
    """Context information for event recovery."""
    event_id: str
    recovery_type: EventRecoveryType
    failed_operation: str
    original_data: Dict[str, Any]
    partial_data: Dict[str, Any]
    error_message: str
    timestamp: datetime
    retry_count: int = 0
    max_retries: int = 3
    recovery_actions: List[RecoveryAction] = None
    
    def __post_init__(self):
        if self.recovery_actions is None:
            self.recovery_actions = []
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EventRecoveryManager(LoggerMixin):
    """
    Manager for recovering from partial event creation failures.
    """
    
    def __init__(self, database: DatabaseManager, event_bus: EventBus):
        self.database = database
        self.event_bus = event_bus
        self._recovery_contexts: Dict[str, EventRecoveryContext] = {}
        self._recovery_handlers: Dict[EventRecoveryType, callable] = {}
        self._recovery_queue: List[EventRecoveryContext] = []
        self._processing_recovery = False
        
        # Register default recovery handlers
        self._register_default_handlers()
    
    def _register_default_handlers(self) -> None:
        """Register default recovery handlers."""
        self._recovery_handlers[EventRecoveryType.PARTIAL_CREATION_FAILURE] = self._handle_partial_creation_failure
        self._recovery_handlers[EventRecoveryType.POLL_CREATION_FAILURE] = self._handle_poll_creation_failure
        self._recovery_handlers[EventRecoveryType.DISCORD_EVENT_FAILURE] = self._handle_discord_event_failure
        self._recovery_handlers[EventRecoveryType.NOTIFICATION_FAILURE] = self._handle_notification_failure
        self._recovery_handlers[EventRecoveryType.STATE_CORRUPTION] = self._handle_state_corruption
        self._recovery_handlers[EventRecoveryType.DATA_INCONSISTENCY] = self._handle_data_inconsistency
    
    async def report_event_failure(
        self,
        event_id: str,
        recovery_type: EventRecoveryType,
        failed_operation: str,
        original_data: Dict[str, Any],
        partial_data: Dict[str, Any],
        error: Exception
    ) -> bool:
        """
        Report an event failure and initiate recovery.
        
        Args:
            event_id: ID of the event that failed
            recovery_type: Type of recovery needed
            failed_operation: Operation that failed
            original_data: Original data before failure
            partial_data: Partial data that was created
            error: The error that occurred
            
        Returns:
            True if recovery was initiated successfully
        """
        try:
            # Create recovery context
            recovery_context = EventRecoveryContext(
                event_id=event_id,
                recovery_type=recovery_type,
                failed_operation=failed_operation,
                original_data=original_data,
                partial_data=partial_data,
                error_message=str(error),
                timestamp=datetime.now()
            )
            
            # Store recovery context
            self._recovery_contexts[event_id] = recovery_context
            
            # Save to database for persistence
            await self.database.insert_one(
                "event_recovery_contexts",
                recovery_context.to_dict()
            )
            
            # Add to recovery queue
            self._recovery_queue.append(recovery_context)
            
            # Start recovery processing if not already running
            if not self._processing_recovery:
                asyncio.create_task(self._process_recovery_queue())
            
            self.logger.error(
                "Event failure reported for recovery",
                event_id=event_id,
                recovery_type=recovery_type.value,
                failed_operation=failed_operation,
                error=str(error)
            )
            
            # Emit event for monitoring
            await self.event_bus.emit(
                EventType.ERROR_OCCURRED,
                {
                    "type": "event_recovery_initiated",
                    "event_id": event_id,
                    "recovery_type": recovery_type.value,
                    "failed_operation": failed_operation,
                    "error": str(error)
                }
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to report event failure",
                event_id=event_id,
                error=str(e)
            )
            return False
    
    async def _process_recovery_queue(self) -> None:
        """Process the recovery queue."""
        self._processing_recovery = True
        
        try:
            while self._recovery_queue:
                recovery_context = self._recovery_queue.pop(0)
                
                try:
                    await self._attempt_recovery(recovery_context)
                except Exception as e:
                    self.logger.error(
                        "Error processing recovery",
                        event_id=recovery_context.event_id,
                        error=str(e)
                    )
                
                # Small delay between recovery attempts
                await asyncio.sleep(1)
        
        finally:
            self._processing_recovery = False
    
    async def _attempt_recovery(self, recovery_context: EventRecoveryContext) -> bool:
        """
        Attempt to recover from an event failure.
        
        Args:
            recovery_context: Recovery context information
            
        Returns:
            True if recovery was successful
        """
        handler = self._recovery_handlers.get(recovery_context.recovery_type)
        if not handler:
            self.logger.error(
                "No recovery handler found",
                recovery_type=recovery_context.recovery_type.value
            )
            return False
        
        try:
            success = await handler(recovery_context)
            
            if success:
                self.logger.info(
                    "Event recovery successful",
                    event_id=recovery_context.event_id,
                    recovery_type=recovery_context.recovery_type.value
                )
                
                # Remove from active contexts
                self._recovery_contexts.pop(recovery_context.event_id, None)
                
                # Mark as resolved in database
                await self.database.update_one(
                    "event_recovery_contexts",
                    {"event_id": recovery_context.event_id},
                    {"$set": {"resolved": True, "resolved_at": datetime.now()}}
                )
                
                # Emit success event
                await self.event_bus.emit(
                    EventType.ERROR_OCCURRED,
                    {
                        "type": "event_recovery_successful",
                        "event_id": recovery_context.event_id,
                        "recovery_type": recovery_context.recovery_type.value
                    }
                )
            else:
                # Increment retry count
                recovery_context.retry_count += 1
                
                if recovery_context.retry_count < recovery_context.max_retries:
                    # Re-queue for retry
                    self._recovery_queue.append(recovery_context)
                    
                    self.logger.warning(
                        "Event recovery failed, will retry",
                        event_id=recovery_context.event_id,
                        retry_count=recovery_context.retry_count,
                        max_retries=recovery_context.max_retries
                    )
                else:
                    # Max retries reached, mark for manual intervention
                    await self._mark_for_manual_intervention(recovery_context)
            
            return success
            
        except Exception as e:
            self.logger.error(
                "Recovery handler failed",
                event_id=recovery_context.event_id,
                recovery_type=recovery_context.recovery_type.value,
                error=str(e)
            )
            return False
    
    async def _mark_for_manual_intervention(self, recovery_context: EventRecoveryContext) -> None:
        """Mark an event for manual intervention."""
        try:
            # Update recovery context
            recovery_context.recovery_actions.append(RecoveryAction.MANUAL_INTERVENTION)
            
            # Save to manual intervention collection
            await self.database.insert_one(
                "manual_interventions",
                {
                    "event_id": recovery_context.event_id,
                    "recovery_type": recovery_context.recovery_type.value,
                    "failed_operation": recovery_context.failed_operation,
                    "original_data": recovery_context.original_data,
                    "partial_data": recovery_context.partial_data,
                    "error_message": recovery_context.error_message,
                    "retry_count": recovery_context.retry_count,
                    "created_at": recovery_context.timestamp,
                    "status": "pending",
                    "priority": "high" if recovery_context.recovery_type in [
                        EventRecoveryType.PARTIAL_CREATION_FAILURE,
                        EventRecoveryType.STATE_CORRUPTION
                    ] else "medium"
                }
            )
            
            # Remove from active contexts
            self._recovery_contexts.pop(recovery_context.event_id, None)
            
            # Emit manual intervention event
            await self.event_bus.emit(
                EventType.ERROR_OCCURRED,
                {
                    "type": "manual_intervention_required",
                    "event_id": recovery_context.event_id,
                    "recovery_type": recovery_context.recovery_type.value,
                    "failed_operation": recovery_context.failed_operation,
                    "retry_count": recovery_context.retry_count
                }
            )
            
            self.logger.error(
                "Event marked for manual intervention",
                event_id=recovery_context.event_id,
                recovery_type=recovery_context.recovery_type.value,
                retry_count=recovery_context.retry_count
            )
            
        except Exception as e:
            self.logger.error(
                "Failed to mark event for manual intervention",
                event_id=recovery_context.event_id,
                error=str(e)
            )
    
    # Recovery handlers
    
    async def _handle_partial_creation_failure(self, recovery_context: EventRecoveryContext) -> bool:
        """Handle partial event creation failures."""
        try:
            event_id = recovery_context.event_id
            original_data = recovery_context.original_data
            partial_data = recovery_context.partial_data
            
            # Check what was successfully created
            event_doc = await self.database.find_one("events", {"_id": event_id})
            
            if not event_doc:
                # Event wasn't created at all, try to create it
                return await self._retry_event_creation(recovery_context)
            
            # Event exists but may be incomplete
            missing_fields = []
            
            # Check required fields
            required_fields = ["title", "description", "creator_id", "guild_id", "state"]
            for field in required_fields:
                if field not in event_doc and field in original_data:
                    missing_fields.append(field)
            
            if missing_fields:
                # Update with missing fields
                update_data = {field: original_data[field] for field in missing_fields}
                
                await self.database.update_one(
                    "events",
                    {"_id": event_id},
                    {"$set": update_data}
                )
                
                self.logger.info(
                    "Restored missing event fields",
                    event_id=event_id,
                    missing_fields=missing_fields
                )
            
            # Check if polls need to be created
            if "polls" in original_data and "polls" not in event_doc:
                await self.database.update_one(
                    "events",
                    {"_id": event_id},
                    {"$set": {"polls": original_data["polls"]}}
                )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to handle partial creation failure",
                event_id=recovery_context.event_id,
                error=str(e)
            )
            return False
    
    async def _handle_poll_creation_failure(self, recovery_context: EventRecoveryContext) -> bool:
        """Handle poll creation failures."""
        try:
            event_id = recovery_context.event_id
            original_data = recovery_context.original_data
            
            # Get current event state
            event_doc = await self.database.find_one("events", {"_id": event_id})
            if not event_doc:
                return False
            
            # Determine which poll failed to create
            failed_poll_type = recovery_context.failed_operation.replace("_creation", "")
            
            # Create the missing poll
            poll_data = original_data.get("poll_data", {})
            if poll_data:
                await self.database.update_one(
                    "events",
                    {"_id": event_id},
                    {"$set": {f"polls.{failed_poll_type}": poll_data}}
                )
                
                # Update event state if necessary
                if event_doc.get("state") == "DRAFT":
                    new_state = self._determine_poll_state(failed_poll_type)
                    await self.database.update_one(
                        "events",
                        {"_id": event_id},
                        {"$set": {"state": new_state}}
                    )
                
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(
                "Failed to handle poll creation failure",
                event_id=recovery_context.event_id,
                error=str(e)
            )
            return False
    
    async def _handle_discord_event_failure(self, recovery_context: EventRecoveryContext) -> bool:
        """Handle Discord scheduled event creation failures."""
        try:
            event_id = recovery_context.event_id
            
            # Get current event
            event_doc = await self.database.find_one("events", {"_id": event_id})
            if not event_doc:
                return False
            
            # Check if Discord event was already created
            if event_doc.get("discord_event_id"):
                return True  # Already resolved
            
            # Try to create Discord event again
            # This would typically involve calling the Discord API
            # For now, we'll mark it as needing manual intervention
            # since Discord event creation requires specific bot permissions
            
            await self.database.update_one(
                "events",
                {"_id": event_id},
                {
                    "$set": {
                        "discord_event_failed": True,
                        "discord_event_failure_reason": recovery_context.error_message
                    }
                }
            )
            
            return True  # Marked for later retry
            
        except Exception as e:
            self.logger.error(
                "Failed to handle Discord event failure",
                event_id=recovery_context.event_id,
                error=str(e)
            )
            return False
    
    async def _handle_notification_failure(self, recovery_context: EventRecoveryContext) -> bool:
        """Handle notification creation failures."""
        try:
            event_id = recovery_context.event_id
            original_data = recovery_context.original_data
            
            # Get notification data from original data
            notification_data = original_data.get("notification_data", {})
            if not notification_data:
                return True  # Nothing to recover
            
            # Try to create the notification again
            await self.database.insert_one("notifications", notification_data)
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to handle notification failure",
                event_id=recovery_context.event_id,
                error=str(e)
            )
            return False
    
    async def _handle_state_corruption(self, recovery_context: EventRecoveryContext) -> bool:
        """Handle event state corruption."""
        try:
            event_id = recovery_context.event_id
            
            # Get current event
            event_doc = await self.database.find_one("events", {"_id": event_id})
            if not event_doc:
                return False
            
            # Determine correct state based on event data
            correct_state = self._determine_correct_state(event_doc)
            
            if correct_state != event_doc.get("state"):
                await self.database.update_one(
                    "events",
                    {"_id": event_id},
                    {"$set": {"state": correct_state}}
                )
                
                self.logger.info(
                    "Corrected event state",
                    event_id=event_id,
                    old_state=event_doc.get("state"),
                    new_state=correct_state
                )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to handle state corruption",
                event_id=recovery_context.event_id,
                error=str(e)
            )
            return False
    
    async def _handle_data_inconsistency(self, recovery_context: EventRecoveryContext) -> bool:
        """Handle data inconsistency issues."""
        try:
            event_id = recovery_context.event_id
            
            # Get current event
            event_doc = await self.database.find_one("events", {"_id": event_id})
            if not event_doc:
                return False
            
            # Fix common inconsistencies
            updates = {}
            
            # Fix poll vote counts
            polls = event_doc.get("polls", {})
            for poll_type, poll_data in polls.items():
                if isinstance(poll_data, dict):
                    options = poll_data.get("options", [])
                    for i, option in enumerate(options):
                        if isinstance(option, dict):
                            votes = option.get("votes", [])
                            actual_count = len(votes)
                            stored_count = option.get("vote_count", 0)
                            
                            if actual_count != stored_count:
                                updates[f"polls.{poll_type}.options.{i}.vote_count"] = actual_count
            
            # Fix RSVP counts
            rsvp_data = event_doc.get("rsvp_data", {})
            if rsvp_data:
                yes_count = sum(1 for status in rsvp_data.values() if status == "YES")
                no_count = sum(1 for status in rsvp_data.values() if status == "NO")
                maybe_count = sum(1 for status in rsvp_data.values() if status == "MAYBE")
                
                updates.update({
                    "rsvp_counts.yes": yes_count,
                    "rsvp_counts.no": no_count,
                    "rsvp_counts.maybe": maybe_count
                })
            
            if updates:
                await self.database.update_one(
                    "events",
                    {"_id": event_id},
                    {"$set": updates}
                )
                
                self.logger.info(
                    "Fixed data inconsistencies",
                    event_id=event_id,
                    fixes=list(updates.keys())
                )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to handle data inconsistency",
                event_id=recovery_context.event_id,
                error=str(e)
            )
            return False
    
    # Helper methods
    
    async def _retry_event_creation(self, recovery_context: EventRecoveryContext) -> bool:
        """Retry complete event creation."""
        try:
            original_data = recovery_context.original_data
            
            # Create the event document
            await self.database.insert_one("events", original_data)
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to retry event creation",
                event_id=recovery_context.event_id,
                error=str(e)
            )
            return False
    
    def _determine_poll_state(self, poll_type: str) -> str:
        """Determine the correct event state based on poll type."""
        state_mapping = {
            "date_poll": "DATE_POLLING",
            "time_poll": "TIME_POLLING",
            "game_poll": "GAME_POLLING"
        }
        return state_mapping.get(poll_type, "DRAFT")
    
    def _determine_correct_state(self, event_doc: Dict[str, Any]) -> str:
        """Determine the correct state for an event based on its data."""
        polls = event_doc.get("polls", {})
        
        # Check if event is completed
        if event_doc.get("completed_at"):
            return "COMPLETED"
        
        # Check if event is cancelled
        if event_doc.get("cancelled_at"):
            return "CANCELLED"
        
        # Check if event is scheduled
        if event_doc.get("schedule", {}).get("selected_date") and event_doc.get("schedule", {}).get("selected_time"):
            return "SCHEDULED"
        
        # Check active polls
        if "game_poll" in polls and polls["game_poll"].get("is_active"):
            return "GAME_POLLING"
        
        if "time_poll" in polls and polls["time_poll"].get("is_active"):
            return "TIME_POLLING"
        
        if "date_poll" in polls and polls["date_poll"].get("is_active"):
            return "DATE_POLLING"
        
        return "DRAFT"
    
    async def get_manual_interventions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get events requiring manual intervention."""
        try:
            return await self.database.find_many(
                "manual_interventions",
                {"status": "pending"},
                sort=[("created_at", -1)],
                limit=limit
            )
        except Exception as e:
            self.logger.error("Failed to get manual interventions", error=str(e))
            return []
    
    async def resolve_manual_intervention(
        self, 
        event_id: str, 
        resolution: str,
        resolved_by: str
    ) -> bool:
        """Mark a manual intervention as resolved."""
        try:
            await self.database.update_one(
                "manual_interventions",
                {"event_id": event_id, "status": "pending"},
                {
                    "$set": {
                        "status": "resolved",
                        "resolution": resolution,
                        "resolved_by": resolved_by,
                        "resolved_at": datetime.now()
                    }
                }
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to resolve manual intervention",
                event_id=event_id,
                error=str(e)
            )
            return False