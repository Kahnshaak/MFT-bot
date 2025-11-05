# Implementation Plan

## Phase 1: Core Infrastructure

- [x] 1. Clean up existing codebase
  - Remove all unused commands from events.py (keep only the infrastructure we need)
  - Remove complex state machine logic and poll management code
  - Keep only: database connection, basic Event model, logging
  - _Requirements: All_

- [x] 2. Create simplified Event model
  - Define Event model with fields: id, guild_id, channel_id, message_id, creator_id, title, created_at, expires_at, status, date_votes, time_votes, winning_date, winning_time, discord_event_id
  - Add methods: add_vote(), get_vote_counts(), calculate_winner()
  - Write validation for event data
  - _Requirements: 1.1, 2.1_

## Phase 2: Event Creation Flow

- [x] 3. Implement `/event create` command
  - Create single slash command handler for `/event create`
  - Command should send EventCreationModal to user
  - Add error handling for command execution
  - _Requirements: 1.1_

- [x] 4. Create EventCreationModal
  - Build modal with single required field: "Event Title" (max 100 chars)
  - On submit: create event document in database with status="active"
  - Set expires_at to 7 days from creation
  - Call poll generation function
  - _Requirements: 1.2_

- [x] 5. Implement poll generation
  - Generate list of dates: all remaining days in current month
  - Generate list of times: 5pm through 11pm in 1-hour increments (17:00, 18:00, 19:00, 20:00, 21:00, 22:00, 23:00)
  - Create poll embed showing event title, expiration date, and instructions
  - Add "Vote" button that opens VoteModal
  - Send poll message to channel and store message_id in database
  - _Requirements: 1.3, 1.4, 1.6_

## Phase 3: Voting System

- [x] 6. Create VoteModal for date/time selection
  - Build modal with two text input fields: "Dates (comma-separated)" and "Times (comma-separated)"
  - Add instructions: "Enter dates as DD (e.g., 15,16,20) and times as 5pm,6pm,7pm"
  - Parse user input and validate dates/times
  - _Requirements: 4.1, 4.2_

- [x] 7. Implement vote recording
  - On VoteModal submit: parse dates and times from user input
  - Store votes in event document: date_votes and time_votes dictionaries
  - If user has existing votes, replace them (don't duplicate)
  - Update poll embed to show current vote counts for each option
  - _Requirements: 4.3, 4.4, 4.5_

- [x] 8. Create poll embed update function
  - Build embed showing: event title, expiration time, vote counts per date, vote counts per time
  - Format: "Oct 15: 3 votes ⭐, Oct 16: 5 votes ⭐⭐"
  - Update the original poll message with new embed
  - _Requirements: 4.4_

## Phase 4: Poll Expiration and Event Creation

- [x] 9. Implement background task for poll expiration
  - Create background task that runs every 5 minutes
  - Query database for events where expires_at < now and status="active"
  - For each expired poll: call winner calculation and event creation
  - _Requirements: 2.1_

- [x] 10. Implement winner calculation
  - Count votes for each date option, find option(s) with most votes
  - Count votes for each time option, find option(s) with most votes
  - If single winner for both: return winning_date and winning_time
  - If tie for either: return tie information
  - Handle edge case: no votes cast (treat as tie, notify admin)
  - _Requirements: 2.2, 2.3, 2.5_

- [x] 11. Create Discord Scheduled Event
  - Combine winning_date and winning_time into datetime object
  - Use Discord API to create scheduled event with event title and datetime
  - Set entity_type to "external" and location to "Discord"
  - Store discord_event_id in event document
  - Update event status to "scheduled"
  - _Requirements: 2.4_

- [x] 12. Update poll message with results
  - Edit original poll message to show: "✅ Event Scheduled!"
  - Display winning date and time
  - Add link to Discord Scheduled Event
  - Remove vote button (poll is closed)
  - _Requirements: 2.6_

## Phase 5: Tie Handling

- [x] 13. Implement admin notification for ties
  - When tie is detected: find guild's system channel or first text channel
  - Send message: "⚠️ Poll tie for event '[title]'! Tied dates: [dates] or Tied times: [times]"
  - Include event ID and link to original poll message
  - Update event status to "tie"
  - _Requirements: 2.5_

## Phase 6: Error Handling and Polish

- [x] 14. Add error handling for Discord API failures
  - Wrap scheduled event creation in try/except
  - If creation fails: retry up to 3 times with exponential backoff
  - If all retries fail: log error and send message to channel
  - Keep event data for manual recovery
  - _Requirements: 2.4_

- [x] 15. Add error handling for database failures
  - Wrap all database operations in try/except
  - Log all database errors with full context
  - Send user-friendly error messages to Discord
  - _Requirements: All_

- [x] 16. Add input validation and sanitization
  - Validate event title: 3-100 chars, no @everyone/@here mentions
  - Validate date input: must be valid day numbers in current month
  - Validate time input: must be valid times in 5pm-11pm range
  - Show clear error messages for invalid input
  - _Requirements: 1.2, 4.2_

## Testing Checklist

After implementation, manually test:
- [ ] Run `/event create` and verify modal appears
- [ ] Submit modal with valid title and verify poll is created
- [ ] Click "Vote" button and verify modal appears
- [ ] Submit votes and verify they are recorded and displayed
- [ ] Submit votes again and verify they update (not duplicate)
- [ ] Manually trigger expiration and verify event is created
- [ ] Test tie scenario (create event with tied votes)
- [ ] Test no-votes scenario
- [ ] Test invalid input in vote modal
- [ ] Test bot restart during active poll
