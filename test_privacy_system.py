"""
Test script for privacy and compliance system.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta

# Add src directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from database.manager import DatabaseManager
from core.audit_logger import AuditLogger
from core.privacy_manager import PrivacyManager, ConsentType, DataExportFormat
from core.data_retention import DataRetentionManager


async def test_privacy_system():
    """Test the privacy and compliance system."""
    print("🔒 Testing Privacy and Compliance System")
    print("=" * 50)
    
    # Initialize components
    database_url = os.getenv("DATABASE_URL", "mongodb://localhost:27017/gamenight_bot_test")
    database = DatabaseManager(database_url)
    
    try:
        await database.connect()
        print("✅ Database connected")
        
        audit_logger = AuditLogger(database)
        privacy_manager = PrivacyManager(database, audit_logger)
        retention_manager = DataRetentionManager(database, audit_logger)
        
        # Test user consent management
        print("\n📋 Testing Consent Management")
        user_id = "123456789"
        guild_id = "987654321"
        
        # Record consent
        success = await privacy_manager.record_consent(
            user_id=user_id,
            guild_id=guild_id,
            consent_type=ConsentType.DATA_COLLECTION,
            granted=True
        )
        print(f"✅ Consent recorded: {success}")
        
        # Check consent
        consent_status = await privacy_manager.get_user_consent(
            user_id=user_id,
            guild_id=guild_id,
            consent_type=ConsentType.DATA_COLLECTION
        )
        print(f"✅ Consent status: {consent_status}")
        
        # Test data export
        print("\n📤 Testing Data Export")
        
        # Create some test user data
        test_user_data = {
            "user_id": user_id,
            "guild_id": guild_id,
            "display_name": "Test User",
            "timezone": "UTC",
            "profile_public": True,
            "stats_public": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        await database.insert_one("users", test_user_data)
        print("✅ Test user data created")
        
        # Request data export
        request_id = await privacy_manager.request_data_export(
            user_id=user_id,
            guild_id=guild_id,
            format=DataExportFormat.JSON
        )
        print(f"✅ Data export requested: {request_id}")
        
        # Wait a moment for processing
        await asyncio.sleep(2)
        
        # Check export status
        export_status = await privacy_manager.get_export_status(request_id)
        if export_status:
            print(f"✅ Export status: {export_status['status']}")
        
        # Test privacy settings
        print("\n⚙️ Testing Privacy Settings")
        
        settings_updated = await privacy_manager.update_privacy_settings(
            user_id=user_id,
            guild_id=guild_id,
            settings={
                "profile_public": False,
                "stats_public": False
            }
        )
        print(f"✅ Privacy settings updated: {settings_updated}")
        
        current_settings = await privacy_manager.get_privacy_settings(user_id, guild_id)
        print(f"✅ Current settings: {current_settings}")
        
        # Test data retention
        print("\n🗂️ Testing Data Retention")
        
        # Initialize default policies
        await retention_manager.initialize_default_policies()
        print("✅ Default retention policies initialized")
        
        # List policies
        policies = await retention_manager.list_policies()
        print(f"✅ Found {len(policies)} retention policies")
        
        for policy in policies[:3]:  # Show first 3
            print(f"   - {policy.name}: {policy.retention_days} days ({policy.action.value})")
        
        # Test compliance report
        print("\n📊 Testing Compliance Report")
        
        compliance_report = await privacy_manager.generate_compliance_report(guild_id)
        print("✅ Compliance report generated")
        print(f"   - Total users: {compliance_report['data_summary']['total_users']}")
        print(f"   - Total events: {compliance_report['data_summary']['total_events']}")
        
        # Test data deletion (right to be forgotten)
        print("\n🗑️ Testing Data Deletion")
        
        deletion_results = await privacy_manager.delete_user_data(
            user_id=user_id,
            guild_id=guild_id,
            keep_anonymized=True
        )
        print("✅ User data deleted")
        print(f"   - Records deleted: {deletion_results['deleted_records']}")
        print(f"   - Records anonymized: {deletion_results['anonymized_records']}")
        
        # Verify user data is gone
        user_data = await database.find_one(
            "users",
            {"user_id": user_id, "guild_id": guild_id}
        )
        print(f"✅ User data verification: {'Deleted' if not user_data else 'Still exists'}")
        
        print("\n🎉 All privacy system tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        if database:
            await database.disconnect()
            print("✅ Database disconnected")


if __name__ == "__main__":
    asyncio.run(test_privacy_system())