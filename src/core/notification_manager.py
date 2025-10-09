"""
Simple notification manager for basic notification delivery.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import discord

from core.event_bus import EventBus, EventType
from models.notification import (
    Notification, NotificationType, NotificationStatus
)
from models.user import User
from utils.logging_config import get_logger


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
        get_logger(__name__).info("Notification manager started")
    
    async def stop(self):
        """Stop the notification manager."""
        # Cancel all scheduled tasks
        for task in self.scheduled_tasks.values():
            if not task.done():
                task.cancel()
        
        self.scheduled_tasks.clear()
        get_logger(__name__).info("Notification manager stopped")
    
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
    
    # Event handlers
    async def _on_event_scheduled(self, event_data):
        """Handle event scheduling by creating reminders."""
        pass  # Simplified - no automatic reminders
    
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