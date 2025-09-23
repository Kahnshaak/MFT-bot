"""
Core framework package for the Discord Game Night Bot.

This package contains the core systems including event bus, security,
validation, metrics, and other foundational components.
"""

from .event_bus import EventBus, EventType, Event as BusEvent
from .security_manager import SecurityManager, Permission
from .validation_manager import ValidationManager
from .metrics_collector import MetricsCollector
from .health_monitor import HealthMonitor
from .audit_logger import AuditLogger, AuditEventType
from .permission_decorators import (
    require_permission, require_any_permission, rate_limit, 
    validate_input, has_permission, has_any_permission
)

__all__ = [
    # Event bus
    'EventBus', 'EventType', 'BusEvent',
    
    # Security
    'SecurityManager', 'Permission',
    
    # Validation
    'ValidationManager',
    
    # Monitoring
    'MetricsCollector', 'HealthMonitor',
    
    # Audit
    'AuditLogger', 'AuditEventType',
    
    # Decorators
    'require_permission', 'require_any_permission', 'rate_limit',
    'validate_input', 'has_permission', 'has_any_permission'
]