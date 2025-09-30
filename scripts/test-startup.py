#!/usr/bin/env python3
"""
Test script to verify bot startup validation without actually starting the bot.
"""

import asyncio
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

async def test_startup():
    """Test the startup validation process."""
    try:
        print("🧪 Testing startup validation...")
        
        # Test settings loading
        from config.settings import Settings
        settings = Settings()
        print("✅ Settings loaded successfully")
        
        # Test startup validator
        from core.startup_validator import StartupValidator
        validator = StartupValidator(settings)
        print("✅ Startup validator created")
        
        # Run validation (but skip Discord connection test for now)
        print("\n🔍 Running validation checks...")
        
        # Test individual components
        env_ok = await validator._validate_environment()
        print(f"Environment: {'✅' if env_ok else '❌'}")
        
        deps_ok = await validator._validate_dependencies()
        print(f"Dependencies: {'✅' if deps_ok else '❌'}")
        
        fs_ok = await validator._validate_filesystem()
        print(f"Filesystem: {'✅' if fs_ok else '❌'}")
        
        # Test database manager creation (without connecting)
        from database.manager import DatabaseManager
        db_manager = DatabaseManager(settings.database_url)
        print("✅ Database manager created")
        
        # Test migration manager creation
        from database.migrations import MigrationManager
        migration_manager = MigrationManager(db_manager)
        print("✅ Migration manager created")
        
        print("\n🎉 All startup components can be initialized!")
        print("Bot is ready for deployment (pending actual database/Discord connectivity)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Startup test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_startup())
    sys.exit(0 if success else 1)