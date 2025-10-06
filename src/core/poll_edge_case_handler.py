"""
Enhanced poll edge case handler for managing complex poll scenarios.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from enum import Enum

from database.manager import DatabaseManager
from core.event_bus import EventBus, EventType
from utils.logging_config import get_logger, LoggerMixin
from utils.exceptions import (
    PollEdgeCaseError, UserDepartedError, PollError,
    ErrorCode, GameNightBotException
)


class EdgeCaseType(str, Enum):
    """Types of poll edge cases."""
    USER_DEPARTED_DURING_POLL = "user_departed_during_poll"
    DUPLICATE_VOTE_ATTEMPT = "duplicate_vote_attempt"
    POLL_EXPIRED_DURING_VOTE = "poll_expired_during_vote"
    INVALID_VOTE_STATE = "invalid_vote_state"
    CONCURRENT_VOTE_CONFLICT = "concurrent_vote_conflict"
    POLL_DATA_CORRUPTION = "poll_data_corruption"
    USER_PERMISSION_CHANGED = "user_permission_changed"
    POLL_OPTION_REMOVED = "poll_option_removed"


class PollEdgeCaseHandler(LoggerMixin):
    """
    Handler for complex poll edge cases and validation scenarios.
    """
    
    def __init__(self, database: DatabaseManager, event_bus: EventBus):
        self.database = database
        self.event_bus = event_bus
        self._active_votes: Dict[str, Set[str]] = {}  # poll_id -> set of user_ids currently voting
        self._vote_locks: Dict[str, asyncio.Lock] = {}  # poll_id -> lock for vote operations
    
    async def handle_user_departure_during_poll(
        self, 
        event_id: str, 
        poll_type: str, 
        departed_user_id: str
    ) -> bool:
        """
        Handle user leaving server during active poll.
        
        Args:
            event_id: Event ID containing the poll
            poll_type: Type of poll (date_poll, time_poll, game_poll)
            departed_user_id: ID of user who left
            
        Returns:
            True if handled successfully
        """
        try:
            self.logger.info(
                "Handling user departure during poll",
                event_id=event_id,
                poll_type=poll_type,
                user_id=departed_user_id
            )
            
            # Get current event data
            event_doc = await self.database.find_one("events", {"_id": event_id})
            if not event_doc:
                self.logger.warning("Event not found for user departure handling", event_id=event_id)
                return False
            
            polls = event_doc.get("polls", {})
            if poll_type not in polls:
                self.logger.warning("Poll not found for user departure handling", poll_type=poll_type)
                return False
            
            poll_data = polls[poll_type]
            
            # Remove user's votes from all options
            votes_removed = 0
            options = poll_data.get("options", [])
            
            for option in options:
                votes = option.get("votes", [])
                if departed_user_id in votes:
                    votes.remove(departed_user_id)
                    option["vote_count"] = len(votes)
                    votes_removed += 1
            
            # Update poll metadata
            poll_data["departed_users"] = poll_data.get("departed_users", [])
            if departed_user_id not in poll_data["departed_users"]:
                poll_data["departed_users"].append(departed_user_id)
            
            # Recalculate total votes
            total_votes = sum(option.get("vote_count", 0) for option in options)
            poll_data["total_votes"] = total_votes
            
            # Update database
            await self.database.update_one(
                "events",
                {"_id": event_id},
                {"$set": {f"polls.{poll_type}": poll_data}}
            )
            
            # Emit event for UI updates
            await self.event_bus.emit(
                EventType.POLL_UPDATED,
                {
                    "event_id": event_id,
                    "poll_type": poll_type,
                    "action": "user_departed",
                    "departed_user_id": departed_user_id,
                    "votes_removed": votes_removed,
                    "new_total_votes": total_votes
                }
            )
            
            self.logger.info(
                "Successfully handled user departure",
                event_id=event_id,
                poll_type=poll_type,
                votes_removed=votes_removed
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to handle user departure during poll",
                event_id=event_id,
                poll_type=poll_type,
                user_id=departed_user_id,
                error=str(e)
            )
            return False
    
    async def validate_vote_attempt(
        self, 
        event_id: str, 
        poll_type: str, 
        user_id: str, 
        option_id: str
    ) -> Dict[str, Any]:
        """
        Validate a vote attempt and handle edge cases.
        
        Args:
            event_id: Event ID
            poll_type: Type of poll
            user_id: User attempting to vote
            option_id: Option being voted for
            
        Returns:
            Dictionary with validation results and any edge case handling
        """
        poll_key = f"{event_id}_{poll_type}"
        
        # Ensure we have a lock for this poll
        if poll_key not in self._vote_locks:
            self._vote_locks[poll_key] = asyncio.Lock()
        
        async with self._vote_locks[poll_key]:
            try:
                # Check if user is currently voting (prevent concurrent votes)
                if poll_key not in self._active_votes:
                    self._active_votes[poll_key] = set()
                
                if user_id in self._active_votes[poll_key]:
                    return {
                        "valid": False,
                        "edge_case": EdgeCaseType.CONCURRENT_VOTE_CONFLICT,
                        "message": "You are already in the process of voting. Please wait."
                    }
                
                # Mark user as actively voting
                self._active_votes[poll_key].add(user_id)
                
                try:
                    # Get current event and poll data
                    event_doc = await self.database.find_one("events", {"_id": event_id})
                    if not event_doc:
                        return {
                            "valid": False,
                            "edge_case": EdgeCaseType.INVALID_VOTE_STATE,
                            "message": "Event not found."
                        }
                    
                    polls = event_doc.get("polls", {})
                    if poll_type not in polls:
                        return {
                            "valid": False,
                            "edge_case": EdgeCaseType.INVALID_VOTE_STATE,
                            "message": "Poll not found."
                        }
                    
                    poll_data = polls[poll_type]
                    
                    # Check if poll is still active
                    if not poll_data.get("is_active", False):
                        return {
                            "valid": False,
                            "edge_case": EdgeCaseType.POLL_EXPIRED_DURING_VOTE,
                            "message": "This poll has expired."
                        }
                    
                    # Check if poll has expired
                    closes_at = poll_data.get("closes_at")
                    if closes_at and datetime.fromisoformat(closes_at) < datetime.now():
                        # Mark poll as inactive
                        await self.database.update_one(
                            "events",
                            {"_id": event_id},
                            {"$set": {f"polls.{poll_type}.is_active": False}}
                        )
                        
                        return {
                            "valid": False,
                            "edge_case": EdgeCaseType.POLL_EXPIRED_DURING_VOTE,
                            "message": "This poll has expired."
                        }
                    
                    # Check if user has already departed
                    departed_users = poll_data.get("departed_users", [])
                    if user_id in departed_users:
                        return {
                            "valid": False,
                            "edge_case": EdgeCaseType.USER_DEPARTED_DURING_POLL,
                            "message": "You are no longer eligible to vote in this poll."
                        }
                    
                    # Validate option exists
                    options = poll_data.get("options", [])
                    option_exists = any(opt.get("id") == option_id for opt in options)
                    
                    if not option_exists:
                        return {
                            "valid": False,
                            "edge_case": EdgeCaseType.POLL_OPTION_REMOVED,
                            "message": "The selected option is no longer available."
                        }
                    
                    # Check for duplicate vote
                    user_current_votes = []
                    for option in options:
                        if user_id in option.get("votes", []):
                            user_current_votes.append(option.get("id"))
                    
                    if option_id in user_current_votes:
                        return {
                            "valid": False,
                            "edge_case": EdgeCaseType.DUPLICATE_VOTE_ATTEMPT,
                            "message": "You have already voted for this option."
                        }
                    
                    # Validate poll data integrity
                    integrity_check = await self._validate_poll_data_integrity(poll_data)
                    if not integrity_check["valid"]:
                        return {
                            "valid": False,
                            "edge_case": EdgeCaseType.POLL_DATA_CORRUPTION,
                            "message": "Poll data is corrupted. Please contact an administrator."
                        }
                    
                    return {
                        "valid": True,
                        "poll_data": poll_data,
                        "current_votes": user_current_votes
                    }
                
                finally:
                    # Remove user from active votes
                    self._active_votes[poll_key].discard(user_id)
                    
                    # Clean up empty sets
                    if not self._active_votes[poll_key]:
                        del self._active_votes[poll_key]
            
            except Exception as e:
                self.logger.error(
                    "Error validating vote attempt",
                    event_id=event_id,
                    poll_type=poll_type,
                    user_id=user_id,
                    error=str(e)
                )
                return {
                    "valid": False,
                    "edge_case": EdgeCaseType.INVALID_VOTE_STATE,
                    "message": "An error occurred while processing your vote."
                }
    
    async def handle_concurrent_vote_conflict(
        self, 
        event_id: str, 
        poll_type: str, 
        conflicting_users: List[str]
    ) -> bool:
        """
        Handle conflicts when multiple users vote simultaneously.
        
        Args:
            event_id: Event ID
            poll_type: Type of poll
            conflicting_users: List of users with conflicting votes
            
        Returns:
            True if resolved successfully
        """
        try:
            self.logger.warning(
                "Handling concurrent vote conflict",
                event_id=event_id,
                poll_type=poll_type,
                conflicting_users=conflicting_users
            )
            
            # Get current poll state
            event_doc = await self.database.find_one("events", {"_id": event_id})
            if not event_doc:
                return False
            
            poll_data = event_doc.get("polls", {}).get(poll_type, {})
            options = poll_data.get("options", [])
            
            # Recalculate vote counts to resolve conflicts
            for option in options:
                votes = option.get("votes", [])
                # Remove duplicates while preserving order
                unique_votes = list(dict.fromkeys(votes))
                option["votes"] = unique_votes
                option["vote_count"] = len(unique_votes)
            
            # Update total votes
            total_votes = sum(option.get("vote_count", 0) for option in options)
            poll_data["total_votes"] = total_votes
            
            # Add conflict resolution metadata
            poll_data["conflict_resolutions"] = poll_data.get("conflict_resolutions", [])
            poll_data["conflict_resolutions"].append({
                "timestamp": datetime.now().isoformat(),
                "type": "concurrent_vote_conflict",
                "affected_users": conflicting_users,
                "resolution": "vote_deduplication"
            })
            
            # Update database
            await self.database.update_one(
                "events",
                {"_id": event_id},
                {"$set": {f"polls.{poll_type}": poll_data}}
            )
            
            # Emit event for UI updates
            await self.event_bus.emit(
                EventType.POLL_UPDATED,
                {
                    "event_id": event_id,
                    "poll_type": poll_type,
                    "action": "conflict_resolved",
                    "resolution_type": "concurrent_vote_conflict"
                }
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to handle concurrent vote conflict",
                event_id=event_id,
                poll_type=poll_type,
                error=str(e)
            )
            return False
    
    async def repair_corrupted_poll_data(
        self, 
        event_id: str, 
        poll_type: str
    ) -> bool:
        """
        Attempt to repair corrupted poll data.
        
        Args:
            event_id: Event ID
            poll_type: Type of poll
            
        Returns:
            True if repair was successful
        """
        try:
            self.logger.info(
                "Attempting to repair corrupted poll data",
                event_id=event_id,
                poll_type=poll_type
            )
            
            event_doc = await self.database.find_one("events", {"_id": event_id})
            if not event_doc:
                return False
            
            poll_data = event_doc.get("polls", {}).get(poll_type, {})
            if not poll_data:
                return False
            
            # Repair missing required fields
            if "title" not in poll_data:
                poll_data["title"] = f"{poll_type.replace('_', ' ').title()} Poll"
            
            if "options" not in poll_data:
                poll_data["options"] = []
            
            if "is_active" not in poll_data:
                poll_data["is_active"] = False
            
            if "total_votes" not in poll_data:
                poll_data["total_votes"] = 0
            
            # Repair option data
            options = poll_data.get("options", [])
            for i, option in enumerate(options):
                if not isinstance(option, dict):
                    # Convert invalid option to dict
                    options[i] = {
                        "id": f"option_{i}",
                        "label": str(option) if option else f"Option {i+1}",
                        "votes": [],
                        "vote_count": 0
                    }
                    continue
                
                # Ensure required fields
                if "id" not in option:
                    option["id"] = f"option_{i}"
                
                if "label" not in option:
                    option["label"] = f"Option {i+1}"
                
                if "votes" not in option:
                    option["votes"] = []
                elif not isinstance(option["votes"], list):
                    option["votes"] = []
                
                # Fix vote count
                votes = option.get("votes", [])
                # Remove duplicates
                unique_votes = list(dict.fromkeys(votes))
                option["votes"] = unique_votes
                option["vote_count"] = len(unique_votes)
            
            # Recalculate total votes
            total_votes = sum(option.get("vote_count", 0) for option in options)
            poll_data["total_votes"] = total_votes
            
            # Add repair metadata
            poll_data["repairs"] = poll_data.get("repairs", [])
            poll_data["repairs"].append({
                "timestamp": datetime.now().isoformat(),
                "type": "data_corruption_repair",
                "repaired_fields": ["options", "vote_counts", "total_votes"]
            })
            
            # Update database
            await self.database.update_one(
                "events",
                {"_id": event_id},
                {"$set": {f"polls.{poll_type}": poll_data}}
            )
            
            self.logger.info(
                "Successfully repaired corrupted poll data",
                event_id=event_id,
                poll_type=poll_type
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to repair corrupted poll data",
                event_id=event_id,
                poll_type=poll_type,
                error=str(e)
            )
            return False
    
    async def _validate_poll_data_integrity(self, poll_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate poll data integrity.
        
        Args:
            poll_data: Poll data to validate
            
        Returns:
            Dictionary with validation results
        """
        issues = []
        
        # Check required fields
        required_fields = ["title", "options", "is_active"]
        for field in required_fields:
            if field not in poll_data:
                issues.append(f"Missing required field: {field}")
        
        # Validate options
        options = poll_data.get("options", [])
        if not isinstance(options, list):
            issues.append("Options must be a list")
        else:
            for i, option in enumerate(options):
                if not isinstance(option, dict):
                    issues.append(f"Option {i} must be a dictionary")
                    continue
                
                # Check option fields
                if "votes" in option:
                    votes = option["votes"]
                    if not isinstance(votes, list):
                        issues.append(f"Option {i} votes must be a list")
                    else:
                        # Check for duplicate votes
                        if len(votes) != len(set(votes)):
                            issues.append(f"Option {i} has duplicate votes")
                        
                        # Check vote count consistency
                        vote_count = option.get("vote_count", 0)
                        if vote_count != len(votes):
                            issues.append(f"Option {i} vote count mismatch")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues
        }
    
    async def cleanup_expired_locks(self) -> None:
        """Clean up expired vote locks and active vote tracking."""
        try:
            # Clean up empty active vote sets
            empty_polls = [poll_key for poll_key, users in self._active_votes.items() if not users]
            for poll_key in empty_polls:
                del self._active_votes[poll_key]
            
            # Clean up unused locks (keep only those with active votes)
            active_poll_keys = set(self._active_votes.keys())
            unused_locks = [poll_key for poll_key in self._vote_locks.keys() if poll_key not in active_poll_keys]
            
            for poll_key in unused_locks:
                del self._vote_locks[poll_key]
            
            self.logger.debug(
                "Cleaned up vote locks",
                removed_active_votes=len(empty_polls),
                removed_locks=len(unused_locks)
            )
            
        except Exception as e:
            self.logger.error("Error cleaning up expired locks", error=str(e))