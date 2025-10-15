"""
Events cog for managing game night events with interactive polls and RSVP tracking.
"""

import asyncio
from datetime import datetime, date, time, timedelta
from typing import Optional, List, Dict, Any
import uuid

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

from models.event import Event, EventState, Poll, RSVPStatus, PollType, PollOption
from core.event_bus import EventBus, EventType
from core.simple_permissions import require_permission_simple
# from core.permission_decorators import require_permission  # Temporarily disabled
from core.security_manager import Permission
from core.validation_manager import ValidationManager
from core.poll_manager import PollManager
# Removed poll_notifications module during cleanup
from views.enhanced_poll_views import (
    EnhancedDatePollView, EnhancedTimePollView, TieResolutionView,
    PersistentPollView
)
from utils.exceptions import ValidationError, PermissionDeniedError, ErrorCode, PollTieError
from utils.logging_config import get_logger, LoggerMixin


class EventCreationModal(discord.ui.Modal):
    """Modal for event creation with title and description inputs."""
    
    def __init__(self, cog: 'EventsCog'):
        super().__init__(title="Create New Game Night Event")
        self.cog = cog
        cog.logger.info("EventCreationModal __init__ called")
        
        # Event title input
        self.title_input = discord.ui.InputText(
            label="Event Title",
            placeholder="Enter a title for your game night...",
            min_length=3,
            max_length=100,
            required=True
        )
        self.add_item(self.title_input)
        
        # Event description input (simplified - no paragraph style for now)
        self.description_input = discord.ui.InputText(
            label="Event Description",
            placeholder="Describe your game night (optional)...",
            max_length=500,  # Reduced length
            required=False
        )
        self.add_item(self.description_input)
    

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        self.cog.logger.info("=== MODAL SUBMISSION START ===")
        self.cog.logger.info(f"Title: {self.title_input.value}")
        self.cog.logger.info(f"Description: {self.description_input.value}")
        self.cog.logger.info(f"User: {interaction.user.id}")
        self.cog.logger.info(f"Guild: {interaction.guild.id}")
        
        try:
            # Create Event object with DRAFT state
            event = Event(
                guild_id=str(interaction.guild.id),
                title=self.title_input.value,
                description=self.description_input.value or None,
                creator_id=str(interaction.user.id),
                state=EventState.DRAFT
            )
            
            # Validate the event
            event.validate_data()
            
            # Store in MongoDB events collection
            try:
                # Convert to dict using by_alias=False to get snake_case field names
                # Use mode='python' to keep datetime objects as datetime (not ISO strings)
                event_dict = event.model_dump(
                    by_alias=False,
                    exclude_none=False,
                    mode='python'
                )
                
                # Remove the id field if it's None to let MongoDB generate it
                if event_dict.get('id') is None:
                    event_dict.pop('id', None)
                
                event_id = await self.cog.bot.database.insert_one('events', event_dict)
                self.cog.logger.info(f"Event saved to database with ID: {event_id}")
                
                # Send confirmation message with event ID
                await interaction.response.send_message(
                    f"✅ **Event Created Successfully!**\n\n"
                    f"**Event ID:** `{event_id}`\n"
                    f"**Title:** {self.title_input.value}\n"
                    f"**Description:** {self.description_input.value or 'No description provided'}\n"
                    f"**State:** DRAFT\n\n"
                    f"🎮 Your game night event has been created and saved!",
                    ephemeral=True
                )
                self.cog.logger.info("Event creation response sent successfully")
                
            except Exception as db_error:
                self.cog.logger.error(f"Database error while saving event: {db_error}", exc_info=True)
                await interaction.response.send_message(
                    f"❌ Failed to save event to database. Please try again or contact an administrator.",
                    ephemeral=True
                )
            
        except ValidationError as ve:
            self.cog.logger.error(f"Validation error in modal submission: {ve}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Invalid event data: {str(ve)}",
                ephemeral=True
            )
        except Exception as e:
            self.cog.logger.error(f"Error in modal submission: {e}", exc_info=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"❌ Something went wrong creating your event. Please try again.",
                        ephemeral=True
                    )
            except Exception as response_error:
                self.cog.logger.error(f"Failed to send error response: {response_error}")
        
        self.cog.logger.info("=== MODAL SUBMISSION END ===")
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """Handle modal errors."""
        print(f"MODAL ERROR DETECTED: {error}")
        self.cog.logger.error(f"Modal error detected: {error}", exc_info=True)
        self.cog.logger.error(f"Error type: {type(error)}")
        self.cog.logger.error(f"Error args: {error.args}")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ Modal error: {error}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Modal error: {error}",
                    ephemeral=True
                )
        except Exception as e:
            self.cog.logger.error(f"Failed to send modal error message: {e}")


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
        
        # Add votes for selected options (directly to options, bypassing poll.add_vote)
        votes_added = 0
        for option_id in self.values:
            for option in view.poll.options:
                if option.option_id == option_id:
                    if option.add_vote(user_id):
                        votes_added += 1
                    break
        
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
                "❌ Something went wrong. Please try again or contact an administrator if the issue persists.",
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
            
        except PollTieError as tie_error:
            # Handle tie - show tie resolution view
            date_poll = view.event.get_poll(PollType.DATE)
            tied_options = [date_poll.get_option_by_id(opt_id) for opt_id in tie_error.tied_options]
            tied_options = [opt for opt in tied_options if opt]  # Filter out None
            
            tie_view = TieResolutionView(view.cog, view.event, date_poll, tied_options)
            
            await interaction.response.send_message(
                f"🤝 **Tie Detected!**\n\n"
                f"The date poll resulted in a tie between {len(tied_options)} options.\n"
                f"Please select the winning option:",
                view=tie_view,
                ephemeral=True
            )
            
        except Exception as e:
            view.cog.logger.error(f"Error closing date poll: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ Something went wrong. Please try again or contact an administrator if the issue persists.",
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
            
        except PollTieError as tie_error:
            # Handle tie - show tie resolution view
            time_poll = view.event.get_poll(PollType.TIME)
            tied_options = [time_poll.get_option_by_id(opt_id) for opt_id in tie_error.tied_options]
            tied_options = [opt for opt in tied_options if opt]  # Filter out None
            
            tie_view = TieResolutionView(view.cog, view.event, time_poll, tied_options)
            
            await interaction.response.send_message(
                f"🤝 **Tie Detected!**\n\n"
                f"The time poll resulted in a tie between {len(tied_options)} options.\n"
                f"Please select the winning option:",
                view=tie_view,
                ephemeral=True
            )
            
        except Exception as e:
            view.cog.logger.error(f"Error closing time poll: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ Something went wrong. Please try again or contact an administrator if the issue persists.",
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
            
        except PollTieError as tie_error:
            # Handle tie - show tie resolution view
            game_poll = view.event.get_poll(PollType.GAME)
            tied_options = [game_poll.get_option_by_id(opt_id) for opt_id in tie_error.tied_options]
            tied_options = [opt for opt in tied_options if opt]  # Filter out None
            
            tie_view = TieResolutionView(view.cog, view.event, game_poll, tied_options)
            
            await interaction.response.send_message(
                f"🤝 **Tie Detected!**\n\n"
                f"The game poll resulted in a tie between {len(tied_options)} options.\n"
                f"Please select the winning option:",
                view=tie_view,
                ephemeral=True
            )
            
        except Exception as e:
            view.cog.logger.error(f"Error closing game poll: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ Something went wrong. Please try again or contact an administrator if the issue persists.",
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
        
        # Store the message reference in the view for later updates
        if not hasattr(view, 'message'):
            view.message = interaction.message
        
        # Open RSVP modal with parent view reference
        modal = RSVPModal(view.cog, view.event, parent_view=view)
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
        
        # Simple confirmation for event cancellation
        confirmation_view = ConfirmCancelView(view.cog, view.event)
        await interaction.response.send_message(
            f"⚠️ Are you sure you want to cancel **{view.event.title}**?\n"
            f"This action cannot be undone and all participants will be notified.",
            view=confirmation_view,
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
                content="❌ Something went wrong. Please try again or contact an administrator if the issue persists.",
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
    
    def __init__(self, cog: 'EventsCog', event: Event, parent_view: Optional['EventManagementView'] = None):
        super().__init__(title=f"RSVP for {event.title}")
        self.cog = cog
        self.event = event
        self.parent_view = parent_view
        
        # RSVP status selection
        self.status_input = discord.ui.InputText(
            label="Response (YES/NO/MAYBE)",
            placeholder="Enter YES, NO, or MAYBE",
            min_length=2,
            max_length=5,
            required=True
        )
        self.add_item(self.status_input)
        
        # Optional notes
        self.notes_input = discord.ui.InputText(
            label="Notes (Optional)",
            placeholder="Any additional notes...",
            style=discord.InputTextStyle.paragraph,
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
            
            # Get updated event
            updated_event = await self.cog.get_event(self.event.id)
            
            # Update the parent message if we have access to it
            if self.parent_view and hasattr(self.parent_view, 'message') and self.parent_view.message:
                try:
                    embed = self.cog.create_event_embed(updated_event)
                    # Update parent view with new event data
                    self.parent_view.event = updated_event
                    await self.parent_view.message.edit(embed=embed, view=self.parent_view)
                except Exception as e:
                    self.cog.logger.warning(f"Could not update event message: {e}")
            
            status_emoji = {"YES": "✅", "NO": "❌", "MAYBE": "❓"}[status_text]
            await interaction.response.send_message(
                f"{status_emoji} RSVP recorded for **{self.event.title}**: {status_text}\n"
                f"✅ Yes: {updated_event.get_rsvp_count(RSVPStatus.YES)} | "
                f"❌ No: {updated_event.get_rsvp_count(RSVPStatus.NO)} | "
                f"❓ Maybe: {updated_event.get_rsvp_count(RSVPStatus.MAYBE)}",
                ephemeral=True
            )
            
        except Exception as e:
            self.cog.logger.error(f"Error processing RSVP: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ Something went wrong. Please try again or contact an administrator if the issue persists.",
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
        # Removed poll_notifications during cleanup
        
        # Debug logging for cog initialization
        self.logger.info("EventsCog initialized successfully")
        self.logger.info(f"Bot instance: {type(bot)}")
        self.logger.info(f"Validation manager: {type(self.validation)}")
        self.logger.info(f"Event bus: {type(self.event_bus)}")
        self.logger.info(f"Poll manager: {type(self.poll_manager)}")
        
        # Simplified initialization - removed complex UX systems during cleanup
        
        # Subscribe to relevant events (commented out for now to avoid initialization issues)
        # self.event_bus.subscribe(EventType.SYSTEM_STARTUP, self._on_startup)
        # self.event_bus.subscribe(EventType.POLL_COMPLETED, self._on_poll_completed)
        # self.event_bus.subscribe(EventType.POLL_EXPIRED, self._on_poll_expired)
    
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
    
    # Event creation command - now working!
    @commands.slash_command(
        name="event", 
        description="Create a new game night event with interactive polls",
        guild_ids=[650597555872464896, 1328565530596212767]  # Same as working /events command
    )
    async def create_event_command(self, interaction: discord.Interaction):
        """Create a new game night event with interactive scheduling polls."""
        self.logger.info("=== CREATE EVENT COMMAND START ===")
        try:
            self.logger.info("Creating EventCreationModal...")
            modal = EventCreationModal(self)
            self.logger.info("Modal created successfully")
            
            self.logger.info("Sending modal to user...")
            await interaction.response.send_modal(modal)
            self.logger.info("Modal sent successfully")
            
        except Exception as e:
            self.logger.error(f"Error in create_event_command: {e}", exc_info=True)
            try:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
            except:
                await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
    
    # Alternative: Simple command with parameters (backup if modal doesn't work)
    @commands.slash_command(
        name="create-event", 
        description="Create a new game night event (simple version)",
        guild_ids=[650597555872464896, 1328565530596212767]
    )
    async def create_event_simple(
        self, 
        interaction: discord.Interaction,
        title: str,
        description: str = None
    ):
        """Create a new game night event using command parameters."""
        try:
            await interaction.response.send_message(
                f"✅ **Event Created Successfully!**\n\n"
                f"**Title:** {title}\n"
                f"**Description:** {description or 'No description provided'}\n\n"
                f"🎮 Your game night event has been created!",
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"Error in create_event_simple: {e}", exc_info=True)
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
    
    @commands.slash_command(
        name="events", 
        description="List all active events in this server",
        guild_ids=[650597555872464896, 1328565530596212767]  # Add your guild IDs for faster sync
    )
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
                "❌ Something went wrong. Please try again or contact an administrator if the issue persists.",
                ephemeral=True
            )
    
    @commands.slash_command(
        name="start-date-poll", 
        description="Start date poll for an event",
        guild_ids=[650597555872464896, 1328565530596212767]
    )
    async def start_date_poll_command(self, interaction: discord.Interaction, event_id: str):
        """Start date polling for an event."""
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
            
            # Start date poll
            await self.start_date_poll(event)
            
            # Get updated event and poll
            updated_event = await self.get_event(event.id)
            date_poll = updated_event.get_poll(PollType.DATE)
            
            # Create poll embed and view
            embed = self.create_poll_embed(date_poll, updated_event)
            poll_view = DatePollView(self, updated_event, date_poll)
            
            await interaction.response.send_message(
                content=f"📅 **Date Poll Started for {updated_event.title}**\n"
                        f"Vote for your preferred date:",
                embed=embed,
                view=poll_view
            )
            
        except ValidationError as ve:
            await interaction.response.send_message(
                f"❌ {str(ve)}",
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"Error starting date poll: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ Something went wrong. Please try again or contact an administrator if the issue persists.",
                ephemeral=True
            )
    
    @commands.slash_command(
        name="event-manage", 
        description="Manage a specific event (admin only)",
        guild_ids=[650597555872464896, 1328565530596212767]  # Add your guild IDs for faster sync
    )
    # @require_permission(Permission.MANAGE_EVENTS)  # Temporarily disabled
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
                "❌ Something went wrong. Please try again or contact an administrator if the issue persists.",
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
            result = await self.bot.database.find_one('events', {"_id": ObjectId(event_id)})
            if result:
                # Convert _id to id for Pydantic model
                if '_id' in result:
                    result['id'] = str(result['_id'])
                return Event(**result)
            return None
        except Exception as e:
            self.logger.error(f"Error getting event {event_id}: {e}", exc_info=True)
            return None
    
    async def update_event(self, event: Event) -> bool:
        """Update event in database."""
        try:
            # Skip update if event doesn't have an ID (not saved yet)
            if not event.id:
                self.logger.warning("Attempted to update event without ID")
                return False
            
            # Update timestamp
            event.update_timestamp()
            
            from bson import ObjectId
            # Convert event to dict for database storage
            event_dict = event.model_dump(by_alias=False, exclude_none=False, mode='python')
            
            # Remove id field and use _id for MongoDB
            event_id = event_dict.pop('id', None)
            if event_id:
                event_dict['_id'] = ObjectId(str(event_id))
            
            # Use update_one with $set to update the document
            result = await self.bot.database.update_one(
                'events',
                {"_id": ObjectId(str(event.id))},
                {"$set": event_dict}
            )
            return result
        except Exception as e:
            self.logger.error(f"Error updating event {event.id}: {e}", exc_info=True)
            return False
    
    async def get_guild_events(self, guild_id: str, active_only: bool = True) -> List[Event]:
        """Get events for a guild."""
        try:
            query = {"guild_id": guild_id}
            if active_only:
                query["state"] = {"$nin": [EventState.COMPLETED.value, EventState.CANCELLED.value]}
            
            # Use database manager's find_many method
            docs = await self.bot.database.find_many(
                'events',
                query,
                sort=[("created_at", -1)]
            )
            
            events = []
            for doc in docs:
                # Convert _id to id for Pydantic model
                if '_id' in doc:
                    doc['id'] = str(doc['_id'])
                events.append(Event(**doc))
            return events
        except Exception as e:
            self.logger.error(f"Error getting guild events: {e}", exc_info=True)
            return []
    
    async def create_discord_scheduled_event(self, event: Event, max_retries: int = 3) -> Optional[str]:
        """
        Create a Discord scheduled event with retry logic.
        
        Args:
            event: The event to create a Discord scheduled event for
            max_retries: Maximum number of retry attempts
            
        Returns:
            Discord event ID if successful, None otherwise
            
        Raises:
            ValidationError: If event data is invalid
        """
        import asyncio
        from datetime import datetime, timedelta
        
        # Validate that we have all required data
        if not event.scheduled_date or not event.scheduled_time:
            raise ValidationError("Event must have both date and time set")
        
        # Get the guild
        guild = self.bot.get_guild(int(event.guild_id))
        if not guild:
            self.logger.error(f"Guild {event.guild_id} not found")
            return None
        
        # Combine date and time into a datetime
        event_datetime = datetime.combine(event.scheduled_date, event.scheduled_time)
        
        # Calculate end time (default to 3 hours later)
        end_datetime = event_datetime + timedelta(hours=3)
        
        # Get game names from game poll if available
        game_poll = event.get_poll(PollType.GAME)
        game_names = []
        if game_poll:
            winning_options = game_poll.get_winning_options()
            game_names = [opt.label for opt in winning_options if opt.vote_count > 0]
        
        # Build description
        description = event.description or ""
        if game_names:
            description += f"\n\n🎮 Games: {', '.join(game_names)}"
        
        # Truncate description to Discord's limit (1000 characters)
        if len(description) > 1000:
            description = description[:997] + "..."
        
        # Retry logic with exponential backoff
        last_error = None
        for attempt in range(max_retries):
            try:
                self.logger.info(f"Creating Discord scheduled event (attempt {attempt + 1}/{max_retries})")
                
                # Create the scheduled event
                scheduled_event = await guild.create_scheduled_event(
                    name=event.title[:100],  # Discord limit is 100 characters
                    description=description,
                    start_time=event_datetime,
                    end_time=end_datetime,
                    entity_type=discord.ScheduledEventLocationType.external,
                    location="Discord"
                )
                
                self.logger.info(f"Successfully created Discord scheduled event: {scheduled_event.id}")
                return str(scheduled_event.id)
                
            except discord.HTTPException as e:
                last_error = e
                self.logger.warning(f"Discord API error on attempt {attempt + 1}: {e}")
                
                # Check if it's a rate limit error
                if e.status == 429:
                    retry_after = getattr(e, 'retry_after', None) or (2 ** attempt)
                    self.logger.info(f"Rate limited, waiting {retry_after} seconds")
                    await asyncio.sleep(retry_after)
                else:
                    # Exponential backoff for other errors
                    wait_time = 2 ** attempt
                    self.logger.info(f"Waiting {wait_time} seconds before retry")
                    await asyncio.sleep(wait_time)
                    
            except Exception as e:
                last_error = e
                self.logger.error(f"Unexpected error creating Discord event: {e}", exc_info=True)
                
                # Exponential backoff
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
        
        # All retries failed
        self.logger.error(f"Failed to create Discord scheduled event after {max_retries} attempts: {last_error}")
        
        # Emit event for admin notification
        await self.event_bus.emit(
            EventType.SYSTEM_ERROR,
            {
                "error_type": "discord_event_creation_failed",
                "event_id": str(event.id),
                "event_title": event.title,
                "error_message": str(last_error),
                "attempts": max_retries
            },
            guild_id=event.guild_id
        )
        
        return None
    
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
    
    async def cancel_event(self, event: Event) -> bool:
        """
        Cancel an event and notify all participants.
        
        This method:
        1. Deletes the Discord scheduled event if it exists
        2. Updates the event state to CANCELLED
        3. Notifies all participants who RSVP'd
        
        Args:
            event: The event to cancel
            
        Returns:
            True if cancellation was successful, False otherwise
        """
        try:
            self.logger.info(f"Cancelling event {event.id}: {event.title}")
            
            # Check if event can be cancelled
            if not event.can_transition_to(EventState.CANCELLED):
                self.logger.warning(f"Event {event.id} cannot be cancelled from state {event.state}")
                return False
            
            # Delete Discord scheduled event if it exists
            if event.discord_event_id:
                try:
                    guild = self.bot.get_guild(int(event.guild_id))
                    if guild:
                        # Get the scheduled event
                        scheduled_event = await guild.fetch_scheduled_event(int(event.discord_event_id))
                        if scheduled_event:
                            await scheduled_event.delete()
                            self.logger.info(f"Deleted Discord scheduled event {event.discord_event_id}")
                except discord.NotFound:
                    self.logger.warning(f"Discord scheduled event {event.discord_event_id} not found")
                except discord.HTTPException as e:
                    self.logger.error(f"Failed to delete Discord scheduled event: {e}")
                except Exception as e:
                    self.logger.error(f"Unexpected error deleting Discord scheduled event: {e}", exc_info=True)
            
            # Update event state to CANCELLED
            event.transition_to(EventState.CANCELLED)
            await self.update_event(event)
            
            # Notify all participants who RSVP'd
            participant_ids = list(event.rsvps.keys())
            if participant_ids:
                try:
                    guild = self.bot.get_guild(int(event.guild_id))
                    if guild:
                        # Create cancellation message
                        message = (
                            f"**Event Cancelled: {event.title}**\n\n"
                            f"The event you RSVP'd to has been cancelled.\n"
                        )
                        
                        if event.scheduled_date and event.scheduled_time:
                            message += f"**Original Date:** {event.scheduled_date.strftime('%A, %B %d, %Y')}\n"
                            message += f"**Original Time:** {event.scheduled_time.strftime('%I:%M %p')}\n"
                        
                        # Send notification to each participant
                        notification_count = 0
                        for user_id in participant_ids:
                            try:
                                member = guild.get_member(int(user_id))
                                if member:
                                    embed = discord.Embed(
                                        title="❌ Event Cancelled",
                                        description=message,
                                        color=discord.Color.red(),
                                        timestamp=datetime.utcnow()
                                    )
                                    embed.set_footer(text=f"Event ID: {event.id}")
                                    
                                    await member.send(embed=embed)
                                    notification_count += 1
                                    self.logger.debug(f"Sent cancellation notification to user {user_id}")
                            except discord.Forbidden:
                                self.logger.warning(f"Cannot send DM to user {user_id} (DMs disabled)")
                            except Exception as e:
                                self.logger.error(f"Failed to notify user {user_id}: {e}")
                        
                        self.logger.info(f"Sent cancellation notifications to {notification_count}/{len(participant_ids)} participants")
                except Exception as e:
                    self.logger.error(f"Error sending cancellation notifications: {e}", exc_info=True)
            
            # Emit event cancellation event
            await self.event_bus.emit(
                EventType.EVENT_CANCELLED,
                {
                    "event_id": str(event.id),
                    "event_title": event.title,
                    "guild_id": event.guild_id,
                    "participant_count": len(participant_ids)
                },
                guild_id=event.guild_id
            )
            
            self.logger.info(f"Successfully cancelled event {event.id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error cancelling event {event.id}: {e}", exc_info=True)
            return False
    
    async def start_enhanced_date_poll(self, event: Event) -> None:
        """Start enhanced date polling (wrapper for start_date_poll)."""
        await self.start_date_poll(event)
    
    def create_enhanced_poll_embed(self, poll: Poll, event: Event) -> discord.Embed:
        """Create enhanced poll embed (wrapper for create_poll_embed)."""
        return self.create_poll_embed(poll, event)
    
    async def start_date_poll(self, event: Event) -> None:
        """Start date polling for an event (simplified to 7 days)."""
        if not event.can_transition_to(EventState.DATE_POLLING):
            raise ValidationError("Cannot start date poll in current state")
        
        # Create date options for next 7 days (simplified from 30 days)
        options = []
        today = date.today()
        
        for i in range(7):
            poll_date = today + timedelta(days=i + 1)  # Start from tomorrow
            option = PollOption(
                option_id=str(uuid.uuid4()),
                label=poll_date.strftime("%A, %B %d"),
                value=poll_date.isoformat(),  # Store ISO date string
                votes=[],
                vote_count=0
            )
            options.append(option)
        
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
            guild_id=event.guild_id
        )
        
        self.logger.info(f"Date poll started for event {event.id} with {len(options)} options")
    
    async def close_date_poll_and_start_time_poll(self, event: Event, admin_selected_option_id: Optional[str] = None) -> None:
        """
        Close date poll and start time poll.
        
        Args:
            event: The event to update
            admin_selected_option_id: Optional admin-selected option ID for tie resolution
        """
        date_poll = event.get_poll(PollType.DATE)
        if not date_poll or not date_poll.is_active:
            raise ValidationError("No active date poll found")
        
        # Close date poll
        winner_option_id = date_poll.close_poll()
        
        # Handle tie case - requires admin selection
        if not winner_option_id:
            winning_options = date_poll.get_winning_options()
            
            # No votes case
            if not winning_options or all(opt.vote_count == 0 for opt in winning_options):
                raise ValidationError("No votes in date poll")
            
            # Tie case - check if admin provided selection
            if admin_selected_option_id:
                if date_poll.admin_select_winner(admin_selected_option_id):
                    winner_option_id = admin_selected_option_id
                else:
                    raise ValidationError("Invalid admin selection")
            else:
                # Tie needs admin resolution - raise special error
                raise PollTieError(
                    f"Tie detected between {len(winning_options)} options. Admin selection required.",
                    tied_options=[opt.option_id for opt in winning_options],
                    poll_type=PollType.DATE.value
                )
        
        # Get winning date
        winner_option = date_poll.get_option_by_id(winner_option_id)
        selected_date = date.fromisoformat(winner_option.value)
        event.scheduled_date = selected_date
        
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
                value=t.isoformat(),  # Store ISO time string
                votes=[],
                vote_count=0
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
            guild_id=event.guild_id
        )
        
        await self.event_bus.emit(
            EventType.POLL_CREATED,
            {
                "event_id": str(event.id),
                "poll_type": PollType.TIME.value,
                "option_count": len(time_options)
            },
            guild_id=event.guild_id
        )
    
    async def close_time_poll_and_start_game_poll(self, event: Event, admin_selected_option_id: Optional[str] = None) -> None:
        """
        Close time poll and start game poll.
        
        Args:
            event: The event to update
            admin_selected_option_id: Optional admin-selected option ID for tie resolution
        """
        time_poll = event.get_poll(PollType.TIME)
        if not time_poll or not time_poll.is_active:
            raise ValidationError("No active time poll found")
        
        # Close time poll
        winner_option_id = time_poll.close_poll()
        
        # Handle tie case - requires admin selection
        if not winner_option_id:
            winning_options = time_poll.get_winning_options()
            
            # No votes case
            if not winning_options or all(opt.vote_count == 0 for opt in winning_options):
                raise ValidationError("No votes in time poll")
            
            # Tie case - check if admin provided selection
            if admin_selected_option_id:
                if time_poll.admin_select_winner(admin_selected_option_id):
                    winner_option_id = admin_selected_option_id
                else:
                    raise ValidationError("Invalid admin selection")
            else:
                # Tie needs admin resolution - raise special error
                raise PollTieError(
                    f"Tie detected between {len(winning_options)} options. Admin selection required.",
                    tied_options=[opt.option_id for opt in winning_options],
                    poll_type=PollType.TIME.value
                )
        
        # Get winning time
        winner_option = time_poll.get_option_by_id(winner_option_id)
        selected_time = time.fromisoformat(winner_option.value)
        event.scheduled_time = selected_time
        
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
                value=game,  # For games, value is same as label
                votes=[],
                vote_count=0
            )
            game_options.append(option)
        
        # Create game poll
        game_poll = Poll(
            poll_type=PollType.GAME,
            title=f"Select Game for {event.title}",
            description=f"Date: {event.scheduled_date.strftime('%A, %B %d')}\n"
                       f"Time: {event.scheduled_time.strftime('%I:%M %p')}\n"
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
            guild_id=event.guild_id
        )
        
        await self.event_bus.emit(
            EventType.POLL_CREATED,
            {
                "event_id": str(event.id),
                "poll_type": PollType.GAME.value,
                "option_count": len(game_options)
            },
            guild_id=event.guild_id
        )
    
    async def close_game_poll_and_schedule_event(self, event: Event, admin_selected_option_id: Optional[str] = None) -> None:
        """
        Close game poll and schedule the event.
        
        Args:
            event: The event to update
            admin_selected_option_id: Optional admin-selected option ID for tie resolution
        """
        game_poll = event.get_poll(PollType.GAME)
        if not game_poll or not game_poll.is_active:
            raise ValidationError("No active game poll found")
        
        # Close game poll
        winner_option_id = game_poll.close_poll()
        
        # Handle tie case - requires admin selection
        if not winner_option_id:
            winning_options = game_poll.get_winning_options()
            
            # No votes case
            if not winning_options or all(opt.vote_count == 0 for opt in winning_options):
                raise ValidationError("No votes in game poll")
            
            # Tie case - check if admin provided selection
            if admin_selected_option_id:
                if game_poll.admin_select_winner(admin_selected_option_id):
                    winner_option_id = admin_selected_option_id
                else:
                    raise ValidationError("Invalid admin selection")
            else:
                # Tie needs admin resolution - raise special error
                raise PollTieError(
                    f"Tie detected between {len(winning_options)} options. Admin selection required.",
                    tied_options=[opt.option_id for opt in winning_options],
                    poll_type=PollType.GAME.value
                )
        
        # Transition to scheduled
        event.transition_to(EventState.SCHEDULED)
        
        # Create Discord scheduled event with retry logic
        try:
            discord_event_id = await self.create_discord_scheduled_event(event)
            if discord_event_id:
                event.discord_event_id = discord_event_id
                self.logger.info(f"Discord scheduled event created: {discord_event_id}")
            else:
                self.logger.warning(f"Failed to create Discord scheduled event for event {event.id}")
        except ValidationError as ve:
            self.logger.error(f"Validation error creating Discord event: {ve}")
            # Continue without Discord event - event is still scheduled
        except Exception as e:
            self.logger.error(f"Unexpected error creating Discord event: {e}", exc_info=True)
            # Continue without Discord event - event is still scheduled
        
        # Update in database (including discord_event_id if set)
        await self.update_event(event)
        
        # Emit events
        await self.event_bus.emit(
            EventType.POLL_COMPLETED,
            {
                "event_id": str(event.id),
                "poll_type": PollType.GAME.value,
                "winner_option_id": winner_option_id
            },
            guild_id=event.guild_id
        )
        
        await self.event_bus.emit(
            EventType.EVENT_UPDATED,
            {
                "event_id": str(event.id),
                "new_state": EventState.SCHEDULED.value,
                "title": event.title,
                "discord_event_id": event.discord_event_id
            },
            guild_id=event.guild_id
        )
        
        # Emit scheduled event for Discord integration
        await self.event_bus.emit(
            EventType.EVENT_SCHEDULED,
            {
                "event_id": str(event.id),
                "title": event.title,
                "scheduled_date": event.scheduled_date.isoformat() if event.scheduled_date else None,
                "scheduled_time": event.scheduled_time.isoformat() if event.scheduled_time else None,
                "timezone": event.timezone,
                "discord_event_id": event.discord_event_id
            },
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
        
        # Sync with Discord scheduled event if it exists
        if event.discord_event_id and status == RSVPStatus.YES:
            await self.sync_rsvp_to_discord_event(event, user_id, status)
        
        # Emit event
        await self.event_bus.emit(
            EventType.EVENT_UPDATED,
            {
                "event_id": str(event.id),
                "rsvp_user_id": user_id,
                "rsvp_status": status.value
            },
            guild_id=event.guild_id,
            user_id=user_id
        )
    
    async def sync_rsvp_to_discord_event(
        self,
        event: Event,
        user_id: str,
        status: RSVPStatus
    ) -> None:
        """Sync RSVP with Discord scheduled event interested users."""
        try:
            guild = self.bot.get_guild(int(event.guild_id))
            if not guild:
                self.logger.warning(f"Guild {event.guild_id} not found for RSVP sync")
                return
            
            # Get the Discord scheduled event
            try:
                scheduled_event = await guild.fetch_scheduled_event(int(event.discord_event_id))
            except discord.NotFound:
                self.logger.warning(f"Discord scheduled event {event.discord_event_id} not found")
                return
            except discord.HTTPException as e:
                self.logger.error(f"Error fetching Discord scheduled event: {e}")
                return
            
            # Note: Discord API doesn't provide direct methods to add/remove interested users
            # The interested status is managed by users themselves through the Discord UI
            # We can only read the interested users, not modify them programmatically
            # This is a Discord API limitation
            
            self.logger.info(f"RSVP synced for user {user_id} on event {event.id} (status: {status.value})")
            
        except Exception as e:
            self.logger.error(f"Error syncing RSVP to Discord event: {e}", exc_info=True)
    
    async def sync_discord_interested_users_to_rsvp(self, event: Event) -> int:
        """
        Sync interested users from Discord scheduled event to our RSVP system.
        Returns the number of users synced.
        """
        if not event.discord_event_id:
            return 0
        
        try:
            guild = self.bot.get_guild(int(event.guild_id))
            if not guild:
                self.logger.warning(f"Guild {event.guild_id} not found for sync")
                return 0
            
            # Get the Discord scheduled event
            try:
                scheduled_event = await guild.fetch_scheduled_event(int(event.discord_event_id))
            except discord.NotFound:
                self.logger.warning(f"Discord scheduled event {event.discord_event_id} not found")
                return 0
            except discord.HTTPException as e:
                self.logger.error(f"Error fetching Discord scheduled event: {e}")
                return 0
            
            # Fetch interested users
            synced_count = 0
            try:
                async for user in scheduled_event.users():
                    user_id = str(user.id)
                    # Only add if they haven't already RSVP'd
                    if user_id not in event.rsvps:
                        event.add_rsvp(user_id, RSVPStatus.YES)
                        synced_count += 1
                        self.logger.info(f"Synced interested user {user_id} to RSVP")
            except discord.HTTPException as e:
                self.logger.error(f"Error fetching interested users: {e}")
                return synced_count
            
            # Update event in database if we synced any users
            if synced_count > 0:
                await self.update_event(event)
                self.logger.info(f"Synced {synced_count} interested users from Discord event to RSVP")
            
            return synced_count
            
        except Exception as e:
            self.logger.error(f"Error syncing Discord interested users: {e}", exc_info=True)
            return 0
    
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
        if event.scheduled_date:
            schedule_text = event.scheduled_date.strftime("%A, %B %d, %Y")
            if event.scheduled_time:
                schedule_text += f" at {event.scheduled_time.strftime('%I:%M %p')}"
            
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
    
    @commands.slash_command(
        name="calendar", 
        description="Export upcoming events to calendar file (.ics)",
        guild_ids=[650597555872464896, 1328565530596212767]  # Add your guild IDs for faster sync
    )
    async def export_calendar(
        self,
        interaction: discord.Interaction,
        days_ahead: int = 30
    ):
        """Export scheduled events to an iCalendar (.ics) file."""
        try:
            await interaction.response.defer()
            
            # Validate days_ahead parameter
            if not (1 <= days_ahead <= 90):
                await interaction.followup.send(
                    "❌ Days ahead must be between 1 and 90.",
                    ephemeral=True
                )
                return
            
            # Get scheduled events for the guild
            from datetime import datetime, timedelta
            cutoff_date = datetime.utcnow() + timedelta(days=days_ahead)
            
            events_cursor = self.bot.database.events.find({
                'guild_id': str(interaction.guild.id),
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
                await interaction.followup.send(
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
            
            filename = f"gamenight_events_{interaction.guild.name}_{datetime.utcnow().strftime('%Y%m%d')}.ics"
            discord_file = discord.File(calendar_file, filename=filename)
            
            embed = discord.Embed(
                title="📅 Calendar Export", 
                description=f"Exported **{len(events)}** scheduled events from the next {days_ahead} days.", 
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(
                name="How to Use",
                value="Download the .ics file and import it into your calendar app (Google Calendar, Outlook, Apple Calendar, etc.)",
                inline=False
            )
            embed.set_footer(text="Game Night Bot • Interactive Gaming Community")
            
            await interaction.followup.send(embed=embed, file=discord_file)
            
            # Log the export
            self.logger.info(
                f"Calendar export generated for guild {interaction.guild.id} by user {interaction.user.id}, "
                f"{len(events)} events, {days_ahead} days ahead"
            )
            
        except Exception as e:
            self.logger.error(f"Error exporting calendar: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Something went wrong. Please try again or contact an administrator if the issue persists.",
                ephemeral=True
            )
    
    async def sync_discord_rsvps(self, event: Event) -> int:
        """Sync RSVPs from Discord scheduled event to bot event."""
        # Use our built-in sync method
        return await self.sync_discord_interested_users_to_rsvp(event)
    
    @commands.slash_command(
        name="sync-rsvps", 
        description="Manually sync RSVPs from Discord scheduled event",
        guild_ids=[650597555872464896, 1328565530596212767]  # Add your guild IDs for faster sync
    )
    # @require_permission(Permission.MANAGE_EVENTS)  # Temporarily disabled
    async def sync_rsvps_command(
        self,
        interaction: discord.Interaction,
        event_id: str
    ):
        """Manually sync RSVPs from Discord scheduled event."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Get the event
            event = await self.get_event(event_id)
            if not event:
                await interaction.followup.send("❌ Event not found.", ephemeral=True)
                return
            
            if event.guild_id != str(interaction.guild.id):
                await interaction.followup.send("❌ Event not found in this server.", ephemeral=True)
                return
            
            if not event.discord_event_id:
                await interaction.followup.send("❌ This event is not linked to a Discord scheduled event.", ephemeral=True)
                return
            
            # Sync RSVPs
            synced_count = await self.sync_discord_rsvps(event)
            
            if synced_count > 0:
                await interaction.followup.send(
                    f"✅ Synced **{synced_count}** RSVPs from Discord scheduled event.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "ℹ️ No new RSVPs to sync from Discord scheduled event.",
                    ephemeral=True
                )
            
        except Exception as e:
            self.logger.error(f"Error syncing RSVPs: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Something went wrong. Please try again or contact an administrator if the issue persists.",
                ephemeral=True
            )
    
    @commands.slash_command(
        name="retry-discord-event", 
        description="Retry creating Discord scheduled event",
        guild_ids=[650597555872464896, 1328565530596212767]  # Add your guild IDs for faster sync
    )
    # @require_permission(Permission.MANAGE_EVENTS)  # Temporarily disabled
    async def retry_discord_event(
        self,
        interaction: discord.Interaction,
        event_id: str
    ):
        """Retry creating a Discord scheduled event for a bot event."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Get the event
            event = await self.get_event(event_id)
            if not event:
                await interaction.followup.send("❌ Event not found.", ephemeral=True)
                return
            
            if event.guild_id != str(interaction.guild.id):
                await interaction.followup.send("❌ Event not found in this server.", ephemeral=True)
                return
            
            if not event.is_scheduled():
                await interaction.followup.send("❌ Event must be scheduled before creating Discord event.", ephemeral=True)
                return
            
            if event.discord_event_id:
                await interaction.followup.send("❌ Event already has a Discord scheduled event.", ephemeral=True)
                return
            
            # Attempt to create Discord event
            if not self.bot.discord_events:
                await interaction.followup.send("❌ Discord events integration not available.", ephemeral=True)
                return
            
            discord_event_id = await self.bot.discord_events.create_discord_event(event)
            
            if discord_event_id:
                await interaction.followup.send(
                    f"✅ Successfully created Discord scheduled event for **{event.title}**.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Failed to create Discord scheduled event for **{event.title}**. Check logs for details.",
                    ephemeral=True
                )
            
        except Exception as e:
            self.logger.error(f"Error retrying Discord event creation: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Something went wrong. Please try again or contact an administrator if the issue persists.",
                ephemeral=True
            )


    @commands.slash_command(
        name="event-list",
        description="List upcoming events in this server",
        guild_ids=[650597555872464896, 1328565530596212767]
    )
    async def event_list_command(
        self,
        interaction: discord.Interaction,
        show_all: bool = False
    ):
        """
        List upcoming events in the server.
        
        Args:
            show_all: If True, show completed and cancelled events too
        """
        try:
            await interaction.response.defer()
            
            # Get events for this guild
            events = await self.get_guild_events(str(interaction.guild.id), active_only=not show_all)
            
            if not events:
                await interaction.followup.send(
                    "📅 No events found in this server." if show_all else "📅 No active events found in this server.",
                    ephemeral=True
                )
                return
            
            # Create embed with event list
            embed = discord.Embed(
                title="📅 Game Night Events" if show_all else "📅 Upcoming Game Night Events",
                description=f"Found {len(events)} event(s)",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            # Get user's timezone preference
            user_timezone = await self._get_user_timezone(str(interaction.user.id), str(interaction.guild.id))
            
            # Add events to embed (limit to 10 for readability)
            for event in events[:10]:
                # Get state emoji
                status_emoji = {
                    EventState.DRAFT: "📝",
                    EventState.DATE_POLLING: "📅",
                    EventState.TIME_POLLING: "⏰",
                    EventState.GAME_POLLING: "🎮",
                    EventState.SCHEDULED: "✅",
                    EventState.COMPLETED: "🏁",
                    EventState.CANCELLED: "❌"
                }.get(event.state, "❓")
                
                # Build field value with event details
                field_value = f"**ID:** `{event.id}`\n"
                field_value += f"**State:** {event.state.value}\n"
                field_value += f"**Creator:** <@{event.creator_id}>\n"
                
                # Add scheduled date/time if available
                if event.scheduled_date:
                    field_value += f"**Date:** {event.scheduled_date.strftime('%A, %B %d, %Y')}\n"
                if event.scheduled_time:
                    # Format time in user's timezone
                    time_str = self._format_time_in_timezone(
                        event.scheduled_date,
                        event.scheduled_time,
                        event.timezone,
                        user_timezone
                    )
                    field_value += f"**Time:** {time_str}\n"
                
                # Add RSVP counts
                yes_count = event.get_rsvp_count(RSVPStatus.YES)
                no_count = event.get_rsvp_count(RSVPStatus.NO)
                maybe_count = event.get_rsvp_count(RSVPStatus.MAYBE)
                field_value += f"**RSVPs:** ✅ {yes_count} | ❌ {no_count} | ❓ {maybe_count}\n"
                
                embed.add_field(
                    name=f"{status_emoji} {event.title}",
                    value=field_value,
                    inline=False
                )
            
            if len(events) > 10:
                embed.set_footer(text=f"Showing 10 of {len(events)} events. Use /event-view to see specific events.")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            self.logger.error(f"Error listing events: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Something went wrong. Please try again or contact an administrator if the issue persists.",
                ephemeral=True
            )
    
    @commands.slash_command(
        name="event-view",
        description="View detailed information about a specific event",
        guild_ids=[650597555872464896, 1328565530596212767]
    )
    async def event_view_command(
        self,
        interaction: discord.Interaction,
        event_id: str
    ):
        """
        View detailed information about a specific event.
        
        Args:
            event_id: The ID of the event to view
        """
        try:
            await interaction.response.defer()
            
            # Get the event
            event = await self.get_event(event_id)
            if not event:
                await interaction.followup.send(
                    "❌ Event not found. Please check the event ID.",
                    ephemeral=True
                )
                return
            
            # Check if event belongs to this guild
            if event.guild_id != str(interaction.guild.id):
                await interaction.followup.send(
                    "❌ Event not found in this server.",
                    ephemeral=True
                )
                return
            
            # Get user's timezone preference
            user_timezone = await self._get_user_timezone(str(interaction.user.id), str(interaction.guild.id))
            
            # Create detailed event embed
            embed = self.create_detailed_event_embed(event, user_timezone)
            
            # Add management view if user can manage the event
            view = None
            if await self.can_manage_event(interaction.user, event):
                view = EventManagementView(self, event)
            
            await interaction.followup.send(embed=embed, view=view)
            
        except Exception as e:
            self.logger.error(f"Error viewing event: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Something went wrong. Please try again or contact an administrator if the issue persists.",
                ephemeral=True
            )
    
    def create_detailed_event_embed(self, event: Event, user_timezone: str = "UTC") -> discord.Embed:
        """
        Create a detailed embed for an event showing all information.
        
        Args:
            event: The event to create an embed for
            user_timezone: User's timezone for time display (defaults to UTC)
            
        Returns:
            Discord embed with detailed event information
        """
        # Get state emoji
        status_emoji = {
            EventState.DRAFT: "📝",
            EventState.DATE_POLLING: "📅",
            EventState.TIME_POLLING: "⏰",
            EventState.GAME_POLLING: "🎮",
            EventState.SCHEDULED: "✅",
            EventState.COMPLETED: "🏁",
            EventState.CANCELLED: "❌"
        }.get(event.state, "❓")
        
        # Create embed
        embed = discord.Embed(
            title=f"{status_emoji} {event.title}",
            description=event.description or "No description provided",
            color=self._get_state_color(event.state),
            timestamp=event.created_at
        )
        
        # Add basic info
        embed.add_field(
            name="📋 Event Info",
            value=f"**ID:** `{event.id}`\n"
                  f"**State:** {event.state.value}\n"
                  f"**Creator:** <@{event.creator_id}>\n"
                  f"**Created:** {event.created_at.strftime('%Y-%m-%d %H:%M UTC')}",
            inline=False
        )
        
        # Add scheduling info if available
        if event.scheduled_date or event.scheduled_time:
            schedule_value = ""
            if event.scheduled_date:
                schedule_value += f"**Date:** {event.scheduled_date.strftime('%A, %B %d, %Y')}\n"
            if event.scheduled_time:
                # Format time in user's timezone
                time_str = self._format_time_in_timezone(
                    event.scheduled_date,
                    event.scheduled_time,
                    event.timezone,
                    user_timezone
                )
                schedule_value += f"**Time:** {time_str}\n"
            if event.discord_event_id:
                schedule_value += f"**Discord Event:** [View Event](https://discord.com/events/{event.guild_id}/{event.discord_event_id})\n"
            
            embed.add_field(
                name="📅 Schedule",
                value=schedule_value,
                inline=False
            )
        
        # Add poll information
        self._add_poll_info_to_embed(embed, event)
        
        # Add RSVP information
        yes_count = event.get_rsvp_count(RSVPStatus.YES)
        no_count = event.get_rsvp_count(RSVPStatus.NO)
        maybe_count = event.get_rsvp_count(RSVPStatus.MAYBE)
        total_rsvps = yes_count + no_count + maybe_count
        
        rsvp_value = f"**Total RSVPs:** {total_rsvps}\n"
        rsvp_value += f"✅ **Yes:** {yes_count}\n"
        rsvp_value += f"❌ **No:** {no_count}\n"
        rsvp_value += f"❓ **Maybe:** {maybe_count}\n"
        
        # List attendees (Yes RSVPs)
        if yes_count > 0:
            attendees = event.get_attendee_list()
            if len(attendees) <= 10:
                rsvp_value += f"\n**Attendees:** {', '.join(f'<@{uid}>' for uid in attendees)}"
            else:
                rsvp_value += f"\n**Attendees:** {len(attendees)} users (too many to list)"
        
        embed.add_field(
            name="✋ RSVPs",
            value=rsvp_value,
            inline=False
        )
        
        embed.set_footer(text=f"Event ID: {event.id}")
        
        return embed
    
    def _add_poll_info_to_embed(self, embed: discord.Embed, event: Event) -> None:
        """
        Add poll information to an embed.
        
        Args:
            embed: The embed to add poll info to
            event: The event with polls
        """
        # Check for date poll
        date_poll = event.get_poll(PollType.DATE)
        if date_poll:
            poll_status = "🟢 Active" if date_poll.is_active else "🔴 Closed"
            total_votes = sum(opt.vote_count for opt in date_poll.options)
            
            poll_value = f"**Status:** {poll_status}\n"
            poll_value += f"**Total Votes:** {total_votes}\n"
            
            if not date_poll.is_active and event.scheduled_date:
                poll_value += f"**Winner:** {event.scheduled_date.strftime('%A, %B %d')}\n"
            elif date_poll.options:
                # Show top 3 options
                sorted_options = sorted(date_poll.options, key=lambda x: x.vote_count, reverse=True)
                for i, opt in enumerate(sorted_options[:3], 1):
                    poll_value += f"{i}. {opt.label}: {opt.vote_count} vote(s)\n"
            
            embed.add_field(
                name="📅 Date Poll",
                value=poll_value,
                inline=True
            )
        
        # Check for time poll
        time_poll = event.get_poll(PollType.TIME)
        if time_poll:
            poll_status = "🟢 Active" if time_poll.is_active else "🔴 Closed"
            total_votes = sum(opt.vote_count for opt in time_poll.options)
            
            poll_value = f"**Status:** {poll_status}\n"
            poll_value += f"**Total Votes:** {total_votes}\n"
            
            if not time_poll.is_active and event.scheduled_time:
                poll_value += f"**Winner:** {event.scheduled_time.strftime('%I:%M %p')}\n"
            elif time_poll.options:
                # Show top 3 options
                sorted_options = sorted(time_poll.options, key=lambda x: x.vote_count, reverse=True)
                for i, opt in enumerate(sorted_options[:3], 1):
                    poll_value += f"{i}. {opt.label}: {opt.vote_count} vote(s)\n"
            
            embed.add_field(
                name="⏰ Time Poll",
                value=poll_value,
                inline=True
            )
        
        # Check for game poll
        game_poll = event.get_poll(PollType.GAME)
        if game_poll:
            poll_status = "🟢 Active" if game_poll.is_active else "🔴 Closed"
            total_votes = sum(opt.vote_count for opt in game_poll.options)
            
            poll_value = f"**Status:** {poll_status}\n"
            poll_value += f"**Total Votes:** {total_votes}\n"
            
            if game_poll.options:
                # Show top 5 options
                sorted_options = sorted(game_poll.options, key=lambda x: x.vote_count, reverse=True)
                for i, opt in enumerate(sorted_options[:5], 1):
                    emoji = "🏆" if i == 1 and not game_poll.is_active else f"{i}."
                    poll_value += f"{emoji} {opt.label}: {opt.vote_count} vote(s)\n"
            
            embed.add_field(
                name="🎮 Game Poll",
                value=poll_value,
                inline=False
            )
    
    async def _get_user_timezone(self, user_id: str, guild_id: str) -> str:
        """
        Get user's timezone preference.
        
        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
            
        Returns:
            User's timezone string (defaults to UTC if not set)
        """
        try:
            from models.repositories import RepositoryManager
            repositories = RepositoryManager(self.bot.database)
            user = await repositories.users.get_by_user_and_guild(user_id, guild_id)
            return user.timezone if user else "UTC"
        except Exception as e:
            self.logger.error(f"Error getting user timezone: {e}")
            return "UTC"
    
    def _format_time_in_timezone(
        self, 
        event_date: Optional[date], 
        event_time: Optional[time], 
        event_timezone: str, 
        user_timezone: str
    ) -> str:
        """
        Format event time in user's timezone.
        
        Args:
            event_date: Event date
            event_time: Event time
            event_timezone: Event's timezone
            user_timezone: User's timezone
            
        Returns:
            Formatted time string with timezone indicator
        """
        if not event_date or not event_time:
            return ""
        
        try:
            # Combine date and time in event's timezone
            event_tz = ZoneInfo(event_timezone)
            event_datetime = datetime.combine(event_date, event_time, tzinfo=event_tz)
            
            # Convert to user's timezone
            user_tz = ZoneInfo(user_timezone)
            user_datetime = event_datetime.astimezone(user_tz)
            
            # Format the time
            time_str = user_datetime.strftime('%I:%M %p')
            
            # Add timezone indicator if different from event timezone
            if event_timezone != user_timezone:
                return f"{time_str} {user_timezone} (originally {event_time.strftime('%I:%M %p')} {event_timezone})"
            else:
                return f"{time_str} {user_timezone}"
        except Exception as e:
            self.logger.error(f"Error formatting time in timezone: {e}")
            # Fallback to original format
            return f"{event_time.strftime('%I:%M %p')} {event_timezone}"
    
    def _get_state_color(self, state: EventState) -> discord.Color:
        """
        Get color for event state.
        
        Args:
            state: The event state
            
        Returns:
            Discord color for the state
        """
        color_map = {
            EventState.DRAFT: discord.Color.light_gray(),
            EventState.DATE_POLLING: discord.Color.blue(),
            EventState.TIME_POLLING: discord.Color.purple(),
            EventState.GAME_POLLING: discord.Color.orange(),
            EventState.SCHEDULED: discord.Color.green(),
            EventState.COMPLETED: discord.Color.dark_gray(),
            EventState.CANCELLED: discord.Color.red()
        }
        return color_map.get(state, discord.Color.default())


async def setup(bot):
    """Set up the Events cog."""
    await bot.add_cog(EventsCog(bot))
