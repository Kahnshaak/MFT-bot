"""
Notifications cog for managing reminders and alerts.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import discord
from discord.ext import commands
from discord import app_commands

from core.notification_manager import NotificationManager
from core.event_bus import EventBus, EventType
from core.permission_decorators import require_permission
from core.security_manager import Permission
from models.notification import NotificationType, NotificationChannel
from models.user import User, NotificationTiming
from utils.exceptions import ValidationError, PermissionDeniedError
from utils.logging_config import get_logger, LoggerMixin


class NotificationPreferencesView(discord.ui.View):
    """View for managing notification preferences."""
    
    def __init__(self, cog: 'NotificationsCog', user_id: str, guild_id: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
    
    @discord.ui.select(
        placeholder="Choose notification channel...",
        options=[
            discord.SelectOption(
                label="Direct Messages Only",
                value="DM",
                description="Receive notifications via DM",
                emoji="📩"
            ),
            discord.SelectOption(
                label="Server Channels Only", 
                value="SERVER",
                description="Receive notifications in server channels",
                emoji="💬"
            ),
            discord.SelectOption(
                label="Both DM and Server",
                value="BOTH", 
                description="Receive notifications via both methods",
                emoji="📢"
            )
        ]
    )
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Handle channel preference selection."""
        try:
            await self.cog.update_notification_channel(
                self.user_id, self.guild_id, NotificationChannel(select.values[0])
            )
            
            channel_names = {
                "DM": "Direct Messages Only",
                "SERVER": "Server Channels Only", 
                "BOTH": "Both DM and Server"
            }
            
            await interaction.response.send_message(
                f"✅ Notification channel updated to: **{channel_names[select.values[0]]}**",
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error updating preferences: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.select(
        placeholder="Choose reminder timing...",
        options=[
            discord.SelectOption(
                label="1 Hour Before",
                value="HOUR_BEFORE",
                description="Get reminders 1 hour before events",
                emoji="⏰"
            ),
            discord.SelectOption(
                label="1 Day Before",
                value="DAY_BEFORE",
                description="Get reminders 1 day before events", 
                emoji="📅"
            ),
            discord.SelectOption(
                label="Both 1 Day and 1 Hour",
                value="BOTH_REMINDERS",
                description="Get reminders at both times",
                emoji="🔔"
            )
        ]
    )
    async def timing_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Handle timing preference selection."""
        try:
            timing_map = {
                "HOUR_BEFORE": NotificationTiming.HOUR_BEFORE,
                "DAY_BEFORE": NotificationTiming.DAY_BEFORE,
                "BOTH_REMINDERS": NotificationTiming.DAY_BEFORE  # Will set both
            }
            
            await self.cog.update_notification_timing(
                self.user_id, self.guild_id, timing_map[select.values[0]]
            )
            
            timing_names = {
                "HOUR_BEFORE": "1 Hour Before Events",
                "DAY_BEFORE": "1 Day Before Events",
                "BOTH_REMINDERS": "Both 1 Day and 1 Hour Before"
            }
            
            await interaction.response.send_message(
                f"✅ Reminder timing updated to: **{timing_names[select.values[0]]}**",
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error updating preferences: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.button(label="Toggle Event Reminders", style=discord.ButtonStyle.secondary, emoji="🎮")
    async def toggle_event_reminders(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle event reminder notifications."""
        try:
            enabled = await self.cog.toggle_event_reminders(self.user_id, self.guild_id)
            status = "enabled" if enabled else "disabled"
            
            await interaction.response.send_message(
                f"✅ Event reminders {status}",
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error updating preferences: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.button(label="Toggle Poll Notifications", style=discord.ButtonStyle.secondary, emoji="📊")
    async def toggle_poll_notifications(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle poll notification preferences."""
        try:
            enabled = await self.cog.toggle_poll_notifications(self.user_id, self.guild_id)
            status = "enabled" if enabled else "disabled"
            
            await interaction.response.send_message(
                f"✅ Poll notifications {status}",
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error updating preferences: {str(e)}",
                ephemeral=True
            )


class NotificationsCog(commands.Cog, LoggerMixin):
    """
    Cog for managing notifications and reminders.
    
    Provides commands for users to manage their notification preferences
    and for administrators to send custom notifications.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.notification_manager: Optional[NotificationManager] = None
        
    async def cog_load(self):
        """Initialize the cog."""
        # Get core components from bot
        self.notification_manager = NotificationManager(
            self.bot,
            self.bot.database,
            self.bot.event_bus
        )
        
        # Start notification manager
        await self.notification_manager.start()
        
        self.logger.info("Notifications cog loaded")
    
    async def cog_unload(self):
        """Clean up when cog is unloaded."""
        if self.notification_manager:
            await self.notification_manager.stop()
        
        self.logger.info("Notifications cog unloaded")
    
    @app_commands.command(name="notifications", description="Manage your notification preferences")
    async def notifications_preferences(self, interaction: discord.Interaction):
        """Manage notification preferences."""
        try:
            user_id = str(interaction.user.id)
            guild_id = str(interaction.guild.id)
            
            # Get current preferences
            user_data = await self.bot.database.users.find_one({
                "user_id": user_id,
                "guild_id": guild_id
            })
            
            if user_data:
                user = User(**user_data)
                prefs = user.notification_preferences
            else:
                # Create default preferences
                from models.user import NotificationPreferences
                prefs = NotificationPreferences()
            
            # Create embed showing current preferences
            embed = discord.Embed(
                title="🔔 Notification Preferences",
                description="Manage how and when you receive notifications",
                color=0x00ff00
            )
            
            # Channel preference
            channel_names = {
                NotificationChannel.DM: "Direct Messages Only",
                NotificationChannel.SERVER: "Server Channels Only",
                NotificationChannel.BOTH: "Both DM and Server"
            }
            embed.add_field(
                name="📱 Delivery Channel",
                value=channel_names.get(prefs.channel, "Both DM and Server"),
                inline=True
            )
            
            # Timing preference
            timing_names = {
                NotificationTiming.HOUR_BEFORE: "1 Hour Before",
                NotificationTiming.DAY_BEFORE: "1 Day Before",
                NotificationTiming.IMMEDIATE: "Immediately"
            }
            embed.add_field(
                name="⏰ Reminder Timing",
                value=timing_names.get(prefs.reminder_timing, "1 Day Before"),
                inline=True
            )
            
            # Toggle states
            embed.add_field(
                name="🎮 Event Reminders",
                value="✅ Enabled" if prefs.event_reminders else "❌ Disabled",
                inline=True
            )
            
            embed.add_field(
                name="📊 Poll Notifications",
                value="✅ Enabled" if prefs.poll_notifications else "❌ Disabled",
                inline=True
            )
            
            embed.add_field(
                name="🎯 Game Pings",
                value="✅ Enabled" if prefs.game_pings else "❌ Disabled",
                inline=True
            )
            
            # Quiet hours
            if prefs.quiet_hours_start and prefs.quiet_hours_end:
                quiet_hours = f"{prefs.quiet_hours_start.strftime('%H:%M')} - {prefs.quiet_hours_end.strftime('%H:%M')}"
            else:
                quiet_hours = "Not set"
            
            embed.add_field(
                name="🌙 Quiet Hours",
                value=quiet_hours,
                inline=True
            )
            
            embed.set_footer(text="Use the buttons below to update your preferences")
            
            # Create view with preference controls
            view = NotificationPreferencesView(self, user_id, guild_id)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in notifications command: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while loading your preferences.",
                ephemeral=True
            )
    
    @app_commands.command(name="test-notification", description="Send a test notification to yourself")
    async def test_notification(self, interaction: discord.Interaction):
        """Send a test notification."""
        try:
            user_id = str(interaction.user.id)
            guild_id = str(interaction.guild.id)
            
            context_data = {
                "event_title": "Test Game Night",
                "event_date": "Tomorrow",
                "event_time": "8:00 PM",
                "selected_game": "Test Game"
            }
            
            success = await self.notification_manager.send_immediate_notification(
                notification_type=NotificationType.EVENT_REMINDER,
                guild_id=guild_id,
                recipient_user_ids=[user_id],
                context_data=context_data
            )
            
            if success:
                await interaction.response.send_message(
                    "✅ Test notification sent! Check your DMs and/or the server channel.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ Failed to send test notification.",
                    ephemeral=True
                )
                
        except Exception as e:
            self.logger.error(f"Error sending test notification: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while sending the test notification.",
                ephemeral=True
            )
    
    @app_commands.command(name="notification-stats", description="View notification statistics")
    @require_permission(Permission.MANAGE_EVENTS)
    async def notification_stats(self, interaction: discord.Interaction):
        """View notification statistics (admin only)."""
        try:
            guild_id = str(interaction.guild.id)
            
            # Get notification statistics from database
            total_notifications = await self.bot.database.notifications.count_documents({
                "guild_id": guild_id
            })
            
            sent_notifications = await self.bot.database.notifications.count_documents({
                "guild_id": guild_id,
                "status": "SENT"
            })
            
            failed_notifications = await self.bot.database.notifications.count_documents({
                "guild_id": guild_id,
                "status": "FAILED"
            })
            
            scheduled_notifications = await self.bot.database.notifications.count_documents({
                "guild_id": guild_id,
                "status": "SCHEDULED"
            })
            
            # Calculate success rate
            success_rate = (sent_notifications / total_notifications * 100) if total_notifications > 0 else 0
            
            embed = discord.Embed(
                title="📊 Notification Statistics",
                description="Server notification delivery statistics",
                color=0x0099ff
            )
            
            embed.add_field(
                name="📈 Total Notifications",
                value=f"{total_notifications:,}",
                inline=True
            )
            
            embed.add_field(
                name="✅ Successfully Sent",
                value=f"{sent_notifications:,}",
                inline=True
            )
            
            embed.add_field(
                name="❌ Failed",
                value=f"{failed_notifications:,}",
                inline=True
            )
            
            embed.add_field(
                name="⏰ Scheduled",
                value=f"{scheduled_notifications:,}",
                inline=True
            )
            
            embed.add_field(
                name="📊 Success Rate",
                value=f"{success_rate:.1f}%",
                inline=True
            )
            
            # Get recent notification types
            recent_types = await self.bot.database.notifications.aggregate([
                {"$match": {"guild_id": guild_id}},
                {"$group": {"_id": "$notification_type", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 5}
            ]).to_list(length=5)
            
            if recent_types:
                type_summary = "\n".join([
                    f"• {item['_id'].replace('_', ' ').title()}: {item['count']}"
                    for item in recent_types
                ])
                embed.add_field(
                    name="📋 Notification Types",
                    value=type_summary,
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error getting notification stats: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while retrieving statistics.",
                ephemeral=True
            )
    
    async def update_notification_channel(
        self, 
        user_id: str, 
        guild_id: str, 
        channel: NotificationChannel
    ):
        """Update user's notification channel preference."""
        await self.bot.database.users.update_one(
            {"user_id": user_id, "guild_id": guild_id},
            {
                "$set": {
                    "notification_preferences.channel": channel.value,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        
        # Emit event
        await self.bot.event_bus.emit(
            EventType.USER_PREFERENCES_UPDATED,
            {
                "user_id": user_id,
                "preference_type": "notification_channel",
                "new_value": channel.value
            },
            source="notifications_cog",
            guild_id=guild_id,
            user_id=user_id
        )
    
    async def update_notification_timing(
        self, 
        user_id: str, 
        guild_id: str, 
        timing: NotificationTiming
    ):
        """Update user's notification timing preference."""
        await self.bot.database.users.update_one(
            {"user_id": user_id, "guild_id": guild_id},
            {
                "$set": {
                    "notification_preferences.reminder_timing": timing.value,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        
        # Emit event
        await self.bot.event_bus.emit(
            EventType.USER_PREFERENCES_UPDATED,
            {
                "user_id": user_id,
                "preference_type": "reminder_timing",
                "new_value": timing.value
            },
            source="notifications_cog",
            guild_id=guild_id,
            user_id=user_id
        )
    
    async def toggle_event_reminders(self, user_id: str, guild_id: str) -> bool:
        """Toggle event reminder notifications. Returns new state."""
        # Get current state
        user_data = await self.bot.database.users.find_one({
            "user_id": user_id,
            "guild_id": guild_id
        })
        
        current_state = True  # Default enabled
        if user_data and "notification_preferences" in user_data:
            current_state = user_data["notification_preferences"].get("event_reminders", True)
        
        new_state = not current_state
        
        await self.bot.database.users.update_one(
            {"user_id": user_id, "guild_id": guild_id},
            {
                "$set": {
                    "notification_preferences.event_reminders": new_state,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        
        # Emit event
        await self.bot.event_bus.emit(
            EventType.USER_PREFERENCES_UPDATED,
            {
                "user_id": user_id,
                "preference_type": "event_reminders",
                "new_value": new_state
            },
            source="notifications_cog",
            guild_id=guild_id,
            user_id=user_id
        )
        
        return new_state
    
    async def toggle_poll_notifications(self, user_id: str, guild_id: str) -> bool:
        """Toggle poll notifications. Returns new state."""
        # Get current state
        user_data = await self.bot.database.users.find_one({
            "user_id": user_id,
            "guild_id": guild_id
        })
        
        current_state = True  # Default enabled
        if user_data and "notification_preferences" in user_data:
            current_state = user_data["notification_preferences"].get("poll_notifications", True)
        
        new_state = not current_state
        
        await self.bot.database.users.update_one(
            {"user_id": user_id, "guild_id": guild_id},
            {
                "$set": {
                    "notification_preferences.poll_notifications": new_state,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        
        # Emit event
        await self.bot.event_bus.emit(
            EventType.USER_PREFERENCES_UPDATED,
            {
                "user_id": user_id,
                "preference_type": "poll_notifications",
                "new_value": new_state
            },
            source="notifications_cog",
            guild_id=guild_id,
            user_id=user_id
        )
        
        return new_state


async def setup(bot):
    """Set up the cog."""
    await bot.add_cog(NotificationsCog(bot))