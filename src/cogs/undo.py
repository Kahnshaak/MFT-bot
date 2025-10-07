"""
Undo functionality for recent user actions.
"""

import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

import discord
from discord.ext import commands

from core.confirmation_system import confirmation_manager, UndoView
from core.enhanced_user_feedback import EnhancedUserFeedback, FeedbackType
from core.accessibility_enhancements import accessibility_manager
from utils.logging_config import get_logger, LoggerMixin


class UndoCog(commands.Cog, LoggerMixin):
    """
    Undo functionality for recent user actions.
    
    Allows users to undo recent destructive actions like event cancellations,
    schedule deletions, and other reversible operations.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.confirmation_manager = confirmation_manager
        self.feedback_system = EnhancedUserFeedback()
    
    @commands.slash_command(
        name="undo",
        description="Undo recent actions you've performed"
    )
    async def undo_command(self, interaction: discord.Interaction):
        """Show available undo actions for the user."""
        try:
            user_id = str(interaction.user.id)
            guild_id = str(interaction.guild.id)
            
            # Get available undo actions for this user
            undo_actions = self.confirmation_manager.get_user_undo_actions(user_id, guild_id)
            
            if not undo_actions:
                feedback = self.feedback_system.create_feedback(
                    message="No recent actions can be undone",
                    feedback_type=FeedbackType.INFO,
                    suggestions=[
                        "Undo actions expire after 30 minutes",
                        "Only certain destructive actions can be undone",
                        "Actions you perform will appear here if they're undoable"
                    ]
                )
                await self.feedback_system.send_feedback(interaction, feedback)
                return
            
            # Create undo view
            view = UndoView(self.confirmation_manager, undo_actions)
            embed = view.create_embed()
            
            await accessibility_manager.send_accessible_message(
                interaction,
                embed=embed,
                view=view,
                ephemeral=True,
                user_id=user_id
            )
        
        except Exception as e:
            self.logger.error(f"Error in undo command: {e}", exc_info=True)
            feedback = self.feedback_system.from_exception(e)
            await self.feedback_system.send_feedback(interaction, feedback)
    
    @commands.slash_command(
        name="undo-history",
        description="View your recent action history"
    )
    async def undo_history_command(self, interaction: discord.Interaction):
        """Show user's recent action history."""
        try:
            user_id = str(interaction.user.id)
            guild_id = str(interaction.guild.id)
            
            # Get all undo actions (including expired ones) for history
            all_actions = []
            for action in self.confirmation_manager.undo_actions.values():
                if (action.user_id == user_id and 
                    action.guild_id == guild_id):
                    all_actions.append(action)
            
            # Sort by creation time (newest first)
            all_actions.sort(key=lambda x: x.created_at, reverse=True)
            
            embed = accessibility_manager.create_accessible_embed(
                title="📜 Your Action History",
                description="Recent actions you've performed:",
                color=discord.Color.blue(),
                user_id=user_id
            )
            
            if not all_actions:
                embed.add_field(
                    name="No History",
                    value="You haven't performed any tracked actions yet.",
                    inline=False
                )
            else:
                for i, action in enumerate(all_actions[:10]):  # Show last 10 actions
                    time_ago = datetime.utcnow() - action.created_at
                    minutes_ago = int(time_ago.total_seconds() / 60)
                    
                    status_emoji = "✅" if action.is_undone else ("❌" if action.is_expired() else "⏳")
                    status_text = "Undone" if action.is_undone else ("Expired" if action.is_expired() else "Available")
                    
                    embed.add_field(
                        name=f"{i+1}. {action.description}",
                        value=(
                            f"**Type:** {action.action_type}\n"
                            f"**Time:** {minutes_ago} minutes ago\n"
                            f"**Status:** {status_emoji} {status_text}"
                        ),
                        inline=True
                    )
            
            embed.set_footer(text="Use /undo to undo available actions")
            
            await interaction.response.send_message(embed=embed.build(), ephemeral=True)
        
        except Exception as e:
            self.logger.error(f"Error in undo history command: {e}", exc_info=True)
            feedback = self.feedback_system.from_exception(e)
            await self.feedback_system.send_feedback(interaction, feedback)


def setup(bot):
    """Set up the undo cog."""
    bot.add_cog(UndoCog(bot))