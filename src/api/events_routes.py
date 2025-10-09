"""
Events API routes for the Game Night Bot web dashboard.

Provides basic REST endpoints for events management.
"""

from datetime import datetime, date, time
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models.event import Event, EventState, RSVPStatus
from models.repositories import EventRepository
from database.manager import DatabaseManager
from utils.logging_config import LoggerMixin


class EventCreateRequest(BaseModel):
    """Request model for creating events."""
    title: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)
    creator_id: str = Field(..., description="Discord user ID of creator")


class EventUpdateRequest(BaseModel):
    """Request model for updating events."""
    title: Optional[str] = Field(None, min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)


class RSVPRequest(BaseModel):
    """Request model for RSVP responses."""
    status: RSVPStatus
    notes: Optional[str] = Field(None, max_length=500)


class BasicEventResponse(BaseModel):
    """Basic response model for events."""
    id: str
    guild_id: str
    title: str
    description: Optional[str]
    creator_id: str
    state: EventState
    created_at: datetime
    updated_at: datetime


class EventListResponse(BaseModel):
    """Response model for event lists."""
    events: List[BasicEventResponse]
    total_count: int
    page: int
    page_size: int


class EventsRoutes(LoggerMixin):
    """Events API routes handler."""
    
    def __init__(self, database: DatabaseManager):
        self.database = database
        self.event_repo = EventRepository(database, Event)
        self.router = APIRouter(prefix="/api/events", tags=["events"])
        self._setup_routes()
    
    def _setup_routes(self):
        """Set up basic events routes."""
        
        @self.router.get("", response_model=EventListResponse)
        async def list_events(
            guild_id: str = Query(..., description="Guild ID filter"),
            page: int = Query(1, ge=1, description="Page number"),
            page_size: int = Query(20, ge=1, le=100, description="Page size")
        ):
            """List events with basic pagination."""
            try:
                # Build basic filter
                filter_dict = {"guild_id": guild_id}
                
                # Get total count
                total_count = await self.event_repo.count(filter_dict)
                
                # Get paginated results
                skip = (page - 1) * page_size
                events = await self.event_repo.find(
                    filter_dict,
                    limit=page_size,
                    skip=skip,
                    sort=[("created_at", -1)]
                )
                
                # Convert to response format
                event_responses = [self._event_to_response(event) for event in events]
                
                return EventListResponse(
                    events=event_responses,
                    total_count=total_count,
                    page=page,
                    page_size=page_size
                )
                
            except Exception as e:
                self.logger.error("Failed to list events", error=str(e))
                raise HTTPException(status_code=500, detail=f"Failed to list events: {str(e)}")
        
        @self.router.post("", response_model=BasicEventResponse)
        async def create_event(
            request: EventCreateRequest,
            guild_id: str = Query(..., description="Guild ID")
        ):
            """Create a new event."""
            try:
                # Create basic event object
                event = Event(
                    guild_id=guild_id,
                    title=request.title,
                    description=request.description,
                    creator_id=request.creator_id
                )
                
                # Save to database
                event_id = await self.event_repo.create(event)
                event.id = event_id
                
                self.logger.info("Event created", event_id=event_id, guild_id=guild_id)
                
                return self._event_to_response(event)
                
            except Exception as e:
                self.logger.error("Failed to create event", error=str(e))
                raise HTTPException(status_code=500, detail=f"Failed to create event: {str(e)}")
        
        @self.router.get("/{event_id}", response_model=BasicEventResponse)
        async def get_event(event_id: str):
            """Get event by ID."""
            try:
                event = await self.event_repo.get_by_id(event_id)
                if not event:
                    raise HTTPException(status_code=404, detail="Event not found")
                
                return self._event_to_response(event)
                
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("Failed to get event", event_id=event_id, error=str(e))
                raise HTTPException(status_code=500, detail=f"Failed to get event: {str(e)}")
        
        @self.router.put("/{event_id}", response_model=BasicEventResponse)
        async def update_event(event_id: str, request: EventUpdateRequest):
            """Update event."""
            try:
                event = await self.event_repo.get_by_id(event_id)
                if not event:
                    raise HTTPException(status_code=404, detail="Event not found")
                
                # Update basic fields
                if request.title is not None:
                    event.title = request.title
                if request.description is not None:
                    event.description = request.description
                
                # Save changes
                await self.event_repo.update(event_id, event)
                
                self.logger.info("Event updated", event_id=event_id)
                
                return self._event_to_response(event)
                
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("Failed to update event", event_id=event_id, error=str(e))
                raise HTTPException(status_code=500, detail=f"Failed to update event: {str(e)}")
        
        @self.router.delete("/{event_id}")
        async def delete_event(event_id: str):
            """Delete event."""
            try:
                event = await self.event_repo.get_by_id(event_id)
                if not event:
                    raise HTTPException(status_code=404, detail="Event not found")
                
                await self.event_repo.delete(event_id)
                
                self.logger.info("Event deleted", event_id=event_id)
                return {"message": "Event deleted successfully"}
                
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("Failed to delete event", event_id=event_id, error=str(e))
                raise HTTPException(status_code=500, detail=f"Failed to delete event: {str(e)}")
        
        @self.router.post("/{event_id}/rsvp")
        async def rsvp_to_event(
            event_id: str,
            request: RSVPRequest,
            user_id: str = Query(..., description="User ID for RSVP")
        ):
            """RSVP to an event."""
            try:
                event = await self.event_repo.get_by_id(event_id)
                if not event:
                    raise HTTPException(status_code=404, detail="Event not found")
                
                # Add RSVP
                event.add_rsvp(user_id, request.status, request.notes)
                
                # Save changes
                await self.event_repo.update(event_id, event)
                
                self.logger.info("RSVP recorded", event_id=event_id, user_id=user_id, status=request.status.value)
                
                return {"message": "RSVP recorded successfully"}
                
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("Failed to record RSVP", event_id=event_id, error=str(e))
                raise HTTPException(status_code=500, detail=f"Failed to record RSVP: {str(e)}")
    
    def _event_to_response(self, event: Event) -> BasicEventResponse:
        """Convert Event model to basic response format."""
        return BasicEventResponse(
            id=str(event.id),
            guild_id=event.guild_id,
            title=event.title,
            description=event.description,
            creator_id=event.creator_id,
            state=event.state,
            created_at=event.created_at,
            updated_at=event.updated_at
        )


def create_events_router(database: DatabaseManager) -> APIRouter:
    """Create and return the events router."""
    events_routes = EventsRoutes(database)
    return events_routes.router