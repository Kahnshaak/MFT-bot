"""
Simplified Events cog for game night event creation with polls.
"""

from datetime import datetime, timedelta
from typing import Optional

import discord
from discord.ext import commands, tasks
from discord import SlashCommandGroup

from models.event import Event
from utils.logging_config import get_logger
from utils.exceptions import DatabaseError, DatabaseConnectionError


class EventCreationModal(discord.ui.Modal):
    """Modal for creating a new event with a title."""
    
    def __init__(self, bot):
        super().__init__(title="Create Game Night Event")
        self.bot = bot
        self.logger = get_logger(__name__)
        
        self.add_item(
            discord.ui.InputText(
                label="Event Title",
                placeholder="Enter event title (3-100 characters)",
                min_length=3,
                max_length=100,
                required=True,
                style=discord.InputTextStyle.short
            )
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle modal submission and create event with poll."""
        try:
            # Get the event title from the modal input
            event_title = self.children[0].value.strip()
            
            # Validate event title
            validation_error = self._validate_title(event_title)
            if validation_error:
                await interaction.response.send_message(
                    f"❌ {validation_error}",
                    ephemeral=True
                )
                return
            
            self.logger.info(
                f"Creating event '{event_title}' for user {interaction.user.id} "
                f"in guild {interaction.guild.id}, channel {interaction.channel.id}"
            )
            
            # Create event document
            event_data = {
                "guild_id": str(interaction.guild.id),
                "channel_id": str(interaction.channel.id),
                "creator_id": str(interaction.user.id),
                "title": event_title,
                "created_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(days=7),
                "status": "active",
                "date_votes": {},
                "time_votes": {},
                "message_id": None,
                "winning_date": None,
                "winning_time": None,
                "discord_event_id": None
            }
            
            # Validate using Event model
            event = Event(**event_data)
            event.validate_data()
            
            # Save to database
            try:
                event_id = await self.bot.database.insert_one("events", event.model_dump())
                self.logger.info(f"Event created with ID: {event_id}")
            except DatabaseError as e:
                self.logger.error(f"Database error creating event: {e}", exc_info=True)
                await interaction.response.send_message(
                    "❌ Failed to save event to database. Please try again later.",
                    ephemeral=True
                )
                return
            
            # Acknowledge the submission
            await interaction.response.send_message(
                f"✅ Event '{event_title}' created! Generating poll...",
                ephemeral=True
            )
            
            # Generate poll (will be implemented in task 5)
            # For now, we'll call a placeholder function
            await self._generate_poll(interaction, event_id, event)
            
        except ValueError as e:
            # Validation error
            self.logger.error(f"Validation error creating event: {e}")
            await interaction.response.send_message(
                f"❌ Invalid event data: {str(e)}",
                ephemeral=True
            )
        except Exception as e:
            # Database or other error
            self.logger.error(f"Error creating event: {e}", exc_info=True)
            
            # Try to respond if we haven't already
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ Failed to create event. Please try again.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ Failed to create event. Please try again.",
                        ephemeral=True
                    )
            except Exception as followup_error:
                self.logger.error(f"Failed to send error message: {followup_error}")
    
    def _validate_title(self, title: str) -> Optional[str]:
        """
        Validate event title.
        
        Args:
            title: Event title to validate
        
        Returns:
            Error message if validation fails, None if valid
        """
        # Check length (already enforced by InputText min_length/max_length, but double-check)
        if len(title) < 3:
            return "Event title must be at least 3 characters long."
        
        if len(title) > 100:
            return "Event title must be no more than 100 characters long."
        
        # Check for @everyone and @here mentions
        if "@everyone" in title.lower():
            return "Event title cannot contain @everyone mentions."
        
        if "@here" in title.lower():
            return "Event title cannot contain @here mentions."
        
        return None
    
    async def _generate_poll(self, interaction: discord.Interaction, event_id: str, event: Event):
        """
        Generate poll for the event with date and time voting options.
        
        Args:
            interaction: Discord interaction
            event_id: Database ID of the event
            event: Event model instance
        """
        try:
            # Generate date options: all remaining days in current month
            date_options = self._generate_date_options()
            
            # Generate time options: 5pm through 11pm in 1-hour increments
            time_options = self._generate_time_options()
            
            self.logger.info(
                f"Generated {len(date_options)} date options and {len(time_options)} time options "
                f"for event {event_id}"
            )
            
            # Create poll embed
            embed = self._create_poll_embed(event, date_options, time_options)
            
            # Create view with Vote button
            view = PollView(event_id, self.bot)
            
            # Send poll message to the channel
            channel = interaction.channel
            poll_message = await channel.send(embed=embed, view=view)
            
            self.logger.info(f"Poll message sent with ID: {poll_message.id} for event {event_id}")
            
            # Update event document with message_id
            try:
                await self.bot.database.update_one(
                    "events",
                    {"_id": event_id},
                    {"$set": {"message_id": str(poll_message.id)}}
                )
                self.logger.info(f"Event {event_id} updated with message_id {poll_message.id}")
            except DatabaseError as e:
                self.logger.error(f"Database error updating event {event_id} with message_id: {e}", exc_info=True)
                await interaction.followup.send(
                    "⚠️ Poll created but failed to save message reference. The poll may not work correctly.",
                    ephemeral=True
                )
            
        except Exception as e:
            self.logger.error(f"Error generating poll for event {event_id}: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "❌ Failed to generate poll. Please try again.",
                    ephemeral=True
                )
            except Exception as followup_error:
                self.logger.error(f"Failed to send error message: {followup_error}")
    
    def _generate_date_options(self) -> list[str]:
        """
        Generate list of date options: all remaining days in current month.
        
        Returns:
            List of date strings in YYYY-MM-DD format
        """
        now = datetime.utcnow()
        current_year = now.year
        current_month = now.month
        current_day = now.day
        
        # Get the last day of the current month
        if current_month == 12:
            next_month = datetime(current_year + 1, 1, 1)
        else:
            next_month = datetime(current_year, current_month + 1, 1)
        
        last_day = (next_month - timedelta(days=1)).day
        
        # Generate dates from today through end of month
        date_options = []
        for day in range(current_day, last_day + 1):
            date = datetime(current_year, current_month, day)
            date_options.append(date.strftime("%Y-%m-%d"))
        
        return date_options
    
    def _generate_time_options(self) -> list[str]:
        """
        Generate list of time options: 5pm through 11pm in 1-hour increments.
        
        Returns:
            List of time strings in HH:MM format (17:00, 18:00, ..., 23:00)
        """
        time_options = []
        for hour in range(17, 24):  # 17:00 (5pm) through 23:00 (11pm)
            time_options.append(f"{hour:02d}:00")
        
        return time_options
    
    def _create_poll_embed(self, event: Event, date_options: list[str], time_options: list[str]) -> discord.Embed:
        """
        Create poll embed showing event details and voting instructions.
        
        Args:
            event: Event model instance
            date_options: List of available date options
            time_options: List of available time options
        
        Returns:
            Discord embed for the poll
        """
        embed = discord.Embed(
            title=f"📅 {event.title}",
            description="Vote for your preferred dates and times!",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Format date options for display
        date_display = []
        for date_str in date_options:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            date_display.append(date_obj.strftime("%b %d"))
        
        # Format time options for display
        time_display = []
        for time_str in time_options:
            hour = int(time_str.split(":")[0])
            if hour >= 12:
                time_12hr = f"{hour - 12 if hour > 12 else 12}pm"
            else:
                time_12hr = f"{hour}am"
            time_display.append(time_12hr)
        
        # Add fields to embed
        embed.add_field(
            name="📆 Available Dates",
            value=", ".join(date_display),
            inline=False
        )
        
        embed.add_field(
            name="🕐 Available Times",
            value=", ".join(time_display),
            inline=False
        )
        
        embed.add_field(
            name="⏰ Poll Expires",
            value=f"<t:{int(event.expires_at.timestamp())}:R> (<t:{int(event.expires_at.timestamp())}:F>)",
            inline=False
        )
        
        embed.add_field(
            name="📝 How to Vote",
            value="Click the **Vote** button below to select your preferred dates and times!",
            inline=False
        )
        
        embed.set_footer(text=f"Created by user ID: {event.creator_id}")
        
        return embed


class VoteView(discord.ui.View):
    """View for voting on event dates and times using select menus."""
    
    def __init__(self, event_id: str, bot, event_data: dict):
        super().__init__(timeout=180)  # 3 minute timeout
        self.event_id = event_id
        self.bot = bot
        self.event_data = event_data
        self.logger = get_logger(__name__)
        self.selected_dates = []
        self.selected_times = []
        
        # Generate date options (next 14 days)
        now = datetime.utcnow()
        date_options = []
        for i in range(14):
            date = now + timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            display = date.strftime("%a, %b %d")
            if i == 0:
                display += " (Today)"
            elif i == 1:
                display += " (Tomorrow)"
            date_options.append(discord.SelectOption(
                label=display,
                value=date_str,
                description=date.strftime("%Y-%m-%d")
            ))
        
        # Add date select menu
        date_select = discord.ui.Select(
            placeholder="📅 Select dates (you can pick multiple)",
            options=date_options[:25],  # Discord limit
            min_values=1,
            max_values=min(len(date_options), 10),  # Allow up to 10 dates
            custom_id="date_select"
        )
        date_select.callback = self.date_select_callback
        self.add_item(date_select)
        
        # Generate time options
        time_options = []
        for hour in range(12, 24):  # 12pm to 11pm
            for minute in [0, 30]:
                time_obj = datetime.strptime(f"{hour}:{minute:02d}", "%H:%M")
                time_str = time_obj.strftime("%H:%M")
                display = time_obj.strftime("%I:%M %p").lstrip("0")
                time_options.append(discord.SelectOption(
                    label=display,
                    value=time_str,
                    description=time_str
                ))
        
        # Add time select menu
        time_select = discord.ui.Select(
            placeholder="🕐 Select times (you can pick multiple)",
            options=time_options[:25],  # Discord limit
            min_values=1,
            max_values=min(len(time_options), 10),  # Allow up to 10 times
            custom_id="time_select"
        )
        time_select.callback = self.time_select_callback
        self.add_item(time_select)
    
    async def date_select_callback(self, interaction: discord.Interaction):
        """Handle date selection."""
        self.selected_dates = interaction.data["values"]
        await interaction.response.defer()
    
    async def time_select_callback(self, interaction: discord.Interaction):
        """Handle time selection."""
        self.selected_times = interaction.data["values"]
        await interaction.response.defer()
    
    @discord.ui.button(label="Submit Vote", style=discord.ButtonStyle.success, emoji="✅", row=2)
    async def submit_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        """Handle vote submission."""
        try:
            # Validate selections
            if not self.selected_dates:
                await interaction.response.send_message(
                    "❌ Please select at least one date before submitting.",
                    ephemeral=True
                )
                return
            
            if not self.selected_times:
                await interaction.response.send_message(
                    "❌ Please select at least one time before submitting.",
                    ephemeral=True
                )
                return
            
            self.logger.info(
                f"User {interaction.user.id} submitted vote for event {self.event_id}: "
                f"dates={self.selected_dates}, times={self.selected_times}"
            )
            
            # Fetch event from database
            try:
                event_data = await self.bot.database.find_one("events", {"_id": self.event_id})
            except DatabaseError as e:
                self.logger.error(f"Database error fetching event {self.event_id}: {e}", exc_info=True)
                await interaction.response.send_message(
                    "❌ Failed to retrieve event from database. Please try again later.",
                    ephemeral=True
                )
                return
            
            if not event_data:
                self.logger.error(f"Event {self.event_id} not found in database")
                await interaction.response.send_message(
                    "❌ Event not found. It may have been deleted.",
                    ephemeral=True
                )
                return
            
            # Create Event model instance
            event = Event(**event_data)
            
            # Check if event is still active
            if event.status != "active":
                self.logger.warning(f"User {interaction.user.id} tried to vote on inactive event {self.event_id}")
                await interaction.response.send_message(
                    "❌ This poll has ended and is no longer accepting votes.",
                    ephemeral=True
                )
                return
            
            # Record votes using Event model method
            user_id = str(interaction.user.id)
            event.add_vote(user_id, self.selected_dates, self.selected_times)
            
            self.logger.info(
                f"Recorded votes for user {interaction.user.id} on event {self.event_id}: "
                f"{len(self.selected_dates)} dates, {len(self.selected_times)} times"
            )
            
            # Update event in database
            try:
                await self.bot.database.update_one(
                    "events",
                    {"_id": self.event_id},
                    {"$set": {
                        "date_votes": event.date_votes,
                        "time_votes": event.time_votes
                    }}
                )
                self.logger.info(f"Updated event {self.event_id} in database with new votes")
            except DatabaseError as e:
                self.logger.error(f"Database error updating votes for event {self.event_id}: {e}", exc_info=True)
                await interaction.response.send_message(
                    "❌ Failed to save your vote to database. Please try again.",
                    ephemeral=True
                )
                return
            
            # Format dates and times for display
            date_displays = []
            for date_str in self.selected_dates:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                date_displays.append(date_obj.strftime("%a, %b %d"))
            
            time_displays = []
            for time_str in self.selected_times:
                time_obj = datetime.strptime(time_str, "%H:%M")
                time_displays.append(time_obj.strftime("%I:%M %p").lstrip("0"))
            
            # Send confirmation
            await interaction.response.send_message(
                f"✅ **Vote recorded!**\n\n"
                f"📆 **Dates:** {', '.join(date_displays)}\n"
                f"🕐 **Times:** {', '.join(time_displays)}",
                ephemeral=True
            )
            
            # Update poll embed to show current vote counts
            try:
                await update_poll_embed(self.bot, interaction.channel, event)
            except Exception as e:
                self.logger.error(f"Failed to update poll embed: {e}", exc_info=True)
            
            # Disable this view
            self.stop()
            
        except Exception as e:
            self.logger.error(f"Error processing vote from user {interaction.user.id}: {e}", exc_info=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred while processing your vote. Please try again.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ An error occurred while processing your vote. Please try again.",
                        ephemeral=True
                    )
            except Exception as followup_error:
                self.logger.error(f"Failed to send error message: {followup_error}")
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌", row=2)
    async def cancel_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        """Handle cancel button."""
        await interaction.response.send_message("Vote cancelled.", ephemeral=True)
        self.stop()


class VoteModal(discord.ui.Modal):
    """Legacy modal for voting - kept for backwards compatibility."""
    
    def __init__(self, event_id: str, bot):
        super().__init__(title="Vote on Event")
        self.event_id = event_id
        self.bot = bot
        self.logger = get_logger(__name__)
        
        self.add_item(
            discord.ui.InputText(
                label="Dates (comma-separated)",
                placeholder="Enter dates as DD (e.g., 15,16,20)",
                required=True,
                style=discord.InputTextStyle.short
            )
        )
        
        self.add_item(
            discord.ui.InputText(
                label="Times (comma-separated)",
                placeholder="Enter times as 5pm,6pm,7pm",
                required=True,
                style=discord.InputTextStyle.short
            )
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle vote submission."""
        try:
            # Get input values
            dates_input = self.children[0].value.strip()
            times_input = self.children[1].value.strip()
            
            self.logger.info(
                f"User {interaction.user.id} submitted vote for event {self.event_id}: "
                f"dates='{dates_input}', times='{times_input}'"
            )
            
            # Parse and validate dates
            parsed_dates = self._parse_dates(dates_input)
            
            # Parse and validate times
            parsed_times = self._parse_times(times_input)
            
            self.logger.info(
                f"Parsed vote from user {interaction.user.id}: "
                f"dates={parsed_dates}, times={parsed_times}"
            )
            
            # Fetch event from database
            try:
                event_data = await self.bot.database.find_one("events", {"_id": self.event_id})
            except DatabaseError as e:
                self.logger.error(f"Database error fetching event {self.event_id}: {e}", exc_info=True)
                await interaction.response.send_message(
                    "❌ Failed to retrieve event from database. Please try again later.",
                    ephemeral=True
                )
                return
            
            if not event_data:
                self.logger.error(f"Event {self.event_id} not found in database")
                await interaction.response.send_message(
                    "❌ Event not found. It may have been deleted.",
                    ephemeral=True
                )
                return
            
            # Create Event model instance
            event = Event(**event_data)
            
            # Check if event is still active
            if event.status != "active":
                self.logger.warning(f"User {interaction.user.id} tried to vote on inactive event {self.event_id}")
                await interaction.response.send_message(
                    "❌ This poll has ended and is no longer accepting votes.",
                    ephemeral=True
                )
                return
            
            # Record votes using Event model method
            user_id = str(interaction.user.id)
            event.add_vote(user_id, parsed_dates, parsed_times)
            
            self.logger.info(
                f"Recorded votes for user {interaction.user.id} on event {self.event_id}: "
                f"{len(parsed_dates)} dates, {len(parsed_times)} times"
            )
            
            # Update event in database
            try:
                await self.bot.database.update_one(
                    "events",
                    {"_id": self.event_id},
                    {"$set": {
                        "date_votes": event.date_votes,
                        "time_votes": event.time_votes
                    }}
                )
                self.logger.info(f"Updated event {self.event_id} in database with new votes")
            except DatabaseError as e:
                self.logger.error(f"Database error updating votes for event {self.event_id}: {e}", exc_info=True)
                await interaction.response.send_message(
                    "❌ Failed to save your vote to database. Please try again.",
                    ephemeral=True
                )
                return
            
            # Acknowledge the interaction first
            await interaction.response.send_message(
                "Processing your vote...",
                ephemeral=True
            )
            
            # Update poll embed to show current vote counts
            await update_poll_embed(self.bot, interaction.channel, event)
            
            # Send confirmation to user
            await interaction.followup.send(
                f"✅ Vote recorded!\n"
                f"📆 Dates: {', '.join([self._format_date_display(d) for d in parsed_dates])}\n"
                f"🕐 Times: {', '.join([self._format_time_display(t) for t in parsed_times])}",
                ephemeral=True
            )
            
        except ValueError as e:
            # Validation error
            self.logger.warning(f"Validation error in vote from user {interaction.user.id}: {e}")
            await interaction.response.send_message(
                f"❌ Invalid input: {str(e)}",
                ephemeral=True
            )
        except Exception as e:
            # Other error
            self.logger.error(f"Error processing vote from user {interaction.user.id}: {e}", exc_info=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred while processing your vote. Please try again.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ An error occurred while processing your vote. Please try again.",
                        ephemeral=True
                    )
            except Exception as followup_error:
                self.logger.error(f"Failed to send error message: {followup_error}")
    
    def _parse_dates(self, dates_input: str) -> list[str]:
        """
        Parse and validate date input.
        
        Args:
            dates_input: Comma-separated date string (e.g., "15,16,20")
        
        Returns:
            List of validated date strings in YYYY-MM-DD format
        
        Raises:
            ValueError: If dates are invalid
        """
        if not dates_input:
            raise ValueError("Dates cannot be empty. Please enter at least one date.")
        
        # Split by comma and clean up
        date_parts = [d.strip() for d in dates_input.split(",") if d.strip()]
        
        if not date_parts:
            raise ValueError("No valid dates provided. Please enter dates as day numbers (e.g., 15,16,20).")
        
        # Get current month info
        now = datetime.utcnow()
        current_year = now.year
        current_month = now.month
        current_day = now.day
        
        # Get the last day of the current month
        if current_month == 12:
            next_month = datetime(current_year + 1, 1, 1)
        else:
            next_month = datetime(current_year, current_month + 1, 1)
        
        last_day = (next_month - timedelta(days=1)).day
        
        parsed_dates = []
        for date_str in date_parts:
            try:
                # Try to parse as day number
                day = int(date_str)
                
                # Validate day is in valid range (must be valid day number)
                if day < 1:
                    raise ValueError(f"Date {day} is not a valid day number. Days must be between 1 and {last_day}.")
                
                if day > last_day:
                    raise ValueError(f"Date {day} is not valid for this month. This month has {last_day} days.")
                
                # Validate day is not in the past
                if day < current_day:
                    raise ValueError(f"Date {day} is in the past. Today is day {current_day}. Please choose dates from today onwards.")
                
                # Create full date string
                date = datetime(current_year, current_month, day)
                parsed_dates.append(date.strftime("%Y-%m-%d"))
                
            except ValueError as e:
                if "invalid literal" in str(e):
                    raise ValueError(f"'{date_str}' is not a valid day number. Please enter numbers only (e.g., 15,16,20).")
                else:
                    raise
        
        if not parsed_dates:
            raise ValueError("No valid dates could be parsed. Please enter dates as day numbers (e.g., 15,16,20).")
        
        return parsed_dates
    
    def _parse_times(self, times_input: str) -> list[str]:
        """
        Parse and validate time input.
        
        Args:
            times_input: Comma-separated time string (e.g., "5pm,6pm,7pm")
        
        Returns:
            List of validated time strings in HH:MM format
        
        Raises:
            ValueError: If times are invalid
        """
        if not times_input:
            raise ValueError("Times cannot be empty. Please enter at least one time.")
        
        # Split by comma and clean up
        time_parts = [t.strip().lower() for t in times_input.split(",") if t.strip()]
        
        if not time_parts:
            raise ValueError("No valid times provided. Please enter times in format like 5pm,6pm,7pm.")
        
        parsed_times = []
        for time_str in time_parts:
            try:
                # Parse time format like "5pm", "6pm", "11pm"
                time_str = time_str.replace(" ", "")
                
                # Check if it ends with am/pm
                if time_str.endswith("pm"):
                    hour_str = time_str[:-2]
                    
                    if not hour_str:
                        raise ValueError(f"'{time_str}' is missing the hour number. Use format like 5pm, 6pm, etc.")
                    
                    hour = int(hour_str)
                    
                    # Validate hour is reasonable (1-12 for 12-hour format)
                    if hour < 1 or hour > 12:
                        raise ValueError(f"Hour {hour} is not valid. Use hours 1-12 with pm (e.g., 5pm, 11pm).")
                    
                    # Convert to 24-hour format
                    if hour == 12:
                        hour_24 = 12
                    else:
                        hour_24 = hour + 12
                        
                elif time_str.endswith("am"):
                    hour_str = time_str[:-2]
                    
                    if not hour_str:
                        raise ValueError(f"'{time_str}' is missing the hour number. Use format like 5pm, 6pm, etc.")
                    
                    hour = int(hour_str)
                    
                    # Validate hour is reasonable (1-12 for 12-hour format)
                    if hour < 1 or hour > 12:
                        raise ValueError(f"Hour {hour} is not valid. Use hours 1-12 with am/pm.")
                    
                    # Convert to 24-hour format
                    if hour == 12:
                        hour_24 = 0
                    else:
                        hour_24 = hour
                else:
                    raise ValueError(f"'{time_str}' must end with 'am' or 'pm'. Use format like 5pm, 6pm, 7pm.")
                
                # Validate hour is in valid range (5pm-11pm = 17:00-23:00)
                if hour_24 < 17 or hour_24 > 23:
                    # Provide helpful message about valid range
                    if hour_24 < 17:
                        raise ValueError(f"Time {time_str} is too early. Valid times are 5pm through 11pm.")
                    else:
                        raise ValueError(f"Time {time_str} is too late. Valid times are 5pm through 11pm.")
                
                # Format as HH:MM
                parsed_times.append(f"{hour_24:02d}:00")
                
            except ValueError as e:
                if "invalid literal" in str(e):
                    raise ValueError(f"'{time_str}' is not a valid time format. Use format like 5pm, 6pm, 7pm.")
                else:
                    raise
        
        if not parsed_times:
            raise ValueError("No valid times could be parsed. Please enter times in format like 5pm,6pm,7pm.")
        
        return parsed_times
    

    def _format_date_display(self, date_str: str) -> str:
        """
        Format date string for display.
        
        Args:
            date_str: Date string in YYYY-MM-DD format
        
        Returns:
            Formatted date string (e.g., "Oct 15")
        """
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.strftime("%b %d")
    
    def _format_time_display(self, time_str: str) -> str:
        """
        Format time string for display.
        
        Args:
            time_str: Time string in HH:MM format
        
        Returns:
            Formatted time string (e.g., "5pm")
        """
        hour = int(time_str.split(":")[0])
        if hour >= 12:
            time_12hr = f"{hour - 12 if hour > 12 else 12}pm"
        else:
            time_12hr = f"{hour}am"
        return time_12hr


async def update_poll_embed(bot, channel, event: Event) -> bool:
    """
    Update the poll message embed to show current vote counts.
    
    This function builds an embed showing:
    - Event title and expiration time
    - Vote counts per date (e.g., "Oct 15: 3 votes ⭐")
    - Vote counts per time (e.g., "5pm: 2 votes ⭐")
    - Instructions for voting
    
    Args:
        bot: Bot instance
        channel: Discord channel containing the poll message
        event: Event model instance with current vote data
    
    Returns:
        bool: True if update was successful, False otherwise
    """
    logger = get_logger(__name__)
    
    try:
        # Validate we have a message to update
        if not event.message_id:
            logger.warning(f"Event {event.id} has no message_id, cannot update poll embed")
            return False
        
        # Fetch the poll message
        try:
            poll_message = await channel.fetch_message(int(event.message_id))
        except discord.NotFound:
            logger.error(f"Poll message {event.message_id} not found for event {event.id}")
            return False
        except discord.Forbidden:
            logger.error(f"No permission to fetch message {event.message_id}")
            return False
        
        # Get vote counts
        date_counts, time_counts = event.get_vote_counts()
        
        # Create updated embed
        embed = discord.Embed(
            title=f"📅 {event.title}",
            description="Vote for your preferred dates and times!",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Generate all available date options
        now = datetime.utcnow()
        current_year = now.year
        current_month = now.month
        current_day = now.day
        
        # Get the last day of the current month
        if current_month == 12:
            next_month = datetime(current_year + 1, 1, 1)
        else:
            next_month = datetime(current_year, current_month + 1, 1)
        
        last_day = (next_month - timedelta(days=1)).day
        
        all_dates = []
        for day in range(current_day, last_day + 1):
            date = datetime(current_year, current_month, day)
            all_dates.append(date.strftime("%Y-%m-%d"))
        
        # Generate all available time options (5pm-11pm)
        all_times = [f"{hour:02d}:00" for hour in range(17, 24)]
        
        # Format date options with vote counts
        date_display = []
        for date_str in all_dates:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%b %d")
            vote_count = date_counts.get(date_str, 0)
            
            if vote_count > 0:
                stars = "⭐" * min(vote_count, 5)  # Max 5 stars for display
                date_display.append(f"{formatted_date}: {vote_count} vote{'s' if vote_count != 1 else ''} {stars}")
            else:
                date_display.append(f"{formatted_date}: 0 votes")
        
        # Format time options with vote counts
        time_display = []
        for time_str in all_times:
            hour = int(time_str.split(":")[0])
            if hour >= 12:
                formatted_time = f"{hour - 12 if hour > 12 else 12}pm"
            else:
                formatted_time = f"{hour}am"
            
            vote_count = time_counts.get(time_str, 0)
            
            if vote_count > 0:
                stars = "⭐" * min(vote_count, 5)  # Max 5 stars for display
                time_display.append(f"{formatted_time}: {vote_count} vote{'s' if vote_count != 1 else ''} {stars}")
            else:
                time_display.append(f"{formatted_time}: 0 votes")
        
        # Add fields to embed
        embed.add_field(
            name="📆 Date Votes",
            value="\n".join(date_display) if date_display else "No dates available",
            inline=False
        )
        
        embed.add_field(
            name="🕐 Time Votes",
            value="\n".join(time_display) if time_display else "No times available",
            inline=False
        )
        
        embed.add_field(
            name="⏰ Poll Expires",
            value=f"<t:{int(event.expires_at.timestamp())}:R> (<t:{int(event.expires_at.timestamp())}:F>)",
            inline=False
        )
        
        embed.add_field(
            name="📝 How to Vote",
            value="Click the **Vote** button below to select your preferred dates and times!",
            inline=False
        )
        
        embed.set_footer(text=f"Created by user ID: {event.creator_id}")
        
        # Update the message
        await poll_message.edit(embed=embed)
        
        logger.info(f"Successfully updated poll embed for event {event.id}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating poll embed for event {event.id}: {e}", exc_info=True)
        return False


class PollView(discord.ui.View):
    """View containing the Vote button for the poll."""
    
    def __init__(self, event_id: str, bot):
        super().__init__(timeout=None)  # Persistent view
        self.event_id = event_id
        self.bot = bot
        self.logger = get_logger(__name__)
    
    @discord.ui.button(label="Vote", style=discord.ButtonStyle.primary, emoji="🗳️")
    async def vote_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        """Handle Vote button click - opens VoteView."""
        try:
            self.logger.info(
                f"User {interaction.user.id} clicked Vote button for event {self.event_id}"
            )
            
            # Fetch event data
            try:
                event_data = await self.bot.database.find_one("events", {"_id": self.event_id})
            except DatabaseError as e:
                self.logger.error(f"Database error fetching event {self.event_id}: {e}", exc_info=True)
                await interaction.response.send_message(
                    "❌ Failed to retrieve event from database. Please try again later.",
                    ephemeral=True
                )
                return
            
            if not event_data:
                self.logger.error(f"Event {self.event_id} not found in database")
                await interaction.response.send_message(
                    "❌ Event not found. It may have been deleted.",
                    ephemeral=True
                )
                return
            
            # Check if event is still active
            if event_data.get("status") != "active":
                await interaction.response.send_message(
                    "❌ This poll has ended and is no longer accepting votes.",
                    ephemeral=True
                )
                return
            
            # Create and send VoteView
            vote_view = VoteView(self.event_id, self.bot, event_data)
            await interaction.response.send_message(
                "**🗳️ Cast Your Vote**\n\n"
                "Select the dates and times that work for you, then click **Submit Vote**.\n"
                "You can select multiple options for both dates and times!",
                view=vote_view,
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error handling vote button click: {e}", exc_info=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred. Please try again.",
                        ephemeral=True
                    )
            except Exception as followup_error:
                self.logger.error(f"Failed to send error message: {followup_error}")


class EventsCog(commands.Cog):
    """
    Simplified cog for managing game night events.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = get_logger(__name__)
        self.logger.info("EventsCog initialized")
        
        # Start the background task for poll expiration
        self.check_expired_polls.start()
        self.logger.info("Poll expiration background task started")
    
    def cog_unload(self):
        """Called when the cog is unloaded."""
        # Stop the background task
        self.check_expired_polls.cancel()
        self.logger.info("Poll expiration background task stopped")
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Called when the cog is ready."""
        self.logger.info("EventsCog ready")
    
    @tasks.loop(hours=1)
    async def check_expired_polls(self):
        """
        Background task that runs every hour to check for expired polls.
        
        For each expired poll:
        1. Calculate winning date and time
        2. Create Discord Scheduled Event (if no tie)
        3. Update poll message with results
        4. Handle ties by notifying admins
        """
        try:
            self.logger.info("Checking for expired polls...")
            
            # Query database for events where expires_at < now and status="active"
            now = datetime.utcnow()
            try:
                expired_events = await self.bot.database.find_many(
                    "events",
                    {
                        "expires_at": {"$lt": now},
                        "status": "active"
                    }
                )
            except DatabaseError as e:
                self.logger.error(f"Database error querying expired polls: {e}", exc_info=True)
                # Don't crash the background task, just skip this iteration
                return
            
            if not expired_events:
                self.logger.info("No expired polls found")
                return
            
            self.logger.info(f"Found {len(expired_events)} expired poll(s)")
            
            # Process each expired poll
            for event_data in expired_events:
                try:
                    event = Event(**event_data)
                    self.logger.info(
                        f"Processing expired poll for event {event.id} ('{event.title}') "
                        f"in guild {event.guild_id}"
                    )
                    
                    # Calculate winner
                    winning_date, winning_time, is_tie, tied_dates, tied_times = event.calculate_winner()
                    
                    if is_tie:
                        # Handle tie - notify admins (task 13)
                        self.logger.info(
                            f"Event {event.id} has a tie. "
                            f"Tied dates: {tied_dates}, Tied times: {tied_times}"
                        )
                        await self._handle_poll_tie(event, tied_dates, tied_times)
                    else:
                        # Create Discord Scheduled Event (task 11)
                        self.logger.info(
                            f"Event {event.id} has a winner. "
                            f"Date: {winning_date}, Time: {winning_time}"
                        )
                        await self._create_scheduled_event(event, winning_date, winning_time)
                    
                except Exception as e:
                    self.logger.error(
                        f"Error processing expired event {event_data.get('_id', 'unknown')}: {e}",
                        exc_info=True
                    )
                    # Continue processing other events
                    continue
            
            self.logger.info("Finished checking expired polls")
            
        except Exception as e:
            self.logger.error(f"Error in check_expired_polls task: {e}", exc_info=True)
    
    @check_expired_polls.before_loop
    async def before_check_expired_polls(self):
        """Wait for the bot to be ready before starting the background task."""
        await self.bot.wait_until_ready()
        self.logger.info("Bot is ready, poll expiration task will now run")
    
    async def _handle_poll_tie(self, event: Event, tied_dates: list[str], tied_times: list[str]):
        """
        Handle a poll that ended in a tie.
        
        This function:
        - Finds guild's system channel or first text channel
        - Sends admin notification about the tie
        - Updates event status to "tie"
        
        Args:
            event: Event model instance
            tied_dates: List of tied date options
            tied_times: List of tied time options
        """
        self.logger.info(f"Handling tie for event {event.id}")
        
        try:
            # Get the guild
            guild = self.bot.get_guild(int(event.guild_id))
            if not guild:
                self.logger.error(f"Guild {event.guild_id} not found for event {event.id}")
                # Still update status to "tie"
                try:
                    await self.bot.database.update_one(
                        "events",
                        {"_id": event.id},
                        {"$set": {"status": "tie"}}
                    )
                except DatabaseError as e:
                    self.logger.error(f"Database error updating event {event.id} status to 'tie': {e}", exc_info=True)
                return
            
            # Find notification channel: system channel or first text channel
            notification_channel = None
            
            # Try system channel first
            if guild.system_channel:
                notification_channel = guild.system_channel
                self.logger.info(f"Using system channel {notification_channel.id} for tie notification")
            else:
                # Find first text channel the bot can send messages to
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).send_messages:
                        notification_channel = channel
                        self.logger.info(f"Using first available text channel {notification_channel.id} for tie notification")
                        break
            
            if not notification_channel:
                self.logger.error(f"No suitable channel found in guild {event.guild_id} for tie notification")
                # Still update status to "tie"
                try:
                    await self.bot.database.update_one(
                        "events",
                        {"_id": event.id},
                        {"$set": {"status": "tie"}}
                    )
                except DatabaseError as e:
                    self.logger.error(f"Database error updating event {event.id} status to 'tie': {e}", exc_info=True)
                return
            
            # Format tied dates for display
            tied_dates_display = []
            for date_str in tied_dates:
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    tied_dates_display.append(date_obj.strftime("%b %d"))
                except ValueError:
                    tied_dates_display.append(date_str)
            
            # Format tied times for display
            tied_times_display = []
            for time_str in tied_times:
                try:
                    hour = int(time_str.split(":")[0])
                    if hour >= 12:
                        time_12hr = f"{hour - 12 if hour > 12 else 12}pm"
                    else:
                        time_12hr = f"{hour}am"
                    tied_times_display.append(time_12hr)
                except (ValueError, IndexError):
                    tied_times_display.append(time_str)
            
            # Build tie message
            tie_parts = []
            if tied_dates:
                tie_parts.append(f"**Tied dates:** {', '.join(tied_dates_display)}")
            if tied_times:
                tie_parts.append(f"**Tied times:** {', '.join(tied_times_display)}")
            
            # Handle case where no votes were cast
            if not tied_dates and not tied_times:
                tie_message = "No votes were cast on this poll."
            else:
                tie_message = " or ".join(tie_parts) if tie_parts else "Unknown tie condition"
            
            # Create link to original poll message
            poll_link = f"https://discord.com/channels/{event.guild_id}/{event.channel_id}/{event.message_id}"
            
            # Send notification message
            notification_text = (
                f"⚠️ **Poll tie for event '{event.title}'!**\n\n"
                f"{tie_message}\n\n"
                f"**Event ID:** `{event.id}`\n"
                f"**Original Poll:** [Click here to view]({poll_link})\n\n"
                f"Please manually resolve this tie and create a scheduled event."
            )
            
            await notification_channel.send(notification_text)
            
            self.logger.info(
                f"Sent tie notification for event {event.id} to channel {notification_channel.id}"
            )
            
            # Update event status to "tie"
            try:
                await self.bot.database.update_one(
                    "events",
                    {"_id": event.id},
                    {"$set": {"status": "tie"}}
                )
                self.logger.info(f"Event {event.id} status updated to 'tie'")
            except DatabaseError as e:
                self.logger.error(f"Database error updating event {event.id} status to 'tie': {e}", exc_info=True)
            
        except discord.Forbidden:
            self.logger.error(
                f"Missing permissions to send tie notification in guild {event.guild_id}"
            )
            # Still update status to "tie"
            try:
                await self.bot.database.update_one(
                    "events",
                    {"_id": event.id},
                    {"$set": {"status": "tie"}}
                )
            except DatabaseError as e:
                self.logger.error(f"Database error updating event {event.id} status to 'tie': {e}", exc_info=True)
        except Exception as e:
            self.logger.error(
                f"Error handling tie for event {event.id}: {e}",
                exc_info=True
            )
            # Still update status to "tie"
            try:
                await self.bot.database.update_one(
                    "events",
                    {"_id": event.id},
                    {"$set": {"status": "tie"}}
                )
            except DatabaseError as e:
                self.logger.error(f"Database error updating event {event.id} status to 'tie': {e}", exc_info=True)
    
    async def _create_scheduled_event(self, event: Event, winning_date: str, winning_time: str):
        """
        Create a Discord Scheduled Event for the winning date/time.
        
        This function:
        - Combines winning_date and winning_time into datetime
        - Creates Discord Scheduled Event with retry logic
        - Stores discord_event_id in database
        - Updates event status to "scheduled"
        - Updates poll message with results (task 12)
        
        Args:
            event: Event model instance
            winning_date: Winning date string (YYYY-MM-DD)
            winning_time: Winning time string (HH:MM)
        """
        self.logger.info(
            f"Creating scheduled event for event {event.id} "
            f"with date {winning_date} and time {winning_time}"
        )
        
        try:
            # Get the guild
            guild = self.bot.get_guild(int(event.guild_id))
            if not guild:
                self.logger.error(f"Guild {event.guild_id} not found for event {event.id}")
                # Update status to expired but keep winning date/time
                try:
                    await self.bot.database.update_one(
                        "events",
                        {"_id": event.id},
                        {"$set": {
                            "winning_date": winning_date,
                            "winning_time": winning_time,
                            "status": "expired"
                        }}
                    )
                except DatabaseError as e:
                    self.logger.error(f"Database error updating event {event.id} after guild not found: {e}", exc_info=True)
                return
            
            # Combine winning_date and winning_time into datetime object
            # winning_date format: YYYY-MM-DD
            # winning_time format: HH:MM
            date_parts = winning_date.split("-")
            time_parts = winning_time.split(":")
            
            event_datetime = datetime(
                year=int(date_parts[0]),
                month=int(date_parts[1]),
                day=int(date_parts[2]),
                hour=int(time_parts[0]),
                minute=int(time_parts[1])
            )
            
            self.logger.info(f"Event datetime: {event_datetime}")
            
            # Create Discord Scheduled Event with retry logic
            scheduled_event = await self._create_scheduled_event_with_retry(
                guild, event, event_datetime
            )
            
            if not scheduled_event:
                # All retries failed
                self.logger.error(
                    f"Failed to create scheduled event for event {event.id} after all retries"
                )
                # Update with winning date/time but keep status as expired
                try:
                    await self.bot.database.update_one(
                        "events",
                        {"_id": event.id},
                        {"$set": {
                            "winning_date": winning_date,
                            "winning_time": winning_time,
                            "status": "expired"
                        }}
                    )
                except DatabaseError as e:
                    self.logger.error(f"Database error updating event {event.id} after scheduled event creation failed: {e}", exc_info=True)
                
                # Send error message to channel
                await self._send_scheduled_event_failure_message(event, winning_date, winning_time)
                return
            
            self.logger.info(
                f"Discord Scheduled Event created with ID {scheduled_event.id} "
                f"for event {event.id}"
            )
            
            # Store discord_event_id in event document and update status to "scheduled"
            try:
                await self.bot.database.update_one(
                    "events",
                    {"_id": event.id},
                    {"$set": {
                        "winning_date": winning_date,
                        "winning_time": winning_time,
                        "discord_event_id": str(scheduled_event.id),
                        "status": "scheduled"
                    }}
                )
                self.logger.info(
                    f"Event {event.id} updated with discord_event_id {scheduled_event.id} "
                    f"and status 'scheduled'"
                )
            except DatabaseError as e:
                self.logger.error(f"Database error updating event {event.id} with scheduled event details: {e}", exc_info=True)
                # Event was created in Discord but not saved to DB - log critical error
                self.logger.critical(
                    f"CRITICAL: Discord event {scheduled_event.id} created but failed to save to database for event {event.id}. "
                    f"Manual intervention may be required."
                )
            
            # Update poll message with results (task 12)
            # Update event object with new data
            event.winning_date = winning_date
            event.winning_time = winning_time
            event.discord_event_id = str(scheduled_event.id)
            event.status = "scheduled"
            
            await self._update_poll_with_results(event, scheduled_event)
            
        except discord.Forbidden:
            self.logger.error(
                f"Missing permissions to create scheduled event in guild {event.guild_id} "
                f"for event {event.id}"
            )
            # Update with winning date/time but keep status as expired
            try:
                await self.bot.database.update_one(
                    "events",
                    {"_id": event.id},
                    {"$set": {
                        "winning_date": winning_date,
                        "winning_time": winning_time,
                        "status": "expired"
                    }}
                )
            except DatabaseError as e:
                self.logger.error(f"Database error updating event {event.id} after permission error: {e}", exc_info=True)
            # Send error message to channel
            await self._send_scheduled_event_failure_message(
                event, winning_date, winning_time, 
                error_msg="Missing permissions to create scheduled events"
            )
        except Exception as e:
            self.logger.error(
                f"Error creating scheduled event for event {event.id}: {e}",
                exc_info=True
            )
            # Update with winning date/time but keep status as expired
            try:
                await self.bot.database.update_one(
                    "events",
                    {"_id": event.id},
                    {"$set": {
                        "winning_date": winning_date,
                        "winning_time": winning_time,
                        "status": "expired"
                    }}
                )
            except DatabaseError as e:
                self.logger.error(f"Database error updating event {event.id} after error: {e}", exc_info=True)
            # Send error message to channel
            await self._send_scheduled_event_failure_message(event, winning_date, winning_time)
    
    async def _create_scheduled_event_with_retry(
        self, 
        guild: discord.Guild, 
        event: Event, 
        event_datetime: datetime,
        max_retries: int = 3
    ) -> Optional[discord.ScheduledEvent]:
        """
        Create a Discord Scheduled Event with retry logic and exponential backoff.
        
        Args:
            guild: Discord guild object
            event: Event model instance
            event_datetime: Datetime for the scheduled event
            max_retries: Maximum number of retry attempts (default: 3)
        
        Returns:
            ScheduledEvent object if successful, None if all retries failed
        """
        import asyncio
        
        for attempt in range(max_retries):
            try:
                self.logger.info(
                    f"Attempt {attempt + 1}/{max_retries} to create scheduled event "
                    f"for event {event.id}"
                )
                
                # Create Discord Scheduled Event
                scheduled_event = await guild.create_scheduled_event(
                    name=event.title,
                    start_time=event_datetime,
                    location="Discord",
                    description=f"Game night event created via poll",
                    privacy_level=discord.ScheduledEventPrivacyLevel.guild_only
                )
                
                self.logger.info(
                    f"Successfully created scheduled event on attempt {attempt + 1} "
                    f"for event {event.id}"
                )
                return scheduled_event
                
            except discord.Forbidden:
                # Permission error - don't retry
                self.logger.error(
                    f"Permission denied creating scheduled event for event {event.id}. "
                    f"Not retrying."
                )
                raise
                
            except discord.HTTPException as e:
                # HTTP error - retry with exponential backoff
                self.logger.warning(
                    f"HTTP error on attempt {attempt + 1}/{max_retries} "
                    f"creating scheduled event for event {event.id}: {e}"
                )
                
                if attempt < max_retries - 1:
                    # Calculate exponential backoff: 2^attempt seconds
                    backoff_time = 2 ** attempt
                    self.logger.info(
                        f"Retrying in {backoff_time} seconds... "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(backoff_time)
                else:
                    self.logger.error(
                        f"All {max_retries} attempts failed to create scheduled event "
                        f"for event {event.id}"
                    )
                    return None
                    
            except Exception as e:
                # Unexpected error - log and retry
                self.logger.error(
                    f"Unexpected error on attempt {attempt + 1}/{max_retries} "
                    f"creating scheduled event for event {event.id}: {e}",
                    exc_info=True
                )
                
                if attempt < max_retries - 1:
                    # Calculate exponential backoff: 2^attempt seconds
                    backoff_time = 2 ** attempt
                    self.logger.info(
                        f"Retrying in {backoff_time} seconds... "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(backoff_time)
                else:
                    self.logger.error(
                        f"All {max_retries} attempts failed to create scheduled event "
                        f"for event {event.id}"
                    )
                    return None
        
        return None
    
    async def _send_scheduled_event_failure_message(
        self, 
        event: Event, 
        winning_date: str, 
        winning_time: str,
        error_msg: Optional[str] = None
    ):
        """
        Send an error message to the channel when scheduled event creation fails.
        
        Args:
            event: Event model instance
            winning_date: Winning date string (YYYY-MM-DD)
            winning_time: Winning time string (HH:MM)
            error_msg: Optional specific error message
        """
        try:
            # Get the channel
            channel = self.bot.get_channel(int(event.channel_id))
            if not channel:
                self.logger.error(
                    f"Channel {event.channel_id} not found, cannot send failure message "
                    f"for event {event.id}"
                )
                return
            
            # Format winning date and time for display
            date_obj = datetime.strptime(winning_date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%A, %B %d, %Y")
            
            hour = int(winning_time.split(":")[0])
            if hour >= 12:
                formatted_time = f"{hour - 12 if hour > 12 else 12}:00 PM"
            else:
                formatted_time = f"{hour}:00 AM"
            
            # Build error message
            error_embed = discord.Embed(
                title=f"⚠️ {event.title}",
                description="**Failed to Create Scheduled Event**",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            
            error_embed.add_field(
                name="📊 Poll Results",
                value=(
                    f"**Winning Date:** {formatted_date}\n"
                    f"**Winning Time:** {formatted_time}"
                ),
                inline=False
            )
            
            if error_msg:
                error_embed.add_field(
                    name="❌ Error",
                    value=error_msg,
                    inline=False
                )
            else:
                error_embed.add_field(
                    name="❌ Error",
                    value="Failed to create Discord Scheduled Event after multiple attempts.",
                    inline=False
                )
            
            error_embed.add_field(
                name="🔧 Manual Action Required",
                value=(
                    "Please manually create a scheduled event with the winning date and time above. "
                    f"Event data has been saved (Event ID: `{event.id}`)."
                ),
                inline=False
            )
            
            error_embed.set_footer(text=f"Event ID: {event.id}")
            
            # Send error message to channel
            await channel.send(embed=error_embed)
            
            self.logger.info(
                f"Sent scheduled event failure message to channel {channel.id} "
                f"for event {event.id}"
            )
            
        except discord.Forbidden:
            self.logger.error(
                f"Missing permissions to send failure message in channel {event.channel_id} "
                f"for event {event.id}"
            )
        except Exception as e:
            self.logger.error(
                f"Error sending failure message for event {event.id}: {e}",
                exc_info=True
            )
    
    async def _update_poll_with_results(self, event: Event, scheduled_event: discord.ScheduledEvent):
        """
        Update the poll message to show the event has been scheduled.
        
        This function:
        - Edits the original poll message
        - Shows "✅ Event Scheduled!" status
        - Displays winning date and time
        - Adds link to Discord Scheduled Event
        - Removes vote button (poll is closed)
        
        Args:
            event: Event model instance with winning date/time
            scheduled_event: Discord ScheduledEvent object
        """
        self.logger.info(f"Updating poll message for event {event.id} with results")
        
        try:
            # Get the channel
            channel = self.bot.get_channel(int(event.channel_id))
            if not channel:
                self.logger.error(f"Channel {event.channel_id} not found for event {event.id}")
                return
            
            # Get the poll message
            try:
                poll_message = await channel.fetch_message(int(event.message_id))
            except discord.NotFound:
                self.logger.error(f"Poll message {event.message_id} not found for event {event.id}")
                return
            except discord.Forbidden:
                self.logger.error(f"No permission to fetch message {event.message_id}")
                return
            
            # Format winning date and time for display
            date_obj = datetime.strptime(event.winning_date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%A, %B %d, %Y")
            
            hour = int(event.winning_time.split(":")[0])
            if hour >= 12:
                formatted_time = f"{hour - 12 if hour > 12 else 12}:00 PM"
            else:
                formatted_time = f"{hour}:00 AM"
            
            # Create updated embed showing results
            embed = discord.Embed(
                title=f"✅ {event.title}",
                description="**Event Scheduled!**",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="📅 Scheduled Date",
                value=formatted_date,
                inline=False
            )
            
            embed.add_field(
                name="🕐 Scheduled Time",
                value=formatted_time,
                inline=False
            )
            
            # Add link to Discord Scheduled Event
            # Discord event URLs: https://discord.com/events/{guild_id}/{event_id}
            event_url = f"https://discord.com/events/{event.guild_id}/{scheduled_event.id}"
            embed.add_field(
                name="🔗 Event Link",
                value=f"[Click here to view the scheduled event]({event_url})",
                inline=False
            )
            
            embed.add_field(
                name="📊 Poll Results",
                value="The poll has closed and the event has been scheduled based on the votes.",
                inline=False
            )
            
            embed.set_footer(text=f"Poll closed • Created by user ID: {event.creator_id}")
            
            # Update the message without the vote button (remove view)
            await poll_message.edit(embed=embed, view=None)
            
            self.logger.info(f"Successfully updated poll message for event {event.id}")
            
        except Exception as e:
            self.logger.error(
                f"Error updating poll message for event {event.id}: {e}",
                exc_info=True
            )
    
    @discord.slash_command(
        name="event",
        description="Create a game night event with automatic poll"
    )
    async def event_create(self, ctx: discord.ApplicationContext):
        """
        Create a new game night event.
        
        This command opens a modal where users can enter an event title.
        After submission, a poll will be created for date/time voting.
        """
        try:
            self.logger.info(
                f"User {ctx.author.id} ({ctx.author.name}) initiated event creation "
                f"in guild {ctx.guild.id if ctx.guild else 'DM'}"
            )
            
            # Ensure command is used in a guild
            if not ctx.guild:
                await ctx.respond(
                    "❌ This command can only be used in a server, not in DMs.",
                    ephemeral=True
                )
                return
            
            # Send the modal to the user
            modal = EventCreationModal(self.bot)
            await ctx.send_modal(modal)
            
            self.logger.info(f"Event creation modal sent to user {ctx.author.id}")
            
        except discord.Forbidden:
            self.logger.error(f"Missing permissions to send modal in guild {ctx.guild.id}")
            await ctx.respond(
                "❌ I don't have permission to send modals. Please check my permissions.",
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(
                f"Error in event_create command for user {ctx.author.id}: {e}",
                exc_info=True
            )
            # Try to respond if we haven't already
            try:
                if not ctx.response.is_done():
                    await ctx.respond(
                        "❌ An error occurred while creating the event. Please try again.",
                        ephemeral=True
                    )
                else:
                    await ctx.followup.send(
                        "❌ An error occurred while creating the event. Please try again.",
                        ephemeral=True
                    )
            except Exception as followup_error:
                self.logger.error(f"Failed to send error message: {followup_error}")


def setup(bot):
    """Load the EventsCog."""
    bot.add_cog(EventsCog(bot))
