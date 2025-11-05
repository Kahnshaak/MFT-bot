# Database Error Handling Implementation

## Overview
This document describes the comprehensive database error handling implemented across the Discord Game Night Bot application.

## Implementation Summary

### Core Principle
All database operations are wrapped in try/except blocks that:
1. Catch `DatabaseError` exceptions
2. Log errors with full context and stack traces
3. Provide user-friendly error messages
4. Implement graceful degradation where possible
5. Prevent data corruption

### Error Handling Layers

#### Layer 1: Database Manager (`src/database/manager.py`)
- All CRUD operations wrapped in try/except
- Raises `DatabaseError` with operation context
- Logs all errors with full details
- **Status:** Already implemented ✓

#### Layer 2: Repositories (`src/models/repositories.py`)
- All repository methods wrapped in try/except
- Catches exceptions and raises `DatabaseError`
- Logs errors with model context
- **Status:** Already implemented ✓

#### Layer 3: Application Layer (`src/cogs/events.py`)
- All database calls wrapped in try/except
- Catches `DatabaseError` from lower layers
- Provides user-friendly Discord messages
- Implements graceful degradation
- **Status:** Newly implemented ✓

#### Layer 4: API Layer (`src/api/*.py`)
- All database operations wrapped in try/except
- Returns HTTP error responses
- Logs errors with request context
- **Status:** Already implemented ✓

## Specific Implementations

### Event Creation
**Location:** `EventCreationModal.callback()`
```python
try:
    event_id = await self.bot.database.insert_one("events", event.model_dump())
except DatabaseError as e:
    self.logger.error(f"Database error creating event: {e}", exc_info=True)
    await interaction.response.send_message(
        "❌ Failed to save event to database. Please try again later.",
        ephemeral=True
    )
    return
```

### Vote Submission
**Location:** `VoteModal.callback()`
```python
try:
    event_data = await self.bot.database.find_one("events", {"_id": self.event_id})
except DatabaseError as e:
    self.logger.error(f"Database error fetching event: {e}", exc_info=True)
    await interaction.response.send_message(
        "❌ Failed to retrieve event from database. Please try again later.",
        ephemeral=True
    )
    return
```

### Background Tasks
**Location:** `EventsCog.check_expired_polls()`
```python
try:
    expired_events = await self.bot.database.find_many(
        "events",
        {"expires_at": {"$lt": now}, "status": "active"}
    )
except DatabaseError as e:
    self.logger.error(f"Database error querying expired polls: {e}", exc_info=True)
    return  # Skip this iteration, will retry in 5 minutes
```

### Critical Operations
**Location:** `EventsCog._create_scheduled_event()`
```python
try:
    await self.bot.database.update_one(...)
except DatabaseError as e:
    self.logger.error(f"Database error: {e}", exc_info=True)
    self.logger.critical(
        f"CRITICAL: Discord event {scheduled_event.id} created but failed to save to database. "
        f"Manual intervention may be required."
    )
```

## Error Messages

### User-Facing Messages
All error messages are:
- Clear and non-technical
- Ephemeral (only visible to the user)
- Actionable (suggest retry or contact admin)

Examples:
- "❌ Failed to save event to database. Please try again later."
- "❌ Failed to retrieve event from database. Please try again later."
- "❌ Failed to save your vote to database. Please try again."
- "⚠️ Poll created but failed to save message reference. The poll may not work correctly."

### Log Messages
All errors are logged with:
- Full error message
- Stack trace (`exc_info=True`)
- Contextual information (event IDs, user IDs, operation)
- Severity level (ERROR or CRITICAL)

## Graceful Degradation

### Partial Failures
When non-critical operations fail, the system continues:
- Poll created but message_id not saved → Poll still visible
- Status update fails → Operation completes, status updated on next retry
- Vote count update fails → Vote recorded, display updated on next vote

### Critical Failures
When critical operations fail, the system:
- Logs CRITICAL level errors
- Preserves external state (Discord events)
- Logs all details for manual recovery
- Continues execution to minimize user impact

## Testing

### Manual Testing
Run the demonstration script:
```bash
python tests/manual_test_database_error_handling.py
```

This demonstrates:
- Error catching and handling
- User-friendly messages
- Graceful degradation
- Background task resilience
- Critical error handling

### Integration Testing
To test with actual database failures:
1. Stop MongoDB service
2. Run `/event create` command
3. Verify user sees friendly error message
4. Verify error is logged
5. Verify bot continues operating

### Automated Testing
See `tests/test_database_error_handling.py` for unit tests (note: some tests need Discord mocking improvements)

## Monitoring

### Log Levels
- **ERROR:** Normal database errors (connection issues, timeouts)
- **CRITICAL:** State divergence (Discord event created but DB save failed)

### Metrics to Monitor
- Database error frequency
- Error types (connection, timeout, write failures)
- Critical errors requiring manual intervention
- User retry patterns

## Recovery Procedures

### Connection Failures
1. Database automatically reconnects
2. Background tasks retry on next iteration
3. Users can retry failed operations immediately

### Critical State Divergence
1. Search logs for CRITICAL level errors
2. Identify Discord events not saved to database
3. Manually update database with Discord event IDs
4. Verify event status is correct

## Best Practices

### When Adding New Database Operations
1. Always wrap in try/except
2. Catch `DatabaseError` specifically
3. Log with full context (`exc_info=True`)
4. Provide user-friendly error message
5. Implement graceful degradation if possible
6. Document critical operations

### Error Message Guidelines
- Use ❌ for errors
- Use ⚠️ for warnings
- Keep messages under 100 characters
- Suggest action (retry, contact admin)
- Use ephemeral messages for errors

## Files Modified
- `src/cogs/events.py` - Added comprehensive error handling
- `tests/manual_test_database_error_handling.py` - Created demonstration script
- `.kiro/specs/simple-event-bot/task-15-summary.md` - Implementation documentation

## Requirements Coverage
✅ Wrap all database operations in try/except
✅ Log all database errors with full context
✅ Send user-friendly error messages to Discord
✅ Covers all requirements (All)

## Conclusion
The application now has comprehensive database error handling at all layers, providing:
- Resilient operation during database issues
- Clear error messages for users
- Detailed logging for debugging
- Graceful degradation where possible
- Protection against data corruption
