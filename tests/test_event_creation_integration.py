"""
Integration test for Task 4: Event creation and storage.

This test verifies the complete flow with actual database operations
(using a test database).
"""

import os
import sys
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

# Add src directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

import discord

from cogs.events import EventCreationModal, EventsCog
from models.event import Event, EventState
from core.event_bus import EventBus
from core.validation_manager import ValidationManager
from core.poll_manager import PollManager
from database.manager import DatabaseManager


class MockBot:
    """Mock bot with real database manager."""
    
    def __init__(self, database_manager):
        self.database = database_manager
        self.event_bus = EventBus()
        self.validation = ValidationManager()
        self.security = MagicMock()
        self.poll_manager = PollManager(self.event_bus, database_manager)


class MockGuild:
    """Mock Discord guild."""
    
    def __init__(self, guild_id: int = 123456789):
        self.id = guild_id
        self.name = "Test Guild"


class MockUser:
    """Mock Discord user."""
    
    def __init__(self, user_id: int = 987654321):
        self.id = user_id
        self.name = "TestUser"
        self.mention = f"<@{user_id}>"


class MockInteraction:
    """Mock Discord interaction."""
    
    def __init__(self, guild: MockGuild, user: MockUser):
        self.guild = guild
        self.user = user
        self.response = MagicMock()
        self.response.send_message = AsyncMock()
        self.response.is_done = MagicMock(return_value=False)


@pytest.fixture
async def database_manager():
    """Create a database manager connected to test database."""
    # Use test database URL from environment or default to local MongoDB
    db_url = os.getenv('TEST_DATABASE_URL', 'mongodb://localhost:27017/gamenight_bot_test')
    
    db = DatabaseManager(db_url)
    
    try:
        await db.connect()
        yield db
    except Exception as e:
        pytest.skip(f"Database not available: {e}")
    finally:
        # Cleanup: delete test data
        if db.is_connected:
            try:
                await db.database['events'].delete_many({'guild_id': '123456789'})
            except:
                pass
            await db.disconnect()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_event_creation_full_integration(database_manager):
    """
    Full integration test for event creation and storage.
    
    This test verifies:
    1. Event is created with correct data
    2. Event is saved to MongoDB
    3. Event can be retrieved from database
    4. All fields are correctly stored and retrieved
    
    Requirements tested:
    - 1.1: Complete event creation workflow
    - 9.3: Database operations
    """
    # Arrange
    bot = MockBot(database_manager)
    events_cog = EventsCog(bot)
    
    modal = EventCreationModal(events_cog)
    modal.title_input = MagicMock()
    modal.title_input.value = "Integration Test Event"
    modal.description_input = MagicMock()
    modal.description_input.value = "Testing full integration"
    
    guild = MockGuild()
    user = MockUser()
    interaction = MockInteraction(guild, user)
    
    # Act - Submit the modal
    await modal.on_submit(interaction)
    
    # Assert - Verify confirmation message was sent
    interaction.response.send_message.assert_called_once()
    message = interaction.response.send_message.call_args[0][0]
    assert "✅" in message
    assert "Event Created Successfully" in message
    assert "Integration Test Event" in message
    
    # Extract event ID from message
    import re
    event_id_match = re.search(r'Event ID:\*\* `([^`]+)`', message)
    assert event_id_match, "Event ID not found in confirmation message"
    event_id = event_id_match.group(1)
    
    # Verify event was saved to database
    from bson import ObjectId
    saved_event = await database_manager.find_one(
        'events',
        {'_id': ObjectId(event_id)}
    )
    
    assert saved_event is not None, "Event not found in database"
    assert saved_event['guild_id'] == str(guild.id)
    assert saved_event['creator_id'] == str(user.id)
    assert saved_event['title'] == "Integration Test Event"
    assert saved_event['description'] == "Testing full integration"
    assert saved_event['state'] == EventState.DRAFT
    assert 'created_at' in saved_event
    assert 'updated_at' in saved_event


@pytest.mark.asyncio
@pytest.mark.integration
async def test_event_creation_database_error_handling(database_manager):
    """
    Test error handling when database operations fail.
    
    Requirements tested:
    - 9.3: Database error handling
    """
    # Arrange
    bot = MockBot(database_manager)
    events_cog = EventsCog(bot)
    
    # Force database error by disconnecting
    await database_manager.disconnect()
    
    modal = EventCreationModal(events_cog)
    modal.title_input = MagicMock()
    modal.title_input.value = "Error Test Event"
    modal.description_input = MagicMock()
    modal.description_input.value = "Testing error handling"
    
    guild = MockGuild()
    user = MockUser()
    interaction = MockInteraction(guild, user)
    
    # Act
    await modal.on_submit(interaction)
    
    # Assert - Error message was sent
    interaction.response.send_message.assert_called_once()
    message = interaction.response.send_message.call_args[0][0]
    assert "❌" in message
    assert "Failed to save event" in message


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
