"""
Mobile UI Cog - Provides mobile-optimized Discord UI components and commands.

This cog demonstrates and provides mobile-friendly Discord interactions,
optimized for touch interfaces and mobile Discord clients.
"""

import discord
from discord.ext import commands
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import asyncio
import logging

from utils.mobile_ui_components import (
    MobileOptimizedView, MobileOptimizedButton, MobileOptimizedSelect,
    MobileOptimizedModal, MobileFriendlyPollView, MobileQuickActionView,
    create_mobile_optimized_embed, get_mobile_user_agent_info
)
from utils.logging_config import get_logger, LoggerMixin
from core.permission_decorators import require_permissions


class MobileUICog(commands.Cog, LoggerMixin):
    """Cog providing mobile-optimized UI components and commands."""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = get_logger(__name__)
        self.mobile_sessions = {}  # Track mobile user sessions
    
    @commands.slash_command(
        name="mobile",
        description="Access mobile-optimized features and quick actions"
    )
    async def mobile_command(self, ctx: discord.ApplicationContext):
        """Main mobile command with quick actions."""
        try:
            # Detect if user might be on mobile
            mobile_info = get_mobile_user_agent_info(ctx.interaction)
            
            # Create mobile-optimized embed
            embed = create_mobile_optimized_embed(
                title="🎮 Game Night Mobile Hub",
                description="Quick access to all Game Night Bot features, optimized for mobile Discord.",
                color=0x4e73df
            )
            
            embed.add_field(
                name="📱 Mobile Features",
                value="• Touch-optimized buttons\n• Simplified navigation\n• Quick actions\n• Swipe gestures",
                inline=True
            )
            
            embed.add_field(
                name="🚀 Quick Actions",
                value="• Create events\n• View your events\n• Manage games\n• Update preferences",
                inline=True
            )
            
            # Add mobile-specific tips
            if mobile_info.get("is_mobile", True):
                embed.add_field(
                    name="💡 Mobile Tips",
                    value="• Use buttons instead of typing commands\n• Swipe to navigate\n• Long press for options",
                    inline=False
                )
            
            # Create mobile quick action view
            view = MobileQuickActionView()
            
            await ctx.respond(embed=embed, view=view, ephemeral=True)
            
            self.logger.info(f"Mobile hub accessed by {ctx.author.id}")
            
        except Exception as e:
            self.logger.error(f"Error in mobile command: {e}")
            await ctx.respond(
                "❌ An error occurred while loading the mobile hub. Please try again.",
                ephemeral=True
            )
    
    @commands.slash_command(
        name="mobile-poll",
        description="Create a mobile-optimized poll for testing"
    )
    @require_permissions(['manage_events'])
    async def mobile_poll_command(
        self, 
        ctx: discord.ApplicationContext,
        title: str = "Sample Mobile Poll",
        poll_type: str = commands.Option(
            str,
            description="Type of poll to create",
            choices=["date", "time", "game"]
        ) = "date"
    ):
        """Create a mobile-optimized poll for demonstration."""
        try:
            # Create sample poll data
            if poll_type == "date":
                options = [
                    {"date": "2024-12-20", "display_date": "Dec 20"},
                    {"date": "2024-12-21", "display_date": "Dec 21"},
                    {"date": "2024-12-22", "display_date": "Dec 22"},
                    {"date": "2024-12-23", "display_date": "Dec 23"}
                ]
            elif poll_type == "time":
                options = [
                    {"time": "19:00", "display_time": "7:00 PM"},
                    {"time": "19:30", "display_time": "7:30 PM"},
                    {"time": "20:00", "display_time": "8:00 PM"},
                    {"time": "20:30", "display_time": "8:30 PM"}
                ]
            else:  # game
                options = [
                    {"name": "Among Us", "description": "Social deduction game"},
                    {"name": "Minecraft", "description": "Sandbox building game"},
                    {"name": "Rocket League", "description": "Car soccer game"},
                    {"name": "Fall Guys", "description": "Party battle royale"}
                ]
            
            poll_data = {
                "type": poll_type,
                "title": title,
                "options": options,
                "created_at": datetime.utcnow().isoformat()
            }
            
            event_data = {
                "title": f"Mobile Test Event - {title}",
                "description": "This is a test event to demonstrate mobile-optimized polling.",
                "creator_id": str(ctx.author.id)
            }
            
            # Create mobile-friendly poll view
            view = MobileFriendlyPollView(poll_data, event_data)
            
            # Create mobile-optimized embed
            embed = create_mobile_optimized_embed(
                title=f"📊 {title}",
                description=f"Mobile-optimized {poll_type} poll. Tap the buttons below to vote!",
                color=0x36b9cc
            )
            
            embed.add_field(
                name="📱 Mobile Features",
                value="• Large touch targets\n• Clear visual feedback\n• Simplified interface",
                inline=True
            )
            
            embed.add_field(
                name="🗳️ How to Vote",
                value="• Tap your preferred option\n• Tap again to remove vote\n• View results anytime",
                inline=True
            )
            
            embed.set_footer(text="This poll demonstrates mobile-optimized Discord UI")
            
            await ctx.respond(embed=embed, view=view)
            
            self.logger.info(f"Mobile poll created by {ctx.author.id}: {poll_type}")
            
        except Exception as e:
            self.logger.error(f"Error creating mobile poll: {e}")
            await ctx.respond(
                "❌ Failed to create mobile poll. Please try again.",
                ephemeral=True
            )
    
    @commands.slash_command(
        name="mobile-test",
        description="Test mobile UI components and responsiveness"
    )
    async def mobile_test_command(self, ctx: discord.ApplicationContext):
        """Test various mobile UI components."""
        try:
            # Create test view with various mobile components
            view = MobileTestView()
            
            embed = create_mobile_optimized_embed(
                title="🧪 Mobile UI Test Suite",
                description="Test various mobile-optimized Discord UI components.",
                color=0xf6c23e
            )
            
            embed.add_field(
                name="🔘 Test Components",
                value="• Buttons with touch feedback\n• Dropdowns with limited options\n• Modals with mobile keyboards\n• Responsive layouts",
                inline=False
            )
            
            embed.add_field(
                name="📏 Design Principles",
                value="• 44px minimum touch targets\n• Clear visual hierarchy\n• Reduced cognitive load\n• Thumb-friendly placement",
                inline=False
            )
            
            await ctx.respond(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in mobile test: {e}")
            await ctx.respond(
                "❌ Mobile test failed. Please try again.",
                ephemeral=True
            )
    
    @commands.slash_command(
        name="mobile-feedback",
        description="Provide feedback on mobile experience"
    )
    async def mobile_feedback_command(self, ctx: discord.ApplicationContext):
        """Collect mobile user feedback."""
        try:
            modal = MobileFeedbackModal()
            await ctx.response.send_modal(modal)
            
        except Exception as e:
            self.logger.error(f"Error showing feedback modal: {e}")
            await ctx.respond(
                "❌ Failed to show feedback form. Please try again.",
                ephemeral=True
            )


class MobileTestView(MobileOptimizedView):
    """View for testing mobile UI components."""
    
    def __init__(self):
        super().__init__(timeout=300)
        self._setup_test_components()
    
    def _setup_test_components(self):
        """Set up various test components."""
        # Test buttons with different styles
        styles = [
            (discord.ButtonStyle.primary, "Primary", "🔵"),
            (discord.ButtonStyle.secondary, "Secondary", "⚪"),
            (discord.ButtonStyle.success, "Success", "✅"),
            (discord.ButtonStyle.danger, "Danger", "❌")
        ]
        
        for i, (style, label, emoji) in enumerate(styles):
            button = MobileOptimizedButton(
                label=label,
                style=style,
                emoji=emoji,
                custom_id=f"test_button_{i}",
                row=0
            )
            
            async def button_callback(interaction: discord.Interaction, btn_label=label):
                await self._handle_button_test(interaction, btn_label)
            
            button.callback = button_callback
            self.add_item(button)
        
        # Test dropdown
        options = [
            discord.SelectOption(label="Option 1", emoji="1️⃣", description="First test option"),
            discord.SelectOption(label="Option 2", emoji="2️⃣", description="Second test option"),
            discord.SelectOption(label="Option 3", emoji="3️⃣", description="Third test option")
        ]
        
        select = MobileOptimizedSelect(
            placeholder="Test dropdown selection...",
            options=options,
            custom_id="test_select",
            row=1
        )
        
        async def select_callback(interaction: discord.Interaction):
            await self._handle_select_test(interaction)
        
        select.callback = select_callback
        self.add_item(select)
        
        # Test modal button
        modal_button = MobileOptimizedButton(
            label="Test Modal",
            emoji="📝",
            style=discord.ButtonStyle.secondary,
            custom_id="test_modal",
            row=2
        )
        
        async def modal_callback(interaction: discord.Interaction):
            await self._handle_modal_test(interaction)
        
        modal_button.callback = modal_callback
        self.add_item(modal_button)
    
    async def _handle_button_test(self, interaction: discord.Interaction, button_label: str):
        """Handle button test interaction."""
        embed = create_mobile_optimized_embed(
            title="✅ Button Test",
            description=f"You tapped the **{button_label}** button!",
            color=0x1cc88a
        )
        embed.add_field(
            name="📱 Mobile Feedback",
            value="• Button registered touch correctly\n• Visual feedback provided\n• Response time optimized",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _handle_select_test(self, interaction: discord.Interaction):
        """Handle select test interaction."""
        selected = interaction.data['values'][0]
        
        embed = create_mobile_optimized_embed(
            title="📋 Dropdown Test",
            description=f"You selected: **{selected}**",
            color=0x36b9cc
        )
        embed.add_field(
            name="📱 Mobile Experience",
            value="• Dropdown opened correctly\n• Options clearly visible\n• Selection registered",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _handle_modal_test(self, interaction: discord.Interaction):
        """Handle modal test interaction."""
        modal = MobileTestModal()
        await interaction.response.send_modal(modal)


class MobileTestModal(MobileOptimizedModal):
    """Modal for testing mobile input."""
    
    def __init__(self):
        super().__init__(title="Mobile Input Test")
        
        self.text_input = discord.ui.TextInput(
            label="Test Input",
            placeholder="Type something to test mobile keyboard...",
            style=discord.TextStyle.short,
            max_length=100,
            required=True
        )
        self.add_item(self.text_input)
        
        self.feedback_input = discord.ui.TextInput(
            label="Experience Rating",
            placeholder="Rate your mobile experience (1-5)",
            style=discord.TextStyle.short,
            max_length=1,
            required=False
        )
        self.add_item(self.feedback_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        user_input = self.text_input.value
        rating = self.feedback_input.value or "Not provided"
        
        embed = create_mobile_optimized_embed(
            title="📝 Modal Test Complete",
            description="Mobile keyboard input test successful!",
            color=0x1cc88a
        )
        
        embed.add_field(
            name="Your Input",
            value=f"```{user_input}```",
            inline=False
        )
        
        embed.add_field(
            name="Experience Rating",
            value=rating,
            inline=True
        )
        
        embed.add_field(
            name="📱 Mobile Keyboard",
            value="• Keyboard appeared correctly\n• Input registered properly\n• Modal responsive",
            inline=True
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class MobileFeedbackModal(MobileOptimizedModal):
    """Modal for collecting mobile user feedback."""
    
    def __init__(self):
        super().__init__(title="Mobile Experience Feedback")
        
        self.experience_input = discord.ui.TextInput(
            label="Overall Experience (1-5)",
            placeholder="Rate your mobile Discord experience...",
            style=discord.TextStyle.short,
            max_length=1,
            required=True
        )
        self.add_item(self.experience_input)
        
        self.feedback_input = discord.ui.TextInput(
            label="Feedback & Suggestions",
            placeholder="What could be improved for mobile users?",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=False
        )
        self.add_item(self.feedback_input)
        
        self.device_input = discord.ui.TextInput(
            label="Device Type",
            placeholder="e.g., iPhone 14, Samsung Galaxy S23, iPad...",
            style=discord.TextStyle.short,
            max_length=50,
            required=False
        )
        self.add_item(self.device_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle feedback submission."""
        rating = self.experience_input.value
        feedback = self.feedback_input.value or "No additional feedback"
        device = self.device_input.value or "Not specified"
        
        # Log feedback for analysis
        logger = logging.getLogger(__name__)
        logger.info(f"Mobile feedback received from {interaction.user.id}: "
                   f"Rating={rating}, Device={device}, Feedback={feedback}")
        
        embed = create_mobile_optimized_embed(
            title="🙏 Thank You for Your Feedback!",
            description="Your mobile experience feedback has been recorded.",
            color=0x1cc88a
        )
        
        embed.add_field(
            name="Your Rating",
            value=f"⭐ {rating}/5",
            inline=True
        )
        
        embed.add_field(
            name="Device",
            value=device,
            inline=True
        )
        
        embed.add_field(
            name="📱 Continuous Improvement",
            value="We use this feedback to improve the mobile Discord experience for all users.",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


def setup(bot):
    """Set up the Mobile UI cog."""
    bot.add_cog(MobileUICog(bot))