"""
Enhanced poll views with persistence, customization, and advanced interactions.
"""

import asyncio
from datetime import datetime, time, date
from typing import Dict, List, Optional, Any
import uuid

import discord
from discord.ext import commands

from models.event import Event, Poll, PollOption, PollType, EventState
from core.poll_manager import PollManager
from core.event_bus import EventBus, EventType
from utils.logging_config import get_logger, LoggerMixin
from utils.mobile_ui_components import (
    MobileOptimizedView, MobileOptimizedButton, MobileOptimizedSelect, 
    MobileOptimizedModal, create_mobile_optimized_embed
)


class PersistentPollView(MobileOptimizedView, LoggerMixin):
    """Base class for persistent poll views that survive bot restarts."""
    
    def __init__(self, cog, event: Event, poll: Poll, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.event = event
        self.poll = poll
        self.poll_manager: PollManager = cog.poll_manager
        self.event_bus: EventBus = cog.event_bus
        
        # Store view state for reconstruction
        self.view_data = {
            'event_id': str(event.id),
            'poll_type': poll.poll_type.value,
            'view_type': self.__class__.__name__
        }
    
    async def on_timeout(self):
        """Handle view timeout by disabling components."""
        for item in self.children:
            item.disabled = True
        
        # Try to update the message if possible
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=self)
        except discord.NotFound:
            pass  # Message was deleted
        except Exception as e:
            self.logger.error(f"Error updating view on timeout: {e}")
    
    async def reconstruct_from_data(self, bot, view_data: Dict[str, Any]):
        """Reconstruct view from stored data after bot restart."""
        try:
            # Get fresh event and poll data
            event_data = await bot.database.events.find_one({'_id': view_data['event_id']})
            if not event_data:
                return None
            
            event = Event(**event_data)
            poll = event.get_poll(PollType(view_data['poll_type']))
            if not poll:
                return None
            
            # Update instance data
            self.event = event
            self.poll = poll
            
            return self
            
        except Exception as e:
            get_logger(__name__).error(f"Error reconstructing view: {e}")
            return None


class EnhancedDatePollView(PersistentPollView):
    """Enhanced date poll view with custom options and better UX."""
    
    def __init__(self, cog, event: Event, poll: Poll):
        super().__init__(cog, event, poll, timeout=None)  # Persistent view
        
        # Add buttons for each date option
        self._add_date_buttons()
        
        # Add custom date button if poll allows customization
        if self._allows_custom_dates():
            self.add_item(CustomDateButton())
        
        # Add poll management buttons for admins
        self.add_item(ExtendPollButton())
        self.add_item(ClosePollButton())
    
    def _add_date_buttons(self):
        """Add buttons for each date option."""
        for i, option in enumerate(self.poll.options[:20]):  # Discord limit
            button = EnhancedDateButton(option, i)
            self.add_item(button)
    
    def _allows_custom_dates(self) -> bool:
        """Check if custom dates are allowed for this poll."""
        # This could be configurable per guild/event
        return True
    
    async def update_poll_display(self, interaction: discord.Interaction):
        """Update the poll display with current results."""
        embed = self.cog.create_enhanced_poll_embed(self.poll, self.event)
        await interaction.response.edit_message(embed=embed, view=self)


class EnhancedDateButton(MobileOptimizedButton):
    """Enhanced date button with vote tracking and visual feedback."""
    
    def __init__(self, option: PollOption, index: int):
        # Dynamic styling based on vote count
        style = self._get_button_style(option.vote_count)
        
        # Show vote count in label
        label = f"{option.label} ({option.vote_count})"
        
        super().__init__(
            label=label,
            style=style,
            custom_id=f"date_{option.option_id}",
            emoji="📅"
        )
        self.option = option
    
    def _get_button_style(self, vote_count: int) -> discord.ButtonStyle:
        """Get button style based on vote count."""
        if vote_count == 0:
            return discord.ButtonStyle.secondary
        elif vote_count <= 2:
            return discord.ButtonStyle.primary
        else:
            return discord.ButtonStyle.success
    
    async def callback(self, interaction: discord.Interaction):
        """Handle button click with enhanced feedback."""
        view: EnhancedDatePollView = self.view
        user_id = str(interaction.user.id)
        
        # Check if poll is still active
        if not view.poll.is_active:
            await interaction.response.send_message(
                "❌ This poll has ended.",
                ephemeral=True
            )
            return
        
        # Check if user already voted for this option
        if user_id in self.option.votes:
            # Remove vote
            success = view.poll.remove_vote(user_id, self.option.option_id)
            action = "removed"
            emoji = "➖"
        else:
            # Add vote
            success = view.poll.add_vote(user_id, self.option.option_id)
            action = "added"
            emoji = "✅"
        
        if success:
            # Update event in database
            await view.cog.update_event(view.event)
            
            # Update button appearance
            self.label = f"{self.option.label} ({self.option.vote_count})"
            self.style = self._get_button_style(self.option.vote_count)
            
            # Update all buttons to reflect current state
            for item in view.children:
                if isinstance(item, EnhancedDateButton):
                    item.label = f"{item.option.label} ({item.option.vote_count})"
                    item.style = item._get_button_style(item.option.vote_count)
            
            # Update the display
            await view.update_poll_display(interaction)
            
            # Send confirmation
            await interaction.followup.send(
                f"{emoji} Vote {action} for **{self.option.label}**",
                ephemeral=True
            )
            
            # Emit analytics event
            await view.event_bus.emit(
                EventType.POLL_VOTE_CAST,
                {
                    "event_id": str(view.event.id),
                    "poll_type": view.poll.poll_type.value,
                    "option_id": self.option.option_id,
                    "user_id": user_id,
                    "action": action
                },
                source="enhanced_poll_views",
                guild_id=view.event.guild_id,
                user_id=user_id
            )
        else:
            await interaction.response.send_message(
                "❌ Unable to process your vote. Please try again.",
                ephemeral=True
            )


class CustomDateButton(MobileOptimizedButton):
    """Button to add custom date option."""
    
    def __init__(self):
        super().__init__(
            label="Add Custom Date",
            style=discord.ButtonStyle.secondary,
            emoji="➕",
            custom_id="custom_date"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Open modal for custom date input."""
        modal = CustomDateModal(self.view)
        await interaction.response.send_modal(modal)


class CustomDateModal(MobileOptimizedModal):
    """Modal for adding custom date option."""
    
    def __init__(self, view: EnhancedDatePollView):
        super().__init__(title="Add Custom Date")
        self.view = view
        
        self.date_input = discord.ui.TextInput(
            label="Date (YYYY-MM-DD or MM/DD/YYYY)",
            placeholder="Enter date in YYYY-MM-DD format...",
            min_length=8,
            max_length=10,
            required=True
        )
        self.add_item(self.date_input)
        
        self.label_input = discord.ui.TextInput(
            label="Display Label (Optional)",
            placeholder="How should this date be displayed?",
            max_length=50,
            required=False
        )
        self.add_item(self.label_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle custom date submission."""
        try:
            # Parse date
            date_str = self.date_input.value.strip()
            parsed_date = self._parse_date(date_str)
            
            if parsed_date < date.today():
                await interaction.response.send_message(
                    "❌ Cannot add dates in the past.",
                    ephemeral=True
                )
                return
            
            # Create label
            label = self.label_input.value.strip() if self.label_input.value else parsed_date.strftime("%A, %B %d")
            
            # Add option to poll
            success = await self.view.poll_manager.add_custom_poll_option(
                event_id=str(self.view.event.id),
                poll_type=self.view.poll.poll_type,
                label=label,
                value=parsed_date
            )
            
            if success:
                # Refresh the view
                await self._refresh_view(interaction)
                await interaction.followup.send(
                    f"✅ Added custom date: **{label}**",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ Failed to add custom date. Please try again.",
                    ephemeral=True
                )
                
        except ValueError as e:
            await interaction.response.send_message(
                f"❌ Invalid date format: {e}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                "❌ An error occurred while adding the custom date.",
                ephemeral=True
            )
    
    def _parse_date(self, date_str: str) -> date:
        """Parse date string into date object."""
        # Try different formats
        formats = ["%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        raise ValueError("Invalid date format. Use YYYY-MM-DD or MM/DD/YYYY")
    
    async def _refresh_view(self, interaction: discord.Interaction):
        """Refresh the poll view with updated options."""
        # Get updated event data
        event_data = await self.view.cog.bot.database.events.find_one({'_id': str(self.view.event.id)})
        if event_data:
            updated_event = Event(**event_data)
            updated_poll = updated_event.get_poll(self.view.poll.poll_type)
            
            if updated_poll:
                # Create new view with updated data
                new_view = EnhancedDatePollView(self.view.cog, updated_event, updated_poll)
                embed = self.view.cog.create_enhanced_poll_embed(updated_poll, updated_event)
                
                # Update the message
                await interaction.edit_original_response(embed=embed, view=new_view)


class ExtendPollButton(discord.ui.Button):
    """Button to extend poll voting time."""
    
    def __init__(self):
        super().__init__(
            label="Extend Poll",
            style=discord.ButtonStyle.secondary,
            emoji="⏰",
            custom_id="extend_poll"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle poll extension."""
        view: EnhancedDatePollView = self.view
        
        # Check permissions
        if not await view.cog.can_manage_event(interaction.user, view.event):
            await interaction.response.send_message(
                "❌ You don't have permission to extend this poll.",
                ephemeral=True
            )
            return
        
        # Extend poll by 15 minutes
        await view.poll_manager._extend_poll_voting(view.event, view.poll)
        
        await interaction.response.send_message(
            "⏰ Poll extended by 15 minutes!",
            ephemeral=True
        )


class ClosePollButton(discord.ui.Button):
    """Button to manually close poll."""
    
    def __init__(self):
        super().__init__(
            label="Close Poll",
            style=discord.ButtonStyle.danger,
            emoji="🔒",
            custom_id="close_poll"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle manual poll closure."""
        view: EnhancedDatePollView = self.view
        
        # Check permissions
        if not await view.cog.can_manage_event(interaction.user, view.event):
            await interaction.response.send_message(
                "❌ You don't have permission to close this poll.",
                ephemeral=True
            )
            return
        
        # Confirm closure
        confirm_view = ConfirmClosePollView(view)
        await interaction.response.send_message(
            "⚠️ Are you sure you want to close this poll early?",
            view=confirm_view,
            ephemeral=True
        )


class ConfirmClosePollView(discord.ui.View):
    """Confirmation view for closing poll early."""
    
    def __init__(self, parent_view: EnhancedDatePollView):
        super().__init__(timeout=60)
        self.parent_view = parent_view
    
    @discord.ui.button(label="Yes, Close Poll", style=discord.ButtonStyle.danger)
    async def confirm_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm poll closure."""
        try:
            # Close poll manually
            await self.parent_view.poll_manager._close_poll_and_advance(
                self.parent_view.event, 
                self.parent_view.poll
            )
            
            await interaction.response.edit_message(
                content="✅ Poll closed successfully!",
                view=None
            )
        except Exception as e:
            await interaction.response.edit_message(
                content="❌ Error closing poll. Please try again.",
                view=None
            )
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel poll closure."""
        await interaction.response.edit_message(
            content="Poll closure cancelled.",
            view=None
        )


class EnhancedTimePollView(PersistentPollView):
    """Enhanced time poll view with custom time slots."""
    
    def __init__(self, cog, event: Event, poll: Poll):
        super().__init__(cog, event, poll, timeout=None)
        
        # Add time selection dropdown
        self.add_item(TimeSelectionDropdown(poll.options))
        
        # Add custom time button
        self.add_item(CustomTimeButton())
        
        # Add management buttons
        self.add_item(ExtendPollButton())
        self.add_item(ClosePollButton())


class TimeSelectionDropdown(discord.ui.Select):
    """Enhanced dropdown for time selection with vote counts."""
    
    def __init__(self, options: List[PollOption]):
        select_options = []
        for option in options[:25]:  # Discord limit
            # Show vote count in description
            description = f"{option.vote_count} votes"
            if option.vote_count == 1:
                description = "1 vote"
            
            select_options.append(
                discord.SelectOption(
                    label=option.label,
                    value=option.option_id,
                    description=description,
                    emoji="⏰"
                )
            )
        
        super().__init__(
            placeholder="Choose your preferred time(s)...",
            min_values=1,
            max_values=min(len(select_options), 3),
            options=select_options
        )
        self.poll_options = {opt.option_id: opt for opt in options}
    
    async def callback(self, interaction: discord.Interaction):
        """Handle time selection."""
        view: EnhancedTimePollView = self.view
        user_id = str(interaction.user.id)
        
        if not view.poll.is_active:
            await interaction.response.send_message(
                "❌ This poll has ended.",
                ephemeral=True
            )
            return
        
        # Remove all existing votes for this user
        for option in view.poll.options:
            option.remove_vote(user_id)
        
        # Add votes for selected options
        selected_labels = []
        for option_id in self.values:
            if view.poll.add_vote(user_id, option_id):
                option = view.poll.get_option_by_id(option_id)
                if option:
                    selected_labels.append(option.label)
        
        if selected_labels:
            # Update event in database
            await view.cog.update_event(view.event)
            
            # Update dropdown options to show new vote counts
            self._update_option_descriptions()
            
            # Update display
            embed = view.cog.create_enhanced_poll_embed(view.poll, view.event)
            await interaction.response.edit_message(embed=embed, view=view)
            
            # Send confirmation
            await interaction.followup.send(
                f"✅ Voted for: {', '.join(selected_labels)}",
                ephemeral=True
            )
            
            # Emit analytics event
            await view.event_bus.emit(
                EventType.POLL_VOTE_CAST,
                {
                    "event_id": str(view.event.id),
                    "poll_type": view.poll.poll_type.value,
                    "option_ids": self.values,
                    "user_id": user_id
                },
                source="enhanced_poll_views",
                guild_id=view.event.guild_id,
                user_id=user_id
            )
        else:
            await interaction.response.send_message(
                "❌ Unable to record your votes. Please try again.",
                ephemeral=True
            )
    
    def _update_option_descriptions(self):
        """Update option descriptions with current vote counts."""
        for i, select_option in enumerate(self.options):
            poll_option = self.poll_options.get(select_option.value)
            if poll_option:
                vote_count = poll_option.vote_count
                select_option.description = f"{vote_count} vote{'s' if vote_count != 1 else ''}"


class CustomTimeButton(discord.ui.Button):
    """Button to add custom time option."""
    
    def __init__(self):
        super().__init__(
            label="Add Custom Time",
            style=discord.ButtonStyle.secondary,
            emoji="➕",
            custom_id="custom_time"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Open modal for custom time input."""
        modal = CustomTimeModal(self.view)
        await interaction.response.send_modal(modal)


class CustomTimeModal(discord.ui.Modal):
    """Modal for adding custom time option."""
    
    def __init__(self, view: EnhancedTimePollView):
        super().__init__(title="Add Custom Time")
        self.view = view
        
        self.time_input = discord.ui.TextInput(
            label="Time (HH:MM AM/PM or 24-hour)",
            placeholder="e.g., 7:30 PM or 19:30",
            min_length=4,
            max_length=8,
            required=True
        )
        self.add_item(self.time_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle custom time submission."""
        try:
            # Parse time
            time_str = self.time_input.value.strip()
            parsed_time = self._parse_time(time_str)
            
            # Create label
            label = parsed_time.strftime("%I:%M %p").lstrip('0')
            
            # Add option to poll
            success = await self.view.poll_manager.add_custom_poll_option(
                event_id=str(self.view.event.id),
                poll_type=self.view.poll.poll_type,
                label=label,
                value=parsed_time
            )
            
            if success:
                await interaction.response.send_message(
                    f"✅ Added custom time: **{label}**",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ Failed to add custom time. Please try again.",
                    ephemeral=True
                )
                
        except ValueError as e:
            await interaction.response.send_message(
                f"❌ Invalid time format: {e}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                "❌ An error occurred while adding the custom time.",
                ephemeral=True
            )
    
    def _parse_time(self, time_str: str) -> time:
        """Parse time string into time object."""
        # Try different formats
        formats = ["%I:%M %p", "%I:%M%p", "%H:%M", "%I %p", "%I%p"]
        
        for fmt in formats:
            try:
                return datetime.strptime(time_str.upper(), fmt).time()
            except ValueError:
                continue
        
        raise ValueError("Invalid time format. Use HH:MM AM/PM or 24-hour format")


class TieResolutionView(discord.ui.View):
    """View for admin tie resolution."""
    
    def __init__(self, cog, event: Event, poll: Poll, tied_options: List[PollOption]):
        super().__init__(timeout=300)  # 5 minute timeout for admin action
        self.cog = cog
        self.event = event
        self.poll = poll
        self.tied_options = tied_options
        
        # Add buttons for each tied option
        for i, option in enumerate(tied_options[:5]):  # Limit to 5 options
            button = TieResolutionButton(option, i)
            self.add_item(button)
        
        # Add runoff poll option
        if len(tied_options) <= 5:
            self.add_item(CreateRunoffButton())


class TieResolutionButton(discord.ui.Button):
    """Button for admin to select winning option in tie."""
    
    def __init__(self, option: PollOption, index: int):
        super().__init__(
            label=f"Choose: {option.label}",
            style=discord.ButtonStyle.primary,
            custom_id=f"tie_resolve_{option.option_id}"
        )
        self.option = option
    
    async def callback(self, interaction: discord.Interaction):
        """Handle admin tie resolution."""
        view: TieResolutionView = self.view
        
        # Check admin permissions
        if not await view.cog.can_manage_event(interaction.user, view.event):
            await interaction.response.send_message(
                "❌ You don't have permission to resolve this tie.",
                ephemeral=True
            )
            return
        
        # Resolve tie
        success = await view.cog.poll_manager.admin_resolve_tie(
            event_id=str(view.event.id),
            poll_type=view.poll.poll_type,
            chosen_option_id=self.option.option_id
        )
        
        if success:
            await interaction.response.edit_message(
                content=f"✅ Tie resolved! Selected: **{self.option.label}**",
                view=None
            )
        else:
            await interaction.response.send_message(
                "❌ Failed to resolve tie. Please try again.",
                ephemeral=True
            )


class CreateRunoffButton(discord.ui.Button):
    """Button to create runoff poll for tied options."""
    
    def __init__(self):
        super().__init__(
            label="Create Runoff Poll",
            style=discord.ButtonStyle.secondary,
            emoji="🗳️",
            custom_id="create_runoff"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Create runoff poll with tied options."""
        view: TieResolutionView = self.view
        
        # Check admin permissions
        if not await view.cog.can_manage_event(interaction.user, view.event):
            await interaction.response.send_message(
                "❌ You don't have permission to create a runoff poll.",
                ephemeral=True
            )
            return
        
        # Create runoff poll
        await view.cog.poll_manager._create_runoff_poll(
            view.event, 
            view.poll, 
            view.tied_options
        )
        
        await interaction.response.edit_message(
            content="🗳️ Runoff poll created with tied options!",
            view=None
        )