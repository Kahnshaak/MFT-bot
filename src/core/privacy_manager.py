"""
Privacy and compliance manager for GDPR and data protection requirements.
"""

import asyncio
import json
import zipfile
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import secrets

try:
    from utils.logging_config import get_logger, LoggerMixin
    from utils.exceptions import GameNightBotException, ValidationError
    from database.manager import DatabaseManager
    from core.audit_logger import AuditLogger, AuditEventType
    from models.user import User
    from models.event import Event
    from models.guild import GuildConfig
except ImportError:
    from src.utils.logging_config import get_logger, LoggerMixin
    from src.utils.exceptions import GameNightBotException, ValidationError
    from src.database.manager import DatabaseManager
    from src.core.audit_logger import AuditLogger, AuditEventType
    from src.models.user import User
    from src.models.event import Event
    from src.models.guild import GuildConfig


class DataRetentionPeriod(Enum):
    """Data retention periods for different data types."""
    EVENTS_COMPLETED = 365  # 1 year
    EVENTS_CANCELLED = 90   # 3 months
    USER_INACTIVE = 730     # 2 years
    AUDIT_LOGS = 2555       # 7 years (legal requirement)
    NOTIFICATIONS = 30      # 1 month
    ANALYTICS_DATA = 1095   # 3 years


class ConsentType(Enum):
    """Types of user consent."""
    DATA_COLLECTION = "data_collection"
    ANALYTICS = "analytics"
    NOTIFICATIONS = "notifications"
    PROFILE_VISIBILITY = "profile_visibility"
    DATA_SHARING = "data_sharing"


class DataExportFormat(Enum):
    """Supported data export formats."""
    JSON = "json"
    CSV = "csv"
    ZIP = "zip"


@dataclass
class ConsentRecord:
    """Record of user consent."""
    user_id: str
    guild_id: str
    consent_type: ConsentType
    granted: bool
    timestamp: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "guild_id": self.guild_id,
            "consent_type": self.consent_type.value,
            "granted": self.granted,
            "timestamp": self.timestamp.isoformat(),
            "ip_address": self.ip_address,
            "user_agent": self.user_agent
        }


@dataclass
class DataExportRequest:
    """Data export request record."""
    request_id: str
    user_id: str
    guild_id: str
    requested_at: datetime
    format: DataExportFormat
    status: str  # pending, processing, completed, failed
    completed_at: Optional[datetime] = None
    file_path: Optional[str] = None
    expires_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "guild_id": self.guild_id,
            "requested_at": self.requested_at.isoformat(),
            "format": self.format.value,
            "status": self.status,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "file_path": self.file_path,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }


class PrivacyManager(LoggerMixin):
    """
    Privacy and compliance manager for GDPR and data protection.
    
    Handles:
    - User consent management
    - Data export requests
    - Data deletion (right to be forgotten)
    - Data retention policies
    - Privacy controls
    - Audit trails for data access
    """
    
    def __init__(self, database: DatabaseManager, audit_logger: AuditLogger):
        self.database = database
        self.audit_logger = audit_logger
        self.export_directory = Path("data_exports")
        self.export_directory.mkdir(exist_ok=True)
        
        # Collections
        self.consent_collection = "user_consent"
        self.export_requests_collection = "data_export_requests"
        self.retention_policies_collection = "data_retention_policies"
        
        # Default retention periods (in days)
        self.retention_periods = {
            "events": DataRetentionPeriod.EVENTS_COMPLETED.value,
            "cancelled_events": DataRetentionPeriod.EVENTS_CANCELLED.value,
            "inactive_users": DataRetentionPeriod.USER_INACTIVE.value,
            "audit_logs": DataRetentionPeriod.AUDIT_LOGS.value,
            "notifications": DataRetentionPeriod.NOTIFICATIONS.value,
            "analytics": DataRetentionPeriod.ANALYTICS_DATA.value
        }
    
    # Consent Management
    
    async def record_consent(
        self,
        user_id: str,
        guild_id: str,
        consent_type: ConsentType,
        granted: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> bool:
        """
        Record user consent for data processing.
        
        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
            consent_type: Type of consent
            granted: Whether consent was granted
            ip_address: User's IP address
            user_agent: User's browser/client info
            
        Returns:
            True if consent was recorded successfully
        """
        try:
            consent_record = ConsentRecord(
                user_id=user_id,
                guild_id=guild_id,
                consent_type=consent_type,
                granted=granted,
                timestamp=datetime.utcnow(),
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            # Store consent record
            await self.database.insert_one(
                self.consent_collection,
                consent_record.to_dict()
            )
            
            # Log audit event
            await self.audit_logger.log_event(
                event_type=AuditEventType.USER_PROFILE_UPDATED,
                action=f"Consent {consent_type.value} {'granted' if granted else 'revoked'}",
                user_id=user_id,
                guild_id=guild_id,
                details={
                    "consent_type": consent_type.value,
                    "granted": granted
                },
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            self.logger.info(
                "User consent recorded",
                user_id=user_id,
                guild_id=guild_id,
                consent_type=consent_type.value,
                granted=granted
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to record user consent",
                user_id=user_id,
                guild_id=guild_id,
                consent_type=consent_type.value,
                error=str(e)
            )
            return False
    
    async def get_user_consent(
        self,
        user_id: str,
        guild_id: str,
        consent_type: ConsentType
    ) -> Optional[bool]:
        """
        Get current consent status for a user.
        
        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
            consent_type: Type of consent to check
            
        Returns:
            True if consent granted, False if denied, None if not recorded
        """
        try:
            # Get most recent consent record
            consent_record = await self.database.find_one(
                self.consent_collection,
                {
                    "user_id": user_id,
                    "guild_id": guild_id,
                    "consent_type": consent_type.value
                },
                sort=[("timestamp", -1)]
            )
            
            if consent_record:
                return consent_record["granted"]
            
            return None
            
        except Exception as e:
            self.logger.error(
                "Failed to get user consent",
                user_id=user_id,
                guild_id=guild_id,
                consent_type=consent_type.value,
                error=str(e)
            )
            return None
    
    async def get_all_user_consents(
        self,
        user_id: str,
        guild_id: str
    ) -> Dict[str, bool]:
        """
        Get all consent statuses for a user.
        
        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
            
        Returns:
            Dictionary mapping consent types to granted status
        """
        consents = {}
        
        for consent_type in ConsentType:
            consent_status = await self.get_user_consent(user_id, guild_id, consent_type)
            if consent_status is not None:
                consents[consent_type.value] = consent_status
        
        return consents
    
    async def revoke_all_consents(
        self,
        user_id: str,
        guild_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> bool:
        """
        Revoke all consents for a user.
        
        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
            ip_address: User's IP address
            user_agent: User's browser/client info
            
        Returns:
            True if all consents were revoked successfully
        """
        success = True
        
        for consent_type in ConsentType:
            result = await self.record_consent(
                user_id=user_id,
                guild_id=guild_id,
                consent_type=consent_type,
                granted=False,
                ip_address=ip_address,
                user_agent=user_agent
            )
            if not result:
                success = False
        
        return success
    
    # Data Export (Right to Data Portability)
    
    async def request_data_export(
        self,
        user_id: str,
        guild_id: str,
        format: DataExportFormat = DataExportFormat.JSON
    ) -> str:
        """
        Request data export for a user.
        
        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
            format: Export format
            
        Returns:
            Request ID for tracking
        """
        try:
            request_id = secrets.token_urlsafe(32)
            
            export_request = DataExportRequest(
                request_id=request_id,
                user_id=user_id,
                guild_id=guild_id,
                requested_at=datetime.utcnow(),
                format=format,
                status="pending",
                expires_at=datetime.utcnow() + timedelta(days=30)  # Export expires in 30 days
            )
            
            # Store export request
            await self.database.insert_one(
                self.export_requests_collection,
                export_request.to_dict()
            )
            
            # Log audit event
            await self.audit_logger.log_event(
                event_type=AuditEventType.USER_DATA_EXPORTED,
                action="Data export requested",
                user_id=user_id,
                guild_id=guild_id,
                resource_id=request_id,
                details={
                    "format": format.value,
                    "status": "pending"
                }
            )
            
            # Process export asynchronously
            asyncio.create_task(self._process_data_export(request_id))
            
            self.logger.info(
                "Data export requested",
                user_id=user_id,
                guild_id=guild_id,
                request_id=request_id,
                format=format.value
            )
            
            return request_id
            
        except Exception as e:
            self.logger.error(
                "Failed to request data export",
                user_id=user_id,
                guild_id=guild_id,
                error=str(e)
            )
            raise GameNightBotException(f"Failed to request data export: {str(e)}")
    
    async def _process_data_export(self, request_id: str) -> None:
        """
        Process data export request asynchronously.
        
        Args:
            request_id: Export request ID
        """
        try:
            # Update status to processing
            await self.database.update_one(
                self.export_requests_collection,
                {"request_id": request_id},
                {"$set": {"status": "processing"}}
            )
            
            # Get export request
            request_doc = await self.database.find_one(
                self.export_requests_collection,
                {"request_id": request_id}
            )
            
            if not request_doc:
                raise ValueError(f"Export request {request_id} not found")
            
            user_id = request_doc["user_id"]
            guild_id = request_doc["guild_id"]
            format = DataExportFormat(request_doc["format"])
            
            # Collect all user data
            user_data = await self._collect_user_data(user_id, guild_id)
            
            # Generate export file
            file_path = await self._generate_export_file(request_id, user_data, format)
            
            # Update request with completion info
            await self.database.update_one(
                self.export_requests_collection,
                {"request_id": request_id},
                {
                    "$set": {
                        "status": "completed",
                        "completed_at": datetime.utcnow().isoformat(),
                        "file_path": str(file_path)
                    }
                }
            )
            
            # Log completion
            await self.audit_logger.log_event(
                event_type=AuditEventType.USER_DATA_EXPORTED,
                action="Data export completed",
                user_id=user_id,
                guild_id=guild_id,
                resource_id=request_id,
                details={
                    "format": format.value,
                    "status": "completed",
                    "file_size": file_path.stat().st_size
                }
            )
            
            self.logger.info(
                "Data export completed",
                user_id=user_id,
                guild_id=guild_id,
                request_id=request_id,
                file_path=str(file_path)
            )
            
        except Exception as e:
            # Update status to failed
            await self.database.update_one(
                self.export_requests_collection,
                {"request_id": request_id},
                {"$set": {"status": "failed"}}
            )
            
            self.logger.error(
                "Data export failed",
                request_id=request_id,
                error=str(e)
            )
    
    async def _collect_user_data(self, user_id: str, guild_id: str) -> Dict[str, Any]:
        """
        Collect all data for a user across all collections.
        
        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
            
        Returns:
            Dictionary containing all user data
        """
        user_data = {
            "export_info": {
                "user_id": user_id,
                "guild_id": guild_id,
                "exported_at": datetime.utcnow().isoformat(),
                "export_version": "1.0"
            }
        }
        
        try:
            # User profile data
            user_profile = await self.database.find_one(
                "users",
                {"user_id": user_id, "guild_id": guild_id}
            )
            if user_profile:
                # Remove internal MongoDB fields
                user_profile.pop("_id", None)
                user_data["profile"] = user_profile
            
            # Events created by user
            created_events = await self.database.find_many(
                "events",
                {"creator_id": user_id, "guild_id": guild_id}
            )
            for event in created_events:
                event.pop("_id", None)
            user_data["events_created"] = created_events
            
            # Events user participated in (RSVPs)
            participated_events = await self.database.find_many(
                "events",
                {
                    "guild_id": guild_id,
                    f"rsvp_data.{user_id}": {"$exists": True}
                }
            )
            
            # Extract only user's RSVP data from each event
            user_rsvps = []
            for event in participated_events:
                event.pop("_id", None)
                if "rsvp_data" in event and user_id in event["rsvp_data"]:
                    user_rsvp = {
                        "event_id": event.get("discord_event_id") or "unknown",
                        "event_title": event.get("title"),
                        "event_date": event.get("schedule", {}).get("selected_date"),
                        "rsvp": event["rsvp_data"][user_id],
                        "attendance": event.get("attendance", {}).get(user_id)
                    }
                    user_rsvps.append(user_rsvp)
            
            user_data["event_participation"] = user_rsvps
            
            # Notifications sent to user
            notifications = await self.database.find_many(
                "notifications",
                {"user_id": user_id, "guild_id": guild_id}
            )
            for notification in notifications:
                notification.pop("_id", None)
            user_data["notifications"] = notifications
            
            # Game interests
            game_interests = await self.database.find_many(
                "game_interests",
                {"user_id": user_id, "guild_id": guild_id}
            )
            for interest in game_interests:
                interest.pop("_id", None)
            user_data["game_interests"] = game_interests
            
            # Consent records
            consent_records = await self.database.find_many(
                self.consent_collection,
                {"user_id": user_id, "guild_id": guild_id}
            )
            for consent in consent_records:
                consent.pop("_id", None)
            user_data["consent_history"] = consent_records
            
            # Audit logs involving the user
            audit_logs = await self.audit_logger.get_audit_logs(
                guild_id=guild_id,
                user_id=user_id,
                limit=1000  # Last 1000 audit entries
            )
            user_data["audit_history"] = audit_logs
            
            return user_data
            
        except Exception as e:
            self.logger.error(
                "Failed to collect user data",
                user_id=user_id,
                guild_id=guild_id,
                error=str(e)
            )
            raise
    
    async def _generate_export_file(
        self,
        request_id: str,
        user_data: Dict[str, Any],
        format: DataExportFormat
    ) -> Path:
        """
        Generate export file in requested format.
        
        Args:
            request_id: Export request ID
            user_data: User data to export
            format: Export format
            
        Returns:
            Path to generated file
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        if format == DataExportFormat.JSON:
            file_path = self.export_directory / f"export_{request_id}_{timestamp}.json"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(user_data, f, indent=2, ensure_ascii=False, default=str)
        
        elif format == DataExportFormat.ZIP:
            file_path = self.export_directory / f"export_{request_id}_{timestamp}.zip"
            
            with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Add main data file
                zf.writestr(
                    "user_data.json",
                    json.dumps(user_data, indent=2, ensure_ascii=False, default=str)
                )
                
                # Add README
                readme_content = self._generate_export_readme(user_data)
                zf.writestr("README.txt", readme_content)
        
        else:
            raise ValueError(f"Unsupported export format: {format}")
        
        return file_path
    
    def _generate_export_readme(self, user_data: Dict[str, Any]) -> str:
        """Generate README content for data export."""
        export_info = user_data.get("export_info", {})
        
        return f"""
Data Export README
==================

This archive contains all personal data associated with your Discord account
in the Game Night Bot system.

Export Information:
- User ID: {export_info.get('user_id', 'Unknown')}
- Guild ID: {export_info.get('guild_id', 'Unknown')}
- Exported At: {export_info.get('exported_at', 'Unknown')}
- Export Version: {export_info.get('export_version', '1.0')}

Contents:
- user_data.json: Complete data export in JSON format

Data Categories Included:
- Profile information and preferences
- Events you created
- Events you participated in (RSVPs and attendance)
- Game interests and notifications
- Consent history
- Recent audit log entries

Data Processing Legal Basis:
This data was processed under the legal basis of legitimate interest for
providing game night coordination services, and with your explicit consent
where required by GDPR.

Your Rights:
- Right to rectification: Request correction of inaccurate data
- Right to erasure: Request deletion of your data
- Right to restrict processing: Request limitation of data processing
- Right to data portability: This export fulfills this right
- Right to object: Object to processing of your data

Contact:
If you have questions about this data export or wish to exercise your rights,
please contact the server administrators.

Generated by Game Night Bot Privacy Manager v1.0
        """.strip()
    
    async def get_export_status(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status of data export request.
        
        Args:
            request_id: Export request ID
            
        Returns:
            Export request status or None if not found
        """
        try:
            request_doc = await self.database.find_one(
                self.export_requests_collection,
                {"request_id": request_id}
            )
            
            if request_doc:
                request_doc.pop("_id", None)
                return request_doc
            
            return None
            
        except Exception as e:
            self.logger.error(
                "Failed to get export status",
                request_id=request_id,
                error=str(e)
            )
            return None
    
    async def download_export(self, request_id: str) -> Optional[Path]:
        """
        Get path to export file for download.
        
        Args:
            request_id: Export request ID
            
        Returns:
            Path to export file or None if not available
        """
        try:
            request_doc = await self.database.find_one(
                self.export_requests_collection,
                {"request_id": request_id}
            )
            
            if not request_doc or request_doc["status"] != "completed":
                return None
            
            file_path = Path(request_doc["file_path"])
            
            if file_path.exists():
                # Log download access
                await self.audit_logger.log_event(
                    event_type=AuditEventType.USER_DATA_EXPORTED,
                    action="Data export downloaded",
                    user_id=request_doc["user_id"],
                    guild_id=request_doc["guild_id"],
                    resource_id=request_id,
                    details={"file_path": str(file_path)}
                )
                
                return file_path
            
            return None
            
        except Exception as e:
            self.logger.error(
                "Failed to get export download",
                request_id=request_id,
                error=str(e)
            )
            return None    

    # Data Deletion (Right to be Forgotten)
    
    async def delete_user_data(
        self,
        user_id: str,
        guild_id: str,
        keep_anonymized: bool = True
    ) -> Dict[str, Any]:
        """
        Delete all user data (right to be forgotten).
        
        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
            keep_anonymized: Whether to keep anonymized data for analytics
            
        Returns:
            Dictionary with deletion results
        """
        try:
            deletion_results = {
                "user_id": user_id,
                "guild_id": guild_id,
                "deleted_at": datetime.utcnow().isoformat(),
                "collections_processed": {},
                "anonymized_records": 0,
                "deleted_records": 0
            }
            
            # Delete user profile
            result = await self.database.delete_one(
                "users",
                {"user_id": user_id, "guild_id": guild_id}
            )
            deletion_results["collections_processed"]["users"] = {
                "deleted": 1 if result else 0
            }
            if result:
                deletion_results["deleted_records"] += 1
            
            # Handle events created by user
            created_events = await self.database.find_many(
                "events",
                {"creator_id": user_id, "guild_id": guild_id}
            )
            
            events_deleted = 0
            events_anonymized = 0
            
            for event in created_events:
                if keep_anonymized:
                    # Anonymize event (replace user ID with anonymous identifier)
                    await self.database.update_one(
                        "events",
                        {"_id": event["_id"]},
                        {
                            "$set": {
                                "creator_id": "anonymous_user",
                                "anonymized_at": datetime.utcnow().isoformat()
                            }
                        }
                    )
                    events_anonymized += 1
                else:
                    # Delete event entirely
                    await self.database.delete_one(
                        "events",
                        {"_id": event["_id"]}
                    )
                    events_deleted += 1
            
            deletion_results["collections_processed"]["events"] = {
                "deleted": events_deleted,
                "anonymized": events_anonymized
            }
            deletion_results["deleted_records"] += events_deleted
            deletion_results["anonymized_records"] += events_anonymized
            
            # Remove user from RSVP data in other events
            events_with_rsvp = await self.database.find_many(
                "events",
                {
                    "guild_id": guild_id,
                    f"rsvp_data.{user_id}": {"$exists": True}
                }
            )
            
            rsvp_removed = 0
            for event in events_with_rsvp:
                await self.database.update_one(
                    "events",
                    {"_id": event["_id"]},
                    {
                        "$unset": {
                            f"rsvp_data.{user_id}": "",
                            f"attendance.{user_id}": ""
                        }
                    }
                )
                rsvp_removed += 1
            
            deletion_results["collections_processed"]["event_rsvps"] = {
                "removed": rsvp_removed
            }
            
            # Delete notifications
            result = await self.database.delete_many(
                "notifications",
                {"user_id": user_id, "guild_id": guild_id}
            )
            notifications_deleted = result.get("deleted_count", 0)
            deletion_results["collections_processed"]["notifications"] = {
                "deleted": notifications_deleted
            }
            deletion_results["deleted_records"] += notifications_deleted
            
            # Delete game interests
            result = await self.database.delete_many(
                "game_interests",
                {"user_id": user_id, "guild_id": guild_id}
            )
            interests_deleted = result.get("deleted_count", 0)
            deletion_results["collections_processed"]["game_interests"] = {
                "deleted": interests_deleted
            }
            deletion_results["deleted_records"] += interests_deleted
            
            # Delete consent records (keep for legal compliance)
            # Note: We may need to keep consent records for legal reasons
            # but mark them as deleted user
            await self.database.update_many(
                self.consent_collection,
                {"user_id": user_id, "guild_id": guild_id},
                {
                    "$set": {
                        "user_deleted": True,
                        "deleted_at": datetime.utcnow().isoformat()
                    }
                }
            )
            
            # Anonymize audit logs (keep for security but remove PII)
            if keep_anonymized:
                await self.database.update_many(
                    "audit_logs",
                    {"user_id": user_id, "guild_id": guild_id},
                    {
                        "$set": {
                            "user_id": "anonymous_user",
                            "anonymized_at": datetime.utcnow().isoformat()
                        }
                    }
                )
            
            # Delete export requests
            result = await self.database.delete_many(
                self.export_requests_collection,
                {"user_id": user_id, "guild_id": guild_id}
            )
            exports_deleted = result.get("deleted_count", 0)
            deletion_results["collections_processed"]["export_requests"] = {
                "deleted": exports_deleted
            }
            deletion_results["deleted_records"] += exports_deleted
            
            # Log the deletion
            await self.audit_logger.log_event(
                event_type=AuditEventType.USER_DATA_EXPORTED,  # Using closest available type
                action="User data deleted (Right to be Forgotten)",
                user_id=user_id,
                guild_id=guild_id,
                details={
                    "keep_anonymized": keep_anonymized,
                    "deletion_results": deletion_results
                }
            )
            
            self.logger.info(
                "User data deleted",
                user_id=user_id,
                guild_id=guild_id,
                deleted_records=deletion_results["deleted_records"],
                anonymized_records=deletion_results["anonymized_records"]
            )
            
            return deletion_results
            
        except Exception as e:
            self.logger.error(
                "Failed to delete user data",
                user_id=user_id,
                guild_id=guild_id,
                error=str(e)
            )
            raise GameNightBotException(f"Failed to delete user data: {str(e)}")
    
    # Data Retention Policies
    
    async def apply_retention_policies(self) -> Dict[str, Any]:
        """
        Apply data retention policies to clean up old data.
        
        Returns:
            Dictionary with cleanup results
        """
        try:
            cleanup_results = {
                "started_at": datetime.utcnow().isoformat(),
                "policies_applied": {},
                "total_deleted": 0,
                "errors": []
            }
            
            # Clean up completed events
            cutoff_date = datetime.utcnow() - timedelta(days=self.retention_periods["events"])
            result = await self._cleanup_old_events("COMPLETED", cutoff_date)
            cleanup_results["policies_applied"]["completed_events"] = result
            cleanup_results["total_deleted"] += result.get("deleted", 0)
            
            # Clean up cancelled events
            cutoff_date = datetime.utcnow() - timedelta(days=self.retention_periods["cancelled_events"])
            result = await self._cleanup_old_events("CANCELLED", cutoff_date)
            cleanup_results["policies_applied"]["cancelled_events"] = result
            cleanup_results["total_deleted"] += result.get("deleted", 0)
            
            # Clean up old notifications
            cutoff_date = datetime.utcnow() - timedelta(days=self.retention_periods["notifications"])
            result = await self._cleanup_old_notifications(cutoff_date)
            cleanup_results["policies_applied"]["notifications"] = result
            cleanup_results["total_deleted"] += result.get("deleted", 0)
            
            # Clean up inactive users
            cutoff_date = datetime.utcnow() - timedelta(days=self.retention_periods["inactive_users"])
            result = await self._cleanup_inactive_users(cutoff_date)
            cleanup_results["policies_applied"]["inactive_users"] = result
            cleanup_results["total_deleted"] += result.get("deleted", 0)
            
            # Clean up old audit logs
            cutoff_date = datetime.utcnow() - timedelta(days=self.retention_periods["audit_logs"])
            result = await self.audit_logger.cleanup_old_logs(self.retention_periods["audit_logs"])
            cleanup_results["policies_applied"]["audit_logs"] = {"deleted": result}
            cleanup_results["total_deleted"] += result
            
            # Clean up expired export files
            result = await self._cleanup_expired_exports()
            cleanup_results["policies_applied"]["export_files"] = result
            cleanup_results["total_deleted"] += result.get("deleted", 0)
            
            cleanup_results["completed_at"] = datetime.utcnow().isoformat()
            
            self.logger.info(
                "Data retention policies applied",
                total_deleted=cleanup_results["total_deleted"],
                policies_count=len(cleanup_results["policies_applied"])
            )
            
            return cleanup_results
            
        except Exception as e:
            self.logger.error(
                "Failed to apply retention policies",
                error=str(e)
            )
            return {
                "error": str(e),
                "started_at": datetime.utcnow().isoformat()
            }
    
    async def _cleanup_old_events(self, state: str, cutoff_date: datetime) -> Dict[str, int]:
        """Clean up old events in specified state."""
        try:
            # Find old events
            old_events = await self.database.find_many(
                "events",
                {
                    "state": state,
                    "updated_at": {"$lt": cutoff_date.isoformat()}
                }
            )
            
            deleted_count = 0
            for event in old_events:
                # Delete associated data first
                event_id = str(event.get("_id"))
                
                # Delete notifications for this event
                await self.database.delete_many(
                    "notifications",
                    {"event_id": event_id}
                )
                
                # Delete the event
                await self.database.delete_one(
                    "events",
                    {"_id": event["_id"]}
                )
                
                deleted_count += 1
            
            return {"deleted": deleted_count}
            
        except Exception as e:
            self.logger.error(
                f"Failed to cleanup old {state} events",
                error=str(e)
            )
            return {"deleted": 0, "error": str(e)}
    
    async def _cleanup_old_notifications(self, cutoff_date: datetime) -> Dict[str, int]:
        """Clean up old notifications."""
        try:
            result = await self.database.delete_many(
                "notifications",
                {
                    "created_at": {"$lt": cutoff_date.isoformat()},
                    "processed": True
                }
            )
            
            return {"deleted": result.get("deleted_count", 0)}
            
        except Exception as e:
            self.logger.error(
                "Failed to cleanup old notifications",
                error=str(e)
            )
            return {"deleted": 0, "error": str(e)}
    
    async def _cleanup_inactive_users(self, cutoff_date: datetime) -> Dict[str, int]:
        """Clean up inactive users."""
        try:
            # Find users who haven't been active
            inactive_users = await self.database.find_many(
                "users",
                {
                    "statistics.last_active": {"$lt": cutoff_date.isoformat()}
                }
            )
            
            deleted_count = 0
            for user in inactive_users:
                # Check if user has any recent activity in events
                recent_events = await self.database.count_documents(
                    "events",
                    {
                        "$or": [
                            {"creator_id": user["user_id"]},
                            {f"rsvp_data.{user['user_id']}": {"$exists": True}}
                        ],
                        "created_at": {"$gte": cutoff_date.isoformat()}
                    }
                )
                
                # Only delete if no recent activity
                if recent_events == 0:
                    await self.delete_user_data(
                        user["user_id"],
                        user["guild_id"],
                        keep_anonymized=True
                    )
                    deleted_count += 1
            
            return {"deleted": deleted_count}
            
        except Exception as e:
            self.logger.error(
                "Failed to cleanup inactive users",
                error=str(e)
            )
            return {"deleted": 0, "error": str(e)}
    
    async def _cleanup_expired_exports(self) -> Dict[str, int]:
        """Clean up expired export files."""
        try:
            # Find expired export requests
            expired_exports = await self.database.find_many(
                self.export_requests_collection,
                {
                    "expires_at": {"$lt": datetime.utcnow().isoformat()},
                    "status": "completed"
                }
            )
            
            deleted_files = 0
            deleted_records = 0
            
            for export in expired_exports:
                # Delete file if it exists
                if export.get("file_path"):
                    file_path = Path(export["file_path"])
                    if file_path.exists():
                        file_path.unlink()
                        deleted_files += 1
                
                # Delete database record
                await self.database.delete_one(
                    self.export_requests_collection,
                    {"_id": export["_id"]}
                )
                deleted_records += 1
            
            return {
                "deleted": deleted_records,
                "files_deleted": deleted_files
            }
            
        except Exception as e:
            self.logger.error(
                "Failed to cleanup expired exports",
                error=str(e)
            )
            return {"deleted": 0, "error": str(e)}
    
    # Privacy Controls
    
    async def update_privacy_settings(
        self,
        user_id: str,
        guild_id: str,
        settings: Dict[str, bool]
    ) -> bool:
        """
        Update user privacy settings.
        
        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
            settings: Privacy settings to update
            
        Returns:
            True if settings were updated successfully
        """
        try:
            # Validate settings
            valid_settings = {
                "profile_public",
                "stats_public",
                "allow_game_pings",
                "allow_event_notifications",
                "allow_analytics_tracking"
            }
            
            update_data = {}
            for key, value in settings.items():
                if key in valid_settings:
                    update_data[key] = value
            
            if not update_data:
                return False
            
            # Update user privacy settings
            result = await self.database.update_one(
                "users",
                {"user_id": user_id, "guild_id": guild_id},
                {"$set": update_data}
            )
            
            if result:
                # Log privacy settings change
                await self.audit_logger.log_event(
                    event_type=AuditEventType.USER_PROFILE_UPDATED,
                    action="Privacy settings updated",
                    user_id=user_id,
                    guild_id=guild_id,
                    details={"updated_settings": update_data}
                )
                
                self.logger.info(
                    "Privacy settings updated",
                    user_id=user_id,
                    guild_id=guild_id,
                    settings=update_data
                )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "Failed to update privacy settings",
                user_id=user_id,
                guild_id=guild_id,
                error=str(e)
            )
            return False
    
    async def get_privacy_settings(
        self,
        user_id: str,
        guild_id: str
    ) -> Dict[str, bool]:
        """
        Get user privacy settings.
        
        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
            
        Returns:
            Dictionary of privacy settings
        """
        try:
            user = await self.database.find_one(
                "users",
                {"user_id": user_id, "guild_id": guild_id}
            )
            
            if not user:
                # Return default privacy settings
                return {
                    "profile_public": True,
                    "stats_public": True,
                    "allow_game_pings": True,
                    "allow_event_notifications": True,
                    "allow_analytics_tracking": True
                }
            
            return {
                "profile_public": user.get("profile_public", True),
                "stats_public": user.get("stats_public", True),
                "allow_game_pings": user.get("allow_game_pings", True),
                "allow_event_notifications": user.get("allow_event_notifications", True),
                "allow_analytics_tracking": user.get("allow_analytics_tracking", True)
            }
            
        except Exception as e:
            self.logger.error(
                "Failed to get privacy settings",
                user_id=user_id,
                guild_id=guild_id,
                error=str(e)
            )
            return {}
    
    # Backup and Recovery
    
    async def create_privacy_backup(self, guild_id: str) -> Dict[str, Any]:
        """
        Create backup of privacy-related data for a guild.
        
        Args:
            guild_id: Discord guild ID
            
        Returns:
            Backup information
        """
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_id = f"privacy_backup_{guild_id}_{timestamp}"
            
            # Create backup directory
            backup_dir = Path("backups") / backup_id
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            backup_info = {
                "backup_id": backup_id,
                "guild_id": guild_id,
                "created_at": datetime.utcnow().isoformat(),
                "collections": {},
                "file_count": 0,
                "total_size": 0
            }
            
            # Backup collections with privacy data
            collections_to_backup = [
                self.consent_collection,
                self.export_requests_collection,
                "users",  # Privacy settings
                "audit_logs"  # Privacy-related audit logs
            ]
            
            for collection in collections_to_backup:
                if collection == "audit_logs":
                    # Only backup privacy-related audit logs
                    data = await self.database.find_many(
                        collection,
                        {
                            "guild_id": guild_id,
                            "event_type": {
                                "$in": [
                                    "user_profile_updated",
                                    "user_data_exported",
                                    "permission_granted",
                                    "permission_denied"
                                ]
                            }
                        }
                    )
                else:
                    data = await self.database.find_many(
                        collection,
                        {"guild_id": guild_id}
                    )
                
                # Remove MongoDB ObjectIds
                for item in data:
                    item.pop("_id", None)
                
                # Save to file
                file_path = backup_dir / f"{collection}.json"
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)
                
                backup_info["collections"][collection] = {
                    "record_count": len(data),
                    "file_size": file_path.stat().st_size
                }
                backup_info["file_count"] += 1
                backup_info["total_size"] += file_path.stat().st_size
            
            # Create backup metadata file
            metadata_path = backup_dir / "backup_metadata.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(backup_info, f, indent=2, ensure_ascii=False)
            
            # Log backup creation
            await self.audit_logger.log_event(
                event_type=AuditEventType.BACKUP_CREATED,
                action="Privacy data backup created",
                guild_id=guild_id,
                resource_id=backup_id,
                details={
                    "backup_size": backup_info["total_size"],
                    "collections": list(backup_info["collections"].keys())
                }
            )
            
            self.logger.info(
                "Privacy backup created",
                backup_id=backup_id,
                guild_id=guild_id,
                total_size=backup_info["total_size"]
            )
            
            return backup_info
            
        except Exception as e:
            self.logger.error(
                "Failed to create privacy backup",
                guild_id=guild_id,
                error=str(e)
            )
            raise GameNightBotException(f"Failed to create privacy backup: {str(e)}")
    
    # Compliance Reporting
    
    async def generate_compliance_report(self, guild_id: str) -> Dict[str, Any]:
        """
        Generate compliance report for a guild.
        
        Args:
            guild_id: Discord guild ID
            
        Returns:
            Compliance report
        """
        try:
            report = {
                "guild_id": guild_id,
                "generated_at": datetime.utcnow().isoformat(),
                "report_version": "1.0",
                "data_summary": {},
                "consent_summary": {},
                "retention_status": {},
                "privacy_controls": {},
                "recent_requests": {}
            }
            
            # Data summary
            report["data_summary"] = {
                "total_users": await self.database.count_documents(
                    "users", {"guild_id": guild_id}
                ),
                "total_events": await self.database.count_documents(
                    "events", {"guild_id": guild_id}
                ),
                "total_notifications": await self.database.count_documents(
                    "notifications", {"guild_id": guild_id}
                ),
                "total_audit_logs": await self.database.count_documents(
                    "audit_logs", {"guild_id": guild_id}
                )
            }
            
            # Consent summary
            consent_stats = {}
            for consent_type in ConsentType:
                granted_count = await self.database.count_documents(
                    self.consent_collection,
                    {
                        "guild_id": guild_id,
                        "consent_type": consent_type.value,
                        "granted": True
                    }
                )
                denied_count = await self.database.count_documents(
                    self.consent_collection,
                    {
                        "guild_id": guild_id,
                        "consent_type": consent_type.value,
                        "granted": False
                    }
                )
                consent_stats[consent_type.value] = {
                    "granted": granted_count,
                    "denied": denied_count
                }
            
            report["consent_summary"] = consent_stats
            
            # Retention status
            now = datetime.utcnow()
            report["retention_status"] = {
                "events_due_for_cleanup": await self.database.count_documents(
                    "events",
                    {
                        "guild_id": guild_id,
                        "state": {"$in": ["COMPLETED", "CANCELLED"]},
                        "updated_at": {
                            "$lt": (now - timedelta(days=self.retention_periods["events"])).isoformat()
                        }
                    }
                ),
                "notifications_due_for_cleanup": await self.database.count_documents(
                    "notifications",
                    {
                        "guild_id": guild_id,
                        "processed": True,
                        "created_at": {
                            "$lt": (now - timedelta(days=self.retention_periods["notifications"])).isoformat()
                        }
                    }
                ),
                "inactive_users": await self.database.count_documents(
                    "users",
                    {
                        "guild_id": guild_id,
                        "statistics.last_active": {
                            "$lt": (now - timedelta(days=self.retention_periods["inactive_users"])).isoformat()
                        }
                    }
                )
            }
            
            # Recent data requests (last 30 days)
            thirty_days_ago = now - timedelta(days=30)
            report["recent_requests"] = {
                "data_exports": await self.database.count_documents(
                    self.export_requests_collection,
                    {
                        "guild_id": guild_id,
                        "requested_at": {"$gte": thirty_days_ago.isoformat()}
                    }
                ),
                "deletion_requests": await self.database.count_documents(
                    "audit_logs",
                    {
                        "guild_id": guild_id,
                        "action": {"$regex": "deleted.*Right to be Forgotten"},
                        "timestamp": {"$gte": thirty_days_ago.timestamp()}
                    }
                )
            }
            
            return report
            
        except Exception as e:
            self.logger.error(
                "Failed to generate compliance report",
                guild_id=guild_id,
                error=str(e)
            )
            raise GameNightBotException(f"Failed to generate compliance report: {str(e)}")