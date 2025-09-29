"""
Users cog for managing user profiles, preferences, and statistics.
"""

import asyncio
import json
from datetime import datetime, time, timedelta
from typing import Optional, List, Dict, Any
import pytz
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback for Python < 3.9
    from backports.zoneinfo import ZoneInfo

import discord
from discord.ext import commands
try:
    from discord import app_commands
except ImportError:
    # Fallback for older discord.py versions
    app_commands = None

from models.user import (
    User, NotificationChannel, NotificationTiming, DayOfWeek, 
    AvailabilitySlot, NotificationPreferences, GameInterest
)
from models.repositories import RepositoryManager
from models.base import ValidationMixin
from core.event_bus import EventBus, EventType
from core.permission_decorators import require_permission
from core.security_manager import Permission
from core.validation_manager import ValidationManager
from utils.exceptions import ValidationError, PermissionDeniedError, ErrorCode
from utils.logging_config import get_logger, LoggerMixin


class TimezoneModal(discord.ui.Modal):
    """Modal for setting user timezone."""
    
    def __init__(self, cog: 'UsersCog', current_timezone: str = "UTC"):
        super().__init__(title="Set Your Timezone")
        self.cog = cog
        
        self.timezone_input = discord.ui.TextInput(
            label="Timezone",
            placeholder="e.g., America/New_York, Europe/London, UTC",
            default=current_timezone,
            min_length=3,
            max_length=50,
            required=True
        )
        self.add_item(self.timezone_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle timezone setting."""
        try:
            timezone = self.timezone_input.value.strip()
            
            # Validate timezone
            try:
                ZoneInfo(timezone)
            except Exception:
                await interaction.response.send_message(
                    f"❌ Invalid timezone: `{timezone}`\n"
                    f"Please use a valid timezone like `America/New_York` or `UTC`.",
                    ephemeral=True
                )
                return
            
            # Update user timezone
            await self.cog.update_user_timezone(
                str(interaction.user.id),
                str(interaction.guild.id),
                timezone
            )
            
            await interaction.response.send_message(
                f"✅ Timezone set to **{timezone}**",
                ephemeral=True
            )
            
        except Exception as e:
            self.cog.logger.error(f"Error setting timezone: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while setting your timezone.",
                ephemeral=True
            )


class AvailabilityModal(discord.ui.Modal):
    """Modal for adding availability slot."""
    
    def __init__(self, cog: 'UsersCog'):
        super().__init__(title="Add Availability Slot")
        self.cog = cog
        
        self.day_input = discord.ui.TextInput(
            label="Day of Week",
            placeholder="Monday, Tuesday, Wednesday, etc.",
            min_length=6,
            max_length=9,
            required=True
        )
        self.add_item(self.day_input)
        
        self.start_time_input = discord.ui.TextInput(
            label="Start Time",
            placeholder="e.g., 18:00, 6:00 PM",
            min_length=4,
            max_length=8,
            required=True
        )
        self.add_item(self.start_time_input)
        
        self.end_time_input = discord.ui.TextInput(
            label="End Time",
            placeholder="e.g., 22:00, 10:00 PM",
            min_length=4,
            max_length=8,
            required=True
        )
        self.add_item(self.end_time_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle availability slot addition."""
        try:
            # Parse day
            day_str = self.day_input.value.strip().upper()
            try:
                day = DayOfWeek(day_str)
            except ValueError:
                await interaction.response.send_message(
                    f"❌ Invalid day: `{self.day_input.value}`\n"
                    f"Please use: Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday",
                    ephemeral=True
                )
                return
            
            # Parse times
            start_time = self.cog.parse_time(self.start_time_input.value)
            end_time = self.cog.parse_time(self.end_time_input.value)
            
            if not start_time or not end_time:
                await interaction.response.send_message(
                    "❌ Invalid time format. Please use formats like:\n"
                    "• 18:00 or 6:00 PM\n"
                    "• 22:30 or 10:30 PM",
                    ephemeral=True
                )
                return
            
            if start_time >= end_time:
                await interaction.response.send_message(
                    "❌ Start time must be before end time.",
                    ephemeral=True
                )
                return
            
            # Add availability slot
            success = await self.cog.add_availability_slot(
                str(interaction.user.id),
                str(interaction.guild.id),
                day,
                start_time,
                end_time
            )
            
            if success:
                await interaction.response.send_message(
                    f"✅ Added availability: **{day.value.title()}** "
                    f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ Could not add availability slot. It may overlap with an existing slot.",
                    ephemeral=True
                )
            
        except Exception as e:
            self.cog.logger.error(f"Error adding availability: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while adding availability.",
                ephemeral=True
            )


class NotificationPreferencesModal(discord.ui.Modal):
    """Modal for setting notification preferences."""
    
    def __init__(self, cog: 'UsersCog', current_prefs: NotificationPreferences):
        super().__init__(title="Notification Preferences")
        self.cog = cog
        
        self.channel_input = discord.ui.TextInput(
            label="Notification Channel (DM/SERVER/BOTH/NONE)",
            placeholder="Where to receive notifications",
            default=current_prefs.channel.value,
            min_length=2,
            max_length=6,
            required=True
        )
        self.add_item(self.channel_input)
        
        self.timing_input = discord.ui.TextInput(
            label="Reminder Timing",
            placeholder="IMMEDIATE, HOUR_BEFORE, DAY_BEFORE, WEEK_BEFORE",
            default=current_prefs.reminder_timing.value,
            min_length=9,
            max_length=15,
            required=True
        )
        self.add_item(self.timing_input)
        
        self.quiet_hours_input = discord.ui.TextInput(
            label="Quiet Hours (optional)",
            placeholder="e.g., 22:00-08:00 (24-hour format)",
            default=self._format_quiet_hours(current_prefs),
            max_length=11,
            required=False
        )
        self.add_item(self.quiet_hours_input)
    
    def _format_quiet_hours(self, prefs: NotificationPreferences) -> str:
        """Format quiet hours for display."""
        if prefs.quiet_hours_start and prefs.quiet_hours_end:
            return f"{prefs.quiet_hours_start.strftime('%H:%M')}-{prefs.quiet_hours_end.strftime('%H:%M')}"
        return ""
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle notification preferences update."""
        try:
            # Parse channel
            channel_str = self.channel_input.value.strip().upper()
            try:
                channel = NotificationChannel(channel_str)
            except ValueError:
                await interaction.response.send_message(
                    f"❌ Invalid channel: `{channel_str}`\n"
                    f"Please use: DM, SERVER, BOTH, or NONE",
                    ephemeral=True
                )
                return
            
            # Parse timing
            timing_str = self.timing_input.value.strip().upper()
            try:
                timing = NotificationTiming(timing_str)
            except ValueError:
                await interaction.response.send_message(
                    f"❌ Invalid timing: `{timing_str}`\n"
                    f"Please use: IMMEDIATE, HOUR_BEFORE, DAY_BEFORE, or WEEK_BEFORE",
                    ephemeral=True
                )
                return
            
            # Parse quiet hours
            quiet_start = None
            quiet_end = None
            if self.quiet_hours_input.value.strip():
                quiet_hours = self.quiet_hours_input.value.strip()
                if '-' in quiet_hours:
                    try:
                        start_str, end_str = quiet_hours.split('-', 1)
                        quiet_start = self.cog.parse_time(start_str.strip())
                        quiet_end = self.cog.parse_time(end_str.strip())
                        
                        if not quiet_start or not quiet_end:
                            raise ValueError("Invalid time format")
                    except Exception:
                        await interaction.response.send_message(
                            "❌ Invalid quiet hours format. Use: 22:00-08:00",
                            ephemeral=True
                        )
                        return
            
            # Update preferences
            await self.cog.update_notification_preferences(
                str(interaction.user.id),
                str(interaction.guild.id),
                channel,
                timing,
                quiet_start,
                quiet_end
            )
            
            await interaction.response.send_message(
                f"✅ Notification preferences updated!\n"
                f"• Channel: **{channel.value}**\n"
                f"• Timing: **{timing.value}**" +
                (f"\n• Quiet hours: **{quiet_hours}**" if quiet_hours else ""),
                ephemeral=True
            )
            
        except Exception as e:
            self.cog.logger.error(f"Error updating notification preferences: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while updating preferences.",
                ephemeral=True
            )


class ProfileView(discord.ui.View):
    """View for profile management."""
    
    def __init__(self, cog: 'UsersCog', user: User):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
    
    @discord.ui.button(label="Set Timezone", style=discord.ButtonStyle.primary, emoji="🌍")
    async def set_timezone(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TimezoneModal(self.cog, self.user.timezone)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Add Availability", style=discord.ButtonStyle.secondary, emoji="📅")
    async def add_availability(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AvailabilityModal(self.cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Notification Settings", style=discord.ButtonStyle.secondary, emoji="🔔")
    async def notification_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = NotificationPreferencesModal(self.cog, self.user.notification_preferences)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Export Data", style=discord.ButtonStyle.secondary, emoji="📄")
    async def export_data(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.export_user_data(interaction)


class UsersCog(commands.Cog, LoggerMixin):
    """
    Users cog for managing user profiles, preferences, and statistics.
    
    Handles user onboarding, profile management, timezone preferences,
    availability scheduling, and notification preferences.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.validation: ValidationManager = bot.validation
        self.event_bus: EventBus = bot.event_bus
        self.repositories: RepositoryManager = RepositoryManager(bot.database)
        
        # Subscribe to relevant events
        self.event_bus.subscribe(EventType.USER_JOINED_GUILD, self._on_user_joined)
        self.event_bus.subscribe(EventType.EVENT_RSVP_UPDATED, self._on_rsvp_updated)
        self.event_bus.subscribe(EventType.EVENT_COMPLETED, self._on_event_completed)
    
    async def _on_user_joined(self, event_data):
        """Handle new user joining guild."""
        try:
            user_id = event_data.data.get('user_id')
            guild_id = event_data.data.get('guild_id')
            
            if user_id and guild_id:
                # Start onboarding flow
                await self._start_onboarding_flow(user_id, guild_id)
        except Exception as e:
            self.logger.error(f"Error handling user joined event: {e}", exc_info=True)
    
    async def _on_rsvp_updated(self, event_data):
        """Handle RSVP updates for statistics."""
        try:
            user_id = event_data.data.get('user_id')
            guild_id = event_data.data.get('guild_id')
            status = event_data.data.get('status')
            
            if user_id and guild_id and status:
                await self._update_rsvp_statistics(user_id, guild_id, status)
        except Exception as e:
            self.logger.error(f"Error updating RSVP statistics: {e}", exc_info=True)
    
    async def _on_event_completed(self, event_data):
        """Handle event completion for attendance tracking."""
        try:
            event_id = event_data.data.get('event_id')
            guild_id = event_data.data.get('guild_id')
            attendees = event_data.data.get('attendees', [])
            
            if event_id and guild_id:
                await self._update_attendance_statistics(guild_id, attendees)
        except Exception as e:
            self.logger.error(f"Error updating attendance statistics: {e}", exc_info=True)
    
    async def _start_onboarding_flow(self, user_id: str, guild_id: str):
        """Start onboarding flow for new users."""
        try:
            # Get Discord user and guild
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return
            
            user = guild.get_member(int(user_id))
            if not user:
                return
            
            # Create user profile
            await self.repositories.ensure_user_profile(
                user_id, guild_id, user.display_name
            )
            
            # Send welcome message with onboarding
            embed = discord.Embed(
                title="🎮 Welcome to Game Night Bot!",
                description=(
                    f"Hi {user.mention}! I help organize game nights for your server.\n\n"
                    f"**Get Started:**\n"
                    f"• Use `/profile` to set up your profile\n"
                    f"• Set your timezone with `/preferences timezone`\n"
                    f"• Add your availability with `/preferences availability`\n"
                    f"• Configure notifications with `/preferences notifications`\n\n"
                    f"**Commands:**\n"
                    f"• `/games add <game>` - Add games you're interested in\n"
                    f"• `/games list` - See your game interests\n"
                    f"• `/profile` - View your profile and stats\n"
                ),
                color=discord.Color.green()
            )
            
            try:
                await user.send(embed=embed)
            except discord.Forbidden:
                # Can't DM user, try to find a general channel
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).send_messages:
                        await channel.send(f"{user.mention}", embed=embed)
                        break
            
            # Emit onboarding event
            await self.event_bus.emit(
                EventType.USER_ONBOARDED,
                {"user_id": user_id, "guild_id": guild_id},
                source="users_cog",
                guild_id=guild_id,
                user_id=user_id
            )
            
        except Exception as e:
            self.logger.error(f"Error in onboarding flow: {e}", exc_info=True)
    
    @commands.slash_command(name="profile", description="View and manage your profile")
    async def profile_command(self, interaction: discord.Interaction):
        """Display user profile with management options."""
        try:
            # Get or create user profile
            user = await self.repositories.ensure_user_profile(
                str(interaction.user.id),
                str(interaction.guild.id),
                interaction.user.display_name
            )
            
            # Create profile embed
            embed = self.create_profile_embed(user, interaction.user)
            
            # Create management view
            view = ProfileView(self, user)
            
            await interaction.response.send_message(
                embed=embed,
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error displaying profile: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while loading your profile.",
                ephemeral=True
            )
    
    @commands.slash_command(name="stats", description="View your game night statistics")
    async def stats_command(self, interaction: discord.Interaction):
        """Display user statistics."""
        try:
            user = await self.repositories.users.get_by_user_and_guild(
                str(interaction.user.id),
                str(interaction.guild.id)
            )
            
            if not user:
                await interaction.response.send_message(
                    "❌ No profile found. Use `/profile` to create one.",
                    ephemeral=True
                )
                return
            
            # Create statistics embed
            embed = self.create_statistics_embed(user, interaction.user)
            
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error displaying statistics: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while loading your statistics.",
                ephemeral=True
            )
    
    @commands.slash_command(name="timezone", description="Set your timezone")
    async def set_timezone_command(self, interaction: discord.Interaction, timezone: str):
        """Set user timezone."""
        try:
            # Validate timezone
            try:
                ZoneInfo(timezone)
            except Exception:
                await interaction.response.send_message(
                    f"❌ Invalid timezone: `{timezone}`\n"
                    f"Please use a valid timezone like `America/New_York` or `UTC`.\n"
                    f"See: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
                    ephemeral=True
                )
                return
            
            # Update user timezone
            await self.update_user_timezone(
                str(interaction.user.id),
                str(interaction.guild.id),
                timezone
            )
            
            await interaction.response.send_message(
                f"✅ Timezone set to **{timezone}**",
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error setting timezone: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while setting your timezone.",
                ephemeral=True
            )
    
    @commands.slash_command(name="availability", description="Manage your weekly availability")
    async def availability_command(self, interaction: discord.Interaction):
        """Manage user availability."""
        try:
            user = await self.repositories.ensure_user_profile(
                str(interaction.user.id),
                str(interaction.guild.id),
                interaction.user.display_name
            )
            
            # Create availability embed
            embed = self.create_availability_embed(user)
            
            # Create management view
            view = AvailabilityManagementView(self, user)
            
            await interaction.response.send_message(
                embed=embed,
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error managing availability: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while loading availability.",
                ephemeral=True
            )
    
    @commands.slash_command(name="notifications", description="Configure notification preferences")
    async def notifications_command(self, interaction: discord.Interaction):
        """Configure notification preferences."""
        try:
            user = await self.repositories.ensure_user_profile(
                str(interaction.user.id),
                str(interaction.guild.id),
                interaction.user.display_name
            )
            
            modal = NotificationPreferencesModal(self, user.notification_preferences)
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            self.logger.error(f"Error configuring notifications: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while loading notification preferences.",
                ephemeral=True
            )
    
    @commands.slash_command(name="games-add", description="Add a game to your interests")
    async def add_game_command(
        self, 
        interaction: discord.Interaction, 
        game_name: str,
        interest_level: int = 5
    ):
        """Add game interest."""
        try:
            if not (1 <= interest_level <= 10):
                await interaction.response.send_message(
                    "❌ Interest level must be between 1 and 10.",
                    ephemeral=True
                )
                return
            
            # Validate and sanitize game name
            game_name = ValidationMixin.sanitize_text(game_name, 100)
            if not game_name:
                await interaction.response.send_message(
                    "❌ Invalid game name.",
                    ephemeral=True
                )
                return
            
            # Get or create user
            user = await self.repositories.ensure_user_profile(
                str(interaction.user.id),
                str(interaction.guild.id),
                interaction.user.display_name
            )
            
            # Add game interest
            success = user.add_game_interest(game_name, interest_level)
            
            if success:
                # Update in database
                await self.repositories.users.update(str(user.id), user)
                
                await interaction.response.send_message(
                    f"✅ Added **{game_name}** to your interests (level {interest_level}/10)",
                    ephemeral=True
                )
                
                # Emit event
                await self.event_bus.emit(
                    EventType.USER_GAME_INTEREST_ADDED,
                    {
                        "user_id": str(interaction.user.id),
                        "guild_id": str(interaction.guild.id),
                        "game_name": game_name,
                        "interest_level": interest_level
                    },
                    source="users_cog",
                    guild_id=str(interaction.guild.id),
                    user_id=str(interaction.user.id)
                )
            else:
                await interaction.response.send_message(
                    f"❌ You're already interested in **{game_name}**. Use `/games list` to see your interests.",
                    ephemeral=True
                )
            
        except Exception as e:
            self.logger.error(f"Error adding game interest: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while adding the game.",
                ephemeral=True
            )
    
    @commands.slash_command(name="games-remove", description="Remove a game from your interests")
    async def remove_game_command(self, interaction: discord.Interaction, game_name: str):
        """Remove game interest."""
        try:
            user = await self.repositories.users.get_by_user_and_guild(
                str(interaction.user.id),
                str(interaction.guild.id)
            )
            
            if not user:
                await interaction.response.send_message(
                    "❌ No profile found. Use `/profile` to create one.",
                    ephemeral=True
                )
                return
            
            # Remove game interest
            success = user.remove_game_interest(game_name)
            
            if success:
                # Update in database
                await self.repositories.users.update(str(user.id), user)
                
                await interaction.response.send_message(
                    f"✅ Removed **{game_name}** from your interests",
                    ephemeral=True
                )
                
                # Emit event
                await self.event_bus.emit(
                    EventType.USER_GAME_INTEREST_REMOVED,
                    {
                        "user_id": str(interaction.user.id),
                        "guild_id": str(interaction.guild.id),
                        "game_name": game_name
                    },
                    source="users_cog",
                    guild_id=str(interaction.guild.id),
                    user_id=str(interaction.user.id)
                )
            else:
                await interaction.response.send_message(
                    f"❌ **{game_name}** not found in your interests.",
                    ephemeral=True
                )
            
        except Exception as e:
            self.logger.error(f"Error removing game interest: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while removing the game.",
                ephemeral=True
            )
    
    @commands.slash_command(name="games-list", description="List your game interests")
    async def list_games_command(self, interaction: discord.Interaction):
        """List user's game interests."""
        try:
            user = await self.repositories.users.get_by_user_and_guild(
                str(interaction.user.id),
                str(interaction.guild.id)
            )
            
            if not user or not user.game_interests:
                await interaction.response.send_message(
                    "❌ No game interests found. Use `/games add <game>` to add some!",
                    ephemeral=True
                )
                return
            
            # Create games embed
            embed = self.create_games_embed(user, interaction.user)
            
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error listing games: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while loading your games.",
                ephemeral=True
            )
    
    async def export_user_data(self, interaction: discord.Interaction):
        """Export user data for GDPR compliance."""
        try:
            user = await self.repositories.users.get_by_user_and_guild(
                str(interaction.user.id),
                str(interaction.guild.id)
            )
            
            if not user:
                await interaction.response.send_message(
                    "❌ No profile found.",
                    ephemeral=True
                )
                return
            
            # Mark data export as requested
            user.request_data_export()
            await self.repositories.users.update(str(user.id), user)
            
            # Get export data
            export_data = user.get_export_data()
            
            # Create JSON file
            json_data = json.dumps(export_data, indent=2, default=str)
            
            # Create file
            file = discord.File(
                fp=discord.utils.StringIO(json_data),
                filename=f"gamenight_data_{interaction.user.id}_{datetime.utcnow().strftime('%Y%m%d')}.json"
            )
            
            await interaction.response.send_message(
                "📄 Here's your exported data:",
                file=file,
                ephemeral=True
            )
            
            # Emit event
            await self.event_bus.emit(
                EventType.USER_DATA_EXPORTED,
                {
                    "user_id": str(interaction.user.id),
                    "guild_id": str(interaction.guild.id),
                    "export_timestamp": datetime.utcnow().isoformat()
                },
                source="users_cog",
                guild_id=str(interaction.guild.id),
                user_id=str(interaction.user.id)
            )
            
        except Exception as e:
            self.logger.error(f"Error exporting user data: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while exporting your data.",
                ephemeral=True
            )
    
    # Helper methods
    
    def create_profile_embed(self, user: User, discord_user: discord.Member) -> discord.Embed:
        """Create profile embed."""
        embed = discord.Embed(
            title=f"🎮 {discord_user.display_name}'s Profile",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🌍 Timezone",
            value=user.timezone,
            inline=True
        )
        
        embed.add_field(
            name="🎯 Game Interests",
            value=str(len(user.game_interests)),
            inline=True
        )
        
        embed.add_field(
            name="📅 Availability Slots",
            value=str(len(user.availability)),
            inline=True
        )
        
        # Notification preferences
        prefs = user.notification_preferences
        embed.add_field(
            name="🔔 Notifications",
            value=f"Channel: {prefs.channel.value}\nTiming: {prefs.reminder_timing.value}",
            inline=False
        )
        
        # Statistics
        stats = user.statistics
        embed.add_field(
            name="📊 Statistics",
            value=(
                f"Events Created: {stats.events_created}\n"
                f"Events Attended: {stats.events_attended}\n"
                f"Attendance Rate: {stats.attendance_rate:.1%}"
            ),
            inline=True
        )
        
        # Availability summary
        if user.availability:
            available_days = sorted(list(user.get_available_days()), key=lambda d: list(DayOfWeek).index(d))
            days_str = ", ".join(day.value.title() for day in available_days)
            embed.add_field(
                name="📅 Available Days",
                value=days_str,
                inline=False
            )
        
        embed.set_thumbnail(url=discord_user.display_avatar.url)
        embed.timestamp = datetime.utcnow()
        
        return embed
    
    def create_statistics_embed(self, user: User, discord_user: discord.Member) -> discord.Embed:
        """Create statistics embed."""
        stats = user.statistics
        
        embed = discord.Embed(
            title=f"📊 {discord_user.display_name}'s Statistics",
            color=discord.Color.green()
        )
        
        # Event statistics
        embed.add_field(
            name="🎮 Event Participation",
            value=(
                f"**Created:** {stats.events_created}\n"
                f"**Attended:** {stats.events_attended}\n"
                f"**RSVP Yes:** {stats.events_rsvp_yes}\n"
                f"**RSVP No:** {stats.events_rsvp_no}\n"
                f"**RSVP Maybe:** {stats.events_rsvp_maybe}"
            ),
            inline=True
        )
        
        # Attendance rate
        embed.add_field(
            name="📈 Attendance Rate",
            value=f"**{stats.attendance_rate:.1%}**\n({stats.events_attended}/{stats.events_rsvp_yes})",
            inline=True
        )
        
        # Favorite games
        if stats.favorite_games:
            top_games = stats.favorite_games[:5]  # Top 5
            games_text = "\n".join(f"{i+1}. {game}" for i, game in enumerate(top_games))
            embed.add_field(
                name="🏆 Favorite Games",
                value=games_text,
                inline=False
            )
        
        # Activity timestamps
        if stats.last_event_attended:
            embed.add_field(
                name="🕒 Last Activity",
                value=(
                    f"**Last Event:** <t:{int(stats.last_event_attended.timestamp())}:R>\n"
                    f"**Last Active:** <t:{int(stats.last_active.timestamp())}:R>"
                ),
                inline=False
            )
        
        embed.set_thumbnail(url=discord_user.display_avatar.url)
        embed.timestamp = datetime.utcnow()
        
        return embed
    
    def create_availability_embed(self, user: User) -> discord.Embed:
        """Create availability embed."""
        embed = discord.Embed(
            title="📅 Your Availability",
            description="Your weekly availability schedule",
            color=discord.Color.blue()
        )
        
        if not user.availability:
            embed.add_field(
                name="No Availability Set",
                value="Use the button below to add your availability slots.",
                inline=False
            )
        else:
            # Group by day
            by_day = {}
            for slot in user.availability:
                if slot.day not in by_day:
                    by_day[slot.day] = []
                by_day[slot.day].append(slot)
            
            # Sort days
            sorted_days = sorted(by_day.keys(), key=lambda d: list(DayOfWeek).index(d))
            
            for day in sorted_days:
                slots = sorted(by_day[day], key=lambda s: s.start_time)
                slots_text = "\n".join(
                    f"{slot.start_time.strftime('%H:%M')} - {slot.end_time.strftime('%H:%M')}"
                    for slot in slots
                )
                embed.add_field(
                    name=day.value.title(),
                    value=slots_text,
                    inline=True
                )
        
        embed.add_field(
            name="🌍 Timezone",
            value=user.timezone,
            inline=False
        )
        
        return embed
    
    def create_games_embed(self, user: User, discord_user: discord.Member) -> discord.Embed:
        """Create games interests embed."""
        embed = discord.Embed(
            title=f"🎮 {discord_user.display_name}'s Game Interests",
            color=discord.Color.purple()
        )
        
        # Sort by interest level (highest first)
        sorted_games = sorted(user.game_interests, key=lambda g: g.interest_level, reverse=True)
        
        games_text = ""
        for game in sorted_games:
            notification_icon = "🔔" if game.notification_enabled else "🔕"
            games_text += f"{notification_icon} **{game.game_name}** (Level {game.interest_level}/10)\n"
        
        if games_text:
            embed.description = games_text
        else:
            embed.description = "No game interests added yet."
        
        embed.add_field(
            name="📊 Total Games",
            value=str(len(user.game_interests)),
            inline=True
        )
        
        if user.game_interests:
            avg_interest = sum(g.interest_level for g in user.game_interests) / len(user.game_interests)
            embed.add_field(
                name="📈 Average Interest",
                value=f"{avg_interest:.1f}/10",
                inline=True
            )
        
        embed.set_thumbnail(url=discord_user.display_avatar.url)
        
        return embed
    
    def parse_time(self, time_str: str) -> Optional[time]:
        """Parse time string into time object."""
        time_str = time_str.strip().upper()
        
        # Try different formats
        formats = [
            "%H:%M",      # 18:00
            "%I:%M %p",   # 6:00 PM
            "%I %p",      # 6 PM
            "%H",         # 18
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(time_str, fmt)
                return dt.time()
            except ValueError:
                continue
        
        return None
    
    async def update_user_timezone(self, user_id: str, guild_id: str, timezone: str):
        """Update user timezone."""
        user = await self.repositories.ensure_user_profile(user_id, guild_id)
        user.timezone = timezone
        user.update_timestamp()
        
        await self.repositories.users.update(str(user.id), user)
        
        # Emit event
        await self.event_bus.emit(
            EventType.USER_TIMEZONE_UPDATED,
            {
                "user_id": user_id,
                "guild_id": guild_id,
                "timezone": timezone
            },
            source="users_cog",
            guild_id=guild_id,
            user_id=user_id
        )
    
    async def add_availability_slot(
        self, 
        user_id: str, 
        guild_id: str, 
        day: DayOfWeek, 
        start_time: time, 
        end_time: time
    ) -> bool:
        """Add availability slot."""
        user = await self.repositories.ensure_user_profile(user_id, guild_id)
        
        success = user.add_availability_slot(day, start_time, end_time)
        
        if success:
            await self.repositories.users.update(str(user.id), user)
            
            # Emit event
            await self.event_bus.emit(
                EventType.USER_AVAILABILITY_UPDATED,
                {
                    "user_id": user_id,
                    "guild_id": guild_id,
                    "day": day.value,
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "action": "added"
                },
                source="users_cog",
                guild_id=guild_id,
                user_id=user_id
            )
        
        return success
    
    async def update_notification_preferences(
        self,
        user_id: str,
        guild_id: str,
        channel: NotificationChannel,
        timing: NotificationTiming,
        quiet_start: Optional[time] = None,
        quiet_end: Optional[time] = None
    ):
        """Update notification preferences."""
        user = await self.repositories.ensure_user_profile(user_id, guild_id)
        
        # Update preferences
        user.notification_preferences.channel = channel
        user.notification_preferences.reminder_timing = timing
        user.notification_preferences.quiet_hours_start = quiet_start
        user.notification_preferences.quiet_hours_end = quiet_end
        user.update_timestamp()
        
        await self.repositories.users.update(str(user.id), user)
        
        # Emit event
        await self.event_bus.emit(
            EventType.USER_PREFERENCES_UPDATED,
            {
                "user_id": user_id,
                "guild_id": guild_id,
                "preferences_type": "notifications",
                "channel": channel.value,
                "timing": timing.value
            },
            source="users_cog",
            guild_id=guild_id,
            user_id=user_id
        )
    
    async def _update_rsvp_statistics(self, user_id: str, guild_id: str, status: str):
        """Update RSVP statistics."""
        try:
            user = await self.repositories.users.get_by_user_and_guild(user_id, guild_id)
            if user:
                user.statistics.update_rsvp(status)
                await self.repositories.users.update(str(user.id), user)
        except Exception as e:
            self.logger.error(f"Error updating RSVP statistics: {e}", exc_info=True)
    
    async def _update_attendance_statistics(self, guild_id: str, attendees: List[str]):
        """Update attendance statistics for multiple users."""
        try:
            for user_id in attendees:
                user = await self.repositories.users.get_by_user_and_guild(user_id, guild_id)
                if user:
                    user.statistics.update_attendance(True)
                    await self.repositories.users.update(str(user.id), user)
        except Exception as e:
            self.logger.error(f"Error updating attendance statistics: {e}", exc_info=True)


class AvailabilityManagementView(discord.ui.View):
    """View for managing availability slots."""
    
    def __init__(self, cog: UsersCog, user: User):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
    
    @discord.ui.button(label="Add Slot", style=discord.ButtonStyle.primary, emoji="➕")
    async def add_slot(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AvailabilityModal(self.cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Remove Slot", style=discord.ButtonStyle.danger, emoji="➖")
    async def remove_slot(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.user.availability:
            await interaction.response.send_message(
                "❌ No availability slots to remove.",
                ephemeral=True
            )
            return
        
        # Create dropdown with current slots
        options = []
        for i, slot in enumerate(self.user.availability):
            options.append(discord.SelectOption(
                label=f"{slot.day.value.title()} {slot.start_time.strftime('%H:%M')}-{slot.end_time.strftime('%H:%M')}",
                value=str(i),
                description=f"Remove this availability slot"
            ))
        
        if len(options) > 25:
            options = options[:25]  # Discord limit
        
        select = RemoveAvailabilitySelect(self.cog, self.user, options)
        view = discord.ui.View()
        view.add_item(select)
        
        await interaction.response.send_message(
            "Select a slot to remove:",
            view=view,
            ephemeral=True
        )


class RemoveAvailabilitySelect(discord.ui.Select):
    """Select for removing availability slots."""
    
    def __init__(self, cog: UsersCog, user: User, options: List[discord.SelectOption]):
        super().__init__(placeholder="Choose slot to remove...", options=options)
        self.cog = cog
        self.user = user
    
    async def callback(self, interaction: discord.Interaction):
        try:
            slot_index = int(self.values[0])
            
            if 0 <= slot_index < len(self.user.availability):
                slot = self.user.availability[slot_index]
                
                # Remove slot
                success = self.user.remove_availability_slot(slot.day, slot.start_time)
                
                if success:
                    # Update in database
                    await self.cog.repositories.users.update(str(self.user.id), self.user)
                    
                    await interaction.response.edit_message(
                        content=f"✅ Removed availability slot: **{slot.day.value.title()}** "
                               f"{slot.start_time.strftime('%H:%M')}-{slot.end_time.strftime('%H:%M')}",
                        view=None
                    )
                    
                    # Emit event
                    await self.cog.event_bus.emit(
                        EventType.USER_AVAILABILITY_UPDATED,
                        {
                            "user_id": str(interaction.user.id),
                            "guild_id": str(interaction.guild.id),
                            "day": slot.day.value,
                            "start_time": slot.start_time.isoformat(),
                            "end_time": slot.end_time.isoformat(),
                            "action": "removed"
                        },
                        source="users_cog",
                        guild_id=str(interaction.guild.id),
                        user_id=str(interaction.user.id)
                    )
                else:
                    await interaction.response.edit_message(
                        content="❌ Failed to remove availability slot.",
                        view=None
                    )
            else:
                await interaction.response.edit_message(
                    content="❌ Invalid slot selection.",
                    view=None
                )
                
        except Exception as e:
            self.cog.logger.error(f"Error removing availability slot: {e}", exc_info=True)
            await interaction.response.edit_message(
                content="❌ An error occurred while removing the slot.",
                view=None
            )


async def setup(bot):
    """Set up the Users cog."""
    await bot.add_cog(UsersCog(bot))