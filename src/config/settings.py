"""
Configuration management system for the Discord Game Night Bot.
"""

import os
from typing import Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Discord Configuration
    discord_token: str = Field(..., env="DISCORD_TOKEN")
    discord_client_id: str = Field(..., env="DISCORD_CLIENT_ID")
    discord_client_secret: str = Field(..., env="DISCORD_CLIENT_SECRET")
    
    # Database Configuration
    database_url: str = Field(
        default="mongodb://localhost:27017/gamenight_bot",
        env="DATABASE_URL"
    )
    
    # Web Dashboard Configuration
    jwt_secret: str = Field(..., env="JWT_SECRET")
    web_host: str = Field(default="0.0.0.0", env="WEB_HOST")
    web_port: int = Field(default=8000, env="WEB_PORT")
    
    # Logging Configuration
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file_path: str = Field(default="logs/gamenight_bot.log", env="LOG_FILE_PATH")
    log_max_bytes: int = Field(default=10485760, env="LOG_MAX_BYTES")  # 10MB
    log_backup_count: int = Field(default=5, env="LOG_BACKUP_COUNT")
    
    # Environment
    environment: str = Field(default="development", env="ENVIRONMENT")
    
    # Security
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        env="ALLOWED_ORIGINS"
    )
    
    # Rate Limiting
    rate_limit_per_minute: int = Field(default=60, env="RATE_LIMIT_PER_MINUTE")
    rate_limit_burst: int = Field(default=10, env="RATE_LIMIT_BURST")
    
    # Bot Configuration
    command_prefix: str = Field(default="!", env="COMMAND_PREFIX")
    max_poll_options: int = Field(default=25, env="MAX_POLL_OPTIONS")
    default_poll_timeout_hours: int = Field(default=24, env="DEFAULT_POLL_TIMEOUT_HOURS")
    
    # Notification Configuration
    notification_retry_attempts: int = Field(default=3, env="NOTIFICATION_RETRY_ATTEMPTS")
    notification_retry_delay: int = Field(default=300, env="NOTIFICATION_RETRY_DELAY")  # 5 minutes
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Parse allowed_origins if it's a string
        if isinstance(self.allowed_origins, str):
            self.allowed_origins = [
                origin.strip() 
                for origin in self.allowed_origins.split(",")
                if origin.strip()
            ]
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment.lower() == "development"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() == "production"