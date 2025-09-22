"""
Unit tests for database operations and models.
"""

import pytest
import asyncio
from datetime import datetime, date, time, timezone
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

from src.database.manager import DatabaseManager
from src.database.migrations import MigrationManager, InitialMigration
from src.models import (
    Event, EventState, User, RecurringSchedule, GuildConfig,
    EventRepository, UserRepository, RecurringScheduleRepository,
    GuildConfigRepository, RepositoryManager
)
from src.utils.exceptions import DatabaseError, DatabaseConnectionError


class TestDatabaseManager:
    """Test DatabaseManager functionality."""
    
    @pytest.fixture
    def mock_client(self):
        """Mock MongoDB client."""
        client = AsyncMock()
        client.admin.command = AsyncMock(return_value={"ok": 1})
        return client
    
    @pytest.fixture
    def db_manager(self):
        """Create DatabaseManager instance for testing."""
        return DatabaseManager("mongodb://localhost:27017/test_gamenight")
    
    @pytest.mark.asyncio
    async def test_connection_success(self, db_manager, mock_client):
        """Test successful database connection."""
        with patch('motor.motor_asyncio.AsyncIOMotorClient', return_value=mock_client):
            await db_manager.connect()
            
            assert db_manager.is_connected
            assert db_manager.client is not None
            assert db_manager.database is not None
    
    @pytest.mark.asyncio
    async def test_connection_failure(self, db_manager):
        """Test database connection failure."""
        with patch('motor.motor_asyncio.AsyncIOMotorClient') as mock_motor:
            mock_motor.side_effect = Exception("Connection failed")
            
            with pytest.raises(DatabaseConnectionError):
                await db_manager.connect()
    
    @pytest.mark.asyncio
    async def test_ping_success(self, db_manager, mock_client):
        """Test successful database ping."""
        db_manager.client = mock_client
        db_manager._connected = True
        
        result = await db_manager.ping()
        assert result is True
        mock_client.admin.command.assert_called_with('ping')
    
    @pytest.mark.asyncio
    async def test_ping_failure(self, db_manager, mock_client):
        """Test database ping failure."""
        mock_client.admin.command.side_effect = Exception("Ping failed")
        db_manager.client = mock_client
        db_manager._connected = True
        
        result = await db_manager.ping()
        assert result is False
    
    @pytest.mark.asyncio
    async def test_crud_operations(self, db_manager):
        """Test basic CRUD operations."""
        # Mock database
        mock_collection = AsyncMock()
        mock_database = MagicMock()
        mock_database.__getitem__.return_value = mock_collection
        db_manager.database = mock_database
        
        # Test insert
        mock_collection.insert_one.return_value = MagicMock(inserted_id="test_id")
        result = await db_manager.insert_one("test_collection", {"name": "test"})
        assert result == "test_id"
        
        # Test find_one
        mock_collection.find_one.return_value = {"_id": "test_id", "name": "test"}
        result = await db_manager.find_one("test_collection", {"_id": "test_id"})
        assert result["name"] == "test"
        
        # Test update_one
        mock_collection.update_one.return_value = MagicMock(modified_count=1)
        result = await db_manager.update_one(
            "test_collection", 
            {"_id": "test_id"}, 
            {"$set": {"name": "updated"}}
        )
        assert result is True
        
        # Test delete_one
        mock_collection.delete_one.return_value = MagicMock(deleted_count=1)
        result = await db_manager.delete_one("test_collection", {"_id": "test_id"})
        assert result is True


class TestEventModel:
    """Test Event model functionality."""
    
    def test_event_creation(self):
        """Test creating a new event."""
        event = Event(
            guild_id="123456789012345678",
            title="Test Game Night",
            description="A test event",
            creator_id="987654321098765432"
        )
        
        assert event.guild_id == "123456789012345678"
        assert event.title == "Test Game Night"
        assert event.state == EventState.DRAFT
        assert event.is_active()
        assert not event.is_scheduled()
    
    def test_event_validation(self):
        """Test event data validation."""
        event = Event(
            guild_id="123456789012345678",
            title="Test Event",
            creator_id="987654321098765432"
        )
        
        # Should not raise exception for valid event
        event.validate_data()
        
        # Test invalid guild ID
        with pytest.raises(ValueError):
            Event(
                guild_id="invalid",
                title="Test",
                creator_id="987654321098765432"
            )
    
    def test_event_state_transitions(self):
        """Test event state transitions."""
        event = Event(
            guild_id="123456789012345678",
            title="Test Event",
            creator_id="987654321098765432"
        )
        
        # Valid transition
        assert event.can_transition_to(EventState.DATE_POLLING)
        assert event.transition_to(EventState.DATE_POLLING)
        assert event.state == EventState.DATE_POLLING
        
        # Invalid transition
        assert not event.can_transition_to(EventState.COMPLETED)
        assert not event.transition_to(EventState.COMPLETED)
        assert event.state == EventState.DATE_POLLING
    
    def test_rsvp_functionality(self):
        """Test RSVP functionality."""
        from src.models.event import RSVPStatus
        
        event = Event(
            guild_id="123456789012345678",
            title="Test Event",
            creator_id="987654321098765432"
        )
        
        # Add RSVP
        event.add_rsvp("111111111111111111", RSVPStatus.YES, "Looking forward to it!")
        event.add_rsvp("222222222222222222", RSVPStatus.NO)
        event.add_rsvp("333333333333333333", RSVPStatus.MAYBE)
        
        assert event.get_rsvp_count(RSVPStatus.YES) == 1
        assert event.get_rsvp_count(RSVPStatus.NO) == 1
        assert event.get_rsvp_count(RSVPStatus.MAYBE) == 1
        
        attendees = event.get_attendee_list()
        assert "111111111111111111" in attendees
        assert "222222222222222222" not in attendees


class TestUserModel:
    """Test User model functionality."""
    
    def test_user_creation(self):
        """Test creating a new user."""
        user = User(
            user_id="123456789012345678",
            guild_id="987654321098765432",
            display_name="TestUser",
            timezone="America/New_York"
        )
        
        assert user.user_id == "123456789012345678"
        assert user.guild_id == "987654321098765432"
        assert user.timezone == "America/New_York"
    
    def test_game_interest_management(self):
        """Test game interest functionality."""
        user = User(
            user_id="123456789012345678",
            guild_id="987654321098765432"
        )
        
        # Add game interest
        assert user.add_game_interest("Dungeons & Dragons", 8)
        assert user.add_game_interest("Monopoly", 5)
        
        # Duplicate should fail
        assert not user.add_game_interest("Dungeons & Dragons", 9)
        
        # Check interest
        assert user.is_interested_in_game("Dungeons & Dragons")
        assert user.is_interested_in_game("Monopoly")
        assert not user.is_interested_in_game("Chess")
        
        # Remove interest
        assert user.remove_game_interest("Monopoly")
        assert not user.is_interested_in_game("Monopoly")
        assert not user.remove_game_interest("Chess")  # Not found
    
    def test_availability_management(self):
        """Test availability slot management."""
        from src.models.user import DayOfWeek
        
        user = User(
            user_id="123456789012345678",
            guild_id="987654321098765432"
        )
        
        # Add availability
        assert user.add_availability_slot(
            DayOfWeek.FRIDAY,
            time(19, 0),  # 7:00 PM
            time(23, 0)   # 11:00 PM
        )
        
        # Check availability
        assert user.is_available_at(DayOfWeek.FRIDAY, time(20, 0))
        assert not user.is_available_at(DayOfWeek.FRIDAY, time(18, 0))
        assert not user.is_available_at(DayOfWeek.SATURDAY, time(20, 0))
        
        # Overlapping slot should fail
        assert not user.add_availability_slot(
            DayOfWeek.FRIDAY,
            time(18, 0),
            time(20, 0)
        )


class TestRepositories:
    """Test repository functionality."""
    
    @pytest.fixture
    def mock_db_manager(self):
        """Mock database manager."""
        db = AsyncMock()
        db.insert_one = AsyncMock(return_value="test_id")
        db.find_one = AsyncMock(return_value=None)
        db.find_many = AsyncMock(return_value=[])
        db.update_one = AsyncMock(return_value=True)
        db.delete_one = AsyncMock(return_value=True)
        db.count_documents = AsyncMock(return_value=0)
        return db
    
    @pytest.mark.asyncio
    async def test_event_repository(self, mock_db_manager):
        """Test EventRepository functionality."""
        repo = EventRepository(mock_db_manager, Event)
        
        # Test create
        event = Event(
            guild_id="123456789012345678",
            title="Test Event",
            creator_id="987654321098765432"
        )
        
        result = await repo.create(event)
        assert result == "test_id"
        mock_db_manager.insert_one.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_user_repository(self, mock_db_manager):
        """Test UserRepository functionality."""
        repo = UserRepository(mock_db_manager, User)
        
        # Test get_by_user_and_guild
        mock_db_manager.find_many.return_value = []
        result = await repo.get_by_user_and_guild("123456789012345678", "987654321098765432")
        assert result is None
        
        # Test with user found
        from bson import ObjectId
        user_data = {
            "_id": ObjectId(),
            "user_id": "123456789012345678",
            "guild_id": "987654321098765432",
            "timezone": "UTC",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "availability": [],
            "notification_preferences": {
                "channel": "BOTH",
                "event_reminders": True,
                "poll_notifications": True,
                "game_pings": True,
                "reminder_timing": "DAY_BEFORE",
                "max_game_pings_per_day": 5
            },
            "game_interests": [],
            "statistics": {
                "events_created": 0,
                "events_attended": 0,
                "events_rsvp_yes": 0,
                "events_rsvp_no": 0,
                "events_rsvp_maybe": 0,
                "total_rsvps": 0,
                "attendance_rate": 0.0,
                "favorite_games": [],
                "games_played_count": {},
                "last_active": datetime.now(timezone.utc)
            },
            "profile_public": True,
            "stats_public": True
        }
        mock_db_manager.find_many.return_value = [user_data]
        
        result = await repo.get_by_user_and_guild("123456789012345678", "987654321098765432")
        assert result is not None
        assert result.user_id == "123456789012345678"
    
    @pytest.mark.asyncio
    async def test_repository_manager(self, mock_db_manager):
        """Test RepositoryManager functionality."""
        manager = RepositoryManager(mock_db_manager)
        
        assert isinstance(manager.events, EventRepository)
        assert isinstance(manager.users, UserRepository)
        assert isinstance(manager.recurring_schedules, RecurringScheduleRepository)
        assert isinstance(manager.guild_configs, GuildConfigRepository)


class TestMigrations:
    """Test migration system."""
    
    @pytest.fixture
    def mock_db_manager(self):
        """Mock database manager for migrations."""
        db = AsyncMock()
        mock_migrations_collection = AsyncMock()
        mock_database = AsyncMock()
        mock_database.migrations = mock_migrations_collection
        mock_database.list_collection_names = AsyncMock(return_value=[])
        db.database = mock_database
        return db
    
    @pytest.mark.asyncio
    async def test_migration_manager_creation(self, mock_db_manager):
        """Test creating migration manager."""
        manager = MigrationManager(mock_db_manager)
        assert len(manager.migrations) > 0
        assert any(m.version == "001" for m in manager.migrations)
    
    @pytest.mark.skip(reason="Complex async mocking - integration test needed")
    async def test_get_applied_migrations(self, mock_db_manager):
        """Test getting applied migrations."""
        pass
    
    @pytest.mark.asyncio
    async def test_apply_migration(self, mock_db_manager):
        """Test applying a migration."""
        mock_db_manager.database.migrations.insert_one = AsyncMock()
        
        manager = MigrationManager(mock_db_manager)
        migration = InitialMigration()
        
        # Mock successful migration
        with patch.object(migration, 'up', new_callable=AsyncMock) as mock_up:
            result = await manager.apply_migration(migration)
            assert result is True
            mock_up.assert_called_once_with(mock_db_manager)
            mock_db_manager.database.migrations.insert_one.assert_called_once()
    
    @pytest.mark.skip(reason="Complex async mocking - integration test needed")
    async def test_migration_status(self, mock_db_manager):
        """Test getting migration status."""
        pass


class TestDataValidation:
    """Test data validation functionality."""
    
    def test_guild_id_validation(self):
        """Test guild ID validation."""
        from src.models.base import ValidationMixin
        
        # Valid guild ID
        assert ValidationMixin.validate_guild_id("123456789012345678") == "123456789012345678"
        
        # Invalid guild IDs
        with pytest.raises(ValueError):
            ValidationMixin.validate_guild_id("")
        
        with pytest.raises(ValueError):
            ValidationMixin.validate_guild_id("invalid")
        
        with pytest.raises(ValueError):
            ValidationMixin.validate_guild_id(None)
    
    def test_timezone_validation(self):
        """Test timezone validation."""
        from src.models.base import ValidationMixin
        
        # Valid timezones
        assert ValidationMixin.validate_timezone("UTC") == "UTC"
        assert ValidationMixin.validate_timezone("America/New_York") == "America/New_York"
        
        # Invalid timezone
        with pytest.raises(ValueError):
            ValidationMixin.validate_timezone("Invalid/Timezone")
    
    def test_text_sanitization(self):
        """Test text sanitization."""
        from src.models.base import ValidationMixin
        
        # Normal text
        assert ValidationMixin.sanitize_text("Hello World") == "Hello World"
        
        # Text with mentions
        result = ValidationMixin.sanitize_text("Hello @everyone and @here")
        assert "@everyone" not in result
        assert "@here" not in result
        
        # Long text
        long_text = "a" * 2500
        result = ValidationMixin.sanitize_text(long_text, 100)
        assert len(result) <= 100
        assert result.endswith("...")


# Pytest configuration
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


if __name__ == "__main__":
    pytest.main([__file__])