"""
Timestamps cog for timezone conversion and Discord timestamp utilities.
"""

import re
from datetime import datetime, timedelta, time
from typing import Optional, List, Dict, Any, Tuple
from zoneinfo import ZoneInfo, available_timezones
import pytz

import discord
from discord.ext import commands
try:
    from discord import app_commands
except ImportError:
    # Fallback for older discord.py versions
    app_commands = None

from core.event_bus import EventBus, EventType
from core.permission_decorators import require_permission
from core.security_manager import Permission
from core.validation_manager import ValidationManager
from utils.exceptions import ValidationError, PermissionDeniedError, ErrorCode
from utils.logging_config import get_logger, LoggerMixin


class TimestampFormat(discord.Enum):
    """Discord timestamp format options."""
    SHORT_TIME = "t"
    LONG_TIME = "T"
    SHORT_DATE = "d"
    LONG_DATE = "D"
    SHORT_DATETIME = "f"
    LONG_DATETIME = "F"
    RELATIVE = "R"


class TimezoneModal(discord.ui.Modal):
    """Modal for timezone lookup and information."""
    
    def __init__(self, cog: 'TimestampsCog'):
        super().__init__(title="Timezone Lookup")
        self.cog = cog
        
        self.timezone_input = discord.ui.TextInput(
            label="Timezone",
            placeholder="e.g., America/New_York, Europe/London, PST, EST",
            min_length=2,
            max_length=50,
            required=True
        )
        self.add_item(self.timezone_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle timezone lookup."""
        try:
            timezone_query = self.timezone_input.value.strip()
            
            # Find matching timezone
            timezone_info = await self.cog.lookup_timezone(timezone_query)
            
            if not timezone_info:
                await interaction.response.send_message(
                    f"❌ Could not find timezone: `{timezone_query}`\n"
                    f"Try using full timezone names like `America/New_York` or common abbreviations like `EST`.",
                    ephemeral=True
                )
                return
            
            # Create timezone info embed
            embed = self.cog.create_timezone_info_embed(timezone_info)
            
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            
        except Exception as e:
            self.cog.logger.error(f"Error in timezone lookup: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while looking up the timezone.",
                ephemeral=True
            )


class TimeConversionView(discord.ui.View):
    """View for interactive time conversion."""
    
    def __init__(self, cog: 'TimestampsCog', original_time: datetime, from_tz: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_time = original_time
        self.from_tz = from_tz
    
    @discord.ui.button(label="Convert to Other Timezone", style=discord.ButtonStyle.primary, emoji="🌍")
    async def convert_timezone(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open timezone conversion modal."""
        modal = TimezoneConversionModal(self.cog, self.original_time, self.from_tz)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Show All Formats", style=discord.ButtonStyle.secondary, emoji="📅")
    async def show_all_formats(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show all Discord timestamp formats."""
        embed = self.cog.create_timestamp_formats_embed(self.original_time)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TimezoneConversionModal(discord.ui.Modal):
    """Modal for converting time to another timezone."""
    
    def __init__(self, cog: 'TimestampsCog', original_time: datetime, from_tz: str):
        super().__init__(title="Convert to Timezone")
        self.cog = cog
        self.original_time = original_time
        self.from_tz = from_tz
        
        self.target_timezone_input = discord.ui.TextInput(
            label="Target Timezone",
            placeholder="e.g., America/Los_Angeles, Europe/Paris, JST",
            min_length=2,
            max_length=50,
            required=True
        )
        self.add_item(self.target_timezone_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle timezone conversion."""
        try:
            target_tz_query = self.target_timezone_input.value.strip()
            
            # Resolve target timezone
            target_tz_info = await self.cog.lookup_timezone(target_tz_query)
            
            if not target_tz_info:
                await interaction.response.send_message(
                    f"❌ Could not find timezone: `{target_tz_query}`",
                    ephemeral=True
                )
                return
            
            # Convert time
            converted_time = self.cog.convert_time_to_timezone(
                self.original_time, 
                self.from_tz, 
                target_tz_info['name']
            )
            
            # Create conversion result embed
            embed = self.cog.create_conversion_result_embed(
                self.original_time,
                self.from_tz,
                converted_time,
                target_tz_info['name']
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.cog.logger.error(f"Error in timezone conversion: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while converting the timezone.",
                ephemeral=True
            )


class TimestampsCog(commands.Cog, LoggerMixin):
    """
    Timestamps cog for timezone conversion and Discord timestamp utilities.
    
    Provides commands for:
    - Converting times between timezones
    - Generating Discord timestamp formats
    - Parsing natural language time input
    - Timezone lookup and information
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.validation: ValidationManager = bot.validation
        self.event_bus: EventBus = bot.event_bus
        
        # Timezone aliases for common abbreviations
        self.timezone_aliases = {
            # US Timezones
            'EST': 'America/New_York',
            'EDT': 'America/New_York',
            'CST': 'America/Chicago',
            'CDT': 'America/Chicago',
            'MST': 'America/Denver',
            'MDT': 'America/Denver',
            'PST': 'America/Los_Angeles',
            'PDT': 'America/Los_Angeles',
            'AKST': 'America/Anchorage',
            'AKDT': 'America/Anchorage',
            'HST': 'Pacific/Honolulu',
            
            # European Timezones
            'GMT': 'Europe/London',
            'BST': 'Europe/London',
            'CET': 'Europe/Paris',
            'CEST': 'Europe/Paris',
            'EET': 'Europe/Helsinki',
            'EEST': 'Europe/Helsinki',
            
            # Asian Timezones
            'JST': 'Asia/Tokyo',
            'KST': 'Asia/Seoul',
            'CST_CHINA': 'Asia/Shanghai',
            'IST': 'Asia/Kolkata',
            
            # Australian Timezones
            'AEST': 'Australia/Sydney',
            'AEDT': 'Australia/Sydney',
            'ACST': 'Australia/Adelaide',
            'ACDT': 'Australia/Adelaide',
            'AWST': 'Australia/Perth',
            
            # Other common
            'UTC': 'UTC',
            'GMT': 'UTC',
        }
        
        # Natural language patterns for time parsing
        self.time_patterns = [
            # Absolute times
            (r'(\d{1,2}):(\d{2})\s*(am|pm)?', self._parse_time_hm),
            (r'(\d{1,2})\s*(am|pm)', self._parse_time_h),
            (r'(\d{1,2}):(\d{2}):(\d{2})', self._parse_time_hms),
            
            # Relative times
            (r'in\s+(\d+)\s+(minute|minutes|min|mins)', self._parse_relative_minutes),
            (r'in\s+(\d+)\s+(hour|hours|hr|hrs)', self._parse_relative_hours),
            (r'in\s+(\d+)\s+(day|days)', self._parse_relative_days),
            
            # Named times
            (r'\b(noon|midday)\b', self._parse_noon),
            (r'\bmidnight\b', self._parse_midnight),
            (r'\bmorning\b', self._parse_morning),
            (r'\bafternoon\b', self._parse_afternoon),
            (r'\bevening\b', self._parse_evening),
            (r'\bnight\b', self._parse_night),
        ]
        
        # Date patterns
        self.date_patterns = [
            # Relative dates
            (r'today', self._parse_today),
            (r'tomorrow', self._parse_tomorrow),
            (r'yesterday', self._parse_yesterday),
            (r'next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)', self._parse_next_weekday),
            (r'this\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)', self._parse_this_weekday),
            
            # Absolute dates
            (r'(\d{1,2})/(\d{1,2})/(\d{4})', self._parse_date_mdy),
            (r'(\d{4})-(\d{1,2})-(\d{1,2})', self._parse_date_ymd),
            (r'(\d{1,2})-(\d{1,2})-(\d{4})', self._parse_date_dmy),
        ]
    
    @commands.slash_command(
        name="time-convert",
        description="Convert time between timezones"
    )
    async def convert_time(
        self, 
        interaction: discord.Interaction,
        time_input: str,
        from_timezone: str,
        to_timezone: Optional[str] = None
    ):
        """Convert time between timezones."""
        try:
            # Parse the time input
            parsed_time = await self.parse_time_input(time_input)
            if not parsed_time:
                await interaction.response.send_message(
                    f"❌ Could not parse time: `{time_input}`\n"
                    f"Try formats like: `2:30 PM`, `14:30`, `tomorrow at 8pm`, `next friday 7pm`",
                    ephemeral=True
                )
                return
            
            # Resolve source timezone
            from_tz_info = await self.lookup_timezone(from_timezone)
            if not from_tz_info:
                await interaction.response.send_message(
                    f"❌ Could not find source timezone: `{from_timezone}`",
                    ephemeral=True
                )
                return
            
            # Localize the parsed time to the source timezone
            source_tz = ZoneInfo(from_tz_info['name'])
            localized_time = parsed_time.replace(tzinfo=source_tz)
            
            if to_timezone:
                # Convert to specific timezone
                to_tz_info = await self.lookup_timezone(to_timezone)
                if not to_tz_info:
                    await interaction.response.send_message(
                        f"❌ Could not find target timezone: `{to_timezone}`",
                        ephemeral=True
                    )
                    return
                
                converted_time = self.convert_time_to_timezone(
                    localized_time, 
                    from_tz_info['name'], 
                    to_tz_info['name']
                )
                
                embed = self.create_conversion_result_embed(
                    localized_time,
                    from_tz_info['name'],
                    converted_time,
                    to_tz_info['name']
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                # Show conversions to multiple common timezones
                embed = self.create_multi_timezone_embed(localized_time, from_tz_info['name'])
                view = TimeConversionView(self, localized_time, from_tz_info['name'])
                
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in time conversion: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while converting the time.",
                ephemeral=True
            )
    
    @commands.slash_command(
        name="time-zone",
        description="Look up timezone information"
    )
    async def timezone_info(self, interaction: discord.Interaction, timezone: str):
        """Look up timezone information."""
        try:
            timezone_info = await self.lookup_timezone(timezone)
            
            if not timezone_info:
                # Show suggestions for partial matches
                suggestions = self.find_timezone_suggestions(timezone)
                
                embed = discord.Embed(
                    title="❌ Timezone Not Found",
                    description=f"Could not find timezone: `{timezone}`",
                    color=discord.Color.red()
                )
                
                if suggestions:
                    embed.add_field(
                        name="Did you mean?",
                        value="\n".join(f"• `{tz}`" for tz in suggestions[:10]),
                        inline=False
                    )
                
                embed.add_field(
                    name="💡 Tips",
                    value=(
                        "• Use full names: `America/New_York`, `Europe/London`\n"
                        "• Try abbreviations: `EST`, `PST`, `GMT`\n"
                        "• Use `/time zone` without arguments to browse"
                    ),
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            embed = self.create_timezone_info_embed(timezone_info)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in timezone lookup: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while looking up the timezone.",
                ephemeral=True
            )
    
    @commands.slash_command(
        name="time-format",
        description="Generate Discord timestamp formats"
    )
    async def format_timestamp(
        self, 
        interaction: discord.Interaction,
        time_input: str,
        timezone: Optional[str] = "UTC",
        format_type: Optional[TimestampFormat] = None
    ):
        """Generate Discord timestamp formats."""
        try:
            # Parse the time input
            parsed_time = await self.parse_time_input(time_input)
            if not parsed_time:
                await interaction.response.send_message(
                    f"❌ Could not parse time: `{time_input}`\n"
                    f"Try formats like: `2:30 PM`, `tomorrow at 8pm`, `2024-01-15 14:30`",
                    ephemeral=True
                )
                return
            
            # Resolve timezone
            tz_info = await self.lookup_timezone(timezone)
            if not tz_info:
                await interaction.response.send_message(
                    f"❌ Could not find timezone: `{timezone}`",
                    ephemeral=True
                )
                return
            
            # Localize the time
            tz = ZoneInfo(tz_info['name'])
            localized_time = parsed_time.replace(tzinfo=tz)
            
            if format_type:
                # Generate specific format
                timestamp = int(localized_time.timestamp())
                discord_format = f"<t:{timestamp}:{format_type.value}>"
                
                embed = discord.Embed(
                    title="🕒 Discord Timestamp",
                    color=discord.Color.blue()
                )
                
                embed.add_field(
                    name="Input",
                    value=f"`{time_input}` in `{tz_info['name']}`",
                    inline=False
                )
                
                embed.add_field(
                    name="Discord Format",
                    value=f"`{discord_format}`",
                    inline=False
                )
                
                embed.add_field(
                    name="Preview",
                    value=discord_format,
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                # Show all formats
                embed = self.create_timestamp_formats_embed(localized_time)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in timestamp formatting: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while formatting the timestamp.",
                ephemeral=True
            )
    
    @commands.slash_command(
        name="time-now",
        description="Show current time in multiple timezones"
    )
    async def current_time(self, interaction: discord.Interaction):
        """Show current time in multiple timezones."""
        try:
            now = datetime.now(ZoneInfo("UTC"))
            
            embed = discord.Embed(
                title="🌍 Current Time Around the World",
                color=discord.Color.green(),
                timestamp=now
            )
            
            # Common timezones to display
            common_timezones = [
                ("UTC", "UTC"),
                ("New York", "America/New_York"),
                ("Los Angeles", "America/Los_Angeles"),
                ("London", "Europe/London"),
                ("Paris", "Europe/Paris"),
                ("Tokyo", "Asia/Tokyo"),
                ("Sydney", "Australia/Sydney"),
            ]
            
            for display_name, tz_name in common_timezones:
                try:
                    tz = ZoneInfo(tz_name)
                    local_time = now.astimezone(tz)
                    
                    # Get timezone abbreviation
                    abbr = local_time.strftime('%Z')
                    
                    embed.add_field(
                        name=f"{display_name} ({abbr})",
                        value=f"`{local_time.strftime('%Y-%m-%d %H:%M:%S')}`",
                        inline=True
                    )
                except Exception:
                    continue
            
            # Add Discord timestamp
            timestamp = int(now.timestamp())
            embed.add_field(
                name="Discord Timestamp",
                value=f"<t:{timestamp}:F>",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error showing current time: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while getting current time.",
                ephemeral=True
            )
    
    # Helper methods
    
    async def parse_time_input(self, time_input: str) -> Optional[datetime]:
        """Parse natural language time input into datetime."""
        time_input = time_input.lower().strip()
        
        # Try to parse as complete datetime first
        complete_datetime = self._parse_complete_datetime(time_input)
        if complete_datetime:
            return complete_datetime
        
        # Parse date and time separately
        parsed_date = None
        parsed_time = None
        
        # Extract date information
        for pattern, parser in self.date_patterns:
            match = re.search(pattern, time_input, re.IGNORECASE)
            if match:
                try:
                    parsed_date = parser(match)
                    break
                except Exception:
                    continue
        
        # Extract time information
        for pattern, parser in self.time_patterns:
            match = re.search(pattern, time_input, re.IGNORECASE)
            if match:
                try:
                    parsed_time = parser(match)
                    break
                except Exception:
                    continue
        
        # Combine date and time
        if parsed_date and parsed_time:
            if isinstance(parsed_time, datetime):
                # If parsed_time is a datetime, use its time component
                return datetime.combine(parsed_date.date(), parsed_time.time())
            else:
                return datetime.combine(parsed_date.date(), parsed_time)
        elif parsed_date:
            return parsed_date
        elif parsed_time:
            if isinstance(parsed_time, datetime):
                # If parsed_time is already a datetime, return it directly
                return parsed_time
            else:
                # Use today's date with the parsed time
                today = datetime.now().date()
                return datetime.combine(today, parsed_time)
        
        return None
    
    def _parse_complete_datetime(self, time_input: str) -> Optional[datetime]:
        """Parse complete datetime strings."""
        # ISO format
        iso_patterns = [
            r'(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{1,2}):(\d{1,2})',
            r'(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{1,2})',
            r'(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{1,2})\s*(am|pm)?',
        ]
        
        for pattern in iso_patterns:
            match = re.match(pattern, time_input, re.IGNORECASE)
            if match:
                try:
                    groups = match.groups()
                    if len(groups) >= 5:
                        if pattern.startswith(r'(\d{4})'):  # YYYY-MM-DD format
                            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                            hour, minute = int(groups[3]), int(groups[4])
                            second = int(groups[5]) if len(groups) > 5 and groups[5] else 0
                        else:  # MM/DD/YYYY format
                            month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
                            hour, minute = int(groups[3]), int(groups[4])
                            second = 0
                            
                            # Handle AM/PM
                            if len(groups) > 5 and groups[5]:
                                if groups[5].lower() == 'pm' and hour != 12:
                                    hour += 12
                                elif groups[5].lower() == 'am' and hour == 12:
                                    hour = 0
                        
                        return datetime(year, month, day, hour, minute, second)
                except Exception:
                    continue
        
        return None
    
    async def lookup_timezone(self, timezone_query: str) -> Optional[Dict[str, Any]]:
        """Look up timezone information."""
        timezone_query = timezone_query.strip()
        
        # Reject empty queries
        if not timezone_query:
            return None
        
        # Check aliases first
        if timezone_query.upper() in self.timezone_aliases:
            timezone_name = self.timezone_aliases[timezone_query.upper()]
        else:
            timezone_name = timezone_query
        
        # Validate timezone
        try:
            tz = ZoneInfo(timezone_name)
            now = datetime.now(tz)
            
            return {
                'name': timezone_name,
                'abbreviation': now.strftime('%Z'),
                'offset': now.strftime('%z'),
                'current_time': now,
                'is_dst': bool(now.dst()),
                'query': timezone_query
            }
        except Exception:
            # Try fuzzy matching
            return self._fuzzy_match_timezone(timezone_query)
    
    def _fuzzy_match_timezone(self, query: str) -> Optional[Dict[str, Any]]:
        """Attempt fuzzy matching for timezone names."""
        if not query or len(query) < 2:
            return None
            
        query_lower = query.lower().replace(' ', '_')
        
        # First try exact substring matches in timezone names
        for tz_name in available_timezones():
            tz_lower = tz_name.lower()
            
            # Check if query matches city name or region
            if query_lower in tz_lower:
                try:
                    tz = ZoneInfo(tz_name)
                    now = datetime.now(tz)
                    
                    return {
                        'name': tz_name,
                        'abbreviation': now.strftime('%Z'),
                        'offset': now.strftime('%z'),
                        'current_time': now,
                        'is_dst': bool(now.dst()),
                        'query': query
                    }
                except Exception:
                    continue
        
        # Try matching just the city part (after the last slash)
        for tz_name in available_timezones():
            city = tz_name.split('/')[-1].lower().replace('_', ' ')
            if query_lower == city or query_lower in city:
                try:
                    tz = ZoneInfo(tz_name)
                    now = datetime.now(tz)
                    
                    return {
                        'name': tz_name,
                        'abbreviation': now.strftime('%Z'),
                        'offset': now.strftime('%z'),
                        'current_time': now,
                        'is_dst': bool(now.dst()),
                        'query': query
                    }
                except Exception:
                    continue
        
        return None
    
    def find_timezone_suggestions(self, query: str) -> List[str]:
        """Find timezone suggestions for partial matches."""
        query_lower = query.lower()
        suggestions = []
        
        # Check aliases
        for alias, tz_name in self.timezone_aliases.items():
            if query_lower in alias.lower():
                suggestions.append(alias)
        
        # Check timezone names
        for tz_name in available_timezones():
            if query_lower in tz_name.lower():
                suggestions.append(tz_name)
                if len(suggestions) >= 10:
                    break
        
        return suggestions
    
    def convert_time_to_timezone(
        self, 
        source_time: datetime, 
        from_tz: str, 
        to_tz: str
    ) -> datetime:
        """Convert time from one timezone to another."""
        # Ensure source time is timezone-aware
        if source_time.tzinfo is None:
            source_tz = ZoneInfo(from_tz)
            source_time = source_time.replace(tzinfo=source_tz)
        
        # Convert to target timezone
        target_tz = ZoneInfo(to_tz)
        return source_time.astimezone(target_tz)
    
    def create_timezone_info_embed(self, timezone_info: Dict[str, Any]) -> discord.Embed:
        """Create embed with timezone information."""
        embed = discord.Embed(
            title=f"🌍 Timezone: {timezone_info['name']}",
            color=discord.Color.blue()
        )
        
        current_time = timezone_info['current_time']
        
        embed.add_field(
            name="Current Time",
            value=f"`{current_time.strftime('%Y-%m-%d %H:%M:%S')}`",
            inline=True
        )
        
        embed.add_field(
            name="Abbreviation",
            value=f"`{timezone_info['abbreviation']}`",
            inline=True
        )
        
        embed.add_field(
            name="UTC Offset",
            value=f"`{timezone_info['offset']}`",
            inline=True
        )
        
        embed.add_field(
            name="Daylight Saving",
            value="✅ Active" if timezone_info['is_dst'] else "❌ Not Active",
            inline=True
        )
        
        # Add Discord timestamp
        timestamp = int(current_time.timestamp())
        embed.add_field(
            name="Discord Timestamp",
            value=f"<t:{timestamp}:F>",
            inline=False
        )
        
        embed.timestamp = current_time
        
        return embed
    
    def create_conversion_result_embed(
        self, 
        source_time: datetime, 
        from_tz: str, 
        target_time: datetime, 
        to_tz: str
    ) -> discord.Embed:
        """Create embed showing time conversion result."""
        embed = discord.Embed(
            title="🔄 Time Conversion",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name=f"From: {from_tz}",
            value=f"`{source_time.strftime('%Y-%m-%d %H:%M:%S %Z')}`",
            inline=False
        )
        
        embed.add_field(
            name=f"To: {to_tz}",
            value=f"`{target_time.strftime('%Y-%m-%d %H:%M:%S %Z')}`",
            inline=False
        )
        
        # Add Discord timestamps
        source_timestamp = int(source_time.timestamp())
        embed.add_field(
            name="Discord Timestamp",
            value=f"<t:{source_timestamp}:F>",
            inline=False
        )
        
        return embed
    
    def create_multi_timezone_embed(self, source_time: datetime, from_tz: str) -> discord.Embed:
        """Create embed showing time in multiple timezones."""
        embed = discord.Embed(
            title="🌍 Time Conversion",
            description=f"**Source:** `{source_time.strftime('%Y-%m-%d %H:%M:%S')}` in `{from_tz}`",
            color=discord.Color.blue()
        )
        
        # Common target timezones
        target_timezones = [
            ("UTC", "UTC"),
            ("New York (EST/EDT)", "America/New_York"),
            ("Los Angeles (PST/PDT)", "America/Los_Angeles"),
            ("London (GMT/BST)", "Europe/London"),
            ("Paris (CET/CEST)", "Europe/Paris"),
            ("Tokyo (JST)", "Asia/Tokyo"),
        ]
        
        for display_name, tz_name in target_timezones:
            if tz_name != from_tz:  # Skip source timezone
                try:
                    converted = self.convert_time_to_timezone(source_time, from_tz, tz_name)
                    embed.add_field(
                        name=display_name,
                        value=f"`{converted.strftime('%Y-%m-%d %H:%M:%S %Z')}`",
                        inline=True
                    )
                except Exception:
                    continue
        
        # Add Discord timestamp
        timestamp = int(source_time.timestamp())
        embed.add_field(
            name="Discord Timestamp",
            value=f"<t:{timestamp}:F>",
            inline=False
        )
        
        return embed
    
    def create_timestamp_formats_embed(self, dt: datetime) -> discord.Embed:
        """Create embed showing all Discord timestamp formats."""
        embed = discord.Embed(
            title="📅 Discord Timestamp Formats",
            description=f"**Time:** `{dt.strftime('%Y-%m-%d %H:%M:%S %Z')}`",
            color=discord.Color.purple()
        )
        
        timestamp = int(dt.timestamp())
        
        formats = [
            ("Short Time", "t", f"<t:{timestamp}:t>"),
            ("Long Time", "T", f"<t:{timestamp}:T>"),
            ("Short Date", "d", f"<t:{timestamp}:d>"),
            ("Long Date", "D", f"<t:{timestamp}:D>"),
            ("Short Date/Time", "f", f"<t:{timestamp}:f>"),
            ("Long Date/Time", "F", f"<t:{timestamp}:F>"),
            ("Relative", "R", f"<t:{timestamp}:R>"),
        ]
        
        for name, code, discord_format in formats:
            embed.add_field(
                name=f"{name} (`{code}`)",
                value=f"`{discord_format}`\n{discord_format}",
                inline=True
            )
        
        return embed
    
    # Time parsing helper methods
    
    def _parse_time_hm(self, match) -> time:
        """Parse HH:MM format with optional AM/PM."""
        hour = int(match.group(1))
        minute = int(match.group(2))
        ampm = match.group(3)
        
        # Validate ranges
        if minute < 0 or minute > 59:
            raise ValueError(f"Invalid minute: {minute}")
        
        if ampm:
            # 12-hour format validation
            if hour < 1 or hour > 12:
                raise ValueError(f"Invalid hour for 12-hour format: {hour}")
            
            if ampm.lower() == 'pm' and hour != 12:
                hour += 12
            elif ampm.lower() == 'am' and hour == 12:
                hour = 0
        else:
            # 24-hour format validation
            if hour < 0 or hour > 23:
                raise ValueError(f"Invalid hour for 24-hour format: {hour}")
        
        return time(hour, minute)
    
    def _parse_time_h(self, match) -> time:
        """Parse H format with AM/PM."""
        hour = int(match.group(1))
        ampm = match.group(2)
        
        # Validate hour range
        if hour < 1 or hour > 12:
            raise ValueError(f"Invalid hour for 12-hour format: {hour}")
        
        if ampm.lower() == 'pm' and hour != 12:
            hour += 12
        elif ampm.lower() == 'am' and hour == 12:
            hour = 0
        
        return time(hour, 0)
    
    def _parse_time_hms(self, match) -> time:
        """Parse HH:MM:SS format."""
        hour = int(match.group(1))
        minute = int(match.group(2))
        second = int(match.group(3))
        
        return time(hour, minute, second)
    
    def _parse_relative_minutes(self, match) -> datetime:
        """Parse 'in X minutes'."""
        minutes = int(match.group(1))
        return datetime.now() + timedelta(minutes=minutes)
    
    def _parse_relative_hours(self, match) -> datetime:
        """Parse 'in X hours'."""
        hours = int(match.group(1))
        return datetime.now() + timedelta(hours=hours)
    
    def _parse_relative_days(self, match) -> datetime:
        """Parse 'in X days'."""
        days = int(match.group(1))
        return datetime.now() + timedelta(days=days)
    
    def _parse_today(self, match) -> datetime:
        """Parse 'today'."""
        return datetime.now()
    
    def _parse_tomorrow(self, match) -> datetime:
        """Parse 'tomorrow'."""
        return datetime.now() + timedelta(days=1)
    
    def _parse_yesterday(self, match) -> datetime:
        """Parse 'yesterday'."""
        return datetime.now() - timedelta(days=1)
    
    def _parse_next_weekday(self, match) -> datetime:
        """Parse 'next [weekday]'."""
        weekday_name = match.group(1).lower()
        weekdays = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        target_weekday = weekdays[weekday_name]
        today = datetime.now()
        days_ahead = target_weekday - today.weekday()
        
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        
        return today + timedelta(days=days_ahead)
    
    def _parse_this_weekday(self, match) -> datetime:
        """Parse 'this [weekday]'."""
        weekday_name = match.group(1).lower()
        weekdays = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        target_weekday = weekdays[weekday_name]
        today = datetime.now()
        days_ahead = target_weekday - today.weekday()
        
        if days_ahead < 0:  # Target day already happened this week
            days_ahead += 7
        
        return today + timedelta(days=days_ahead)
    
    def _parse_date_mdy(self, match) -> datetime:
        """Parse MM/DD/YYYY format."""
        month = int(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3))
        
        return datetime(year, month, day)
    
    def _parse_date_ymd(self, match) -> datetime:
        """Parse YYYY-MM-DD format."""
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        
        return datetime(year, month, day)
    
    def _parse_date_dmy(self, match) -> datetime:
        """Parse DD-MM-YYYY format."""
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))
        
        return datetime(year, month, day)
    
    def _parse_noon(self, match) -> time:
        """Parse 'noon' or 'midday'."""
        return time(12, 0)
    
    def _parse_midnight(self, match) -> time:
        """Parse 'midnight'."""
        return time(0, 0)
    
    def _parse_morning(self, match) -> time:
        """Parse 'morning'."""
        return time(9, 0)
    
    def _parse_afternoon(self, match) -> time:
        """Parse 'afternoon'."""
        return time(14, 0)
    
    def _parse_evening(self, match) -> time:
        """Parse 'evening'."""
        return time(18, 0)
    
    def _parse_night(self, match) -> time:
        """Parse 'night'."""
        return time(21, 0)


async def setup(bot):
    """Set up the Timestamps cog."""
    await bot.add_cog(TimestampsCog(bot))