"""
Advanced error handling and recovery systems for complex failure scenarios.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, asdict
from enum import Enum
import traceback

from database.manager import DatabaseManager
from core.event_bus import EventBus, EventType, Event
from utils.logging_config import get_logger, LoggerMixin
from utils.exceptions import (
    GameNightBotException, 
    DatabaseError, 
    EventError,
    ErrorCode
)


class RecoveryAction(str, Enum):
    """Types of recovery actions that can be taken."""
    RETRY = "RETRY"
    ROLLBACK = "ROLLBACK"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"
    SKIP = "SKIP"
    ESCALATE = "ESCALATE"
    REPAIR = "REPAIR"


class FailureType(str, Enum):
    """Categories of failures that can occur."""
    DATABASE_CONNECTIVITY = "DATABASE_CONNECTIVITY"
    EVENT_CREATION = "EVENT_CREATION"
    POLL_MANAGEMENT = "POLL_MANAGEMENT"
    DATA_CORRUPTION = "DATA_CORRUPTION"
    DISCORD_API = "DISCORD_API"
    STATE_INCONSISTENCY = "STATE_INCONSISTENCY"
    SYSTEM_CRASH = "SYSTEM_CRASH"


@dataclass
class FailureContext:
    """Context information about a failure."""
    failure_type: FailureType
    operation: str
    error_message: str
    error_details: Dict[str, Any]
    timestamp: float
    retry_count: int = 0
    max_retries: int = 3
    recovery_actions: List[RecoveryAction] = None
    
    def __post_init__(self):
        if self.recovery_actions is None:
            self.recovery_actions = []


@dataclass
class RecoveryState:
    """State information for recovery operations."""
    operation_id: str
    original_data: Dict[str, Any]
    checkpoint_data: Dict[str, Any]
    recovery_steps: List[str]
    completed_steps: List[str]
    failed_steps: List[str]
    created_at: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RecoveryState':
        return cls(**data)


class RecoveryManager(LoggerMixin):
    """
    Advanced recovery manager for handling complex failure scenarios.
    """
    
    def __init__(self, database: DatabaseManager, event_bus: EventBus):
        self.database = database
        self.event_bus = event_bus
        self._operation_queue: List[Dict[str, Any]] = []
        self._recovery_states: Dict[str, RecoveryState] = {}
        self._failure_handlers: Dict[FailureType, Callable] = {}
        self._consistency_checkers: List[Callable] = []
        self._recovery_active = False
        
        # Register default failure handlers
        self._register_default_handlers()
        
        # Register event bus listeners
        self._register_event_listeners()
    
    def _register_default_handlers(self) -> None:
        """Register default failure handlers."""
        self._failure_handlers[FailureType.DATABASE_CONNECTIVITY] = self._handle_database_connectivity_failure
        self._failure_handlers[FailureType.EVENT_CREATION] = self._handle_event_creation_failure
        self._failure_handlers[FailureType.POLL_MANAGEMENT] = self._handle_poll_management_failure
        self._failure_handlers[FailureType.DATA_CORRUPTION] = self._handle_data_corruption_failure
        self._failure_handlers[FailureType.DISCORD_API] = self._handle_discord_api_failure
        self._failure_handlers[FailureType.STATE_INCONSISTENCY] = self._handle_state_inconsistency_failure
        self._failure_handlers[FailureType.SYSTEM_CRASH] = self._handle_system_crash_failure
    
    def _register_event_listeners(self) -> None:
        """Register event bus listeners for recovery events."""
        self.event_bus.subscribe(EventType.ERROR_OCCURRED, self._on_error_occurred)
        self.event_bus.subscribe(EventType.SYSTEM_STARTUP, self._on_system_startup)
        self.event_bus.subscribe(EventType.SYSTEM_SHUTDOWN, self._on_system_shutdown)
    
    async def handle_failure(
        self, 
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Handle a failure with appropriate recovery actions.
        
        Args:
            failure_context: Context about the failure
            operation_data: Data related to the failed operation
            
        Returns:
            True if recovery was successful, False otherwise
        """
        self.logger.error(
            "Handling failure",
            failure_type=failure_context.failure_type.value,
            operation=failure_context.operation,
            error_message=failure_context.error_message,
            retry_count=failure_context.retry_count
        )
        
        # Get appropriate handler
        handler = self._failure_handlers.get(failure_context.failure_type)
        if not handler:
            self.logger.error(
                "No handler found for failure type",
                failure_type=failure_context.failure_type.value
            )
            return False
        
        try:
            # Create recovery state if needed
            if operation_data:
                recovery_state = await self._create_recovery_state(
                    failure_context.operation,
                    operation_data
                )
                self._recovery_states[recovery_state.operation_id] = recovery_state
            
            # Execute recovery handler
            success = await handler(failure_context, operation_data)
            
            if success:
                self.logger.info(
                    "Recovery successful",
                    failure_type=failure_context.failure_type.value,
                    operation=failure_context.operation
                )
                
                # Emit recovery success event
                await self.event_bus.emit(
                    EventType.ERROR_OCCURRED,
                    {
                        "recovery_successful": True,
                        "failure_type": failure_context.failure_type.value,
                        "operation": failure_context.operation
                    }
                )
            else:
                self.logger.error(
                    "Recovery failed",
                    failure_type=failure_context.failure_type.value,
                    operation=failure_context.operation
                )
            
            return success
            
        except Exception as e:
            self.logger.error(
                "Recovery handler failed",
                failure_type=failure_context.failure_type.value,
                error=str(e),
                exc_info=True
            )
            return False
    
    async def queue_operation(
        self, 
        operation: Dict[str, Any],
        priority: int = 0
    ) -> None:
        """
        Queue an operation for later execution during recovery.
        
        Args:
            operation: Operation data to queue
            priority: Priority level (higher = more important)
        """
        operation['priority'] = priority
        operation['queued_at'] = time.time()
        
        # Insert in priority order
        inserted = False
        for i, queued_op in enumerate(self._operation_queue):
            if priority > queued_op.get('priority', 0):
                self._operation_queue.insert(i, operation)
                inserted = True
                break
        
        if not inserted:
            self._operation_queue.append(operation)
        
        self.logger.debug(
            "Operation queued",
            operation_type=operation.get('type'),
            priority=priority,
            queue_size=len(self._operation_queue)
        )
    
    async def process_queued_operations(self) -> int:
        """
        Process all queued operations.
        
        Returns:
            Number of operations successfully processed
        """
        if not self._operation_queue:
            return 0
        
        self.logger.info(
            "Processing queued operations",
            queue_size=len(self._operation_queue)
        )
        
        processed = 0
        failed_operations = []
        
        while self._operation_queue:
            operation = self._operation_queue.pop(0)
            
            try:
                success = await self._execute_queued_operation(operation)
                if success:
                    processed += 1
                else:
                    failed_operations.append(operation)
                    
            except Exception as e:
                self.logger.error(
                    "Failed to execute queued operation",
                    operation_type=operation.get('type'),
                    error=str(e)
                )
                failed_operations.append(operation)
        
        # Re-queue failed operations with lower priority
        for failed_op in failed_operations:
            failed_op['retry_count'] = failed_op.get('retry_count', 0) + 1
            if failed_op['retry_count'] < 3:
                failed_op['priority'] = max(0, failed_op.get('priority', 0) - 1)
                self._operation_queue.append(failed_op)
        
        self.logger.info(
            "Finished processing queued operations",
            processed=processed,
            failed=len(failed_operations),
            requeued=len([op for op in failed_operations if op['retry_count'] < 3])
        )
        
        return processed
    
    async def check_data_consistency(self) -> List[Dict[str, Any]]:
        """
        Run data consistency checks and return any issues found.
        
        Returns:
            List of consistency issues
        """
        issues = []
        
        for checker in self._consistency_checkers:
            try:
                checker_issues = await checker()
                if checker_issues:
                    issues.extend(checker_issues)
            except Exception as e:
                self.logger.error(
                    "Consistency checker failed",
                    checker=checker.__name__,
                    error=str(e)
                )
                issues.append({
                    "type": "checker_failure",
                    "checker": checker.__name__,
                    "error": str(e)
                })
        
        if issues:
            self.logger.warning(
                "Data consistency issues found",
                issue_count=len(issues)
            )
        
        return issues
    
    async def repair_data_corruption(
        self, 
        corruption_type: str,
        affected_data: Dict[str, Any]
    ) -> bool:
        """
        Attempt to repair data corruption.
        
        Args:
            corruption_type: Type of corruption detected
            affected_data: Data that is corrupted
            
        Returns:
            True if repair was successful
        """
        self.logger.info(
            "Attempting data corruption repair",
            corruption_type=corruption_type
        )
        
        try:
            if corruption_type == "missing_required_fields":
                return await self._repair_missing_fields(affected_data)
            elif corruption_type == "invalid_state_transition":
                return await self._repair_invalid_state(affected_data)
            elif corruption_type == "orphaned_references":
                return await self._repair_orphaned_references(affected_data)
            elif corruption_type == "duplicate_entries":
                return await self._repair_duplicate_entries(affected_data)
            else:
                self.logger.warning(
                    "Unknown corruption type",
                    corruption_type=corruption_type
                )
                return False
                
        except Exception as e:
            self.logger.error(
                "Data repair failed",
                corruption_type=corruption_type,
                error=str(e)
            )
            return False
    
    async def restore_system_state(self) -> bool:
        """
        Restore system state after a crash or restart.
        
        Returns:
            True if restoration was successful
        """
        self.logger.info("Starting system state restoration")
        
        try:
            # Restore recovery states
            await self._restore_recovery_states()
            
            # Process any queued operations
            processed = await self.process_queued_operations()
            
            # Check for incomplete operations
            incomplete_ops = await self._find_incomplete_operations()
            
            # Restore active polls and views
            await self._restore_active_polls()
            
            # Reschedule missed notifications
            await self._reschedule_missed_notifications()
            
            self.logger.info(
                "System state restoration completed",
                processed_operations=processed,
                incomplete_operations=len(incomplete_ops)
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "System state restoration failed",
                error=str(e),
                exc_info=True
            )
            return False
    
    def register_consistency_checker(self, checker: Callable) -> None:
        """Register a data consistency checker function."""
        self._consistency_checkers.append(checker)
        self.logger.debug(
            "Registered consistency checker",
            checker=checker.__name__
        )
    
    def register_failure_handler(
        self, 
        failure_type: FailureType,
        handler: Callable
    ) -> None:
        """Register a custom failure handler."""
        self._failure_handlers[failure_type] = handler
        self.logger.debug(
            "Registered failure handler",
            failure_type=failure_type.value,
            handler=handler.__name__
        )
    
    # Event handlers
    
    async def _on_error_occurred(self, event: Event) -> None:
        """Handle error occurred events."""
        if not self._recovery_active:
            return
        
        error_data = event.data
        failure_type = error_data.get('failure_type')
        
        if failure_type:
            failure_context = FailureContext(
                failure_type=FailureType(failure_type),
                operation=error_data.get('operation', 'unknown'),
                error_message=error_data.get('error_message', ''),
                error_details=error_data.get('error_details', {}),
                timestamp=event.timestamp
            )
            
            await self.handle_failure(failure_context, error_data.get('operation_data'))
    
    async def _on_system_startup(self, event: Event) -> None:
        """Handle system startup events."""
        self._recovery_active = True
        await self.restore_system_state()
    
    async def _on_system_shutdown(self, event: Event) -> None:
        """Handle system shutdown events."""
        self._recovery_active = False
        await self._save_recovery_states()
    
    # Recovery state management
    
    async def _create_recovery_state(
        self, 
        operation: str,
        operation_data: Dict[str, Any]
    ) -> RecoveryState:
        """Create a recovery state for an operation."""
        operation_id = f"{operation}_{int(time.time() * 1000)}"
        
        recovery_state = RecoveryState(
            operation_id=operation_id,
            original_data=operation_data.copy(),
            checkpoint_data={},
            recovery_steps=[],
            completed_steps=[],
            failed_steps=[],
            created_at=time.time()
        )
        
        # Save to database
        await self.database.insert_one(
            "recovery_states",
            recovery_state.to_dict()
        )
        
        return recovery_state
    
    async def _save_recovery_states(self) -> None:
        """Save all recovery states to database."""
        for recovery_state in self._recovery_states.values():
            await self.database.update_one(
                "recovery_states",
                {"operation_id": recovery_state.operation_id},
                {"$set": recovery_state.to_dict()},
                upsert=True
            )
    
    async def _restore_recovery_states(self) -> None:
        """Restore recovery states from database."""
        try:
            states = await self.database.find_many(
                "recovery_states",
                {"created_at": {"$gte": time.time() - 86400}}  # Last 24 hours
            )
            
            for state_data in states:
                recovery_state = RecoveryState.from_dict(state_data)
                self._recovery_states[recovery_state.operation_id] = recovery_state
            
            self.logger.info(
                "Restored recovery states",
                count=len(states)
            )
            
        except Exception as e:
            self.logger.error(
                "Failed to restore recovery states",
                error=str(e)
            )    
 
   # Default failure handlers
    
    async def _handle_database_connectivity_failure(
        self, 
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Handle database connectivity failures with operation queuing."""
        self.logger.info("Handling database connectivity failure")
        
        # Queue the operation for later
        if operation_data:
            await self.queue_operation({
                'type': 'database_operation',
                'operation': failure_context.operation,
                'data': operation_data,
                'failure_context': asdict(failure_context)
            }, priority=5)
        
        # Attempt to reconnect
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                await asyncio.sleep(min(2 ** attempt, 30))  # Exponential backoff
                
                if await self.database.ping():
                    self.logger.info(
                        "Database connectivity restored",
                        attempt=attempt + 1
                    )
                    
                    # Process queued operations
                    await self.process_queued_operations()
                    return True
                    
            except Exception as e:
                self.logger.warning(
                    "Database reconnection attempt failed",
                    attempt=attempt + 1,
                    error=str(e)
                )
        
        self.logger.error("Database connectivity could not be restored")
        return False
    
    async def _handle_event_creation_failure(
        self, 
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Handle event creation failures with state preservation."""
        self.logger.info("Handling event creation failure")
        
        if not operation_data:
            return False
        
        try:
            # Preserve event data for manual intervention
            preserved_data = {
                'event_data': operation_data,
                'failure_reason': failure_context.error_message,
                'failure_details': failure_context.error_details,
                'created_at': time.time(),
                'status': 'pending_manual_intervention'
            }
            
            # Save to failed_events collection
            await self.database.insert_one("failed_events", preserved_data)
            
            # Notify administrators
            await self.event_bus.emit(
                EventType.ERROR_OCCURRED,
                {
                    'type': 'event_creation_failed',
                    'event_data': operation_data,
                    'requires_manual_intervention': True,
                    'failure_context': asdict(failure_context)
                }
            )
            
            self.logger.info(
                "Event creation failure handled - preserved for manual intervention",
                event_title=operation_data.get('title', 'Unknown')
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to handle event creation failure",
                error=str(e)
            )
            return False
    
    async def _handle_poll_management_failure(
        self, 
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Handle poll management edge cases with automated resolution."""
        self.logger.info("Handling poll management failure")
        
        if not operation_data:
            return False
        
        poll_issue = failure_context.error_details.get('poll_issue')
        event_id = operation_data.get('event_id')
        
        try:
            if poll_issue == 'tie_vote':
                return await self._resolve_poll_tie(event_id, operation_data)
            elif poll_issue == 'no_votes':
                return await self._handle_poll_no_votes(event_id, operation_data)
            elif poll_issue == 'user_departure':
                return await self._handle_user_departure_during_poll(event_id, operation_data)
            elif poll_issue == 'poll_timeout':
                return await self._handle_poll_timeout(event_id, operation_data)
            else:
                self.logger.warning(
                    "Unknown poll issue",
                    poll_issue=poll_issue
                )
                return False
                
        except Exception as e:
            self.logger.error(
                "Poll management failure handling failed",
                error=str(e)
            )
            return False
    
    async def _handle_data_corruption_failure(
        self, 
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Handle data corruption with automated repair procedures."""
        self.logger.info("Handling data corruption failure")
        
        corruption_type = failure_context.error_details.get('corruption_type')
        affected_data = failure_context.error_details.get('affected_data', {})
        
        if corruption_type:
            return await self.repair_data_corruption(corruption_type, affected_data)
        
        return False
    
    async def _handle_discord_api_failure(
        self, 
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Handle Discord API failures with retry logic."""
        self.logger.info("Handling Discord API failure")
        
        # Check if it's a rate limit
        if 'rate limit' in failure_context.error_message.lower():
            retry_after = failure_context.error_details.get('retry_after', 60)
            
            # Queue operation for retry after rate limit
            if operation_data:
                await asyncio.sleep(retry_after)
                await self.queue_operation({
                    'type': 'discord_api_operation',
                    'operation': failure_context.operation,
                    'data': operation_data,
                    'retry_after': retry_after
                }, priority=3)
            
            return True
        
        # For other API failures, retry with exponential backoff
        if failure_context.retry_count < failure_context.max_retries:
            delay = min(2 ** failure_context.retry_count, 300)  # Max 5 minutes
            await asyncio.sleep(delay)
            
            if operation_data:
                await self.queue_operation({
                    'type': 'discord_api_operation',
                    'operation': failure_context.operation,
                    'data': operation_data,
                    'retry_count': failure_context.retry_count + 1
                }, priority=2)
            
            return True
        
        return False
    
    async def _handle_state_inconsistency_failure(
        self, 
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Handle state inconsistency issues."""
        self.logger.info("Handling state inconsistency failure")
        
        inconsistency_type = failure_context.error_details.get('inconsistency_type')
        
        if inconsistency_type == 'event_state_mismatch':
            return await self._repair_event_state_mismatch(operation_data)
        elif inconsistency_type == 'poll_state_mismatch':
            return await self._repair_poll_state_mismatch(operation_data)
        elif inconsistency_type == 'rsvp_sync_mismatch':
            return await self._repair_rsvp_sync_mismatch(operation_data)
        
        return False
    
    async def _handle_system_crash_failure(
        self, 
        failure_context: FailureContext,
        operation_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Handle system crash recovery."""
        self.logger.info("Handling system crash failure")
        
        # This is handled by the restore_system_state method
        # which is called on startup
        return await self.restore_system_state()
    
    # Specific recovery operations
    
    async def _resolve_poll_tie(self, event_id: str, operation_data: Dict[str, Any]) -> bool:
        """Resolve a poll tie situation."""
        try:
            # Get event data
            event_doc = await self.database.find_one("events", {"_id": event_id})
            if not event_doc:
                return False
            
            poll_type = operation_data.get('poll_type')
            tied_options = operation_data.get('tied_options', [])
            
            # Create a runoff poll with tied options
            runoff_poll_data = {
                'event_id': event_id,
                'poll_type': f"{poll_type}_runoff",
                'options': tied_options,
                'is_runoff': True,
                'original_poll_id': operation_data.get('poll_id')
            }
            
            # Update event with runoff poll
            await self.database.update_one(
                "events",
                {"_id": event_id},
                {
                    "$set": {
                        f"polls.{poll_type}_runoff": runoff_poll_data,
                        "state": "RUNOFF_POLLING"
                    }
                }
            )
            
            # Emit event for UI update
            await self.event_bus.emit(
                EventType.POLL_CREATED,
                {
                    'event_id': event_id,
                    'poll_type': f"{poll_type}_runoff",
                    'is_runoff': True
                }
            )
            
            self.logger.info(
                "Poll tie resolved with runoff poll",
                event_id=event_id,
                poll_type=poll_type
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to resolve poll tie",
                event_id=event_id,
                error=str(e)
            )
            return False
    
    async def _handle_poll_no_votes(self, event_id: str, operation_data: Dict[str, Any]) -> bool:
        """Handle polls with no votes."""
        try:
            poll_type = operation_data.get('poll_type')
            
            # Extend poll deadline by 24 hours
            new_deadline = datetime.now() + timedelta(hours=24)
            
            await self.database.update_one(
                "events",
                {"_id": event_id},
                {
                    "$set": {
                        f"polls.{poll_type}.closes_at": new_deadline,
                        f"polls.{poll_type}.extended": True
                    }
                }
            )
            
            # Notify users about extension
            await self.event_bus.emit(
                EventType.POLL_UPDATED,
                {
                    'event_id': event_id,
                    'poll_type': poll_type,
                    'action': 'extended',
                    'new_deadline': new_deadline.isoformat()
                }
            )
            
            self.logger.info(
                "Poll extended due to no votes",
                event_id=event_id,
                poll_type=poll_type
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to handle poll no votes",
                event_id=event_id,
                error=str(e)
            )
            return False
    
    async def _handle_user_departure_during_poll(
        self, 
        event_id: str, 
        operation_data: Dict[str, Any]
    ) -> bool:
        """Handle user leaving during active poll."""
        try:
            user_id = operation_data.get('user_id')
            poll_type = operation_data.get('poll_type')
            
            # Remove user's votes from all options
            await self.database.update_one(
                "events",
                {"_id": event_id},
                {
                    "$pull": {
                        f"polls.{poll_type}.options.$[].votes": user_id
                    }
                }
            )
            
            # Recalculate vote counts
            event_doc = await self.database.find_one("events", {"_id": event_id})
            if event_doc and poll_type in event_doc.get('polls', {}):
                poll = event_doc['polls'][poll_type]
                for option in poll.get('options', []):
                    option['vote_count'] = len(option.get('votes', []))
                
                await self.database.update_one(
                    "events",
                    {"_id": event_id},
                    {"$set": {f"polls.{poll_type}": poll}}
                )
            
            self.logger.info(
                "Handled user departure during poll",
                event_id=event_id,
                user_id=user_id,
                poll_type=poll_type
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to handle user departure during poll",
                event_id=event_id,
                error=str(e)
            )
            return False
    
    async def _handle_poll_timeout(self, event_id: str, operation_data: Dict[str, Any]) -> bool:
        """Handle poll timeout with automatic advancement."""
        try:
            poll_type = operation_data.get('poll_type')
            
            # Get current poll results
            event_doc = await self.database.find_one("events", {"_id": event_id})
            if not event_doc:
                return False
            
            poll = event_doc.get('polls', {}).get(poll_type)
            if not poll:
                return False
            
            # Find option with most votes
            options = poll.get('options', [])
            if not options:
                return False
            
            # Sort by vote count
            sorted_options = sorted(options, key=lambda x: x.get('vote_count', 0), reverse=True)
            winner = sorted_options[0]
            
            # Check for ties
            if len(sorted_options) > 1 and winner['vote_count'] == sorted_options[1]['vote_count']:
                # Handle tie
                tied_options = [opt for opt in sorted_options if opt['vote_count'] == winner['vote_count']]
                return await self._resolve_poll_tie(event_id, {
                    'poll_type': poll_type,
                    'tied_options': tied_options,
                    'poll_id': poll.get('poll_id')
                })
            
            # Set winner and advance state
            await self.database.update_one(
                "events",
                {"_id": event_id},
                {
                    "$set": {
                        f"polls.{poll_type}.winner_option_id": winner['option_id'],
                        f"polls.{poll_type}.is_active": False
                    }
                }
            )
            
            # Advance event state
            next_state = self._get_next_event_state(poll_type)
            if next_state:
                await self.database.update_one(
                    "events",
                    {"_id": event_id},
                    {"$set": {"state": next_state}}
                )
            
            self.logger.info(
                "Poll timeout handled with automatic advancement",
                event_id=event_id,
                poll_type=poll_type,
                winner_option=winner['option_id']
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to handle poll timeout",
                event_id=event_id,
                error=str(e)
            )
            return False
    
    # Data repair operations
    
    async def _repair_missing_fields(self, affected_data: Dict[str, Any]) -> bool:
        """Repair documents with missing required fields."""
        try:
            collection = affected_data.get('collection')
            document_id = affected_data.get('document_id')
            missing_fields = affected_data.get('missing_fields', [])
            
            if not all([collection, document_id, missing_fields]):
                return False
            
            # Define default values for common fields
            default_values = {
                'created_at': datetime.now(),
                'updated_at': datetime.now(),
                'state': 'DRAFT',
                'is_active': True,
                'votes': [],
                'vote_count': 0,
                'options': [],
                'polls': {},
                'rsvp_data': {},
                'attendance': {}
            }
            
            # Build update document
            update_doc = {}
            for field in missing_fields:
                if field in default_values:
                    update_doc[field] = default_values[field]
                else:
                    # Try to infer appropriate default
                    if field.endswith('_id'):
                        update_doc[field] = None
                    elif field.endswith('_count'):
                        update_doc[field] = 0
                    elif field.endswith('_list') or field.endswith('s'):
                        update_doc[field] = []
                    else:
                        update_doc[field] = None
            
            # Apply repair
            await self.database.update_one(
                collection,
                {"_id": document_id},
                {"$set": update_doc}
            )
            
            self.logger.info(
                "Repaired missing fields",
                collection=collection,
                document_id=document_id,
                repaired_fields=list(update_doc.keys())
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to repair missing fields",
                error=str(e)
            )
            return False
    
    async def _repair_invalid_state(self, affected_data: Dict[str, Any]) -> bool:
        """Repair invalid state transitions."""
        try:
            collection = affected_data.get('collection')
            document_id = affected_data.get('document_id')
            current_state = affected_data.get('current_state')
            expected_state = affected_data.get('expected_state')
            
            if collection == 'events':
                # Determine correct state based on event data
                event_doc = await self.database.find_one(collection, {"_id": document_id})
                if not event_doc:
                    return False
                
                correct_state = self._determine_correct_event_state(event_doc)
                
                await self.database.update_one(
                    collection,
                    {"_id": document_id},
                    {"$set": {"state": correct_state}}
                )
                
                self.logger.info(
                    "Repaired invalid event state",
                    document_id=document_id,
                    old_state=current_state,
                    new_state=correct_state
                )
                
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(
                "Failed to repair invalid state",
                error=str(e)
            )
            return False
    
    async def _repair_orphaned_references(self, affected_data: Dict[str, Any]) -> bool:
        """Repair orphaned references between documents."""
        try:
            reference_type = affected_data.get('reference_type')
            
            if reference_type == 'event_user_references':
                # Clean up user references in events where users no longer exist
                return await self._clean_orphaned_user_references()
            elif reference_type == 'poll_option_references':
                # Clean up poll option references
                return await self._clean_orphaned_poll_references()
            
            return False
            
        except Exception as e:
            self.logger.error(
                "Failed to repair orphaned references",
                error=str(e)
            )
            return False
    
    async def _repair_duplicate_entries(self, affected_data: Dict[str, Any]) -> bool:
        """Repair duplicate entries in collections."""
        try:
            collection = affected_data.get('collection')
            duplicate_field = affected_data.get('duplicate_field')
            
            # Find duplicates
            pipeline = [
                {"$group": {
                    "_id": f"${duplicate_field}",
                    "count": {"$sum": 1},
                    "docs": {"$push": "$$ROOT"}
                }},
                {"$match": {"count": {"$gt": 1}}}
            ]
            
            duplicates = await self.database.aggregate(collection, pipeline)
            
            for duplicate_group in duplicates:
                docs = duplicate_group['docs']
                # Keep the most recent document
                docs.sort(key=lambda x: x.get('created_at', datetime.min), reverse=True)
                
                # Delete older duplicates
                for doc in docs[1:]:
                    await self.database.delete_one(collection, {"_id": doc['_id']})
            
            self.logger.info(
                "Repaired duplicate entries",
                collection=collection,
                duplicate_field=duplicate_field,
                groups_processed=len(duplicates)
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to repair duplicate entries",
                error=str(e)
            )
            return False
    
    # Helper methods
    
    async def _execute_queued_operation(self, operation: Dict[str, Any]) -> bool:
        """Execute a queued operation."""
        operation_type = operation.get('type')
        
        try:
            if operation_type == 'database_operation':
                return await self._execute_database_operation(operation)
            elif operation_type == 'discord_api_operation':
                return await self._execute_discord_api_operation(operation)
            else:
                self.logger.warning(
                    "Unknown queued operation type",
                    operation_type=operation_type
                )
                return False
                
        except Exception as e:
            self.logger.error(
                "Failed to execute queued operation",
                operation_type=operation_type,
                error=str(e)
            )
            return False
    
    async def _execute_database_operation(self, operation: Dict[str, Any]) -> bool:
        """Execute a queued database operation."""
        # Implementation depends on the specific operation
        # This is a placeholder for the actual implementation
        return True
    
    async def _execute_discord_api_operation(self, operation: Dict[str, Any]) -> bool:
        """Execute a queued Discord API operation."""
        # Implementation depends on the specific operation
        # This is a placeholder for the actual implementation
        return True
    
    async def _find_incomplete_operations(self) -> List[Dict[str, Any]]:
        """Find operations that were interrupted."""
        # Look for events in transitional states
        incomplete_events = await self.database.find_many(
            "events",
            {
                "state": {"$in": ["DATE_POLLING", "TIME_POLLING", "GAME_POLLING"]},
                "updated_at": {"$lt": datetime.now() - timedelta(hours=1)}
            }
        )
        
        return incomplete_events
    
    async def _restore_active_polls(self) -> None:
        """Restore active polls and their views."""
        # Find active polls
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
        
        # Emit events to recreate views
        for event in active_events:
            await self.event_bus.emit(
                EventType.POLL_CREATED,
                {
                    'event_id': str(event['_id']),
                    'restore_view': True,
                    'event_data': event
                }
            )
    
    async def _reschedule_missed_notifications(self) -> None:
        """Reschedule notifications that were missed during downtime."""
        # Find notifications that should have been sent
        missed_notifications = await self.database.find_many(
            "notifications",
            {
                "scheduled_for": {"$lt": datetime.now()},
                "processed": False,
                "failed": {"$ne": True}
            }
        )
        
        for notification in missed_notifications:
            # Reschedule for immediate processing
            await self.database.update_one(
                "notifications",
                {"_id": notification['_id']},
                {"$set": {"scheduled_for": datetime.now()}}
            )
    
    def _get_next_event_state(self, poll_type: str) -> Optional[str]:
        """Get the next event state after a poll completes."""
        state_transitions = {
            'date': 'TIME_POLLING',
            'time': 'GAME_POLLING',
            'game': 'SCHEDULED'
        }
        return state_transitions.get(poll_type.lower())
    
    def _determine_correct_event_state(self, event_doc: Dict[str, Any]) -> str:
        """Determine the correct state for an event based on its data."""
        polls = event_doc.get('polls', {})
        
        if 'game_poll' in polls and polls['game_poll'].get('winner_option_id'):
            return 'SCHEDULED'
        elif 'time_poll' in polls and polls['time_poll'].get('winner_option_id'):
            return 'GAME_POLLING'
        elif 'date_poll' in polls and polls['date_poll'].get('winner_option_id'):
            return 'TIME_POLLING'
        elif 'date_poll' in polls:
            return 'DATE_POLLING'
        else:
            return 'DRAFT'
    
    async def _clean_orphaned_user_references(self) -> bool:
        """Clean up orphaned user references in events."""
        # This would involve checking user references against actual users
        # and removing references to users who no longer exist
        return True
    
    async def _clean_orphaned_poll_references(self) -> bool:
        """Clean up orphaned poll option references."""
        # This would involve cleaning up poll data inconsistencies
        return True
    
    async def _repair_event_state_mismatch(self, operation_data: Dict[str, Any]) -> bool:
        """Repair event state mismatches."""
        event_id = operation_data.get('event_id')
        if not event_id:
            return False
        
        event_doc = await self.database.find_one("events", {"_id": event_id})
        if not event_doc:
            return False
        
        correct_state = self._determine_correct_event_state(event_doc)
        
        await self.database.update_one(
            "events",
            {"_id": event_id},
            {"$set": {"state": correct_state}}
        )
        
        return True
    
    async def _repair_poll_state_mismatch(self, operation_data: Dict[str, Any]) -> bool:
        """Repair poll state mismatches."""
        # Implementation for poll state repair
        return True
    
    async def _repair_rsvp_sync_mismatch(self, operation_data: Dict[str, Any]) -> bool:
        """Repair RSVP synchronization mismatches."""
        # Implementation for RSVP sync repair
        return True