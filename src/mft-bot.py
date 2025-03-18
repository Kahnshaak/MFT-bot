import discord
from discord.ext import commands
from dotenv import load_dotenv
import redis
from pymongo import MongoClient

# Make sure not to import all from any other modules
from commands import *
from mftbot.mftlogging import mftlogger
from mftbot.mftlogging.config import config

# Keys
#TOKEN = os.getenv("DISCORD_BOT_TOKEN")
#MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
#REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
#REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

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

PREFIX = config["prefix"]
ADMIN_ROLE = config["admin_role"]
DEFAULT_POLL_DURATION = config["default_poll_duration"]

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

@bot.event
async def on_ready():
    logging.info(f"Bot online as {bot.user}")

# ----------- POLLS ----------- #
# -------- SCHEDULING -------- #
## Make it so that people can put in their general schedule and then we can send out a ping asking for modifications on the month.
## similar to how I did with SWE group

for command_class in __all__:
    command_module = globals()[command_class]
    bot.add_cog(command_module(bot))
    logging.info(f"Loaded command: {command_class}")


load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if __name__ == "__main__":
    bot.run(TOKEN)
