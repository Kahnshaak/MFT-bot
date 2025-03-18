import logging
from config import config

LOG_LEVELS = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR
}

LOGGING_LEVEL = config.get("logging_level", "INFO").upper()
selected_log_level = LOG_LEVELS.get(LOGGING_LEVEL, logging.INFO)

logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)

logging.info(f"Logging level set to: {LOGGING_LEVEL}")
