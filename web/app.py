#!/usr/bin/env python3
"""
Game Night Bot Web Dashboard

A comprehensive web interface for the Discord Game Night Bot with OAuth2 authentication,
JWT session management, and comprehensive security features.
"""

import os
import sys
import secrets
import logging
import json
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union

# Add src to Python path for imports
sys.path.append(str(Path(__file__).parent.parent / "src"))

from fastapi import FastAPI, HTTPException, Depends, Request, Response, status, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn
import aiohttp
import jwt
from jwt import PyJWTError
from pydantic import BaseModel, ValidationError
from motor.motor_asyncio import AsyncIOMotorClient
import structlog
from logging_config import (
    setup_web_logging, 
    RequestLoggingMiddleware,
    log_authentication_success,
    log_authentication_failure,
    log_authorization_failure,
    log_security_event,
    log_api_access
)

# Configure structured logging
logger = setup_web_logging()

# Security models
class TokenData(BaseModel):
    user_id: str
    guild_ids: List[str]
    username: str
    avatar: Optional[str] = None
    permissions: List[str] = []
    exp: datetime

class UserSession(BaseModel):
    user_id: str
    guild_ids: List[str]
    username: str
    avatar: Optional[str] = None
    permissions: List[str] = []
    is_authenticated: bool = True

class DiscordUser(BaseModel):
    id: str
    username: str
    discriminator: str
    avatar: Optional[str] = None
    email: Optional[str] = None

class DiscordGuild(BaseModel):
    id: str
    name: str
    icon: Optional[str] = None
    owner: bool
    permissions: int

# Enhanced settings for web app
class WebSettings:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "mongodb://localhost:27017/gamenight_bot")
        self.discord_client_id = os.getenv("DISCORD_CLIENT_ID")
        self.discord_client_secret = os.getenv("DISCORD_CLIENT_SECRET")
        self.jwt_secret = os.getenv("JWT_SECRET", secrets.token_urlsafe(32))
        self.jwt_algorithm = "HS256"
        self.jwt_expiration_hours = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))
        self.allowed_origins = os.getenv("ALLOWED_ORIGINS", "").split(",")
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.web_host = os.getenv("WEB_HOST", "0.0.0.0")
        self.web_port = int(os.getenv("WEB_PORT", "8000"))
        
        # Discord OAuth URLs
        self.discord_api_base = "https://discord.com/api/v10"
        self.discord_oauth_base = "https://discord.com/api/oauth2"
        self.redirect_uri = f"http://localhost:{self.web_port}/auth/callback"
        
        # Validate required settings
        if not self.discord_client_id or not self.discord_client_secret:
            logger.warning("Discord OAuth credentials not configured - authentication will be disabled")

# Security utilities
class SecurityManager:
    def __init__(self, settings: WebSettings):
        self.settings = settings
        self.security = HTTPBearer(auto_error=False)
    
    def generate_csrf_token(self) -> str:
        """Generate a CSRF token."""
        return secrets.token_urlsafe(32)
    
    def create_access_token(self, user_data: Dict[str, Any]) -> str:
        """Create a JWT access token."""
        expire = datetime.utcnow() + timedelta(hours=self.settings.jwt_expiration_hours)
        to_encode = {
            "user_id": user_data["id"],
            "guild_ids": [guild["id"] for guild in user_data.get("guilds", [])],
            "username": user_data["username"],
            "avatar": user_data.get("avatar"),
            "permissions": user_data.get("permissions", []),
            "exp": expire
        }
        
        encoded_jwt = jwt.encode(
            to_encode, 
            self.settings.jwt_secret, 
            algorithm=self.settings.jwt_algorithm
        )
        return encoded_jwt
    
    def verify_token(self, token: str) -> Optional[TokenData]:
        """Verify and decode a JWT token."""
        try:
            payload = jwt.decode(
                token, 
                self.settings.jwt_secret, 
                algorithms=[self.settings.jwt_algorithm]
            )
            
            # Check expiration
            exp_timestamp = payload.get("exp")
            if exp_timestamp and datetime.utcnow() > datetime.fromtimestamp(exp_timestamp):
                return None
            
            return TokenData(**payload)
        except (PyJWTError, ValidationError) as e:
            logger.warning("Token verification failed", error=str(e))
            return None
    
    async def get_current_user(self, credentials: Optional[HTTPAuthorizationCredentials] = None) -> Optional[UserSession]:
        """Get current authenticated user from token."""
        if not credentials:
            return None
        
        token_data = self.verify_token(credentials.credentials)
        if not token_data:
            return None
        
        return UserSession(
            user_id=token_data.user_id,
            guild_ids=token_data.guild_ids,
            username=token_data.username,
            avatar=token_data.avatar,
            permissions=token_data.permissions
        )

# Discord OAuth manager
class DiscordOAuthManager:
    def __init__(self, settings: WebSettings):
        self.settings = settings
        self.session = None
    
    async def get_session(self):
        """Get or create aiohttp session."""
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close_session(self):
        """Close aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None
    
    def get_oauth_url(self, state: str) -> str:
        """Generate Discord OAuth authorization URL."""
        params = {
            "client_id": self.settings.discord_client_id,
            "redirect_uri": self.settings.redirect_uri,
            "response_type": "code",
            "scope": "identify guilds",
            "state": state
        }
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.settings.discord_oauth_base}/authorize?{query_string}"
    
    async def exchange_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for access token."""
        session = await self.get_session()
        
        data = {
            "client_id": self.settings.discord_client_id,
            "client_secret": self.settings.discord_client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.settings.redirect_uri
        }
        
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        try:
            async with session.post(f"{self.settings.discord_oauth_base}/token", data=data, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error("Discord token exchange failed", status=resp.status, response=await resp.text())
                    return None
        except Exception as e:
            logger.error("Discord token exchange error", error=str(e))
            return None
    
    async def get_user_info(self, access_token: str) -> Optional[DiscordUser]:
        """Get user information from Discord API."""
        session = await self.get_session()
        headers = {"Authorization": f"Bearer {access_token}"}
        
        try:
            async with session.get(f"{self.settings.discord_api_base}/users/@me", headers=headers) as resp:
                if resp.status == 200:
                    user_data = await resp.json()
                    return DiscordUser(**user_data)
                else:
                    logger.error("Discord user info failed", status=resp.status)
                    return None
        except Exception as e:
            logger.error("Discord user info error", error=str(e))
            return None
    
    async def get_user_guilds(self, access_token: str) -> List[DiscordGuild]:
        """Get user's guilds from Discord API."""
        session = await self.get_session()
        headers = {"Authorization": f"Bearer {access_token}"}
        
        try:
            async with session.get(f"{self.settings.discord_api_base}/users/@me/guilds", headers=headers) as resp:
                if resp.status == 200:
                    guilds_data = await resp.json()
                    return [DiscordGuild(**guild) for guild in guilds_data]
                else:
                    logger.error("Discord guilds info failed", status=resp.status)
                    return []
        except Exception as e:
            logger.error("Discord guilds info error", error=str(e))
            return []

# Initialize settings and managers
settings = WebSettings()
security_manager = SecurityManager(settings)
oauth_manager = DiscordOAuthManager(settings)

# Initialize FastAPI app with enhanced security
app = FastAPI(
    title="Game Night Bot Dashboard",
    description="Secure web dashboard for Discord Game Night Bot management with OAuth2 authentication",
    version="1.0.0",
    docs_url="/docs" if settings.environment == "development" else None,
    redoc_url="/redoc" if settings.environment == "development" else None
)

# Security middleware
if settings.environment == "production":
    app.add_middleware(
        TrustedHostMiddleware, 
        allowed_hosts=["localhost", "127.0.0.1", "0.0.0.0"]
    )

# CORS middleware with proper configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins if settings.allowed_origins != [""] else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Add request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Custom security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    
    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    return response

# CSRF protection middleware
@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    # Skip CSRF for GET requests and API endpoints that don't modify data
    if request.method in ["GET", "HEAD", "OPTIONS"] or request.url.path.startswith("/api/health"):
        return await call_next(request)
    
    # Check for CSRF token in headers for API requests
    if request.url.path.startswith("/api/"):
        csrf_token = request.headers.get("X-CSRF-Token")
        if not csrf_token:
            return JSONResponse(
                status_code=403,
                content={"error": "CSRF token required", "code": "CSRF_TOKEN_MISSING"}
            )
    
    return await call_next(request)

# Mount static files and templates
static_dir = Path(__file__).parent / "static"
templates_dir = Path(__file__).parent / "templates"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))

# Global variables
database = None


@app.on_event("startup")
async def startup_event():
    """Initialize database connection and services on startup."""
    global database
    try:
        # MongoDB connection for web dashboard
        client = AsyncIOMotorClient(settings.database_url)
        database = client.get_default_database()
        
        # Test database connection
        await database.command("ping")
        logger.info("Web dashboard connected to database successfully")
        
        # Log startup information
        logger.info("Game Night Bot Web Dashboard starting", 
                   environment=settings.environment,
                   oauth_enabled=bool(settings.discord_client_id and settings.discord_client_secret))
        
    except Exception as e:
        logger.error("Failed to connect to database", error=str(e))
        # Don't raise - allow web app to start even if DB is unavailable


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up database connection and services on shutdown."""
    global database
    
    # Close OAuth session
    await oauth_manager.close_session()
    
    # Close database connection
    if database is not None:
        database.client.close()
        logger.info("Web dashboard disconnected from database")

# Dependency functions
async def get_current_user(request: Request) -> Optional[UserSession]:
    """Dependency to get current authenticated user from cookie or header."""
    # Try to get token from cookie first
    token = request.cookies.get("access_token")
    
    # If no cookie, try Authorization header
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
    
    if not token:
        return None
    
    # Verify token
    token_data = security_manager.verify_token(token)
    if not token_data:
        return None
    
    return UserSession(
        user_id=token_data.user_id,
        guild_ids=token_data.guild_ids,
        username=token_data.username,
        avatar=token_data.avatar,
        permissions=token_data.permissions
    )

async def require_authentication(current_user: UserSession = Depends(get_current_user)) -> UserSession:
    """Dependency that requires authentication."""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user

async def require_admin_permissions(current_user: UserSession = Depends(require_authentication)) -> UserSession:
    """Dependency that requires admin permissions."""
    if "admin" not in current_user.permissions and "manage_guild" not in current_user.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permissions required"
        )
    return current_user


# Authentication routes
@app.get("/auth/login")
async def login_page(request: Request):
    """Login page with Discord OAuth."""
    if not settings.discord_client_id or not settings.discord_client_secret:
        raise HTTPException(
            status_code=503, 
            detail="Discord OAuth not configured"
        )
    
    # Generate state for CSRF protection
    state = security_manager.generate_csrf_token()
    oauth_url = oauth_manager.get_oauth_url(state)
    
    # Store state in session (in production, use Redis or database)
    response = templates.TemplateResponse("login.html", {
        "request": request,
        "title": "Login - Game Night Bot Dashboard",
        "oauth_url": oauth_url
    })
    
    # Set state cookie for verification
    response.set_cookie(
        key="oauth_state", 
        value=state, 
        max_age=600,  # 10 minutes
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax"
    )
    
    return response

@app.get("/auth/callback")
async def oauth_callback(request: Request, code: str, state: str):
    """Handle Discord OAuth callback."""
    try:
        # Verify state parameter
        stored_state = request.cookies.get("oauth_state")
        if not stored_state or stored_state != state:
            raise HTTPException(status_code=400, detail="Invalid state parameter")
        
        # Exchange code for access token
        token_data = await oauth_manager.exchange_code(code)
        if not token_data:
            raise HTTPException(status_code=400, detail="Failed to exchange authorization code")
        
        access_token = token_data["access_token"]
        
        # Get user information
        user_info = await oauth_manager.get_user_info(access_token)
        if not user_info:
            raise HTTPException(status_code=400, detail="Failed to get user information")
        
        # Get user guilds
        user_guilds = await oauth_manager.get_user_guilds(access_token)
        
        # Check if user has access to any guilds with the bot
        # In production, verify against database of guilds where bot is installed
        guild_permissions = []
        for guild in user_guilds:
            # Check if user has admin permissions in guild
            if guild.permissions & 0x8:  # Administrator permission
                guild_permissions.append("admin")
            elif guild.permissions & 0x20:  # Manage Guild permission
                guild_permissions.append("manage_guild")
        
        # Create user data for JWT
        user_data = {
            "id": user_info.id,
            "username": user_info.username,
            "avatar": user_info.avatar,
            "guilds": [{"id": g.id, "name": g.name} for g in user_guilds],
            "permissions": list(set(guild_permissions))
        }
        
        # Create JWT token
        jwt_token = security_manager.create_access_token(user_data)
        
        # Create response and set JWT cookie
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key="access_token",
            value=jwt_token,
            max_age=settings.jwt_expiration_hours * 3600,
            httponly=True,
            secure=settings.environment == "production",
            samesite="lax"
        )
        
        # Clear state cookie
        response.delete_cookie("oauth_state")
        
        # Log successful authentication
        client_ip = request.client.host if request.client else "unknown"
        log_authentication_success(user_info.id, user_info.username, client_ip)
        logger.info("User authenticated successfully", user_id=user_info.id, username=user_info.username)
        return response
        
    except HTTPException as e:
        # Log authentication failure
        client_ip = request.client.host if request.client else "unknown"
        log_authentication_failure(str(e.detail), client_ip, {"status_code": e.status_code})
        raise
    except Exception as e:
        # Log authentication error
        client_ip = request.client.host if request.client else "unknown"
        log_authentication_failure("OAuth callback error", client_ip, {"error": str(e)})
        logger.error("OAuth callback error", error=str(e))
        raise HTTPException(status_code=500, detail="Authentication failed")

@app.post("/auth/logout")
async def logout():
    """Logout endpoint."""
    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie("access_token")
    return response

@app.get("/auth/me")
async def get_current_user_info(current_user: UserSession = Depends(get_current_user)):
    """Get current user information."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return {
        "user_id": current_user.user_id,
        "username": current_user.username,
        "avatar": current_user.avatar,
        "guild_ids": current_user.guild_ids,
        "permissions": current_user.permissions,
        "is_authenticated": current_user.is_authenticated
    }

# Main dashboard routes
@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request, current_user: Optional[UserSession] = Depends(get_current_user)):
    """Main dashboard page."""
    try:
        # Check authentication
        if not current_user:
            return RedirectResponse(url="/auth/login", status_code=302)
        
        # Get basic statistics
        stats = await get_dashboard_stats()
        
        # Generate CSRF token for forms
        csrf_token = security_manager.generate_csrf_token()
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "title": "Game Night Bot Dashboard",
            "stats": stats,
            "current_time": datetime.utcnow().isoformat(),
            "user": current_user,
            "csrf_token": csrf_token
        })
    except Exception as e:
        logger.error("Dashboard error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Dashboard error: {str(e)}")


@app.get("/api/health")
async def health_check():
    """Health check endpoint - no authentication required."""
    try:
        # Check database connection
        db_status = "disconnected"
        if database:
            try:
                await database.command("ping")
                db_status = "connected"
            except Exception as e:
                db_status = "error"
                logger.warning("Database health check failed", error=str(e))
        
        # Check OAuth configuration
        oauth_status = "configured" if (settings.discord_client_id and settings.discord_client_secret) else "not_configured"
        
        health_data = {
            "status": "healthy" if db_status == "connected" else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "database": db_status,
            "oauth": oauth_status,
            "version": "1.0.0",
            "environment": settings.environment
        }
        
        return health_data
        
    except Exception as e:
        logger.error("Health check error", error=str(e))
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }


@app.get("/api/monitoring/dashboard")
async def get_monitoring_dashboard(current_user: UserSession = Depends(require_authentication)):
    """Get comprehensive monitoring dashboard data."""
    try:
        logger.info("Monitoring dashboard accessed", user_id=current_user.user_id)
        
        # This would integrate with the bot's monitoring systems
        # For now, return basic structure with authentication
        return {
            "success": True,
            "data": {
                "overall_status": "healthy",
                "components": [
                    {"name": "Database", "status": "connected" if database else "disconnected"},
                    {"name": "Discord OAuth", "status": "configured" if settings.discord_client_id else "not_configured"},
                    {"name": "Web Dashboard", "status": "running"}
                ],
                "metrics_summary": {
                    "total_requests": 0,
                    "error_rate": 0.0,
                    "avg_response_time": 0
                },
                "performance_summary": {
                    "cpu_usage": 0,
                    "memory_usage": 0,
                    "disk_usage": 0
                },
                "active_alerts": [],
                "system_info": {
                    "environment": settings.environment,
                    "version": "1.0.0"
                },
                "last_updated": datetime.utcnow().isoformat()
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error("Monitoring dashboard error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Monitoring dashboard error: {str(e)}")


@app.get("/api/monitoring/metrics")
async def get_metrics(current_user: UserSession = Depends(require_authentication)):
    """Get system metrics."""
    try:
        logger.info("Metrics accessed", user_id=current_user.user_id)
        
        # This would integrate with the bot's metrics collector
        return {
            "success": True,
            "data": {
                "system_stats": {
                    "uptime_seconds": 0,
                    "total_commands": 0,
                    "total_errors": 0,
                    "active_sessions": 1  # Current user
                },
                "command_summary": {
                    "total_commands": 0,
                    "total_errors": 0,
                    "avg_success_rate": 1.0,
                    "unique_commands": 0
                },
                "top_commands": [],
                "authentication_stats": {
                    "total_logins": 0,
                    "failed_logins": 0,
                    "active_sessions": 1
                }
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error("Metrics error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Metrics error: {str(e)}")


@app.get("/api/monitoring/performance")
async def get_performance(current_user: UserSession = Depends(require_authentication)):
    """Get performance statistics."""
    try:
        logger.info("Performance data accessed", user_id=current_user.user_id)
        
        # This would integrate with the bot's performance monitor
        return {
            "success": True,
            "data": {
                "total_operations": 0,
                "avg_response_time_ms": 0,
                "operations_by_threshold": {
                    "fast": 0,    # < 100ms
                    "medium": 0,  # 100-500ms
                    "slow": 0,    # 500ms-2s
                    "very_slow": 0  # > 2s
                },
                "slowest_operations": [],
                "trending_operations": {},
                "web_performance": {
                    "avg_page_load": 0,
                    "api_response_time": 0
                }
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error("Performance error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Performance error: {str(e)}")


@app.get("/api/monitoring/alerts")
async def get_alerts(current_user: UserSession = Depends(require_authentication)):
    """Get active alerts."""
    try:
        logger.info("Alerts accessed", user_id=current_user.user_id)
        
        # This would integrate with the bot's alerting system
        alerts = []
        
        # Check for configuration issues
        if not settings.discord_client_id or not settings.discord_client_secret:
            alerts.append({
                "id": "oauth_not_configured",
                "level": "warning",
                "message": "Discord OAuth not configured",
                "timestamp": datetime.utcnow().isoformat(),
                "category": "configuration"
            })
        
        if not database:
            alerts.append({
                "id": "database_disconnected",
                "level": "critical",
                "message": "Database connection unavailable",
                "timestamp": datetime.utcnow().isoformat(),
                "category": "infrastructure"
            })
        
        return {
            "success": True,
            "data": alerts,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error("Alerts error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Alerts error: {str(e)}")


@app.get("/api/monitoring/logs")
async def get_logs(
    current_user: UserSession = Depends(require_authentication),
    hours: int = 1,
    level: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 100
):
    """Get and search logs."""
    try:
        logger.info("Logs accessed", user_id=current_user.user_id, hours=hours, level=level)
        
        # This would integrate with the bot's log aggregator
        # For now, return structure with some sample data
        return {
            "success": True,
            "data": {
                "entries": [
                    {
                        "timestamp": datetime.utcnow().isoformat(),
                        "level": "INFO",
                        "logger": "web.dashboard",
                        "message": f"Logs accessed by user {current_user.username}",
                        "user_id": current_user.user_id
                    }
                ],
                "total_count": 1,
                "analysis": {
                    "total_entries": 1,
                    "entries_by_level": {
                        "INFO": 1,
                        "WARNING": 0,
                        "ERROR": 0,
                        "CRITICAL": 0
                    },
                    "top_loggers": ["web.dashboard"],
                    "error_patterns": []
                }
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error("Logs error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Logs error: {str(e)}")


@app.get("/api/stats")
async def get_stats(current_user: UserSession = Depends(require_authentication)):
    """Get dashboard statistics."""
    try:
        logger.info("Stats accessed", user_id=current_user.user_id)
        
        stats = await get_dashboard_stats()
        return {
            "success": True,
            "data": stats,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error("Stats error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Stats error: {str(e)}")


@app.get("/api/events")
async def get_events(
    current_user: UserSession = Depends(require_authentication),
    limit: int = 50, 
    skip: int = 0,
    guild_id: Optional[str] = None,
    state: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Get events with filtering and search capabilities."""
    try:
        logger.info("Events accessed", user_id=current_user.user_id, limit=limit, skip=skip)
        
        if not database:
            return {
                "success": False,
                "error": "Database not available",
                "data": [],
                "count": 0,
                "total": 0
            }
        
        # Build query filter
        query_filter = {}
        
        # Filter by guild if specified and user has access
        if guild_id:
            if guild_id not in current_user.guild_ids:
                raise HTTPException(status_code=403, detail="Access denied to this guild")
            query_filter["guild_id"] = guild_id
        else:
            # Only show events from guilds user has access to
            query_filter["guild_id"] = {"$in": current_user.guild_ids}
        
        # Filter by state
        if state:
            query_filter["state"] = state
        
        # Search in title and description
        if search:
            query_filter["$or"] = [
                {"title": {"$regex": search, "$options": "i"}},
                {"description": {"$regex": search, "$options": "i"}}
            ]
        
        # Date range filter
        if start_date or end_date:
            date_filter = {}
            if start_date:
                date_filter["$gte"] = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if end_date:
                date_filter["$lte"] = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            query_filter["created_at"] = date_filter
        
        # Get total count for pagination
        total_count = await database.events.count_documents(query_filter)
        
        # Get events with pagination
        events_cursor = database.events.find(query_filter).sort("created_at", -1).limit(limit).skip(skip)
        events = []
        
        async for event_doc in events_cursor:
            # Convert ObjectId to string for JSON serialization
            event_doc["_id"] = str(event_doc["_id"])
            # Remove sensitive data
            if "creator_id" in event_doc:
                event_doc["creator_id"] = str(event_doc["creator_id"])
            events.append(event_doc)
        
        return {
            "success": True,
            "data": events,
            "count": len(events),
            "total": total_count,
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Events error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Events error: {str(e)}")

# Enhanced API endpoints for dashboard functionality

@app.get("/api/events/calendar")
async def get_events_calendar(
    current_user: UserSession = Depends(require_authentication),
    month: Optional[int] = None,
    year: Optional[int] = None,
    guild_id: Optional[str] = None
):
    """Get events formatted for calendar view."""
    try:
        if not database:
            return {"success": False, "error": "Database not available", "data": []}
        
        # Default to current month/year
        now = datetime.utcnow()
        target_month = month or now.month
        target_year = year or now.year
        
        # Calculate date range for the month
        start_date = datetime(target_year, target_month, 1)
        if target_month == 12:
            end_date = datetime(target_year + 1, 1, 1)
        else:
            end_date = datetime(target_year, target_month + 1, 1)
        
        # Build query
        query_filter = {
            "guild_id": {"$in": current_user.guild_ids},
            "$or": [
                {"schedule.selected_date": {"$gte": start_date, "$lt": end_date}},
                {"created_at": {"$gte": start_date, "$lt": end_date}}
            ]
        }
        
        if guild_id and guild_id in current_user.guild_ids:
            query_filter["guild_id"] = guild_id
        
        events = []
        async for event_doc in database.events.find(query_filter):
            # Format for calendar
            event_date = event_doc.get("schedule", {}).get("selected_date") or event_doc.get("created_at")
            events.append({
                "id": str(event_doc["_id"]),
                "title": event_doc["title"],
                "date": event_date.isoformat() if event_date else None,
                "state": event_doc["state"],
                "guild_id": event_doc["guild_id"]
            })
        
        return {
            "success": True,
            "data": events,
            "month": target_month,
            "year": target_year,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error("Calendar events error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Calendar events error: {str(e)}")

@app.get("/api/users")
async def get_users(
    current_user: UserSession = Depends(require_admin_permissions),
    limit: int = 50,
    skip: int = 0,
    search: Optional[str] = None,
    guild_id: Optional[str] = None,
    active_only: bool = False
):
    """Get users with filtering and search capabilities."""
    try:
        if not database:
            return {"success": False, "error": "Database not available", "data": [], "total": 0}
        
        # Build query filter
        query_filter = {}
        
        if guild_id and guild_id in current_user.guild_ids:
            query_filter["guild_id"] = guild_id
        else:
            query_filter["guild_id"] = {"$in": current_user.guild_ids}
        
        # Search filter
        if search:
            query_filter["$or"] = [
                {"profile.display_name": {"$regex": search, "$options": "i"}},
                {"user_id": {"$regex": search, "$options": "i"}}
            ]
        
        # Active users filter (users with recent activity)
        if active_only:
            week_ago = datetime.utcnow() - timedelta(days=7)
            query_filter["last_activity"] = {"$gte": week_ago}
        
        # Get total count
        total_count = await database.users.count_documents(query_filter)
        
        # Get users
        users = []
        async for user_doc in database.users.find(query_filter).limit(limit).skip(skip):
            user_doc["_id"] = str(user_doc["_id"])
            # Remove sensitive data
            if "email" in user_doc:
                del user_doc["email"]
            users.append(user_doc)
        
        return {
            "success": True,
            "data": users,
            "count": len(users),
            "total": total_count,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error("Users API error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Users API error: {str(e)}")

@app.get("/api/analytics/attendance")
async def get_attendance_analytics(
    current_user: UserSession = Depends(require_authentication),
    days: int = 30,
    guild_id: Optional[str] = None
):
    """Get attendance analytics data."""
    try:
        if not database:
            return {"success": False, "error": "Database not available", "data": {}}
        
        # Date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Build query
        query_filter = {
            "guild_id": {"$in": current_user.guild_ids},
            "state": "COMPLETED",
            "schedule.selected_date": {"$gte": start_date, "$lte": end_date}
        }
        
        if guild_id and guild_id in current_user.guild_ids:
            query_filter["guild_id"] = guild_id
        
        # Aggregate attendance data
        pipeline = [
            {"$match": query_filter},
            {"$group": {
                "_id": {
                    "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$schedule.selected_date"}}
                },
                "total_events": {"$sum": 1},
                "total_attendees": {"$sum": {"$size": {"$ifNull": ["$attendance.confirmed", []]}}},
                "avg_attendance": {"$avg": {"$size": {"$ifNull": ["$attendance.confirmed", []]}}}
            }},
            {"$sort": {"_id.date": 1}}
        ]
        
        attendance_data = []
        async for doc in database.events.aggregate(pipeline):
            attendance_data.append({
                "date": doc["_id"]["date"],
                "events": doc["total_events"],
                "attendees": doc["total_attendees"],
                "avg_attendance": round(doc["avg_attendance"], 2)
            })
        
        return {
            "success": True,
            "data": {
                "daily_attendance": attendance_data,
                "period_days": days,
                "total_events": len(attendance_data)
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error("Attendance analytics error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Attendance analytics error: {str(e)}")

@app.get("/api/analytics/games")
async def get_games_analytics(
    current_user: UserSession = Depends(require_authentication),
    days: int = 30,
    guild_id: Optional[str] = None
):
    """Get game popularity analytics."""
    try:
        if not database:
            return {"success": False, "error": "Database not available", "data": {}}
        
        # Date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Build query for completed events
        query_filter = {
            "guild_id": {"$in": current_user.guild_ids},
            "state": "COMPLETED",
            "schedule.selected_date": {"$gte": start_date, "$lte": end_date}
        }
        
        if guild_id and guild_id in current_user.guild_ids:
            query_filter["guild_id"] = guild_id
        
        # Aggregate game popularity
        pipeline = [
            {"$match": query_filter},
            {"$unwind": {"path": "$polls.game_poll.selected_games", "preserveNullAndEmptyArrays": True}},
            {"$group": {
                "_id": "$polls.game_poll.selected_games",
                "play_count": {"$sum": 1},
                "total_attendees": {"$sum": {"$size": {"$ifNull": ["$attendance.confirmed", []]}}}
            }},
            {"$match": {"_id": {"$ne": None}}},
            {"$sort": {"play_count": -1}},
            {"$limit": 20}
        ]
        
        games_data = []
        async for doc in database.events.aggregate(pipeline):
            games_data.append({
                "game": doc["_id"],
                "play_count": doc["play_count"],
                "total_attendees": doc["total_attendees"]
            })
        
        # Get game interests data
        interests_pipeline = [
            {"$match": {"guild_id": {"$in": current_user.guild_ids}}},
            {"$unwind": {"path": "$game_interests", "preserveNullAndEmptyArrays": True}},
            {"$group": {
                "_id": "$game_interests",
                "interest_count": {"$sum": 1}
            }},
            {"$match": {"_id": {"$ne": None}}},
            {"$sort": {"interest_count": -1}},
            {"$limit": 20}
        ]
        
        interests_data = []
        async for doc in database.users.aggregate(interests_pipeline):
            interests_data.append({
                "game": doc["_id"],
                "interest_count": doc["interest_count"]
            })
        
        return {
            "success": True,
            "data": {
                "popular_games": games_data,
                "game_interests": interests_data,
                "period_days": days
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error("Games analytics error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Games analytics error: {str(e)}")

@app.get("/api/config")
async def get_config(current_user: UserSession = Depends(require_admin_permissions)):
    """Get bot configuration for the user's guilds."""
    try:
        if not database:
            return {"success": False, "error": "Database not available", "data": {}}
        
        # Get guild configurations
        configs = []
        async for config_doc in database.guild_configs.find({"guild_id": {"$in": current_user.guild_ids}}):
            config_doc["_id"] = str(config_doc["_id"])
            configs.append(config_doc)
        
        return {
            "success": True,
            "data": configs,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error("Config API error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Config API error: {str(e)}")

@app.put("/api/config/{guild_id}")
async def update_config(
    guild_id: str,
    config_data: dict,
    current_user: UserSession = Depends(require_admin_permissions)
):
    """Update guild configuration."""
    try:
        if guild_id not in current_user.guild_ids:
            raise HTTPException(status_code=403, detail="Access denied to this guild")
        
        if not database:
            raise HTTPException(status_code=503, detail="Database not available")
        
        # Validate configuration data
        allowed_fields = [
            "default_timezone", "notification_channels", "admin_roles", 
            "organizer_roles", "default_reminder_times", "max_events_per_user"
        ]
        
        validated_config = {k: v for k, v in config_data.items() if k in allowed_fields}
        validated_config["updated_at"] = datetime.utcnow()
        validated_config["updated_by"] = current_user.user_id
        
        # Update or create configuration
        result = await database.guild_configs.update_one(
            {"guild_id": guild_id},
            {"$set": validated_config},
            upsert=True
        )
        
        return {
            "success": True,
            "message": "Configuration updated successfully",
            "modified_count": result.modified_count,
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Config update error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Config update error: {str(e)}")

@app.get("/api/export/events")
async def export_events(
    current_user: UserSession = Depends(require_authentication),
    format: str = "json",
    guild_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Export events data."""
    try:
        if not database:
            raise HTTPException(status_code=503, detail="Database not available")
        
        # Build query
        query_filter = {"guild_id": {"$in": current_user.guild_ids}}
        
        if guild_id and guild_id in current_user.guild_ids:
            query_filter["guild_id"] = guild_id
        
        if start_date or end_date:
            date_filter = {}
            if start_date:
                date_filter["$gte"] = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if end_date:
                date_filter["$lte"] = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            query_filter["created_at"] = date_filter
        
        # Get events
        events = []
        async for event_doc in database.events.find(query_filter).sort("created_at", -1):
            event_doc["_id"] = str(event_doc["_id"])
            events.append(event_doc)
        
        if format.lower() == "csv":
            # Convert to CSV format
            import csv
            import io
            
            output = io.StringIO()
            if events:
                fieldnames = ["title", "state", "created_at", "guild_id", "creator_id"]
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                
                for event in events:
                    row = {field: event.get(field, "") for field in fieldnames}
                    writer.writerow(row)
            
            return Response(
                content=output.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=events_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"}
            )
        else:
            # JSON format
            return {
                "success": True,
                "data": events,
                "count": len(events),
                "exported_at": datetime.utcnow().isoformat()
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Export events error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Export events error: {str(e)}")

@app.get("/api/csrf-token")
async def get_csrf_token(current_user: UserSession = Depends(require_authentication)):
    """Get CSRF token for authenticated requests."""
    csrf_token = security_manager.generate_csrf_token()
    return {
        "csrf_token": csrf_token,
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================================
# COMPREHENSIVE REST API ENDPOINTS
# ============================================================================

# API Models for request/response validation
class EventCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    guild_id: str
    duration_minutes: Optional[int] = None
    default_games: Optional[List[str]] = []

class EventUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    state: Optional[str] = None

class UserPreferencesRequest(BaseModel):
    timezone: Optional[str] = None
    notification_preferences: Optional[Dict[str, Any]] = None
    availability: Optional[Dict[str, Any]] = None

class GameInterestRequest(BaseModel):
    game_name: str
    action: str  # "add" or "remove"

class ConfigUpdateRequest(BaseModel):
    settings: Dict[str, Any]

class SearchRequest(BaseModel):
    query: str
    filters: Optional[Dict[str, Any]] = {}
    sort_by: Optional[str] = "created_at"
    sort_order: Optional[str] = "desc"
    limit: Optional[int] = 50
    offset: Optional[int] = 0

# ============================================================================
# EVENTS API - Full CRUD Operations
# ============================================================================

@app.post("/api/events")
async def create_event(
    event_data: EventCreateRequest,
    current_user: UserSession = Depends(require_authentication)
):
    """Create a new event."""
    try:
        if not database:
            raise HTTPException(status_code=503, detail="Database unavailable")
        
        # Verify user has permission for this guild
        if event_data.guild_id not in current_user.guild_ids:
            raise HTTPException(status_code=403, detail="No permission for this guild")
        
        # Create event document
        event_doc = {
            "guild_id": event_data.guild_id,
            "title": event_data.title,
            "description": event_data.description or "",
            "creator_id": current_user.user_id,
            "state": "DRAFT",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "schedule": {
                "selected_date": None,
                "selected_time": None,
                "timezone": "UTC",
                "duration_minutes": event_data.duration_minutes
            },
            "polls": {
                "date_poll": None,
                "time_poll": None,
                "game_poll": None
            },
            "rsvp_data": {},
            "attendance": {},
            "default_games": event_data.default_games or []
        }
        
        result = await database.events.insert_one(event_doc)
        event_doc["_id"] = str(result.inserted_id)
        
        log_api_access(current_user.user_id, "POST", "/api/events", "success")
        logger.info("Event created", event_id=str(result.inserted_id), user_id=current_user.user_id)
        
        return {
            "success": True,
            "data": event_doc,
            "message": "Event created successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log_api_access(current_user.user_id, "POST", "/api/events", "error", {"error": str(e)})
        logger.error("Event creation error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Event creation error: {str(e)}")

@app.get("/api/events/{event_id}")
async def get_event(
    event_id: str,
    current_user: UserSession = Depends(require_authentication)
):
    """Get a specific event by ID."""
    try:
        if not database:
            raise HTTPException(status_code=503, detail="Database unavailable")
        
        from bson import ObjectId
        try:
            object_id = ObjectId(event_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid event ID format")
        
        event = await database.events.find_one({"_id": object_id})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        # Check permission
        if event["guild_id"] not in current_user.guild_ids:
            raise HTTPException(status_code=403, detail="No permission to view this event")
        
        # Convert ObjectId to string
        event["_id"] = str(event["_id"])
        
        return {
            "success": True,
            "data": event,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get event error", error=str(e), event_id=event_id, user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Get event error: {str(e)}")

@app.put("/api/events/{event_id}")
async def update_event(
    event_id: str,
    event_data: EventUpdateRequest,
    current_user: UserSession = Depends(require_authentication)
):
    """Update an existing event."""
    try:
        if not database:
            raise HTTPException(status_code=503, detail="Database unavailable")
        
        from bson import ObjectId
        try:
            object_id = ObjectId(event_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid event ID format")
        
        # Get existing event
        event = await database.events.find_one({"_id": object_id})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        # Check permission (creator or admin)
        if (event["creator_id"] != current_user.user_id and 
            event["guild_id"] not in current_user.guild_ids):
            raise HTTPException(status_code=403, detail="No permission to update this event")
        
        # Build update document
        update_doc = {"updated_at": datetime.utcnow()}
        if event_data.title is not None:
            update_doc["title"] = event_data.title
        if event_data.description is not None:
            update_doc["description"] = event_data.description
        if event_data.duration_minutes is not None:
            update_doc["schedule.duration_minutes"] = event_data.duration_minutes
        if event_data.state is not None:
            update_doc["state"] = event_data.state
        
        result = await database.events.update_one(
            {"_id": object_id},
            {"$set": update_doc}
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=400, detail="No changes made")
        
        # Get updated event
        updated_event = await database.events.find_one({"_id": object_id})
        updated_event["_id"] = str(updated_event["_id"])
        
        log_api_access(current_user.user_id, "PUT", f"/api/events/{event_id}", "success")
        logger.info("Event updated", event_id=event_id, user_id=current_user.user_id)
        
        return {
            "success": True,
            "data": updated_event,
            "message": "Event updated successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log_api_access(current_user.user_id, "PUT", f"/api/events/{event_id}", "error", {"error": str(e)})
        logger.error("Event update error", error=str(e), event_id=event_id, user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Event update error: {str(e)}")

@app.delete("/api/events/{event_id}")
async def delete_event(
    event_id: str,
    current_user: UserSession = Depends(require_authentication)
):
    """Delete/cancel an event."""
    try:
        if not database:
            raise HTTPException(status_code=503, detail="Database unavailable")
        
        from bson import ObjectId
        try:
            object_id = ObjectId(event_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid event ID format")
        
        # Get existing event
        event = await database.events.find_one({"_id": object_id})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        # Check permission (creator or admin)
        if (event["creator_id"] != current_user.user_id and 
            "admin" not in current_user.permissions):
            raise HTTPException(status_code=403, detail="No permission to delete this event")
        
        # Soft delete by setting state to CANCELLED
        result = await database.events.update_one(
            {"_id": object_id},
            {"$set": {"state": "CANCELLED", "updated_at": datetime.utcnow()}}
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=400, detail="Event could not be cancelled")
        
        log_api_access(current_user.user_id, "DELETE", f"/api/events/{event_id}", "success")
        logger.info("Event cancelled", event_id=event_id, user_id=current_user.user_id)
        
        return {
            "success": True,
            "message": "Event cancelled successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log_api_access(current_user.user_id, "DELETE", f"/api/events/{event_id}", "error", {"error": str(e)})
        logger.error("Event deletion error", error=str(e), event_id=event_id, user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Event deletion error: {str(e)}")

# ============================================================================
# USERS API - Profile and Preferences Management
# ============================================================================

@app.get("/api/users/{user_id}")
async def get_user_profile(
    user_id: str,
    current_user: UserSession = Depends(require_authentication)
):
    """Get user profile information."""
    try:
        if not database:
            raise HTTPException(status_code=503, detail="Database unavailable")
        
        # Users can view their own profile, admins can view any profile
        if (user_id != current_user.user_id and 
            "admin" not in current_user.permissions):
            raise HTTPException(status_code=403, detail="No permission to view this profile")
        
        user = await database.users.find_one({"user_id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Remove sensitive information
        user.pop("_id", None)
        
        return {
            "success": True,
            "data": user,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get user profile error", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail=f"Get user profile error: {str(e)}")

@app.put("/api/users/{user_id}/preferences")
async def update_user_preferences(
    user_id: str,
    preferences: UserPreferencesRequest,
    current_user: UserSession = Depends(require_authentication)
):
    """Update user preferences."""
    try:
        if not database:
            raise HTTPException(status_code=503, detail="Database unavailable")
        
        # Users can only update their own preferences
        if user_id != current_user.user_id:
            raise HTTPException(status_code=403, detail="Can only update your own preferences")
        
        # Build update document
        update_doc = {"updated_at": datetime.utcnow()}
        if preferences.timezone is not None:
            update_doc["profile.timezone"] = preferences.timezone
        if preferences.notification_preferences is not None:
            update_doc["profile.notification_preferences"] = preferences.notification_preferences
        if preferences.availability is not None:
            update_doc["profile.availability"] = preferences.availability
        
        result = await database.users.update_one(
            {"user_id": user_id},
            {"$set": update_doc},
            upsert=True
        )
        
        # Get updated user
        updated_user = await database.users.find_one({"user_id": user_id})
        if updated_user:
            updated_user.pop("_id", None)
        
        log_api_access(current_user.user_id, "PUT", f"/api/users/{user_id}/preferences", "success")
        logger.info("User preferences updated", user_id=user_id)
        
        return {
            "success": True,
            "data": updated_user,
            "message": "Preferences updated successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log_api_access(current_user.user_id, "PUT", f"/api/users/{user_id}/preferences", "error", {"error": str(e)})
        logger.error("Update user preferences error", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail=f"Update preferences error: {str(e)}")

@app.post("/api/users/{user_id}/games")
async def manage_game_interests(
    user_id: str,
    game_request: GameInterestRequest,
    current_user: UserSession = Depends(require_authentication)
):
    """Add or remove game interests for a user."""
    try:
        if not database:
            raise HTTPException(status_code=503, detail="Database unavailable")
        
        # Users can only manage their own game interests
        if user_id != current_user.user_id:
            raise HTTPException(status_code=403, detail="Can only manage your own game interests")
        
        if game_request.action == "add":
            result = await database.users.update_one(
                {"user_id": user_id},
                {
                    "$addToSet": {"game_interests": game_request.game_name},
                    "$set": {"updated_at": datetime.utcnow()}
                },
                upsert=True
            )
            message = f"Added interest in {game_request.game_name}"
        elif game_request.action == "remove":
            result = await database.users.update_one(
                {"user_id": user_id},
                {
                    "$pull": {"game_interests": game_request.game_name},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            message = f"Removed interest in {game_request.game_name}"
        else:
            raise HTTPException(status_code=400, detail="Action must be 'add' or 'remove'")
        
        # Get updated user
        updated_user = await database.users.find_one({"user_id": user_id})
        if updated_user:
            updated_user.pop("_id", None)
        
        log_api_access(current_user.user_id, "POST", f"/api/users/{user_id}/games", "success")
        logger.info("Game interests updated", user_id=user_id, action=game_request.action, game=game_request.game_name)
        
        return {
            "success": True,
            "data": updated_user,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log_api_access(current_user.user_id, "POST", f"/api/users/{user_id}/games", "error", {"error": str(e)})
        logger.error("Manage game interests error", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail=f"Manage game interests error: {str(e)}")

# ============================================================================
# GAMES API - Game Management and Analytics
# ============================================================================

@app.get("/api/games")
async def get_games(
    current_user: UserSession = Depends(require_authentication),
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """Get list of games with optional search."""
    try:
        if not database:
            raise HTTPException(status_code=503, detail="Database unavailable")
        
        # Build aggregation pipeline
        pipeline = []
        
        # Get all unique games from user interests and event data
        pipeline.extend([
            {"$group": {"_id": "$game_interests"}},
            {"$unwind": "$_id"},
            {"$group": {"_id": "$_id", "interest_count": {"$sum": 1}}}
        ])
        
        # Add search filter if provided
        if search:
            pipeline.insert(0, {
                "$match": {"game_interests": {"$regex": search, "$options": "i"}}
            })
        
        # Add sorting and pagination
        pipeline.extend([
            {"$sort": {"interest_count": -1, "_id": 1}},
            {"$skip": offset},
            {"$limit": limit}
        ])
        
        games_cursor = database.users.aggregate(pipeline)
        games = await games_cursor.to_list(length=limit)
        
        # Format results
        formatted_games = []
        for game in games:
            formatted_games.append({
                "name": game["_id"],
                "interest_count": game["interest_count"],
                "popularity_score": game["interest_count"]  # Could be more complex
            })
        
        return {
            "success": True,
            "data": {
                "games": formatted_games,
                "total_count": len(formatted_games),
                "has_more": len(formatted_games) == limit
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error("Get games error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Get games error: {str(e)}")

@app.get("/api/games/popular")
async def get_popular_games(
    current_user: UserSession = Depends(require_authentication),
    limit: int = 10
):
    """Get most popular games by interest count."""
    try:
        if not database:
            raise HTTPException(status_code=503, detail="Database unavailable")
        
        pipeline = [
            {"$unwind": "$game_interests"},
            {"$group": {
                "_id": "$game_interests",
                "interest_count": {"$sum": 1},
                "users": {"$addToSet": "$user_id"}
            }},
            {"$sort": {"interest_count": -1}},
            {"$limit": limit},
            {"$project": {
                "name": "$_id",
                "interest_count": 1,
                "unique_users": {"$size": "$users"},
                "_id": 0
            }}
        ]
        
        popular_games_cursor = database.users.aggregate(pipeline)
        popular_games = await popular_games_cursor.to_list(length=limit)
        
        return {
            "success": True,
            "data": popular_games,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error("Get popular games error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Get popular games error: {str(e)}")

# ============================================================================
# SEARCH API - Advanced Search and Filtering
# ============================================================================

@app.post("/api/search")
async def advanced_search(
    search_request: SearchRequest,
    current_user: UserSession = Depends(require_authentication)
):
    """Advanced search across all data types."""
    try:
        if not database:
            raise HTTPException(status_code=503, detail="Database unavailable")
        
        results = {
            "events": [],
            "users": [],
            "games": []
        }
        
        # Search events
        event_filter = {"guild_id": {"$in": current_user.guild_ids}}
        if search_request.query:
            event_filter["$or"] = [
                {"title": {"$regex": search_request.query, "$options": "i"}},
                {"description": {"$regex": search_request.query, "$options": "i"}}
            ]
        
        # Apply additional filters
        if search_request.filters:
            if "state" in search_request.filters:
                event_filter["state"] = search_request.filters["state"]
            if "creator_id" in search_request.filters:
                event_filter["creator_id"] = search_request.filters["creator_id"]
            if "date_range" in search_request.filters:
                date_range = search_request.filters["date_range"]
                if "start" in date_range:
                    event_filter["created_at"] = {"$gte": datetime.fromisoformat(date_range["start"])}
                if "end" in date_range:
                    event_filter.setdefault("created_at", {})["$lte"] = datetime.fromisoformat(date_range["end"])
        
        # Sort configuration
        sort_field = search_request.sort_by or "created_at"
        sort_direction = -1 if search_request.sort_order == "desc" else 1
        
        events_cursor = database.events.find(event_filter).sort(sort_field, sort_direction).limit(search_request.limit).skip(search_request.offset)
        events = await events_cursor.to_list(length=search_request.limit)
        
        for event in events:
            event["_id"] = str(event["_id"])
            results["events"].append(event)
        
        # Search users (admin only)
        if "admin" in current_user.permissions:
            user_filter = {}
            if search_request.query:
                user_filter["$or"] = [
                    {"profile.username": {"$regex": search_request.query, "$options": "i"}},
                    {"game_interests": {"$regex": search_request.query, "$options": "i"}}
                ]
            
            users_cursor = database.users.find(user_filter).limit(search_request.limit).skip(search_request.offset)
            users = await users_cursor.to_list(length=search_request.limit)
            
            for user in users:
                user.pop("_id", None)
                results["users"].append(user)
        
        # Search games
        if search_request.query:
            game_pipeline = [
                {"$unwind": "$game_interests"},
                {"$match": {"game_interests": {"$regex": search_request.query, "$options": "i"}}},
                {"$group": {
                    "_id": "$game_interests",
                    "interest_count": {"$sum": 1}
                }},
                {"$sort": {"interest_count": -1}},
                {"$limit": search_request.limit}
            ]
            
            games_cursor = database.users.aggregate(game_pipeline)
            games = await games_cursor.to_list(length=search_request.limit)
            
            for game in games:
                results["games"].append({
                    "name": game["_id"],
                    "interest_count": game["interest_count"]
                })
        
        log_api_access(current_user.user_id, "POST", "/api/search", "success")
        
        return {
            "success": True,
            "data": results,
            "query": search_request.query,
            "filters": search_request.filters,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log_api_access(current_user.user_id, "POST", "/api/search", "error", {"error": str(e)})
        logger.error("Advanced search error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Advanced search error: {str(e)}")

# ============================================================================
# CONFIGURATION IMPORT/EXPORT API
# ============================================================================

@app.post("/api/config/import")
async def import_configuration(
    request: Request,
    current_user: UserSession = Depends(require_admin_permissions)
):
    """Import configuration from uploaded file."""
    try:
        if not database:
            raise HTTPException(status_code=503, detail="Database unavailable")
        
        # Get uploaded file
        form = await request.form()
        config_file = form.get("config_file")
        
        if not config_file:
            raise HTTPException(status_code=400, detail="No configuration file provided")
        
        # Read and parse configuration
        config_content = await config_file.read()
        try:
            config_data = json.loads(config_content.decode('utf-8'))
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON format")
        
        # Validate configuration structure
        required_fields = ["version", "guild_configs", "timestamp"]
        if not all(field in config_data for field in required_fields):
            raise HTTPException(status_code=400, detail="Invalid configuration format")
        
        # Import guild configurations
        imported_count = 0
        for guild_id, guild_config in config_data["guild_configs"].items():
            # Verify user has permission for this guild
            if guild_id not in current_user.guild_ids:
                continue
            
            await database.guild_configs.update_one(
                {"guild_id": guild_id},
                {"$set": {
                    **guild_config,
                    "updated_at": datetime.utcnow(),
                    "imported_by": current_user.user_id
                }},
                upsert=True
            )
            imported_count += 1
        
        log_api_access(current_user.user_id, "POST", "/api/config/import", "success")
        logger.info("Configuration imported", user_id=current_user.user_id, imported_count=imported_count)
        
        return {
            "success": True,
            "message": f"Successfully imported configuration for {imported_count} guilds",
            "imported_count": imported_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log_api_access(current_user.user_id, "POST", "/api/config/import", "error", {"error": str(e)})
        logger.error("Configuration import error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Configuration import error: {str(e)}")

@app.get("/api/config/export")
async def export_configuration(
    current_user: UserSession = Depends(require_admin_permissions),
    guild_ids: Optional[str] = None
):
    """Export configuration for specified guilds."""
    try:
        if not database:
            raise HTTPException(status_code=503, detail="Database unavailable")
        
        # Parse guild IDs
        target_guilds = []
        if guild_ids:
            target_guilds = guild_ids.split(",")
            # Verify permissions
            for guild_id in target_guilds:
                if guild_id not in current_user.guild_ids:
                    raise HTTPException(status_code=403, detail=f"No permission for guild {guild_id}")
        else:
            target_guilds = current_user.guild_ids
        
        # Get guild configurations
        guild_configs = {}
        for guild_id in target_guilds:
            config = await database.guild_configs.find_one({"guild_id": guild_id})
            if config:
                config.pop("_id", None)
                guild_configs[guild_id] = config
        
        # Build export data
        export_data = {
            "version": "1.0.0",
            "exported_at": datetime.utcnow().isoformat(),
            "exported_by": current_user.user_id,
            "guild_configs": guild_configs
        }
        
        log_api_access(current_user.user_id, "GET", "/api/config/export", "success")
        logger.info("Configuration exported", user_id=current_user.user_id, guild_count=len(guild_configs))
        
        return {
            "success": True,
            "data": export_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log_api_access(current_user.user_id, "GET", "/api/config/export", "error", {"error": str(e)})
        logger.error("Configuration export error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Configuration export error: {str(e)}")

# ============================================================================
# API DOCUMENTATION ENDPOINT
# ============================================================================

@app.get("/api/docs/openapi.json")
async def get_openapi_spec():
    """Get OpenAPI specification for the API."""
    return app.openapi()

@app.get("/api/docs")
async def api_documentation():
    """Interactive API documentation."""
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Game Night Bot API Documentation</title>
        <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@3.52.5/swagger-ui.css" />
    </head>
    <body>
        <div id="swagger-ui"></div>
        <script src="https://unpkg.com/swagger-ui-dist@3.52.5/swagger-ui-bundle.js"></script>
        <script>
            SwaggerUIBundle({
                url: '/api/docs/openapi.json',
                dom_id: '#swagger-ui',
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIBundle.presets.standalone
                ]
            });
        </script>
    </body>
    </html>
    """)


@app.get("/events", response_class=HTMLResponse)
async def events_page(request: Request, current_user: UserSession = Depends(require_authentication)):
    """Events management page."""
    try:
        csrf_token = security_manager.generate_csrf_token()
        
        return templates.TemplateResponse("events.html", {
            "request": request,
            "title": "Events - Game Night Bot Dashboard",
            "user": current_user,
            "csrf_token": csrf_token
        })
    except Exception as e:
        logger.error("Events page error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Events page error: {str(e)}")


@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, current_user: UserSession = Depends(require_admin_permissions)):
    """Users management page - admin only."""
    try:
        csrf_token = security_manager.generate_csrf_token()
        
        return templates.TemplateResponse("users.html", {
            "request": request,
            "title": "Users - Game Night Bot Dashboard",
            "user": current_user,
            "csrf_token": csrf_token
        })
    except Exception as e:
        logger.error("Users page error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Users page error: {str(e)}")


@app.get("/monitoring", response_class=HTMLResponse)
async def monitoring_page(request: Request, current_user: UserSession = Depends(require_admin_permissions)):
    """System monitoring page - admin only."""
    try:
        csrf_token = security_manager.generate_csrf_token()
        
        return templates.TemplateResponse("monitoring.html", {
            "request": request,
            "title": "Monitoring - Game Night Bot Dashboard",
            "user": current_user,
            "csrf_token": csrf_token
        })
    except Exception as e:
        logger.error("Monitoring page error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Monitoring page error: {str(e)}")

@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request, current_user: UserSession = Depends(require_authentication)):
    """Analytics dashboard page."""
    try:
        csrf_token = security_manager.generate_csrf_token()
        
        return templates.TemplateResponse("analytics.html", {
            "request": request,
            "title": "Analytics - Game Night Bot Dashboard",
            "user": current_user,
            "csrf_token": csrf_token
        })
    except Exception as e:
        logger.error("Analytics page error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Analytics page error: {str(e)}")

@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request, current_user: UserSession = Depends(require_admin_permissions)):
    """Configuration management page - admin only."""
    try:
        csrf_token = security_manager.generate_csrf_token()
        
        return templates.TemplateResponse("config.html", {
            "request": request,
            "title": "Configuration - Game Night Bot Dashboard",
            "user": current_user,
            "csrf_token": csrf_token
        })
    except Exception as e:
        logger.error("Config page error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Config page error: {str(e)}")


# WebSocket connection manager for real-time updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
    
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # Remove disconnected connections
                self.active_connections.remove(connection)

manager = ConnectionManager()

@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time status updates."""
    await manager.connect(websocket)
    try:
        while True:
            # Send status updates every 10 seconds
            await asyncio.sleep(10)
            
            # Get current stats
            stats = await get_dashboard_stats()
            health_data = {
                "type": "status_update",
                "data": {
                    "stats": stats,
                    "timestamp": datetime.utcnow().isoformat(),
                    "database_status": "connected" if database else "disconnected"
                }
            }
            
            await manager.send_personal_message(json.dumps(health_data), websocket)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)

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