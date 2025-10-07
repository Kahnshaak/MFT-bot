"""
Data retention policy management system.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

try:
    from utils.logging_config import get_logger, LoggerMixin
    from database.manager import DatabaseManager
    from core.audit_logger import AuditLogger, AuditEventType
except ImportError:
    from src.utils.logging_config import get_logger, LoggerMixin
    from src.database.manager import DatabaseManager
    from src.core.audit_logger import AuditLogger, AuditEventType


class RetentionPolicyType(Enum):
    """Types of data retention policies."""
    TIME_BASED = "time_based"
    COUNT_BASED = "count_based"
    CONDITION_BASED = "condition_based"


class RetentionAction(Enum):
    """Actions to take when retention policy is triggered."""
    DELETE = "delete"
    ANONYMIZE = "anonymize"
    ARCHIVE = "archive"


@dataclass
class RetentionPolicy:
    """Data retention policy configuration."""
    
    policy_id: str
    name: str
    description: str
    collection: str
    policy_type: RetentionPolicyType
    action: RetentionAction
    
    # Time-based policy settings
    retention_days: Optional[int] = None
    date_field: Optional[str] = None
    
    # Count-based policy settings
    max_records: Optional[int] = None
    sort_field: Optional[str] = None
    sort_order: int = -1  # -1 for descending, 1 for ascending
    
    # Condition-based policy settings
    conditions: Optional[Dict[str, Any]] = None
    
    # Policy metadata
    is_active: bool = True
    created_at: datetime = None
    updated_at: datetime = None
    last_executed: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        data = asdict(self)
        # Convert enums to strings
        data['policy_type'] = self.policy_type.value
        data['action'] = self.action.value
        # Convert datetime objects to ISO strings
        for field in ['created_at', 'updated_at', 'last_executed']:
            if data[field]:
                data[field] = data[field].isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RetentionPolicy':
        """Create from dictionary."""
        # Convert string enums back to enum objects
        data['policy_type'] = RetentionPolicyType(data['policy_type'])
        data['action'] = RetentionAction(data['action'])
        
        # Convert ISO strings back to datetime objects
        for field in ['created_at', 'updated_at', 'last_executed']:
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field])
        
        return cls(**data)


class DataRetentionManager(LoggerMixin):
    """
    Data retention policy management system.
    
    Manages and executes data retention policies to ensure compliance
    with privacy regulations and organizational data governance.
    """
    
    def __init__(self, database: DatabaseManager, audit_logger: AuditLogger):
        self.database = database
        self.audit_logger = audit_logger
        self.policies_collection = "data_retention_policies"
        
        # Default policies for GDPR compliance
        self.default_policies = [
            RetentionPolicy(
                policy_id="events_completed",
                name="Completed Events Retention",
                description="Delete completed events after 1 year",
                collection="events",
                policy_type=RetentionPolicyType.TIME_BASED,
                action=RetentionAction.DELETE,
                retention_days=365,
                date_field="updated_at",
                conditions={"state": "COMPLETED"}
            ),
            RetentionPolicy(
                policy_id="events_cancelled",
                name="Cancelled Events Retention", 
                description="Delete cancelled events after 3 months",
                collection="events",
                policy_type=RetentionPolicyType.TIME_BASED,
                action=RetentionAction.DELETE,
                retention_days=90,
                date_field="updated_at",
                conditions={"state": "CANCELLED"}
            ),
            RetentionPolicy(
                policy_id="notifications_processed",
                name="Processed Notifications Retention",
                description="Delete processed notifications after 30 days",
                collection="notifications",
                policy_type=RetentionPolicyType.TIME_BASED,
                action=RetentionAction.DELETE,
                retention_days=30,
                date_field="created_at",
                conditions={"processed": True}
            ),
            RetentionPolicy(
                policy_id="inactive_users",
                name="Inactive Users Retention",
                description="Anonymize users inactive for 2 years",
                collection="users",
                policy_type=RetentionPolicyType.TIME_BASED,
                action=RetentionAction.ANONYMIZE,
                retention_days=730,
                date_field="statistics.last_active"
            ),
            RetentionPolicy(
                policy_id="audit_logs_old",
                name="Old Audit Logs Retention",
                description="Delete audit logs older than 7 years (legal requirement)",
                collection="audit_logs",
                policy_type=RetentionPolicyType.TIME_BASED,
                action=RetentionAction.DELETE,
                retention_days=2555,  # 7 years
                date_field="timestamp"
            ),
            RetentionPolicy(
                policy_id="export_requests_expired",
                name="Expired Export Requests",
                description="Delete expired data export requests and files",
                collection="data_export_requests",
                policy_type=RetentionPolicyType.CONDITION_BASED,
                action=RetentionAction.DELETE,
                conditions={
                    "expires_at": {"$lt": "NOW"},
                    "status": "completed"
                }
            )
        ]
    
    async def initialize_default_policies(self) -> None:
        """Initialize default retention policies if they don't exist."""
        try:
            for policy in self.default_policies:
                existing = await self.database.find_one(
                    self.policies_collection,
                    {"policy_id": policy.policy_id}
                )
                
                if not existing:
                    await self.database.insert_one(
                        self.policies_collection,
                        policy.to_dict()
                    )
                    
                    self.logger.info(
                        "Created default retention policy",
                        policy_id=policy.policy_id,
                        name=policy.name
                    )
            
            self.logger.info("Default retention policies initialized")
            
        except Exception as e:
            self.logger.error(
                "Failed to initialize default retention policies",
                error=str(e)
            )
    
    async def create_policy(self, policy: RetentionPolicy) -> bool:
        """
        Create a new retention policy.
        
        Args:
            policy: Retention policy to create
            
        Returns:
            True if policy was created successfully
        """
        try:
            # Check if policy ID already exists
            existing = await self.database.find_one(
                self.policies_collection,
                {"policy_id": policy.policy_id}
            )
            
            if existing:
                raise ValueError(f"Policy with ID '{policy.policy_id}' already exists")
            
            # Validate policy
            self._validate_policy(policy)
            
            # Store policy
            await self.database.insert_one(
                self.policies_collection,
                policy.to_dict()
            )
            
            # Log creation
            await self.audit_logger.log_event(
                event_type=AuditEventType.BOT_CONFIG_CHANGED,
                action=f"Retention policy created: {policy.name}",
                resource_id=policy.policy_id,
                details={
                    "policy_type": policy.policy_type.value,
                    "action": policy.action.value,
                    "collection": policy.collection
                }
            )
            
            self.logger.info(
                "Retention policy created",
                policy_id=policy.policy_id,
                name=policy.name
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to create retention policy",
                policy_id=policy.policy_id,
                error=str(e)
            )
            return False
    
    async def update_policy(self, policy_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update an existing retention policy.
        
        Args:
            policy_id: ID of policy to update
            updates: Fields to update
            
        Returns:
            True if policy was updated successfully
        """
        try:
            # Get existing policy
            existing = await self.database.find_one(
                self.policies_collection,
                {"policy_id": policy_id}
            )
            
            if not existing:
                raise ValueError(f"Policy with ID '{policy_id}' not found")
            
            # Update timestamp
            updates["updated_at"] = datetime.utcnow().isoformat()
            
            # Update policy
            result = await self.database.update_one(
                self.policies_collection,
                {"policy_id": policy_id},
                {"$set": updates}
            )
            
            if result:
                # Log update
                await self.audit_logger.log_event(
                    event_type=AuditEventType.BOT_CONFIG_CHANGED,
                    action=f"Retention policy updated: {policy_id}",
                    resource_id=policy_id,
                    details={"updated_fields": list(updates.keys())}
                )
                
                self.logger.info(
                    "Retention policy updated",
                    policy_id=policy_id,
                    updated_fields=list(updates.keys())
                )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "Failed to update retention policy",
                policy_id=policy_id,
                error=str(e)
            )
            return False
    
    async def delete_policy(self, policy_id: str) -> bool:
        """
        Delete a retention policy.
        
        Args:
            policy_id: ID of policy to delete
            
        Returns:
            True if policy was deleted successfully
        """
        try:
            # Get existing policy for logging
            existing = await self.database.find_one(
                self.policies_collection,
                {"policy_id": policy_id}
            )
            
            if not existing:
                return False
            
            # Delete policy
            result = await self.database.delete_one(
                self.policies_collection,
                {"policy_id": policy_id}
            )
            
            if result:
                # Log deletion
                await self.audit_logger.log_event(
                    event_type=AuditEventType.BOT_CONFIG_CHANGED,
                    action=f"Retention policy deleted: {existing.get('name', policy_id)}",
                    resource_id=policy_id,
                    details={"policy_name": existing.get("name")}
                )
                
                self.logger.info(
                    "Retention policy deleted",
                    policy_id=policy_id,
                    name=existing.get("name")
                )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "Failed to delete retention policy",
                policy_id=policy_id,
                error=str(e)
            )
            return False
    
    async def get_policy(self, policy_id: str) -> Optional[RetentionPolicy]:
        """
        Get a retention policy by ID.
        
        Args:
            policy_id: Policy ID
            
        Returns:
            RetentionPolicy object or None if not found
        """
        try:
            policy_data = await self.database.find_one(
                self.policies_collection,
                {"policy_id": policy_id}
            )
            
            if policy_data:
                policy_data.pop("_id", None)
                return RetentionPolicy.from_dict(policy_data)
            
            return None
            
        except Exception as e:
            self.logger.error(
                "Failed to get retention policy",
                policy_id=policy_id,
                error=str(e)
            )
            return None
    
    async def list_policies(self, active_only: bool = True) -> List[RetentionPolicy]:
        """
        List all retention policies.
        
        Args:
            active_only: Only return active policies
            
        Returns:
            List of RetentionPolicy objects
        """
        try:
            query = {}
            if active_only:
                query["is_active"] = True
            
            policies_data = await self.database.find_many(
                self.policies_collection,
                query,
                sort=[("created_at", 1)]
            )
            
            policies = []
            for policy_data in policies_data:
                policy_data.pop("_id", None)
                policies.append(RetentionPolicy.from_dict(policy_data))
            
            return policies
            
        except Exception as e:
            self.logger.error(
                "Failed to list retention policies",
                error=str(e)
            )
            return []
    
    async def execute_policy(self, policy_id: str) -> Dict[str, Any]:
        """
        Execute a specific retention policy.
        
        Args:
            policy_id: ID of policy to execute
            
        Returns:
            Dictionary with execution results
        """
        try:
            policy = await self.get_policy(policy_id)
            if not policy:
                raise ValueError(f"Policy '{policy_id}' not found")
            
            if not policy.is_active:
                raise ValueError(f"Policy '{policy_id}' is not active")
            
            self.logger.info(
                "Executing retention policy",
                policy_id=policy_id,
                name=policy.name
            )
            
            # Execute based on policy type
            if policy.policy_type == RetentionPolicyType.TIME_BASED:
                result = await self._execute_time_based_policy(policy)
            elif policy.policy_type == RetentionPolicyType.COUNT_BASED:
                result = await self._execute_count_based_policy(policy)
            elif policy.policy_type == RetentionPolicyType.CONDITION_BASED:
                result = await self._execute_condition_based_policy(policy)
            else:
                raise ValueError(f"Unknown policy type: {policy.policy_type}")
            
            # Update last executed timestamp
            await self.database.update_one(
                self.policies_collection,
                {"policy_id": policy_id},
                {"$set": {"last_executed": datetime.utcnow().isoformat()}}
            )
            
            # Log execution
            await self.audit_logger.log_event(
                event_type=AuditEventType.BOT_CONFIG_CHANGED,
                action=f"Retention policy executed: {policy.name}",
                resource_id=policy_id,
                details={
                    "records_affected": result.get("records_affected", 0),
                    "action": policy.action.value
                }
            )
            
            self.logger.info(
                "Retention policy executed",
                policy_id=policy_id,
                records_affected=result.get("records_affected", 0)
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "Failed to execute retention policy",
                policy_id=policy_id,
                error=str(e)
            )
            return {"error": str(e), "records_affected": 0}
    
    async def execute_all_policies(self) -> Dict[str, Any]:
        """
        Execute all active retention policies.
        
        Returns:
            Dictionary with execution results for all policies
        """
        try:
            policies = await self.list_policies(active_only=True)
            
            results = {
                "executed_at": datetime.utcnow().isoformat(),
                "policies_executed": 0,
                "total_records_affected": 0,
                "policy_results": {},
                "errors": []
            }
            
            for policy in policies:
                try:
                    policy_result = await self.execute_policy(policy.policy_id)
                    
                    results["policy_results"][policy.policy_id] = policy_result
                    results["policies_executed"] += 1
                    results["total_records_affected"] += policy_result.get("records_affected", 0)
                    
                    if "error" in policy_result:
                        results["errors"].append({
                            "policy_id": policy.policy_id,
                            "error": policy_result["error"]
                        })
                
                except Exception as e:
                    error_msg = f"Policy {policy.policy_id} failed: {str(e)}"
                    results["errors"].append({
                        "policy_id": policy.policy_id,
                        "error": str(e)
                    })
                    self.logger.error(error_msg)
            
            self.logger.info(
                "All retention policies executed",
                policies_executed=results["policies_executed"],
                total_records_affected=results["total_records_affected"],
                errors_count=len(results["errors"])
            )
            
            return results
            
        except Exception as e:
            self.logger.error(
                "Failed to execute all retention policies",
                error=str(e)
            )
            return {
                "error": str(e),
                "executed_at": datetime.utcnow().isoformat(),
                "policies_executed": 0,
                "total_records_affected": 0
            }
    
    def _validate_policy(self, policy: RetentionPolicy) -> None:
        """Validate retention policy configuration."""
        if policy.policy_type == RetentionPolicyType.TIME_BASED:
            if not policy.retention_days or policy.retention_days <= 0:
                raise ValueError("Time-based policy requires positive retention_days")
            if not policy.date_field:
                raise ValueError("Time-based policy requires date_field")
        
        elif policy.policy_type == RetentionPolicyType.COUNT_BASED:
            if not policy.max_records or policy.max_records <= 0:
                raise ValueError("Count-based policy requires positive max_records")
            if not policy.sort_field:
                raise ValueError("Count-based policy requires sort_field")
        
        elif policy.policy_type == RetentionPolicyType.CONDITION_BASED:
            if not policy.conditions:
                raise ValueError("Condition-based policy requires conditions")
    
    async def _execute_time_based_policy(self, policy: RetentionPolicy) -> Dict[str, Any]:
        """Execute time-based retention policy."""
        cutoff_date = datetime.utcnow() - timedelta(days=policy.retention_days)
        
        # Build query
        query = {policy.date_field: {"$lt": cutoff_date.isoformat()}}
        
        # Add additional conditions if specified
        if policy.conditions:
            query.update(policy.conditions)
        
        # Find records to process
        records = await self.database.find_many(policy.collection, query)
        
        records_affected = 0
        
        for record in records:
            if policy.action == RetentionAction.DELETE:
                await self.database.delete_one(
                    policy.collection,
                    {"_id": record["_id"]}
                )
                records_affected += 1
            
            elif policy.action == RetentionAction.ANONYMIZE:
                # Anonymize record (implementation depends on collection)
                anonymized_data = await self._anonymize_record(policy.collection, record)
                if anonymized_data:
                    await self.database.update_one(
                        policy.collection,
                        {"_id": record["_id"]},
                        {"$set": anonymized_data}
                    )
                    records_affected += 1
        
        return {"records_affected": records_affected}
    
    async def _execute_count_based_policy(self, policy: RetentionPolicy) -> Dict[str, Any]:
        """Execute count-based retention policy."""
        # Count total records
        total_count = await self.database.count_documents(policy.collection, {})
        
        if total_count <= policy.max_records:
            return {"records_affected": 0}
        
        # Find excess records
        records_to_remove = total_count - policy.max_records
        
        # Get records to process (oldest/newest based on sort order)
        records = await self.database.find_many(
            policy.collection,
            {},
            sort=[(policy.sort_field, policy.sort_order)],
            limit=records_to_remove
        )
        
        records_affected = 0
        
        for record in records:
            if policy.action == RetentionAction.DELETE:
                await self.database.delete_one(
                    policy.collection,
                    {"_id": record["_id"]}
                )
                records_affected += 1
        
        return {"records_affected": records_affected}
    
    async def _execute_condition_based_policy(self, policy: RetentionPolicy) -> Dict[str, Any]:
        """Execute condition-based retention policy."""
        # Process special conditions like "NOW"
        query = {}
        for key, value in policy.conditions.items():
            if isinstance(value, dict) and "$lt" in value and value["$lt"] == "NOW":
                query[key] = {"$lt": datetime.utcnow().isoformat()}
            else:
                query[key] = value
        
        # Find records to process
        records = await self.database.find_many(policy.collection, query)
        
        records_affected = 0
        
        for record in records:
            if policy.action == RetentionAction.DELETE:
                await self.database.delete_one(
                    policy.collection,
                    {"_id": record["_id"]}
                )
                records_affected += 1
        
        return {"records_affected": records_affected}
    
    async def _anonymize_record(self, collection: str, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Anonymize a record based on collection type."""
        anonymized_data = {
            "anonymized_at": datetime.utcnow().isoformat()
        }
        
        if collection == "users":
            anonymized_data.update({
                "user_id": "anonymous_user",
                "display_name": "Anonymous User",
                "profile_public": False,
                "stats_public": False
            })
        
        elif collection == "events":
            anonymized_data.update({
                "creator_id": "anonymous_user"
            })
        
        elif collection == "audit_logs":
            anonymized_data.update({
                "user_id": "anonymous_user",
                "ip_address": None,
                "user_agent": None
            })
        
        return anonymized_data if anonymized_data else None