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
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union

# Add src to Python path for imports
sys.path.append(str(Path(__file__).parent.parent / "src"))

from fastapi import FastAPI, HTTPException, Depends, Request, Response, status
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
    guild_id: Optional[str] = None
):
    """Get recent events."""
    try:
        logger.info("Events accessed", user_id=current_user.user_id, limit=limit, skip=skip)
        
        if not database:
            return {
                "success": False,
                "error": "Database not available",
                "data": [],
                "count": 0
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
        
        # Get recent events
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
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Events error", error=str(e), user_id=current_user.user_id)
        raise HTTPException(status_code=500, detail=f"Events error: {str(e)}")

@app.get("/api/csrf-token")
async def get_csrf_token(current_user: UserSession = Depends(require_authentication)):
    """Get CSRF token for authenticated requests."""
    csrf_token = security_manager.generate_csrf_token()
    return {
        "csrf_token": csrf_token,
        "timestamp": datetime.utcnow().isoformat()
    }


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