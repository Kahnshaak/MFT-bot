"""
Logging configuration for the Game Night Bot Web Dashboard.
"""

import os
import sys
import logging
import logging.handlers
from pathlib import Path
import structlog
from datetime import datetime


def setup_web_logging():
    """Set up comprehensive logging for the web dashboard."""
    
    # Create logs directory
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Configure standard logging
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    simple_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level))
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler for web dashboard
    web_log_file = logs_dir / "gamenight_web.log"
    file_handler = logging.handlers.RotatingFileHandler(
        web_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(file_handler)
    
    # Error log file
    error_log_file = logs_dir / "gamenight_web.error.log"
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(error_handler)
    
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
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Log startup information
    logger = structlog.get_logger("web.startup")
    logger.info(
        "Web dashboard logging configured",
        log_level=log_level,
        log_file=str(web_log_file),
        error_log_file=str(error_log_file)
    )
    
    return logger


def get_request_logger():
    """Get a logger for HTTP requests."""
    return structlog.get_logger("web.requests")


def get_auth_logger():
    """Get a logger for authentication events."""
    return structlog.get_logger("web.auth")


def get_security_logger():
    """Get a logger for security events."""
    return structlog.get_logger("web.security")


def get_api_logger():
    """Get a logger for API operations."""
    return structlog.get_logger("web.api")


class RequestLoggingMiddleware:
    """Middleware to log HTTP requests and responses."""
    
    def __init__(self, app):
        self.app = app
        self.logger = get_request_logger()
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        start_time = datetime.utcnow()
        request_id = f"req_{start_time.timestamp()}"
        
        # Log request
        self.logger.info(
            "HTTP request started",
            request_id=request_id,
            method=scope["method"],
            path=scope["path"],
            query_string=scope.get("query_string", b"").decode(),
            client_ip=scope.get("client", ["unknown", None])[0]
        )
        
        # Capture response
        response_status = None
        
        async def send_wrapper(message):
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = message["status"]
            await send(message)
        
        try:
            await self.app(scope, receive, send_wrapper)
            
            # Log successful response
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.logger.info(
                "HTTP request completed",
                request_id=request_id,
                status_code=response_status,
                duration_ms=round(duration, 2)
            )
            
        except Exception as e:
            # Log error response
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.logger.error(
                "HTTP request failed",
                request_id=request_id,
                error=str(e),
                duration_ms=round(duration, 2)
            )
            raise


# Security event logging functions
def log_authentication_success(user_id: str, username: str, ip_address: str = None):
    """Log successful authentication."""
    logger = get_auth_logger()
    logger.info(
        "Authentication successful",
        user_id=user_id,
        username=username,
        ip_address=ip_address,
        event_type="auth_success"
    )


def log_authentication_failure(reason: str, ip_address: str = None, details: dict = None):
    """Log failed authentication attempt."""
    logger = get_auth_logger()
    logger.warning(
        "Authentication failed",
        reason=reason,
        ip_address=ip_address,
        details=details or {},
        event_type="auth_failure"
    )


def log_authorization_failure(user_id: str, resource: str, required_permission: str, ip_address: str = None):
    """Log authorization failure."""
    logger = get_security_logger()
    logger.warning(
        "Authorization denied",
        user_id=user_id,
        resource=resource,
        required_permission=required_permission,
        ip_address=ip_address,
        event_type="authz_failure"
    )


def log_security_event(event_type: str, details: dict, severity: str = "info"):
    """Log general security event."""
    logger = get_security_logger()
    
    log_func = getattr(logger, severity.lower(), logger.info)
    log_func(
        "Security event",
        event_type=event_type,
        details=details
    )


def log_api_access(user_id: str, endpoint: str, method: str, success: bool, duration_ms: float = None):
    """Log API access."""
    logger = get_api_logger()
    
    log_data = {
        "user_id": user_id,
        "endpoint": endpoint,
        "method": method,
        "success": success,
        "event_type": "api_access"
    }
    
    if duration_ms is not None:
        log_data["duration_ms"] = duration_ms
    
    if success:
        logger.info("API access", **log_data)
    else:
        logger.warning("API access failed", **log_data)