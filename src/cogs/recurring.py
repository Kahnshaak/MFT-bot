"""
Recurring events cog for automated event creation and management.
"""

import asyncio
from datetime import datetime, date, time, timedelta
from typing import Optional, List, Dict, Any
import uuid
from bson import ObjectId

import discord
from discord.ext import commands, tasks
try:
    from discord import app_commands
except ImportError:
    # Create a mock app_commands for testing
    class MockAppCommands:
        @staticmethod
        def command(**kwargs):
            def decorator(func):
                return func
            return decorator
        
        @staticmethod
        def describe(**kwargs):
            def decorator(func):
                return func
            return decorator
        
        @staticmethod
        def choices(**kwargs):
            def decorator(func):
                return func
            return decorator
        
        class Choice:
            def __init__(self, name, value):
                self.name = name
                self.value = value
    
    app_commands = MockAppCommands()

from models.recurring import (
    RecurringSchedule, ScheduleTrigger, EventTemplate, ExecutionHistory,
    TriggerType, ScheduleStatus, ExecutionStatus
)
from models.event import Event, EventState
from core.event_bus import EventBus, EventType
from core.permission_decorators import require_permission
from core.security_manager import Permission
from core.validation_manager import ValidationManager
from utils.exceptions import ValidationError, PermissionDeniedError, ErrorCode
from utils.logging_config import get_logger, LoggerMixin


class ScheduleCreationModal(discord.ui.Modal):
    """Modal for creating recurring schedules."""
    
    def __init__(self, cog: 'RecurringCog'):
        super().__init__(title="Create Recurring Schedule")
        self.cog = cog
        
        # Schedule name input
        self.name_input = discord.ui.TextInput(
            label="Schedule Name",
            placeholder="Enter a name for this recurring schedule...",
            min_length=1,
            max_length=100,
            required=True
        )
        self.add_item(self.name_input)
        
        # Description input
        self.description_input = discord.ui.TextInput(
            label="Description (Optional)",
            placeholder="Describe this recurring schedule...",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=False
        )
        self.add_item(self.description_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        try:
            # Validate inputs
            name = self.cog.validation.sanitize_text(self.name_input.value, 100)
            description = None
            if self.description_input.value:
                description = self.cog.validation.sanitize_text(self.description_input.value, 500)
            
            # Create schedule configuration view
            view = ScheduleConfigurationView(self.cog, name, description, str(interaction.user.id))
            
            embed = discord.Embed(
                title="🔄 Configure Recurring Schedule",
                description=f"**Name:** {name}\n**Description:** {description or 'None'}",
                color=0x3498db
            )
            embed.add_field(
                name="Next Steps",
                value="Use the buttons below to configure your recurring schedule:",
                inline=False
            )
            
            await interaction.response.send_message(
                embed=embed,
                view=view,
                ephemeral=True
            )
            
        except ValidationError as e:
            await interaction.response.send_message(
                f"❌ Invalid input: {e.user_message}",
                ephemeral=True
            )
        except Exception as e:
            self.cog.logger.error(f"Error in schedule creation modal: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ Something went wrong. Please try again.",
                ephemeral=True
            )


class ScheduleConfigurationView(discord.ui.View):
    """View for configuring recurring schedule parameters."""
    
    def __init__(self, cog: 'RecurringCog', name: str, description: Optional[str], creator_id: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.name = name
        self.description = description
        self.creator_id = creator_id
        
        # Configuration state
        self.trigger_type: Optional[TriggerType] = None
        self.trigger_time: Optional[time] = None
        self.day_of_week: Optional[int] = None
        self.day_of_month: Optional[int] = None
        self.timezone: str = "UTC"
        self.event_template: Optional[EventTemplate] = None
    
    @discord.ui.button(label="Set Trigger Type", style=discord.ButtonStyle.primary, emoji="⏰")
    async def set_trigger_type(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Set the trigger type (weekly/monthly)."""
        view = TriggerTypeSelectView(self)
        await interaction.response.send_message(
            "Select when this schedule should trigger:",
            view=view,
            ephemeral=True
        )
    
    @discord.ui.button(label="Set Event Template", style=discord.ButtonStyle.secondary, emoji="📝")
    async def set_event_template(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Set the event template."""
        modal = EventTemplateModal(self)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Create Schedule", style=discord.ButtonStyle.success, emoji="✅")
    async def create_schedule(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Create the recurring schedule."""
        # Validate configuration
        if not self.trigger_type:
            await interaction.response.send_message(
                "❌ Please set the trigger type first.",
                ephemeral=True
            )
            return
        
        if not self.trigger_time:
            await interaction.response.send_message(
                "❌ Please set the trigger time first.",
                ephemeral=True
            )
            return
        
        if not self.event_template:
            await interaction.response.send_message(
                "❌ Please set the event template first.",
                ephemeral=True
            )
            return
        
        if self.trigger_type == TriggerType.WEEKLY and self.day_of_week is None:
            await interaction.response.send_message(
                "❌ Please set the day of week for weekly triggers.",
                ephemeral=True
            )
            return
        
        if self.trigger_type == TriggerType.MONTHLY and self.day_of_month is None:
            await interaction.response.send_message(
                "❌ Please set the day of month for monthly triggers.",
                ephemeral=True
            )
            return
        
        try:
            # Create the schedule
            schedule = await self.cog.create_recurring_schedule(
                guild_id=str(interaction.guild.id),
                creator_id=self.creator_id,
                name=self.name,
                description=self.description,
                trigger_type=self.trigger_type,
                trigger_time=self.trigger_time,
                day_of_week=self.day_of_week,
                day_of_month=self.day_of_month,
                timezone=self.timezone,
                event_template=self.event_template
            )
            
            embed = discord.Embed(
                title="✅ Recurring Schedule Created",
                description=f"**{schedule.name}** has been created successfully!",
                color=0x27ae60
            )
            embed.add_field(
                name="Schedule ID",
                value=f"`{schedule.id}`",
                inline=True
            )
            embed.add_field(
                name="Next Trigger",
                value=f"<t:{int(schedule.next_trigger.timestamp())}:F>" if schedule.next_trigger else "Not scheduled",
                inline=True
            )
            
            await interaction.response.edit_message(
                embed=embed,
                view=None
            )
            
        except Exception as e:
            self.cog.logger.error(f"Error creating recurring schedule: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ Failed to create schedule. Please try again.",
                ephemeral=True
            )


class TriggerTypeSelectView(discord.ui.View):
    """View for selecting trigger type."""
    
    def __init__(self, parent_view: ScheduleConfigurationView):
        super().__init__(timeout=60)
        self.parent_view = parent_view
    
    @discord.ui.button(label="Weekly", style=discord.ButtonStyle.primary, emoji="📅")
    async def weekly_trigger(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Set weekly trigger."""
        self.parent_view.trigger_type = TriggerType.WEEKLY
        
        # Show day selection
        view = DayOfWeekSelectView(self.parent_view)
        await interaction.response.edit_message(
            content="Select the day of the week:",
            view=view
        )
    
    @discord.ui.button(label="Monthly", style=discord.ButtonStyle.secondary, emoji="🗓️")
    async def monthly_trigger(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Set monthly trigger."""
        self.parent_view.trigger_type = TriggerType.MONTHLY
        
        # Show day selection
        modal = DayOfMonthModal(self.parent_view)
        await interaction.response.send_modal(modal)


class DayOfWeekSelectView(discord.ui.View):
    """View for selecting day of week."""
    
    def __init__(self, parent_view: ScheduleConfigurationView):
        super().__init__(timeout=60)
        self.parent_view = parent_view
        
        # Add buttons for each day
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for i, day in enumerate(days):
            button = discord.ui.Button(
                label=day,
                style=discord.ButtonStyle.secondary,
                custom_id=f"day_{i}"
            )
            button.callback = self.create_day_callback(i, day)
            self.add_item(button)
    
    def create_day_callback(self, day_index: int, day_name: str):
        """Create callback for day button."""
        async def callback(interaction: discord.Interaction):
            self.parent_view.day_of_week = day_index
            
            # Show time selection
            modal = TriggerTimeModal(self.parent_view, f"Weekly on {day_name}")
            await interaction.response.send_modal(modal)
        
        return callback


class DayOfMonthModal(discord.ui.Modal):
    """Modal for selecting day of month."""
    
    def __init__(self, parent_view: ScheduleConfigurationView):
        super().__init__(title="Set Day of Month")
        self.parent_view = parent_view
        
        self.day_input = discord.ui.TextInput(
            label="Day of Month (1-31)",
            placeholder="Enter day of month (e.g., 15)",
            min_length=1,
            max_length=2,
            required=True
        )
        self.add_item(self.day_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        try:
            day = int(self.day_input.value)
            if day < 1 or day > 31:
                raise ValueError("Day must be between 1 and 31")
            
            self.parent_view.day_of_month = day
            
            # Show time selection
            modal = TriggerTimeModal(self.parent_view, f"Monthly on day {day}")
            await interaction.response.send_modal(modal)
            
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid day between 1 and 31.",
                ephemeral=True
            )


class TriggerTimeModal(discord.ui.Modal):
    """Modal for setting trigger time."""
    
    def __init__(self, parent_view: ScheduleConfigurationView, trigger_description: str):
        super().__init__(title="Set Trigger Time")
        self.parent_view = parent_view
        self.trigger_description = trigger_description
        
        self.time_input = discord.ui.TextInput(
            label="Time (HH:MM format)",
            placeholder="Enter time in 24-hour format (e.g., 19:00)",
            min_length=4,
            max_length=5,
            required=True
        )
        self.add_item(self.time_input)
        
        self.timezone_input = discord.ui.TextInput(
            label="Timezone (Optional)",
            placeholder="Enter timezone (e.g., America/New_York) or leave blank for UTC",
            max_length=50,
            required=False
        )
        self.add_item(self.timezone_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        try:
            # Parse time
            time_str = self.time_input.value.strip()
            if ':' not in time_str:
                raise ValueError("Time must be in HH:MM format")
            
            hour_str, minute_str = time_str.split(':', 1)
            hour = int(hour_str)
            minute = int(minute_str)
            
            if hour < 0 or hour > 23:
                raise ValueError("Hour must be between 0 and 23")
            if minute < 0 or minute > 59:
                raise ValueError("Minute must be between 0 and 59")
            
            self.parent_view.trigger_time = time(hour, minute)
            
            # Set timezone
            if self.timezone_input.value:
                timezone = self.timezone_input.value.strip()
                # Basic timezone validation
                import pytz
                try:
                    pytz.timezone(timezone)
                    self.parent_view.timezone = timezone
                except pytz.exceptions.UnknownTimeZoneError:
                    raise ValueError("Invalid timezone")
            
            await interaction.response.send_message(
                f"✅ Trigger set: {self.trigger_description} at {time_str} ({self.parent_view.timezone})",
                ephemeral=True
            )
            
        except ValueError as e:
            await interaction.response.send_message(
                f"❌ Invalid input: {str(e)}",
                ephemeral=True
            )


class EventTemplateModal(discord.ui.Modal):
    """Modal for creating event template."""
    
    def __init__(self, parent_view: ScheduleConfigurationView):
        super().__init__(title="Create Event Template")
        self.parent_view = parent_view
        
        self.title_input = discord.ui.TextInput(
            label="Event Title Template",
            placeholder="Enter title template (use {variables} for substitution)",
            min_length=1,
            max_length=100,
            required=True
        )
        self.add_item(self.title_input)
        
        self.description_input = discord.ui.TextInput(
            label="Event Description Template",
            placeholder="Enter description template (optional)",
            style=discord.TextStyle.paragraph,
            max_length=2000,
            required=False
        )
        self.add_item(self.description_input)
        
        self.games_input = discord.ui.TextInput(
            label="Default Games (Optional)",
            placeholder="Enter games separated by commas",
            max_length=500,
            required=False
        )
        self.add_item(self.games_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        try:
            # Parse games
            default_games = []
            if self.games_input.value:
                games_text = self.games_input.value.strip()
                default_games = [game.strip() for game in games_text.split(',') if game.strip()]
            
            # Create template
            template = EventTemplate(
                title_template=self.title_input.value.strip(),
                description_template=self.description_input.value.strip() if self.description_input.value else None,
                default_games=default_games
            )
            
            self.parent_view.event_template = template
            
            await interaction.response.send_message(
                f"✅ Event template created:\n**Title:** {template.title_template}\n**Games:** {', '.join(default_games) if default_games else 'None'}",
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error creating template: {str(e)}",
                ephemeral=True
            )


class ScheduleListView(discord.ui.View):
    """View for displaying and managing recurring schedules."""
    
    def __init__(self, cog: 'RecurringCog', schedules: List[RecurringSchedule], page: int = 0):
        super().__init__(timeout=300)
        self.cog = cog
        self.schedules = schedules
        self.page = page
        self.per_page = 5
        
        # Add navigation buttons if needed
        if len(schedules) > self.per_page:
            if page > 0:
                self.add_item(PreviousPageButton())
            if (page + 1) * self.per_page < len(schedules):
                self.add_item(NextPageButton())
    
    def get_current_schedules(self) -> List[RecurringSchedule]:
        """Get schedules for current page."""
        start = self.page * self.per_page
        end = start + self.per_page
        return self.schedules[start:end]


class PreviousPageButton(discord.ui.Button):
    """Button for previous page."""
    
    def __init__(self):
        super().__init__(label="Previous", style=discord.ButtonStyle.secondary, emoji="⬅️")
    
    async def callback(self, interaction: discord.Interaction):
        view: ScheduleListView = self.view
        new_view = ScheduleListView(view.cog, view.schedules, view.page - 1)
        embed = view.cog.create_schedules_list_embed(new_view.get_current_schedules(), new_view.page)
        await interaction.response.edit_message(embed=embed, view=new_view)


class NextPageButton(discord.ui.Button):
    """Button for next page."""
    
    def __init__(self):
        super().__init__(label="Next", style=discord.ButtonStyle.secondary, emoji="➡️")
    
    async def callback(self, interaction: discord.Interaction):
        view: ScheduleListView = self.view
        new_view = ScheduleListView(view.cog, view.schedules, view.page + 1)
        embed = view.cog.create_schedules_list_embed(new_view.get_current_schedules(), new_view.page)
        await interaction.response.edit_message(embed=embed, view=new_view)


class RecurringCog(commands.Cog, LoggerMixin):
    """
    Recurring events cog for automated event creation and management.
    
    Handles recurring event schedules, template-based event generation,
    and background processing of scheduled events.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.validation: ValidationManager = bot.validation
        self.event_bus: EventBus = bot.event_bus
        
        # Start background task for processing schedules
        self.schedule_processor.start()
        
        # Subscribe to relevant events
        self.event_bus.subscribe(EventType.SYSTEM_STARTUP, self._on_startup)
        self.event_bus.subscribe(EventType.SYSTEM_SHUTDOWN, self._on_shutdown)
    
    def cog_unload(self):
        """Clean up when cog is unloaded."""
        self.schedule_processor.cancel()
    
    async def _on_startup(self, event):
        """Handle system startup."""
        self.logger.info("Recurring events cog started")
        
        # Update next trigger times for all active schedules
        await self._update_all_schedule_triggers()
    
    async def _on_shutdown(self, event):
        """Handle system shutdown."""
        self.logger.info("Recurring events cog shutting down")
        self.schedule_processor.cancel()
    
    @tasks.loop(minutes=1)
    async def schedule_processor(self):
        """Background task to process recurring schedules."""
        try:
            current_time = datetime.utcnow()
            
            # Find schedules that are due for execution
            due_schedules = await self.bot.database.recurring_schedules.find({
                'status': ScheduleStatus.ACTIVE.value,
                'next_trigger': {'$lte': current_time}
            }).to_list(length=100)
            
            for schedule_data in due_schedules:
                schedule = RecurringSchedule(**schedule_data)
                
                if schedule.is_due_for_execution(current_time):
                    await self._execute_schedule(schedule)
            
        except Exception as e:
            self.logger.error(f"Error in schedule processor: {e}", exc_info=True)
    
    @schedule_processor.before_loop
    async def before_schedule_processor(self):
        """Wait for bot to be ready before starting schedule processor."""
        await self.bot.wait_until_ready()
    
    async def _execute_schedule(self, schedule: RecurringSchedule) -> None:
        """Execute a recurring schedule by creating an event."""
        try:
            self.logger.info(f"Executing recurring schedule: {schedule.name}")
            
            # Get template context
            context = schedule.get_template_context()
            
            # Render event details from template
            title = schedule.template.render_title(context)
            description = schedule.template.render_description(context)
            
            # Create event using events cog
            events_cog = self.bot.get_cog('EventsCog')
            if not events_cog:
                raise Exception("Events cog not found")
            
            # Create the event
            event = await events_cog.create_event(
                guild_id=schedule.guild_id,
                creator_id=schedule.creator_id,
                title=title,
                description=description
            )
            
            # Add default games to the event if specified
            if schedule.template.default_games:
                # This would be handled by the events cog's game poll creation
                pass
            
            # Record successful execution
            schedule.record_execution(
                status=ExecutionStatus.SUCCESS,
                event_id=str(event.id),
                context=context
            )
            
            # Update schedule in database
            await self.bot.database.recurring_schedules.update_one(
                {'_id': schedule.id},
                {'$set': schedule.to_dict()}
            )
            
            # Emit event
            await self.event_bus.emit(
                EventType.EVENT_CREATED,
                {
                    'event_id': str(event.id),
                    'recurring_schedule_id': str(schedule.id),
                    'execution_count': schedule.execution_count
                },
                source='recurring_cog',
                guild_id=schedule.guild_id
            )
            
            self.logger.info(f"Successfully executed recurring schedule: {schedule.name}")
            
        except Exception as e:
            self.logger.error(f"Failed to execute recurring schedule {schedule.name}: {e}", exc_info=True)
            
            # Record failed execution
            schedule.record_execution(
                status=ExecutionStatus.FAILED,
                error_message=str(e),
                context=schedule.get_template_context()
            )
            
            # Update schedule in database
            await self.bot.database.recurring_schedules.update_one(
                {'_id': schedule.id},
                {'$set': schedule.to_dict()}
            )
            
            # Notify administrators
            await self._notify_admins_of_failure(schedule, str(e))
    
    async def _notify_admins_of_failure(self, schedule: RecurringSchedule, error_message: str) -> None:
        """Notify administrators of schedule execution failure."""
        try:
            guild = self.bot.get_guild(int(schedule.guild_id))
            if not guild:
                return
            
            # Find admin channel
            admin_channel = None
            for channel in guild.text_channels:
                if 'admin' in channel.name.lower() or 'mod' in channel.name.lower():
                    admin_channel = channel
                    break
            
            if not admin_channel:
                admin_channel = guild.text_channels[0] if guild.text_channels else None
            
            if admin_channel:
                embed = discord.Embed(
                    title="🚨 Recurring Schedule Failed",
                    description=f"The recurring schedule **{schedule.name}** failed to execute.",
                    color=0xe74c3c
                )
                embed.add_field(
                    name="Error",
                    value=f"```{error_message[:1000]}```",
                    inline=False
                )
                embed.add_field(
                    name="Schedule ID",
                    value=f"`{schedule.id}`",
                    inline=True
                )
                embed.add_field(
                    name="Next Attempt",
                    value=f"<t:{int(schedule.next_trigger.timestamp())}:F>" if schedule.next_trigger else "Not scheduled",
                    inline=True
                )
                
                await admin_channel.send(embed=embed)
        
        except Exception as e:
            self.logger.error(f"Failed to notify admins of schedule failure: {e}", exc_info=True)
    
    async def _update_all_schedule_triggers(self) -> None:
        """Update next trigger times for all active schedules."""
        try:
            active_schedules = await self.bot.database.recurring_schedules.find({
                'status': ScheduleStatus.ACTIVE.value
            }).to_list(length=None)
            
            for schedule_data in active_schedules:
                schedule = RecurringSchedule(**schedule_data)
                schedule.update_next_trigger()
                
                await self.bot.database.recurring_schedules.update_one(
                    {'_id': schedule.id},
                    {'$set': {'next_trigger': schedule.next_trigger, 'updated_at': schedule.updated_at}}
                )
            
            self.logger.info(f"Updated trigger times for {len(active_schedules)} schedules")
        
        except Exception as e:
            self.logger.error(f"Error updating schedule triggers: {e}", exc_info=True)    
  
  # Slash Commands
    
    @app_commands.command(name="recurring", description="Manage recurring event schedules")
    @app_commands.describe(
        action="Action to perform",
        schedule_id="Schedule ID (for manage/delete actions)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="create", value="create"),
        app_commands.Choice(name="list", value="list"),
        app_commands.Choice(name="manage", value="manage"),
        app_commands.Choice(name="preview", value="preview")
    ])
    async def recurring_command(
        self,
        interaction: discord.Interaction,
        action: str,
        schedule_id: Optional[str] = None
    ):
        """Main recurring events command."""
        try:
            if action == "create":
                await self._handle_create_command(interaction)
            elif action == "list":
                await self._handle_list_command(interaction)
            elif action == "manage":
                await self._handle_manage_command(interaction, schedule_id)
            elif action == "preview":
                await self._handle_preview_command(interaction, schedule_id)
            else:
                await interaction.response.send_message(
                    "❌ Invalid action. Use create, list, manage, or preview.",
                    ephemeral=True
                )
        
        except Exception as e:
            self.logger.error(f"Error in recurring command: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Something went wrong. Please try again.",
                    ephemeral=True
                )
    
    async def _handle_create_command(self, interaction: discord.Interaction):
        """Handle create recurring schedule command."""
        # Check permissions
        if not await self._check_create_permission(interaction.user, interaction.guild):
            await interaction.response.send_message(
                "❌ You don't have permission to create recurring schedules.",
                ephemeral=True
            )
            return
        
        # Show creation modal
        modal = ScheduleCreationModal(self)
        await interaction.response.send_modal(modal)
    
    async def _handle_list_command(self, interaction: discord.Interaction):
        """Handle list recurring schedules command."""
        try:
            # Get schedules for this guild
            schedules_data = await self.bot.database.recurring_schedules.find({
                'guild_id': str(interaction.guild.id)
            }).sort('created_at', -1).to_list(length=100)
            
            if not schedules_data:
                await interaction.response.send_message(
                    "📋 No recurring schedules found for this server.",
                    ephemeral=True
                )
                return
            
            schedules = [RecurringSchedule(**data) for data in schedules_data]
            
            # Create list embed and view
            embed = self.create_schedules_list_embed(schedules[:5], 0)
            view = ScheduleListView(self, schedules) if len(schedules) > 5 else None
            
            await interaction.response.send_message(
                embed=embed,
                view=view,
                ephemeral=True
            )
        
        except Exception as e:
            self.logger.error(f"Error listing schedules: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ Failed to list schedules. Please try again.",
                ephemeral=True
            )
    
    async def _handle_manage_command(self, interaction: discord.Interaction, schedule_id: Optional[str]):
        """Handle manage recurring schedule command."""
        if not schedule_id:
            await interaction.response.send_message(
                "❌ Please provide a schedule ID to manage.",
                ephemeral=True
            )
            return
        
        try:
            # Get schedule
            schedule_data = await self.bot.database.recurring_schedules.find_one({
                '_id': schedule_id,
                'guild_id': str(interaction.guild.id)
            })
            
            if not schedule_data:
                await interaction.response.send_message(
                    "❌ Schedule not found or you don't have access to it.",
                    ephemeral=True
                )
                return
            
            schedule = RecurringSchedule(**schedule_data)
            
            # Check permissions
            if not await self._check_manage_permission(interaction.user, schedule):
                await interaction.response.send_message(
                    "❌ You don't have permission to manage this schedule.",
                    ephemeral=True
                )
                return
            
            # Create management view
            embed = self.create_schedule_details_embed(schedule)
            view = ScheduleManagementView(self, schedule)
            
            await interaction.response.send_message(
                embed=embed,
                view=view,
                ephemeral=True
            )
        
        except Exception as e:
            self.logger.error(f"Error managing schedule: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ Failed to load schedule. Please try again.",
                ephemeral=True
            )
    
    async def _handle_preview_command(self, interaction: discord.Interaction, schedule_id: Optional[str]):
        """Handle preview recurring schedule command."""
        if not schedule_id:
            await interaction.response.send_message(
                "❌ Please provide a schedule ID to preview.",
                ephemeral=True
            )
            return
        
        try:
            # Get schedule
            schedule_data = await self.bot.database.recurring_schedules.find_one({
                '_id': schedule_id,
                'guild_id': str(interaction.guild.id)
            })
            
            if not schedule_data:
                await interaction.response.send_message(
                    "❌ Schedule not found.",
                    ephemeral=True
                )
                return
            
            schedule = RecurringSchedule(**schedule_data)
            
            # Generate preview
            context = schedule.get_template_context()
            title = schedule.template.render_title(context)
            description = schedule.template.render_description(context)
            
            embed = discord.Embed(
                title="🔍 Schedule Preview",
                description=f"Preview of next event from **{schedule.name}**",
                color=0x3498db
            )
            embed.add_field(
                name="Event Title",
                value=title,
                inline=False
            )
            if description:
                embed.add_field(
                    name="Event Description",
                    value=description[:1000] + ("..." if len(description) > 1000 else ""),
                    inline=False
                )
            if schedule.template.default_games:
                embed.add_field(
                    name="Default Games",
                    value=", ".join(schedule.template.default_games),
                    inline=False
                )
            embed.add_field(
                name="Next Trigger",
                value=f"<t:{int(schedule.next_trigger.timestamp())}:F>" if schedule.next_trigger else "Not scheduled",
                inline=True
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        except Exception as e:
            self.logger.error(f"Error previewing schedule: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ Failed to preview schedule. Please try again.",
                ephemeral=True
            )
    
    # Helper Methods
    
    async def create_recurring_schedule(
        self,
        guild_id: str,
        creator_id: str,
        name: str,
        description: Optional[str],
        trigger_type: TriggerType,
        trigger_time: time,
        day_of_week: Optional[int],
        day_of_month: Optional[int],
        timezone: str,
        event_template: EventTemplate
    ) -> RecurringSchedule:
        """Create a new recurring schedule."""
        # Create trigger
        trigger = ScheduleTrigger(
            trigger_type=trigger_type,
            day_of_week=day_of_week,
            day_of_month=day_of_month,
            trigger_time=trigger_time,
            timezone=timezone
        )
        
        # Create schedule
        schedule = RecurringSchedule(
            guild_id=guild_id,
            creator_id=creator_id,
            name=name,
            description=description,
            trigger=trigger,
            template=event_template,
            status=ScheduleStatus.ACTIVE
        )
        
        # Calculate next trigger
        schedule.update_next_trigger()
        
        # Save to database
        result = await self.bot.database.recurring_schedules.insert_one(schedule.to_dict())
        schedule.id = result.inserted_id
        
        # Emit event
        await self.event_bus.emit(
            EventType.EVENT_CREATED,  # Using existing event type for now
            {
                'schedule_id': str(schedule.id),
                'schedule_name': schedule.name,
                'trigger_type': trigger_type.value
            },
            source='recurring_cog',
            guild_id=guild_id,
            user_id=creator_id
        )
        
        return schedule
    
    async def pause_schedule(self, schedule: RecurringSchedule) -> bool:
        """Pause a recurring schedule."""
        if schedule.pause():
            await self.bot.database.recurring_schedules.update_one(
                {'_id': schedule.id},
                {'$set': schedule.to_dict()}
            )
            return True
        return False
    
    async def resume_schedule(self, schedule: RecurringSchedule) -> bool:
        """Resume a recurring schedule."""
        if schedule.resume():
            await self.bot.database.recurring_schedules.update_one(
                {'_id': schedule.id},
                {'$set': schedule.to_dict()}
            )
            return True
        return False
    
    async def delete_schedule(self, schedule: RecurringSchedule) -> bool:
        """Delete a recurring schedule."""
        try:
            result = await self.bot.database.recurring_schedules.delete_one({
                '_id': schedule.id
            })
            return result.deleted_count > 0
        except Exception as e:
            self.logger.error(f"Error deleting schedule: {e}", exc_info=True)
            return False
    
    def create_schedules_list_embed(self, schedules: List[RecurringSchedule], page: int) -> discord.Embed:
        """Create embed for schedules list."""
        embed = discord.Embed(
            title="🔄 Recurring Schedules",
            description=f"Page {page + 1} - {len(schedules)} schedule(s)",
            color=0x3498db
        )
        
        for schedule in schedules:
            status_emoji = {
                ScheduleStatus.ACTIVE: "🟢",
                ScheduleStatus.PAUSED: "🟡",
                ScheduleStatus.DISABLED: "🔴"
            }.get(schedule.status, "❓")
            
            trigger_desc = self._format_trigger_description(schedule.trigger)
            next_trigger = f"<t:{int(schedule.next_trigger.timestamp())}:R>" if schedule.next_trigger else "Not scheduled"
            
            embed.add_field(
                name=f"{status_emoji} {schedule.name}",
                value=f"**ID:** `{schedule.id}`\n"
                      f"**Trigger:** {trigger_desc}\n"
                      f"**Next:** {next_trigger}\n"
                      f"**Executions:** {schedule.execution_count}",
                inline=True
            )
        
        return embed
    
    def create_schedule_details_embed(self, schedule: RecurringSchedule) -> discord.Embed:
        """Create detailed embed for a schedule."""
        status_emoji = {
            ScheduleStatus.ACTIVE: "🟢 Active",
            ScheduleStatus.PAUSED: "🟡 Paused",
            ScheduleStatus.DISABLED: "🔴 Disabled"
        }.get(schedule.status, "❓ Unknown")
        
        embed = discord.Embed(
            title=f"🔄 {schedule.name}",
            description=schedule.description or "No description",
            color=0x3498db
        )
        
        embed.add_field(
            name="Status",
            value=status_emoji,
            inline=True
        )
        embed.add_field(
            name="Executions",
            value=f"{schedule.execution_count}" + (f"/{schedule.max_executions}" if schedule.max_executions else ""),
            inline=True
        )
        embed.add_field(
            name="Success Rate",
            value=f"{schedule.get_success_rate():.1%}",
            inline=True
        )
        
        trigger_desc = self._format_trigger_description(schedule.trigger)
        embed.add_field(
            name="Trigger",
            value=trigger_desc,
            inline=False
        )
        
        if schedule.next_trigger:
            embed.add_field(
                name="Next Execution",
                value=f"<t:{int(schedule.next_trigger.timestamp())}:F>",
                inline=False
            )
        
        embed.add_field(
            name="Event Template",
            value=f"**Title:** {schedule.template.title_template}\n"
                  f"**Games:** {', '.join(schedule.template.default_games) if schedule.template.default_games else 'None'}",
            inline=False
        )
        
        # Recent executions
        recent = schedule.get_recent_executions(3)
        if recent:
            execution_text = []
            for exec in recent:
                status_emoji = {"SUCCESS": "✅", "FAILED": "❌", "SKIPPED": "⏭️"}.get(exec.status.value, "❓")
                time_str = f"<t:{int(exec.execution_time.timestamp())}:R>"
                execution_text.append(f"{status_emoji} {time_str}")
            
            embed.add_field(
                name="Recent Executions",
                value="\n".join(execution_text),
                inline=False
            )
        
        return embed
    
    def _format_trigger_description(self, trigger: ScheduleTrigger) -> str:
        """Format trigger description for display."""
        if trigger.trigger_type == TriggerType.WEEKLY:
            days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            day_name = days[trigger.day_of_week] if trigger.day_of_week is not None else "Unknown"
            return f"Weekly on {day_name} at {trigger.trigger_time.strftime('%H:%M')} ({trigger.timezone})"
        elif trigger.trigger_type == TriggerType.MONTHLY:
            return f"Monthly on day {trigger.day_of_month} at {trigger.trigger_time.strftime('%H:%M')} ({trigger.timezone})"
        else:
            return f"Custom trigger at {trigger.trigger_time.strftime('%H:%M')} ({trigger.timezone})"
    
    async def _check_create_permission(self, user: discord.Member, guild: discord.Guild) -> bool:
        """Check if user can create recurring schedules."""
        # Check if user has administrator permissions or manage events permission
        return (
            user.guild_permissions.administrator or
            user.guild_permissions.manage_events or
            user.guild_permissions.manage_guild
        )
    
    async def _check_manage_permission(self, user: discord.Member, schedule: RecurringSchedule) -> bool:
        """Check if user can manage a specific schedule."""
        # Creator can always manage their schedule
        if str(user.id) == schedule.creator_id:
            return True
        
        # Administrators can manage any schedule
        return (
            user.guild_permissions.administrator or
            user.guild_permissions.manage_guild
        )


class ScheduleManagementView(discord.ui.View):
    """View for managing individual recurring schedules."""
    
    def __init__(self, cog: RecurringCog, schedule: RecurringSchedule):
        super().__init__(timeout=300)
        self.cog = cog
        self.schedule = schedule
        
        # Add buttons based on schedule status
        if schedule.status == ScheduleStatus.ACTIVE:
            self.add_item(PauseScheduleButton())
        elif schedule.status == ScheduleStatus.PAUSED:
            self.add_item(ResumeScheduleButton())
        
        # Always add test and delete buttons
        self.add_item(TestScheduleButton())
        self.add_item(DeleteScheduleButton())


class PauseScheduleButton(discord.ui.Button):
    """Button to pause a schedule."""
    
    def __init__(self):
        super().__init__(label="Pause", style=discord.ButtonStyle.secondary, emoji="⏸️")
    
    async def callback(self, interaction: discord.Interaction):
        view: ScheduleManagementView = self.view
        
        if await view.cog.pause_schedule(view.schedule):
            await interaction.response.send_message(
                f"⏸️ Schedule **{view.schedule.name}** has been paused.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Failed to pause schedule.",
                ephemeral=True
            )


class ResumeScheduleButton(discord.ui.Button):
    """Button to resume a schedule."""
    
    def __init__(self):
        super().__init__(label="Resume", style=discord.ButtonStyle.success, emoji="▶️")
    
    async def callback(self, interaction: discord.Interaction):
        view: ScheduleManagementView = self.view
        
        if await view.cog.resume_schedule(view.schedule):
            await interaction.response.send_message(
                f"▶️ Schedule **{view.schedule.name}** has been resumed.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Failed to resume schedule.",
                ephemeral=True
            )


class TestScheduleButton(discord.ui.Button):
    """Button to test a schedule by executing it once."""
    
    def __init__(self):
        super().__init__(label="Test Execute", style=discord.ButtonStyle.primary, emoji="🧪")
    
    async def callback(self, interaction: discord.Interaction):
        view: ScheduleManagementView = self.view
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Execute the schedule once for testing
            await view.cog._execute_schedule(view.schedule)
            
            await interaction.followup.send(
                f"🧪 Test execution completed for **{view.schedule.name}**. Check the events list for the created event.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Test execution failed: {str(e)}",
                ephemeral=True
            )


class DeleteScheduleButton(discord.ui.Button):
    """Button to delete a schedule."""
    
    def __init__(self):
        super().__init__(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    
    async def callback(self, interaction: discord.Interaction):
        view: ScheduleManagementView = self.view
        
        # Confirm deletion
        confirm_view = ConfirmDeleteView(view.cog, view.schedule)
        await interaction.response.send_message(
            f"⚠️ Are you sure you want to delete **{view.schedule.name}**? This action cannot be undone.",
            view=confirm_view,
            ephemeral=True
        )


class ConfirmDeleteView(discord.ui.View):
    """Confirmation view for schedule deletion."""
    
    def __init__(self, cog: RecurringCog, schedule: RecurringSchedule):
        super().__init__(timeout=60)
        self.cog = cog
        self.schedule = schedule
    
    @discord.ui.button(label="Yes, Delete", style=discord.ButtonStyle.danger)
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.cog.delete_schedule(self.schedule):
            await interaction.response.edit_message(
                content=f"🗑️ Schedule **{self.schedule.name}** has been deleted.",
                view=None
            )
        else:
            await interaction.response.edit_message(
                content="❌ Failed to delete schedule.",
                view=None
            )
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Deletion cancelled.",
            view=None
        )


async def setup(bot):
    """Set up the recurring events cog."""
    await bot.add_cog(RecurringCog(bot))