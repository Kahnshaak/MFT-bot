# Games Cog Documentation

The Games cog provides a comprehensive game interest and notification system for Discord servers. It allows users to register interest in games, ping other interested users, and includes advanced features like fuzzy matching, popularity tracking, and notification frequency limiting.

## Features

### Core Functionality

1. **Game Interest Registration**
   - Users can add/remove games from their interest list
   - Interest levels from 1-10 for prioritization
   - Automatic game database creation and management

2. **Fuzzy Matching System**
   - Intelligent game name resolution with confidence scoring
   - Support for game aliases and alternative names
   - Typo-tolerant search functionality

3. **Game Ping System**
   - Notify users interested in specific games
   - Frequency limiting to prevent spam
   - User-configurable notification limits

4. **Popularity Tracking**
   - Real-time game popularity scoring
   - Trending games detection
   - Analytics for interests, pings, and plays

5. **Game Organization**
   - Categories (Board Game, Video Game, etc.)
   - Custom tags for flexible organization
   - Alias management for common name variations

6. **Notification Management**
   - Per-user, per-game frequency limits
   - Daily and weekly ping limits
   - Automatic counter resets

## Commands

### User Commands

#### `/games-add <game_name> [interest_level]`
Add a game to your interest list.
- `game_name`: Name of the game
- `interest_level`: Your interest level (1-10, default: 5)

**Example:**
```
/games-add Among Us 8
```

#### `/games-remove <game_name>`
Remove a game from your interest list.

**Example:**
```
/games-remove Among Us
```

#### `/games-list`
Display your current game interests with interest levels.

#### `/games-ping <game_name>`
Ping users interested in a specific game.
- Includes fuzzy matching for game names
- Shows confirmation dialog for ambiguous matches
- Respects user notification frequency limits

**Example:**
```
/games-ping Among Us
```

#### `/games-limits <game_name> [daily_limit] [weekly_limit]`
Configure notification frequency limits for a specific game.
- `daily_limit`: Max pings per day (1-50, default: 3)
- `weekly_limit`: Max pings per week (1-100, default: 10)

**Example:**
```
/games-limits "Among Us" 5 15
```

### Discovery Commands

#### `/games-popular [limit]`
Show the most popular games in the server.
- `limit`: Number of games to show (1-25, default: 10)

#### `/games-trending [limit]`
Show currently trending games based on recent activity.
- `limit`: Number of games to show (1-25, default: 10)

#### `/games-search <query>`
Search for games with fuzzy matching.
- Returns games with confidence scores
- Useful for finding exact game names

### Admin Commands

#### `/games-manage <game_name>`
Manage game metadata (requires MANAGE_EVENTS permission).
- Add/remove aliases
- Add categories and tags
- View detailed statistics

## Game Model

### Game Properties

- **Name**: Primary game name
- **Description**: Optional game description
- **Categories**: Predefined categories (Board Game, Video Game, etc.)
- **Tags**: Custom tags for organization
- **Aliases**: Alternative names for fuzzy matching
- **Statistics**: Popularity metrics and activity tracking

### Categories

- `BOARD_GAME`: Traditional board games
- `VIDEO_GAME`: Digital/computer games
- `CARD_GAME`: Card-based games
- `TABLETOP_RPG`: Role-playing games
- `PARTY_GAME`: Social party games
- `STRATEGY`: Strategy-focused games
- `COOPERATIVE`: Cooperative games
- `COMPETITIVE`: Competitive games
- `OTHER`: Miscellaneous games

### Statistics Tracking

Games automatically track:
- **Total Interests**: Number of users interested
- **Total Pings**: Number of ping notifications sent
- **Total Plays**: Number of recorded plays
- **Recent Activity**: Activity in last 7-30 days
- **Popularity Score**: Calculated popularity metric
- **Trending Status**: Based on recent activity spikes

## Fuzzy Matching System

The system uses intelligent fuzzy matching to handle:
- Typos in game names
- Alternative spellings
- Common abbreviations
- Partial matches

### Confidence Scoring

- **1.0**: Exact match with primary name
- **0.9-0.99**: High confidence alias match
- **0.6-0.89**: Good fuzzy match
- **< 0.6**: Low confidence (not shown)

### Alias Management

Games can have multiple aliases with individual confidence scores:
- Exact alternative names (confidence: 1.0)
- Common abbreviations (confidence: 0.8-0.9)
- Partial matches (confidence: 0.6-0.7)

## Notification Frequency Limiting

### Default Limits
- **Daily**: 3 pings per game per day
- **Weekly**: 10 pings per game per week

### User Configuration
Users can customize limits per game:
- Increase limits for favorite games
- Decrease limits for less interesting games
- Set to 0 to disable notifications entirely

### Automatic Reset
- Daily counters reset at midnight UTC
- Weekly counters reset every 7 days
- Counters are checked before each ping

## Integration with Other Systems

### Event Bus Integration
The Games cog emits events for:
- Game interest added/removed
- Game pings sent
- Game statistics updated
- Notification limits reached

### User Profile Integration
- Game interests stored in user profiles
- Statistics tracked per user
- Notification preferences respected

### Database Integration
- Automatic game creation on first interest
- Efficient querying with proper indexing
- Statistics aggregation and caching

## Performance Considerations

### Database Optimization
- Indexed queries for fast game lookups
- Efficient fuzzy matching algorithms
- Cached popularity calculations

### Memory Usage
- Lazy loading of game statistics
- Efficient data structures for matching
- Minimal memory footprint per game

### Rate Limiting
- Built-in frequency limiting prevents spam
- Configurable limits per user/game
- Automatic cleanup of old data

## Error Handling

### Common Scenarios
- Invalid game names (sanitized automatically)
- Duplicate interests (prevented)
- Missing permissions (graceful failure)
- Database connectivity issues (queued operations)

### User Feedback
- Clear error messages for invalid input
- Helpful suggestions for typos
- Confirmation dialogs for ambiguous actions

## Future Enhancements

### Planned Features
- Game recommendation system
- Integration with external game databases
- Advanced analytics and reporting
- Scheduled game night suggestions
- Cross-server game interest sharing

### API Extensions
- REST API endpoints for web dashboard
- Webhook notifications for external systems
- Import/export functionality
- Bulk operations for administrators

## Configuration

### Environment Variables
No additional environment variables required. The Games cog uses the existing database and event bus infrastructure.

### Database Collections
- `games`: Game metadata and statistics
- `notification_frequency_limits`: User notification limits
- `users`: User profiles with game interests (existing)

### Permissions
- **Basic Usage**: All users can add interests and ping games
- **Game Management**: Requires `MANAGE_EVENTS` permission
- **Admin Features**: Requires appropriate role mappings

## Troubleshooting

### Common Issues

1. **Game not found in ping**
   - Use `/games-search` to find exact name
   - Check for typos in game name
   - Verify game exists in server

2. **No users pinged**
   - Check if users have notification limits
   - Verify users are still in server
   - Confirm users have notifications enabled

3. **Fuzzy matching not working**
   - Game may not exist in database yet
   - Try exact name first, then add aliases
   - Check confidence threshold settings

### Debug Commands
- `/games-search`: Find exact game names
- `/games-manage`: View game details and statistics
- `/games-popular`: See what games are tracked

### Logging
The Games cog logs all major operations:
- Game interest changes
- Ping notifications sent
- Frequency limit violations
- Database operations
- Error conditions

All logs include relevant context (user ID, guild ID, game name) for debugging.