"""
Accessibility preferences and features for users.
"""

import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

import discord
from discord.ext import commands

from core.accessibility_enhancements import accessibility_manager, AccessibilityLevel
from core.enhanced_user_feedback import EnhancedUserFeedback, FeedbackType
from utils.logging_config import get_logger, LoggerMixin


class AccessibilityPreferencesModal(discord.ui.Modal):
    """Modal for setting accessibility preferences."""
    
    def __init__(self, cog: 'AccessibilityCog', current_level: AccessibilityLevel):
        super().__init__(title="Accessibility Preferences")
        self.cog = cog
        
        self.level_input = discord.ui.TextInput(
            label="Accessibility Level (BASIC/ENHANCED/FULL)",
            placeholder="Choose your preferred accessibility level",
            default=current_level.value.upper(),
            min_length=4,
            max_length=8,
            required=True
        )
        self.add_item(self.level_input)
        
        self.screen_reader_input = discord.ui.TextInput(
            label="Using Screen Reader? (YES/NO)",
            placeholder="Do you use a screen reader?",
            default="NO",
            min_length=2,
            max_length=3,
            required=False
        )
        self.add_item(self.screen_reader_input)
        
        self.high_contrast_input = discord.ui.TextInput(
            label="High Contrast Mode? (YES/NO)",
            placeholder="Do you prefer high contrast colors?",
            default="NO",
            min_length=2,
            max_length=3,
            required=False
        )
        self.add_item(self.high_contrast_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle preferences submission."""
        try:
            # Parse accessibility level
            level_str = self.level_input.value.strip().lower()
            try:
                accessibility_level = AccessibilityLevel(level_str)
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid accessibility level. Please use: BASIC, ENHANCED, or FULL",
                    ephemeral=True
                )
                return
            
            # Parse other preferences
            uses_screen_reader = self.screen_reader_input.value.strip().upper() == "YES"
            high_contrast = self.high_contrast_input.value.strip().upper() == "YES"
            
            # Save preferences
            preferences = {
                'accessibility_level': accessibility_level.value,
                'uses_screen_reader': uses_screen_reader,
                'high_contrast': high_contrast,
                'updated_at': datetime.utcnow().isoformat()
            }
            
            accessibility_manager.set_user_accessibility_preferences(
                str(interaction.user.id),
                preferences
            )
            
            # Create success feedback
            feedback = self.cog.feedback_system.create_feedback(
                message="Accessibility preferences updated successfully!",
                feedback_type=FeedbackType.SUCCESS,
                suggestions=[
                    f"Accessibility level set to: {accessibility_level.value.upper()}",
                    "These settings will apply to all bot interactions",
                    "You can change these preferences anytime with /accessibility"
                ]
            )
            
            await self.cog.feedback_system.send_feedback(interaction, feedback)
        
        except Exception as e:
            self.cog.logger.error(f"Error updating accessibility preferences: {e}", exc_info=True)
            feedback = self.cog.feedback_system.from_exception(e)
            await self.cog.feedback_system.send_feedback(interaction, feedback)


class AccessibilityCog(commands.Cog, LoggerMixin):
    """
    Accessibility preferences and features for users.
    
    Allows users to configure accessibility settings like screen reader support,
    high contrast mode, and enhanced descriptions.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.feedback_system = EnhancedUserFeedback()
    
    @commands.slash_command(
        name="accessibility",
        description="Configure accessibility preferences"
    )
    async def accessibility_command(self, interaction: discord.Interaction):
        """Configure accessibility preferences."""
        try:
            user_id = str(interaction.user.id)
            current_level = accessibility_manager.get_user_accessibility_level(user_id)
            
            # Show current preferences
            embed = accessibility_manager.create_accessible_embed(
                title="♿ Accessibility Preferences",
                description="Configure how the bot presents information to you",
                color=discord.Color.blue(),
                user_id=user_id
            )
            
            embed.add_field(
                name="🔧 Current Settings",
                value=f"**Accessibility Level:** {current_level.value.title()}",
                inline=False,
                screen_reader_description=f"Your current accessibility level is {current_level.value}"
            )
            
            embed.add_field(
                name="📋 Accessibility Levels",
                value=(
                    "**BASIC:** Standard Discord interface\n"
                    "**ENHANCED:** Additional descriptions and context\n"
                    "**FULL:** Maximum accessibility features and screen reader support"
                ),
                inline=False,
                screen_reader_description="Three levels available: Basic for standard interface, Enhanced for additional context, Full for maximum accessibility"
            )
            
            embed.add_field(
                name="🎯 Features",
                value=(
                    "• Screen reader friendly descriptions\n"
                    "• Enhanced button and dropdown labels\n"
                    "• Detailed navigation instructions\n"
                    "• Alternative text for complex information"
                ),
                inline=False
            )
            
            view = AccessibilityView(self, current_level)
            
            await accessibility_manager.send_accessible_message(
                interaction,
                embed=embed.build(),
                view=view,
                ephemeral=True,
                user_id=user_id
            )
        
        except Exception as e:
            self.logger.error(f"Error in accessibility command: {e}", exc_info=True)
            feedback = self.feedback_system.from_exception(e)
            await self.feedback_system.send_feedback(interaction, feedback)
    
    @commands.slash_command(
        name="accessibility-test",
        description="Test accessibility features with a sample interface"
    )
    async def accessibility_test_command(self, interaction: discord.Interaction):
        """Test accessibility features."""
        try:
            user_id = str(interaction.user.id)
            
            embed = accessibility_manager.create_accessible_embed(
                title="🧪 Accessibility Test Interface",
                description="This is a test interface to demonstrate accessibility features",
                color=discord.Color.green(),
                user_id=user_id
            )
            
            embed.add_field(
                name="📊 Sample Data",
                value="**Events:** 5 upcoming\n**Games:** 12 in your interests\n**Notifications:** 3 pending",
                inline=True,
                screen_reader_description="Sample statistics showing 5 upcoming events, 12 games in your interests, and 3 pending notifications"
            )
            
            embed.add_field(
                name="🎮 Popular Games",
                value="1. Among Us\n2. Minecraft\n3. Valorant",
                inline=True,
                screen_reader_description="Top 3 popular games: Among Us, Minecraft, and Valorant"
            )
            
            embed.add_accessibility_note("This test interface demonstrates enhanced descriptions and screen reader support")
            
            view = AccessibilityTestView()
            
            await accessibility_manager.send_accessible_message(
                interaction,
                embed=embed.build(),
                view=view,
                ephemeral=True,
                user_id=user_id
            )
        
        except Exception as e:
            self.logger.error(f"Error in accessibility test command: {e}", exc_info=True)
            feedback = self.feedback_system.from_exception(e)
            await self.feedback_system.send_feedback(interaction, feedback)


class AccessibilityView(discord.ui.View):
    """View for accessibility preferences."""
    
    def __init__(self, cog: AccessibilityCog, current_level: AccessibilityLevel):
        super().__init__(timeout=300)
        self.cog = cog
        self.current_level = current_level
    
    @discord.ui.button(
        label="Update Preferences", 
        style=discord.ButtonStyle.primary, 
        emoji="⚙️"
    )
    async def update_preferences(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open preferences modal."""
        modal = AccessibilityPreferencesModal(self.cog, self.current_level)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(
        label="Test Features", 
        style=discord.ButtonStyle.secondary, 
        emoji="🧪"
    )
    async def test_features(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Test accessibility features."""
        await interaction.response.defer()
        
        # Create a test interface
        embed = accessibility_manager.create_accessible_embed(
            title="🧪 Feature Test",
            description="Testing accessibility features with your current settings",
            color=discord.Color.green(),
            user_id=str(interaction.user.id)
        )
        
        embed.add_field(
            name="✅ Features Active",
            value=(
                f"• Accessibility Level: {self.current_level.value.title()}\n"
                "• Enhanced descriptions enabled\n"
                "• Screen reader support active\n"
                "• Navigation assistance available"
            ),
            inline=False
        )
        
        await interaction.followup.send(embed=embed.build(), ephemeral=True)


class AccessibilityTestView(discord.ui.View):
    """Test view for accessibility features."""
    
    def __init__(self):
        super().__init__(timeout=300)
        
        # Add various UI components for testing
        from core.accessibility_enhancements import AccessibleButton, AccessibleSelect
        
        # Test button with accessibility features
        test_button = AccessibleButton(
            label="Test Button",
            style=discord.ButtonStyle.primary,
            emoji="🔘",
            aria_label="Test button for accessibility features",
            description="Demonstrates enhanced button accessibility",
            keyboard_shortcut="Alt+T"
        )
        self.add_item(test_button)
        
        # Test select with accessibility features
        test_select = AccessibleSelect(
            placeholder="Choose an option to test",
            aria_label="Test dropdown for accessibility features",
            instructions="Select any option to test dropdown accessibility"
        )
        
        test_select.add_accessible_option(
            label="Option 1",
            value="opt1",
            description="First test option",
            detailed_description="This is the first option in the test dropdown, used to demonstrate accessibility features"
        )
        
        test_select.add_accessible_option(
            label="Option 2", 
            value="opt2",
            description="Second test option",
            detailed_description="This is the second option with enhanced accessibility descriptions"
        )
        
        self.add_item(test_select)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Handle any interaction with test components."""
        await interaction.response.send_message(
            "✅ Accessibility test interaction successful! "
            "This demonstrates that enhanced accessibility features are working.",
            ephemeral=True
        )
        return True


def setup(bot):
    """Set up the accessibility cog."""
    bot.add_cog(AccessibilityCog(bot))