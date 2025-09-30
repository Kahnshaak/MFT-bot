#!/usr/bin/env python3
"""
Game Night Bot Web Dashboard

A minimal web interface for the Discord Game Night Bot.
This provides a basic dashboard for server administrators to manage events,
view statistics, and configure bot settings.
"""

import os
import sys
from pathlib import Path

# Add src to Python path for imports
sys.path.append(str(Path(__file__).parent.parent / "src"))

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from datetime import datetime
from typing import Optional, List, Dict, Any

# Simple settings for web app
class WebSettings:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "mongodb://localhost:27017/gamenight_bot")

# Initialize FastAPI app
app = FastAPI(
    title="Game Night Bot Dashboard",
    description="Web dashboard for Discord Game Night Bot management",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# Global variables
settings = WebSettings()
database = None


@app.on_event("startup")
async def startup_event():
    """Initialize database connection on startup."""
    global database
    try:
        # Simple MongoDB connection for web dashboard
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(settings.database_url)
        database = client.get_default_database()
        print("✅ Web dashboard connected to database")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        # Don't raise - allow web app to start even if DB is unavailable


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up database connection on shutdown."""
    global database
    if database:
        database.client.close()
        print("✅ Web dashboard disconnected from database")


@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Main dashboard page."""
    try:
        # Get basic statistics
        stats = await get_dashboard_stats()
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "title": "Game Night Bot Dashboard",
            "stats": stats,
            "current_time": datetime.utcnow().isoformat()
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dashboard error: {str(e)}")


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Check database connection
        if database:
            # Simple database ping
            try:
                await database.events.count_documents({})
                db_status = "connected"
            except Exception:
                db_status = "error"
        else:
            db_status = "disconnected"
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "database": db_status,
            "version": "1.0.0"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }


@app.get("/api/stats")
async def get_stats():
    """Get dashboard statistics."""
    try:
        stats = await get_dashboard_stats()
        return {
            "success": True,
            "data": stats,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stats error: {str(e)}")


@app.get("/api/events")
async def get_events(limit: int = 50, skip: int = 0):
    """Get recent events."""
    try:
        if not database:
            return {
                "success": False,
                "error": "Database not available",
                "data": [],
                "count": 0
            }
        
        # Get recent events
        events_cursor = database.events.find({}).sort("created_at", -1).limit(limit).skip(skip)
        events = []
        
        async for event_doc in events_cursor:
            # Convert ObjectId to string for JSON serialization
            event_doc["_id"] = str(event_doc["_id"])
            events.append(event_doc)
        
        return {
            "success": True,
            "data": events,
            "count": len(events),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Events error: {str(e)}")


@app.get("/events", response_class=HTMLResponse)
async def events_page(request: Request):
    """Events management page."""
    try:
        return templates.TemplateResponse("events.html", {
            "request": request,
            "title": "Events - Game Night Bot Dashboard"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Events page error: {str(e)}")


@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    """Users management page."""
    try:
        return templates.TemplateResponse("users.html", {
            "request": request,
            "title": "Users - Game Night Bot Dashboard"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Users page error: {str(e)}")


async def get_dashboard_stats() -> Dict[str, Any]:
    """Get dashboard statistics."""
    try:
        if not database:
            return {
                "total_events": 0,
                "active_events": 0,
                "total_users": 0,
                "total_guilds": 0,
                "database_status": "disconnected"
            }
        
        # Get event statistics
        total_events = await database.events.count_documents({})
        active_events = await database.events.count_documents({
            "state": {"$in": ["DRAFT", "DATE_POLLING", "TIME_POLLING", "GAME_POLLING", "SCHEDULED"]}
        })
        
        # Get user statistics
        total_users = await database.users.count_documents({})
        
        # Get guild count (unique guild_ids from events)
        guild_pipeline = [
            {"$group": {"_id": "$guild_id"}},
            {"$count": "total"}
        ]
        guild_result = await database.events.aggregate(guild_pipeline).to_list(1)
        total_guilds = guild_result[0]["total"] if guild_result else 0
        
        return {
            "total_events": total_events,
            "active_events": active_events,
            "total_users": total_users,
            "total_guilds": total_guilds,
            "database_status": "connected"
        }
    except Exception as e:
        print(f"Error getting dashboard stats: {e}")
        return {
            "total_events": 0,
            "active_events": 0,
            "total_users": 0,
            "total_guilds": 0,
            "database_status": "error",
            "error": str(e)
        }


if __name__ == "__main__":
    # Get configuration from environment
    host = os.getenv("WEB_HOST", "0.0.0.0")
    port = int(os.getenv("WEB_PORT", "8000"))
    debug = os.getenv("ENVIRONMENT", "development") == "development"
    
    print(f"🚀 Starting Game Night Bot Web Dashboard on {host}:{port}")
    print(f"📊 Dashboard will be available at http://{host}:{port}")
    
    # Run the web application
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info" if not debug else "debug"
    )