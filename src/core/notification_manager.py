"""
Notification manager for scheduling and delivering reminders and alerts.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from collections import defaultdict
import discord

from core.event_bus import EventBus, EventType
from core.batch_processor import NotificationBatchProcessor
from models.notification import (
    Notification, NotificationChannel, NotificationType, NotificationStatus,
    NotificationTemplate, DEFAULT_TEMPLATES
)
from models.user import User, NotificationPreferences, NotificationTiming
from utils.logging_config import get_logger, LoggerMixin
from utils.exceptions import GameNightBotException


class NotificationManager(LoggerMixin):
    """
    Manages notification scheduling, delivery, and retry logic.
    
    Handles both immediate and scheduled notifications with support for
    multiple delivery channels and retry mechanisms.
    """
    
    def __init__(self, bot, database_manager, event_bus: EventBus):
        self.bot = bot
        self.database = database_manager
        self.event_bus = event_bus
        self.templates = DEFAULT_TEMPLATES.copy()
        self.scheduled_tasks: Dict[str, asyncio.Task] = {}
        self.processing_queue = asyncio.Queue()
        self.is_running = False
        
        # Batch processing for notifications
        self.batch_processor = NotificationBatchProcessor(self._send_notification_batch)
        
        # Subscribe to relevant events
        self.event_bus.subscribe(EventType.EVENT_SCHEDULED, self._on_event_scheduled)
        self.event_bus.subscribe(EventType.EVENT_CANCELLED, self._on_event_cancelled)
        self.event_bus.subscribe(EventType.EVENT_UPDATED, self._on_event_updated)
        self.event_bus.subscribe(EventType.POLL_CREATED, self._on_poll_created)
        self.event_bus.subscribe(EventType.USER_PREFERENCES_UPDATED, self._on_user_preferences_updated)
    
    async def start(self):
        """Start the notification manager."""
        if self.is_running:
            return
        
        self.is_running = True
        
        # Start batch processor
        await self.batch_processor.start()
        
        # Start background tasks
        asyncio.create_task(self._notification_processor())
        asyncio.create_task(self._scheduled_notification_checker())
        asyncio.create_task(self._retry_failed_notifications())
        
        # Load pending notifications from database
        await self._load_pending_notifications()
        
        self.logger.info("Notification manager started with batch processing")
    
    async def stop(self):
        """Stop the notification manager."""
        self.is_running = False
        
        # Stop batch processor
        await self.batch_processor.stop()
        
        # Cancel all scheduled tasks
        for task in self.scheduled_tasks.values():
            if not task.done():
                task.cancel()
        
        self.scheduled_tasks.clear()
        self.logger.info("Notification manager stopped")
    
    async def schedule_event_reminder(
        self,
        event_id: str,
        guild_id: str,
        recipient_user_ids: List[str],
        reminder_time: datetime,
        context_data: Dict[str, Any]
    ) -> str:
        """
        Schedule an event reminder notification.
        
        Args:
            event_id: ID of the event
            guild_id: Discord guild ID
            recipient_user_ids: List of user IDs to notify
            reminder_time: When to send the reminder
            context_data: Event data for template rendering
            
        Returns:
            Notification ID
        """
        template = self.templates[NotificationType.EVENT_REMINDER]
        rendered = template.render(context_data)
        
        notification = Notification(
            guild_id=guild_id,
            notification_type=NotificationType.EVENT_REMINDER,
            scheduled_for=reminder_time,
            recipient_user_ids=recipient_user_ids,
            title=rendered["title"],
            message=rendered["message"],
            event_id=event_id,
            context_data=context_data,
            embed_data={
                "color": template.embed_color,
                "timestamp": reminder_time.isoformat()
            }
        )
        
        # Save to database
        result = await self.database.notifications.insert_one(notification.to_dict())
        notification_id = str(result.inserted_id)
        
        # Schedule delivery
        await self._schedule_notification_delivery(notification_id, reminder_time)
        
        self.logger.info(f"Scheduled event reminder for {len(recipient_user_ids)} users")
        return notification_id
    
    async def schedule_poll_reminder(
        self,
        event_id: str,
        poll_id: str,
        guild_id: str,
        recipient_user_ids: List[str],
        reminder_time: datetime,
        context_data: Dict[str, Any]
    ) -> str:
        """Schedule a poll reminder notification."""
        template = self.templates[NotificationType.POLL_REMINDER]
        rendered = template.render(context_data)
        
        notification = Notification(
            guild_id=guild_id,
            notification_type=NotificationType.POLL_REMINDER,
            scheduled_for=reminder_time,
            recipient_user_ids=recipient_user_ids,
            title=rendered["title"],
            message=rendered["message"],
            event_id=event_id,
            poll_id=poll_id,
            context_data=context_data,
            embed_data={
                "color": template.embed_color,
                "timestamp": reminder_time.isoformat()
            }
        )
        
        result = await self.database.notifications.insert_one(notification.to_dict())
        notification_id = str(result.inserted_id)
        
        await self._schedule_notification_delivery(notification_id, reminder_time)
        
        self.logger.info(f"Scheduled poll reminder for {len(recipient_user_ids)} users")
        return notification_id
    
    async def send_immediate_notification(
        self,
        notification_type: NotificationType,
        guild_id: str,
        recipient_user_ids: List[str],
        context_data: Dict[str, Any],
        channel_preference: NotificationChannel = NotificationChannel.BOTH
    ) -> bool:
        """
        Send an immediate notification.
        
        Args:
            notification_type: Type of notification
            guild_id: Discord guild ID
            recipient_user_ids: List of user IDs to notify
            context_data: Data for template rendering
            channel_preference: Preferred delivery channel
            
        Returns:
            True if notification was queued successfully
        """
        if notification_type not in self.templates:
            self.logger.error(f"No template found for notification type: {notification_type}")
            return False
        
        template = self.templates[notification_type]
        rendered = template.render(context_data)
        
        notification = Notification(
            guild_id=guild_id,
            notification_type=notification_type,
            scheduled_for=datetime.utcnow(),
            recipient_user_ids=recipient_user_ids,
            channel_preference=channel_preference,
            title=rendered["title"],
            message=rendered["message"],
            context_data=context_data,
            embed_data={
                "color": template.embed_color,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        # Save to database
        result = await self.database.notifications.insert_one(notification.to_dict())
        notification_id = str(result.inserted_id)
        
        # Queue for immediate processing
        await self.processing_queue.put(notification_id)
        
        self.logger.info(f"Queued immediate notification for {len(recipient_user_ids)} users")
        return True
    
    async def cancel_notifications(
        self,
        event_id: Optional[str] = None,
        notification_type: Optional[NotificationType] = None,
        guild_id: Optional[str] = None
    ) -> int:
        """
        Cancel scheduled notifications matching criteria.
        
        Returns:
            Number of notifications cancelled
        """
        query = {"status": NotificationStatus.SCHEDULED.value}
        
        if event_id:
            query["event_id"] = event_id
        if notification_type:
            query["notification_type"] = notification_type.value
        if guild_id:
            query["guild_id"] = guild_id
        
        # Update database
        result = await self.database.notifications.update_many(
            query,
            {"$set": {"status": NotificationStatus.CANCELLED.value}}
        )
        
        # Cancel scheduled tasks
        cancelled_tasks = 0
        for task_id in list(self.scheduled_tasks.keys()):
            if event_id and event_id in task_id:
                task = self.scheduled_tasks.pop(task_id)
                if not task.done():
                    task.cancel()
                    cancelled_tasks += 1
        
        self.logger.info(f"Cancelled {result.modified_count} notifications and {cancelled_tasks} tasks")
        return result.modified_count
    
    async def _schedule_notification_delivery(self, notification_id: str, delivery_time: datetime):
        """Schedule a notification for delivery at a specific time."""
        delay = (delivery_time - datetime.utcnow()).total_seconds()
        
        if delay <= 0:
            # Immediate delivery
            await self.processing_queue.put(notification_id)
        else:
            # Scheduled delivery
            task = asyncio.create_task(
                self._delayed_notification_delivery(notification_id, delay)
            )
            self.scheduled_tasks[f"notification_{notification_id}"] = task
    
    async def _delayed_notification_delivery(self, notification_id: str, delay: float):
        """Deliver a notification after a delay."""
        try:
            await asyncio.sleep(delay)
            await self.processing_queue.put(notification_id)
        except asyncio.CancelledError:
            pass  # Task was cancelled
        finally:
            # Clean up task reference
            task_key = f"notification_{notification_id}"
            self.scheduled_tasks.pop(task_key, None)
    
    async def _notification_processor(self):
        """Background task to process notification queue."""
        while self.is_running:
            try:
                # Wait for notification to process
                notification_id = await asyncio.wait_for(
                    self.processing_queue.get(),
                    timeout=1.0
                )
                
                await self._deliver_notification(notification_id)
                
            except asyncio.TimeoutError:
                continue  # No notifications to process
            except Exception as e:
                self.logger.error(f"Error in notification processor: {e}", exc_info=True)
    
    async def _deliver_notification(self, notification_id: str):
        """Deliver a specific notification."""
        try:
            # Get notification from database
            notification_data = await self.database.notifications.find_one(
                {"_id": notification_id}
            )
            
            if not notification_data:
                self.logger.warning(f"Notification {notification_id} not found")
                return
            
            notification = Notification(**notification_data)
            
            if notification.status != NotificationStatus.SCHEDULED:
                self.logger.debug(f"Notification {notification_id} not scheduled, skipping")
                return
            
            # Get guild
            guild = self.bot.get_guild(int(notification.guild_id))
            if not guild:
                self.logger.warning(f"Guild {notification.guild_id} not found")
                await self._mark_notification_failed(
                    notification_id, 
                    "Guild not found"
                )
                return
            
            # Deliver to each recipient
            successful_deliveries = 0
            total_recipients = len(notification.recipient_user_ids)
            
            for user_id in notification.recipient_user_ids:
                try:
                    success = await self._deliver_to_user(
                        notification, guild, user_id
                    )
                    if success:
                        successful_deliveries += 1
                        
                except Exception as e:
                    self.logger.error(f"Failed to deliver to user {user_id}: {e}")
            
            # Update notification status
            if successful_deliveries == total_recipients:
                await self._mark_notification_sent(notification_id)
            elif successful_deliveries > 0:
                await self._mark_notification_partial(notification_id, successful_deliveries, total_recipients)
            else:
                await self._mark_notification_failed(notification_id, "All deliveries failed")
            
            # Emit notification event
            await self.event_bus.emit(
                EventType.NOTIFICATION_SENT,
                {
                    "notification_id": notification_id,
                    "notification_type": notification.notification_type.value,
                    "successful_deliveries": successful_deliveries,
                    "total_recipients": total_recipients,
                    "event_id": notification.event_id
                },
                source="notification_manager",
                guild_id=notification.guild_id
            )
            
        except Exception as e:
            self.logger.error(f"Error delivering notification {notification_id}: {e}", exc_info=True)
            await self._mark_notification_failed(notification_id, str(e))
    
    async def _deliver_to_user(
        self, 
        notification: Notification, 
        guild: discord.Guild, 
        user_id: str
    ) -> bool:
        """
        Deliver notification to a specific user based on their preferences.
        
        Returns:
            True if delivery was successful
        """
        # Get user preferences
        user_data = await self.database.users.find_one({
            "user_id": user_id,
            "guild_id": notification.guild_id
        })
        
        if user_data:
            user = User(**user_data)
            channel_pref = user.notification_preferences.channel
        else:
            channel_pref = NotificationChannel.BOTH
        
        # Determine delivery channels
        channels_to_try = []
        
        if channel_pref in [NotificationChannel.DM, NotificationChannel.BOTH]:
            channels_to_try.append("dm")
        
        if channel_pref in [NotificationChannel.SERVER, NotificationChannel.BOTH]:
            channels_to_try.append("server")
        
        # Try delivery to each channel
        for channel_type in channels_to_try:
            try:
                if channel_type == "dm":
                    success = await self._send_dm(notification, user_id)
                else:
                    success = await self._send_server_message(notification, guild, user_id)
                
                if success:
                    return True
                    
            except Exception as e:
                self.logger.error(f"Failed to deliver via {channel_type} to {user_id}: {e}")
        
        return False
    
    async def _send_dm(self, notification: Notification, user_id: str) -> bool:
        """Send notification via DM."""
        try:
            user = self.bot.get_user(int(user_id))
            if not user:
                user = await self.bot.fetch_user(int(user_id))
            
            if not user:
                return False
            
            embed = discord.Embed(
                title=notification.title,
                description=notification.message,
                color=notification.embed_data.get("color", 0x00ff00)
            )
            
            if notification.embed_data.get("timestamp"):
                embed.timestamp = datetime.fromisoformat(
                    notification.embed_data["timestamp"].replace("Z", "+00:00")
                )
            
            await user.send(embed=embed)
            return True
            
        except discord.Forbidden:
            self.logger.debug(f"Cannot send DM to user {user_id} (DMs disabled)")
            return False
        except Exception as e:
            self.logger.error(f"Error sending DM to {user_id}: {e}")
            return False
    
    async def _send_server_message(
        self, 
        notification: Notification, 
        guild: discord.Guild, 
        user_id: str
    ) -> bool:
        """Send notification via server channel."""
        try:
            # Find appropriate channel (events, general, etc.)
            target_channel = None
            
            # Look for events or game-night channels first
            for channel in guild.text_channels:
                if channel.name.lower() in ['events', 'game-night', 'gamenight', 'announcements']:
                    target_channel = channel
                    break
            
            # Fallback to general or first available channel
            if not target_channel:
                for channel in guild.text_channels:
                    if channel.name.lower() == 'general':
                        target_channel = channel
                        break
            
            if not target_channel and guild.text_channels:
                target_channel = guild.text_channels[0]
            
            if not target_channel:
                return False
            
            # Check permissions
            if not target_channel.permissions_for(guild.me).send_messages:
                return False
            
            user = guild.get_member(int(user_id))
            if not user:
                return False
            
            embed = discord.Embed(
                title=notification.title,
                description=notification.message,
                color=notification.embed_data.get("color", 0x00ff00)
            )
            
            if notification.embed_data.get("timestamp"):
                embed.timestamp = datetime.fromisoformat(
                    notification.embed_data["timestamp"].replace("Z", "+00:00")
                )
            
            # Mention the user
            content = f"{user.mention}"
            
            await target_channel.send(content=content, embed=embed)
            return True
            
        except Exception as e:
            self.logger.error(f"Error sending server message to {user_id}: {e}")
            return False
    
    async def _mark_notification_sent(self, notification_id: str):
        """Mark notification as successfully sent."""
        await self.database.notifications.update_one(
            {"_id": notification_id},
            {
                "$set": {
                    "status": NotificationStatus.SENT.value,
                    "updated_at": datetime.utcnow()
                }
            }
        )
    
    async def _mark_notification_failed(self, notification_id: str, error_message: str):
        """Mark notification as failed."""
        await self.database.notifications.update_one(
            {"_id": notification_id},
            {
                "$set": {
                    "status": NotificationStatus.FAILED.value,
                    "updated_at": datetime.utcnow()
                },
                "$push": {
                    "deliveries": {
                        "status": NotificationStatus.FAILED.value,
                        "attempted_at": datetime.utcnow(),
                        "error_message": error_message[:500]
                    }
                }
            }
        )
    
    async def _mark_notification_partial(
        self, 
        notification_id: str, 
        successful: int, 
        total: int
    ):
        """Mark notification as partially delivered."""
        status = NotificationStatus.SENT if successful == total else NotificationStatus.FAILED
        
        await self.database.notifications.update_one(
            {"_id": notification_id},
            {
                "$set": {
                    "status": status.value,
                    "updated_at": datetime.utcnow()
                }
            }
        )
    
    async def _scheduled_notification_checker(self):
        """Background task to check for due notifications."""
        while self.is_running:
            try:
                # Check every minute for due notifications
                await asyncio.sleep(60)
                
                # Find notifications that are due
                due_notifications = await self.database.notifications.find({
                    "status": NotificationStatus.SCHEDULED.value,
                    "scheduled_for": {"$lte": datetime.utcnow()}
                }).to_list(length=100)
                
                for notification_data in due_notifications:
                    notification_id = str(notification_data["_id"])
                    await self.processing_queue.put(notification_id)
                
                if due_notifications:
                    self.logger.info(f"Found {len(due_notifications)} due notifications")
                
            except Exception as e:
                self.logger.error(f"Error in scheduled notification checker: {e}", exc_info=True)
    
    async def _retry_failed_notifications(self):
        """Background task to retry failed notifications."""
        while self.is_running:
            try:
                # Check every 5 minutes for retryable notifications
                await asyncio.sleep(300)
                
                # Find failed notifications that can be retried
                retry_time = datetime.utcnow() - timedelta(minutes=5)
                
                failed_notifications = await self.database.notifications.find({
                    "status": NotificationStatus.FAILED.value,
                    "updated_at": {"$lte": retry_time}
                }).to_list(length=50)
                
                for notification_data in failed_notifications:
                    notification = Notification(**notification_data)
                    
                    if notification.can_retry():
                        notification_id = str(notification_data["_id"])
                        
                        # Reset status to scheduled
                        await self.database.notifications.update_one(
                            {"_id": notification_id},
                            {
                                "$set": {
                                    "status": NotificationStatus.SCHEDULED.value,
                                    "updated_at": datetime.utcnow()
                                }
                            }
                        )
                        
                        # Queue for retry
                        await self.processing_queue.put(notification_id)
                        
                        self.logger.info(f"Queued notification {notification_id} for retry")
                
            except Exception as e:
                self.logger.error(f"Error in retry processor: {e}", exc_info=True)
    
    async def _load_pending_notifications(self):
        """Load pending notifications from database on startup."""
        try:
            pending_notifications = await self.database.notifications.find({
                "status": NotificationStatus.SCHEDULED.value,
                "scheduled_for": {"$gte": datetime.utcnow()}
            }).to_list(length=1000)
            
            for notification_data in pending_notifications:
                notification = Notification(**notification_data)
                notification_id = str(notification_data["_id"])
                
                await self._schedule_notification_delivery(
                    notification_id, 
                    notification.scheduled_for
                )
            
            self.logger.info(f"Loaded {len(pending_notifications)} pending notifications")
            
        except Exception as e:
            self.logger.error(f"Error loading pending notifications: {e}", exc_info=True)
    
    # Event handlers
    async def _on_event_scheduled(self, event_data):
        """Handle event scheduling by creating reminders."""
        data = event_data.data
        event_id = data["event_id"]
        guild_id = data["guild_id"]
        
        # Get event details
        event_doc = await self.database.events.find_one({"_id": event_id})
        if not event_doc:
            return
        
        # Get attendees (users who RSVP'd yes)
        attendee_ids = []
        for user_id, rsvp in event_doc.get("rsvp_data", {}).items():
            if rsvp.get("status") == "YES":
                attendee_ids.append(user_id)
        
        if not attendee_ids:
            return
        
        # Schedule reminders based on user preferences
        event_datetime = datetime.combine(
            event_doc["schedule"]["selected_date"],
            event_doc["schedule"]["selected_time"]
        )
        
        # Default reminders: 24h and 1h before
        reminder_times = [
            event_datetime - timedelta(hours=24),
            event_datetime - timedelta(hours=1)
        ]
        
        context_data = {
            "event_title": event_doc["title"],
            "event_date": event_doc["schedule"]["selected_date"].strftime("%B %d, %Y"),
            "event_time": event_doc["schedule"]["selected_time"].strftime("%I:%M %p"),
            "selected_game": data.get("selected_game", "TBD")
        }
        
        for reminder_time in reminder_times:
            if reminder_time > datetime.utcnow():
                await self.schedule_event_reminder(
                    event_id=event_id,
                    guild_id=guild_id,
                    recipient_user_ids=attendee_ids,
                    reminder_time=reminder_time,
                    context_data=context_data
                )
    
    async def _on_event_cancelled(self, event_data):
        """Handle event cancellation."""
        data = event_data.data
        event_id = data["event_id"]
        
        # Cancel existing reminders
        await self.cancel_notifications(event_id=event_id)
        
        # Send cancellation notification
        attendee_ids = data.get("attendee_ids", [])
        if attendee_ids:
            context_data = {
                "event_title": data.get("event_title", "Unknown Event"),
                "event_date": data.get("event_date", "TBD"),
                "event_time": data.get("event_time", "TBD"),
                "cancellation_reason": data.get("reason", "No reason provided")
            }
            
            await self.send_immediate_notification(
                notification_type=NotificationType.EVENT_CANCELLED,
                guild_id=data["guild_id"],
                recipient_user_ids=attendee_ids,
                context_data=context_data
            )
    
    async def _on_event_updated(self, event_data):
        """Handle event updates."""
        data = event_data.data
        
        # Send update notification to attendees
        attendee_ids = data.get("attendee_ids", [])
        if attendee_ids:
            context_data = {
                "event_title": data.get("event_title", "Unknown Event"),
                "event_date": data.get("event_date", "TBD"),
                "event_time": data.get("event_time", "TBD"),
                "selected_game": data.get("selected_game", "TBD")
            }
            
            await self.send_immediate_notification(
                notification_type=NotificationType.EVENT_UPDATED,
                guild_id=data["guild_id"],
                recipient_user_ids=attendee_ids,
                context_data=context_data
            )
    
    async def _on_poll_created(self, event_data):
        """Handle poll creation by scheduling reminders."""
        data = event_data.data
        timeout_minutes = data.get("timeout_minutes", 60)
        
        # Schedule poll closing reminder (5 minutes before)
        if timeout_minutes > 10:
            reminder_time = datetime.utcnow() + timedelta(minutes=timeout_minutes - 5)
            
            # Get event participants
            event_doc = await self.database.events.find_one({"_id": data["event_id"]})
            if event_doc:
                # Get all guild members for now (could be refined to interested users)
                guild = self.bot.get_guild(int(data["guild_id"]))
                if guild:
                    member_ids = [str(member.id) for member in guild.members if not member.bot]
                    
                    context_data = {
                        "event_title": event_doc["title"],
                        "poll_title": data.get("poll_title", "Poll"),
                        "minutes_remaining": 5
                    }
                    
                    await self.schedule_poll_reminder(
                        event_id=data["event_id"],
                        poll_id=data.get("poll_id", ""),
                        guild_id=data["guild_id"],
                        recipient_user_ids=member_ids[:50],  # Limit to avoid spam
                        reminder_time=reminder_time,
                        context_data=context_data
                    )
    
    async def _on_user_preferences_updated(self, event_data):
        """Handle user preference updates."""
        # Could reschedule notifications based on new preferences
        pass
    
    async def _send_notification_batch(self, notifications: List[Dict[str, Any]]) -> None:
        """
        Send a batch of notifications efficiently.
        
        Args:
            notifications: List of notification data dictionaries
        """
        # Group notifications by guild and channel for efficient delivery
        grouped_notifications = defaultdict(lambda: defaultdict(list))
        
        for notification_data in notifications:
            guild_id = notification_data.get('guild_id')
            channel_pref = notification_data.get('channel_preference', 'BOTH')
            grouped_notifications[guild_id][channel_pref].append(notification_data)
        
        # Process each group
        for guild_id, channel_groups in grouped_notifications.items():
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                self.logger.warning(f"Guild {guild_id} not found for batch notifications")
                continue
            
            for channel_pref, group_notifications in channel_groups.items():
                try:
                    if channel_pref in ['DM', 'BOTH']:
                        await self._send_dm_batch(group_notifications)
                    
                    if channel_pref in ['SERVER', 'BOTH']:
                        await self._send_server_batch(guild, group_notifications)
                        
                except Exception as e:
                    self.logger.error(f"Failed to send notification batch: {e}")
                    raise
    
    async def _send_dm_batch(self, notifications: List[Dict[str, Any]]) -> None:
        """Send a batch of DM notifications."""
        # Group by user to avoid duplicate DMs
        user_notifications = defaultdict(list)
        
        for notification in notifications:
            for user_id in notification.get('recipient_user_ids', []):
                user_notifications[user_id].append(notification)
        
        # Send DMs concurrently (with rate limiting)
        dm_tasks = []
        for user_id, user_notifs in user_notifications.items():
            task = asyncio.create_task(self._send_user_dm_batch(user_id, user_notifs))
            dm_tasks.append(task)
        
        # Wait for all DMs to complete
        await asyncio.gather(*dm_tasks, return_exceptions=True)
    
    async def _send_user_dm_batch(self, user_id: str, notifications: List[Dict[str, Any]]) -> None:
        """Send multiple notifications to a single user via DM."""
        try:
            user = self.bot.get_user(int(user_id))
            if not user:
                user = await self.bot.fetch_user(int(user_id))
            
            if not user:
                return
            
            # Combine notifications into a single message if possible
            if len(notifications) == 1:
                # Single notification
                notification = notifications[0]
                embed = discord.Embed(
                    title=notification['title'],
                    description=notification['message'],
                    color=notification.get('embed_data', {}).get('color', 0x00ff00)
                )
                await user.send(embed=embed)
            else:
                # Multiple notifications - create summary
                embed = discord.Embed(
                    title=f"📢 {len(notifications)} Notifications",
                    color=0x00ff00
                )
                
                for i, notification in enumerate(notifications[:5]):  # Limit to 5 to avoid embed limits
                    embed.add_field(
                        name=notification['title'],
                        value=notification['message'][:100] + ('...' if len(notification['message']) > 100 else ''),
                        inline=False
                    )
                
                if len(notifications) > 5:
                    embed.add_field(
                        name="Additional Notifications",
                        value=f"... and {len(notifications) - 5} more notifications",
                        inline=False
                    )
                
                await user.send(embed=embed)
                
        except discord.Forbidden:
            self.logger.debug(f"Cannot send DM to user {user_id} (DMs disabled)")
        except Exception as e:
            self.logger.error(f"Error sending DM batch to {user_id}: {e}")
    
    async def _send_server_batch(self, guild: discord.Guild, notifications: List[Dict[str, Any]]) -> None:
        """Send a batch of server notifications."""
        # Find appropriate channel
        target_channel = None
        
        # Look for events or game-night channels first
        for channel in guild.text_channels:
            if channel.name.lower() in ['events', 'game-night', 'gamenight', 'announcements']:
                target_channel = channel
                break
        
        # Fallback to general or first available channel
        if not target_channel:
            for channel in guild.text_channels:
                if channel.name.lower() == 'general':
                    target_channel = channel
                    break
        
        if not target_channel and guild.text_channels:
            target_channel = guild.text_channels[0]
        
        if not target_channel or not target_channel.permissions_for(guild.me).send_messages:
            return
        
        # Group notifications by type for better organization
        notification_groups = defaultdict(list)
        for notification in notifications:
            notif_type = notification.get('notification_type', 'GENERAL')
            notification_groups[notif_type].append(notification)
        
        # Send each group
        for notif_type, group_notifications in notification_groups.items():
            try:
                await self._send_server_notification_group(target_channel, notif_type, group_notifications)
            except Exception as e:
                self.logger.error(f"Failed to send server notification group {notif_type}: {e}")
    
    async def _send_server_notification_group(
        self, 
        channel: discord.TextChannel, 
        notification_type: str, 
        notifications: List[Dict[str, Any]]
    ) -> None:
        """Send a group of notifications of the same type to a server channel."""
        if len(notifications) == 1:
            # Single notification
            notification = notifications[0]
            
            # Collect all recipients for mentions
            all_recipients = set()
            for user_id in notification.get('recipient_user_ids', []):
                all_recipients.add(user_id)
            
            # Create mentions (limit to avoid spam)
            mentions = []
            for user_id in list(all_recipients)[:10]:  # Limit to 10 mentions
                member = channel.guild.get_member(int(user_id))
                if member:
                    mentions.append(member.mention)
            
            content = " ".join(mentions) if mentions else ""
            
            embed = discord.Embed(
                title=notification['title'],
                description=notification['message'],
                color=notification.get('embed_data', {}).get('color', 0x00ff00)
            )
            
            await channel.send(content=content, embed=embed)
        
        else:
            # Multiple notifications of same type
            embed = discord.Embed(
                title=f"📢 {notification_type.replace('_', ' ').title()} Updates",
                color=0x00ff00
            )
            
            # Collect all unique recipients
            all_recipients = set()
            for notification in notifications:
                for user_id in notification.get('recipient_user_ids', []):
                    all_recipients.add(user_id)
            
            # Add notification summaries
            for i, notification in enumerate(notifications[:5]):  # Limit to 5
                embed.add_field(
                    name=notification['title'],
                    value=notification['message'][:100] + ('...' if len(notification['message']) > 100 else ''),
                    inline=False
                )
            
            if len(notifications) > 5:
                embed.add_field(
                    name="Additional Updates",
                    value=f"... and {len(notifications) - 5} more updates",
                    inline=False
                )
            
            # Create mentions (limit to avoid spam)
            mentions = []
            for user_id in list(all_recipients)[:10]:  # Limit to 10 mentions
                member = channel.guild.get_member(int(user_id))
                if member:
                    mentions.append(member.mention)
            
            content = " ".join(mentions) if mentions else ""
            
            await channel.send(content=content, embed=embed)
    
    async def send_batch_notification(
        self,
        notifications: List[Dict[str, Any]]
    ) -> None:
        """
        Send multiple notifications using batch processing.
        
        Args:
            notifications: List of notification dictionaries
        """
        for notification in notifications:
            await self.batch_processor.add_item(notification)
    
    def get_batch_stats(self) -> Dict[str, Any]:
        """Get batch processing statistics."""
        return self.batch_processor.get_stats()