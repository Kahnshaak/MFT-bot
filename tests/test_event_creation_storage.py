"""
Tests for Task 4: Basic event creation and storage.

This test file verifies that:
1. Database save operation works in EventCreationModal.on_submit()
2. Event object is created with DRAFT state and stored in MongoDB
3. Event ID and confirmation message are returned to user
4. Error handling for database failures is implemented
"""

import os
import sys
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

# Add src directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

import discord

from cogs.events import EventCreationModal, EventsCog
from models.event import Event, EventState
from core.event_bus import EventBus
from core.validation_manager import ValidationManager
from database.manager import DatabaseManager


class MockBot:
    """Mock bot for testing."""
    
    def __init__(self):
        self.database = MagicMock(spec=DatabaseManager)
        self.event_bus = EventBus()
        self.validation = ValidationManager()
        self.security = MagicMock()
        self.poll_manager = MagicMock()


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
def mock_bot():
    """Create a mock bot instance."""
    return MockBot()


@pytest.fixture
def events_cog(mock_bot):
    """Create an Events cog instance."""
    return EventsCog(mock_bot)


@pytest.fixture
def mock_interaction():
    """Create a mock interaction."""
    guild = MockGuild()
    user = MockUser()
    return MockInteraction(guild, user)


@pytest.mark.asyncio
async def test_event_creation_modal_successful_save(events_cog, mock_bot, mock_interaction):
    """
    Test that EventCreationModal successfully creates and saves an event.
    
    Requirements tested:
    - 1.1: Event creation workflow
    - 9.3: Database operations
    """
    # Arrange
    modal = EventCreationModal(events_cog)
    modal.title_input = MagicMock()
    modal.title_input.value = "Epic Game Night"
    modal.description_input = MagicMock()
    modal.description_input.value = "Let's play some awesome games!"
    
    # Mock database insert to return an ID
    test_event_id = str(ObjectId())
    mock_bot.database.insert_one = AsyncMock(return_value=test_event_id)
    
    # Act
    await modal.on_submit(mock_interaction)
    
    # Assert - Verify database was called
    mock_bot.database.insert_one.assert_called_once()
    call_args = mock_bot.database.insert_one.call_args
    
    # Verify collection name
    assert call_args[0][0] == 'events'
    
    # Verify event data
    event_dict = call_args[0][1]
    assert event_dict['guild_id'] == str(mock_interaction.guild.id)
    assert event_dict['creator_id'] == str(mock_interaction.user.id)
    assert event_dict['title'] == "Epic Game Night"
    assert event_dict['description'] == "Let's play some awesome games!"
    assert event_dict['state'] == EventState.DRAFT
    
    # Verify confirmation message was sent
    mock_interaction.response.send_message.assert_called_once()
    message_call = mock_interaction.response.send_message.call_args[0][0]
    assert "✅" in message_call
    assert "Event Created Successfully" in message_call
    assert test_event_id in message_call
    assert "Epic Game Night" in message_call
    assert "DRAFT" in message_call


@pytest.mark.asyncio
async def test_event_creation_modal_with_empty_description(events_cog, mock_bot, mock_interaction):
    """
    Test that EventCreationModal handles empty description correctly.
    
    Requirements tested:
    - 1.1: Event creation workflow with optional fields
    """
    # Arrange
    modal = EventCreationModal(events_cog)
    modal.title_input = MagicMock()
    modal.title_input.value = "Quick Game Night"
    modal.description_input = MagicMock()
    modal.description_input.value = ""  # Empty description
    
    # Mock database insert
    test_event_id = str(ObjectId())
    mock_bot.database.insert_one = AsyncMock(return_value=test_event_id)
    
    # Act
    await modal.on_submit(mock_interaction)
    
    # Assert
    mock_bot.database.insert_one.assert_called_once()
    event_dict = mock_bot.database.insert_one.call_args[0][1]
    
    # Description should be None when empty
    assert event_dict['description'] is None
    
    # Confirmation message should handle empty description
    message_call = mock_interaction.response.send_message.call_args[0][0]
    assert "No description provided" in message_call


@pytest.mark.asyncio
async def test_event_creation_modal_database_failure(events_cog, mock_bot, mock_interaction):
    """
    Test that EventCreationModal handles database failures gracefully.
    
    Requirements tested:
    - 9.3: Database error handling
    """
    # Arrange
    modal = EventCreationModal(events_cog)
    modal.title_input = MagicMock()
    modal.title_input.value = "Game Night"
    modal.description_input = MagicMock()
    modal.description_input.value = "Fun times"
    
    # Mock database insert to raise an exception
    mock_bot.database.insert_one = AsyncMock(side_effect=Exception("Database connection failed"))
    
    # Act
    await modal.on_submit(mock_interaction)
    
    # Assert - Error message was sent
    mock_interaction.response.send_message.assert_called_once()
    error_message = mock_interaction.response.send_message.call_args[0][0]
    assert "❌" in error_message
    assert "Failed to save event" in error_message


@pytest.mark.asyncio
async def test_event_creation_modal_validation_error(events_cog, mock_bot, mock_interaction):
    """
    Test that EventCreationModal handles validation errors.
    
    Requirements tested:
    - 1.1: Input validation during event creation
    """
    # Arrange
    modal = EventCreationModal(events_cog)
    modal.title_input = MagicMock()
    modal.title_input.value = "AB"  # Too short (min 3 chars)
    modal.description_input = MagicMock()
    modal.description_input.value = "Description"
    
    # Act
    await modal.on_submit(mock_interaction)
    
    # Assert - Error message was sent
    mock_interaction.response.send_message.assert_called_once()
    error_message = mock_interaction.response.send_message.call_args[0][0]
    assert "❌" in error_message


@pytest.mark.asyncio
async def test_event_object_created_with_correct_state(events_cog, mock_bot, mock_interaction):
    """
    Test that Event object is created with DRAFT state.
    
    Requirements tested:
    - 1.1: Event starts in DRAFT state
    """
    # Arrange
    modal = EventCreationModal(events_cog)
    modal.title_input = MagicMock()
    modal.title_input.value = "Test Event"
    modal.description_input = MagicMock()
    modal.description_input.value = "Test Description"
    
    test_event_id = str(ObjectId())
    mock_bot.database.insert_one = AsyncMock(return_value=test_event_id)
    
    # Act
    await modal.on_submit(mock_interaction)
    
    # Assert
    event_dict = mock_bot.database.insert_one.call_args[0][1]
    assert event_dict['state'] == EventState.DRAFT
    assert event_dict['state'] == "DRAFT"  # Verify string representation


@pytest.mark.asyncio
async def test_event_id_returned_in_confirmation(events_cog, mock_bot, mock_interaction):
    """
    Test that event ID is returned in confirmation message.
    
    Requirements tested:
    - 1.1: User receives event ID for reference
    """
    # Arrange
    modal = EventCreationModal(events_cog)
    modal.title_input = MagicMock()
    modal.title_input.value = "Test Event"
    modal.description_input = MagicMock()
    modal.description_input.value = "Description"
    
    # Use a specific event ID to verify it's in the message
    test_event_id = "507f1f77bcf86cd799439011"
    mock_bot.database.insert_one = AsyncMock(return_value=test_event_id)
    
    # Act
    await modal.on_submit(mock_interaction)
    
    # Assert
    message_call = mock_interaction.response.send_message.call_args[0][0]
    assert test_event_id in message_call
    assert "Event ID" in message_call


@pytest.mark.asyncio
async def test_event_stored_in_events_collection(events_cog, mock_bot, mock_interaction):
    """
    Test that event is stored in the 'events' collection.
    
    Requirements tested:
    - 9.3: Correct database collection usage
    """
    # Arrange
    modal = EventCreationModal(events_cog)
    modal.title_input = MagicMock()
    modal.title_input.value = "Test Event"
    modal.description_input = MagicMock()
    modal.description_input.value = "Description"
    
    mock_bot.database.insert_one = AsyncMock(return_value=str(ObjectId()))
    
    # Act
    await modal.on_submit(mock_interaction)
    
    # Assert - Verify collection name is 'events'
    collection_name = mock_bot.database.insert_one.call_args[0][0]
    assert collection_name == 'events'


@pytest.mark.asyncio
async def test_event_contains_all_required_fields(events_cog, mock_bot, mock_interaction):
    """
    Test that created event contains all required fields.
    
    Requirements tested:
    - 1.1: Complete event data structure
    """
    # Arrange
    modal = EventCreationModal(events_cog)
    modal.title_input = MagicMock()
    modal.title_input.value = "Complete Event"
    modal.description_input = MagicMock()
    modal.description_input.value = "Full description"
    
    mock_bot.database.insert_one = AsyncMock(return_value=str(ObjectId()))
    
    # Act
    await modal.on_submit(mock_interaction)
    
    # Assert
    event_dict = mock_bot.database.insert_one.call_args[0][1]
    
    # Verify all required fields are present
    assert 'guild_id' in event_dict
    assert 'creator_id' in event_dict
    assert 'title' in event_dict
    assert 'description' in event_dict
    assert 'state' in event_dict
    assert 'created_at' in event_dict
    assert 'updated_at' in event_dict
    
    # Verify field values
    assert event_dict['guild_id'] == str(mock_interaction.guild.id)
    assert event_dict['creator_id'] == str(mock_interaction.user.id)
    assert event_dict['title'] == "Complete Event"
    assert event_dict['description'] == "Full description"
    assert event_dict['state'] == EventState.DRAFT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
