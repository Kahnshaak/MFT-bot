"""
Health monitoring system with database and Discord API checks.
"""

import asyncio
import time
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum

import discord
from discord.ext import tasks

from database.manager import DatabaseManager
from utils.logging_config import get_logger, LoggerMixin
from utils.exceptions import GameNightBotException


class HealthStatus(Enum):
    """Health check status values."""
    
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """Represents a health check result."""
    
    name: str
    status: HealthStatus
    message: str
    duration_ms: float
    timestamp: float
    details: Optional[Dict[str, Any]] = None


class HealthMonitor(LoggerMixin):
    """
    Monitors system health including database connectivity and Discord API status.
    """
    
    def __init__(self, database: DatabaseManager, bot: discord.Client):
        self.database = database
        self.bot = bot
        self._health_checks: Dict[str, HealthCheck] = {}
        self._check_functions: Dict[str, Callable] = {}
        self._alert_callbacks: List[Callable] = []
        self._monitoring_active = False
        
        # Register default health checks
        self._register_default_checks()
    
    def _register_default_checks(self) -> None:
        """Register default health check functions."""
        self.register_check("database", self._check_database_health)
        self.register_check("discord_api", self._check_discord_api_health)
        self.register_check("memory_usage", self._check_memory_usage)
        self.register_check("bot_connectivity", self._check_bot_connectivity)
    
    def register_check(self, name: str, check_function: Callable) -> None:
        """
        Register a health check function.
        
        Args:
            name: Unique name for the health check
            check_function: Async function that returns HealthCheck
        """
        self._check_functions[name] = check_function
        self.logger.debug("Registered health check", name=name)
    
    def register_alert_callback(self, callback: Callable[[HealthCheck], None]) -> None:
        """
        Register a callback to be called when health issues are detected.
        
        Args:
            callback: Function to call with HealthCheck when issues occur
        """
        self._alert_callbacks.append(callback)
    
    async def start_monitoring(self, interval_seconds: int = 60) -> None:
        """
        Start periodic health monitoring.
        
        Args:
            interval_seconds: How often to run health checks
        """
        if self._monitoring_active:
            self.logger.warning("Health monitoring already active")
            return
        
        self._monitoring_active = True
        self.health_check_loop.change_interval(seconds=interval_seconds)
        self.health_check_loop.start()
        
        self.logger.info(
            "Started health monitoring",
            interval_seconds=interval_seconds
        )
    
    async def stop_monitoring(self) -> None:
        """Stop health monitoring."""
        if not self._monitoring_active:
            return
        
        self._monitoring_active = False
        self.health_check_loop.stop()
        
        self.logger.info("Stopped health monitoring")
    
    @tasks.loop()
    async def health_check_loop(self) -> None:
        """Periodic health check loop."""
        try:
            await self.run_all_checks()
        except Exception as e:
            self.logger.error(
                "Error in health check loop",
                error=str(e),
                exc_info=True
            )
    
    async def run_all_checks(self) -> Dict[str, HealthCheck]:
        """
        Run all registered health checks.
        
        Returns:
            Dictionary of health check results
        """
        results = {}
        
        for name, check_function in self._check_functions.items():
            try:
                start_time = time.time()
                result = await check_function()
                duration_ms = (time.time() - start_time) * 1000
                
                if isinstance(result, HealthCheck):
                    result.duration_ms = duration_ms
                    results[name] = result
                else:
                    # Handle functions that don't return HealthCheck objects
                    results[name] = HealthCheck(
                        name=name,
                        status=HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY,
                        message="Check completed",
                        duration_ms=duration_ms,
                        timestamp=time.time()
                    )
                
                self._health_checks[name] = results[name]
                
                # Trigger alerts for unhealthy checks
                if results[name].status == HealthStatus.UNHEALTHY:
                    await self._trigger_alerts(results[name])
                
            except Exception as e:
                error_check = HealthCheck(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Health check failed: {str(e)}",
                    duration_ms=0,
                    timestamp=time.time(),
                    details={"error_type": type(e).__name__}
                )
                results[name] = error_check
                self._health_checks[name] = error_check
                
                self.logger.error(
                    "Health check failed",
                    check_name=name,
                    error=str(e)
                )
                
                await self._trigger_alerts(error_check)
        
        return results
    
    async def run_single_check(self, name: str) -> Optional[HealthCheck]:
        """
        Run a single health check by name.
        
        Args:
            name: Name of the health check to run
            
        Returns:
            HealthCheck result or None if check doesn't exist
        """
        if name not in self._check_functions:
            return None
        
        check_function = self._check_functions[name]
        
        try:
            start_time = time.time()
            result = await check_function()
            duration_ms = (time.time() - start_time) * 1000
            
            if isinstance(result, HealthCheck):
                result.duration_ms = duration_ms
                self._health_checks[name] = result
                return result
            else:
                health_check = HealthCheck(
                    name=name,
                    status=HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY,
                    message="Check completed",
                    duration_ms=duration_ms,
                    timestamp=time.time()
                )
                self._health_checks[name] = health_check
                return health_check
                
        except Exception as e:
            error_check = HealthCheck(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                duration_ms=0,
                timestamp=time.time(),
                details={"error_type": type(e).__name__}
            )
            self._health_checks[name] = error_check
            return error_check
    
    def get_overall_health(self) -> HealthStatus:
        """
        Get overall system health status.
        
        Returns:
            Overall health status based on all checks
        """
        if not self._health_checks:
            return HealthStatus.UNKNOWN
        
        statuses = [check.status for check in self._health_checks.values()]
        
        if any(status == HealthStatus.UNHEALTHY for status in statuses):
            return HealthStatus.UNHEALTHY
        elif any(status == HealthStatus.DEGRADED for status in statuses):
            return HealthStatus.DEGRADED
        elif all(status == HealthStatus.HEALTHY for status in statuses):
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.UNKNOWN
    
    def get_health_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all health checks.
        
        Returns:
            Dictionary with health summary information
        """
        overall_status = self.get_overall_health()
        
        return {
            "overall_status": overall_status.value,
            "checks": {
                name: {
                    "status": check.status.value,
                    "message": check.message,
                    "duration_ms": check.duration_ms,
                    "timestamp": check.timestamp,
                    "details": check.details
                }
                for name, check in self._health_checks.items()
            },
            "last_check": max(
                (check.timestamp for check in self._health_checks.values()),
                default=0
            )
        }
    
    async def _trigger_alerts(self, health_check: HealthCheck) -> None:
        """Trigger alert callbacks for unhealthy checks."""
        for callback in self._alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(health_check)
                else:
                    callback(health_check)
            except Exception as e:
                self.logger.error(
                    "Alert callback failed",
                    callback=callback.__name__,
                    error=str(e)
                )
    
    # Default health check implementations
    
    async def _check_database_health(self) -> HealthCheck:
        """Check database connectivity and performance."""
        try:
            # Test basic connectivity
            await self.database.ping()
            
            # Test a simple query
            start_time = time.time()
            result = await self.database.test_connection()
            query_duration = (time.time() - start_time) * 1000
            
            if query_duration > 5000:  # 5 seconds
                return HealthCheck(
                    name="database",
                    status=HealthStatus.DEGRADED,
                    message=f"Database responding slowly ({query_duration:.1f}ms)",
                    duration_ms=0,
                    timestamp=time.time(),
                    details={"query_duration_ms": query_duration}
                )
            
            return HealthCheck(
                name="database",
                status=HealthStatus.HEALTHY,
                message=f"Database healthy (query: {query_duration:.1f}ms)",
                duration_ms=0,
                timestamp=time.time(),
                details={"query_duration_ms": query_duration}
            )
            
        except Exception as e:
            return HealthCheck(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database connection failed: {str(e)}",
                duration_ms=0,
                timestamp=time.time(),
                details={"error": str(e)}
            )
    
    async def _check_discord_api_health(self) -> HealthCheck:
        """Check Discord API connectivity."""
        try:
            # Test API connectivity by getting bot user info
            start_time = time.time()
            user = await self.bot.fetch_user(self.bot.user.id)
            api_duration = (time.time() - start_time) * 1000
            
            if api_duration > 3000:  # 3 seconds
                return HealthCheck(
                    name="discord_api",
                    status=HealthStatus.DEGRADED,
                    message=f"Discord API responding slowly ({api_duration:.1f}ms)",
                    duration_ms=0,
                    timestamp=time.time(),
                    details={"api_duration_ms": api_duration}
                )
            
            return HealthCheck(
                name="discord_api",
                status=HealthStatus.HEALTHY,
                message=f"Discord API healthy ({api_duration:.1f}ms)",
                duration_ms=0,
                timestamp=time.time(),
                details={"api_duration_ms": api_duration}
            )
            
        except Exception as e:
            return HealthCheck(
                name="discord_api",
                status=HealthStatus.UNHEALTHY,
                message=f"Discord API connection failed: {str(e)}",
                duration_ms=0,
                timestamp=time.time(),
                details={"error": str(e)}
            )
    
    async def _check_memory_usage(self) -> HealthCheck:
        """Check memory usage."""
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            # Check if memory usage is concerning
            if memory_mb > 1000:  # 1GB
                status = HealthStatus.DEGRADED
                message = f"High memory usage: {memory_mb:.1f}MB"
            elif memory_mb > 2000:  # 2GB
                status = HealthStatus.UNHEALTHY
                message = f"Very high memory usage: {memory_mb:.1f}MB"
            else:
                status = HealthStatus.HEALTHY
                message = f"Memory usage normal: {memory_mb:.1f}MB"
            
            return HealthCheck(
                name="memory_usage",
                status=status,
                message=message,
                duration_ms=0,
                timestamp=time.time(),
                details={"memory_mb": memory_mb}
            )
            
        except ImportError:
            return HealthCheck(
                name="memory_usage",
                status=HealthStatus.UNKNOWN,
                message="psutil not available for memory monitoring",
                duration_ms=0,
                timestamp=time.time()
            )
        except Exception as e:
            return HealthCheck(
                name="memory_usage",
                status=HealthStatus.UNHEALTHY,
                message=f"Memory check failed: {str(e)}",
                duration_ms=0,
                timestamp=time.time(),
                details={"error": str(e)}
            )
    
    async def _check_bot_connectivity(self) -> HealthCheck:
        """Check bot's connection to Discord."""
        try:
            if not self.bot.is_ready():
                return HealthCheck(
                    name="bot_connectivity",
                    status=HealthStatus.UNHEALTHY,
                    message="Bot is not ready",
                    duration_ms=0,
                    timestamp=time.time()
                )
            
            latency_ms = self.bot.latency * 1000
            
            if latency_ms > 1000:  # 1 second
                status = HealthStatus.DEGRADED
                message = f"High latency: {latency_ms:.1f}ms"
            else:
                status = HealthStatus.HEALTHY
                message = f"Bot connected (latency: {latency_ms:.1f}ms)"
            
            return HealthCheck(
                name="bot_connectivity",
                status=status,
                message=message,
                duration_ms=0,
                timestamp=time.time(),
                details={
                    "latency_ms": latency_ms,
                    "guild_count": len(self.bot.guilds)
                }
            )
            
        except Exception as e:
            return HealthCheck(
                name="bot_connectivity",
                status=HealthStatus.UNHEALTHY,
                message=f"Bot connectivity check failed: {str(e)}",
                duration_ms=0,
                timestamp=time.time(),
                details={"error": str(e)}
            )