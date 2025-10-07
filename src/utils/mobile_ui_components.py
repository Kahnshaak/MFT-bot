"""
Mobile-optimized Discord UI components for better mobile Discord client experience.

This module provides enhanced UI components specifically designed for mobile Discord clients,
with improved touch targets, simplified layouts, and better accessibility.
"""

import discord
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime, timedelta
import asyncio
import logging

logger = logging.getLogger(__name__)


class MobileOptimizedView(discord.ui.View):
    """Base view class optimized for mobile Discord clients."""
    
    def __init__(self, *, timeout: Optional[float] = 300):
        super().__init__(timeout=timeout)
        self.mobile_optimized = True
        self._setup_mobile_optimizations()
    
    def _setup_mobile_optimizations(self):
        """Apply mobile-specific optimizations."""
        # Reduce timeout for mobile users (shorter attention spans)
        if self.timeout and self.timeout > 300:
            self.timeout = 300
    
    def add_item(self, item: discord.ui.Item) -> None:
        """Override to apply mobile optimizations to items."""
        if hasattr(item, 'apply_mobile_optimizations'):
            item.apply_mobile_optimizations()
        super().add_item(item)
    
    async def on_timeout(self) -> None:
        """Handle timeout with mobile-friendly message."""
        try:
            # Disable all components
            for item in self.children:
                item.disabled = True
            
            # Update message with timeout notice
            if hasattr(self, 'message') and self.message:
                embed = discord.Embed(
                    title="⏰ Interaction Timeout",
                    description="This interaction has timed out. Please run the command again to continue.",
                    color=0xf6c23e
                )
                embed.set_footer(text="Tip: Mobile interactions timeout faster to save battery")
                
                await self.message.edit(embed=embed, view=self)
        except Exception as e:
            logger.error(f"Error handling mobile view timeout: {e}")


class MobileOptimizedButton(discord.ui.Button):
    """Button optimized for mobile touch interfaces."""
    
    def __init__(self, 
                 *,
                 style: discord.ButtonStyle = discord.ButtonStyle.secondary,
                 label: Optional[str] = None,
                 emoji: Optional[str] = None,
                 custom_id: Optional[str] = None,
                 url: Optional[str] = None,
                 disabled: bool = False,
                 row: Optional[int] = None,
                 mobile_priority: int = 0):
        
        # Apply mobile optimizations to label
        if label and len(label) > 20:
            # Truncate long labels for mobile
            label = label[:17] + "..."
        
        super().__init__(
            style=style,
            label=label,
            emoji=emoji,
            custom_id=custom_id,
            url=url,
            disabled=disabled,
            row=row
        )
        
        self.mobile_priority = mobile_priority
        self.mobile_optimized = True
    
    def apply_mobile_optimizations(self):
        """Apply mobile-specific optimizations."""
        # Ensure emoji is present for better touch targets
        if not self.emoji and self.label:
            # Add default emoji based on button style
            emoji_map = {
                discord.ButtonStyle.primary: "🔵",
                discord.ButtonStyle.secondary: "⚪",
                discord.ButtonStyle.success: "✅",
                discord.ButtonStyle.danger: "❌",
                discord.ButtonStyle.link: "🔗"
            }
            self.emoji = emoji_map.get(self.style, "⚪")


class MobileOptimizedSelect(discord.ui.Select):
    """Select dropdown optimized for mobile interfaces."""
    
    def __init__(self,
                 *,
                 custom_id: Optional[str] = None,
                 placeholder: Optional[str] = None,
                 min_values: int = 1,
                 max_values: int = 1,
                 options: List[discord.SelectOption] = None,
                 disabled: bool = False,
                 row: Optional[int] = None):
        
        # Limit options for mobile (Discord mobile has scrolling issues with many options)
        if options and len(options) > 15:
            options = options[:15]
            logger.warning("Truncated select options to 15 for mobile optimization")
        
        # Optimize placeholder text
        if placeholder and len(placeholder) > 50:
            placeholder = placeholder[:47] + "..."
        
        super().__init__(
            custom_id=custom_id,
            placeholder=placeholder or "Select an option...",
            min_values=min_values,
            max_values=max_values,
            options=options or [],
            disabled=disabled,
            row=row
        )
        
        self.mobile_optimized = True
    
    def apply_mobile_optimizations(self):
        """Apply mobile-specific optimizations."""
        # Ensure all options have emojis for better visual distinction
        for option in self.options:
            if not option.emoji:
                # Add default emoji based on option position
                emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
                idx = self.options.index(option)
                if idx < len(emojis):
                    option.emoji = emojis[idx]


class MobileOptimizedModal(discord.ui.Modal):
    """Modal optimized for mobile input."""
    
    def __init__(self, *, title: str, timeout: Optional[float] = 300):
        # Shorten title for mobile
        if len(title) > 30:
            title = title[:27] + "..."
        
        super().__init__(title=title, timeout=timeout)
        self.mobile_optimized = True
    
    def add_item(self, item: discord.ui.Item) -> None:
        """Override to apply mobile optimizations to text inputs."""
        if hasattr(item, 'placeholder') and hasattr(item, 'max_length'):
            self._optimize_text_input(item)
        super().add_item(item)
    
    def _optimize_text_input(self, text_input):
        """Optimize text input for mobile."""
        # Shorten placeholder text
        if text_input.placeholder and len(text_input.placeholder) > 60:
            text_input.placeholder = text_input.placeholder[:57] + "..."
        
        # Adjust max length for mobile typing
        if text_input.max_length and text_input.max_length > 500:
            text_input.max_length = 500
        
        # Provide mobile-friendly default values
        if not text_input.default and text_input.label:
            if "date" in text_input.label.lower():
                text_input.placeholder = "YYYY-MM-DD (e.g., 2024-12-25)"
            elif "time" in text_input.label.lower():
                text_input.placeholder = "HH:MM AM/PM (e.g., 7:30 PM)"


class MobileFriendlyPollView(MobileOptimizedView):
    """Poll view specifically optimized for mobile voting."""
    
    def __init__(self, poll_data: Dict[str, Any], event_data: Dict[str, Any]):
        super().__init__(timeout=600)  # Longer timeout for polls
        self.poll_data = poll_data
        self.event_data = event_data
        self.votes = {}
        
        self._setup_poll_components()
    
    def _setup_poll_components(self):
        """Set up mobile-optimized poll components."""
        poll_type = self.poll_data.get('type', 'date')
        options = self.poll_data.get('options', [])
        
        if poll_type == 'date':
            self._setup_date_poll(options)
        elif poll_type == 'time':
            self._setup_time_poll(options)
        elif poll_type == 'game':
            self._setup_game_poll(options)
    
    def _setup_date_poll(self, options: List[Dict]):
        """Set up mobile-optimized date poll."""
        # Limit to 4 buttons per row for mobile
        for i, option in enumerate(options[:20]):  # Discord limit
            row = i // 4
            
            button = MobileOptimizedButton(
                label=self._format_date_label(option),
                emoji="📅",
                custom_id=f"date_vote_{i}",
                style=discord.ButtonStyle.secondary,
                row=row,
                mobile_priority=i
            )
            
            # Create callback for this specific option
            async def date_callback(interaction: discord.Interaction, option_data=option, option_index=i):
                await self._handle_vote(interaction, option_data, option_index)
            
            button.callback = date_callback
            self.add_item(button)
        
        # Add management buttons on separate row
        self._add_management_buttons()
    
    def _setup_time_poll(self, options: List[Dict]):
        """Set up mobile-optimized time poll."""
        # Use dropdown for time selection (better for mobile)
        if len(options) <= 25:  # Discord limit
            select_options = []
            for i, option in enumerate(options):
                select_options.append(discord.SelectOption(
                    label=self._format_time_label(option),
                    value=str(i),
                    emoji="🕐",
                    description=f"Vote for {option.get('display_time', 'this time')}"
                ))
            
            select = MobileOptimizedSelect(
                placeholder="Select your preferred time...",
                options=select_options,
                custom_id="time_vote_select",
                row=0
            )
            
            async def time_callback(interaction: discord.Interaction):
                selected_index = int(select.values[0])
                option_data = options[selected_index]
                await self._handle_vote(interaction, option_data, selected_index)
            
            select.callback = time_callback
            self.add_item(select)
        else:
            # Fall back to buttons if too many options
            self._setup_date_poll(options)  # Reuse date poll logic
        
        self._add_management_buttons()
    
    def _setup_game_poll(self, options: List[Dict]):
        """Set up mobile-optimized game poll."""
        # Use select dropdown for games (better for mobile scrolling)
        if len(options) <= 25:
            select_options = []
            for i, option in enumerate(options):
                select_options.append(discord.SelectOption(
                    label=option.get('name', f'Game {i+1}')[:100],  # Discord limit
                    value=str(i),
                    emoji="🎮",
                    description=option.get('description', 'Vote for this game')[:100]
                ))
            
            select = MobileOptimizedSelect(
                placeholder="Select games you'd like to play...",
                options=select_options,
                min_values=1,
                max_values=min(len(options), 5),  # Allow multiple selections
                custom_id="game_vote_select",
                row=0
            )
            
            async def game_callback(interaction: discord.Interaction):
                selected_indices = [int(val) for val in select.values]
                selected_games = [options[i] for i in selected_indices]
                await self._handle_multi_vote(interaction, selected_games, selected_indices)
            
            select.callback = game_callback
            self.add_item(select)
        
        self._add_management_buttons()
    
    def _add_management_buttons(self):
        """Add poll management buttons optimized for mobile."""
        # Results button
        results_btn = MobileOptimizedButton(
            label="Results",
            emoji="📊",
            style=discord.ButtonStyle.primary,
            custom_id="show_results",
            row=4  # Bottom row
        )
        
        async def results_callback(interaction: discord.Interaction):
            await self._show_results(interaction)
        
        results_btn.callback = results_callback
        self.add_item(results_btn)
        
        # Refresh button
        refresh_btn = MobileOptimizedButton(
            label="Refresh",
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            custom_id="refresh_poll",
            row=4
        )
        
        async def refresh_callback(interaction: discord.Interaction):
            await self._refresh_poll(interaction)
        
        refresh_btn.callback = refresh_callback
        self.add_item(refresh_btn)
    
    def _format_date_label(self, option: Dict) -> str:
        """Format date label for mobile display."""
        date_str = option.get('date', '')
        if isinstance(date_str, str):
            try:
                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                return date_obj.strftime('%m/%d')  # Short format for mobile
            except:
                pass
        return date_str[:10]  # Fallback
    
    def _format_time_label(self, option: Dict) -> str:
        """Format time label for mobile display."""
        time_str = option.get('time', '')
        display_time = option.get('display_time', time_str)
        return display_time[:20]  # Limit length for mobile
    
    async def _handle_vote(self, interaction: discord.Interaction, option_data: Dict, option_index: int):
        """Handle a single vote with mobile-optimized feedback."""
        user_id = str(interaction.user.id)
        
        # Toggle vote
        if user_id in self.votes and self.votes[user_id] == option_index:
            del self.votes[user_id]
            action = "removed"
        else:
            self.votes[user_id] = option_index
            action = "recorded"
        
        # Mobile-friendly response
        embed = discord.Embed(
            title="✅ Vote Updated",
            description=f"Your vote has been {action}!",
            color=0x1cc88a
        )
        embed.set_footer(text="Tap 'Results' to see current standings")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _handle_multi_vote(self, interaction: discord.Interaction, selected_options: List[Dict], indices: List[int]):
        """Handle multiple votes (for game polls)."""
        user_id = str(interaction.user.id)
        self.votes[user_id] = indices
        
        game_names = [opt.get('name', f'Game {i+1}') for opt in selected_options]
        
        embed = discord.Embed(
            title="✅ Votes Recorded",
            description=f"You voted for: {', '.join(game_names[:3])}{'...' if len(game_names) > 3 else ''}",
            color=0x1cc88a
        )
        embed.set_footer(text="Tap 'Results' to see current standings")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _show_results(self, interaction: discord.Interaction):
        """Show poll results in mobile-friendly format."""
        if not self.votes:
            embed = discord.Embed(
                title="📊 Poll Results",
                description="No votes yet! Be the first to vote.",
                color=0x36b9cc
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Count votes
        vote_counts = {}
        for user_votes in self.votes.values():
            if isinstance(user_votes, list):
                # Multi-vote (games)
                for vote in user_votes:
                    vote_counts[vote] = vote_counts.get(vote, 0) + 1
            else:
                # Single vote
                vote_counts[user_votes] = vote_counts.get(user_votes, 0) + 1
        
        # Create mobile-friendly results
        embed = discord.Embed(
            title="📊 Current Results",
            color=0x4e73df
        )
        
        options = self.poll_data.get('options', [])
        sorted_results = sorted(vote_counts.items(), key=lambda x: x[1], reverse=True)
        
        results_text = ""
        for i, (option_index, count) in enumerate(sorted_results[:10]):  # Top 10 for mobile
            if option_index < len(options):
                option = options[option_index]
                if self.poll_data.get('type') == 'date':
                    label = self._format_date_label(option)
                elif self.poll_data.get('type') == 'time':
                    label = self._format_time_label(option)
                else:
                    label = option.get('name', f'Option {option_index + 1}')
                
                # Mobile-friendly progress bar
                bar_length = min(count, 10)
                bar = "█" * bar_length + "░" * (10 - bar_length)
                results_text += f"{label}: {count} vote{'s' if count != 1 else ''}\n{bar}\n\n"
        
        embed.description = results_text or "No results to display"
        embed.set_footer(text=f"Total votes: {sum(vote_counts.values())}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _refresh_poll(self, interaction: discord.Interaction):
        """Refresh poll data."""
        embed = discord.Embed(
            title="🔄 Poll Refreshed",
            description="Poll data has been updated!",
            color=0x36b9cc
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class MobileQuickActionView(MobileOptimizedView):
    """Quick action view for common mobile shortcuts."""
    
    def __init__(self):
        super().__init__(timeout=180)  # Shorter timeout for quick actions
        self._setup_quick_actions()
    
    def _setup_quick_actions(self):
        """Set up mobile quick action buttons."""
        actions = [
            ("📅 New Event", "create_event", discord.ButtonStyle.primary),
            ("👥 My Events", "my_events", discord.ButtonStyle.secondary),
            ("🎮 Games", "manage_games", discord.ButtonStyle.secondary),
            ("⚙️ Settings", "user_settings", discord.ButtonStyle.secondary),
            ("📊 Stats", "view_stats", discord.ButtonStyle.secondary),
            ("❓ Help", "show_help", discord.ButtonStyle.secondary)
        ]
        
        for i, (label, action, style) in enumerate(actions):
            row = i // 3  # 3 buttons per row for mobile
            
            button = MobileOptimizedButton(
                label=label,
                style=style,
                custom_id=action,
                row=row
            )
            
            # Create callback for this action
            async def action_callback(interaction: discord.Interaction, action_type=action):
                await self._handle_quick_action(interaction, action_type)
            
            button.callback = action_callback
            self.add_item(button)
    
    async def _handle_quick_action(self, interaction: discord.Interaction, action_type: str):
        """Handle quick action selection."""
        action_messages = {
            "create_event": "Use `/gn event create` to create a new event!",
            "my_events": "Use `/gn user events` to see your events!",
            "manage_games": "Use `/gn games list` to manage your game interests!",
            "user_settings": "Use `/gn user preferences` to update your settings!",
            "view_stats": "Use `/gn user stats` to view your statistics!",
            "show_help": "Use `/gn help` for a complete command list!"
        }
        
        message = action_messages.get(action_type, "Action not available")
        
        embed = discord.Embed(
            title="🚀 Quick Action",
            description=message,
            color=0x4e73df
        )
        embed.set_footer(text="Tip: Save frequently used commands to your mobile keyboard shortcuts")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


def create_mobile_optimized_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    """Create an embed optimized for mobile viewing."""
    # Limit title length for mobile
    if len(title) > 50:
        title = title[:47] + "..."
    
    # Limit description length for mobile
    if description and len(description) > 1000:
        description = description[:997] + "..."
    
    embed = discord.Embed(title=title, description=description, **kwargs)
    
    # Set mobile-friendly footer
    embed.set_footer(text="📱 Optimized for mobile Discord")
    
    return embed


def get_mobile_user_agent_info(interaction: discord.Interaction) -> Dict[str, bool]:
    """Detect if user is on mobile Discord client."""
    # This is a placeholder - Discord doesn't provide user agent info
    # In practice, we optimize for mobile by default
    return {
        "is_mobile": True,  # Assume mobile for better UX
        "is_ios": False,
        "is_android": False
    }