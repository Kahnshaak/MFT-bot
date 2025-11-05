# Design Document

## Overview

A simplified Discord bot for game night scheduling using py-cord and MongoDB. The bot provides a single command (`/event create`) that launches an interactive poll for date and time selection, then automatically creates a Discord Scheduled Event when the poll expires.

## Architecture

### High-Level Flow

```
User runs /event create
    ↓
Modal appears for event title
    ↓
User submits modal
    ↓
Bot creates poll with date/time options
    ↓
Users vote on dates/times (7 days)
    ↓
Poll expires
    ↓
Bot calculates winner
    ↓
Bot creates Discord Scheduled Event
```

### Components

**Bot Core:**
- Discord bot using py-cord
- MongoDB for data persistence
- Background task scheduler for poll expiration

**Event Creation Flow:**
- Slash command handler
- Modal for event details
- Poll generation logic

**Poll System:**
- Interactive buttons/modal for voting
- Vote tracking and counting
- Automatic expiration after 7 days

**Event Scheduling:**
- Winner calculation
- Discord Scheduled Event creation
- Tie handling with admin notification

## Data Models

### Event Document (MongoDB)

```python
{
    "_id": ObjectId,
    "guild_id": str,
    "channel_id": str,
    "message_id": str,  # Poll message ID
    "creator_id": str,
    "title": str,
    "created_at": datetime,
    "expires_at": datetime,
    "status": str,  # "active", "expired", "scheduled"
    "date_votes": {
        "2025-10-15": ["user_id_1", "user_id_2"],
        "2025-10-16": ["user_id_3"]
    },
    "time_votes": {
        "17:00": ["user_id_1"],
        "18:00": ["user_id_2", "user_id_3"]
    },
    "winning_date": str | null,
    "winning_time": str | null,
    "discord_event_id": str | null
}
```

## Components and Interfaces

### Slash Command: `/event create`

**Handler:**
```python
@bot.slash_command(name="event", description="Create a game night event")
async def create_event(ctx):
    # Show modal for event details
    modal = EventCreationModal()
    await ctx.send_modal(modal)
```

**Modal:**
```python
class EventCreationModal(discord.ui.Modal):
    title_input = InputText(label="Event Title", required=True)
    
    async def callback(self, interaction):
        # Create event in database
        # Generate poll with date/time options
        # Send poll message with voting buttons
```

### Poll Generation

**Date Options:**
- Get all remaining dates in current month
- Create button/modal for each date
- Maximum 25 dates (Discord button limit)

**Time Options:**
- Start at 5pm (17:00)
- 1-hour increments: 5pm, 6pm, 7pm, 8pm, 9pm, 10pm, 11pm
- 7 time slots total

**Poll View:**
```python
class PollView(discord.ui.View):
    # Button to open voting modal
    @discord.ui.button(label="Vote", style=primary)
    async def vote_button(self, interaction):
        modal = VoteModal(event_id)
        await interaction.response.send_modal(modal)

class VoteModal(discord.ui.Modal):
    # Checkboxes or multi-select for dates
    # Checkboxes or multi-select for times
    
    async def callback(self, interaction):
        # Save votes to database
        # Update poll message with new counts
```

### Background Task: Poll Expiration

```python
@tasks.loop(minutes=5)
async def check_expired_polls():
    # Find polls where expires_at < now
    # For each expired poll:
    #   - Calculate winning date (most votes)
    #   - Calculate winning time (most votes)
    #   - If tie: send admin notification
    #   - If winner: create Discord Scheduled Event
    #   - Update poll message with results
```

### Winner Calculation

```python
def calculate_winner(votes_dict):
    # Count votes for each option
    # Return option with most votes
    # If tie, return list of tied options
    
    max_votes = max(len(voters) for voters in votes_dict.values())
    winners = [option for option, voters in votes_dict.items() 
               if len(voters) == max_votes]
    
    if len(winners) == 1:
        return winners[0], None  # Clear winner
    else:
        return None, winners  # Tie
```

### Discord Scheduled Event Creation

```python
async def create_scheduled_event(guild, title, date, time):
    # Combine date and time into datetime
    event_time = datetime.combine(date, time)
    
    # Create Discord Scheduled Event
    scheduled_event = await guild.create_scheduled_event(
        name=title,
        start_time=event_time,
        entity_type=discord.EntityType.external,
        location="Discord"
    )
    
    return scheduled_event.id
```

### Admin Notification for Ties

```python
async def notify_admin_of_tie(guild, event, tied_options):
    # Find admin channel or use system channel
    admin_channel = guild.system_channel
    
    # Send message with tie information
    await admin_channel.send(
        f"⚠️ Poll tie for event '{event['title']}'!\n"
        f"Tied options: {', '.join(tied_options)}\n"
        f"Please manually resolve."
    )
```

## Error Handling

### Discord API Failures
- Retry scheduled event creation up to 3 times
- Log errors and notify in channel if creation fails
- Keep event data for manual recovery

### Database Failures
- Queue operations if database is unavailable
- Retry with exponential backoff
- Log all failures for debugging

### Poll Expiration Failures
- If winner calculation fails, log error and notify admins
- If scheduled event creation fails, keep poll data and allow retry
- Ensure poll status is updated even if downstream operations fail

## Testing Strategy

### Manual Testing Checklist
1. Run `/event create` and verify modal appears
2. Submit modal and verify poll is created with correct dates/times
3. Vote on poll and verify votes are recorded
4. Vote multiple times and verify votes update (not duplicate)
5. Wait for expiration (or manually trigger) and verify event is created
6. Test tie scenario and verify admin notification

### Edge Cases
- Poll created on last day of month (should show dates from current month only)
- No votes cast (should notify admin)
- Only one vote cast (should still create event)
- User votes then changes vote (should update, not duplicate)
- Bot restarts during active poll (should resume on restart)

## Implementation Notes

### Simplified Approach
- No complex state machine - just "active" and "expired" status
- No manual poll closing - always auto-expires after 7 days
- No game selection - just date and time
- No RSVP system - use Discord's built-in interested/going feature
- No recurring events - one-time events only
- No timezone handling - use server's default timezone

### Future Enhancements (Not in Scope)
- Custom poll duration
- Game selection
- Manual poll closing
- Timezone support
- Recurring events
- Event editing/cancellation
