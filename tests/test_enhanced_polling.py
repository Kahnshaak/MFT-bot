"""
Tests for enhanced polling system functionality.
"""

import pytest
import asyncio
from datetime import datetime, timedelta, date, time
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models.event import Event, EventState, Poll
from core.poll_manager import PollManager
from core.event_bus import EventBus, EventType


class TestPollManager:
    """Test the poll manager functionality."""
    
    @pytest.fixture
    def event_bus(self):
        """Create mock event bus."""
        return AsyncMock(spec=EventBus)
    
    @pytest.fixture
    def database_manager(self):
        """Create mock database manager."""
        db = MagicMock()
        db.events = AsyncMock()
        return db
    
    @pytest.fixture
    def poll_manager(self, event_bus, database_manager):
        """Create poll manager instance."""
        return PollManager(event_bus, database_manager)
    
    @pytest.fixture
    def sample_event(self):
        """Create sample event for testing."""
        return Event(
            guild_id="123456789",
            creator_id="987654321",
            title="Test Game Night",
            description="A test event",
            state=EventState.DRAFT
        )
    
    @pytest.mark.asyncio
    async def test_create_poll(self, poll_manager, sample_event):
        """Test creating a simple poll."""
        options = ["Option 1", "Option 2", "Option 3"]
        
        poll = await poll_manager.create_poll(
            event=sample_event,
            title="Test Poll",
            options=options
        )
        
        assert poll.title == "Test Poll"
        assert len(poll.options) == 3
        assert poll.is_active
        assert len(sample_event.polls) == 1
    
    @pytest.mark.asyncio
    async def test_process_vote(self, poll_manager, sample_event):
        """Test processing votes."""
        options = ["Option 1", "Option 2"]
        poll = await poll_manager.create_poll(sample_event, "Test Poll", options)
        
        # Valid vote
        success = await poll_manager.process_vote(poll, "user1", "Option 1")
        assert success
        assert poll.votes["user1"] == "Option 1"
        
        # Invalid vote
        success = await poll_manager.process_vote(poll, "user2", "Invalid Option")
        assert not success
        assert "user2" not in poll.votes
    
    def test_get_poll_results(self, poll_manager):
        """Test getting poll results."""
        poll = Poll(title="Test Poll", options=["Option 1", "Option 2"])
        poll.votes = {
            "user1": "Option 1",
            "user2": "Option 1", 
            "user3": "Option 2"
        }
        
        results = poll_manager.get_poll_results(poll)
        
        assert results["Option 1"] == 2
        assert results["Option 2"] == 1





if __name__ == "__main__":
    pytest.main([__file__])