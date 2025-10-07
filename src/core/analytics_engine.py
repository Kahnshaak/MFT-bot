"""
Advanced Analytics Engine for Game Night Bot

Provides comprehensive analytics, reporting, and predictive capabilities
for event attendance, game popularity, user engagement, and scheduling optimization.
"""

import asyncio
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass
from enum import Enum
import statistics
import json

from models.event import Event, EventState, RSVPStatus
from models.user import User, UserStatistics
from database.manager import DatabaseManager
from utils.logging_config import LoggerMixin


class TrendDirection(str, Enum):
    """Trend direction indicators."""
    UP = "UP"
    DOWN = "DOWN"
    STABLE = "STABLE"


class SeasonalPeriod(str, Enum):
    """Seasonal analysis periods."""
    SPRING = "SPRING"  # Mar-May
    SUMMER = "SUMMER"  # Jun-Aug
    FALL = "FALL"      # Sep-Nov
    WINTER = "WINTER"  # Dec-Feb


@dataclass
class TrendData:
    """Trend analysis data."""
    current_value: float
    previous_value: float
    change_percent: float
    direction: TrendDirection
    
    @classmethod
    def calculate(cls, current: float, previous: float) -> 'TrendData':
        """Calculate trend from current and previous values."""
        if previous == 0:
            change_percent = 100.0 if current > 0 else 0.0
            direction = TrendDirection.UP if current > 0 else TrendDirection.STABLE
        else:
            change_percent = ((current - previous) / previous) * 100
            if abs(change_percent) < 5:  # Less than 5% change is stable
                direction = TrendDirection.STABLE
            else:
                direction = TrendDirection.UP if change_percent > 0 else TrendDirection.DOWN
        
        return cls(
            current_value=current,
            previous_value=previous,
            change_percent=change_percent,
            direction=direction
        )


@dataclass
class AttendanceMetrics:
    """Attendance analysis metrics."""
    total_events: int
    completed_events: int
    total_rsvps: int
    total_attendees: int
    average_attendance_rate: float
    average_rsvp_count: float
    completion_rate: float
    no_show_rate: float
    trend: TrendData


@dataclass
class GamePopularityMetrics:
    """Game popularity analysis metrics."""
    game_name: str
    interest_count: int
    events_played: int
    total_attendees: int
    average_attendance: float
    seasonal_trends: Dict[SeasonalPeriod, int]
    growth_rate: float
    recommendation_score: float


@dataclass
class UserEngagementMetrics:
    """User engagement analysis metrics."""
    user_id: str
    username: str
    participation_score: float
    events_created: int
    events_attended: int
    attendance_rate: float
    rsvp_reliability: float
    favorite_games: List[str]
    activity_trend: TrendDirection
    last_active: datetime


@dataclass
class SchedulingRecommendation:
    """Event scheduling recommendation."""
    recommended_date: date
    recommended_time: str
    confidence_score: float
    expected_attendance: int
    reasoning: List[str]
    alternative_options: List[Dict[str, Any]]


class AnalyticsEngine(LoggerMixin):
    """
    Advanced analytics engine for comprehensive reporting and insights.
    
    Provides detailed analysis of attendance patterns, game popularity,
    user engagement, and predictive scheduling recommendations.
    """
    
    def __init__(self, database: DatabaseManager):
        self.database = database
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
        self._last_cache_update = {}
    
    async def get_attendance_analytics(
        self,
        guild_id: str,
        days_back: int = 30,
        include_trends: bool = True
    ) -> AttendanceMetrics:
        """
        Get comprehensive attendance analytics for a guild.
        
        Args:
            guild_id: Discord guild ID
            days_back: Number of days to analyze
            include_trends: Whether to include trend analysis
            
        Returns:
            AttendanceMetrics with detailed attendance data
        """
        cache_key = f"attendance_{guild_id}_{days_back}"
        if self._is_cached(cache_key):
            return self._cache[cache_key]
        
        try:
            # Get events in the specified period
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days_back)
            
            events = await self._get_events_in_period(guild_id, start_date, end_date)
            
            # Calculate basic metrics
            total_events = len(events)
            completed_events = len([e for e in events if e.state == EventState.COMPLETED])
            
            total_rsvps = 0
            total_attendees = 0
            attendance_rates = []
            
            for event in events:
                if event.state == EventState.COMPLETED:
                    rsvp_yes_count = event.get_rsvp_count(RSVPStatus.YES)
                    actual_attendees = sum(1 for attended in event.attendance.values() if attended)
                    
                    total_rsvps += rsvp_yes_count
                    total_attendees += actual_attendees
                    
                    if rsvp_yes_count > 0:
                        attendance_rates.append(actual_attendees / rsvp_yes_count)
            
            # Calculate derived metrics
            average_attendance_rate = statistics.mean(attendance_rates) if attendance_rates else 0.0
            average_rsvp_count = total_rsvps / max(completed_events, 1)
            completion_rate = completed_events / max(total_events, 1)
            no_show_rate = 1.0 - average_attendance_rate if average_attendance_rate > 0 else 0.0
            
            # Calculate trends if requested
            trend = None
            if include_trends:
                # Compare with previous period
                prev_start = start_date - timedelta(days=days_back)
                prev_events = await self._get_events_in_period(guild_id, prev_start, start_date)
                prev_completed = len([e for e in prev_events if e.state == EventState.COMPLETED])
                
                trend = TrendData.calculate(completed_events, prev_completed)
            
            metrics = AttendanceMetrics(
                total_events=total_events,
                completed_events=completed_events,
                total_rsvps=total_rsvps,
                total_attendees=total_attendees,
                average_attendance_rate=average_attendance_rate,
                average_rsvp_count=average_rsvp_count,
                completion_rate=completion_rate,
                no_show_rate=no_show_rate,
                trend=trend
            )
            
            self._cache[cache_key] = metrics
            self._last_cache_update[cache_key] = datetime.utcnow()
            
            return metrics
            
        except Exception as e:
            self.logger.error(
                "Failed to get attendance analytics",
                guild_id=guild_id,
                days_back=days_back,
                error=str(e),
                exc_info=True
            )
            # Return empty metrics on error
            return AttendanceMetrics(
                total_events=0,
                completed_events=0,
                total_rsvps=0,
                total_attendees=0,
                average_attendance_rate=0.0,
                average_rsvp_count=0.0,
                completion_rate=0.0,
                no_show_rate=0.0,
                trend=None
            )
    
    async def get_game_popularity_analytics(
        self,
        guild_id: str,
        days_back: int = 90,
        include_seasonal: bool = True
    ) -> List[GamePopularityMetrics]:
        """
        Get game popularity analytics with seasonal trends.
        
        Args:
            guild_id: Discord guild ID
            days_back: Number of days to analyze
            include_seasonal: Whether to include seasonal analysis
            
        Returns:
            List of GamePopularityMetrics sorted by popularity
        """
        cache_key = f"games_{guild_id}_{days_back}"
        if self._is_cached(cache_key):
            return self._cache[cache_key]
        
        try:
            # Get game interests from users
            users = await self._get_guild_users(guild_id)
            game_interests = defaultdict(int)
            
            for user in users:
                for interest in user.game_interests:
                    if interest.notification_enabled:
                        game_interests[interest.game_name] += 1
            
            # Get events with game data
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days_back)
            events = await self._get_events_in_period(guild_id, start_date, end_date)
            
            # Analyze game play frequency and attendance
            game_events = defaultdict(list)
            for event in events:
                if event.state == EventState.COMPLETED:
                    # Extract game from event title or polls
                    game_poll = event.get_poll("GAME")
                    if game_poll and game_poll.winner_option_id:
                        winner_option = game_poll.get_option_by_id(game_poll.winner_option_id)
                        if winner_option:
                            game_name = winner_option.value
                            game_events[game_name].append(event)
            
            # Calculate metrics for each game
            game_metrics = []
            for game_name in set(list(game_interests.keys()) + list(game_events.keys())):
                events_played = len(game_events[game_name])
                total_attendees = sum(
                    sum(1 for attended in event.attendance.values() if attended)
                    for event in game_events[game_name]
                )
                average_attendance = total_attendees / max(events_played, 1)
                
                # Calculate seasonal trends if requested
                seasonal_trends = {}
                if include_seasonal:
                    seasonal_trends = await self._calculate_seasonal_trends(
                        guild_id, game_name, days_back * 4  # Look back further for seasonal data
                    )
                
                # Calculate growth rate (simplified)
                growth_rate = self._calculate_game_growth_rate(game_name, game_events[game_name])
                
                # Calculate recommendation score
                recommendation_score = self._calculate_recommendation_score(
                    game_interests[game_name],
                    events_played,
                    average_attendance,
                    growth_rate
                )
                
                metrics = GamePopularityMetrics(
                    game_name=game_name,
                    interest_count=game_interests[game_name],
                    events_played=events_played,
                    total_attendees=total_attendees,
                    average_attendance=average_attendance,
                    seasonal_trends=seasonal_trends,
                    growth_rate=growth_rate,
                    recommendation_score=recommendation_score
                )
                game_metrics.append(metrics)
            
            # Sort by recommendation score
            game_metrics.sort(key=lambda x: x.recommendation_score, reverse=True)
            
            self._cache[cache_key] = game_metrics
            self._last_cache_update[cache_key] = datetime.utcnow()
            
            return game_metrics
            
        except Exception as e:
            self.logger.error(
                "Failed to get game popularity analytics",
                guild_id=guild_id,
                error=str(e),
                exc_info=True
            )
            return []
    
    async def get_user_engagement_metrics(
        self,
        guild_id: str,
        days_back: int = 30,
        limit: int = 50
    ) -> List[UserEngagementMetrics]:
        """
        Get user engagement metrics and participation scoring.
        
        Args:
            guild_id: Discord guild ID
            days_back: Number of days to analyze
            limit: Maximum number of users to return
            
        Returns:
            List of UserEngagementMetrics sorted by participation score
        """
        cache_key = f"engagement_{guild_id}_{days_back}"
        if self._is_cached(cache_key):
            return self._cache[cache_key][:limit]
        
        try:
            users = await self._get_guild_users(guild_id)
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days_back)
            events = await self._get_events_in_period(guild_id, start_date, end_date)
            
            user_metrics = []
            for user in users:
                # Calculate participation metrics
                events_created = len([e for e in events if e.creator_id == user.user_id])
                
                events_attended = 0
                total_rsvps = 0
                rsvp_matches = 0
                
                for event in events:
                    if event.state == EventState.COMPLETED:
                        if user.user_id in event.rsvp_data:
                            rsvp = event.rsvp_data[user.user_id]
                            if rsvp.status == RSVPStatus.YES:
                                total_rsvps += 1
                                if event.attendance.get(user.user_id, False):
                                    events_attended += 1
                                    rsvp_matches += 1
                
                attendance_rate = events_attended / max(total_rsvps, 1)
                rsvp_reliability = rsvp_matches / max(total_rsvps, 1)
                
                # Calculate participation score (0-100)
                participation_score = self._calculate_participation_score(
                    events_created,
                    events_attended,
                    attendance_rate,
                    rsvp_reliability,
                    len(user.game_interests)
                )
                
                # Determine activity trend
                activity_trend = self._calculate_activity_trend(user, events, days_back)
                
                # Get favorite games
                favorite_games = user.statistics.favorite_games[:3]
                
                metrics = UserEngagementMetrics(
                    user_id=user.user_id,
                    username=user.display_name or f"User_{user.user_id[:8]}",
                    participation_score=participation_score,
                    events_created=events_created,
                    events_attended=events_attended,
                    attendance_rate=attendance_rate,
                    rsvp_reliability=rsvp_reliability,
                    favorite_games=favorite_games,
                    activity_trend=activity_trend,
                    last_active=user.statistics.last_active
                )
                user_metrics.append(metrics)
            
            # Sort by participation score
            user_metrics.sort(key=lambda x: x.participation_score, reverse=True)
            
            self._cache[cache_key] = user_metrics
            self._last_cache_update[cache_key] = datetime.utcnow()
            
            return user_metrics[:limit]
            
        except Exception as e:
            self.logger.error(
                "Failed to get user engagement metrics",
                guild_id=guild_id,
                error=str(e),
                exc_info=True
            )
            return []
    
    async def get_scheduling_recommendations(
        self,
        guild_id: str,
        target_date_range: int = 14
    ) -> List[SchedulingRecommendation]:
        """
        Get predictive scheduling recommendations for optimal event timing.
        
        Args:
            guild_id: Discord guild ID
            target_date_range: Number of days ahead to recommend
            
        Returns:
            List of SchedulingRecommendation sorted by confidence score
        """
        try:
            # Get historical data for analysis
            historical_events = await self._get_events_in_period(
                guild_id,
                datetime.utcnow() - timedelta(days=90),
                datetime.utcnow()
            )
            
            users = await self._get_guild_users(guild_id)
            
            # Analyze optimal days and times
            day_attendance = defaultdict(list)
            time_attendance = defaultdict(list)
            
            for event in historical_events:
                if event.state == EventState.COMPLETED and event.schedule.selected_date:
                    day_of_week = event.schedule.selected_date.weekday()
                    attendance_rate = event.get_attendance_rate()
                    
                    day_attendance[day_of_week].append(attendance_rate)
                    
                    if event.schedule.selected_time:
                        hour = event.schedule.selected_time.hour
                        time_attendance[hour].append(attendance_rate)
            
            # Calculate average attendance by day and time
            optimal_days = {}
            for day, rates in day_attendance.items():
                optimal_days[day] = statistics.mean(rates) if rates else 0.0
            
            optimal_times = {}
            for hour, rates in time_attendance.items():
                optimal_times[hour] = statistics.mean(rates) if rates else 0.0
            
            # Generate recommendations for the next target_date_range days
            recommendations = []
            base_date = datetime.utcnow().date() + timedelta(days=1)
            
            for days_ahead in range(1, target_date_range + 1):
                target_date = base_date + timedelta(days=days_ahead)
                day_of_week = target_date.weekday()
                
                # Calculate expected attendance based on historical data
                day_score = optimal_days.get(day_of_week, 0.5)
                
                # Find best time for this day
                best_hour = max(optimal_times.keys(), key=lambda h: optimal_times[h]) if optimal_times else 19
                time_score = optimal_times.get(best_hour, 0.5)
                
                # Consider user availability
                availability_score = await self._calculate_availability_score(
                    users, target_date, best_hour
                )
                
                # Calculate overall confidence score
                confidence_score = (day_score * 0.4 + time_score * 0.4 + availability_score * 0.2)
                
                # Estimate expected attendance
                active_users = len([u for u in users if u.statistics.last_active > datetime.utcnow() - timedelta(days=30)])
                expected_attendance = int(active_users * confidence_score)
                
                # Generate reasoning
                reasoning = []
                if day_score > 0.7:
                    reasoning.append(f"High historical attendance on {target_date.strftime('%A')}s")
                if time_score > 0.7:
                    reasoning.append(f"Optimal time slot ({best_hour}:00)")
                if availability_score > 0.6:
                    reasoning.append("Good user availability overlap")
                
                if not reasoning:
                    reasoning.append("Based on general patterns")
                
                # Generate alternative times
                alternatives = []
                for alt_hour in sorted(optimal_times.keys(), key=lambda h: optimal_times[h], reverse=True)[1:4]:
                    alt_score = optimal_times[alt_hour]
                    alternatives.append({
                        "time": f"{alt_hour}:00",
                        "confidence": alt_score,
                        "expected_attendance": int(active_users * alt_score)
                    })
                
                recommendation = SchedulingRecommendation(
                    recommended_date=target_date,
                    recommended_time=f"{best_hour}:00",
                    confidence_score=confidence_score,
                    expected_attendance=expected_attendance,
                    reasoning=reasoning,
                    alternative_options=alternatives
                )
                recommendations.append(recommendation)
            
            # Sort by confidence score
            recommendations.sort(key=lambda x: x.confidence_score, reverse=True)
            
            return recommendations
            
        except Exception as e:
            self.logger.error(
                "Failed to get scheduling recommendations",
                guild_id=guild_id,
                error=str(e),
                exc_info=True
            )
            return []
    
    async def export_analytics_data(
        self,
        guild_id: str,
        include_user_data: bool = False
    ) -> Dict[str, Any]:
        """
        Export comprehensive analytics data for reporting.
        
        Args:
            guild_id: Discord guild ID
            include_user_data: Whether to include detailed user data
            
        Returns:
            Dictionary containing all analytics data
        """
        try:
            export_data = {
                "guild_id": guild_id,
                "export_timestamp": datetime.utcnow().isoformat(),
                "attendance_analytics": {},
                "game_popularity": [],
                "user_engagement": [],
                "scheduling_recommendations": [],
                "comparative_analysis": {}
            }
            
            # Get attendance analytics for different periods
            for period in [7, 30, 90]:
                metrics = await self.get_attendance_analytics(guild_id, period)
                export_data["attendance_analytics"][f"{period}_days"] = {
                    "total_events": metrics.total_events,
                    "completed_events": metrics.completed_events,
                    "average_attendance_rate": metrics.average_attendance_rate,
                    "completion_rate": metrics.completion_rate,
                    "trend": {
                        "direction": metrics.trend.direction.value if metrics.trend else None,
                        "change_percent": metrics.trend.change_percent if metrics.trend else 0
                    }
                }
            
            # Get game popularity
            game_metrics = await self.get_game_popularity_analytics(guild_id)
            export_data["game_popularity"] = [
                {
                    "game_name": g.game_name,
                    "interest_count": g.interest_count,
                    "events_played": g.events_played,
                    "average_attendance": g.average_attendance,
                    "recommendation_score": g.recommendation_score,
                    "seasonal_trends": {k.value: v for k, v in g.seasonal_trends.items()}
                }
                for g in game_metrics[:20]  # Top 20 games
            ]
            
            # Get user engagement (anonymized unless specifically requested)
            user_metrics = await self.get_user_engagement_metrics(guild_id)
            if include_user_data:
                export_data["user_engagement"] = [
                    {
                        "user_id": u.user_id,
                        "username": u.username,
                        "participation_score": u.participation_score,
                        "events_created": u.events_created,
                        "events_attended": u.events_attended,
                        "attendance_rate": u.attendance_rate,
                        "activity_trend": u.activity_trend.value
                    }
                    for u in user_metrics[:50]
                ]
            else:
                # Anonymized summary
                export_data["user_engagement"] = {
                    "total_users": len(user_metrics),
                    "average_participation_score": statistics.mean([u.participation_score for u in user_metrics]) if user_metrics else 0,
                    "highly_engaged_users": len([u for u in user_metrics if u.participation_score > 70]),
                    "active_creators": len([u for u in user_metrics if u.events_created > 0])
                }
            
            # Get scheduling recommendations
            recommendations = await self.get_scheduling_recommendations(guild_id)
            export_data["scheduling_recommendations"] = [
                {
                    "date": r.recommended_date.isoformat(),
                    "time": r.recommended_time,
                    "confidence_score": r.confidence_score,
                    "expected_attendance": r.expected_attendance,
                    "reasoning": r.reasoning
                }
                for r in recommendations[:10]
            ]
            
            # Add comparative analysis
            export_data["comparative_analysis"] = await self._generate_comparative_analysis(guild_id)
            
            return export_data
            
        except Exception as e:
            self.logger.error(
                "Failed to export analytics data",
                guild_id=guild_id,
                error=str(e),
                exc_info=True
            )
            return {"error": "Failed to export analytics data"}
    
    # Helper methods
    
    async def _get_events_in_period(
        self,
        guild_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Event]:
        """Get events within a specific time period."""
        try:
            query = {
                "guild_id": guild_id,
                "created_at": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
            
            events_data = await self.database.find_documents("events", query)
            return [Event(**event_data) for event_data in events_data]
            
        except Exception as e:
            self.logger.error(
                "Failed to get events in period",
                guild_id=guild_id,
                start_date=start_date,
                end_date=end_date,
                error=str(e)
            )
            return []
    
    async def _get_guild_users(self, guild_id: str) -> List[User]:
        """Get all users for a guild."""
        try:
            users_data = await self.database.find_documents(
                "users",
                {"guild_id": guild_id}
            )
            return [User(**user_data) for user_data in users_data]
            
        except Exception as e:
            self.logger.error(
                "Failed to get guild users",
                guild_id=guild_id,
                error=str(e)
            )
            return []
    
    async def _calculate_seasonal_trends(
        self,
        guild_id: str,
        game_name: str,
        days_back: int
    ) -> Dict[SeasonalPeriod, int]:
        """Calculate seasonal trends for a game."""
        try:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days_back)
            events = await self._get_events_in_period(guild_id, start_date, end_date)
            
            seasonal_counts = {season: 0 for season in SeasonalPeriod}
            
            for event in events:
                if event.state == EventState.COMPLETED and event.schedule.selected_date:
                    month = event.schedule.selected_date.month
                    if month in [3, 4, 5]:
                        seasonal_counts[SeasonalPeriod.SPRING] += 1
                    elif month in [6, 7, 8]:
                        seasonal_counts[SeasonalPeriod.SUMMER] += 1
                    elif month in [9, 10, 11]:
                        seasonal_counts[SeasonalPeriod.FALL] += 1
                    else:
                        seasonal_counts[SeasonalPeriod.WINTER] += 1
            
            return seasonal_counts
            
        except Exception as e:
            self.logger.error(
                "Failed to calculate seasonal trends",
                guild_id=guild_id,
                game_name=game_name,
                error=str(e)
            )
            return {season: 0 for season in SeasonalPeriod}
    
    def _calculate_game_growth_rate(self, game_name: str, events: List[Event]) -> float:
        """Calculate growth rate for a game based on recent events."""
        if len(events) < 2:
            return 0.0
        
        # Sort events by date
        sorted_events = sorted(events, key=lambda e: e.created_at)
        
        # Compare first half vs second half
        mid_point = len(sorted_events) // 2
        first_half = sorted_events[:mid_point]
        second_half = sorted_events[mid_point:]
        
        if len(first_half) == 0:
            return 100.0 if len(second_half) > 0 else 0.0
        
        growth_rate = ((len(second_half) - len(first_half)) / len(first_half)) * 100
        return max(-100.0, min(100.0, growth_rate))  # Clamp between -100% and 100%
    
    def _calculate_recommendation_score(
        self,
        interest_count: int,
        events_played: int,
        average_attendance: float,
        growth_rate: float
    ) -> float:
        """Calculate recommendation score for a game."""
        # Normalize components to 0-1 scale
        interest_score = min(interest_count / 20, 1.0)  # Max 20 interested users = 1.0
        events_score = min(events_played / 10, 1.0)     # Max 10 events = 1.0
        attendance_score = average_attendance / 10      # Assuming max 10 attendees per event
        growth_score = max(0, (growth_rate + 100) / 200)  # Convert -100 to +100 range to 0-1
        
        # Weighted combination
        score = (
            interest_score * 0.3 +
            events_score * 0.2 +
            attendance_score * 0.3 +
            growth_score * 0.2
        ) * 100
        
        return min(100.0, score)
    
    def _calculate_participation_score(
        self,
        events_created: int,
        events_attended: int,
        attendance_rate: float,
        rsvp_reliability: float,
        game_interests: int
    ) -> float:
        """Calculate user participation score."""
        # Component scores (0-1 scale)
        creation_score = min(events_created / 5, 1.0)    # Max 5 events created = 1.0
        attendance_score = min(events_attended / 10, 1.0) # Max 10 events attended = 1.0
        reliability_score = rsvp_reliability
        rate_score = attendance_rate
        interest_score = min(game_interests / 10, 1.0)   # Max 10 game interests = 1.0
        
        # Weighted combination
        score = (
            creation_score * 0.25 +
            attendance_score * 0.25 +
            reliability_score * 0.2 +
            rate_score * 0.2 +
            interest_score * 0.1
        ) * 100
        
        return min(100.0, score)
    
    def _calculate_activity_trend(
        self,
        user: User,
        events: List[Event],
        days_back: int
    ) -> TrendDirection:
        """Calculate user activity trend."""
        try:
            # Split period in half and compare activity
            mid_date = datetime.utcnow() - timedelta(days=days_back // 2)
            
            recent_activity = 0
            older_activity = 0
            
            for event in events:
                if event.creator_id == user.user_id or user.user_id in event.rsvp_data:
                    if event.created_at >= mid_date:
                        recent_activity += 1
                    else:
                        older_activity += 1
            
            if older_activity == 0:
                return TrendDirection.UP if recent_activity > 0 else TrendDirection.STABLE
            
            change_ratio = recent_activity / older_activity
            if change_ratio > 1.2:
                return TrendDirection.UP
            elif change_ratio < 0.8:
                return TrendDirection.DOWN
            else:
                return TrendDirection.STABLE
                
        except Exception:
            return TrendDirection.STABLE
    
    async def _calculate_availability_score(
        self,
        users: List[User],
        target_date: date,
        target_hour: int
    ) -> float:
        """Calculate availability score for a specific date and time."""
        try:
            day_of_week = target_date.weekday()
            available_users = 0
            total_users_with_availability = 0
            
            for user in users:
                if user.availability:
                    total_users_with_availability += 1
                    # Check if user is available at this day/time
                    for slot in user.availability:
                        if (slot.day.value == day_of_week and
                            slot.start_time.hour <= target_hour <= slot.end_time.hour):
                            available_users += 1
                            break
            
            if total_users_with_availability == 0:
                return 0.5  # Default score if no availability data
            
            return available_users / total_users_with_availability
            
        except Exception:
            return 0.5
    
    async def _generate_comparative_analysis(self, guild_id: str) -> Dict[str, Any]:
        """Generate comparative analysis between different event types and timing."""
        try:
            events = await self._get_events_in_period(
                guild_id,
                datetime.utcnow() - timedelta(days=90),
                datetime.utcnow()
            )
            
            # Analyze by day of week
            day_analysis = defaultdict(list)
            for event in events:
                if event.state == EventState.COMPLETED and event.schedule.selected_date:
                    day_name = event.schedule.selected_date.strftime('%A')
                    attendance_rate = event.get_attendance_rate()
                    day_analysis[day_name].append(attendance_rate)
            
            day_averages = {
                day: statistics.mean(rates) if rates else 0
                for day, rates in day_analysis.items()
            }
            
            # Analyze by time of day
            time_analysis = defaultdict(list)
            for event in events:
                if (event.state == EventState.COMPLETED and 
                    event.schedule.selected_time):
                    hour = event.schedule.selected_time.hour
                    time_slot = self._get_time_slot_name(hour)
                    attendance_rate = event.get_attendance_rate()
                    time_analysis[time_slot].append(attendance_rate)
            
            time_averages = {
                slot: statistics.mean(rates) if rates else 0
                for slot, rates in time_analysis.items()
            }
            
            return {
                "day_of_week_analysis": day_averages,
                "time_of_day_analysis": time_averages,
                "best_day": max(day_averages.keys(), key=lambda k: day_averages[k]) if day_averages else None,
                "best_time_slot": max(time_averages.keys(), key=lambda k: time_averages[k]) if time_averages else None
            }
            
        except Exception as e:
            self.logger.error(
                "Failed to generate comparative analysis",
                guild_id=guild_id,
                error=str(e)
            )
            return {}
    
    def _get_time_slot_name(self, hour: int) -> str:
        """Get time slot name for an hour."""
        if 6 <= hour < 12:
            return "Morning"
        elif 12 <= hour < 17:
            return "Afternoon"
        elif 17 <= hour < 21:
            return "Evening"
        else:
            return "Night"
    
    def _is_cached(self, cache_key: str) -> bool:
        """Check if data is cached and still valid."""
        if cache_key not in self._cache:
            return False
        
        last_update = self._last_cache_update.get(cache_key)
        if not last_update:
            return False
        
        return (datetime.utcnow() - last_update).total_seconds() < self._cache_ttl