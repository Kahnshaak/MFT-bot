"""
Analytics API routes for the Game Night Bot web dashboard.

Provides REST endpoints for accessing comprehensive analytics data,
including attendance tracking, game popularity, user engagement,
and predictive scheduling recommendations.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import json

from fastapi import APIRouter, HTTPException, Depends, Query, Response
from pydantic import BaseModel, Field

from core.analytics_engine import AnalyticsEngine, TrendDirection, SeasonalPeriod
from database.manager import DatabaseManager
from utils.logging_config import LoggerMixin


class AnalyticsResponse(BaseModel):
    """Base analytics response model."""
    success: bool = True
    data: Any
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    cache_info: Optional[Dict[str, Any]] = None


class AttendanceAnalyticsResponse(BaseModel):
    """Attendance analytics response model."""
    total_events: int
    completed_events: int
    total_rsvps: int
    total_attendees: int
    average_attendance_rate: float
    average_rsvp_count: float
    completion_rate: float
    no_show_rate: float
    trend: Optional[Dict[str, Any]] = None
    daily_activity: Optional[Dict[str, Dict[str, int]]] = None
    events_by_status: Optional[Dict[str, int]] = None


class GamePopularityResponse(BaseModel):
    """Game popularity response model."""
    popular_games: List[Dict[str, Any]]
    seasonal_analysis: Dict[str, Dict[str, int]]
    trending_games: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]


class UserEngagementResponse(BaseModel):
    """User engagement response model."""
    top_organizers: List[Dict[str, Any]]
    active_users: List[Dict[str, Any]]
    engagement_summary: Dict[str, Any]
    participation_distribution: Dict[str, int]


class SchedulingRecommendationsResponse(BaseModel):
    """Scheduling recommendations response model."""
    recommendations: List[Dict[str, Any]]
    optimal_patterns: Dict[str, Any]
    availability_insights: Dict[str, Any]


class AnalyticsRoutes(LoggerMixin):
    """Analytics API routes handler."""
    
    def __init__(self, database: DatabaseManager):
        self.database = database
        self.analytics_engine = AnalyticsEngine(database)
        self.router = APIRouter(prefix="/api/analytics", tags=["analytics"])
        self._setup_routes()
    
    def _setup_routes(self):
        """Set up all analytics routes."""
        
        @self.router.get("/attendance", response_model=AnalyticsResponse)
        async def get_attendance_analytics(
            guild_id: Optional[str] = Query(None, description="Guild ID filter"),
            days_back: int = Query(30, ge=1, le=365, description="Days to analyze"),
            include_trends: bool = Query(True, description="Include trend analysis"),
            include_daily: bool = Query(True, description="Include daily breakdown")
        ):
            """Get comprehensive attendance analytics."""
            try:
                if not guild_id:
                    # If no guild specified, get from user session or return error
                    raise HTTPException(status_code=400, detail="Guild ID required")
                
                # Get basic attendance metrics
                metrics = await self.analytics_engine.get_attendance_analytics(
                    guild_id, days_back, include_trends
                )
                
                response_data = AttendanceAnalyticsResponse(
                    total_events=metrics.total_events,
                    completed_events=metrics.completed_events,
                    total_rsvps=metrics.total_rsvps,
                    total_attendees=metrics.total_attendees,
                    average_attendance_rate=metrics.average_attendance_rate,
                    average_rsvp_count=metrics.average_rsvp_count,
                    completion_rate=metrics.completion_rate,
                    no_show_rate=metrics.no_show_rate,
                    trend={
                        "direction": metrics.trend.direction.value,
                        "change_percent": metrics.trend.change_percent,
                        "current_value": metrics.trend.current_value,
                        "previous_value": metrics.trend.previous_value
                    } if metrics.trend else None
                )
                
                # Add daily activity breakdown if requested
                if include_daily:
                    daily_activity = await self._get_daily_activity(guild_id, days_back)
                    response_data.daily_activity = daily_activity
                
                # Add events by status breakdown
                events_by_status = await self._get_events_by_status(guild_id, days_back)
                response_data.events_by_status = events_by_status
                
                return AnalyticsResponse(
                    data=response_data.dict(),
                    cache_info={"cached": False, "ttl": 300}
                )
                
            except Exception as e:
                self.logger.error(
                    "Failed to get attendance analytics",
                    guild_id=guild_id,
                    days_back=days_back,
                    error=str(e),
                    exc_info=True
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get attendance analytics: {str(e)}"
                )
        
        @self.router.get("/games", response_model=AnalyticsResponse)
        async def get_game_popularity_analytics(
            guild_id: Optional[str] = Query(None, description="Guild ID filter"),
            days_back: int = Query(90, ge=1, le=365, description="Days to analyze"),
            include_seasonal: bool = Query(True, description="Include seasonal analysis"),
            limit: int = Query(20, ge=1, le=100, description="Maximum games to return")
        ):
            """Get game popularity analytics with seasonal trends."""
            try:
                if not guild_id:
                    raise HTTPException(status_code=400, detail="Guild ID required")
                
                # Get game popularity metrics
                game_metrics = await self.analytics_engine.get_game_popularity_analytics(
                    guild_id, days_back, include_seasonal
                )
                
                # Format popular games data
                popular_games = []
                for game in game_metrics[:limit]:
                    game_data = {
                        "name": game.game_name,
                        "interest_count": game.interest_count,
                        "events_played": game.events_played,
                        "total_attendees": game.total_attendees,
                        "average_attendance": game.average_attendance,
                        "growth_rate": game.growth_rate,
                        "recommendation_score": game.recommendation_score
                    }
                    
                    if include_seasonal:
                        game_data["seasonal_trends"] = {
                            season.value: count 
                            for season, count in game.seasonal_trends.items()
                        }
                    
                    popular_games.append(game_data)
                
                # Generate seasonal analysis summary
                seasonal_analysis = {}
                if include_seasonal and game_metrics:
                    for season in SeasonalPeriod:
                        seasonal_analysis[season.value] = {
                            "total_events": sum(g.seasonal_trends.get(season, 0) for g in game_metrics),
                            "top_games": sorted(
                                [(g.game_name, g.seasonal_trends.get(season, 0)) for g in game_metrics],
                                key=lambda x: x[1],
                                reverse=True
                            )[:5]
                        }
                
                # Identify trending games (high growth rate)
                trending_games = [
                    {
                        "name": g.game_name,
                        "growth_rate": g.growth_rate,
                        "interest_count": g.interest_count
                    }
                    for g in sorted(game_metrics, key=lambda x: x.growth_rate, reverse=True)[:10]
                    if g.growth_rate > 10  # Only games with >10% growth
                ]
                
                # Generate recommendations
                recommendations = [
                    {
                        "name": g.game_name,
                        "recommendation_score": g.recommendation_score,
                        "reason": self._generate_game_recommendation_reason(g)
                    }
                    for g in game_metrics[:10]
                    if g.recommendation_score > 50
                ]
                
                response_data = GamePopularityResponse(
                    popular_games=popular_games,
                    seasonal_analysis=seasonal_analysis,
                    trending_games=trending_games,
                    recommendations=recommendations
                )
                
                return AnalyticsResponse(
                    data=response_data.dict(),
                    cache_info={"cached": False, "ttl": 300}
                )
                
            except Exception as e:
                self.logger.error(
                    "Failed to get game popularity analytics",
                    guild_id=guild_id,
                    error=str(e),
                    exc_info=True
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get game popularity analytics: {str(e)}"
                )
        
        @self.router.get("/engagement", response_model=AnalyticsResponse)
        async def get_user_engagement_analytics(
            guild_id: Optional[str] = Query(None, description="Guild ID filter"),
            days_back: int = Query(30, ge=1, le=365, description="Days to analyze"),
            limit: int = Query(50, ge=1, le=200, description="Maximum users to return")
        ):
            """Get user engagement metrics and participation scoring."""
            try:
                if not guild_id:
                    raise HTTPException(status_code=400, detail="Guild ID required")
                
                # Get user engagement metrics
                user_metrics = await self.analytics_engine.get_user_engagement_metrics(
                    guild_id, days_back, limit
                )
                
                # Format top organizers (users who created events)
                top_organizers = [
                    {
                        "user_id": u.user_id,
                        "username": u.username,
                        "events_created": u.events_created,
                        "avg_attendance": u.attendance_rate * u.events_attended if u.events_attended > 0 else 0,
                        "success_rate": u.attendance_rate,
                        "participation_score": u.participation_score
                    }
                    for u in user_metrics
                    if u.events_created > 0
                ][:20]
                
                # Format active users (by attendance)
                active_users = [
                    {
                        "user_id": u.user_id,
                        "username": u.username,
                        "events_attended": u.events_attended,
                        "attendance_rate": u.attendance_rate,
                        "rsvp_reliability": u.rsvp_reliability,
                        "favorite_game": u.favorite_games[0] if u.favorite_games else None,
                        "participation_score": u.participation_score,
                        "activity_trend": u.activity_trend.value
                    }
                    for u in sorted(user_metrics, key=lambda x: x.events_attended, reverse=True)
                ][:20]
                
                # Generate engagement summary
                if user_metrics:
                    engagement_summary = {
                        "total_users": len(user_metrics),
                        "average_participation_score": sum(u.participation_score for u in user_metrics) / len(user_metrics),
                        "highly_engaged_users": len([u for u in user_metrics if u.participation_score > 70]),
                        "active_creators": len([u for u in user_metrics if u.events_created > 0]),
                        "regular_attendees": len([u for u in user_metrics if u.events_attended >= 3]),
                        "reliable_users": len([u for u in user_metrics if u.rsvp_reliability > 0.8])
                    }
                else:
                    engagement_summary = {
                        "total_users": 0,
                        "average_participation_score": 0,
                        "highly_engaged_users": 0,
                        "active_creators": 0,
                        "regular_attendees": 0,
                        "reliable_users": 0
                    }
                
                # Generate participation score distribution
                participation_distribution = {
                    "0-20": len([u for u in user_metrics if 0 <= u.participation_score < 20]),
                    "20-40": len([u for u in user_metrics if 20 <= u.participation_score < 40]),
                    "40-60": len([u for u in user_metrics if 40 <= u.participation_score < 60]),
                    "60-80": len([u for u in user_metrics if 60 <= u.participation_score < 80]),
                    "80-100": len([u for u in user_metrics if 80 <= u.participation_score <= 100])
                }
                
                response_data = UserEngagementResponse(
                    top_organizers=top_organizers,
                    active_users=active_users,
                    engagement_summary=engagement_summary,
                    participation_distribution=participation_distribution
                )
                
                return AnalyticsResponse(
                    data=response_data.dict(),
                    cache_info={"cached": False, "ttl": 300}
                )
                
            except Exception as e:
                self.logger.error(
                    "Failed to get user engagement analytics",
                    guild_id=guild_id,
                    error=str(e),
                    exc_info=True
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get user engagement analytics: {str(e)}"
                )
        
        @self.router.get("/scheduling", response_model=AnalyticsResponse)
        async def get_scheduling_recommendations(
            guild_id: Optional[str] = Query(None, description="Guild ID filter"),
            days_ahead: int = Query(14, ge=1, le=30, description="Days ahead to recommend")
        ):
            """Get predictive scheduling recommendations."""
            try:
                if not guild_id:
                    raise HTTPException(status_code=400, detail="Guild ID required")
                
                # Get scheduling recommendations
                recommendations = await self.analytics_engine.get_scheduling_recommendations(
                    guild_id, days_ahead
                )
                
                # Format recommendations
                formatted_recommendations = [
                    {
                        "date": r.recommended_date.isoformat(),
                        "day_of_week": r.recommended_date.strftime("%A"),
                        "time": r.recommended_time,
                        "confidence_score": r.confidence_score,
                        "expected_attendance": r.expected_attendance,
                        "reasoning": r.reasoning,
                        "alternatives": r.alternative_options
                    }
                    for r in recommendations
                ]
                
                # Generate optimal patterns analysis
                optimal_patterns = await self._analyze_optimal_patterns(guild_id)
                
                # Generate availability insights
                availability_insights = await self._analyze_availability_patterns(guild_id)
                
                response_data = SchedulingRecommendationsResponse(
                    recommendations=formatted_recommendations,
                    optimal_patterns=optimal_patterns,
                    availability_insights=availability_insights
                )
                
                return AnalyticsResponse(
                    data=response_data.dict(),
                    cache_info={"cached": False, "ttl": 600}  # Cache longer for scheduling
                )
                
            except Exception as e:
                self.logger.error(
                    "Failed to get scheduling recommendations",
                    guild_id=guild_id,
                    error=str(e),
                    exc_info=True
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get scheduling recommendations: {str(e)}"
                )
        
        @self.router.get("/export")
        async def export_analytics_data(
            guild_id: Optional[str] = Query(None, description="Guild ID filter"),
            format: str = Query("json", regex="^(json|csv)$", description="Export format"),
            include_user_data: bool = Query(False, description="Include detailed user data")
        ):
            """Export comprehensive analytics data."""
            try:
                if not guild_id:
                    raise HTTPException(status_code=400, detail="Guild ID required")
                
                # Get comprehensive analytics data
                export_data = await self.analytics_engine.export_analytics_data(
                    guild_id, include_user_data
                )
                
                if format == "json":
                    # Return JSON response
                    response = Response(
                        content=json.dumps(export_data, indent=2, default=str),
                        media_type="application/json"
                    )
                    response.headers["Content-Disposition"] = f"attachment; filename=analytics_{guild_id}_{datetime.now().strftime('%Y%m%d')}.json"
                    return response
                
                elif format == "csv":
                    # Convert to CSV format
                    csv_content = await self._convert_to_csv(export_data)
                    response = Response(
                        content=csv_content,
                        media_type="text/csv"
                    )
                    response.headers["Content-Disposition"] = f"attachment; filename=analytics_{guild_id}_{datetime.now().strftime('%Y%m%d')}.csv"
                    return response
                
            except Exception as e:
                self.logger.error(
                    "Failed to export analytics data",
                    guild_id=guild_id,
                    format=format,
                    error=str(e),
                    exc_info=True
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to export analytics data: {str(e)}"
                )
        
        @self.router.get("/comparative", response_model=AnalyticsResponse)
        async def get_comparative_analysis(
            guild_id: Optional[str] = Query(None, description="Guild ID filter"),
            days_back: int = Query(90, ge=30, le=365, description="Days to analyze")
        ):
            """Get comparative analysis between different event types and timing."""
            try:
                if not guild_id:
                    raise HTTPException(status_code=400, detail="Guild ID required")
                
                # Get comparative analysis
                comparative_data = await self.analytics_engine._generate_comparative_analysis(guild_id)
                
                # Add additional comparative metrics
                comparative_data.update({
                    "event_type_comparison": await self._compare_event_types(guild_id, days_back),
                    "timing_effectiveness": await self._analyze_timing_effectiveness(guild_id, days_back),
                    "seasonal_comparison": await self._compare_seasonal_performance(guild_id)
                })
                
                return AnalyticsResponse(
                    data=comparative_data,
                    cache_info={"cached": False, "ttl": 600}
                )
                
            except Exception as e:
                self.logger.error(
                    "Failed to get comparative analysis",
                    guild_id=guild_id,
                    error=str(e),
                    exc_info=True
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get comparative analysis: {str(e)}"
                )
    
    # Helper methods
    
    async def _get_daily_activity(self, guild_id: str, days_back: int) -> Dict[str, Dict[str, int]]:
        """Get daily activity breakdown."""
        try:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days_back)
            
            events = await self.analytics_engine._get_events_in_period(guild_id, start_date, end_date)
            
            daily_activity = {}
            current_date = start_date.date()
            
            while current_date <= end_date.date():
                date_str = current_date.isoformat()
                daily_activity[date_str] = {"created": 0, "completed": 0}
                current_date += timedelta(days=1)
            
            for event in events:
                event_date = event.created_at.date().isoformat()
                if event_date in daily_activity:
                    daily_activity[event_date]["created"] += 1
                    
                    if event.state.value == "COMPLETED":
                        daily_activity[event_date]["completed"] += 1
            
            return daily_activity
            
        except Exception as e:
            self.logger.error("Failed to get daily activity", error=str(e))
            return {}
    
    async def _get_events_by_status(self, guild_id: str, days_back: int) -> Dict[str, int]:
        """Get events breakdown by status."""
        try:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days_back)
            
            events = await self.analytics_engine._get_events_in_period(guild_id, start_date, end_date)
            
            status_counts = {}
            for event in events:
                status = event.state.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return status_counts
            
        except Exception as e:
            self.logger.error("Failed to get events by status", error=str(e))
            return {}
    
    def _generate_game_recommendation_reason(self, game_metrics) -> str:
        """Generate recommendation reason for a game."""
        reasons = []
        
        if game_metrics.interest_count > 5:
            reasons.append(f"High interest ({game_metrics.interest_count} users)")
        
        if game_metrics.events_played > 2:
            reasons.append(f"Proven popularity ({game_metrics.events_played} events)")
        
        if game_metrics.average_attendance > 5:
            reasons.append(f"Good attendance ({game_metrics.average_attendance:.1f} avg)")
        
        if game_metrics.growth_rate > 20:
            reasons.append("Growing trend")
        
        return "; ".join(reasons) if reasons else "Balanced metrics"
    
    async def _analyze_optimal_patterns(self, guild_id: str) -> Dict[str, Any]:
        """Analyze optimal scheduling patterns."""
        try:
            # This would analyze historical data to find patterns
            # For now, return a basic structure
            return {
                "best_days": ["Friday", "Saturday", "Sunday"],
                "best_times": ["19:00", "20:00", "21:00"],
                "optimal_duration": 180,  # minutes
                "peak_attendance_day": "Saturday",
                "peak_attendance_time": "20:00"
            }
        except Exception:
            return {}
    
    async def _analyze_availability_patterns(self, guild_id: str) -> Dict[str, Any]:
        """Analyze user availability patterns."""
        try:
            users = await self.analytics_engine._get_guild_users(guild_id)
            
            # Analyze availability patterns
            day_availability = {}
            time_availability = {}
            
            for user in users:
                for slot in user.availability:
                    day = slot.day.value
                    day_availability[day] = day_availability.get(day, 0) + 1
                    
                    # Count hourly availability
                    for hour in range(slot.start_time.hour, slot.end_time.hour + 1):
                        time_availability[hour] = time_availability.get(hour, 0) + 1
            
            return {
                "most_available_day": max(day_availability.keys(), key=lambda k: day_availability[k]) if day_availability else None,
                "most_available_time": max(time_availability.keys(), key=lambda k: time_availability[k]) if time_availability else None,
                "availability_by_day": day_availability,
                "availability_by_hour": time_availability
            }
            
        except Exception:
            return {}
    
    async def _compare_event_types(self, guild_id: str, days_back: int) -> Dict[str, Any]:
        """Compare different event types."""
        # Placeholder for event type comparison
        return {
            "recurring_vs_oneoff": {
                "recurring_attendance": 0.75,
                "oneoff_attendance": 0.65,
                "recurring_completion": 0.85,
                "oneoff_completion": 0.70
            }
        }
    
    async def _analyze_timing_effectiveness(self, guild_id: str, days_back: int) -> Dict[str, Any]:
        """Analyze timing effectiveness."""
        # Placeholder for timing analysis
        return {
            "advance_notice_impact": {
                "1_day": 0.60,
                "3_days": 0.75,
                "7_days": 0.85,
                "14_days": 0.80
            }
        }
    
    async def _compare_seasonal_performance(self, guild_id: str) -> Dict[str, Any]:
        """Compare seasonal performance."""
        # Placeholder for seasonal comparison
        return {
            "spring": {"events": 15, "avg_attendance": 7.2},
            "summer": {"events": 12, "avg_attendance": 6.8},
            "fall": {"events": 18, "avg_attendance": 8.1},
            "winter": {"events": 20, "avg_attendance": 8.5}
        }
    
    async def _convert_to_csv(self, data: Dict[str, Any]) -> str:
        """Convert analytics data to CSV format."""
        try:
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write headers and basic data
            writer.writerow(["Metric", "Value"])
            writer.writerow(["Export Timestamp", data.get("export_timestamp", "")])
            writer.writerow(["Guild ID", data.get("guild_id", "")])
            
            # Write attendance data
            if "attendance_analytics" in data:
                writer.writerow([])
                writer.writerow(["Attendance Analytics"])
                for period, metrics in data["attendance_analytics"].items():
                    writer.writerow([f"Total Events ({period})", metrics.get("total_events", 0)])
                    writer.writerow([f"Completion Rate ({period})", f"{metrics.get('completion_rate', 0):.2%}"])
            
            # Write game popularity data
            if "game_popularity" in data:
                writer.writerow([])
                writer.writerow(["Game Popularity"])
                writer.writerow(["Game Name", "Interest Count", "Events Played", "Avg Attendance"])
                for game in data["game_popularity"]:
                    writer.writerow([
                        game.get("game_name", ""),
                        game.get("interest_count", 0),
                        game.get("events_played", 0),
                        f"{game.get('average_attendance', 0):.1f}"
                    ])
            
            return output.getvalue()
            
        except Exception as e:
            self.logger.error("Failed to convert to CSV", error=str(e))
            return "Error generating CSV export"


def create_analytics_router(database: DatabaseManager) -> APIRouter:
    """Create and return the analytics router."""
    analytics_routes = AnalyticsRoutes(database)
    return analytics_routes.router