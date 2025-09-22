# Discord Game Night Scheduling Bot - Technical Specification

## Project Overview

A Discord bot designed to facilitate scheduling game nights for groups of friends through automated polling, event creation, and notification management. The bot will use Python with py-cord and MongoDB for data persistence, deployed via Docker with a comprehensive web dashboard for configuration and management.

## Core Objectives

- Automate the process of scheduling game nights through democratic polling
- Integrate with Discord's native event system
- Provide flexible notification and reminder systems
- Support both one-time and recurring events
- Maintain user preferences and attendance history
- Enable easy deployment for other communities
- Provide comprehensive web-based administration interface

## Functional Requirements

### 1. Command Structure & Organization

#### 1.1 Command Hierarchy
All commands use the `/mft` prefix with subcommand groups:

**Event Management Commands (`/mft event`)**
- `/mft event create [title] [description]` - Start interactive event creation workflow
- `/mft event list [upcoming|past|all]` - Display events with pagination
- `/mft event details <event_id>` - Show detailed event information
- `/mft event cancel <event_id>` - Cancel an event (organizer/admin only)
- `/mft event edit <event_id>` - Modify event details (organizer/admin only)
- `/mft event template save <name>` - Save current event as template
- `/mft event template use <name>` - Create event from template
- `/mft event export <event_id>` - Generate .ics calendar file

**Recurring Event Commands (`/mft recurring`)**
- `/mft recurring create` - Set up new recurring event schedule
- `/mft recurring list` - Show all recurring schedules
- `/mft recurring edit <schedule_id>` - Modify recurring schedule
- `/mft recurring pause <schedule_id>` - Temporarily disable schedule
- `/mft recurring resume <schedule_id>` - Re-enable paused schedule
- `/mft recurring delete <schedule_id>` - Remove recurring schedule

**User Preference Commands (`/mft user`)**
- `/mft user preferences` - Open preferences configuration modal
- `/mft user timezone <timezone>` - Set user timezone
- `/mft user availability` - Configure general availability schedule
- `/mft user notifications` - Configure notification preferences
- `/mft user stats` - View personal attendance statistics
- `/mft user games add <game_name>` - Add game to interest list
- `/mft user games remove <game_name>` - Remove game from interest list
- `/mft user games list` - Show current game interests

**Game Notification Commands (`/mft games`)**
- `/mft games ping <game_name>` - Ping users interested in specific game
- `/mft games popular` - Show most requested games
- `/mft games search <partial_name>` - Find games in database

**Admin Commands (`/mft admin`)**
- `/mft admin config` - Open server configuration interface
- `/mft admin roles set <permission_level> <discord_role>` - Map Discord roles to bot permissions
- `/mft admin channels set <channel_type> <discord_channel>` - Configure bot channels
- `/mft admin backup create` - Manual database backup
- `/mft admin backup restore <backup_file>` - Restore from backup
- `/mft admin stats server` - Server-wide statistics
- `/mft admin migrate` - Run database migrations
- `/mft admin maintenance <enable|disable>` - Toggle maintenance mode

**Utility Commands (`/mft utils`)**
- `/mft utils help [command]` - Detailed command help
- `/mft utils ping` - Bot responsiveness test
- `/mft utils version` - Bot version and status information

#### 1.2 Command Interaction Flows

**Event Creation Workflow:**
1. User: `/mft event create "Monthly Game Night" "Description"`
2. Bot: Shows modal for basic event details (if not provided)
3. Bot: Creates date selection embed with buttons for next 30 days
4. Users: Click dates they're available
5. Bot: After poll closes, creates time selection for winning date(s)
6. Users: Select preferred time slots
7. Bot: Creates game selection multi-select dropdown
8. Users: Vote for games to play
9. Bot: Creates Discord scheduled event and posts summary
10. Bot: Generates .ics file and posts download link

**Recurring Event Setup Workflow:**
1. User: `/mft recurring create`
2. Bot: Opens configuration modal with fields:
   - Schedule name
   - Trigger date (day of month)
   - Poll duration
   - Auto-close vs manual
   - Notification channel
   - Default title template
3. Bot: Confirms settings and activates schedule
4. Bot: Schedules first poll trigger in database

### 2. Event Management System

#### 2.1 Event States & Transitions
Events progress through explicit states with defined transitions:

**Event States:**
- `DRAFT` - Event created but polling not started
- `DATE_POLLING` - Users voting on available dates
- `TIME_POLLING` - Users selecting times for chosen date(s)
- `GAME_POLLING` - Users voting on games to play
- `PENDING_APPROVAL` - Waiting for admin approval (if required)
- `SCHEDULED` - Discord event created, waiting for event date
- `ACTIVE` - Event is currently happening
- `COMPLETED` - Event finished, attendance recorded
- `CANCELLED` - Event cancelled at any stage

**State Transition Rules:**
- Only organizers/admins can move from `DRAFT` to `DATE_POLLING`
- Polls auto-advance after timeout or manual admin advancement
- `CANCELLED` state can be reached from any state by organizer/admin
- Failed Discord event creation moves to `FAILED` state with admin notification

#### 2.2 Poll Management Details

**Date Poll Configuration:**
```json
{
  "type": "date_selection",
  "duration_hours": 168, // 1 week default
  "auto_close": true,
  "options": ["2025-09-15", "2025-09-16", "2025-09-22"],
  "min_votes": 1,
  "winner_selection": "majority" // or "admin_choice"
}
```

**Time Poll Configuration:**
```json
{
  "type": "time_selection", 
  "selected_date": "2025-09-15",
  "time_slots": ["18:00", "19:00", "20:00"],
  "timezone_display": "user_local", // show times in user's timezone
  "duration_hours": 48
}
```

**Game Poll Configuration:**
```json
{
  "type": "game_selection",
  "selection_type": "multiple", // users can vote for multiple games
  "max_selections": 3,
  "allow_write_ins": true,
  "game_suggestions": ["Minecraft", "Among Us", "Jackbox Games"]
}
```

#### 2.3 Discord Event Integration
**Event Creation Parameters:**
- **Name**: From event title or template
- **Description**: Includes selected games, organizer, RSVP instructions
- **Start Time**: Converted to UTC from selected time/timezone
- **Location**: Discord voice channel (configurable)
- **Cover Image**: Optional, configurable per server

**Event Sync Requirements:**
- Bot maintains mapping between internal event ID and Discord event ID
- Changes to Discord event trigger bot event updates
- Bot event cancellation removes Discord event
- RSVP status synced bidirectionally where possible

### 3. Recurring Event Automation

#### 3.1 Scheduling Engine
**Trigger System:**
- Cron-like scheduling stored in database
- Daily check at configurable time (default: 00:00 UTC)
- Identifies scheduled poll triggers for current date
- Creates new events with configured templates

**Configuration Schema:**
```json
{
  "schedule_id": "monthly_game_night",
  "guild_id": "123456789",
  "channel_id": "987654321",
  "trigger_day": 20, // 20th of each month
  "poll_duration_hours": 168,
  "template": {
    "title": "Monthly Game Night - {month} {year}",
    "description": "Our monthly community game night!",
    "default_games": ["Minecraft", "Among Us"]
  },
  "notification_settings": {...},
  "is_active": true,
  "next_trigger": "2025-09-20T00:00:00Z"
}
```

**Automation Workflow:**
1. Daily scheduler identifies active recurring events due for trigger
2. Creates new event in `DRAFT` state with template data
3. Automatically advances to `DATE_POLLING` state
4. Sends notification to configured channel
5. Follows standard event workflow from that point
6. Calculates and schedules next trigger date

### 4. User Management & Permissions

#### 4.1 Permission System Implementation
**Role Mapping Configuration:**
```json
{
  "guild_id": "123456789",
  "role_mappings": {
    "admin": ["123456789012345678"], // Discord role IDs
    "organizer": ["234567890123456789", "345678901234567890"],
    "user": ["@everyone"] // special case for default role
  },
  "command_permissions": {
    "/mft admin": ["admin"],
    "/mft event create": ["admin", "organizer", "user"],
    "/mft event cancel": ["admin", "organizer", "event_creator"],
    "/mft recurring": ["admin", "organizer"]
  }
}
```

**Permission Check Logic:**
1. Check user's Discord roles in current server
2. Map Discord roles to bot permission levels
3. Verify command permission requirements
4. Special case: "event_creator" permission for users who created specific events
5. Admin users can override all permissions

#### 4.2 User Profile Management
**User Data Schema:**
```json
{
  "_id": "ObjectId",
  "user_id": "discord_user_id",
  "guild_id": "discord_guild_id", 
  "profile": {
    "timezone": "America/New_York",
    "display_timezone": true,
    "availability": {
      "monday": {"available": false},
      "tuesday": {"available": true, "preferred_times": ["19:00", "20:00"]},
      "wednesday": {"available": true, "preferred_times": ["19:00", "20:00"]},
      "thursday": {"available": true, "preferred_times": ["19:00", "20:00"]},
      "friday": {"available": true, "preferred_times": ["19:00", "20:00"]},
      "saturday": {"available": true, "preferred_times": ["14:00", "15:00", "19:00", "20:00"]},
      "sunday": {"available": true, "preferred_times": ["14:00", "15:00", "19:00", "20:00"]}
    }
  },
  "preferences": {
    "notification_channels": ["dm", "server"], // where to receive notifications
    "reminder_times": [168, 24, 2], // hours before event
    "auto_rsvp": false // automatically RSVP yes if available
  },
  "game_interests": ["Minecraft", "Among Us", "Jackbox Games"],
  "attendance_history": [
    {
      "event_id": "ObjectId",
      "rsvp_status": "yes",
      "attended": true,
      "event_date": "2025-08-15T20:00:00Z"
    }
  ],
  "statistics": {
    "events_attended": 15,
    "events_missed": 3,
    "attendance_rate": 0.83,
    "favorite_games": ["Minecraft", "Among Us"]
  },
  "created_at": "2025-08-16T10:30:00Z",
  "updated_at": "2025-08-16T10:30:00Z"
}
```

### 5. Notification & Reminder System

#### 5.1 Notification Engine Architecture
**Notification Queue System:**
```python
# Notification types and their handling
NOTIFICATION_TYPES = {
    "event_reminder": {
        "template": "Reminder: {event_title} starts in {time_until}",
        "channels": ["dm", "notification_channel"],
        "scheduling": "time_based"
    },
    "poll_closing": {
        "template": "Poll for {event_title} closes in {time_until}",
        "channels": ["notification_channel"],
        "scheduling": "time_based"
    },
    "game_ping": {
        "template": "{requester} is looking for players for {game_name}!",
        "channels": ["notification_channel"],
        "scheduling": "immediate"
    },
    "admin_alert": {
        "template": "Admin Alert: {alert_message}",
        "channels": ["admin_channel", "dm_admins"],
        "scheduling": "immediate"
    }
}
```

**Scheduling Logic:**
1. Event creation triggers reminder scheduling based on user preferences
2. Reminders stored in database with execution timestamp
3. Background task checks for due notifications every minute
4. Failed notification delivery triggers retry with exponential backoff
5. Max 3 retry attempts before marking as failed

#### 5.2 Game Notification System
**Interest Registration:**
```json
{
  "user_id": "123456789",
  "game_name": "Minecraft", // normalized name
  "aliases": ["minecraft", "MC"], // fuzzy matching options
  "registered_date": "2025-08-16T10:30:00Z",
  "notification_count": 5 // how many times they've been notified
}
```

**Ping Logic:**
1. User runs `/mft games ping "Minecraft"`
2. Bot searches for exact match in game interests
3. If no exact match, suggests close matches with buttons to select
4. On confirmation, bot mentions all interested users
5. Updates notification count for analytics

### 6. Web Dashboard Specification

#### 6.1 Authentication & Security
**Discord OAuth Integration:**
- **Pros**: Seamless user experience, automatic permission sync, no separate accounts
- **Cons**: Dependency on Discord availability, OAuth scope requirements
- **Implementation**: Use Discord OAuth2 with guilds scope for server access verification

**Security Measures:**
- JWT tokens for session management
- CSRF protection on all forms
- Rate limiting on API endpoints
- Input validation and sanitization
- Audit logging for admin actions

#### 6.2 Dashboard Features & Pages

**Authentication Flow:**
1. User visits dashboard URL
2. "Login with Discord" button initiates OAuth flow
3. Discord redirects with authorization code
4. Bot exchanges code for access token
5. Dashboard verifies user's server membership and permissions
6. Creates session JWT with user permissions embedded

**Main Navigation Structure:**
```
Dashboard Home
├── Events
│   ├── Upcoming Events
│   ├── Event History  
│   ├── Create Event
│   └── Event Templates
├── Recurring Schedules
│   ├── Active Schedules
│   ├── Schedule History
│   └── Create Schedule
├── Users & Permissions
│   ├── User Management
│   ├── Role Configuration
│   └── Permission Settings
├── Analytics & Reports
│   ├── Attendance Reports
│   ├── Popular Games
│   └── User Engagement
├── Configuration
│   ├── Server Settings
│   ├── Notification Settings
│   ├── Channel Configuration
│   └── Backup & Restore
└── System
    ├── Bot Status
    ├── Logs
    └── Maintenance
```

**Detailed Page Specifications:**

**Events Dashboard:**
- Calendar view with event cards
- Filter/search functionality (date range, creator, status)
- Quick actions: Edit, Cancel, Duplicate, Export
- Real-time status updates via WebSocket or polling
- Event details modal with poll results and attendance

**User Management:**
- Paginated user list with search and filters
- Bulk permission updates
- User activity summaries
- Individual user detail view with attendance history

**Analytics Dashboard:**
- Interactive charts (Chart.js or similar)
- Attendance trends over time
- Most popular games with play frequency
- User engagement metrics
- Exportable reports (CSV/PDF)

**Configuration Interface:**
- Form-based settings with validation
- Real-time preview of changes
- Import/export configuration files
- Settings version history

#### 6.3 API Endpoints
**RESTful API Structure:**
```
GET    /api/events                 - List events with pagination/filters
POST   /api/events                 - Create new event  
GET    /api/events/{id}            - Get event details
PUT    /api/events/{id}            - Update event
DELETE /api/events/{id}            - Cancel event

GET    /api/users                  - List users with filters
GET    /api/users/{id}             - Get user profile
PUT    /api/users/{id}/preferences - Update user preferences

GET    /api/config                 - Get server configuration
PUT    /api/config                 - Update server configuration

GET    /api/analytics/attendance   - Attendance statistics
GET    /api/analytics/games        - Game popularity statistics
GET    /api/analytics/engagement   - User engagement metrics

POST   /api/admin/backup           - Create backup
POST   /api/admin/restore          - Restore from backup
GET    /api/admin/logs             - Get system logs
```

### 7. Timestamp Conversion Cog

#### 7.1 Standalone Utility Functions
**Command Structure:**
- `/timestamp convert <input_time> [from_timezone] [to_timezone]` - Convert between timezones
- `/timestamp discord <input_time> [timezone]` - Generate Discord timestamp format
- `/timestamp now [timezone]` - Current time in specified timezone
- `/timestamp formats` - Show available timestamp format examples

**Implementation Details:**
```python
# Discord timestamp formats
DISCORD_FORMATS = {
    "short_time": "t",      # 4:20 PM
    "long_time": "T",       # 4:20:30 PM  
    "short_date": "d",      # 20/04/2021
    "long_date": "D",       # 20 April 2021
    "short_datetime": "f",  # 20 April 2021 4:20 PM
    "long_datetime": "F",   # Tuesday, 20 April 2021 4:20 PM
    "relative": "R"         # 2 months ago
}
```

**Usage Examples:**
- `/timestamp convert "2025-09-15 8:00 PM" America/New_York UTC`
- `/timestamp discord "tomorrow 7 PM" America/Los_Angeles` 
- `/timestamp now Europe/London`

### 8. Database Desimft Details

#### 8.1 Complete Schema Definitions

**Events Collection:**
```json
{
  "_id": "ObjectId",
  "guild_id": "str",
  "discord_event_id": "str|null",
  "title": "str",
  "description": "str",
  "creator_id": "str",
  "organizer_ids": ["str"], // can have multiple organizers
  
  "state": "enum[DRAFT, DATE_POLLING, TIME_POLLING, GAME_POLLING, PENDING_APPROVAL, SCHEDULED, ACTIVE, COMPLETED, CANCELLED, FAILED]",
  
  "schedule": {
    "selected_date": "date|null",
    "selected_time": "time|null", 
    "timezone": "str",
    "duration_minutes": "int|null"
  },
  
  "polls": {
    "date_poll": {
      "is_active": "bool",
      "closes_at": "datetime|null",
      "options": [
        {
          "date": "date",
          "votes": ["user_id"],
          "vote_count": "int"
        }
      ],
      "winner": "date|null"
    },
    "time_poll": {
      "is_active": "bool", 
      "closes_at": "datetime|null",
      "options": [
        {
          "time": "time",
          "votes": ["user_id"], 
          "vote_count": "int"
        }
      ],
      "winner": "time|null"
    },
    "game_poll": {
      "is_active": "bool",
      "closes_at": "datetime|null", 
      "allow_multiple": "bool",
      "allow_write_ins": "bool",
      "options": [
        {
          "game_name": "str",
          "votes": ["user_id"],
          "vote_count": "int"
        }
      ],
      "winners": ["str"]
    }
  },
  
  "rsvp_data": {
    "yes": ["user_id"],
    "no": ["user_id"], 
    "maybe": ["user_id"]
  },
  
  "attendance": {
    "expected": ["user_id"], // those who RSVP'd yes
    "actual": ["user_id"],   // those who actually attended
    "recorded": "bool",
    "recorded_by": "user_id|null",
    "recorded_at": "datetime|null"
  },
  
  "recurring_config": {
    "is_recurring": "bool",
    "parent_schedule_id": "ObjectId|null",
    "next_occurrence": "datetime|null"
  },
  
  "notification_config": {
    "reminder_times": ["int"], // hours before event
    "notification_channel": "str|null",
    "sent_reminders": [
      {
        "time": "int", // hours before
        "sent_at": "datetime",
        "recipients": ["user_id"]
      }
    ]
  },
  
  "metadata": {
    "created_at": "datetime",
    "updated_at": "datetime", 
    "version": "int", // for migration tracking
    "source": "enum[MANUAL, RECURRING, TEMPLATE]",
    "template_id": "ObjectId|null"
  }
}
```

**Recurring Schedules Collection:**
```json
{
  "_id": "ObjectId",
  "guild_id": "str",
  "name": "str",
  "description": "str",
  "creator_id": "str",
  
  "schedule": {
    "trigger_type": "enum[MONTHLY, WEEKLY, CUSTOM]",
    "trigger_day": "int", // day of month for monthly, day of week for weekly
    "trigger_time": "time", // time of day to start poll
    "timezone": "str"
  },
  
  "poll_config": {
    "duration_hours": "int",
    "auto_close": "bool",
    "require_approval": "bool"
  },
  
  "template": {
    "title_template": "str", // supports {month}, {year}, {date} variables
    "description_template": "str",
    "default_games": ["str"],
    "default_duration_minutes": "int"
  },
  
  "notification_config": {
    "channel_id": "str",
    "mention_roles": ["str"],
    "reminder_schedule": ["int"]
  },
  
  "execution_history": [
    {
      "triggered_at": "datetime",
      "event_id": "ObjectId",
      "success": "bool",
      "error_message": "str|null"
    }
  ],
  
  "status": {
    "is_active": "bool",
    "next_trigger": "datetime",
    "last_triggered": "datetime|null",
    "pause_reason": "str|null",
    "paused_by": "user_id|null",
    "paused_at": "datetime|null"
  },
  
  "metadata": {
    "created_at": "datetime",
    "updated_at": "datetime",
    "created_by": "str"
  }
}
```

### 9. Error Handling & Edge Cases

#### 9.1 Specific Failure Scenarios & Responses

**Discord Event Creation Failure:**
1. Bot attempts to create Discord scheduled event
2. If failure occurs (rate limit, permissions, etc.):
   - Wait 30 seconds, retry once
   - If second attempt fails:
     - Mark event state as `FAILED`
     - Send alert to admin channel: "Failed to create Discord event for '{event_title}'. Event ID: {internal_id}. Error: {error_message}"
     - Log full error details to system logs
     - Event remains in system for manual admin intervention

**Database Connection Loss:**
1. Implement connection pooling with automatic reconnection
2. Exponential backoff retry strategy: 1s, 2s, 4s, 8s, 16s, max 60s
3. Queue critical operations (notifications, event state changes) during outages
4. Process queued operations when connection restored
5. Admin alert if connection loss exceeds 5 minutes

**Bot Restart/Crash Recovery:**
1. On startup, bot performs recovery check:
   - Find events in `DATE_POLLING`, `TIME_POLLING`, or `GAME_POLLING` states with expired close times
   - Automatically advance these polls or mark for admin review
   - Check for missed notification triggers and reschedule
   - Verify recurring event schedules and catch up any missed triggers
2. Recovery log sent to admin channel with summary of actions taken

**User Permission Edge Cases:**
- User loses server permissions while event is active: Event continues, user loses management access
- Event creator leaves server: Event ownership transfers to admin or remains orphaned (configurable)
- Role mappings change: Permissions updated on next command use, no retroactive changes

**Poll Edge Cases:**
- Tie votes: Configurable behavior (admin choice, runoff poll, or cancel)
- No votes received: Admin notification, option to extend poll or cancel
- All voters leave server: Event automatically cancelled with notification
- Discord outage during poll: Poll automatically extended by outage duration

#### 9.2 Data Consistency & Validation

**Input Validation Rules:**
```python
VALIDATION_RULES = {
    "event_title": {
        "max_length": 100,
        "min_length": 3,
        "forbidden_chars": ["@", "#", ":", "```"]
    },
    "event_description": {
        "max_length": 2000,
        "allow_empty": True
    },
    "game_name": {
        "max_length": 50,
        "min_length": 1,
        "normalize": "title_case"
    },
    "timezone": {
        "validate": "pytz.timezone",
        "fallback": "UTC"
    },
    "date_selection": {
        "min_date": "today",
        "max_date": "today + 365 days",
        "format": "YYYY-MM-DD"
    }
}
```

**Database Transaction Requirements:**
- Event state changes must be atomic
- Poll vote recording must handle concurrent access
- RSVP updates must maintain consistency between bot and Discord
- Recurring event generation must prevent duplicates

### 10. Multi-Server Deployment Considerations

#### 10.1 Database Schema for Multi-Server
**Server Isolation:**
- All collections include `guild_id` field as part of compound indexes
- Separate configuration per server
- Isolated user profiles per server (users can have different settings per server)
- Cross-server analytics disabled by default

**Migration Strategy:**
```python
# Migration system for schema changes
MIGRATIONS = {
    "v1.0_to_v1.1": {
        "description": "Add notification_config to events",
        "operations": [
            {
                "collection": "events",
                "operation": "add_field",
                "field": "notification_config",
                "default": {"reminder_times": [24], "sent_reminders": []}
            }
        ]
    }
}
```

#### 10.2 Configuration Management
**Server-Specific Settings:**
```json
{
  "guild_id": "123456789",
  "bot_config": {
    "command_prefix": "/mft",
    "default_timezone": "America/New_York",
    "max_concurrent_events": 5,
    "poll_duration_default_hours": 168
  },
  "channels": {
    "admin_alerts": "123456789",
    "notifications": "234567890", 
    "event_announcements": "345678901"
  },
  "roles": {
    "admin": ["123456789"],
    "organizer": ["234567890"],
    "muted": ["345678901"] // users who can't create events
  },
  "features": {
    "recurring_events": true,
    "web_dashboard": true,
    "game_notifications": true,
    "automatic_reminders": true
  }
}
```

## Technical Implementation Details

### 11. Cog Architecture & Inter-Communication

#### 11.1 Event Bus System
```python
# Centralized event system for cross-cog communication
class BotEventBus:
    def __init__(self):
        self.listeners = defaultdict(list)
    
    def register(self, event_type: str, callback: callable):
        self.listeners[event_type].append(callback)
    
    def emit(self, event_type: str, data: dict):
        for callback in self.listeners[event_type]:
            await callback(data)

# Event types
EVENTS = {
    "event.created": "New event created",
    "event.state_changed": "Event moved to new state", 
    "poll.vote_received": "User voted in poll",
    "poll.closed": "Poll voting period ended",
    "user.rsvp_changed": "User RSVP status updated",
    "notification.scheduled": "New notification scheduled",
    "recurring.triggered": "Recurring event triggered"
}
```

#### 11.2 Database Access Layer
```python
# Shared database utilities
class DatabaseManager:
    def __init__(self, mongo_client):
        self.client = mongo_client
        self.db = mongo_client.gamenight_bot
    
    async def get_user_profile(self, user_id: str, guild_id: str):
        # Standardized user profile retrieval
        pass
    
    async def update_event_state(self, event_id: str, new_state: str):
        # Atomic state transitions with validation
        pass
    
    async def record_vote(self, poll_id: str, user_id: str, option: str):
        # Concurrent-safe vote recording
        pass
```

### 12. Performance & Scalability Considerations

#### 12.1 Database Optimization
**Indexing Strategy:**
```python
# Required indexes for performance
INDEXES = {
    "events": [
        {"guild_id": 1, "state": 1, "created_at": -1},
        {"guild_id": 1, "discord_event_id": 1},
        {"guild_id": 1, "schedule.selected_date": 1}
    ],
    "users": [
        {"user_id": 1, "guild_id": 1},
        {"guild_id": 1, "game_interests": 1}
    ],
    "recurring_schedules": [
        {"guild_id": 1, "status.is_active": 1, "status.next_trigger": 1}
    ],
    "notifications": [
        {"scheduled_for": 1, "processed": 1}
    ]
}
```

**Query Optimization:**
- Use projection to limit returned fields
- Implement pagination for all list operations
- Cache frequently accessed data (server configs, user preferences)
- Use aggregation pipelines for complex reports

#### 12.2 Resource Management
**Memory Usage:**
- Limit concurrent poll processing
- Implement command cooldowns to prevent spam
- Cache user permissions to avoid repeated Discord API calls
- Regular cleanup of expired poll data

**Rate Limit Handling:**
- Implement Discord API rate limit respect
- Queue non-urgent operations during rate limits  
- Prioritize critical operations (event creation, notifications)
- Admin alerts when rate limits cause significant delays

### 13. Testing & Quality Assurance

#### 13.1 Test Coverage Requirements
**Unit Tests:**
- Database operations and data validation
- Poll logic and state transitions
- Permission checking and role mapping
- Timezone conversion and date handling
- Notification scheduling and delivery

**Integration Tests:**
- Complete event creation workflows
- Recurring event automation
- Discord API integration
- Web dashboard API endpoints
- Multi-user poll scenarios

**End-to-End Tests:**
- Full event lifecycle from creation to completion
- User permission scenarios
- Error handling and recovery
- Cross-timezone event coordination

#### 13.2 Monitoring & Observability
**Metrics Collection:**
- Command usage frequency
- Event success/failure rates  
- User engagement levels
- System resource usage
- Error rates by operation type

**Health Checks:**
- Database connectivity
- Discord API responsiveness
- Notification queue processing
- Web dashboard availability
- Recurring event scheduler status

**Logging Strategy:**
```python
# Structured logging for better monitoring
LOG_LEVELS = {
    "DEBUG": "Detailed execution flow, variable values",
    "INFO": "Normal operations, user actions, event milestones", 
    "WARNING": "Recoverable errors, rate limits, validation failures",
    "ERROR": "Operation failures, API errors, data inconsistencies",
    "CRITICAL": "System failures, security issues, data corruption"
}

# Log format
{
    "timestamp": "2025-08-16T15:30:00.123Z",
    "level": "INFO",
    "component": "EventsCog",
    "action": "event_created",
    "guild_id": "123456789",
    "user_id": "987654321", 
    "event_id": "60a7c8b5c9d4e2f1a8b3c4d5",
    "message": "New event created: Monthly Game Night",
    "metadata": {
        "execution_time_ms": 45,
        "discord_api_calls": 2
    }
}
```

## Deployment & Infrastructure

### 14. Docker Configuration & Orchestration

#### 14.1 Container Architecture
**Multi-Container Setup:**
```yaml
# docker-compose.yml
version: '3.8'

services:
  gamenight-bot:
    build: .
    container_name: gamenight-bot
    restart: unless-stopped
    environment:
      - DISCORD_TOKEN=${DISCORD_TOKEN}
      - MONGODB_URI=mongodb://mongo:27017/gamenight_bot
      - WEB_DASHBOARD_PORT=8080
      - REDIS_URL=redis://redis:6379
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
      - ./backups:/app/backups
    ports:
      - "8080:8080"
    depends_on:
      - mongo
      - redis
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8080/health')"]
      interval: 30s
      timeout: 10s
      retries: 3

  mongo:
    image: mongo:6.0
    container_name: gamenight-mongo
    restart: unless-stopped
    environment:
      - MONGO_INITDB_DATABASE=gamenight_bot
    volumes:
      - mongodb_data:/data/db
      - ./mongo-init:/docker-entrypoint-initdb.d
    ports:
      - "27017:27017"
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      retries: 3

  redis:
    image: redis:7-alpine
    container_name: gamenight-redis
    restart: unless-stopped
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3

  web-dashboard:
    build:
      context: .
      dockerfile: Dockerfile.dashboard
    container_name: gamenight-dashboard
    restart: unless-stopped
    environment:
      - API_BASE_URL=http://gamenight-bot:8080/api
      - DISCORD_CLIENT_ID=${DISCORD_CLIENT_ID}
      - DISCORD_CLIENT_SECRET=${DISCORD_CLIENT_SECRET}
      - JWT_SECRET=${JWT_SECRET}
    ports:
      - "3000:3000"
    depends_on:
      - gamenight-bot

volumes:
  mongodb_data:
  redis_data:
```

#### 14.2 Configuration Management
**Environment Variables:**
```bash
# .env file structure
# Discord Configuration
DISCORD_TOKEN=your_bot_token_here
DISCORD_CLIENT_ID=your_client_id_here
DISCORD_CLIENT_SECRET=your_client_secret_here

# Database Configuration
MONGODB_URI=mongodb://mongo:27017/gamenight_bot
REDIS_URL=redis://redis:6379

# Application Configuration
ENVIRONMENT=production
LOG_LEVEL=INFO
WEB_DASHBOARD_PORT=8080
JWT_SECRET=your_jwt_secret_here
BACKUP_RETENTION_DAYS=30

# Optional External Services
SENTRY_DSN=your_sentry_dsn_here
WEBHOOK_URL=your_monitoring_webhook_here
```

**Configuration File Structure:**
```yaml
# config/default.yaml
bot:
  name: "GameNight Bot"
  version: "1.0.0"
  description: "Discord Game Night Scheduling Bot"
  
  # Command configuration
  commands:
    prefix: "/mft"
    cooldown_seconds: 3
    max_concurrent_polls: 10
  
  # Feature toggles
  features:
    web_dashboard: true
    recurring_events: true
    game_notifications: true
    calendar_export: true
    analytics: true

# Server defaults (can be overridden per guild)
defaults:
  timezone: "UTC"
  poll_duration_hours: 168
  reminder_times: [168, 24, 2]  # week, day, 2 hours before
  max_events_per_user: 5
  max_recurring_schedules: 3
  
  # Notification settings
  notifications:
    admin_channel_required: true
    default_reminder_channel: "general"
    dm_notifications: true
  
  # Poll settings
  polls:
    auto_close: true
    min_votes_required: 1
    tie_resolution: "admin_choice"  # or "runoff_poll"
    vote_change_allowed: true

# System configuration
system:
  # Database settings
  database:
    connection_timeout_ms: 5000
    retry_attempts: 3
    backup_schedule: "0 2 * * *"  # Daily at 2 AM
  
  # Performance settings
  performance:
    cache_ttl_seconds: 300
    max_concurrent_operations: 50
    rate_limit_per_user: 30  # commands per minute
  
  # Logging configuration
  logging:
    level: "INFO"
    file_path: "/app/logs/gamenight.log"
    max_file_size_mb: 100
    backup_count: 5
    format: "json"

# Web dashboard configuration
dashboard:
  port: 8080
  host: "0.0.0.0"
  secret_key: "${JWT_SECRET}"
  session_timeout_hours: 24
  
  # OAuth settings
  oauth:
    discord_client_id: "${DISCORD_CLIENT_ID}"
    discord_client_secret: "${DISCORD_CLIENT_SECRET}"
    redirect_uri: "http://localhost:3000/auth/callback"
    scopes: ["identify", "guilds"]
  
  # API settings
  api:
    rate_limit_per_hour: 1000
    enable_cors: true
    cors_origins: ["http://localhost:3000"]
```

### 15. Backup & Recovery Strategy

#### 15.1 Automated Backup System
**Backup Script Implementation:**
```python
# backup_manager.py
import asyncio
from datetime import datetime, timedelta
import subprocess
import os
import logging

class BackupManager:
    def __init__(self, config):
        self.mongodb_uri = config['mongodb_uri']
        self.backup_dir = config['backup_dir']
        self.retention_days = config['retention_days']
    
    async def create_backup(self):
        """Create full MongoDB backup"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f"{self.backup_dir}/gamenight_backup_{timestamp}"
        
        try:
            # Create MongoDB dump
            subprocess.run([
                'mongodump',
                '--uri', self.mongodb_uri,
                '--out', backup_path
            ], check=True)
            
            # Compress backup
            subprocess.run([
                'tar', '-czf', f"{backup_path}.tar.gz",
                '-C', self.backup_dir,
                f"gamenight_backup_{timestamp}"
            ], check=True)
            
            # Remove uncompressed backup
            subprocess.run(['rm', '-rf', backup_path], check=True)
            
            logging.info(f"Backup created successfully: {backup_path}.tar.gz")
            
            # Cleanup old backups
            await self.cleanup_old_backups()
            
        except subprocess.CalledProcessError as e:
            logging.error(f"Backup failed: {e}")
            raise
    
    async def cleanup_old_backups(self):
        """Remove backups older than retention period"""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        
        for filename in os.listdir(self.backup_dir):
            if filename.startswith('gamenight_backup_') and filename.endswith('.tar.gz'):
                # Extract timestamp from filename
                timestamp_str = filename.replace('gamenight_backup_', '').replace('.tar.gz', '')
                try:
                    file_date = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                    if file_date < cutoff_date:
                        os.remove(os.path.join(self.backup_dir, filename))
                        logging.info(f"Deleted old backup: {filename}")
                except ValueError:
                    logging.warning(f"Could not parse backup filename: {filename}")
```

**Backup Schedule Configuration:**
```yaml
# Cron job for automated backups
# In docker-compose.yml, add to gamenight-bot service:
command: >
  sh -c "
    echo '0 2 * * * /app/scripts/backup.sh' | crontab - &&
    python -m bot.main
  "
```

#### 15.2 Data Recovery Procedures
**Recovery Script:**
```python
# recovery_manager.py
class RecoveryManager:
    def __init__(self, config):
        self.mongodb_uri = config['mongodb_uri']
        self.backup_dir = config['backup_dir']
    
    async def restore_from_backup(self, backup_filename):
        """Restore database from backup file"""
        backup_path = os.path.join(self.backup_dir, backup_filename)
        
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"Backup file not found: {backup_path}")
        
        try:
            # Extract backup
            extract_dir = backup_path.replace('.tar.gz', '')
            subprocess.run([
                'tar', '-xzf', backup_path,
                '-C', self.backup_dir
            ], check=True)
            
            # Restore database
            subprocess.run([
                'mongorestore',
                '--uri', self.mongodb_uri,
                '--drop',  # Drop existing collections
                extract_dir
            ], check=True)
            
            logging.info(f"Database restored successfully from {backup_filename}")
            
            # Cleanup extracted files
            subprocess.run(['rm', '-rf', extract_dir], check=True)
            
        except subprocess.CalledProcessError as e:
            logging.error(f"Restore failed: {e}")
            raise
    
    async def verify_data_integrity(self):
        """Verify database integrity after restore"""
        # Check for required collections
        # Verify indexes exist
        # Run data consistency checks
        pass
```

### 16. Security Implementation

#### 16.1 Input Validation & Sanitization
**Comprehensive Validation System:**
```python
# validation.py
import re
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import pytz

class ValidationError(Exception):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")

class InputValidator:
    # Validation rules
    RULES = {
        'event_title': {
            'required': True,
            'min_length': 3,
            'max_length': 100,
            'forbidden_patterns': [r'@everyone', r'@here', r'<@&\d+>'],  # No mass mentions
            'forbidden_chars': ['`', '\\n', '\\r']
        },
        'event_description': {
            'required': False,
            'max_length': 2000,
            'forbidden_patterns': [r'@everyone', r'@here'],
            'allow_markdown': True
        },
        'game_name': {
            'required': True,
            'min_length': 1,
            'max_length': 50,
            'normalize': 'title_case',
            'forbidden_chars': ['<', '>', '@', '#']
        },
        'timezone': {
            'required': True,
            'validate_timezone': True,
            'fallback': 'UTC'
        },
        'user_id': {
            'required': True,
            'pattern': r'^\d{17,19},  # Discord snowflake format
            'type': 'string'
        }
    }
    
    @classmethod
    def validate_field(cls, field_name: str, value: Any) -> Any:
        """Validate individual field"""
        if field_name not in cls.RULES:
            return value
        
        rules = cls.RULES[field_name]
        
        # Required check
        if rules.get('required', False) and not value:
            raise ValidationError(field_name, "Field is required")
        
        if not value and not rules.get('required', False):
            return rules.get('fallback', value)
        
        # Type conversion
        if rules.get('type') == 'string' and not isinstance(value, str):
            value = str(value)
        
        # Length validation
        if isinstance(value, str):
            if rules.get('min_length') and len(value) < rules['min_length']:
                raise ValidationError(field_name, f"Minimum length is {rules['min_length']}")
            if rules.get('max_length') and len(value) > rules['max_length']:
                raise ValidationError(field_name, f"Maximum length is {rules['max_length']}")
        
        # Pattern validation
        if rules.get('pattern'):
            if not re.match(rules['pattern'], str(value)):
                raise ValidationError(field_name, "Invalid format")
        
        # Forbidden patterns
        for pattern in rules.get('forbidden_patterns', []):
            if re.search(pattern, str(value), re.IGNORECASE):
                raise ValidationError(field_name, "Contains forbidden content")
        
        # Forbidden characters
        for char in rules.get('forbidden_chars', []):
            if char in str(value):
                raise ValidationError(field_name, f"Contains forbidden character: {char}")
        
        # Special validations
        if rules.get('validate_timezone') and value:
            try:
                pytz.timezone(value)
            except pytz.UnknownTimeZoneError:
                raise ValidationError(field_name, "Invalid timezone")
        
        # Normalization
        if rules.get('normalize') == 'title_case' and isinstance(value, str):
            value = value.title()
        
        return value
    
    @classmethod
    def validate_event_data(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate complete event creation data"""
        validated = {}
        
        for field, value in data.items():
            try:
                validated[field] = cls.validate_field(field, value)
            except ValidationError:
                raise
        
        # Cross-field validation
        if 'start_date' in validated and 'end_date' in validated:
            if validated['start_date'] >= validated['end_date']:
                raise ValidationError('end_date', "End date must be after start date")
        
        return validated
```

#### 16.2 Permission Security
**Advanced Permission Checking:**
```python
# permissions.py
from enum import Enum
from typing import List, Dict, Optional
import discord

class PermissionLevel(Enum):
    USER = 1
    ORGANIZER = 2  
    ADMIN = 3
    BOT_OWNER = 4

class SecurityManager:
    def __init__(self, bot):
        self.bot = bot
        self.permission_cache = {}  # Cache permissions for performance
        self.cache_ttl = 300  # 5 minutes
    
    async def check_permission(self, user: discord.User, guild: discord.Guild, 
                              required_level: PermissionLevel, 
                              resource_id: Optional[str] = None) -> bool:
        """Check if user has required permission level"""
        
        # Bot owner override
        if user.id == self.bot.owner_id:
            return True
        
        # Check cache first
        cache_key = f"{guild.id}:{user.id}:{required_level.value}"
        if cache_key in self.permission_cache:
            cached_time, result = self.permission_cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                return result
        
        # Get user's permission level
        user_level = await self.get_user_permission_level(user, guild)
        
        # Resource-specific checks (e.g., event creator)
        if resource_id and required_level == PermissionLevel.ORGANIZER:
            if await self.is_resource_creator(user.id, resource_id):
                user_level = max(user_level, PermissionLevel.ORGANIZER)
        
        # Check permission
        result = user_level.value >= required_level.value
        
        # Cache result
        self.permission_cache[cache_key] = (time.time(), result)
        
        return result
    
    async def get_user_permission_level(self, user: discord.User, 
                                       guild: discord.Guild) -> PermissionLevel:
        """Determine user's permission level in guild"""
        
        # Get guild configuration
        guild_config = await self.bot.database.get_guild_config(guild.id)
        role_mappings = guild_config.get('role_mappings', {})
        
        member = guild.get_member(user.id)
        if not member:
            return PermissionLevel.USER
        
        # Check for admin permissions
        if member.guild_permissions.administrator:
            return PermissionLevel.ADMIN
        
        # Check role mappings
        user_roles = [role.id for role in member.roles]
        
        for role_id in user_roles:
            if str(role_id) in role_mappings.get('admin', []):
                return PermissionLevel.ADMIN
            elif str(role_id) in role_mappings.get('organizer', []):
                return PermissionLevel.ORGANIZER
        
        return PermissionLevel.USER
    
    async def is_resource_creator(self, user_id: str, resource_id: str) -> bool:
        """Check if user created the resource (event, schedule, etc.)"""
        # Check in database if user is creator of resource
        resource = await self.bot.database.get_resource_creator(resource_id)
        return resource and resource.get('creator_id') == str(user_id)

# Decorator for command permission checking
def require_permission(level: PermissionLevel, resource_param: str = None):
    def decorator(func):
        async def wrapper(cog, ctx, *args, **kwargs):
            # Extract resource ID if specified
            resource_id = None
            if resource_param and resource_param in kwargs:
                resource_id = kwargs[resource_param]
            
            # Check permission
            has_permission = await cog.bot.security.check_permission(
                ctx.author, ctx.guild, level, resource_id
            )
            
            if not has_permission:
                await ctx.respond("You don't have permission to use this command.", ephemeral=True)
                return
            
            return await func(cog, ctx, *args, **kwargs)
        return wrapper
    return decorator
```

### 17. Monitoring & Observability

#### 17.1 Metrics Collection System
**Performance Monitoring:**
```python
# metrics.py
import time
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import asyncio

class MetricsCollector:
    def __init__(self):
        self.command_counts = Counter()
        self.response_times = defaultdict(list)
        self.error_counts = Counter()
        self.active_events = defaultdict(int)
        self.notification_stats = {
            'sent': 0,
            'failed': 0,
            'retry_count': 0
        }
        self.database_stats = {
            'queries': 0,
            'avg_query_time': 0.0,
            'connection_errors': 0
        }
    
    def record_command(self, command_name: str, execution_time: float, success: bool):
        """Record command execution metrics"""
        self.command_counts[command_name] += 1
        self.response_times[command_name].append(execution_time)
        
        if not success:
            self.error_counts[command_name] += 1
    
    def record_event_state_change(self, guild_id: str, old_state: str, new_state: str):
        """Track event lifecycle metrics"""
        if new_state == 'SCHEDULED':
            self.active_events[guild_id] += 1
        elif old_state == 'SCHEDULED' and new_state in ['COMPLETED', 'CANCELLED']:
            self.active_events[guild_id] = max(0, self.active_events[guild_id] - 1)
    
    def get_summary(self) -> dict:
        """Get comprehensive metrics summary"""
        now = datetime.now()
        
        # Calculate average response times
        avg_response_times = {}
        for command, times in self.response_times.items():
            if times:
                avg_response_times[command] = sum(times) / len(times)
        
        # Calculate error rates
        error_rates = {}
        for command in self.command_counts:
            total = self.command_counts[command]
            errors = self.error_counts.get(command, 0)
            error_rates[command] = (errors / total) * 100 if total > 0 else 0
        
        return {
            'timestamp': now.isoformat(),
            'commands': {
                'total_executed': sum(self.command_counts.values()),
                'counts_by_command': dict(self.command_counts),
                'avg_response_times': avg_response_times,
                'error_rates': error_rates
            },
            'events': {
                'active_by_guild': dict(self.active_events),
                'total_active': sum(self.active_events.values())
            },
            'notifications': self.notification_stats.copy(),
            'database': self.database_stats.copy()
        }

# Context manager for timing operations
class Timer:
    def __init__(self, metrics_collector: MetricsCollector, operation_name: str):
        self.metrics = metrics_collector
        self.operation = operation_name
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        execution_time = time.time() - self.start_time
        success = exc_type is None
        self.metrics.record_command(self.operation, execution_time, success)
```

#### 17.2 Health Monitoring System
**Comprehensive Health Checks:**
```python
# health_monitor.py
import asyncio
import aiohttp
from datetime import datetime
from enum import Enum

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"  
    UNHEALTHY = "unhealthy"

class HealthMonitor:
    def __init__(self, bot):
        self.bot = bot
        self.checks = {}
        self.overall_status = HealthStatus.HEALTHY
        self.last_check = None
    
    async def register_check(self, name: str, check_func: callable, 
                           timeout: int = 30, critical: bool = True):
        """Register a health check function"""
        self.checks[name] = {
            'func': check_func,
            'timeout': timeout,
            'critical': critical,
            'last_result': None,
            'last_run': None
        }
    
    async def run_health_checks(self) -> dict:
        """Execute all registered health checks"""
        results = {}
        critical_failures = 0
        total_failures = 0
        
        for name, check_info in self.checks.items():
            try:
                # Run check with timeout
                result = await asyncio.wait_for(
                    check_info['func'](), 
                    timeout=check_info['timeout']
                )
                
                results[name] = {
                    'status': 'pass',
                    'result': result,
                    'timestamp': datetime.now().isoformat()
                }
                check_info['last_result'] = True
                
            except asyncio.TimeoutError:
                results[name] = {
                    'status': 'timeout',
                    'error': f"Check timed out after {check_info['timeout']}s",
                    'timestamp': datetime.now().isoformat()
                }
                check_info['last_result'] = False
                total_failures += 1
                if check_info['critical']:
                    critical_failures += 1
                    
            except Exception as e:
                results[name] = {
                    'status': 'fail',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                }
                check_info['last_result'] = False
                total_failures += 1
                if check_info['critical']:
                    critical_failures += 1
            
            check_info['last_run'] = datetime.now()
        
        # Determine overall status
        if critical_failures > 0:
            self.overall_status = HealthStatus.UNHEALTHY
        elif total_failures > 0:
            self.overall_status = HealthStatus.DEGRADED
        else:
            self.overall_status = HealthStatus.HEALTHY
        
        self.last_check = datetime.now()
        
        return {
            'status': self.overall_status.value,
            'timestamp': self.last_check.isoformat(),
            'checks': results,
            'summary': {
                'total_checks': len(self.checks),
                'passed': len(self.checks) - total_failures,
                'failed': total_failures,
                'critical_failures': critical_failures
            }
        }

# Health check implementations
async def check_database_connectivity(bot):
    """Verify database connection and basic operations"""
    try:
        # Simple ping to database
        await bot.database.client.admin.command('ping')
        
        # Test basic operations
        test_doc = {'test': True, 'timestamp': datetime.now()}
        result = await bot.database.db.health_checks.insert_one(test_doc)
        await bot.database.db.health_checks.delete_one({'_id': result.inserted_id})
        
        return "Database connectivity verified"
    except Exception as e:
        raise Exception(f"Database connectivity failed: {e}")

async def check_discord_api(bot):
    """Verify Discord API connectivity"""
    try:
        # Test basic Discord API call
        latency = bot.latency
        if latency > 1.0:  # High latency warning
            return f"Discord API responsive but high latency: {latency:.2f}s"
        return f"Discord API responsive, latency: {latency:.3f}s"
    except Exception as e:
        raise Exception(f"Discord API check failed: {e}")

async def check_notification_queue(bot):
    """Verify notification system is processing"""
    pending_notifications = await bot.database.get_pending_notifications()
    overdue_count = len([n for n in pending_notifications 
                        if n['scheduled_for'] < datetime.now() - timedelta(minutes=10)])
    
    if overdue_count > 10:
        raise Exception(f"Too many overdue notifications: {overdue_count}")
    
    return f"Notification queue healthy, {len(pending_notifications)} pending, {overdue_count} overdue"

async def check_recurring_events(bot):
    """Verify recurring event scheduler is working"""
    missed_schedules = await bot.database.get_missed_recurring_schedules()
    
    if len(missed_schedules) > 0:
        raise Exception(f"Missed recurring schedules detected: {len(missed_schedules)}")
    
    return "Recurring event scheduler healthy"
```

## Implementation Roadmap

### 18. Development Phases with Detailed Milestones

#### 18.1 Phase 1: Foundation & Infrastructure (Weeks 1-3)
**Week 1: Project Setup**
- [ ] Initialize repository with proper structure
- [ ] Set up Docker development environment
- [ ] Configure MongoDB with initial collections
- [ ] Implement basic bot framework with py-cord
- [ ] Create configuration management system
- [ ] Set up logging and error handling framework

**Week 2: Database Layer**
- [ ] Implement database models for all collections
- [ ] Create data access layer with connection pooling
- [ ] Implement basic CRUD operations
- [ ] Add database migration system
- [ ] Create backup and restore functionality
- [ ] Write comprehensive database tests

**Week 3: Core Bot Structure**
- [ ] Implement cog loading system
- [ ] Create event bus for inter-cog communication
- [ ] Build permission and security framework
- [ ] Implement input validation system  
- [ ] Create health monitoring foundation
- [ ] Set up metrics collection system

**Deliverables:**
- Working bot that can connect to Discord
- Database system with full CRUD operations
- Configuration management working
- Basic logging and monitoring in place

#### 18.2 Phase 2: Event Management Core (Weeks 4-7)
**Week 4: Basic Event System**
- [ ] Implement Event model and database operations
- [ ] Create `/mft event create` command with modal interface
- [ ] Build basic event display with embeds
- [ ] Implement event state management system
- [ ] Create event cancellation functionality

**Week 5: Polling System**
- [ ] Implement date selection polling with buttons
- [ ] Create time selection system
- [ ] Build game selection with multi-select
- [ ] Add poll management (close, extend, override)
- [ ] Implement vote recording and conflict resolution

**Week 6: Discord Integration**  
- [ ] Integrate with Discord scheduled events API
- [ ] Implement bidirectional RSVP synchronization
- [ ] Create event update propagation system
- [ ] Add Discord event failure handling
- [ ] Build calendar (.ics) export functionality

**Week 7: Event Management Commands**
- [ ] Complete all `/mft event` subcommands
- [ ] Implement event templates system
- [ ] Create event editing interface
- [ ] Add event history and statistics
- [ ] Build admin override capabilities

**Deliverables:**
- Complete event creation workflow
- Working poll system with Discord integration
- Event management commands functional
- Discord scheduled event integration working

#### 18.3 Phase 3: User System & Permissions (Weeks 8-10)
**Week 8: User Profiles**
- [ ] Implement user profile system
- [ ] Create timezone preference management
- [ ] Build availability scheduling interface
- [ ] Add user statistics tracking
- [ ] Implement game interest registration

**Week 9: Permission System**
- [ ] Complete role mapping functionality
- [ ] Implement permission checking decorators
- [ ] Create admin configuration commands
- [ ] Build permission override system
- [ ] Add resource-specific permissions (event creators)

**Week 10: User Commands**
- [ ] Implement all `/mft user` commands
- [ ] Create preference configuration interface
- [ ] Build user statistics display
- [ ] Add timezone conversion utilities
- [ ] Complete game interest management

**Deliverables:**
- Complete user profile system
- Working permission framework
- User preference management
- Role-based access control functional

#### 18.4 Phase 4: Advanced Features (Weeks 11-15)

**Week 11: Notification System**
- [ ] Implement notification scheduling engine
- [ ] Create reminder delivery system
- [ ] Build notification preference management
- [ ] Add multi-channel notification support
- [ ] Implement notification retry logic with exponential backoff

**Week 12: Recurring Events**
- [ ] Create recurring schedule configuration
- [ ] Implement automated event generation
- [ ] Build recurring event management interface
- [ ] Add schedule pause/resume functionality
- [ ] Create recurring event analytics

**Week 13: Game Notification System**
- [ ] Implement game interest registration
- [ ] Create game ping functionality with fuzzy matching
- [ ] Build game database with aliases
- [ ] Add game popularity tracking
- [ ] Implement notification frequency controls

**Week 14: Timestamp Utilities**
- [ ] Create standalone timestamp conversion cog
- [ ] Implement Discord timestamp formatting
- [ ] Add timezone conversion utilities
- [ ] Build timestamp parsing and validation
- [ ] Create timezone detection helpers

**Week 15: Calendar & Export Features**
- [ ] Complete .ics file generation
- [ ] Implement calendar view formatting
- [ ] Create event export functionality
- [ ] Add calendar integration helpers
- [ ] Build event synchronization tools

**Deliverables:**
- Complete notification system
- Recurring events fully functional
- Game notification system working
- Calendar integration complete

#### 18.5 Phase 5: Web Dashboard (Weeks 16-20)

**Week 16: Dashboard Foundation**
- [ ] Set up Flask/FastAPI web framework
- [ ] Implement Discord OAuth authentication
- [ ] Create basic dashboard layout and navigation
- [ ] Build JWT session management
- [ ] Add CSRF protection and security headers

**Week 17: Core Dashboard Pages**
- [ ] Create events dashboard with calendar view
- [ ] Implement user management interface
- [ ] Build configuration management pages
- [ ] Add real-time status indicators
- [ ] Create responsive layout framework

**Week 18: Advanced Dashboard Features**
- [ ] Implement analytics and reporting pages
- [ ] Create interactive charts and visualizations
- [ ] Build export functionality (CSV, PDF)
- [ ] Add configuration import/export
- [ ] Implement advanced filtering and search

**Week 19: API Development**
- [ ] Complete RESTful API endpoints
- [ ] Add API authentication and rate limiting
- [ ] Implement WebSocket for real-time updates
- [ ] Create API documentation
- [ ] Add API versioning support

**Week 20: Dashboard Polish**
- [ ] Improve UI/UX with modern components
- [ ] Add mobile responsiveness improvements
- [ ] Implement dark mode support
- [ ] Create user onboarding flow
- [ ] Add comprehensive error handling

**Deliverables:**
- Complete web dashboard with all features
- RESTful API with documentation
- OAuth authentication working
- Analytics and reporting functional

#### 18.6 Phase 6: Testing & Deployment (Weeks 21-24)

**Week 21: Comprehensive Testing**
- [ ] Write unit tests for all core functions
- [ ] Create integration tests for workflows
- [ ] Implement end-to-end testing scenarios
- [ ] Add load testing for performance validation
- [ ] Create automated test CI/CD pipeline

**Week 22: Performance Optimization**
- [ ] Optimize database queries and indexing
- [ ] Implement caching strategies
- [ ] Optimize Discord API usage
- [ ] Improve memory usage and cleanup
- [ ] Add performance monitoring alerts

**Week 23: Documentation & Deployment**
- [ ] Create comprehensive deployment documentation
- [ ] Write user guides and admin documentation
- [ ] Create Docker deployment configs
- [ ] Build automated deployment scripts
- [ ] Test multi-server deployment scenarios

**Week 24: Final Polish & Release**
- [ ] Fix remaining bugs and edge cases
- [ ] Implement user feedback improvements
- [ ] Create release packages and versioning
- [ ] Set up monitoring and alerting
- [ ] Prepare for community release

**Deliverables:**
- Fully tested and documented system
- Production-ready deployment
- Complete user and admin documentation
- Community-ready release packages

## Quality Assurance & Testing Strategy

### 19. Testing Framework & Coverage

#### 19.1 Unit Testing Strategy
**Test Coverage Requirements:**
```python
# test_structure.py
# Minimum 90% code coverage for critical components

TEST_CATEGORIES = {
    "database_operations": {
        "coverage_target": 95,
        "tests": [
            "test_event_crud_operations",
            "test_user_profile_management", 
            "test_concurrent_vote_recording",
            "test_data_validation_rules",
            "test_database_migration_scripts"
        ]
    },
    "event_management": {
        "coverage_target": 90,
        "tests": [
            "test_event_creation_workflow",
            "test_poll_state_transitions",
            "test_discord_integration_sync",
            "test_event_cancellation_cascade",
            "test_recurring_event_generation"
        ]
    },
    "permission_system": {
        "coverage_target": 95,
        "tests": [
            "test_role_mapping_validation",
            "test_permission_inheritance",
            "test_resource_ownership_checks",
            "test_admin_override_functionality"
        ]
    },
    "notification_system": {
        "coverage_target": 85,
        "tests": [
            "test_reminder_scheduling",
            "test_notification_delivery_retry",
            "test_multi_channel_distribution",
            "test_user_preference_filtering"
        ]
    }
}

# Example comprehensive test
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta

@pytest.mark.asyncio
class TestEventCreationWorkflow:
    async def test_complete_event_creation_flow(self):
        """Test full event creation from start to Discord integration"""
        # Setup mocks
        mock_bot = Mock()
        mock_database = AsyncMock()
        mock_discord_api = AsyncMock()
        
        # Test data
        event_data = {
            "title": "Test Game Night",
            "description": "Testing event creation",
            "creator_id": "123456789",
            "guild_id": "987654321"
        }
        
        # Test event creation
        event_manager = EventManager(mock_bot, mock_database)
        
        # Step 1: Create draft event
        event_id = await event_manager.create_event(event_data)
        assert event_id is not None
        mock_database.insert_event.assert_called_once()
        
        # Step 2: Start date polling
        await event_manager.start_date_poll(event_id, date_options=["2025-09-15", "2025-09-16"])
        mock_database.update_event_state.assert_called_with(event_id, "DATE_POLLING")
        
        # Step 3: Record votes
        await event_manager.record_vote(event_id, "date_poll", "123456789", "2025-09-15")
        await event_manager.record_vote(event_id, "date_poll", "987654321", "2025-09-15")
        
        # Step 4: Close poll and advance
        await event_manager.close_poll(event_id, "date_poll")
        mock_database.update_event_state.assert_called_with(event_id, "TIME_POLLING")
        
        # Step 5: Complete time and game polls
        await event_manager.record_vote(event_id, "time_poll", "123456789", "20:00")
        await event_manager.close_poll(event_id, "time_poll")
        
        await event_manager.record_vote(event_id, "game_poll", "123456789", "Minecraft")
        await event_manager.close_poll(event_id, "game_poll")
        
        # Step 6: Create Discord event
        with patch.object(event_manager, 'create_discord_event', new=AsyncMock()) as mock_create:
            mock_create.return_value = "discord_event_123"
            await event_manager.finalize_event(event_id)
            mock_create.assert_called_once()
            mock_database.update_event_state.assert_called_with(event_id, "SCHEDULED")
    
    async def test_event_creation_with_discord_failure(self):
        """Test error handling when Discord event creation fails"""
        # Setup for Discord API failure
        mock_bot = Mock()
        mock_database = AsyncMock()
        
        event_manager = EventManager(mock_bot, mock_database)
        
        with patch.object(event_manager, 'create_discord_event', 
                         side_effect=discord.HTTPException(Mock(), Mock())) as mock_create:
            
            # Should retry once then fail
            result = await event_manager.finalize_event("test_event_id")
            
            assert mock_create.call_count == 2  # Initial + 1 retry
            mock_database.update_event_state.assert_called_with("test_event_id", "FAILED")
            # Should also send admin notification
            mock_database.create_admin_notification.assert_called_once()
    
    @pytest.mark.parametrize("invalid_input,expected_error", [
        ("", "Event title is required"),
        ("a" * 101, "Event title too long"),
        ("Test @everyone", "Event title contains forbidden content"),
        (None, "Event title is required")
    ])
    async def test_event_validation_errors(self, invalid_input, expected_error):
        """Test input validation for event creation"""
        event_data = {
            "title": invalid_input,
            "description": "Valid description",
            "creator_id": "123456789",
            "guild_id": "987654321"
        }
        
        event_manager = EventManager(Mock(), AsyncMock())
        
        with pytest.raises(ValidationError) as exc_info:
            await event_manager.create_event(event_data)
        
        assert expected_error in str(exc_info.value)
```

#### 19.2 Integration Testing
**Multi-Component Test Scenarios:**
```python
# test_integration.py
@pytest.mark.integration
class TestCompleteUserJourney:
    async def test_user_joins_creates_attends_event(self):
        """Test complete user journey from joining server to attending event"""
        # Setup test environment with real database
        async with TestEnvironment() as env:
            bot = env.bot
            user = env.create_test_user()
            guild = env.create_test_guild()
            
            # Step 1: User joins server and sets preferences
            await bot.get_cog('UserCog').setup_user_preferences(
                user.id, guild.id, 
                {"timezone": "America/New_York", "availability": {...}}
            )
            
            # Step 2: User creates event
            event_id = await bot.get_cog('EventsCog').create_event(
                guild.id, user.id, "Integration Test Event"
            )
            
            # Step 3: Other users vote in polls
            other_users = [env.create_test_user() for _ in range(3)]
            for other_user in other_users:
                await bot.get_cog('EventsCog').record_vote(
                    event_id, "date_poll", other_user.id, "2025-09-15"
                )
            
            # Step 4: Poll closes automatically
            await env.advance_time(days=7)  # Simulate poll duration
            await bot.get_cog('EventsCog').process_expired_polls()
            
            # Step 5: Event gets finalized and Discord event created
            event = await bot.database.get_event(event_id)
            assert event['state'] == 'SCHEDULED'
            assert event['discord_event_id'] is not None
            
            # Step 6: Reminders sent
            await env.advance_time(days=6)  # Day before event
            notifications = await bot.database.get_sent_notifications(event_id)
            assert len(notifications) > 0
            
            # Step 7: Event occurs and attendance recorded
            await env.advance_time(days=1)
            await bot.get_cog('EventsCog').record_attendance(
                event_id, [user.id] + [u.id for u in other_users[:2]]
            )
            
            # Verify final state
            final_event = await bot.database.get_event(event_id)
            assert final_event['state'] == 'COMPLETED'
            assert len(final_event['attendance']['actual']) == 3
```

### 20. Performance Benchmarks & Optimization

#### 20.1 Performance Requirements
**Response Time Targets:**
```python
PERFORMANCE_TARGETS = {
    "command_response_time": {
        "simple_commands": "< 500ms",     # /mft user stats
        "database_queries": "< 1000ms",   # /mft event list
        "complex_operations": "< 3000ms", # /mft event create
        "discord_api_calls": "< 2000ms"   # Discord event creation
    },
    "concurrent_users": {
        "simultaneous_commands": 50,      # Commands executed concurrently
        "poll_participation": 100,        # Users voting simultaneously
        "notification_delivery": 1000     # Concurrent notification sending
    },
    "resource_usage": {
        "memory_usage": "< 512MB",        # Peak memory consumption
        "cpu_usage": "< 80%",            # During normal operation
        "database_connections": "< 20",   # Connection pool size
        "discord_rate_limits": "< 80%"   # Rate limit utilization
    }
}
```

**Load Testing Scenarios:**
```python
# load_test.py
import asyncio
import aiohttp
import time
from concurrent.futures import ThreadPoolExecutor

class LoadTestRunner:
    def __init__(self, base_url, concurrent_users=50):
        self.base_url = base_url
        self.concurrent_users = concurrent_users
        self.results = {
            'total_requests': 0,
            'successful_requests': 0, 
            'failed_requests': 0,
            'response_times': [],
            'errors': []
        }
    
    async def simulate_user_session(self, user_id: int):
        """Simulate a complete user session"""
        async with aiohttp.ClientSession() as session:
            try:
                # Login
                start_time = time.time()
                async with session.post(f"{self.base_url}/auth/login",
                                       json={"user_id": f"test_user_{user_id}"}) as resp:
                    if resp.status == 200:
                        self.results['successful_requests'] += 1
                    else:
                        self.results['failed_requests'] += 1
                        self.results['errors'].append(f"Login failed: {resp.status}")
                
                login_time = time.time() - start_time
                self.results['response_times'].append(login_time)
                
                # Create event
                start_time = time.time()
                async with session.post(f"{self.base_url}/api/events",
                                       json={
                                           "title": f"Load Test Event {user_id}",
                                           "description": "Testing concurrent event creation"
                                       }) as resp:
                    if resp.status == 201:
                        event_data = await resp.json()
                        event_id = event_data['id']
                        self.results['successful_requests'] += 1
                    else:
                        self.results['failed_requests'] += 1
                        return
                
                create_time = time.time() - start_time
                self.results['response_times'].append(create_time)
                
                # Vote in poll
                await asyncio.sleep(1)  # Simulate user thinking time
                start_time = time.time()
                async with session.post(f"{self.base_url}/api/events/{event_id}/vote",
                                       json={
                                           "poll_type": "date_poll",
                                           "option": "2025-09-15"
                                       }) as resp:
                    vote_time = time.time() - start_time
                    self.results['response_times'].append(vote_time)
                    
                    if resp.status == 200:
                        self.results['successful_requests'] += 1
                    else:
                        self.results['failed_requests'] += 1
                
                self.results['total_requests'] += 3  # login, create, vote
                
            except Exception as e:
                self.results['errors'].append(f"Session error: {str(e)}")
                self.results['failed_requests'] += 1
    
    async def run_load_test(self, duration_seconds=300):
        """Run load test for specified duration"""
        start_time = time.time()
        
        while time.time() - start_time < duration_seconds:
            # Create batch of concurrent users
            tasks = [
                self.simulate_user_session(i) 
                for i in range(self.concurrent_users)
            ]
            
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Brief pause between batches
            await asyncio.sleep(5)
        
        return self.generate_report()
    
    def generate_report(self):
        """Generate performance test report"""
        if not self.results['response_times']:
            return {"error": "No successful requests recorded"}
        
        response_times = self.results['response_times']
        
        return {
            "summary": {
                "total_requests": self.results['total_requests'],
                "successful_requests": self.results['successful_requests'],
                "failed_requests": self.results['failed_requests'],
                "success_rate": (self.results['successful_requests'] / 
                               max(1, self.results['total_requests'])) * 100
            },
            "performance": {
                "avg_response_time": sum(response_times) / len(response_times),
                "min_response_time": min(response_times),
                "max_response_time": max(response_times),
                "p95_response_time": sorted(response_times)[int(len(response_times) * 0.95)],
                "requests_per_second": self.results['successful_requests'] / 
                                     max(1, len(response_times))
            },
            "errors": self.results['errors'][:10]  # First 10 errors
        }
```

## Conclusion & Success Criteria

### 21. Project Success Metrics

#### 21.1 Technical Success Criteria
- **Reliability**: 99.5% uptime with graceful degradation during outages
- **Performance**: All commands respond within defined SLA targets  
- **Scalability**: Support for 100+ concurrent users per server
- **Data Integrity**: Zero data loss with automated backup/recovery
- **Security**: No unauthorized access or data breaches
- **Compatibility**: Works across all major Discord clients and platforms

#### 21.2 User Experience Success Criteria  
- **Adoption**: 80%+ of server members participate in events
- **Retention**: Users continue using bot after 30 days
- **Satisfaction**: Positive feedback on ease of use and functionality
- **Efficiency**: Reduces time to organize events by 50%+ vs manual methods
- **Accessibility**: All features work with screen readers and accessibility tools

#### 21.3 Community Success Criteria
- **Deployment**: Easy installation process for non-technical users
- **Documentation**: Complete guides enable self-service setup and troubleshooting  
- **Maintenance**: Minimal ongoing maintenance required (< 2 hours/month)
- **Extensibility**: Clear APIs enable community contributions and customizations
- **Support**: Active community support with response times < 24 hours

### 22. Risk Assessment & Mitigation

#### 22.1 Technical Risks
| Risk | Impact | Probability | Mitigation Strategy |
|------|---------|-------------|-------------------|
| Discord API Changes | High | Medium | Version pinning, API monitoring, fallback implementations |
| Database Corruption | High | Low | Automated backups, replication, transaction logging |
| Performance Degradation | Medium | Medium | Load testing, monitoring, horizontal scaling capability |
| Security Vulnerabilities | High | Medium | Regular security audits, input validation, dependency updates |
| Hosting Failures | Medium | Medium | Multi-region deployment option, local deployment capability |

#### 22.2 User Adoption Risks  
| Risk | Impact | Probability | Mitigation Strategy |
|------|---------|-------------|-------------------|
| Complex User Interface | High | Medium | User testing, progressive disclosure, comprehensive tutorials |
| Feature Overload | Medium | Medium | Configurable features, default simplicity, gradual feature introduction |
| Migration Friction | Medium | Low | Import tools, migration guides, parallel operation support |
| Learning Curve | Medium | Medium | Interactive onboarding, contextual help, video tutorials |

### 23. Future Roadmap & Extensions

#### 23.1 Version 1.1 Planned Features
- **Mobile App Integration**: Companion mobile app for notifications and quick RSVP
- **Voice Channel Integration**: Automatic voice channel creation and management  
- **Game Library Integration**: API connections to Steam, Xbox Live, PlayStation Network
- **Advanced Analytics**: Machine learning for optimal event timing predictions
- **Multi-language Support**: Internationalization for non-English communities

#### 23.2 Long-term Vision
- **Cross-platform Expansion**: Support for Slack, Microsoft Teams, other platforms
- **Event Marketplace**: Community sharing of event templates and configurations
- **Integration Ecosystem**: Plugin system for community-developed extensions  
- **Enterprise Features**: Multi-organization management, advanced reporting, SSO
- **AI-Powered Scheduling**: Intelligent scheduling based on user preferences and patterns

---

## Document Maintenance

**Last Updated**: August 16, 2025
**Version**: 2.0 
**Next Review**: September 16, 2025

**Change Log**:
- v2.0: Complete rewrite with explicit AI-usable specifications
- v1.0: Initial specification document

**Reviewers**: 
- Project Lead: [Name]
- Technical Lead: [Name] 
- Community Representative: [Name]

**Approval**: 
- [ ] Technical requirements approved
- [ ] Resource allocation confirmed  
- [ ] Timeline feasibility validated
- [ ] Risk assessment completed

This specification document serves as the definitive guide for implementing the Discord Game Night Scheduling Bot. It provides explicit, actionable requirements suitable for AI-assisted development while maintaining flexibility for iterative improvements based on user feedback and technical discoveries during implementation.
