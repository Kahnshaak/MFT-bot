"""
Simple database manager for MongoDB operations.
"""

from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

import motor.motor_asyncio
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

try:
    from utils.logging_config import get_logger
    from utils.exceptions import DatabaseConnectionError, DatabaseError
except ImportError:
    from src.utils.logging_config import get_logger
    from src.utils.exceptions import DatabaseConnectionError, DatabaseError


class DatabaseManager:
    """
    Simple MongoDB database manager.
    """
    
    def __init__(self, connection_url: str):
        self.connection_url = connection_url
        self.client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
        self.database: Optional[motor.motor_asyncio.AsyncIOMotorDatabase] = None
        self._connected = False
        self.logger = get_logger(__name__)
        
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
            self.logger.info(f"Connecting to MongoDB database: {self.database_name}")
            
            # Create client
            self.client = motor.motor_asyncio.AsyncIOMotorClient(self.connection_url)
            
            # Get database
            self.database = self.client[self.database_name]
            
            # Test connection
            await self.client.admin.command('ping')
            
            self._connected = True
            self.logger.info("Successfully connected to MongoDB")
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            self.logger.error(f"Failed to connect to MongoDB: {str(e)}")
            raise DatabaseConnectionError(f"Failed to connect to MongoDB: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error connecting to MongoDB: {str(e)}")
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
    
    # Basic CRUD operations
    
    async def insert_one(self, collection: str, document: Dict[str, Any]) -> str:
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
            return str(result.inserted_id)
        except Exception as e:
            self.logger.error(f"Failed to insert document in {collection}: {str(e)}")
            raise DatabaseError(f"Insert operation failed: {str(e)}")
    
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
            return await self.database[collection].find_one(filter_dict, projection)
        except Exception as e:
            self.logger.error(f"Failed to find document in {collection}: {str(e)}")
            raise DatabaseError(f"Find operation failed: {str(e)}")
    
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
            
            return await cursor.to_list(length=limit)
        except Exception as e:
            self.logger.error(f"Failed to find documents in {collection}: {str(e)}")
            raise DatabaseError(f"Find operation failed: {str(e)}")
    
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
            return result.modified_count > 0 or result.upserted_id is not None
        except Exception as e:
            self.logger.error(f"Failed to update document in {collection}: {str(e)}")
            raise DatabaseError(f"Update operation failed: {str(e)}")
    
    async def delete_one(self, collection: str, filter_dict: Dict[str, Any]) -> bool:
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
            return result.deleted_count > 0
        except Exception as e:
            self.logger.error(f"Failed to delete document in {collection}: {str(e)}")
            raise DatabaseError(f"Delete operation failed: {str(e)}")
    
    async def count_documents(self, collection: str, filter_dict: Dict[str, Any]) -> int:
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
            return await self.database[collection].count_documents(filter_dict)
        except Exception as e:
            self.logger.error(f"Failed to count documents in {collection}: {str(e)}")
            raise DatabaseError(f"Count operation failed: {str(e)}")