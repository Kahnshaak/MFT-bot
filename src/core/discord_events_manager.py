"""
Discord Scheduled Events Manager for integrating bot events with Discord's native scheduled events.

This module handles:
- Creating Discord scheduled events from bot events
- Bidirectional RSVP synchronization
- Event update propagation
- Error handling and recovery
- Calendar export functionality
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any, Tuple
from enum import Enum
import logging

import discord
from discord.ext import tasks

from models.event import Event, EventState, RSVPStatus, PollType
from core.event_bus import EventBus, EventType
from utils.exceptions import GameNightBotException, ErrorCode
from utils.logging_config import LoggerMixin
from utils.discord_api_utils import with_discord_retry, safe_discord_request, get_guild_safely, get_scheduled_event_safely


class DiscordEventError(GameNightBotException):
    """Errors related to Discord scheduled events."""
    
    def __init__(self, message: str, error_code: ErrorCode = ErrorCode.DISCORD_API_ERROR, 
                 original_error: Optional[Exception] = None):
        super().__init__(message, error_code)
        self.original_error = original_error


class DiscordEventSyncStatus(str, Enum):
    """Status of Discord event synchronization."""
    PENDING = "PENDING"
    SYNCED = "SYNCED"
    FAILED = "FAILED"
    NEEDS_UPDATE = "NEEDS_UPDATE"


class DiscordEventsManager(LoggerMixin):
    """
    Manager for Discord scheduled events integration.
    
    Handles creation, updates, and synchronization of Discord scheduled events
    with bot events, including RSVP synchronization and error recovery.
    """
    
    def __init__(self, bot, event_bus: EventBus, database_manager):
        self.bot = bot
        self.event_bus = event_bus
        self.database = database_manager
        
        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        self.rate_limit_delay = 60  # seconds
        
        # Track sync status
        self.sync_status: Dict[str, DiscordEventSyncStatus] = {}
        
        # Subscribe to relevant events
        self.event_bus.subscribe(EventType.EVENT_SCHEDULED, self._on_event_scheduled)
        self.event_bus.subscribe(EventType.EVENT_UPDATED, self._on_event_updated)
        self.event_bus.subscribe(EventType.EVENT_CANCELLED, self._on_event_cancelled)
        
        # Start background tasks
        self.sync_rsvps_task.start()
        self.cleanup_failed_events_task.start()
    
    @with_discord_retry(max_retries=3, base_delay=5.0)
    async def create_discord_event(self, event: Event) -> Optional[str]:
        """
        Create a Discord scheduled event from a bot event.
        
        Args:
            event: The bot event to create a Discord event for
            
        Returns:
            Discord event ID if successful, None if failed
            
        Raises:
            DiscordEventError: If creation fails after retries
        """
        if not event.is_scheduled():
            raise DiscordEventError(
                "Cannot create Discord event for unscheduled bot event",
                ErrorCode.VALIDATION_ERROR
            )
        
        guild = await get_guild_safely(self.bot, event.guild_id)
        if not guild:
            raise DiscordEventError(
                f"Guild {event.guild_id} not found",
                ErrorCode.GUILD_NOT_FOUND
            )
        
        # Calculate event start time
        start_time = self._calculate_event_datetime(event)
        end_time = start_time + timedelta(minutes=event.schedule.duration_minutes or 180)
        
        # Prepare event data
        event_data = {
            'name': event.title,
            'description': self._format_event_description(event),
            'start_time': start_time,
            'end_time': end_time,
            'privacy_level': discord.ScheduledEventPrivacyLevel.guild_only,
            'entity_type': discord.ScheduledEventLocationType.external,
            'location': 'Discord Voice/Text Channels'
        }
        
        # Create the Discord event (retry logic handled by decorator)
        discord_event = await guild.create_scheduled_event(**event_data)
        
        # Update bot event with Discord event ID
        await self._update_event_discord_id(event, str(discord_event.id))
        
        # Mark as synced
        self.sync_status[str(event.id)] = DiscordEventSyncStatus.SYNCED
        
        # Emit success event
        await self.event_bus.emit(
            EventType.DISCORD_EVENT_CREATED,
            {
                'event_id': str(event.id),
                'discord_event_id': str(discord_event.id),
                'guild_id': event.guild_id
            },
            source='discord_events_manager',
            guild_id=event.guild_id
        )
        
        self.logger.info(
            f"Created Discord event {discord_event.id} for bot event {event.id}"
        )
        
        return str(discord_event.id)
    
    @with_discord_retry(max_retries=2, base_delay=2.0)
    async def update_discord_event(self, event: Event) -> bool:
        """
        Update an existing Discord scheduled event.
        
        Args:
            event: The bot event with updated information
            
        Returns:
            True if update was successful, False otherwise
        """
        if not event.discord_event_id:
            self.logger.warning(f"No Discord event ID for bot event {event.id}")
            return False
        
        guild = await get_guild_safely(self.bot, event.guild_id)
        if not guild:
            self.logger.error(f"Guild {event.guild_id} not found")
            return False
        
        discord_event = await get_scheduled_event_safely(guild, event.discord_event_id)
        if not discord_event:
            self.logger.warning(f"Discord event {event.discord_event_id} not found, clearing reference")
            await self._update_event_discord_id(event, None)
            return False
        
        try:
            
            # Prepare update data
            update_data = {}
            
            if discord_event.name != event.title:
                update_data['name'] = event.title
            
            new_description = self._format_event_description(event)
            if discord_event.description != new_description:
                update_data['description'] = new_description
            
            if event.is_scheduled():
                new_start_time = self._calculate_event_datetime(event)
                if discord_event.start_time != new_start_time:
                    update_data['start_time'] = new_start_time
                    update_data['end_time'] = new_start_time + timedelta(
                        minutes=event.schedule.duration_minutes or 180
                    )
            
            # Apply updates if any
            if update_data:
                await discord_event.edit(**update_data)
                
                self.logger.info(f"Updated Discord event {discord_event.id} for bot event {event.id}")
                
                # Emit update event
                await self.event_bus.emit(
                    EventType.DISCORD_EVENT_UPDATED,
                    {
                        'event_id': str(event.id),
                        'discord_event_id': str(discord_event.id),
                        'updates': list(update_data.keys())
                    },
                    source='discord_events_manager',
                    guild_id=event.guild_id
                )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating Discord event: {e}", exc_info=True)
            return False
    
    @with_discord_retry(max_retries=2, base_delay=2.0)
    async def cancel_discord_event(self, event: Event) -> bool:
        """
        Cancel a Discord scheduled event.
        
        Args:
            event: The bot event that was cancelled
            
        Returns:
            True if cancellation was successful, False otherwise
        """
        if not event.discord_event_id:
            return True  # Nothing to cancel
        
        guild = await get_guild_safely(self.bot, event.guild_id)
        if not guild:
            self.logger.error(f"Guild {event.guild_id} not found")
            return False
        
        discord_event = await get_scheduled_event_safely(guild, event.discord_event_id)
        if not discord_event:
            self.logger.warning(f"Discord event {event.discord_event_id} not found")
            return True  # Already gone
        
        try:
            await discord_event.cancel()
            
            self.logger.info(f"Cancelled Discord event {discord_event.id} for bot event {event.id}")
            
            # Emit cancellation event
            await self.event_bus.emit(
                EventType.DISCORD_EVENT_CANCELLED,
                {
                    'event_id': str(event.id),
                    'discord_event_id': str(discord_event.id)
                },
                source='discord_events_manager',
                guild_id=event.guild_id
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error cancelling Discord event: {e}", exc_info=True)
            return False
    
    async def sync_rsvps_from_discord(self, event: Event) -> int:
        """
        Synchronize RSVPs from Discord scheduled event to bot event.
        
        Args:
            event: The bot event to sync RSVPs for
            
        Returns:
            Number of RSVPs synchronized
        """
        if not event.discord_event_id:
            return 0
        
        guild = await get_guild_safely(self.bot, event.guild_id)
        if not guild:
            return 0
        
        discord_event = await get_scheduled_event_safely(guild, event.discord_event_id)
        if not discord_event:
            self.logger.warning(f"Discord event {event.discord_event_id} not found for RSVP sync")
            return 0
        
        try:
            
            # Get Discord event subscribers
            subscribers = []
            async for user in discord_event.subscribers():
                subscribers.append(user)
            
            synced_count = 0
            
            # Sync each subscriber
            for user in subscribers:
                user_id = str(user.id)
                
                # Check if user already has RSVP in bot event
                existing_rsvp = event.rsvp_data.get(user_id)
                
                if not existing_rsvp or existing_rsvp.status != RSVPStatus.YES:
                    # Add/update RSVP as YES
                    event.add_rsvp(user_id, RSVPStatus.YES, "Synced from Discord event")
                    synced_count += 1
            
            # Update event in database if changes were made
            if synced_count > 0:
                await self._save_event(event)
                
                self.logger.info(f"Synced {synced_count} RSVPs from Discord event {discord_event.id}")
                
                # Emit sync event
                await self.event_bus.emit(
                    EventType.RSVP_SYNCED,
                    {
                        'event_id': str(event.id),
                        'discord_event_id': str(discord_event.id),
                        'synced_count': synced_count
                    },
                    source='discord_events_manager',
                    guild_id=event.guild_id
                )
            
            return synced_count
            
        except Exception as e:
            self.logger.error(f"Error syncing RSVPs: {e}", exc_info=True)
            return 0
    
    def generate_calendar_export(self, events: List[Event]) -> str:
        """
        Generate an iCalendar (.ics) file for the given events.
        
        Args:
            events: List of events to include in the calendar
            
        Returns:
            iCalendar content as string
        """
        from datetime import datetime
        import uuid
        
        # iCalendar header
        ics_content = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Game Night Bot//Game Night Events//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH"
        ]
        
        for event in events:
            if not event.is_scheduled():
                continue
            
            # Calculate event times
            start_dt = self._calculate_event_datetime(event)
            end_dt = start_dt + timedelta(minutes=event.schedule.duration_minutes or 180)
            
            # Format times for iCalendar (UTC)
            start_utc = start_dt.astimezone(timezone.utc)
            end_utc = end_dt.astimezone(timezone.utc)
            
            dtstart = start_utc.strftime("%Y%m%dT%H%M%SZ")
            dtend = end_utc.strftime("%Y%m%dT%H%M%SZ")
            dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            
            # Generate unique ID
            uid = f"{event.id}@gamenight-bot"
            
            # Event entry
            ics_content.extend([
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART:{dtstart}",
                f"DTEND:{dtend}",
                f"SUMMARY:{self._escape_ics_text(event.title)}",
                f"DESCRIPTION:{self._escape_ics_text(self._format_event_description(event))}",
                f"STATUS:CONFIRMED",
                f"TRANSP:OPAQUE",
                "END:VEVENT"
            ])
        
        ics_content.append("END:VCALENDAR")
        
        return "\r\n".join(ics_content)
    
    def _calculate_event_datetime(self, event: Event) -> datetime:
        """Calculate the full datetime for an event."""
        if not event.schedule.selected_date or not event.schedule.selected_time:
            raise ValueError("Event must have both date and time selected")
        
        # Combine date and time
        naive_dt = datetime.combine(event.schedule.selected_date, event.schedule.selected_time)
        
        # Apply timezone
        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo(event.schedule.timezone)
            return naive_dt.replace(tzinfo=tz)
        except ImportError:
            # Fallback for Python < 3.9
            import pytz
            tz = pytz.timezone(event.schedule.timezone)
            return tz.localize(naive_dt)
    
    def _format_event_description(self, event: Event) -> str:
        """Format event description for Discord scheduled event."""
        description_parts = []
        
        if event.description:
            description_parts.append(event.description)
        
        # Add game information if available
        game_poll = event.get_poll(PollType.GAME)
        if game_poll and game_poll.winner_option_id:
            winner_option = game_poll.get_option_by_id(game_poll.winner_option_id)
            if winner_option:
                description_parts.append(f"\n🎮 Game: {winner_option.label}")
        
        # Add RSVP count
        yes_count = event.get_rsvp_count(RSVPStatus.YES)
        maybe_count = event.get_rsvp_count(RSVPStatus.MAYBE)
        
        if yes_count > 0 or maybe_count > 0:
            rsvp_text = f"\n👥 RSVPs: {yes_count} Yes"
            if maybe_count > 0:
                rsvp_text += f", {maybe_count} Maybe"
            description_parts.append(rsvp_text)
        
        # Add bot attribution
        description_parts.append("\n\n🤖 Managed by Game Night Bot")
        
        return "".join(description_parts)
    
    def _escape_ics_text(self, text: str) -> str:
        """Escape text for iCalendar format."""
        if not text:
            return ""
        
        # Escape special characters
        text = text.replace("\\", "\\\\")
        text = text.replace(",", "\\,")
        text = text.replace(";", "\\;")
        text = text.replace("\n", "\\n")
        text = text.replace("\r", "")
        
        return text
    
    async def _update_event_discord_id(self, event: Event, discord_event_id: Optional[str]):
        """Update the Discord event ID for a bot event."""
        await self.database.events.update_one(
            {'_id': event.id},
            {'$set': {'discord_event_id': discord_event_id}}
        )
        event.discord_event_id = discord_event_id
    
    async def _save_event(self, event: Event):
        """Save event to database."""
        await self.database.events.replace_one(
            {'_id': event.id},
            event.model_dump(by_alias=True)
        )
    
    async def _on_event_scheduled(self, event_data):
        """Handle event scheduled events."""
        try:
            event_id = event_data.data.get('event_id')
            if not event_id:
                return
            
            # Get the event
            event_doc = await self.database.events.find_one({'_id': event_id})
            if not event_doc:
                return
            
            event = Event(**event_doc)
            
            # Create Discord event
            discord_event_id = await self.create_discord_event(event)
            
            if discord_event_id:
                self.logger.info(f"Successfully created Discord event for {event_id}")
            else:
                self.logger.error(f"Failed to create Discord event for {event_id}")
                
                # Notify admins of failure
                await self._notify_admin_of_failure(event, "Failed to create Discord scheduled event")
        
        except Exception as e:
            self.logger.error(f"Error handling event scheduled: {e}", exc_info=True)
    
    async def _on_event_updated(self, event_data):
        """Handle event updated events."""
        try:
            event_id = event_data.data.get('event_id')
            if not event_id:
                return
            
            # Get the event
            event_doc = await self.database.events.find_one({'_id': event_id})
            if not event_doc:
                return
            
            event = Event(**event_doc)
            
            # Update Discord event if it exists
            if event.discord_event_id:
                success = await self.update_discord_event(event)
                if not success:
                    self.logger.warning(f"Failed to update Discord event for {event_id}")
        
        except Exception as e:
            self.logger.error(f"Error handling event updated: {e}", exc_info=True)
    
    async def _on_event_cancelled(self, event_data):
        """Handle event cancelled events."""
        try:
            event_id = event_data.data.get('event_id')
            if not event_id:
                return
            
            # Get the event
            event_doc = await self.database.events.find_one({'_id': event_id})
            if not event_doc:
                return
            
            event = Event(**event_doc)
            
            # Cancel Discord event if it exists
            if event.discord_event_id:
                success = await self.cancel_discord_event(event)
                if not success:
                    self.logger.warning(f"Failed to cancel Discord event for {event_id}")
        
        except Exception as e:
            self.logger.error(f"Error handling event cancelled: {e}", exc_info=True)
    
    async def _notify_admin_of_failure(self, event: Event, error_message: str):
        """Notify server admins of Discord event failures."""
        try:
            guild = self.bot.get_guild(int(event.guild_id))
            if not guild:
                return
            
            # Find admin channel
            admin_channel = None
            for channel in guild.text_channels:
                if any(keyword in channel.name.lower() for keyword in ['admin', 'mod', 'staff']):
                    admin_channel = channel
                    break
            
            if not admin_channel:
                # Use system channel or first available channel
                admin_channel = guild.system_channel or guild.text_channels[0] if guild.text_channels else None
            
            if admin_channel:
                embed = discord.Embed(
                    title="⚠️ Discord Event Integration Error",
                    description=f"Failed to sync event **{event.title}** with Discord scheduled events.",
                    color=discord.Color.orange()
                )
                embed.add_field(name="Error", value=error_message, inline=False)
                embed.add_field(name="Event ID", value=str(event.id), inline=True)
                embed.add_field(name="Event State", value=event.state.value, inline=True)
                
                await admin_channel.send(embed=embed)
        
        except Exception as e:
            self.logger.error(f"Failed to notify admin of Discord event failure: {e}", exc_info=True)
    
    @tasks.loop(minutes=30)
    async def sync_rsvps_task(self):
        """Background task to sync RSVPs from Discord events."""
        try:
            # Find events with Discord event IDs that are scheduled or completed recently
            cutoff_date = datetime.utcnow() - timedelta(days=1)
            
            events_cursor = self.database.events.find({
                'discord_event_id': {'$ne': None},
                'state': {'$in': ['SCHEDULED', 'COMPLETED']},
                'updated_at': {'$gte': cutoff_date}
            })
            
            async for event_doc in events_cursor:
                event = Event(**event_doc)
                synced_count = await self.sync_rsvps_from_discord(event)
                
                if synced_count > 0:
                    self.logger.info(f"Synced {synced_count} RSVPs for event {event.id}")
        
        except Exception as e:
            self.logger.error(f"Error in RSVP sync task: {e}", exc_info=True)
    
    @tasks.loop(hours=6)
    async def cleanup_failed_events_task(self):
        """Background task to retry failed Discord event creations."""
        try:
            # Find events that failed Discord event creation
            failed_events = []
            for event_id, status in self.sync_status.items():
                if status == DiscordEventSyncStatus.FAILED:
                    event_doc = await self.database.events.find_one({'_id': event_id})
                    if event_doc:
                        event = Event(**event_doc)
                        if event.is_scheduled() and not event.discord_event_id:
                            failed_events.append(event)
            
            # Retry failed events
            for event in failed_events:
                try:
                    discord_event_id = await self.create_discord_event(event)
                    if discord_event_id:
                        self.logger.info(f"Successfully retried Discord event creation for {event.id}")
                        # Remove from failed status
                        self.sync_status.pop(str(event.id), None)
                except Exception as e:
                    self.logger.warning(f"Retry failed for event {event.id}: {e}")
        
        except Exception as e:
            self.logger.error(f"Error in cleanup failed events task: {e}", exc_info=True)
    
    @sync_rsvps_task.before_loop
    async def before_sync_rsvps_task(self):
        """Wait for bot to be ready before starting RSVP sync task."""
        await self.bot.wait_until_ready()
    
    @cleanup_failed_events_task.before_loop
    async def before_cleanup_failed_events_task(self):
        """Wait for bot to be ready before starting cleanup task."""
        await self.bot.wait_until_ready()