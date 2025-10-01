"""
Administrative commands and controls for server management.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import discord
from discord.ext import commands

from core.security_manager import Permission, SecurityManager
from core.audit_logger import AuditLogger, AuditEventType
from core.permission_decorators import require_permission, rate_limit
from core.health_monitor import HealthMonitor, HealthStatus
from models.guild import GuildConfig, PermissionLevel, NotificationChannelType, RoleMapping
from database.manager import DatabaseManager
from utils.logging_config import get_logger, LoggerMixin
from utils.exceptions import PermissionDeniedError, ValidationError, GameNightBotException


class AdminCog(commands.Cog, LoggerMixin):
    """Administrative commands and server management."""
    
    def __init__(self, bot):
        self.bot = bot
        self.database: DatabaseManager = bot.database
        self.security: SecurityManager = bot.security
        self.audit_logger: AuditLogger = bot.audit_logger
        self.health_monitor: HealthMonitor = bot.health_monitor
        
        # Maintenance mode tracking
        self._maintenance_guilds: set = set()
    
    @discord.slash_command(
        name="admin",
        description="Administrative commands for server management"
    )
    @require_permission(Permission.CONFIGURE_BOT)
    @rate_limit(max_requests=10, window_seconds=300, per_user=True)
    async def admin_command(
        self,
        ctx: discord.ApplicationContext,
        action: discord.Option(
            str,
            description="Administrative action to perform",
            choices=[
                discord.OptionChoice(name="config", value="config"),
                discord.OptionChoice(name="roles", value="roles"),
                discord.OptionChoice(name="stats", value="stats"),
                discord.OptionChoice(name="health", value="health"),
                discord.OptionChoice(name="maintenance", value="maintenance"),
                discord.OptionChoice(name="backup", value="backup")
            ]
        ),
        target: discord.Option(
            str,
            description="Target for the action (role, channel, user, etc.)",
            required=False,
            default=None
        ) = None,
        value: discord.Option(
            str,
            description="Value or setting to apply",
            required=False,
            default=None
        ) = None
    ):
        """Main administrative command dispatcher."""
        await ctx.defer(ephemeral=True)
        
        try:
            if action == "config":
                await self._handle_config_command(ctx, target, value)
            elif action == "roles":
                await self._handle_roles_command(ctx, target, value)
            elif action == "stats":
                await self._handle_stats_command(ctx, target)
            elif action == "health":
                await self._handle_health_command(ctx, target)
            elif action == "maintenance":
                await self._handle_maintenance_command(ctx, target, value)
            elif action == "backup":
                await self._handle_backup_command(ctx, target)
            else:
                await ctx.followup.send("❌ Unknown administrative action.", ephemeral=True)
                
        except PermissionDeniedError as e:
            await ctx.followup.send(f"❌ {e.user_message}", ephemeral=True)
        except ValidationError as e:
            await ctx.followup.send(f"❌ {e.user_message}", ephemeral=True)
        except Exception as e:
            self.logger.error(
                "Admin command error",
                action=action,
                target=target,
                value=value,
                user_id=ctx.user.id,
                guild_id=ctx.guild.id,
                error=str(e),
                exc_info=True
            )
            await ctx.followup.send(
                "❌ An error occurred while processing the administrative command.",
                ephemeral=True
            )
    
    async def _handle_config_command(
        self,
        ctx: discord.ApplicationContext,
        target: Optional[str],
        value: Optional[str]
    ):
        """Handle server configuration commands."""
        guild_config = await self._get_guild_config(ctx.guild.id)
        
        if not target:
            # Show current configuration
            embed = await self._create_config_embed(guild_config)
            view = ConfigView(self, guild_config, ctx.user.id)
            await ctx.followup.send(embed=embed, view=view, ephemeral=True)
            return
        
        # Handle specific configuration changes
        if target == "timezone":
            if not value:
                await ctx.followup.send(
                    "❌ Please specify a timezone (e.g., 'America/New_York', 'UTC').",
                    ephemeral=True
                )
                return
            
            try:
                guild_config.event_defaults.default_timezone = value
                await self._save_guild_config(guild_config)
                
                await self.audit_logger.log_event(
                    event_type=AuditEventType.BOT_CONFIG_CHANGED,
                    action=f"Changed default timezone to {value}",
                    user_id=str(ctx.user.id),
                    guild_id=str(ctx.guild.id),
                    details={"setting": "default_timezone", "new_value": value}
                )
                
                await ctx.followup.send(
                    f"✅ Default timezone updated to `{value}`.",
                    ephemeral=True
                )
                
            except Exception as e:
                await ctx.followup.send(
                    f"❌ Invalid timezone: {value}",
                    ephemeral=True
                )
        
        elif target == "features":
            # Show feature toggle interface
            embed = await self._create_features_embed(guild_config)
            view = FeaturesView(self, guild_config, ctx.user.id)
            await ctx.followup.send(embed=embed, view=view, ephemeral=True)
        
        else:
            await ctx.followup.send(
                f"❌ Unknown configuration target: {target}",
                ephemeral=True
            )
    
    async def _handle_roles_command(
        self,
        ctx: discord.ApplicationContext,
        target: Optional[str],
        value: Optional[str]
    ):
        """Handle role mapping configuration."""
        guild_config = await self._get_guild_config(ctx.guild.id)
        
        if not target:
            # Show role mapping interface
            embed = await self._create_roles_embed(guild_config, ctx.guild)
            view = RolesMappingView(self, guild_config, ctx.user.id, ctx.guild)
            await ctx.followup.send(embed=embed, view=view, ephemeral=True)
            return
        
        # Handle specific role commands
        if target == "add":
            # Show role selection interface
            view = AddRoleView(self, guild_config, ctx.user.id, ctx.guild)
            await ctx.followup.send(
                "Select a role to configure permissions:",
                view=view,
                ephemeral=True
            )
        
        elif target == "remove":
            if not value:
                await ctx.followup.send(
                    "❌ Please specify a role ID to remove.",
                    ephemeral=True
                )
                return
            
            if guild_config.remove_role_mapping(value):
                await self._save_guild_config(guild_config)
                
                await self.audit_logger.log_event(
                    event_type=AuditEventType.ROLE_MAPPING_CHANGED,
                    action=f"Removed role mapping for role {value}",
                    user_id=str(ctx.user.id),
                    guild_id=str(ctx.guild.id),
                    details={"role_id": value, "action": "removed"}
                )
                
                await ctx.followup.send(
                    f"✅ Removed role mapping for <@&{value}>.",
                    ephemeral=True
                )
            else:
                await ctx.followup.send(
                    f"❌ No role mapping found for <@&{value}>.",
                    ephemeral=True
                )
        
        else:
            await ctx.followup.send(
                f"❌ Unknown role command: {target}",
                ephemeral=True
            )
    
    async def _handle_stats_command(
        self,
        ctx: discord.ApplicationContext,
        target: Optional[str]
    ):
        """Handle server statistics commands."""
        guild_config = await self._get_guild_config(ctx.guild.id)
        
        if target == "detailed":
            # Show detailed statistics
            embed = await self._create_detailed_stats_embed(guild_config, ctx.guild)
        else:
            # Show basic statistics
            embed = await self._create_stats_embed(guild_config, ctx.guild)
        
        await ctx.followup.send(embed=embed, ephemeral=True)
    
    async def _handle_health_command(
        self,
        ctx: discord.ApplicationContext,
        target: Optional[str]
    ):
        """Handle health monitoring commands."""
        if target == "check":
            # Run all health checks
            await ctx.followup.send("🔍 Running health checks...", ephemeral=True)
            
            health_results = await self.health_monitor.run_all_checks()
            embed = await self._create_health_embed(health_results)
            
            await ctx.edit_original_response(content=None, embed=embed)
        
        elif target == "summary":
            # Show health summary
            health_summary = self.health_monitor.get_health_summary()
            embed = await self._create_health_summary_embed(health_summary)
            await ctx.followup.send(embed=embed, ephemeral=True)
        
        else:
            # Show current health status
            health_summary = self.health_monitor.get_health_summary()
            embed = await self._create_health_summary_embed(health_summary)
            view = HealthView(self, ctx.user.id)
            await ctx.followup.send(embed=embed, view=view, ephemeral=True)
    
    async def _handle_maintenance_command(
        self,
        ctx: discord.ApplicationContext,
        target: Optional[str],
        value: Optional[str]
    ):
        """Handle maintenance mode commands."""
        guild_config = await self._get_guild_config(ctx.guild.id)
        
        if target == "enable":
            if guild_config.maintenance_mode:
                await ctx.followup.send(
                    "⚠️ Maintenance mode is already enabled.",
                    ephemeral=True
                )
                return
            
            guild_config.enter_maintenance_mode()
            await self._save_guild_config(guild_config)
            self._maintenance_guilds.add(ctx.guild.id)
            
            await self.audit_logger.log_event(
                event_type=AuditEventType.MAINTENANCE_MODE_ENABLED,
                action="Enabled maintenance mode",
                user_id=str(ctx.user.id),
                guild_id=str(ctx.guild.id),
                details={"reason": value or "Manual activation"}
            )
            
            # Notify in configured admin channel
            await self._notify_maintenance_mode(ctx.guild, True, value)
            
            await ctx.followup.send(
                "🔧 **Maintenance mode enabled.** Bot functionality is limited.",
                ephemeral=True
            )
        
        elif target == "disable":
            if not guild_config.maintenance_mode:
                await ctx.followup.send(
                    "✅ Maintenance mode is already disabled.",
                    ephemeral=True
                )
                return
            
            guild_config.exit_maintenance_mode()
            await self._save_guild_config(guild_config)
            self._maintenance_guilds.discard(ctx.guild.id)
            
            await self.audit_logger.log_event(
                event_type=AuditEventType.MAINTENANCE_MODE_DISABLED,
                action="Disabled maintenance mode",
                user_id=str(ctx.user.id),
                guild_id=str(ctx.guild.id)
            )
            
            # Notify in configured admin channel
            await self._notify_maintenance_mode(ctx.guild, False)
            
            await ctx.followup.send(
                "✅ **Maintenance mode disabled.** Bot is fully operational.",
                ephemeral=True
            )
        
        else:
            # Show maintenance status
            status = "🔧 **Enabled**" if guild_config.maintenance_mode else "✅ **Disabled**"
            await ctx.followup.send(
                f"**Maintenance Mode Status:** {status}",
                ephemeral=True
            )
    
    async def _handle_backup_command(
        self,
        ctx: discord.ApplicationContext,
        target: Optional[str]
    ):
        """Handle backup commands."""
        if target == "create":
            await ctx.followup.send("💾 Creating backup...", ephemeral=True)
            
            try:
                backup_data = await self._create_backup(ctx.guild.id)
                guild_config = await self._get_guild_config(ctx.guild.id)
                guild_config.record_backup()
                await self._save_guild_config(guild_config)
                
                await self.audit_logger.log_event(
                    event_type=AuditEventType.BACKUP_CREATED,
                    action="Manual backup created",
                    user_id=str(ctx.user.id),
                    guild_id=str(ctx.guild.id),
                    details={"backup_size": len(str(backup_data))}
                )
                
                await ctx.edit_original_response(
                    content="✅ **Backup created successfully.**\n"
                           f"📊 Data size: {len(str(backup_data)):,} characters\n"
                           f"🕒 Created: <t:{int(time.time())}:F>"
                )
                
            except Exception as e:
                self.logger.error(
                    "Backup creation failed",
                    guild_id=ctx.guild.id,
                    user_id=ctx.user.id,
                    error=str(e),
                    exc_info=True
                )
                await ctx.edit_original_response(
                    content="❌ **Backup creation failed.** Please check logs for details."
                )
        
        else:
            # Show backup status
            guild_config = await self._get_guild_config(ctx.guild.id)
            
            if guild_config.last_backup:
                last_backup_ts = int(guild_config.last_backup.timestamp())
                backup_status = f"📅 Last backup: <t:{last_backup_ts}:R>"
            else:
                backup_status = "⚠️ No backups created yet"
            
            await ctx.followup.send(
                f"**Backup Status**\n{backup_status}",
                ephemeral=True
            )
    
    # Helper methods for AdminCog
    
    async def _get_guild_config(self, guild_id: int) -> GuildConfig:
        """Get or create guild configuration."""
        try:
            config_data = await self.database.find_document(
                "guild_configs",
                {"guild_id": str(guild_id)}
            )
            
            if config_data:
                return GuildConfig(**config_data)
            else:
                # Create default configuration
                config = GuildConfig(guild_id=str(guild_id))
                await self._save_guild_config(config)
                return config
                
        except Exception as e:
            self.logger.error(
                "Failed to get guild config",
                guild_id=guild_id,
                error=str(e)
            )
            # Return default config as fallback
            return GuildConfig(guild_id=str(guild_id))
    
    async def _save_guild_config(self, config: GuildConfig) -> None:
        """Save guild configuration to database."""
        try:
            config.validate_data()
            config.update_timestamp()
            
            await self.database.upsert_document(
                "guild_configs",
                {"guild_id": config.guild_id},
                config.model_dump()
            )
            
        except Exception as e:
            self.logger.error(
                "Failed to save guild config",
                guild_id=config.guild_id,
                error=str(e)
            )
            raise GameNightBotException("Failed to save configuration")
    
    async def _create_config_embed(self, guild_config: GuildConfig) -> discord.Embed:
        """Create configuration overview embed."""
        embed = discord.Embed(
            title="🛠️ Server Configuration",
            description="Current bot configuration for this server",
            color=discord.Color.blue()
        )
        
        # Basic settings
        embed.add_field(
            name="⚙️ Basic Settings",
            value=f"**Default Timezone:** {guild_config.event_defaults.default_timezone}\n"
                  f"**Permission Level:** {guild_config.default_permission_level.value}\n"
                  f"**Maintenance Mode:** {'🔧 Enabled' if guild_config.maintenance_mode else '✅ Disabled'}",
            inline=False
        )
        
        # Feature status
        features = guild_config.features
        enabled_features = []
        if features.events_enabled:
            enabled_features.append("Events")
        if features.recurring_events_enabled:
            enabled_features.append("Recurring")
        if features.game_pings_enabled:
            enabled_features.append("Game Pings")
        if features.analytics_enabled:
            enabled_features.append("Analytics")
        
        embed.add_field(
            name="🎛️ Enabled Features",
            value=", ".join(enabled_features) if enabled_features else "None",
            inline=True
        )
        
        # Role mappings
        embed.add_field(
            name="👥 Role Mappings",
            value=f"{len(guild_config.role_mappings)} configured",
            inline=True
        )
        
        # Notification channels
        embed.add_field(
            name="📢 Notification Channels",
            value=f"{len(guild_config.notification_channels)} configured",
            inline=True
        )
        
        # Statistics
        stats = guild_config.statistics
        embed.add_field(
            name="📊 Server Statistics",
            value=f"**Events Created:** {stats.total_events_created}\n"
                  f"**Events Completed:** {stats.total_events_completed}\n"
                  f"**Registered Users:** {stats.total_users_registered}",
            inline=False
        )
        
        # Last backup
        if guild_config.last_backup:
            backup_ts = int(guild_config.last_backup.timestamp())
            embed.add_field(
                name="💾 Last Backup",
                value=f"<t:{backup_ts}:R>",
                inline=True
            )
        
        embed.set_footer(text="Use the buttons below to configure specific settings")
        return embed
    
    async def _create_features_embed(self, guild_config: GuildConfig) -> discord.Embed:
        """Create features configuration embed."""
        embed = discord.Embed(
            title="🎛️ Feature Configuration",
            description="Enable or disable bot features for this server",
            color=discord.Color.green()
        )
        
        features = guild_config.features
        feature_list = [
            ("🎉 Events", features.events_enabled),
            ("🔄 Recurring Events", features.recurring_events_enabled),
            ("🎮 Game Pings", features.game_pings_enabled),
            ("📊 Analytics", features.analytics_enabled),
            ("📅 Discord Events Integration", features.discord_events_integration),
            ("📋 User Profiles", features.user_profiles_enabled),
            ("🌐 Web Dashboard", features.web_dashboard_enabled),
            ("📤 Calendar Export", features.calendar_export_enabled)
        ]
        
        enabled_text = ""
        disabled_text = ""
        
        for name, enabled in feature_list:
            if enabled:
                enabled_text += f"✅ {name}\n"
            else:
                disabled_text += f"❌ {name}\n"
        
        if enabled_text:
            embed.add_field(name="Enabled Features", value=enabled_text, inline=True)
        
        if disabled_text:
            embed.add_field(name="Disabled Features", value=disabled_text, inline=True)
        
        embed.set_footer(text="Click the buttons below to toggle features")
        return embed
    
    async def _create_roles_embed(self, guild_config: GuildConfig, guild: discord.Guild) -> discord.Embed:
        """Create role mappings embed."""
        embed = discord.Embed(
            title="👥 Role Permission Mappings",
            description="Configure which Discord roles have bot permissions",
            color=discord.Color.purple()
        )
        
        if not guild_config.role_mappings:
            embed.add_field(
                name="No Role Mappings",
                value="No custom role permissions configured. All users have default permissions.",
                inline=False
            )
        else:
            for mapping in guild_config.role_mappings:
                role = guild.get_role(int(mapping.role_id))
                role_name = role.name if role else f"Unknown Role ({mapping.role_id})"
                
                permissions = []
                if mapping.can_create_events:
                    permissions.append("Create Events")
                if mapping.can_manage_all_events:
                    permissions.append("Manage All Events")
                if mapping.can_create_recurring:
                    permissions.append("Recurring Events")
                if mapping.can_view_analytics:
                    permissions.append("View Analytics")
                if mapping.can_manage_guild_config:
                    permissions.append("Manage Config")
                
                embed.add_field(
                    name=f"{role_name}",
                    value=f"**Level:** {mapping.permission_level.value}\n"
                          f"**Permissions:** {', '.join(permissions) if permissions else 'Basic only'}",
                    inline=True
                )
        
        embed.add_field(
            name="Default Permission Level",
            value=f"Users without specific role mappings get: **{guild_config.default_permission_level.value}**",
            inline=False
        )
        
        embed.set_footer(text="Use the buttons below to add or remove role mappings")
        return embed
    
    async def _create_channels_embed(self, guild_config: GuildConfig, guild: discord.Guild) -> discord.Embed:
        """Create notification channels embed."""
        embed = discord.Embed(
            title="📢 Notification Channels",
            description="Configure where the bot sends different types of notifications",
            color=discord.Color.orange()
        )
        
        if not guild_config.notification_channels:
            embed.add_field(
                name="No Channels Configured",
                value="Bot will use default behavior for notifications.",
                inline=False
            )
        else:
            channel_types = {}
            for channel_config in guild_config.notification_channels:
                channel = guild.get_channel(int(channel_config.channel_id))
                channel_name = f"#{channel.name}" if channel else f"Unknown ({channel_config.channel_id})"
                
                if channel_config.channel_type not in channel_types:
                    channel_types[channel_config.channel_type] = []
                
                channel_types[channel_config.channel_type].append(
                    f"{'✅' if channel_config.is_active else '❌'} {channel_name}"
                )
            
            for channel_type, channels in channel_types.items():
                embed.add_field(
                    name=f"{channel_type.value.title()} Notifications",
                    value="\n".join(channels),
                    inline=True
                )
        
        embed.set_footer(text="Use the buttons below to configure notification channels")
        return embed
    
    async def _create_defaults_embed(self, guild_config: GuildConfig) -> discord.Embed:
        """Create event defaults embed."""
        embed = discord.Embed(
            title="⚙️ Event Defaults",
            description="Default settings for new events",
            color=discord.Color.blue()
        )
        
        defaults = guild_config.event_defaults
        
        embed.add_field(
            name="🕒 Time Settings",
            value=f"**Timezone:** {defaults.default_timezone}\n"
                  f"**Duration:** {defaults.default_duration_minutes} minutes",
            inline=True
        )
        
        embed.add_field(
            name="📊 Poll Durations",
            value=f"**Date Poll:** {defaults.date_poll_duration_hours}h\n"
                  f"**Time Poll:** {defaults.time_poll_duration_hours}h\n"
                  f"**Game Poll:** {defaults.game_poll_duration_hours}h",
            inline=True
        )
        
        embed.add_field(
            name="🎮 Game Settings",
            value=f"**Max Options:** {defaults.max_game_options}\n"
                  f"**Default Games:** {len(defaults.default_games)} configured\n"
                  f"**Auto RSVP Creator:** {'Yes' if defaults.auto_rsvp_creator else 'No'}",
            inline=True
        )
        
        if defaults.default_games:
            games_text = ", ".join(defaults.default_games[:5])
            if len(defaults.default_games) > 5:
                games_text += f" (+{len(defaults.default_games) - 5} more)"
            
            embed.add_field(
                name="🎯 Default Games",
                value=games_text,
                inline=False
            )
        
        return embed
    
    async def _create_stats_embed(self, guild_config: GuildConfig, guild: discord.Guild) -> discord.Embed:
        """Create server statistics embed."""
        embed = discord.Embed(
            title="📊 Server Statistics",
            description=f"Bot usage statistics for {guild.name}",
            color=discord.Color.gold()
        )
        
        stats = guild_config.statistics
        
        # Basic stats
        embed.add_field(
            name="📈 Event Statistics",
            value=f"**Total Created:** {stats.total_events_created}\n"
                  f"**Completed:** {stats.total_events_completed}\n"
                  f"**This Month:** {stats.events_this_month}\n"
                  f"**Completion Rate:** {(stats.total_events_completed / max(stats.total_events_created, 1) * 100):.1f}%",
            inline=True
        )
        
        embed.add_field(
            name="👥 User Statistics",
            value=f"**Registered Users:** {stats.total_users_registered}\n"
                  f"**Active This Month:** {stats.active_users_this_month}\n"
                  f"**Avg Attendance:** {(stats.average_attendance_rate * 100):.1f}%\n"
                  f"**Avg RSVPs:** {stats.average_rsvp_count:.1f}",
            inline=True
        )
        
        # Popular games
        if stats.popular_games:
            top_games = sorted(stats.popular_games.items(), key=lambda x: x[1], reverse=True)[:5]
            games_text = "\n".join([f"**{game}:** {count}" for game, count in top_games])
            
            embed.add_field(
                name="🎮 Popular Games",
                value=games_text,
                inline=False
            )
        
        # Server info
        embed.add_field(
            name="🏠 Server Info",
            value=f"**Members:** {guild.member_count}\n"
                  f"**Channels:** {len(guild.channels)}\n"
                  f"**Roles:** {len(guild.roles)}",
            inline=True
        )
        
        # Last updated
        if stats.last_calculated:
            updated_ts = int(stats.last_calculated.timestamp())
            embed.add_field(
                name="🕒 Last Updated",
                value=f"<t:{updated_ts}:R>",
                inline=True
            )
        
        embed.set_footer(text="Statistics are updated automatically as events are created and completed")
        return embed
    
    async def _create_detailed_stats_embed(self, guild_config: GuildConfig, guild: discord.Guild) -> discord.Embed:
        """Create detailed statistics embed."""
        embed = await self._create_stats_embed(guild_config, guild)
        embed.title = "📊 Detailed Server Statistics"
        
        # Add more detailed information
        stats = guild_config.statistics
        
        # Activity trends (would need historical data in real implementation)
        embed.add_field(
            name="📈 Activity Trends",
            value="*Detailed trends require historical data collection*\n"
                  f"Current month activity: {stats.events_this_month} events",
            inline=False
        )
        
        # Feature usage
        features = guild_config.features
        enabled_count = sum([
            features.events_enabled,
            features.recurring_events_enabled,
            features.game_pings_enabled,
            features.analytics_enabled,
            features.discord_events_integration
        ])
        
        embed.add_field(
            name="🎛️ Feature Usage",
            value=f"**Features Enabled:** {enabled_count}/5\n"
                  f"**Role Mappings:** {len(guild_config.role_mappings)}\n"
                  f"**Notification Channels:** {len(guild_config.notification_channels)}",
            inline=True
        )
        
        return embed
    
    async def _create_health_embed(self, health_results: Dict[str, Any]) -> discord.Embed:
        """Create health check results embed."""
        overall_status = HealthStatus.HEALTHY
        if any(check.status == HealthStatus.UNHEALTHY for check in health_results.values()):
            overall_status = HealthStatus.UNHEALTHY
            color = discord.Color.red()
        elif any(check.status == HealthStatus.DEGRADED for check in health_results.values()):
            overall_status = HealthStatus.DEGRADED
            color = discord.Color.orange()
        else:
            color = discord.Color.green()
        
        embed = discord.Embed(
            title=f"🏥 Health Check Results",
            description=f"Overall Status: **{overall_status.value.upper()}**",
            color=color,
            timestamp=datetime.utcnow()
        )
        
        for name, check in health_results.items():
            status_emoji = {
                HealthStatus.HEALTHY: "✅",
                HealthStatus.DEGRADED: "⚠️",
                HealthStatus.UNHEALTHY: "❌",
                HealthStatus.UNKNOWN: "❓"
            }.get(check.status, "❓")
            
            embed.add_field(
                name=f"{status_emoji} {name.replace('_', ' ').title()}",
                value=f"**Status:** {check.status.value}\n"
                      f"**Message:** {check.message}\n"
                      f"**Duration:** {check.duration_ms:.1f}ms",
                inline=True
            )
        
        embed.set_footer(text="Health checks run automatically every minute")
        return embed
    
    async def _create_health_summary_embed(self, health_summary: Dict[str, Any]) -> discord.Embed:
        """Create health summary embed."""
        overall_status = health_summary.get("overall_status", "unknown")
        
        color_map = {
            "healthy": discord.Color.green(),
            "degraded": discord.Color.orange(),
            "unhealthy": discord.Color.red(),
            "unknown": discord.Color.grey()
        }
        
        embed = discord.Embed(
            title="🏥 System Health Summary",
            description=f"Overall Status: **{overall_status.upper()}**",
            color=color_map.get(overall_status, discord.Color.grey())
        )
        
        checks = health_summary.get("checks", {})
        
        healthy_checks = []
        degraded_checks = []
        unhealthy_checks = []
        
        for name, check_data in checks.items():
            status = check_data.get("status", "unknown")
            check_name = name.replace('_', ' ').title()
            
            if status == "healthy":
                healthy_checks.append(check_name)
            elif status == "degraded":
                degraded_checks.append(check_name)
            elif status == "unhealthy":
                unhealthy_checks.append(check_name)
        
        if healthy_checks:
            embed.add_field(
                name="✅ Healthy",
                value="\n".join(healthy_checks),
                inline=True
            )
        
        if degraded_checks:
            embed.add_field(
                name="⚠️ Degraded",
                value="\n".join(degraded_checks),
                inline=True
            )
        
        if unhealthy_checks:
            embed.add_field(
                name="❌ Unhealthy",
                value="\n".join(unhealthy_checks),
                inline=True
            )
        
        last_check = health_summary.get("last_check", 0)
        if last_check:
            embed.add_field(
                name="🕒 Last Check",
                value=f"<t:{int(last_check)}:R>",
                inline=False
            )
        
        return embed
    
    async def _notify_maintenance_mode(
        self,
        guild: discord.Guild,
        enabled: bool,
        reason: Optional[str] = None
    ) -> None:
        """Notify about maintenance mode changes."""
        try:
            guild_config = await self._get_guild_config(guild.id)
            admin_channel = guild_config.get_notification_channel(NotificationChannelType.ADMIN)
            
            if admin_channel:
                channel = guild.get_channel(int(admin_channel.channel_id))
                if channel:
                    embed = discord.Embed(
                        title="🔧 Maintenance Mode" if enabled else "✅ Maintenance Complete",
                        description="Bot functionality is limited during maintenance." if enabled else "Bot is fully operational.",
                        color=discord.Color.orange() if enabled else discord.Color.green()
                    )
                    
                    if enabled and reason:
                        embed.add_field(name="Reason", value=reason, inline=False)
                    
                    embed.timestamp = datetime.utcnow()
                    
                    await channel.send(embed=embed)
        
        except Exception as e:
            self.logger.error(
                "Failed to notify maintenance mode change",
                guild_id=guild.id,
                enabled=enabled,
                error=str(e)
            )
    
    async def _create_backup(self, guild_id: int) -> Dict[str, Any]:
        """Create a backup of guild data."""
        try:
            backup_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "guild_id": str(guild_id),
                "version": "1.0"
            }
            
            # Backup guild configuration
            guild_config = await self._get_guild_config(guild_id)
            backup_data["guild_config"] = guild_config.model_dump()
            
            # Backup events
            events = await self.database.find_documents(
                "events",
                {"guild_id": str(guild_id)}
            )
            backup_data["events"] = events
            
            # Backup user profiles
            users = await self.database.find_documents(
                "users",
                {"guild_id": str(guild_id)}
            )
            backup_data["users"] = users
            
            # Backup recurring schedules
            recurring = await self.database.find_documents(
                "recurring_schedules",
                {"guild_id": str(guild_id)}
            )
            backup_data["recurring_schedules"] = recurring
            
            # Backup game interests
            game_interests = await self.database.find_documents(
                "game_interests",
                {"guild_id": str(guild_id)}
            )
            backup_data["game_interests"] = game_interests
            
            self.logger.info(
                "Backup created successfully",
                guild_id=guild_id,
                data_size=len(str(backup_data))
            )
            
            return backup_data
            
        except Exception as e:
            self.logger.error(
                "Backup creation failed",
                guild_id=guild_id,
                error=str(e)
            )
            raise GameNightBotException(f"Backup creation failed: {str(e)}")
    
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Initialize configuration when bot joins a guild."""
        try:
            # Create default guild configuration
            config = GuildConfig(
                guild_id=str(guild.id),
                guild_name=guild.name
            )
            await self._save_guild_config(config)
            
            self.logger.info(
                "Initialized configuration for new guild",
                guild_id=guild.id,
                guild_name=guild.name
            )
            
        except Exception as e:
            self.logger.error(
                "Failed to initialize guild configuration",
                guild_id=guild.id,
                error=str(e)
            )
    
    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        """Update guild configuration when guild is updated."""
        if before.name != after.name:
            try:
                guild_config = await self._get_guild_config(after.id)
                guild_config.guild_name = after.name
                await self._save_guild_config(guild_config)
                
                self.logger.info(
                    "Updated guild name in configuration",
                    guild_id=after.id,
                    old_name=before.name,
                    new_name=after.name
                )
                
            except Exception as e:
                self.logger.error(
                    "Failed to update guild name",
                    guild_id=after.id,
                    error=str(e)
                )


class ConfigView(discord.ui.View):
    """Interactive view for server configuration."""
    
    def __init__(self, cog: AdminCog, guild_config: GuildConfig, user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_config = guild_config
        self.user_id = user_id
    
    async def interaction_check(self, ctx: discord.ApplicationContext) -> bool:
        return ctx.user.id == self.user_id
    
    @discord.ui.button(label="Features", style=discord.ButtonStyle.primary, emoji="🎛️")
    async def features_button(self, ctx: discord.ApplicationContext, button: discord.ui.Button):
        embed = await self.cog._create_features_embed(self.guild_config)
        view = FeaturesView(self.cog, self.guild_config, self.user_id)
        await ctx.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="Channels", style=discord.ButtonStyle.secondary, emoji="📢")
    async def channels_button(self, ctx: discord.ApplicationContext, button: discord.ui.Button):
        embed = await self.cog._create_channels_embed(self.guild_config, ctx.guild)
        view = ChannelsView(self.cog, self.guild_config, self.user_id, ctx.guild)
        await ctx.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="Defaults", style=discord.ButtonStyle.secondary, emoji="⚙️")
    async def defaults_button(self, ctx: discord.ApplicationContext, button: discord.ui.Button):
        embed = await self.cog._create_defaults_embed(self.guild_config)
        await ctx.response.edit_message(embed=embed, view=self)


class FeaturesView(discord.ui.View):
    """Interactive view for feature toggles."""
    
    def __init__(self, cog: AdminCog, guild_config: GuildConfig, user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_config = guild_config
        self.user_id = user_id
        self._update_buttons()
    
    def _update_buttons(self):
        """Update button states based on current feature flags."""
        self.clear_items()
        
        features = [
            ("events_enabled", "Events", "🎉"),
            ("recurring_events_enabled", "Recurring", "🔄"),
            ("game_pings_enabled", "Game Pings", "🎮"),
            ("analytics_enabled", "Analytics", "📊"),
            ("discord_events_integration", "Discord Events", "📅")
        ]
        
        for feature_name, label, emoji in features:
            enabled = getattr(self.guild_config.features, feature_name)
            style = discord.ButtonStyle.success if enabled else discord.ButtonStyle.danger
            button = discord.ui.Button(
                label=f"{label}: {'ON' if enabled else 'OFF'}",
                style=style,
                emoji=emoji,
                custom_id=feature_name
            )
            button.callback = self._create_toggle_callback(feature_name)
            self.add_item(button)
        
        # Add back button
        back_button = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary, emoji="⬅️")
        back_button.callback = self._back_callback
        self.add_item(back_button)
    
    def _create_toggle_callback(self, feature_name: str):
        async def callback(ctx: discord.ApplicationContext):
            current_value = getattr(self.guild_config.features, feature_name)
            new_value = not current_value
            setattr(self.guild_config.features, feature_name, new_value)
            
            await self.cog._save_guild_config(self.guild_config)
            
            await self.cog.audit_logger.log_event(
                event_type=AuditEventType.BOT_CONFIG_CHANGED,
                action=f"{'Enabled' if new_value else 'Disabled'} feature: {feature_name}",
                user_id=str(ctx.user.id),
                guild_id=str(ctx.guild.id),
                details={"feature": feature_name, "enabled": new_value}
            )
            
            self._update_buttons()
            embed = await self.cog._create_features_embed(self.guild_config)
            await ctx.response.edit_message(embed=embed, view=self)
        
        return callback
    
    async def _back_callback(self, ctx: discord.ApplicationContext):
        embed = await self.cog._create_config_embed(self.guild_config)
        view = ConfigView(self.cog, self.guild_config, self.user_id)
        await ctx.response.edit_message(embed=embed, view=view)
    
    async def interaction_check(self, ctx: discord.ApplicationContext) -> bool:
        return ctx.user.id == self.user_id


class RolesMappingView(discord.ui.View):
    """Interactive view for role mapping management."""
    
    def __init__(self, cog: AdminCog, guild_config: GuildConfig, user_id: int, guild: discord.Guild):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_config = guild_config
        self.user_id = user_id
        self.guild = guild
    
    async def interaction_check(self, ctx: discord.ApplicationContext) -> bool:
        return ctx.user.id == self.user_id
    
    @discord.ui.button(label="Add Role", style=discord.ButtonStyle.success, emoji="➕")
    async def add_role_button(self, ctx: discord.ApplicationContext, button: discord.ui.Button):
        view = AddRoleView(self.cog, self.guild_config, self.user_id, self.guild)
        await ctx.response.edit_message(
            content="Select a role to configure permissions:",
            embed=None,
            view=view
        )
    
    @discord.ui.button(label="Remove Role", style=discord.ButtonStyle.danger, emoji="➖")
    async def remove_role_button(self, ctx: discord.ApplicationContext, button: discord.ui.Button):
        if not self.guild_config.role_mappings:
            await ctx.response.send_message(
                "❌ No role mappings configured.",
                ephemeral=True
            )
            return
        
        view = RemoveRoleView(self.cog, self.guild_config, self.user_id, self.guild)
        await ctx.response.edit_message(
            content="Select a role mapping to remove:",
            embed=None,
            view=view
        )


class AddRoleView(discord.ui.View):
    """View for adding role mappings."""
    
    def __init__(self, cog: AdminCog, guild_config: GuildConfig, user_id: int, guild: discord.Guild):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_config = guild_config
        self.user_id = user_id
        self.guild = guild
        
        # Add role select dropdown
        self.add_item(RoleSelect(guild_config, guild))
    
    async def interaction_check(self, ctx: discord.ApplicationContext) -> bool:
        return ctx.user.id == self.user_id


class RoleSelect(discord.ui.Select):
    """Role selection dropdown."""
    
    def __init__(self, guild_config: GuildConfig, guild: discord.Guild):
        self.guild_config = guild_config
        
        # Get roles that aren't already mapped
        mapped_role_ids = {mapping.role_id for mapping in guild_config.role_mappings}
        available_roles = [
            role for role in guild.roles
            if str(role.id) not in mapped_role_ids and not role.is_bot_managed() and role != guild.default_role
        ][:25]  # Discord limit
        
        options = [
            discord.SelectOption(
                label=role.name[:100],
                value=str(role.id),
                description=f"Members: {len(role.members)}"
            )
            for role in available_roles
        ]
        
        if not options:
            options = [discord.SelectOption(label="No roles available", value="none")]
        
        super().__init__(
            placeholder="Choose a role to configure...",
            options=options,
            disabled=len(options) == 1 and options[0].value == "none"
        )
    
    async def callback(self, ctx: discord.ApplicationContext):
        if self.values[0] == "none":
            return
        
        role_id = self.values[0]
        role = ctx.guild.get_role(int(role_id))
        
        if not role:
            await ctx.response.send_message("❌ Role not found.", ephemeral=True)
            return
        
        view = PermissionConfigView(self.guild_config, role, ctx.user.id)
        embed = discord.Embed(
            title=f"Configure Permissions: {role.name}",
            description="Select the permission level and specific permissions for this role.",
            color=role.color or discord.Color.blue()
        )
        
        await ctx.response.edit_message(embed=embed, view=view)


class PermissionConfigView(discord.ui.View):
    """View for configuring role permissions."""
    
    def __init__(self, guild_config: GuildConfig, role: discord.Role, user_id: int):
        super().__init__(timeout=300)
        self.guild_config = guild_config
        self.role = role
        self.user_id = user_id
        
        # Permission level select
        self.add_item(PermissionLevelSelect())
        
        # Individual permission toggles
        permissions = [
            ("can_create_events", "Create Events"),
            ("can_manage_own_events", "Manage Own Events"),
            ("can_manage_all_events", "Manage All Events"),
            ("can_create_recurring", "Create Recurring"),
            ("can_view_analytics", "View Analytics"),
            ("can_manage_guild_config", "Manage Config")
        ]
        
        for perm_name, label in permissions:
            button = discord.ui.Button(
                label=f"{label}: OFF",
                style=discord.ButtonStyle.danger,
                custom_id=perm_name
            )
            button.callback = self._create_permission_callback(perm_name, label)
            self.add_item(button)
        
        # Save button
        save_button = discord.ui.Button(label="Save", style=discord.ButtonStyle.success, emoji="💾")
        save_button.callback = self._save_callback
        self.add_item(save_button)
    
    def _create_permission_callback(self, perm_name: str, label: str):
        async def callback(ctx: discord.ApplicationContext):
            # Toggle button state
            button = ctx.data['custom_id']
            for item in self.children:
                if hasattr(item, 'custom_id') and item.custom_id == button:
                    current_state = "ON" in item.label
                    new_state = not current_state
                    item.label = f"{label}: {'ON' if new_state else 'OFF'}"
                    item.style = discord.ButtonStyle.success if new_state else discord.ButtonStyle.danger
                    break
            
            await ctx.response.edit_message(view=self)
        
        return callback
    
    async def _save_callback(self, ctx: discord.ApplicationContext):
        # Extract permission settings from buttons
        permissions = {}
        permission_level = PermissionLevel.MEMBER  # Default
        
        for item in self.children:
            if hasattr(item, 'custom_id') and item.custom_id:
                if item.custom_id.startswith('can_'):
                    permissions[item.custom_id] = "ON" in item.label
            elif isinstance(item, PermissionLevelSelect) and item.values:
                permission_level = PermissionLevel(item.values[0])
        
        # Create role mapping
        role_mapping = RoleMapping(
            role_id=str(self.role.id),
            permission_level=permission_level,
            **permissions
        )
        
        # Add to guild config
        self.guild_config.add_role_mapping(
            str(self.role.id),
            permission_level,
            **permissions
        )
        
        # Save to database (this would be handled by the cog)
        await ctx.response.send_message(
            f"✅ **Role mapping saved for {self.role.name}**\n"
            f"Permission Level: {permission_level.value}\n"
            f"Permissions: {', '.join(k for k, v in permissions.items() if v)}",
            ephemeral=True
        )
    
    async def interaction_check(self, ctx: discord.ApplicationContext) -> bool:
        return ctx.user.id == self.user_id


class PermissionLevelSelect(discord.ui.Select):
    """Permission level selection dropdown."""
    
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Admin",
                value=PermissionLevel.ADMIN.value,
                description="Full administrative access",
                emoji="👑"
            ),
            discord.SelectOption(
                label="Organizer",
                value=PermissionLevel.ORGANIZER.value,
                description="Can create and manage events",
                emoji="🎯"
            ),
            discord.SelectOption(
                label="Member",
                value=PermissionLevel.MEMBER.value,
                description="Basic event participation",
                emoji="👤"
            ),
            discord.SelectOption(
                label="Restricted",
                value=PermissionLevel.RESTRICTED.value,
                description="Limited access",
                emoji="🔒"
            )
        ]
        
        super().__init__(
            placeholder="Select permission level...",
            options=options
        )
    
    async def callback(self, ctx: discord.ApplicationContext):
        await ctx.response.defer()


class RemoveRoleView(discord.ui.View):
    """View for removing role mappings."""
    
    def __init__(self, cog: AdminCog, guild_config: GuildConfig, user_id: int, guild: discord.Guild):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_config = guild_config
        self.user_id = user_id
        
        # Add remove role select
        self.add_item(RemoveRoleSelect(cog, guild_config, guild))
    
    async def interaction_check(self, ctx: discord.ApplicationContext) -> bool:
        return ctx.user.id == self.user_id


class RemoveRoleSelect(discord.ui.Select):
    """Role removal selection dropdown."""
    
    def __init__(self, cog: AdminCog, guild_config: GuildConfig, guild: discord.Guild):
        self.cog = cog
        self.guild_config = guild_config
        
        options = []
        for mapping in guild_config.role_mappings:
            role = guild.get_role(int(mapping.role_id))
            role_name = role.name if role else f"Unknown Role ({mapping.role_id})"
            
            options.append(discord.SelectOption(
                label=role_name[:100],
                value=mapping.role_id,
                description=f"Level: {mapping.permission_level.value}"
            ))
        
        if not options:
            options = [discord.SelectOption(label="No mappings to remove", value="none")]
        
        super().__init__(
            placeholder="Choose a role mapping to remove...",
            options=options,
            disabled=len(options) == 1 and options[0].value == "none"
        )
    
    async def callback(self, ctx: discord.ApplicationContext):
        if self.values[0] == "none":
            return
        
        role_id = self.values[0]
        role = ctx.guild.get_role(int(role_id))
        role_name = role.name if role else f"Role {role_id}"
        
        if self.guild_config.remove_role_mapping(role_id):
            await self.cog._save_guild_config(self.guild_config)
            
            await self.cog.audit_logger.log_event(
                event_type=AuditEventType.ROLE_MAPPING_CHANGED,
                action=f"Removed role mapping for {role_name}",
                user_id=str(ctx.user.id),
                guild_id=str(ctx.guild.id),
                details={"role_id": role_id, "action": "removed"}
            )
            
            await ctx.response.send_message(
                f"✅ **Removed role mapping for {role_name}**",
                ephemeral=True
            )
        else:
            await ctx.response.send_message(
                f"❌ Failed to remove role mapping for {role_name}",
                ephemeral=True
            )


class ChannelsView(discord.ui.View):
    """View for managing notification channels."""
    
    def __init__(self, cog: AdminCog, guild_config: GuildConfig, user_id: int, guild: discord.Guild):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_config = guild_config
        self.user_id = user_id
        self.guild = guild
    
    async def interaction_check(self, ctx: discord.ApplicationContext) -> bool:
        return ctx.user.id == self.user_id
    
    @discord.ui.button(label="Add Channel", style=discord.ButtonStyle.success, emoji="➕")
    async def add_channel_button(self, ctx: discord.ApplicationContext, button: discord.ui.Button):
        view = AddChannelView(self.cog, self.guild_config, self.user_id, self.guild)
        await ctx.response.edit_message(
            content="Configure a notification channel:",
            view=view
        )


class AddChannelView(discord.ui.View):
    """View for adding notification channels."""
    
    def __init__(self, cog: AdminCog, guild_config: GuildConfig, user_id: int, guild: discord.Guild):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_config = guild_config
        self.user_id = user_id
        self.guild = guild
        
        # Add channel select and type select
        self.add_item(ChannelSelect(guild))
        self.add_item(ChannelTypeSelect())
    
    async def interaction_check(self, ctx: discord.ApplicationContext) -> bool:
        return ctx.user.id == self.user_id


class ChannelSelect(discord.ui.Select):
    """Channel selection dropdown."""
    
    def __init__(self, guild: discord.Guild):
        text_channels = [ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages][:25]
        
        options = [
            discord.SelectOption(
                label=f"#{channel.name}",
                value=str(channel.id),
                description=channel.topic[:100] if channel.topic else "No description"
            )
            for channel in text_channels
        ]
        
        if not options:
            options = [discord.SelectOption(label="No channels available", value="none")]
        
        super().__init__(
            placeholder="Select a channel...",
            options=options,
            disabled=len(options) == 1 and options[0].value == "none"
        )
    
    async def callback(self, ctx: discord.ApplicationContext):
        await ctx.response.defer()


class ChannelTypeSelect(discord.ui.Select):
    """Channel type selection dropdown."""
    
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Events",
                value=NotificationChannelType.EVENTS.value,
                description="Event creation and updates",
                emoji="🎉"
            ),
            discord.SelectOption(
                label="Polls",
                value=NotificationChannelType.POLLS.value,
                description="Poll notifications",
                emoji="📊"
            ),
            discord.SelectOption(
                label="Reminders",
                value=NotificationChannelType.REMINDERS.value,
                description="Event reminders",
                emoji="⏰"
            ),
            discord.SelectOption(
                label="Admin",
                value=NotificationChannelType.ADMIN.value,
                description="Administrative notifications",
                emoji="⚙️"
            )
        ]
        
        super().__init__(
            placeholder="Select notification type...",
            options=options
        )
    
    async def callback(self, ctx: discord.ApplicationContext):
        await ctx.response.defer()


class HealthView(discord.ui.View):
    """View for health monitoring controls."""
    
    def __init__(self, cog: AdminCog, user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
    
    async def interaction_check(self, ctx: discord.ApplicationContext) -> bool:
        return ctx.user.id == self.user_id
    
    @discord.ui.button(label="Run Checks", style=discord.ButtonStyle.primary, emoji="🔍")
    async def run_checks_button(self, ctx: discord.ApplicationContext, button: discord.ui.Button):
        await ctx.response.edit_message(content="🔍 Running health checks...", embed=None, view=None)
        
        health_results = await self.cog.health_monitor.run_all_checks()
        embed = await self.cog._create_health_embed(health_results)
        
        await ctx.edit_original_response(content=None, embed=embed, view=self)
    
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def refresh_button(self, ctx: discord.ApplicationContext, button: discord.ui.Button):
        health_summary = self.cog.health_monitor.get_health_summary()
        embed = await self.cog._create_health_summary_embed(health_summary)
        await ctx.response.edit_message(embed=embed, view=self)


async def setup(bot):
    """Set up the Admin cog."""
    await bot.add_cog(AdminCog(bot))