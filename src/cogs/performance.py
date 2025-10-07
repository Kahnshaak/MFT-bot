"""
Performance monitoring and optimization commands for administrators.
"""

import asyncio
from typing import Optional, Dict, Any
import discord
from discord.ext import commands
from discord import app_commands

from core.permission_decorators import require_permission
from core.security_manager import Permission
from utils.logging_config import get_logger, LoggerMixin


class PerformanceCog(commands.Cog, LoggerMixin):
    """
    Cog for performance monitoring and optimization commands.
    
    Provides administrators with tools to monitor bot performance,
    view statistics, and trigger optimizations.
    """
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="performance-stats", description="View bot performance statistics")
    @require_permission(Permission.MANAGE_GUILD)
    async def performance_stats(self, interaction: discord.Interaction):
        """View comprehensive performance statistics."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            if not hasattr(self.bot, 'performance_integration') or not self.bot.performance_integration:
                await interaction.followup.send(
                    "❌ Performance monitoring is not available.",
                    ephemeral=True
                )
                return
            
            # Get comprehensive stats
            stats = await self.bot.performance_integration.get_comprehensive_stats()
            
            # Create main embed
            embed = discord.Embed(
                title="🔧 Bot Performance Statistics",
                description="Comprehensive performance metrics and statistics",
                color=0x00ff00
            )
            
            # System metrics
            system_stats = stats.get('metrics', {}).get('system_stats', {})
            embed.add_field(
                name="⏱️ System Metrics",
                value=(
                    f"**Uptime:** {system_stats.get('uptime_seconds', 0):.0f}s\n"
                    f"**Commands:** {system_stats.get('total_commands', 0):,}\n"
                    f"**Errors:** {system_stats.get('total_errors', 0):,}"
                ),
                inline=True
            )
            
            # Cache statistics
            cache_stats = stats.get('cache', {})
            embed.add_field(
                name="💾 Cache Performance",
                value=(
                    f"**Hit Rate:** {cache_stats.get('hit_rate', 0):.1f}%\n"
                    f"**Size:** {cache_stats.get('size', 0):,}/{cache_stats.get('max_size', 0):,}\n"
                    f"**Evictions:** {cache_stats.get('evictions', 0):,}"
                ),
                inline=True
            )
            
            # Rate limiting
            rate_stats = stats.get('rate_limiting', {})
            embed.add_field(
                name="🚦 Rate Limiting",
                value=(
                    f"**Success Rate:** {rate_stats.get('success_rate', 0):.1f}%\n"
                    f"**Active Keys:** {rate_stats.get('active_keys', 0):,}\n"
                    f"**Blocked Keys:** {rate_stats.get('blocked_keys', 0):,}"
                ),
                inline=True
            )
            
            # Performance summary
            performance = stats.get('performance', {})
            embed.add_field(
                name="📊 Response Times",
                value=(
                    f"**Avg Response:** {performance.get('avg_response_time_ms', 0):.1f}ms\n"
                    f"**Total Operations:** {performance.get('total_operations', 0):,}\n"
                    f"**Trending:** {performance.get('trending_operations', {}).get('stable', 0)} stable"
                ),
                inline=True
            )
            
            # Database performance
            db_stats = stats.get('database', {})
            if db_stats and 'query_stats' in db_stats:
                query_count = len(db_stats['query_stats'])
                embed.add_field(
                    name="🗄️ Database",
                    value=(
                        f"**Query Types:** {query_count}\n"
                        f"**Slow Queries:** {len(db_stats.get('slow_queries', []))}\n"
                        f"**Recommendations:** {len(db_stats.get('index_recommendations', {}))}"
                    ),
                    inline=True
                )
            
            # Batch processing
            batch_stats = stats.get('batch_processing', {})
            if batch_stats:
                total_processed = sum(
                    processor.get('total_processed', 0) 
                    for processor in batch_stats.values()
                )
                embed.add_field(
                    name="📦 Batch Processing",
                    value=(
                        f"**Processors:** {len(batch_stats)}\n"
                        f"**Total Processed:** {total_processed:,}\n"
                        f"**Active Batches:** {sum(processor.get('processing_batches', 0) for processor in batch_stats.values())}"
                    ),
                    inline=True
                )
            
            embed.set_footer(text=f"Generated at {stats.get('timestamp', 'unknown')}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in performance stats command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while retrieving performance statistics.",
                ephemeral=True
            )
    
    @app_commands.command(name="performance-analysis", description="Run comprehensive performance analysis")
    @require_permission(Permission.MANAGE_GUILD)
    async def performance_analysis(self, interaction: discord.Interaction):
        """Run comprehensive performance analysis with recommendations."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            if not hasattr(self.bot, 'performance_integration') or not self.bot.performance_integration:
                await interaction.followup.send(
                    "❌ Performance monitoring is not available.",
                    ephemeral=True
                )
                return
            
            # Run analysis
            analysis = await self.bot.performance_integration.run_performance_analysis()
            
            # Create analysis embed
            embed = discord.Embed(
                title="🔍 Performance Analysis Report",
                description="Detailed analysis with optimization recommendations",
                color=0xff9900
            )
            
            # Performance alerts
            alerts = analysis.get('alerts', [])
            if alerts:
                alert_summary = []
                for alert in alerts[:5]:  # Show top 5 alerts
                    alert_summary.append(f"• {alert.get('message', 'Unknown alert')}")
                
                embed.add_field(
                    name="⚠️ Performance Alerts",
                    value="\n".join(alert_summary) if alert_summary else "No alerts",
                    inline=False
                )
            
            # Slow operations
            slow_ops = analysis.get('slow_operations', [])
            if slow_ops:
                slow_summary = []
                for op in slow_ops[:3]:  # Show top 3 slow operations
                    slow_summary.append(
                        f"• {op['operation']}: {op['avg_duration_ms']:.1f}ms "
                        f"({op['total_calls']} calls)"
                    )
                
                embed.add_field(
                    name="🐌 Slow Operations",
                    value="\n".join(slow_summary) if slow_summary else "No slow operations",
                    inline=False
                )
            
            # Cache efficiency
            cache_eff = analysis.get('cache_efficiency', {})
            embed.add_field(
                name="💾 Cache Efficiency",
                value=(
                    f"**Hit Rate:** {cache_eff.get('hit_rate', 0):.1f}%\n"
                    f"**Utilization:** {cache_eff.get('size_utilization', 0):.1f}%\n"
                    f"**Evictions:** {cache_eff.get('evictions', 0):,}"
                ),
                inline=True
            )
            
            # Recommendations
            recommendations = analysis.get('recommendations', [])
            if recommendations:
                rec_text = "\n".join([f"• {rec}" for rec in recommendations[:5]])
                embed.add_field(
                    name="💡 Recommendations",
                    value=rec_text if rec_text else "No recommendations",
                    inline=False
                )
            
            # Optimization suggestions
            suggestions = analysis.get('optimization_suggestions', [])
            if suggestions:
                sug_text = "\n".join([
                    f"• {sug.get('suggestion', 'Unknown suggestion')}"
                    for sug in suggestions[:3]
                ])
                embed.add_field(
                    name="🔧 Optimization Suggestions",
                    value=sug_text if sug_text else "No suggestions",
                    inline=False
                )
            
            embed.set_footer(text=f"Analysis completed at {analysis.get('timestamp', 'unknown')}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in performance analysis command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while running performance analysis.",
                ephemeral=True
            )
    
    @app_commands.command(name="optimize-database", description="Run database optimizations")
    @require_permission(Permission.MANAGE_GUILD)
    async def optimize_database(self, interaction: discord.Interaction):
        """Run database optimizations including index creation."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            if not hasattr(self.bot, 'database') or not self.bot.database:
                await interaction.followup.send(
                    "❌ Database is not available.",
                    ephemeral=True
                )
                return
            
            # Run database optimizations
            results = await self.bot.database.optimize_queries()
            
            embed = discord.Embed(
                title="🗄️ Database Optimization Results",
                description="Results from database optimization process",
                color=0x00ff00
            )
            
            # Index creation results
            indexes_created = results.get('indexes_created', {})
            if indexes_created:
                index_summary = []
                for collection, indexes in indexes_created.items():
                    if indexes:
                        index_summary.append(f"**{collection}:** {len(indexes)} indexes")
                
                embed.add_field(
                    name="📊 Indexes Created",
                    value="\n".join(index_summary) if index_summary else "No indexes created",
                    inline=False
                )
            
            # Performance metrics
            embed.add_field(
                name="📈 Performance Metrics",
                value=(
                    f"**Slow Queries:** {results.get('slow_queries_count', 0)}\n"
                    f"**Total Queries:** {results.get('total_queries', 0):,}\n"
                    f"**Avg Query Time:** {results.get('avg_query_time', 0):.2f}ms"
                ),
                inline=True
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in database optimization command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while optimizing the database.",
                ephemeral=True
            )
    
    @app_commands.command(name="clear-cache", description="Clear bot caches")
    @require_permission(Permission.MANAGE_GUILD)
    async def clear_cache(
        self, 
        interaction: discord.Interaction,
        pattern: Optional[str] = None
    ):
        """Clear bot caches with optional pattern matching."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            if not hasattr(self.bot, 'cache_manager') or not self.bot.cache_manager:
                await interaction.followup.send(
                    "❌ Cache manager is not available.",
                    ephemeral=True
                )
                return
            
            # Clear cache
            if pattern:
                cleared_count = await self.bot.cache_manager.invalidate_pattern(pattern)
                message = f"✅ Cleared {cleared_count} cache entries matching pattern: `{pattern}`"
            else:
                await self.bot.cache_manager.clear()
                message = "✅ All caches cleared successfully"
            
            # Also clear database query cache if available
            if hasattr(self.bot, 'database') and self.bot.database:
                db_cleared = await self.bot.database.clear_cache(pattern)
                if db_cleared > 0:
                    message += f"\n🗄️ Cleared {db_cleared} database query cache entries"
            
            await interaction.followup.send(message, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in clear cache command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while clearing caches.",
                ephemeral=True
            )
    
    @app_commands.command(name="flush-batches", description="Flush all pending batch operations")
    @require_permission(Permission.MANAGE_GUILD)
    async def flush_batches(self, interaction: discord.Interaction):
        """Flush all pending batch operations."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            if not hasattr(self.bot, 'database') or not self.bot.database:
                await interaction.followup.send(
                    "❌ Database is not available.",
                    ephemeral=True
                )
                return
            
            # Flush database batches
            results = await self.bot.database.flush_batches()
            
            # Also flush notification batches if available
            notification_result = "not available"
            if hasattr(self.bot, 'notification_manager') and self.bot.notification_manager:
                try:
                    await self.bot.notification_manager.batch_processor.flush()
                    notification_result = "flushed"
                except Exception as e:
                    notification_result = f"error: {str(e)}"
            
            embed = discord.Embed(
                title="📦 Batch Flush Results",
                description="Results from flushing pending batch operations",
                color=0x00ff00
            )
            
            # Database batch results
            db_results = []
            for name, result in results.items():
                status = "✅" if result == "flushed" else "❌"
                db_results.append(f"{status} {name}: {result}")
            
            embed.add_field(
                name="🗄️ Database Batches",
                value="\n".join(db_results) if db_results else "No database batches",
                inline=False
            )
            
            # Notification batch result
            status = "✅" if notification_result == "flushed" else "❌"
            embed.add_field(
                name="📧 Notification Batches",
                value=f"{status} notifications: {notification_result}",
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in flush batches command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while flushing batches.",
                ephemeral=True
            )


async def setup(bot):
    """Set up the cog."""
    await bot.add_cog(PerformanceCog(bot))