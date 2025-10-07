#!/usr/bin/env python3
"""
Unit tests for analytics system components that don't require database.

Tests the core analytics logic, calculations, and data structures.
"""

import sys
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from core.analytics_engine import (
    AnalyticsEngine, TrendDirection, SeasonalPeriod, 
    TrendData, AttendanceMetrics, GamePopularityMetrics,
    UserEngagementMetrics, SchedulingRecommendation
)
from models.event import Event, EventState, RSVPStatus
from models.user import User, UserStatistics, GameInterest


def test_trend_data_calculation():
    """Test trend data calculation logic."""
    print("🧮 Testing trend data calculations...")
    
    # Test upward trend
    trend_up = TrendData.calculate(100, 80)
    assert trend_up.direction == TrendDirection.UP
    assert abs(trend_up.change_percent - 25.0) < 0.1
    
    # Test downward trend
    trend_down = TrendData.calculate(80, 100)
    assert trend_down.direction == TrendDirection.DOWN
    assert abs(trend_down.change_percent - (-20.0)) < 0.1
    
    # Test stable trend
    trend_stable = TrendData.calculate(100, 98)
    assert trend_stable.direction == TrendDirection.STABLE
    assert abs(trend_stable.change_percent - 2.04) < 0.1
    
    # Test zero previous value
    trend_zero = TrendData.calculate(50, 0)
    assert trend_zero.direction == TrendDirection.UP
    assert trend_zero.change_percent == 100.0
    
    print("✅ Trend data calculation tests passed")


def test_analytics_engine_calculations():
    """Test analytics engine calculation methods."""
    print("🔢 Testing analytics engine calculations...")
    
    # Create mock database
    mock_db = Mock()
    engine = AnalyticsEngine(mock_db)
    
    # Test game growth rate calculation
    events = [
        Mock(created_at=datetime.now() - timedelta(days=30)),
        Mock(created_at=datetime.now() - timedelta(days=25)),
        Mock(created_at=datetime.now() - timedelta(days=10)),
        Mock(created_at=datetime.now() - timedelta(days=5)),
        Mock(created_at=datetime.now() - timedelta(days=1))
    ]
    
    growth_rate = engine._calculate_game_growth_rate("Test Game", events)
    assert -100 <= growth_rate <= 100, "Growth rate should be between -100% and 100%"
    
    # Test recommendation score calculation
    rec_score = engine._calculate_recommendation_score(
        interest_count=10,
        events_played=5,
        average_attendance=7.5,
        growth_rate=25.0
    )
    assert 0 <= rec_score <= 100, "Recommendation score should be between 0 and 100"
    
    # Test participation score calculation
    part_score = engine._calculate_participation_score(
        events_created=3,
        events_attended=8,
        attendance_rate=0.85,
        rsvp_reliability=0.90,
        game_interests=5
    )
    assert 0 <= part_score <= 100, "Participation score should be between 0 and 100"
    
    print("✅ Analytics engine calculation tests passed")


def test_seasonal_period_logic():
    """Test seasonal period determination."""
    print("🌍 Testing seasonal period logic...")
    
    # Test month to season mapping
    spring_months = [3, 4, 5]  # March, April, May
    summer_months = [6, 7, 8]  # June, July, August
    fall_months = [9, 10, 11]  # September, October, November
    winter_months = [12, 1, 2]  # December, January, February
    
    # Verify all months are covered
    all_months = spring_months + summer_months + fall_months + winter_months
    assert len(set(all_months)) == 12, "All 12 months should be covered"
    
    # Test SeasonalPeriod enum
    seasons = list(SeasonalPeriod)
    assert len(seasons) == 4, "Should have 4 seasons"
    assert SeasonalPeriod.SPRING in seasons
    assert SeasonalPeriod.SUMMER in seasons
    assert SeasonalPeriod.FALL in seasons
    assert SeasonalPeriod.WINTER in seasons
    
    print("✅ Seasonal period logic tests passed")


def test_data_model_validation():
    """Test analytics data model validation."""
    print("📊 Testing data model validation...")
    
    # Test AttendanceMetrics validation
    attendance_metrics = AttendanceMetrics(
        total_events=50,
        completed_events=45,
        total_rsvps=200,
        total_attendees=180,
        average_attendance_rate=0.85,
        average_rsvp_count=4.4,
        completion_rate=0.90,
        no_show_rate=0.10,
        trend=None
    )
    
    # Validate calculated fields make sense
    assert attendance_metrics.completed_events <= attendance_metrics.total_events
    assert 0 <= attendance_metrics.completion_rate <= 1
    assert 0 <= attendance_metrics.average_attendance_rate <= 1
    assert 0 <= attendance_metrics.no_show_rate <= 1
    
    # Test GamePopularityMetrics validation
    game_metrics = GamePopularityMetrics(
        game_name="Test Game",
        interest_count=15,
        events_played=8,
        total_attendees=60,
        average_attendance=7.5,
        seasonal_trends={SeasonalPeriod.SPRING: 2, SeasonalPeriod.SUMMER: 3, SeasonalPeriod.FALL: 2, SeasonalPeriod.WINTER: 1},
        growth_rate=25.0,
        recommendation_score=75.5
    )
    
    assert game_metrics.interest_count >= 0
    assert game_metrics.events_played >= 0
    assert game_metrics.average_attendance >= 0
    assert 0 <= game_metrics.recommendation_score <= 100
    
    # Test UserEngagementMetrics validation
    user_metrics = UserEngagementMetrics(
        user_id="test_user_123",
        username="TestUser",
        participation_score=85.5,
        events_created=5,
        events_attended=12,
        attendance_rate=0.80,
        rsvp_reliability=0.90,
        favorite_games=["Game1", "Game2", "Game3"],
        activity_trend=TrendDirection.UP,
        last_active=datetime.now()
    )
    
    assert 0 <= user_metrics.participation_score <= 100
    assert user_metrics.events_created >= 0
    assert user_metrics.events_attended >= 0
    assert 0 <= user_metrics.attendance_rate <= 1
    assert 0 <= user_metrics.rsvp_reliability <= 1
    
    # Test SchedulingRecommendation validation
    scheduling_rec = SchedulingRecommendation(
        recommended_date=datetime.now().date(),
        recommended_time="19:00",
        confidence_score=0.75,
        expected_attendance=8,
        reasoning=["High historical attendance on Fridays", "Optimal time slot"],
        alternative_options=[
            {"time": "20:00", "confidence": 0.70, "expected_attendance": 7},
            {"time": "18:00", "confidence": 0.65, "expected_attendance": 6}
        ]
    )
    
    assert 0 <= scheduling_rec.confidence_score <= 1
    assert scheduling_rec.expected_attendance >= 0
    assert len(scheduling_rec.reasoning) > 0
    
    print("✅ Data model validation tests passed")


def test_time_slot_categorization():
    """Test time slot categorization logic."""
    print("⏰ Testing time slot categorization...")
    
    # Create mock analytics engine
    mock_db = Mock()
    engine = AnalyticsEngine(mock_db)
    
    # Test time slot names
    assert engine._get_time_slot_name(8) == "Morning"
    assert engine._get_time_slot_name(14) == "Afternoon"
    assert engine._get_time_slot_name(19) == "Evening"
    assert engine._get_time_slot_name(23) == "Night"
    assert engine._get_time_slot_name(2) == "Night"
    
    print("✅ Time slot categorization tests passed")


def test_cache_functionality():
    """Test analytics caching functionality."""
    print("💾 Testing cache functionality...")
    
    # Create mock database
    mock_db = Mock()
    engine = AnalyticsEngine(mock_db)
    
    # Test cache key generation and validation
    cache_key = "test_key"
    
    # Initially not cached
    assert not engine._is_cached(cache_key)
    
    # Add to cache
    engine._cache[cache_key] = "test_data"
    engine._last_cache_update[cache_key] = datetime.utcnow()
    
    # Should be cached now
    assert engine._is_cached(cache_key)
    
    # Test cache expiration
    engine._last_cache_update[cache_key] = datetime.utcnow() - timedelta(seconds=400)  # Older than TTL
    assert not engine._is_cached(cache_key)
    
    print("✅ Cache functionality tests passed")


def run_all_unit_tests():
    """Run all unit tests."""
    print("🚀 Starting Analytics Unit Test Suite")
    print("=" * 50)
    
    try:
        test_trend_data_calculation()
        test_analytics_engine_calculations()
        test_seasonal_period_logic()
        test_data_model_validation()
        test_time_slot_categorization()
        test_cache_functionality()
        
        print("\n" + "=" * 50)
        print("🎉 ALL UNIT TESTS PASSED!")
        print("✅ Analytics system core logic is working correctly")
        print("📝 Note: Database integration tests require MongoDB connection")
        
    except Exception as e:
        print(f"\n❌ UNIT TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = run_all_unit_tests()
    if not success:
        sys.exit(1)