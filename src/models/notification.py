"""
Notification model for managing scheduled reminders and alerts.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import Field, field_validator

from .base import BaseDocument, ValidationMixin, TimestampMixin


class NotificationChannel(str, Enum):
    """Notification delivery channels."""
    DM = "DM"
    SERVER = "SERVER"
    BOTH = "BOTH"


class NotificationType(str, Enum):
    """Types of notifications."""
    EVENT_REMINDER = "EVENT_REMINDER"
    POLL_REMINDER = "POLL_REMINDER"
    POLL_CLOSING = "POLL_CLOSING"
    EVENT_CANCELLED = "EVENT_CANCELLED"
    EVENT_UPDATED = "EVENT_UPDATED"
    ADMIN_ALERT = "ADMIN_ALERT"
    SYSTEM_ALERT = "SYSTEM_ALERT"


class NotificationStatus(str, Enum):
    """Notification delivery status."""
    SCHEDULED = "SCHEDULED"
    SENT = "SENT"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class NotificationTemplate(BaseDocument):
    """Template for notification messages."""
    
    notification_type: NotificationType = Field(..., description="Type of notification")
    title_template: str = Field(..., max_length=200, description="Title template with placeholders")
    message_template: str = Field(..., max_length=2000, description="Message template with placeholders")
    embed_color: Optional[int] = Field(None, description="Embed color for Discord messages")
    
    @field_validator('title_template', 'message_template')
    @classmethod
    def validate_templates(cls, v):
        return ValidationMixin.sanitize_text(v, 2000)
    
    def validate_data(self) -> None:
        """Validate template data."""
        if not self.title_template.strip():
            raise ValueError("Title template cannot be empty")
        if not self.message_template.strip():
            raise ValueError("Message template cannot be empty")
    
    def render(self, context: Dict[str, Any]) -> Dict[str, str]:
        """Render template with context variables."""
        try:
            title = self.title_template.format(**context)
            message = self.message_template.format(**context)
            return {"title": title, "message": message}
        except KeyError as e:
            raise ValueError(f"Missing template variable: {e}")


class NotificationDelivery(BaseDocument):
    """Individual notification delivery attempt."""
    
    channel_type: NotificationChannel = Field(..., description="Delivery channel")
    channel_id: Optional[str] = Field(None, description="Discord channel/user ID")
    status: NotificationStatus = Field(default=NotificationStatus.SCHEDULED)
    attempted_at: Optional[datetime] = Field(None, description="When delivery was attempted")
    delivered_at: Optional[datetime] = Field(None, description="When successfully delivered")
    error_message: Optional[str] = Field(None, max_length=500, description="Error if delivery failed")
    retry_count: int = Field(default=0, ge=0, description="Number of retry attempts")
    
    def validate_data(self) -> None:
        """Validate delivery data."""
        if self.status == NotificationStatus.SENT and not self.delivered_at:
            self.delivered_at = TimestampMixin.utc_now()
        
        if self.status == NotificationStatus.FAILED and not self.error_message:
            raise ValueError("Error message required for failed deliveries")


class Notification(BaseDocument, ValidationMixin, TimestampMixin):
    """
    Notification model for scheduled reminders and alerts.
    
    Manages the lifecycle of notifications from scheduling to delivery.
    """
    
    guild_id: str = Field(..., description="Discord guild ID")
    notification_type: NotificationType = Field(..., description="Type of notification")
    
    # Scheduling
    scheduled_for: datetime = Field(..., description="When to send the notification")
    timezone: str = Field(default="UTC", description="Timezone for scheduling")
    
    # Recipients
    recipient_user_ids: List[str] = Field(default_factory=list, description="Target user IDs")
    recipient_role_ids: List[str] = Field(default_factory=list, description="Target role IDs")
    channel_preference: NotificationChannel = Field(default=NotificationChannel.BOTH)
    
    # Content
    title: str = Field(..., max_length=200, description="Notification title")
    message: str = Field(..., max_length=2000, description="Notification message")
    embed_data: Optional[Dict[str, Any]] = Field(None, description="Discord embed data")
    
    # Context
    event_id: Optional[str] = Field(None, description="Related event ID")
    poll_id: Optional[str] = Field(None, description="Related poll ID")
    context_data: Dict[str, Any] = Field(default_factory=dict, description="Additional context")
    
    # Delivery tracking
    deliveries: List[NotificationDelivery] = Field(default_factory=list)
    status: NotificationStatus = Field(default=NotificationStatus.SCHEDULED)
    
    # Retry configuration
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay_minutes: int = Field(default=5, ge=1, le=60)
    
    @field_validator('guild_id')
    @classmethod
    def validate_guild_id(cls, v):
        return ValidationMixin.validate_guild_id(v)
    
    @field_validator('recipient_user_ids')
    @classmethod
    def validate_user_ids(cls, v):
        return [ValidationMixin.validate_user_id(uid) for uid in v]
    
    @field_validator('timezone')
    @classmethod
    def validate_timezone(cls, v):
        return ValidationMixin.validate_timezone(v)
    
    @field_validator('title', 'message')
    @classmethod
    def validate_content(cls, v):
        return ValidationMixin.sanitize_text(v, 2000)
    
    def validate_data(self) -> None:
        """Validate notification data."""
        if not self.title.strip():
            raise ValueError("Notification title cannot be empty")
        
        if not self.message.strip():
            raise ValueError("Notification message cannot be empty")
        
        if not self.recipient_user_ids and not self.recipient_role_ids:
            raise ValueError("At least one recipient (user or role) must be specified")
        
        if self.scheduled_for < TimestampMixin.utc_now():
            raise ValueError("Cannot schedule notifications in the past")
    
    def is_due(self) -> bool:
        """Check if notification is due for delivery."""
        return (
            self.status == NotificationStatus.SCHEDULED and
            self.scheduled_for <= TimestampMixin.utc_now()
        )
    
    def can_retry(self) -> bool:
        """Check if notification can be retried."""
        return (
            self.status == NotificationStatus.FAILED and
            self.get_retry_count() < self.max_retries
        )
    
    def get_retry_count(self) -> int:
        """Get total retry count across all deliveries."""
        return sum(delivery.retry_count for delivery in self.deliveries)
    
    def add_delivery_attempt(
        self,
        channel_type: NotificationChannel,
        channel_id: Optional[str] = None,
        success: bool = False,
        error_message: Optional[str] = None
    ) -> None:
        """Add a delivery attempt record."""
        delivery = NotificationDelivery(
            channel_type=channel_type,
            channel_id=channel_id,
            status=NotificationStatus.SENT if success else NotificationStatus.FAILED,
            attempted_at=TimestampMixin.utc_now(),
            error_message=error_message
        )
        
        if success:
            delivery.delivered_at = TimestampMixin.utc_now()
        
        self.deliveries.append(delivery)
        self.update_timestamp()
        
        # Update overall status
        if success and all(d.status == NotificationStatus.SENT for d in self.deliveries):
            self.status = NotificationStatus.SENT
        elif not success:
            self.status = NotificationStatus.FAILED
    
    def mark_cancelled(self) -> None:
        """Mark notification as cancelled."""
        self.status = NotificationStatus.CANCELLED
        self.update_timestamp()
    
    def get_next_retry_time(self) -> Optional[datetime]:
        """Get the next retry time if retries are available."""
        if not self.can_retry():
            return None
        
        retry_count = self.get_retry_count()
        # Exponential backoff: 5, 10, 20 minutes
        delay_minutes = self.retry_delay_minutes * (2 ** retry_count)
        
        return TimestampMixin.utc_now() + timedelta(minutes=delay_minutes)
    
    def get_delivery_summary(self) -> Dict[str, Any]:
        """Get summary of delivery attempts."""
        total_attempts = len(self.deliveries)
        successful_deliveries = sum(1 for d in self.deliveries if d.status == NotificationStatus.SENT)
        failed_deliveries = sum(1 for d in self.deliveries if d.status == NotificationStatus.FAILED)
        
        return {
            "total_attempts": total_attempts,
            "successful": successful_deliveries,
            "failed": failed_deliveries,
            "success_rate": successful_deliveries / total_attempts if total_attempts > 0 else 0,
            "last_attempt": max((d.attempted_at for d in self.deliveries), default=None),
            "can_retry": self.can_retry()
        }


# Default notification templates
DEFAULT_TEMPLATES = {
    NotificationType.EVENT_REMINDER: NotificationTemplate(
        notification_type=NotificationType.EVENT_REMINDER,
        title_template="🎮 Game Night Reminder: {event_title}",
        message_template=(
            "Don't forget about **{event_title}**!\n\n"
            "📅 **Date:** {event_date}\n"
            "⏰ **Time:** {event_time}\n"
            "🎯 **Game:** {selected_game}\n\n"
            "See you there! 🎉"
        ),
        embed_color=0x00ff00
    ),
    
    NotificationType.POLL_REMINDER: NotificationTemplate(
        notification_type=NotificationType.POLL_REMINDER,
        title_template="📊 Poll Reminder: {poll_title}",
        message_template=(
            "⏰ **{minutes_remaining} minutes left** to vote in the poll!\n\n"
            "**Event:** {event_title}\n"
            "**Poll:** {poll_title}\n\n"
            "Make sure your voice is heard! 🗳️"
        ),
        embed_color=0xffaa00
    ),
    
    NotificationType.POLL_CLOSING: NotificationTemplate(
        notification_type=NotificationType.POLL_CLOSING,
        title_template="⚠️ Poll Closing Soon: {poll_title}",
        message_template=(
            "🚨 **Last chance to vote!**\n\n"
            "**Event:** {event_title}\n"
            "**Poll:** {poll_title}\n\n"
            "Poll closes in **{minutes_remaining} minutes**!"
        ),
        embed_color=0xff0000
    ),
    
    NotificationType.EVENT_CANCELLED: NotificationTemplate(
        notification_type=NotificationType.EVENT_CANCELLED,
        title_template="❌ Event Cancelled: {event_title}",
        message_template=(
            "Unfortunately, **{event_title}** has been cancelled.\n\n"
            "📅 **Was scheduled for:** {event_date} at {event_time}\n"
            "💬 **Reason:** {cancellation_reason}\n\n"
            "We'll let you know about future events! 📢"
        ),
        embed_color=0xff0000
    ),
    
    NotificationType.EVENT_UPDATED: NotificationTemplate(
        notification_type=NotificationType.EVENT_UPDATED,
        title_template="📝 Event Updated: {event_title}",
        message_template=(
            "**{event_title}** has been updated!\n\n"
            "📅 **Date:** {event_date}\n"
            "⏰ **Time:** {event_time}\n"
            "🎯 **Game:** {selected_game}\n\n"
            "Check the latest details! ✨"
        ),
        embed_color=0x0099ff
    ),
    
    NotificationType.ADMIN_ALERT: NotificationTemplate(
        notification_type=NotificationType.ADMIN_ALERT,
        title_template="🔔 Admin Alert: {alert_title}",
        message_template=(
            "**Admin attention required:**\n\n"
            "{alert_message}\n\n"
            "**Event:** {event_title}\n"
            "**Time:** {timestamp}"
        ),
        embed_color=0xff6600
    )
}