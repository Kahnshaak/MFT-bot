"""
Simple poll management system for the simplified event model.
Polls are now embedded directly in Event objects.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime

from models.event import Event
from core.event_bus import EventBus, EventType
from utils.logging_config import get_logger, LoggerMixin


class PollManager(LoggerMixin):
    """
    Simple poll management system for embedded event polls.
    """
    
    def __init__(self, event_bus: EventBus, database_manager):
        self.event_bus = event_bus
        self.database = database_manager
    
    async def process_vote(self, event: Event, user_id: str, dates: List[str], times: List[str]) -> bool:
        """
        Process votes for an event poll.
        
        Args:
            event: Event object to vote on
            user_id: Discord user ID
            dates: List of date strings to vote for
            times: List of time strings to vote for
            
        Returns:
            True if vote was processed successfully
        """
        try:
            event.add_vote(user_id, dates, times)
            return True
        except Exception as e:
            self.logger.error(f"Failed to process vote: {e}")
            return False
    
    def get_poll_results(self, event: Event) -> Tuple[Dict[str, int], Dict[str, int]]:
        """
        Get poll results for an event.
        
        Args:
            event: Event object
            
        Returns:
            Tuple of (date_counts, time_counts)
        """
        return event.get_vote_counts()
    
    def calculate_winner(self, event: Event) -> Tuple[Optional[str], Optional[str], bool, List[str], List[str]]:
        """
        Calculate winning date and time for an event.
        
        Args:
            event: Event object
            
        Returns:
            Tuple of (winning_date, winning_time, is_tie, tied_dates, tied_times)
        """
        return event.calculate_winner()