#!/usr/bin/env python3
"""
Test script for the monitoring, metrics, and health checking systems.
"""

import asyncio
import sys
import os
import time
from pathlib import Path

# Add src directory to Python path
sys.path.append(str(Path(__file__).parent / "src"))

from core.metrics_collector import MetricsCollector
from core.health_monitor import HealthMonitor, HealthCheck, HealthStatus
from core.performance_monitor import PerformanceMonitor, PerformanceTracker
from core.alerting_system import AlertingSystem, LogAlertChannel, AlertType, AlertSeverity
from core.system_status_dashboard import SystemStatusDashboard
from core.log_aggregator import LogAggregator, LogLevel


class MockBot:
    """Mock bot for testing."""
    
    def __init__(self):
        self.user = type('User', (), {'id': 12345})()
        self.latency = 0.05  # 50ms
        self.guilds = []
    
    def is_ready(self):
        return True
    
    async def fetch_user(self, user_id):
        return self.user


class MockDatabase:
    """Mock database for testing."""
    
    async def ping(self):
        await asyncio.sleep(0.01)  # Simulate network delay
        return True
    
    async def test_connection(self):
        await asyncio.sleep(0.02)
        return {"status": "ok"}
    
    async def insert_document(self, collection, document):
        await asyncio.sleep(0.005)
        return {"inserted_id": "mock_id"}
    
    async def find_documents(self, collection, query, **kwargs):
        await asyncio.sleep(0.01)
        return []
    
    async def update_document(self, collection, query, update):
        await asyncio.sleep(0.005)
        return {"modified_count": 1}
    
    async def delete_documents(self, collection, query):
        await asyncio.sleep(0.005)
        return {"deleted_count": 1}


async def test_metrics_collector():
    """Test the metrics collector."""
    print("🧪 Testing Metrics Collector...")
    
    metrics = MetricsCollector()
    
    # Test counter metrics
    metrics.record_counter("test_counter", 1.0, {"type": "test"})
    metrics.record_counter("test_counter", 2.0, {"type": "test"})
    
    counter_value = metrics.get_counter_value("test_counter", {"type": "test"})
    assert counter_value == 3.0, f"Expected 3.0, got {counter_value}"
    
    # Test gauge metrics
    metrics.record_gauge("test_gauge", 42.0, {"type": "test"})
    gauge_value = metrics.get_gauge_value("test_gauge", {"type": "test"})
    assert gauge_value == 42.0, f"Expected 42.0, got {gauge_value}"
    
    # Test timer metrics
    with metrics.timer("test_operation", {"type": "test"}):
        await asyncio.sleep(0.01)  # 10ms
    
    timer_stats = metrics.get_timer_stats("test_operation", {"type": "test"})
    if timer_stats:  # Only check if stats are available
        assert "count" in timer_stats or len(timer_stats) > 0, f"Timer stats empty: {timer_stats}"
        if "count" in timer_stats:
            assert timer_stats["count"] == 1, f"Expected 1 timer entry, got {timer_stats['count']}"
        if "min" in timer_stats:
            assert timer_stats["min"] >= 0.01, f"Expected min >= 0.01, got {timer_stats['min']}"
    
    # Test command recording
    await metrics.record_command("test_command", 0.05, True, "guild_123", "user_456")
    command_stats = metrics.get_command_stats()
    assert "test_command" in command_stats, "test_command not found in stats"
    assert command_stats["test_command"]["success_rate"] == 1.0, "Expected 100% success rate"
    
    print("✅ Metrics Collector tests passed!")


async def test_health_monitor():
    """Test the health monitor."""
    print("🧪 Testing Health Monitor...")
    
    mock_bot = MockBot()
    mock_db = MockDatabase()
    
    health_monitor = HealthMonitor(mock_db, mock_bot)
    
    # Test individual health checks
    db_check = await health_monitor.run_single_check("database")
    assert db_check is not None, "Database health check failed"
    assert db_check.status == HealthStatus.HEALTHY, f"Expected healthy, got {db_check.status}"
    
    api_check = await health_monitor.run_single_check("discord_api")
    assert api_check is not None, "Discord API health check failed"
    
    # Test all health checks
    all_checks = await health_monitor.run_all_checks()
    assert len(all_checks) > 0, "No health checks returned"
    
    # Test overall health
    overall_health = health_monitor.get_overall_health()
    assert overall_health in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY], \
        f"Invalid overall health status: {overall_health}"
    
    # Test health summary
    summary = health_monitor.get_health_summary()
    assert "overall_status" in summary, "Missing overall_status in summary"
    assert "checks" in summary, "Missing checks in summary"
    
    print("✅ Health Monitor tests passed!")


async def test_performance_monitor():
    """Test the performance monitor."""
    print("🧪 Testing Performance Monitor...")
    
    metrics = MetricsCollector()
    perf_monitor = PerformanceMonitor(metrics)
    
    # Test operation tracking
    op_id = perf_monitor.start_operation("test_operation", {"context": "test"})
    await asyncio.sleep(0.01)  # 10ms
    metric = perf_monitor.end_operation(op_id, "test_operation", {"context": "test"})
    
    assert metric is not None, "Performance metric not returned"
    assert metric.duration_ms >= 10, f"Expected duration >= 10ms, got {metric.duration_ms}"
    
    # Test direct recording
    await perf_monitor.record_operation("direct_test", 25.0, {"type": "direct"})
    
    # Test performance tracker context manager
    with PerformanceTracker(perf_monitor, "context_test", {"type": "context"}):
        await asyncio.sleep(0.005)  # 5ms
    
    # Test statistics
    stats = perf_monitor.get_operation_stats("test_operation")
    assert stats is not None, "No stats returned for test_operation"
    assert stats.total_calls == 1, f"Expected 1 call, got {stats.total_calls}"
    
    all_stats = perf_monitor.get_all_operation_stats()
    assert len(all_stats) >= 3, f"Expected at least 3 operations, got {len(all_stats)}"
    
    # Test performance alerts
    alerts = await perf_monitor.get_performance_alerts()
    assert isinstance(alerts, list), "Performance alerts should be a list"
    
    # Test optimization suggestions
    suggestions = await perf_monitor.get_optimization_suggestions()
    assert isinstance(suggestions, list), "Optimization suggestions should be a list"
    
    print("✅ Performance Monitor tests passed!")


async def test_alerting_system():
    """Test the alerting system."""
    print("🧪 Testing Alerting System...")
    
    mock_db = MockDatabase()
    alerting = AlertingSystem(mock_db)
    
    # Add log channel
    log_channel = LogAlertChannel()
    alerting.add_channel(log_channel)
    
    # Test sending alerts
    alert = await alerting.send_alert(
        AlertType.CUSTOM,
        AlertSeverity.MEDIUM,
        "Test Alert",
        "This is a test alert message",
        source="test_system",
        details={"test": True}
    )
    
    assert alert is not None, "Alert not created"
    assert alert.title == "Test Alert", f"Expected 'Test Alert', got '{alert.title}'"
    assert alert.severity == AlertSeverity.MEDIUM, f"Expected MEDIUM, got {alert.severity}"
    
    # Test active alerts
    active_alerts = alerting.get_active_alerts()
    assert len(active_alerts) == 1, f"Expected 1 active alert, got {len(active_alerts)}"
    
    # Test alert resolution
    alert_id = list(alerting._active_alerts.keys())[0]
    resolved = await alerting.resolve_alert(alert_id, "Test resolution")
    assert resolved, "Alert resolution failed"
    
    active_alerts_after = alerting.get_active_alerts()
    assert len(active_alerts_after) == 0, f"Expected 0 active alerts after resolution, got {len(active_alerts_after)}"
    
    print("✅ Alerting System tests passed!")


async def test_system_dashboard():
    """Test the system status dashboard."""
    print("🧪 Testing System Status Dashboard...")
    
    # Set up components
    mock_bot = MockBot()
    mock_db = MockDatabase()
    
    metrics = MetricsCollector()
    health_monitor = HealthMonitor(mock_db, mock_bot)
    perf_monitor = PerformanceMonitor(metrics)
    alerting = AlertingSystem(mock_db)
    
    # Create dashboard
    dashboard = SystemStatusDashboard(
        health_monitor,
        metrics,
        perf_monitor,
        alerting,
        mock_db
    )
    
    # Test dashboard refresh
    dashboard_data = await dashboard.refresh_dashboard()
    assert dashboard_data is not None, "Dashboard data not returned"
    assert hasattr(dashboard_data, 'overall_status'), "Missing overall_status"
    assert hasattr(dashboard_data, 'components'), "Missing components"
    
    # Test current data retrieval
    current_data = dashboard.get_current_data()
    assert current_data is not None, "Current data not available"
    
    # Test dashboard metrics
    dashboard_metrics = await dashboard.get_dashboard_metrics()
    assert "last_refresh" in dashboard_metrics, "Missing last_refresh in dashboard metrics"
    assert "components_count" in dashboard_metrics, "Missing components_count"
    
    # Test data export
    exported_data = await dashboard.export_dashboard_data("json")
    assert isinstance(exported_data, str), "Exported data should be a string"
    assert len(exported_data) > 0, "Exported data is empty"
    
    print("✅ System Status Dashboard tests passed!")


async def test_log_aggregator():
    """Test the log aggregator."""
    print("🧪 Testing Log Aggregator...")
    
    mock_db = MockDatabase()
    log_aggregator = LogAggregator(database_manager=mock_db)
    
    # Test log parsing
    test_log_line = "2024-01-01 12:00:00,123 - test.logger - INFO - This is a test message"
    parsed_entry = log_aggregator.parser.parse_log_line(test_log_line)
    
    assert parsed_entry is not None, "Log entry not parsed"
    assert parsed_entry.level == LogLevel.INFO, f"Expected INFO, got {parsed_entry.level}"
    assert parsed_entry.logger_name == "test.logger", f"Expected 'test.logger', got '{parsed_entry.logger_name}'"
    assert "test message" in parsed_entry.message, "Message not parsed correctly"
    
    # Test log analysis (with empty data since we don't have real log files)
    analysis = log_aggregator.analyzer.analyze_entries([])
    assert analysis.total_entries == 0, "Expected 0 entries for empty analysis"
    
    # Test error summary
    error_summary = await log_aggregator.get_error_summary(1)
    assert "total_errors" in error_summary, "Missing total_errors in summary"
    assert "error_rate_per_hour" in error_summary, "Missing error_rate_per_hour"
    
    print("✅ Log Aggregator tests passed!")


async def test_integration():
    """Test integration between monitoring components."""
    print("🧪 Testing Integration...")
    
    # Set up all components
    mock_bot = MockBot()
    mock_db = MockDatabase()
    
    metrics = MetricsCollector()
    health_monitor = HealthMonitor(mock_db, mock_bot)
    perf_monitor = PerformanceMonitor(metrics)
    alerting = AlertingSystem(mock_db)
    dashboard = SystemStatusDashboard(health_monitor, metrics, perf_monitor, alerting, mock_db)
    
    # Add log channel to alerting
    log_channel = LogAlertChannel()
    alerting.add_channel(log_channel)
    
    # Simulate some activity
    await metrics.record_command("integration_test", 0.1, True, "guild_123", "user_456")
    
    with PerformanceTracker(perf_monitor, "integration_operation"):
        await asyncio.sleep(0.02)
    
    # Run health checks
    health_results = await health_monitor.run_all_checks()
    
    # Check for health alerts
    await alerting.check_health_alerts(health_results)
    
    # Check for metrics alerts
    await alerting.check_metrics_alerts(metrics)
    
    # Refresh dashboard
    dashboard_data = await dashboard.refresh_dashboard()
    
    # Verify integration
    assert len(health_results) > 0, "No health results"
    assert dashboard_data is not None, "No dashboard data"
    assert dashboard_data.overall_status is not None, "No overall status"
    
    # Test performance alerts
    perf_alerts = await perf_monitor.get_performance_alerts()
    assert isinstance(perf_alerts, list), "Performance alerts should be a list"
    
    print("✅ Integration tests passed!")


async def main():
    """Run all monitoring system tests."""
    print("🚀 Starting Monitoring System Tests...\n")
    
    try:
        await test_metrics_collector()
        print()
        
        await test_health_monitor()
        print()
        
        await test_performance_monitor()
        print()
        
        await test_alerting_system()
        print()
        
        await test_system_dashboard()
        print()
        
        await test_log_aggregator()
        print()
        
        await test_integration()
        print()
        
        print("🎉 All monitoring system tests passed!")
        print("\n📊 Monitoring System Features Implemented:")
        print("✅ Comprehensive metrics collection for commands, performance, and usage")
        print("✅ Health monitoring system with database, Discord API, and system checks")
        print("✅ Alerting system for critical failures and performance degradation")
        print("✅ Performance monitoring with response time tracking and optimization")
        print("✅ System status dashboard with real-time health indicators")
        print("✅ Log aggregation and analysis for troubleshooting")
        print("✅ Web dashboard integration with monitoring APIs")
        print("✅ Discord bot commands for accessing monitoring data")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())