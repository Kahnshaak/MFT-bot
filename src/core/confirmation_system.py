"""
Enhanced confirmation system for destructive operations with undo functionality.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable, Awaitable
from enum import Enum
import uuid

import discord
from discord.ext import commands

from utils.logging_config import get_logger


class ConfirmationType(Enum):
    """Types of confirmations."""
    DELETE = "delete"
    CANCEL = "cancel"
    MODIFY = "modify"
    BULK_ACTION = "bulk_action"
    IRREVERSIBLE = "irreversible"


class ConfirmationSeverity(Enum):
    """Severity levels for confirmations."""
    LOW = "low"        # Simple confirmation
    MEDIUM = "medium"  # Requires typing confirmation
    HIGH = "high"      # Requires multiple steps
    CRITICAL = "critical"  # Requires admin approval


class UndoAction:
    """Represents an action that can be undone."""
    
    def __init__(
        self,
        action_id: str,
        user_id: str,
        guild_id: str,
        action_type: str,
        description: str,
        undo_function: Callable[[], Awaitable[bool]],
        undo_data: Dict[str, Any] = None,
        expires_at: datetime = None
    ):
        self.action_id = action_id
        self.user_id = user_id
        self.guild_id = guild_id
        self.action_type = action_type
        self.description = description
        self.undo_function = undo_function
        self.undo_data = undo_data or {}
        self.created_at = datetime.utcnow()
        self.expires_at = expires_at or (datetime.utcnow() + timedelta(minutes=30))
        self.is_undone = False
    
    def is_expired(self) -> bool:
        """Check if the undo action has expired."""
        return datetime.utcnow() > self.expires_at
    
    async def execute_undo(self) -> bool:
        """Execute the undo action."""
        if self.is_expired() or self.is_undone:
            return False
        
        try:
            success = await self.undo_function()
            if success:
                self.is_undone = True
            return success
        except Exception:
            return False


class ConfirmationManager:
    """Manages confirmations and undo actions."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.pending_confirmations: Dict[str, Dict[str, Any]] = {}
        self.undo_actions: Dict[str, UndoAction] = {}
        self._cleanup_task = None
    
    async def start_cleanup_task(self):
        """Start the cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_actions())
    
    async def _cleanup_expired_actions(self):
        """Clean up expired undo actions."""
        while True:
            try:
                current_time = datetime.utcnow()
                expired_actions = [
                    action_id for action_id, action in self.undo_actions.items()
                    if action.is_expired()
                ]
                
                for action_id in expired_actions:
                    del self.undo_actions[action_id]
                
                # Clean up every 5 minutes
                await asyncio.sleep(300)
            
            except Exception as e:
                self.logger.error(f"Error cleaning up expired actions: {e}", exc_info=True)
                await asyncio.sleep(60)  # Retry in 1 minute on error
    
    def create_confirmation(
        self,
        action_type: ConfirmationType,
        severity: ConfirmationSeverity,
        title: str,
        description: str,
        consequences: List[str] = None,
        confirmation_text: str = None,
        user_id: str = None,
        guild_id: str = None
    ) -> 'ConfirmationView':
        """Create a confirmation dialog."""
        
        confirmation_id = str(uuid.uuid4())
        
        # Store confirmation data
        self.pending_confirmations[confirmation_id] = {
            'action_type': action_type,
            'severity': severity,
            'title': title,
            'description': description,
            'consequences': consequences or [],
            'confirmation_text': confirmation_text,
            'user_id': user_id,
            'guild_id': guild_id,
            'created_at': datetime.utcnow()
        }
        
        return ConfirmationView(self, confirmation_id)
    
    def add_undo_action(
        self,
        user_id: str,
        guild_id: str,
        action_type: str,
        description: str,
        undo_function: Callable[[], Awaitable[bool]],
        undo_data: Dict[str, Any] = None,
        expires_minutes: int = 30
    ) -> str:
        """Add an undo action."""
        
        action_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=expires_minutes)
        
        undo_action = UndoAction(
            action_id=action_id,
            user_id=user_id,
            guild_id=guild_id,
            action_type=action_type,
            description=description,
            undo_function=undo_function,
            undo_data=undo_data,
            expires_at=expires_at
        )
        
        self.undo_actions[action_id] = undo_action
        return action_id
    
    async def execute_undo(self, action_id: str, user_id: str) -> bool:
        """Execute an undo action."""
        if action_id not in self.undo_actions:
            return False
        
        undo_action = self.undo_actions[action_id]
        
        # Verify user can undo this action
        if undo_action.user_id != user_id:
            return False
        
        return await undo_action.execute_undo()
    
    def get_user_undo_actions(self, user_id: str, guild_id: str = None) -> List[UndoAction]:
        """Get available undo actions for a user."""
        actions = []
        for undo_action in self.undo_actions.values():
            if (undo_action.user_id == user_id and 
                not undo_action.is_expired() and 
                not undo_action.is_undone and
                (guild_id is None or undo_action.guild_id == guild_id)):
                actions.append(undo_action)
        
        return sorted(actions, key=lambda x: x.created_at, reverse=True)


class ConfirmationView(discord.ui.View):
    """Interactive confirmation dialog."""
    
    def __init__(self, manager: ConfirmationManager, confirmation_id: str):
        super().__init__(timeout=300)  # 5 minute timeout
        self.manager = manager
        self.confirmation_id = confirmation_id
        self.confirmed = False
        self.cancelled = False
        
        # Get confirmation data
        self.data = manager.pending_confirmations.get(confirmation_id, {})
        
        # Add buttons based on severity
        severity = self.data.get('severity', ConfirmationSeverity.LOW)
        
        if severity == ConfirmationSeverity.CRITICAL:
            # Critical actions require typing confirmation
            self.add_item(TypeConfirmationButton())
        else:
            # Regular confirmation buttons
            self.add_item(ConfirmButton())
        
        self.add_item(CancelButton())
    
    def create_embed(self) -> discord.Embed:
        """Create confirmation embed."""
        action_type = self.data.get('action_type', ConfirmationType.DELETE)
        severity = self.data.get('severity', ConfirmationSeverity.LOW)
        
        # Choose color based on severity
        color_map = {
            ConfirmationSeverity.LOW: discord.Color.orange(),
            ConfirmationSeverity.MEDIUM: discord.Color.red(),
            ConfirmationSeverity.HIGH: discord.Color.dark_red(),
            ConfirmationSeverity.CRITICAL: discord.Color.from_rgb(139, 0, 0)  # Dark red
        }
        
        # Choose emoji based on action type
        emoji_map = {
            ConfirmationType.DELETE: "🗑️",
            ConfirmationType.CANCEL: "❌",
            ConfirmationType.MODIFY: "✏️",
            ConfirmationType.BULK_ACTION: "📦",
            ConfirmationType.IRREVERSIBLE: "⚠️"
        }
        
        embed = discord.Embed(
            title=f"{emoji_map.get(action_type, '⚠️')} {self.data.get('title', 'Confirmation Required')}",
            description=self.data.get('description', 'Are you sure you want to proceed?'),
            color=color_map.get(severity, discord.Color.orange())
        )
        
        # Add consequences if specified
        consequences = self.data.get('consequences', [])
        if consequences:
            consequences_text = "\n".join(f"• {consequence}" for consequence in consequences)
            embed.add_field(
                name="⚠️ This will:",
                value=consequences_text,
                inline=False
            )
        
        # Add severity warning for high-risk actions
        if severity in [ConfirmationSeverity.HIGH, ConfirmationSeverity.CRITICAL]:
            embed.add_field(
                name="🚨 Warning",
                value="This action cannot be undone. Please confirm you want to proceed.",
                inline=False
            )
        
        return embed
    
    async def on_timeout(self):
        """Handle view timeout."""
        # Clean up pending confirmation
        if self.confirmation_id in self.manager.pending_confirmations:
            del self.manager.pending_confirmations[self.confirmation_id]


class ConfirmButton(discord.ui.Button):
    """Confirmation button."""
    
    def __init__(self):
        super().__init__(
            label="Confirm",
            style=discord.ButtonStyle.danger,
            emoji="✅"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle confirmation."""
        view: ConfirmationView = self.view
        view.confirmed = True
        
        # Disable all buttons
        for item in view.children:
            item.disabled = True
        
        embed = discord.Embed(
            title="✅ Confirmed",
            description="Action confirmed. Processing...",
            color=discord.Color.green()
        )
        
        await interaction.response.edit_message(embed=embed, view=view)
        view.stop()


class CancelButton(discord.ui.Button):
    """Cancel button."""
    
    def __init__(self):
        super().__init__(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            emoji="❌"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle cancellation."""
        view: ConfirmationView = self.view
        view.cancelled = True
        
        # Disable all buttons
        for item in view.children:
            item.disabled = True
        
        embed = discord.Embed(
            title="❌ Cancelled",
            description="Action cancelled. No changes were made.",
            color=discord.Color.blue()
        )
        
        await interaction.response.edit_message(embed=embed, view=view)
        view.stop()


class TypeConfirmationButton(discord.ui.Button):
    """Button that opens a modal for typing confirmation."""
    
    def __init__(self):
        super().__init__(
            label="Type to Confirm",
            style=discord.ButtonStyle.danger,
            emoji="⌨️"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Open typing confirmation modal."""
        view: ConfirmationView = self.view
        confirmation_text = view.data.get('confirmation_text', 'CONFIRM')
        
        modal = TypeConfirmationModal(confirmation_text)
        await interaction.response.send_modal(modal)
        
        # Wait for modal completion
        await modal.wait()
        
        if modal.confirmed:
            view.confirmed = True
            
            # Disable all buttons
            for item in view.children:
                item.disabled = True
            
            embed = discord.Embed(
                title="✅ Confirmed",
                description="Action confirmed. Processing...",
                color=discord.Color.green()
            )
            
            await interaction.edit_original_response(embed=embed, view=view)
            view.stop()


class TypeConfirmationModal(discord.ui.Modal):
    """Modal for typing confirmation."""
    
    def __init__(self, confirmation_text: str):
        super().__init__(title="Type to Confirm")
        self.confirmation_text = confirmation_text.upper()
        self.confirmed = False
        
        self.text_input = discord.ui.TextInput(
            label=f"Type '{confirmation_text}' to confirm",
            placeholder=f"Type {confirmation_text} here...",
            min_length=len(confirmation_text),
            max_length=len(confirmation_text) + 10,
            required=True
        )
        self.add_item(self.text_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        user_input = self.text_input.value.strip().upper()
        
        if user_input == self.confirmation_text:
            self.confirmed = True
            await interaction.response.defer()
        else:
            await interaction.response.send_message(
                f"❌ Incorrect confirmation text. Please type '{self.confirmation_text}' exactly.",
                ephemeral=True
            )


class UndoView(discord.ui.View):
    """View for undo actions."""
    
    def __init__(self, manager: ConfirmationManager, undo_actions: List[UndoAction]):
        super().__init__(timeout=300)
        self.manager = manager
        self.undo_actions = undo_actions
        
        # Add undo buttons for each action (max 5)
        for i, action in enumerate(undo_actions[:5]):
            button = UndoButton(action, i)
            self.add_item(button)
    
    def create_embed(self) -> discord.Embed:
        """Create undo actions embed."""
        embed = discord.Embed(
            title="↩️ Available Undo Actions",
            description="You can undo these recent actions:",
            color=discord.Color.blue()
        )
        
        for i, action in enumerate(self.undo_actions[:5]):
            time_ago = datetime.utcnow() - action.created_at
            minutes_ago = int(time_ago.total_seconds() / 60)
            
            embed.add_field(
                name=f"{i+1}. {action.description}",
                value=f"**Type:** {action.action_type}\n**Time:** {minutes_ago} minutes ago",
                inline=True
            )
        
        if not self.undo_actions:
            embed.description = "No recent actions can be undone."
        
        embed.set_footer(text="Undo actions expire after 30 minutes")
        return embed


class UndoButton(discord.ui.Button):
    """Button for undoing a specific action."""
    
    def __init__(self, undo_action: UndoAction, index: int):
        super().__init__(
            label=f"Undo {index + 1}",
            style=discord.ButtonStyle.secondary,
            emoji="↩️"
        )
        self.undo_action = undo_action
    
    async def callback(self, interaction: discord.Interaction):
        """Handle undo action."""
        view: UndoView = self.view
        
        # Verify user can undo this action
        if self.undo_action.user_id != str(interaction.user.id):
            await interaction.response.send_message(
                "❌ You can only undo your own actions.",
                ephemeral=True
            )
            return
        
        # Execute undo
        success = await view.manager.execute_undo(
            self.undo_action.action_id,
            str(interaction.user.id)
        )
        
        if success:
            await interaction.response.send_message(
                f"✅ Successfully undid: {self.undo_action.description}",
                ephemeral=True
            )
            
            # Disable this button
            self.disabled = True
            await interaction.edit_original_response(view=view)
        else:
            await interaction.response.send_message(
                f"❌ Failed to undo action. It may have expired or already been undone.",
                ephemeral=True
            )


# Global confirmation manager instance
confirmation_manager = ConfirmationManager()