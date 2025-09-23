"""
Events cog for managing game night events with interactive polls and RSVP tracking.
"""

import asyncio
from datetime import datetime, date, time, timedelta
from typing import Optional, List, Dict, Any
import uuid

import discord
from discord.ext import commands
try:
    from discord import app_commands
except ImportError:
    # Fallback for older discord.py versions
    app_commands = None

from models.event import Event, EventState, Poll, PollType, PollOption, RSVPStatus
from core.event_bus import EventBus, EventType
from core.permission_decorators import require_permission
from core.security_manager import Permission
from core.validation_manager import ValidationManager
from core.poll_manager import PollManager
from core.poll_notifications import PollNotificationScheduler
from views.enhanced_poll_views import (
    EnhancedDatePollView, EnhancedTimePollView, TieResolutionView,
    PersistentPollView
)
from utils.exceptions import ValidationError, PermissionDeniedError, ErrorCode
from utils.logging_config import get_logger, LoggerMixin


class EventCreationModal(discord.ui.Modal):
    """Modal for event creation with title and description inputs."""
    
    def __init__(self, cog: 'EventsCog'):
        super().__init__(title="Create New Game Night Event")
        self.cog = cog
        
        # Event title input
        self.title_input = discord.ui.TextInput(
            label="Event Title",
            placeholder="Enter a title for your game night...",
            min_length=3,
            max_length=100,
            required=True
        )
        self.add_item(self.title_input)
        
        # Event description input
        self.description_input = discord.ui.TextInput(
            label="Event Description",
            placeholder="Describe your game night (optional)...",
            style=discord.TextStyle.paragraph,
            max_length=2000,
            required=False
        )
        self.add_item(self.description_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        try:
            # Validate inputs
            title, description = await self.cog.validate_event_input(
                self.title_input.value,
                self.description_input.value
            )
            
            # Create the event
            event = await self.cog.create_event(
                guild_id=str(interaction.guild.id),
                creator_id=str(interaction.user.id),
                title=title,
                description=description
            )
            
            # Create and send the event embed
            embed = self.cog.create_event_embed(event)
            view = EventManagementView(self.cog, event)
            
            await interaction.response.send_message(
                f"✅ Event **{event.title}** created successfully!",
                embed=embed,
                view=view
            )
            
        except ValidationError as e:
            await interaction.response.send_message(
                f"❌ Invalid input: {e.user_message}",
                ephemeral=True
            )
        except Exception as e:
            self.cog.logger.error(f"Error creating event: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while creating the event. Please try again.",
                ephemeral=True
            )


class DatePollView(discord.ui.View):
    """View for date selection poll with buttons."""
    
    def __init__(self, cog: 'EventsCog', event: Event, poll: Poll):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.event = event
        self.poll = poll
        
        # Add buttons for each date option (max 25 buttons)
        for i, option in enumerate(poll.options[:25]):
            button = DateButton(option, i)
            self.add_item(button)
    
    async def on_timeout(self):
        """Handle view timeout."""
        # Disable all buttons
        for item in self.children:
            item.disabled = True


class DateButton(discord.ui.Button):
    """Button for date selection."""
    
    def __init__(self, option: PollOption, index: int):
        # Use different styles for visual variety
        styles = [discord.ButtonStyle.primary, discord.ButtonStyle.secondary]
        style = styles[index % 2]
        
        super().__init__(
            label=option.label,
            style=style,
            custom_id=f"date_{option.option_id}"
        )
        self.option = option
    
    async def callback(self, interaction: discord.Interaction):
        """Handle button click."""
        view: DatePollView = self.view
        
        # Add vote
        user_id = str(interaction.user.id)
        success = view.poll.add_vote(user_id, self.option.option_id)
        
        if success:
            # Update the event in database
            await view.cog.update_event(view.event)
            
            # Update the embed
            embed = view.cog.create_poll_embed(view.poll, view.event)
            await interaction.response.edit_message(embed=embed, view=view)
            
            # Emit event
            await view.cog.event_bus.emit(
                EventType.POLL_VOTE_CAST,
                {
                    "event_id": str(view.event.id),
                    "poll_type": view.poll.poll_type.value,
                    "option_id": self.option.option_id,
                    "user_id": user_id
                },
                source="events_cog",
                guild_id=view.event.guild_id,
                user_id=user_id
            )
        else:
            await interaction.response.send_message(
                "❌ Unable to record your vote. Please try again.",
                ephemeral=True
            )


class TimePollView(discord.ui.View):
    """View for time selection poll with buttons."""
    
    def __init__(self, cog: 'EventsCog', event: Event, poll: Poll):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.event = event
        self.poll = poll
        
        # Add buttons for each time option
        for i, option in enumerate(poll.options):
            button = TimeButton(option, i)
            self.add_item(button)
    
    async def on_timeout(self):
        """Handle view timeout."""
        # Disable all buttons
        for item in self.children:
            item.disabled = True


class TimeButton(discord.ui.Button):
    """Button for time selection."""
    
    def __init__(self, option: PollOption, index: int):
        # Use different styles for visual variety
        styles = [discord.ButtonStyle.primary, discord.ButtonStyle.secondary]
        style = styles[index % 2]
        
        super().__init__(
            label=option.label,
            style=style,
            custom_id=f"time_{option.option_id}"
        )
        self.option = option
    
    async def callback(self, interaction: discord.Interaction):
        """Handle button click."""
        view: TimePollView = self.view
        
        # Add vote
        user_id = str(interaction.user.id)
        success = view.poll.add_vote(user_id, self.option.option_id)
        
        if success:
            # Update the event in database
            await view.cog.update_event(view.event)
            
            # Update the embed
            embed = view.cog.create_poll_embed(view.poll, view.event)
            await interaction.response.edit_message(embed=embed, view=view)
            
            # Emit event
            await view.cog.event_bus.emit(
                EventType.POLL_VOTE_CAST,
                {
                    "event_id": str(view.event.id),
                    "poll_type": view.poll.poll_type.value,
                    "option_id": self.option.option_id,
                    "user_id": user_id
                },
                source="events_cog",
                guild_id=view.event.guild_id,
                user_id=user_id
            )
        else:
            await interaction.response.send_message(
                "❌ Unable to record your vote. Please try again.",
                ephemeral=True
            )


class GamePollView(discord.ui.View):
    """View for game selection poll with dropdown."""
    
    def __init__(self, cog: 'EventsCog', event: Event, poll: Poll):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.event = event
        self.poll = poll
        
        # Add dropdown for game selection (max 25 options)
        dropdown = GameDropdown(poll.options[:25])
        self.add_item(dropdown)
    
    async def on_timeout(self):
        """Handle view timeout."""
        # Disable all items
        for item in self.children:
            item.disabled = True


class GameDropdown(discord.ui.Select):
    """Dropdown for game selection."""
    
    def __init__(self, options: List[PollOption]):
        # Convert poll options to select options
        select_options = []
        for option in options:
            select_options.append(
                discord.SelectOption(
                    label=option.label,
                    value=option.option_id,
                    description=f"Vote for {option.label}"
                )
            )
        
        super().__init__(
            placeholder="Choose your preferred games...",
            min_values=1,
            max_values=min(len(select_options), 3),  # Allow up to 3 selections
            options=select_options
        )
        self.poll_options = {opt.option_id: opt for opt in options}
    
    async def callback(self, interaction: discord.Interaction):
        """Handle dropdown selection."""
        view: GamePollView = self.view
        user_id = str(interaction.user.id)
        
        # Remove all existing votes for this user (since it's multi-select)
        for option in view.poll.options:
            option.remove_vote(user_id)
        
        # Add votes for selected options
        votes_added = 0
        for option_id in self.values:
            if view.poll.add_vote(user_id, option_id):
                votes_added += 1
        
        if votes_added > 0:
            # Update the event in database
            await view.cog.update_event(view.event)
            
            # Update the embed
            embed = view.cog.create_poll_embed(view.poll, view.event)
            await interaction.response.edit_message(embed=embed, view=view)
            
            # Emit event
            await view.cog.event_bus.emit(
                EventType.POLL_VOTE_CAST,
                {
                    "event_id": str(view.event.id),
                    "poll_type": view.poll.poll_type.value,
                    "option_ids": self.values,
                    "user_id": user_id
                },
                source="events_cog",
                guild_id=view.event.guild_id,
                user_id=user_id
            )
        else:
            await interaction.response.send_message(
                "❌ Unable to record your votes. Please try again.",
                ephemeral=True
            )


class EventManagementView(discord.ui.View):
    """View for event management actions."""
    
    def __init__(self, cog: 'EventsCog', event: Event):
        super().__init__(timeout=None)  # Persistent view
        self.cog = cog
        self.event = event
        
        # Add buttons based on event state
        if event.state == EventState.DRAFT:
            self.add_item(StartDatePollButton())
        elif event.state == EventState.DATE_POLLING:
            self.add_item(CloseDatePollButton())
        elif event.state == EventState.TIME_POLLING:
            self.add_item(CloseTimePollButton())
        elif event.state == EventState.GAME_POLLING:
            self.add_item(CloseGamePollButton())
        
        # Always add RSVP and cancel buttons for active events
        if event.is_active():
            self.add_item(RSVPButton())
            self.add_item(CancelEventButton())


class StartDatePollButton(discord.ui.Button):
    """Button to start date polling."""
    
    def __init__(self):
        super().__init__(
            label="Start Date Poll",
            style=discord.ButtonStyle.primary,
            emoji="📅"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: EventManagementView = self.view
        
        # Check permissions
        if not await view.cog.can_manage_event(interaction.user, view.event):
            await interaction.response.send_message(
                "❌ You don't have permission to manage this event.",
                ephemeral=True
            )
            return
        
        try:
            # Start enhanced date polling
            await view.cog.start_enhanced_date_poll(view.event)
            
            # Get updated event and poll
            updated_event = await view.cog.get_event(view.event.id)
            date_poll = updated_event.get_poll(PollType.DATE)
            
            # Create poll embed and view
            embed = view.cog.create_enhanced_poll_embed(date_poll, updated_event)
            poll_view = EnhancedDatePollView(view.cog, updated_event, date_poll)
            
            await interaction.response.edit_message(
                content=f"📅 **Date Poll Started for {updated_event.title}**\n"
                        f"Vote for your preferred date:",
                embed=embed,
                view=poll_view
            )
            
        except Exception as e:
            view.cog.logger.error(f"Error starting date poll: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while starting the date poll.",
                ephemeral=True
            )


class CloseDatePollButton(discord.ui.Button):
    """Button to close date polling and advance to time poll."""
    
    def __init__(self):
        super().__init__(
            label="Close Date Poll",
            style=discord.ButtonStyle.success,
            emoji="✅"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: EventManagementView = self.view
        
        # Check permissions
        if not await view.cog.can_manage_event(interaction.user, view.event):
            await interaction.response.send_message(
                "❌ You don't have permission to manage this event.",
                ephemeral=True
            )
            return
        
        try:
            # Close date poll and start time poll
            await view.cog.close_date_poll_and_start_time_poll(view.event)
            
            # Get updated event and time poll
            updated_event = await view.cog.get_event(view.event.id)
            time_poll = updated_event.get_poll(PollType.TIME)
            
            # Create time poll embed and view
            embed = view.cog.create_enhanced_poll_embed(time_poll, updated_event)
            poll_view = EnhancedTimePollView(view.cog, updated_event, time_poll)
            
            await interaction.response.edit_message(
                content=f"⏰ **Time Poll Started for {updated_event.title}**\n"
                        f"Vote for your preferred time:",
                embed=embed,
                view=poll_view
            )
            
        except Exception as e:
            view.cog.logger.error(f"Error closing date poll: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while closing the date poll.",
                ephemeral=True
            )


class CloseTimePollButton(discord.ui.Button):
    """Button to close time polling and advance to game poll."""
    
    def __init__(self):
        super().__init__(
            label="Close Time Poll",
            style=discord.ButtonStyle.success,
            emoji="⏰"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: EventManagementView = self.view
        
        # Check permissions
        if not await view.cog.can_manage_event(interaction.user, view.event):
            await interaction.response.send_message(
                "❌ You don't have permission to manage this event.",
                ephemeral=True
            )
            return
        
        try:
            # Close time poll and start game poll
            await view.cog.close_time_poll_and_start_game_poll(view.event)
            
            # Get updated event and game poll
            updated_event = await view.cog.get_event(view.event.id)
            game_poll = updated_event.get_poll(PollType.GAME)
            
            # Create game poll embed and view
            embed = view.cog.create_poll_embed(game_poll, updated_event)
            poll_view = GamePollView(view.cog, updated_event, game_poll)
            
            await interaction.response.edit_message(
                content=f"🎮 **Game Poll Started for {updated_event.title}**\n"
                        f"Vote for your preferred games:",
                embed=embed,
                view=poll_view
            )
            
        except Exception as e:
            view.cog.logger.error(f"Error closing time poll: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while closing the time poll.",
                ephemeral=True
            )


class CloseGamePollButton(discord.ui.Button):
    """Button to close game polling and schedule event."""
    
    def __init__(self):
        super().__init__(
            label="Close Game Poll & Schedule",
            style=discord.ButtonStyle.success,
            emoji="🎮"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: EventManagementView = self.view
        
        # Check permissions
        if not await view.cog.can_manage_event(interaction.user, view.event):
            await interaction.response.send_message(
                "❌ You don't have permission to manage this event.",
                ephemeral=True
            )
            return
        
        try:
            # Close game poll and schedule event
            await view.cog.close_game_poll_and_schedule_event(view.event)
            
            # Get updated event
            updated_event = await view.cog.get_event(view.event.id)
            
            # Create final event embed and management view
            embed = view.cog.create_event_embed(updated_event)
            management_view = EventManagementView(view.cog, updated_event)
            
            await interaction.response.edit_message(
                content=f"✅ **Event Scheduled!**\n"
                        f"**{updated_event.title}** is now fully scheduled and ready!",
                embed=embed,
                view=management_view
            )
            
        except Exception as e:
            view.cog.logger.error(f"Error closing game poll: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while closing the game poll.",
                ephemeral=True
            )


class RSVPButton(discord.ui.Button):
    """Button to open RSVP modal."""
    
    def __init__(self):
        super().__init__(
            label="RSVP",
            style=discord.ButtonStyle.secondary,
            emoji="✋"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: EventManagementView = self.view
        
        # Open RSVP modal
        modal = RSVPModal(view.cog, view.event)
        await interaction.response.send_modal(modal)


class CancelEventButton(discord.ui.Button):
    """Button to cancel event."""
    
    def __init__(self):
        super().__init__(
            label="Cancel Event",
            style=discord.ButtonStyle.danger,
            emoji="❌"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: EventManagementView = self.view
        
        # Check permissions
        if not await view.cog.can_manage_event(interaction.user, view.event):
            await interaction.response.send_message(
                "❌ You don't have permission to cancel this event.",
                ephemeral=True
            )
            return
        
        # Confirm cancellation
        confirm_view = ConfirmCancelView(view.cog, view.event)
        await interaction.response.send_message(
            f"⚠️ Are you sure you want to cancel **{view.event.title}**?",
            view=confirm_view,
            ephemeral=True
        )


class ConfirmCancelView(discord.ui.View):
    """Confirmation view for event cancellation."""
    
    def __init__(self, cog: 'EventsCog', event: Event):
        super().__init__(timeout=60)
        self.cog = cog
        self.event = event
    
    @discord.ui.button(label="Yes, Cancel Event", style=discord.ButtonStyle.danger)
    async def confirm_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await self.cog.cancel_event(self.event)
            await interaction.response.edit_message(
                content=f"✅ Event **{self.event.title}** has been cancelled.",
                view=None
            )
        except Exception as e:
            self.cog.logger.error(f"Error cancelling event: {e}", exc_info=True)
            await interaction.response.edit_message(
                content="❌ An error occurred while cancelling the event.",
                view=None
            )
    
    @discord.ui.button(label="No, Keep Event", style=discord.ButtonStyle.secondary)
    async def cancel_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Event cancellation cancelled.",
            view=None
        )


class RSVPModal(discord.ui.Modal):
    """Modal for RSVP responses."""
    
    def __init__(self, cog: 'EventsCog', event: Event):
        super().__init__(title=f"RSVP for {event.title}")
        self.cog = cog
        self.event = event
        
        # RSVP status selection
        self.status_input = discord.ui.TextInput(
            label="Response (YES/NO/MAYBE)",
            placeholder="Enter YES, NO, or MAYBE",
            min_length=2,
            max_length=5,
            required=True
        )
        self.add_item(self.status_input)
        
        # Optional notes
        self.notes_input = discord.ui.TextInput(
            label="Notes (Optional)",
            placeholder="Any additional notes...",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=False
        )
        self.add_item(self.notes_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parse RSVP status
            status_text = self.status_input.value.upper().strip()
            if status_text == "YES":
                status = RSVPStatus.YES
            elif status_text == "NO":
                status = RSVPStatus.NO
            elif status_text == "MAYBE":
                status = RSVPStatus.MAYBE
            else:
                await interaction.response.send_message(
                    "❌ Invalid response. Please enter YES, NO, or MAYBE.",
                    ephemeral=True
                )
                return
            
            # Get notes
            notes = self.notes_input.value.strip() if self.notes_input.value else None
            
            # Add RSVP
            await self.cog.add_rsvp(
                self.event,
                str(interaction.user.id),
                status,
                notes
            )
            
            status_emoji = {"YES": "✅", "NO": "❌", "MAYBE": "❓"}[status_text]
            await interaction.response.send_message(
                f"{status_emoji} RSVP recorded for **{self.event.title}**: {status_text}",
                ephemeral=True
            )
            
        except Exception as e:
            self.cog.logger.error(f"Error processing RSVP: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while processing your RSVP.",
                ephemeral=True
            )


class EventsCog(commands.Cog, LoggerMixin):
    """
    Events cog for managing game night events.
    
    Handles the complete event lifecycle from creation through polls to completion.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.validation: ValidationManager = bot.validation
        self.event_bus: EventBus = bot.event_bus
        
        # Initialize enhanced poll management
        self.poll_manager = PollManager(self.event_bus, bot.database)
        self.poll_notifications = PollNotificationScheduler(self.event_bus, bot.database, bot)
        
        # Subscribe to relevant events
        self.event_bus.subscribe(EventType.SYSTEM_STARTUP, self._on_startup)
        self.event_bus.subscribe(EventType.POLL_COMPLETED, self._on_poll_completed)
        self.event_bus.subscribe(EventType.POLL_EXPIRED, self._on_poll_expired)
    
    async def _on_startup(self, event):
        """Handle system startup."""
        self.logger.info("Events cog started")
        
        # Reconstruct persistent views for active polls
        await self._reconstruct_persistent_views()
    
    async def _on_poll_completed(self, event_data):
        """Handle poll completion events."""
        data = event_data.data
        
        # Check if this requires admin intervention for ties
        if data.get('result') == 'tie_needs_admin_resolution':
            await self._handle_tie_resolution_needed(data)
    
    async def _on_poll_expired(self, event_data):
        """Handle poll expiration events."""
        data = event_data.data
        
        if data.get('had_tie'):
            await self._handle_tie_resolution_needed(data)
    
    async def _handle_tie_resolution_needed(self, data: Dict[str, Any]):
        """Handle when a poll tie needs admin resolution."""
        try:
            event_id = data['event_id']
            poll_type = PollType(data['poll_type'])
            
            # Get event and poll data
            event_data = await self.bot.database.events.find_one({'_id': event_id})
            if not event_data:
                return
            
            event = Event(**event_data)
            poll = event.get_poll(poll_type)
            if not poll:
                return
            
            # Get tied options
            tied_options = []
            if 'tied_options' in data:
                for option_data in data['tied_options']:
                    option = poll.get_option_by_id(option_data['id'])
                    if option:
                        tied_options.append(option)
            
            if tied_options:
                # Create tie resolution view and send to admins
                guild = self.bot.get_guild(int(event.guild_id))
                if guild:
                    # Find admin channel or use general
                    admin_channel = None
                    for channel in guild.text_channels:
                        if 'admin' in channel.name.lower() or 'mod' in channel.name.lower():
                            admin_channel = channel
                            break
                    
                    if not admin_channel:
                        admin_channel = guild.text_channels[0] if guild.text_channels else None
                    
                    if admin_channel:
                        view = TieResolutionView(self, event, poll, tied_options)
                        await admin_channel.send(
                            f"🔧 **Admin Action Required**\n"
                            f"Poll tie in event **{event.title}** needs resolution.\n"
                            f"Tied options: {', '.join(opt.label for opt in tied_options)}",
                            view=view
                        )
        
        except Exception as e:
            self.logger.error(f"Error handling tie resolution: {e}", exc_info=True)
    
    async def _reconstruct_persistent_views(self):
        """Reconstruct persistent views for active polls after bot restart."""
        try:
            # Find all active events with active polls
            active_events = await self.bot.database.events.find({
                'state': {'$in': ['DATE_POLLING', 'TIME_POLLING', 'GAME_POLLING']}
            }).to_list(length=100)
            
            for event_data in active_events:
                event = Event(**event_data)
                
                # Check each poll type
                for poll_type in [PollType.DATE, PollType.TIME, PollType.GAME]:
                    poll = event.get_poll(poll_type)
                    if poll and poll.is_active:
                        # Recreate timeout for this poll
                        if poll.closes_at:
                            remaining_seconds = (poll.closes_at - datetime.utcnow()).total_seconds()
                            if remaining_seconds > 0:
                                # Reschedule timeout
                                await self.poll_manager.schedule_poll_notifications(
                                    event_id=str(event.id),
                                    poll_type=poll_type,
                                    timeout_seconds=int(remaining_seconds)
                                )
            
            self.logger.info(f"Reconstructed persistent views for {len(active_events)} active events")
            
        except Exception as e:
            self.logger.error(f"Error reconstructing persistent views: {e}", exc_info=True)
    
    @commands.slash_command(name="event", description="Create a new game night event")
    @require_permission(Permission.CREATE_EVENTS)
    async def create_event_command(self, interaction: discord.Interaction):
        """Create a new game night event."""
        modal = EventCreationModal(self)
        await interaction.response.send_modal(modal)
    
    @commands.slash_command(name="events", description="List active events in this server")
    async def list_events_command(self, interaction: discord.Interaction):
        """List active events in the server."""
        try:
            events = await self.get_guild_events(str(interaction.guild.id))
            
            if not events:
                await interaction.response.send_message(
                    "📅 No active events found in this server.",
                    ephemeral=True
                )
                return
            
            # Create embed with event list
            embed = discord.Embed(
                title="📅 Active Events",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            for event in events[:10]:  # Limit to 10 events
                status_emoji = {
                    EventState.DRAFT: "📝",
                    EventState.DATE_POLLING: "📅",
                    EventState.TIME_POLLING: "⏰",
                    EventState.GAME_POLLING: "🎮",
                    EventState.SCHEDULED: "✅"
                }.get(event.state, "❓")
                
                embed.add_field(
                    name=f"{status_emoji} {event.title}",
                    value=f"State: {event.state.value}\n"
                          f"Creator: <@{event.creator_id}>\n"
                          f"RSVPs: {event.get_rsvp_count(RSVPStatus.YES)} Yes, "
                          f"{event.get_rsvp_count(RSVPStatus.NO)} No, "
                          f"{event.get_rsvp_count(RSVPStatus.MAYBE)} Maybe",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            self.logger.error(f"Error listing events: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while listing events.",
                ephemeral=True
            )
    
    @commands.slash_command(name="event-manage", description="Manage a specific event")
    async def manage_event_command(self, interaction: discord.Interaction, event_id: str):
        """Manage a specific event by ID."""
        try:
            # Get the event
            event = await self.get_event_by_id(event_id)
            if not event:
                await interaction.response.send_message(
                    "❌ Event not found. Please check the event ID.",
                    ephemeral=True
                )
                return
            
            # Check if event belongs to this guild
            if event.guild_id != str(interaction.guild.id):
                await interaction.response.send_message(
                    "❌ Event not found in this server.",
                    ephemeral=True
                )
                return
            
            # Check permissions
            if not await self.can_manage_event(interaction.user, event):
                await interaction.response.send_message(
                    "❌ You don't have permission to manage this event.",
                    ephemeral=True
                )
                return
            
            # Create event embed and management view
            embed = self.create_event_embed(event)
            view = EventManagementView(self, event)
            
            await interaction.response.send_message(
                f"🎮 **Managing Event: {event.title}**",
                embed=embed,
                view=view
            )
            
        except Exception as e:
            self.logger.error(f"Error managing event: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while loading the event.",
                ephemeral=True
            )
    
    async def create_event(
        self,
        guild_id: str,
        creator_id: str,
        title: str,
        description: Optional[str] = None
    ) -> Event:
        """Create a new event."""
        # Validate inputs using ValidationMixin methods
        from models.base import ValidationMixin
        try:
            ValidationMixin.validate_guild_id(guild_id)
            ValidationMixin.validate_user_id(creator_id)
        except ValueError as e:
            raise ValidationError(str(e))
        
        # Create event
        event = Event(
            guild_id=guild_id,
            creator_id=creator_id,
            title=title,
            description=description,
            state=EventState.DRAFT
        )
        
        # Validate event data
        event.validate_data()
        
        # Save to database
        await self.bot.database.events.insert_one(event.model_dump())
        
        # Emit event
        await self.event_bus.emit(
            EventType.EVENT_CREATED,
            {
                "event_id": str(event.id),
                "title": event.title,
                "creator_id": creator_id
            },
            source="events_cog",
            guild_id=guild_id,
            user_id=creator_id
        )
        
        self.logger.info(
            "Event created",
            event_id=str(event.id),
            title=event.title,
            guild_id=guild_id,
            creator_id=creator_id
        )
        
        return event    

    async def get_event(self, event_id: str) -> Optional[Event]:
        """Get event by ID."""
        try:
            from bson import ObjectId
            result = await self.bot.database.events.find_one({"_id": ObjectId(event_id)})
            if result:
                return Event(**result)
            return None
        except Exception as e:
            self.logger.error(f"Error getting event {event_id}: {e}")
            return None
    
    async def update_event(self, event: Event) -> bool:
        """Update event in database."""
        try:
            # Skip update if event doesn't have an ID (not saved yet)
            if not event.id:
                self.logger.warning("Attempted to update event without ID")
                return False
                
            from bson import ObjectId
            result = await self.bot.database.events.replace_one(
                {"_id": ObjectId(str(event.id))},
                event.model_dump()
            )
            return result.modified_count > 0
        except Exception as e:
            self.logger.error(f"Error updating event {event.id}: {e}")
            return False
    
    async def get_guild_events(self, guild_id: str, active_only: bool = True) -> List[Event]:
        """Get events for a guild."""
        try:
            query = {"guild_id": guild_id}
            if active_only:
                query["state"] = {"$nin": [EventState.COMPLETED.value, EventState.CANCELLED.value]}
            
            cursor = self.bot.database.events.find(query).sort("created_at", -1)
            events = []
            async for doc in cursor:
                events.append(Event(**doc))
            return events
        except Exception as e:
            self.logger.error(f"Error getting guild events: {e}")
            return []
    
    async def can_manage_event(self, user: discord.User, event: Event) -> bool:
        """Check if user can manage the event."""
        try:
            # Event creator can always manage
            if str(user.id) == event.creator_id:
                return True
            
            # Check permissions through security manager
            # This would use the permission system from the security manager
            # For now, we'll allow server administrators
            if hasattr(user, 'guild_permissions') and user.guild_permissions.administrator:
                return True
        except Exception as e:
            self.logger.error(f"Error checking event management permissions: {e}")
        
        return False
    
    async def start_date_poll(self, event: Event) -> None:
        """Start date polling for an event."""
        if not event.can_transition_to(EventState.DATE_POLLING):
            raise ValidationError("Cannot start date poll in current state")
        
        # Create date options for next 30 days
        options = []
        today = date.today()
        
        for i in range(30):
            poll_date = today + timedelta(days=i + 1)  # Start from tomorrow
            # Skip Mondays and Tuesdays (common work days)
            if poll_date.weekday() not in [0, 1]:
                option = PollOption(
                    option_id=str(uuid.uuid4()),
                    label=poll_date.strftime("%A, %B %d"),
                    value=poll_date.isoformat()
                )
                options.append(option)
                
                # Limit to 20 options to fit in Discord buttons
                if len(options) >= 20:
                    break
        
        # Create date poll
        date_poll = Poll(
            poll_type=PollType.DATE,
            title=f"Select Date for {event.title}",
            description="Vote for your preferred date:",
            options=options,
            is_active=True,
            closes_at=datetime.utcnow() + timedelta(hours=24)  # 24 hour poll
        )
        
        # Add poll to event and transition state
        event.add_poll(date_poll)
        event.transition_to(EventState.DATE_POLLING)
        
        # Update in database
        await self.update_event(event)
        
        # Emit event
        await self.event_bus.emit(
            EventType.POLL_CREATED,
            {
                "event_id": str(event.id),
                "poll_type": PollType.DATE.value,
                "option_count": len(options)
            },
            source="events_cog",
            guild_id=event.guild_id
        )
    
    async def close_date_poll_and_start_time_poll(self, event: Event) -> None:
        """Close date poll and start time poll."""
        date_poll = event.get_poll(PollType.DATE)
        if not date_poll or not date_poll.is_active:
            raise ValidationError("No active date poll found")
        
        # Close date poll
        winner_option_id = date_poll.close_poll()
        if not winner_option_id:
            raise ValidationError("No votes in date poll")
        
        # Get winning date
        winner_option = date_poll.get_option_by_id(winner_option_id)
        selected_date = date.fromisoformat(winner_option.value)
        event.schedule.selected_date = selected_date
        
        # Create time options
        time_options = []
        base_times = [
            time(18, 0),  # 6:00 PM
            time(19, 0),  # 7:00 PM
            time(20, 0),  # 8:00 PM
            time(21, 0),  # 9:00 PM
        ]
        
        for t in base_times:
            option = PollOption(
                option_id=str(uuid.uuid4()),
                label=t.strftime("%I:%M %p"),
                value=t.isoformat()
            )
            time_options.append(option)
        
        # Create time poll
        time_poll = Poll(
            poll_type=PollType.TIME,
            title=f"Select Time for {event.title}",
            description=f"Date selected: {selected_date.strftime('%A, %B %d')}\n"
                       f"Now vote for your preferred time:",
            options=time_options,
            is_active=True,
            closes_at=datetime.utcnow() + timedelta(hours=12)  # 12 hour poll
        )
        
        # Add poll and transition
        event.add_poll(time_poll)
        event.transition_to(EventState.TIME_POLLING)
        
        # Update in database
        await self.update_event(event)
        
        # Emit events
        await self.event_bus.emit(
            EventType.POLL_COMPLETED,
            {
                "event_id": str(event.id),
                "poll_type": PollType.DATE.value,
                "winner_option_id": winner_option_id
            },
            source="events_cog",
            guild_id=event.guild_id
        )
        
        await self.event_bus.emit(
            EventType.POLL_CREATED,
            {
                "event_id": str(event.id),
                "poll_type": PollType.TIME.value,
                "option_count": len(time_options)
            },
            source="events_cog",
            guild_id=event.guild_id
        )
    
    async def close_time_poll_and_start_game_poll(self, event: Event) -> None:
        """Close time poll and start game poll."""
        time_poll = event.get_poll(PollType.TIME)
        if not time_poll or not time_poll.is_active:
            raise ValidationError("No active time poll found")
        
        # Close time poll
        winner_option_id = time_poll.close_poll()
        if not winner_option_id:
            raise ValidationError("No votes in time poll")
        
        # Get winning time
        winner_option = time_poll.get_option_by_id(winner_option_id)
        selected_time = time.fromisoformat(winner_option.value)
        event.schedule.selected_time = selected_time
        
        # Create game options (default popular games)
        game_options = []
        default_games = [
            "Among Us",
            "Jackbox Games",
            "Minecraft",
            "Fall Guys",
            "Rocket League",
            "Overwatch 2",
            "Valorant",
            "League of Legends",
            "Apex Legends",
            "Other (specify in chat)"
        ]
        
        for game in default_games:
            option = PollOption(
                option_id=str(uuid.uuid4()),
                label=game,
                value=game
            )
            game_options.append(option)
        
        # Create game poll
        game_poll = Poll(
            poll_type=PollType.GAME,
            title=f"Select Game for {event.title}",
            description=f"Date: {event.schedule.selected_date.strftime('%A, %B %d')}\n"
                       f"Time: {event.schedule.selected_time.strftime('%I:%M %p')}\n"
                       f"Vote for your preferred game:",
            options=game_options,
            is_active=True,
            is_multiple_choice=True,  # Allow multiple game selections
            closes_at=datetime.utcnow() + timedelta(hours=12)  # 12 hour poll
        )
        
        # Add poll and transition
        event.add_poll(game_poll)
        event.transition_to(EventState.GAME_POLLING)
        
        # Update in database
        await self.update_event(event)
        
        # Emit events
        await self.event_bus.emit(
            EventType.POLL_COMPLETED,
            {
                "event_id": str(event.id),
                "poll_type": PollType.TIME.value,
                "winner_option_id": winner_option_id
            },
            source="events_cog",
            guild_id=event.guild_id
        )
        
        await self.event_bus.emit(
            EventType.POLL_CREATED,
            {
                "event_id": str(event.id),
                "poll_type": PollType.GAME.value,
                "option_count": len(game_options)
            },
            source="events_cog",
            guild_id=event.guild_id
        )
    
    async def close_game_poll_and_schedule_event(self, event: Event) -> None:
        """Close game poll and schedule the event."""
        game_poll = event.get_poll(PollType.GAME)
        if not game_poll or not game_poll.is_active:
            raise ValidationError("No active game poll found")
        
        # Close game poll
        winner_option_id = game_poll.close_poll()
        if not winner_option_id:
            raise ValidationError("No votes in game poll")
        
        # Transition to scheduled
        event.transition_to(EventState.SCHEDULED)
        
        # Update in database
        await self.update_event(event)
        
        # Emit events
        await self.event_bus.emit(
            EventType.POLL_COMPLETED,
            {
                "event_id": str(event.id),
                "poll_type": PollType.GAME.value,
                "winner_option_id": winner_option_id
            },
            source="events_cog",
            guild_id=event.guild_id
        )
        
        await self.event_bus.emit(
            EventType.EVENT_UPDATED,
            {
                "event_id": str(event.id),
                "new_state": EventState.SCHEDULED.value,
                "title": event.title
            },
            source="events_cog",
            guild_id=event.guild_id
        )
        
        # Emit scheduled event for Discord integration
        await self.event_bus.emit(
            EventType.EVENT_SCHEDULED,
            {
                "event_id": str(event.id),
                "title": event.title,
                "scheduled_date": event.schedule.selected_date.isoformat() if event.schedule.selected_date else None,
                "scheduled_time": event.schedule.selected_time.isoformat() if event.schedule.selected_time else None,
                "timezone": event.schedule.timezone
            },
            source="events_cog",
            guild_id=event.guild_id
        )
    
    async def add_rsvp(
        self,
        event: Event,
        user_id: str,
        status: RSVPStatus,
        notes: Optional[str] = None
    ) -> None:
        """Add RSVP response to event."""
        if not event.is_active():
            raise ValidationError("Cannot RSVP to inactive event")
        
        # Add RSVP
        event.add_rsvp(user_id, status, notes)
        
        # Update in database
        await self.update_event(event)
        
        # Emit event
        await self.event_bus.emit(
            EventType.EVENT_UPDATED,
            {
                "event_id": str(event.id),
                "rsvp_user_id": user_id,
                "rsvp_status": status.value
            },
            source="events_cog",
            guild_id=event.guild_id,
            user_id=user_id
        )
    
    async def cancel_event(self, event: Event) -> None:
        """Cancel an event."""
        if not event.can_transition_to(EventState.CANCELLED):
            raise ValidationError("Cannot cancel event in current state")
        
        # Transition to cancelled
        event.transition_to(EventState.CANCELLED)
        
        # Close any active polls
        for poll in event.polls.values():
            if poll.is_active:
                poll.is_active = False
        
        # Update in database
        await self.update_event(event)
        
        # Emit event
        await self.event_bus.emit(
            EventType.EVENT_CANCELLED,
            {
                "event_id": str(event.id),
                "title": event.title
            },
            source="events_cog",
            guild_id=event.guild_id
        )
    
    async def validate_event_input(self, title: str, description: Optional[str] = None) -> tuple[str, Optional[str]]:
        """Validate and sanitize event input."""
        # Validate title
        if not title or not title.strip():
            raise ValidationError("Event title cannot be empty")
        
        title = self.validation.sanitize_text(title.strip(), 100)
        if len(title) < 3:
            raise ValidationError("Event title must be at least 3 characters long")
        
        # Validate description
        if description:
            description = self.validation.sanitize_text(description.strip(), 2000)
            if not description:  # If sanitization resulted in empty string
                description = None
        
        return title, description
    
    async def get_event_by_id(self, event_id: str) -> Optional[Event]:
        """Get event by ID with error handling."""
        try:
            return await self.get_event(event_id)
        except Exception as e:
            self.logger.error(f"Error retrieving event {event_id}: {e}")
            return None
    
    def create_event_embed(self, event: Event) -> discord.Embed:
        """Create Discord embed for event display."""
        # Choose color based on state
        color_map = {
            EventState.DRAFT: discord.Color.light_grey(),
            EventState.DATE_POLLING: discord.Color.blue(),
            EventState.TIME_POLLING: discord.Color.orange(),
            EventState.GAME_POLLING: discord.Color.purple(),
            EventState.SCHEDULED: discord.Color.green(),
            EventState.COMPLETED: discord.Color.dark_green(),
            EventState.CANCELLED: discord.Color.red()
        }
        
        embed = discord.Embed(
            title=f"🎮 {event.title}",
            description=event.description or "No description provided",
            color=color_map.get(event.state, discord.Color.default()),
            timestamp=datetime.utcnow()
        )
        
        # Add state information
        state_emoji = {
            EventState.DRAFT: "📝",
            EventState.DATE_POLLING: "📅",
            EventState.TIME_POLLING: "⏰",
            EventState.GAME_POLLING: "🎮",
            EventState.SCHEDULED: "✅",
            EventState.COMPLETED: "🏁",
            EventState.CANCELLED: "❌"
        }
        
        embed.add_field(
            name="Status",
            value=f"{state_emoji.get(event.state, '❓')} {event.state.value.replace('_', ' ').title()}",
            inline=True
        )
        
        # Add creator
        embed.add_field(
            name="Organizer",
            value=f"<@{event.creator_id}>",
            inline=True
        )
        
        # Add schedule if available
        if event.schedule.selected_date:
            schedule_text = event.schedule.selected_date.strftime("%A, %B %d, %Y")
            if event.schedule.selected_time:
                schedule_text += f" at {event.schedule.selected_time.strftime('%I:%M %p')}"
            
            embed.add_field(
                name="📅 Scheduled",
                value=schedule_text,
                inline=False
            )
        
        # Add RSVP counts
        yes_count = event.get_rsvp_count(RSVPStatus.YES)
        no_count = event.get_rsvp_count(RSVPStatus.NO)
        maybe_count = event.get_rsvp_count(RSVPStatus.MAYBE)
        
        embed.add_field(
            name="RSVPs",
            value=f"✅ {yes_count} Yes  ❌ {no_count} No  ❓ {maybe_count} Maybe",
            inline=False
        )
        
        # Add footer
        embed.set_footer(text=f"Event ID: {event.id}")
        
        return embed
    
    def create_poll_embed(self, poll: Poll, event: Event) -> discord.Embed:
        """Create Discord embed for poll display."""
        embed = discord.Embed(
            title=poll.title,
            description=poll.description,
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Add poll options with vote counts
        for option in poll.options:
            vote_bar = "█" * min(option.vote_count, 10)  # Visual vote bar
            embed.add_field(
                name=f"{option.label}",
                value=f"{vote_bar} ({option.vote_count} votes)",
                inline=False
            )
        
        # Add poll info
        total_votes = sum(opt.vote_count for opt in poll.options)
        embed.add_field(
            name="Poll Info",
            value=f"Total Votes: {total_votes}\n"
                  f"Multiple Choice: {'Yes' if poll.is_multiple_choice else 'No'}\n"
                  f"Status: {'Active' if poll.is_active else 'Closed'}",
            inline=True
        )
        
        if poll.closes_at:
            embed.add_field(
                name="Closes At",
                value=f"<t:{int(poll.closes_at.timestamp())}:R>",
                inline=True
            )
        
        embed.set_footer(text=f"Event: {event.title}")
        
        return embed
    
    @commands.slash_command(name="calendar", description="Export events to calendar file")
    async def export_calendar(
        self,
        ctx: discord.ApplicationContext,
        days_ahead: int = discord.Option(
            int,
            description="Number of days ahead to include (default: 30)",
            default=30,
            min_value=1,
            max_value=365
        )
    ):
        """Export scheduled events to an iCalendar (.ics) file."""
        try:
            await ctx.defer()
            
            # Get scheduled events for the guild
            from datetime import datetime, timedelta
            cutoff_date = datetime.utcnow() + timedelta(days=days_ahead)
            
            events_cursor = self.bot.database.events.find({
                'guild_id': str(ctx.guild.id),
                'state': EventState.SCHEDULED.value,
                'schedule.selected_date': {
                    '$gte': datetime.utcnow().date().isoformat(),
                    '$lte': cutoff_date.date().isoformat()
                }
            })
            
            events = []
            async for event_doc in events_cursor:
                events.append(Event(**event_doc))
            
            if not events:
                await ctx.followup.send(
                    f"❌ No scheduled events found in the next {days_ahead} days.",
                    ephemeral=True
                )
                return
            
            # Generate calendar content
            calendar_content = self.bot.discord_events.generate_calendar_export(events)
            
            # Create file
            import io
            calendar_file = io.BytesIO(calendar_content.encode('utf-8'))
            calendar_file.seek(0)
            
            filename = f"gamenight_events_{ctx.guild.name}_{datetime.utcnow().strftime('%Y%m%d')}.ics"
            discord_file = discord.File(calendar_file, filename=filename)
            
            embed = discord.Embed(
                title="📅 Calendar Export",
                description=f"Exported **{len(events)}** scheduled events from the next {days_ahead} days.",
                color=discord.Color.green()
            )
            embed.add_field(
                name="How to Use",
                value="Download the .ics file and import it into your calendar app (Google Calendar, Outlook, Apple Calendar, etc.)",
                inline=False
            )
            
            await ctx.followup.send(embed=embed, file=discord_file)
            
            # Log the export
            self.logger.info(
                f"Calendar export generated for guild {ctx.guild.id} by user {ctx.user.id}, "
                f"{len(events)} events, {days_ahead} days ahead"
            )
            
        except Exception as e:
            self.logger.error(f"Error exporting calendar: {e}", exc_info=True)
            await ctx.followup.send(
                "❌ An error occurred while generating the calendar export.",
                ephemeral=True
            )
    
    async def sync_discord_rsvps(self, event: Event) -> int:
        """Sync RSVPs from Discord scheduled event to bot event."""
        if not self.bot.discord_events:
            return 0
        
        return await self.bot.discord_events.sync_rsvps_from_discord(event)
    
    @commands.slash_command(name="sync-rsvps", description="Manually sync RSVPs from Discord scheduled event")
    @require_permission(Permission.MANAGE_EVENTS)
    async def sync_rsvps_command(
        self,
        ctx: discord.ApplicationContext,
        event_id: str = discord.Option(
            str,
            description="Event ID to sync RSVPs for"
        )
    ):
        """Manually sync RSVPs from Discord scheduled event."""
        try:
            await ctx.defer(ephemeral=True)
            
            # Get the event
            event = await self.get_event(event_id)
            if not event:
                await ctx.followup.send("❌ Event not found.", ephemeral=True)
                return
            
            if event.guild_id != str(ctx.guild.id):
                await ctx.followup.send("❌ Event not found in this server.", ephemeral=True)
                return
            
            if not event.discord_event_id:
                await ctx.followup.send("❌ This event is not linked to a Discord scheduled event.", ephemeral=True)
                return
            
            # Sync RSVPs
            synced_count = await self.sync_discord_rsvps(event)
            
            if synced_count > 0:
                await ctx.followup.send(
                    f"✅ Synced **{synced_count}** RSVPs from Discord scheduled event.",
                    ephemeral=True
                )
            else:
                await ctx.followup.send(
                    "ℹ️ No new RSVPs to sync from Discord scheduled event.",
                    ephemeral=True
                )
            
        except Exception as e:
            self.logger.error(f"Error syncing RSVPs: {e}", exc_info=True)
            await ctx.followup.send(
                "❌ An error occurred while syncing RSVPs.",
                ephemeral=True
            )
    
    @commands.slash_command(name="retry-discord-event", description="Retry creating Discord scheduled event")
    @require_permission(Permission.MANAGE_EVENTS)
    async def retry_discord_event(
        self,
        ctx: discord.ApplicationContext,
        event_id: str = discord.Option(
            str,
            description="Event ID to retry Discord event creation for"
        )
    ):
        """Retry creating a Discord scheduled event for a bot event."""
        try:
            await ctx.defer(ephemeral=True)
            
            # Get the event
            event = await self.get_event(event_id)
            if not event:
                await ctx.followup.send("❌ Event not found.", ephemeral=True)
                return
            
            if event.guild_id != str(ctx.guild.id):
                await ctx.followup.send("❌ Event not found in this server.", ephemeral=True)
                return
            
            if not event.is_scheduled():
                await ctx.followup.send("❌ Event must be scheduled before creating Discord event.", ephemeral=True)
                return
            
            if event.discord_event_id:
                await ctx.followup.send("❌ Event already has a Discord scheduled event.", ephemeral=True)
                return
            
            # Attempt to create Discord event
            if not self.bot.discord_events:
                await ctx.followup.send("❌ Discord events integration not available.", ephemeral=True)
                return
            
            discord_event_id = await self.bot.discord_events.create_discord_event(event)
            
            if discord_event_id:
                await ctx.followup.send(
                    f"✅ Successfully created Discord scheduled event for **{event.title}**.",
                    ephemeral=True
                )
            else:
                await ctx.followup.send(
                    f"❌ Failed to create Discord scheduled event for **{event.title}**. Check logs for details.",
                    ephemeral=True
                )
            
        except Exception as e:
            self.logger.error(f"Error retrying Discord event creation: {e}", exc_info=True)
            await ctx.followup.send(
                "❌ An error occurred while retrying Discord event creation.",
                ephemeral=True
            )


async def setup(bot):
    """Set up the Events cog."""
    await bot.add_cog(EventsCog(bot))    
  
  # Enhanced poll management methods
    
    async def start_enhanced_date_poll(self, event: Event, custom_options: Optional[Dict[str, Any]] = None) -> None:
        """Start enhanced date polling with timeout management."""
        if not event.can_transition_to(EventState.DATE_POLLING):
            raise ValidationError("Cannot start date poll in current state")
        
        # Generate date options (next 30 days, excluding weekdays if configured)
        date_options = self._generate_date_options()
        
        # Create poll using poll manager
        poll = await self.poll_manager.create_poll_with_timeout(
            event=event,
            poll_type=PollType.DATE,
            title="Select Event Date",
            options=date_options,
            timeout_minutes=custom_options.get('timeout_minutes') if custom_options else None,
            custom_options=custom_options
        )
        
        # Transition event state
        event.transition_to(EventState.DATE_POLLING)
        
        # Update in database
        await self.update_event(event)
        
        # Emit event
        await self.event_bus.emit(
            EventType.EVENT_STATE_CHANGED,
            {
                "event_id": str(event.id),
                "old_state": EventState.DRAFT.value,
                "new_state": EventState.DATE_POLLING.value
            },
            source="events_cog",
            guild_id=event.guild_id
        )
    
    async def start_enhanced_time_poll(self, event: Event, selected_date: date, custom_options: Optional[Dict[str, Any]] = None) -> None:
        """Start enhanced time polling with custom options."""
        if not event.can_transition_to(EventState.TIME_POLLING):
            raise ValidationError("Cannot start time poll in current state")
        
        # Generate time options
        time_options = self._generate_time_options(selected_date)
        
        # Create poll using poll manager
        poll = await self.poll_manager.create_poll_with_timeout(
            event=event,
            poll_type=PollType.TIME,
            title="Select Event Time",
            options=time_options,
            timeout_minutes=custom_options.get('timeout_minutes') if custom_options else None,
            is_multiple_choice=True,  # Allow multiple time preferences
            custom_options=custom_options
        )
        
        # Set selected date
        event.schedule.selected_date = selected_date
        
        # Transition event state
        event.transition_to(EventState.TIME_POLLING)
        
        # Update in database
        await self.update_event(event)
        
        # Emit event
        await self.event_bus.emit(
            EventType.EVENT_STATE_CHANGED,
            {
                "event_id": str(event.id),
                "old_state": EventState.DATE_POLLING.value,
                "new_state": EventState.TIME_POLLING.value,
                "selected_date": selected_date.isoformat()
            },
            source="events_cog",
            guild_id=event.guild_id
        )
    
    async def start_enhanced_game_poll(self, event: Event, selected_time: time, custom_options: Optional[Dict[str, Any]] = None) -> None:
        """Start enhanced game polling with custom games."""
        if not event.can_transition_to(EventState.GAME_POLLING):
            raise ValidationError("Cannot start game poll in current state")
        
        # Generate game options (popular games + custom options)
        game_options = await self._generate_game_options(event.guild_id, custom_options)
        
        # Create poll using poll manager
        poll = await self.poll_manager.create_poll_with_timeout(
            event=event,
            poll_type=PollType.GAME,
            title="Select Games to Play",
            options=game_options,
            timeout_minutes=custom_options.get('timeout_minutes') if custom_options else None,
            is_multiple_choice=True,  # Allow multiple game selections
            custom_options=custom_options
        )
        
        # Set selected time
        event.schedule.selected_time = selected_time
        
        # Transition event state
        event.transition_to(EventState.GAME_POLLING)
        
        # Update in database
        await self.update_event(event)
        
        # Emit event
        await self.event_bus.emit(
            EventType.EVENT_STATE_CHANGED,
            {
                "event_id": str(event.id),
                "old_state": EventState.TIME_POLLING.value,
                "new_state": EventState.GAME_POLLING.value,
                "selected_time": selected_time.isoformat()
            },
            source="events_cog",
            guild_id=event.guild_id
        )
    
    def _generate_date_options(self) -> List[Dict[str, Any]]:
        """Generate date options for the next 30 days."""
        from datetime import date, timedelta
        
        options = []
        today = date.today()
        
        for i in range(1, 31):  # Next 30 days
            option_date = today + timedelta(days=i)
            
            # Skip Mondays and Tuesdays (common work days) unless it's a holiday
            if option_date.weekday() in [0, 1]:  # Monday = 0, Tuesday = 1
                continue
            
            label = option_date.strftime("%A, %B %d")
            options.append({
                'label': label,
                'value': option_date
            })
        
        return options[:20]  # Limit to 20 options for UI constraints
    
    def _generate_time_options(self, selected_date: date) -> List[Dict[str, Any]]:
        """Generate time options for the selected date."""
        from datetime import time
        
        options = []
        
        # Common gaming times (evening focus)
        common_times = [
            (17, 0),   # 5:00 PM
            (17, 30),  # 5:30 PM
            (18, 0),   # 6:00 PM
            (18, 30),  # 6:30 PM
            (19, 0),   # 7:00 PM
            (19, 30),  # 7:30 PM
            (20, 0),   # 8:00 PM
            (20, 30),  # 8:30 PM
            (21, 0),   # 9:00 PM
            (21, 30),  # 9:30 PM
        ]
        
        # Weekend times (include afternoon)
        if selected_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
            weekend_times = [
                (14, 0),   # 2:00 PM
                (14, 30),  # 2:30 PM
                (15, 0),   # 3:00 PM
                (15, 30),  # 3:30 PM
                (16, 0),   # 4:00 PM
                (16, 30),  # 4:30 PM
            ]
            common_times = weekend_times + common_times
        
        for hour, minute in common_times:
            time_obj = time(hour, minute)
            label = time_obj.strftime("%I:%M %p").lstrip('0')
            options.append({
                'label': label,
                'value': time_obj
            })
        
        return options
    
    async def _generate_game_options(self, guild_id: str, custom_options: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Generate game options based on guild preferences and popular games."""
        options = []
        
        # Default popular games
        popular_games = [
            "Among Us",
            "Jackbox Games",
            "Fall Guys",
            "Rocket League",
            "Minecraft",
            "Valorant",
            "League of Legends",
            "Overwatch 2",
            "Apex Legends",
            "Gartic Phone"
        ]
        
        # Add popular games
        for game in popular_games:
            options.append({
                'label': game,
                'value': game
            })
        
        # Add custom games if provided
        if custom_options and 'additional_games' in custom_options:
            for game in custom_options['additional_games']:
                options.append({
                    'label': game,
                    'value': game
                })
        
        # TODO: In a full implementation, this would query the database for:
        # - Guild-specific popular games
        # - User game interests
        # - Recently played games
        
        return options[:25]  # Discord dropdown limit
    
    def create_enhanced_poll_embed(self, poll: Poll, event: Event) -> discord.Embed:
        """Create enhanced embed for poll display with analytics."""
        poll_type_info = {
            PollType.DATE: {"emoji": "📅", "color": discord.Color.blue()},
            PollType.TIME: {"emoji": "⏰", "color": discord.Color.green()},
            PollType.GAME: {"emoji": "🎮", "color": discord.Color.purple()}
        }
        
        info = poll_type_info.get(poll.poll_type, {"emoji": "📊", "color": discord.Color.grey()})
        
        embed = discord.Embed(
            title=f"{info['emoji']} {poll.title}",
            description=poll.description or f"Vote for your preferred {poll.poll_type.value.lower()}!",
            color=info["color"],
            timestamp=datetime.utcnow()
        )
        
        # Add event info
        embed.add_field(
            name="Event",
            value=event.title,
            inline=True
        )
        
        # Add poll status
        status = "🟢 Active" if poll.is_active else "🔴 Closed"
        embed.add_field(
            name="Status",
            value=status,
            inline=True
        )
        
        # Add closing time if available
        if poll.closes_at:
            embed.add_field(
                name="Closes",
                value=f"<t:{int(poll.closes_at.timestamp())}:R>",
                inline=True
            )
        
        # Add options with vote counts
        if poll.options:
            total_votes = sum(opt.vote_count for opt in poll.options)
            
            options_text = []
            for i, option in enumerate(poll.options[:10]):  # Limit display
                percentage = (option.vote_count / total_votes * 100) if total_votes > 0 else 0
                bar_length = int(percentage / 10)  # 10% per bar segment
                bar = "█" * bar_length + "░" * (10 - bar_length)
                
                options_text.append(
                    f"**{option.label}**\n"
                    f"{bar} {option.vote_count} votes ({percentage:.1f}%)"
                )
            
            embed.add_field(
                name=f"Options ({len(poll.options)} total)",
                value="\n\n".join(options_text) if options_text else "No options available",
                inline=False
            )
            
            # Add participation info
            unique_voters = len(set(user_id for opt in poll.options for user_id in opt.votes))
            embed.add_field(
                name="Participation",
                value=f"{unique_voters} voters, {total_votes} total votes",
                inline=True
            )
        
        # Add footer with poll type
        embed.set_footer(text=f"{poll.poll_type.value.title()} Poll • Event ID: {event.id}")
        
        return embed
    
    async def get_poll_analytics_summary(self, event_id: str, poll_type: PollType) -> Optional[Dict[str, Any]]:
        """Get analytics summary for a poll."""
        return self.poll_manager.get_poll_analytics(event_id, poll_type)
    
    @commands.slash_command(name="poll-extend", description="Extend an active poll")
    @require_permission(Permission.MANAGE_EVENTS)
    async def extend_poll_command(
        self, 
        interaction: discord.Interaction, 
        event_id: str, 
        poll_type: str,
        minutes: int = 15
    ):
        """Extend an active poll by specified minutes."""
        try:
            # Validate poll type
            try:
                poll_type_enum = PollType(poll_type.upper())
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid poll type. Use: DATE, TIME, or GAME",
                    ephemeral=True
                )
                return
            
            # Get event
            event = await self.get_event_by_id(event_id)
            if not event:
                await interaction.response.send_message(
                    "❌ Event not found.",
                    ephemeral=True
                )
                return
            
            # Check permissions
            if not await self.can_manage_event(interaction.user, event):
                await interaction.response.send_message(
                    "❌ You don't have permission to manage this event.",
                    ephemeral=True
                )
                return
            
            # Get poll
            poll = event.get_poll(poll_type_enum)
            if not poll or not poll.is_active:
                await interaction.response.send_message(
                    f"❌ No active {poll_type_enum.value.lower()} poll found.",
                    ephemeral=True
                )
                return
            
            # Extend poll
            await self.poll_manager._extend_poll_voting(event, poll)
            
            await interaction.response.send_message(
                f"⏰ {poll_type_enum.value.title()} poll extended by {minutes} minutes!",
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error extending poll: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while extending the poll.",
                ephemeral=True
            )
    
    @commands.slash_command(name="poll-analytics", description="View poll analytics")
    @require_permission(Permission.VIEW_ANALYTICS)
    async def poll_analytics_command(
        self, 
        interaction: discord.Interaction, 
        event_id: str, 
        poll_type: str
    ):
        """View analytics for a poll."""
        try:
            # Validate poll type
            try:
                poll_type_enum = PollType(poll_type.upper())
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid poll type. Use: DATE, TIME, or GAME",
                    ephemeral=True
                )
                return
            
            # Get analytics
            analytics = await self.get_poll_analytics_summary(event_id, poll_type_enum)
            if not analytics:
                await interaction.response.send_message(
                    "❌ No analytics data found for this poll.",
                    ephemeral=True
                )
                return
            
            # Create analytics embed
            embed = discord.Embed(
                title=f"📊 {poll_type_enum.value.title()} Poll Analytics",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="Participation",
                value=f"**{analytics['unique_voters']}** unique voters\n"
                      f"**{analytics['total_votes']}** total votes\n"
                      f"**{analytics['vote_changes']}** vote changes",
                inline=True
            )
            
            embed.add_field(
                name="Timing",
                value=f"**{analytics['average_time_to_vote_seconds']:.1f}s** avg. time to vote",
                inline=True
            )
            
            embed.set_footer(text=f"Event ID: {event_id}")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error getting poll analytics: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while retrieving analytics.",
                ephemeral=True
            )