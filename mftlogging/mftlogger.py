import logging
import os
import sys

sys.path.append(os.path.dirname(__file__))
from config import config

LOG_LEVELS = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR
}

LOGGING_LEVEL = config.get("logging_level", "INFO").upper()
selected_log_level = LOG_LEVELS.get(LOGGING_LEVEL, logging.INFO)

logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(logs_dir, exist_ok=True)
log_file = os.path.join(logs_dir, "bot.log")

logging.basicConfig(
        level=selected_log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler("bot.log"),
            logging.StreamHandler()
    ]
)

logging.info(f"Logging level set to: {LOGGING_LEVEL}")
