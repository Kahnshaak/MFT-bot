"""
Data access layer with repository pattern for database operations.
"""

from abc import ABC, abstractmethod
from datetime import datetime, date
from typing import Dict, List, Optional, Any, Type, TypeVar, Generic
from bson import ObjectId

try:
    from database.manager import DatabaseManager
    from utils.exceptions import DocumentNotFoundError, DatabaseError
    from utils.logging_config import LoggerMixin
except ImportError:
    from src.database.manager import DatabaseManager
    from src.utils.exceptions import DocumentNotFoundError, DatabaseError
    from src.utils.logging_config import LoggerMixin

from .base import BaseDocument
from .event import Event, EventState, PollType, RSVPStatus
from .user import User, GameInterest, NotificationChannel as UserNotificationChannel
from .recurring import RecurringSchedule, ScheduleStatus, ExecutionStatus
from .guild import GuildConfig, PermissionLevel, NotificationChannelType

T = TypeVar('T', bound=BaseDocument)


class BaseRepository(Generic[T], LoggerMixin, ABC):
    """
    Base repository class providing common CRUD operations.
    """
    
    def __init__(self, db_manager: DatabaseManager, model_class: Type[T]):
        self.db = db_manager
        self.model_class = model_class
        self.collection_name = self._get_collection_name()
    
    @abstractmethod
    def _get_collection_name(self) -> str:
        """Get the collection name for this repository."""
        pass
    
    async def create(self, document: T) -> str:
        """
        Create a new document.
        
        Args:
            document: Document to create
            
        Returns:
            Created document ID
            
        Raises:
            DatabaseError: If creation fails
        """
        try:
            document.validate_data()
            data = document.to_dict()
            
            # Remove None _id if present
            if '_id' in data and data['_id'] is None:
                del data['_id']
            
            document_id = await self.db.insert_one(self.collection_name, data)
            
            self.logger.info(
                "Created document",
                collection=self.collection_name,
                document_id=document_id
            )
            
            return document_id
        except Exception as e:
            self.logger.error(
                "Failed to create document",
                collection=self.collection_name,
                error=str(e)
            )
            raise DatabaseError(f"Failed to create {self.model_class.__name__}: {str(e)}")
    
    async def get_by_id(self, document_id: str) -> Optional[T]:
        """
        Get document by ID.
        
        Args:
            document_id: Document ID
            
        Returns:
            Document if found, None otherwise
        """
        try:
            data = await self.db.find_one(
                self.collection_name,
                {"_id": ObjectId(document_id)}
            )
            
            if data:
                return self.model_class.from_dict(data)
            return None
        except Exception as e:
            self.logger.error(
                "Failed to get document by ID",
                collection=self.collection_name,
                document_id=document_id,
                error=str(e)
            )
            raise DatabaseError(f"Failed to get {self.model_class.__name__}: {str(e)}")
    
    async def update(self, document_id: str, document: T) -> bool:
        """
        Update document by ID.
        
        Args:
            document_id: Document ID
            document: Updated document
            
        Returns:
            True if updated, False if not found
        """
        try:
            document.validate_data()
            document.update_timestamp()
            
            data = document.to_dict()
            # Remove _id from update data
            if '_id' in data:
                del data['_id']
            
            result = await self.db.update_one(
                self.collection_name,
                {"_id": ObjectId(document_id)},
                {"$set": data}
            )
            
            if result:
                self.logger.info(
                    "Updated document",
                    collection=self.collection_name,
                    document_id=document_id
                )
            
            return result
        except Exception as e:
            self.logger.error(
                "Failed to update document",
                collection=self.collection_name,
                document_id=document_id,
                error=str(e)
            )
            raise DatabaseError(f"Failed to update {self.model_class.__name__}: {str(e)}")
    
    async def delete(self, document_id: str) -> bool:
        """
        Delete document by ID.
        
        Args:
            document_id: Document ID
            
        Returns:
            True if deleted, False if not found
        """
        try:
            result = await self.db.delete_one(
                self.collection_name,
                {"_id": ObjectId(document_id)}
            )
            
            if result:
                self.logger.info(
                    "Deleted document",
                    collection=self.collection_name,
                    document_id=document_id
                )
            
            return result
        except Exception as e:
            self.logger.error(
                "Failed to delete document",
                collection=self.collection_name,
                document_id=document_id,
                error=str(e)
            )
            raise DatabaseError(f"Failed to delete {self.model_class.__name__}: {str(e)}")
    
    async def find(
        self,
        filter_dict: Dict[str, Any],
        limit: Optional[int] = None,
        skip: Optional[int] = None,
        sort: Optional[List[tuple]] = None
    ) -> List[T]:
        """
        Find documents matching filter.
        
        Args:
            filter_dict: Query filter
            limit: Maximum number of results
            skip: Number of results to skip
            sort: Sort specification
            
        Returns:
            List of matching documents
        """
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
            self.logger.error(
                "Failed to find documents",
                collection=self.collection_name,
                filter=filter_dict,
                error=str(e)
            )
            raise DatabaseError(f"Failed to find {self.model_class.__name__}: {str(e)}")
    
    async def count(self, filter_dict: Dict[str, Any]) -> int:
        """
        Count documents matching filter.
        
        Args:
            filter_dict: Query filter
            
        Returns:
            Number of matching documents
        """
        try:
            return await self.db.count_documents(self.collection_name, filter_dict)
        except Exception as e:
            self.logger.error(
                "Failed to count documents",
                collection=self.collection_name,
                filter=filter_dict,
                error=str(e)
            )
            raise DatabaseError(f"Failed to count {self.model_class.__name__}: {str(e)}")


class EventRepository(BaseRepository[Event]):
    """Repository for Event documents."""
    
    def _get_collection_name(self) -> str:
        return "events"
    
    async def get_by_guild(
        self,
        guild_id: str,
        state: Optional[EventState] = None,
        limit: Optional[int] = None
    ) -> List[Event]:
        """Get events for a guild, optionally filtered by state."""
        filter_dict = {"guild_id": guild_id}
        if state:
            filter_dict["state"] = state.value
        
        return await self.find(
            filter_dict,
            limit=limit,
            sort=[("created_at", -1)]
        )
    
    async def get_by_creator(
        self,
        creator_id: str,
        guild_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Event]:
        """Get events created by a user."""
        filter_dict = {"creator_id": creator_id}
        if guild_id:
            filter_dict["guild_id"] = guild_id
        
        return await self.find(
            filter_dict,
            limit=limit,
            sort=[("created_at", -1)]
        )
    
    async def get_scheduled_events(
        self,
        guild_id: Optional[str] = None,
        after_date: Optional[date] = None
    ) -> List[Event]:
        """Get scheduled events, optionally filtered by guild and date."""
        filter_dict = {"state": EventState.SCHEDULED.value}
        
        if guild_id:
            filter_dict["guild_id"] = guild_id
        
        if after_date:
            filter_dict["schedule.selected_date"] = {"$gte": after_date}
        
        return await self.find(
            filter_dict,
            sort=[("schedule.selected_date", 1), ("schedule.selected_time", 1)]
        )
    
    async def get_active_polls(
        self,
        guild_id: Optional[str] = None,
        poll_type: Optional[PollType] = None
    ) -> List[Event]:
        """Get events with active polls."""
        filter_dict = {}
        
        if guild_id:
            filter_dict["guild_id"] = guild_id
        
        # Events in polling states
        polling_states = [
            EventState.DATE_POLLING.value,
            EventState.TIME_POLLING.value,
            EventState.GAME_POLLING.value
        ]
        filter_dict["state"] = {"$in": polling_states}
        
        events = await self.find(filter_dict, sort=[("created_at", -1)])
        
        # Filter by poll type if specified
        if poll_type:
            filtered_events = []
            for event in events:
                poll = event.get_poll(poll_type)
                if poll and poll.is_active:
                    filtered_events.append(event)
            return filtered_events
        
        return events
    
    async def get_by_discord_event_id(self, discord_event_id: str) -> Optional[Event]:
        """Get event by Discord scheduled event ID."""
        results = await self.find({"discord_event_id": discord_event_id})
        return results[0] if results else None
    
    async def get_events_needing_reminders(
        self,
        before_time: datetime,
        guild_id: Optional[str] = None
    ) -> List[Event]:
        """Get scheduled events that need reminders sent."""
        filter_dict = {
            "state": EventState.SCHEDULED.value,
            # This would need to be implemented based on reminder scheduling logic
            # For now, just return scheduled events
        }
        
        if guild_id:
            filter_dict["guild_id"] = guild_id
        
        return await self.find(filter_dict)
    
    async def update_event_state(self, event_id: str, new_state: EventState) -> bool:
        """Update event state."""
        try:
            result = await self.db.update_one(
                self.collection_name,
                {"_id": ObjectId(event_id)},
                {
                    "$set": {
                        "state": new_state.value,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            return result
        except Exception as e:
            self.logger.error(
                "Failed to update event state",
                event_id=event_id,
                new_state=new_state.value,
                error=str(e)
            )
            raise DatabaseError(f"Failed to update event state: {str(e)}")
    
    async def add_rsvp(
        self,
        event_id: str,
        user_id: str,
        status: RSVPStatus,
        notes: Optional[str] = None
    ) -> bool:
        """Add or update RSVP for an event."""
        try:
            rsvp_data = {
                "user_id": user_id,
                "status": status.value,
                "response_time": datetime.utcnow(),
                "notes": notes
            }
            
            result = await self.db.update_one(
                self.collection_name,
                {"_id": ObjectId(event_id)},
                {
                    "$set": {
                        f"rsvp_data.{user_id}": rsvp_data,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            return result
        except Exception as e:
            self.logger.error(
                "Failed to add RSVP",
                event_id=event_id,
                user_id=user_id,
                error=str(e)
            )
            raise DatabaseError(f"Failed to add RSVP: {str(e)}")


class UserRepository(BaseRepository[User]):
    """Repository for User documents."""
    
    def _get_collection_name(self) -> str:
        return "users"
    
    async def get_by_user_and_guild(self, user_id: str, guild_id: str) -> Optional[User]:
        """Get user by Discord user ID and guild ID."""
        results = await self.find({"user_id": user_id, "guild_id": guild_id})
        return results[0] if results else None
    
    async def get_by_guild(self, guild_id: str, limit: Optional[int] = None) -> List[User]:
        """Get all users in a guild."""
        return await self.find(
            {"guild_id": guild_id},
            limit=limit,
            sort=[("statistics.last_active", -1)]
        )
    
    async def get_users_interested_in_game(
        self,
        guild_id: str,
        game_name: str
    ) -> List[User]:
        """Get users interested in a specific game."""
        # Use case-insensitive regex for game matching
        filter_dict = {
            "guild_id": guild_id,
            "game_interests.game_name": {"$regex": f"^{game_name}$", "$options": "i"},
            "game_interests.notification_enabled": True
        }
        
        return await self.find(filter_dict)
    
    async def get_users_with_timezone(
        self,
        guild_id: str,
        timezone: str
    ) -> List[User]:
        """Get users in a specific timezone."""
        return await self.find({"guild_id": guild_id, "timezone": timezone})
    
    async def update_user_statistics(
        self,
        user_id: str,
        guild_id: str,
        stat_updates: Dict[str, Any]
    ) -> bool:
        """Update user statistics."""
        try:
            update_dict = {}
            for key, value in stat_updates.items():
                update_dict[f"statistics.{key}"] = value
            
            update_dict["updated_at"] = datetime.utcnow()
            
            result = await self.db.update_one(
                self.collection_name,
                {"user_id": user_id, "guild_id": guild_id},
                {"$set": update_dict}
            )
            return result
        except Exception as e:
            self.logger.error(
                "Failed to update user statistics",
                user_id=user_id,
                guild_id=guild_id,
                error=str(e)
            )
            raise DatabaseError(f"Failed to update user statistics: {str(e)}")
    
    async def add_game_interest(
        self,
        user_id: str,
        guild_id: str,
        game_name: str,
        interest_level: int = 5
    ) -> bool:
        """Add game interest for a user."""
        try:
            game_interest = {
                "game_name": game_name,
                "interest_level": interest_level,
                "added_at": datetime.utcnow(),
                "notification_enabled": True
            }
            
            result = await self.db.update_one(
                self.collection_name,
                {
                    "user_id": user_id,
                    "guild_id": guild_id,
                    "game_interests.game_name": {"$ne": game_name}
                },
                {
                    "$push": {"game_interests": game_interest},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            return result
        except Exception as e:
            self.logger.error(
                "Failed to add game interest",
                user_id=user_id,
                guild_id=guild_id,
                game_name=game_name,
                error=str(e)
            )
            raise DatabaseError(f"Failed to add game interest: {str(e)}")
    
    async def remove_game_interest(
        self,
        user_id: str,
        guild_id: str,
        game_name: str
    ) -> bool:
        """Remove game interest for a user."""
        try:
            result = await self.db.update_one(
                self.collection_name,
                {"user_id": user_id, "guild_id": guild_id},
                {
                    "$pull": {"game_interests": {"game_name": game_name}},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            return result
        except Exception as e:
            self.logger.error(
                "Failed to remove game interest",
                user_id=user_id,
                guild_id=guild_id,
                game_name=game_name,
                error=str(e)
            )
            raise DatabaseError(f"Failed to remove game interest: {str(e)}")


class RecurringScheduleRepository(BaseRepository[RecurringSchedule]):
    """Repository for RecurringSchedule documents."""
    
    def _get_collection_name(self) -> str:
        return "recurring_schedules"
    
    async def get_by_guild(
        self,
        guild_id: str,
        status: Optional[ScheduleStatus] = None
    ) -> List[RecurringSchedule]:
        """Get recurring schedules for a guild."""
        filter_dict = {"guild_id": guild_id}
        if status:
            filter_dict["status"] = status.value
        
        return await self.find(filter_dict, sort=[("created_at", -1)])
    
    async def get_active_schedules(self) -> List[RecurringSchedule]:
        """Get all active schedules across all guilds."""
        return await self.find(
            {"status": ScheduleStatus.ACTIVE.value},
            sort=[("next_trigger", 1)]
        )
    
    async def get_due_schedules(self, current_time: datetime) -> List[RecurringSchedule]:
        """Get schedules that are due for execution."""
        filter_dict = {
            "status": ScheduleStatus.ACTIVE.value,
            "next_trigger": {"$lte": current_time}
        }
        
        return await self.find(filter_dict, sort=[("next_trigger", 1)])
    
    async def update_next_trigger(
        self,
        schedule_id: str,
        next_trigger: datetime
    ) -> bool:
        """Update next trigger time for a schedule."""
        try:
            result = await self.db.update_one(
                self.collection_name,
                {"_id": ObjectId(schedule_id)},
                {
                    "$set": {
                        "next_trigger": next_trigger,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            return result
        except Exception as e:
            self.logger.error(
                "Failed to update next trigger",
                schedule_id=schedule_id,
                error=str(e)
            )
            raise DatabaseError(f"Failed to update next trigger: {str(e)}")
    
    async def record_execution(
        self,
        schedule_id: str,
        status: ExecutionStatus,
        event_id: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Record execution attempt for a schedule."""
        try:
            execution_record = {
                "execution_time": datetime.utcnow(),
                "status": status.value,
                "event_id": event_id,
                "error_message": error_message
            }
            
            update_dict = {
                "$push": {"execution_history": execution_record},
                "$set": {"updated_at": datetime.utcnow()}
            }
            
            # Increment execution count for successful executions
            if status == ExecutionStatus.SUCCESS:
                update_dict["$inc"] = {"execution_count": 1}
            
            result = await self.db.update_one(
                self.collection_name,
                {"_id": ObjectId(schedule_id)},
                update_dict
            )
            return result
        except Exception as e:
            self.logger.error(
                "Failed to record execution",
                schedule_id=schedule_id,
                status=status.value,
                error=str(e)
            )
            raise DatabaseError(f"Failed to record execution: {str(e)}")


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
        config = GuildConfig(
            guild_id=guild_id,
            guild_name=guild_name
        )
        return await self.create(config)
    
    async def update_role_mappings(
        self,
        guild_id: str,
        role_mappings: List[Dict[str, Any]]
    ) -> bool:
        """Update role mappings for a guild."""
        try:
            result = await self.db.update_one(
                self.collection_name,
                {"guild_id": guild_id},
                {
                    "$set": {
                        "role_mappings": role_mappings,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            return result
        except Exception as e:
            self.logger.error(
                "Failed to update role mappings",
                guild_id=guild_id,
                error=str(e)
            )
            raise DatabaseError(f"Failed to update role mappings: {str(e)}")
    
    async def update_feature_flags(
        self,
        guild_id: str,
        feature_updates: Dict[str, bool]
    ) -> bool:
        """Update feature flags for a guild."""
        try:
            update_dict = {}
            for feature, enabled in feature_updates.items():
                update_dict[f"features.{feature}"] = enabled
            
            update_dict["updated_at"] = datetime.utcnow()
            
            result = await self.db.update_one(
                self.collection_name,
                {"guild_id": guild_id},
                {"$set": update_dict}
            )
            return result
        except Exception as e:
            self.logger.error(
                "Failed to update feature flags",
                guild_id=guild_id,
                error=str(e)
            )
            raise DatabaseError(f"Failed to update feature flags: {str(e)}")
    
    async def update_statistics(
        self,
        guild_id: str,
        stat_updates: Dict[str, Any]
    ) -> bool:
        """Update guild statistics."""
        try:
            update_dict = {}
            for key, value in stat_updates.items():
                update_dict[f"statistics.{key}"] = value
            
            update_dict["statistics.last_calculated"] = datetime.utcnow()
            update_dict["updated_at"] = datetime.utcnow()
            
            result = await self.db.update_one(
                self.collection_name,
                {"guild_id": guild_id},
                {"$set": update_dict}
            )
            return result
        except Exception as e:
            self.logger.error(
                "Failed to update guild statistics",
                guild_id=guild_id,
                error=str(e)
            )
            raise DatabaseError(f"Failed to update guild statistics: {str(e)}")


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