"""
Recurring Events API routes for the Game Night Bot web dashboard.

Provides basic REST endpoints for recurring events management.
"""

from datetime import datetime, time
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models.recurring import RecurringSchedule, TriggerType, ScheduleStatus
from models.repositories import RecurringScheduleRepository
from database.manager import DatabaseManager
from utils.logging_config import LoggerMixin


class RecurringScheduleCreateRequest(BaseModel):
    """Request model for creating recurring schedules."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    creator_id: str = Field(..., description="Discord user ID of creator")
    trigger_type: TriggerType
    trigger_time: time


class RecurringScheduleUpdateRequest(BaseModel):
    """Request model for updating recurring schedules."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class BasicRecurringScheduleResponse(BaseModel):
    """Basic response model for recurring schedules."""
    id: str
    guild_id: str
    name: str
    description: Optional[str]
    creator_id: str
    status: ScheduleStatus
    created_at: datetime
    updated_at: datetime


class RecurringScheduleListResponse(BaseModel):
    """Response model for recurring schedule lists."""
    schedules: List[BasicRecurringScheduleResponse]
    total_count: int
    page: int
    page_size: int


class RecurringRoutes(LoggerMixin):
    """Recurring events API routes handler."""
    
    def __init__(self, database: DatabaseManager):
        self.database = database
        self.schedule_repo = RecurringScheduleRepository(database, RecurringSchedule)
        self.router = APIRouter(prefix="/api/recurring", tags=["recurring"])
        self._setup_routes()
    
    def _setup_routes(self):
        """Set up basic recurring events routes."""
        
        @self.router.get("", response_model=RecurringScheduleListResponse)
        async def list_recurring_schedules(
            guild_id: str = Query(..., description="Guild ID filter"),
            page: int = Query(1, ge=1, description="Page number"),
            page_size: int = Query(20, ge=1, le=100, description="Page size")
        ):
            """List recurring schedules with basic pagination."""
            try:
                # Build basic filter
                filter_dict = {"guild_id": guild_id}
                
                # Get total count
                total_count = await self.schedule_repo.count(filter_dict)
                
                # Get paginated results
                skip = (page - 1) * page_size
                schedules = await self.schedule_repo.find(
                    filter_dict,
                    limit=page_size,
                    skip=skip,
                    sort=[("created_at", -1)]
                )
                
                # Convert to response format
                schedule_responses = [self._schedule_to_response(schedule) for schedule in schedules]
                
                return RecurringScheduleListResponse(
                    schedules=schedule_responses,
                    total_count=total_count,
                    page=page,
                    page_size=page_size
                )
                
            except Exception as e:
                self.logger.error("Failed to list recurring schedules", error=str(e))
                raise HTTPException(status_code=500, detail=f"Failed to list recurring schedules: {str(e)}")
        
        @self.router.post("", response_model=BasicRecurringScheduleResponse)
        async def create_recurring_schedule(
            request: RecurringScheduleCreateRequest,
            guild_id: str = Query(..., description="Guild ID")
        ):
            """Create a new recurring schedule."""
            try:
                # Create basic schedule
                schedule = RecurringSchedule(
                    guild_id=guild_id,
                    name=request.name,
                    description=request.description,
                    creator_id=request.creator_id
                )
                
                # Save to database
                schedule_id = await self.schedule_repo.create(schedule)
                schedule.id = schedule_id
                
                self.logger.info("Recurring schedule created", schedule_id=schedule_id, guild_id=guild_id)
                
                return self._schedule_to_response(schedule)
                
            except Exception as e:
                self.logger.error("Failed to create recurring schedule", error=str(e))
                raise HTTPException(status_code=500, detail=f"Failed to create recurring schedule: {str(e)}")
        
        @self.router.get("/{schedule_id}", response_model=BasicRecurringScheduleResponse)
        async def get_recurring_schedule(schedule_id: str):
            """Get recurring schedule by ID."""
            try:
                schedule = await self.schedule_repo.get_by_id(schedule_id)
                if not schedule:
                    raise HTTPException(status_code=404, detail="Recurring schedule not found")
                
                return self._schedule_to_response(schedule)
                
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("Failed to get recurring schedule", schedule_id=schedule_id, error=str(e))
                raise HTTPException(status_code=500, detail=f"Failed to get recurring schedule: {str(e)}")
        
        @self.router.put("/{schedule_id}", response_model=BasicRecurringScheduleResponse)
        async def update_recurring_schedule(schedule_id: str, request: RecurringScheduleUpdateRequest):
            """Update recurring schedule."""
            try:
                schedule = await self.schedule_repo.get_by_id(schedule_id)
                if not schedule:
                    raise HTTPException(status_code=404, detail="Recurring schedule not found")
                
                # Update basic fields
                if request.name is not None:
                    schedule.name = request.name
                if request.description is not None:
                    schedule.description = request.description
                
                # Save changes
                await self.schedule_repo.update(schedule_id, schedule)
                
                self.logger.info("Recurring schedule updated", schedule_id=schedule_id)
                
                return self._schedule_to_response(schedule)
                
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("Failed to update recurring schedule", schedule_id=schedule_id, error=str(e))
                raise HTTPException(status_code=500, detail=f"Failed to update recurring schedule: {str(e)}")
        
        @self.router.delete("/{schedule_id}")
        async def delete_recurring_schedule(schedule_id: str):
            """Delete recurring schedule."""
            try:
                schedule = await self.schedule_repo.get_by_id(schedule_id)
                if not schedule:
                    raise HTTPException(status_code=404, detail="Recurring schedule not found")
                
                await self.schedule_repo.delete(schedule_id)
                
                self.logger.info("Recurring schedule deleted", schedule_id=schedule_id)
                
                return {"message": "Recurring schedule deleted successfully"}
                
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("Failed to delete recurring schedule", schedule_id=schedule_id, error=str(e))
                raise HTTPException(status_code=500, detail=f"Failed to delete recurring schedule: {str(e)}")
    
    def _schedule_to_response(self, schedule: RecurringSchedule) -> BasicRecurringScheduleResponse:
        """Convert RecurringSchedule model to basic response format."""
        return BasicRecurringScheduleResponse(
            id=str(schedule.id),
            guild_id=schedule.guild_id,
            name=schedule.name,
            description=schedule.description,
            creator_id=schedule.creator_id,
            status=schedule.status,
            created_at=schedule.created_at,
            updated_at=schedule.updated_at
        )


def create_recurring_router(database: DatabaseManager) -> APIRouter:
    """Create and return the recurring events router."""
    recurring_routes = RecurringRoutes(database)
    return recurring_routes.router