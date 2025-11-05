# Task 9 Summary: Background Task for Poll Expiration

## Implementation Overview

Successfully implemented a background task that runs every 5 minutes to check for expired polls and process them automatically.

## Changes Made

### 1. Updated `src/cogs/events.py`

#### Added imports:
- `from discord.ext import commands, tasks` - Added `tasks` for background task support

#### Modified `EventsCog` class:
- **`__init__` method**: Added initialization of the background task `check_expired_polls.start()`
- **`cog_unload` method**: Added cleanup to stop the background task when cog is unloaded
- **`check_expired_polls` task**: New background task that:
  - Runs every 5 minutes using `@tasks.loop(minutes=5)`
  - Queries database for events where `expires_at < now` and `status="active"`
  - Processes each expired poll by:
    - Creating an Event model instance
    - Calculating the winner using `event.calculate_winner()`
    - Handling ties by calling `_handle_poll_tie()`
    - Handling winners by calling `_create_scheduled_event()`
  - Continues processing other events if one fails (error handling)
  - Logs all operations for debugging

- **`before_check_expired_polls` method**: Waits for bot to be ready before starting the task
- **`_handle_poll_tie` method**: Placeholder for task 13 that:
  - Updates event status to "tie"
  - Logs the tie information
  - Will be fully implemented in task 13 to notify admins

- **`_create_scheduled_event` method**: Placeholder for task 11 that:
  - Updates event with winning date/time
  - Updates status to "expired" (will be "scheduled" after task 11)
  - Will be fully implemented in task 11 to create Discord Scheduled Event
  - Will call task 12 to update poll message with results

### 2. Created `tests/test_poll_expiration.py`

Comprehensive test suite with 7 tests covering:
- Finding and processing expired events
- Handling no expired events
- Handling tie scenarios
- Handling no votes (treated as tie)
- Continuing processing when one event fails
- Verifying task runs every 5 minutes
- Verifying task cleanup on cog unload

All tests pass successfully.

## Key Features

1. **Automatic Polling**: Runs every 5 minutes without manual intervention
2. **Database Query**: Efficiently finds only expired active polls
3. **Winner Calculation**: Uses the Event model's `calculate_winner()` method
4. **Error Handling**: Continues processing other events if one fails
5. **Graceful Shutdown**: Properly stops the task when cog is unloaded
6. **Wait for Ready**: Ensures bot is ready before starting the task
7. **Logging**: Comprehensive logging for debugging and monitoring

## Database Query

The task queries for events with:
```python
{
    "expires_at": {"$lt": now},
    "status": "active"
}
```

This ensures only polls that have expired and are still active are processed.

## Integration with Future Tasks

The implementation includes placeholder methods that will be completed in future tasks:
- **Task 10**: Winner calculation logic (already implemented in Event model)
- **Task 11**: `_create_scheduled_event()` will create Discord Scheduled Events
- **Task 12**: Poll message update with results
- **Task 13**: `_handle_poll_tie()` will send admin notifications

## Testing

All 7 tests pass:
- ✅ Finds and processes expired events
- ✅ Handles no expired events gracefully
- ✅ Handles tie scenarios correctly
- ✅ Handles no votes (treated as tie)
- ✅ Continues processing on error
- ✅ Runs every 5 minutes
- ✅ Stops on cog unload

## Requirements Met

✅ **Requirement 2.1**: "WHEN a poll expires after 7 days THEN the system SHALL automatically calculate the winning date and time"
- Background task runs every 5 minutes to check for expired polls
- Automatically processes expired polls without manual intervention
- Calls winner calculation for each expired poll

## Next Steps

The background task is now ready and will automatically process expired polls. The next tasks (10-12) will implement:
1. Task 10: Winner calculation (already implemented in Event model)
2. Task 11: Discord Scheduled Event creation
3. Task 12: Poll message update with results
4. Task 13: Admin notification for ties
