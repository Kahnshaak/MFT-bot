"""
Graceful degradation manager for handling service unavailability.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Callable
from enum import Enum
from dataclasses import dataclass, asdict

from core.event_bus import EventBus, EventType
from utils.logging_config import get_logger, LoggerMixin
from utils.exceptions import (
    ServiceUnavailableError, GracefulDegradationError,
    ErrorCode
)


class ServiceType(str, Enum):
    """Types of services that can be degraded."""
    DISCORD_API = "discord_api"
    DATABASE = "database"
    NOTIFICATIONS = "notifications"
    SCHEDULED_EVENTS = "scheduled_events"
    WEB_DASHBOARD = "web_dashboard"
    POLL_MANAGEMENT = "poll_management"
    USER_MANAGEMENT = "user_management"


class DegradationLevel(str, Enum):
    """Levels of service degradation."""
    NORMAL = "normal"
    LIMITED = "limited"
    MINIMAL = "minimal"
    UNAVAILABLE = "unavailable"


@dataclass
class ServiceStatus:
    """Status information for a service."""
    service_type: ServiceType
    degradation_level: DegradationLevel
    last_check: datetime
    failure_count: int
    consecutive_failures: int
    last_failure: Optional[datetime]
    degraded_since: Optional[datetime]
    available_features: List[str]
    unavailable_features: List[str]
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GracefulDegradationManager(LoggerMixin):
    """
    Manager for graceful service degradation when external services fail.
    """
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._service_status: Dict[ServiceType, ServiceStatus] = {}
        self._degradation_handlers: Dict[ServiceType, Callable] = {}
        self._health_checkers: Dict[ServiceType, Callable] = {}
        self._recovery_callbacks: Dict[ServiceType, List[Callable]] = {}
        self._monitoring_tasks: Dict[ServiceType, asyncio.Task] = {}
        
        # Initialize service statuses
        self._initialize_service_statuses()
        
        # Register default degradation handlers
        self._register_default_handlers()
    
    def _initialize_service_statuses(self) -> None:
        """Initialize service status tracking."""
        for service_type in ServiceType:
            self._service_status[service_type] = ServiceStatus(
                service_type=service_type,
                degradation_level=DegradationLevel.NORMAL,
                last_check=datetime.now(),
                failure_count=0,
                consecutive_failures=0,
                last_failure=None,
                degraded_since=None,
                available_features=[],
                unavailable_features=[]
            )
    
    def _register_default_handlers(self) -> None:
        """Register default degradation handlers."""
        self._degradation_handlers[ServiceType.DISCORD_API] = self._handle_discord_api_degradation
        self._degradation_handlers[ServiceType.DATABASE] = self._handle_database_degradation
        self._degradation_handlers[ServiceType.NOTIFICATIONS] = self._handle_notifications_degradation
        self._degradation_handlers[ServiceType.SCHEDULED_EVENTS] = self._handle_scheduled_events_degradation
        self._degradation_handlers[ServiceType.WEB_DASHBOARD] = self._handle_web_dashboard_degradation
        self._degradation_handlers[ServiceType.POLL_MANAGEMENT] = self._handle_poll_management_degradation
        self._degradation_handlers[ServiceType.USER_MANAGEMENT] = self._handle_user_management_degradation
    
    async def report_service_failure(
        self, 
        service_type: ServiceType, 
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> DegradationLevel:
        """
        Report a service failure and determine degradation level.
        
        Args:
            service_type: Type of service that failed
            error: The error that occurred
            context: Additional context about the failure
            
        Returns:
            New degradation level for the service
        """
        status = self._service_status[service_type]
        now = datetime.now()
        
        # Update failure tracking
        status.failure_count += 1
        status.consecutive_failures += 1
        status.last_failure = now
        status.last_check = now
        status.error_message = str(error)
        
        # Determine new degradation level
        old_level = status.degradation_level
        new_level = self._calculate_degradation_level(status)
        
        if new_level != old_level:
            status.degradation_level = new_level
            
            if old_level == DegradationLevel.NORMAL:
                status.degraded_since = now
            
            # Apply degradation
            await self._apply_degradation(service_type, new_level, error, context)
            
            # Emit degradation event
            await self.event_bus.emit(
                EventType.ERROR_OCCURRED,
                {
                    "type": "service_degradation",
                    "service_type": service_type.value,
                    "old_level": old_level.value,
                    "new_level": new_level.value,
                    "failure_count": status.failure_count,
                    "consecutive_failures": status.consecutive_failures,
                    "error": str(error)
                }
            )
        
        self.logger.warning(
            "Service failure reported",
            service_type=service_type.value,
            degradation_level=new_level.value,
            failure_count=status.failure_count,
            consecutive_failures=status.consecutive_failures,
            error=str(error)
        )
        
        return new_level
    
    async def report_service_recovery(
        self, 
        service_type: ServiceType
    ) -> DegradationLevel:
        """
        Report service recovery and potentially restore normal operation.
        
        Args:
            service_type: Type of service that recovered
            
        Returns:
            New degradation level for the service
        """
        status = self._service_status[service_type]
        now = datetime.now()
        
        # Reset failure tracking
        status.consecutive_failures = 0
        status.last_check = now
        status.error_message = None
        
        # Determine if we can restore service
        old_level = status.degradation_level
        
        # Gradually restore service based on stability
        if old_level == DegradationLevel.UNAVAILABLE:
            new_level = DegradationLevel.MINIMAL
        elif old_level == DegradationLevel.MINIMAL:
            new_level = DegradationLevel.LIMITED
        elif old_level == DegradationLevel.LIMITED:
            new_level = DegradationLevel.NORMAL
        else:
            new_level = DegradationLevel.NORMAL
        
        if new_level != old_level:
            status.degradation_level = new_level
            
            if new_level == DegradationLevel.NORMAL:
                status.degraded_since = None
            
            # Apply recovery
            await self._apply_recovery(service_type, new_level)
            
            # Emit recovery event
            await self.event_bus.emit(
                EventType.ERROR_OCCURRED,
                {
                    "type": "service_recovery",
                    "service_type": service_type.value,
                    "old_level": old_level.value,
                    "new_level": new_level.value,
                    "was_degraded_for": (now - status.degraded_since).total_seconds() if status.degraded_since else 0
                }
            )
        
        self.logger.info(
            "Service recovery reported",
            service_type=service_type.value,
            old_level=old_level.value,
            new_level=new_level.value
        )
        
        return new_level
    
    def get_service_status(self, service_type: ServiceType) -> ServiceStatus:
        """Get current status of a service."""
        return self._service_status[service_type]
    
    def get_all_service_statuses(self) -> Dict[ServiceType, ServiceStatus]:
        """Get status of all services."""
        return self._service_status.copy()
    
    def is_service_available(self, service_type: ServiceType) -> bool:
        """Check if a service is available (not completely unavailable)."""
        status = self._service_status[service_type]
        return status.degradation_level != DegradationLevel.UNAVAILABLE
    
    def is_feature_available(self, service_type: ServiceType, feature: str) -> bool:
        """Check if a specific feature is available."""
        status = self._service_status[service_type]
        return feature in status.available_features
    
    def register_health_checker(
        self, 
        service_type: ServiceType, 
        checker: Callable[[], bool]
    ) -> None:
        """Register a health checker for a service."""
        self._health_checkers[service_type] = checker
    
    def register_recovery_callback(
        self, 
        service_type: ServiceType, 
        callback: Callable[[DegradationLevel], None]
    ) -> None:
        """Register a callback for service recovery."""
        if service_type not in self._recovery_callbacks:
            self._recovery_callbacks[service_type] = []
        self._recovery_callbacks[service_type].append(callback)
    
    async def start_monitoring(self, service_type: ServiceType, interval: int = 60) -> None:
        """Start monitoring a service for recovery."""
        if service_type in self._monitoring_tasks:
            self._monitoring_tasks[service_type].cancel()
        
        self._monitoring_tasks[service_type] = asyncio.create_task(
            self._monitor_service_health(service_type, interval)
        )
    
    async def stop_monitoring(self, service_type: ServiceType) -> None:
        """Stop monitoring a service."""
        if service_type in self._monitoring_tasks:
            self._monitoring_tasks[service_type].cancel()
            del self._monitoring_tasks[service_type]
    
    def _calculate_degradation_level(self, status: ServiceStatus) -> DegradationLevel:
        """Calculate appropriate degradation level based on failure history."""
        consecutive_failures = status.consecutive_failures
        
        if consecutive_failures >= 10:
            return DegradationLevel.UNAVAILABLE
        elif consecutive_failures >= 5:
            return DegradationLevel.MINIMAL
        elif consecutive_failures >= 2:
            return DegradationLevel.LIMITED
        else:
            return DegradationLevel.NORMAL
    
    async def _apply_degradation(
        self, 
        service_type: ServiceType, 
        level: DegradationLevel,
        error: Exception,
        context: Optional[Dict[str, Any]]
    ) -> None:
        """Apply degradation for a service."""
        handler = self._degradation_handlers.get(service_type)
        if handler:
            try:
                await handler(level, error, context)
            except Exception as e:
                self.logger.error(
                    "Error applying degradation",
                    service_type=service_type.value,
                    level=level.value,
                    error=str(e)
                )
    
    async def _apply_recovery(
        self, 
        service_type: ServiceType, 
        level: DegradationLevel
    ) -> None:
        """Apply recovery for a service."""
        # Call recovery callbacks
        callbacks = self._recovery_callbacks.get(service_type, [])
        for callback in callbacks:
            try:
                await callback(level)
            except Exception as e:
                self.logger.error(
                    "Error in recovery callback",
                    service_type=service_type.value,
                    error=str(e)
                )
    
    async def _monitor_service_health(
        self, 
        service_type: ServiceType, 
        interval: int
    ) -> None:
        """Monitor service health and attempt recovery."""
        while True:
            try:
                await asyncio.sleep(interval)
                
                status = self._service_status[service_type]
                
                # Only check if service is degraded
                if status.degradation_level == DegradationLevel.NORMAL:
                    continue
                
                # Check if we have a health checker
                health_checker = self._health_checkers.get(service_type)
                if not health_checker:
                    continue
                
                # Perform health check
                try:
                    is_healthy = await health_checker()
                    if is_healthy:
                        await self.report_service_recovery(service_type)
                except Exception as e:
                    self.logger.debug(
                        "Health check failed",
                        service_type=service_type.value,
                        error=str(e)
                    )
                    # Don't report as failure since we're already degraded
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    "Error in service health monitoring",
                    service_type=service_type.value,
                    error=str(e)
                )
    
    # Default degradation handlers
    
    async def _handle_discord_api_degradation(
        self, 
        level: DegradationLevel, 
        error: Exception,
        context: Optional[Dict[str, Any]]
    ) -> None:
        """Handle Discord API degradation."""
        status = self._service_status[ServiceType.DISCORD_API]
        
        if level == DegradationLevel.LIMITED:
            status.available_features = [
                "basic_commands", "text_responses", "cached_data"
            ]
            status.unavailable_features = [
                "scheduled_events", "complex_embeds", "file_uploads"
            ]
        elif level == DegradationLevel.MINIMAL:
            status.available_features = [
                "basic_commands", "text_responses"
            ]
            status.unavailable_features = [
                "scheduled_events", "complex_embeds", "file_uploads", 
                "reactions", "interactive_components"
            ]
        elif level == DegradationLevel.UNAVAILABLE:
            status.available_features = []
            status.unavailable_features = [
                "all_discord_features"
            ]
    
    async def _handle_database_degradation(
        self, 
        level: DegradationLevel, 
        error: Exception,
        context: Optional[Dict[str, Any]]
    ) -> None:
        """Handle database degradation."""
        status = self._service_status[ServiceType.DATABASE]
        
        if level == DegradationLevel.LIMITED:
            status.available_features = [
                "read_operations", "cached_data", "essential_writes"
            ]
            status.unavailable_features = [
                "analytics", "bulk_operations", "complex_queries"
            ]
        elif level == DegradationLevel.MINIMAL:
            status.available_features = [
                "cached_data", "essential_writes"
            ]
            status.unavailable_features = [
                "read_operations", "analytics", "bulk_operations", "complex_queries"
            ]
        elif level == DegradationLevel.UNAVAILABLE:
            status.available_features = [
                "cached_data"
            ]
            status.unavailable_features = [
                "all_database_operations"
            ]
    
    async def _handle_notifications_degradation(
        self, 
        level: DegradationLevel, 
        error: Exception,
        context: Optional[Dict[str, Any]]
    ) -> None:
        """Handle notifications degradation."""
        status = self._service_status[ServiceType.NOTIFICATIONS]
        
        if level == DegradationLevel.LIMITED:
            status.available_features = [
                "critical_notifications", "immediate_notifications"
            ]
            status.unavailable_features = [
                "scheduled_notifications", "bulk_notifications"
            ]
        elif level == DegradationLevel.MINIMAL:
            status.available_features = [
                "critical_notifications"
            ]
            status.unavailable_features = [
                "scheduled_notifications", "bulk_notifications", "reminder_notifications"
            ]
        elif level == DegradationLevel.UNAVAILABLE:
            status.available_features = []
            status.unavailable_features = [
                "all_notifications"
            ]
    
    async def _handle_scheduled_events_degradation(
        self, 
        level: DegradationLevel, 
        error: Exception,
        context: Optional[Dict[str, Any]]
    ) -> None:
        """Handle scheduled events degradation."""
        status = self._service_status[ServiceType.SCHEDULED_EVENTS]
        
        if level == DegradationLevel.LIMITED:
            status.available_features = [
                "event_creation", "basic_rsvp"
            ]
            status.unavailable_features = [
                "discord_scheduled_events", "calendar_sync"
            ]
        elif level == DegradationLevel.MINIMAL:
            status.available_features = [
                "basic_rsvp"
            ]
            status.unavailable_features = [
                "event_creation", "discord_scheduled_events", "calendar_sync"
            ]
        elif level == DegradationLevel.UNAVAILABLE:
            status.available_features = []
            status.unavailable_features = [
                "all_scheduled_events"
            ]
    
    async def _handle_web_dashboard_degradation(
        self, 
        level: DegradationLevel, 
        error: Exception,
        context: Optional[Dict[str, Any]]
    ) -> None:
        """Handle web dashboard degradation."""
        status = self._service_status[ServiceType.WEB_DASHBOARD]
        
        if level == DegradationLevel.LIMITED:
            status.available_features = [
                "basic_viewing", "essential_config"
            ]
            status.unavailable_features = [
                "analytics", "bulk_operations", "advanced_config"
            ]
        elif level == DegradationLevel.MINIMAL:
            status.available_features = [
                "basic_viewing"
            ]
            status.unavailable_features = [
                "analytics", "bulk_operations", "advanced_config", "config_changes"
            ]
        elif level == DegradationLevel.UNAVAILABLE:
            status.available_features = []
            status.unavailable_features = [
                "all_web_features"
            ]
    
    async def _handle_poll_management_degradation(
        self, 
        level: DegradationLevel, 
        error: Exception,
        context: Optional[Dict[str, Any]]
    ) -> None:
        """Handle poll management degradation."""
        status = self._service_status[ServiceType.POLL_MANAGEMENT]
        
        if level == DegradationLevel.LIMITED:
            status.available_features = [
                "basic_voting", "poll_viewing"
            ]
            status.unavailable_features = [
                "poll_creation", "advanced_features", "analytics"
            ]
        elif level == DegradationLevel.MINIMAL:
            status.available_features = [
                "poll_viewing"
            ]
            status.unavailable_features = [
                "basic_voting", "poll_creation", "advanced_features", "analytics"
            ]
        elif level == DegradationLevel.UNAVAILABLE:
            status.available_features = []
            status.unavailable_features = [
                "all_poll_features"
            ]
    
    async def _handle_user_management_degradation(
        self, 
        level: DegradationLevel, 
        error: Exception,
        context: Optional[Dict[str, Any]]
    ) -> None:
        """Handle user management degradation."""
        status = self._service_status[ServiceType.USER_MANAGEMENT]
        
        if level == DegradationLevel.LIMITED:
            status.available_features = [
                "basic_profile", "essential_preferences"
            ]
            status.unavailable_features = [
                "advanced_preferences", "statistics", "data_export"
            ]
        elif level == DegradationLevel.MINIMAL:
            status.available_features = [
                "basic_profile"
            ]
            status.unavailable_features = [
                "advanced_preferences", "statistics", "data_export", "preference_changes"
            ]
        elif level == DegradationLevel.UNAVAILABLE:
            status.available_features = []
            status.unavailable_features = [
                "all_user_features"
            ]