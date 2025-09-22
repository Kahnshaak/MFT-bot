"""
Metrics collection system for monitoring command usage and performance.
"""

import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

from utils.logging_config import get_logger, LoggerMixin


class MetricType(Enum):
    """Types of metrics collected."""
    
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class Metric:
    """Represents a single metric data point."""
    
    name: str
    value: float
    metric_type: MetricType
    timestamp: float = field(default_factory=time.time)
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class TimerContext:
    """Context manager for timing operations."""
    
    collector: 'MetricsCollector'
    metric_name: str
    labels: Dict[str, str]
    start_time: Optional[float] = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = time.time() - self.start_time
            self.collector.record_timer(self.metric_name, duration, self.labels)


class MetricsCollector(LoggerMixin):
    """
    Collects and stores metrics for monitoring bot performance and usage.
    """
    
    def __init__(self, max_history_size: int = 10000):
        self.max_history_size = max_history_size
        self._metrics_history: deque = deque(maxlen=max_history_size)
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._timers: Dict[str, List[float]] = defaultdict(list)
        
        # Performance tracking
        self._command_counts: Dict[str, int] = defaultdict(int)
        self._command_durations: Dict[str, List[float]] = defaultdict(list)
        self._error_counts: Dict[str, int] = defaultdict(int)
        
        # System metrics
        self._start_time = time.time()
    
    def record_counter(
        self, 
        name: str, 
        value: float = 1.0, 
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Record a counter metric (cumulative value).
        
        Args:
            name: Metric name
            value: Value to add to counter
            labels: Optional labels for the metric
        """
        labels = labels or {}
        metric_key = self._make_metric_key(name, labels)
        
        self._counters[metric_key] += value
        
        metric = Metric(
            name=name,
            value=value,
            metric_type=MetricType.COUNTER,
            labels=labels
        )
        self._add_to_history(metric)
        
        self.logger.debug(
            "Recorded counter metric",
            name=name,
            value=value,
            labels=labels
        )
    
    def record_gauge(
        self, 
        name: str, 
        value: float, 
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Record a gauge metric (point-in-time value).
        
        Args:
            name: Metric name
            value: Current value
            labels: Optional labels for the metric
        """
        labels = labels or {}
        metric_key = self._make_metric_key(name, labels)
        
        self._gauges[metric_key] = value
        
        metric = Metric(
            name=name,
            value=value,
            metric_type=MetricType.GAUGE,
            labels=labels
        )
        self._add_to_history(metric)
        
        self.logger.debug(
            "Recorded gauge metric",
            name=name,
            value=value,
            labels=labels
        )
    
    def record_histogram(
        self, 
        name: str, 
        value: float, 
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Record a histogram metric (distribution of values).
        
        Args:
            name: Metric name
            value: Value to add to histogram
            labels: Optional labels for the metric
        """
        labels = labels or {}
        metric_key = self._make_metric_key(name, labels)
        
        self._histograms[metric_key].append(value)
        
        # Keep histogram size manageable
        if len(self._histograms[metric_key]) > 1000:
            self._histograms[metric_key] = self._histograms[metric_key][-1000:]
        
        metric = Metric(
            name=name,
            value=value,
            metric_type=MetricType.HISTOGRAM,
            labels=labels
        )
        self._add_to_history(metric)
    
    def record_timer(
        self, 
        name: str, 
        duration: float, 
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Record a timer metric (duration of operations).
        
        Args:
            name: Metric name
            duration: Duration in seconds
            labels: Optional labels for the metric
        """
        labels = labels or {}
        metric_key = self._make_metric_key(name, labels)
        
        self._timers[metric_key].append(duration)
        
        # Keep timer history manageable
        if len(self._timers[metric_key]) > 1000:
            self._timers[metric_key] = self._timers[metric_key][-1000:]
        
        metric = Metric(
            name=name,
            value=duration,
            metric_type=MetricType.TIMER,
            labels=labels
        )
        self._add_to_history(metric)
        
        self.logger.debug(
            "Recorded timer metric",
            name=name,
            duration=duration,
            labels=labels
        )
    
    def timer(self, name: str, labels: Optional[Dict[str, str]] = None) -> TimerContext:
        """
        Create a timer context manager.
        
        Args:
            name: Metric name
            labels: Optional labels for the metric
            
        Returns:
            Timer context manager
        """
        return TimerContext(
            collector=self,
            metric_name=name,
            labels=labels or {}
        )
    
    async def record_command(
        self, 
        command_name: str, 
        duration: float,
        success: bool = True,
        guild_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> None:
        """
        Record command execution metrics.
        
        Args:
            command_name: Name of the command
            duration: Execution duration in seconds
            success: Whether the command succeeded
            guild_id: Guild where command was executed
            user_id: User who executed the command
        """
        labels = {
            "command": command_name,
            "success": str(success).lower()
        }
        
        if guild_id:
            labels["guild_id"] = guild_id
        
        # Record counter
        self.record_counter("commands_total", 1.0, labels)
        
        # Record duration
        self.record_timer("command_duration_seconds", duration, labels)
        
        # Update internal tracking
        self._command_counts[command_name] += 1
        self._command_durations[command_name].append(duration)
        
        if not success:
            self._error_counts[command_name] += 1
            self.record_counter("command_errors_total", 1.0, {"command": command_name})
    
    async def record_error(
        self, 
        error_type: str, 
        context: Optional[str] = None,
        guild_id: Optional[str] = None
    ) -> None:
        """
        Record error metrics.
        
        Args:
            error_type: Type of error
            context: Context where error occurred
            guild_id: Guild where error occurred
        """
        labels = {"error_type": error_type}
        
        if context:
            labels["context"] = context
        
        if guild_id:
            labels["guild_id"] = guild_id
        
        self.record_counter("errors_total", 1.0, labels)
    
    def get_counter_value(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current counter value."""
        metric_key = self._make_metric_key(name, labels or {})
        return self._counters.get(metric_key, 0.0)
    
    def get_gauge_value(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[float]:
        """Get current gauge value."""
        metric_key = self._make_metric_key(name, labels or {})
        return self._gauges.get(metric_key)
    
    def get_histogram_stats(
        self, 
        name: str, 
        labels: Optional[Dict[str, str]] = None
    ) -> Dict[str, float]:
        """
        Get histogram statistics.
        
        Returns:
            Dictionary with min, max, mean, median, p95, p99 values
        """
        metric_key = self._make_metric_key(name, labels or {})
        values = self._histograms.get(metric_key, [])
        
        if not values:
            return {}
        
        sorted_values = sorted(values)
        count = len(sorted_values)
        
        return {
            "count": count,
            "min": min(sorted_values),
            "max": max(sorted_values),
            "mean": sum(sorted_values) / count,
            "median": sorted_values[count // 2],
            "p95": sorted_values[int(count * 0.95)] if count > 0 else 0,
            "p99": sorted_values[int(count * 0.99)] if count > 0 else 0
        }
    
    def get_timer_stats(
        self, 
        name: str, 
        labels: Optional[Dict[str, str]] = None
    ) -> Dict[str, float]:
        """Get timer statistics (same as histogram)."""
        return self.get_histogram_stats(name, labels)
    
    def get_command_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get command execution statistics.
        
        Returns:
            Dictionary with stats for each command
        """
        stats = {}
        
        for command_name in self._command_counts:
            durations = self._command_durations[command_name]
            error_count = self._error_counts[command_name]
            total_count = self._command_counts[command_name]
            
            if durations:
                avg_duration = sum(durations) / len(durations)
                max_duration = max(durations)
                min_duration = min(durations)
            else:
                avg_duration = max_duration = min_duration = 0
            
            stats[command_name] = {
                "total_executions": total_count,
                "error_count": error_count,
                "success_rate": (total_count - error_count) / total_count if total_count > 0 else 0,
                "avg_duration": avg_duration,
                "max_duration": max_duration,
                "min_duration": min_duration
            }
        
        return stats
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Get system-level statistics."""
        uptime = time.time() - self._start_time
        
        return {
            "uptime_seconds": uptime,
            "total_commands": sum(self._command_counts.values()),
            "total_errors": sum(self._error_counts.values()),
            "metrics_collected": len(self._metrics_history),
            "unique_counters": len(self._counters),
            "unique_gauges": len(self._gauges),
            "unique_histograms": len(self._histograms),
            "unique_timers": len(self._timers)
        }
    
    def _make_metric_key(self, name: str, labels: Dict[str, str]) -> str:
        """Create a unique key for a metric with labels."""
        if not labels:
            return name
        
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def _add_to_history(self, metric: Metric) -> None:
        """Add metric to history."""
        self._metrics_history.append(metric)
    
    def export_metrics(self, format_type: str = "dict") -> Any:
        """
        Export metrics in various formats.
        
        Args:
            format_type: Export format ("dict", "prometheus", etc.)
            
        Returns:
            Metrics in requested format
        """
        if format_type == "dict":
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {k: list(v) for k, v in self._histograms.items()},
                "timers": {k: list(v) for k, v in self._timers.items()},
                "command_stats": self.get_command_stats(),
                "system_stats": self.get_system_stats()
            }
        else:
            raise ValueError(f"Unsupported export format: {format_type}")