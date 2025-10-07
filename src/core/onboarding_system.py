"""
Enhanced user onboarding system with interactive tutorials and progress tracking.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from enum import Enum
import uuid

import discord
from discord.ext import commands

from core.event_bus import EventBus, EventType
from core.accessibility_enhancements import AccessibleEmbed, AccessibleButton, accessibility_manager
from utils.logging_config import get_logger


class OnboardingStep(Enum):
    """Onboarding steps."""
    WELCOME = "welcome"
    PROFILE_SETUP = "profile_setup"
    TIMEZONE_SETUP = "timezone_setup"
    GAME_INTERESTS = "game_interests"
    AVAILABILITY = "availability"
    NOTIFICATIONS = "notifications"
    FIRST_EVENT = "first_event"
    COMPLETION = "completion"


class OnboardingProgress:
    """Tracks user onboarding progress."""
    
    def __init__(self, user_id: str, guild_id: str):
        self.user_id = user_id
        self.guild_id = guild_id
        self.current_step = OnboardingStep.WELCOME
        self.completed_steps: List[OnboardingStep] = []
        self.started_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.is_completed = False
        self.skip_optional = False
        
    def complete_step(self, step: OnboardingStep):
        """Mark a step as completed."""
        if step not in self.completed_steps:
            self.completed_steps.append(step)
        self.last_activity = datetime.utcnow()
        
        # Advance to next step
        steps = list(OnboardingStep)
        current_index = steps.index(self.current_step)
        
        if current_index < len(steps) - 1:
            self.current_step = steps[current_index + 1]
        else:
            self.is_completed = True
    
    def get_progress_percentage(self) -> float:
        """Get completion percentage."""
        total_steps = len(OnboardingStep)
        completed_count = len(self.completed_steps)
        return (completed_count / total_steps) * 100
    
    def is_step_completed(self, step: OnboardingStep) -> bool:
        """Check if a step is completed."""
        return step in self.completed_steps


class OnboardingManager:
    """Manages user onboarding process."""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = get_logger(__name__)
        self.event_bus: EventBus = bot.event_bus
        
        # Track onboarding progress
        self.user_progress: Dict[str, OnboardingProgress] = {}
        
        # Subscribe to relevant events
        self.event_bus.subscribe(EventType.USER_JOINED_GUILD, self._on_user_joined)
        self.event_bus.subscribe(EventType.USER_TIMEZONE_UPDATED, self._on_timezone_updated)
        self.event_bus.subscribe(EventType.GAME_INTEREST_ADDED, self._on_game_interest_added)
        self.event_bus.subscribe(EventType.EVENT_CREATED, self._on_event_created)
    
    async def _on_user_joined(self, event_data):
        """Handle user joining guild."""
        try:
            user_id = event_data.data.get('user_id')
            guild_id = event_data.data.get('guild_id')
            
            if user_id and guild_id:
                await self.start_onboarding(user_id, guild_id)
        except Exception as e:
            self.logger.error(f"Error handling user joined event: {e}", exc_info=True)
    
    async def _on_timezone_updated(self, event_data):
        """Handle timezone update during onboarding."""
        try:
            user_id = event_data.data.get('user_id')
            guild_id = event_data.data.get('guild_id')
            
            progress_key = f"{user_id}_{guild_id}"
            if progress_key in self.user_progress:
                progress = self.user_progress[progress_key]
                progress.complete_step(OnboardingStep.TIMEZONE_SETUP)
                await self._continue_onboarding(user_id, guild_id)
        except Exception as e:
            self.logger.error(f"Error handling timezone update: {e}", exc_info=True)
    
    async def _on_game_interest_added(self, event_data):
        """Handle game interest addition during onboarding."""
        try:
            user_id = event_data.data.get('user_id')
            guild_id = event_data.data.get('guild_id')
            
            progress_key = f"{user_id}_{guild_id}"
            if progress_key in self.user_progress:
                progress = self.user_progress[progress_key]
                progress.complete_step(OnboardingStep.GAME_INTERESTS)
                await self._continue_onboarding(user_id, guild_id)
        except Exception as e:
            self.logger.error(f"Error handling game interest addition: {e}", exc_info=True)
    
    async def _on_event_created(self, event_data):
        """Handle event creation during onboarding."""
        try:
            creator_id = event_data.data.get('creator_id')
            guild_id = event_data.data.get('guild_id')
            
            progress_key = f"{creator_id}_{guild_id}"
            if progress_key in self.user_progress:
                progress = self.user_progress[progress_key]
                progress.complete_step(OnboardingStep.FIRST_EVENT)
                await self._continue_onboarding(creator_id, guild_id)
        except Exception as e:
            self.logger.error(f"Error handling event creation: {e}", exc_info=True)
    
    async def start_onboarding(self, user_id: str, guild_id: str):
        """Start onboarding process for a user."""
        try:
            progress_key = f"{user_id}_{guild_id}"
            
            # Check if user is already onboarding
            if progress_key in self.user_progress:
                return
            
            # Create progress tracker
            progress = OnboardingProgress(user_id, guild_id)
            self.user_progress[progress_key] = progress
            
            # Get Discord objects
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return
            
            user = guild.get_member(int(user_id))
            if not user:
                return
            
            # Start with welcome step
            await self._send_welcome_message(user, guild, progress)
            
        except Exception as e:
            self.logger.error(f"Error starting onboarding: {e}", exc_info=True)
    
    async def _send_welcome_message(self, user: discord.Member, guild: discord.Guild, progress: OnboardingProgress):
        """Send welcome message and start onboarding."""
        try:
            embed = accessibility_manager.create_accessible_embed(
                title="🎮 Welcome to Game Night Bot!",
                description=(
                    f"Hi {user.mention}! I'm here to help you organize amazing game nights with your friends.\n\n"
                    f"Let's get you set up with a quick tour of the essential features. "
                    f"This will only take a few minutes and will make your experience much better!"
                ),
                color=discord.Color.green(),
                user_id=str(user.id)
            )
            
            embed.add_field(
                name="🚀 What We'll Cover",
                value=(
                    "• Setting up your profile and timezone\n"
                    "• Adding games you're interested in\n"
                    "• Configuring your availability\n"
                    "• Setting up notifications\n"
                    "• Creating your first event"
                ),
                inline=False,
                screen_reader_description="We'll cover profile setup, game interests, availability, notifications, and event creation"
            )
            
            embed.add_field(
                name="⏱️ Time Required",
                value="About 3-5 minutes",
                inline=True
            )
            
            embed.add_field(
                name="🎯 Benefits",
                value="Better event scheduling, relevant notifications, easier coordination",
                inline=True
            )
            
            view = OnboardingWelcomeView(self, progress)
            
            try:
                await user.send(embed=embed.build(), view=view)
                progress.complete_step(OnboardingStep.WELCOME)
            except discord.Forbidden:
                # Can't DM user, try to find a suitable channel
                await self._send_to_channel(guild, user, embed.build(), view)
                progress.complete_step(OnboardingStep.WELCOME)
        
        except Exception as e:
            self.logger.error(f"Error sending welcome message: {e}", exc_info=True)
    
    async def _send_to_channel(self, guild: discord.Guild, user: discord.Member, 
                              embed: discord.Embed, view: discord.ui.View = None):
        """Send onboarding message to a suitable channel."""
        # Try to find a suitable channel
        suitable_channels = []
        
        # Look for welcome, general, or bot channels
        for channel in guild.text_channels:
            if any(keyword in channel.name.lower() for keyword in ['welcome', 'general', 'bot', 'commands']):
                if channel.permissions_for(guild.me).send_messages:
                    suitable_channels.append(channel)
        
        # If no suitable channels, use the first available channel
        if not suitable_channels:
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    suitable_channels.append(channel)
                    break
        
        if suitable_channels:
            channel = suitable_channels[0]
            content = f"{user.mention}, welcome! I've sent you a DM to get started, but here's the info in case you can't see it:"
            await channel.send(content=content, embed=embed, view=view)
    
    async def _continue_onboarding(self, user_id: str, guild_id: str):
        """Continue onboarding to the next step."""
        try:
            progress_key = f"{user_id}_{guild_id}"
            if progress_key not in self.user_progress:
                return
            
            progress = self.user_progress[progress_key]
            
            # Get Discord objects
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return
            
            user = guild.get_member(int(user_id))
            if not user:
                return
            
            # Send next step based on current progress
            if progress.current_step == OnboardingStep.PROFILE_SETUP:
                await self._send_profile_setup(user, progress)
            elif progress.current_step == OnboardingStep.TIMEZONE_SETUP:
                await self._send_timezone_setup(user, progress)
            elif progress.current_step == OnboardingStep.GAME_INTERESTS:
                await self._send_game_interests_setup(user, progress)
            elif progress.current_step == OnboardingStep.AVAILABILITY:
                await self._send_availability_setup(user, progress)
            elif progress.current_step == OnboardingStep.NOTIFICATIONS:
                await self._send_notifications_setup(user, progress)
            elif progress.current_step == OnboardingStep.FIRST_EVENT:
                await self._send_first_event_guide(user, progress)
            elif progress.current_step == OnboardingStep.COMPLETION:
                await self._send_completion_message(user, progress)
                
        except Exception as e:
            self.logger.error(f"Error continuing onboarding: {e}", exc_info=True)
    
    async def _send_profile_setup(self, user: discord.Member, progress: OnboardingProgress):
        """Send profile setup step."""
        embed = accessibility_manager.create_accessible_embed(
            title="👤 Step 1: Profile Setup",
            description="Let's start by setting up your basic profile information.",
            color=discord.Color.blue(),
            user_id=str(user.id)
        )
        
        embed.add_field(
            name="🎯 What This Does",
            value="Your profile helps other players know about your gaming preferences and availability.",
            inline=False
        )
        
        embed.add_field(
            name="📋 Quick Action",
            value="Click the button below to open your profile, then we'll move to the next step.",
            inline=False
        )
        
        view = OnboardingProfileView(self, progress)
        
        try:
            await user.send(embed=embed.build(), view=view)
        except discord.Forbidden:
            pass  # Skip if can't DM
    
    async def _send_timezone_setup(self, user: discord.Member, progress: OnboardingProgress):
        """Send timezone setup step."""
        embed = accessibility_manager.create_accessible_embed(
            title="🌍 Step 2: Set Your Timezone",
            description="Setting your timezone ensures all event times are displayed correctly for you.",
            color=discord.Color.blue(),
            user_id=str(user.id)
        )
        
        embed.add_field(
            name="🎯 Why This Matters",
            value="Events will show in your local time, making it easier to know when things are happening.",
            inline=False
        )
        
        embed.add_field(
            name="📋 How To Set It",
            value="Use `/timezone America/New_York` (replace with your timezone)",
            inline=False
        )
        
        embed.add_field(
            name="💡 Common Timezones",
            value=(
                "• `America/New_York` (Eastern US)\n"
                "• `America/Chicago` (Central US)\n"
                "• `America/Denver` (Mountain US)\n"
                "• `America/Los_Angeles` (Pacific US)\n"
                "• `Europe/London` (UK)\n"
                "• `Europe/Paris` (Central Europe)\n"
                "• `UTC` (Universal Time)"
            ),
            inline=False
        )
        
        view = OnboardingTimezoneView(self, progress)
        
        try:
            await user.send(embed=embed.build(), view=view)
        except discord.Forbidden:
            pass
    
    async def _send_game_interests_setup(self, user: discord.Member, progress: OnboardingProgress):
        """Send game interests setup step."""
        embed = accessibility_manager.create_accessible_embed(
            title="🎮 Step 3: Add Your Game Interests",
            description="Tell us what games you like to play so others can find you for game sessions!",
            color=discord.Color.blue(),
            user_id=str(user.id)
        )
        
        embed.add_field(
            name="🎯 What This Does",
            value="When someone wants to play a game you're interested in, you'll get notified!",
            inline=False
        )
        
        embed.add_field(
            name="📋 How To Add Games",
            value="Use `/games add <game_name>` for each game you enjoy",
            inline=False
        )
        
        embed.add_field(
            name="💡 Examples",
            value=(
                "• `/games add Among Us`\n"
                "• `/games add Minecraft`\n"
                "• `/games add Valorant`\n"
                "• `/games add Board Games`"
            ),
            inline=False
        )
        
        view = OnboardingGamesView(self, progress)
        
        try:
            await user.send(embed=embed.build(), view=view)
        except discord.Forbidden:
            pass
    
    async def _send_completion_message(self, user: discord.Member, progress: OnboardingProgress):
        """Send completion message."""
        embed = accessibility_manager.create_accessible_embed(
            title="🎉 Welcome Complete!",
            description="Congratulations! You're all set up and ready to enjoy Game Night Bot.",
            color=discord.Color.green(),
            user_id=str(user.id)
        )
        
        embed.add_field(
            name="🚀 You're Ready To",
            value=(
                "• Create events with `/event create`\n"
                "• Join existing events\n"
                "• Get pinged for games you like\n"
                "• Manage your profile anytime"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🆘 Need Help?",
            value="Use `/help` anytime to get assistance with commands and features.",
            inline=False
        )
        
        embed.add_field(
            name="📊 Your Progress",
            value=f"Completed {len(progress.completed_steps)}/{len(OnboardingStep)} steps in {(datetime.utcnow() - progress.started_at).seconds // 60} minutes!",
            inline=False
        )
        
        # Mark as completed
        progress.is_completed = True
        
        # Clean up progress tracking
        progress_key = f"{progress.user_id}_{progress.guild_id}"
        if progress_key in self.user_progress:
            del self.user_progress[progress_key]
        
        try:
            await user.send(embed=embed.build())
        except discord.Forbidden:
            pass
        
        # Emit completion event
        await self.event_bus.emit(
            EventType.USER_ONBOARDING_COMPLETED,
            {
                "user_id": progress.user_id,
                "guild_id": progress.guild_id,
                "completed_steps": len(progress.completed_steps),
                "duration_minutes": (datetime.utcnow() - progress.started_at).seconds // 60
            },
            source="onboarding_system",
            guild_id=progress.guild_id,
            user_id=progress.user_id
        )
    
    def get_user_progress(self, user_id: str, guild_id: str) -> Optional[OnboardingProgress]:
        """Get user's onboarding progress."""
        progress_key = f"{user_id}_{guild_id}"
        return self.user_progress.get(progress_key)
    
    async def skip_onboarding(self, user_id: str, guild_id: str):
        """Skip onboarding for a user."""
        progress_key = f"{user_id}_{guild_id}"
        if progress_key in self.user_progress:
            progress = self.user_progress[progress_key]
            progress.is_completed = True
            del self.user_progress[progress_key]
cla
ss OnboardingWelcomeView(discord.ui.View):
    """Welcome view for onboarding."""
    
    def __init__(self, manager: OnboardingManager, progress: OnboardingProgress):
        super().__init__(timeout=600)  # 10 minute timeout
        self.manager = manager
        self.progress = progress
    
    @discord.ui.button(label="Let's Get Started!", style=discord.ButtonStyle.primary, emoji="🚀")
    async def start_onboarding(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Start the onboarding process."""
        await interaction.response.send_message(
            "🎉 Great! Let's get you set up. I'll guide you through each step.",
            ephemeral=True
        )
        
        # Move to profile setup
        self.progress.current_step = OnboardingStep.PROFILE_SETUP
        await self.manager._continue_onboarding(self.progress.user_id, self.progress.guild_id)
    
    @discord.ui.button(label="Skip Setup", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_onboarding(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Skip the onboarding process."""
        await interaction.response.send_message(
            "No problem! You can always use `/help` to learn about commands later. "
            "Use `/profile` anytime to set up your preferences.",
            ephemeral=True
        )
        
        await self.manager.skip_onboarding(self.progress.user_id, self.progress.guild_id)


class OnboardingProfileView(discord.ui.View):
    """Profile setup view for onboarding."""
    
    def __init__(self, manager: OnboardingManager, progress: OnboardingProgress):
        super().__init__(timeout=600)
        self.manager = manager
        self.progress = progress
    
    @discord.ui.button(label="Open Profile", style=discord.ButtonStyle.primary, emoji="👤")
    async def open_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open profile command."""
        await interaction.response.send_message(
            "Perfect! Use the `/profile` command to view and set up your profile. "
            "Once you've looked at it, we'll move to the next step.",
            ephemeral=True
        )
        
        # Mark step as completed and continue
        self.progress.complete_step(OnboardingStep.PROFILE_SETUP)
        await self.manager._continue_onboarding(self.progress.user_id, self.progress.guild_id)
    
    @discord.ui.button(label="Skip This Step", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Skip this step."""
        await interaction.response.send_message(
            "Skipped! You can always use `/profile` later to set up your profile.",
            ephemeral=True
        )
        
        self.progress.complete_step(OnboardingStep.PROFILE_SETUP)
        await self.manager._continue_onboarding(self.progress.user_id, self.progress.guild_id)


class OnboardingTimezoneView(discord.ui.View):
    """Timezone setup view for onboarding."""
    
    def __init__(self, manager: OnboardingManager, progress: OnboardingProgress):
        super().__init__(timeout=600)
        self.manager = manager
        self.progress = progress
    
    @discord.ui.button(label="I Set My Timezone", style=discord.ButtonStyle.primary, emoji="🌍")
    async def timezone_set(self, interaction: discord.Interaction, button: discord.ui.Button):
        """User confirms they set their timezone."""
        await interaction.response.send_message(
            "Excellent! Your timezone is now configured. Let's move on to adding your game interests.",
            ephemeral=True
        )
        
        # This will be automatically detected by the event listener
        # But we can manually advance if needed
        self.progress.complete_step(OnboardingStep.TIMEZONE_SETUP)
        await self.manager._continue_onboarding(self.progress.user_id, self.progress.guild_id)
    
    @discord.ui.button(label="Skip This Step", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Skip timezone setup."""
        await interaction.response.send_message(
            "Skipped! You can set your timezone later with `/timezone <your_timezone>`.",
            ephemeral=True
        )
        
        self.progress.complete_step(OnboardingStep.TIMEZONE_SETUP)
        await self.manager._continue_onboarding(self.progress.user_id, self.progress.guild_id)


class OnboardingGamesView(discord.ui.View):
    """Games setup view for onboarding."""
    
    def __init__(self, manager: OnboardingManager, progress: OnboardingProgress):
        super().__init__(timeout=600)
        self.manager = manager
        self.progress = progress
    
    @discord.ui.button(label="I Added Games", style=discord.ButtonStyle.primary, emoji="🎮")
    async def games_added(self, interaction: discord.Interaction, button: discord.ui.Button):
        """User confirms they added games."""
        await interaction.response.send_message(
            "Awesome! Now you'll get notified when people want to play those games. "
            "Let's set up your availability next.",
            ephemeral=True
        )
        
        self.progress.complete_step(OnboardingStep.GAME_INTERESTS)
        await self.manager._continue_onboarding(self.progress.user_id, self.progress.guild_id)
    
    @discord.ui.button(label="Skip This Step", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Skip games setup."""
        await interaction.response.send_message(
            "Skipped! You can add games later with `/games add <game_name>`.",
            ephemeral=True
        )
        
        self.progress.complete_step(OnboardingStep.GAME_INTERESTS)
        await self.manager._continue_onboarding(self.progress.user_id, self.progress.guild_id)


class OnboardingProgressView(discord.ui.View):
    """View to show onboarding progress."""
    
    def __init__(self, manager: OnboardingManager, progress: OnboardingProgress):
        super().__init__(timeout=300)
        self.manager = manager
        self.progress = progress
    
    @discord.ui.button(label="Continue Setup", style=discord.ButtonStyle.primary, emoji="▶️")
    async def continue_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Continue onboarding setup."""
        await interaction.response.send_message(
            "Continuing your setup...",
            ephemeral=True
        )
        
        await self.manager._continue_onboarding(self.progress.user_id, self.progress.guild_id)
    
    @discord.ui.button(label="Skip Remaining", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_remaining(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Skip remaining onboarding steps."""
        await interaction.response.send_message(
            "Setup skipped! You can always use `/help` to learn about features later.",
            ephemeral=True
        )
        
        await self.manager.skip_onboarding(self.progress.user_id, self.progress.guild_id)


def create_onboarding_progress_embed(progress: OnboardingProgress, user: discord.Member) -> discord.Embed:
    """Create an embed showing onboarding progress."""
    embed = accessibility_manager.create_accessible_embed(
        title="📋 Your Setup Progress",
        description=f"Hi {user.display_name}! Here's your onboarding progress:",
        color=discord.Color.blue(),
        user_id=str(user.id)
    )
    
    # Progress bar
    percentage = progress.get_progress_percentage()
    filled_blocks = int(percentage / 10)
    empty_blocks = 10 - filled_blocks
    progress_bar = "█" * filled_blocks + "░" * empty_blocks
    
    embed.add_field(
        name="📊 Overall Progress",
        value=f"`{progress_bar}` {percentage:.0f}%",
        inline=False
    )
    
    # Step status
    steps_status = []
    for step in OnboardingStep:
        if progress.is_step_completed(step):
            steps_status.append(f"✅ {step.value.replace('_', ' ').title()}")
        elif step == progress.current_step:
            steps_status.append(f"🔄 {step.value.replace('_', ' ').title()} (Current)")
        else:
            steps_status.append(f"⏳ {step.value.replace('_', ' ').title()}")
    
    embed.add_field(
        name="📝 Steps",
        value="\n".join(steps_status),
        inline=False
    )
    
    # Time info
    time_elapsed = datetime.utcnow() - progress.started_at
    embed.add_field(
        name="⏱️ Time Elapsed",
        value=f"{time_elapsed.seconds // 60} minutes",
        inline=True
    )
    
    embed.add_field(
        name="🎯 Next Step",
        value=progress.current_step.value.replace('_', ' ').title(),
        inline=True
    )
    
    return embed.build()