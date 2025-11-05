# Requirements Document

## Introduction

This is a simplified Discord bot for scheduling game nights through polls. Users can create events with a single command, which generates a poll for date and time selection. When the poll expires, the bot automatically creates a Discord Scheduled Event based on the winning votes.

## Requirements

### Requirement 1: Event Creation with Polls

**User Story:** As a Discord user, I want to create a game night event by running a single command, so that I can quickly schedule events without manual coordination.

#### Acceptance Criteria

1. WHEN I run `/event create` THEN the system SHALL present me with a modal to enter event details
2. WHEN I submit the modal with an event title THEN the system SHALL create a poll with date and time options
3. WHEN the poll is created THEN the system SHALL display all dates in the current month as voting options
4. WHEN the poll is created THEN the system SHALL display time options starting at 5pm in 1-hour increments
5. WHEN users interact with the poll THEN the system SHALL allow voting for multiple date and time options
6. WHEN the poll is displayed THEN the system SHALL show it will expire in 7 days by default

### Requirement 2: Automatic Event Scheduling

**User Story:** As a user, I want the bot to automatically create a Discord Scheduled Event when the poll expires, so that the event is finalized without manual intervention.

#### Acceptance Criteria

1. WHEN a poll expires after 7 days THEN the system SHALL automatically calculate the winning date and time
2. WHEN calculating the winner THEN the system SHALL select the date option with the most votes
3. WHEN calculating the winner THEN the system SHALL select the time option with the most votes
4. WHEN a clear winner exists THEN the system SHALL create a Discord Scheduled Event with the event title and winning date/time
5. IF there is a tie in votes THEN the system SHALL send a message to an admin channel requesting manual resolution
6. WHEN the Discord Scheduled Event is created THEN the system SHALL update the original poll message to show the final scheduled time

### Requirement 3: Permissions and Access

**User Story:** As a Discord server member, I want to be able to create events, so that anyone can organize game nights.

#### Acceptance Criteria

1. WHEN any user runs `/event create` THEN the system SHALL allow them to create an event
2. WHEN a user creates an event THEN the system SHALL record them as the event creator
3. WHEN there is a tie in poll votes THEN the system SHALL notify server administrators for resolution

### Requirement 4: Poll Interaction

**User Story:** As a user, I want to vote on event dates and times through an interactive interface, so that I can indicate my availability.

#### Acceptance Criteria

1. WHEN I view a poll THEN the system SHALL display date options as interactive buttons or a modal
2. WHEN I click a date option THEN the system SHALL allow me to open a modal to submit my vote
3. WHEN I vote THEN the system SHALL allow me to select multiple dates and times
4. WHEN I vote THEN the system SHALL update the poll display to show current vote counts
5. WHEN I vote multiple times THEN the system SHALL update my previous votes rather than creating duplicates
