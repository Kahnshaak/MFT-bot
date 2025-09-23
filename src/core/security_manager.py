"""
Security manager for authentication, authorization, and security policies.
"""

import hashlib
import hmac
import secrets
import time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum

import discord
from discord.ext import commands

from config.settings import Settings
from utils.logging_config import get_logger, LoggerMixin
from utils.exceptions import (
    PermissionDeniedError, 
    ValidationError, 
    ConfigurationError,
    RateLimitedError
)


class Permission(Enum):
    """Bot permission levels."""
    
    # Basic permissions
    VIEW_EVENTS = "view_events"
    CREATE_EVENTS = "create_events"
    MANAGE_OWN_EVENTS = "manage_own_events"
    
    # Advanced permissions
    MANAGE_ALL_EVENTS = "manage_all_events"
    MANAGE_EVENTS = "manage_events"
    MANAGE_RECURRING = "manage_recurring"
    MANAGE_USERS = "manage_users"
    
    # Administrative permissions
    CONFIGURE_BOT = "configure_bot"
    VIEW_ANALYTICS = "view_analytics"
    MANAGE_PERMISSIONS = "manage_permissions"
    
    # System permissions
    SYSTEM_ADMIN = "system_admin"


@dataclass
class RoleMapping:
    """Maps Discord roles to bot permissions."""
    
    role_id: int
    permissions: Set[Permission]
    guild_id: int


@dataclass
class RateLimitBucket:
    """Rate limiting bucket for tracking usage."""
    
    requests: List[float]
    max_requests: int
    window_seconds: int
    
    def is_rate_limited(self) -> bool:
        """Check if rate limit is exceeded."""
        now = time.time()
        # Remove old requests outside the window
        self.requests = [req_time for req_time in self.requests 
                        if now - req_time < self.window_seconds]
        
        return len(self.requests) >= self.max_requests
    
    def add_request(self) -> None:
        """Add a new request to the bucket."""
        self.requests.append(time.time())


class SecurityManager(LoggerMixin):
    """
    Centralized security management for authentication and authorization.
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self._role_mappings: Dict[int, Dict[int, RoleMapping]] = {}  # guild_id -> role_id -> mapping
        self._rate_limit_buckets: Dict[str, RateLimitBucket] = {}
        self._session_tokens: Dict[str, Dict] = {}
        self._csrf_tokens: Set[str] = set()
        
        # Default permission mappings
        self._default_permissions = {
            "everyone": {Permission.VIEW_EVENTS},
            "member": {Permission.VIEW_EVENTS, Permission.CREATE_EVENTS, Permission.MANAGE_OWN_EVENTS},
            "moderator": {
                Permission.VIEW_EVENTS, Permission.CREATE_EVENTS, 
                Permission.MANAGE_OWN_EVENTS, Permission.MANAGE_ALL_EVENTS,
                Permission.MANAGE_RECURRING, Permission.VIEW_ANALYTICS
            },
            "admin": {perm for perm in Permission}  # All permissions
        }
    
    def configure_role_mapping(
        self, 
        guild_id: int, 
        role_id: int, 
        permissions: Set[Permission]
    ) -> None:
        """
        Configure permission mapping for a Discord role.
        
        Args:
            guild_id: Discord guild ID
            role_id: Discord role ID
            permissions: Set of permissions to grant to this role
        """
        if guild_id not in self._role_mappings:
            self._role_mappings[guild_id] = {}
        
        self._role_mappings[guild_id][role_id] = RoleMapping(
            role_id=role_id,
            permissions=permissions,
            guild_id=guild_id
        )
        
        self.logger.info(
            "Configured role mapping",
            guild_id=guild_id,
            role_id=role_id,
            permissions=[p.value for p in permissions]
        )
    
    def get_user_permissions(
        self, 
        user: discord.Member, 
        guild_id: int
    ) -> Set[Permission]:
        """
        Get all permissions for a user in a guild.
        
        Args:
            user: Discord member
            guild_id: Guild ID
            
        Returns:
            Set of permissions the user has
        """
        permissions = set()
        
        # Check configured role mappings
        guild_mappings = self._role_mappings.get(guild_id, {})
        for role in user.roles:
            if role.id in guild_mappings:
                permissions.update(guild_mappings[role.id].permissions)
        
        # Apply default permissions based on Discord permissions
        if user.guild_permissions.administrator:
            permissions.update(self._default_permissions["admin"])
        elif user.guild_permissions.manage_guild or user.guild_permissions.manage_messages:
            permissions.update(self._default_permissions["moderator"])
        else:
            permissions.update(self._default_permissions["member"])
        
        # Everyone gets basic permissions
        permissions.update(self._default_permissions["everyone"])
        
        return permissions
    
    def check_permission(
        self, 
        user: discord.Member, 
        guild_id: int, 
        required_permission: Permission
    ) -> bool:
        """
        Check if a user has a specific permission.
        
        Args:
            user: Discord member
            guild_id: Guild ID
            required_permission: Permission to check
            
        Returns:
            True if user has permission, False otherwise
        """
        user_permissions = self.get_user_permissions(user, guild_id)
        return required_permission in user_permissions
    
    def require_permission(
        self, 
        user: discord.Member, 
        guild_id: int, 
        required_permission: Permission
    ) -> None:
        """
        Require a user to have a specific permission, raise exception if not.
        
        Args:
            user: Discord member
            guild_id: Guild ID
            required_permission: Permission to require
            
        Raises:
            PermissionDeniedError: If user lacks required permission
        """
        if not self.check_permission(user, guild_id, required_permission):
            self.logger.warning(
                "Permission denied",
                user_id=user.id,
                guild_id=guild_id,
                required_permission=required_permission.value,
                user_permissions=[p.value for p in self.get_user_permissions(user, guild_id)]
            )
            raise PermissionDeniedError(
                f"User lacks required permission: {required_permission.value}"
            )
    
    def check_rate_limit(
        self, 
        identifier: str, 
        max_requests: Optional[int] = None,
        window_seconds: Optional[int] = None
    ) -> None:
        """
        Check and enforce rate limits.
        
        Args:
            identifier: Unique identifier for rate limiting (user_id, ip, etc.)
            max_requests: Maximum requests per window (uses default if None)
            window_seconds: Time window in seconds (uses default if None)
            
        Raises:
            RateLimitedError: If rate limit is exceeded
        """
        max_requests = max_requests or self.settings.rate_limit_per_minute
        window_seconds = window_seconds or 60
        
        if identifier not in self._rate_limit_buckets:
            self._rate_limit_buckets[identifier] = RateLimitBucket(
                requests=[],
                max_requests=max_requests,
                window_seconds=window_seconds
            )
        
        bucket = self._rate_limit_buckets[identifier]
        
        if bucket.is_rate_limited():
            self.logger.warning(
                "Rate limit exceeded",
                identifier=identifier,
                max_requests=max_requests,
                window_seconds=window_seconds
            )
            raise RateLimitedError(
                f"Rate limit exceeded: {max_requests} requests per {window_seconds} seconds"
            )
        
        bucket.add_request()
    
    def validate_input(
        self, 
        input_data: str, 
        max_length: int = 2000,
        min_length: int = 1,
        forbidden_patterns: Optional[List[str]] = None,
        forbidden_chars: Optional[List[str]] = None
    ) -> str:
        """
        Validate and sanitize user input.
        
        Args:
            input_data: Input string to validate
            max_length: Maximum allowed length
            min_length: Minimum required length
            forbidden_patterns: List of forbidden regex patterns
            forbidden_chars: List of forbidden characters
            
        Returns:
            Sanitized input string
            
        Raises:
            ValidationError: If input fails validation
        """
        if not isinstance(input_data, str):
            raise ValidationError("Input must be a string")
        
        # Length validation
        if len(input_data) < min_length:
            raise ValidationError(f"Input too short (minimum {min_length} characters)")
        
        if len(input_data) > max_length:
            raise ValidationError(f"Input too long (maximum {max_length} characters)")
        
        # Check forbidden characters
        if forbidden_chars:
            for char in forbidden_chars:
                if char in input_data:
                    raise ValidationError(f"Input contains forbidden character: {char}")
        
        # Check forbidden patterns
        if forbidden_patterns:
            import re
            for pattern in forbidden_patterns:
                if re.search(pattern, input_data, re.IGNORECASE):
                    raise ValidationError(f"Input contains forbidden pattern")
        
        # Basic sanitization
        sanitized = input_data.strip()
        
        # Remove potential Discord mentions that could cause issues
        sanitized = sanitized.replace('@everyone', '@\u200beveryone')
        sanitized = sanitized.replace('@here', '@\u200bhere')
        
        return sanitized
    
    def generate_csrf_token(self) -> str:
        """Generate a CSRF token for web requests."""
        token = secrets.token_urlsafe(32)
        self._csrf_tokens.add(token)
        return token
    
    def validate_csrf_token(self, token: str) -> bool:
        """Validate a CSRF token."""
        return token in self._csrf_tokens
    
    def consume_csrf_token(self, token: str) -> bool:
        """Validate and consume a CSRF token (one-time use)."""
        if token in self._csrf_tokens:
            self._csrf_tokens.remove(token)
            return True
        return False
    
    def create_session_token(
        self, 
        user_id: str, 
        guild_id: Optional[str] = None,
        expires_in: int = 3600
    ) -> str:
        """
        Create a session token for web authentication.
        
        Args:
            user_id: Discord user ID
            guild_id: Optional guild ID for guild-specific sessions
            expires_in: Token expiration time in seconds
            
        Returns:
            Session token
        """
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + expires_in
        
        self._session_tokens[token] = {
            "user_id": user_id,
            "guild_id": guild_id,
            "expires_at": expires_at,
            "created_at": time.time()
        }
        
        return token
    
    def validate_session_token(self, token: str) -> Optional[Dict]:
        """
        Validate a session token.
        
        Args:
            token: Session token to validate
            
        Returns:
            Session data if valid, None otherwise
        """
        if token not in self._session_tokens:
            return None
        
        session = self._session_tokens[token]
        
        # Check expiration
        if time.time() > session["expires_at"]:
            del self._session_tokens[token]
            return None
        
        return session
    
    def revoke_session_token(self, token: str) -> bool:
        """
        Revoke a session token.
        
        Args:
            token: Token to revoke
            
        Returns:
            True if token was found and revoked, False otherwise
        """
        if token in self._session_tokens:
            del self._session_tokens[token]
            return True
        return False
    
    def cleanup_expired_tokens(self) -> None:
        """Clean up expired session tokens."""
        now = time.time()
        expired_tokens = [
            token for token, session in self._session_tokens.items()
            if now > session["expires_at"]
        ]
        
        for token in expired_tokens:
            del self._session_tokens[token]
        
        if expired_tokens:
            self.logger.debug(
                "Cleaned up expired tokens",
                count=len(expired_tokens)
            )