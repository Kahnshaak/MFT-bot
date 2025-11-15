# Discord Game Night Scheduling Bot

A comprehensive Discord bot for organizing game nights with automated scheduling, polling, and event management.

This bot was also my attempt at vibe coding an application... it has not gone well at all and will definitely just need to be written from scratch. As it stands now I don't have time to complete it, but we will see if I can in the (hopefully) near future.

## Features

- **Automated Event Creation**: Create events with interactive date, time, and game selection polls
- **Recurring Events**: Set up weekly or monthly recurring game nights
- **User Preferences**: Timezone support, game interests, and notification preferences  
- **Game Interest System**: Register interest in games and get pinged when others want to play
- **Web Dashboard**: Manage bot configuration and view analytics through a web interface
- **Comprehensive Logging**: Structured logging with file rotation and multiple log levels
- **Health Monitoring**: Built-in health checks for database and Discord API connectivity

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (optional, for local development)
- Discord Bot Token

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd MFT-bot
   ```

2. **Run the setup script**
   ```bash
   ./scripts/dev-setup.sh
   ```

3. **Configure your bot**
   - Edit `.env` file with your Discord bot token and settings
   - Get your Discord bot token from [Discord Developer Portal](https://discord.com/developers/applications)

4. **Start the bot**
   ```bash
   # Using Docker (recommended)
   docker-compose up -d
   
   # Or run locally with virtual environment
   source venv/bin/activate
   python3 src/bot.py
   ```

### Configuration

Copy `.env.example` to `.env` and configure the following required settings:

```env
# Discord Bot Configuration
DISCORD_TOKEN=your_discord_bot_token_here
DISCORD_CLIENT_ID=your_discord_client_id_here
DISCORD_CLIENT_SECRET=your_discord_client_secret_here

# Database Configuration (MongoDB)
DATABASE_URL=mongodb://admin:password@localhost:27017/gamenight_bot?authSource=admin

# Web Dashboard
JWT_SECRET=your_jwt_secret_key_here
```

## Development

### Project Structure

```
src/
├── bot.py                 # Main bot entry point
├── config/               # Configuration management
├── core/                 # Core framework components
│   ├── event_bus.py      # Inter-component communication
│   ├── security_manager.py # Authentication & authorization
│   ├── metrics_collector.py # Performance monitoring
│   └── health_monitor.py # System health checks
├── database/             # Database layer
├── models/               # Data models
├── cogs/                 # Discord bot cogs (commands)
└── utils/                # Utilities and helpers
```

### Running Tests

```bash
# Test the setup
./scripts/test-setup.sh

# Run unit tests (when implemented)
pytest tests/
```

### Docker Commands

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f bot

# Stop services
docker-compose down

# Rebuild containers
docker-compose build --no-cache
```

## Architecture

The bot follows a modular architecture with:

- **Event Bus System**: Loose coupling between components through publish-subscribe events
- **Security Manager**: Centralized permission and authentication handling
- **Metrics Collection**: Performance monitoring and usage analytics
- **Health Monitoring**: Automated system health checks and alerting
- **Database Layer**: MongoDB with connection pooling and error handling

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
## What is this bot even for??
With members of my friend group graduating college, moving away, having kids, and moving on with life in general, we wanted a way that we could keep in touch and still enjoy playing games together.
Eventually the concept of "Mandatory Fun Time" was born; a time that we would not make any plans, and just hang out doing whatever.
Often this included playing something like Among Us, or Jackbox, or maybe we would play Fortnite.

As our friend group grew, we invited more people to play, and the idea of what MFT was began evolving.
Different friends enjoyed different aspects of the game night and wanted something different.
In addition, schedules became more difficult to manage.

Regular Google Forms are much too cumbersome, and don't fit the need frankly.
Poll bots already in existance also don't meet the requirements.

## So like... what does it do?
I needed a bot that could:
 1. Assist in scheduling the game night
   - This included picking a date and time. We tried a standard meetup time, but that doesn't always work.
   - I needed the scheduling to be flexible enough that people can put in their availability, but also allow for making a firm decision on a start time
 2. Allow for polls on what activity we would do
   - This also needed some tuning, as the group decided that we wanted set times for different types of games (like a small-group game, and a large-group game)
 3. Separate from the game night, we need to be able to ping players for specific games
   - New games are always coming out, and sometimes those are contenders for game night. However, sometimes people want to play those outside the once-a-month occurance. This allows people to add themselves to a messaging queue so that if someone wants to play a game, they can just ping those interested without a million roles in the server, or an additional bot managing said million roles
 4. Also a bit of user management
   - Just to separate concerns, it can also allow a bit of user management for the bot's roles. Maybe you want everyone to be able to ping for games, but only like 3 people to ping for scheduling or something.

## Cool cool, tell me what we're using in this? Can I self-host?
### If you don't care about under-the-hood stuff, just skip this section.

This is written using Pycord, and utilizes MongoDB and Redis.
I am using KeyDB instead of Redis, cause I'm a FOSS bitch, but both are interchangeable in the commands.
Eventually I will get a Podman(Docker) container going so that it should be easy to deploy for your own server.
