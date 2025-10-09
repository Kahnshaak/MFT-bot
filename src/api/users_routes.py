"""
Users API routes for the Game Night Bot web dashboard.

Provides basic REST endpoints for user profile management.
"""

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models.user import User
from models.repositories import UserRepository
from database.manager import DatabaseManager
from utils.logging_config import LoggerMixin


class UserUpdateRequest(BaseModel):
    """Request model for updating users."""
    display_name: Optional[str] = Field(None, max_length=100)
    timezone: Optional[str] = None


class BasicUserResponse(BaseModel):
    """Basic response model for users."""
    id: str
    user_id: str
    guild_id: str
    display_name: Optional[str]
    timezone: str
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    """Response model for user lists."""
    users: List[BasicUserResponse]
    total_count: int
    page: int
    page_size: int


class UsersRoutes(LoggerMixin):
    """Users API routes handler."""
    
    def __init__(self, database: DatabaseManager):
        self.database = database
        self.user_repo = UserRepository(database, User)
        self.router = APIRouter(prefix="/api/users", tags=["users"])
        self._setup_routes()
    
    def _setup_routes(self):
        """Set up basic users routes."""
        
        @self.router.get("", response_model=UserListResponse)
        async def list_users(
            guild_id: str = Query(..., description="Guild ID filter"),
            page: int = Query(1, ge=1, description="Page number"),
            page_size: int = Query(20, ge=1, le=100, description="Page size")
        ):
            """List users with basic pagination."""
            try:
                # Build basic filter
                filter_dict = {"guild_id": guild_id}
                
                # Get total count
                total_count = await self.user_repo.count(filter_dict)
                
                # Get paginated results
                skip = (page - 1) * page_size
                users = await self.user_repo.find(
                    filter_dict,
                    limit=page_size,
                    skip=skip,
                    sort=[("created_at", -1)]
                )
                
                # Convert to response format
                user_responses = [self._user_to_response(user) for user in users]
                
                return UserListResponse(
                    users=user_responses,
                    total_count=total_count,
                    page=page,
                    page_size=page_size
                )
                
            except Exception as e:
                self.logger.error("Failed to list users", error=str(e))
                raise HTTPException(status_code=500, detail=f"Failed to list users: {str(e)}")
        
        @self.router.get("/{user_id}", response_model=BasicUserResponse)
        async def get_user(
            user_id: str,
            guild_id: str = Query(..., description="Guild ID")
        ):
            """Get user by Discord user ID."""
            try:
                user = await self.user_repo.get_by_user_and_guild(user_id, guild_id)
                if not user:
                    raise HTTPException(status_code=404, detail="User not found")
                
                return self._user_to_response(user)
                
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("Failed to get user", user_id=user_id, error=str(e))
                raise HTTPException(status_code=500, detail=f"Failed to get user: {str(e)}")
        
        @self.router.put("/{user_id}", response_model=BasicUserResponse)
        async def update_user(
            user_id: str,
            request: UserUpdateRequest,
            guild_id: str = Query(..., description="Guild ID")
        ):
            """Update user profile."""
            try:
                user = await self.user_repo.get_by_user_and_guild(user_id, guild_id)
                if not user:
                    raise HTTPException(status_code=404, detail="User not found")
                
                # Update basic fields
                if request.display_name is not None:
                    user.display_name = request.display_name
                if request.timezone is not None:
                    user.timezone = request.timezone
                
                # Save changes
                await self.user_repo.update(str(user.id), user)
                
                self.logger.info("User updated", user_id=user_id, guild_id=guild_id)
                
                return self._user_to_response(user)
                
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("Failed to update user", user_id=user_id, error=str(e))
                raise HTTPException(status_code=500, detail=f"Failed to update user: {str(e)}")
    
    def _user_to_response(self, user: User) -> BasicUserResponse:
        """Convert User model to basic response format."""
        return BasicUserResponse(
            id=str(user.id),
            user_id=user.user_id,
            guild_id=user.guild_id,
            display_name=user.display_name,
            timezone=user.timezone,
            created_at=user.created_at,
            updated_at=user.updated_at
        )


def create_users_router(database: DatabaseManager) -> APIRouter:
    """Create and return the users router."""
    users_routes = UsersRoutes(database)
    return users_routes.router