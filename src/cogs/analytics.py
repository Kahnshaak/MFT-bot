"""
Analytics cog for Discord Game Night Bot.

Provides Discord slash commands for accessing analytics data,
generating reports, and viewing insights about server activity.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json

import discord
from discord.ext import commands

from core.analytics_engine import AnalyticsEngine, TrendDirection
from core.permission_decorators import require_permission, rate_limit
from core.security_manager import Permission
from database.manager import DatabaseManager
from utils.logging_config import LoggerMixin
from utils.exceptions import PermissionDeniedError, ValidationError


class AnalyticsView(discord.ui.View):
    """Interactive view for analytics commands."""
    
    def __init__(self, cog, guild_id: str, user_id: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
    
    @discord.ui.button(label="📊 Attendance", style=discord.ButtonStyle.primary)
    async def attendance_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        """Show attendance analytics."""
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message("❌ Only the command user can interact with this.", ephemeral=True)
            return
        
        await interaction.response.defer()
        embed = await self.cog._create_attendance_embed(self.guild_id)
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=self)
    
    @discord.ui.button(label="🎮 Games", style=discord.ButtonStyle.secondary)
    async def games_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        """Show game popularity analytics."""
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message("❌ Only the command user can interact with this.", ephemeral=True)
            return
        
        await interaction.response.defer()
        embed = await self.cog._create_games_embed(self.guild_id)
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=self)
    
    @discord.ui.button(label="👥 Users", style=discord.ButtonStyle.secondary)
    async def users_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        """Show user engagement analytics."""
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message("❌ Only the command user can interact with this.", ephemeral=True)
            return
        
        await interaction.response.defer()
        embed = await self.cog._create_users_embed(self.guild_id)
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=self)
    
    @discord.ui.button(label="📅 Scheduling", style=discord.ButtonStyle.secondary)
    async def scheduling_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        """Show scheduling recommendations."""
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message("❌ Only the command user can interact with this.", ephemeral=True)
            return
        
        await interaction.response.defer()
        embed = await self.cog._create_scheduling_embed(self.guild_id)
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=self)
    
    @discord.ui.button(label="📤 Export", style=discord.ButtonStyle.success)
    async def export_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        """Export analytics data."""
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message("❌ Only the command user can interact with this.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Generate export data
            export_data = await self.cog.analytics_engine.export_analytics_data(
                self.guild_id, include_user_data=False
            )
            
            # Create file
            export_json = json.dumps(export_data, indent=2, default=str)
            file = discord.File(
                fp=discord.utils.StringIO(export_json),
                filename=f"analytics_{self.guild_id}_{datetime.now().strftime('%Y%m%d')}.json"
            )
            
            await interaction.followup.send(
                "📊 **Analytics Export**\n"
                f"Generated: <t:{int(datetime.now().timestamp())}:F>\n"
                f"Data includes: Attendance, Games, User Engagement, Scheduling",
                file=file,
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ Failed to export analytics data: {str(e)}",
                ephemeral=True
            )


class AnalyticsCog(commands.Cog, LoggerMixin):
    """Analytics commands for server insights and reporting."""
    
    def __init__(self, bot):
        self.bot = bot
        self.database: DatabaseManager = bot.database
        self.analytics_engine = AnalyticsEngine(self.database)
    
    @discord.slash_command(
        name="analytics",
        description="View server analytics and insights"
    )
    @require_permission(Permission.VIEW_ANALYTICS)
    @rate_limit(max_requests=5, window_seconds=300, per_user=True)
    async def analytics_command(
        self,
        ctx: discord.ApplicationContext,
        period: discord.Option(
            str,
            description="Analysis period",
            choices=[
                discord.OptionChoice(name="Last 7 days", value="7"),
                discord.OptionChoice(name="Last 30 days", value="30"),
                discord.OptionChoice(name="Last 90 days", value="90")
            ],
            default="30"
        ) = "30",
        category: discord.Option(
            str,
            description="Analytics category to view",
            choices=[
                discord.OptionChoice(name="Overview", value="overview"),
                discord.OptionChoice(name="Attendance", value="attendance"),
                discord.OptionChoice(name="Games", value="games"),
                discord.OptionChoice(name="Users", value="users"),
                discord.OptionChoice(name="Scheduling", value="scheduling")
            ],
            default="overview"
        ) = "overview"
    ):
        """Main analytics command with interactive interface."""
        await ctx.defer()
        
        try:
            guild_id = str(ctx.guild.id)
            days_back = int(period)
            
            if category == "overview":
                embed = await self._create_overview_embed(guild_id, days_back)
                view = AnalyticsView(self, guild_id, str(ctx.user.id))
                await ctx.followup.send(embed=embed, view=view)
            
            elif category == "attendance":
                embed = await self._create_attendance_embed(guild_id, days_back)
                await ctx.followup.send(embed=embed)
            
            elif category == "games":
                embed = await self._create_games_embed(guild_id, days_back)
                await ctx.followup.send(embed=embed)
            
            elif category == "users":
                embed = await self._create_users_embed(guild_id, days_back)
                await ctx.followup.send(embed=embed)
            
            elif category == "scheduling":
                embed = await self._create_scheduling_embed(guild_id)
                await ctx.followup.send(embed=embed)
            
        except PermissionDeniedError as e:
            await ctx.followup.send(f"❌ {e.user_message}", ephemeral=True)
        except Exception as e:
            self.logger.error(
                "Analytics command error",
                guild_id=ctx.guild.id,
                user_id=ctx.user.id,
                category=category,
                period=period,
                error=str(e),
                exc_info=True
            )
            await ctx.followup.send(
                "❌ An error occurred while generating analytics. Please try again later.",
                ephemeral=True
            )
    
    @discord.slash_command(
        name="report",
        description="Generate and export detailed analytics report"
    )
    @require_permission(Permission.VIEW_ANALYTICS)
    @rate_limit(max_requests=2, window_seconds=600, per_user=True)
    async def report_command(
        self,
        ctx: discord.ApplicationContext,
        format: discord.Option(
            str,
            description="Report format",
            choices=[
                discord.OptionChoice(name="JSON", value="json"),
                discord.OptionChoice(name="Summary", value="summary")
            ],
            default="summary"
        ) = "summary",
        include_users: discord.Option(
            bool,
            description="Include detailed user data (admin only)",
            default=False
        ) = False
    ):
        """Generate comprehensive analytics report."""
        await ctx.defer(ephemeral=True)
        
        try:
            guild_id = str(ctx.guild.id)
            
            # Check if user can include user data
            if include_users:
                # Additional permission check for user data
                user_permissions = await self.bot.security.get_user_permissions(
                    str(ctx.user.id), guild_id
                )
                if Permission.MANAGE_GUILD not in user_permissions:
                    include_users = False
                    await ctx.followup.send(
                        "⚠️ User data export requires admin permissions. Generating report without user details.",
                        ephemeral=True
                    )
            
            if format == "json":
                # Generate full JSON export
                export_data = await self.analytics_engine.export_analytics_data(
                    guild_id, include_users
                )
                
                export_json = json.dumps(export_data, indent=2, default=str)
                file = discord.File(
                    fp=discord.utils.StringIO(export_json),
                    filename=f"analytics_report_{guild_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
                )
                
                await ctx.followup.send(
                    "📊 **Complete Analytics Report**\n"
                    f"Generated: <t:{int(datetime.now().timestamp())}:F>\n"
                    f"Includes user data: {'Yes' if include_users else 'No'}",
                    file=file,
                    ephemeral=True
                )
            
            else:
                # Generate summary report
                summary_embed = await self._create_summary_report_embed(guild_id)
                await ctx.followup.send(embed=summary_embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(
                "Report command error",
                guild_id=ctx.guild.id,
                user_id=ctx.user.id,
                format=format,
                include_users=include_users,
                error=str(e),
                exc_info=True
            )
            await ctx.followup.send(
                "❌ Failed to generate report. Please try again later.",
                ephemeral=True
            )
    
    @discord.slash_command(
        name="insights",
        description="Get AI-powered insights and recommendations"
    )
    @require_permission(Permission.VIEW_ANALYTICS)
    @rate_limit(max_requests=3, window_seconds=300, per_user=True)
    async def insights_command(
        self,
        ctx: discord.ApplicationContext,
        focus: discord.Option(
            str,
            description="Focus area for insights",
            choices=[
                discord.OptionChoice(name="Attendance Optimization", value="attendance"),
                discord.OptionChoice(name="Game Recommendations", value="games"),
                discord.OptionChoice(name="Scheduling Optimization", value="scheduling"),
                discord.OptionChoice(name="User Engagement", value="engagement")
            ],
            default="attendance"
        ) = "attendance"
    ):
        """Get AI-powered insights and recommendations."""
        await ctx.defer()
        
        try:
            guild_id = str(ctx.guild.id)
            
            if focus == "attendance":
                embed = await self._create_attendance_insights_embed(guild_id)
            elif focus == "games":
                embed = await self._create_game_insights_embed(guild_id)
            elif focus == "scheduling":
                embed = await self._create_scheduling_insights_embed(guild_id)
            elif focus == "engagement":
                embed = await self._create_engagement_insights_embed(guild_id)
            
            await ctx.followup.send(embed=embed)
            
        except Exception as e:
            self.logger.error(
                "Insights command error",
                guild_id=ctx.guild.id,
                user_id=ctx.user.id,
                focus=focus,
                error=str(e),
                exc_info=True
            )
            await ctx.followup.send(
                "❌ Failed to generate insights. Please try again later.",
                ephemeral=True
            )
    
    # Helper methods for creating embeds
    
    async def _create_overview_embed(self, guild_id: str, days_back: int = 30) -> discord.Embed:
        """Create overview analytics embed."""
        try:
            # Get basic metrics
            attendance_metrics = await self.analytics_engine.get_attendance_analytics(guild_id, days_back)
            game_metrics = await self.analytics_engine.get_game_popularity_analytics(guild_id, days_back)
            user_metrics = await self.analytics_engine.get_user_engagement_metrics(guild_id, days_back, 10)
            
            embed = discord.Embed(
                title="📊 Analytics Overview",
                description=f"Server analytics for the last {days_back} days",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            # Attendance summary
            trend_emoji = "📈" if attendance_metrics.trend and attendance_metrics.trend.direction == TrendDirection.UP else "📉" if attendance_metrics.trend and attendance_metrics.trend.direction == TrendDirection.DOWN else "➡️"
            embed.add_field(
                name="🎯 Event Activity",
                value=f"**Total Events:** {attendance_metrics.total_events}\n"
                      f"**Completed:** {attendance_metrics.completed_events}\n"
                      f"**Completion Rate:** {attendance_metrics.completion_rate:.1%}\n"
                      f"**Trend:** {trend_emoji} {attendance_metrics.trend.change_percent:+.1f}%" if attendance_metrics.trend else "",
                inline=True
            )
            
            # Attendance metrics
            embed.add_field(
                name="👥 Attendance",
                value=f"**Avg Attendance Rate:** {attendance_metrics.average_attendance_rate:.1%}\n"
                      f"**Total Attendees:** {attendance_metrics.total_attendees}\n"
                      f"**Avg RSVPs:** {attendance_metrics.average_rsvp_count:.1f}\n"
                      f"**No-Show Rate:** {attendance_metrics.no_show_rate:.1%}",
                inline=True
            )
            
            # Popular games
            if game_metrics:
                top_games = game_metrics[:3]
                games_text = "\n".join([
                    f"**{game.game_name}:** {game.interest_count} interested"
                    for game in top_games
                ])
                embed.add_field(
                    name="🎮 Popular Games",
                    value=games_text or "No game data available",
                    inline=True
                )
            
            # User engagement
            if user_metrics:
                avg_score = sum(u.participation_score for u in user_metrics) / len(user_metrics)
                active_creators = len([u for u in user_metrics if u.events_created > 0])
                
                embed.add_field(
                    name="📈 User Engagement",
                    value=f"**Active Users:** {len(user_metrics)}\n"
                          f"**Avg Participation:** {avg_score:.1f}/100\n"
                          f"**Event Creators:** {active_creators}\n"
                          f"**Highly Engaged:** {len([u for u in user_metrics if u.participation_score > 70])}",
                    inline=True
                )
            
            embed.set_footer(text="Use the buttons below to explore detailed analytics")
            return embed
            
        except Exception as e:
            self.logger.error("Failed to create overview embed", error=str(e))
            return discord.Embed(
                title="❌ Analytics Error",
                description="Failed to load analytics data. Please try again later.",
                color=discord.Color.red()
            )
    
    async def _create_attendance_embed(self, guild_id: str, days_back: int = 30) -> discord.Embed:
        """Create attendance analytics embed."""
        try:
            metrics = await self.analytics_engine.get_attendance_analytics(guild_id, days_back, True)
            
            embed = discord.Embed(
                title="📊 Attendance Analytics",
                description=f"Detailed attendance analysis for the last {days_back} days",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            # Main metrics
            embed.add_field(
                name="📈 Event Statistics",
                value=f"**Total Events:** {metrics.total_events}\n"
                      f"**Completed Events:** {metrics.completed_events}\n"
                      f"**Completion Rate:** {metrics.completion_rate:.1%}\n"
                      f"**Success Rate:** {(1 - metrics.no_show_rate):.1%}",
                inline=True
            )
            
            embed.add_field(
                name="👥 Attendance Metrics",
                value=f"**Total RSVPs:** {metrics.total_rsvps}\n"
                      f"**Total Attendees:** {metrics.total_attendees}\n"
                      f"**Avg Attendance Rate:** {metrics.average_attendance_rate:.1%}\n"
                      f"**Avg RSVPs per Event:** {metrics.average_rsvp_count:.1f}",
                inline=True
            )
            
            # Trend analysis
            if metrics.trend:
                trend_emoji = "📈" if metrics.trend.direction == TrendDirection.UP else "📉" if metrics.trend.direction == TrendDirection.DOWN else "➡️"
                trend_color = "🟢" if metrics.trend.direction == TrendDirection.UP else "🔴" if metrics.trend.direction == TrendDirection.DOWN else "🟡"
                
                embed.add_field(
                    name="📊 Trend Analysis",
                    value=f"**Direction:** {trend_emoji} {metrics.trend.direction.value}\n"
                          f"**Change:** {metrics.trend.change_percent:+.1f}%\n"
                          f"**Current Period:** {metrics.trend.current_value}\n"
                          f"**Previous Period:** {metrics.trend.previous_value}",
                    inline=True
                )
            
            # Recommendations
            recommendations = []
            if metrics.completion_rate < 0.7:
                recommendations.append("• Consider shorter planning periods")
            if metrics.average_attendance_rate < 0.6:
                recommendations.append("• Review optimal scheduling times")
            if metrics.no_show_rate > 0.3:
                recommendations.append("• Send more reminder notifications")
            
            if recommendations:
                embed.add_field(
                    name="💡 Recommendations",
                    value="\n".join(recommendations),
                    inline=False
                )
            
            return embed
            
        except Exception as e:
            self.logger.error("Failed to create attendance embed", error=str(e))
            return discord.Embed(
                title="❌ Attendance Analytics Error",
                description="Failed to load attendance data.",
                color=discord.Color.red()
            )
    
    async def _create_games_embed(self, guild_id: str, days_back: int = 90) -> discord.Embed:
        """Create game popularity analytics embed."""
        try:
            game_metrics = await self.analytics_engine.get_game_popularity_analytics(guild_id, days_back, True)
            
            embed = discord.Embed(
                title="🎮 Game Popularity Analytics",
                description=f"Game interest and play analysis for the last {days_back} days",
                color=discord.Color.purple(),
                timestamp=datetime.utcnow()
            )
            
            if not game_metrics:
                embed.add_field(
                    name="No Data",
                    value="No game data available for this period.",
                    inline=False
                )
                return embed
            
            # Top games by interest
            top_games = game_metrics[:5]
            games_text = ""
            for i, game in enumerate(top_games, 1):
                trend_emoji = "📈" if game.growth_rate > 10 else "📉" if game.growth_rate < -10 else "➡️"
                games_text += f"**{i}. {game.game_name}**\n"
                games_text += f"   Interest: {game.interest_count} users\n"
                games_text += f"   Events: {game.events_played} | Avg Attendance: {game.average_attendance:.1f}\n"
                games_text += f"   Trend: {trend_emoji} {game.growth_rate:+.1f}%\n\n"
            
            embed.add_field(
                name="🏆 Top Games by Interest",
                value=games_text or "No games found",
                inline=False
            )
            
            # Trending games
            trending = [g for g in game_metrics if g.growth_rate > 20][:3]
            if trending:
                trending_text = "\n".join([
                    f"**{game.game_name}:** +{game.growth_rate:.1f}% growth"
                    for game in trending
                ])
                embed.add_field(
                    name="📈 Trending Games",
                    value=trending_text,
                    inline=True
                )
            
            # Recommendations
            recommended = [g for g in game_metrics if g.recommendation_score > 70][:3]
            if recommended:
                rec_text = "\n".join([
                    f"**{game.game_name}:** {game.recommendation_score:.0f}/100"
                    for game in recommended
                ])
                embed.add_field(
                    name="💡 Recommended Games",
                    value=rec_text,
                    inline=True
                )
            
            return embed
            
        except Exception as e:
            self.logger.error("Failed to create games embed", error=str(e))
            return discord.Embed(
                title="❌ Game Analytics Error",
                description="Failed to load game data.",
                color=discord.Color.red()
            )
    
    async def _create_users_embed(self, guild_id: str, days_back: int = 30) -> discord.Embed:
        """Create user engagement analytics embed."""
        try:
            user_metrics = await self.analytics_engine.get_user_engagement_metrics(guild_id, days_back, 20)
            
            embed = discord.Embed(
                title="👥 User Engagement Analytics",
                description=f"User participation analysis for the last {days_back} days",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            
            if not user_metrics:
                embed.add_field(
                    name="No Data",
                    value="No user engagement data available for this period.",
                    inline=False
                )
                return embed
            
            # Summary statistics
            avg_score = sum(u.participation_score for u in user_metrics) / len(user_metrics)
            highly_engaged = len([u for u in user_metrics if u.participation_score > 70])
            active_creators = len([u for u in user_metrics if u.events_created > 0])
            
            embed.add_field(
                name="📊 Engagement Summary",
                value=f"**Total Active Users:** {len(user_metrics)}\n"
                      f"**Avg Participation Score:** {avg_score:.1f}/100\n"
                      f"**Highly Engaged Users:** {highly_engaged}\n"
                      f"**Event Creators:** {active_creators}",
                inline=True
            )
            
            # Top organizers
            organizers = [u for u in user_metrics if u.events_created > 0][:5]
            if organizers:
                org_text = "\n".join([
                    f"**{user.username}:** {user.events_created} events"
                    for user in organizers
                ])
                embed.add_field(
                    name="🏆 Top Organizers",
                    value=org_text,
                    inline=True
                )
            
            # Most active attendees
            attendees = sorted(user_metrics, key=lambda u: u.events_attended, reverse=True)[:5]
            if attendees:
                att_text = "\n".join([
                    f"**{user.username}:** {user.events_attended} events ({user.attendance_rate:.1%})"
                    for user in attendees
                ])
                embed.add_field(
                    name="🎯 Most Active Attendees",
                    value=att_text,
                    inline=True
                )
            
            # Participation distribution
            score_ranges = {
                "80-100": len([u for u in user_metrics if 80 <= u.participation_score <= 100]),
                "60-79": len([u for u in user_metrics if 60 <= u.participation_score < 80]),
                "40-59": len([u for u in user_metrics if 40 <= u.participation_score < 60]),
                "0-39": len([u for u in user_metrics if 0 <= u.participation_score < 40])
            }
            
            dist_text = "\n".join([
                f"**{range_name}:** {count} users"
                for range_name, count in score_ranges.items()
                if count > 0
            ])
            
            embed.add_field(
                name="📈 Participation Distribution",
                value=dist_text,
                inline=False
            )
            
            return embed
            
        except Exception as e:
            self.logger.error("Failed to create users embed", error=str(e))
            return discord.Embed(
                title="❌ User Analytics Error",
                description="Failed to load user engagement data.",
                color=discord.Color.red()
            )
    
    async def _create_scheduling_embed(self, guild_id: str) -> discord.Embed:
        """Create scheduling recommendations embed."""
        try:
            recommendations = await self.analytics_engine.get_scheduling_recommendations(guild_id, 14)
            
            embed = discord.Embed(
                title="📅 Scheduling Recommendations",
                description="AI-powered recommendations for optimal event scheduling",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            if not recommendations:
                embed.add_field(
                    name="No Recommendations",
                    value="Not enough historical data to generate recommendations.",
                    inline=False
                )
                return embed
            
            # Top 3 recommendations
            top_recs = recommendations[:3]
            for i, rec in enumerate(top_recs, 1):
                confidence_emoji = "🟢" if rec.confidence_score > 0.7 else "🟡" if rec.confidence_score > 0.5 else "🔴"
                
                embed.add_field(
                    name=f"{confidence_emoji} Recommendation #{i}",
                    value=f"**Date:** {rec.recommended_date.strftime('%A, %B %d')}\n"
                          f"**Time:** {rec.recommended_time}\n"
                          f"**Confidence:** {rec.confidence_score:.1%}\n"
                          f"**Expected Attendance:** {rec.expected_attendance}\n"
                          f"**Reasoning:** {', '.join(rec.reasoning[:2])}",
                    inline=True
                )
            
            # Best patterns
            embed.add_field(
                name="📊 Optimal Patterns",
                value="**Best Days:** Friday, Saturday, Sunday\n"
                      "**Best Times:** 7:00 PM - 9:00 PM\n"
                      "**Optimal Notice:** 3-7 days ahead",
                inline=False
            )
            
            return embed
            
        except Exception as e:
            self.logger.error("Failed to create scheduling embed", error=str(e))
            return discord.Embed(
                title="❌ Scheduling Error",
                description="Failed to load scheduling recommendations.",
                color=discord.Color.red()
            )
    
    async def _create_summary_report_embed(self, guild_id: str) -> discord.Embed:
        """Create summary report embed."""
        try:
            # Get data for multiple periods
            metrics_30 = await self.analytics_engine.get_attendance_analytics(guild_id, 30)
            metrics_90 = await self.analytics_engine.get_attendance_analytics(guild_id, 90)
            game_metrics = await self.analytics_engine.get_game_popularity_analytics(guild_id, 90)
            user_metrics = await self.analytics_engine.get_user_engagement_metrics(guild_id, 30)
            
            embed = discord.Embed(
                title="📋 Analytics Summary Report",
                description="Comprehensive server analytics summary",
                color=discord.Color.gold(),
                timestamp=datetime.utcnow()
            )
            
            # 30-day summary
            embed.add_field(
                name="📊 Last 30 Days",
                value=f"**Events:** {metrics_30.total_events} ({metrics_30.completed_events} completed)\n"
                      f"**Attendance Rate:** {metrics_30.average_attendance_rate:.1%}\n"
                      f"**Completion Rate:** {metrics_30.completion_rate:.1%}",
                inline=True
            )
            
            # 90-day comparison
            embed.add_field(
                name="📈 90-Day Comparison",
                value=f"**Total Events:** {metrics_90.total_events}\n"
                      f"**Avg Attendance:** {metrics_90.average_attendance_rate:.1%}\n"
                      f"**Growth:** {((metrics_30.total_events / 30) / max(metrics_90.total_events / 90, 0.01) - 1) * 100:+.1f}%",
                inline=True
            )
            
            # Top insights
            insights = []
            if metrics_30.completion_rate > 0.8:
                insights.append("✅ High event completion rate")
            if metrics_30.average_attendance_rate > 0.7:
                insights.append("✅ Strong attendance rates")
            if len(game_metrics) > 10:
                insights.append("✅ Diverse game interests")
            if len(user_metrics) > 20:
                insights.append("✅ Active community")
            
            if insights:
                embed.add_field(
                    name="🎯 Key Insights",
                    value="\n".join(insights),
                    inline=False
                )
            
            embed.set_footer(text="Full detailed report available via JSON export")
            return embed
            
        except Exception as e:
            self.logger.error("Failed to create summary report embed", error=str(e))
            return discord.Embed(
                title="❌ Report Error",
                description="Failed to generate summary report.",
                color=discord.Color.red()
            )
    
    # Additional insight methods would go here...
    async def _create_attendance_insights_embed(self, guild_id: str) -> discord.Embed:
        """Create attendance optimization insights."""
        # Placeholder implementation
        return discord.Embed(
            title="🎯 Attendance Optimization Insights",
            description="AI-powered recommendations to improve event attendance",
            color=discord.Color.green()
        )
    
    async def _create_game_insights_embed(self, guild_id: str) -> discord.Embed:
        """Create game recommendation insights."""
        # Placeholder implementation
        return discord.Embed(
            title="🎮 Game Recommendation Insights",
            description="Personalized game suggestions based on community preferences",
            color=discord.Color.purple()
        )
    
    async def _create_scheduling_insights_embed(self, guild_id: str) -> discord.Embed:
        """Create scheduling optimization insights."""
        # Placeholder implementation
        return discord.Embed(
            title="📅 Scheduling Optimization Insights",
            description="Data-driven recommendations for optimal event timing",
            color=discord.Color.blue()
        )
    
    async def _create_engagement_insights_embed(self, guild_id: str) -> discord.Embed:
        """Create user engagement insights."""
        # Placeholder implementation
        return discord.Embed(
            title="👥 User Engagement Insights",
            description="Strategies to increase community participation",
            color=discord.Color.orange()
        )


def setup(bot):
    """Set up the Analytics cog."""
    bot.add_cog(AnalyticsCog(bot))