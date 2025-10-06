"""
Log aggregation and analysis system for troubleshooting.
"""

import re
import time
import asyncio
from typing import Dict, List, Optional, Any, Pattern, Callable, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, Counter
from enum import Enum
import json
from pathlib import Path

from utils.logging_config import get_logger, LoggerMixin


class LogLevel(Enum):
    """Log levels for filtering."""
    
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogPattern(Enum):
    """Common log patterns for analysis."""
    
    ERROR_PATTERN = "error_pattern"
    WARNING_PATTERN = "warning_pattern"
    PERFORMANCE_PATTERN = "performance_pattern"
    SECURITY_PATTERN = "security_pattern"
    DATABASE_PATTERN = "database_pattern"
    DISCORD_API_PATTERN = "discord_api_pattern"
    COMMAND_PATTERN = "command_pattern"


@dataclass
class LogEntry:
    """Represents a parsed log entry."""
    
    timestamp: float
    level: LogLevel
    logger_name: str
    message: str
    raw_line: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    function_name: Optional[str] = None
    extra_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "level": self.level.value,
            "logger_name": self.logger_name,
            "message": self.message,
            "raw_line": self.raw_line,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "function_name": self.function_name,
            "extra_data": self.extra_data
        }


@dataclass
class LogAnalysisResult:
    """Results of log analysis."""
    
    total_entries: int
    entries_by_level: Dict[str, int]
    top_loggers: List[Tuple[str, int]]
    top_messages: List[Tuple[str, int]]
    error_patterns: List[Dict[str, Any]]
    time_range: Tuple[float, float]
    analysis_duration_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_entries": self.total_entries,
            "entries_by_level": self.entries_by_level,
            "top_loggers": self.top_loggers,
            "top_messages": self.top_messages,
            "error_patterns": self.error_patterns,
            "time_range": {
                "start": self.time_range[0],
                "end": self.time_range[1]
            },
            "analysis_duration_ms": self.analysis_duration_ms
        }


class LogParser(LoggerMixin):
    """Parses log files into structured entries."""
    
    def __init__(self):
        # Common log format patterns
        self._patterns = {
            # Standard Python logging format
            "standard": re.compile(
                r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - "
                r"(?P<logger_name>[\w\.]+) - "
                r"(?P<level>\w+) - "
                r"(?:(?P<function_name>\w+):(?P<line_number>\d+) - )?"
                r"(?P<message>.*)"
            ),
            
            # Structured logging format (JSON-like)
            "structured": re.compile(
                r"(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z?) "
                r"\[(?P<level>\w+)\] "
                r"(?P<logger_name>[\w\.]+): "
                r"(?P<message>.*)"
            ),
            
            # Simple format
            "simple": re.compile(
                r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
                r"(?P<level>\w+) "
                r"(?P<message>.*)"
            )
        }
    
    def parse_log_line(self, line: str) -> Optional[LogEntry]:
        """Parse a single log line."""
        line = line.strip()
        if not line:
            return None
        
        # Try each pattern
        for pattern_name, pattern in self._patterns.items():
            match = pattern.match(line)
            if match:
                try:
                    groups = match.groupdict()
                    
                    # Parse timestamp
                    timestamp_str = groups["timestamp"]
                    timestamp = self._parse_timestamp(timestamp_str)
                    
                    # Parse level
                    level_str = groups["level"].upper()
                    try:
                        level = LogLevel(level_str)
                    except ValueError:
                        level = LogLevel.INFO  # Default fallback
                    
                    # Extract other fields
                    logger_name = groups.get("logger_name", "unknown")
                    message = groups.get("message", "")
                    function_name = groups.get("function_name")
                    line_number = groups.get("line_number")
                    
                    if line_number:
                        try:
                            line_number = int(line_number)
                        except ValueError:
                            line_number = None
                    
                    # Try to parse structured data from message
                    extra_data = self._extract_structured_data(message)
                    
                    return LogEntry(
                        timestamp=timestamp,
                        level=level,
                        logger_name=logger_name,
                        message=message,
                        raw_line=line,
                        function_name=function_name,
                        line_number=line_number,
                        extra_data=extra_data
                    )
                    
                except Exception as e:
                    self.logger.debug(f"Error parsing log line with pattern {pattern_name}: {e}")
                    continue
        
        # If no pattern matched, create a basic entry
        return LogEntry(
            timestamp=time.time(),
            level=LogLevel.INFO,
            logger_name="unknown",
            message=line,
            raw_line=line
        )
    
    def _parse_timestamp(self, timestamp_str: str) -> float:
        """Parse timestamp string to Unix timestamp."""
        import datetime
        
        # Common timestamp formats
        formats = [
            "%Y-%m-%d %H:%M:%S,%f",  # Python logging default
            "%Y-%m-%d %H:%M:%S.%f",  # Alternative microseconds
            "%Y-%m-%dT%H:%M:%S.%fZ", # ISO format with Z
            "%Y-%m-%dT%H:%M:%S.%f",  # ISO format
            "%Y-%m-%d %H:%M:%S",     # Simple format
        ]
        
        for fmt in formats:
            try:
                dt = datetime.datetime.strptime(timestamp_str, fmt)
                return dt.timestamp()
            except ValueError:
                continue
        
        # Fallback to current time
        return time.time()
    
    def _extract_structured_data(self, message: str) -> Dict[str, Any]:
        """Extract structured data from log message."""
        extra_data = {}
        
        # Try to find JSON-like data
        json_pattern = re.compile(r'\{[^{}]*\}')
        json_matches = json_pattern.findall(message)
        
        for match in json_matches:
            try:
                data = json.loads(match)
                if isinstance(data, dict):
                    extra_data.update(data)
            except json.JSONDecodeError:
                pass
        
        # Extract key=value pairs
        kv_pattern = re.compile(r'(\w+)=([^\s,]+)')
        kv_matches = kv_pattern.findall(message)
        
        for key, value in kv_matches:
            # Try to convert to appropriate type
            try:
                if value.isdigit():
                    extra_data[key] = int(value)
                elif value.replace('.', '').isdigit():
                    extra_data[key] = float(value)
                elif value.lower() in ('true', 'false'):
                    extra_data[key] = value.lower() == 'true'
                else:
                    extra_data[key] = value
            except:
                extra_data[key] = value
        
        return extra_data


class LogAnalyzer(LoggerMixin):
    """Analyzes log entries for patterns and insights."""
    
    def __init__(self):
        # Pattern definitions for common issues
        self._error_patterns = {
            "database_connection": [
                re.compile(r"database.*connection.*failed", re.IGNORECASE),
                re.compile(r"mongodb.*connection.*error", re.IGNORECASE),
                re.compile(r"connection.*timeout", re.IGNORECASE),
            ],
            "discord_api_error": [
                re.compile(r"discord.*api.*error", re.IGNORECASE),
                re.compile(r"http.*error.*4\d{2}", re.IGNORECASE),
                re.compile(r"rate.*limit", re.IGNORECASE),
            ],
            "command_error": [
                re.compile(r"command.*error", re.IGNORECASE),
                re.compile(r"slash.*command.*failed", re.IGNORECASE),
                re.compile(r"application.*command.*error", re.IGNORECASE),
            ],
            "permission_error": [
                re.compile(r"permission.*denied", re.IGNORECASE),
                re.compile(r"missing.*permission", re.IGNORECASE),
                re.compile(r"unauthorized", re.IGNORECASE),
            ],
            "validation_error": [
                re.compile(r"validation.*error", re.IGNORECASE),
                re.compile(r"invalid.*input", re.IGNORECASE),
                re.compile(r"malformed.*data", re.IGNORECASE),
            ]
        }
        
        # Performance indicators
        self._performance_patterns = {
            "slow_operation": [
                re.compile(r"slow.*operation", re.IGNORECASE),
                re.compile(r"timeout", re.IGNORECASE),
                re.compile(r"duration.*\d+.*ms", re.IGNORECASE),
            ],
            "high_memory": [
                re.compile(r"memory.*usage.*high", re.IGNORECASE),
                re.compile(r"out.*of.*memory", re.IGNORECASE),
            ],
            "high_cpu": [
                re.compile(r"cpu.*usage.*high", re.IGNORECASE),
                re.compile(r"high.*load", re.IGNORECASE),
            ]
        }
    
    def analyze_entries(self, entries: List[LogEntry]) -> LogAnalysisResult:
        """Analyze a list of log entries."""
        start_time = time.time()
        
        if not entries:
            return LogAnalysisResult(
                total_entries=0,
                entries_by_level={},
                top_loggers=[],
                top_messages=[],
                error_patterns=[],
                time_range=(0, 0),
                analysis_duration_ms=0
            )
        
        # Basic statistics
        total_entries = len(entries)
        entries_by_level = Counter(entry.level.value for entry in entries)
        logger_counts = Counter(entry.logger_name for entry in entries)
        message_counts = Counter(entry.message for entry in entries)
        
        # Time range
        timestamps = [entry.timestamp for entry in entries]
        time_range = (min(timestamps), max(timestamps))
        
        # Pattern analysis
        error_patterns = self._analyze_error_patterns(entries)
        
        # Performance analysis
        performance_issues = self._analyze_performance_patterns(entries)
        error_patterns.extend(performance_issues)
        
        analysis_duration = (time.time() - start_time) * 1000
        
        return LogAnalysisResult(
            total_entries=total_entries,
            entries_by_level=dict(entries_by_level),
            top_loggers=logger_counts.most_common(10),
            top_messages=message_counts.most_common(10),
            error_patterns=error_patterns,
            time_range=time_range,
            analysis_duration_ms=analysis_duration
        )
    
    def _analyze_error_patterns(self, entries: List[LogEntry]) -> List[Dict[str, Any]]:
        """Analyze entries for error patterns."""
        patterns_found = []
        
        # Filter to error and warning entries
        error_entries = [
            entry for entry in entries 
            if entry.level in [LogLevel.ERROR, LogLevel.CRITICAL, LogLevel.WARNING]
        ]
        
        for pattern_name, patterns in self._error_patterns.items():
            matching_entries = []
            
            for entry in error_entries:
                for pattern in patterns:
                    if pattern.search(entry.message):
                        matching_entries.append(entry)
                        break
            
            if matching_entries:
                # Group by similar messages
                message_groups = defaultdict(list)
                for entry in matching_entries:
                    # Normalize message for grouping
                    normalized = re.sub(r'\d+', 'N', entry.message)
                    normalized = re.sub(r'[a-f0-9]{8,}', 'ID', normalized)
                    message_groups[normalized].append(entry)
                
                patterns_found.append({
                    "pattern_name": pattern_name,
                    "total_occurrences": len(matching_entries),
                    "unique_messages": len(message_groups),
                    "time_range": {
                        "start": min(entry.timestamp for entry in matching_entries),
                        "end": max(entry.timestamp for entry in matching_entries)
                    },
                    "sample_messages": [
                        {
                            "message": list(group)[0],
                            "count": len(entries),
                            "latest_timestamp": max(entry.timestamp for entry in entries)
                        }
                        for group, entries in list(message_groups.items())[:5]
                    ]
                })
        
        return patterns_found
    
    def _analyze_performance_patterns(self, entries: List[LogEntry]) -> List[Dict[str, Any]]:
        """Analyze entries for performance patterns."""
        patterns_found = []
        
        for pattern_name, patterns in self._performance_patterns.items():
            matching_entries = []
            
            for entry in entries:
                for pattern in patterns:
                    if pattern.search(entry.message):
                        matching_entries.append(entry)
                        break
            
            if matching_entries:
                patterns_found.append({
                    "pattern_name": f"performance_{pattern_name}",
                    "total_occurrences": len(matching_entries),
                    "time_range": {
                        "start": min(entry.timestamp for entry in matching_entries),
                        "end": max(entry.timestamp for entry in matching_entries)
                    },
                    "sample_messages": [
                        {
                            "message": entry.message,
                            "timestamp": entry.timestamp,
                            "logger": entry.logger_name
                        }
                        for entry in matching_entries[:5]
                    ]
                })
        
        return patterns_found
    
    def find_correlations(self, entries: List[LogEntry], time_window_seconds: int = 60) -> List[Dict[str, Any]]:
        """Find correlations between different types of log entries."""
        correlations = []
        
        # Group entries by time windows
        time_windows = defaultdict(list)
        
        for entry in entries:
            window_key = int(entry.timestamp // time_window_seconds)
            time_windows[window_key].append(entry)
        
        # Look for patterns within time windows
        for window_key, window_entries in time_windows.items():
            if len(window_entries) < 2:
                continue
            
            # Check for error followed by recovery
            errors = [e for e in window_entries if e.level in [LogLevel.ERROR, LogLevel.CRITICAL]]
            infos = [e for e in window_entries if e.level == LogLevel.INFO]
            
            if errors and infos:
                # Look for recovery messages
                recovery_keywords = ["recovered", "reconnected", "restored", "fixed", "resolved"]
                recovery_messages = [
                    info for info in infos
                    if any(keyword in info.message.lower() for keyword in recovery_keywords)
                ]
                
                if recovery_messages:
                    correlations.append({
                        "type": "error_recovery",
                        "time_window": window_key * time_window_seconds,
                        "error_count": len(errors),
                        "recovery_count": len(recovery_messages),
                        "sample_error": errors[0].message,
                        "sample_recovery": recovery_messages[0].message
                    })
        
        return correlations


class LogAggregator(LoggerMixin):
    """
    Main log aggregation system for collecting and analyzing logs.
    """
    
    def __init__(self, log_directory: str = "logs", database_manager=None):
        self.log_directory = Path(log_directory)
        self.database = database_manager
        
        self.parser = LogParser()
        self.analyzer = LogAnalyzer()
        
        # Cache for parsed entries
        self._entry_cache: Dict[str, List[LogEntry]] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._cache_ttl = 300  # 5 minutes
    
    async def collect_logs(
        self,
        hours_back: int = 24,
        log_levels: Optional[List[LogLevel]] = None,
        logger_names: Optional[List[str]] = None
    ) -> List[LogEntry]:
        """
        Collect log entries from log files.
        
        Args:
            hours_back: How many hours back to collect logs
            log_levels: Filter by log levels
            logger_names: Filter by logger names
            
        Returns:
            List of parsed log entries
        """
        cutoff_time = time.time() - (hours_back * 3600)
        all_entries = []
        
        # Find log files
        log_files = []
        if self.log_directory.exists():
            log_files.extend(self.log_directory.glob("*.log"))
            log_files.extend(self.log_directory.glob("*.log.*"))  # Rotated logs
        
        for log_file in log_files:
            try:
                entries = await self._parse_log_file(log_file, cutoff_time)
                all_entries.extend(entries)
            except Exception as e:
                self.logger.error(f"Error parsing log file {log_file}: {e}")
        
        # Apply filters
        if log_levels:
            all_entries = [e for e in all_entries if e.level in log_levels]
        
        if logger_names:
            all_entries = [e for e in all_entries if e.logger_name in logger_names]
        
        # Sort by timestamp
        all_entries.sort(key=lambda x: x.timestamp)
        
        self.logger.info(f"Collected {len(all_entries)} log entries from {len(log_files)} files")
        return all_entries
    
    async def _parse_log_file(self, log_file: Path, cutoff_time: float) -> List[LogEntry]:
        """Parse a single log file."""
        cache_key = str(log_file)
        
        # Check cache
        if (cache_key in self._entry_cache and 
            cache_key in self._cache_timestamps and
            time.time() - self._cache_timestamps[cache_key] < self._cache_ttl):
            return self._entry_cache[cache_key]
        
        entries = []
        
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        entry = self.parser.parse_log_line(line)
                        if entry and entry.timestamp >= cutoff_time:
                            entry.file_path = str(log_file)
                            if not entry.line_number:
                                entry.line_number = line_num
                            entries.append(entry)
                    except Exception as e:
                        self.logger.debug(f"Error parsing line {line_num} in {log_file}: {e}")
        
        except Exception as e:
            self.logger.error(f"Error reading log file {log_file}: {e}")
            return []
        
        # Cache results
        self._entry_cache[cache_key] = entries
        self._cache_timestamps[cache_key] = time.time()
        
        return entries
    
    async def analyze_logs(
        self,
        hours_back: int = 24,
        log_levels: Optional[List[LogLevel]] = None,
        logger_names: Optional[List[str]] = None
    ) -> LogAnalysisResult:
        """
        Analyze logs and return insights.
        
        Args:
            hours_back: How many hours back to analyze
            log_levels: Filter by log levels
            logger_names: Filter by logger names
            
        Returns:
            Analysis results
        """
        entries = await self.collect_logs(hours_back, log_levels, logger_names)
        return self.analyzer.analyze_entries(entries)
    
    async def search_logs(
        self,
        query: str,
        hours_back: int = 24,
        case_sensitive: bool = False,
        regex: bool = False
    ) -> List[LogEntry]:
        """
        Search logs for specific patterns.
        
        Args:
            query: Search query
            hours_back: How many hours back to search
            case_sensitive: Whether search is case sensitive
            regex: Whether query is a regex pattern
            
        Returns:
            Matching log entries
        """
        entries = await self.collect_logs(hours_back)
        
        if regex:
            try:
                pattern = re.compile(query, 0 if case_sensitive else re.IGNORECASE)
                return [entry for entry in entries if pattern.search(entry.message)]
            except re.error as e:
                self.logger.error(f"Invalid regex pattern: {e}")
                return []
        else:
            if not case_sensitive:
                query = query.lower()
                return [
                    entry for entry in entries 
                    if query in entry.message.lower()
                ]
            else:
                return [
                    entry for entry in entries 
                    if query in entry.message
                ]
    
    async def get_error_summary(self, hours_back: int = 24) -> Dict[str, Any]:
        """Get summary of errors in the specified time period."""
        entries = await self.collect_logs(
            hours_back, 
            log_levels=[LogLevel.ERROR, LogLevel.CRITICAL]
        )
        
        if not entries:
            return {
                "total_errors": 0,
                "error_rate_per_hour": 0,
                "top_error_loggers": [],
                "recent_errors": []
            }
        
        # Calculate error rate
        time_span_hours = hours_back
        error_rate = len(entries) / time_span_hours
        
        # Top error loggers
        logger_counts = Counter(entry.logger_name for entry in entries)
        
        # Recent errors (last 10)
        recent_errors = sorted(entries, key=lambda x: x.timestamp, reverse=True)[:10]
        
        return {
            "total_errors": len(entries),
            "error_rate_per_hour": error_rate,
            "top_error_loggers": logger_counts.most_common(5),
            "recent_errors": [
                {
                    "timestamp": entry.timestamp,
                    "logger": entry.logger_name,
                    "message": entry.message[:200] + "..." if len(entry.message) > 200 else entry.message
                }
                for entry in recent_errors
            ]
        }
    
    async def export_logs(
        self,
        output_file: str,
        hours_back: int = 24,
        format_type: str = "json"
    ) -> bool:
        """
        Export logs to file.
        
        Args:
            output_file: Output file path
            hours_back: How many hours back to export
            format_type: Export format ("json", "csv", "txt")
            
        Returns:
            True if export successful
        """
        try:
            entries = await self.collect_logs(hours_back)
            
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            if format_type == "json":
                with open(output_path, 'w') as f:
                    json.dump([entry.to_dict() for entry in entries], f, indent=2, default=str)
            
            elif format_type == "csv":
                import csv
                with open(output_path, 'w', newline='') as f:
                    if entries:
                        writer = csv.DictWriter(f, fieldnames=entries[0].to_dict().keys())
                        writer.writeheader()
                        for entry in entries:
                            writer.writerow(entry.to_dict())
            
            elif format_type == "txt":
                with open(output_path, 'w') as f:
                    for entry in entries:
                        f.write(f"{entry.raw_line}\n")
            
            else:
                raise ValueError(f"Unsupported format: {format_type}")
            
            self.logger.info(f"Exported {len(entries)} log entries to {output_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error exporting logs: {e}")
            return False
    
    async def cleanup_cache(self) -> None:
        """Clean up expired cache entries."""
        current_time = time.time()
        expired_keys = [
            key for key, timestamp in self._cache_timestamps.items()
            if current_time - timestamp > self._cache_ttl
        ]
        
        for key in expired_keys:
            self._entry_cache.pop(key, None)
            self._cache_timestamps.pop(key, None)
        
        if expired_keys:
            self.logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")