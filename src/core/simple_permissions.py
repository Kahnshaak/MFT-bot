"""
Simplified permission system for py-cord slash commands.
"""

import functools
from typing import Callable
import discord
from discord.ext import commands

from core.security_manager import Permission
from utils.exceptions import PermissionDeniedError
from utils.logging_config import get_logger

logger = get_logger(__name__)


def require_permission_simple(permission: Permission):
    """
    Simplified permission decorator that works with py-cord slash commands.
    
    Args:
        permission: Required permission
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            # Extract user and guild from interaction
            guild = interaction.guild
            
            if not guild:
                await interaction.response.send_message(
                    "❌ This command can only be used in a server.", 
                    ephemeral=True
                )
                return
            
            # Get the member object (which has guild permissions)
            member = guild.get_member(interaction.user.id)
            if not member:
                # Fallback to the user object
                member = interaction.user
            
            # Get security manager from bot
            security_manager = getattr(self.bot, 'security', None)
            if not security_manager:
                logger.error("Security manager not available")
                await interaction.response.send_message(
                    "❌ Security system unavailable.", 
                    ephemeral=True
                )
                return
            
            # Check permission
            try:
                security_manager.require_permission(member, permission)
                logger.debug(
                    f"Permission check passed: {member.id} has {permission.value}"
                )
                
                # Call the original function
                return await func(self, interaction, *args, **kwargs)
                
            except PermissionDeniedError:
                logger.warning(
                    f"Permission denied: {member.id} lacks {permission.value}"
                )
                await interaction.response.send_message(
                    f"❌ You don't have permission to use this command. Required: {permission.value}",
                    ephemeral=True
                )
        
        return wrapper
    return decorator


def check_basic_permissions(interaction: discord.Interaction) -> bool:
    """
    Basic permission check - everyone can create events for now.
    
    Args:
        interaction: Discord interaction
        
    Returns:
        True if user has basic permissions
    """
    # For now, allow everyone in a guild to create events
    return interaction.guild is not None