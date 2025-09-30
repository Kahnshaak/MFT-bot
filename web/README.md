# Game Night Bot Web Dashboard

A minimal web interface for the Discord Game Night Bot that provides basic monitoring and management capabilities.

## Features

- **Dashboard**: Overview of bot statistics and system status
- **Events Management**: View and monitor game night events
- **Users Management**: User directory and statistics (coming soon)
- **Health Monitoring**: Real-time system health checks
- **API Endpoints**: RESTful API for bot data

## Quick Start

The web dashboard is automatically started when using Docker Compose:

```bash
docker-compose up web
```

The dashboard will be available at: http://localhost:8000

## API Endpoints

- `GET /` - Main dashboard
- `GET /api/health` - Health check endpoint
- `GET /api/stats` - Bot statistics
- `GET /api/events` - Recent events data
- `GET /events` - Events management page
- `GET /users` - Users management page

## Development

To run the web dashboard locally:

```bash
cd web
python app.py
```

## Environment Variables

- `WEB_HOST` - Host to bind to (default: 0.0.0.0)
- `WEB_PORT` - Port to listen on (default: 8000)
- `DATABASE_URL` - MongoDB connection string
- `ENVIRONMENT` - Environment mode (development/production)

## Technology Stack

- **FastAPI** - Modern Python web framework
- **Jinja2** - Template engine
- **Bootstrap 5** - CSS framework
- **Bootstrap Icons** - Icon library
- **MongoDB** - Database integration

## Security Notes

This is a minimal dashboard for development and basic monitoring. For production use, consider adding:

- Authentication and authorization
- HTTPS/TLS encryption
- Rate limiting
- Input validation and sanitization
- CSRF protection
- Security headers

## Future Enhancements

- User authentication with Discord OAuth
- Real-time updates with WebSockets
- Advanced analytics and charts
- Event creation and management
- User profile management
- Bot configuration interface
- Audit logs and monitoring