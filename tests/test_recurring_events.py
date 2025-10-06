"""
Tests for recurring events functionality.
"""

import pytest
from datetime import datetime, date, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from models.recurring import (
    RecurringSchedule, ScheduleTrigger, EventTemplate, ExecutionHistory,
    TriggerType, ScheduleStatus, ExecutionStatus
)
from cogs.recurring import RecurringCog


class TestRecurringSchedule:
    """Test recurring schedule model."""
    
    def test_create_weekly_schedule(self):
        """Test creating a weekly recurring schedule."""
        trigger = ScheduleTrigger(
            trigger_type=TriggerType.WEEKLY,
            day_of_week=0,  # Monday
            trigger_time=time(19, 0),
            timezone="UTC"
        )
        
        template = EventTemplate(
            title_template="Weekly Game Night #{execution_count}",
            description_template="Join us for our weekly game night!",
            default_games=["Among Us", "Jackbox Games"]
        )
        
        schedule = RecurringSchedule(
            id=str(uuid.uuid4()),
            guild_id="123456789",
            creator_id="987654321",
            name="Weekly Game Night",
            trigger=trigger,
            template=template
        )
        
        assert schedule.name == "Weekly Game Night"
        assert schedule.trigger.trigger_type == TriggerType.WEEKLY
        assert schedule.trigger.day_of_week == 0
        assert schedule.status == ScheduleStatus.ACTIVE
        assert len(schedule.template.default_games) == 2
    
    def test_create_monthly_schedule(self):
        """Test creating a monthly recurring schedule."""
        trigger = ScheduleTrigger(
            trigger_type=TriggerType.MONTHLY,
            day_of_month=15,
            trigger_time=time(20, 0),
            timezone="America/New_York"
        )
        
        template = EventTemplate(
            title_template="Monthly Tournament - {current_month}",
            description_template="Monthly tournament for {current_month} {current_year}",
            default_games=["League of Legends", "Valorant"]
        )
        
        schedule = RecurringSchedule(
            id=str(uuid.uuid4()),
            guild_id="123456789",
            creator_id="987654321",
            name="Monthly Tournament",
            trigger=trigger,
            template=template
        )
        
        assert schedule.trigger.trigger_type == TriggerType.MONTHLY
        assert schedule.trigger.day_of_month == 15
        assert schedule.trigger.timezone == "America/New_York"
    
    def test_next_trigger_calculation_weekly(self):
        """Test next trigger calculation for weekly schedules."""
        trigger = ScheduleTrigger(
            trigger_type=TriggerType.WEEKLY,
            day_of_week=0,  # Monday
            trigger_time=time(19, 0),
            timezone="UTC"
        )
        
        # Test with a specific date (Tuesday)
        test_date = date(2024, 1, 2)  # Tuesday
        next_date = trigger.get_next_trigger_date(test_date)
        
        # Should be next Monday (January 8, 2024)
        expected_date = date(2024, 1, 8)
        assert next_date == expected_date
    
    def test_next_trigger_calculation_monthly(self):
        """Test next trigger calculation for monthly schedules."""
        trigger = ScheduleTrigger(
            trigger_type=TriggerType.MONTHLY,
            day_of_month=15,
            trigger_time=time(20, 0),
            timezone="UTC"
        )
        
        # Test with a date before the 15th
        test_date = date(2024, 1, 10)
        next_date = trigger.get_next_trigger_date(test_date)
        
        # Should be January 15, 2024
        expected_date = date(2024, 1, 15)
        assert next_date == expected_date
        
        # Test with a date after the 15th
        test_date = date(2024, 1, 20)
        next_date = trigger.get_next_trigger_date(test_date)
        
        # Should be February 15, 2024
        expected_date = date(2024, 2, 15)
        assert next_date == expected_date
    
    def test_template_rendering(self):
        """Test event template rendering with context."""
        template = EventTemplate(
            title_template="Game Night #{execution_count} - {current_month}",
            description_template="Join us for game night in {current_month} {current_year}!",
            default_games=["Game 1", "Game 2"]
        )
        
        context = {
            "execution_count": 5,
            "current_month": "January",
            "current_year": "2024"
        }
        
        rendered_title = template.render_title(context)
        rendered_description = template.render_description(context)
        
        assert rendered_title == "Game Night #5 - January"
        assert rendered_description == "Join us for game night in January 2024!"
    
    def test_schedule_pause_resume(self):
        """Test pausing and resuming schedules."""
        schedule = RecurringSchedule(
            id=str(uuid.uuid4()),
            guild_id="123456789",
            creator_id="987654321",
            name="Test Schedule",
            trigger=ScheduleTrigger(
                trigger_type=TriggerType.WEEKLY,
                day_of_week=0,
                trigger_time=time(19, 0)
            ),
            template=EventTemplate(title_template="Test Event")
        )
        
        # Test pause
        assert schedule.status == ScheduleStatus.ACTIVE
        paused = schedule.pause()
        assert paused is True
        assert schedule.status == ScheduleStatus.PAUSED
        assert schedule.next_trigger is None
        
        # Test resume
        resumed = schedule.resume()
        assert resumed is True
        assert schedule.status == ScheduleStatus.ACTIVE
        assert schedule.next_trigger is not None
        
        # Test pause when already paused
        schedule.status = ScheduleStatus.PAUSED
        paused_again = schedule.pause()
        assert paused_again is False
    
    def test_execution_recording(self):
        """Test recording execution history."""
        schedule = RecurringSchedule(
            id=str(uuid.uuid4()),
            guild_id="123456789",
            creator_id="987654321",
            name="Test Schedule",
            trigger=ScheduleTrigger(
                trigger_type=TriggerType.WEEKLY,
                day_of_week=0,
                trigger_time=time(19, 0)
            ),
            template=EventTemplate(title_template="Test Event")
        )
        
        # Record successful execution
        schedule.record_execution(
            status=ExecutionStatus.SUCCESS,
            event_id="event123",
            context={"test": "data"}
        )
        
        assert schedule.execution_count == 1
        assert len(schedule.execution_history) == 1
        
        execution = schedule.execution_history[0]
        assert execution.status == ExecutionStatus.SUCCESS
        assert execution.event_id == "event123"
        assert execution.context["test"] == "data"
        
        # Record failed execution
        schedule.record_execution(
            status=ExecutionStatus.FAILED,
            error_message="Test error"
        )
        
        assert schedule.execution_count == 1  # Should not increment for failures
        assert len(schedule.execution_history) == 2
        
        failed_execution = schedule.execution_history[1]
        assert failed_execution.status == ExecutionStatus.FAILED
        assert failed_execution.error_message == "Test error"
    
    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        schedule = RecurringSchedule(
            id=str(uuid.uuid4()),
            guild_id="123456789",
            creator_id="987654321",
            name="Test Schedule",
            trigger=ScheduleTrigger(
                trigger_type=TriggerType.WEEKLY,
                day_of_week=0,
                trigger_time=time(19, 0)
            ),
            template=EventTemplate(title_template="Test Event")
        )
        
        # No executions
        assert schedule.get_success_rate() == 0.0
        
        # Add successful executions
        schedule.record_execution(ExecutionStatus.SUCCESS, event_id="1")
        schedule.record_execution(ExecutionStatus.SUCCESS, event_id="2")
        schedule.record_execution(ExecutionStatus.FAILED, error_message="Error")
        
        # 2 successful out of 3 total = 66.7%
        success_rate = schedule.get_success_rate()
        assert abs(success_rate - 0.6666666666666666) < 0.001
    
    def test_is_due_for_execution(self):
        """Test checking if schedule is due for execution."""
        schedule = RecurringSchedule(
            id=str(uuid.uuid4()),
            guild_id="123456789",
            creator_id="987654321",
            name="Test Schedule",
            trigger=ScheduleTrigger(
                trigger_type=TriggerType.WEEKLY,
                day_of_week=0,
                trigger_time=time(19, 0)
            ),
            template=EventTemplate(title_template="Test Event")
        )
        
        # Set next trigger to past time
        past_time = datetime.utcnow() - timedelta(hours=1)
        schedule.next_trigger = past_time
        
        # Should be due
        assert schedule.is_due_for_execution() is True
        
        # Set next trigger to future time
        future_time = datetime.utcnow() + timedelta(hours=1)
        schedule.next_trigger = future_time
        
        # Should not be due
        assert schedule.is_due_for_execution() is False
        
        # Test with paused schedule
        schedule.status = ScheduleStatus.PAUSED
        schedule.next_trigger = past_time
        
        # Should not be due when paused
        assert schedule.is_due_for_execution() is False


@pytest.mark.asyncio
class TestRecurringCog:
    """Test recurring events cog."""
    
    @pytest.fixture
    def mock_bot(self):
        """Create mock bot."""
        bot = MagicMock()
        bot.database = MagicMock()
        bot.validation = MagicMock()
        bot.event_bus = MagicMock()
        bot.get_cog = MagicMock()
        bot.get_guild = MagicMock()
        return bot
    
    @pytest.fixture
    def recurring_cog(self, mock_bot):
        """Create recurring cog instance."""
        with patch('src.cogs.recurring.tasks'):
            cog = RecurringCog(mock_bot)
            return cog
    
    async def test_create_recurring_schedule(self, recurring_cog, mock_bot):
        """Test creating a recurring schedule."""
        # Mock database insert
        mock_bot.database.recurring_schedules.insert_one = AsyncMock()
        
        # Mock event bus
        mock_bot.event_bus.emit = AsyncMock()
        
        # Create template
        template = EventTemplate(
            title_template="Test Event",
            description_template="Test Description"
        )
        
        # Create schedule
        schedule = await recurring_cog.create_recurring_schedule(
            guild_id="123456789",
            creator_id="987654321",
            name="Test Schedule",
            description="Test Description",
            trigger_type=TriggerType.WEEKLY,
            trigger_time=time(19, 0),
            day_of_week=0,
            day_of_month=None,
            timezone="UTC",
            event_template=template
        )
        
        # Verify schedule properties
        assert schedule.name == "Test Schedule"
        assert schedule.guild_id == "123456789"
        assert schedule.creator_id == "987654321"
        assert schedule.trigger.trigger_type == TriggerType.WEEKLY
        assert schedule.status == ScheduleStatus.ACTIVE
        assert schedule.next_trigger is not None
        
        # Verify database call
        mock_bot.database.recurring_schedules.insert_one.assert_called_once()
        
        # Verify event emission
        mock_bot.event_bus.emit.assert_called_once()
    
    async def test_execute_schedule(self, recurring_cog, mock_bot):
        """Test executing a recurring schedule."""
        # Mock events cog
        mock_events_cog = MagicMock()
        mock_events_cog.create_event = AsyncMock()
        mock_events_cog.create_event.return_value = MagicMock(id="event123")
        mock_bot.get_cog.return_value = mock_events_cog
        
        # Mock database update
        mock_bot.database.recurring_schedules.update_one = AsyncMock()
        
        # Mock event bus
        mock_bot.event_bus.emit = AsyncMock()
        
        # Create test schedule
        schedule = RecurringSchedule(
            id=str(uuid.uuid4()),
            guild_id="123456789",
            creator_id="987654321",
            name="Test Schedule",
            trigger=ScheduleTrigger(
                trigger_type=TriggerType.WEEKLY,
                day_of_week=0,
                trigger_time=time(19, 0)
            ),
            template=EventTemplate(
                title_template="Test Event #{execution_count}",
                description_template="Test Description"
            )
        )
        
        # Execute schedule
        await recurring_cog._execute_schedule(schedule)
        
        # Verify event creation
        mock_events_cog.create_event.assert_called_once()
        call_args = mock_events_cog.create_event.call_args
        assert call_args[1]['guild_id'] == "123456789"
        assert call_args[1]['creator_id'] == "987654321"
        assert "Test Event #1" in call_args[1]['title']
        
        # Verify database update
        mock_bot.database.recurring_schedules.update_one.assert_called_once()
        
        # Verify event emission
        mock_bot.event_bus.emit.assert_called_once()
    
    async def test_pause_resume_schedule(self, recurring_cog, mock_bot):
        """Test pausing and resuming schedules."""
        # Mock database update
        mock_bot.database.recurring_schedules.update_one = AsyncMock()
        
        # Create test schedule
        schedule = RecurringSchedule(
            id=str(uuid.uuid4()),
            guild_id="123456789",
            creator_id="987654321",
            name="Test Schedule",
            trigger=ScheduleTrigger(
                trigger_type=TriggerType.WEEKLY,
                day_of_week=0,
                trigger_time=time(19, 0)
            ),
            template=EventTemplate(title_template="Test Event")
        )
        
        # Test pause
        result = await recurring_cog.pause_schedule(schedule)
        assert result is True
        assert schedule.status == ScheduleStatus.PAUSED
        mock_bot.database.recurring_schedules.update_one.assert_called()
        
        # Test resume
        result = await recurring_cog.resume_schedule(schedule)
        assert result is True
        assert schedule.status == ScheduleStatus.ACTIVE
        assert mock_bot.database.recurring_schedules.update_one.call_count == 2
    
    async def test_delete_schedule(self, recurring_cog, mock_bot):
        """Test deleting a schedule."""
        # Mock database delete
        mock_result = MagicMock()
        mock_result.deleted_count = 1
        mock_bot.database.recurring_schedules.delete_one = AsyncMock(return_value=mock_result)
        
        # Create test schedule
        schedule = RecurringSchedule(
            id=str(uuid.uuid4()),
            guild_id="123456789",
            creator_id="987654321",
            name="Test Schedule",
            trigger=ScheduleTrigger(
                trigger_type=TriggerType.WEEKLY,
                day_of_week=0,
                trigger_time=time(19, 0)
            ),
            template=EventTemplate(title_template="Test Event")
        )
        
        # Delete schedule
        result = await recurring_cog.delete_schedule(schedule)
        assert result is True
        
        # Verify database call
        mock_bot.database.recurring_schedules.delete_one.assert_called_once_with({
            '_id': schedule.id
        })


if __name__ == "__main__":
    pytest.main([__file__])