# Discord Game Night Bot - Deployment Guide

This guide provides step-by-step instructions for deploying the simplified Discord Game Night Bot in various environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Docker Deployment (Recommended)](#docker-deployment-recommended)
4. [Manual Deployment](#manual-deployment)
5. [Configuration](#configuration)
6. [Troubleshooting](#troubleshooting)
7. [Monitoring and Maintenance](#monitoring-and-maintenance)

## Prerequisites

### System Requirements

- **Python**: 3.11 or higher
- **MongoDB**: 7.0 or higher
- **Docker**: 20.10+ (for Docker deployment)
- **Docker Compose**: 1.29+ (for Docker deployment)
- **Memory**: Minimum 256MB RAM (reduced from previous requirements)
- **Storage**: Minimum 500MB free space (reduced from previous requirements)

### Discord Setup

1. **Create Discord Application**:
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Click "New Application" and give it a name
   - Note down the **Application ID**

2. **Create Bot User**:
   - Go to the "Bot" section in your application
   - Click "Add Bot"
   - Note down the **Bot Token** (keep this secret!)
   - Enable the following **Privileged Gateway Intents**:
     - Server Members Intent
     - Message Content Intent

3. **Set OAuth2 Scopes**:
   - Go to "OAuth2" → "URL Generator"
   - Select scopes: `bot`, `applications.commands`
   - Select bot permissions:
     - Send Messages
     - Use Slash Commands
     - Manage Events
     - Read Message History
     - Add Reactions
     - Embed Links
     - Attach Files

4. **Invite Bot to Server**:
   - Use the generated OAuth2 URL to invite the bot to your Discord server
   - Ensure the bot has appropriate permissions in the channels it will use

## Environment Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd discord-gamenight-bot
```

### 2. Environment Variables

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit the `.env` file with your configuration:

```env
# Discord Bot Configuration (REQUIRED)
DISCORD_TOKEN=your_bot_token_here
DISCORD_CLIENT_ID=your_client_id_here
DISCORD_CLIENT_SECRET=your_client_secret_here

# Database Configuration
DATABASE_URL=mongodb://admin:password@localhost:27017/gamenight_bot?authSource=admin

# Web Dashboard Configuration (Optional)
JWT_SECRET=your_secure_jwt_secret_here
WEB_HOST=0.0.0.0
WEB_PORT=8000

# Logging Configuration
LOG_LEVEL=INFO

# Environment
ENVIRONMENT=production
```

### 3. Generate Secure Secrets

Generate secure secrets for production:

```bash
# Generate JWT secret
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate strong password for MongoDB
python -c "import secrets; print(secrets.token_urlsafe(16))"
```

## Docker Deployment (Recommended)

Docker deployment is the recommended method as it provides consistency and easy management.

### 1. Prerequisites

Ensure Docker and Docker Compose are installed:

```bash
# Check Docker installation
docker --version
docker-compose --version
```

### 2. Configuration

Update the `.env` file with Docker-specific settings:

```env
# Use Docker MongoDB service
DATABASE_URL=mongodb://admin:password@mongodb:27017/gamenight_bot?authSource=admin
```

### 3. Deploy with Docker Compose

```bash
# Build and start services
docker-compose up -d

# View logs
docker-compose logs -f bot

# Check service status
docker-compose ps
```

### 4. Verify Deployment

```bash
# Check bot logs for successful startup
docker-compose logs bot | grep "Bot is ready"

# Check database connection
docker-compose exec mongodb mongo -u admin -p password --authenticationDatabase admin
```

### 5. Docker Management Commands

```bash
# Stop services
docker-compose down

# Restart bot only
docker-compose restart bot

# Update and rebuild
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# View real-time logs
docker-compose logs -f bot

# Access MongoDB shell
docker-compose exec mongodb mongo -u admin -p password --authenticationDatabase admin
```

## Manual Deployment

For environments where Docker is not available or preferred.

### 1. Install Python Dependencies

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/Mac:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Install and Configure MongoDB

#### Ubuntu/Debian:
```bash
# Import MongoDB public key
wget -qO - https://www.mongodb.org/static/pgp/server-7.0.asc | sudo apt-key add -

# Add MongoDB repository
echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/7.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list

# Install MongoDB
sudo apt-get update
sudo apt-get install -y mongodb-org

# Start MongoDB service
sudo systemctl start mongod
sudo systemctl enable mongod
```

#### CentOS/RHEL:
```bash
# Add MongoDB repository
sudo tee /etc/yum.repos.d/mongodb-org-7.0.repo << EOF
[mongodb-org-7.0]
name=MongoDB Repository
baseurl=https://repo.mongodb.org/yum/redhat/8/mongodb-org/7.0/x86_64/
gpgcheck=1
enabled=1
gpgkey=https://www.mongodb.org/static/pgp/server-7.0.asc
EOF

# Install MongoDB
sudo yum install -y mongodb-org

# Start MongoDB service
sudo systemctl start mongod
sudo systemctl enable mongod
```

### 3. Configure MongoDB Security

```bash
# Connect to MongoDB
mongo

# Create admin user
use admin
db.createUser({
  user: "admin",
  pwd: "your_secure_password",
  roles: ["userAdminAnyDatabase", "dbAdminAnyDatabase", "readWriteAnyDatabase"]
})

# Enable authentication
exit
```

Edit `/etc/mongod.conf`:
```yaml
security:
  authorization: enabled
```

Restart MongoDB:
```bash
sudo systemctl restart mongod
```

### 4. Initialize Database

Before starting the bot, ensure the database is accessible:

```bash
# Test database connection
python -c "
import asyncio
from src.database.manager import DatabaseManager

async def test():
    db = DatabaseManager('mongodb://admin:password@localhost:27017/gamenight_bot?authSource=admin')
    await db.connect()
    print('Database connection successful')
    await db.disconnect()

asyncio.run(test())
"
```

### 5. Start the Bot

```bash
# Run directly
python src/bot.py

# Or run with nohup for background execution
nohup python src/bot.py > bot.log 2>&1 &
```

### 6. Set up System Service (Optional)

Create a systemd service for automatic startup:

```bash
sudo tee /etc/systemd/system/gamenight-bot.service << EOF
[Unit]
Description=Discord Game Night Bot
After=network.target mongod.service

[Service]
Type=simple
User=gamenight
WorkingDirectory=/path/to/discord-gamenight-bot
Environment=PATH=/path/to/discord-gamenight-bot/venv/bin
ExecStart=/path/to/discord-gamenight-bot/venv/bin/python src/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl enable gamenight-bot
sudo systemctl start gamenight-bot

# Check status
sudo systemctl status gamenight-bot
```

## Configuration

### Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_TOKEN` | ✅ | - | Discord bot token |
| `DISCORD_CLIENT_ID` | ✅ | - | Discord application client ID |
| `DISCORD_CLIENT_SECRET` | ✅ | - | Discord application client secret |
| `DATABASE_URL` | ❌ | `mongodb://localhost:27017/gamenight_bot` | MongoDB connection string |
| `JWT_SECRET` | ❌ | - | JWT secret for web authentication (only needed if using web dashboard) |
| `WEB_HOST` | ❌ | `0.0.0.0` | Web server host (only needed if using web dashboard) |
| `WEB_PORT` | ❌ | `8000` | Web server port (only needed if using web dashboard) |
| `LOG_LEVEL` | ❌ | `INFO` | Logging level |
| `ENVIRONMENT` | ❌ | `development` | Environment (development/production) |

### Bot Configuration

The bot can be configured through Discord slash commands once deployed:

```
/admin config - Configure server settings
/admin roles - Set up permission roles
```

## Troubleshooting

### Common Issues

#### 1. Bot Won't Start

**Symptoms**: Bot exits immediately or shows connection errors

**Solutions**:
```bash
# Check environment variables
cat .env

# Verify Discord token
# Token should start with "MTM" or similar

# Test basic bot startup
python -c "import discord; print('Discord.py imported successfully')"
```

#### 2. Database Connection Failed

**Symptoms**: "Cannot connect to database" errors

**Solutions**:
```bash
# Check MongoDB status
sudo systemctl status mongod

# Test MongoDB connection
mongo mongodb://admin:password@localhost:27017/gamenight_bot?authSource=admin

# Check firewall settings
sudo ufw status
```

#### 3. Permission Errors

**Symptoms**: Bot responds with permission errors

**Solutions**:
- Verify bot has required permissions in Discord server
- Check role hierarchy (bot role should be above managed roles)
- Re-invite bot with updated permissions

#### 4. Import Errors

**Symptoms**: "ModuleNotFoundError" or import errors

**Solutions**:
```bash
# Reinstall dependencies
pip install -r requirements.txt

# Check Python path
python -c "import sys; print(sys.path)"

# Verify virtual environment
which python
```

### Log Analysis

#### View Recent Logs
```bash
# Docker deployment
docker-compose logs --tail=100 bot

# Manual deployment
tail -f logs/gamenight_bot.log
```

#### Common Log Messages

- `Successfully connected to MongoDB` - Database connected
- `Bot is ready!` - Bot connected to Discord
- `Loaded cog:` - Cog loaded successfully
- `Command tree synced` - Slash commands registered

### Health Checks

Basic health monitoring:

```bash
# Check bot status via logs
grep "Bot is ready" logs/gamenight_bot.log

# Database connectivity test
python -c "
import asyncio
from src.database.manager import DatabaseManager

async def test():
    db = DatabaseManager('mongodb://admin:password@localhost:27017/gamenight_bot?authSource=admin')
    await db.connect()
    print('Database connection successful')
    await db.disconnect()

asyncio.run(test())
"
```

## Monitoring and Maintenance

### Regular Maintenance Tasks

#### 1. Log Management
Monitor log file sizes:

```bash
# Check log file sizes
du -sh logs/

# Manual log cleanup if needed
find logs/ -name "*.log" -mtime +30 -delete
```

#### 2. Database Maintenance

```bash
# Connect to MongoDB
mongo mongodb://admin:password@localhost:27017/gamenight_bot?authSource=admin

# Check database stats
db.stats()

# Check collection sizes
db.events.stats()
db.users.stats()

# Compact database (if needed)
db.runCommand({compact: "events"})
```

#### 3. Update Bot

```bash
# Docker deployment
git pull
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Manual deployment
git pull
pip install -r requirements.txt
sudo systemctl restart gamenight-bot
```

### Monitoring

#### Key Metrics to Monitor

1. **Bot Uptime**: Check if bot is responding to commands
2. **Database Performance**: Monitor query response times
3. **Memory Usage**: Ensure adequate memory available
4. **Disk Space**: Monitor log file growth
5. **Error Rates**: Check error logs for issues

#### Monitoring Commands

```bash
# Check bot process
ps aux | grep bot.py

# Monitor resource usage
top -p $(pgrep -f bot.py)

# Check disk usage
df -h

# Monitor database connections
mongo --eval "db.serverStatus().connections"
```

### Backup and Recovery

#### Database Backup

```bash
# Create backup
mongodump --uri="mongodb://admin:password@localhost:27017/gamenight_bot?authSource=admin" --out=backup/$(date +%Y%m%d)

# Restore from backup
mongorestore --uri="mongodb://admin:password@localhost:27017/gamenight_bot?authSource=admin" backup/20231201/gamenight_bot/
```

#### Configuration Backup

```bash
# Backup configuration
cp .env .env.backup.$(date +%Y%m%d)
cp docker-compose.yml docker-compose.yml.backup.$(date +%Y%m%d)
```

### Security Considerations

1. **Keep Secrets Secure**: Never commit `.env` file to version control
2. **Regular Updates**: Keep dependencies updated for security patches
3. **Network Security**: Use firewalls to restrict database access
4. **Access Control**: Limit who has access to production environment
5. **Audit Logs**: Regularly review audit logs for suspicious activity

### Support

For additional support:

1. Check the troubleshooting section above
2. Review bot logs for error messages
3. Test database connectivity
4. Check Discord API status at https://discordstatus.com/

---

## Quick Start Checklist

- [ ] Discord application and bot created
- [ ] Bot invited to Discord server with proper permissions
- [ ] `.env` file configured with all required variables
- [ ] MongoDB installed and running (or Docker available)
- [ ] Dependencies installed
- [ ] Database connectivity tested
- [ ] Bot starts successfully and responds to commands
- [ ] Logs are being written correctly
- [ ] Database connections working

Once all items are checked, your Discord Game Night Bot should be fully operational!