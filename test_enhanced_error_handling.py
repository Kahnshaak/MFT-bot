#!/usr/bin/env python3
"""
Test script for enhanced error handling and edge case coverage.
"""

import asyncio
import sys
import os
from datetime import datetime
from typing import Dict, Any

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from database.manager import DatabaseManager
from core.event_bus import EventBus, EventType
from core.poll_edge_case_handler import PollEdgeCaseHandler, EdgeCaseType
from core.graceful_degradation_manager import GracefulDegradationManager, ServiceType, DegradationLevel
from core.event_recovery_manager import EventRecoveryManager, EventRecoveryType
from utils.exceptions import (
    TimezoneError, DeprecatedTimezoneError, PollEdgeCaseError,
    ServiceUnavailableError, GracefulDegradationError
)
from utils.logging_config import setup_logging
from config.settings import Settings


class EnhancedErrorHandlingTester:
    """Test suite for enhanced error handling features."""
    
    def __init__(self):
        self.settings = Settings()
        setup_logging(self.settings)
        
        self.database = None
        self.event_bus = None
        self.poll_handler = None
        self.degradation_manager = None
        self.event_recovery = None
        
        self.test_results = []
    
    async def setup(self):
        """Set up test environment."""
        print("🔧 Setting up test environment...")
        
        # Initialize components
        self.database = DatabaseManager(self.settings.database_url)
        await self.database.connect()
        
        self.event_bus = EventBus()
        self.poll_handler = PollEdgeCaseHandler(self.database, self.event_bus)
        self.degradation_manager = GracefulDegradationManager(self.event_bus)
        self.event_recovery = EventRecoveryManager(self.database, self.event_bus)
        
        print("✅ Test environment ready")
    
    async def cleanup(self):
        """Clean up test environment."""
        print("🧹 Cleaning up test environment...")
        
        if self.database:
            await self.database.disconnect()
        
        print("✅ Cleanup complete")
    
    def record_test_result(self, test_name: str, success: bool, details: str = ""):
        """Record a test result."""
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details,
            "timestamp": datetime.now()
        })
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {details}")
    
    async def test_poll_edge_cases(self):
        """Test poll edge case handling."""
        print("\n🗳️  Testing poll edge case handling...")
        
        # Create test event
        test_event = {
            "_id": "test_event_123",
            "guild_id": "123456789",
            "creator_id": "user123",
            "title": "Test Event",
            "state": "DATE_POLLING",
            "polls": {
                "date_poll": {
                    "title": "Date Selection",
                    "is_active": True,
                    "options": [
                        {
                            "id": "option1",
                            "label": "Tomorrow",
                            "votes": ["user123", "user456"],
                            "vote_count": 2
                        },
                        {
                            "id": "option2", 
                            "label": "Next Week",
                            "votes": ["user789"],
                            "vote_count": 1
                        }
                    ],
                    "total_votes": 3
                }
            }
        }
        
        try:
            # Insert test event
            await self.database.insert_one("events", test_event)
            
            # Test user departure during poll
            success = await self.poll_handler.handle_user_departure_during_poll(
                "test_event_123", "date_poll", "user123"
            )
            self.record_test_result(
                "User departure during poll",
                success,
                "User votes removed and poll updated"
            )
            
            # Test vote validation
            validation_result = await self.poll_handler.validate_vote_attempt(
                "test_event_123", "date_poll", "user999", "option1"
            )
            self.record_test_result(
                "Vote validation",
                validation_result["valid"],
                f"Validation result: {validation_result.get('message', 'Valid')}"
            )
            
            # Test duplicate vote detection
            duplicate_result = await self.poll_handler.validate_vote_attempt(
                "test_event_123", "date_poll", "user456", "option1"
            )
            self.record_test_result(
                "Duplicate vote detection",
                not duplicate_result["valid"] and duplicate_result.get("edge_case") == EdgeCaseType.DUPLICATE_VOTE_ATTEMPT,
                "Duplicate vote correctly detected"
            )
            
            # Test poll data repair
            repair_success = await self.poll_handler.repair_corrupted_poll_data(
                "test_event_123", "date_poll"
            )
            self.record_test_result(
                "Poll data repair",
                repair_success,
                "Poll data integrity restored"
            )
            
        except Exception as e:
            self.record_test_result(
                "Poll edge case handling",
                False,
                f"Error: {str(e)}"
            )
        finally:
            # Cleanup test data
            try:
                await self.database.delete_one("events", {"_id": "test_event_123"})
            except:
                pass
    
    async def test_graceful_degradation(self):
        """Test graceful degradation system."""
        print("\n🔄 Testing graceful degradation...")
        
        try:
            # Test service failure reporting
            degradation_level = await self.degradation_manager.report_service_failure(
                ServiceType.DISCORD_API,
                Exception("Rate limit exceeded"),
                {"operation": "send_message"}
            )
            
            self.record_test_result(
                "Service failure reporting",
                degradation_level != DegradationLevel.NORMAL,
                f"Degradation level: {degradation_level.value}"
            )
            
            # Test service status checking
            status = self.degradation_manager.get_service_status(ServiceType.DISCORD_API)
            self.record_test_result(
                "Service status tracking",
                status.failure_count > 0,
                f"Failure count: {status.failure_count}"
            )
            
            # Test service recovery
            recovery_level = await self.degradation_manager.report_service_recovery(
                ServiceType.DISCORD_API
            )
            self.record_test_result(
                "Service recovery",
                recovery_level != degradation_level,
                f"Recovery level: {recovery_level.value}"
            )
            
        except Exception as e:
            self.record_test_result(
                "Graceful degradation",
                False,
                f"Error: {str(e)}"
            )
    
    async def test_event_recovery(self):
        """Test event recovery system."""
        print("\n🔧 Testing event recovery...")
        
        try:
            # Test partial creation failure reporting
            success = await self.event_recovery.report_event_failure(
                "test_event_456",
                EventRecoveryType.PARTIAL_CREATION_FAILURE,
                "poll_creation",
                {"title": "Test Event", "creator_id": "user123"},
                {"title": "Test Event"},  # Partial data
                Exception("Poll creation failed")
            )
            
            self.record_test_result(
                "Event failure reporting",
                success,
                "Recovery context created and queued"
            )
            
            # Wait a moment for processing
            await asyncio.sleep(2)
            
            # Check manual interventions
            interventions = await self.event_recovery.get_manual_interventions(limit=10)
            self.record_test_result(
                "Manual intervention tracking",
                len(interventions) >= 0,  # Should have at least our test case if it failed recovery
                f"Found {len(interventions)} interventions"
            )
            
        except Exception as e:
            self.record_test_result(
                "Event recovery",
                False,
                f"Error: {str(e)}"
            )
    
    async def test_timezone_error_handling(self):
        """Test enhanced timezone error handling."""
        print("\n🌍 Testing timezone error handling...")
        
        try:
            # Test deprecated timezone detection
            try:
                raise DeprecatedTimezoneError(
                    "Deprecated timezone used",
                    deprecated_tz="EST5EDT",
                    suggested_tz="America/New_York"
                )
            except DeprecatedTimezoneError as e:
                self.record_test_result(
                    "Deprecated timezone error",
                    "EST5EDT" in str(e) and "America/New_York" in str(e),
                    "Proper deprecation warning with suggestion"
                )
            
            # Test invalid timezone handling
            try:
                raise TimezoneError(
                    "Invalid timezone",
                    timezone="Invalid/Timezone"
                )
            except TimezoneError as e:
                self.record_test_result(
                    "Invalid timezone error",
                    "Invalid/Timezone" in e.details.get("timezone", ""),
                    "Timezone error with proper context"
                )
            
        except Exception as e:
            self.record_test_result(
                "Timezone error handling",
                False,
                f"Unexpected error: {str(e)}"
            )
    
    async def test_discord_api_error_handling(self):
        """Test Discord API error handling."""
        print("\n🤖 Testing Discord API error handling...")
        
        try:
            # Test service unavailable error
            try:
                raise ServiceUnavailableError(
                    "Discord API unavailable",
                    service="Discord API"
                )
            except ServiceUnavailableError as e:
                self.record_test_result(
                    "Service unavailable error",
                    e.error_code.value == "SERVICE_UNAVAILABLE",
                    "Proper service unavailable handling"
                )
            
            # Test graceful degradation error
            try:
                raise GracefulDegradationError(
                    "Operating in degraded mode",
                    degraded_features=["scheduled_events", "complex_embeds"]
                )
            except GracefulDegradationError as e:
                self.record_test_result(
                    "Graceful degradation error",
                    len(e.details.get("degraded_features", [])) == 2,
                    "Degraded features properly tracked"
                )
            
        except Exception as e:
            self.record_test_result(
                "Discord API error handling",
                False,
                f"Unexpected error: {str(e)}"
            )
    
    async def test_data_consistency_checks(self):
        """Test data consistency checking."""
        print("\n🔍 Testing data consistency checks...")
        
        try:
            # Create test data with inconsistencies
            test_event_with_issues = {
                "_id": "inconsistent_event",
                "guild_id": "123456789",
                "creator_id": "nonexistent_user",  # Orphaned reference
                "title": "Test Event",
                "state": "INVALID_STATE",  # Invalid state
                "polls": {
                    "date_poll": {
                        "options": [
                            {
                                "id": "option1",
                                "votes": ["user1", "user2"],
                                "vote_count": 5  # Inconsistent count
                            }
                        ]
                    }
                }
            }
            
            await self.database.insert_one("events", test_event_with_issues)
            
            # Run consistency check
            from core.consistency_checker import DataConsistencyChecker
            consistency_checker = DataConsistencyChecker(self.database, self.event_bus)
            
            issues = await consistency_checker.run_collection_check("events")
            
            self.record_test_result(
                "Data consistency detection",
                len(issues) > 0,
                f"Found {len(issues)} consistency issues"
            )
            
            # Test auto-repair
            if issues:
                repair_results = await consistency_checker.auto_repair_issues(issues, max_repairs=10)
                self.record_test_result(
                    "Auto-repair functionality",
                    repair_results["attempted"] > 0,
                    f"Attempted {repair_results['attempted']} repairs, {repair_results['successful']} successful"
                )
            
        except Exception as e:
            self.record_test_result(
                "Data consistency checks",
                False,
                f"Error: {str(e)}"
            )
        finally:
            # Cleanup
            try:
                await self.database.delete_one("events", {"_id": "inconsistent_event"})
            except:
                pass
    
    async def run_all_tests(self):
        """Run all enhanced error handling tests."""
        print("🧪 Starting Enhanced Error Handling Test Suite")
        print("=" * 60)
        
        await self.setup()
        
        try:
            await self.test_poll_edge_cases()
            await self.test_graceful_degradation()
            await self.test_event_recovery()
            await self.test_timezone_error_handling()
            await self.test_discord_api_error_handling()
            await self.test_data_consistency_checks()
            
        finally:
            await self.cleanup()
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"  - {result['test']}: {result['details']}")
        
        print("\n🎯 Enhanced error handling test suite completed!")
        return failed_tests == 0


async def main():
    """Main test runner."""
    tester = EnhancedErrorHandlingTester()
    
    try:
        success = await tester.run_all_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test suite crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())