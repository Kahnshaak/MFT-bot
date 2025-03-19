import discord
import os
import logging
from discord.ext import commands
from dotenv import load_dotenv

import sys
sys.path.append('../')
from mftlogging.mftlogger import logging
from mftlogging.config import config

load_dotenv()

# Keys
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Bot Configuration
intents = discord.Intents.default()
intents.guilds = True
intents.guild_messages = True
intents.message_content = True

PREFIX = config["prefix"]
ADMIN_ROLE = config["admin_role"]
DEFAULT_POLL_DURATION = config["default_poll_duration"]

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

import redis
from pymongo import MongoClient

# Database
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["mft_bot"]
    polls_collection = db["polls"]
    settings_collection = db["settings"]
    logging.info("MongoDB connection established")
except Exception as e:
    logging.error(f"Failed to connect to MongoDB: {e}")

try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    redis_client.ping()
    logging.info("Redis connection established")
except Exception as e:
    logging.error(f"Failed to connect to Redis: {e}")

@bot.event
async def on_ready():
    logging.info(f"Bot online as {bot.user}")

# Load commands
cogs_list = [
    'admin'
]
for cog in cogs_list:
    try:
        bot.load_extension(f'cogs.{cog}')
            logging.info(f"Loaded cog: {cog}")
    except Exception as e:
        logging.error(f"Failed to load cog {cog}: {e}")


if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")
