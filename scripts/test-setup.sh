#!/bin/bash

# Test script to verify the setup is working correctly

set -e

echo "Testing Discord Game Night Bot setup..."

# Test Python imports
echo "Testing Python imports..."

# Check if virtual environment exists and activate it
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

cd src
python3 -c "
try:
    from config.settings import Settings
    from core.event_bus import EventBus
    from core.security_manager import SecurityManager
    from core.metrics_collector import MetricsCollector
    from core.health_monitor import HealthMonitor
    from database.manager import DatabaseManager
    from utils.logging_config import setup_logging
    from utils.exceptions import GameNightBotException
    from utils.error_handler import ErrorHandler
    print('\nAll imports successful\n')
except ImportError as e:
    print(f'\nImport error: {e}')
    print('Make sure to run ./scripts/dev-setup.sh first to install dependencies\n')
    exit(1)
"

cd ..

# Test Docker setup
echo "Testing Docker setup..."
if docker-compose config > /dev/null 2>&1; then
    echo "Docker Compose configuration is valid"
else
    echo "Docker Compose configuration is invalid"
    exit 1
fi

# Test MongoDB connection (if running)
if docker-compose ps mongodb | grep -q "Up"; then
    echo "Testing MongoDB connection..."
    if docker-compose exec -T mongodb mongosh --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
        echo "MongoDB connection successful"
    else
        echo "MongoDB connection failed (this is expected if not configured yet)"
    fi
else
    echo "MongoDB container not running"
fi

echo ""
echo "Setup test complete!"
echo ""
echo "If you see any errors above, please check:"
echo "1. All required dependencies are installed"
echo "2. Docker and Docker Compose are working"
echo "3. .env file is properly configured"