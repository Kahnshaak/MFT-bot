"""
Tests for the core bot framework and event bus system.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.event_bus import EventBus, EventType, Event
from core.security_manager import SecurityManager, Permission
from core.validation_manager import ValidationManager, ValidationRule, ValidationType
from core.metrics_collector import MetricsCollector
from core.audit_logger import AuditLogger, AuditEventType
from config.settings import Settings


class TestEventBus:
    """Test the event bus system."""
    
    @pytest.fixture
    def event_bus(self):
        return EventBus()
    
    def test_event_bus_initialization(self, event_bus):
        """Test event bus initializes correctly."""
        assert event_bus is not None
        assert len(event_bus._subscribers) == 0
        assert len(event_bus._middleware) == 0
    
    def test_subscribe_and_emit(self, event_bus):
        """Test subscribing to events and emitting them."""
        callback_called = False
        received_event = None
        
        def callback(event):
            nonlocal callback_called, received_event
            callback_called = True
            received_event = event
        
        # Subscribe to event
        event_bus.subscribe(EventType.EVENT_CREATED, callback)
        
        # Emit event
        asyncio.run(event_bus.emit(
            EventType.EVENT_CREATED,
            {"test": "data"},
            source="test"
        ))
        
        assert callback_called
        assert received_event is not None
        assert received_event.event_type == EventType.EVENT_CREATED
        assert received_event.data == {"test": "data"}
        assert received_event.source == "test"
    
    def test_middleware(self, event_bus):
        """Test event bus middleware."""
        middleware_called = False
        
        def middleware(event):
            nonlocal middleware_called
            middleware_called = True
            event.data["middleware_processed"] = True
            return event
        
        def callback(event):
            assert event.data.get("middleware_processed") is True
        
        event_bus.add_middleware(middleware)
        event_bus.subscribe(EventType.EVENT_CREATED, callback)
        
        asyncio.run(event_bus.emit(
            EventType.EVENT_CREATED,
            {"test": "data"}
        ))
        
        assert middleware_called


class TestSecurityManager:
    """Test the security manager."""
    
    @pytest.fixture
    def settings(self):
        return Settings(
            discord_token="test_token",
            discord_client_id="test_client_id",
            discord_client_secret="test_client_secret",
            jwt_secret="test_jwt_secret"
        )
    
    @pytest.fixture
    def security_manager(self, settings):
        return SecurityManager(settings)
    
    def test_security_manager_initialization(self, security_manager):
        """Test security manager initializes correctly."""
        assert security_manager is not None
        assert len(security_manager._role_mappings) == 0
    
    def test_permission_configuration(self, security_manager):
        """Test configuring role permissions."""
        guild_id = 123456789
        role_id = 987654321
        permissions = {Permission.CREATE_EVENTS, Permission.MANAGE_OWN_EVENTS}
        
        security_manager.configure_role_mapping(guild_id, role_id, permissions)
        
        assert guild_id in security_manager._role_mappings
        assert role_id in security_manager._role_mappings[guild_id]
        assert security_manager._role_mappings[guild_id][role_id].permissions == permissions
    
    def test_input_validation(self, security_manager):
        """Test input validation."""
        # Valid input
        result = security_manager.validate_input("Hello World", max_length=20)
        assert result == "Hello World"
        
        # Input too long
        with pytest.raises(Exception):  # ValidationError
            security_manager.validate_input("x" * 100, max_length=10)
        
        # Forbidden characters
        with pytest.raises(Exception):  # ValidationError
            security_manager.validate_input("test@everyone", forbidden_patterns=["@everyone"])


class TestValidationManager:
    """Test the validation manager."""
    
    @pytest.fixture
    def validation_manager(self):
        return ValidationManager()
    
    def test_validation_manager_initialization(self, validation_manager):
        """Test validation manager initializes correctly."""
        assert validation_manager is not None
        assert len(validation_manager._global_rules) > 0
    
    def test_string_validation(self, validation_manager):
        """Test string validation."""
        rule = ValidationRule(
            field_name="test_field",
            validation_type=ValidationType.STRING,
            min_length=3,
            max_length=10
        )
        
        # Valid string
        result = validation_manager.validate_field("test_field", "hello", rule)
        assert result == "hello"
        
        # Too short
        with pytest.raises(Exception):  # ValidationError
            validation_manager.validate_field("test_field", "hi", rule)
        
        # Too long
        with pytest.raises(Exception):  # ValidationError
            validation_manager.validate_field("test_field", "this is too long", rule)
    
    def test_event_title_validation(self, validation_manager):
        """Test event title validation using global rules."""
        # Valid title
        result = validation_manager.validate_field("event_title", "Game Night Friday")
        assert "Game Night Friday" in result
        
        # Title with forbidden content
        with pytest.raises(Exception):  # ValidationError
            validation_manager.validate_field("event_title", "Game Night @everyone")


class TestMetricsCollector:
    """Test the metrics collector."""
    
    @pytest.fixture
    def metrics_collector(self):
        return MetricsCollector()
    
    def test_metrics_collector_initialization(self, metrics_collector):
        """Test metrics collector initializes correctly."""
        assert metrics_collector is not None
        assert len(metrics_collector._counters) == 0
    
    def test_counter_metrics(self, metrics_collector):
        """Test counter metrics."""
        metrics_collector.record_counter("test_counter", 5.0)
        
        value = metrics_collector.get_counter_value("test_counter")
        assert value == 5.0
        
        # Increment counter
        metrics_collector.record_counter("test_counter", 3.0)
        value = metrics_collector.get_counter_value("test_counter")
        assert value == 8.0
    
    def test_gauge_metrics(self, metrics_collector):
        """Test gauge metrics."""
        metrics_collector.record_gauge("test_gauge", 42.0)
        
        value = metrics_collector.get_gauge_value("test_gauge")
        assert value == 42.0
        
        # Update gauge
        metrics_collector.record_gauge("test_gauge", 100.0)
        value = metrics_collector.get_gauge_value("test_gauge")
        assert value == 100.0
    
    @pytest.mark.asyncio
    async def test_command_metrics(self, metrics_collector):
        """Test command execution metrics."""
        await metrics_collector.record_command(
            command_name="test_command",
            duration=0.5,
            success=True,
            guild_id="123456789",
            user_id="987654321"
        )
        
        stats = metrics_collector.get_command_stats()
        assert "test_command" in stats
        assert stats["test_command"]["total_executions"] == 1
        assert stats["test_command"]["success_rate"] == 1.0


class TestAuditLogger:
    """Test the audit logger."""
    
    @pytest.fixture
    def mock_database(self):
        database = Mock()
        database.insert_document = AsyncMock()
        database.find_documents = AsyncMock(return_value=[])
        return database
    
    @pytest.fixture
    def audit_logger(self, mock_database):
        return AuditLogger(mock_database)
    
    @pytest.mark.asyncio
    async def test_audit_logger_initialization(self, audit_logger):
        """Test audit logger initializes correctly."""
        assert audit_logger is not None
        assert audit_logger._audit_collection == "audit_logs"
    
    @pytest.mark.asyncio
    async def test_log_event(self, audit_logger, mock_database):
        """Test logging audit events."""
        await audit_logger.log_event(
            event_type=AuditEventType.EVENT_CREATED,
            action="Created new event",
            user_id="123456789",
            guild_id="987654321",
            resource_id="event_123",
            resource_type="event"
        )
        
        # Verify database was called
        mock_database.insert_document.assert_called_once()
        call_args = mock_database.insert_document.call_args[0]
        assert call_args[0] == "audit_logs"  # collection name
        
        # Verify event data
        event_data = call_args[1]
        assert event_data["event_type"] == AuditEventType.EVENT_CREATED
        assert event_data["action"] == "Created new event"
        assert event_data["user_id"] == "123456789"
        assert event_data["guild_id"] == "987654321"
    
    @pytest.mark.asyncio
    async def test_log_security_event(self, audit_logger, mock_database):
        """Test logging security events."""
        await audit_logger.log_security_event(
            event_type=AuditEventType.RATE_LIMIT_EXCEEDED,
            action="Rate limit exceeded",
            user_id="123456789",
            severity="high"
        )
        
        mock_database.insert_document.assert_called_once()
        call_args = mock_database.insert_document.call_args[0]
        event_data = call_args[1]
        
        assert event_data["details"]["severity"] == "high"


class TestIntegration:
    """Test integration between core components."""
    
    @pytest.mark.asyncio
    async def test_event_bus_with_metrics(self):
        """Test event bus integration with metrics collector."""
        event_bus = EventBus()
        metrics = MetricsCollector()
        
        # Add metrics middleware
        def metrics_middleware(event):
            metrics.record_counter("events_processed", 1.0)
            return event
        
        event_bus.add_middleware(metrics_middleware)
        
        # Emit event
        await event_bus.emit(EventType.EVENT_CREATED, {"test": "data"})
        
        # Check metrics
        assert metrics.get_counter_value("events_processed") == 1.0
    
    @pytest.mark.asyncio
    async def test_validation_with_security(self):
        """Test validation manager integration with security manager."""
        settings = Settings(
            discord_token="test_token",
            discord_client_id="test_client_id", 
            discord_client_secret="test_client_secret",
            jwt_secret="test_jwt_secret"
        )
        
        validation = ValidationManager()
        security = SecurityManager(settings)
        
        # Test that validation catches security issues
        with pytest.raises(Exception):  # ValidationError
            validation.validate_field("event_title", "Test @everyone event")
        
        # Test that security validation also works
        with pytest.raises(Exception):  # ValidationError
            security.validate_input("Test @everyone", forbidden_patterns=["@everyone"])


if __name__ == "__main__":
    pytest.main([__file__])