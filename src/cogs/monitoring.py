"""
Monitoring cog for accessing system monitoring and health information.
"""

import asyncio
import time
from typing import Optional, List, Dict, Any

import discord
from discord.ext import commands
from discord import app_commands

from utils.logging_config import get_logger, LoggerMixin
from core.permission_decorators import require_permission
from core.alerting_system import AlertSeverity, AlertType
from core.log_aggregator import LogLevel


class MonitoringCog(commands.Cog, LoggerMixin):
    """Cog for system monitoring and health commands."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="health", description="Check system health status")
    @require_permission("admin")
    async def health_check(self, interaction: discord.Interaction):
        """Check system health status."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            if not self.bot.health_monitor:
                await interaction.followup.send("❌ Health monitoring not available", ephemeral=True)
                return
            
            # Run health checks
            health_results = await self.bot.health_monitor.run_all_checks()
            overall_health = self.bot.health_monitor.get_overall_health()
            
            # Create embed
            embed = discord.Embed(
                title="🏥 System Health Status",
                color=self._get_health_color(overall_health.value),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="Overall Status",
                value=f"**{overall_health.value.upper()}**",
                inline=False
            )
            
            # Add individual health checks
            for check_name, health_check in health_results.items():
                status_emoji = {
                    "healthy": "✅",
                    "degraded": "⚠️",
                    "unhealthy": "❌",
                    "unknown": "❓"
                }.get(health_check.status.value, "❓")
                
                embed.add_field(
                    name=f"{status_emoji} {check_name.replace('_', ' ').title()}",
                    value=f"{health_check.message}\n*{health_check.duration_ms:.1f}ms*",
                    inline=True
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in health check command: {e}")
            await interaction.followup.send(f"❌ Error checking health: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="metrics", description="View system metrics summary")
    @require_permission("admin")
    async def metrics_summary(self, interaction: discord.Interaction):
        """View system metrics summary."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            if not self.bot.metrics:
                await interaction.followup.send("❌ Metrics collection not available", ephemeral=True)
                return
            
            # Get metrics data
            system_stats = self.bot.metrics.get_system_stats()
            command_stats = self.bot.metrics.get_command_stats()
            
            # Create embed
            embed = discord.Embed(
                title="📊 System Metrics",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            # System stats
            uptime_hours = system_stats.get("uptime_seconds", 0) / 3600
            embed.add_field(
                name="System",
                value=f"**Uptime:** {uptime_hours:.1f} hours\n"
                      f"**Commands:** {system_stats.get('total_commands', 0)}\n"
                      f"**Errors:** {system_stats.get('total_errors', 0)}",
                inline=True
            )
            
            # Metrics collection stats
            embed.add_field(
                name="Metrics",
                value=f"**Collected:** {system_stats.get('metrics_collected', 0)}\n"
                      f"**Counters:** {system_stats.get('unique_counters', 0)}\n"
                      f"**Gauges:** {system_stats.get('unique_gauges', 0)}",
                inline=True
            )
            
            # Top commands
            if command_stats:
                top_commands = sorted(
                    [(name, stats["total_executions"]) for name, stats in command_stats.items()],
                    key=lambda x: x[1],
                    reverse=True
                )[:5]
                
                top_commands_text = "\n".join([
                    f"**{name}:** {count}" for name, count in top_commands
                ])
                
                embed.add_field(
                    name="Top Commands",
                    value=top_commands_text or "No commands recorded",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in metrics command: {e}")
            await interaction.followup.send(f"❌ Error getting metrics: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="performance", description="View performance statistics")
    @require_permission("admin")
    async def performance_stats(self, interaction: discord.Interaction):
        """View performance statistics."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            if not self.bot.performance_monitor:
                await interaction.followup.send("❌ Performance monitoring not available", ephemeral=True)
                return
            
            # Get performance data
            performance_summary = self.bot.performance_monitor.get_performance_summary()
            performance_alerts = await self.bot.performance_monitor.get_performance_alerts()
            
            # Create embed
            embed = discord.Embed(
                title="⚡ Performance Statistics",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            
            # Summary stats
            embed.add_field(
                name="Overview",
                value=f"**Operations:** {performance_summary.get('total_operations', 0)}\n"
                      f"**Avg Response:** {performance_summary.get('avg_response_time_ms', 0):.1f}ms",
                inline=True
            )
            
            # Threshold distribution
            threshold_dist = performance_summary.get('operations_by_threshold', {})
            if threshold_dist:
                threshold_text = "\n".join([
                    f"**{threshold.title()}:** {count}"
                    for threshold, count in threshold_dist.items()
                ])
                embed.add_field(
                    name="Response Times",
                    value=threshold_text,
                    inline=True
                )
            
            # Slowest operations
            slowest_ops = performance_summary.get('slowest_operations', [])
            if slowest_ops:
                slowest_text = "\n".join([
                    f"**{op['operation']}:** {op['avg_duration_ms']:.1f}ms"
                    for op in slowest_ops[:5]
                ])
                embed.add_field(
                    name="Slowest Operations",
                    value=slowest_text,
                    inline=False
                )
            
            # Performance alerts
            if performance_alerts:
                alert_text = "\n".join([
                    f"⚠️ **{alert['operation']}:** {alert['message']}"
                    for alert in performance_alerts[:3]
                ])
                embed.add_field(
                    name="Performance Alerts",
                    value=alert_text,
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in performance command: {e}")
            await interaction.followup.send(f"❌ Error getting performance stats: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="alerts", description="View active system alerts")
    @require_permission("admin")
    async def active_alerts(self, interaction: discord.Interaction):
        """View active system alerts."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            if not self.bot.alerting_system:
                await interaction.followup.send("❌ Alerting system not available", ephemeral=True)
                return
            
            # Get active alerts
            active_alerts = self.bot.alerting_system.get_active_alerts()
            
            if not active_alerts:
                embed = discord.Embed(
                    title="🔔 System Alerts",
                    description="✅ No active alerts",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Create embed
            embed = discord.Embed(
                title="🚨 Active System Alerts",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="Summary",
                value=f"**Total Active Alerts:** {len(active_alerts)}",
                inline=False
            )
            
            # Show alerts (limit to 10)
            for i, alert in enumerate(active_alerts[:10]):
                severity_emoji = {
                    "low": "🔵",
                    "medium": "🟡",
                    "high": "🟠",
                    "critical": "🔴"
                }.get(alert.severity.value, "⚪")
                
                alert_age = time.time() - alert.timestamp
                age_text = f"{alert_age / 60:.0f}m ago" if alert_age < 3600 else f"{alert_age / 3600:.1f}h ago"
                
                embed.add_field(
                    name=f"{severity_emoji} {alert.title}",
                    value=f"{alert.message}\n*{age_text}*",
                    inline=False
                )
            
            if len(active_alerts) > 10:
                embed.add_field(
                    name="Note",
                    value=f"Showing 10 of {len(active_alerts)} alerts",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in alerts command: {e}")
            await interaction.followup.send(f"❌ Error getting alerts: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="logs", description="Search and analyze recent logs")
    @app_commands.describe(
        query="Search query (optional)",
        hours="Hours back to search (default: 1)",
        level="Log level filter"
    )
    @require_permission("admin")
    async def search_logs(
        self,
        interaction: discord.Interaction,
        query: Optional[str] = None,
        hours: Optional[int] = 1,
        level: Optional[str] = None
    ):
        """Search and analyze recent logs."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            if not self.bot.log_aggregator:
                await interaction.followup.send("❌ Log aggregation not available", ephemeral=True)
                return
            
            hours = max(1, min(hours or 1, 24))  # Limit to 1-24 hours
            
            # Parse log level
            log_levels = None
            if level:
                try:
                    log_levels = [LogLevel(level.upper())]
                except ValueError:
                    await interaction.followup.send(f"❌ Invalid log level: {level}", ephemeral=True)
                    return
            
            if query:
                # Search logs
                entries = await self.bot.log_aggregator.search_logs(
                    query=query,
                    hours_back=hours,
                    case_sensitive=False
                )
                
                embed = discord.Embed(
                    title=f"🔍 Log Search Results",
                    description=f"Query: `{query}` | Last {hours}h",
                    color=discord.Color.blue(),
                    timestamp=discord.utils.utcnow()
                )
                
                embed.add_field(
                    name="Results",
                    value=f"Found {len(entries)} matching entries",
                    inline=False
                )
                
                # Show recent matches
                if entries:
                    recent_entries = sorted(entries, key=lambda x: x.timestamp, reverse=True)[:5]
                    for i, entry in enumerate(recent_entries):
                        entry_time = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
                        message_preview = entry.message[:100] + "..." if len(entry.message) > 100 else entry.message
                        
                        embed.add_field(
                            name=f"{entry.level.value} - {entry_time}",
                            value=f"**{entry.logger_name}**\n{message_preview}",
                            inline=False
                        )
                
            else:
                # Analyze logs
                analysis = await self.bot.log_aggregator.analyze_logs(
                    hours_back=hours,
                    log_levels=log_levels
                )
                
                embed = discord.Embed(
                    title="📋 Log Analysis",
                    description=f"Analysis of last {hours}h",
                    color=discord.Color.blue(),
                    timestamp=discord.utils.utcnow()
                )
                
                # Summary
                embed.add_field(
                    name="Summary",
                    value=f"**Total Entries:** {analysis.total_entries}\n"
                          f"**Analysis Time:** {analysis.analysis_duration_ms:.1f}ms",
                    inline=True
                )
                
                # Entries by level
                if analysis.entries_by_level:
                    level_text = "\n".join([
                        f"**{level}:** {count}"
                        for level, count in analysis.entries_by_level.items()
                    ])
                    embed.add_field(
                        name="By Level",
                        value=level_text,
                        inline=True
                    )
                
                # Top loggers
                if analysis.top_loggers:
                    logger_text = "\n".join([
                        f"**{logger}:** {count}"
                        for logger, count in analysis.top_loggers[:5]
                    ])
                    embed.add_field(
                        name="Top Loggers",
                        value=logger_text,
                        inline=False
                    )
                
                # Error patterns
                if analysis.error_patterns:
                    pattern_text = "\n".join([
                        f"**{pattern['pattern_name']}:** {pattern['total_occurrences']} occurrences"
                        for pattern in analysis.error_patterns[:3]
                    ])
                    embed.add_field(
                        name="Error Patterns",
                        value=pattern_text,
                        inline=False
                    )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in logs command: {e}")
            await interaction.followup.send(f"❌ Error searching logs: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="dashboard", description="Get system dashboard URL or status")
    @require_permission("admin")
    async def dashboard_info(self, interaction: discord.Interaction):
        """Get system dashboard information."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            if not self.bot.system_dashboard:
                await interaction.followup.send("❌ System dashboard not available", ephemeral=True)
                return
            
            # Get dashboard data
            dashboard_data = self.bot.system_dashboard.get_current_data()
            if not dashboard_data:
                dashboard_data = await self.bot.system_dashboard.refresh_dashboard()
            
            # Create embed
            embed = discord.Embed(
                title="📊 System Dashboard",
                color=self._get_health_color(dashboard_data.overall_status.value),
                timestamp=discord.utils.utcnow()
            )
            
            # Overall status
            embed.add_field(
                name="Overall Status",
                value=f"**{dashboard_data.overall_status.value.upper()}**",
                inline=True
            )
            
            # Component summary
            component_counts = {}
            for component in dashboard_data.components:
                status = component.status.value
                component_counts[status] = component_counts.get(status, 0) + 1
            
            if component_counts:
                status_text = "\n".join([
                    f"**{status.title()}:** {count}"
                    for status, count in component_counts.items()
                ])
                embed.add_field(
                    name="Components",
                    value=status_text,
                    inline=True
                )
            
            # Active alerts
            embed.add_field(
                name="Active Alerts",
                value=f"**{len(dashboard_data.active_alerts)}** alerts",
                inline=True
            )
            
            # System info
            system_info = dashboard_data.system_info
            if system_info:
                uptime = system_info.get("uptime_seconds", 0)
                memory_mb = system_info.get("memory_usage_mb", 0)
                
                embed.add_field(
                    name="System Info",
                    value=f"**Uptime:** {uptime / 3600:.1f}h\n"
                          f"**Memory:** {memory_mb:.1f}MB",
                    inline=True
                )
            
            # Performance summary
            perf_summary = dashboard_data.performance_summary
            if perf_summary:
                avg_response = perf_summary.get("avg_response_time_ms", 0)
                total_ops = perf_summary.get("total_operations", 0)
                
                embed.add_field(
                    name="Performance",
                    value=f"**Operations:** {total_ops}\n"
                          f"**Avg Response:** {avg_response:.1f}ms",
                    inline=True
                )
            
            # Last updated
            last_updated = dashboard_data.last_updated
            if last_updated:
                updated_ago = time.time() - last_updated
                embed.add_field(
                    name="Last Updated",
                    value=f"{updated_ago:.0f} seconds ago",
                    inline=True
                )
            
            # Add web dashboard URL if available
            web_url = self.bot.settings.get('WEB_DASHBOARD_URL')
            if web_url:
                embed.add_field(
                    name="Web Dashboard",
                    value=f"[Open Dashboard]({web_url})",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in dashboard command: {e}")
            await interaction.followup.send(f"❌ Error getting dashboard info: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="test-alert", description="Send a test alert (admin only)")
    @app_commands.describe(severity="Alert severity level")
    @require_permission("admin")
    async def test_alert(
        self,
        interaction: discord.Interaction,
        severity: Optional[str] = "medium"
    ):
        """Send a test alert."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            if not self.bot.alerting_system:
                await interaction.followup.send("❌ Alerting system not available", ephemeral=True)
                return
            
            # Parse severity
            try:
                alert_severity = AlertSeverity(severity.lower())
            except ValueError:
                await interaction.followup.send(
                    f"❌ Invalid severity. Use: {', '.join([s.value for s in AlertSeverity])}",
                    ephemeral=True
                )
                return
            
            # Send test alert
            await self.bot.alerting_system.send_alert(
                alert_type=AlertType.CUSTOM,
                severity=alert_severity,
                title="Test Alert",
                message=f"This is a test alert with {severity} severity triggered by {interaction.user.mention}",
                source="monitoring_cog",
                details={
                    "user_id": str(interaction.user.id),
                    "guild_id": str(interaction.guild.id) if interaction.guild else None,
                    "test": True
                }
            )
            
            await interaction.followup.send(
                f"✅ Test alert sent with {severity} severity",
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error sending test alert: {e}")
            await interaction.followup.send(f"❌ Error sending test alert: {str(e)}", ephemeral=True)
    
    def _get_health_color(self, status: str) -> discord.Color:
        """Get Discord color for health status."""
        color_map = {
            "healthy": discord.Color.green(),
            "warning": discord.Color.yellow(),
            "critical": discord.Color.red(),
            "unknown": discord.Color.grey()
        }
        return color_map.get(status, discord.Color.grey())


async def setup(bot):
    """Set up the monitoring cog."""
    await bot.add_cog(MonitoringCog(bot))