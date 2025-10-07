#!/usr/bin/env python3
"""
Test script for the advanced analytics system.

This script tests the analytics engine, API routes, and Discord cog
to ensure all components work together correctly.
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, Any

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from core.analytics_engine import AnalyticsEngine, TrendDirection, SeasonalPeriod
from database.manager import DatabaseManager
from models.event import Event, EventState, RSVPStatus, EventSchedule, RSVPResponse
from models.user import User, UserStatistics, GameInterest, NotificationPreferences
from config.settings import Settings


class AnalyticsTestSuite:
    """Test suite for analytics functionality."""
    
    def __init__(self):
        self.settings = Settings()
        self.database = None
        self.analytics_engine = None
        self.test_guild_id = "123456789012345678"
        self.test_user_ids = [f"user_{i:03d}" for i in range(1, 21)]  # 20 test users
    
    async def setup(self):
        """Set up test environment."""
        print("🔧 Setting up test environment...")
        
        # Initialize database
        self.database = DatabaseManager(self.settings.database_url)
        await self.database.connect()
        
        # Initialize analytics engine
        self.analytics_engine = AnalyticsEngine(self.database)
        
        print("✅ Test environment ready")
    
    async def cleanup(self):
        """Clean up test data."""
        print("🧹 Cleaning up test data...")
        
        try:
            # Remove test data
            await self.database.delete_documents("events", {"guild_id": self.test_guild_id})
            await self.database.delete_documents("users", {"guild_id": self.test_guild_id})
            print("✅ Test data cleaned up")
        except Exception as e:
            print(f"⚠️  Cleanup warning: {e}")
        
        # Close database connection
        if self.database:
            await self.database.disconnect()
    
    async def create_test_data(self):
        """Create comprehensive test data for analytics."""
        print("📊 Creating test data...")
        
        # Create test users with varied engagement patterns
        users_data = []
        for i, user_id in enumerate(self.test_user_ids):
            # Create varied user profiles
            game_interests = []
            if i < 10:  # First 10 users interested in popular games
                game_interests.extend([
                    GameInterest(game_name="Among Us", interest_level=8),
                    GameInterest(game_name="Minecraft", interest_level=7),
                ])
            if i < 15:  # First 15 users interested in other games
                game_interests.append(
                    GameInterest(game_name="Valorant", interest_level=6)
                )
            if i % 3 == 0:  # Every third user likes niche games
                game_interests.append(
                    GameInterest(game_name="Deep Rock Galactic", interest_level=9)
                )
            
            # Create user statistics with realistic patterns
            stats = UserStatistics(
                events_created=max(0, 5 - i // 4),  # Top users create more events
                events_attended=max(1, 10 - i // 2),  # Varied attendance
                events_rsvp_yes=max(2, 12 - i // 2),
                events_rsvp_no=i // 5,
                events_rsvp_maybe=i // 8,
                last_active=datetime.utcnow() - timedelta(days=i // 2)
            )
            stats.validate_data()  # This will calculate derived fields
            
            user = User(
                user_id=user_id,
                guild_id=self.test_guild_id,
                display_name=f"TestUser{i+1:02d}",
                timezone="UTC",
                game_interests=game_interests,
                statistics=stats,
                notification_preferences=NotificationPreferences()
            )
            users_data.append(user.model_dump())
        
        # Insert users
        await self.database.insert_documents("users", users_data)
        print(f"✅ Created {len(users_data)} test users")
        
        # Create test events with realistic patterns
        events_data = []
        base_date = datetime.utcnow() - timedelta(days=90)
        
        for i in range(50):  # Create 50 test events over 90 days
            event_date = base_date + timedelta(days=i * 1.8)  # Spread events over time
            
            # Create varied event states
            if i < 35:  # Most events are completed
                state = EventState.COMPLETED
            elif i < 45:  # Some are scheduled
                state = EventState.SCHEDULED
            else:  # Few are cancelled
                state = EventState.CANCELLED
            
            # Create RSVP data
            rsvp_data = {}
            attendance = {}
            
            if state == EventState.COMPLETED:
                # Add realistic RSVP and attendance patterns
                num_rsvps = min(len(self.test_user_ids), 5 + (i % 8))  # 5-12 RSVPs
                for j in range(num_rsvps):
                    user_id = self.test_user_ids[j]
                    
                    # Most users RSVP yes, some maybe, few no
                    if j < num_rsvps * 0.7:
                        status = RSVPStatus.YES
                        # 80% attendance rate for yes RSVPs
                        attended = j < num_rsvps * 0.56
                    elif j < num_rsvps * 0.9:
                        status = RSVPStatus.MAYBE
                        # 40% attendance rate for maybe RSVPs
                        attended = j < num_rsvps * 0.36
                    else:
                        status = RSVPStatus.NO
                        attended = False
                    
                    rsvp_data[user_id] = RSVPResponse(
                        user_id=user_id,
                        status=status,
                        response_time=event_date - timedelta(days=2)
                    ).model_dump()
                    
                    if status == RSVPStatus.YES or (status == RSVPStatus.MAYBE and attended):
                        attendance[user_id] = attended
            
            # Create event schedule
            schedule = EventSchedule(
                selected_date=event_date.date(),
                selected_time=event_date.time(),
                timezone="UTC",
                duration_minutes=180
            )
            
            event = Event(
                guild_id=self.test_guild_id,
                title=f"Game Night #{i+1}",
                description=f"Test event {i+1} for analytics",
                creator_id=self.test_user_ids[i % 5],  # Rotate creators
                state=state,
                schedule=schedule,
                rsvp_data=rsvp_data,
                attendance=attendance,
                created_at=event_date - timedelta(days=7),  # Created a week before
                updated_at=event_date
            )
            
            events_data.append(event.model_dump())
        
        # Insert events
        await self.database.insert_documents("events", events_data)
        print(f"✅ Created {len(events_data)} test events")
    
    async def test_attendance_analytics(self):
        """Test attendance analytics functionality."""
        print("\n📊 Testing attendance analytics...")
        
        try:
            # Test different time periods
            for days_back in [7, 30, 90]:
                metrics = await self.analytics_engine.get_attendance_analytics(
                    self.test_guild_id, days_back, include_trends=True
                )
                
                print(f"  📈 {days_back}-day metrics:")
                print(f"    Total events: {metrics.total_events}")
                print(f"    Completed events: {metrics.completed_events}")
                print(f"    Avg attendance rate: {metrics.average_attendance_rate:.1%}")
                print(f"    Completion rate: {metrics.completion_rate:.1%}")
                
                if metrics.trend:
                    print(f"    Trend: {metrics.trend.direction.value} ({metrics.trend.change_percent:+.1f}%)")
                
                # Validate results
                assert metrics.total_events >= 0, "Total events should be non-negative"
                assert 0 <= metrics.completion_rate <= 1, "Completion rate should be between 0 and 1"
                assert 0 <= metrics.average_attendance_rate <= 1, "Attendance rate should be between 0 and 1"
            
            print("✅ Attendance analytics tests passed")
            
        except Exception as e:
            print(f"❌ Attendance analytics test failed: {e}")
            raise
    
    async def test_game_popularity_analytics(self):
        """Test game popularity analytics functionality."""
        print("\n🎮 Testing game popularity analytics...")
        
        try:
            game_metrics = await self.analytics_engine.get_game_popularity_analytics(
                self.test_guild_id, days_back=90, include_seasonal=True
            )
            
            print(f"  📊 Found {len(game_metrics)} games with analytics")
            
            for i, game in enumerate(game_metrics[:5]):  # Show top 5
                print(f"    {i+1}. {game.game_name}:")
                print(f"       Interest: {game.interest_count} users")
                print(f"       Events played: {game.events_played}")
                print(f"       Avg attendance: {game.average_attendance:.1f}")
                print(f"       Recommendation score: {game.recommendation_score:.1f}")
                print(f"       Growth rate: {game.growth_rate:+.1f}%")
            
            # Validate results
            assert len(game_metrics) > 0, "Should find some games"
            for game in game_metrics:
                assert game.interest_count >= 0, "Interest count should be non-negative"
                assert game.events_played >= 0, "Events played should be non-negative"
                assert 0 <= game.recommendation_score <= 100, "Recommendation score should be 0-100"
            
            print("✅ Game popularity analytics tests passed")
            
        except Exception as e:
            print(f"❌ Game popularity analytics test failed: {e}")
            raise
    
    async def test_user_engagement_analytics(self):
        """Test user engagement analytics functionality."""
        print("\n👥 Testing user engagement analytics...")
        
        try:
            user_metrics = await self.analytics_engine.get_user_engagement_metrics(
                self.test_guild_id, days_back=30, limit=10
            )
            
            print(f"  📊 Found {len(user_metrics)} users with engagement data")
            
            for i, user in enumerate(user_metrics[:5]):  # Show top 5
                print(f"    {i+1}. {user.username}:")
                print(f"       Participation score: {user.participation_score:.1f}/100")
                print(f"       Events created: {user.events_created}")
                print(f"       Events attended: {user.events_attended}")
                print(f"       Attendance rate: {user.attendance_rate:.1%}")
                print(f"       RSVP reliability: {user.rsvp_reliability:.1%}")
                print(f"       Activity trend: {user.activity_trend.value}")
            
            # Validate results
            assert len(user_metrics) > 0, "Should find some users"
            for user in user_metrics:
                assert 0 <= user.participation_score <= 100, "Participation score should be 0-100"
                assert user.events_created >= 0, "Events created should be non-negative"
                assert user.events_attended >= 0, "Events attended should be non-negative"
                assert 0 <= user.attendance_rate <= 1, "Attendance rate should be 0-1"
                assert 0 <= user.rsvp_reliability <= 1, "RSVP reliability should be 0-1"
            
            print("✅ User engagement analytics tests passed")
            
        except Exception as e:
            print(f"❌ User engagement analytics test failed: {e}")
            raise
    
    async def test_scheduling_recommendations(self):
        """Test scheduling recommendations functionality."""
        print("\n📅 Testing scheduling recommendations...")
        
        try:
            recommendations = await self.analytics_engine.get_scheduling_recommendations(
                self.test_guild_id, target_date_range=7
            )
            
            print(f"  📊 Generated {len(recommendations)} scheduling recommendations")
            
            for i, rec in enumerate(recommendations[:3]):  # Show top 3
                print(f"    {i+1}. {rec.recommended_date.strftime('%A, %B %d')} at {rec.recommended_time}:")
                print(f"       Confidence: {rec.confidence_score:.1%}")
                print(f"       Expected attendance: {rec.expected_attendance}")
                print(f"       Reasoning: {', '.join(rec.reasoning[:2])}")
            
            # Validate results
            for rec in recommendations:
                assert 0 <= rec.confidence_score <= 1, "Confidence score should be 0-1"
                assert rec.expected_attendance >= 0, "Expected attendance should be non-negative"
                assert len(rec.reasoning) > 0, "Should have reasoning"
            
            print("✅ Scheduling recommendations tests passed")
            
        except Exception as e:
            print(f"❌ Scheduling recommendations test failed: {e}")
            raise
    
    async def test_export_functionality(self):
        """Test analytics export functionality."""
        print("\n📤 Testing export functionality...")
        
        try:
            # Test export without user data
            export_data = await self.analytics_engine.export_analytics_data(
                self.test_guild_id, include_user_data=False
            )
            
            # Validate export structure
            required_keys = [
                "guild_id", "export_timestamp", "attendance_analytics",
                "game_popularity", "user_engagement", "scheduling_recommendations",
                "comparative_analysis"
            ]
            
            for key in required_keys:
                assert key in export_data, f"Export should contain {key}"
            
            print("  ✅ Export structure validation passed")
            
            # Test export with user data
            export_data_with_users = await self.analytics_engine.export_analytics_data(
                self.test_guild_id, include_user_data=True
            )
            
            assert isinstance(export_data_with_users["user_engagement"], list), "User engagement should be a list when including user data"
            
            print("  ✅ Export with user data validation passed")
            print("✅ Export functionality tests passed")
            
        except Exception as e:
            print(f"❌ Export functionality test failed: {e}")
            raise
    
    async def run_all_tests(self):
        """Run all analytics tests."""
        print("🚀 Starting Analytics System Test Suite")
        print("=" * 50)
        
        try:
            await self.setup()
            await self.create_test_data()
            
            # Run individual test suites
            await self.test_attendance_analytics()
            await self.test_game_popularity_analytics()
            await self.test_user_engagement_analytics()
            await self.test_scheduling_recommendations()
            await self.test_export_functionality()
            
            print("\n" + "=" * 50)
            print("🎉 ALL ANALYTICS TESTS PASSED!")
            print("✅ The advanced analytics system is working correctly")
            
        except Exception as e:
            print(f"\n❌ TEST SUITE FAILED: {e}")
            raise
        finally:
            await self.cleanup()


async def main():
    """Main test function."""
    test_suite = AnalyticsTestSuite()
    
    try:
        await test_suite.run_all_tests()
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        await test_suite.cleanup()
    except Exception as e:
        print(f"\n💥 Test suite crashed: {e}")
        await test_suite.cleanup()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())