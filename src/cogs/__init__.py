"""
Cogs package for the Discord Game Night Bot.

This package contains all Discord bot cogs (command modules).
Individual cogs are loaded by the bot as needed.
"""

# Import cogs for easier access
from .events import EventsCog

__all__ = ['EventsCog']
