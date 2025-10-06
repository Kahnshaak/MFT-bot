"""
Alerting system for critical failures and performance degradation.
"""

import asyncio
import time
from typing import Dict, List, Optional, Callable, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

import discord
from discord.ext import tasks

from utils.logging_config import get_logger, LoggerMixin
from core.health_monitor import HealthCheck, HealthStatus
from core.metrics_collector import MetricsCollector


class AlertSeverity(Enum):
    """Alert severity levels."""
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(Enum):
    """Types of alerts."""
    
    HEALTH_CHECK_FAILED = "health_check_failed"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    ERROR_RATE_HIGH = "error_rate_high"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    SYSTEM_FAILURE = "system_failure"
    SECURITY_INCIDENT = "security_incident"
    CUSTOM = "custom"


@dataclass
class Alert:
    """Represents an alert."""
    
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    timestamp: float = field(default_factory=time.time)
    source: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: Optional[float] = None
    resolution_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "timestamp": self.timestamp,
            "source": self.source,
            "details": self.details,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at,
            "resolution_message": self.resolution_message
        }


class AlertChannel(ABC):
    """Abstract base class for alert channels."""
    
    @abstractmethod
    async def send_alert(self, alert: Alert) -> bool:
        """Send an alert through this channel."""
        pass
    
    @abstractmethod
    async def send_resolution(self, alert: Alert) -> bool:
        """Send alert resolution through this channel."""
        pass


class DiscordAlertChannel(AlertChannel, LoggerMixin):
    """Discord channel for sending alerts."""
    
    def __init__(self, bot: discord.Client, channel_id: int, mention_roles: Optional[List[int]] = None):
        self.bot = bot
        self.channel_id = channel_id
        self.mention_roles = mention_roles or []
    
    async def send_alert(self, alert: Alert) -> bool:
        """Send alert to Discord channel."""
        try:
            channel = self.bot.get_channel(self.channel_id)
            if not channel:
                self.logger.error(f"Alert channel {self.channel_id} not found")
                return False
            
            # Create embed
            embed = discord.Embed(
                title=f"🚨 {alert.title}",
                description=alert.message,
                color=self._get_color_for_severity(alert.severity),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="Severity",
                value=alert.severity.value.upper(),
                inline=True
            )
            
            embed.add_field(
                name="Type",
                value=alert.alert_type.value.replace("_", " ").title(),
                inline=True
            )
            
            if alert.source:
                embed.add_field(
                    name="Source",
                    value=alert.source,
                    inline=True
                )
            
            # Add details if present
            if alert.details:
                details_text = "\n".join([
                    f"**{k}:** {v}" for k, v in alert.details.items()
                    if len(str(v)) < 100  # Avoid too long details
                ])
                if details_text:
                    embed.add_field(
                        name="Details",
                        value=details_text[:1024],  # Discord field limit
                        inline=False
                    )
            
            # Prepare mentions
            mentions = []
            for role_id in self.mention_roles:
                if alert.severity in [AlertSeverity.HIGH, AlertSeverity.CRITICAL]:
                    mentions.append(f"<@&{role_id}>")
            
            mention_text = " ".join(mentions) if mentions else ""
            
            await channel.send(content=mention_text, embed=embed)
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send Discord alert: {e}")
            return False
    
    async def send_resolution(self, alert: Alert) -> bool:
        """Send alert resolution to Discord channel."""
        try:
            channel = self.bot.get_channel(self.channel_id)
            if not channel:
                return False
            
            embed = discord.Embed(
                title=f"✅ Alert Resolved: {alert.title}",
                description=alert.resolution_message or "Alert has been resolved",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="Original Severity",
                value=alert.severity.value.upper(),
                inline=True
            )
            
            if alert.resolved_at:
                duration = alert.resolved_at - alert.timestamp
                embed.add_field(
                    name="Duration",
                    value=f"{duration:.1f} seconds",
                    inline=True
                )
            
            await channel.send(embed=embed)
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send Discord resolution: {e}")
            return False
    
    def _get_color_for_severity(self, severity: AlertSeverity) -> discord.Color:
        """Get Discord color for alert severity."""
        color_map = {
            AlertSeverity.LOW: discord.Color.blue(),
            AlertSeverity.MEDIUM: discord.Color.yellow(),
            AlertSeverity.HIGH: discord.Color.orange(),
            AlertSeverity.CRITICAL: discord.Color.red()
        }
        return color_map.get(severity, discord.Color.grey())


class LogAlertChannel(AlertChannel, LoggerMixin):
    """Log-based alert channel."""
    
    async def send_alert(self, alert: Alert) -> bool:
        """Log the alert."""
        try:
            log_method = {
                AlertSeverity.LOW: self.logger.info,
                AlertSeverity.MEDIUM: self.logger.warning,
                AlertSeverity.HIGH: self.logger.error,
                AlertSeverity.CRITICAL: self.logger.critical
            }.get(alert.severity, self.logger.info)
            
            log_method(
                f"ALERT: {alert.title}",
                message=alert.message,
                severity=alert.severity.value,
                alert_type=alert.alert_type.value,
                source=alert.source,
                details=alert.details
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to log alert: {e}")
            return False
    
    async def send_resolution(self, alert: Alert) -> bool:
        """Log the alert resolution."""
        try:
            self.logger.info(
                f"ALERT RESOLVED: {alert.title}",
                resolution_message=alert.resolution_message,
                duration=alert.resolved_at - alert.timestamp if alert.resolved_at else None
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to log alert resolution: {e}")
            return False


class AlertingSystem(LoggerMixin):
    """
    Comprehensive alerting system for critical failures and performance issues.
    """
    
    def __init__(self, database_manager=None):
        self.database = database_manager
        self._channels: List[AlertChannel] = []
        self._active_alerts: Dict[str, Alert] = {}
        self._alert_rules: List[Callable] = []
        self._suppression_rules: Dict[str, float] = {}  # alert_key -> last_sent_time
        self._monitoring_active = False
        
        # Default suppression times (seconds)
        self._default_suppression = {
            AlertSeverity.LOW: 300,      # 5 minutes
            AlertSeverity.MEDIUM: 180,   # 3 minutes
            AlertSeverity.HIGH: 60,      # 1 minute
            AlertSeverity.CRITICAL: 30   # 30 seconds
        }
    
    def add_channel(self, channel: AlertChannel) -> None:
        """Add an alert channel."""
        self._channels.append(channel)
        self.logger.info(f"Added alert channel: {type(channel).__name__}")
    
    def add_rule(self, rule_function: Callable) -> None:
        """
        Add an alert rule function.
        
        Rule function should take metrics/health data and return Alert or None.
        """
        self._alert_rules.append(rule_function)
        self.logger.info(f"Added alert rule: {rule_function.__name__}")
    
    async def send_alert(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        message: str,
        source: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        suppress_duplicates: bool = True
    ) -> Alert:
        """
        Send an alert through all configured channels.
        
        Args:
            alert_type: Type of alert
            severity: Alert severity
            title: Alert title
            message: Alert message
            source: Source of the alert
            details: Additional details
            suppress_duplicates: Whether to suppress duplicate alerts
            
        Returns:
            The created Alert object
        """
        alert = Alert(
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            source=source,
            details=details or {}
        )
        
        # Check suppression
        if suppress_duplicates:
            alert_key = f"{alert_type.value}:{title}"
            last_sent = self._suppression_rules.get(alert_key, 0)
            suppression_time = self._default_suppression.get(severity, 60)
            
            if time.time() - last_sent < suppression_time:
                self.logger.debug(f"Alert suppressed: {title}")
                return alert
            
            self._suppression_rules[alert_key] = time.time()
        
        # Store active alert
        alert_id = f"{alert.alert_type.value}_{alert.timestamp}"
        self._active_alerts[alert_id] = alert
        
        # Send through all channels
        success_count = 0
        for channel in self._channels:
            try:
                if await channel.send_alert(alert):
                    success_count += 1
            except Exception as e:
                self.logger.error(f"Failed to send alert through {type(channel).__name__}: {e}")
        
        # Store in database if available
        if self.database:
            try:
                await self.database.insert_document("alerts", alert.to_dict())
            except Exception as e:
                self.logger.error(f"Failed to store alert in database: {e}")
        
        self.logger.info(
            f"Alert sent through {success_count}/{len(self._channels)} channels",
            title=title,
            severity=severity.value,
            alert_type=alert_type.value
        )
        
        return alert
    
    async def resolve_alert(
        self,
        alert_id: str,
        resolution_message: Optional[str] = None
    ) -> bool:
        """
        Resolve an active alert.
        
        Args:
            alert_id: ID of the alert to resolve
            resolution_message: Optional resolution message
            
        Returns:
            True if alert was resolved successfully
        """
        if alert_id not in self._active_alerts:
            self.logger.warning(f"Alert {alert_id} not found in active alerts")
            return False
        
        alert = self._active_alerts[alert_id]
        alert.resolved = True
        alert.resolved_at = time.time()
        alert.resolution_message = resolution_message
        
        # Send resolution through channels
        success_count = 0
        for channel in self._channels:
            try:
                if await channel.send_resolution(alert):
                    success_count += 1
            except Exception as e:
                self.logger.error(f"Failed to send resolution through {type(channel).__name__}: {e}")
        
        # Update in database
        if self.database:
            try:
                await self.database.update_document(
                    "alerts",
                    {"timestamp": alert.timestamp},
                    {"$set": alert.to_dict()}
                )
            except Exception as e:
                self.logger.error(f"Failed to update alert in database: {e}")
        
        # Remove from active alerts
        del self._active_alerts[alert_id]
        
        self.logger.info(f"Alert resolved: {alert.title}")
        return True
    
    async def check_health_alerts(self, health_results: Dict[str, HealthCheck]) -> None:
        """Check health results and generate alerts."""
        for check_name, health_check in health_results.items():
            if health_check.status == HealthStatus.UNHEALTHY:
                await self.send_alert(
                    alert_type=AlertType.HEALTH_CHECK_FAILED,
                    severity=AlertSeverity.HIGH,
                    title=f"Health Check Failed: {check_name}",
                    message=health_check.message,
                    source=check_name,
                    details={
                        "check_name": check_name,
                        "duration_ms": health_check.duration_ms,
                        "details": health_check.details or {}
                    }
                )
            elif health_check.status == HealthStatus.DEGRADED:
                await self.send_alert(
                    alert_type=AlertType.PERFORMANCE_DEGRADATION,
                    severity=AlertSeverity.MEDIUM,
                    title=f"Performance Degraded: {check_name}",
                    message=health_check.message,
                    source=check_name,
                    details={
                        "check_name": check_name,
                        "duration_ms": health_check.duration_ms,
                        "details": health_check.details or {}
                    }
                )
    
    async def check_metrics_alerts(self, metrics: MetricsCollector) -> None:
        """Check metrics and generate alerts."""
        try:
            # Check error rates
            command_stats = metrics.get_command_stats()
            for command_name, stats in command_stats.items():
                error_rate = 1 - stats.get("success_rate", 1.0)
                
                if error_rate > 0.5:  # 50% error rate
                    await self.send_alert(
                        alert_type=AlertType.ERROR_RATE_HIGH,
                        severity=AlertSeverity.HIGH,
                        title=f"High Error Rate: {command_name}",
                        message=f"Command {command_name} has {error_rate:.1%} error rate",
                        source="metrics_collector",
                        details={
                            "command": command_name,
                            "error_rate": error_rate,
                            "total_executions": stats.get("total_executions", 0),
                            "error_count": stats.get("error_count", 0)
                        }
                    )
                
                # Check response times
                avg_duration = stats.get("avg_duration", 0)
                if avg_duration > 5.0:  # 5 seconds
                    await self.send_alert(
                        alert_type=AlertType.PERFORMANCE_DEGRADATION,
                        severity=AlertSeverity.MEDIUM,
                        title=f"Slow Response Time: {command_name}",
                        message=f"Command {command_name} average response time is {avg_duration:.2f}s",
                        source="metrics_collector",
                        details={
                            "command": command_name,
                            "avg_duration": avg_duration,
                            "max_duration": stats.get("max_duration", 0)
                        }
                    )
            
        except Exception as e:
            self.logger.error(f"Error checking metrics alerts: {e}")
    
    def get_active_alerts(self) -> List[Alert]:
        """Get list of active alerts."""
        return list(self._active_alerts.values())
    
    async def get_alert_history(
        self,
        limit: int = 100,
        severity: Optional[AlertSeverity] = None,
        alert_type: Optional[AlertType] = None
    ) -> List[Dict[str, Any]]:
        """Get alert history from database."""
        if not self.database:
            return []
        
        try:
            query = {}
            if severity:
                query["severity"] = severity.value
            if alert_type:
                query["alert_type"] = alert_type.value
            
            results = await self.database.find_documents(
                "alerts",
                query,
                sort=[("timestamp", -1)],
                limit=limit
            )
            
            return results
            
        except Exception as e:
            self.logger.error(f"Failed to get alert history: {e}")
            return []
    
    async def cleanup_old_alerts(self, days_to_keep: int = 30) -> int:
        """Clean up old alerts from database."""
        if not self.database:
            return 0
        
        try:
            cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
            
            result = await self.database.delete_documents(
                "alerts",
                {"timestamp": {"$lt": cutoff_time}}
            )
            
            deleted_count = result.get("deleted_count", 0)
            self.logger.info(f"Cleaned up {deleted_count} old alerts")
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup old alerts: {e}")
            return 0


# Pre-defined alert rules
async def database_connection_rule(health_results: Dict[str, HealthCheck]) -> Optional[Alert]:
    """Alert rule for database connection issues."""
    db_check = health_results.get("database")
    if db_check and db_check.status == HealthStatus.UNHEALTHY:
        return Alert(
            alert_type=AlertType.SYSTEM_FAILURE,
            severity=AlertSeverity.CRITICAL,
            title="Database Connection Lost",
            message="Database connection is unavailable",
            source="database_health_check",
            details={"check_details": db_check.details or {}}
        )
    return None


async def discord_api_rule(health_results: Dict[str, HealthCheck]) -> Optional[Alert]:
    """Alert rule for Discord API issues."""
    api_check = health_results.get("discord_api")
    if api_check and api_check.status == HealthStatus.UNHEALTHY:
        return Alert(
            alert_type=AlertType.SYSTEM_FAILURE,
            severity=AlertSeverity.HIGH,
            title="Discord API Connection Lost",
            message="Discord API is unavailable",
            source="discord_api_health_check",
            details={"check_details": api_check.details or {}}
        )
    return None


async def memory_usage_rule(health_results: Dict[str, HealthCheck]) -> Optional[Alert]:
    """Alert rule for high memory usage."""
    memory_check = health_results.get("memory_usage")
    if memory_check and memory_check.details:
        memory_mb = memory_check.details.get("memory_mb", 0)
        if memory_mb > 2000:  # 2GB
            return Alert(
                alert_type=AlertType.RESOURCE_EXHAUSTION,
                severity=AlertSeverity.CRITICAL,
                title="High Memory Usage",
                message=f"Memory usage is {memory_mb:.1f}MB",
                source="memory_health_check",
                details={"memory_mb": memory_mb}
            )
    return None