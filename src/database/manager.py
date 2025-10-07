"""
Database manager for MongoDB operations with connection pooling and error handling.
"""

import asyncio
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

import motor.motor_asyncio
from pymongo import IndexModel
from pymongo.errors import (
    ConnectionFailure, 
    ServerSelectionTimeoutError,
    DuplicateKeyError,
    OperationFailure
)

try:
    from utils.logging_config import get_logger, LoggerMixin
    from utils.exceptions import (
        DatabaseConnectionError,
        DatabaseError,
        DocumentNotFoundError,
        GameNightBotException
    )
    from utils.error_handler import retry_on_failure
    from database.query_optimizer import QueryOptimizer, QueryPlan, QueryType
    from core.cache_manager import CacheManager
    from core.batch_processor import DatabaseBatchProcessor
except ImportError:
    from src.utils.logging_config import get_logger, LoggerMixin
    from src.utils.exceptions import (
        DatabaseConnectionError,
        DatabaseError,
        DocumentNotFoundError,
        GameNightBotException
    )
    from src.utils.error_handler import retry_on_failure
    from src.database.query_optimizer import QueryOptimizer, QueryPlan, QueryType
    from src.core.cache_manager import CacheManager
    from src.core.batch_processor import DatabaseBatchProcessor


class DatabaseManager(LoggerMixin):
    """
    MongoDB database manager with connection pooling and error handling.
    """
    
    def __init__(self, connection_url: str, cache_manager: Optional[CacheManager] = None):
        self.connection_url = connection_url
        self.client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
        self.database: Optional[motor.motor_asyncio.AsyncIOMotorDatabase] = None
        self._connected = False
        
        # Parse database name from URL
        parsed_url = urlparse(connection_url)
        self.database_name = parsed_url.path.lstrip('/') or 'gamenight_bot'
        
        # Performance optimizations
        self.cache_manager = cache_manager
        self.query_optimizer: Optional[QueryOptimizer] = None
        self.batch_processors: Dict[str, DatabaseBatchProcessor] = {}
        
        # Connection pool settings (optimized)
        self.pool_settings = {
            'maxPoolSize': 100,  # Increased from 50
            'minPoolSize': 10,   # Increased from 5
            'maxIdleTimeMS': 30000,
            'serverSelectionTimeoutMS': 5000,
            'connectTimeoutMS': 10000,
            'socketTimeoutMS': 20000,
            'retryWrites': True,
            'retryReads': True,
            'readPreference': 'secondaryPreferred'  # Use secondary for reads when possible
        }
    
    async def connect(self) -> None:
        """
        Establish connection to MongoDB.
        
        Raises:
            DatabaseConnectionError: If connection fails
        """
        try:
            self.logger.info("Connecting to MongoDB", database=self.database_name)
            
            # Create client with optimized connection pooling
            self.client = motor.motor_asyncio.AsyncIOMotorClient(
                self.connection_url,
                **self.pool_settings
            )
            
            # Get database
            self.database = self.client[self.database_name]
            
            # Test connection
            await self.client.admin.command('ping')
            
            # Create indexes
            await self._create_indexes()
            
            # Initialize performance optimizations
            await self._initialize_optimizations()
            
            self._connected = True
            self.logger.info("Successfully connected to MongoDB with optimizations enabled")
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            self.logger.error("Failed to connect to MongoDB", error=str(e))
            raise DatabaseConnectionError(f"Failed to connect to MongoDB: {str(e)}")
        except Exception as e:
            self.logger.error("Unexpected error connecting to MongoDB", error=str(e))
            raise DatabaseConnectionError(f"Unexpected database error: {str(e)}")
    
    async def disconnect(self) -> None:
        """Disconnect from MongoDB."""
        # Stop batch processors
        for processor in self.batch_processors.values():
            await processor.stop()
        self.batch_processors.clear()
        
        if self.client:
            self.client.close()
            self._connected = False
            self.logger.info("Disconnected from MongoDB")
    
    @property
    def is_connected(self) -> bool:
        """Check if database is connected."""
        return self._connected and self.client is not None
    
    @property
    def events(self):
        """Events collection."""
        if not self.database:
            raise DatabaseConnectionError("Database not connected")
        return self.database.events
    
    @property
    def users(self):
        """Users collection."""
        if not self.database:
            raise DatabaseConnectionError("Database not connected")
        return self.database.users
    
    @property
    def notifications(self):
        """Notifications collection."""
        if not self.database:
            raise DatabaseConnectionError("Database not connected")
        return self.database.notifications
    
    @property
    def recurring_schedules(self):
        """Recurring schedules collection."""
        if not self.database:
            raise DatabaseConnectionError("Database not connected")
        return self.database.recurring_schedules
    
    @property
    def game_interests(self):
        """Game interests collection."""
        if not self.database:
            raise DatabaseConnectionError("Database not connected")
        return self.database.game_interests
    
    @property
    def guild_configs(self):
        """Guild configurations collection."""
        if not self.database:
            raise DatabaseConnectionError("Database not connected")
        return self.database.guild_configs
    
    @property
    def audit_logs(self):
        """Audit logs collection."""
        if not self.database:
            raise DatabaseConnectionError("Database not connected")
        return self.database.audit_logs
    
    @retry_on_failure(max_attempts=3, delay=1.0)
    async def ping(self) -> bool:
        """
        Ping the database to check connectivity.
        
        Returns:
            True if ping successful, False otherwise
        """
        try:
            if not self.client:
                return False
            
            await self.client.admin.command('ping')
            return True
        except Exception as e:
            self.logger.warning("Database ping failed", error=str(e))
            return False
    
    async def test_connection(self) -> bool:
        """
        Test database connection with a simple query.
        
        Returns:
            True if test successful, False otherwise
        """
        try:
            if not self.database:
                return False
            
            # Simple test query
            await self.database.events.count_documents({})
            return True
        except Exception as e:
            self.logger.warning("Database test query failed", error=str(e))
            return False
    
    async def _create_indexes(self) -> None:
        """Create database indexes for optimal performance."""
        try:
            # Events collection indexes
            events_indexes = [
                IndexModel([("guild_id", 1), ("state", 1), ("created_at", -1)]),
                IndexModel([("guild_id", 1), ("discord_event_id", 1)]),
                IndexModel([("guild_id", 1), ("schedule.selected_date", 1)]),
                IndexModel([("creator_id", 1), ("created_at", -1)])
            ]
            await self.database.events.create_indexes(events_indexes)
            
            # Users collection indexes
            users_indexes = [
                IndexModel([("user_id", 1), ("guild_id", 1)], unique=True),
                IndexModel([("guild_id", 1), ("game_interests", 1)])
            ]
            await self.database.users.create_indexes(users_indexes)
            
            # Notifications collection indexes
            notifications_indexes = [
                IndexModel([("scheduled_for", 1), ("processed", 1)]),
                IndexModel([("guild_id", 1), ("user_id", 1)]),
                IndexModel([("event_id", 1)])
            ]
            await self.database.notifications.create_indexes(notifications_indexes)
            
            # Recurring schedules indexes
            recurring_indexes = [
                IndexModel([("guild_id", 1), ("status", 1)]),
                IndexModel([("next_trigger", 1)]),
                IndexModel([("creator_id", 1), ("created_at", -1)])
            ]
            await self.database.recurring_schedules.create_indexes(recurring_indexes)
            
            # Game interests indexes
            game_interests_indexes = [
                IndexModel([("guild_id", 1), ("game_name", 1)]),
                IndexModel([("user_id", 1), ("guild_id", 1)])
            ]
            await self.database.game_interests.create_indexes(game_interests_indexes)
            
            # Guild configs indexes
            guild_configs_indexes = [
                IndexModel([("guild_id", 1)], unique=True)
            ]
            await self.database.guild_configs.create_indexes(guild_configs_indexes)
            
            # Audit logs indexes
            audit_logs_indexes = [
                IndexModel([("guild_id", 1), ("timestamp", -1)]),
                IndexModel([("action_type", 1), ("timestamp", -1)]),
                IndexModel([("user_id", 1), ("timestamp", -1)])
            ]
            await self.database.audit_logs.create_indexes(audit_logs_indexes)
            
            self.logger.info("Database indexes created successfully")
            
        except Exception as e:
            self.logger.error("Failed to create database indexes", error=str(e))
            # Don't raise exception here as indexes are not critical for basic operation
    
    async def _initialize_optimizations(self) -> None:
        """Initialize performance optimizations."""
        try:
            # Initialize query optimizer
            self.query_optimizer = QueryOptimizer(self.database, self.cache_manager)
            
            # Initialize batch processors
            self.batch_processors['insert'] = DatabaseBatchProcessor(self, 'insert')
            self.batch_processors['update'] = DatabaseBatchProcessor(self, 'update')
            self.batch_processors['delete'] = DatabaseBatchProcessor(self, 'delete')
            
            # Start batch processors
            for processor in self.batch_processors.values():
                await processor.start()
            
            self.logger.info("Database optimizations initialized")
            
        except Exception as e:
            self.logger.error("Failed to initialize database optimizations", error=str(e))
    
    # Optimized CRUD operations
    
    async def insert_one(
        self, 
        collection: str, 
        document: Dict[str, Any],
        use_batch: bool = False
    ) -> str:
        """
        Insert a single document.
        
        Args:
            collection: Collection name
            document: Document to insert
            use_batch: Whether to use batch processing
            
        Returns:
            Inserted document ID as string
            
        Raises:
            DatabaseError: If insertion fails
        """
        try:
            if use_batch and 'insert' in self.batch_processors:
                # Add to batch processor
                await self.batch_processors['insert'].add_item({
                    'collection': collection,
                    'document': document
                })
                # For batched operations, we can't return the actual ID immediately
                return "batched"
            else:
                # Direct insertion with query optimizer
                if self.query_optimizer:
                    query_plan = QueryPlan(
                        query_type=QueryType.INSERT,
                        collection=collection,
                        filter_dict={'document': document}
                    )
                    return await self.query_optimizer.execute_query(query_plan)
                else:
                    # Fallback to direct operation
                    result = await self.database[collection].insert_one(document)
                    self.logger.debug(
                        "Inserted document",
                        collection=collection,
                        document_id=str(result.inserted_id)
                    )
                    return str(result.inserted_id)
                    
        except DuplicateKeyError as e:
            raise DatabaseError(f"Duplicate key error: {str(e)}", operation="insert_one")
        except Exception as e:
            self.logger.error(
                "Failed to insert document",
                collection=collection,
                error=str(e)
            )
            raise DatabaseError(f"Insert operation failed: {str(e)}", operation="insert_one")
    
    async def find_one(
        self, 
        collection: str, 
        filter_dict: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Find a single document with caching and optimization.
        
        Args:
            collection: Collection name
            filter_dict: Query filter
            projection: Optional field projection
            
        Returns:
            Document if found, None otherwise
            
        Raises:
            DatabaseError: If query fails
        """
        try:
            if self.query_optimizer:
                query_plan = QueryPlan(
                    query_type=QueryType.FIND_ONE,
                    collection=collection,
                    filter_dict=filter_dict,
                    projection=projection
                )
                return await self.query_optimizer.execute_query(query_plan)
            else:
                # Fallback to direct operation
                result = await self.database[collection].find_one(filter_dict, projection)
                return result
        except Exception as e:
            self.logger.error(
                "Failed to find document",
                collection=collection,
                filter=filter_dict,
                error=str(e)
            )
            raise DatabaseError(f"Find operation failed: {str(e)}", operation="find_one")
    
    async def find_many(
        self, 
        collection: str, 
        filter_dict: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None,
        sort: Optional[List[tuple]] = None,
        limit: Optional[int] = None,
        skip: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Find multiple documents with caching and optimization.
        
        Args:
            collection: Collection name
            filter_dict: Query filter
            projection: Optional field projection
            sort: Optional sort specification
            limit: Optional limit on results
            skip: Optional number of documents to skip
            
        Returns:
            List of matching documents
            
        Raises:
            DatabaseError: If query fails
        """
        try:
            if self.query_optimizer:
                query_plan = QueryPlan(
                    query_type=QueryType.FIND,
                    collection=collection,
                    filter_dict=filter_dict,
                    projection=projection,
                    sort=sort,
                    limit=limit,
                    skip=skip
                )
                return await self.query_optimizer.execute_query(query_plan)
            else:
                # Fallback to direct operation
                cursor = self.database[collection].find(filter_dict, projection)
                
                if sort:
                    cursor = cursor.sort(sort)
                if skip:
                    cursor = cursor.skip(skip)
                if limit:
                    cursor = cursor.limit(limit)
                
                results = await cursor.to_list(length=limit)
                return results
        except Exception as e:
            self.logger.error(
                "Failed to find documents",
                collection=collection,
                filter=filter_dict,
                error=str(e)
            )
            raise DatabaseError(f"Find operation failed: {str(e)}", operation="find_many")
    
    async def update_one(
        self, 
        collection: str, 
        filter_dict: Dict[str, Any],
        update_dict: Dict[str, Any],
        upsert: bool = False
    ) -> bool:
        """
        Update a single document.
        
        Args:
            collection: Collection name
            filter_dict: Query filter
            update_dict: Update operations
            upsert: Whether to insert if document doesn't exist
            
        Returns:
            True if document was modified, False otherwise
            
        Raises:
            DatabaseError: If update fails
        """
        try:
            result = await self.database[collection].update_one(
                filter_dict, 
                update_dict, 
                upsert=upsert
            )
            
            self.logger.debug(
                "Updated document",
                collection=collection,
                matched_count=result.matched_count,
                modified_count=result.modified_count,
                upserted_id=str(result.upserted_id) if result.upserted_id else None
            )
            
            return result.modified_count > 0 or result.upserted_id is not None
        except Exception as e:
            self.logger.error(
                "Failed to update document",
                collection=collection,
                filter=filter_dict,
                error=str(e)
            )
            raise DatabaseError(f"Update operation failed: {str(e)}", operation="update_one")
    
    async def delete_one(
        self, 
        collection: str, 
        filter_dict: Dict[str, Any]
    ) -> bool:
        """
        Delete a single document.
        
        Args:
            collection: Collection name
            filter_dict: Query filter
            
        Returns:
            True if document was deleted, False otherwise
            
        Raises:
            DatabaseError: If deletion fails
        """
        try:
            result = await self.database[collection].delete_one(filter_dict)
            
            self.logger.debug(
                "Deleted document",
                collection=collection,
                deleted_count=result.deleted_count
            )
            
            return result.deleted_count > 0
        except Exception as e:
            self.logger.error(
                "Failed to delete document",
                collection=collection,
                filter=filter_dict,
                error=str(e)
            )
            raise DatabaseError(f"Delete operation failed: {str(e)}", operation="delete_one")
    
    async def count_documents(
        self, 
        collection: str, 
        filter_dict: Dict[str, Any]
    ) -> int:
        """
        Count documents matching filter.
        
        Args:
            collection: Collection name
            filter_dict: Query filter
            
        Returns:
            Number of matching documents
            
        Raises:
            DatabaseError: If count fails
        """
        try:
            count = await self.database[collection].count_documents(filter_dict)
            return count
        except Exception as e:
            self.logger.error(
                "Failed to count documents",
                collection=collection,
                filter=filter_dict,
                error=str(e)
            )
            raise DatabaseError(f"Count operation failed: {str(e)}", operation="count_documents")
    
    async def aggregate(
        self, 
        collection: str, 
        pipeline: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Run aggregation pipeline.
        
        Args:
            collection: Collection name
            pipeline: Aggregation pipeline
            
        Returns:
            Aggregation results
            
        Raises:
            DatabaseError: If aggregation fails
        """
        try:
            cursor = self.database[collection].aggregate(pipeline)
            results = await cursor.to_list(length=None)
            return results
        except Exception as e:
            self.logger.error(
                "Failed to run aggregation",
                collection=collection,
                error=str(e)
            )
            raise DatabaseError(f"Aggregation failed: {str(e)}", operation="aggregate")
    
    # Performance monitoring and optimization methods
    
    async def get_performance_stats(self) -> Dict[str, Any]:
        """Get database performance statistics."""
        stats = {
            'connection_pool': await self._get_connection_pool_stats(),
            'query_stats': {},
            'batch_stats': {},
            'cache_stats': {},
            'slow_queries': [],
            'index_recommendations': {}
        }
        
        if self.query_optimizer:
            stats['query_stats'] = self.query_optimizer.get_query_stats()
            stats['slow_queries'] = self.query_optimizer.get_slow_queries()
            stats['index_recommendations'] = self.query_optimizer.get_index_recommendations()
        
        if self.batch_processors:
            stats['batch_stats'] = {
                name: processor.get_stats()
                for name, processor in self.batch_processors.items()
            }
        
        if self.cache_manager:
            stats['cache_stats'] = self.cache_manager.get_stats()
        
        return stats
    
    async def _get_connection_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        if not self.client:
            return {}
        
        try:
            # Get server status for connection info
            server_status = await self.client.admin.command('serverStatus')
            connections = server_status.get('connections', {})
            
            return {
                'current': connections.get('current', 0),
                'available': connections.get('available', 0),
                'total_created': connections.get('totalCreated', 0),
                'active': connections.get('active', 0)
            }
        except Exception as e:
            self.logger.warning(f"Failed to get connection pool stats: {e}")
            return {}
    
    async def optimize_queries(self) -> Dict[str, Any]:
        """Run query optimization analysis."""
        if not self.query_optimizer:
            return {'error': 'Query optimizer not available'}
        
        # Create recommended indexes
        index_results = await self.query_optimizer.create_recommended_indexes()
        
        # Get performance recommendations
        stats = self.query_optimizer.get_query_stats()
        slow_queries = self.query_optimizer.get_slow_queries(limit=10)
        
        return {
            'indexes_created': index_results,
            'slow_queries_count': len(slow_queries),
            'total_queries': sum(stat['execution_count'] for stat in stats.values()),
            'avg_query_time': sum(stat['avg_time'] for stat in stats.values()) / len(stats) if stats else 0
        }
    
    async def flush_batches(self) -> Dict[str, Any]:
        """Flush all pending batch operations."""
        results = {}
        
        for name, processor in self.batch_processors.items():
            try:
                await processor.flush()
                results[name] = 'flushed'
            except Exception as e:
                results[name] = f'error: {str(e)}'
        
        return results
    
    async def clear_cache(self, pattern: str = None) -> int:
        """Clear database cache."""
        if not self.query_optimizer:
            return 0
        
        return await self.query_optimizer.invalidate_cache(pattern)
    
    async def get_collection_stats(self, collection: str) -> Dict[str, Any]:
        """Get statistics for a specific collection."""
        try:
            stats = await self.database.command('collStats', collection)
            
            return {
                'count': stats.get('count', 0),
                'size': stats.get('size', 0),
                'avg_obj_size': stats.get('avgObjSize', 0),
                'storage_size': stats.get('storageSize', 0),
                'indexes': stats.get('nindexes', 0),
                'index_size': stats.get('totalIndexSize', 0)
            }
        except Exception as e:
            self.logger.error(f"Failed to get collection stats for {collection}: {e}")
            return {}
    
    async def analyze_collection_performance(self, collection: str) -> Dict[str, Any]:
        """Analyze performance for a specific collection."""
        stats = await self.get_collection_stats(collection)
        
        # Get query stats for this collection
        query_stats = {}
        if self.query_optimizer:
            all_stats = self.query_optimizer.get_query_stats()
            query_stats = {
                key: value for key, value in all_stats.items()
                if value['collection'] == collection
            }
        
        # Performance recommendations
        recommendations = []
        
        if stats.get('count', 0) > 10000 and stats.get('indexes', 0) < 3:
            recommendations.append("Consider adding more indexes for large collection")
        
        if stats.get('avg_obj_size', 0) > 16000:  # 16KB
            recommendations.append("Large document size detected - consider document restructuring")
        
        return {
            'collection_stats': stats,
            'query_stats': query_stats,
            'recommendations': recommendations
        }