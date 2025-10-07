"""
Performance monitoring integration for the Discord bot.
"""

import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from core.cache_manager import CacheManager, UserPreferencesCache, GameListCache, EventCache
from core.rate_limiter import RateLimiter, COMMON_RULES
from core.batch_processor import BatchProcessorManager
from core.performance_monitor import PerformanceMonitor
from core.metrics_collector import MetricsCollector
from utils.logging_config import get_logger, LoggerMixin


class PerformanceIntegration(LoggerMixin):
    """
    Integrates all performance optimization components for the bot.
    """
    
    def __init__(self, bot):
        self.bot = bot
        
        # Core performance components
        self.metrics_collector = MetricsCollector(max_history_size=50000)
        self.performance_monitor = PerformanceMonitor(self.metrics_collector)
        self.cache_manager = CacheManager(
            max_size=50000,
            default_ttl=1800,  # 30 minutes
            cleanup_interval=300  # 5 minutes
        )
        self.rate_limiter = RateLimiter(cleanup_interval=300)
        self.batch_manager = BatchProcessorManager()
        
        # Specialized caches
        self.user_cache = UserPreferencesCache(self.cache_manager)
        self.game_cache = GameListCache(self.cache_manager)
        self.event_cache = EventCache(self.cache_manager)
        
        # Performance tracking
        self._performance_alerts: Dict[str, datetime] = {}
        self._alert_cooldown = timedelta(minutes=15)  # Prevent spam
        
        # Background tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._optimization_task: Optional[asyncio.Task] = None
    
    async def initialize(self) -> None:
        """Initialize all performance components."""
        try:
            # Start core components
            await self.cache_manager.start()
            await self.rate_limiter.start()
            await self.batch_manager.start()
            
            # Add common rate limiting rules
            for rule in COMMON_RULES.values():
                self.rate_limiter.add_rule(rule)
            
            # Start background monitoring
            self._monitoring_task = asyncio.create_task(self._performance_monitoring_loop())
            self._optimization_task = asyncio.create_task(self._optimization_loop())
            
            # Integrate with bot components
            await self._integrate_with_bot()
            
            self.logger.info("Performance integration initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize performance integration: {e}", exc_info=True)
            raise
    
    async def shutdown(self) -> None:
        """Shutdown all performance components."""
        try:
            # Cancel background tasks
            if self._monitoring_task and not self._monitoring_task.done():
                self._monitoring_task.cancel()
                try:
                    await self._monitoring_task
                except asyncio.CancelledError:
                    pass
            
            if self._optimization_task and not self._optimization_task.done():
                self._optimization_task.cancel()
                try:
                    await self._optimization_task
                except asyncio.CancelledError:
                    pass
            
            # Stop components
            await self.batch_manager.stop()
            await self.rate_limiter.stop()
            await self.cache_manager.stop()
            
            self.logger.info("Performance integration shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during performance integration shutdown: {e}", exc_info=True)
    
    async def _integrate_with_bot(self) -> None:
        """Integrate performance components with bot systems."""
        # Add performance components to bot for easy access
        self.bot.metrics_collector = self.metrics_collector
        self.bot.performance_monitor = self.performance_monitor
        self.bot.cache_manager = self.cache_manager
        self.bot.rate_limiter = self.rate_limiter
        self.bot.batch_manager = self.batch_manager
        
        # Add specialized caches
        self.bot.user_cache = self.user_cache
        self.bot.game_cache = self.game_cache
        self.bot.event_cache = self.event_cache
        
        # Update database manager with cache
        if hasattr(self.bot, 'database') and self.bot.database:
            self.bot.database.cache_manager = self.cache_manager
            # Re-initialize optimizations if database is already connected
            if self.bot.database.is_connected:
                await self.bot.database._initialize_optimizations()
    
    async def _performance_monitoring_loop(self) -> None:
        """Background task for performance monitoring."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                # Check for performance alerts
                alerts = await self.performance_monitor.get_performance_alerts()
                
                for alert in alerts:
                    await self._handle_performance_alert(alert)
                
                # Log performance summary every 10 minutes
                if datetime.now().minute % 10 == 0:
                    await self._log_performance_summary()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in performance monitoring loop: {e}", exc_info=True)
    
    async def _optimization_loop(self) -> None:
        """Background task for automatic optimizations."""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                
                # Get optimization suggestions
                suggestions = await self.performance_monitor.get_optimization_suggestions()
                
                for suggestion in suggestions:
                    await self._apply_optimization_suggestion(suggestion)
                
                # Database optimizations every hour
                if datetime.now().minute == 0:
                    await self._run_database_optimizations()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in optimization loop: {e}", exc_info=True)
    
    async def _handle_performance_alert(self, alert: Dict[str, Any]) -> None:
        """Handle a performance alert."""
        alert_key = f"{alert['type']}:{alert['operation']}"
        current_time = datetime.now()
        
        # Check cooldown to prevent spam
        if alert_key in self._performance_alerts:
            if current_time - self._performance_alerts[alert_key] < self._alert_cooldown:
                return
        
        self._performance_alerts[alert_key] = current_time
        
        # Log the alert
        self.logger.warning(
            f"Performance alert: {alert['message']}",
            extra={
                'alert_type': alert['type'],
                'operation': alert['operation'],
                'severity': alert['severity'],
                'details': alert.get('details', {})
            }
        )
        
        # Take automatic action based on alert type
        if alert['type'] == 'slow_average_performance':
            await self._handle_slow_performance_alert(alert)
        elif alert['type'] == 'high_critical_operations':
            await self._handle_critical_operations_alert(alert)
        elif alert['type'] == 'performance_degradation':
            await self._handle_degradation_alert(alert)
    
    async def _handle_slow_performance_alert(self, alert: Dict[str, Any]) -> None:
        """Handle slow performance alert."""
        operation = alert['operation']
        
        # Clear related caches
        if 'database' in operation.lower():
            await self.cache_manager.invalidate_pattern("query:*")
            self.logger.info(f"Cleared database query cache due to slow performance in {operation}")
        
        # Increase cache TTL for frequently accessed data
        if 'user' in operation.lower():
            # This would require cache configuration updates
            pass
    
    async def _handle_critical_operations_alert(self, alert: Dict[str, Any]) -> None:
        """Handle critical operations alert."""
        operation = alert['operation']
        
        # Implement circuit breaker pattern for critical operations
        # This is a simplified implementation
        self.logger.warning(f"High number of critical operations detected for {operation}")
        
        # Could implement temporary rate limiting or circuit breaking here
    
    async def _handle_degradation_alert(self, alert: Dict[str, Any]) -> None:
        """Handle performance degradation alert."""
        operation = alert['operation']
        
        # Force garbage collection and cache cleanup
        import gc
        gc.collect()
        
        # Clear old cache entries
        await self.cache_manager._cleanup_expired()
        
        self.logger.info(f"Performed cleanup due to performance degradation in {operation}")
    
    async def _apply_optimization_suggestion(self, suggestion: Dict[str, Any]) -> None:
        """Apply an optimization suggestion automatically."""
        suggestion_type = suggestion['type']
        
        if suggestion_type == 'database_optimization':
            # Database optimizations are handled separately
            pass
        elif suggestion_type == 'memory_optimization':
            # Trigger cache cleanup
            await self.cache_manager._cleanup_expired()
        elif suggestion_type == 'rate_limiting':
            # Could adjust rate limits dynamically
            pass
    
    async def _run_database_optimizations(self) -> None:
        """Run database optimizations."""
        if hasattr(self.bot, 'database') and self.bot.database:
            try:
                # Run query optimization
                optimization_results = await self.bot.database.optimize_queries()
                
                if optimization_results.get('indexes_created'):
                    self.logger.info(
                        f"Database optimization completed: {optimization_results}"
                    )
                
            except Exception as e:
                self.logger.error(f"Database optimization failed: {e}")
    
    async def _log_performance_summary(self) -> None:
        """Log a performance summary."""
        try:
            # Get system stats
            system_stats = self.metrics_collector.get_system_stats()
            performance_summary = self.performance_monitor.get_performance_summary()
            cache_stats = self.cache_manager.get_stats()
            rate_limit_stats = await self.rate_limiter.get_global_stats()
            
            self.logger.info(
                "Performance Summary",
                extra={
                    'uptime_seconds': system_stats['uptime_seconds'],
                    'total_commands': system_stats['total_commands'],
                    'total_errors': system_stats['total_errors'],
                    'cache_hit_rate': cache_stats['hit_rate'],
                    'cache_size': cache_stats['size'],
                    'rate_limit_success_rate': rate_limit_stats['success_rate'],
                    'avg_response_time': performance_summary['avg_response_time_ms']
                }
            )
            
        except Exception as e:
            self.logger.error(f"Failed to log performance summary: {e}")
    
    async def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        stats = {
            'timestamp': datetime.now().isoformat(),
            'metrics': self.metrics_collector.export_metrics(),
            'performance': self.performance_monitor.get_performance_summary(),
            'cache': self.cache_manager.get_stats(),
            'rate_limiting': await self.rate_limiter.get_global_stats(),
            'batch_processing': self.batch_manager.get_all_stats()
        }
        
        # Add database stats if available
        if hasattr(self.bot, 'database') and self.bot.database:
            try:
                stats['database'] = await self.bot.database.get_performance_stats()
            except Exception as e:
                stats['database'] = {'error': str(e)}
        
        return stats
    
    async def run_performance_analysis(self) -> Dict[str, Any]:
        """Run a comprehensive performance analysis."""
        analysis = {
            'timestamp': datetime.now().isoformat(),
            'alerts': await self.performance_monitor.get_performance_alerts(),
            'optimization_suggestions': await self.performance_monitor.get_optimization_suggestions(),
            'slow_operations': [],
            'cache_efficiency': {},
            'rate_limit_violations': {},
            'recommendations': []
        }
        
        # Get performance stats
        performance_stats = self.performance_monitor.get_all_operation_stats()
        
        # Identify slow operations
        for operation, stats in performance_stats.items():
            if stats.avg_duration_ms > 1000:  # Slower than 1 second
                analysis['slow_operations'].append({
                    'operation': operation,
                    'avg_duration_ms': stats.avg_duration_ms,
                    'total_calls': stats.total_calls
                })
        
        # Cache efficiency analysis
        cache_stats = self.cache_manager.get_stats()
        analysis['cache_efficiency'] = {
            'hit_rate': cache_stats['hit_rate'],
            'size_utilization': (cache_stats['size'] / cache_stats['max_size']) * 100,
            'evictions': cache_stats['evictions']
        }
        
        # Generate recommendations
        if cache_stats['hit_rate'] < 70:
            analysis['recommendations'].append("Consider increasing cache TTL or size")
        
        if len(analysis['slow_operations']) > 5:
            analysis['recommendations'].append("Multiple slow operations detected - review database indexes")
        
        return analysis
    
    async def optimize_for_load(self, expected_load_multiplier: float = 1.5) -> Dict[str, Any]:
        """Optimize system for expected load increase."""
        optimizations = {
            'cache_adjustments': {},
            'rate_limit_adjustments': {},
            'batch_size_adjustments': {},
            'recommendations': []
        }
        
        # Adjust cache sizes
        current_cache_stats = self.cache_manager.get_stats()
        if current_cache_stats['size'] / current_cache_stats['max_size'] > 0.8:
            # Cache is getting full, recommend increase
            optimizations['recommendations'].append(
                f"Consider increasing cache size from {current_cache_stats['max_size']} "
                f"to {int(current_cache_stats['max_size'] * expected_load_multiplier)}"
            )
        
        # Adjust batch processing
        batch_stats = self.batch_manager.get_all_stats()
        for name, stats in batch_stats.items():
            if stats['pending_items'] > stats['config']['max_batch_size'] * 0.8:
                optimizations['batch_size_adjustments'][name] = {
                    'current_size': stats['config']['max_batch_size'],
                    'recommended_size': int(stats['config']['max_batch_size'] * expected_load_multiplier)
                }
        
        return optimizations