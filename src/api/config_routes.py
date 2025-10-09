"""
Configuration API routes for the Game Night Bot web dashboard.

Provides basic REST endpoints for guild configuration management.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models.guild import GuildConfig
from models.repositories import GuildConfigRepository
from database.manager import DatabaseManager
from utils.logging_config import LoggerMixin


class GuildConfigUpdateRequest(BaseModel):
    """Request model for updating guild configurations."""
    guild_name: Optional[str] = Field(None, max_length=100)
    default_timezone: Optional[str] = None
    default_event_duration: Optional[int] = Field(None, ge=15, le=1440)
    max_events_per_user: Optional[int] = Field(None, ge=1, le=50)


class BasicGuildConfigResponse(BaseModel):
    """Basic response model for guild configurations."""
    id: str
    guild_id: str
    guild_name: Optional[str]
    default_timezone: str
    default_event_duration: int
    max_events_per_user: int
    created_at: datetime
    updated_at: datetime


class ConfigRoutes(LoggerMixin):
    """Configuration API routes handler."""
    
    def __init__(self, database: DatabaseManager):
        self.database = database
        self.config_repo = GuildConfigRepository(database, GuildConfig)
        self.router = APIRouter(prefix="/api/config", tags=["configuration"])
        self._setup_routes()
    
    def _setup_routes(self):
        """Set up basic configuration routes."""
        
        @self.router.get("/{guild_id}", response_model=BasicGuildConfigResponse)
        async def get_guild_config(guild_id: str):
            """Get guild configuration."""
            try:
                config = await self.config_repo.get_by_guild_id(guild_id)
                if not config:
                    # Create default configuration
                    config_id = await self.config_repo.create_default_config(guild_id)
                    config = await self.config_repo.get_by_id(config_id)
                
                return self._config_to_response(config)
                
            except Exception as e:
                self.logger.error("Failed to get guild config", guild_id=guild_id, error=str(e))
                raise HTTPException(status_code=500, detail=f"Failed to get guild config: {str(e)}")
        
        @self.router.put("/{guild_id}", response_model=BasicGuildConfigResponse)
        async def update_guild_config(guild_id: str, request: GuildConfigUpdateRequest):
            """Update guild configuration."""
            try:
                config = await self.config_repo.get_by_guild_id(guild_id)
                if not config:
                    raise HTTPException(status_code=404, detail="Guild configuration not found")
                
                # Update basic fields only
                if request.guild_name is not None:
                    config.guild_name = request.guild_name
                if request.default_timezone is not None:
                    config.default_timezone = request.default_timezone
                if request.default_event_duration is not None:
                    config.default_event_duration = request.default_event_duration
                if request.max_events_per_user is not None:
                    config.max_events_per_user = request.max_events_per_user
                
                # Save changes
                await self.config_repo.update(str(config.id), config)
                
                self.logger.info("Guild config updated", guild_id=guild_id)
                
                return self._config_to_response(config)
                
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("Failed to update guild config", guild_id=guild_id, error=str(e))
                raise HTTPException(status_code=500, detail=f"Failed to update guild config: {str(e)}")
    
    def _config_to_response(self, config: GuildConfig) -> BasicGuildConfigResponse:
        """Convert GuildConfig model to basic response format."""
        return BasicGuildConfigResponse(
            id=str(config.id),
            guild_id=config.guild_id,
            guild_name=config.guild_name,
            default_timezone=config.default_timezone,
            default_event_duration=config.default_event_duration,
            max_events_per_user=config.max_events_per_user,
            created_at=config.created_at,
            updated_at=config.updated_at
        )


def create_config_router(database: DatabaseManager) -> APIRouter:
    """Create and return the configuration router."""
    config_routes = ConfigRoutes(database)
    return config_routes.router