"""
Integration tests for core bot framework components.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.event_bus import EventBus, EventType, Event
from core.security_manager import SecurityManager, Permission
from core.validation_manager import ValidationManager, ValidationRule, ValidationType
from core.metrics_collector import MetricsCollector
from core.health_monitor import HealthMonitor, HealthStatus
from core.audit_logger import AuditLogger, AuditEventType
from config.settings import Settings
from utils.exceptions import ValidationError, PermissionDeniedError


class TestCoreFrameworkIntegration:
    """Test integration between core framework components."""
    
    @pytest.fixture
    async def mock_database(self):
        """Mock database manager."""
        db = AsyncMock()
        db.ping = AsyncMock()
        db.test_connection = AsyncMock(return_value=True)
        db.insert_document = AsyncMock()
        db.find_documents = AsyncMock(return_value=[])
        return db
    
    @pytest.fixture
    def mock_bot(self):
        """Mock Discord bot."""
        bot = MagicMock()
        bot.user = MagicMock()
        bot.user.id = 12345
        bot.is_ready = MagicMock(return_value=True)
        bot.latency = 0.1
        bot.guilds = []
        bot.fetch_user = AsyncMock()
        return bot
    
    @pytest.fixture
    def settings(self):
        """Test settings."""
        return Settings(
            discord_token="test_token",
            discord_client_id="test_client_id",
            discord_client_secret="test_secret",
            jwt_secret="test_jwt_secret",
            database_url="mongodb://test:27017/test"
        )
    
    @pytest.fixture
    async def event_bus(self):
        """Event bus instance."""
        return EventBus()
    
    @pytest.fixture
    def security_manager(self, settings):
        """Security manager instance."""
        return SecurityManager(settings)
    
    @pytest.fixture
    def validation_manager(self):
        """Validation manager instance."""
        return ValidationManager()
    
    @pytest.fixture
    def metrics_collector(self):
        """Metrics collector instance."""
        return MetricsCollector()
    
    @pytest.fixture
    async def health_monitor(self, mock_database, mock_bot):
        """Health monitor instance."""
        return HealthMonitor(mock_database, mock_bot)
    
    @pytest.fixture
    async def audit_logger(self, mock_database):
        """Audit logger instance."""
        return AuditLogger(mock_database)
    
    async def test_event_bus_basic_functionality(self, event_bus):
        """Test basic event bus functionality."""
        # Test event subscription and emission
        received_events = []
        
        async def event_handler(event: Event):
            received_events.append(event)
        
        # Subscribe to event
        event_bus.subscribe(EventType.EVENT_CREATED, event_handler)
        
        # Emit event
        await event_bus.emit(
            EventType.EVENT_CREATED,
            {"event_id": "test_123", "title": "Test Event"},
            source="test",
            guild_id="guild_123",
            user_id="user_456"
        )
        
        # Verify event was received
        assert len(received_events) == 1
        event = received_events[0]
        assert event.event_type == EventType.EVENT_CREATED
        assert event.data["event_id"] == "test_123"
        assert event.guild_id == "guild_123"
        assert event.user_id == "user_456"
    
    async def test_event_bus_middleware(self, event_bus, metrics_collector):
        """Test event bus middleware functionality."""
        # Add middleware that modifies events
        def test_middleware(event: Event) -> Event:
            event.data["middleware_processed"] = True
            return event
        
        event_bus.add_middleware(test_middleware)
        
        received_events = []
        
        async def event_handler(event: Event):
            received_events.append(event)
        
        event_bus.subscribe(EventType.USER_JOINED_GUILD, event_handler)
        
        await event_bus.emit(
            EventType.USER_JOINED_GUILD,
            {"user_id": "user_123"},
            source="test"
        )
        
        # Verify middleware processed the event
        assert len(received_events) == 1
        assert received_events[0].data["middleware_processed"] is True
    
    async def test_security_manager_permissions(self, security_manager):
        """Test security manager permission system."""
        # Create mock Discord member
        mock_member = MagicMock()
        mock_member.id = 12345
        mock_member.roles = []
        mock_member.guild_permissions = MagicMock()
        mock_member.guild_permissions.administrator = False
        mock_member.guild_permissions.manage_guild = False
        mock_member.guild_permissions.manage_messages = False
        
        guild_id = 67890
        
        # Test basic member permissions
        permissions = security_manager.get_user_permissions(mock_member, guild_id)
        assert Permission.VIEW_EVENTS in permissions
        assert Permission.CREATE_EVENTS in permissions
        assert Permission.MANAGE_ALL_EVENTS not in permissions
        
        # Test admin permissions
        mock_member.guild_permissions.administrator = True
        admin_permissions = security_manager.get_user_permissions(mock_member, guild_id)
        assert Permission.SYSTEM_ADMIN in admin_permissions
        assert len(admin_permissions) > len(permissions)
    
    async def test_validation_manager_input_validation(self, validation_manager):
        """Test validation manager input validation."""
        # Test valid event title
        valid_title = validation_manager.validate_field(
            "event_title",
            "My Game Night Event"
        )
        assert valid_title == "My Game Night Event"
        
        # Test invalid event title (too short)
        with pytest.raises(ValidationError):
            validation_manager.validate_field("event_title", "Hi")
        
        # Test invalid event title (forbidden content)
        with pytest.raises(ValidationError):
            validation_manager.validate_field("event_title", "Test @everyone")
        
        # Test game name sanitization
        game_name = validation_manager.validate_field(
            "game_name",
            "  among   us  "
        )
        assert game_name == "Among Us"
    
    async def test_metrics_collector_recording(self, metrics_collector):
        """Test metrics collector functionality."""
        # Record various metrics
        await metrics_collector.record_command(
            "test_command",
            duration=0.5,
            success=True,
            guild_id="guild_123",
            user_id="user_456"
        )
        
        metrics_collector.record_counter("test_counter", 5.0, {"type": "test"})
        metrics_collector.record_gauge("test_gauge", 42.0)
        
        # Verify metrics were recorded
        counter_value = metrics_collector.get_counter_value("commands_total", {
            "command": "test_command",
            "success": "true",
            "guild_id": "guild_123"
        })
        assert counter_value == 1.0
        
        gauge_value = metrics_collector.get_gauge_value("test_gauge")
        assert gauge_value == 42.0
        
        # Test command stats
        stats = metrics_collector.get_command_stats()
        assert "test_command" in stats
        assert stats["test_command"]["total_executions"] == 1
        assert stats["test_command"]["success_rate"] == 1.0
    
    async def test_health_monitor_checks(self, health_monitor, mock_database):
        """Test health monitor functionality."""
        # Run health checks
        results = await health_monitor.run_all_checks()
        
        # Verify health checks ran
        assert "database" in results
        assert "discord_api" in results
        assert "bot_connectivity" in results
        
        # Verify database check
        db_check = results["database"]
        assert db_check.name == "database"
        assert db_check.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
        
        # Test overall health status
        overall_status = health_monitor.get_overall_health()
        assert isinstance(overall_status, HealthStatus)
    
    async def test_audit_logger_functionality(self, audit_logger, mock_database):
        """Test audit logger functionality."""
        # Log various audit events
        await audit_logger.log_event(
            event_type=AuditEventType.EVENT_CREATED,
            action="Created test event",
            user_id="user_123",
            guild_id="guild_456",
            resource_id="event_789",
            resource_type="event",
            details={"title": "Test Event"}
        )
        
        await audit_logger.log_security_event(
            event_type=AuditEventType.RATE_LIMIT_EXCEEDED,
            action="Rate limit exceeded",
            user_id="user_123",
            severity="medium"
        )
        
        # Verify database calls were made
        assert mock_database.insert_document.call_count == 2
        
        # Verify correct collection was used
        calls = mock_database.insert_document.call_args_list
        for call in calls:
            assert call[0][0] == "audit_logs"  # Collection name
    
    async def test_integrated_error_handling(self, event_bus, audit_logger):
        """Test integrated error handling across components."""
        # Add middleware that raises an exception
        def failing_middleware(event: Event) -> Event:
            raise ValueError("Test middleware error")
        
        event_bus.add_middleware(failing_middleware)
        
        received_events = []
        
        async def event_handler(event: Event):
            received_events.append(event)
        
        # Subscribe to both original and error events
        event_bus.subscribe(EventType.EVENT_CREATED, event_handler)
        event_bus.subscribe(EventType.ERROR_OCCURRED, event_handler)
        
        # Emit event that will trigger middleware error
        await event_bus.emit(
            EventType.EVENT_CREATED,
            {"test": "data"},
            source="test"
        )
        
        # Should receive error event due to middleware failure
        error_events = [e for e in received_events if e.event_type == EventType.ERROR_OCCURRED]
        assert len(error_events) > 0
        
        error_event = error_events[0]
        assert "error_type" in error_event.data
        assert error_event.data["error_type"] == "ValueError"
    
    async def test_rate_limiting_integration(self, security_manager):
        """Test rate limiting functionality."""
        identifier = "test_user_123"
        
        # Should not be rate limited initially
        security_manager.check_rate_limit(identifier, max_requests=2, window_seconds=60)
        security_manager.check_rate_limit(identifier, max_requests=2, window_seconds=60)
        
        # Third request should be rate limited
        with pytest.raises(Exception):  # Should raise RateLimitedError
            security_manager.check_rate_limit(identifier, max_requests=2, window_seconds=60)
    
    async def test_permission_and_validation_integration(self, security_manager, validation_manager):
        """Test integration between permission and validation systems."""
        # Create mock member with basic permissions
        mock_member = MagicMock()
        mock_member.id = 12345
        mock_member.roles = []
        mock_member.guild_permissions = MagicMock()
        mock_member.guild_permissions.administrator = False
        mock_member.guild_permissions.manage_guild = False
        mock_member.guild_permissions.manage_messages = False
        
        guild_id = 67890
        
        # Test permission check
        has_create_permission = security_manager.check_permission(
            mock_member, guild_id, Permission.CREATE_EVENTS
        )
        assert has_create_permission is True
        
        # Test validation of event data
        event_data = {
            "title": "Valid Event Title",
            "description": "This is a valid event description"
        }
        
        validated_data = validation_manager.validate_data(event_data)
        assert validated_data["title"] == "Valid Event Title"
        assert "description" in validated_data


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])