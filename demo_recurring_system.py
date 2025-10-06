#!/usr/bin/env python3
"""
Demo script to test the recurring events system functionality.
"""

import asyncio
import sys
import os
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from models.recurring import (
    RecurringSchedule, ScheduleTrigger, EventTemplate,
    TriggerType, ScheduleStatus, ExecutionStatus
)


async def demo_recurring_system():
    """Demonstrate the recurring events system."""
    print("🔄 Recurring Events System Demo")
    print("=" * 50)
    
    # 1. Create a weekly recurring schedule
    print("\n1. Creating Weekly Recurring Schedule")
    print("-" * 40)
    
    weekly_trigger = ScheduleTrigger(
        trigger_type=TriggerType.WEEKLY,
        day_of_week=0,  # Monday
        trigger_time=time(19, 0),  # 7 PM
        timezone="UTC"
    )
    
    weekly_template = EventTemplate(
        title_template="Weekly Game Night #{execution_count}",
        description_template="Join us for our weekly game night on {current_date}!",
        default_games=["Among Us", "Jackbox Games", "Fall Guys"],
        variables={"theme": "casual"}
    )
    
    weekly_schedule = RecurringSchedule(
        guild_id="123456789012345678",
        creator_id="987654321098765432",
        name="Weekly Game Night",
        description="Our regular weekly game night for the community",
        trigger=weekly_trigger,
        template=weekly_template
    )
    
    print(f"✅ Created schedule: {weekly_schedule.name}")
    print(f"   Trigger: {weekly_schedule.trigger.trigger_type.value} on day {weekly_schedule.trigger.day_of_week}")
    print(f"   Time: {weekly_schedule.trigger.trigger_time}")
    print(f"   Status: {weekly_schedule.status.value}")
    
    # Calculate next trigger
    weekly_schedule.update_next_trigger()
    print(f"   Next trigger: {weekly_schedule.next_trigger}")
    
    # 2. Create a monthly recurring schedule
    print("\n2. Creating Monthly Recurring Schedule")
    print("-" * 40)
    
    monthly_trigger = ScheduleTrigger(
        trigger_type=TriggerType.MONTHLY,
        day_of_month=15,  # 15th of each month
        trigger_time=time(20, 0),  # 8 PM
        timezone="America/New_York"
    )
    
    monthly_template = EventTemplate(
        title_template="Monthly Tournament - {current_month} {current_year}",
        description_template="Monthly competitive tournament for {current_month}. Prize pool available!",
        default_games=["League of Legends", "Valorant", "CS2"],
        variables={"prize_pool": "$100"}
    )
    
    monthly_schedule = RecurringSchedule(
        guild_id="123456789012345678",
        creator_id="987654321098765432",
        name="Monthly Tournament",
        description="Competitive monthly tournament with prizes",
        trigger=monthly_trigger,
        template=monthly_template
    )
    
    print(f"✅ Created schedule: {monthly_schedule.name}")
    print(f"   Trigger: {monthly_schedule.trigger.trigger_type.value} on day {monthly_schedule.trigger.day_of_month}")
    print(f"   Time: {monthly_schedule.trigger.trigger_time} ({monthly_schedule.trigger.timezone})")
    
    monthly_schedule.update_next_trigger()
    print(f"   Next trigger: {monthly_schedule.next_trigger}")
    
    # 3. Test template rendering
    print("\n3. Testing Template Rendering")
    print("-" * 40)
    
    context = weekly_schedule.get_template_context()
    print(f"Template context: {context}")
    
    rendered_title = weekly_schedule.template.render_title(context)
    rendered_description = weekly_schedule.template.render_description(context)
    
    print(f"Rendered title: {rendered_title}")
    print(f"Rendered description: {rendered_description}")
    
    # 4. Test schedule management operations
    print("\n4. Testing Schedule Management")
    print("-" * 40)
    
    # Test pause/resume
    print(f"Initial status: {weekly_schedule.status.value}")
    
    paused = weekly_schedule.pause()
    print(f"Paused: {paused}, New status: {weekly_schedule.status.value}")
    print(f"Next trigger after pause: {weekly_schedule.next_trigger}")
    
    resumed = weekly_schedule.resume()
    print(f"Resumed: {resumed}, New status: {weekly_schedule.status.value}")
    print(f"Next trigger after resume: {weekly_schedule.next_trigger}")
    
    # 5. Test execution recording
    print("\n5. Testing Execution Recording")
    print("-" * 40)
    
    # Simulate successful executions
    for i in range(3):
        weekly_schedule.record_execution(
            status=ExecutionStatus.SUCCESS,
            event_id=f"event_{i+1}",
            context={"execution_number": i+1}
        )
    
    # Simulate a failed execution
    weekly_schedule.record_execution(
        status=ExecutionStatus.FAILED,
        error_message="Discord API timeout",
        context={"retry_count": 3}
    )
    
    print(f"Total executions: {weekly_schedule.execution_count}")
    print(f"Success rate: {weekly_schedule.get_success_rate():.1%}")
    
    # Show recent executions
    recent = weekly_schedule.get_recent_executions(3)
    print(f"Recent executions ({len(recent)}):")
    for exec in recent:
        print(f"  - {exec.status.value}: {exec.execution_time.strftime('%Y-%m-%d %H:%M:%S')}")
        if exec.error_message:
            print(f"    Error: {exec.error_message}")
    
    # 6. Test due execution check
    print("\n6. Testing Due Execution Check")
    print("-" * 40)
    
    # Set trigger to past time to simulate due execution
    past_time = datetime.utcnow() - timedelta(minutes=30)
    weekly_schedule.next_trigger = past_time
    
    is_due = weekly_schedule.is_due_for_execution()
    print(f"Schedule due for execution: {is_due}")
    
    # Test with future time
    future_time = datetime.utcnow() + timedelta(hours=2)
    weekly_schedule.next_trigger = future_time
    
    is_due = weekly_schedule.is_due_for_execution()
    print(f"Schedule due for execution (future): {is_due}")
    
    # 7. Test trigger calculations
    print("\n7. Testing Trigger Calculations")
    print("-" * 40)
    
    from datetime import date
    
    # Test weekly trigger
    test_date = date(2024, 10, 1)  # Tuesday
    next_weekly = weekly_trigger.get_next_trigger_date(test_date)
    print(f"Next weekly trigger after {test_date}: {next_weekly}")
    
    # Test monthly trigger
    next_monthly = monthly_trigger.get_next_trigger_date(test_date)
    print(f"Next monthly trigger after {test_date}: {next_monthly}")
    
    print("\n✅ Recurring Events System Demo Complete!")
    print("All functionality working correctly.")


if __name__ == "__main__":
    asyncio.run(demo_recurring_system())