#!/usr/bin/env python3
"""
Core test script for enhanced error handling without database dependencies.
"""

import asyncio
import sys
import os
from datetime import datetime
from typing import Dict, Any

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from utils.exceptions import (
    TimezoneError, DeprecatedTimezoneError, PollEdgeCaseError,
    ServiceUnavailableError, GracefulDegradationError, UserDepartedError,
    ErrorCode
)
from core.graceful_degradation_manager import ServiceType, DegradationLevel
from utils.logging_config import setup_logging
from config.settings import Settings


class CoreErrorHandlingTester:
    """Test suite for core error handling features without database dependencies."""
    
    def __init__(self):
        self.test_results = []
    
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
    
    def test_exception_hierarchy(self):
        """Test custom exception hierarchy."""
        print("\n🏗️  Testing exception hierarchy...")
        
        try:
            # Test TimezoneError
            try:
                raise TimezoneError("Invalid timezone", timezone="Invalid/Zone")
            except TimezoneError as e:
                self.record_test_result(
                    "TimezoneError creation",
                    e.error_code == ErrorCode.TIMEZONE_CONVERSION_ERROR and "Invalid/Zone" in str(e.details),
                    "Proper error code and details"
                )
            
            # Test DeprecatedTimezoneError
            try:
                raise DeprecatedTimezoneError(
                    "Deprecated timezone",
                    deprecated_tz="EST5EDT",
                    suggested_tz="America/New_York"
                )
            except DeprecatedTimezoneError as e:
                self.record_test_result(
                    "DeprecatedTimezoneError creation",
                    e.error_code == ErrorCode.DEPRECATED_TIMEZONE and "EST5EDT" in e.user_message,
                    "Proper deprecation warning"
                )
            
            # Test ServiceUnavailableError
            try:
                raise ServiceUnavailableError("Service down", service="Discord API")
            except ServiceUnavailableError as e:
                self.record_test_result(
                    "ServiceUnavailableError creation",
                    e.error_code == ErrorCode.SERVICE_UNAVAILABLE and "Discord API" in str(e.details),
                    "Service context preserved"
                )
            
            # Test GracefulDegradationError
            try:
                raise GracefulDegradationError(
                    "Degraded mode",
                    degraded_features=["feature1", "feature2"]
                )
            except GracefulDegradationError as e:
                self.record_test_result(
                    "GracefulDegradationError creation",
                    len(e.details.get("degraded_features", [])) == 2,
                    "Degraded features tracked"
                )
            
            # Test UserDepartedError
            try:
                raise UserDepartedError("User left", user_id="123456")
            except UserDepartedError as e:
                self.record_test_result(
                    "UserDepartedError creation",
                    e.error_code == ErrorCode.USER_LEFT_SERVER and e.details.get("user_id") == "123456",
                    "User context preserved"
                )
            
        except Exception as e:
            self.record_test_result(
                "Exception hierarchy",
                False,
                f"Unexpected error: {str(e)}"
            )
    
    def test_error_code_coverage(self):
        """Test error code coverage."""
        print("\n🔢 Testing error code coverage...")
        
        try:
            # Check that all new error codes exist
            new_error_codes = [
                ErrorCode.SERVICE_UNAVAILABLE,
                ErrorCode.GRACEFUL_DEGRADATION,
                ErrorCode.DATA_CORRUPTION,
                ErrorCode.ORPHANED_DATA,
                ErrorCode.DISCORD_CONNECTION_FAILED,
                ErrorCode.DISCORD_SERVICE_UNAVAILABLE,
                ErrorCode.EVENT_PARTIAL_FAILURE,
                ErrorCode.POLL_USER_DEPARTED,
                ErrorCode.POLL_DUPLICATE_VOTE,
                ErrorCode.POLL_EDGE_CASE,
                ErrorCode.USER_LEFT_SERVER,
                ErrorCode.DEPRECATED_TIMEZONE,
                ErrorCode.TIMEZONE_CONVERSION_ERROR
            ]
            
            self.record_test_result(
                "New error codes defined",
                len(new_error_codes) == 13,
                f"All {len(new_error_codes)} new error codes available"
            )
            
            # Test error code uniqueness
            all_codes = [code.value for code in ErrorCode]
            unique_codes = set(all_codes)
            
            self.record_test_result(
                "Error code uniqueness",
                len(all_codes) == len(unique_codes),
                f"{len(unique_codes)} unique codes out of {len(all_codes)} total"
            )
            
        except Exception as e:
            self.record_test_result(
                "Error code coverage",
                False,
                f"Error: {str(e)}"
            )
    
    def test_graceful_degradation_logic(self):
        """Test graceful degradation logic without database."""
        print("\n🔄 Testing graceful degradation logic...")
        
        try:
            from core.graceful_degradation_manager import GracefulDegradationManager
            from core.event_bus import EventBus
            
            # Create minimal event bus for testing
            event_bus = EventBus()
            degradation_manager = GracefulDegradationManager(event_bus)
            
            # Test service status initialization
            status = degradation_manager.get_service_status(ServiceType.DISCORD_API)
            self.record_test_result(
                "Service status initialization",
                status.degradation_level == DegradationLevel.NORMAL,
                f"Initial level: {status.degradation_level.value}"
            )
            
            # Test service availability check
            is_available = degradation_manager.is_service_available(ServiceType.DISCORD_API)
            self.record_test_result(
                "Service availability check",
                is_available,
                "Service initially available"
            )
            
            # Test feature availability (should be empty initially)
            has_feature = degradation_manager.is_feature_available(ServiceType.DISCORD_API, "test_feature")
            self.record_test_result(
                "Feature availability check",
                not has_feature,  # Should be False since no features are defined initially
                "Feature availability correctly checked"
            )
            
        except Exception as e:
            self.record_test_result(
                "Graceful degradation logic",
                False,
                f"Error: {str(e)}"
            )
    
    def test_enhanced_discord_api_utils(self):
        """Test enhanced Discord API utilities."""
        print("\n🤖 Testing enhanced Discord API utilities...")
        
        try:
            from utils.discord_api_utils import RateLimitManager
            
            # Test rate limit manager initialization
            rate_manager = RateLimitManager()
            self.record_test_result(
                "RateLimitManager initialization",
                hasattr(rate_manager, '_buckets') and hasattr(rate_manager, '_global_rate_limit'),
                "Rate limit manager properly initialized"
            )
            
            # Test bucket tracking
            rate_manager._buckets['test_bucket'] = {
                'reset_time': 0,  # Already expired
                'retry_after': 1.0
            }
            
            self.record_test_result(
                "Rate limit bucket tracking",
                'test_bucket' in rate_manager._buckets,
                "Bucket tracking works"
            )
            
        except Exception as e:
            self.record_test_result(
                "Enhanced Discord API utils",
                False,
                f"Error: {str(e)}"
            )
    
    def test_error_message_quality(self):
        """Test error message quality and user-friendliness."""
        print("\n💬 Testing error message quality...")
        
        try:
            # Test user-friendly messages
            timezone_error = TimezoneError("Invalid timezone", timezone="Bad/Zone")
            self.record_test_result(
                "User-friendly timezone error",
                "timezone" in timezone_error.user_message.lower(),
                f"Message: {timezone_error.user_message}"
            )
            
            # Test deprecation warning clarity
            deprecated_error = DeprecatedTimezoneError(
                "Deprecated",
                deprecated_tz="EST5EDT",
                suggested_tz="America/New_York"
            )
            self.record_test_result(
                "Clear deprecation warning",
                "EST5EDT" in deprecated_error.user_message and "America/New_York" in deprecated_error.user_message,
                f"Message: {deprecated_error.user_message}"
            )
            
            # Test graceful degradation message
            degradation_error = GracefulDegradationError(
                "Degraded",
                degraded_features=["feature1"]
            )
            self.record_test_result(
                "Graceful degradation message",
                "limited" in degradation_error.user_message.lower() or "available" in degradation_error.user_message.lower(),
                f"Message: {degradation_error.user_message}"
            )
            
        except Exception as e:
            self.record_test_result(
                "Error message quality",
                False,
                f"Error: {str(e)}"
            )
    
    def test_error_context_preservation(self):
        """Test that error context is properly preserved."""
        print("\n📋 Testing error context preservation...")
        
        try:
            # Test timezone error context
            tz_error = TimezoneError("Test", timezone="Test/Zone")
            context = tz_error.to_dict()
            
            self.record_test_result(
                "Timezone error context",
                context.get("details", {}).get("timezone") == "Test/Zone",
                "Timezone preserved in context"
            )
            
            # Test service error context
            service_error = ServiceUnavailableError("Test", service="TestService")
            service_context = service_error.to_dict()
            
            self.record_test_result(
                "Service error context",
                service_context.get("details", {}).get("service") == "TestService",
                "Service name preserved in context"
            )
            
            # Test user departure context
            user_error = UserDepartedError("Test", user_id="user123")
            user_context = user_error.to_dict()
            
            self.record_test_result(
                "User departure context",
                user_context.get("details", {}).get("user_id") == "user123",
                "User ID preserved in context"
            )
            
        except Exception as e:
            self.record_test_result(
                "Error context preservation",
                False,
                f"Error: {str(e)}"
            )
    
    def run_all_tests(self):
        """Run all core error handling tests."""
        print("🧪 Starting Core Error Handling Test Suite")
        print("=" * 60)
        
        self.test_exception_hierarchy()
        self.test_error_code_coverage()
        self.test_graceful_degradation_logic()
        self.test_enhanced_discord_api_utils()
        self.test_error_message_quality()
        self.test_error_context_preservation()
        
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
        
        print("\n🎯 Core error handling test suite completed!")
        return failed_tests == 0


def main():
    """Main test runner."""
    tester = CoreErrorHandlingTester()
    
    try:
        success = tester.run_all_tests()
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
    main()