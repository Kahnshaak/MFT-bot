"""
Permission decorators and middleware for command and API endpoint protection.
"""

import functools
from typing import Callable, Optional, Union, List
import discord
from discord.ext import commands

from core.security_manager import Permission, SecurityManager
from utils.exceptions import PermissionDeniedError
from utils.logging_config import get_logger

logger = get_logger(__name__)


def require_permission(
    permission: Permission,
    check_owner: bool = True,
    resource_id_param: Optional[str] = None
):
    """
    Decorator to require specific permissions for command execution.
    
    Args:
        permission: Required permission
        check_owner: Whether to allow resource owners to bypass permission check
        resource_id_param: Parameter name that contains resource ID for ownership check
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract context and user from arguments
            ctx = None
            user = None
            guild_id = None
            
            # Handle different function signatures
            if args:
                if isinstance(args[0], commands.Context):
                    ctx = args[0]
                    user = ctx.author
                    guild_id = str(ctx.guild.id) if ctx.guild else None
                elif isinstance(args[0], discord.Interaction):
                    interaction = args[0]
                    user = interaction.user
                    guild_id = str(interaction.guild.id) if interaction.guild else None
                elif hasattr(args[0], 'bot'):
                    # Cog method - check if second argument is interaction/context
                    cog = args[0]
                    if len(args) > 1:
                        if isinstance(args[1], commands.Context):
                            ctx = args[1]
                            user = ctx.author
                            guild_id = str(ctx.guild.id) if ctx.guild else None
                        elif isinstance(args[1], discord.Interaction):
                            interaction = args[1]
                            user = interaction.user
                            guild_id = str(interaction.guild.id) if interaction.guild else None
            
            if not user or not guild_id:
                raise PermissionDeniedError("Unable to determine user context")
            
            # Get security manager
            security_manager = None
            if ctx and hasattr(ctx.bot, 'security'):
                security_manager = ctx.bot.security
            elif hasattr(args[0], 'bot') and hasattr(args[0].bot, 'security'):
                security_manager = args[0].bot.security
            
            if not security_manager:
                logger.error("Security manager not available")
                raise PermissionDeniedError("Security system unavailable")
            
            # Check ownership if applicable
            if check_owner and resource_id_param:
                resource_id = kwargs.get(resource_id_param)
                if resource_id and await _check_resource_ownership(user.id, resource_id, args[0]):
                    logger.debug(
                        "Permission granted via ownership",
                        user_id=user.id,
                        resource_id=resource_id,
                        permission=permission.value
                    )
                    return await func(*args, **kwargs)
            
            # Check permission
            try:
                security_manager.require_permission(user, permission)
                
                logger.debug(
                    "Permission check passed",
                    user_id=user.id,
                    guild_id=guild_id,
                    permission=permission.value
                )
                
                return await func(*args, **kwargs)
                
            except PermissionDeniedError as e:
                logger.warning(
                    "Permission denied",
                    user_id=user.id,
                    guild_id=guild_id,
                    permission=permission.value,
                    function=func.__name__
                )
                raise
        
        return wrapper
    return decorator


def require_any_permission(*permissions: Permission):
    """
    Decorator to require any one of the specified permissions.
    
    Args:
        permissions: List of permissions, user needs at least one
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract context similar to require_permission
            ctx = None
            user = None
            guild_id = None
            
            if args:
                if isinstance(args[0], commands.Context):
                    ctx = args[0]
                    user = ctx.author
                    guild_id = str(ctx.guild.id) if ctx.guild else None
                elif isinstance(args[0], discord.Interaction):
                    interaction = args[0]
                    user = interaction.user
                    guild_id = str(interaction.guild.id) if interaction.guild else None
                elif hasattr(args[0], 'bot'):
                    cog = args[0]
                    if len(args) > 1:
                        if isinstance(args[1], commands.Context):
                            ctx = args[1]
                            user = ctx.author
                            guild_id = str(ctx.guild.id) if ctx.guild else None
                        elif isinstance(args[1], discord.Interaction):
                            interaction = args[1]
                            user = interaction.user
                            guild_id = str(interaction.guild.id) if interaction.guild else None
            
            if not user or not guild_id:
                raise PermissionDeniedError("Unable to determine user context")
            
            # Get security manager
            security_manager = None
            if ctx and hasattr(ctx.bot, 'security'):
                security_manager = ctx.bot.security
            elif hasattr(args[0], 'bot') and hasattr(args[0].bot, 'security'):
                security_manager = args[0].bot.security
            
            if not security_manager:
                raise PermissionDeniedError("Security system unavailable")
            
            # Check if user has any of the required permissions
            user_permissions = security_manager.get_user_permissions(user)
            
            for permission in permissions:
                if permission in user_permissions:
                    logger.debug(
                        "Permission check passed (any)",
                        user_id=user.id,
                        guild_id=guild_id,
                        granted_permission=permission.value,
                        required_permissions=[p.value for p in permissions]
                    )
                    return await func(*args, **kwargs)
            
            logger.warning(
                "Permission denied (any)",
                user_id=user.id,
                guild_id=guild_id,
                required_permissions=[p.value for p in permissions],
                user_permissions=[p.value for p in user_permissions]
            )
            
            raise PermissionDeniedError(
                f"User lacks any of the required permissions: {[p.value for p in permissions]}"
            )
        
        return wrapper
    return decorator


# Rate limiting removed in simplified version


def validate_input(**field_rules):
    """
    Decorator to validate input parameters using validation manager.
    
    Args:
        field_rules: Dictionary mapping parameter names to validation rules
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Get validation manager
            validation_manager = None
            if args and hasattr(args[0], 'bot') and hasattr(args[0].bot, 'validation'):
                validation_manager = args[0].bot.validation
            
            if validation_manager and field_rules:
                # Validate specified parameters using simplified validation
                validated_data = validation_manager.validate_data(kwargs, field_rules)
                kwargs.update(validated_data)
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


async def _check_resource_ownership(user_id: int, resource_id: str, cog) -> bool:
    """
    Check if a user owns a specific resource.
    
    Args:
        user_id: Discord user ID
        resource_id: Resource identifier
        cog: Cog instance to access database
        
    Returns:
        True if user owns the resource, False otherwise
    """
    try:
        # This is a placeholder - actual implementation would depend on resource type
        # For events, check if user is the creator
        if hasattr(cog, 'bot') and hasattr(cog.bot, 'database'):
            database = cog.bot.database
            
            # Try to find the resource and check ownership
            # This would need to be customized based on resource type
            event = await database.get_event(resource_id)
            if event and event.get('creator_id') == str(user_id):
                return True
        
        return False
    except Exception as e:
        logger.error(
            "Error checking resource ownership",
            user_id=user_id,
            resource_id=resource_id,
            error=str(e)
        )
        return False


# Command check functions for discord.py
def has_permission(permission: Permission):
    """
    Discord.py command check for permissions.
    
    Args:
        permission: Required permission
    """
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False
        
        security_manager = getattr(ctx.bot, 'security', None)
        if not security_manager:
            return False
        
        return security_manager.check_permission(ctx.author, permission)
    
    return commands.check(predicate)


def has_any_permission(*permissions: Permission):
    """
    Discord.py command check for any of the specified permissions.
    
    Args:
        permissions: List of permissions, user needs at least one
    """
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False
        
        security_manager = getattr(ctx.bot, 'security', None)
        if not security_manager:
            return False
        
        user_permissions = security_manager.get_user_permissions(ctx.author)
        
        return any(perm in user_permissions for perm in permissions)
    
    return commands.check(predicate)