"""
Performance monitoring system with response time tracking and optimization.
"""

import time
import asyncio
import statistics
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

from utils.logging_config import get_logger, LoggerMixin
from core.metrics_collector import MetricsCollector


class PerformanceThreshold(Enum):
    """Performance threshold levels."""
    
    EXCELLENT = "excellent"    # < 100ms
    GOOD = "good"             # 100ms - 500ms
    ACCEPTABLE = "acceptable"  # 500ms - 1000ms
    SLOW = "slow"             # 1000ms - 3000ms
    CRITICAL = "critical"     # > 3000ms


@dataclass
class PerformanceMetric:
    """Represents a performance metric."""
    
    operation: str
    duration_ms: float
    timestamp: float = field(default_factory=time.time)
    context: Dict[str, Any] = field(default_factory=dict)
    threshold: Optional[PerformanceThreshold] = None
    
    def __post_init__(self):
        """Calculate threshold after initialization."""
        if self.threshold is None:
            self.threshold = self._calculate_threshold()
    
    def _calculate_threshold(self) -> PerformanceThreshold:
        """Calculate performance threshold based on duration."""
        if self.duration_ms < 100:
            return PerformanceThreshold.EXCELLENT
        elif self.duration_ms < 500:
            return PerformanceThreshold.GOOD
        elif self.duration_ms < 1000:
            return PerformanceThreshold.ACCEPTABLE
        elif self.duration_ms < 3000:
            return PerformanceThreshold.SLOW
        else:
            return PerformanceThreshold.CRITICAL


@dataclass
class PerformanceStats:
    """Performance statistics for an operation."""
    
    operation: str
    total_calls: int
    avg_duration_ms: float
    min_duration_ms: float
    max_duration_ms: float
    p50_duration_ms: float
    p95_duration_ms: float
    p99_duration_ms: float
    threshold_distribution: Dict[str, int]
    recent_trend: str  # "improving", "stable", "degrading"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "operation": self.operation,
            "total_calls": self.total_calls,
            "avg_duration_ms": self.avg_duration_ms,
            "min_duration_ms": self.min_duration_ms,
            "max_duration_ms": self.max_duration_ms,
            "p50_duration_ms": self.p50_duration_ms,
            "p95_duration_ms": self.p95_duration_ms,
            "p99_duration_ms": self.p99_duration_ms,
            "threshold_distribution": self.threshold_distribution,
            "recent_trend": self.recent_trend
        }


class PerformanceOptimizer(LoggerMixin):
    """Analyzes performance data and suggests optimizations."""
    
    def __init__(self):
        self._optimization_rules: List[Callable] = []
        self._register_default_rules()
    
    def _register_default_rules(self) -> None:
        """Register default optimization rules."""
        self._optimization_rules.extend([
            self._database_query_optimization,
            self._discord_api_optimization,
            self._command_processing_optimization,
            self._memory_usage_optimization
        ])
    
    def add_optimization_rule(self, rule: Callable) -> None:
        """Add a custom optimization rule."""
        self._optimization_rules.append(rule)
    
    async def analyze_performance(self, stats: Dict[str, PerformanceStats]) -> List[Dict[str, Any]]:
        """
        Analyze performance statistics and generate optimization suggestions.
        
        Args:
            stats: Dictionary of operation name to performance stats
            
        Returns:
            List of optimization suggestions
        """
        suggestions = []
        
        for rule in self._optimization_rules:
            try:
                rule_suggestions = await rule(stats)
                if rule_suggestions:
                    suggestions.extend(rule_suggestions)
            except Exception as e:
                self.logger.error(f"Error in optimization rule {rule.__name__}: {e}")
        
        return suggestions
    
    async def _database_query_optimization(self, stats: Dict[str, PerformanceStats]) -> List[Dict[str, Any]]:
        """Optimization suggestions for database queries."""
        suggestions = []
        
        for operation, stat in stats.items():
            if "database" in operation.lower() or "query" in operation.lower():
                if stat.avg_duration_ms > 1000:  # 1 second
                    suggestions.append({
                        "type": "database_optimization",
                        "operation": operation,
                        "severity": "high" if stat.avg_duration_ms > 3000 else "medium",
                        "suggestion": "Consider adding database indexes or optimizing query structure",
                        "details": {
                            "avg_duration_ms": stat.avg_duration_ms,
                            "p95_duration_ms": stat.p95_duration_ms,
                            "total_calls": stat.total_calls
                        }
                    })
                
                # Check for high variance
                if stat.max_duration_ms > stat.avg_duration_ms * 5:
                    suggestions.append({
                        "type": "database_consistency",
                        "operation": operation,
                        "severity": "medium",
                        "suggestion": "High variance in query times - investigate query plan consistency",
                        "details": {
                            "avg_duration_ms": stat.avg_duration_ms,
                            "max_duration_ms": stat.max_duration_ms,
                            "variance_ratio": stat.max_duration_ms / stat.avg_duration_ms
                        }
                    })
        
        return suggestions
    
    async def _discord_api_optimization(self, stats: Dict[str, PerformanceStats]) -> List[Dict[str, Any]]:
        """Optimization suggestions for Discord API calls."""
        suggestions = []
        
        for operation, stat in stats.items():
            if "discord" in operation.lower() or "api" in operation.lower():
                if stat.avg_duration_ms > 2000:  # 2 seconds
                    suggestions.append({
                        "type": "discord_api_optimization",
                        "operation": operation,
                        "severity": "medium",
                        "suggestion": "Consider implementing request batching or caching for Discord API calls",
                        "details": {
                            "avg_duration_ms": stat.avg_duration_ms,
                            "total_calls": stat.total_calls
                        }
                    })
                
                # Check for rate limiting indicators
                critical_count = stat.threshold_distribution.get("critical", 0)
                if critical_count > stat.total_calls * 0.1:  # More than 10% critical
                    suggestions.append({
                        "type": "rate_limiting",
                        "operation": operation,
                        "severity": "high",
                        "suggestion": "High number of slow API calls - check for rate limiting",
                        "details": {
                            "critical_percentage": (critical_count / stat.total_calls) * 100,
                            "critical_count": critical_count,
                            "total_calls": stat.total_calls
                        }
                    })
        
        return suggestions
    
    async def _command_processing_optimization(self, stats: Dict[str, PerformanceStats]) -> List[Dict[str, Any]]:
        """Optimization suggestions for command processing."""
        suggestions = []
        
        for operation, stat in stats.items():
            if "command" in operation.lower():
                if stat.avg_duration_ms > 500:  # 500ms
                    suggestions.append({
                        "type": "command_optimization",
                        "operation": operation,
                        "severity": "medium",
                        "suggestion": "Command processing is slow - consider async operations or caching",
                        "details": {
                            "avg_duration_ms": stat.avg_duration_ms,
                            "p95_duration_ms": stat.p95_duration_ms
                        }
                    })
                
                # Check for degrading trend
                if stat.recent_trend == "degrading":
                    suggestions.append({
                        "type": "performance_degradation",
                        "operation": operation,
                        "severity": "medium",
                        "suggestion": "Performance is degrading over time - investigate resource leaks",
                        "details": {
                            "trend": stat.recent_trend,
                            "avg_duration_ms": stat.avg_duration_ms
                        }
                    })
        
        return suggestions
    
    async def _memory_usage_optimization(self, stats: Dict[str, PerformanceStats]) -> List[Dict[str, Any]]:
        """Optimization suggestions for memory usage."""
        suggestions = []
        
        for operation, stat in stats.items():
            if "memory" in operation.lower():
                # This would need memory-specific metrics
                # For now, just check if operations are consistently slow
                if (stat.threshold_distribution.get("slow", 0) + 
                    stat.threshold_distribution.get("critical", 0)) > stat.total_calls * 0.3:
                    
                    suggestions.append({
                        "type": "memory_optimization",
                        "operation": operation,
                        "severity": "medium",
                        "suggestion": "High percentage of slow operations - check for memory pressure",
                        "details": {
                            "slow_percentage": ((stat.threshold_distribution.get("slow", 0) + 
                                               stat.threshold_distribution.get("critical", 0)) / 
                                              stat.total_calls) * 100
                        }
                    })
        
        return suggestions


class PerformanceMonitor(LoggerMixin):
    """
    Comprehensive performance monitoring system with response time tracking.
    """
    
    def __init__(self, metrics_collector: MetricsCollector, max_history_size: int = 10000):
        self.metrics = metrics_collector
        self.max_history_size = max_history_size
        
        # Performance data storage
        self._performance_history: deque = deque(maxlen=max_history_size)
        self._operation_metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        
        # Performance tracking
        self._active_operations: Dict[str, float] = {}  # operation_id -> start_time
        
        # Optimization
        self.optimizer = PerformanceOptimizer()
        
        # Thresholds for alerts
        self._alert_thresholds = {
            "avg_duration_ms": 1000,      # 1 second average
            "p95_duration_ms": 3000,      # 3 seconds p95
            "critical_percentage": 10     # 10% critical operations
        }
    
    def start_operation(self, operation: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Start tracking a performance operation.
        
        Args:
            operation: Name of the operation
            context: Additional context information
            
        Returns:
            Operation ID for tracking
        """
        operation_id = f"{operation}_{time.time()}_{id(context or {})}"
        self._active_operations[operation_id] = time.time()
        
        return operation_id
    
    def end_operation(
        self, 
        operation_id: str, 
        operation: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[PerformanceMetric]:
        """
        End tracking a performance operation.
        
        Args:
            operation_id: Operation ID from start_operation
            operation: Name of the operation
            context: Additional context information
            
        Returns:
            PerformanceMetric if operation was tracked
        """
        if operation_id not in self._active_operations:
            self.logger.warning(f"Operation {operation_id} not found in active operations")
            return None
        
        start_time = self._active_operations.pop(operation_id)
        duration_ms = (time.time() - start_time) * 1000
        
        metric = PerformanceMetric(
            operation=operation,
            duration_ms=duration_ms,
            context=context or {}
        )
        
        # Store metric
        self._performance_history.append(metric)
        self._operation_metrics[operation].append(metric)
        
        # Record in metrics collector
        self.metrics.record_timer(
            f"performance_{operation}",
            duration_ms / 1000,  # Convert to seconds
            {"operation": operation}
        )
        
        self.logger.debug(
            f"Performance metric recorded",
            operation=operation,
            duration_ms=duration_ms,
            threshold=metric.threshold.value
        )
        
        return metric
    
    async def record_operation(
        self,
        operation: str,
        duration_ms: float,
        context: Optional[Dict[str, Any]] = None
    ) -> PerformanceMetric:
        """
        Record a completed operation directly.
        
        Args:
            operation: Name of the operation
            duration_ms: Duration in milliseconds
            context: Additional context information
            
        Returns:
            PerformanceMetric
        """
        metric = PerformanceMetric(
            operation=operation,
            duration_ms=duration_ms,
            context=context or {}
        )
        
        # Store metric
        self._performance_history.append(metric)
        self._operation_metrics[operation].append(metric)
        
        # Record in metrics collector
        self.metrics.record_timer(
            f"performance_{operation}",
            duration_ms / 1000,
            {"operation": operation}
        )
        
        return metric
    
    def get_operation_stats(self, operation: str) -> Optional[PerformanceStats]:
        """
        Get performance statistics for a specific operation.
        
        Args:
            operation: Name of the operation
            
        Returns:
            PerformanceStats or None if no data available
        """
        if operation not in self._operation_metrics:
            return None
        
        metrics = list(self._operation_metrics[operation])
        if not metrics:
            return None
        
        durations = [m.duration_ms for m in metrics]
        
        # Calculate percentiles
        sorted_durations = sorted(durations)
        count = len(sorted_durations)
        
        p50 = sorted_durations[int(count * 0.5)] if count > 0 else 0
        p95 = sorted_durations[int(count * 0.95)] if count > 0 else 0
        p99 = sorted_durations[int(count * 0.99)] if count > 0 else 0
        
        # Calculate threshold distribution
        threshold_counts = defaultdict(int)
        for metric in metrics:
            threshold_counts[metric.threshold.value] += 1
        
        # Calculate trend (simple comparison of recent vs older metrics)
        recent_trend = self._calculate_trend(metrics)
        
        return PerformanceStats(
            operation=operation,
            total_calls=len(durations),
            avg_duration_ms=statistics.mean(durations),
            min_duration_ms=min(durations),
            max_duration_ms=max(durations),
            p50_duration_ms=p50,
            p95_duration_ms=p95,
            p99_duration_ms=p99,
            threshold_distribution=dict(threshold_counts),
            recent_trend=recent_trend
        )
    
    def get_all_operation_stats(self) -> Dict[str, PerformanceStats]:
        """Get performance statistics for all operations."""
        stats = {}
        
        for operation in self._operation_metrics.keys():
            operation_stats = self.get_operation_stats(operation)
            if operation_stats:
                stats[operation] = operation_stats
        
        return stats
    
    def _calculate_trend(self, metrics: List[PerformanceMetric]) -> str:
        """Calculate performance trend for metrics."""
        if len(metrics) < 10:
            return "stable"
        
        # Compare recent 25% vs older 25%
        recent_count = max(1, len(metrics) // 4)
        recent_metrics = metrics[-recent_count:]
        older_metrics = metrics[:recent_count]
        
        recent_avg = statistics.mean([m.duration_ms for m in recent_metrics])
        older_avg = statistics.mean([m.duration_ms for m in older_metrics])
        
        # Calculate percentage change
        if older_avg == 0:
            return "stable"
        
        change_percent = ((recent_avg - older_avg) / older_avg) * 100
        
        if change_percent > 20:
            return "degrading"
        elif change_percent < -20:
            return "improving"
        else:
            return "stable"
    
    async def get_performance_alerts(self) -> List[Dict[str, Any]]:
        """Get performance-related alerts."""
        alerts = []
        stats = self.get_all_operation_stats()
        
        for operation, stat in stats.items():
            # Check average duration
            if stat.avg_duration_ms > self._alert_thresholds["avg_duration_ms"]:
                alerts.append({
                    "type": "slow_average_performance",
                    "operation": operation,
                    "severity": "medium",
                    "message": f"Average response time is {stat.avg_duration_ms:.1f}ms",
                    "details": stat.to_dict()
                })
            
            # Check p95 duration
            if stat.p95_duration_ms > self._alert_thresholds["p95_duration_ms"]:
                alerts.append({
                    "type": "slow_p95_performance",
                    "operation": operation,
                    "severity": "high",
                    "message": f"95th percentile response time is {stat.p95_duration_ms:.1f}ms",
                    "details": stat.to_dict()
                })
            
            # Check critical percentage
            critical_count = stat.threshold_distribution.get("critical", 0)
            critical_percentage = (critical_count / stat.total_calls) * 100 if stat.total_calls > 0 else 0
            
            if critical_percentage > self._alert_thresholds["critical_percentage"]:
                alerts.append({
                    "type": "high_critical_operations",
                    "operation": operation,
                    "severity": "high",
                    "message": f"{critical_percentage:.1f}% of operations are critically slow",
                    "details": stat.to_dict()
                })
            
            # Check degrading trend
            if stat.recent_trend == "degrading":
                alerts.append({
                    "type": "performance_degradation",
                    "operation": operation,
                    "severity": "medium",
                    "message": "Performance is degrading over time",
                    "details": stat.to_dict()
                })
        
        return alerts
    
    async def get_optimization_suggestions(self) -> List[Dict[str, Any]]:
        """Get performance optimization suggestions."""
        stats = self.get_all_operation_stats()
        return await self.optimizer.analyze_performance(stats)
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get overall performance summary."""
        stats = self.get_all_operation_stats()
        
        if not stats:
            return {
                "total_operations": 0,
                "avg_response_time_ms": 0,
                "operations_by_threshold": {},
                "slowest_operations": [],
                "trending_operations": {}
            }
        
        # Calculate overall metrics
        all_durations = []
        threshold_counts = defaultdict(int)
        trend_counts = defaultdict(int)
        
        for stat in stats.values():
            all_durations.extend([stat.avg_duration_ms] * stat.total_calls)
            
            for threshold, count in stat.threshold_distribution.items():
                threshold_counts[threshold] += count
            
            trend_counts[stat.recent_trend] += 1
        
        # Find slowest operations
        slowest_operations = sorted(
            [(name, stat.avg_duration_ms) for name, stat in stats.items()],
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        return {
            "total_operations": len(stats),
            "avg_response_time_ms": statistics.mean(all_durations) if all_durations else 0,
            "operations_by_threshold": dict(threshold_counts),
            "slowest_operations": [
                {"operation": name, "avg_duration_ms": duration}
                for name, duration in slowest_operations
            ],
            "trending_operations": dict(trend_counts)
        }


# Context manager for easy performance tracking
class PerformanceTracker:
    """Context manager for tracking operation performance."""
    
    def __init__(self, monitor: PerformanceMonitor, operation: str, context: Optional[Dict[str, Any]] = None):
        self.monitor = monitor
        self.operation = operation
        self.context = context
        self.operation_id = None
    
    def __enter__(self):
        self.operation_id = self.monitor.start_operation(self.operation, self.context)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.operation_id:
            self.monitor.end_operation(self.operation_id, self.operation, self.context)


# Decorator for automatic performance tracking
def track_performance(operation_name: str = None):
    """Decorator to automatically track function performance."""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            # Try to get performance monitor from first argument (usually self)
            monitor = None
            if args and hasattr(args[0], 'performance_monitor'):
                monitor = args[0].performance_monitor
            elif args and hasattr(args[0], 'bot') and hasattr(args[0].bot, 'performance_monitor'):
                monitor = args[0].bot.performance_monitor
            
            if not monitor:
                # No monitor available, just execute function
                return await func(*args, **kwargs)
            
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            
            with PerformanceTracker(monitor, op_name):
                return await func(*args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            # Try to get performance monitor from first argument (usually self)
            monitor = None
            if args and hasattr(args[0], 'performance_monitor'):
                monitor = args[0].performance_monitor
            elif args and hasattr(args[0], 'bot') and hasattr(args[0].bot, 'performance_monitor'):
                monitor = args[0].bot.performance_monitor
            
            if not monitor:
                # No monitor available, just execute function
                return func(*args, **kwargs)
            
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            
            with PerformanceTracker(monitor, op_name):
                return func(*args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator