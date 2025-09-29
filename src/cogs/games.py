"""
Games cog for managing game interests and notification system.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from difflib import SequenceMatcher

import discord
from discord.ext import commands
from discord import app_commands

from models.game import Game, GameCategory, GameAlias, NotificationFrequencyLimit
from models.user import User
from models.repositories import RepositoryManager
from models.base import ValidationMixin
from core.event_bus import EventBus, EventType
from core.permission_decorators import require_permission
from core.security_manager import Permission
from core.validation_manager import ValidationManager
from utils.exceptions import ValidationError, PermissionDeniedError, ErrorCode
from utils.logging_config import get_logger, LoggerMixin


class GameSearchModal(discord.ui.Modal):
    """Modal for game search and confirmation."""
    
    def __init__(self, cog: 'GamesCog', search_term: str, matches: List[Tuple[Game, float]]):
        super().__init__(title="Game Search Results")
        self.cog = cog
        self.search_term = search_term
        self.matches = matches
        
        # Create options text
        options_text = "Found these matches:\n"
        for i, (game, confidence) in enumerate(matches[:5], 1):
            options_text += f"{i}. {game.name} ({confidence:.1%} match)\n"
        
        if not matches:
            options_text = f"No matches found for '{search_term}'"
        
        self.game_input = discord.ui.TextInput(
            label="Select Game (number) or Enter New Name",
            placeholder="Enter 1-5 for matches above, or type new game name",
            default="1" if matches else search_term,
            min_length=1,
            max_length=100,
            required=True
        )
        self.add_item(self.game_input)
        
        # Add matches info as a read-only field
        self.matches_info = discord.ui.TextInput(
            label="Search Results",
            default=options_text,
            style=discord.TextStyle.paragraph,
            required=False
        )
        self.matches_info.disabled = True
        self.add_item(self.matches_info)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle game selection or new game entry."""
        try:
            user_input = self.game_input.value.strip()
            
            # Check if user selected a number
            if user_input.isdigit():
                selection = int(user_input)
                if 1 <= selection <= len(self.matches):
                    selected_game = self.matches[selection - 1][0]
                    await self.cog._handle_game_ping_confirmed(
                        interaction, selected_game.name
                    )
                    return
                else:
                    await interaction.response.send_message(
                        f"❌ Invalid selection. Please choose 1-{len(self.matches)}.",
                        ephemeral=True
                    )
                    return
            
            # User entered a new game name
            await self.cog._handle_game_ping_confirmed(interaction, user_input)
            
        except Exception as e:
            self.cog.logger.error(f"Error in game search modal: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while processing your selection.",
                ephemeral=True
            )


class GameManagementView(discord.ui.View):
    """View for game management operations."""
    
    def __init__(self, cog: 'GamesCog', game: Game):
        super().__init__(timeout=300)
        self.cog = cog
        self.game = game
    
    @discord.ui.button(label="Add Alias", style=discord.ButtonStyle.secondary, emoji="🔗")
    async def add_alias(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = GameAliasModal(self.cog, self.game, "add")
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Add Category", style=discord.ButtonStyle.secondary, emoji="📂")
    async def add_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = GameCategoryModal(self.cog, self.game)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Add Tag", style=discord.ButtonStyle.secondary, emoji="🏷️")
    async def add_tag(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = GameTagModal(self.cog, self.game)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="View Stats", style=discord.ButtonStyle.primary, emoji="📊")
    async def view_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.cog.create_game_stats_embed(self.game)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class GameAliasModal(discord.ui.Modal):
    """Modal for adding/removing game aliases."""
    
    def __init__(self, cog: 'GamesCog', game: Game, action: str):
        super().__init__(title=f"{action.title()} Game Alias")
        self.cog = cog
        self.game = game
        self.action = action
        
        self.alias_input = discord.ui.TextInput(
            label="Alias Name",
            placeholder="Enter alternative name for the game",
            min_length=1,
            max_length=100,
            required=True
        )
        self.add_item(self.alias_input)
        
        if action == "add":
            self.confidence_input = discord.ui.TextInput(
                label="Confidence (0.1-1.0)",
                placeholder="How confident is this match? (default: 1.0)",
                default="1.0",
                min_length=1,
                max_length=3,
                required=False
            )
            self.add_item(self.confidence_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle alias addition/removal."""
        try:
            alias = self.alias_input.value.strip()
            
            if self.action == "add":
                confidence = 1.0
                if hasattr(self, 'confidence_input') and self.confidence_input.value:
                    try:
                        confidence = float(self.confidence_input.value)
                        if not (0.1 <= confidence <= 1.0):
                            raise ValueError("Confidence must be between 0.1 and 1.0")
                    except ValueError as e:
                        await interaction.response.send_message(
                            f"❌ Invalid confidence value: {e}",
                            ephemeral=True
                        )
                        return
                
                success = self.game.add_alias(alias, confidence)
                if success:
                    await self.cog.repositories.games.update(str(self.game.id), self.game)
                    await interaction.response.send_message(
                        f"✅ Added alias **{alias}** to **{self.game.name}**",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"❌ Alias **{alias}** already exists or matches the primary name.",
                        ephemeral=True
                    )
            
            elif self.action == "remove":
                success = self.game.remove_alias(alias)
                if success:
                    await self.cog.repositories.games.update(str(self.game.id), self.game)
                    await interaction.response.send_message(
                        f"✅ Removed alias **{alias}** from **{self.game.name}**",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"❌ Alias **{alias}** not found.",
                        ephemeral=True
                    )
            
        except Exception as e:
            self.cog.logger.error(f"Error handling alias modal: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while processing the alias.",
                ephemeral=True
            )


class GameCategoryModal(discord.ui.Modal):
    """Modal for adding game categories."""
    
    def __init__(self, cog: 'GamesCog', game: Game):
        super().__init__(title="Add Game Category")
        self.cog = cog
        self.game = game
        
        # Create category options text
        categories = [cat.value for cat in GameCategory]
        options_text = "Available categories:\n" + ", ".join(categories)
        
        self.category_input = discord.ui.TextInput(
            label="Category",
            placeholder="Enter category name (see options below)",
            min_length=1,
            max_length=20,
            required=True
        )
        self.add_item(self.category_input)
        
        self.options_info = discord.ui.TextInput(
            label="Available Categories",
            default=options_text,
            style=discord.TextStyle.paragraph,
            required=False
        )
        self.options_info.disabled = True
        self.add_item(self.options_info)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle category addition."""
        try:
            category_str = self.category_input.value.strip().upper()
            
            try:
                category = GameCategory(category_str)
            except ValueError:
                await interaction.response.send_message(
                    f"❌ Invalid category: **{category_str}**\n"
                    f"Available: {', '.join([cat.value for cat in GameCategory])}",
                    ephemeral=True
                )
                return
            
            success = self.game.add_category(category)
            if success:
                await self.cog.repositories.games.update(str(self.game.id), self.game)
                await interaction.response.send_message(
                    f"✅ Added category **{category.value}** to **{self.game.name}**",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ Category **{category.value}** already exists for this game.",
                    ephemeral=True
                )
            
        except Exception as e:
            self.cog.logger.error(f"Error adding category: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while adding the category.",
                ephemeral=True
            )


class GameTagModal(discord.ui.Modal):
    """Modal for adding game tags."""
    
    def __init__(self, cog: 'GamesCog', game: Game):
        super().__init__(title="Add Game Tag")
        self.cog = cog
        self.game = game
        
        self.tag_input = discord.ui.TextInput(
            label="Tag",
            placeholder="Enter custom tag for the game",
            min_length=1,
            max_length=50,
            required=True
        )
        self.add_item(self.tag_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle tag addition."""
        try:
            tag = self.tag_input.value.strip()
            
            success = self.game.add_tag(tag)
            if success:
                await self.cog.repositories.games.update(str(self.game.id), self.game)
                await interaction.response.send_message(
                    f"✅ Added tag **{tag}** to **{self.game.name}**",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ Tag **{tag}** already exists for this game.",
                    ephemeral=True
                )
            
        except Exception as e:
            self.cog.logger.error(f"Error adding tag: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while adding the tag.",
                ephemeral=True
            )


class GamesCog(commands.Cog, LoggerMixin):
    """
    Games cog for managing game interests and notification system.
    
    Handles game interest registration, fuzzy matching, ping system,
    popularity tracking, and notification frequency limiting.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.validation: ValidationManager = bot.validation
        self.event_bus: EventBus = bot.event_bus
        self.repositories: RepositoryManager = RepositoryManager(bot.database)
        
        # Subscribe to relevant events
        self.event_bus.subscribe(EventType.USER_GAME_INTEREST_ADDED, self._on_game_interest_added)
        self.event_bus.subscribe(EventType.USER_GAME_INTEREST_REMOVED, self._on_game_interest_removed)
    
    async def _on_game_interest_added(self, event_data):
        """Handle game interest added event."""
        try:
            guild_id = event_data.data.get('guild_id')
            game_name = event_data.data.get('game_name')
            
            if guild_id and game_name:
                # Update game statistics
                await self._update_game_statistics(guild_id, game_name, 'interest_added')
        except Exception as e:
            self.logger.error(f"Error handling game interest added: {e}", exc_info=True)
    
    async def _on_game_interest_removed(self, event_data):
        """Handle game interest removed event."""
        try:
            guild_id = event_data.data.get('guild_id')
            game_name = event_data.data.get('game_name')
            
            if guild_id and game_name:
                # Update game statistics
                await self._update_game_statistics(guild_id, game_name, 'interest_removed')
        except Exception as e:
            self.logger.error(f"Error handling game interest removed: {e}", exc_info=True)
    
    async def _update_game_statistics(self, guild_id: str, game_name: str, action: str):
        """Update game statistics based on action."""
        try:
            # Find or create game
            game = await self.repositories.games.get_by_name(guild_id, game_name)
            if not game:
                game = Game(
                    guild_id=guild_id,
                    name=game_name,
                    is_active=True
                )
                game_id = await self.repositories.games.create(game)
                game = await self.repositories.games.get_by_id(game_id)
            
            # Update statistics
            if action == 'interest_added':
                game.update_interest_added()
            elif action == 'interest_removed':
                game.update_interest_removed()
            elif action == 'ping_sent':
                game.update_ping_sent()
            elif action == 'play_recorded':
                game.update_play_recorded()
            
            # Save updated game
            await self.repositories.games.update(str(game.id), game)
            
        except Exception as e:
            self.logger.error(f"Error updating game statistics: {e}", exc_info=True)
    
    @app_commands.command(name="games-add", description="Add a game to your interests")
    @app_commands.describe(
        game_name="Name of the game you're interested in",
        interest_level="Your interest level (1-10, default: 5)"
    )
    async def add_game_command(
        self,
        interaction: discord.Interaction,
        game_name: str,
        interest_level: int = 5
    ):
        """Add game interest."""
        try:
            if not (1 <= interest_level <= 10):
                await interaction.response.send_message(
                    "❌ Interest level must be between 1 and 10.",
                    ephemeral=True
                )
                return
            
            # Validate and sanitize game name
            game_name = ValidationMixin.sanitize_text(game_name, 100)
            if not game_name:
                await interaction.response.send_message(
                    "❌ Invalid game name.",
                    ephemeral=True
                )
                return
            
            # Get or create user
            user = await self.repositories.ensure_user_profile(
                str(interaction.user.id),
                str(interaction.guild.id),
                interaction.user.display_name
            )
            
            # Add game interest
            success = user.add_game_interest(game_name, interest_level)
            
            if success:
                # Update in database
                await self.repositories.users.update(str(user.id), user)
                
                await interaction.response.send_message(
                    f"✅ Added **{game_name}** to your interests (level {interest_level}/10)",
                    ephemeral=True
                )
                
                # Emit event
                await self.event_bus.emit(
                    EventType.USER_GAME_INTEREST_ADDED,
                    {
                        "user_id": str(interaction.user.id),
                        "guild_id": str(interaction.guild.id),
                        "game_name": game_name,
                        "interest_level": interest_level
                    },
                    source="games_cog",
                    guild_id=str(interaction.guild.id),
                    user_id=str(interaction.user.id)
                )
            else:
                await interaction.response.send_message(
                    f"❌ You're already interested in **{game_name}**. Use `/games list` to see your interests.",
                    ephemeral=True
                )
            
        except Exception as e:
            self.logger.error(f"Error adding game interest: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while adding the game.",
                ephemeral=True
            )
    
    @app_commands.command(name="games-remove", description="Remove a game from your interests")
    @app_commands.describe(game_name="Name of the game to remove")
    async def remove_game_command(self, interaction: discord.Interaction, game_name: str):
        """Remove game interest."""
        try:
            user = await self.repositories.users.get_by_user_and_guild(
                str(interaction.user.id),
                str(interaction.guild.id)
            )
            
            if not user:
                await interaction.response.send_message(
                    "❌ No profile found. Use `/profile` to create one.",
                    ephemeral=True
                )
                return
            
            # Remove game interest
            success = user.remove_game_interest(game_name)
            
            if success:
                # Update in database
                await self.repositories.users.update(str(user.id), user)
                
                await interaction.response.send_message(
                    f"✅ Removed **{game_name}** from your interests",
                    ephemeral=True
                )
                
                # Emit event
                await self.event_bus.emit(
                    EventType.USER_GAME_INTEREST_REMOVED,
                    {
                        "user_id": str(interaction.user.id),
                        "guild_id": str(interaction.guild.id),
                        "game_name": game_name
                    },
                    source="games_cog",
                    guild_id=str(interaction.guild.id),
                    user_id=str(interaction.user.id)
                )
            else:
                await interaction.response.send_message(
                    f"❌ **{game_name}** not found in your interests.",
                    ephemeral=True
                )
            
        except Exception as e:
            self.logger.error(f"Error removing game interest: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while removing the game.",
                ephemeral=True
            )
    
    @app_commands.command(name="games-list", description="List your game interests")
    async def list_games_command(self, interaction: discord.Interaction):
        """List user's game interests."""
        try:
            user = await self.repositories.users.get_by_user_and_guild(
                str(interaction.user.id),
                str(interaction.guild.id)
            )
            
            if not user or not user.game_interests:
                await interaction.response.send_message(
                    "❌ No game interests found. Use `/games add <game>` to add some!",
                    ephemeral=True
                )
                return
            
            # Create games embed
            embed = self.create_user_games_embed(user, interaction.user)
            
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error listing games: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while loading your games.",
                ephemeral=True
            )
    
    @app_commands.command(name="games-ping", description="Ping users interested in a game")
    @app_commands.describe(game_name="Name of the game to ping for")
    async def ping_game_command(self, interaction: discord.Interaction, game_name: str):
        """Ping users interested in a game."""
        try:
            # Search for matching games
            matches = await self.repositories.games.search_games(
                str(interaction.guild.id),
                game_name,
                limit=5
            )
            
            if not matches:
                # No exact matches, show search modal
                modal = GameSearchModal(self, game_name, [])
                await interaction.response.send_modal(modal)
                return
            
            # Check if we have a perfect match
            perfect_match = None
            for game, confidence in matches:
                if confidence >= 0.95:  # Very high confidence
                    perfect_match = game
                    break
            
            if perfect_match:
                # Use perfect match directly
                await self._handle_game_ping_confirmed(interaction, perfect_match.name)
            else:
                # Show search modal with options
                modal = GameSearchModal(self, game_name, matches)
                await interaction.response.send_modal(modal)
            
        except Exception as e:
            self.logger.error(f"Error pinging game: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while pinging for the game.",
                ephemeral=True
            )
    
    async def _handle_game_ping_confirmed(self, interaction: discord.Interaction, game_name: str):
        """Handle confirmed game ping."""
        try:
            # Get interested users
            interested_users = await self.repositories.users.get_users_interested_in_game(
                str(interaction.guild.id),
                game_name
            )
            
            if not interested_users:
                await interaction.response.send_message(
                    f"❌ No users are interested in **{game_name}**.",
                    ephemeral=True
                )
                return
            
            # Filter users based on frequency limits
            pingable_users = []
            for user in interested_users:
                # Skip the user who initiated the ping
                if user.user_id == str(interaction.user.id):
                    continue
                
                can_ping = await self.repositories.notification_frequency.can_send_ping(
                    user.user_id,
                    game_name
                )
                
                if can_ping:
                    pingable_users.append(user)
            
            if not pingable_users:
                await interaction.response.send_message(
                    f"❌ All users interested in **{game_name}** have reached their notification limits.",
                    ephemeral=True
                )
                return
            
            # Create ping message
            mentions = []
            for user in pingable_users:
                try:
                    discord_user = interaction.guild.get_member(int(user.user_id))
                    if discord_user:
                        mentions.append(discord_user.mention)
                        
                        # Record ping sent for frequency limiting
                        await self.repositories.notification_frequency.record_ping_sent(
                            user.user_id,
                            game_name
                        )
                except ValueError:
                    continue
            
            if not mentions:
                await interaction.response.send_message(
                    f"❌ No users available to ping for **{game_name}**.",
                    ephemeral=True
                )
                return
            
            # Create embed for the ping
            embed = discord.Embed(
                title=f"🎮 Game Night Ping: {game_name}",
                description=f"{interaction.user.mention} wants to play **{game_name}**!",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="Interested Players",
                value=" ".join(mentions),
                inline=False
            )
            
            embed.set_footer(
                text=f"Use /games add {game_name} to get pinged for this game"
            )
            
            # Send the ping
            await interaction.response.send_message(
                content=" ".join(mentions),
                embed=embed
            )
            
            # Update game statistics
            await self._update_game_statistics(
                str(interaction.guild.id),
                game_name,
                'ping_sent'
            )
            
            # Emit event
            await self.event_bus.emit(
                EventType.NOTIFICATION_SENT,
                {
                    "type": "game_ping",
                    "game_name": game_name,
                    "sender_id": str(interaction.user.id),
                    "recipient_count": len(pingable_users),
                    "guild_id": str(interaction.guild.id)
                },
                source="games_cog",
                guild_id=str(interaction.guild.id),
                user_id=str(interaction.user.id)
            )
            
        except Exception as e:
            self.logger.error(f"Error handling game ping: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while sending the ping.",
                    ephemeral=True
                )
    
    @app_commands.command(name="games-popular", description="Show popular games in this server")
    @app_commands.describe(limit="Number of games to show (default: 10)")
    async def popular_games_command(self, interaction: discord.Interaction, limit: int = 10):
        """Show popular games."""
        try:
            if not (1 <= limit <= 25):
                await interaction.response.send_message(
                    "❌ Limit must be between 1 and 25.",
                    ephemeral=True
                )
                return
            
            popular_games = await self.repositories.games.get_popular_games(
                str(interaction.guild.id),
                limit=limit
            )
            
            if not popular_games:
                await interaction.response.send_message(
                    "❌ No games found in this server.",
                    ephemeral=True
                )
                return
            
            embed = self.create_popular_games_embed(popular_games, interaction.guild)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error showing popular games: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while loading popular games.",
                ephemeral=True
            )
    
    @app_commands.command(name="games-trending", description="Show trending games in this server")
    @app_commands.describe(limit="Number of games to show (default: 10)")
    async def trending_games_command(self, interaction: discord.Interaction, limit: int = 10):
        """Show trending games."""
        try:
            if not (1 <= limit <= 25):
                await interaction.response.send_message(
                    "❌ Limit must be between 1 and 25.",
                    ephemeral=True
                )
                return
            
            trending_games = await self.repositories.games.get_trending_games(
                str(interaction.guild.id),
                limit=limit
            )
            
            if not trending_games:
                await interaction.response.send_message(
                    "❌ No trending games found in this server.",
                    ephemeral=True
                )
                return
            
            embed = self.create_trending_games_embed(trending_games, interaction.guild)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error showing trending games: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while loading trending games.",
                ephemeral=True
            )
    
    @app_commands.command(name="games-search", description="Search for games in this server")
    @app_commands.describe(query="Search term for game names")
    async def search_games_command(self, interaction: discord.Interaction, query: str):
        """Search for games."""
        try:
            matches = await self.repositories.games.search_games(
                str(interaction.guild.id),
                query,
                limit=10
            )
            
            if not matches:
                await interaction.response.send_message(
                    f"❌ No games found matching **{query}**.",
                    ephemeral=True
                )
                return
            
            embed = self.create_search_results_embed(query, matches, interaction.guild)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error searching games: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while searching for games.",
                ephemeral=True
            )
    
    @app_commands.command(name="games-manage", description="Manage a game's metadata")
    @app_commands.describe(game_name="Name of the game to manage")
    @require_permission(Permission.MANAGE_EVENTS)
    async def manage_game_command(self, interaction: discord.Interaction, game_name: str):
        """Manage game metadata."""
        try:
            game = await self.repositories.games.get_by_name(
                str(interaction.guild.id),
                game_name
            )
            
            if not game:
                await interaction.response.send_message(
                    f"❌ Game **{game_name}** not found.",
                    ephemeral=True
                )
                return
            
            embed = self.create_game_details_embed(game)
            view = GameManagementView(self, game)
            
            await interaction.response.send_message(
                embed=embed,
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error managing game: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while loading game management.",
                ephemeral=True
            )
    
    @app_commands.command(name="games-limits", description="Configure your notification frequency limits")
    @app_commands.describe(
        game_name="Game to configure limits for",
        daily_limit="Maximum pings per day (1-50, default: 3)",
        weekly_limit="Maximum pings per week (1-100, default: 10)"
    )
    async def configure_limits_command(
        self,
        interaction: discord.Interaction,
        game_name: str,
        daily_limit: int = 3,
        weekly_limit: int = 10
    ):
        """Configure notification frequency limits."""
        try:
            if not (1 <= daily_limit <= 50):
                await interaction.response.send_message(
                    "❌ Daily limit must be between 1 and 50.",
                    ephemeral=True
                )
                return
            
            if not (1 <= weekly_limit <= 100):
                await interaction.response.send_message(
                    "❌ Weekly limit must be between 1 and 100.",
                    ephemeral=True
                )
                return
            
            if daily_limit * 7 < weekly_limit:
                await interaction.response.send_message(
                    "❌ Weekly limit cannot be higher than daily limit × 7.",
                    ephemeral=True
                )
                return
            
            # Create or update limit
            await self.repositories.notification_frequency.create_or_update_limit(
                str(interaction.user.id),
                game_name,
                daily_limit,
                weekly_limit
            )
            
            await interaction.response.send_message(
                f"✅ Updated notification limits for **{game_name}**:\n"
                f"• Daily: {daily_limit} pings\n"
                f"• Weekly: {weekly_limit} pings",
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error configuring limits: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while configuring limits.",
                ephemeral=True
            )
    
    def create_user_games_embed(self, user: User, discord_user: discord.User) -> discord.Embed:
        """Create embed showing user's game interests."""
        embed = discord.Embed(
            title=f"🎮 {discord_user.display_name}'s Game Interests",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        if not user.game_interests:
            embed.description = "No game interests yet. Use `/games add <game>` to add some!"
            return embed
        
        # Sort by interest level (descending)
        sorted_interests = sorted(
            user.game_interests,
            key=lambda x: x.interest_level,
            reverse=True
        )
        
        games_text = ""
        for interest in sorted_interests[:20]:  # Limit to 20 games
            notification_status = "🔔" if interest.notification_enabled else "🔕"
            games_text += f"{notification_status} **{interest.game_name}** (Level {interest.interest_level}/10)\n"
        
        if len(user.game_interests) > 20:
            games_text += f"\n... and {len(user.game_interests) - 20} more games"
        
        embed.add_field(
            name=f"Games ({len(user.game_interests)})",
            value=games_text,
            inline=False
        )
        
        embed.set_footer(text="🔔 = Notifications enabled, 🔕 = Notifications disabled")
        return embed
    
    def create_popular_games_embed(self, games: List[Game], guild: discord.Guild) -> discord.Embed:
        """Create embed showing popular games."""
        embed = discord.Embed(
            title=f"🏆 Popular Games in {guild.name}",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        if not games:
            embed.description = "No games found."
            return embed
        
        games_text = ""
        for i, game in enumerate(games, 1):
            stats = game.statistics
            games_text += (
                f"{i}. **{game.get_display_name()}**\n"
                f"   👥 {stats.total_interests} interested • "
                f"📢 {stats.total_pings} pings • "
                f"🎯 {stats.popularity_score:.1f} score\n"
            )
        
        embed.add_field(
            name="Rankings",
            value=games_text,
            inline=False
        )
        
        embed.set_footer(text="🔥 = Trending game")
        return embed
    
    def create_trending_games_embed(self, games: List[Game], guild: discord.Guild) -> discord.Embed:
        """Create embed showing trending games."""
        embed = discord.Embed(
            title=f"🔥 Trending Games in {guild.name}",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        
        if not games:
            embed.description = "No trending games found."
            return embed
        
        games_text = ""
        for i, game in enumerate(games, 1):
            stats = game.statistics
            games_text += (
                f"{i}. **{game.name}** 🔥\n"
                f"   📈 {stats.recent_interests} new interests • "
                f"📢 {stats.recent_pings} recent pings\n"
            )
        
        embed.add_field(
            name="Hot Right Now",
            value=games_text,
            inline=False
        )
        
        embed.set_footer(text="Based on activity in the last 30 days")
        return embed
    
    def create_search_results_embed(
        self,
        query: str,
        matches: List[Tuple[Game, float]],
        guild: discord.Guild
    ) -> discord.Embed:
        """Create embed showing search results."""
        embed = discord.Embed(
            title=f"🔍 Search Results for '{query}'",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        if not matches:
            embed.description = "No matches found."
            return embed
        
        results_text = ""
        for i, (game, confidence) in enumerate(matches, 1):
            stats = game.statistics
            results_text += (
                f"{i}. **{game.get_display_name()}** ({confidence:.1%} match)\n"
                f"   👥 {stats.total_interests} interested • "
                f"📢 {stats.total_pings} pings\n"
            )
        
        embed.add_field(
            name="Matches",
            value=results_text,
            inline=False
        )
        
        embed.set_footer(text="Use /games ping <name> to ping interested users")
        return embed
    
    def create_game_details_embed(self, game: Game) -> discord.Embed:
        """Create detailed embed for a game."""
        embed = discord.Embed(
            title=f"🎮 {game.get_display_name()}",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        if game.description:
            embed.description = game.description
        
        # Categories
        if game.categories:
            categories_text = ", ".join([cat.value for cat in game.categories])
            embed.add_field(
                name="📂 Categories",
                value=categories_text,
                inline=True
            )
        
        # Tags
        if game.tags:
            tags_text = ", ".join(game.tags)
            embed.add_field(
                name="🏷️ Tags",
                value=tags_text,
                inline=True
            )
        
        # Statistics
        stats = game.statistics
        stats_text = (
            f"👥 **{stats.total_interests}** interested users\n"
            f"📢 **{stats.total_pings}** total pings\n"
            f"🎯 **{stats.popularity_score:.1f}** popularity score"
        )
        
        if game.is_trending():
            stats_text += f"\n🔥 **Trending** ({stats.recent_interests} recent interests)"
        
        embed.add_field(
            name="📊 Statistics",
            value=stats_text,
            inline=False
        )
        
        # Aliases
        if game.aliases:
            aliases_text = ", ".join([alias.alias for alias in game.aliases[:10]])
            if len(game.aliases) > 10:
                aliases_text += f" (+{len(game.aliases) - 10} more)"
            
            embed.add_field(
                name="🔗 Aliases",
                value=aliases_text,
                inline=False
            )
        
        embed.set_footer(text=f"Created {game.created_at.strftime('%Y-%m-%d')}")
        return embed
    
    def create_game_stats_embed(self, game: Game) -> discord.Embed:
        """Create detailed statistics embed for a game."""
        embed = discord.Embed(
            title=f"📊 Statistics for {game.name}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        stats = game.statistics
        
        # Overall stats
        overall_text = (
            f"👥 **{stats.total_interests}** total interests\n"
            f"📢 **{stats.total_pings}** total pings\n"
            f"🎮 **{stats.total_plays}** recorded plays\n"
            f"🎯 **{stats.popularity_score:.1f}** popularity score"
        )
        
        embed.add_field(
            name="Overall Statistics",
            value=overall_text,
            inline=True
        )
        
        # Recent activity
        recent_text = (
            f"📈 **{stats.recent_interests}** new interests (30d)\n"
            f"📢 **{stats.recent_pings}** recent pings (7d)\n"
            f"🎮 **{stats.recent_plays}** recent plays (30d)"
        )
        
        embed.add_field(
            name="Recent Activity",
            value=recent_text,
            inline=True
        )
        
        # Last activity
        last_activity_text = ""
        if stats.last_interest_added:
            last_activity_text += f"👥 Last interest: {stats.last_interest_added.strftime('%Y-%m-%d')}\n"
        if stats.last_ping_sent:
            last_activity_text += f"📢 Last ping: {stats.last_ping_sent.strftime('%Y-%m-%d')}\n"
        if stats.last_play_recorded:
            last_activity_text += f"🎮 Last play: {stats.last_play_recorded.strftime('%Y-%m-%d')}\n"
        
        if last_activity_text:
            embed.add_field(
                name="Last Activity",
                value=last_activity_text,
                inline=False
            )
        
        if game.is_trending():
            embed.add_field(
                name="🔥 Trending Status",
                value="This game is currently trending!",
                inline=False
            )
        
        return embed


async def setup(bot):
    """Set up the Games cog."""
    await bot.add_cog(GamesCog(bot))