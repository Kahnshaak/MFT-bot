# Users Cog Documentation

## Overview

The Users cog provides comprehensive user profile and preference management for the Discord Game Night Scheduling Bot. It handles user onboarding, timezone preferences, availability scheduling, notification settings, game interests, and statistics tracking.

## Features

### 1. User Profile Management
- **Profile Creation**: Automatic profile creation for new users
- **Profile Display**: Rich embeds showing user information and statistics
- **Data Export**: GDPR-compliant data export functionality
- **Privacy Controls**: Public/private profile and statistics settings

### 2. Timezone Management
- **Timezone Setting**: Support for all standard timezones
- **Automatic Conversion**: All times displayed in user's timezone
- **Validation**: Comprehensive timezone validation with helpful error messages

### 3. Availability Scheduling
- **Weekly Patterns**: Set recurring weekly availability slots
- **Conflict Detection**: Prevents overlapping availability slots
- **Visual Display**: Clear calendar-style availability display
- **Flexible Management**: Add/remove individual slots easily

### 4. Notification Preferences
- **Channel Selection**: Choose between DM, server, both, or none
- **Timing Options**: Immediate, hour before, day before, or week before
- **Quiet Hours**: Set do-not-disturb periods
- **Frequency Limits**: Prevent notification spam

### 5. Game Interest Management
- **Interest Registration**: Add games with interest levels (1-10)
- **Notification Control**: Enable/disable notifications per game
- **Interest Analytics**: Track favorite games and play frequency
- **Fuzzy Matching**: Smart game name matching and suggestions

### 6. Statistics Tracking
- **Event Participation**: Track events created, attended, and RSVP'd
- **Attendance Rate**: Calculate and display attendance percentage
- **Game Preferences**: Track most played and favorite games
- **Activity History**: Record last active times and participation

### 7. User Onboarding
- **Welcome Flow**: Automated onboarding for new server members
- **Setup Guidance**: Step-by-step profile setup instructions
- **Feature Introduction**: Overview of available commands and features

## Commands

### Profile Commands

#### `/profile`
Display and manage your user profile with interactive buttons.

**Features:**
- View current profile information
- Quick access to timezone, availability, and notification settings
- Statistics overview
- Data export option

#### `/stats`
View detailed game night statistics.

**Information Displayed:**
- Events created, attended, and RSVP statistics
- Attendance rate calculation
- Favorite games list
- Recent activity timestamps

### Preference Commands

#### `/timezone <timezone>`
Set your timezone for automatic time conversion.

**Parameters:**
- `timezone`: Valid timezone (e.g., "America/New_York", "Europe/London", "UTC")

**Examples:**
```
/timezone America/New_York
/timezone Europe/London
/timezone Asia/Tokyo
```

#### `/availability`
Manage your weekly availability schedule with interactive interface.

**Features:**
- View current availability slots
- Add new availability slots via modal
- Remove existing slots via dropdown
- Visual calendar display

#### `/notifications`
Configure notification preferences via interactive modal.

**Settings:**
- **Channel**: Where to receive notifications (DM/SERVER/BOTH/NONE)
- **Timing**: When to receive reminders (IMMEDIATE/HOUR_BEFORE/DAY_BEFORE/WEEK_BEFORE)
- **Quiet Hours**: Optional do-not-disturb period (e.g., "22:00-08:00")

### Game Interest Commands

#### `/games-add <game_name> [interest_level]`
Add a game to your interests list.

**Parameters:**
- `game_name`: Name of the game (required)
- `interest_level`: Interest level 1-10 (optional, default: 5)

**Examples:**
```
/games-add Chess 8
/games-add "Among Us" 7
/games-add Monopoly
```

#### `/games-remove <game_name>`
Remove a game from your interests list.

**Parameters:**
- `game_name`: Name of the game to remove

#### `/games-list`
Display all your game interests with levels and notification settings.

## Interactive Components

### Modals

#### Timezone Modal
- **Timezone Input**: Text field with validation and suggestions
- **Current Value**: Pre-filled with current timezone
- **Validation**: Real-time timezone validation with helpful error messages

#### Availability Modal
- **Day Selection**: Dropdown or text input for day of week
- **Start Time**: Flexible time input (24-hour or 12-hour format)
- **End Time**: Flexible time input with validation
- **Overlap Detection**: Prevents conflicting time slots

#### Notification Preferences Modal
- **Channel Selection**: Dropdown for notification delivery method
- **Timing Selection**: Dropdown for reminder timing
- **Quiet Hours**: Optional time range input

### Views and Buttons

#### Profile View
- **Set Timezone**: Quick timezone setting
- **Add Availability**: Open availability modal
- **Notification Settings**: Open notification preferences
- **Export Data**: Generate GDPR data export

#### Availability Management View
- **Add Slot**: Open availability modal
- **Remove Slot**: Dropdown selection of existing slots

## Data Models

### User Profile Structure
```python
{
    "user_id": "Discord user ID",
    "guild_id": "Discord guild ID",
    "display_name": "User display name",
    "timezone": "User timezone (default: UTC)",
    "availability": [
        {
            "day": "MONDAY|TUESDAY|...",
            "start_time": "HH:MM",
            "end_time": "HH:MM"
        }
    ],
    "notification_preferences": {
        "channel": "DM|SERVER|BOTH|NONE",
        "reminder_timing": "IMMEDIATE|HOUR_BEFORE|DAY_BEFORE|WEEK_BEFORE",
        "quiet_hours_start": "HH:MM",
        "quiet_hours_end": "HH:MM",
        "max_game_pings_per_day": 5
    },
    "game_interests": [
        {
            "game_name": "Game name",
            "interest_level": 1-10,
            "notification_enabled": true,
            "added_at": "timestamp",
            "last_played": "timestamp"
        }
    ],
    "statistics": {
        "events_created": 0,
        "events_attended": 0,
        "events_rsvp_yes": 0,
        "events_rsvp_no": 0,
        "events_rsvp_maybe": 0,
        "attendance_rate": 0.0,
        "favorite_games": ["game1", "game2"],
        "games_played_count": {"game1": 5, "game2": 3}
    }
}
```

## Event System Integration

### Events Emitted

#### User Lifecycle Events
- `USER_ONBOARDED`: When a new user completes onboarding
- `USER_TIMEZONE_UPDATED`: When user changes timezone
- `USER_AVAILABILITY_UPDATED`: When availability is modified
- `USER_PREFERENCES_UPDATED`: When notification preferences change

#### Game Interest Events
- `USER_GAME_INTEREST_ADDED`: When user adds game interest
- `USER_GAME_INTEREST_REMOVED`: When user removes game interest

#### Data Events
- `USER_DATA_EXPORTED`: When user exports their data

### Events Consumed

#### System Events
- `USER_JOINED_GUILD`: Triggers onboarding flow
- `EVENT_RSVP_UPDATED`: Updates RSVP statistics
- `EVENT_COMPLETED`: Updates attendance statistics

## Privacy and GDPR Compliance

### Data Export
- **Complete Export**: All user data in JSON format
- **Structured Format**: Easy to read and process
- **Timestamp Tracking**: Records when export was requested
- **Secure Delivery**: Data sent via ephemeral Discord message

### Privacy Controls
- **Profile Visibility**: Users can make profiles public/private
- **Statistics Visibility**: Separate control for statistics display
- **Data Deletion**: Support for data removal requests

## Error Handling

### Input Validation
- **Timezone Validation**: Comprehensive timezone checking with suggestions
- **Time Format Parsing**: Flexible time input parsing (12/24 hour)
- **Overlap Detection**: Prevents conflicting availability slots
- **Game Name Sanitization**: Removes problematic characters

### User-Friendly Messages
- **Clear Error Messages**: Specific, actionable error descriptions
- **Helpful Suggestions**: Alternative options when input fails
- **Graceful Degradation**: Fallback options when features unavailable

## Performance Considerations

### Database Optimization
- **Efficient Queries**: Optimized database queries with proper indexing
- **Batch Operations**: Bulk updates for statistics
- **Caching Strategy**: In-memory caching for frequently accessed data

### Rate Limiting
- **Command Cooldowns**: Prevent spam of resource-intensive operations
- **Notification Limits**: Built-in frequency limiting for game pings
- **Export Throttling**: Limit data export frequency

## Testing

### Unit Tests
- **Core Functionality**: All major functions have unit tests
- **Edge Cases**: Comprehensive edge case coverage
- **Mock Integration**: Proper mocking of external dependencies

### Integration Tests
- **Bot Loading**: Verify cog loads correctly with bot
- **Command Registration**: Ensure all commands are properly registered
- **Event Handling**: Test event emission and consumption

## Future Enhancements

### Planned Features
- **Calendar Integration**: Export availability to external calendars
- **Advanced Analytics**: More detailed participation analytics
- **Social Features**: Friend connections and shared interests
- **Mobile Optimization**: Better mobile interface support

### Extensibility
- **Plugin Architecture**: Support for custom preference types
- **API Integration**: External service integrations
- **Webhook Support**: External notification delivery
- **Custom Fields**: User-defined profile fields

## Troubleshooting

### Common Issues

#### Timezone Problems
- **Invalid Timezone**: Use standard timezone names from IANA database
- **Display Issues**: Check timezone setting in user profile
- **Conversion Errors**: Verify timezone is properly set

#### Availability Conflicts
- **Overlapping Slots**: Remove conflicting slots before adding new ones
- **Time Format**: Use 24-hour format (HH:MM) or 12-hour with AM/PM
- **Day Selection**: Use full day names (Monday, Tuesday, etc.)

#### Notification Issues
- **Missing Notifications**: Check notification preferences and quiet hours
- **Too Many Notifications**: Adjust frequency limits and game interests
- **Channel Problems**: Verify bot permissions for DM or server messages

### Support Commands
- **Profile Reset**: Contact administrator for profile reset
- **Data Recovery**: Export data before making major changes
- **Permission Issues**: Check bot permissions in server settings