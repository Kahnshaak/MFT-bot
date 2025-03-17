import discord
from discord.ext import commands
import redis
from pymongo import MongoClient
import os
import json

# Keys
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Database
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["mft_bot"]
polls_collection = db["polls"]
settings_collection = db["settings"]

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

# Bot Configuration

intents = discord.Intents.default()
intents.guilds = True
intents.guild_messages = True
intents.message_content = True

with open("config.json", "r") as f:
    try:
        config = json.load(f)
    except:


PREFIX = config.get("prefix", "!"
DEFAULT_POLL_DURATION = config.get("default_poll_duration", 3600)

bot = commands.Bot(command_prefix="!", intents=intents)


# ----------- POLLS ----------- #


# -------- SCHEDULING -------- #
## Make it so that people can put in their general schedule and then we can send out a ping asking for modifications on the month.
## similar to how I did with SWE group

