"""
Comprehensive logging configuration with structured logging, file rotation, and multiple log levels.
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional

import structlog
from colorama import Fore, Style, init as colorama_init

from src.config.settings import Settings


# Initialize colorama for cross-platform colored output
colorama_init(autoreset=True)


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log levels."""
    
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.MAGENTA + Style.BRIGHT,
    }
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, '')
        record.levelname = f"{log_color}{record.levelname}{Style.RESET_ALL}"
        return super().format(record)


def setup_logging(settings: Optional[Settings] = None) -> None:
    """
    Set up comprehensive logging configuration.
    
    Args:
        settings: Application settings. If None, will create new instance.
    """
    if settings is None:
        settings = Settings()
    
    # Create logs directory if it doesn't exist
    log_dir = Path(settings.log_file_path).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if not settings.is_development 
            else structlog.dev.ConsoleRenderer(colors=True)
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler with colors for development
    console_handler = logging.StreamHandler(sys.stdout)
    if settings.is_development:
        console_formatter = ColoredFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    else:
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        filename=settings.log_file_path,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding='utf-8'
    )
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # Error file handler for errors and above
    error_file_path = str(Path(settings.log_file_path).with_suffix('.error.log'))
    error_handler = logging.handlers.RotatingFileHandler(
        filename=error_file_path,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    root_logger.addHandler(error_handler)
    
    # Set specific logger levels
    logging.getLogger('discord').setLevel(logging.WARNING)
    logging.getLogger('discord.http').setLevel(logging.WARNING)
    logging.getLogger('motor').setLevel(logging.WARNING)
    logging.getLogger('pymongo').setLevel(logging.WARNING)
    
    # Log startup message
    logger = structlog.get_logger(__name__)
    logger.info(
        "Logging system initialized",
        log_level=settings.log_level,
        log_file=settings.log_file_path,
        environment=settings.environment
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name, typically __name__
        
    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


class LoggerMixin:
    """Mixin class to add logging capabilities to any class."""
    
    @property
    def logger(self) -> structlog.BoundLogger:
        """Get logger for this class."""
        return get_logger(self.__class__.__module__ + "." + self.__class__.__name__)


# Context manager for adding context to logs
class LogContext:
    """Context manager for adding structured context to logs."""
    
    def __init__(self, **context):
        self.context = context
        self.token = None
    
    def __enter__(self):
        self.token = structlog.contextvars.bind_contextvars(**self.context)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.token:
            structlog.contextvars.unbind_contextvars(self.token)