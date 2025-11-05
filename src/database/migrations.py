"""
Database migration system for the Discord Game Night Bot.
Handles database initialization, schema migrations, and data migrations.
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
import json

from pymongo import IndexModel
from pymongo.errors import OperationFailure, DuplicateKeyError

try:
    from database.manager import DatabaseManager
    from utils.logging_config import get_logger, LoggerMixin
    from utils.exceptions import DatabaseError, GameNightBotException
except ImportError:
    from src.database.manager import DatabaseManager
    from src.utils.logging_config import get_logger, LoggerMixin
    from src.utils.exceptions import DatabaseError, GameNightBotException


class MigrationError(GameNightBotException):
    """Raised when migration fails."""
    pass


class Migration:
    """Represents a single database migration."""
    
    def __init__(
        self,
        version: str,
        description: str,
        up_func: Callable,
        down_func: Optional[Callable] = None
    ):
        self.version = version
        self.description = description
        self.up_func = up_func
        self.down_func = down_func
        self.applied_at: Optional[datetime] = None
    
    async def apply(self, db_manager: DatabaseManager) -> None:
        """Apply the migration."""
        await self.up_func(db_manager)
        self.applied_at = datetime.now(timezone.utc)
    
    async def rollback(self, db_manager: DatabaseManager) -> None:
        """Rollback the migration."""
        if self.down_func:
            await self.down_func(db_manager)
        else:
            raise MigrationError(f"Migration {self.version} does not support rollback")


class MigrationManager(LoggerMixin):
    """
    Manages database migrations and initialization.
    """
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.migrations: List[Migration] = []
        self._register_migrations()
    
    def _register_migrations(self) -> None:
        """Register all available migrations."""
        # Migration 001: Initial schema setup
        self.migrations.append(Migration(
            version="001",
            description="Initial database schema and indexes",
            up_func=self._migration_001_up,
            down_func=self._migration_001_down
        ))
        
        # Migration 002: Add audit logging collections
        self.migrations.append(Migration(
            version="002", 
            description="Add audit logging and security collections",
            up_func=self._migration_002_up,
            down_func=self._migration_002_down
        ))
        
        # Migration 003: Add notification system collections
        self.migrations.append(Migration(
            version="003",
            description="Add notification system and scheduling",
            up_func=self._migration_003_up,
            down_func=self._migration_003_down
        ))
        
        # Migration 004: Add recurring events system
        self.migrations.append(Migration(
            version="004",
            description="Add recurring events and templates",
            up_func=self._migration_004_up,
            down_func=self._migration_004_down
        ))
    
    async def initialize_database(self) -> None:
        """Initialize database with required collections and run migrations."""
        self.logger.info("Initializing database...")
        
        try:
            # Ensure migrations collection exists
            await self._ensure_migrations_collection()
            
            # Run pending migrations
            await self.run_pending_migrations()
            
            # Verify database integrity
            await self._verify_database_integrity()
            
            self.logger.info("Database initialization completed successfully")
            
        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}")
            raise MigrationError(f"Database initialization failed: {e}")
    
    async def _ensure_migrations_collection(self) -> None:
        """Ensure the migrations tracking collection exists."""
        try:
            # Create migrations collection if it doesn't exist
            collections = await self.db_manager.database.list_collection_names()
            if "migrations" not in collections:
                await self.db_manager.database.create_collection("migrations")
                
                # Create index on version field
                await self.db_manager.database.migrations.create_index(
                    [("version", 1)], unique=True
                )
                
                self.logger.info("Created migrations collection")
        except Exception as e:
            raise MigrationError(f"Failed to create migrations collection: {e}")
    
    async def get_applied_migrations(self) -> List[str]:
        """Get list of applied migration versions."""
        try:
            cursor = self.db_manager.database.migrations.find(
                {"applied": True},
                {"version": 1}
            ).sort("applied_at", 1)
            
            migrations = await cursor.to_list(length=None)
            return [m["version"] for m in migrations]
        except Exception as e:
            self.logger.error(f"Failed to get applied migrations: {e}")
            return []
    
    async def run_pending_migrations(self) -> None:
        """Run all pending migrations."""
        applied_versions = await self.get_applied_migrations()
        
        pending_migrations = [
            m for m in self.migrations 
            if m.version not in applied_versions
        ]
        
        if not pending_migrations:
            self.logger.info("No pending migrations")
            return
        
        self.logger.info(f"Running {len(pending_migrations)} pending migrations")
        
        for migration in pending_migrations:
            await self._apply_migration(migration)
    
    async def _apply_migration(self, migration: Migration) -> None:
        """Apply a single migration."""
        self.logger.info(f"Applying migration {migration.version}: {migration.description}")
        
        try:
            # Apply the migration
            await migration.apply(self.db_manager)
            
            # Record migration as applied
            await self.db_manager.database.migrations.insert_one({
                "version": migration.version,
                "description": migration.description,
                "applied": True,
                "applied_at": datetime.now(timezone.utc)
            })
            
            self.logger.info(f"Successfully applied migration {migration.version}")
            
        except Exception as e:
            self.logger.error(f"Failed to apply migration {migration.version}: {e}")
            raise MigrationError(f"Migration {migration.version} failed: {e}")
    
    async def rollback_migration(self, version: str) -> None:
        """Rollback a specific migration."""
        migration = next((m for m in self.migrations if m.version == version), None)
        if not migration:
            raise MigrationError(f"Migration {version} not found")
        
        self.logger.info(f"Rolling back migration {version}")
        
        try:
            await migration.rollback(self.db_manager)
            
            # Remove migration record
            await self.db_manager.database.migrations.delete_one({"version": version})
            
            self.logger.info(f"Successfully rolled back migration {version}")
            
        except Exception as e:
            self.logger.error(f"Failed to rollback migration {version}: {e}")
            raise MigrationError(f"Rollback of migration {version} failed: {e}")
    
    async def _verify_database_integrity(self) -> None:
        """Verify database integrity after migrations."""
        required_collections = [
            "events", "users", "notifications", "recurring_schedules",
            "game_interests", "guild_configs", "audit_logs", "migrations"
        ]
        
        existing_collections = await self.db_manager.database.list_collection_names()
        
        missing_collections = [
            col for col in required_collections 
            if col not in existing_collections
        ]
        
        if missing_collections:
            raise MigrationError(f"Missing collections after migration: {missing_collections}")
        
        self.logger.info("Database integrity verification passed")
    
    # Migration implementations
    
    async def _migration_001_up(self, db_manager: DatabaseManager) -> None:
        """Migration 001: Initial schema setup."""
        # Create core collections
        collections_to_create = [
            "events", "users", "guild_configs", "game_interests"
        ]
        
        existing_collections = await db_manager.database.list_collection_names()
        
        for collection_name in collections_to_create:
            if collection_name not in existing_collections:
                await db_manager.database.create_collection(collection_name)
        
        # Create indexes for events collection
        events_indexes = [
            IndexModel([("guild_id", 1), ("status", 1), ("created_at", -1)]),
            IndexModel([("guild_id", 1), ("discord_event_id", 1)]),
            IndexModel([("guild_id", 1), ("expires_at", 1)]),
            IndexModel([("creator_id", 1), ("created_at", -1)])
        ]
        await db_manager.database.events.create_indexes(events_indexes)
        
        # Create indexes for users collection
        users_indexes = [
            IndexModel([("user_id", 1), ("guild_id", 1)], unique=True),
            IndexModel([("guild_id", 1), ("game_interests", 1)])
        ]
        await db_manager.database.users.create_indexes(users_indexes)
        
        # Create indexes for guild_configs collection
        guild_configs_indexes = [
            IndexModel([("guild_id", 1)], unique=True)
        ]
        await db_manager.database.guild_configs.create_indexes(guild_configs_indexes)
        
        # Create indexes for game_interests collection
        game_interests_indexes = [
            IndexModel([("guild_id", 1), ("game_name", 1)]),
            IndexModel([("user_id", 1), ("guild_id", 1)])
        ]
        await db_manager.database.game_interests.create_indexes(game_interests_indexes)
    
    async def _migration_001_down(self, db_manager: DatabaseManager) -> None:
        """Migration 001 rollback."""
        collections_to_drop = ["events", "users", "guild_configs", "game_interests"]
        
        for collection_name in collections_to_drop:
            await db_manager.database.drop_collection(collection_name)
    
    async def _migration_002_up(self, db_manager: DatabaseManager) -> None:
        """Migration 002: Add audit logging."""
        # Create audit_logs collection
        existing_collections = await db_manager.database.list_collection_names()
        if "audit_logs" not in existing_collections:
            await db_manager.database.create_collection("audit_logs")
        
        # Create indexes for audit_logs collection
        audit_logs_indexes = [
            IndexModel([("guild_id", 1), ("timestamp", -1)]),
            IndexModel([("action_type", 1), ("timestamp", -1)]),
            IndexModel([("user_id", 1), ("timestamp", -1)]),
            IndexModel([("severity", 1), ("timestamp", -1)])
        ]
        await db_manager.database.audit_logs.create_indexes(audit_logs_indexes)
    
    async def _migration_002_down(self, db_manager: DatabaseManager) -> None:
        """Migration 002 rollback."""
        await db_manager.database.drop_collection("audit_logs")
    
    async def _migration_003_up(self, db_manager: DatabaseManager) -> None:
        """Migration 003: Add notification system."""
        # Create notifications collection
        existing_collections = await db_manager.database.list_collection_names()
        if "notifications" not in existing_collections:
            await db_manager.database.create_collection("notifications")
        
        # Create indexes for notifications collection
        notifications_indexes = [
            IndexModel([("scheduled_for", 1), ("processed", 1)]),
            IndexModel([("guild_id", 1), ("user_id", 1)]),
            IndexModel([("event_id", 1)]),
            IndexModel([("notification_type", 1), ("scheduled_for", 1)])
        ]
        await db_manager.database.notifications.create_indexes(notifications_indexes)
    
    async def _migration_003_down(self, db_manager: DatabaseManager) -> None:
        """Migration 003 rollback."""
        await db_manager.database.drop_collection("notifications")
    
    async def _migration_004_up(self, db_manager: DatabaseManager) -> None:
        """Migration 004: Add recurring events system."""
        # Create recurring_schedules collection
        existing_collections = await db_manager.database.list_collection_names()
        if "recurring_schedules" not in existing_collections:
            await db_manager.database.create_collection("recurring_schedules")
        
        # Create indexes for recurring_schedules collection
        recurring_indexes = [
            IndexModel([("guild_id", 1), ("status.is_active", 1)]),
            IndexModel([("status.next_trigger", 1)]),
            IndexModel([("schedule.trigger_type", 1), ("status.is_active", 1)])
        ]
        await db_manager.database.recurring_schedules.create_indexes(recurring_indexes)
    
    async def _migration_004_down(self, db_manager: DatabaseManager) -> None:
        """Migration 004 rollback."""
        await db_manager.database.drop_collection("recurring_schedules")
    
    async def export_migration_status(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        """Export current migration status."""
        applied_migrations = await self.get_applied_migrations()
        
        status = {
            "database_name": self.db_manager.database_name,
            "total_migrations": len(self.migrations),
            "applied_migrations": len(applied_migrations),
            "pending_migrations": len(self.migrations) - len(applied_migrations),
            "migrations": []
        }
        
        for migration in self.migrations:
            migration_info = {
                "version": migration.version,
                "description": migration.description,
                "applied": migration.version in applied_migrations
            }
            status["migrations"].append(migration_info)
        
        if file_path:
            with open(file_path, 'w') as f:
                json.dump(status, f, indent=2, default=str)
        
        return status


async def initialize_database(db_manager: DatabaseManager) -> None:
    """
    Convenience function to initialize database.
    
    Args:
        db_manager: Database manager instance
    """
    migration_manager = MigrationManager(db_manager)
    await migration_manager.initialize_database()


if __name__ == "__main__":
    """Run migrations as standalone script."""
    async def main():
        from config.settings import Settings
        
        try:
            settings = Settings()
            db_manager = DatabaseManager(settings.database_url)
            await db_manager.connect()
            
            migration_manager = MigrationManager(db_manager)
            await migration_manager.initialize_database()
            
            # Export status
            status = await migration_manager.export_migration_status("migration_status.json")
            print(f"Database initialized successfully!")
            print(f"Applied {status['applied_migrations']}/{status['total_migrations']} migrations")
            
        except Exception as e:
            print(f"Migration failed: {e}")
            raise
        finally:
            if db_manager:
                await db_manager.disconnect()
    
    asyncio.run(main())