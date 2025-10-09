"""
Analytics API routes for the Game Night Bot web dashboard.

Provides basic REST endpoints for simple analytics data.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database.manager import DatabaseManager
from utils.logging_config import LoggerMixin


class BasicStatsResponse(BaseModel):
    """Basic statistics response model."""
    total_events: int
    completed_events: int
    total_users: int
    popular_games: List[str]


class AnalyticsRoutes(LoggerMixin):
    """Analytics API routes handler."""
    
    def __init__(self, database: DatabaseManager):
        self.database = database
        self.router = APIRouter(prefix="/api/analytics", tags=["analytics"])
        self._setup_routes()
    
    def _setup_routes(self):
        """Set up basic analytics routes."""
        
        @self.router.get("/stats", response_model=BasicStatsResponse)
        async def get_basic_stats(
            guild_id: str = Query(..., description="Guild ID")
        ):
            """Get basic statistics for a guild."""
            try:
                # Get basic event counts
                events_collection = self.database.get_collection("events")
                total_events = await events_collection.count_documents({"guild_id": guild_id})
                completed_events = await events_collection.count_documents({
                    "guild_id": guild_id,
                    "state": "COMPLETED"
                })
                
                # Get user count
                users_collection = self.database.get_collection("users")
                total_users = await users_collection.count_documents({"guild_id": guild_id})
                
                # Get popular games (simple aggregation)
                pipeline = [
                    {"$match": {"guild_id": guild_id}},
                    {"$unwind": "$game_interests"},
                    {"$group": {"_id": "$game_interests.game_name", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                    {"$limit": 5}
                ]
                popular_games_cursor = users_collection.aggregate(pipeline)
                popular_games = [doc["_id"] async for doc in popular_games_cursor]
                
                return BasicStatsResponse(
                    total_events=total_events,
                    completed_events=completed_events,
                    total_users=total_users,
                    popular_games=popular_games
                )
                
            except Exception as e:
                self.logger.error("Failed to get basic stats", guild_id=guild_id, error=str(e))
                raise HTTPException(status_code=500, detail=f"Failed to get basic stats: {str(e)}")

def create_analytics_router(database: DatabaseManager) -> APIRouter:
    """Create and return the analytics router."""
    analytics_routes = AnalyticsRoutes(database)
    return analytics_routes.router