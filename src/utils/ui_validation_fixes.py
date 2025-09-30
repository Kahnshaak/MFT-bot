"""
Discord UI Validation and Fixes

This module contains fixes and improvements for Discord UI components
based on the audit findings.
"""

import discord
from discord.ext import commands
from typing import Dict, List, Optional, Any
from datetime import datetime


class ImprovedEmbedBuilder:
    """Builder for creating consistent, well-formatted embeds."""
    
    # Consistent color scheme
    COLORS = {
        'primary': discord.Color.blue(),
        'success': discord.Color.green(), 
        'warning': discord.Color.orange(),
        'error': discord.Color.red(),
        'info': discord.Color.blurple(),
        'secondary': discord.Color.greyple()
    }
    
    @classmethod
    def create_event_embed(cls, event, state_color: str = 'primary') -> discord.Embed:
        """Create a properly formatted event embed."""
        embed = discord.Embed(
            title=f"🎮 {cls._truncate_text(event.title, 250)}",
            description=cls._truncate_text(event.description or "No description provided", 4000),
            color=cls.COLORS.get(state_color, cls.COLORS['primary']),
            timestamp=datetime.utcnow()
        )
        
        # Add state indicator
        state_emojis = {
            'DRAFT': '📝',
            'DATE_POLLING': '📅',
            'TIME_POLLING': '⏰', 
            'GAME_POLLING': '🎮',
            'SCHEDULED': '✅',
            'COMPLETED': '🏁',
            'CANCELLED': '❌'
        }
        
        state_emoji = state_emojis.get(event.state.value, '📊')
        embed.add_field(
            name="Status",
            value=f"{state_emoji} {event.state.value.replace('_', ' ').title()}",
            inline=True
        )
        
        # Add creator info
        embed.add_field(
            name="Created By",
            value=f"<@{event.creator_id}>",
            inline=True
        )
        
        # Add schedule info if available
        if hasattr(event, 'schedule') and event.schedule:
            schedule_text = []
            
            # Handle both dict and object schedule formats
            if isinstance(event.schedule, dict):
                if event.schedule.get('selected_date'):
                    schedule_text.append(f"📅 {event.schedule['selected_date']}")
                if event.schedule.get('selected_time'):
                    schedule_text.append(f"⏰ {event.schedule['selected_time']}")
            else:
                # Handle object format
                if hasattr(event.schedule, 'selected_date') and event.schedule.selected_date:
                    schedule_text.append(f"📅 {event.schedule.selected_date}")
                if hasattr(event.schedule, 'selected_time') and event.schedule.selected_time:
                    schedule_text.append(f"⏰ {event.schedule.selected_time}")
            
            if schedule_text:
                embed.add_field(
                    name="Schedule",
                    value="\n".join(schedule_text),
                    inline=False
                )
        
        # Add RSVP count if available
        if hasattr(event, 'rsvp_data') and event.rsvp_data:
            try:
                if isinstance(event.rsvp_data, dict):
                    yes_count = len([r for r in event.rsvp_data.values() if r.get('status') == 'YES'])
                    maybe_count = len([r for r in event.rsvp_data.values() if r.get('status') == 'MAYBE'])
                    no_count = len([r for r in event.rsvp_data.values() if r.get('status') == 'NO'])
                else:
                    # Handle other formats
                    yes_count = maybe_count = no_count = 0
                
                embed.add_field(
                    name="RSVPs",
                    value=f"✅ {yes_count} • ❓ {maybe_count} • ❌ {no_count}",
                    inline=True
                )
            except Exception:
                # Skip RSVP display if there's an error
                pass
        
        embed.set_footer(text="Game Night Bot • Use buttons below to interact")
        return embed
    
    @classmethod
    def create_poll_embed(cls, poll, event, show_analytics: bool = False) -> discord.Embed:
        """Create a properly formatted poll embed."""
        poll_type_info = {
            'DATE': {'emoji': '📅', 'color': 'primary'},
            'TIME': {'emoji': '⏰', 'color': 'info'},
            'GAME': {'emoji': '🎮', 'color': 'success'}
        }
        
        info = poll_type_info.get(poll.poll_type.value, {'emoji': '📊', 'color': 'secondary'})
        
        embed = discord.Embed(
            title=f"{info['emoji']} {cls._truncate_text(poll.title, 250)}",
            description=cls._truncate_text(poll.description or f"Vote for your preferred {poll.poll_type.value.lower()}!", 4000),
            color=cls.COLORS[info['color']],
            timestamp=datetime.utcnow()
        )
        
        # Add poll options with vote counts
        if poll.options:
            options_text = []
            total_votes = sum(len(option.votes) for option in poll.options)
            
            for i, option in enumerate(poll.options[:20]):  # Limit for embed field
                vote_count = len(option.votes)
                percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0
                
                # Create progress bar
                bar_length = 10
                filled = int(percentage / 10)
                bar = "█" * filled + "░" * (bar_length - filled)
                
                options_text.append(
                    f"**{i+1}.** {cls._truncate_text(option.label, 80)}\n"
                    f"`{bar}` {vote_count} votes ({percentage:.1f}%)"
                )
            
            # Split into multiple fields if too long
            options_str = "\n\n".join(options_text)
            if len(options_str) > 1000:
                # Split into multiple fields
                mid_point = len(options_text) // 2
                
                embed.add_field(
                    name="Options (1/2)",
                    value="\n\n".join(options_text[:mid_point]),
                    inline=False
                )
                embed.add_field(
                    name="Options (2/2)", 
                    value="\n\n".join(options_text[mid_point:]),
                    inline=False
                )
            else:
                embed.add_field(
                    name="Options",
                    value=options_str or "No options available",
                    inline=False
                )
        
        # Add poll status
        status_text = []
        if poll.is_active:
            status_text.append("🟢 **Active** - Voting is open")
        else:
            status_text.append("🔴 **Closed** - Voting has ended")
        
        if hasattr(poll, 'closes_at') and poll.closes_at:
            status_text.append(f"⏰ Closes: <t:{int(poll.closes_at.timestamp())}:R>")
        
        embed.add_field(
            name="Poll Status",
            value="\n".join(status_text),
            inline=True
        )
        
        # Add participation stats
        if show_analytics and poll.options:
            total_participants = len(set().union(*[option.votes for option in poll.options]))
            embed.add_field(
                name="Participation",
                value=f"👥 {total_participants} participants\n📊 {total_votes} total votes",
                inline=True
            )
        
        embed.set_footer(text=f"Event: {event.title} • Use buttons/dropdown to vote")
        return embed
    
    @classmethod
    def create_user_profile_embed(cls, user, discord_user) -> discord.Embed:
        """Create a properly formatted user profile embed."""
        embed = discord.Embed(
            title=f"🎮 {cls._truncate_text(discord_user.display_name, 250)}'s Profile",
            color=cls.COLORS['info'],
            timestamp=datetime.utcnow()
        )
        
        embed.set_thumbnail(url=discord_user.display_avatar.url)
        
        # Basic info
        embed.add_field(
            name="Timezone",
            value=f"🌍 {user.timezone}",
            inline=True
        )
        
        # Game interests
        if user.game_interests:
            interests_text = []
            for interest in user.game_interests[:10]:  # Limit display
                try:
                    # Handle both dict and object formats
                    if isinstance(interest, dict):
                        level = interest.get('interest_level', 5)
                        game_name = interest.get('game_name', 'Unknown Game')
                    else:
                        # Handle object format
                        level = getattr(interest, 'interest_level', 5)
                        game_name = getattr(interest, 'game_name', 'Unknown Game')
                    
                    stars = "⭐" * min(level // 2, 5)  # Convert to star rating
                    interests_text.append(f"{stars} {game_name}")
                except Exception:
                    # Skip malformed interests
                    continue
            
            if len(user.game_interests) > 10:
                interests_text.append(f"... and {len(user.game_interests) - 10} more")
            
            embed.add_field(
                name=f"Game Interests ({len(user.game_interests)})",
                value="\n".join(interests_text) or "None",
                inline=False
            )
        
        # Availability summary
        if hasattr(user, 'availability') and user.availability:
            available_days = len(user.availability)
            embed.add_field(
                name="Availability",
                value=f"📅 Available {available_days} days/week",
                inline=True
            )
        
        # Notification preferences
        if hasattr(user, 'notification_preferences') and user.notification_preferences:
            prefs = user.notification_preferences
            embed.add_field(
                name="Notifications",
                value=f"📱 {prefs.channel.value} • ⏰ {prefs.reminder_timing.value.replace('_', ' ').title()}",
                inline=True
            )
        
        # Statistics
        if hasattr(user, 'statistics') and user.statistics:
            stats = user.statistics
            embed.add_field(
                name="Statistics",
                value=(
                    f"🎯 {stats.events_attended} events attended\n"
                    f"📊 {stats.attendance_rate:.1%} attendance rate\n"
                    f"🎮 {len(stats.favorite_games)} favorite games"
                ),
                inline=False
            )
        
        embed.set_footer(text="Use buttons below to manage your profile")
        return embed
    
    @classmethod
    def create_error_embed(cls, title: str, description: str, error_type: str = 'error') -> discord.Embed:
        """Create a properly formatted error embed."""
        color_map = {
            'error': cls.COLORS['error'],
            'warning': cls.COLORS['warning'],
            'info': cls.COLORS['info']
        }
        
        embed = discord.Embed(
            title=f"❌ {cls._truncate_text(title, 250)}",
            description=cls._truncate_text(description, 4000),
            color=color_map.get(error_type, cls.COLORS['error']),
            timestamp=datetime.utcnow()
        )
        
        embed.set_footer(text="If this error persists, please contact an administrator")
        return embed
    
    @classmethod
    def create_success_embed(cls, title: str, description: str) -> discord.Embed:
        """Create a properly formatted success embed."""
        embed = discord.Embed(
            title=f"✅ {cls._truncate_text(title, 250)}",
            description=cls._truncate_text(description, 4000),
            color=cls.COLORS['success'],
            timestamp=datetime.utcnow()
        )
        
        return embed
    
    @classmethod
    def _truncate_text(cls, text: str, max_length: int) -> str:
        """Safely truncate text to fit Discord limits."""
        if not text:
            return ""
        
        if len(text) <= max_length:
            return text
        
        # Truncate and add ellipsis
        return text[:max_length - 3] + "..."


class ImprovedButtonBuilder:
    """Builder for creating consistent, well-formatted buttons."""
    
    @classmethod
    def create_event_management_buttons(cls, event_state: str) -> List[discord.ui.Button]:
        """Create appropriate buttons based on event state."""
        buttons = []
        
        if event_state == 'DRAFT':
            buttons.append(discord.ui.Button(
                label="Start Date Poll",
                style=discord.ButtonStyle.primary,
                emoji="📅",
                custom_id="start_date_poll"
            ))
        elif event_state == 'DATE_POLLING':
            buttons.append(discord.ui.Button(
                label="Close Date Poll",
                style=discord.ButtonStyle.success,
                emoji="✅",
                custom_id="close_date_poll"
            ))
        elif event_state == 'TIME_POLLING':
            buttons.append(discord.ui.Button(
                label="Close Time Poll",
                style=discord.ButtonStyle.success,
                emoji="⏰",
                custom_id="close_time_poll"
            ))
        elif event_state == 'GAME_POLLING':
            buttons.append(discord.ui.Button(
                label="Close Game Poll",
                style=discord.ButtonStyle.success,
                emoji="🎮",
                custom_id="close_game_poll"
            ))
        
        # Always add RSVP and cancel for active events
        if event_state in ['SCHEDULED', 'DATE_POLLING', 'TIME_POLLING', 'GAME_POLLING']:
            buttons.append(discord.ui.Button(
                label="RSVP",
                style=discord.ButtonStyle.secondary,
                emoji="✋",
                custom_id="rsvp_event"
            ))
        
        # Always add cancel option for non-completed events
        if event_state not in ['COMPLETED', 'CANCELLED']:
            buttons.append(discord.ui.Button(
                label="Cancel Event",
                style=discord.ButtonStyle.danger,
                emoji="❌",
                custom_id="cancel_event"
            ))
        
        return buttons
    
    @classmethod
    def create_poll_management_buttons(cls) -> List[discord.ui.Button]:
        """Create poll management buttons."""
        return [
            discord.ui.Button(
                label="Extend Poll",
                style=discord.ButtonStyle.secondary,
                emoji="⏰",
                custom_id="extend_poll"
            ),
            discord.ui.Button(
                label="Close Poll",
                style=discord.ButtonStyle.danger,
                emoji="🔒",
                custom_id="close_poll"
            )
        ]


class ImprovedModalBuilder:
    """Builder for creating consistent, well-formatted modals."""
    
    @classmethod
    def create_event_creation_modal(cls) -> discord.ui.Modal:
        """Create an improved event creation modal."""
        modal = discord.ui.Modal(title="Create Game Night Event")
        
        # Event title input
        title_input = discord.ui.TextInput(
            label="Event Title",
            placeholder="Enter a descriptive title (e.g., 'Friday Night Gaming')",
            min_length=3,
            max_length=100,
            required=True
        )
        modal.add_item(title_input)
        
        # Event description input
        description_input = discord.ui.TextInput(
            label="Description (Optional)",
            placeholder="Describe your event, special rules, or requirements...",
            style=discord.TextStyle.paragraph,
            max_length=2000,
            required=False
        )
        modal.add_item(description_input)
        
        return modal
    
    @classmethod
    def create_timezone_modal(cls, current_timezone: str = "UTC") -> discord.ui.Modal:
        """Create an improved timezone setting modal."""
        modal = discord.ui.Modal(title="Set Your Timezone")
        
        timezone_input = discord.ui.TextInput(
            label="Timezone",
            placeholder="e.g., America/New_York, Europe/London, UTC",
            default=current_timezone,
            min_length=3,
            max_length=50,
            required=True
        )
        modal.add_item(timezone_input)
        
        # Add help text
        help_input = discord.ui.TextInput(
            label="Need Help?",
            default="Visit: en.wikipedia.org/wiki/List_of_tz_database_time_zones",
            style=discord.TextStyle.short,
            required=False
        )
        help_input.disabled = True
        modal.add_item(help_input)
        
        return modal


def validate_command_descriptions() -> Dict[str, List[str]]:
    """Validate and return improved command descriptions."""
    return {
        # Events commands
        "event": "Create a new game night event with interactive polls",
        "events": "List all active events in this server",
        "event-manage": "Manage a specific event (admin only)",
        "calendar": "Export upcoming events to calendar file (.ics)",
        "sync-rsvps": "Manually sync RSVPs from Discord scheduled event",
        "retry-discord-event": "Retry creating Discord scheduled event",
        "poll-extend": "Extend voting time for an active poll",
        "poll-analytics": "View detailed analytics for a poll",
        
        # Users commands  
        "profile": "View and manage your user profile and preferences",
        "stats": "View your game night participation statistics",
        "timezone": "Set your timezone for accurate event times",
        "availability": "Manage your weekly availability schedule",
        "notifications": "Configure when and how you receive notifications",
        
        # Games commands
        "games-add": "Add a game to your interest list with rating",
        "games-remove": "Remove a game from your interest list", 
        "games-list": "View all games you're interested in",
        "games-ping": "Notify users interested in a specific game",
        "games-popular": "Show the most popular games in this server",
        "games-trending": "Show games gaining popularity recently",
        "games-search": "Search for games by name with fuzzy matching",
        "games-manage": "Manage game metadata and aliases (admin only)",
        "games-limits": "Configure notification frequency limits per game"
    }


def validate_parameter_descriptions() -> Dict[str, Dict[str, str]]:
    """Validate and return improved parameter descriptions."""
    return {
        "games-add": {
            "game_name": "Name of the game you want to be notified about",
            "interest_level": "Your interest level from 1 (low) to 10 (high)"
        },
        "games-remove": {
            "game_name": "Name of the game to remove from your interests"
        },
        "games-ping": {
            "game_name": "Name of the game to ping interested users about"
        },
        "games-popular": {
            "limit": "Maximum number of games to show (1-25, default: 10)"
        },
        "games-trending": {
            "limit": "Maximum number of games to show (1-25, default: 10)"
        },
        "games-search": {
            "query": "Search term to find games (supports partial matches)"
        },
        "games-manage": {
            "game_name": "Name of the game to manage metadata for"
        },
        "games-limits": {
            "game_name": "Game to configure notification limits for",
            "max_per_day": "Maximum pings per day (1-10, default: 3)",
            "max_per_week": "Maximum pings per week (1-50, default: 15)"
        },
        "timezone": {
            "timezone": "Your timezone (e.g., America/New_York, Europe/London)"
        },
        "event-manage": {
            "event_id": "ID of the event to manage (from /events list)"
        },
        "calendar": {
            "days_ahead": "Number of days to include (1-90, default: 30)",
            "format": "Calendar format: ics or json (default: ics)"
        },
        "sync-rsvps": {
            "event_id": "ID of the event to sync RSVPs for"
        },
        "retry-discord-event": {
            "event_id": "ID of the event to retry Discord integration for"
        },
        "poll-extend": {
            "event_id": "ID of the event with the poll to extend",
            "poll_type": "Type of poll: date, time, or game",
            "minutes": "Minutes to extend (5-60, default: 15)"
        },
        "poll-analytics": {
            "event_id": "ID of the event to view poll analytics for",
            "poll_type": "Type of poll: date, time, or game"
        }
    }