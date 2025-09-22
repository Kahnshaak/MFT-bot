"""
Audit logging system for tracking administrative actions and security events.
"""

import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum

import discord

from utils.logging_config import get_logger, LoggerMixin
from database.manager import DatabaseManager


class AuditEventType(Enum):
    """Types of audit events."""
    
    # Authentication events
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    LOGIN_FAILED = "login_failed"
    SESSION_EXPIRED = "session_expired"
    
    # Permission events
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"
    ROLE_MAPPING_CHANGED = "role_mapping_changed"
    
    # Event management
    EVENT_CREATED = "event_created"
    EVENT_UPDATED = "event_updated"
    EVENT_CANCELLED = "event_cancelled"
    EVENT_DELETED = "event_deleted"
    
    # Poll management
    POLL_CREATED = "poll_created"
    POLL_CLOSED = "poll_closed"
    POLL_VOTE_CAST = "poll_vote_cast"
    POLL_ADMIN_OVERRIDE = "poll_admin_override"
    
    # User management
    USER_PROFILE_UPDATED = "user_profile_updated"
    USER_BANNED = "user_banned"
    USER_UNBANNED = "user_unbanned"
    USER_DATA_EXPORTED = "user_data_exported"
    
    # Configuration changes
    BOT_CONFIG_CHANGED = "bot_config_changed"
    RECURRING_SCHEDULE_CREATED = "recurring_schedule_created"
    RECURRING_SCHEDULE_UPDATED = "recurring_schedule_updated"
    RECURRING_SCHEDULE_DELETED = "recurring_schedule_deleted"
    
    # Security events
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    SECURITY_VIOLATION = "security_violation"
    
    # System events
    BACKUP_CREATED = "backup_created"
    BACKUP_RESTORED = "backup_restored"
    MAINTENANCE_MODE_ENABLED = "maintenance_mode_enabled"
    MAINTENANCE_MODE_DISABLED = "maintenance_mode_disabled"


@dataclass
class AuditEvent:
    """Represents an audit log entry."""
    
    event_type: AuditEventType
    user_id: Optional[str]
    guild_id: Optional[str]
    resource_id: Optional[str]
    resource_type: Optional[str]
    action: str
    details: Dict[str, Any]
    timestamp: float
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert audit event to dictionary."""
        return asdict(self)


class AuditLogger(LoggerMixin):
    """
    Audit logging system for tracking security-relevant events.
    """
    
    def __init__(self, database: DatabaseManager):
        self.database = database
        self._audit_collection = "audit_logs"
    
    async def log_event(
        self,
        event_type: AuditEventType,
        action: str,
        user_id: Optional[str] = None,
        guild_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> None:
        """
        Log an audit event.
        
        Args:
            event_type: Type of audit event
            action: Description of the action performed
            user_id: ID of user who performed the action
            guild_id: Guild where action occurred
            resource_id: ID of affected resource
            resource_type: Type of affected resource
            details: Additional event details
            ip_address: IP address of the user
            user_agent: User agent string
            session_id: Session identifier
        """
        audit_event = AuditEvent(
            event_type=event_type,
            user_id=user_id,
            guild_id=guild_id,
            resource_id=resource_id,
            resource_type=resource_type,
            action=action,
            details=details or {},
            timestamp=time.time(),
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id
        )
        
        try:
            # Store in database
            await self.database.insert_document(
                self._audit_collection,
                audit_event.to_dict()
            )
            
            # Log to application logs
            self.logger.info(
                "Audit event logged",
                event_type=event_type.value,
                action=action,
                user_id=user_id,
                guild_id=guild_id,
                resource_id=resource_id
            )
            
        except Exception as e:
            self.logger.error(
                "Failed to log audit event",
                event_type=event_type.value,
                action=action,
                error=str(e)
            )
    
    async def log_authentication_event(
        self,
        event_type: AuditEventType,
        user_id: str,
        success: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log authentication-related events.
        
        Args:
            event_type: Type of authentication event
            user_id: User ID
            success: Whether the authentication was successful
            ip_address: IP address
            user_agent: User agent string
            details: Additional details
        """
        action = f"Authentication {'successful' if success else 'failed'}"
        
        await self.log_event(
            event_type=event_type,
            action=action,
            user_id=user_id,
            details={
                "success": success,
                **(details or {})
            },
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    async def log_permission_event(
        self,
        granted: bool,
        user_id: str,
        guild_id: str,
        permission: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log permission-related events.
        
        Args:
            granted: Whether permission was granted
            user_id: User ID
            guild_id: Guild ID
            permission: Permission that was checked
            resource_id: Resource ID if applicable
            details: Additional details
        """
        event_type = AuditEventType.PERMISSION_GRANTED if granted else AuditEventType.PERMISSION_DENIED
        action = f"Permission {permission} {'granted' if granted else 'denied'}"
        
        await self.log_event(
            event_type=event_type,
            action=action,
            user_id=user_id,
            guild_id=guild_id,
            resource_id=resource_id,
            details={
                "permission": permission,
                **(details or {})
            }
        )
    
    async def log_resource_event(
        self,
        event_type: AuditEventType,
        action: str,
        user_id: str,
        guild_id: str,
        resource_id: str,
        resource_type: str,
        old_data: Optional[Dict[str, Any]] = None,
        new_data: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log resource management events.
        
        Args:
            event_type: Type of event
            action: Action description
            user_id: User who performed the action
            guild_id: Guild ID
            resource_id: Resource ID
            resource_type: Type of resource
            old_data: Previous resource data
            new_data: New resource data
            details: Additional details
        """
        event_details = details or {}
        
        if old_data:
            event_details["old_data"] = old_data
        
        if new_data:
            event_details["new_data"] = new_data
        
        await self.log_event(
            event_type=event_type,
            action=action,
            user_id=user_id,
            guild_id=guild_id,
            resource_id=resource_id,
            resource_type=resource_type,
            details=event_details
        )
    
    async def log_security_event(
        self,
        event_type: AuditEventType,
        action: str,
        user_id: Optional[str] = None,
        guild_id: Optional[str] = None,
        severity: str = "medium",
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> None:
        """
        Log security-related events.
        
        Args:
            event_type: Type of security event
            action: Action description
            user_id: User ID if applicable
            guild_id: Guild ID if applicable
            severity: Severity level (low, medium, high, critical)
            details: Additional details
            ip_address: IP address
        """
        event_details = {
            "severity": severity,
            **(details or {})
        }
        
        await self.log_event(
            event_type=event_type,
            action=action,
            user_id=user_id,
            guild_id=guild_id,
            details=event_details,
            ip_address=ip_address
        )
        
        # Also log to application logs with appropriate level
        log_level = {
            "low": self.logger.debug,
            "medium": self.logger.info,
            "high": self.logger.warning,
            "critical": self.logger.error
        }.get(severity, self.logger.info)
        
        log_level(
            "Security event",
            event_type=event_type.value,
            action=action,
            severity=severity,
            user_id=user_id,
            guild_id=guild_id
        )
    
    async def get_audit_logs(
        self,
        guild_id: Optional[str] = None,
        user_id: Optional[str] = None,
        event_type: Optional[AuditEventType] = None,
        resource_id: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit logs with filtering.
        
        Args:
            guild_id: Filter by guild ID
            user_id: Filter by user ID
            event_type: Filter by event type
            resource_id: Filter by resource ID
            start_time: Filter by start timestamp
            end_time: Filter by end timestamp
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of audit log entries
        """
        query = {}
        
        if guild_id:
            query["guild_id"] = guild_id
        
        if user_id:
            query["user_id"] = user_id
        
        if event_type:
            query["event_type"] = event_type.value
        
        if resource_id:
            query["resource_id"] = resource_id
        
        if start_time or end_time:
            timestamp_query = {}
            if start_time:
                timestamp_query["$gte"] = start_time
            if end_time:
                timestamp_query["$lte"] = end_time
            query["timestamp"] = timestamp_query
        
        try:
            results = await self.database.find_documents(
                self._audit_collection,
                query,
                sort=[("timestamp", -1)],
                limit=limit,
                skip=offset
            )
            
            return results
            
        except Exception as e:
            self.logger.error(
                "Failed to retrieve audit logs",
                error=str(e),
                query=query
            )
            return []
    
    async def get_user_activity(
        self,
        user_id: str,
        guild_id: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get user activity summary.
        
        Args:
            user_id: User ID
            guild_id: Optional guild ID filter
            days: Number of days to look back
            
        Returns:
            Dictionary with user activity statistics
        """
        start_time = time.time() - (days * 24 * 60 * 60)
        
        query = {
            "user_id": user_id,
            "timestamp": {"$gte": start_time}
        }
        
        if guild_id:
            query["guild_id"] = guild_id
        
        try:
            logs = await self.database.find_documents(
                self._audit_collection,
                query,
                sort=[("timestamp", -1)]
            )
            
            # Aggregate statistics
            event_counts = {}
            total_events = len(logs)
            
            for log in logs:
                event_type = log.get("event_type", "unknown")
                event_counts[event_type] = event_counts.get(event_type, 0) + 1
            
            return {
                "user_id": user_id,
                "guild_id": guild_id,
                "period_days": days,
                "total_events": total_events,
                "event_counts": event_counts,
                "recent_events": logs[:10]  # Last 10 events
            }
            
        except Exception as e:
            self.logger.error(
                "Failed to get user activity",
                user_id=user_id,
                guild_id=guild_id,
                error=str(e)
            )
            return {
                "user_id": user_id,
                "guild_id": guild_id,
                "error": str(e)
            }
    
    async def cleanup_old_logs(self, days_to_keep: int = 90) -> int:
        """
        Clean up old audit logs.
        
        Args:
            days_to_keep: Number of days of logs to keep
            
        Returns:
            Number of logs deleted
        """
        cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
        
        try:
            result = await self.database.delete_documents(
                self._audit_collection,
                {"timestamp": {"$lt": cutoff_time}}
            )
            
            deleted_count = result.get("deleted_count", 0)
            
            self.logger.info(
                "Cleaned up old audit logs",
                deleted_count=deleted_count,
                days_to_keep=days_to_keep
            )
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(
                "Failed to cleanup old audit logs",
                error=str(e)
            )
            return 0