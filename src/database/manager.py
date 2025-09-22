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

from src.utils.logging_config import get_logger, LoggerMixin
from src.utils.exceptions import (
    DatabaseConnectionError,
    DatabaseError,
    DocumentNotFoundError,
    GameNightBotException
)
from src.utils.error_handler import retry_on_failure


class DatabaseManager(LoggerMixin):
    """
    MongoDB database manager with connection pooling and error handling.
    """
    
    def __init__(self, connection_url: str):
        self.connection_url = connection_url
        self.client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
        self.database: Optional[motor.motor_asyncio.AsyncIOMotorDatabase] = None
        self._connected = False
        
        # Parse database name from URL
        parsed_url = urlparse(connection_url)
        self.database_name = parsed_url.path.lstrip('/') or 'gamenight_bot'
    
    async def connect(self) -> None:
        """
        Establish connection to MongoDB.
        
        Raises:
            DatabaseConnectionError: If connection fails
        """
        try:
            self.logger.info("Connecting to MongoDB", database=self.database_name)
            
            # Create client with connection pooling
            self.client = motor.motor_asyncio.AsyncIOMotorClient(
                self.connection_url,
                maxPoolSize=50,
                minPoolSize=5,
                maxIdleTimeMS=30000,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=20000
            )
            
            # Get database
            self.database = self.client[self.database_name]
            
            # Test connection
            await self.client.admin.command('ping')
            
            # Create indexes
            await self._create_indexes()
            
            self._connected = True
            self.logger.info("Successfully connected to MongoDB")
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            self.logger.error("Failed to connect to MongoDB", error=str(e))
            raise DatabaseConnectionError(f"Failed to connect to MongoDB: {str(e)}")
        except Exception as e:
            self.logger.error("Unexpected error connecting to MongoDB", error=str(e))
            raise DatabaseConnectionError(f"Unexpected database error: {str(e)}")
    
    async def disconnect(self) -> None:
        """Disconnect from MongoDB."""
        if self.client:
            self.client.close()
            self._connected = False
            self.logger.info("Disconnected from MongoDB")
    
    @property
    def is_connected(self) -> bool:
        """Check if database is connected."""
        return self._connected and self.client is not None
    
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
                IndexModel([("guild_id", 1), ("status.is_active", 1)]),
                IndexModel([("status.next_trigger", 1)])
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
    
    # Generic CRUD operations
    
    async def insert_one(
        self, 
        collection: str, 
        document: Dict[str, Any]
    ) -> str:
        """
        Insert a single document.
        
        Args:
            collection: Collection name
            document: Document to insert
            
        Returns:
            Inserted document ID as string
            
        Raises:
            DatabaseError: If insertion fails
        """
        try:
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
        Find a single document.
        
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
        Find multiple documents.
        
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