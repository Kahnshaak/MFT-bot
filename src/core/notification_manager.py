"""
Simple notification manager for basic notification delivery.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import discord

from core.event_bus import EventBus, EventType
from models.notification import (
    Notification, NotificationType, NotificationStatus, NotificationChannel
)
from models.user import User, NotificationTiming
from utils.logging_config import get_logger


# Default notification templates
DEFAULT_TEMPLATES = {
    NotificationType.EVENT_REMINDER: {
        "title": "🎮 Game Night Reminder",
        "message": "**{event_title}** is coming up!\n\n📅 Date: {event_date}\n⏰ Time: {event_time}\n🎯 Game: {selected_game}\n\nDon't forget to RSVP!"
    },
    NotificationType.EVENT_CANCELLED: {
        "title": "❌ Event Cancelled",
        "message": "**{event_title}** has been cancelled.\n\nWe'll see you at the next game night!"
    }
}


class NotificationManager:
    """
    Simple notification manager for basic notification delivery.
    """
    
    def __init__(self, bot, database_manager, event_bus: EventBus):
        self.bot = bot
        self.database = database_manager
        self.event_bus = event_bus
        self.templates = DEFAULT_TEMPLATES.copy()
        self.scheduled_tasks: Dict[str, asyncio.Task] = {}
        
        # Subscribe to relevant events
        self.event_bus.subscribe(EventType.NOTIFICATION_SCHEDULED, self._on_event_scheduled)
        self.event_bus.subscribe(EventType.EVENT_CANCELLED, self._on_event_cancelled)
        self.event_bus.subscribe(EventType.EVENT_UPDATED, self._on_event_updated)
        self.event_bus.subscribe(EventType.POLL_CREATED, self._on_poll_created)
    
    async def start(self):
        """Start the notification manager."""
        # Start background task to process scheduled notifications
        self.processing_task = asyncio.create_task(self._process_scheduled_notifications())
        get_logger(__name__).info("Notification manager started")
    
    async def stop(self):
        """Stop the notification manager."""
        # Cancel processing task
        if hasattr(self, 'processing_task') and not self.processing_task.done():
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
        
        # Cancel all scheduled tasks
        for task in self.scheduled_tasks.values():
            if not task.done():
                task.cancel()
        
        self.scheduled_tasks.clear()
        get_logger(__name__).info("Notification manager stopped")
    
    async def _process_scheduled_notifications(self):
        """Background task to process scheduled notifications."""
        get_logger(__name__).info("Starting notification processing task")
        
        while True:
            try:
                # Check for due notifications every 30 seconds
                await asyncio.sleep(30)
                
                # Find notifications that are due
                due_notifications = await self.database.notifications.find({
                    "status": NotificationStatus.SCHEDULED.value,
                    "scheduled_for": {"$lte": datetime.utcnow()}
                }).to_list(length=100)
                
                for notification_data in due_notifications:
                    notification_id = str(notification_data["_id"])
                    
                    # Skip if already being processed
                    if notification_id in self.scheduled_tasks:
                        continue
                    
                    # Process notification
                    await self._send_notification(notification_id)
                
            except asyncio.CancelledError:
                get_logger(__name__).info("Notification processing task cancelled")
                break
            except Exception as e:
                get_logger(__name__).error(f"Error in notification processing: {e}", exc_info=True)
                # Continue processing despite errors
                await asyncio.sleep(5)
    
    async def schedule_reminder(
        self,
        event_id: str,
        guild_id: str,
        recipient_user_ids: List[str],
        reminder_time: datetime,
        message: str
    ) -> str:
        """
        Schedule a simple reminder notification.
        
        Args:
            event_id: ID of the event
            guild_id: Discord guild ID
            recipient_user_ids: List of user IDs to notify
            reminder_time: When to send the reminder
            message: Message to send
            
        Returns:
            Notification ID
        """
        notification = Notification(
            guild_id=guild_id,
            notification_type=NotificationType.EVENT_REMINDER,
            scheduled_for=reminder_time,
            recipient_user_ids=recipient_user_ids,
            title="Event Reminder",
            message=message,
            event_id=event_id
        )
        
        # Save to database
        result = await self.database.notifications.insert_one(notification.to_dict())
        notification_id = str(result.inserted_id)
        
        # Schedule delivery
        delay = (reminder_time - datetime.utcnow()).total_seconds()
        if delay > 0:
            task = asyncio.create_task(self._delayed_delivery(notification_id, delay))
            self.scheduled_tasks[notification_id] = task
        else:
            await self._send_notification(notification_id)
        
        get_logger(__name__).info(f"Scheduled reminder for {len(recipient_user_ids)} users")
        return notification_id
    
    async def send_notification(
        self,
        guild_id: str,
        recipient_user_ids: List[str],
        message: str,
        title: str = "Notification"
    ) -> bool:
        """
        Send an immediate notification.
        
        Args:
            guild_id: Discord guild ID
            recipient_user_ids: List of user IDs to notify
            message: Message to send
            title: Notification title
            
        Returns:
            True if notification was sent successfully
        """
        try:
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return False
            
            embed = discord.Embed(
                title=title,
                description=message,
                color=0x00ff00
            )
            
            # Send to each recipient
            for user_id in recipient_user_ids:
                try:
                    user = guild.get_member(int(user_id))
                    if user:
                        await user.send(embed=embed)
                except Exception as e:
                    get_logger(__name__).error(f"Failed to send notification to {user_id}: {e}")
            
            return True
            
        except Exception as e:
            get_logger(__name__).error(f"Error sending notification: {e}")
            return False
    
    async def cancel_notifications(self, event_id: str) -> int:
        """
        Cancel scheduled notifications for an event.
        
        Returns:
            Number of notifications cancelled
        """
        # Cancel scheduled tasks
        cancelled_count = 0
        for task_id, task in list(self.scheduled_tasks.items()):
            if not task.done():
                task.cancel()
                cancelled_count += 1
        
        # Update database
        result = await self.database.notifications.update_many(
            {"event_id": event_id, "status": NotificationStatus.SCHEDULED.value},
            {"$set": {"status": NotificationStatus.CANCELLED.value}}
        )
        
        get_logger(__name__).info(f"Cancelled {cancelled_count} scheduled tasks and {result.modified_count} database notifications")
        return result.modified_count
    
    async def _delayed_delivery(self, notification_id: str, delay: float):
        """Deliver a notification after a delay."""
        try:
            await asyncio.sleep(delay)
            await self._send_notification(notification_id)
        except asyncio.CancelledError:
            pass  # Task was cancelled
        finally:
            self.scheduled_tasks.pop(notification_id, None)
    
    async def _send_notification(self, notification_id: str):
        """Send a specific notification."""
        try:
            # Get notification from database
            notification_data = await self.database.notifications.find_one(
                {"_id": notification_id}
            )
            
            if not notification_data:
                return
            
            notification = Notification(**notification_data)
            
            if notification.status != NotificationStatus.SCHEDULED:
                return
            
            # Send notification
            success = await self.send_notification(
                guild_id=notification.guild_id,
                recipient_user_ids=notification.recipient_user_ids,
                message=notification.message,
                title=notification.title
            )
            
            # Update status
            status = NotificationStatus.SENT if success else NotificationStatus.FAILED
            await self.database.notifications.update_one(
                {"_id": notification_id},
                {"$set": {"status": status.value, "updated_at": datetime.utcnow()}}
            )
            
        except Exception as e:
            get_logger(__name__).error(f"Error sending notification {notification_id}: {e}")
    
    async def schedule_event_reminders(
        self,
        event_id: str,
        guild_id: str,
        event_title: str,
        event_datetime: datetime,
        selected_game: Optional[str] = None
    ) -> List[str]:
        """
        Schedule 24-hour and 1-hour reminders for an event.
        
        Args:
            event_id: Event ID
            guild_id: Discord guild ID
            event_title: Event title
            event_datetime: When the event starts
            selected_game: Selected game name
            
        Returns:
            List of notification IDs created
        """
        notification_ids = []
        
        # Get all users who RSVP'd YES to the event
        event_data = await self.database.events.find_one({"_id": event_id})
        if not event_data:
            get_logger(__name__).warning(f"Event {event_id} not found for reminder scheduling")
            return notification_ids
        
        # Get attendee list from RSVPs
        rsvps = event_data.get("rsvps", {})
        attendee_ids = [user_id for user_id, rsvp in rsvps.items() if rsvp.get("status") == "YES"]
        
        if not attendee_ids:
            get_logger(__name__).info(f"No attendees for event {event_id}, skipping reminders")
            return notification_ids
        
        # Filter users based on their notification preferences
        users_for_24h = []
        users_for_1h = []
        
        for user_id in attendee_ids:
            user_data = await self.database.users.find_one({
                "user_id": user_id,
                "guild_id": guild_id
            })
            
            # Check if user wants event reminders (default True)
            if user_data:
                event_reminders = user_data.get("event_reminders", True)
                if not event_reminders:
                    continue
            
            # Add to both lists by default
            users_for_24h.append(user_id)
            users_for_1h.append(user_id)
        
        # Prepare message content
        event_date_str = event_datetime.strftime("%A, %B %d, %Y")
        event_time_str = event_datetime.strftime("%I:%M %p")
        game_str = selected_game or "TBD"
        
        message = f"**{event_title}** is coming up!\n\n📅 Date: {event_date_str}\n⏰ Time: {event_time_str}\n🎯 Game: {game_str}\n\nSee you there!"
        
        # Schedule 24-hour reminder
        reminder_24h = event_datetime - timedelta(hours=24)
        if reminder_24h > datetime.utcnow() and users_for_24h:
            notification_id = await self.schedule_reminder(
                event_id=event_id,
                guild_id=guild_id,
                recipient_user_ids=users_for_24h,
                reminder_time=reminder_24h,
                message=f"⏰ **24 Hour Reminder**\n\n{message}"
            )
            notification_ids.append(notification_id)
            get_logger(__name__).info(f"Scheduled 24-hour reminder for {len(users_for_24h)} users")
        
        # Schedule 1-hour reminder
        reminder_1h = event_datetime - timedelta(hours=1)
        if reminder_1h > datetime.utcnow() and users_for_1h:
            notification_id = await self.schedule_reminder(
                event_id=event_id,
                guild_id=guild_id,
                recipient_user_ids=users_for_1h,
                reminder_time=reminder_1h,
                message=f"⏰ **1 Hour Reminder**\n\n{message}"
            )
            notification_ids.append(notification_id)
            get_logger(__name__).info(f"Scheduled 1-hour reminder for {len(users_for_1h)} users")
        
        return notification_ids
    
    async def send_immediate_notification(
        self,
        notification_type: NotificationType,
        guild_id: str,
        recipient_user_ids: List[str],
        context_data: Dict[str, Any]
    ) -> bool:
        """
        Send an immediate notification to users.
        
        Args:
            notification_type: Type of notification
            guild_id: Discord guild ID
            recipient_user_ids: List of user IDs to notify
            context_data: Context data for template rendering
            
        Returns:
            True if sent successfully
        """
        template = self.templates.get(notification_type)
        if not template:
            get_logger(__name__).warning(f"No template found for {notification_type}")
            return False
        
        title = template["title"]
        message = template["message"].format(**context_data)
        
        return await self.send_notification(
            guild_id=guild_id,
            recipient_user_ids=recipient_user_ids,
            message=message,
            title=title
        )
    
    # Event handlers
    async def _on_event_scheduled(self, event_data):
        """Handle event scheduling by creating reminders."""
        try:
            data = event_data.data
            event_id = data.get("event_id")
            guild_id = data.get("guild_id", event_data.guild_id)
            title = data.get("title")
            scheduled_date = data.get("scheduled_date")
            scheduled_time = data.get("scheduled_time")
            
            if not all([event_id, guild_id, title, scheduled_date, scheduled_time]):
                get_logger(__name__).warning("Missing required data for event reminder scheduling")
                return
            
            # Parse datetime
            from datetime import date, time
            event_date = date.fromisoformat(scheduled_date)
            event_time = time.fromisoformat(scheduled_time)
            event_datetime = datetime.combine(event_date, event_time)
            
            # Get event details for game info
            event_doc = await self.database.events.find_one({"_id": event_id})
            selected_game = None
            if event_doc:
                # Try to get selected game from game poll
                polls = event_doc.get("polls", [])
                for poll in polls:
                    if poll.get("poll_type") == "GAME":
                        options = poll.get("options", [])
                        if options:
                            # Find option with most votes
                            max_votes = max(opt.get("vote_count", 0) for opt in options)
                            for opt in options:
                                if opt.get("vote_count", 0) == max_votes:
                                    selected_game = opt.get("label")
                                    break
                        break
            
            # Schedule reminders
            await self.schedule_event_reminders(
                event_id=event_id,
                guild_id=guild_id,
                event_title=title,
                event_datetime=event_datetime,
                selected_game=selected_game
            )
            
        except Exception as e:
            get_logger(__name__).error(f"Error scheduling event reminders: {e}", exc_info=True)
    
    async def _on_event_cancelled(self, event_data):
        """Handle event cancellation."""
        data = event_data.data
        event_id = data.get("event_id")
        if event_id:
            await self.cancel_notifications(event_id)
    
    async def _on_event_updated(self, event_data):
        """Handle event updates."""
        pass  # Simplified - no automatic update notifications
    
    async def _on_poll_created(self, event_data):
        """Handle poll creation."""
        pass  # Simplified - no automatic poll reminders