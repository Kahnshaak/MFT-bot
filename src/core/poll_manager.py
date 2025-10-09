"""
Simple poll management system.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime

from models.event import Event, Poll, EventState
from core.event_bus import EventBus, EventType
from utils.logging_config import get_logger, LoggerMixin


class PollManager(LoggerMixin):
    """
    Simple poll management system.
    """
    
    def __init__(self, event_bus: EventBus, database_manager):
        self.event_bus = event_bus
        self.database = database_manager
    
    async def create_poll(self, event: Event, title: str, options: List[str]) -> Poll:
        """Create a simple poll."""
        poll = Poll(title=title, options=options)
        event.polls.append(poll)
        return poll
    
    async def process_vote(self, poll: Poll, user_id: str, option: str) -> bool:
        """Process a vote on a poll."""
        if option in poll.options:
            poll.votes[user_id] = option
            return True
        return False
    
    def get_poll_results(self, poll: Poll) -> Dict[str, int]:
        """Get poll results."""
        results = {}
        for option in poll.options:
            results[option] = sum(1 for vote in poll.votes.values() if vote == option)
        return results