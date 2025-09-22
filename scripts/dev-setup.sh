#!/bin/bash

# Development setup script for Discord Game Night Bot

set -e

echo "Setting up Discord Game Night Bot development environment..."

# Check if Docker is installed
DOCKER_AVAILABLE=false
if command -v docker &> /dev/null && command -v docker-compose &> /dev/null; then
    DOCKER_AVAILABLE=true
    echo "Docker and Docker Compose are available"
else
    echo "Docker or Docker Compose not found. Skipping Docker setup."
    echo "   You can still run the bot locally with Python."
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "Please edit .env file with your Discord bot token and other settings"
else
    echo ".env file already exists"
fi

# Create logs directory
mkdir -p logs
echo "Created logs directory"

# Start MongoDB container if Docker is available
if [ "$DOCKER_AVAILABLE" = true ]; then
    echo "Starting MongoDB container..."
    docker-compose up -d mongodb

    # Wait for MongoDB to be ready
    echo "Waiting for MongoDB to be ready..."
    sleep 10

    # Check if MongoDB is running
    if docker-compose ps mongodb | grep -q "Up"; then
        echo "MongoDB is running"
    else
        echo "Failed to start MongoDB"
        echo "  You can still continue with local development"
    fi
else
    echo "Skipping MongoDB container setup (Docker not available)"
    echo "   For local development, you'll need to install MongoDB separately"
fi

# Create and activate virtual environment
if command -v python3 &> /dev/null; then
    echo "Creating Python virtual environment..."
    
    if python3 -m venv venv 2>/dev/null; then
        echo "Installing Python dependencies in virtual environment..."
        source venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
        echo "Python dependencies installed in virtual environment"
        echo "To activate the virtual environment, run: source venv/bin/activate"
    else
        echo "Failed to create virtual environment"
        echo "On Ubuntu/Debian, you may need to install python3-venv:"
        echo "   sudo apt install python3-venv"
        echo "On other systems, try installing python3-dev or python3-devel"
        echo ""
        echo "Attempting to install dependencies globally (not recommended for production)..."
        if pip3 install -r requirements.txt 2>/dev/null; then
            echo "Dependencies installed globally"
        else
            echo "Failed to install dependencies. Please install them manually."
        fi
    fi
else
    echo "Python 3 not found. You can still use Docker to run the bot."
fi

echo ""
echo "Development environment setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your Discord bot token"

if [ "$DOCKER_AVAILABLE" = true ]; then
    echo "2. Run 'docker-compose up bot' to start the bot with Docker"
    echo "3. Or run locally:"
    echo "   - source venv/bin/activate"
    echo "   - python3 src/bot.py"
    echo ""
    echo "Useful commands:"
    echo "- docker-compose up -d     # Start all services in background"
    echo "- docker-compose logs bot  # View bot logs"
    echo "- docker-compose down      # Stop all services"
    echo "- source venv/bin/activate # Activate virtual environment"
else
    echo "2. Install MongoDB locally or use a cloud MongoDB service"
    echo "3. Run locally:"
    echo "   - source venv/bin/activate"
    echo "   - python3 src/bot.py"
    echo ""
    echo "Useful commands:"
    echo "- source venv/bin/activate # Activate virtual environment"
    echo "- ./scripts/test-setup.sh  # Test the setup"
fi