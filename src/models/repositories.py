"""
Simple data access layer with repository pattern for database operations.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Type, TypeVar, Generic, Any
from bson import ObjectId

try:
    from database.manager import DatabaseManager
    from utils.exceptions import DatabaseError
    from utils.logging_config import get_logger
except ImportError:
    from src.database.manager import DatabaseManager
    from src.utils.exceptions import DatabaseError
    from src.utils.logging_config import get_logger

from .base import BaseDocument
from .event import Event
from .user import User, GameInterest
from .recurring import RecurringSchedule, ScheduleStatus
from .guild import GuildConfig
from .game import Game

T = TypeVar('T', bound=BaseDocument)


class BaseRepository(Generic[T], ABC):
    """
    Base repository class providing common CRUD operations.
    """
    
    def __init__(self, db_manager: DatabaseManager, model_class: Type[T]):
        self.db = db_manager
        self.model_class = model_class
        self.collection_name = self._get_collection_name()
        self.logger = get_logger(__name__)
    
    @abstractmethod
    def _get_collection_name(self) -> str:
        """Get the collection name for this repository."""
        pass
    
    async def create(self, document: T) -> str:
        """Create a new document."""
        try:
            document.validate_data()
            data = document.to_dict()
            
            # Remove None _id if present
            if '_id' in data and data['_id'] is None:
                del data['_id']
            
            return await self.db.insert_one(self.collection_name, data)
        except Exception as e:
            self.logger.error(f"Failed to create {self.model_class.__name__}: {str(e)}")
            raise DatabaseError(f"Failed to create {self.model_class.__name__}: {str(e)}")
    
    async def get_by_id(self, document_id: str) -> Optional[T]:
        """Get document by ID."""
        try:
            data = await self.db.find_one(self.collection_name, {"_id": ObjectId(document_id)})
            return self.model_class.from_dict(data) if data else None
        except Exception as e:
            self.logger.error(f"Failed to get {self.model_class.__name__}: {str(e)}")
            raise DatabaseError(f"Failed to get {self.model_class.__name__}: {str(e)}")
    
    async def update(self, document_id: str, document: T) -> bool:
        """Update document by ID."""
        try:
            document.validate_data()
            data = document.to_dict()
            
            # Remove _id from update data
            if '_id' in data:
                del data['_id']
            
            return await self.db.update_one(
                self.collection_name,
                {"_id": ObjectId(document_id)},
                {"$set": data}
            )
        except Exception as e:
            self.logger.error(f"Failed to update {self.model_class.__name__}: {str(e)}")
            raise DatabaseError(f"Failed to update {self.model_class.__name__}: {str(e)}")
    
    async def delete(self, document_id: str) -> bool:
        """Delete document by ID."""
        try:
            return await self.db.delete_one(self.collection_name, {"_id": ObjectId(document_id)})
        except Exception as e:
            self.logger.error(f"Failed to delete {self.model_class.__name__}: {str(e)}")
            raise DatabaseError(f"Failed to delete {self.model_class.__name__}: {str(e)}")
    
    async def find(
        self,
        filter_dict: Dict[str, Any],
        limit: Optional[int] = None,
        skip: Optional[int] = None,
        sort: Optional[List[tuple]] = None
    ) -> List[T]:
        """Find documents matching filter."""
        try:
            results = await self.db.find_many(
                self.collection_name,
                filter_dict,
                limit=limit,
                skip=skip,
                sort=sort
            )
            return [self.model_class.from_dict(data) for data in results]
        except Exception as e:
            self.logger.error(f"Failed to find {self.model_class.__name__}: {str(e)}")
            raise DatabaseError(f"Failed to find {self.model_class.__name__}: {str(e)}")
    
    async def count(self, filter_dict: Dict[str, Any]) -> int:
        """Count documents matching filter."""
        try:
            return await self.db.count_documents(self.collection_name, filter_dict)
        except Exception as e:
            self.logger.error(f"Failed to count {self.model_class.__name__}: {str(e)}")
            raise DatabaseError(f"Failed to count {self.model_class.__name__}: {str(e)}")


class EventRepository(BaseRepository[Event]):
    """Repository for Event documents."""
    
    def _get_collection_name(self) -> str:
        return "events"
    
    async def get_by_guild(self, guild_id: str, limit: Optional[int] = None) -> List[Event]:
        """Get events for a guild."""
        return await self.find({"guild_id": guild_id}, limit=limit, sort=[("created_at", -1)])
    
    async def get_by_creator(self, creator_id: str, guild_id: str) -> List[Event]:
        """Get events created by a user."""
        return await self.find({"creator_id": creator_id, "guild_id": guild_id}, sort=[("created_at", -1)])
    
    # RSVP functionality removed in simplified Event model
    # async def add_rsvp(self, event_id: str, user_id: str, status: str) -> bool:
    #     """Add or update RSVP for an event."""
    #     try:
    #         rsvp_data = {"user_id": user_id, "status": status}
    #         return await self.db.update_one(
    #             self.collection_name,
    #             {"_id": ObjectId(event_id)},
    #             {"$set": {f"rsvps.{user_id}": rsvp_data, "updated_at": datetime.utcnow()}}
    #         )
    #     except Exception as e:
    #         self.logger.error(f"Failed to add RSVP: {str(e)}")
    #         raise DatabaseError(f"Failed to add RSVP: {str(e)}")


class UserRepository(BaseRepository[User]):
    """Repository for User documents."""
    
    def _get_collection_name(self) -> str:
        return "users"
    
    async def get_by_user_and_guild(self, user_id: str, guild_id: str) -> Optional[User]:
        """Get user by Discord user ID and guild ID."""
        results = await self.find({"user_id": user_id, "guild_id": guild_id})
        return results[0] if results else None
    
    async def get_by_guild(self, guild_id: str) -> List[User]:
        """Get all users in a guild."""
        return await self.find({"guild_id": guild_id})
    
    async def get_users_interested_in_game(self, guild_id: str, game_name: str) -> List[User]:
        """Get users interested in a specific game."""
        filter_dict = {
            "guild_id": guild_id,
            "game_interests.game_name": {"$regex": f"^{game_name}$", "$options": "i"},
            "game_interests.notification_enabled": True
        }
        return await self.find(filter_dict)


class RecurringScheduleRepository(BaseRepository[RecurringSchedule]):
    """Repository for RecurringSchedule documents."""
    
    def _get_collection_name(self) -> str:
        return "recurring_schedules"
    
    async def get_by_guild(self, guild_id: str) -> List[RecurringSchedule]:
        """Get recurring schedules for a guild."""
        return await self.find({"guild_id": guild_id}, sort=[("created_at", -1)])
    
    async def get_active_schedules(self) -> List[RecurringSchedule]:
        """Get all active schedules."""
        return await self.find({"status": ScheduleStatus.ACTIVE.value})


class GuildConfigRepository(BaseRepository[GuildConfig]):
    """Repository for GuildConfig documents."""
    
    def _get_collection_name(self) -> str:
        return "guild_configs"
    
    async def get_by_guild_id(self, guild_id: str) -> Optional[GuildConfig]:
        """Get guild configuration by guild ID."""
        results = await self.find({"guild_id": guild_id})
        return results[0] if results else None
    
    async def create_default_config(self, guild_id: str, guild_name: str = None) -> str:
        """Create default configuration for a new guild."""
        config = GuildConfig(guild_id=guild_id, guild_name=guild_name)
        return await self.create(config)


class GameRepository(BaseRepository[Game]):
    """Repository for Game documents."""
    
    def _get_collection_name(self) -> str:
        return "games"
    
    async def get_by_guild(self, guild_id: str) -> List[Game]:
        """Get games for a guild."""
        return await self.find({"guild_id": guild_id, "is_active": True}, sort=[("name", 1)])
    
    async def get_by_name(self, guild_id: str, name: str) -> Optional[Game]:
        """Get game by exact name match."""
        results = await self.find({
            "guild_id": guild_id,
            "name": {"$regex": f"^{name}$", "$options": "i"}
        })
        return results[0] if results else None


class RepositoryManager:
    """
    Manager class for all repositories.
    
    Provides centralized access to all data repositories.
    """
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        
        # Initialize repositories
        self.events = EventRepository(db_manager, Event)
        self.users = UserRepository(db_manager, User)
        self.recurring_schedules = RecurringScheduleRepository(db_manager, RecurringSchedule)
        self.guild_configs = GuildConfigRepository(db_manager, GuildConfig)
        self.games = GameRepository(db_manager, Game)
    
    async def ensure_guild_config(self, guild_id: str, guild_name: str = None) -> GuildConfig:
        """
        Ensure guild configuration exists, creating default if needed.
        
        Args:
            guild_id: Discord guild ID
            guild_name: Optional guild name
            
        Returns:
            Guild configuration
        """
        config = await self.guild_configs.get_by_guild_id(guild_id)
        if not config:
            config_id = await self.guild_configs.create_default_config(guild_id, guild_name)
            config = await self.guild_configs.get_by_id(config_id)
        
        return config
    
    async def ensure_user_profile(
        self,
        user_id: str,
        guild_id: str,
        display_name: str = None
    ) -> User:
        """
        Ensure user profile exists, creating default if needed.
        
        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
            display_name: Optional display name
            
        Returns:
            User profile
        """
        user = await self.users.get_by_user_and_guild(user_id, guild_id)
        if not user:
            user = User(
                user_id=user_id,
                guild_id=guild_id,
                display_name=display_name
            )
            user_id_str = await self.users.create(user)
            user = await self.users.get_by_id(user_id_str)
        
        return user