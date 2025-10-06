"""
Database recovery system with operation queuing and transaction rollback.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import traceback

from database.manager import DatabaseManager
from utils.logging_config import get_logger, LoggerMixin
from utils.exceptions import DatabaseError, DatabaseConnectionError


class OperationType(str, Enum):
    """Types of database operations."""
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    FIND = "FIND"
    AGGREGATE = "AGGREGATE"
    TRANSACTION = "TRANSACTION"


class OperationStatus(str, Enum):
    """Status of database operations."""
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class DatabaseOperation:
    """Represents a database operation that can be queued and retried."""
    operation_id: str
    operation_type: OperationType
    collection: str
    method: str
    args: List[Any]
    kwargs: Dict[str, Any]
    priority: int = 0
    max_retries: int = 3
    retry_count: int = 0
    status: OperationStatus = OperationStatus.PENDING
    created_at: float = None
    executed_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_message: Optional[str] = None
    result: Optional[Any] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DatabaseOperation':
        return cls(**data)


@dataclass
class TransactionContext:
    """Context for database transactions with rollback capability."""
    transaction_id: str
    operations: List[DatabaseOperation]
    rollback_operations: List[DatabaseOperation]
    status: OperationStatus = OperationStatus.PENDING
    created_at: float = None
    committed_at: Optional[float] = None
    rolled_back_at: Optional[float] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()


class DatabaseRecoveryManager(LoggerMixin):
    """
    Enhanced database manager with recovery capabilities.
    """
    
    def __init__(self, database: DatabaseManager):
        self.database = database
        self._operation_queue: List[DatabaseOperation] = []
        self._failed_operations: List[DatabaseOperation] = []
        self._active_transactions: Dict[str, TransactionContext] = {}
        self._connection_lost = False
        self._recovery_active = False
        self._queue_lock = asyncio.Lock()
        
        # Connection monitoring
        self._last_ping = 0
        self._ping_interval = 30  # seconds
        self._connection_check_task = None
    
    async def start_recovery_monitoring(self) -> None:
        """Start connection monitoring and recovery."""
        if self._recovery_active:
            return
        
        self._recovery_active = True
        self._connection_check_task = asyncio.create_task(self._connection_monitor_loop())
        
        self.logger.info("Database recovery monitoring started")
    
    async def stop_recovery_monitoring(self) -> None:
        """Stop recovery monitoring."""
        self._recovery_active = False
        
        if self._connection_check_task:
            self._connection_check_task.cancel()
            try:
                await self._connection_check_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Database recovery monitoring stopped")
    
    async def execute_with_recovery(
        self,
        operation_type: OperationType,
        collection: str,
        method: str,
        *args,
        priority: int = 0,
        max_retries: int = 3,
        **kwargs
    ) -> Any:
        """
        Execute a database operation with automatic recovery.
        
        Args:
            operation_type: Type of operation
            collection: Collection name
            method: Method to call on the collection
            *args: Arguments for the method
            priority: Operation priority (higher = more important)
            max_retries: Maximum retry attempts
            **kwargs: Keyword arguments for the method
            
        Returns:
            Operation result
            
        Raises:
            DatabaseError: If operation fails after all retries
        """
        operation = DatabaseOperation(
            operation_id=f"{method}_{int(time.time() * 1000)}",
            operation_type=operation_type,
            collection=collection,
            method=method,
            args=list(args),
            kwargs=kwargs,
            priority=priority,
            max_retries=max_retries
        )
        
        # If connection is available, try immediate execution
        if not self._connection_lost and await self._check_connection():
            try:
                return await self._execute_operation(operation)
            except DatabaseConnectionError:
                self._connection_lost = True
                self.logger.warning("Database connection lost during operation")
        
        # Queue operation for later execution
        await self._queue_operation(operation)
        
        # Wait for operation to complete or fail
        return await self._wait_for_operation(operation)
    
    async def begin_transaction(self, transaction_id: Optional[str] = None) -> str:
        """
        Begin a database transaction with rollback capability.
        
        Args:
            transaction_id: Optional transaction ID
            
        Returns:
            Transaction ID
        """
        if transaction_id is None:
            transaction_id = f"txn_{int(time.time() * 1000)}"
        
        transaction = TransactionContext(
            transaction_id=transaction_id,
            operations=[],
            rollback_operations=[]
        )
        
        self._active_transactions[transaction_id] = transaction
        
        self.logger.debug(
            "Transaction started",
            transaction_id=transaction_id
        )
        
        return transaction_id
    
    async def add_to_transaction(
        self,
        transaction_id: str,
        operation_type: OperationType,
        collection: str,
        method: str,
        *args,
        rollback_method: Optional[str] = None,
        rollback_args: Optional[List[Any]] = None,
        rollback_kwargs: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        """
        Add an operation to a transaction.
        
        Args:
            transaction_id: Transaction ID
            operation_type: Type of operation
            collection: Collection name
            method: Method to call
            *args: Method arguments
            rollback_method: Method to call for rollback
            rollback_args: Arguments for rollback method
            rollback_kwargs: Keyword arguments for rollback method
            **kwargs: Method keyword arguments
        """
        if transaction_id not in self._active_transactions:
            raise DatabaseError(f"Transaction {transaction_id} not found")
        
        transaction = self._active_transactions[transaction_id]
        
        # Create forward operation
        operation = DatabaseOperation(
            operation_id=f"{transaction_id}_{method}_{len(transaction.operations)}",
            operation_type=operation_type,
            collection=collection,
            method=method,
            args=list(args),
            kwargs=kwargs
        )
        
        transaction.operations.append(operation)
        
        # Create rollback operation if specified
        if rollback_method:
            rollback_operation = DatabaseOperation(
                operation_id=f"{transaction_id}_rollback_{len(transaction.rollback_operations)}",
                operation_type=operation_type,
                collection=collection,
                method=rollback_method,
                args=rollback_args or [],
                kwargs=rollback_kwargs or {}
            )
            
            transaction.rollback_operations.insert(0, rollback_operation)  # Reverse order
    
    async def commit_transaction(self, transaction_id: str) -> bool:
        """
        Commit a transaction.
        
        Args:
            transaction_id: Transaction ID
            
        Returns:
            True if successful, False otherwise
        """
        if transaction_id not in self._active_transactions:
            raise DatabaseError(f"Transaction {transaction_id} not found")
        
        transaction = self._active_transactions[transaction_id]
        transaction.status = OperationStatus.EXECUTING
        
        try:
            # Execute all operations in the transaction
            for operation in transaction.operations:
                await self._execute_operation(operation)
            
            transaction.status = OperationStatus.COMPLETED
            transaction.committed_at = time.time()
            
            self.logger.info(
                "Transaction committed successfully",
                transaction_id=transaction_id,
                operation_count=len(transaction.operations)
            )
            
            # Clean up
            del self._active_transactions[transaction_id]
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Transaction commit failed",
                transaction_id=transaction_id,
                error=str(e)
            )
            
            # Attempt rollback
            await self.rollback_transaction(transaction_id)
            return False
    
    async def rollback_transaction(self, transaction_id: str) -> bool:
        """
        Rollback a transaction.
        
        Args:
            transaction_id: Transaction ID
            
        Returns:
            True if successful, False otherwise
        """
        if transaction_id not in self._active_transactions:
            self.logger.warning(
                "Attempted to rollback non-existent transaction",
                transaction_id=transaction_id
            )
            return False
        
        transaction = self._active_transactions[transaction_id]
        transaction.status = OperationStatus.EXECUTING
        
        try:
            # Execute rollback operations in reverse order
            for rollback_operation in transaction.rollback_operations:
                try:
                    await self._execute_operation(rollback_operation)
                except Exception as e:
                    self.logger.error(
                        "Rollback operation failed",
                        transaction_id=transaction_id,
                        operation_id=rollback_operation.operation_id,
                        error=str(e)
                    )
                    # Continue with other rollback operations
            
            transaction.status = OperationStatus.ROLLED_BACK
            transaction.rolled_back_at = time.time()
            
            self.logger.info(
                "Transaction rolled back",
                transaction_id=transaction_id,
                rollback_operation_count=len(transaction.rollback_operations)
            )
            
            # Clean up
            del self._active_transactions[transaction_id]
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Transaction rollback failed",
                transaction_id=transaction_id,
                error=str(e)
            )
            
            transaction.status = OperationStatus.FAILED
            return False
    
    async def process_queued_operations(self) -> int:
        """
        Process all queued operations.
        
        Returns:
            Number of operations successfully processed
        """
        if not self._operation_queue:
            return 0
        
        async with self._queue_lock:
            self.logger.info(
                "Processing queued database operations",
                queue_size=len(self._operation_queue)
            )
            
            processed = 0
            failed_operations = []
            
            # Sort by priority
            self._operation_queue.sort(key=lambda op: op.priority, reverse=True)
            
            while self._operation_queue:
                operation = self._operation_queue.pop(0)
                
                try:
                    await self._execute_operation(operation)
                    processed += 1
                    
                except Exception as e:
                    operation.retry_count += 1
                    operation.error_message = str(e)
                    
                    if operation.retry_count < operation.max_retries:
                        # Re-queue with lower priority
                        operation.priority = max(0, operation.priority - 1)
                        failed_operations.append(operation)
                    else:
                        # Move to failed operations
                        operation.status = OperationStatus.FAILED
                        self._failed_operations.append(operation)
                        
                        self.logger.error(
                            "Database operation failed permanently",
                            operation_id=operation.operation_id,
                            operation_type=operation.operation_type.value,
                            error=str(e)
                        )
            
            # Re-queue failed operations that haven't exceeded max retries
            self._operation_queue.extend(failed_operations)
            
            self.logger.info(
                "Finished processing queued database operations",
                processed=processed,
                failed=len(failed_operations),
                permanently_failed=len([op for op in self._failed_operations 
                                      if op.created_at > time.time() - 3600])  # Last hour
            )
            
            return processed
    
    async def get_operation_status(self, operation_id: str) -> Optional[DatabaseOperation]:
        """Get the status of a specific operation."""
        # Check queued operations
        for operation in self._operation_queue:
            if operation.operation_id == operation_id:
                return operation
        
        # Check failed operations
        for operation in self._failed_operations:
            if operation.operation_id == operation_id:
                return operation
        
        return None
    
    async def retry_failed_operations(self, max_age_hours: int = 24) -> int:
        """
        Retry failed operations that are not too old.
        
        Args:
            max_age_hours: Maximum age of operations to retry
            
        Returns:
            Number of operations re-queued for retry
        """
        cutoff_time = time.time() - (max_age_hours * 3600)
        retry_operations = []
        
        # Find failed operations that can be retried
        for operation in self._failed_operations[:]:
            if (operation.created_at > cutoff_time and 
                operation.retry_count < operation.max_retries):
                
                operation.status = OperationStatus.PENDING
                operation.retry_count += 1
                retry_operations.append(operation)
                self._failed_operations.remove(operation)
        
        # Add to queue
        async with self._queue_lock:
            self._operation_queue.extend(retry_operations)
        
        self.logger.info(
            "Re-queued failed operations for retry",
            retry_count=len(retry_operations)
        )
        
        return len(retry_operations)
    
    async def cleanup_old_operations(self, max_age_hours: int = 168) -> int:
        """
        Clean up old failed operations.
        
        Args:
            max_age_hours: Maximum age to keep (default: 1 week)
            
        Returns:
            Number of operations cleaned up
        """
        cutoff_time = time.time() - (max_age_hours * 3600)
        
        old_operations = [
            op for op in self._failed_operations 
            if op.created_at < cutoff_time
        ]
        
        for operation in old_operations:
            self._failed_operations.remove(operation)
        
        self.logger.info(
            "Cleaned up old failed operations",
            cleaned_count=len(old_operations)
        )
        
        return len(old_operations)
    
    # Private methods
    
    async def _connection_monitor_loop(self) -> None:
        """Monitor database connection and trigger recovery."""
        while self._recovery_active:
            try:
                await asyncio.sleep(self._ping_interval)
                
                if await self._check_connection():
                    if self._connection_lost:
                        self.logger.info("Database connection restored")
                        self._connection_lost = False
                        
                        # Process queued operations
                        await self.process_queued_operations()
                else:
                    if not self._connection_lost:
                        self.logger.warning("Database connection lost")
                        self._connection_lost = True
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    "Error in connection monitor loop",
                    error=str(e)
                )
    
    async def _check_connection(self) -> bool:
        """Check if database connection is available."""
        try:
            return await self.database.ping()
        except Exception:
            return False
    
    async def _queue_operation(self, operation: DatabaseOperation) -> None:
        """Add an operation to the queue."""
        async with self._queue_lock:
            # Insert in priority order
            inserted = False
            for i, queued_op in enumerate(self._operation_queue):
                if operation.priority > queued_op.priority:
                    self._operation_queue.insert(i, operation)
                    inserted = True
                    break
            
            if not inserted:
                self._operation_queue.append(operation)
        
        self.logger.debug(
            "Database operation queued",
            operation_id=operation.operation_id,
            operation_type=operation.operation_type.value,
            priority=operation.priority
        )
    
    async def _execute_operation(self, operation: DatabaseOperation) -> Any:
        """Execute a database operation."""
        operation.status = OperationStatus.EXECUTING
        operation.executed_at = time.time()
        
        try:
            # Get the collection
            collection = getattr(self.database, operation.collection)
            
            # Get the method
            method = getattr(collection, operation.method)
            
            # Execute the operation
            result = await method(*operation.args, **operation.kwargs)
            
            operation.status = OperationStatus.COMPLETED
            operation.completed_at = time.time()
            operation.result = result
            
            self.logger.debug(
                "Database operation completed",
                operation_id=operation.operation_id,
                operation_type=operation.operation_type.value,
                duration_ms=(operation.completed_at - operation.executed_at) * 1000
            )
            
            return result
            
        except Exception as e:
            operation.status = OperationStatus.FAILED
            operation.error_message = str(e)
            
            self.logger.error(
                "Database operation failed",
                operation_id=operation.operation_id,
                operation_type=operation.operation_type.value,
                error=str(e)
            )
            
            raise
    
    async def _wait_for_operation(self, operation: DatabaseOperation) -> Any:
        """Wait for an operation to complete."""
        max_wait_time = 300  # 5 minutes
        check_interval = 0.1  # 100ms
        waited = 0
        
        while waited < max_wait_time:
            if operation.status == OperationStatus.COMPLETED:
                return operation.result
            elif operation.status == OperationStatus.FAILED:
                raise DatabaseError(
                    f"Database operation failed: {operation.error_message}"
                )
            
            await asyncio.sleep(check_interval)
            waited += check_interval
        
        raise DatabaseError(
            f"Database operation timed out: {operation.operation_id}"
        )
    
    # Convenience methods that wrap the database manager
    
    async def insert_one_with_recovery(
        self, 
        collection: str, 
        document: Dict[str, Any],
        **kwargs
    ) -> str:
        """Insert a document with recovery."""
        return await self.execute_with_recovery(
            OperationType.INSERT,
            collection,
            "insert_one",
            document,
            **kwargs
        )
    
    async def find_one_with_recovery(
        self, 
        collection: str, 
        filter_dict: Dict[str, Any],
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Find a document with recovery."""
        return await self.execute_with_recovery(
            OperationType.FIND,
            collection,
            "find_one",
            filter_dict,
            **kwargs
        )
    
    async def update_one_with_recovery(
        self, 
        collection: str, 
        filter_dict: Dict[str, Any],
        update_dict: Dict[str, Any],
        **kwargs
    ) -> bool:
        """Update a document with recovery."""
        return await self.execute_with_recovery(
            OperationType.UPDATE,
            collection,
            "update_one",
            filter_dict,
            update_dict,
            **kwargs
        )
    
    async def delete_one_with_recovery(
        self, 
        collection: str, 
        filter_dict: Dict[str, Any],
        **kwargs
    ) -> bool:
        """Delete a document with recovery."""
        return await self.execute_with_recovery(
            OperationType.DELETE,
            collection,
            "delete_one",
            filter_dict,
            **kwargs
        )