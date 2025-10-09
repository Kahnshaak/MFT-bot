"""
Simple security manager for basic permission checking.
"""

from typing import Set
from enum import Enum

import discord

from utils.logging_config import get_logger
from utils.exceptions import PermissionDeniedError


class Permission(Enum):
    """Basic bot permission levels."""
    
    # Basic permissions
    VIEW_EVENTS = "view_events"
    CREATE_EVENTS = "create_events"
    MANAGE_OWN_EVENTS = "manage_own_events"
    
    # Administrative permissions
    MANAGE_ALL_EVENTS = "manage_all_events"
    MANAGE_RECURRING = "manage_recurring"
    CONFIGURE_BOT = "configure_bot"


class SecurityManager:
    """
    Simple security manager for basic permission checking.
    """
    
    def __init__(self, settings=None):
        self.settings = settings
    
    def get_user_permissions(self, user: discord.Member) -> Set[Permission]:
        """
        Get basic permissions for a user based on Discord permissions.
        
        Args:
            user: Discord member
            
        Returns:
            Set of permissions the user has
        """
        permissions = {Permission.VIEW_EVENTS}  # Everyone can view events
        
        # Basic member permissions
        permissions.add(Permission.CREATE_EVENTS)
        permissions.add(Permission.MANAGE_OWN_EVENTS)
        
        # Admin permissions
        if user.guild_permissions.administrator or user.guild_permissions.manage_guild:
            permissions.add(Permission.MANAGE_ALL_EVENTS)
            permissions.add(Permission.MANAGE_RECURRING)
            permissions.add(Permission.CONFIGURE_BOT)
        
        return permissions
    
    def check_permission(self, user: discord.Member, required_permission: Permission) -> bool:
        """
        Check if a user has a specific permission.
        
        Args:
            user: Discord member
            required_permission: Permission to check
            
        Returns:
            True if user has permission, False otherwise
        """
        user_permissions = self.get_user_permissions(user)
        return required_permission in user_permissions
    
    def require_permission(self, user: discord.Member, required_permission: Permission) -> None:
        """
        Require a user to have a specific permission, raise exception if not.
        
        Args:
            user: Discord member
            required_permission: Permission to require
            
        Raises:
            PermissionDeniedError: If user lacks required permission
        """
        if not self.check_permission(user, required_permission):
            get_logger(__name__).warning(f"Permission denied for user {user.id}: {required_permission.value}")
            raise PermissionDeniedError(f"User lacks required permission: {required_permission.value}")
    
    def validate_input(self, input_data: str, max_length: int = 2000) -> str:
        """
        Basic input validation and sanitization.
        
        Args:
            input_data: Input string to validate
            max_length: Maximum allowed length
            
        Returns:
            Sanitized input string
        """
        if not isinstance(input_data, str):
            return str(input_data)
        
        # Length validation
        if len(input_data) > max_length:
            input_data = input_data[:max_length]
        
        # Basic sanitization
        sanitized = input_data.strip()
        
        # Remove potential Discord mentions that could cause issues
        sanitized = sanitized.replace('@everyone', '@\u200beveryone')
        sanitized = sanitized.replace('@here', '@\u200bhere')
        
        return sanitized