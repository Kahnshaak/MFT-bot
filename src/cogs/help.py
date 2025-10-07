"""
Comprehensive help system with contextual command assistance.
"""

import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

import discord
from discord.ext import commands

from core.event_bus import EventBus, EventType
from core.permission_decorators import require_permission
from core.security_manager import Permission
from utils.logging_config import get_logger, LoggerMixin
from utils.exceptions import ValidationError


class HelpCategory:
    """Represents a help category with commands."""
    
    def __init__(self, name: str, description: str, emoji: str = "📋"):
        self.name = name
        self.description = description
        self.emoji = emoji
        self.commands = []
    
    def add_command(self, command_info: Dict[str, Any]):
        """Add command information to this category."""
        self.commands.append(command_info)


class HelpCommand:
    """Represents a help command with detailed information."""
    
    def __init__(self, name: str, description: str, usage: str, 
                 examples: List[str] = None, permissions: str = "Everyone",
                 category: str = "General"):
        self.name = name
        self.description = description
        self.usage = usage
        self.examples = examples or []
        self.permissions = permissions
        self.category = category


class HelpSystem:
    """Comprehensive help system for the bot."""
    
    def __init__(self):
        self.categories = {}
        self.commands = {}
        self._initialize_help_data()
    
    def _initialize_help_data(self):
        """Initialize help data with all bot commands."""
        # Events category
        events_category = HelpCategory(
            "Events", 
            "Create and manage game night events",
            "🎮"
        )
        
        events_commands = [
            HelpCommand(
                "event create",
                "Create a new game night event with interactive polls",
                "/event create",
                ["/event create"],
                "Everyone",
                "Events"
            ),
            HelpCommand(
                "event list",
                "View all upcoming and past events",
                "/event list [status]",
                ["/event list", "/event list upcoming", "/event list completed"],
                "Everyone", 
                "Events"
            ),
            HelpCommand(
                "event info",
                "Get detailed information about a specific event",
                "/event info <event_id>",
                ["/event info 12345"],
                "Everyone",
                "Events"
            )
        ]
        
        for cmd in events_commands:
            events_category.add_command(cmd.__dict__)
            self.commands[cmd.name] = cmd
        
        self.categories["Events"] = events_category 
       
        # Games category
        games_category = HelpCategory(
            "Games",
            "Manage game interests and notifications", 
            "🎯"
        )
        
        games_commands = [
            HelpCommand(
                "games add",
                "Add a game to your interest list",
                "/games add <game_name>",
                ["/games add Among Us", "/games add Minecraft"],
                "Everyone",
                "Games"
            ),
            HelpCommand(
                "games remove", 
                "Remove a game from your interest list",
                "/games remove <game_name>",
                ["/games remove Among Us"],
                "Everyone",
                "Games"
            ),
            HelpCommand(
                "games list",
                "View your game interests and statistics",
                "/games list",
                ["/games list"],
                "Everyone",
                "Games"
            ),
            HelpCommand(
                "games ping",
                "Notify all users interested in a specific game",
                "/games ping <game_name>",
                ["/games ping Among Us"],
                "Everyone",
                "Games"
            )
        ]
        
        for cmd in games_commands:
            games_category.add_command(cmd.__dict__)
            self.commands[cmd.name] = cmd
        
        self.categories["Games"] = games_category
        
        # User Management category
        users_category = HelpCategory(
            "Profile & Settings",
            "Manage your profile, preferences, and settings",
            "👤"
        )
        
        users_commands = [
            HelpCommand(
                "profile",
                "View and manage your user profile",
                "/profile",
                ["/profile"],
                "Everyone",
                "Profile & Settings"
            ),
            HelpCommand(
                "timezone",
                "Set your timezone for accurate event times",
                "/timezone <timezone>",
                ["/timezone America/New_York", "/timezone Europe/London"],
                "Everyone",
                "Profile & Settings"
            ),
            HelpCommand(
                "availability",
                "Manage your weekly availability schedule",
                "/availability",
                ["/availability"],
                "Everyone",
                "Profile & Settings"
            ),
            HelpCommand(
                "notifications",
                "Configure notification preferences",
                "/notifications",
                ["/notifications"],
                "Everyone",
                "Profile & Settings"
            )
        ]
        
        for cmd in users_commands:
            users_category.add_command(cmd.__dict__)
            self.commands[cmd.name] = cmd
        
        self.categories["Profile & Settings"] = users_category    
    
        # Admin category
        admin_category = HelpCategory(
            "Administration",
            "Server administration and configuration",
            "⚙️"
        )
        
        admin_commands = [
            HelpCommand(
                "admin config",
                "Configure server settings and bot behavior",
                "/admin config [setting] [value]",
                ["/admin config", "/admin config timezone UTC"],
                "Administrators",
                "Administration"
            ),
            HelpCommand(
                "admin roles",
                "Configure role permissions and mappings",
                "/admin roles [action] [role]",
                ["/admin roles", "/admin roles add @GameMaster"],
                "Administrators", 
                "Administration"
            ),
            HelpCommand(
                "admin stats",
                "View server statistics and analytics",
                "/admin stats [detailed]",
                ["/admin stats", "/admin stats detailed"],
                "Administrators",
                "Administration"
            )
        ]
        
        for cmd in admin_commands:
            admin_category.add_command(cmd.__dict__)
            self.commands[cmd.name] = cmd
        
        self.categories["Administration"] = admin_category
        
        # Utilities category
        utils_category = HelpCategory(
            "Utilities",
            "Helpful utilities and tools",
            "🛠️"
        )
        
        utils_commands = [
            HelpCommand(
                "time convert",
                "Convert time between timezones",
                "/time convert <time> <from_timezone> <to_timezone>",
                ["/time convert 8:00 PM America/New_York Europe/London"],
                "Everyone",
                "Utilities"
            ),
            HelpCommand(
                "time zone",
                "Get information about a timezone",
                "/time zone <timezone>",
                ["/time zone America/New_York"],
                "Everyone",
                "Utilities"
            ),
            HelpCommand(
                "help",
                "Get help with bot commands and features",
                "/help [command]",
                ["/help", "/help event create", "/help games"],
                "Everyone",
                "Utilities"
            )
        ]
        
        for cmd in utils_commands:
            utils_category.add_command(cmd.__dict__)
            self.commands[cmd.name] = cmd
        
        self.categories["Utilities"] = utils_category
    
    def get_category_embed(self, category_name: str) -> discord.Embed:
        """Get embed for a specific category."""
        if category_name not in self.categories:
            return None
        
        category = self.categories[category_name]
        embed = discord.Embed(
            title=f"{category.emoji} {category.name}",
            description=category.description,
            color=discord.Color.blue()
        )
        
        for cmd in category.commands:
            embed.add_field(
                name=f"/{cmd['name']}",
                value=f"{cmd['description']}\n`{cmd['usage']}`",
                inline=False
            )
        
        embed.set_footer(text="Use /help <command> for detailed information about a specific command")
        return embed    

    def get_command_embed(self, command_name: str) -> discord.Embed:
        """Get detailed embed for a specific command."""
        if command_name not in self.commands:
            return None
        
        cmd = self.commands[command_name]
        embed = discord.Embed(
            title=f"📖 /{cmd.name}",
            description=cmd.description,
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Usage",
            value=f"`{cmd.usage}`",
            inline=False
        )
        
        if cmd.examples:
            examples_text = "\n".join(f"`{example}`" for example in cmd.examples)
            embed.add_field(
                name="Examples",
                value=examples_text,
                inline=False
            )
        
        embed.add_field(
            name="Required Permissions",
            value=cmd.permissions,
            inline=True
        )
        
        embed.add_field(
            name="Category",
            value=cmd.category,
            inline=True
        )
        
        embed.set_footer(text="Need more help? Use /help to see all categories")
        return embed
    
    def get_main_help_embed(self) -> discord.Embed:
        """Get main help embed with all categories."""
        embed = discord.Embed(
            title="🎮 Game Night Bot Help",
            description="Welcome to Game Night Bot! Here are all available command categories:",
            color=discord.Color.blue()
        )
        
        for category_name, category in self.categories.items():
            embed.add_field(
                name=f"{category.emoji} {category.name}",
                value=f"{category.description}\n`/help {category_name.lower()}`",
                inline=True
            )
        
        embed.add_field(
            name="🆘 Need More Help?",
            value=(
                "• Use `/help <category>` to see commands in a category\n"
                "• Use `/help <command>` for detailed command info\n"
                "• Contact server administrators for additional support"
            ),
            inline=False
        )
        
        embed.set_footer(text="Game Night Bot - Making game nights easier!")
        return embed


class HelpView(discord.ui.View):
    """Interactive help view with category navigation."""
    
    def __init__(self, help_system: HelpSystem):
        super().__init__(timeout=300)
        self.help_system = help_system
        
        # Add category dropdown
        self.add_item(CategoryDropdown(help_system))
    
    @discord.ui.button(label="Main Menu", style=discord.ButtonStyle.primary, emoji="🏠")
    async def main_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Return to main help menu."""
        embed = self.help_system.get_main_help_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class CategoryDropdown(discord.ui.Select):
    """Dropdown for selecting help categories."""
    
    def __init__(self, help_system: HelpSystem):
        self.help_system = help_system
        
        options = []
        for category_name, category in help_system.categories.items():
            options.append(
                discord.SelectOption(
                    label=category.name,
                    description=category.description,
                    emoji=category.emoji,
                    value=category_name
                )
            )
        
        super().__init__(
            placeholder="Choose a category to explore...",
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle category selection."""
        category_name = self.values[0]
        embed = self.help_system.get_category_embed(category_name)
        
        if embed:
            await interaction.response.edit_message(embed=embed, view=self.view)
        else:
            await interaction.response.send_message(
                "❌ Category not found. Please try again.",
                ephemeral=True
            )


class HelpCog(commands.Cog, LoggerMixin):
    """
    Comprehensive help system with contextual command assistance.
    
    Provides interactive help with categories, detailed command information,
    and contextual assistance for users.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.help_system = HelpSystem()
        self.event_bus: EventBus = bot.event_bus
        
        # Subscribe to events for contextual help
        self.event_bus.subscribe(EventType.COMMAND_ERROR, self._on_command_error)
        self.event_bus.subscribe(EventType.USER_ONBOARDED, self._on_user_onboarded)
    
    async def _on_command_error(self, event_data):
        """Provide contextual help when commands fail."""
        try:
            data = event_data.data
            command_name = data.get('command_name')
            user_id = data.get('user_id')
            guild_id = data.get('guild_id')
            error_type = data.get('error_type')
            
            if command_name and user_id and guild_id:
                # Send contextual help for the failed command
                guild = self.bot.get_guild(int(guild_id))
                if guild:
                    user = guild.get_member(int(user_id))
                    if user:
                        await self._send_contextual_help(user, command_name, error_type)
        
        except Exception as e:
            self.logger.error(f"Error providing contextual help: {e}", exc_info=True)
    
    async def _on_user_onboarded(self, event_data):
        """Send getting started help to new users."""
        try:
            data = event_data.data
            user_id = data.get('user_id')
            guild_id = data.get('guild_id')
            
            if user_id and guild_id:
                # Send getting started guide
                guild = self.bot.get_guild(int(guild_id))
                if guild:
                    user = guild.get_member(int(user_id))
                    if user:
                        await self._send_getting_started_guide(user)
        
        except Exception as e:
            self.logger.error(f"Error sending getting started guide: {e}", exc_info=True)
    
    async def _send_contextual_help(self, user: discord.Member, command_name: str, error_type: str):
        """Send contextual help for a failed command."""
        try:
            embed = discord.Embed(
                title="🆘 Need Help?",
                description=f"It looks like you had trouble with the `/{command_name}` command.",
                color=discord.Color.orange()
            )
            
            # Get command help if available
            if command_name in self.help_system.commands:
                cmd = self.help_system.commands[command_name]
                embed.add_field(
                    name="Command Usage",
                    value=f"`{cmd.usage}`",
                    inline=False
                )
                
                if cmd.examples:
                    embed.add_field(
                        name="Examples",
                        value="\n".join(f"`{ex}`" for ex in cmd.examples[:2]),
                        inline=False
                    )
            
            # Add error-specific help
            if error_type == "permission_denied":
                embed.add_field(
                    name="Permission Issue",
                    value="You don't have permission to use this command. Contact a server administrator if you think this is a mistake.",
                    inline=False
                )
            elif error_type == "validation_error":
                embed.add_field(
                    name="Input Issue",
                    value="The information you provided wasn't valid. Please check the examples above and try again.",
                    inline=False
                )
            
            embed.add_field(
                name="Get More Help",
                value=f"Use `/help {command_name}` for detailed information about this command.",
                inline=False
            )
            
            try:
                await user.send(embed=embed)
            except discord.Forbidden:
                # Can't DM user, skip contextual help
                pass
        
        except Exception as e:
            self.logger.error(f"Error sending contextual help: {e}", exc_info=True)
    
    async def _send_getting_started_guide(self, user: discord.Member):
        """Send getting started guide to new users."""
        try:
            embed = discord.Embed(
                title="🚀 Getting Started with Game Night Bot",
                description="Welcome! Here's a quick guide to get you started:",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="1️⃣ Set Up Your Profile",
                value=(
                    "• Use `/profile` to view and manage your profile\n"
                    "• Set your timezone with `/timezone <your_timezone>`\n"
                    "• Add your availability with `/availability`"
                ),
                inline=False
            )
            
            embed.add_field(
                name="2️⃣ Add Game Interests",
                value=(
                    "• Use `/games add <game_name>` to add games you like\n"
                    "• Use `/games list` to see your interests\n"
                    "• Use `/games ping <game_name>` to find others to play with"
                ),
                inline=False
            )
            
            embed.add_field(
                name="3️⃣ Join or Create Events",
                value=(
                    "• Use `/event create` to organize a game night\n"
                    "• Use `/event list` to see upcoming events\n"
                    "• RSVP to events you want to attend"
                ),
                inline=False
            )
            
            embed.add_field(
                name="4️⃣ Get Help Anytime",
                value=(
                    "• Use `/help` to see all available commands\n"
                    "• Use `/help <command>` for specific command help\n"
                    "• Contact server admins if you need assistance"
                ),
                inline=False
            )
            
            embed.set_footer(text="Have fun organizing game nights! 🎮")
            
            try:
                await user.send(embed=embed)
            except discord.Forbidden:
                # Can't DM user, skip getting started guide
                pass
        
        except Exception as e:
            self.logger.error(f"Error sending getting started guide: {e}", exc_info=True)    
    @
commands.slash_command(
        name="help",
        description="Get help with bot commands and features"
    )
    async def help_command(
        self,
        interaction: discord.Interaction,
        query: discord.Option(
            str,
            description="Command name or category to get help with",
            required=False,
            default=None
        ) = None
    ):
        """Main help command with interactive interface."""
        try:
            if not query:
                # Show main help menu
                embed = self.help_system.get_main_help_embed()
                view = HelpView(self.help_system)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                return
            
            query = query.lower().strip()
            
            # Check if it's a specific command
            if query in self.help_system.commands:
                embed = self.help_system.get_command_embed(query)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Check if it's a category
            for category_name, category in self.help_system.categories.items():
                if query == category_name.lower() or query in category_name.lower():
                    embed = self.help_system.get_category_embed(category_name)
                    view = HelpView(self.help_system)
                    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                    return
            
            # Search for partial matches
            matches = []
            for cmd_name in self.help_system.commands:
                if query in cmd_name.lower():
                    matches.append(cmd_name)
            
            if matches:
                if len(matches) == 1:
                    # Single match, show command help
                    embed = self.help_system.get_command_embed(matches[0])
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    # Multiple matches, show options
                    embed = discord.Embed(
                        title="🔍 Multiple Matches Found",
                        description=f"Found multiple commands matching '{query}':",
                        color=discord.Color.orange()
                    )
                    
                    matches_text = "\n".join(f"• `/help {match}`" for match in matches[:10])
                    embed.add_field(
                        name="Did you mean:",
                        value=matches_text,
                        inline=False
                    )
                    
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                # No matches found
                embed = discord.Embed(
                    title="❓ No Help Found",
                    description=f"I couldn't find help for '{query}'.",
                    color=discord.Color.red()
                )
                
                embed.add_field(
                    name="Try:",
                    value=(
                        "• `/help` - See all available categories\n"
                        "• `/help events` - Get help with events\n"
                        "• `/help games` - Get help with games\n"
                        "• `/help profile` - Get help with profile settings"
                    ),
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
        
        except Exception as e:
            self.logger.error(f"Error in help command: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ Something went wrong while loading help. Please try again or contact an administrator if the issue persists.",
                ephemeral=True
            )
    
    @commands.slash_command(
        name="quickstart",
        description="Get a quick guide to using the bot"
    )
    async def quickstart_command(self, interaction: discord.Interaction):
        """Provide a quick start guide for new users."""
        try:
            embed = discord.Embed(
                title="⚡ Quick Start Guide",
                description="Get up and running with Game Night Bot in just a few steps!",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="🎯 Essential First Steps",
                value=(
                    "1. `/timezone America/New_York` - Set your timezone\n"
                    "2. `/games add Minecraft` - Add games you like\n"
                    "3. `/event create` - Create your first event\n"
                    "4. `/profile` - View your complete profile"
                ),
                inline=False
            )
            
            embed.add_field(
                name="🔧 Useful Commands",
                value=(
                    "• `/help` - Get detailed help\n"
                    "• `/event list` - See all events\n"
                    "• `/games ping <game>` - Find people to play with\n"
                    "• `/availability` - Set when you're free"
                ),
                inline=False
            )
            
            embed.add_field(
                name="💡 Pro Tips",
                value=(
                    "• Set up notifications to never miss events\n"
                    "• Add multiple games to get more pings\n"
                    "• Use availability to help with scheduling\n"
                    "• Check `/admin` commands if you're a server admin"
                ),
                inline=False
            )
            
            embed.set_footer(text="Use /help for more detailed information about any command")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        except Exception as e:
            self.logger.error(f"Error in quickstart command: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ Something went wrong while loading the quick start guide. Please try again or contact an administrator if the issue persists.",
                ephemeral=True
            )


def setup(bot):
    """Set up the help cog."""
    bot.add_cog(HelpCog(bot))