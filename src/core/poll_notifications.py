"""
Poll notification system for reminders and status updates.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum

from core.event_bus import EventBus, EventType
from models.event import Event, Poll, PollType
from utils.logging_config import get_logger, LoggerMixin


class NotificationType(str, Enum):
    """Types of poll notifications."""
    POLL_STARTED = "poll_started"
    POLL_REMINDER = "poll_reminder"
    POLL_CLOSING_SOON = "poll_closing_soon"
    POLL_EXTENDED = "poll_extended"
    POLL_CLOSED = "poll_closed"
    TIE_NEEDS_RESOLUTION = "tie_needs_resolution"
    LOW_PARTICIPATION = "low_participation"


class PollNotificationScheduler(LoggerMixin):
    """
    Manages scheduling and delivery of poll-related notifications.
    """
    
    def __init__(self, event_bus: EventBus, database_manager, bot):
        self.event_bus = event_bus
        self.database = database_manager
        self.bot = bot
        self.scheduled_notifications: Dict[str, asyncio.Task] = {}
        
        # Default notification timings (in minutes before poll closes)
        self.default_reminders = {
            PollType.DATE: [60, 15, 5],  # 1 hour, 15 min, 5 min
            PollType.TIME: [30, 10, 2],  # 30 min, 10 min, 2 min
            PollType.GAME: [30, 10, 2]   # 30 min, 10 min, 2 min
        }
        
        # Subscribe to events
        self.event_bus.subscribe(EventType.POLL_CREATED, self._on_poll_created)
        self.event_bus.subscribe(EventType.POLL_COMPLETED, self._on_poll_completed)
        self.event_bus.subscribe(EventType.POLL_EXPIRED, self._on_poll_expired)
        self.event_bus.subscribe(EventType.POLL_UPDATED, self._on_poll_updated)
    
    async def _on_poll_created(self, event_data):
        """Handle poll creation by scheduling notifications."""
        data = event_data.data
        await self.schedule_poll_notifications(
            event_id=data['event_id'],
            poll_type=PollType(data['poll_type']),
            timeout_seconds=data['timeout_seconds']
        )
    
    async def _on_poll_completed(self, event_data):
        """Handle poll completion by canceling remaining notifications."""
        data = event_data.data
        await self.cancel_poll_notifications(data['event_id'], PollType(data['poll_type']))
        
        # Send completion notification
        await self.send_poll_notification(
            event_id=data['event_id'],
            poll_type=PollType(data['poll_type']),
            notification_type=NotificationType.POLL_CLOSED,
            data={'winner_option_id': data.get('winner_option_id')}
        )
    
    async def _on_poll_expired(self, event_data):
        """Handle poll expiration."""
        data = event_data.data
        
        if data.get('had_tie'):
            await self.send_poll_notification(
                event_id=data['event_id'],
                poll_type=PollType(data['poll_type']),
                notification_type=NotificationType.TIE_NEEDS_RESOLUTION,
                data={'analytics': data.get('analytics', {})}
            )
    
    async def _on_poll_updated(self, event_data):
        """Handle poll updates like extensions."""
        data = event_data.data
        
        if data.get('action') == 'extended':
            await self.send_poll_notification(
                event_id=data['event_id'],
                poll_type=PollType(data['poll_type']),
                notification_type=NotificationType.POLL_EXTENDED,
                data={'extension_minutes': data.get('extension_minutes')}
            )
    
    async def schedule_poll_notifications(
        self, 
        event_id: str, 
        poll_type: PollType, 
        timeout_seconds: int
    ):
        """Schedule all notifications for a poll."""
        try:
            # Get event data
            event_data = await self.database.events.find_one({'_id': event_id})
            if not event_data:
                return
            
            event = Event(**event_data)
            poll = event.get_poll(poll_type)
            if not poll:
                return
            
            # Send poll started notification
            await self.send_poll_notification(
                event_id=event_id,
                poll_type=poll_type,
                notification_type=NotificationType.POLL_STARTED,
                data={'poll_title': poll.title, 'option_count': len(poll.options)}
            )
            
            # Schedule reminder notifications
            reminder_times = self.default_reminders.get(poll_type, [30, 10, 2])
            
            for reminder_minutes in reminder_times:
                reminder_seconds = reminder_minutes * 60
                
                # Only schedule if reminder is before poll closes
                if reminder_seconds < timeout_seconds:
                    delay = timeout_seconds - reminder_seconds
                    
                    task_id = f"{event_id}_{poll_type.value}_reminder_{reminder_minutes}"
                    task = asyncio.create_task(
                        self._delayed_notification(
                            delay=delay,
                            event_id=event_id,
                            poll_type=poll_type,
                            notification_type=NotificationType.POLL_REMINDER,
                            data={'minutes_remaining': reminder_minutes}
                        )
                    )
                    self.scheduled_notifications[task_id] = task
            
            # Schedule low participation check (halfway through poll)
            if timeout_seconds > 600:  # Only for polls longer than 10 minutes
                participation_check_delay = timeout_seconds // 2
                task_id = f"{event_id}_{poll_type.value}_participation_check"
                task = asyncio.create_task(
                    self._delayed_participation_check(
                        delay=participation_check_delay,
                        event_id=event_id,
                        poll_type=poll_type
                    )
                )
                self.scheduled_notifications[task_id] = task
            
            self.logger.info(f"Scheduled notifications for {poll_type.value} poll in event {event_id}")
            
        except Exception as e:
            self.logger.error(f"Error scheduling poll notifications: {e}", exc_info=True)
    
    async def _delayed_notification(
        self,
        delay: float,
        event_id: str,
        poll_type: PollType,
        notification_type: NotificationType,
        data: Dict[str, Any]
    ):
        """Send a notification after a delay."""
        try:
            await asyncio.sleep(delay)
            await self.send_poll_notification(event_id, poll_type, notification_type, data)
        except asyncio.CancelledError:
            pass  # Task was cancelled
        except Exception as e:
            self.logger.error(f"Error in delayed notification: {e}", exc_info=True)
    
    async def _delayed_participation_check(
        self,
        delay: float,
        event_id: str,
        poll_type: PollType
    ):
        """Check poll participation after a delay."""
        try:
            await asyncio.sleep(delay)
            
            # Get current event data
            event_data = await self.database.events.find_one({'_id': event_id})
            if not event_data:
                return
            
            event = Event(**event_data)
            poll = event.get_poll(poll_type)
            if not poll or not poll.is_active:
                return
            
            # Calculate participation
            total_votes = sum(option.vote_count for option in poll.options)
            
            # Get guild member count (simplified - in reality would get eligible voters)
            guild = self.bot.get_guild(int(event.guild_id))
            if guild:
                member_count = guild.member_count
                participation_rate = total_votes / member_count if member_count > 0 else 0
                
                # Send low participation notification if < 20%
                if participation_rate < 0.2:
                    await self.send_poll_notification(
                        event_id=event_id,
                        poll_type=poll_type,
                        notification_type=NotificationType.LOW_PARTICIPATION,
                        data={
                            'total_votes': total_votes,
                            'participation_rate': participation_rate
                        }
                    )
            
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Error in participation check: {e}", exc_info=True)
    
    async def cancel_poll_notifications(self, event_id: str, poll_type: PollType):
        """Cancel all scheduled notifications for a poll."""
        prefix = f"{event_id}_{poll_type.value}"
        
        cancelled_count = 0
        for task_id in list(self.scheduled_notifications.keys()):
            if task_id.startswith(prefix):
                task = self.scheduled_notifications.pop(task_id)
                if not task.done():
                    task.cancel()
                    cancelled_count += 1
        
        if cancelled_count > 0:
            self.logger.info(f"Cancelled {cancelled_count} notifications for {poll_type.value} poll")
    
    async def send_poll_notification(
        self,
        event_id: str,
        poll_type: PollType,
        notification_type: NotificationType,
        data: Optional[Dict[str, Any]] = None
    ):
        """Send a poll notification to appropriate channels."""
        try:
            # Get event data
            event_data = await self.database.events.find_one({'_id': event_id})
            if not event_data:
                return
            
            event = Event(**event_data)
            guild = self.bot.get_guild(int(event.guild_id))
            if not guild:
                return
            
            # Create notification message
            message_content = self._create_notification_message(
                event, poll_type, notification_type, data or {}
            )
            
            if not message_content:
                return
            
            # Get notification channel (for now, use the channel where event was created)
            # In a full implementation, this would check guild settings for notification channels
            channels_to_notify = []
            
            # Try to find a general or events channel
            for channel in guild.text_channels:
                if channel.name.lower() in ['general', 'events', 'game-night', 'announcements']:
                    channels_to_notify.append(channel)
                    break
            
            # If no specific channel found, use the first available text channel
            if not channels_to_notify and guild.text_channels:
                channels_to_notify.append(guild.text_channels[0])
            
            # Send notifications
            for channel in channels_to_notify:
                try:
                    await channel.send(message_content)
                    
                    # Emit notification sent event
                    await self.event_bus.emit(
                        EventType.NOTIFICATION_SENT,
                        {
                            'event_id': event_id,
                            'poll_type': poll_type.value,
                            'notification_type': notification_type.value,
                            'channel_id': str(channel.id)
                        },
                        source='poll_notifications',
                        guild_id=event.guild_id
                    )
                    
                except Exception as e:
                    self.logger.error(f"Failed to send notification to channel {channel.id}: {e}")
                    
                    # Emit notification failed event
                    await self.event_bus.emit(
                        EventType.NOTIFICATION_FAILED,
                        {
                            'event_id': event_id,
                            'poll_type': poll_type.value,
                            'notification_type': notification_type.value,
                            'channel_id': str(channel.id),
                            'error': str(e)
                        },
                        source='poll_notifications',
                        guild_id=event.guild_id
                    )
            
        except Exception as e:
            self.logger.error(f"Error sending poll notification: {e}", exc_info=True)
    
    def _create_notification_message(
        self,
        event: Event,
        poll_type: PollType,
        notification_type: NotificationType,
        data: Dict[str, Any]
    ) -> Optional[str]:
        """Create notification message content."""
        poll = event.get_poll(poll_type)
        if not poll:
            return None
        
        poll_type_emoji = {
            PollType.DATE: "📅",
            PollType.TIME: "⏰",
            PollType.GAME: "🎮"
        }
        
        emoji = poll_type_emoji.get(poll_type, "📊")
        
        if notification_type == NotificationType.POLL_STARTED:
            return (
                f"{emoji} **{poll_type.value.title()} Poll Started!**\n"
                f"Event: **{event.title}**\n"
                f"Poll: {poll.title}\n"
                f"Options: {data.get('option_count', len(poll.options))}\n"
                f"Vote now to help decide!"
            )
        
        elif notification_type == NotificationType.POLL_REMINDER:
            minutes = data.get('minutes_remaining', 0)
            return (
                f"{emoji} **Poll Reminder**\n"
                f"Event: **{event.title}**\n"
                f"Poll: {poll.title}\n"
                f"⏰ **{minutes} minutes remaining** to vote!\n"
                f"Don't miss your chance to participate!"
            )
        
        elif notification_type == NotificationType.POLL_CLOSING_SOON:
            return (
                f"{emoji} **Poll Closing Soon!**\n"
                f"Event: **{event.title}**\n"
                f"Poll: {poll.title}\n"
                f"⚠️ Last chance to vote!"
            )
        
        elif notification_type == NotificationType.POLL_EXTENDED:
            minutes = data.get('extension_minutes', 0)
            return (
                f"{emoji} **Poll Extended**\n"
                f"Event: **{event.title}**\n"
                f"Poll: {poll.title}\n"
                f"⏰ Extended by **{minutes} minutes**\n"
                f"More time to vote!"
            )
        
        elif notification_type == NotificationType.POLL_CLOSED:
            winner_id = data.get('winner_option_id')
            if winner_id:
                winner = poll.get_option_by_id(winner_id)
                winner_text = f"Winner: **{winner.label}**" if winner else "Results available"
            else:
                winner_text = "No clear winner"
            
            return (
                f"{emoji} **Poll Closed**\n"
                f"Event: **{event.title}**\n"
                f"Poll: {poll.title}\n"
                f"✅ {winner_text}"
            )
        
        elif notification_type == NotificationType.TIE_NEEDS_RESOLUTION:
            return (
                f"{emoji} **Poll Tie - Admin Action Needed**\n"
                f"Event: **{event.title}**\n"
                f"Poll: {poll.title}\n"
                f"⚖️ Multiple options tied for first place\n"
                f"Event organizers need to resolve the tie"
            )
        
        elif notification_type == NotificationType.LOW_PARTICIPATION:
            total_votes = data.get('total_votes', 0)
            participation_rate = data.get('participation_rate', 0) * 100
            
            return (
                f"{emoji} **Low Poll Participation**\n"
                f"Event: **{event.title}**\n"
                f"Poll: {poll.title}\n"
                f"📊 Only {total_votes} votes so far ({participation_rate:.1f}% participation)\n"
                f"Encourage more people to vote!"
            )
        
        return None
    
    async def send_custom_poll_notification(
        self,
        event_id: str,
        poll_type: PollType,
        message: str,
        mention_roles: Optional[List[str]] = None
    ):
        """Send a custom notification message for a poll."""
        try:
            event_data = await self.database.events.find_one({'_id': event_id})
            if not event_data:
                return False
            
            event = Event(**event_data)
            guild = self.bot.get_guild(int(event.guild_id))
            if not guild:
                return False
            
            # Add role mentions if specified
            if mention_roles:
                mentions = []
                for role_id in mention_roles:
                    role = guild.get_role(int(role_id))
                    if role:
                        mentions.append(role.mention)
                
                if mentions:
                    message = f"{' '.join(mentions)}\n{message}"
            
            # Send to appropriate channels
            for channel in guild.text_channels:
                if channel.name.lower() in ['general', 'events', 'game-night']:
                    await channel.send(message)
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error sending custom poll notification: {e}", exc_info=True)
            return False
    
    def get_scheduled_notifications(self, event_id: Optional[str] = None) -> Dict[str, Any]:
        """Get information about scheduled notifications."""
        notifications = {}
        
        for task_id, task in self.scheduled_notifications.items():
            if event_id is None or task_id.startswith(event_id):
                notifications[task_id] = {
                    'done': task.done(),
                    'cancelled': task.cancelled()
                }
        
        return notifications
    
    async def cleanup_completed_tasks(self):
        """Clean up completed notification tasks."""
        completed_tasks = []
        
        for task_id, task in self.scheduled_notifications.items():
            if task.done():
                completed_tasks.append(task_id)
        
        for task_id in completed_tasks:
            del self.scheduled_notifications[task_id]
        
        if completed_tasks:
            self.logger.debug(f"Cleaned up {len(completed_tasks)} completed notification tasks")