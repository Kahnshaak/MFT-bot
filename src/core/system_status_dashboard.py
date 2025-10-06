"""
System status dashboard with real-time health indicators.
"""

import time
import asyncio
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json

from utils.logging_config import get_logger, LoggerMixin
from core.health_monitor import HealthMonitor, HealthStatus, HealthCheck
from core.metrics_collector import MetricsCollector
from core.performance_monitor import PerformanceMonitor
from core.alerting_system import AlertingSystem, Alert


class DashboardStatus(Enum):
    """Overall dashboard status."""
    
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class SystemComponent:
    """Represents a system component status."""
    
    name: str
    status: DashboardStatus
    message: str
    last_updated: float = field(default_factory=time.time)
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "last_updated": self.last_updated,
            "details": self.details
        }


@dataclass
class DashboardData:
    """Complete dashboard data structure."""
    
    overall_status: DashboardStatus
    components: List[SystemComponent]
    metrics_summary: Dict[str, Any]
    performance_summary: Dict[str, Any]
    active_alerts: List[Dict[str, Any]]
    system_info: Dict[str, Any]
    last_updated: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "overall_status": self.overall_status.value,
            "components": [comp.to_dict() for comp in self.components],
            "metrics_summary": self.metrics_summary,
            "performance_summary": self.performance_summary,
            "active_alerts": self.active_alerts,
            "system_info": self.system_info,
            "last_updated": self.last_updated
        }


class SystemStatusDashboard(LoggerMixin):
    """
    Real-time system status dashboard with health indicators.
    """
    
    def __init__(
        self,
        health_monitor: HealthMonitor,
        metrics_collector: MetricsCollector,
        performance_monitor: PerformanceMonitor,
        alerting_system: AlertingSystem,
        database_manager=None
    ):
        self.health_monitor = health_monitor
        self.metrics = metrics_collector
        self.performance_monitor = performance_monitor
        self.alerting_system = alerting_system
        self.database = database_manager
        
        # Dashboard state
        self._current_data: Optional[DashboardData] = None
        self._update_callbacks: List[Callable] = []
        self._auto_refresh_task: Optional[asyncio.Task] = None
        self._refresh_interval = 30  # seconds
        
        # Component status cache
        self._component_cache: Dict[str, SystemComponent] = {}
    
    def add_update_callback(self, callback: Callable[[DashboardData], None]) -> None:
        """Add callback to be called when dashboard data updates."""
        self._update_callbacks.append(callback)
    
    async def start_auto_refresh(self, interval_seconds: int = 30) -> None:
        """Start automatic dashboard refresh."""
        self._refresh_interval = interval_seconds
        
        if self._auto_refresh_task and not self._auto_refresh_task.done():
            self._auto_refresh_task.cancel()
        
        self._auto_refresh_task = asyncio.create_task(self._auto_refresh_loop())
        self.logger.info(f"Started dashboard auto-refresh with {interval_seconds}s interval")
    
    async def stop_auto_refresh(self) -> None:
        """Stop automatic dashboard refresh."""
        if self._auto_refresh_task and not self._auto_refresh_task.done():
            self._auto_refresh_task.cancel()
            try:
                await self._auto_refresh_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Stopped dashboard auto-refresh")
    
    async def _auto_refresh_loop(self) -> None:
        """Auto-refresh loop."""
        while True:
            try:
                await self.refresh_dashboard()
                await asyncio.sleep(self._refresh_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in dashboard auto-refresh: {e}")
                await asyncio.sleep(self._refresh_interval)
    
    async def refresh_dashboard(self) -> DashboardData:
        """Refresh all dashboard data."""
        try:
            # Collect all data
            health_data = await self._collect_health_data()
            metrics_data = await self._collect_metrics_data()
            performance_data = await self._collect_performance_data()
            alerts_data = await self._collect_alerts_data()
            system_data = await self._collect_system_data()
            
            # Create components list
            components = []
            
            # Add health components
            for name, health_check in health_data.items():
                status = self._health_to_dashboard_status(health_check.status)
                component = SystemComponent(
                    name=f"Health: {name}",
                    status=status,
                    message=health_check.message,
                    details={
                        "duration_ms": health_check.duration_ms,
                        "timestamp": health_check.timestamp,
                        "details": health_check.details or {}
                    }
                )
                components.append(component)
                self._component_cache[component.name] = component
            
            # Add performance components
            perf_alerts = await self.performance_monitor.get_performance_alerts()
            if perf_alerts:
                for alert in perf_alerts[:5]:  # Limit to top 5
                    status = DashboardStatus.WARNING if alert["severity"] == "medium" else DashboardStatus.CRITICAL
                    component = SystemComponent(
                        name=f"Performance: {alert['operation']}",
                        status=status,
                        message=alert["message"],
                        details=alert.get("details", {})
                    )
                    components.append(component)
            
            # Calculate overall status
            overall_status = self._calculate_overall_status(components, alerts_data)
            
            # Create dashboard data
            dashboard_data = DashboardData(
                overall_status=overall_status,
                components=components,
                metrics_summary=metrics_data,
                performance_summary=performance_data,
                active_alerts=alerts_data,
                system_info=system_data
            )
            
            self._current_data = dashboard_data
            
            # Notify callbacks
            for callback in self._update_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(dashboard_data)
                    else:
                        callback(dashboard_data)
                except Exception as e:
                    self.logger.error(f"Error in dashboard update callback: {e}")
            
            self.logger.debug("Dashboard data refreshed successfully")
            return dashboard_data
            
        except Exception as e:
            self.logger.error(f"Error refreshing dashboard: {e}")
            
            # Return cached data or minimal data
            if self._current_data:
                return self._current_data
            else:
                return DashboardData(
                    overall_status=DashboardStatus.UNKNOWN,
                    components=[],
                    metrics_summary={},
                    performance_summary={},
                    active_alerts=[],
                    system_info={"error": str(e)}
                )
    
    async def _collect_health_data(self) -> Dict[str, HealthCheck]:
        """Collect health monitoring data."""
        try:
            return await self.health_monitor.run_all_checks()
        except Exception as e:
            self.logger.error(f"Error collecting health data: {e}")
            return {}
    
    async def _collect_metrics_data(self) -> Dict[str, Any]:
        """Collect metrics data."""
        try:
            system_stats = self.metrics.get_system_stats()
            command_stats = self.metrics.get_command_stats()
            
            # Calculate summary metrics
            total_commands = sum(stats["total_executions"] for stats in command_stats.values())
            total_errors = sum(stats["error_count"] for stats in command_stats.values())
            avg_success_rate = (
                sum(stats["success_rate"] for stats in command_stats.values()) / len(command_stats)
                if command_stats else 1.0
            )
            
            return {
                "system_stats": system_stats,
                "command_summary": {
                    "total_commands": total_commands,
                    "total_errors": total_errors,
                    "avg_success_rate": avg_success_rate,
                    "unique_commands": len(command_stats)
                },
                "top_commands": sorted(
                    [(name, stats["total_executions"]) for name, stats in command_stats.items()],
                    key=lambda x: x[1],
                    reverse=True
                )[:10]
            }
        except Exception as e:
            self.logger.error(f"Error collecting metrics data: {e}")
            return {"error": str(e)}
    
    async def _collect_performance_data(self) -> Dict[str, Any]:
        """Collect performance monitoring data."""
        try:
            return self.performance_monitor.get_performance_summary()
        except Exception as e:
            self.logger.error(f"Error collecting performance data: {e}")
            return {"error": str(e)}
    
    async def _collect_alerts_data(self) -> List[Dict[str, Any]]:
        """Collect active alerts data."""
        try:
            active_alerts = self.alerting_system.get_active_alerts()
            return [alert.to_dict() for alert in active_alerts]
        except Exception as e:
            self.logger.error(f"Error collecting alerts data: {e}")
            return []
    
    async def _collect_system_data(self) -> Dict[str, Any]:
        """Collect system information."""
        try:
            import psutil
            import platform
            
            # Get system info
            system_info = {
                "platform": platform.system(),
                "platform_version": platform.version(),
                "python_version": platform.python_version(),
                "uptime_seconds": self.metrics.get_system_stats().get("uptime_seconds", 0)
            }
            
            # Get process info
            try:
                process = psutil.Process()
                memory_info = process.memory_info()
                cpu_percent = process.cpu_percent()
                
                system_info.update({
                    "memory_usage_mb": memory_info.rss / 1024 / 1024,
                    "memory_usage_percent": process.memory_percent(),
                    "cpu_usage_percent": cpu_percent,
                    "num_threads": process.num_threads(),
                    "num_fds": process.num_fds() if hasattr(process, 'num_fds') else None
                })
            except Exception as e:
                system_info["process_info_error"] = str(e)
            
            # Get database info if available
            if self.database:
                try:
                    # This would need to be implemented based on your database manager
                    system_info["database_connected"] = True
                except Exception as e:
                    system_info["database_error"] = str(e)
            
            return system_info
            
        except ImportError:
            return {
                "platform": "unknown",
                "psutil_available": False,
                "uptime_seconds": self.metrics.get_system_stats().get("uptime_seconds", 0)
            }
        except Exception as e:
            self.logger.error(f"Error collecting system data: {e}")
            return {"error": str(e)}
    
    def _health_to_dashboard_status(self, health_status: HealthStatus) -> DashboardStatus:
        """Convert health status to dashboard status."""
        mapping = {
            HealthStatus.HEALTHY: DashboardStatus.HEALTHY,
            HealthStatus.DEGRADED: DashboardStatus.WARNING,
            HealthStatus.UNHEALTHY: DashboardStatus.CRITICAL,
            HealthStatus.UNKNOWN: DashboardStatus.UNKNOWN
        }
        return mapping.get(health_status, DashboardStatus.UNKNOWN)
    
    def _calculate_overall_status(
        self, 
        components: List[SystemComponent], 
        active_alerts: List[Dict[str, Any]]
    ) -> DashboardStatus:
        """Calculate overall system status."""
        if not components:
            return DashboardStatus.UNKNOWN
        
        # Check for critical alerts
        critical_alerts = [a for a in active_alerts if a.get("severity") == "critical"]
        if critical_alerts:
            return DashboardStatus.CRITICAL
        
        # Check component statuses
        component_statuses = [comp.status for comp in components]
        
        if any(status == DashboardStatus.CRITICAL for status in component_statuses):
            return DashboardStatus.CRITICAL
        elif any(status == DashboardStatus.WARNING for status in component_statuses):
            return DashboardStatus.WARNING
        elif all(status == DashboardStatus.HEALTHY for status in component_statuses):
            return DashboardStatus.HEALTHY
        else:
            return DashboardStatus.UNKNOWN
    
    def get_current_data(self) -> Optional[DashboardData]:
        """Get current dashboard data."""
        return self._current_data
    
    async def get_component_history(
        self, 
        component_name: str, 
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get historical data for a specific component."""
        if not self.database:
            return []
        
        try:
            start_time = time.time() - (hours * 3600)
            
            # This would need to be implemented based on how you store historical data
            # For now, return empty list
            return []
            
        except Exception as e:
            self.logger.error(f"Error getting component history: {e}")
            return []
    
    async def export_dashboard_data(self, format_type: str = "json") -> str:
        """Export dashboard data in specified format."""
        if not self._current_data:
            await self.refresh_dashboard()
        
        if format_type == "json":
            return json.dumps(self._current_data.to_dict(), indent=2, default=str)
        else:
            raise ValueError(f"Unsupported export format: {format_type}")
    
    async def get_dashboard_metrics(self) -> Dict[str, Any]:
        """Get metrics about the dashboard itself."""
        return {
            "last_refresh": self._current_data.last_updated if self._current_data else None,
            "refresh_interval": self._refresh_interval,
            "auto_refresh_active": self._auto_refresh_task is not None and not self._auto_refresh_task.done(),
            "components_count": len(self._current_data.components) if self._current_data else 0,
            "active_alerts_count": len(self._current_data.active_alerts) if self._current_data else 0,
            "overall_status": self._current_data.overall_status.value if self._current_data else "unknown",
            "update_callbacks_count": len(self._update_callbacks)
        }


# WebSocket handler for real-time updates (if using WebSockets)
class DashboardWebSocketHandler(LoggerMixin):
    """WebSocket handler for real-time dashboard updates."""
    
    def __init__(self, dashboard: SystemStatusDashboard):
        self.dashboard = dashboard
        self._connections: List[Any] = []  # WebSocket connections
        
        # Register for dashboard updates
        self.dashboard.add_update_callback(self._broadcast_update)
    
    async def add_connection(self, websocket) -> None:
        """Add a WebSocket connection."""
        self._connections.append(websocket)
        
        # Send current data immediately
        current_data = self.dashboard.get_current_data()
        if current_data:
            await self._send_to_connection(websocket, {
                "type": "dashboard_update",
                "data": current_data.to_dict()
            })
    
    async def remove_connection(self, websocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self._connections:
            self._connections.remove(websocket)
    
    async def _broadcast_update(self, dashboard_data: DashboardData) -> None:
        """Broadcast dashboard update to all connections."""
        if not self._connections:
            return
        
        message = {
            "type": "dashboard_update",
            "data": dashboard_data.to_dict()
        }
        
        # Send to all connections
        disconnected = []
        for connection in self._connections:
            try:
                await self._send_to_connection(connection, message)
            except Exception as e:
                self.logger.warning(f"Failed to send to WebSocket connection: {e}")
                disconnected.append(connection)
        
        # Remove disconnected connections
        for connection in disconnected:
            self._connections.remove(connection)
    
    async def _send_to_connection(self, connection, message: Dict[str, Any]) -> None:
        """Send message to a specific connection."""
        # This would depend on your WebSocket library
        # For example, with websockets library:
        # await connection.send(json.dumps(message))
        pass


# Dashboard API endpoints (for integration with web framework)
class DashboardAPI(LoggerMixin):
    """API endpoints for dashboard data."""
    
    def __init__(self, dashboard: SystemStatusDashboard):
        self.dashboard = dashboard
    
    async def get_status(self) -> Dict[str, Any]:
        """Get overall system status."""
        current_data = self.dashboard.get_current_data()
        if not current_data:
            current_data = await self.dashboard.refresh_dashboard()
        
        return {
            "status": current_data.overall_status.value,
            "last_updated": current_data.last_updated,
            "components_count": len(current_data.components),
            "active_alerts_count": len(current_data.active_alerts)
        }
    
    async def get_full_dashboard(self) -> Dict[str, Any]:
        """Get complete dashboard data."""
        current_data = self.dashboard.get_current_data()
        if not current_data:
            current_data = await self.dashboard.refresh_dashboard()
        
        return current_data.to_dict()
    
    async def get_components(self) -> List[Dict[str, Any]]:
        """Get system components status."""
        current_data = self.dashboard.get_current_data()
        if not current_data:
            current_data = await self.dashboard.refresh_dashboard()
        
        return [comp.to_dict() for comp in current_data.components]
    
    async def get_alerts(self) -> List[Dict[str, Any]]:
        """Get active alerts."""
        current_data = self.dashboard.get_current_data()
        if not current_data:
            current_data = await self.dashboard.refresh_dashboard()
        
        return current_data.active_alerts
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get metrics summary."""
        current_data = self.dashboard.get_current_data()
        if not current_data:
            current_data = await self.dashboard.refresh_dashboard()
        
        return current_data.metrics_summary
    
    async def get_performance(self) -> Dict[str, Any]:
        """Get performance summary."""
        current_data = self.dashboard.get_current_data()
        if not current_data:
            current_data = await self.dashboard.refresh_dashboard()
        
        return current_data.performance_summary
    
    async def refresh(self) -> Dict[str, Any]:
        """Force refresh dashboard data."""
        current_data = await self.dashboard.refresh_dashboard()
        return current_data.to_dict()