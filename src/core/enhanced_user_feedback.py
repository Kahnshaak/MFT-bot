"""
Enhanced user feedback system with actionable error messages and suggestions.
"""

import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from enum import Enum

import discord
from discord.ext import commands

from utils.exceptions import ErrorCode, GameNightBotException
from utils.logging_config import get_logger


class FeedbackType(Enum):
    """Types of user feedback."""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HELP = "help"


class FeedbackSeverity(Enum):
    """Severity levels for feedback."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class UserFeedback:
    """Represents user feedback with context and suggestions."""
    
    def __init__(
        self,
        message: str,
        feedback_type: FeedbackType,
        severity: FeedbackSeverity = FeedbackSeverity.MEDIUM,
        suggestions: List[str] = None,
        help_command: str = None,
        error_code: str = None,
        context: Dict[str, Any] = None
    ):
        self.message = message
        self.feedback_type = feedback_type
        self.severity = severity
        self.suggestions = suggestions or []
        self.help_command = help_command
        self.error_code = error_code
        self.context = context or {}
        self.timestamp = datetime.utcnow()
    
    def to_embed(self) -> discord.Embed:
        """Convert feedback to Discord embed."""
        # Choose color based on feedback type
        color_map = {
            FeedbackType.SUCCESS: discord.Color.green(),
            FeedbackType.ERROR: discord.Color.red(),
            FeedbackType.WARNING: discord.Color.orange(),
            FeedbackType.INFO: discord.Color.blue(),
            FeedbackType.HELP: discord.Color.purple()
        }
        
        # Choose emoji based on feedback type
        emoji_map = {
            FeedbackType.SUCCESS: "✅",
            FeedbackType.ERROR: "❌",
            FeedbackType.WARNING: "⚠️",
            FeedbackType.INFO: "ℹ️",
            FeedbackType.HELP: "💡"
        }
        
        embed = discord.Embed(
            title=f"{emoji_map[self.feedback_type]} {self.message}",
            color=color_map[self.feedback_type]
        )
        
        # Add suggestions if available
        if self.suggestions:
            suggestions_text = "\n".join(f"• {suggestion}" for suggestion in self.suggestions)
            embed.add_field(
                name="💡 Suggestions",
                value=suggestions_text,
                inline=False
            )
        
        # Add help command if available
        if self.help_command:
            embed.add_field(
                name="🆘 Get Help",
                value=f"Use `{self.help_command}` for more information",
                inline=False
            )
        
        # Add error code for debugging
        if self.error_code:
            embed.set_footer(text=f"Error Code: {self.error_code}")
        
        return embed


class EnhancedUserFeedback:
    """Enhanced user feedback system with contextual messages and suggestions."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self._feedback_templates = self._initialize_feedback_templates()
    
    def _initialize_feedback_templates(self) -> Dict[str, Dict[str, Any]]:
        """Initialize feedback templates for common scenarios."""
        return {
            # Permission errors
            "permission_denied": {
                "message": "You don't have permission to do that",
                "suggestions": [
                    "Contact a server administrator if you think this is a mistake",
                    "Check if you have the required role for this command",
                    "Some commands require special permissions to use"
                ],
                "help_command": "/help permissions"
            },
            
            # Validation errors
            "invalid_input": {
                "message": "The information you provided isn't valid",
                "suggestions": [
                    "Check the format of your input and try again",
                    "Make sure all required fields are filled out",
                    "Use the examples provided as a guide"
                ],
                "help_command": "/help <command>"
            },
            
            "invalid_timezone": {
                "message": "That timezone isn't recognized",
                "suggestions": [
                    "Use a timezone like 'America/New_York' or 'Europe/London'",
                    "Check the timezone list at: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
                    "Try using 'UTC' if you're unsure"
                ],
                "help_command": "/help timezone"
            },
            
            "invalid_time_format": {
                "message": "That time format isn't recognized",
                "suggestions": [
                    "Use 24-hour format like '18:00' or '22:30'",
                    "Use 12-hour format like '6:00 PM' or '10:30 PM'",
                    "Make sure to include minutes (e.g., '8:00' not just '8')"
                ],
                "help_command": "/help time"
            },
            
            # Event errors
            "event_not_found": {
                "message": "I couldn't find that event",
                "suggestions": [
                    "Check the event ID and try again",
                    "Use '/event list' to see all available events",
                    "The event might have been cancelled or completed"
                ],
                "help_command": "/help event"
            },
            
            "event_already_started": {
                "message": "That event has already started",
                "suggestions": [
                    "You can't modify events that have already begun",
                    "Create a new event for future game nights",
                    "Contact an administrator if you need to make changes"
                ],
                "help_command": "/help event create"
            },
            
            # Game errors
            "game_not_found": {
                "message": "I couldn't find that game",
                "suggestions": [
                    "Check the spelling and try again",
                    "Use '/games list' to see available games",
                    "Try adding the game first with '/games add <game_name>'"
                ],
                "help_command": "/help games"
            },
            
            # System errors
            "database_error": {
                "message": "There was a problem with the database",
                "suggestions": [
                    "This is usually temporary - please try again in a moment",
                    "If the problem persists, contact an administrator",
                    "Your data is safe and will be restored automatically"
                ],
                "help_command": "/help support"
            },
            
            "rate_limited": {
                "message": "You're doing that too quickly",
                "suggestions": [
                    "Please wait a moment before trying again",
                    "Rate limits help keep the bot responsive for everyone",
                    "Try spacing out your commands more"
                ],
                "help_command": "/help limits"
            },
            
            # Success messages
            "event_created": {
                "message": "Event created successfully!",
                "suggestions": [
                    "Use the buttons below to start polls",
                    "Share the event with your friends",
                    "You can modify the event until it starts"
                ]
            },
            
            "profile_updated": {
                "message": "Profile updated successfully!",
                "suggestions": [
                    "Your changes will apply to future events",
                    "Use '/profile' to view your complete profile",
                    "Set up notifications to stay informed"
                ]
            }
        }
    
    def create_feedback(
        self,
        template_key: str = None,
        message: str = None,
        feedback_type: FeedbackType = FeedbackType.ERROR,
        severity: FeedbackSeverity = FeedbackSeverity.MEDIUM,
        suggestions: List[str] = None,
        help_command: str = None,
        error_code: str = None,
        context: Dict[str, Any] = None,
        **kwargs
    ) -> UserFeedback:
        """Create user feedback from template or custom parameters."""
        
        if template_key and template_key in self._feedback_templates:
            template = self._feedback_templates[template_key]
            
            # Use template values as defaults, allow overrides
            message = message or template.get("message", "An error occurred")
            suggestions = suggestions or template.get("suggestions", [])
            help_command = help_command or template.get("help_command")
            
            # Format message with context if provided
            if context:
                try:
                    message = message.format(**context)
                    suggestions = [s.format(**context) for s in suggestions]
                except KeyError:
                    # If formatting fails, use original message
                    pass
        
        return UserFeedback(
            message=message or "An error occurred",
            feedback_type=feedback_type,
            severity=severity,
            suggestions=suggestions,
            help_command=help_command,
            error_code=error_code,
            context=context
        )
    
    def from_exception(self, exception: Exception, context: Dict[str, Any] = None) -> UserFeedback:
        """Create feedback from an exception."""
        
        if isinstance(exception, GameNightBotException):
            # Use the exception's user message and error code
            template_key = self._get_template_key_from_error_code(exception.error_code)
            
            return self.create_feedback(
                template_key=template_key,
                message=exception.user_message,
                feedback_type=FeedbackType.ERROR,
                severity=self._get_severity_from_error_code(exception.error_code),
                error_code=exception.error_code.value if exception.error_code else None,
                context=context
            )
        
        # Handle common Discord.py exceptions
        elif isinstance(exception, discord.Forbidden):
            return self.create_feedback(
                template_key="permission_denied",
                feedback_type=FeedbackType.ERROR,
                severity=FeedbackSeverity.MEDIUM,
                context=context
            )
        
        elif isinstance(exception, discord.NotFound):
            return self.create_feedback(
                message="The requested resource wasn't found",
                feedback_type=FeedbackType.ERROR,
                severity=FeedbackSeverity.MEDIUM,
                suggestions=[
                    "Check that the ID or name is correct",
                    "The resource might have been deleted",
                    "Try refreshing and searching again"
                ],
                context=context
            )
        
        # Generic error fallback
        else:
            return self.create_feedback(
                message="Something went wrong",
                feedback_type=FeedbackType.ERROR,
                severity=FeedbackSeverity.HIGH,
                suggestions=[
                    "Please try again in a moment",
                    "If the problem persists, contact an administrator",
                    "Include any error details when reporting the issue"
                ],
                error_code=f"GENERIC_{type(exception).__name__}",
                context=context
            )
    
    def _get_template_key_from_error_code(self, error_code: ErrorCode) -> Optional[str]:
        """Get template key from error code."""
        mapping = {
            ErrorCode.PERMISSION_DENIED: "permission_denied",
            ErrorCode.VALIDATION_ERROR: "invalid_input",
            ErrorCode.INVALID_TIMEZONE: "invalid_timezone",
            ErrorCode.INVALID_TIME_FORMAT: "invalid_time_format",
            ErrorCode.EVENT_NOT_FOUND: "event_not_found",
            ErrorCode.GAME_NOT_FOUND: "game_not_found",
            ErrorCode.DATABASE_ERROR: "database_error",
            ErrorCode.RATE_LIMITED: "rate_limited"
        }
        return mapping.get(error_code)
    
    def _get_severity_from_error_code(self, error_code: ErrorCode) -> FeedbackSeverity:
        """Get severity level from error code."""
        high_severity = {
            ErrorCode.DATABASE_ERROR,
            ErrorCode.SYSTEM_ERROR,
            ErrorCode.CONFIGURATION_ERROR
        }
        
        medium_severity = {
            ErrorCode.PERMISSION_DENIED,
            ErrorCode.VALIDATION_ERROR,
            ErrorCode.EVENT_NOT_FOUND,
            ErrorCode.GAME_NOT_FOUND
        }
        
        if error_code in high_severity:
            return FeedbackSeverity.HIGH
        elif error_code in medium_severity:
            return FeedbackSeverity.MEDIUM
        else:
            return FeedbackSeverity.LOW
    
    async def send_feedback(
        self,
        interaction: Union[discord.Interaction, discord.ApplicationContext],
        feedback: UserFeedback,
        ephemeral: bool = True,
        followup: bool = False
    ):
        """Send feedback to user via interaction."""
        try:
            embed = feedback.to_embed()
            
            if followup or (hasattr(interaction, 'response') and interaction.response.is_done()):
                await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
        
        except Exception as e:
            self.logger.error(f"Error sending feedback: {e}", exc_info=True)
            # Fallback to simple text message
            try:
                simple_message = f"{feedback.message}"
                if feedback.suggestions:
                    simple_message += f"\n\nSuggestions:\n" + "\n".join(f"• {s}" for s in feedback.suggestions[:3])
                
                if followup or (hasattr(interaction, 'response') and interaction.response.is_done()):
                    await interaction.followup.send(simple_message, ephemeral=ephemeral)
                else:
                    await interaction.response.send_message(simple_message, ephemeral=ephemeral)
            except Exception:
                # Last resort - log the error
                self.logger.error(f"Failed to send any feedback to user: {e}", exc_info=True)