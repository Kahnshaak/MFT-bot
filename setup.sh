#!/bin/bash

echo "Setting up the bot environment..."

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

# Start required services KeyDB and MongoDB
echo "Starting up KeyDB and MongoDB..."
keybd-server --daemonize yes
mongodb --fork --logpath /var/log/mongodb.log

echo "Setup complete"
echo "Update your .env if needed"
