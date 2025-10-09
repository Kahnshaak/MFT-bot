#!/bin/bash
set -e

echo "🚀 Starting Discord Game Night Bot in Docker..."

# Function to validate environment
validate_environment() {
    echo "🔍 Validating environment..."
    
    # Check required environment variables
    if [[ -z "$DISCORD_TOKEN" ]]; then
        echo "❌ DISCORD_TOKEN is not set"
        return 1
    fi
    
    if [[ -z "$DISCORD_CLIENT_ID" ]]; then
        echo "❌ DISCORD_CLIENT_ID is not set"
        return 1
    fi
    
    if [[ -z "$DISCORD_CLIENT_SECRET" ]]; then
        echo "❌ DISCORD_CLIENT_SECRET is not set"
        return 1
    fi
    
    echo "✅ Required environment variables are set"
    return 0
}

# Function to wait for database
wait_for_database() {
    echo "⏳ Waiting for database to be ready..."
    
    # Extract database host from DATABASE_URL
    DB_HOST=$(echo "$DATABASE_URL" | sed -n 's/.*@\([^:]*\):.*/\1/p')
    DB_PORT=$(echo "$DATABASE_URL" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
    
    if [[ -z "$DB_HOST" ]]; then
        DB_HOST="mongodb"
    fi
    
    if [[ -z "$DB_PORT" ]]; then
        DB_PORT="27017"
    fi
    
    # Wait for database connection
    timeout=60
    while ! nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; do
        timeout=$((timeout - 1))
        if [[ $timeout -le 0 ]]; then
            echo "❌ Database connection timeout"
            return 1
        fi
        echo "⏳ Waiting for database at $DB_HOST:$DB_PORT... ($timeout seconds remaining)"
        sleep 1
    done
    
    echo "✅ Database is ready"
    return 0
}

# Main execution
main() {
    # Validate environment variables
    if ! validate_environment; then
        echo "💥 Environment validation failed"
        exit 1
    fi
    
    # Wait for database
    if ! wait_for_database; then
        echo "💥 Database connection failed"
        exit 1
    fi
    
    # Start the bot
    echo "🎮 Starting Discord Game Night Bot..."
    exec python src/bot.py
}

# Run main function
main "$@"