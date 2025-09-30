#!/bin/bash

# Discord Game Night Bot Startup Script
# This script handles common deployment issues and provides helpful error messages

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to wait for service
wait_for_service() {
    local host=$1
    local port=$2
    local service_name=$3
    local max_attempts=30
    local attempt=1

    print_status "Waiting for $service_name to be ready..."
    
    while [ $attempt -le $max_attempts ]; do
        if nc -z "$host" "$port" 2>/dev/null; then
            print_success "$service_name is ready!"
            return 0
        fi
        
        print_status "Attempt $attempt/$max_attempts: $service_name not ready yet..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    print_error "$service_name failed to start within expected time"
    return 1
}

# Function to check Python version
check_python_version() {
    print_status "Checking Python version..."
    
    if ! command_exists python3; then
        print_error "Python 3 is not installed"
        return 1
    fi
    
    local python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    local required_version="3.8"
    
    if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
        print_error "Python $python_version is too old. Minimum required: $required_version"
        return 1
    fi
    
    print_success "Python $python_version is compatible"
    return 0
}

# Function to check dependencies
check_dependencies() {
    print_status "Checking dependencies..."
    
    # Check if requirements.txt exists
    if [ ! -f "requirements.txt" ]; then
        print_error "requirements.txt not found"
        return 1
    fi
    
    # Check if virtual environment exists
    if [ ! -d "venv" ] && [ -z "$VIRTUAL_ENV" ]; then
        print_warning "No virtual environment detected"
        print_status "Creating virtual environment..."
        python3 -m venv venv
        source venv/bin/activate
    elif [ -d "venv" ] && [ -z "$VIRTUAL_ENV" ]; then
        print_status "Activating virtual environment..."
        source venv/bin/activate
    fi
    
    # Install/update dependencies
    print_status "Installing/updating dependencies..."
    pip install -r requirements.txt
    
    print_success "Dependencies are ready"
    return 0
}

# Function to check environment configuration
check_environment() {
    print_status "Checking environment configuration..."
    
    # Check if .env file exists
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            print_warning ".env file not found, copying from .env.example"
            cp .env.example .env
            print_error "Please edit .env file with your configuration before running the bot"
            return 1
        else
            print_error ".env file not found and no .env.example available"
            return 1
        fi
    fi
    
    # Run environment validation
    if command_exists python3; then
        print_status "Running environment validation..."
        if python3 scripts/validate-env.py; then
            print_success "Environment validation passed"
        else
            print_error "Environment validation failed"
            return 1
        fi
    fi
    
    return 0
}

# Function to check database connectivity
check_database() {
    print_status "Checking database connectivity..."
    
    # Extract database info from .env
    if [ -f ".env" ]; then
        local db_url=$(grep "DATABASE_URL" .env | cut -d '=' -f2- | tr -d '"')
        
        if [[ $db_url == *"localhost"* ]] || [[ $db_url == *"127.0.0.1"* ]]; then
            # Check if MongoDB is running locally
            if command_exists systemctl; then
                if systemctl is-active --quiet mongod; then
                    print_success "Local MongoDB service is running"
                else
                    print_warning "Local MongoDB service is not running"
                    print_status "Attempting to start MongoDB..."
                    if sudo systemctl start mongod; then
                        print_success "MongoDB started successfully"
                    else
                        print_error "Failed to start MongoDB"
                        return 1
                    fi
                fi
            elif command_exists mongo; then
                # Try to connect directly
                if mongo --eval "db.adminCommand('ping')" >/dev/null 2>&1; then
                    print_success "MongoDB is accessible"
                else
                    print_error "Cannot connect to MongoDB"
                    return 1
                fi
            fi
        elif [[ $db_url == *"mongodb:"* ]]; then
            # Extract host and port for external MongoDB
            local host=$(echo "$db_url" | sed -n 's/.*@\([^:]*\):.*/\1/p')
            local port=$(echo "$db_url" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
            
            if [ -n "$host" ] && [ -n "$port" ]; then
                if wait_for_service "$host" "$port" "MongoDB"; then
                    print_success "External MongoDB is accessible"
                else
                    print_error "Cannot connect to external MongoDB at $host:$port"
                    return 1
                fi
            fi
        fi
    fi
    
    return 0
}

# Function to create necessary directories
create_directories() {
    print_status "Creating necessary directories..."
    
    local dirs=("logs" "src" "scripts")
    
    for dir in "${dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            print_status "Created directory: $dir"
        fi
    done
    
    print_success "Directories are ready"
    return 0
}

# Function to start the bot
start_bot() {
    print_status "Starting Discord Game Night Bot..."
    
    # Set Python path
    export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
    
    # Start the bot with proper error handling
    if python3 src/bot.py; then
        print_success "Bot started successfully"
        return 0
    else
        local exit_code=$?
        print_error "Bot failed to start (exit code: $exit_code)"
        
        # Provide helpful error messages based on exit code
        case $exit_code in
            1)
                print_error "General error - check logs for details"
                ;;
            2)
                print_error "Configuration error - check your .env file"
                ;;
            130)
                print_warning "Bot stopped by user (Ctrl+C)"
                ;;
            *)
                print_error "Unknown error occurred"
                ;;
        esac
        
        return $exit_code
    fi
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --skip-deps     Skip dependency installation"
    echo "  --skip-db       Skip database connectivity check"
    echo "  --skip-env      Skip environment validation"
    echo "  --help          Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  SKIP_VALIDATION=1    Skip all validation checks"
    echo "  DEBUG=1              Enable debug output"
}

# Main function
main() {
    local skip_deps=false
    local skip_db=false
    local skip_env=false
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-deps)
                skip_deps=true
                shift
                ;;
            --skip-db)
                skip_db=true
                shift
                ;;
            --skip-env)
                skip_env=true
                shift
                ;;
            --help)
                show_usage
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    # Enable debug mode if requested
    if [ "${DEBUG:-0}" = "1" ]; then
        set -x
    fi
    
    print_status "🚀 Discord Game Night Bot Startup Script"
    print_status "========================================="
    
    # Skip all checks if requested
    if [ "${SKIP_VALIDATION:-0}" = "1" ]; then
        print_warning "Skipping all validation checks (SKIP_VALIDATION=1)"
        start_bot
        return $?
    fi
    
    # Run startup checks
    create_directories || exit 1
    
    check_python_version || exit 1
    
    if [ "$skip_deps" = false ]; then
        check_dependencies || exit 1
    else
        print_warning "Skipping dependency check"
    fi
    
    if [ "$skip_env" = false ]; then
        check_environment || exit 1
    else
        print_warning "Skipping environment validation"
    fi
    
    if [ "$skip_db" = false ]; then
        check_database || exit 1
    else
        print_warning "Skipping database connectivity check"
    fi
    
    # Start the bot
    start_bot
    return $?
}

# Trap signals for graceful shutdown
trap 'print_warning "Received interrupt signal, shutting down..."; exit 130' INT TERM

# Run main function
main "$@"