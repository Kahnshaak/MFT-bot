"""
Batch processing system for optimizing bulk operations and notification delivery.
"""

import asyncio
from typing import Dict, List, Optional, Any, Callable, TypeVar, Generic
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import time

from utils.logging_config import get_logger, LoggerMixin

T = TypeVar('T')


class BatchStrategy(Enum):
    """Batch processing strategies."""
    
    SIZE_BASED = "size_based"        # Process when batch reaches size limit
    TIME_BASED = "time_based"        # Process after time interval
    HYBRID = "hybrid"                # Process on size OR time limit
    IMMEDIATE = "immediate"          # Process immediately (no batching)


@dataclass
class BatchConfig:
    """Configuration for batch processing."""
    
    name: str
    max_batch_size: int = 100
    max_wait_time: float = 5.0  # seconds
    strategy: BatchStrategy = BatchStrategy.HYBRID
    retry_attempts: int = 3
    retry_delay: float = 1.0
    parallel_batches: int = 1
    
    def __post_init__(self):
        if self.max_batch_size <= 0:
            raise ValueError("max_batch_size must be positive")
        if self.max_wait_time <= 0:
            raise ValueError("max_wait_time must be positive")


@dataclass
class BatchItem(Generic[T]):
    """Item in a batch with metadata."""
    
    data: T
    added_at: float = field(default_factory=time.time)
    attempts: int = 0
    last_error: Optional[str] = None
    
    def can_retry(self, max_attempts: int) -> bool:
        """Check if item can be retried."""
        return self.attempts < max_attempts


@dataclass
class BatchResult:
    """Result of batch processing."""
    
    batch_id: str
    total_items: int
    successful_items: int
    failed_items: int
    processing_time: float
    errors: List[str] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_items == 0:
            return 0.0
        return (self.successful_items / self.total_items) * 100


class BatchProcessor(Generic[T], LoggerMixin):
    """
    Generic batch processor for optimizing bulk operations.
    
    Supports multiple batching strategies and automatic retry logic
    for failed items.
    """
    
    def __init__(
        self,
        config: BatchConfig,
        processor_func: Callable[[List[T]], Any]
    ):
        self.config = config
        self.processor_func = processor_func
        
        # Batch storage
        self._pending_items: deque[BatchItem[T]] = deque()
        self._processing_batches: Dict[str, List[BatchItem[T]]] = {}
        self._failed_items: deque[BatchItem[T]] = deque()
        
        # Processing control
        self._processing_task: Optional[asyncio.Task] = None
        self._retry_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Statistics
        self._total_processed = 0
        self._total_successful = 0
        self._total_failed = 0
        self._batch_count = 0
        
        # Timing
        self._last_batch_time = time.time()
    
    async def start(self) -> None:
        """Start the batch processor."""
        if self._running:
            return
        
        self._running = True
        self._processing_task = asyncio.create_task(self._processing_loop())
        self._retry_task = asyncio.create_task(self._retry_loop())
        
        self.logger.info(f"Batch processor '{self.config.name}' started")
    
    async def stop(self) -> None:
        """Stop the batch processor and process remaining items."""
        self._running = False
        
        # Process remaining items
        if self._pending_items:
            await self._process_pending_batch()
        
        # Cancel tasks
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        
        if self._retry_task and not self._retry_task.done():
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info(f"Batch processor '{self.config.name}' stopped")
    
    async def add_item(self, item: T) -> None:
        """Add item to batch queue."""
        batch_item = BatchItem(data=item)
        self._pending_items.append(batch_item)
        
        # Check if we should process immediately
        if self.config.strategy == BatchStrategy.IMMEDIATE:
            await self._process_single_item(batch_item)
        elif self.config.strategy == BatchStrategy.SIZE_BASED:
            if len(self._pending_items) >= self.config.max_batch_size:
                await self._process_pending_batch()
    
    async def add_items(self, items: List[T]) -> None:
        """Add multiple items to batch queue."""
        for item in items:
            await self.add_item(item)
    
    async def flush(self) -> None:
        """Process all pending items immediately."""
        if self._pending_items:
            await self._process_pending_batch()
    
    async def _processing_loop(self) -> None:
        """Main processing loop."""
        while self._running:
            try:
                await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
                
                current_time = time.time()
                time_since_last_batch = current_time - self._last_batch_time
                
                should_process = False
                
                if self.config.strategy == BatchStrategy.TIME_BASED:
                    should_process = (
                        self._pending_items and 
                        time_since_last_batch >= self.config.max_wait_time
                    )
                elif self.config.strategy == BatchStrategy.HYBRID:
                    should_process = (
                        self._pending_items and (
                            len(self._pending_items) >= self.config.max_batch_size or
                            time_since_last_batch >= self.config.max_wait_time
                        )
                    )
                
                if should_process:
                    await self._process_pending_batch()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in processing loop: {e}", exc_info=True)
    
    async def _retry_loop(self) -> None:
        """Loop for retrying failed items."""
        while self._running:
            try:
                await asyncio.sleep(self.config.retry_delay)
                
                if self._failed_items:
                    # Move failed items back to pending for retry
                    items_to_retry = []
                    
                    while self._failed_items:
                        item = self._failed_items.popleft()
                        if item.can_retry(self.config.retry_attempts):
                            items_to_retry.append(item)
                        else:
                            self.logger.warning(
                                f"Item exceeded retry attempts: {item.last_error}"
                            )
                    
                    # Add back to pending queue
                    for item in items_to_retry:
                        self._pending_items.append(item)
                    
                    if items_to_retry:
                        self.logger.info(f"Retrying {len(items_to_retry)} failed items")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in retry loop: {e}", exc_info=True)
    
    async def _process_pending_batch(self) -> Optional[BatchResult]:
        """Process current pending items as a batch."""
        if not self._pending_items:
            return None
        
        # Extract items for processing
        batch_items = []
        batch_size = min(len(self._pending_items), self.config.max_batch_size)
        
        for _ in range(batch_size):
            if self._pending_items:
                batch_items.append(self._pending_items.popleft())
        
        if not batch_items:
            return None
        
        return await self._process_batch(batch_items)
    
    async def _process_batch(self, batch_items: List[BatchItem[T]]) -> BatchResult:
        """Process a batch of items."""
        batch_id = f"{self.config.name}_{self._batch_count}"
        self._batch_count += 1
        
        start_time = time.time()
        self._processing_batches[batch_id] = batch_items
        
        try:
            # Extract data from batch items
            data_items = [item.data for item in batch_items]
            
            # Process the batch
            if asyncio.iscoroutinefunction(self.processor_func):
                result = await self.processor_func(data_items)
            else:
                result = self.processor_func(data_items)
            
            # All items successful
            successful_count = len(batch_items)
            failed_count = 0
            errors = []
            
            self._total_processed += len(batch_items)
            self._total_successful += successful_count
            
        except Exception as e:
            # Batch failed, mark all items for retry
            error_msg = str(e)
            errors = [error_msg]
            
            for item in batch_items:
                item.attempts += 1
                item.last_error = error_msg
                
                if item.can_retry(self.config.retry_attempts):
                    self._failed_items.append(item)
                else:
                    self._total_failed += 1
            
            successful_count = 0
            failed_count = len(batch_items)
            
            self._total_processed += len(batch_items)
            
            self.logger.error(f"Batch {batch_id} failed: {error_msg}")
        
        finally:
            # Clean up
            del self._processing_batches[batch_id]
            self._last_batch_time = time.time()
        
        processing_time = time.time() - start_time
        
        result = BatchResult(
            batch_id=batch_id,
            total_items=len(batch_items),
            successful_items=successful_count,
            failed_items=failed_count,
            processing_time=processing_time,
            errors=errors
        )
        
        self.logger.info(
            f"Processed batch {batch_id}: {successful_count}/{len(batch_items)} successful "
            f"in {processing_time:.2f}s"
        )
        
        return result
    
    async def _process_single_item(self, item: BatchItem[T]) -> bool:
        """Process a single item immediately."""
        try:
            if asyncio.iscoroutinefunction(self.processor_func):
                await self.processor_func([item.data])
            else:
                self.processor_func([item.data])
            
            self._total_processed += 1
            self._total_successful += 1
            return True
            
        except Exception as e:
            item.attempts += 1
            item.last_error = str(e)
            
            if item.can_retry(self.config.retry_attempts):
                self._failed_items.append(item)
            else:
                self._total_failed += 1
            
            self._total_processed += 1
            self.logger.error(f"Failed to process single item: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get batch processor statistics."""
        success_rate = 0.0
        if self._total_processed > 0:
            success_rate = (self._total_successful / self._total_processed) * 100
        
        return {
            "name": self.config.name,
            "total_processed": self._total_processed,
            "total_successful": self._total_successful,
            "total_failed": self._total_failed,
            "success_rate": success_rate,
            "pending_items": len(self._pending_items),
            "failed_items": len(self._failed_items),
            "processing_batches": len(self._processing_batches),
            "batch_count": self._batch_count,
            "config": {
                "max_batch_size": self.config.max_batch_size,
                "max_wait_time": self.config.max_wait_time,
                "strategy": self.config.strategy.value,
                "retry_attempts": self.config.retry_attempts
            }
        }


class NotificationBatchProcessor(BatchProcessor[Dict[str, Any]]):
    """Specialized batch processor for notifications."""
    
    def __init__(self, notification_sender: Callable):
        config = BatchConfig(
            name="notifications",
            max_batch_size=50,
            max_wait_time=10.0,
            strategy=BatchStrategy.HYBRID,
            retry_attempts=3,
            retry_delay=5.0
        )
        
        super().__init__(config, self._process_notification_batch)
        self.notification_sender = notification_sender
    
    async def _process_notification_batch(self, notifications: List[Dict[str, Any]]) -> None:
        """Process a batch of notifications."""
        # Group notifications by type and channel for efficiency
        grouped = defaultdict(list)
        
        for notification in notifications:
            key = (
                notification.get('notification_type'),
                notification.get('channel_preference', 'BOTH')
            )
            grouped[key].append(notification)
        
        # Process each group
        for (notif_type, channel_pref), group in grouped.items():
            try:
                await self.notification_sender(group)
                self.logger.debug(f"Sent batch of {len(group)} {notif_type} notifications")
            except Exception as e:
                self.logger.error(f"Failed to send notification batch: {e}")
                raise  # Re-raise to trigger retry logic


class DatabaseBatchProcessor(BatchProcessor[Dict[str, Any]]):
    """Specialized batch processor for database operations."""
    
    def __init__(self, database_manager, operation_type: str = "insert"):
        config = BatchConfig(
            name=f"database_{operation_type}",
            max_batch_size=100,
            max_wait_time=2.0,
            strategy=BatchStrategy.HYBRID,
            retry_attempts=2,
            retry_delay=1.0
        )
        
        super().__init__(config, self._process_database_batch)
        self.database = database_manager
        self.operation_type = operation_type
    
    async def _process_database_batch(self, operations: List[Dict[str, Any]]) -> None:
        """Process a batch of database operations."""
        if self.operation_type == "insert":
            await self._process_insert_batch(operations)
        elif self.operation_type == "update":
            await self._process_update_batch(operations)
        elif self.operation_type == "delete":
            await self._process_delete_batch(operations)
        else:
            raise ValueError(f"Unsupported operation type: {self.operation_type}")
    
    async def _process_insert_batch(self, operations: List[Dict[str, Any]]) -> None:
        """Process batch insert operations."""
        # Group by collection
        collections = defaultdict(list)
        
        for op in operations:
            collection = op.get('collection')
            document = op.get('document')
            if collection and document:
                collections[collection].append(document)
        
        # Perform batch inserts
        for collection, documents in collections.items():
            try:
                await self.database[collection].insert_many(documents)
                self.logger.debug(f"Batch inserted {len(documents)} documents to {collection}")
            except Exception as e:
                self.logger.error(f"Batch insert failed for {collection}: {e}")
                raise
    
    async def _process_update_batch(self, operations: List[Dict[str, Any]]) -> None:
        """Process batch update operations."""
        # Group by collection
        collections = defaultdict(list)
        
        for op in operations:
            collection = op.get('collection')
            filter_dict = op.get('filter')
            update_dict = op.get('update')
            if collection and filter_dict and update_dict:
                collections[collection].append({
                    'filter': filter_dict,
                    'update': update_dict
                })
        
        # Perform batch updates
        for collection, updates in collections.items():
            try:
                # Use bulk write for efficiency
                from pymongo import UpdateOne
                requests = [
                    UpdateOne(update['filter'], update['update'])
                    for update in updates
                ]
                
                result = await self.database[collection].bulk_write(requests)
                self.logger.debug(
                    f"Batch updated {result.modified_count}/{len(updates)} documents in {collection}"
                )
            except Exception as e:
                self.logger.error(f"Batch update failed for {collection}: {e}")
                raise
    
    async def _process_delete_batch(self, operations: List[Dict[str, Any]]) -> None:
        """Process batch delete operations."""
        # Group by collection
        collections = defaultdict(list)
        
        for op in operations:
            collection = op.get('collection')
            filter_dict = op.get('filter')
            if collection and filter_dict:
                collections[collection].append(filter_dict)
        
        # Perform batch deletes
        for collection, filters in collections.items():
            try:
                # Use bulk write for efficiency
                from pymongo import DeleteOne
                requests = [DeleteOne(filter_dict) for filter_dict in filters]
                
                result = await self.database[collection].bulk_write(requests)
                self.logger.debug(
                    f"Batch deleted {result.deleted_count}/{len(filters)} documents from {collection}"
                )
            except Exception as e:
                self.logger.error(f"Batch delete failed for {collection}: {e}")
                raise


class BatchProcessorManager(LoggerMixin):
    """Manager for multiple batch processors."""
    
    def __init__(self):
        self._processors: Dict[str, BatchProcessor] = {}
        self._running = False
    
    async def start(self) -> None:
        """Start all batch processors."""
        if self._running:
            return
        
        self._running = True
        
        for processor in self._processors.values():
            await processor.start()
        
        self.logger.info(f"Started {len(self._processors)} batch processors")
    
    async def stop(self) -> None:
        """Stop all batch processors."""
        self._running = False
        
        for processor in self._processors.values():
            await processor.stop()
        
        self.logger.info("Stopped all batch processors")
    
    def add_processor(self, name: str, processor: BatchProcessor) -> None:
        """Add a batch processor."""
        self._processors[name] = processor
        
        if self._running:
            asyncio.create_task(processor.start())
    
    def get_processor(self, name: str) -> Optional[BatchProcessor]:
        """Get a batch processor by name."""
        return self._processors.get(name)
    
    def remove_processor(self, name: str) -> bool:
        """Remove a batch processor."""
        if name in self._processors:
            processor = self._processors.pop(name)
            if self._running:
                asyncio.create_task(processor.stop())
            return True
        return False
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all processors."""
        return {
            name: processor.get_stats()
            for name, processor in self._processors.items()
        }