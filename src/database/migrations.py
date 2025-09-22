"""
Database migration system for schema changes and data updates.
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from bson import ObjectId

from .manager import DatabaseManager
from src.utils.logging_config import get_logger, LoggerMixin
from src.utils.exceptions import DatabaseError


class Migration(ABC, LoggerMixin):
    """
    Base class for database migrations.
    
    Each migration should inherit from this class and implement
    the up() and down() methods.
    """
    
    def __init__(self, version: str, description: str):
        self.version = version
        self.description = description
        self.applied_at: Optional[datetime] = None
    
    @abstractmethod
    async def up(self, db: DatabaseManager) -> None:
        """
        Apply the migration.
        
        Args:
            db: Database manager instance
        """
        pass
    
    @abstractmethod
    async def down(self, db: DatabaseManager) -> None:
        """
        Rollback the migration.
        
        Args:
            db: Database manager instance
        """
        pass
    
    def __str__(self) -> str:
        return f"Migration {self.version}: {self.description}"


class InitialMigration(Migration):
    """Initial migration to set up base collections and indexes."""
    
    def __init__(self):
        super().__init__("001", "Initial database setup")
    
    async def up(self, db: DatabaseManager) -> None:
        """Create initial collections and indexes."""
        self.logger.info("Running initial migration")
        
        # Collections will be created automatically when first document is inserted
        # Indexes are created in DatabaseManager._create_indexes()
        
        # Create migration tracking collection
        await db.database.migrations.create_index("version", unique=True)
        
        self.logger.info("Initial migration completed")
    
    async def down(self, db: DatabaseManager) -> None:
        """Drop all collections (dangerous!)."""
        self.logger.warning("Rolling back initial migration - dropping all collections")
        
        collections = await db.database.list_collection_names()
        for collection_name in collections:
            if collection_name != "migrations":
                await db.database.drop_collection(collection_name)
        
        self.logger.info("Initial migration rollback completed")


class AddUserTimezoneDefaultMigration(Migration):
    """Migration to add default timezone to existing users."""
    
    def __init__(self):
        super().__init__("002", "Add default timezone to existing users")
    
    async def up(self, db: DatabaseManager) -> None:
        """Add timezone field to users without it."""
        self.logger.info("Adding default timezone to users")
        
        result = await db.database.users.update_many(
            {"timezone": {"$exists": False}},
            {"$set": {"timezone": "UTC"}}
        )
        
        self.logger.info(f"Updated {result.modified_count} users with default timezone")
    
    async def down(self, db: DatabaseManager) -> None:
        """Remove timezone field from users."""
        self.logger.info("Removing timezone field from users")
        
        result = await db.database.users.update_many(
            {},
            {"$unset": {"timezone": ""}}
        )
        
        self.logger.info(f"Removed timezone from {result.modified_count} users")


class AddEventTagsMigration(Migration):
    """Migration to add tags field to events."""
    
    def __init__(self):
        super().__init__("003", "Add tags field to events")
    
    async def up(self, db: DatabaseManager) -> None:
        """Add tags field to events."""
        self.logger.info("Adding tags field to events")
        
        result = await db.database.events.update_many(
            {"tags": {"$exists": False}},
            {"$set": {"tags": []}}
        )
        
        self.logger.info(f"Updated {result.modified_count} events with tags field")
    
    async def down(self, db: DatabaseManager) -> None:
        """Remove tags field from events."""
        self.logger.info("Removing tags field from events")
        
        result = await db.database.events.update_many(
            {},
            {"$unset": {"tags": ""}}
        )
        
        self.logger.info(f"Removed tags from {result.modified_count} events")


class UpdateGuildConfigStructureMigration(Migration):
    """Migration to update guild config structure."""
    
    def __init__(self):
        super().__init__("004", "Update guild config structure")
    
    async def up(self, db: DatabaseManager) -> None:
        """Update guild config structure."""
        self.logger.info("Updating guild config structure")
        
        # Add new fields to existing guild configs
        result = await db.database.guild_configs.update_many(
            {"features": {"$exists": False}},
            {
                "$set": {
                    "features": {
                        "events_enabled": True,
                        "recurring_events_enabled": True,
                        "game_pings_enabled": True,
                        "web_dashboard_enabled": True,
                        "analytics_enabled": True,
                        "discord_events_integration": True,
                        "calendar_export_enabled": True,
                        "user_profiles_enabled": True
                    }
                }
            }
        )
        
        self.logger.info(f"Updated {result.modified_count} guild configs with features")
    
    async def down(self, db: DatabaseManager) -> None:
        """Remove features field from guild configs."""
        self.logger.info("Removing features field from guild configs")
        
        result = await db.database.guild_configs.update_many(
            {},
            {"$unset": {"features": ""}}
        )
        
        self.logger.info(f"Removed features from {result.modified_count} guild configs")


class MigrationManager(LoggerMixin):
    """
    Manages database migrations.
    
    Tracks applied migrations and provides methods to apply/rollback changes.
    """
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.migrations: List[Migration] = [
            InitialMigration(),
            AddUserTimezoneDefaultMigration(),
            AddEventTagsMigration(),
            UpdateGuildConfigStructureMigration(),
        ]
    
    async def get_applied_migrations(self) -> List[str]:
        """Get list of applied migration versions."""
        try:
            cursor = self.db.database.migrations.find({}, {"version": 1})
            migrations = await cursor.to_list(length=None)
            return [m["version"] for m in migrations]
        except Exception as e:
            self.logger.error("Failed to get applied migrations", error=str(e))
            return []
    
    async def record_migration(self, migration: Migration) -> None:
        """Record that a migration has been applied."""
        try:
            await self.db.database.migrations.insert_one({
                "version": migration.version,
                "description": migration.description,
                "applied_at": datetime.now(timezone.utc)
            })
            
            self.logger.info(
                "Recorded migration",
                version=migration.version,
                description=migration.description
            )
        except Exception as e:
            self.logger.error(
                "Failed to record migration",
                version=migration.version,
                error=str(e)
            )
            raise DatabaseError(f"Failed to record migration: {str(e)}")
    
    async def remove_migration_record(self, version: str) -> None:
        """Remove migration record (for rollbacks)."""
        try:
            await self.db.database.migrations.delete_one({"version": version})
            self.logger.info("Removed migration record", version=version)
        except Exception as e:
            self.logger.error(
                "Failed to remove migration record",
                version=version,
                error=str(e)
            )
            raise DatabaseError(f"Failed to remove migration record: {str(e)}")
    
    async def get_pending_migrations(self) -> List[Migration]:
        """Get list of migrations that haven't been applied."""
        applied = await self.get_applied_migrations()
        return [m for m in self.migrations if m.version not in applied]
    
    async def apply_migration(self, migration: Migration) -> bool:
        """
        Apply a single migration.
        
        Args:
            migration: Migration to apply
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info(
                "Applying migration",
                version=migration.version,
                description=migration.description
            )
            
            # Apply the migration
            await migration.up(self.db)
            
            # Record successful application
            await self.record_migration(migration)
            
            self.logger.info("Migration applied successfully", version=migration.version)
            return True
            
        except Exception as e:
            self.logger.error(
                "Migration failed",
                version=migration.version,
                error=str(e)
            )
            return False
    
    async def rollback_migration(self, migration: Migration) -> bool:
        """
        Rollback a single migration.
        
        Args:
            migration: Migration to rollback
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info(
                "Rolling back migration",
                version=migration.version,
                description=migration.description
            )
            
            # Rollback the migration
            await migration.down(self.db)
            
            # Remove migration record
            await self.remove_migration_record(migration.version)
            
            self.logger.info("Migration rolled back successfully", version=migration.version)
            return True
            
        except Exception as e:
            self.logger.error(
                "Migration rollback failed",
                version=migration.version,
                error=str(e)
            )
            return False
    
    async def migrate_up(self, target_version: Optional[str] = None) -> bool:
        """
        Apply all pending migrations up to target version.
        
        Args:
            target_version: Stop at this version (None = apply all)
            
        Returns:
            True if all migrations successful, False otherwise
        """
        try:
            pending = await self.get_pending_migrations()
            
            if not pending:
                self.logger.info("No pending migrations")
                return True
            
            # Filter to target version if specified
            if target_version:
                pending = [m for m in pending if m.version <= target_version]
            
            # Sort by version
            pending.sort(key=lambda m: m.version)
            
            self.logger.info(f"Applying {len(pending)} migrations")
            
            for migration in pending:
                success = await self.apply_migration(migration)
                if not success:
                    self.logger.error(
                        "Migration failed, stopping",
                        failed_version=migration.version
                    )
                    return False
            
            self.logger.info("All migrations applied successfully")
            return True
            
        except Exception as e:
            self.logger.error("Migration process failed", error=str(e))
            return False
    
    async def migrate_down(self, target_version: str) -> bool:
        """
        Rollback migrations down to target version.
        
        Args:
            target_version: Rollback to this version
            
        Returns:
            True if all rollbacks successful, False otherwise
        """
        try:
            applied = await self.get_applied_migrations()
            
            # Find migrations to rollback (those after target version)
            to_rollback = []
            for version in applied:
                if version > target_version:
                    migration = next((m for m in self.migrations if m.version == version), None)
                    if migration:
                        to_rollback.append(migration)
            
            if not to_rollback:
                self.logger.info("No migrations to rollback")
                return True
            
            # Sort by version (descending for rollback)
            to_rollback.sort(key=lambda m: m.version, reverse=True)
            
            self.logger.info(f"Rolling back {len(to_rollback)} migrations")
            
            for migration in to_rollback:
                success = await self.rollback_migration(migration)
                if not success:
                    self.logger.error(
                        "Migration rollback failed, stopping",
                        failed_version=migration.version
                    )
                    return False
            
            self.logger.info("All migrations rolled back successfully")
            return True
            
        except Exception as e:
            self.logger.error("Migration rollback process failed", error=str(e))
            return False
    
    async def get_migration_status(self) -> Dict[str, Any]:
        """Get current migration status."""
        try:
            applied = await self.get_applied_migrations()
            pending = await self.get_pending_migrations()
            
            return {
                "total_migrations": len(self.migrations),
                "applied_count": len(applied),
                "pending_count": len(pending),
                "applied_versions": sorted(applied),
                "pending_versions": [m.version for m in pending],
                "latest_version": self.migrations[-1].version if self.migrations else None,
                "current_version": max(applied) if applied else None
            }
        except Exception as e:
            self.logger.error("Failed to get migration status", error=str(e))
            return {"error": str(e)}
    
    async def validate_database_schema(self) -> Dict[str, Any]:
        """
        Validate current database schema against expected structure.
        
        Returns:
            Validation results with any issues found
        """
        try:
            issues = []
            collections = await self.db.database.list_collection_names()
            
            # Expected collections
            expected_collections = [
                "events", "users", "recurring_schedules", 
                "guild_configs", "notifications", "game_interests", 
                "audit_logs", "migrations"
            ]
            
            # Check for missing collections
            for collection in expected_collections:
                if collection not in collections:
                    issues.append(f"Missing collection: {collection}")
            
            # Check for unexpected collections
            for collection in collections:
                if collection not in expected_collections and not collection.startswith("system."):
                    issues.append(f"Unexpected collection: {collection}")
            
            # Check indexes (basic validation)
            for collection in ["events", "users", "recurring_schedules", "guild_configs"]:
                if collection in collections:
                    indexes = await self.db.database[collection].list_indexes().to_list(length=None)
                    if len(indexes) <= 1:  # Only _id index
                        issues.append(f"Missing indexes on collection: {collection}")
            
            return {
                "valid": len(issues) == 0,
                "issues": issues,
                "collections_found": len(collections),
                "collections_expected": len(expected_collections)
            }
            
        except Exception as e:
            self.logger.error("Schema validation failed", error=str(e))
            return {"valid": False, "error": str(e)}


async def run_migrations(db_manager: DatabaseManager) -> bool:
    """
    Convenience function to run all pending migrations.
    
    Args:
        db_manager: Database manager instance
        
    Returns:
        True if successful, False otherwise
    """
    migration_manager = MigrationManager(db_manager)
    return await migration_manager.migrate_up()


async def get_migration_status(db_manager: DatabaseManager) -> Dict[str, Any]:
    """
    Convenience function to get migration status.
    
    Args:
        db_manager: Database manager instance
        
    Returns:
        Migration status information
    """
    migration_manager = MigrationManager(db_manager)
    return await migration_manager.get_migration_status()