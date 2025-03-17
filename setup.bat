@echo off

echo Setting up the bot environment...

python -m venv venv
call venv/bin/activate

pip install -r requirements.txt

echo Starting up KeyDB and MongoDB...
start keybd-server
start mongodb

echo Setup complete
echo Update your .env if needed
pause
