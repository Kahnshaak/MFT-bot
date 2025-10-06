"""
Data consistency checker with automated repair procedures.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum

from database.manager import DatabaseManager
from core.event_bus import EventBus, EventType, Event
from utils.logging_config import get_logger, LoggerMixin
from utils.exceptions import GameNightBotException


class ConsistencyIssueType(str, Enum):
    """Types of consistency issues that can be detected."""
    MISSING_REQUIRED_FIELDS = "MISSING_REQUIRED_FIELDS"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    ORPHANED_REFERENCES = "ORPHANED_REFERENCES"
    DUPLICATE_ENTRIES = "DUPLICATE_ENTRIES"
    DATA_TYPE_MISMATCH = "DATA_TYPE_MISMATCH"
    CONSTRAINT_VIOLATION = "CONSTRAINT_VIOLATION"
    CORRUPTED_RELATIONSHIPS = "CORRUPTED_RELATIONSHIPS"
    INCONSISTENT_TIMESTAMPS = "INCONSISTENT_TIMESTAMPS"


class SeverityLevel(str, Enum):
    """Severity levels for consistency issues."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class ConsistencyIssue:
    """Represents a data consistency issue."""
    issue_type: ConsistencyIssueType
    severity: SeverityLevel
    collection: str
    document_id: Optional[str]
    field_path: Optional[str]
    description: str
    details: Dict[str, Any]
    auto_repairable: bool = False
    repair_function: Optional[str] = None
    detected_at: float = None
    
    def __post_init__(self):
        if self.detected_at is None:
            import time
            self.detected_at = time.time()


class DataConsistencyChecker(LoggerMixin):
    """
    Comprehensive data consistency checker with automated repair capabilities.
    """
    
    def __init__(self, database: DatabaseManager, event_bus: EventBus):
        self.database = database
        self.event_bus = event_bus
        self._consistency_rules: Dict[str, List[Callable]] = {}
        self._repair_functions: Dict[str, Callable] = {}
        self._check_history: List[Dict[str, Any]] = []
        
        # Register default consistency rules
        self._register_default_rules()
        
        # Register default repair functions
        self._register_default_repairs()
    
    def _register_default_rules(self) -> None:
        """Register default consistency checking rules."""
        # Events collection rules
        self.register_consistency_rule("events", self._check_event_required_fields)
        self.register_consistency_rule("events", self._check_event_state_consistency)
        self.register_consistency_rule("events", self._check_event_poll_consistency)
        self.register_consistency_rule("events", self._check_event_timestamps)
        self.register_consistency_rule("events", self._check_event_rsvp_consistency)
        
        # Users collection rules
        self.register_consistency_rule("users", self._check_user_required_fields)
        self.register_consistency_rule("users", self._check_user_duplicates)
        self.register_consistency_rule("users", self._check_user_game_interests)
        
        # Notifications collection rules
        self.register_consistency_rule("notifications", self._check_notification_references)
        self.register_consistency_rule("notifications", self._check_notification_timestamps)
        
        # Recurring schedules rules
        self.register_consistency_rule("recurring_schedules", self._check_recurring_schedule_consistency)
        
        # Cross-collection rules
        self.register_consistency_rule("cross_collection", self._check_orphaned_references)
        self.register_consistency_rule("cross_collection", self._check_referential_integrity)
    
    def _register_default_repairs(self) -> None:
        """Register default repair functions."""
        self._repair_functions.update({
            "repair_missing_fields": self._repair_missing_fields,
            "repair_invalid_state": self._repair_invalid_state,
            "repair_orphaned_references": self._repair_orphaned_references,
            "repair_duplicate_entries": self._repair_duplicate_entries,
            "repair_corrupted_polls": self._repair_corrupted_polls,
            "repair_inconsistent_timestamps": self._repair_inconsistent_timestamps,
            "repair_broken_relationships": self._repair_broken_relationships
        })
    
    def register_consistency_rule(self, collection: str, rule_function: Callable) -> None:
        """
        Register a consistency checking rule for a collection.
        
        Args:
            collection: Collection name or 'cross_collection' for cross-collection rules
            rule_function: Function that checks consistency and returns issues
        """
        if collection not in self._consistency_rules:
            self._consistency_rules[collection] = []
        
        self._consistency_rules[collection].append(rule_function)
        
        self.logger.debug(
            "Registered consistency rule",
            collection=collection,
            rule_function=rule_function.__name__
        )
    
    def register_repair_function(self, name: str, repair_function: Callable) -> None:
        """
        Register a repair function.
        
        Args:
            name: Name of the repair function
            repair_function: Function that performs the repair
        """
        self._repair_functions[name] = repair_function
        
        self.logger.debug(
            "Registered repair function",
            name=name
        )
    
    async def run_full_consistency_check(self) -> List[ConsistencyIssue]:
        """
        Run a full consistency check across all collections.
        
        Returns:
            List of consistency issues found
        """
        self.logger.info("Starting full consistency check")
        start_time = datetime.now()
        
        all_issues = []
        
        # Run collection-specific checks
        for collection, rules in self._consistency_rules.items():
            if collection == "cross_collection":
                continue  # Handle these separately
            
            collection_issues = await self._check_collection_consistency(collection, rules)
            all_issues.extend(collection_issues)
        
        # Run cross-collection checks
        if "cross_collection" in self._consistency_rules:
            cross_issues = await self._run_cross_collection_checks()
            all_issues.extend(cross_issues)
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # Record check history
        check_result = {
            "timestamp": start_time.timestamp(),
            "duration_seconds": duration,
            "total_issues": len(all_issues),
            "issues_by_type": self._categorize_issues(all_issues),
            "issues_by_severity": self._categorize_by_severity(all_issues)
        }
        
        self._check_history.append(check_result)
        
        # Keep only last 100 check results
        if len(self._check_history) > 100:
            self._check_history = self._check_history[-100:]
        
        self.logger.info(
            "Consistency check completed",
            duration_seconds=duration,
            total_issues=len(all_issues),
            critical_issues=len([i for i in all_issues if i.severity == SeverityLevel.CRITICAL]),
            high_issues=len([i for i in all_issues if i.severity == SeverityLevel.HIGH])
        )
        
        # Emit event with results
        await self.event_bus.emit(
            EventType.ERROR_OCCURRED,
            {
                "type": "consistency_check_completed",
                "total_issues": len(all_issues),
                "critical_issues": len([i for i in all_issues if i.severity == SeverityLevel.CRITICAL]),
                "check_duration": duration
            }
        )
        
        return all_issues
    
    async def run_collection_check(self, collection: str) -> List[ConsistencyIssue]:
        """
        Run consistency check for a specific collection.
        
        Args:
            collection: Collection name
            
        Returns:
            List of consistency issues found
        """
        if collection not in self._consistency_rules:
            self.logger.warning(
                "No consistency rules registered for collection",
                collection=collection
            )
            return []
        
        rules = self._consistency_rules[collection]
        return await self._check_collection_consistency(collection, rules)
    
    async def auto_repair_issues(
        self, 
        issues: List[ConsistencyIssue],
        max_repairs: int = 100
    ) -> Dict[str, Any]:
        """
        Automatically repair issues that are marked as auto-repairable.
        
        Args:
            issues: List of consistency issues
            max_repairs: Maximum number of repairs to attempt
            
        Returns:
            Dictionary with repair results
        """
        self.logger.info(
            "Starting automatic repair",
            total_issues=len(issues),
            max_repairs=max_repairs
        )
        
        repairable_issues = [
            issue for issue in issues 
            if issue.auto_repairable and issue.repair_function
        ]
        
        if not repairable_issues:
            self.logger.info("No auto-repairable issues found")
            return {
                "attempted": 0,
                "successful": 0,
                "failed": 0,
                "skipped": len(issues)
            }
        
        # Limit repairs
        if len(repairable_issues) > max_repairs:
            # Prioritize by severity
            repairable_issues.sort(key=lambda x: {
                SeverityLevel.CRITICAL: 4,
                SeverityLevel.HIGH: 3,
                SeverityLevel.MEDIUM: 2,
                SeverityLevel.LOW: 1
            }.get(x.severity, 0), reverse=True)
            
            repairable_issues = repairable_issues[:max_repairs]
        
        attempted = 0
        successful = 0
        failed = 0
        
        for issue in repairable_issues:
            try:
                repair_function = self._repair_functions.get(issue.repair_function)
                if not repair_function:
                    self.logger.warning(
                        "Repair function not found",
                        repair_function=issue.repair_function
                    )
                    failed += 1
                    continue
                
                attempted += 1
                success = await repair_function(issue)
                
                if success:
                    successful += 1
                    self.logger.info(
                        "Issue repaired successfully",
                        issue_type=issue.issue_type.value,
                        collection=issue.collection,
                        document_id=issue.document_id
                    )
                else:
                    failed += 1
                    self.logger.warning(
                        "Issue repair failed",
                        issue_type=issue.issue_type.value,
                        collection=issue.collection,
                        document_id=issue.document_id
                    )
                
            except Exception as e:
                failed += 1
                self.logger.error(
                    "Error during issue repair",
                    issue_type=issue.issue_type.value,
                    collection=issue.collection,
                    document_id=issue.document_id,
                    error=str(e)
                )
        
        result = {
            "attempted": attempted,
            "successful": successful,
            "failed": failed,
            "skipped": len(issues) - len(repairable_issues)
        }
        
        self.logger.info(
            "Automatic repair completed",
            **result
        )
        
        return result
    
    async def get_check_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent consistency check history.
        
        Args:
            limit: Maximum number of results to return
            
        Returns:
            List of check results
        """
        return self._check_history[-limit:] if self._check_history else []
    
    # Private methods
    
    async def _check_collection_consistency(
        self, 
        collection: str, 
        rules: List[Callable]
    ) -> List[ConsistencyIssue]:
        """Check consistency for a specific collection."""
        self.logger.debug(
            "Checking collection consistency",
            collection=collection,
            rule_count=len(rules)
        )
        
        issues = []
        
        for rule in rules:
            try:
                rule_issues = await rule(collection)
                if rule_issues:
                    issues.extend(rule_issues)
            except Exception as e:
                self.logger.error(
                    "Consistency rule failed",
                    collection=collection,
                    rule=rule.__name__,
                    error=str(e)
                )
        
        return issues
    
    async def _run_cross_collection_checks(self) -> List[ConsistencyIssue]:
        """Run cross-collection consistency checks."""
        issues = []
        
        cross_rules = self._consistency_rules.get("cross_collection", [])
        
        for rule in cross_rules:
            try:
                rule_issues = await rule("cross_collection")
                if rule_issues:
                    issues.extend(rule_issues)
            except Exception as e:
                self.logger.error(
                    "Cross-collection consistency rule failed",
                    rule=rule.__name__,
                    error=str(e)
                )
        
        return issues
    
    def _categorize_issues(self, issues: List[ConsistencyIssue]) -> Dict[str, int]:
        """Categorize issues by type."""
        categories = {}
        for issue in issues:
            issue_type = issue.issue_type.value
            categories[issue_type] = categories.get(issue_type, 0) + 1
        return categories
    
    def _categorize_by_severity(self, issues: List[ConsistencyIssue]) -> Dict[str, int]:
        """Categorize issues by severity."""
        severities = {}
        for issue in issues:
            severity = issue.severity.value
            severities[severity] = severities.get(severity, 0) + 1
        return severities
    
    # Default consistency checking rules
    
    async def _check_event_required_fields(self, collection: str) -> List[ConsistencyIssue]:
        """Check for missing required fields in events."""
        issues = []
        
        required_fields = [
            "guild_id", "creator_id", "title", "state", "created_at"
        ]
        
        try:
            # Find events missing required fields
            for field in required_fields:
                missing_docs = await self.database.find_many(
                    collection,
                    {field: {"$exists": False}}
                )
                
                for doc in missing_docs:
                    issues.append(ConsistencyIssue(
                        issue_type=ConsistencyIssueType.MISSING_REQUIRED_FIELDS,
                        severity=SeverityLevel.HIGH,
                        collection=collection,
                        document_id=str(doc.get("_id")),
                        field_path=field,
                        description=f"Missing required field: {field}",
                        details={"missing_field": field, "document": doc},
                        auto_repairable=True,
                        repair_function="repair_missing_fields"
                    ))
        
        except Exception as e:
            self.logger.error(
                "Error checking event required fields",
                error=str(e)
            )
        
        return issues
    
    async def _check_event_state_consistency(self, collection: str) -> List[ConsistencyIssue]:
        """Check event state consistency."""
        issues = []
        
        valid_states = ["DRAFT", "DATE_POLLING", "TIME_POLLING", "GAME_POLLING", "SCHEDULED", "COMPLETED", "CANCELLED"]
        
        try:
            # Find events with invalid states
            invalid_state_docs = await self.database.find_many(
                collection,
                {"state": {"$nin": valid_states}}
            )
            
            for doc in invalid_state_docs:
                issues.append(ConsistencyIssue(
                    issue_type=ConsistencyIssueType.INVALID_STATE_TRANSITION,
                    severity=SeverityLevel.HIGH,
                    collection=collection,
                    document_id=str(doc.get("_id")),
                    field_path="state",
                    description=f"Invalid event state: {doc.get('state')}",
                    details={"invalid_state": doc.get("state"), "document": doc},
                    auto_repairable=True,
                    repair_function="repair_invalid_state"
                ))
            
            # Check state-poll consistency
            events = await self.database.find_many(
                collection,
                {"state": {"$in": ["DATE_POLLING", "TIME_POLLING", "GAME_POLLING"]}}
            )
            
            for event in events:
                state = event.get("state")
                polls = event.get("polls", {})
                
                # Check if state matches poll existence
                if state == "DATE_POLLING" and "date_poll" not in polls:
                    issues.append(ConsistencyIssue(
                        issue_type=ConsistencyIssueType.INVALID_STATE_TRANSITION,
                        severity=SeverityLevel.MEDIUM,
                        collection=collection,
                        document_id=str(event.get("_id")),
                        field_path="state",
                        description="Event in DATE_POLLING state but no date poll exists",
                        details={"state": state, "polls": list(polls.keys())},
                        auto_repairable=True,
                        repair_function="repair_invalid_state"
                    ))
        
        except Exception as e:
            self.logger.error(
                "Error checking event state consistency",
                error=str(e)
            )
        
        return issues
    
    async def _check_event_poll_consistency(self, collection: str) -> List[ConsistencyIssue]:
        """Check poll data consistency within events."""
        issues = []
        
        try:
            events_with_polls = await self.database.find_many(
                collection,
                {"polls": {"$exists": True, "$ne": {}}}
            )
            
            for event in events_with_polls:
                event_id = str(event.get("_id"))
                polls = event.get("polls", {})
                
                for poll_type, poll_data in polls.items():
                    # Check poll structure
                    if not isinstance(poll_data, dict):
                        issues.append(ConsistencyIssue(
                            issue_type=ConsistencyIssueType.DATA_TYPE_MISMATCH,
                            severity=SeverityLevel.HIGH,
                            collection=collection,
                            document_id=event_id,
                            field_path=f"polls.{poll_type}",
                            description=f"Poll data is not a dictionary: {poll_type}",
                            details={"poll_type": poll_type, "poll_data": poll_data},
                            auto_repairable=True,
                            repair_function="repair_corrupted_polls"
                        ))
                        continue
                    
                    # Check required poll fields
                    required_poll_fields = ["title", "options", "is_active"]
                    for field in required_poll_fields:
                        if field not in poll_data:
                            issues.append(ConsistencyIssue(
                                issue_type=ConsistencyIssueType.MISSING_REQUIRED_FIELDS,
                                severity=SeverityLevel.MEDIUM,
                                collection=collection,
                                document_id=event_id,
                                field_path=f"polls.{poll_type}.{field}",
                                description=f"Missing poll field: {field}",
                                details={"poll_type": poll_type, "missing_field": field},
                                auto_repairable=True,
                                repair_function="repair_missing_fields"
                            ))
                    
                    # Check poll options
                    options = poll_data.get("options", [])
                    if not isinstance(options, list):
                        issues.append(ConsistencyIssue(
                            issue_type=ConsistencyIssueType.DATA_TYPE_MISMATCH,
                            severity=SeverityLevel.MEDIUM,
                            collection=collection,
                            document_id=event_id,
                            field_path=f"polls.{poll_type}.options",
                            description="Poll options is not a list",
                            details={"poll_type": poll_type, "options": options},
                            auto_repairable=True,
                            repair_function="repair_corrupted_polls"
                        ))
                    else:
                        # Check option structure
                        for i, option in enumerate(options):
                            if not isinstance(option, dict):
                                issues.append(ConsistencyIssue(
                                    issue_type=ConsistencyIssueType.DATA_TYPE_MISMATCH,
                                    severity=SeverityLevel.MEDIUM,
                                    collection=collection,
                                    document_id=event_id,
                                    field_path=f"polls.{poll_type}.options.{i}",
                                    description=f"Poll option {i} is not a dictionary",
                                    details={"poll_type": poll_type, "option_index": i, "option": option},
                                    auto_repairable=True,
                                    repair_function="repair_corrupted_polls"
                                ))
                                continue
                            
                            # Check vote count consistency
                            votes = option.get("votes", [])
                            vote_count = option.get("vote_count", 0)
                            
                            if len(votes) != vote_count:
                                issues.append(ConsistencyIssue(
                                    issue_type=ConsistencyIssueType.CONSTRAINT_VIOLATION,
                                    severity=SeverityLevel.LOW,
                                    collection=collection,
                                    document_id=event_id,
                                    field_path=f"polls.{poll_type}.options.{i}.vote_count",
                                    description="Vote count doesn't match votes array length",
                                    details={
                                        "poll_type": poll_type,
                                        "option_index": i,
                                        "votes_length": len(votes),
                                        "vote_count": vote_count
                                    },
                                    auto_repairable=True,
                                    repair_function="repair_corrupted_polls"
                                ))
        
        except Exception as e:
            self.logger.error(
                "Error checking event poll consistency",
                error=str(e)
            )
        
        return issues
    
    async def _check_event_timestamps(self, collection: str) -> List[ConsistencyIssue]:
        """Check timestamp consistency in events."""
        issues = []
        
        try:
            events = await self.database.find_many(
                collection,
                {"created_at": {"$exists": True}}
            )
            
            for event in events:
                event_id = str(event.get("_id"))
                created_at = event.get("created_at")
                updated_at = event.get("updated_at")
                
                # Check if updated_at is before created_at
                if updated_at and created_at and updated_at < created_at:
                    issues.append(ConsistencyIssue(
                        issue_type=ConsistencyIssueType.INCONSISTENT_TIMESTAMPS,
                        severity=SeverityLevel.MEDIUM,
                        collection=collection,
                        document_id=event_id,
                        field_path="updated_at",
                        description="updated_at is before created_at",
                        details={
                            "created_at": created_at,
                            "updated_at": updated_at
                        },
                        auto_repairable=True,
                        repair_function="repair_inconsistent_timestamps"
                    ))
        
        except Exception as e:
            self.logger.error(
                "Error checking event timestamps",
                error=str(e)
            )
        
        return issues
    
    async def _check_event_rsvp_consistency(self, collection: str) -> List[ConsistencyIssue]:
        """Check RSVP data consistency."""
        issues = []
        
        try:
            events_with_rsvp = await self.database.find_many(
                collection,
                {"rsvp_data": {"$exists": True, "$ne": {}}}
            )
            
            for event in events_with_rsvp:
                event_id = str(event.get("_id"))
                rsvp_data = event.get("rsvp_data", {})
                
                # Check RSVP structure
                for user_id, rsvp_status in rsvp_data.items():
                    if rsvp_status not in ["YES", "NO", "MAYBE"]:
                        issues.append(ConsistencyIssue(
                            issue_type=ConsistencyIssueType.CONSTRAINT_VIOLATION,
                            severity=SeverityLevel.MEDIUM,
                            collection=collection,
                            document_id=event_id,
                            field_path=f"rsvp_data.{user_id}",
                            description=f"Invalid RSVP status: {rsvp_status}",
                            details={
                                "user_id": user_id,
                                "invalid_status": rsvp_status
                            },
                            auto_repairable=True,
                            repair_function="repair_broken_relationships"
                        ))
        
        except Exception as e:
            self.logger.error(
                "Error checking event RSVP consistency",
                error=str(e)
            )
        
        return issues    

    async def _check_user_required_fields(self, collection: str) -> List[ConsistencyIssue]:
        """Check for missing required fields in users."""
        issues = []
        
        required_fields = ["user_id", "guild_id"]
        
        try:
            for field in required_fields:
                missing_docs = await self.database.find_many(
                    collection,
                    {field: {"$exists": False}}
                )
                
                for doc in missing_docs:
                    issues.append(ConsistencyIssue(
                        issue_type=ConsistencyIssueType.MISSING_REQUIRED_FIELDS,
                        severity=SeverityLevel.HIGH,
                        collection=collection,
                        document_id=str(doc.get("_id")),
                        field_path=field,
                        description=f"Missing required field: {field}",
                        details={"missing_field": field, "document": doc},
                        auto_repairable=True,
                        repair_function="repair_missing_fields"
                    ))
        
        except Exception as e:
            self.logger.error(
                "Error checking user required fields",
                error=str(e)
            )
        
        return issues
    
    async def _check_user_duplicates(self, collection: str) -> List[ConsistencyIssue]:
        """Check for duplicate user entries."""
        issues = []
        
        try:
            # Find duplicates based on user_id + guild_id combination
            pipeline = [
                {
                    "$group": {
                        "_id": {"user_id": "$user_id", "guild_id": "$guild_id"},
                        "count": {"$sum": 1},
                        "docs": {"$push": "$$ROOT"}
                    }
                },
                {"$match": {"count": {"$gt": 1}}}
            ]
            
            duplicates = await self.database.aggregate(collection, pipeline)
            
            for duplicate_group in duplicates:
                docs = duplicate_group["docs"]
                user_id = duplicate_group["_id"]["user_id"]
                guild_id = duplicate_group["_id"]["guild_id"]
                
                # Keep the most recent document, mark others as duplicates
                docs.sort(key=lambda x: x.get("created_at", datetime.min), reverse=True)
                
                for doc in docs[1:]:  # Skip the first (most recent) document
                    issues.append(ConsistencyIssue(
                        issue_type=ConsistencyIssueType.DUPLICATE_ENTRIES,
                        severity=SeverityLevel.MEDIUM,
                        collection=collection,
                        document_id=str(doc.get("_id")),
                        field_path=None,
                        description=f"Duplicate user entry for {user_id} in guild {guild_id}",
                        details={
                            "user_id": user_id,
                            "guild_id": guild_id,
                            "duplicate_count": len(docs)
                        },
                        auto_repairable=True,
                        repair_function="repair_duplicate_entries"
                    ))
        
        except Exception as e:
            self.logger.error(
                "Error checking user duplicates",
                error=str(e)
            )
        
        return issues
    
    async def _check_user_game_interests(self, collection: str) -> List[ConsistencyIssue]:
        """Check user game interests consistency."""
        issues = []
        
        try:
            users_with_interests = await self.database.find_many(
                collection,
                {"game_interests": {"$exists": True}}
            )
            
            for user in users_with_interests:
                user_id = str(user.get("_id"))
                game_interests = user.get("game_interests", [])
                
                # Check if game_interests is a list
                if not isinstance(game_interests, list):
                    issues.append(ConsistencyIssue(
                        issue_type=ConsistencyIssueType.DATA_TYPE_MISMATCH,
                        severity=SeverityLevel.MEDIUM,
                        collection=collection,
                        document_id=user_id,
                        field_path="game_interests",
                        description="game_interests is not a list",
                        details={"game_interests": game_interests},
                        auto_repairable=True,
                        repair_function="repair_missing_fields"
                    ))
                else:
                    # Check for duplicate interests
                    if len(game_interests) != len(set(game_interests)):
                        issues.append(ConsistencyIssue(
                            issue_type=ConsistencyIssueType.DUPLICATE_ENTRIES,
                            severity=SeverityLevel.LOW,
                            collection=collection,
                            document_id=user_id,
                            field_path="game_interests",
                            description="Duplicate game interests",
                            details={"game_interests": game_interests},
                            auto_repairable=True,
                            repair_function="repair_duplicate_entries"
                        ))
        
        except Exception as e:
            self.logger.error(
                "Error checking user game interests",
                error=str(e)
            )
        
        return issues
    
    async def _check_notification_references(self, collection: str) -> List[ConsistencyIssue]:
        """Check notification references to events and users."""
        issues = []
        
        try:
            notifications = await self.database.find_many(collection, {})
            
            for notification in notifications:
                notification_id = str(notification.get("_id"))
                event_id = notification.get("event_id")
                user_id = notification.get("user_id")
                guild_id = notification.get("guild_id")
                
                # Check if referenced event exists
                if event_id:
                    event_exists = await self.database.find_one("events", {"_id": event_id})
                    if not event_exists:
                        issues.append(ConsistencyIssue(
                            issue_type=ConsistencyIssueType.ORPHANED_REFERENCES,
                            severity=SeverityLevel.MEDIUM,
                            collection=collection,
                            document_id=notification_id,
                            field_path="event_id",
                            description=f"Notification references non-existent event: {event_id}",
                            details={"event_id": event_id},
                            auto_repairable=True,
                            repair_function="repair_orphaned_references"
                        ))
                
                # Check if referenced user exists (in the same guild)
                if user_id and guild_id:
                    user_exists = await self.database.find_one(
                        "users", 
                        {"user_id": user_id, "guild_id": guild_id}
                    )
                    if not user_exists:
                        issues.append(ConsistencyIssue(
                            issue_type=ConsistencyIssueType.ORPHANED_REFERENCES,
                            severity=SeverityLevel.LOW,
                            collection=collection,
                            document_id=notification_id,
                            field_path="user_id",
                            description=f"Notification references non-existent user: {user_id}",
                            details={"user_id": user_id, "guild_id": guild_id},
                            auto_repairable=True,
                            repair_function="repair_orphaned_references"
                        ))
        
        except Exception as e:
            self.logger.error(
                "Error checking notification references",
                error=str(e)
            )
        
        return issues
    
    async def _check_notification_timestamps(self, collection: str) -> List[ConsistencyIssue]:
        """Check notification timestamp consistency."""
        issues = []
        
        try:
            notifications = await self.database.find_many(
                collection,
                {"scheduled_for": {"$exists": True}}
            )
            
            for notification in notifications:
                notification_id = str(notification.get("_id"))
                scheduled_for = notification.get("scheduled_for")
                created_at = notification.get("created_at")
                
                # Check if scheduled_for is before created_at
                if created_at and scheduled_for and scheduled_for < created_at:
                    issues.append(ConsistencyIssue(
                        issue_type=ConsistencyIssueType.INCONSISTENT_TIMESTAMPS,
                        severity=SeverityLevel.LOW,
                        collection=collection,
                        document_id=notification_id,
                        field_path="scheduled_for",
                        description="scheduled_for is before created_at",
                        details={
                            "created_at": created_at,
                            "scheduled_for": scheduled_for
                        },
                        auto_repairable=True,
                        repair_function="repair_inconsistent_timestamps"
                    ))
        
        except Exception as e:
            self.logger.error(
                "Error checking notification timestamps",
                error=str(e)
            )
        
        return issues
    
    async def _check_recurring_schedule_consistency(self, collection: str) -> List[ConsistencyIssue]:
        """Check recurring schedule consistency."""
        issues = []
        
        try:
            schedules = await self.database.find_many(collection, {})
            
            for schedule in schedules:
                schedule_id = str(schedule.get("_id"))
                schedule_data = schedule.get("schedule", {})
                status = schedule.get("status", {})
                
                # Check required schedule fields
                required_schedule_fields = ["trigger_type", "trigger_day"]
                for field in required_schedule_fields:
                    if field not in schedule_data:
                        issues.append(ConsistencyIssue(
                            issue_type=ConsistencyIssueType.MISSING_REQUIRED_FIELDS,
                            severity=SeverityLevel.MEDIUM,
                            collection=collection,
                            document_id=schedule_id,
                            field_path=f"schedule.{field}",
                            description=f"Missing schedule field: {field}",
                            details={"missing_field": field},
                            auto_repairable=True,
                            repair_function="repair_missing_fields"
                        ))
                
                # Check trigger_type validity
                trigger_type = schedule_data.get("trigger_type")
                if trigger_type and trigger_type not in ["MONTHLY", "WEEKLY"]:
                    issues.append(ConsistencyIssue(
                        issue_type=ConsistencyIssueType.CONSTRAINT_VIOLATION,
                        severity=SeverityLevel.MEDIUM,
                        collection=collection,
                        document_id=schedule_id,
                        field_path="schedule.trigger_type",
                        description=f"Invalid trigger_type: {trigger_type}",
                        details={"invalid_trigger_type": trigger_type},
                        auto_repairable=True,
                        repair_function="repair_invalid_state"
                    ))
                
                # Check if active schedule has next_trigger
                is_active = status.get("is_active", False)
                next_trigger = status.get("next_trigger")
                
                if is_active and not next_trigger:
                    issues.append(ConsistencyIssue(
                        issue_type=ConsistencyIssueType.MISSING_REQUIRED_FIELDS,
                        severity=SeverityLevel.HIGH,
                        collection=collection,
                        document_id=schedule_id,
                        field_path="status.next_trigger",
                        description="Active schedule missing next_trigger",
                        details={"is_active": is_active},
                        auto_repairable=True,
                        repair_function="repair_missing_fields"
                    ))
        
        except Exception as e:
            self.logger.error(
                "Error checking recurring schedule consistency",
                error=str(e)
            )
        
        return issues
    
    async def _check_orphaned_references(self, collection: str) -> List[ConsistencyIssue]:
        """Check for orphaned references across collections."""
        issues = []
        
        try:
            # Check events referencing non-existent users
            events = await self.database.find_many("events", {})
            
            for event in events:
                event_id = str(event.get("_id"))
                creator_id = event.get("creator_id")
                guild_id = event.get("guild_id")
                
                # Check if creator exists
                if creator_id and guild_id:
                    creator_exists = await self.database.find_one(
                        "users",
                        {"user_id": creator_id, "guild_id": guild_id}
                    )
                    
                    if not creator_exists:
                        issues.append(ConsistencyIssue(
                            issue_type=ConsistencyIssueType.ORPHANED_REFERENCES,
                            severity=SeverityLevel.MEDIUM,
                            collection="events",
                            document_id=event_id,
                            field_path="creator_id",
                            description=f"Event references non-existent creator: {creator_id}",
                            details={"creator_id": creator_id, "guild_id": guild_id},
                            auto_repairable=False,  # Requires manual intervention
                            repair_function=None
                        ))
                
                # Check RSVP references
                rsvp_data = event.get("rsvp_data", {})
                for user_id in rsvp_data.keys():
                    user_exists = await self.database.find_one(
                        "users",
                        {"user_id": user_id, "guild_id": guild_id}
                    )
                    
                    if not user_exists:
                        issues.append(ConsistencyIssue(
                            issue_type=ConsistencyIssueType.ORPHANED_REFERENCES,
                            severity=SeverityLevel.LOW,
                            collection="events",
                            document_id=event_id,
                            field_path=f"rsvp_data.{user_id}",
                            description=f"Event RSVP references non-existent user: {user_id}",
                            details={"user_id": user_id, "guild_id": guild_id},
                            auto_repairable=True,
                            repair_function="repair_orphaned_references"
                        ))
        
        except Exception as e:
            self.logger.error(
                "Error checking orphaned references",
                error=str(e)
            )
        
        return issues
    
    async def _check_referential_integrity(self, collection: str) -> List[ConsistencyIssue]:
        """Check referential integrity across collections."""
        issues = []
        
        try:
            # Check if all events have corresponding Discord events when scheduled
            scheduled_events = await self.database.find_many(
                "events",
                {"state": "SCHEDULED", "discord_event_id": {"$exists": True, "$ne": None}}
            )
            
            # This would require Discord API calls to verify, so we'll skip for now
            # In a real implementation, you'd check if the Discord event still exists
            
        except Exception as e:
            self.logger.error(
                "Error checking referential integrity",
                error=str(e)
            )
        
        return issues
    
    # Default repair functions
    
    async def _repair_missing_fields(self, issue: ConsistencyIssue) -> bool:
        """Repair missing required fields."""
        try:
            collection = issue.collection
            document_id = issue.document_id
            missing_field = issue.details.get("missing_field")
            
            if not all([collection, document_id, missing_field]):
                return False
            
            # Define default values for common fields
            default_values = {
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "state": "DRAFT",
                "is_active": True,
                "votes": [],
                "vote_count": 0,
                "options": [],
                "polls": {},
                "rsvp_data": {},
                "attendance": {},
                "game_interests": [],
                "profile": {},
                "notification_preferences": {},
                "status": {"is_active": False}
            }
            
            default_value = default_values.get(missing_field)
            if default_value is None:
                # Try to infer appropriate default
                if missing_field.endswith("_id"):
                    default_value = None
                elif missing_field.endswith("_count"):
                    default_value = 0
                elif missing_field.endswith("_list") or missing_field.endswith("s"):
                    default_value = []
                else:
                    default_value = None
            
            # Apply repair
            await self.database.update_one(
                collection,
                {"_id": document_id},
                {"$set": {missing_field: default_value}}
            )
            
            self.logger.info(
                "Repaired missing field",
                collection=collection,
                document_id=document_id,
                field=missing_field,
                default_value=default_value
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to repair missing field",
                issue_type=issue.issue_type.value,
                error=str(e)
            )
            return False
    
    async def _repair_invalid_state(self, issue: ConsistencyIssue) -> bool:
        """Repair invalid states."""
        try:
            collection = issue.collection
            document_id = issue.document_id
            
            if collection == "events":
                # Get event data to determine correct state
                event_doc = await self.database.find_one(collection, {"_id": document_id})
                if not event_doc:
                    return False
                
                # Determine correct state based on event data
                correct_state = self._determine_correct_event_state(event_doc)
                
                await self.database.update_one(
                    collection,
                    {"_id": document_id},
                    {"$set": {"state": correct_state}}
                )
                
                self.logger.info(
                    "Repaired invalid event state",
                    document_id=document_id,
                    new_state=correct_state
                )
                
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(
                "Failed to repair invalid state",
                issue_type=issue.issue_type.value,
                error=str(e)
            )
            return False
    
    async def _repair_orphaned_references(self, issue: ConsistencyIssue) -> bool:
        """Repair orphaned references."""
        try:
            collection = issue.collection
            document_id = issue.document_id
            field_path = issue.field_path
            
            # Remove the orphaned reference
            if "." in field_path:
                # Handle nested field paths
                parts = field_path.split(".")
                if len(parts) == 2:
                    await self.database.update_one(
                        collection,
                        {"_id": document_id},
                        {"$unset": {field_path: ""}}
                    )
            else:
                # Handle top-level fields
                await self.database.update_one(
                    collection,
                    {"_id": document_id},
                    {"$unset": {field_path: ""}}
                )
            
            self.logger.info(
                "Repaired orphaned reference",
                collection=collection,
                document_id=document_id,
                field_path=field_path
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to repair orphaned reference",
                issue_type=issue.issue_type.value,
                error=str(e)
            )
            return False
    
    async def _repair_duplicate_entries(self, issue: ConsistencyIssue) -> bool:
        """Repair duplicate entries."""
        try:
            collection = issue.collection
            document_id = issue.document_id
            
            # Delete the duplicate document
            await self.database.delete_one(collection, {"_id": document_id})
            
            self.logger.info(
                "Removed duplicate entry",
                collection=collection,
                document_id=document_id
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to repair duplicate entry",
                issue_type=issue.issue_type.value,
                error=str(e)
            )
            return False
    
    async def _repair_corrupted_polls(self, issue: ConsistencyIssue) -> bool:
        """Repair corrupted poll data."""
        try:
            collection = issue.collection
            document_id = issue.document_id
            field_path = issue.field_path
            
            if "vote_count" in field_path:
                # Fix vote count mismatch
                event_doc = await self.database.find_one(collection, {"_id": document_id})
                if not event_doc:
                    return False
                
                # Extract poll type and option index from field path
                path_parts = field_path.split(".")
                poll_type = path_parts[1]
                option_index = int(path_parts[3])
                
                polls = event_doc.get("polls", {})
                poll = polls.get(poll_type, {})
                options = poll.get("options", [])
                
                if option_index < len(options):
                    option = options[option_index]
                    votes = option.get("votes", [])
                    correct_vote_count = len(votes)
                    
                    # Update the vote count
                    await self.database.update_one(
                        collection,
                        {"_id": document_id},
                        {"$set": {f"polls.{poll_type}.options.{option_index}.vote_count": correct_vote_count}}
                    )
                    
                    self.logger.info(
                        "Fixed vote count mismatch",
                        document_id=document_id,
                        poll_type=poll_type,
                        option_index=option_index,
                        correct_count=correct_vote_count
                    )
                    
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(
                "Failed to repair corrupted poll",
                issue_type=issue.issue_type.value,
                error=str(e)
            )
            return False
    
    async def _repair_inconsistent_timestamps(self, issue: ConsistencyIssue) -> bool:
        """Repair inconsistent timestamps."""
        try:
            collection = issue.collection
            document_id = issue.document_id
            field_path = issue.field_path
            
            if field_path == "updated_at":
                # Set updated_at to current time
                await self.database.update_one(
                    collection,
                    {"_id": document_id},
                    {"$set": {"updated_at": datetime.now()}}
                )
            elif field_path == "scheduled_for":
                # Set scheduled_for to a reasonable future time
                future_time = datetime.now() + timedelta(hours=1)
                await self.database.update_one(
                    collection,
                    {"_id": document_id},
                    {"$set": {"scheduled_for": future_time}}
                )
            
            self.logger.info(
                "Repaired inconsistent timestamp",
                collection=collection,
                document_id=document_id,
                field_path=field_path
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to repair inconsistent timestamp",
                issue_type=issue.issue_type.value,
                error=str(e)
            )
            return False
    
    async def _repair_broken_relationships(self, issue: ConsistencyIssue) -> bool:
        """Repair broken relationships."""
        try:
            collection = issue.collection
            document_id = issue.document_id
            field_path = issue.field_path
            
            if "rsvp_data" in field_path:
                # Remove invalid RSVP status
                user_id = field_path.split(".")[-1]
                await self.database.update_one(
                    collection,
                    {"_id": document_id},
                    {"$unset": {field_path: ""}}
                )
                
                self.logger.info(
                    "Removed invalid RSVP status",
                    collection=collection,
                    document_id=document_id,
                    user_id=user_id
                )
                
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(
                "Failed to repair broken relationship",
                issue_type=issue.issue_type.value,
                error=str(e)
            )
            return False
    
    def _determine_correct_event_state(self, event_doc: Dict[str, Any]) -> str:
        """Determine the correct state for an event based on its data."""
        polls = event_doc.get("polls", {})
        
        if "game_poll" in polls and polls["game_poll"].get("winner_option_id"):
            return "SCHEDULED"
        elif "time_poll" in polls and polls["time_poll"].get("winner_option_id"):
            return "GAME_POLLING"
        elif "date_poll" in polls and polls["date_poll"].get("winner_option_id"):
            return "TIME_POLLING"
        elif "date_poll" in polls:
            return "DATE_POLLING"
        else:
            return "DRAFT"