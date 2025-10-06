# Recurring Events Cog

The Recurring Events cog provides automated event creation and management functionality for Discord servers. It allows administrators to set up recurring schedules that automatically create game night events based on configurable templates and triggers.

## Features

### Core Functionality

- **Automated Event Creation**: Automatically creates events based on recurring schedules
- **Flexible Scheduling**: Support for weekly and monthly recurring patterns
- **Template-Based Events**: Use customizable templates with variable substitution
- **Background Processing**: Continuous monitoring and execution of due schedules
- **Schedule Management**: Pause, resume, and delete recurring schedules
- **Execution Tracking**: Complete history and analytics for schedule executions
- **Error Handling**: Robust error handling with admin notifications
- **Preview Functionality**: Preview what events will look like before scheduling

### Schedule Types

#### Weekly Schedules
- Trigger on specific days of the week (Monday = 0, Sunday = 6)
- Configurable time and timezone
- Support for multi-week intervals

#### Monthly Schedules
- Trigger on specific day of the month (1-31)
- Automatic handling of months with fewer days
- Configurable time and timezone
- Support for multi-month intervals

### Event Templates

Templates support variable substitution with the following built-in variables:
- `{schedule_name}`: Name of the recurring schedule
- `{execution_count}`: Number of times the schedule has executed
- `{current_date}`: Current date (YYYY-MM-DD)
- `{current_month}`: Current month name
- `{current_year}`: Current year
- `{next_trigger}`: Next scheduled trigger date

Custom variables can also be defined in the template configuration.

## Commands

### `/recurring create`
Creates a new recurring schedule through an interactive setup process.

**Permissions Required**: Administrator, Manage Events, or Manage Guild

**Process**:
1. Enter schedule name and description
2. Configure trigger type (weekly/monthly)
3. Set trigger time and timezone
4. Create event template with title, description, and default games

### `/recurring list`
Lists all recurring schedules for the current server with pagination.

**Information Displayed**:
- Schedule name and status
- Trigger configuration
- Next execution time
- Execution count

### `/recurring manage <schedule_id>`
Opens the management interface for a specific recurring schedule.

**Available Actions**:
- Pause/Resume schedule
- Test execute (create event immediately)
- Delete schedule
- View execution history

**Permissions Required**: Schedule creator or Administrator

### `/recurring preview <schedule_id>`
Shows a preview of what the next event will look like based on the current template and context.

## Schedule Management

### Schedule States

- **ACTIVE**: Schedule is running and will create events automatically
- **PAUSED**: Schedule is temporarily stopped but can be resumed
- **DISABLED**: Schedule is permanently disabled (reached max executions)

### Execution Status

- **SUCCESS**: Event was created successfully
- **FAILED**: Event creation failed (error logged)
- **SKIPPED**: Execution was skipped (e.g., maintenance mode)

### Background Processing

The cog runs a background task every minute to:
1. Check for schedules that are due for execution
2. Execute due schedules by creating events
3. Update schedule state and next trigger times
4. Handle errors and notify administrators

## Configuration

### Database Collections

The cog uses the `recurring_schedules` collection with the following indexes:
- `guild_id + status` (for finding active schedules)
- `next_trigger` (for finding due schedules)
- `creator_id + created_at` (for user schedule lookup)

### Error Handling

When schedule execution fails:
1. Error is logged with full details
2. Execution is recorded as FAILED in history
3. Administrators are notified via server channels
4. Schedule remains active for next attempt

### Admin Notifications

Failed executions trigger notifications sent to:
1. Channels with "admin" or "mod" in the name
2. First available text channel as fallback

## Usage Examples

### Weekly Game Night
```
Schedule Name: Weekly Game Night
Trigger: Weekly on Monday at 7:00 PM UTC
Template Title: "Weekly Game Night #{execution_count}"
Template Description: "Join us for our weekly game night on {current_date}!"
Default Games: Among Us, Jackbox Games, Fall Guys
```

### Monthly Tournament
```
Schedule Name: Monthly Tournament
Trigger: Monthly on 15th at 8:00 PM EST
Template Title: "Monthly Tournament - {current_month} {current_year}"
Template Description: "Competitive tournament for {current_month}. Prize pool available!"
Default Games: League of Legends, Valorant, CS2
```

### Seasonal Events
```
Schedule Name: Holiday Special
Trigger: Monthly on 25th at 6:00 PM UTC
Template Title: "Holiday Game Night - {current_month}"
Template Description: "Special holiday-themed game night for {current_month}!"
Custom Variables: theme=holiday, special_games=true
```

## Integration

### Event Bus Integration

The cog emits the following events:
- `EVENT_CREATED`: When a recurring schedule creates an event
- `ERROR_OCCURRED`: When schedule execution fails

### Events Cog Integration

The recurring cog integrates with the Events cog to:
1. Create events using the standard event creation workflow
2. Trigger automatic polls based on template configuration
3. Inherit all event management features

### Notifications Integration

Created events automatically integrate with the notifications system for:
- Event reminders
- Poll notifications
- RSVP confirmations

## Monitoring and Analytics

### Execution History

Each schedule maintains a complete execution history including:
- Execution timestamp
- Success/failure status
- Created event ID (if successful)
- Error message (if failed)
- Execution context and variables

### Success Rate Tracking

Schedules track success rates for monitoring:
- Total executions attempted
- Successful executions
- Failure rate and common error patterns

### Performance Metrics

The background processor tracks:
- Processing time per schedule
- Queue size and processing delays
- Error rates and recovery times

## Best Practices

### Schedule Design

1. **Clear Naming**: Use descriptive names that indicate frequency and purpose
2. **Reasonable Frequency**: Avoid overly frequent schedules that might spam users
3. **Template Testing**: Use preview functionality to test templates before activation
4. **Timezone Awareness**: Always specify timezones for consistent scheduling

### Template Design

1. **Variable Usage**: Use variables to make templates dynamic and informative
2. **Game Selection**: Include appropriate default games for your community
3. **Description Clarity**: Write clear descriptions that explain the event purpose
4. **Length Limits**: Keep titles under 100 characters and descriptions under 2000

### Maintenance

1. **Regular Review**: Periodically review active schedules for relevance
2. **Error Monitoring**: Check execution history for recurring failures
3. **Performance**: Monitor schedule count and execution times
4. **User Feedback**: Gather feedback on automated events and adjust templates

## Troubleshooting

### Common Issues

**Schedule Not Executing**
- Check schedule status (must be ACTIVE)
- Verify next trigger time is in the past
- Check bot permissions for event creation
- Review error logs for specific failures

**Template Rendering Issues**
- Verify variable names match available context
- Check for special characters that might break rendering
- Test templates using preview functionality

**Permission Errors**
- Ensure bot has necessary Discord permissions
- Verify user permissions for schedule management
- Check guild-specific permission configurations

### Debug Information

Enable debug logging to see:
- Schedule processing details
- Template rendering steps
- Event creation attempts
- Error stack traces

## API Reference

### RecurringSchedule Model

```python
class RecurringSchedule:
    id: ObjectId
    guild_id: str
    name: str
    description: Optional[str]
    creator_id: str
    trigger: ScheduleTrigger
    template: EventTemplate
    status: ScheduleStatus
    next_trigger: Optional[datetime]
    execution_history: List[ExecutionHistory]
    execution_count: int
    max_executions: Optional[int]
```

### ScheduleTrigger Model

```python
class ScheduleTrigger:
    trigger_type: TriggerType  # WEEKLY, MONTHLY, CUSTOM
    day_of_week: Optional[int]  # 0-6 for weekly
    day_of_month: Optional[int]  # 1-31 for monthly
    trigger_time: time
    timezone: str
    weeks_between: int  # For multi-week intervals
    months_between: int  # For multi-month intervals
```

### EventTemplate Model

```python
class EventTemplate:
    title_template: str
    description_template: Optional[str]
    default_games: List[str]
    duration_minutes: Optional[int]
    tags: List[str]
    variables: Dict[str, str]  # Custom variables
```

This comprehensive recurring events system provides powerful automation capabilities while maintaining flexibility and ease of use for Discord server administrators.