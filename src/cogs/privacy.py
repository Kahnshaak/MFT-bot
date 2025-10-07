"""
Privacy cog for GDPR compliance and data protection commands.
"""

import discord
from discord.ext import commands
from typing import Optional

try:
    from utils.logging_config import LoggerMixin
    from utils.error_handler import discord_error_handler
    from core.privacy_manager import PrivacyManager, ConsentType, DataExportFormat
    from core.audit_logger import AuditLogger
    from database.manager import DatabaseManager
except ImportError:
    from src.utils.logging_config import LoggerMixin
    from src.utils.error_handler import discord_error_handler
    from src.core.privacy_manager import PrivacyManager, ConsentType, DataExportFormat
    from src.core.audit_logger import AuditLogger
    from src.database.manager import DatabaseManager


class PrivacyCog(commands.Cog, LoggerMixin):
    """
    Privacy and data protection commands for GDPR compliance.
    
    Provides commands for:
    - Managing consent
    - Requesting data exports
    - Updating privacy settings
    - Data deletion requests
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.database: DatabaseManager = bot.database
        self.audit_logger: AuditLogger = bot.audit_logger
        self.privacy_manager = PrivacyManager(self.database, self.audit_logger)
    
    @discord.slash_command(
        name="privacy_settings",
        description="View and update your privacy settings"
    )
    @discord_error_handler
    async def privacy_settings(
        self,
        ctx: discord.ApplicationContext,
        profile_public: Optional[bool] = None,
        stats_public: Optional[bool] = None,
        allow_game_pings: Optional[bool] = None,
        allow_notifications: Optional[bool] = None,
        allow_analytics: Optional[bool] = None
    ):
        """
        View or update privacy settings.
        
        Args:
            profile_public: Make profile visible to other users
            stats_public: Make statistics visible to other users
            allow_game_pings: Allow game ping notifications
            allow_notifications: Allow event notifications
            allow_analytics: Allow analytics data collection
        """
        await ctx.defer()
        
        user_id = str(ctx.author.id)
        guild_id = str(ctx.guild.id)
        
        # If no parameters provided, show current settings
        if all(param is None for param in [profile_public, stats_public, allow_game_pings, allow_notifications, allow_analytics]):
            current_settings = await self.privacy_manager.get_privacy_settings(user_id, guild_id)
            consents = await self.privacy_manager.get_all_user_consents(user_id, guild_id)
            
            embed = discord.Embed(
                title="🔒 Your Privacy Settings",
                description="Current privacy and consent settings",
                color=discord.Color.blue()
            )
            
            # Privacy settings
            embed.add_field(
                name="Profile Settings",
                value=f"**Profile Public:** {'✅ Yes' if current_settings.get('profile_public', True) else '❌ No'}\n"
                      f"**Stats Public:** {'✅ Yes' if current_settings.get('stats_public', True) else '❌ No'}",
                inline=True
            )
            
            embed.add_field(
                name="Notification Settings",
                value=f"**Game Pings:** {'✅ Enabled' if current_settings.get('allow_game_pings', True) else '❌ Disabled'}\n"
                      f"**Event Notifications:** {'✅ Enabled' if current_settings.get('allow_event_notifications', True) else '❌ Disabled'}",
                inline=True
            )
            
            embed.add_field(
                name="Data Collection",
                value=f"**Analytics:** {'✅ Allowed' if current_settings.get('allow_analytics_tracking', True) else '❌ Blocked'}",
                inline=True
            )
            
            # Consent status
            if consents:
                consent_text = []
                for consent_type, granted in consents.items():
                    status = "✅ Granted" if granted else "❌ Denied"
                    consent_text.append(f"**{consent_type.replace('_', ' ').title()}:** {status}")
                
                embed.add_field(
                    name="Consent Status",
                    value="\n".join(consent_text),
                    inline=False
                )
            
            embed.add_field(
                name="Your Rights",
                value="• Request data export: `/privacy export`\n"
                      "• Delete your data: `/privacy delete`\n"
                      "• Update settings: Use the parameters above\n"
                      "• Manage consent: `/privacy consent`",
                inline=False
            )
            
            await ctx.followup.send(embed=embed)
            return
        
        # Update settings
        settings_to_update = {}
        if profile_public is not None:
            settings_to_update["profile_public"] = profile_public
        if stats_public is not None:
            settings_to_update["stats_public"] = stats_public
        if allow_game_pings is not None:
            settings_to_update["allow_game_pings"] = allow_game_pings
        if allow_notifications is not None:
            settings_to_update["allow_event_notifications"] = allow_notifications
        if allow_analytics is not None:
            settings_to_update["allow_analytics_tracking"] = allow_analytics
        
        success = await self.privacy_manager.update_privacy_settings(
            user_id, guild_id, settings_to_update
        )
        
        if success:
            embed = discord.Embed(
                title="✅ Privacy Settings Updated",
                description="Your privacy settings have been updated successfully.",
                color=discord.Color.green()
            )
            
            # Show what was updated
            updated_text = []
            for key, value in settings_to_update.items():
                setting_name = key.replace('_', ' ').replace('allow ', '').title()
                status = "Enabled" if value else "Disabled"
                updated_text.append(f"**{setting_name}:** {status}")
            
            embed.add_field(
                name="Updated Settings",
                value="\n".join(updated_text),
                inline=False
            )
        else:
            embed = discord.Embed(
                title="❌ Update Failed",
                description="Failed to update your privacy settings. Please try again.",
                color=discord.Color.red()
            )
        
        await ctx.followup.send(embed=embed)
    
    @discord.slash_command(
        name="privacy_consent",
        description="Manage your consent for data processing"
    )
    @discord_error_handler
    async def privacy_consent(
        self,
        ctx: discord.ApplicationContext,
        consent_type: discord.Option(
            str,
            description="Type of consent to manage",
            choices=[
                "data_collection",
                "analytics", 
                "notifications",
                "profile_visibility",
                "data_sharing"
            ]
        ),
        granted: discord.Option(
            bool,
            description="Grant or revoke consent"
        )
    ):
        """
        Grant or revoke consent for specific data processing activities.
        
        Args:
            consent_type: Type of consent to manage
            granted: Whether to grant or revoke consent
        """
        await ctx.defer()
        
        user_id = str(ctx.author.id)
        guild_id = str(ctx.guild.id)
        
        try:
            consent_enum = ConsentType(consent_type)
        except ValueError:
            await ctx.followup.send(
                embed=discord.Embed(
                    title="❌ Invalid Consent Type",
                    description=f"'{consent_type}' is not a valid consent type.",
                    color=discord.Color.red()
                )
            )
            return
        
        success = await self.privacy_manager.record_consent(
            user_id=user_id,
            guild_id=guild_id,
            consent_type=consent_enum,
            granted=granted
        )
        
        if success:
            action = "granted" if granted else "revoked"
            embed = discord.Embed(
                title=f"✅ Consent {action.title()}",
                description=f"Your consent for **{consent_type.replace('_', ' ').title()}** has been {action}.",
                color=discord.Color.green() if granted else discord.Color.orange()
            )
            
            if not granted:
                embed.add_field(
                    name="What This Means",
                    value="We will stop processing your data for this purpose. "
                          "Some bot features may be limited as a result.",
                    inline=False
                )
        else:
            embed = discord.Embed(
                title="❌ Consent Update Failed",
                description="Failed to update your consent. Please try again.",
                color=discord.Color.red()
            )
        
        await ctx.followup.send(embed=embed)
    
    @discord.slash_command(
        name="privacy_export",
        description="Request export of your personal data"
    )
    @discord_error_handler
    async def privacy_export(
        self,
        ctx: discord.ApplicationContext,
        format: discord.Option(
            str,
            description="Export format",
            choices=["json", "zip"],
            default="json"
        )
    ):
        """
        Request export of all your personal data.
        
        Args:
            format: Format for the data export (json or zip)
        """
        await ctx.defer()
        
        user_id = str(ctx.author.id)
        guild_id = str(ctx.guild.id)
        
        try:
            export_format = DataExportFormat(format)
        except ValueError:
            export_format = DataExportFormat.JSON
        
        try:
            request_id = await self.privacy_manager.request_data_export(
                user_id=user_id,
                guild_id=guild_id,
                format=export_format
            )
            
            embed = discord.Embed(
                title="📋 Data Export Requested",
                description="Your data export request has been submitted and is being processed.",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Request ID",
                value=f"`{request_id}`",
                inline=False
            )
            
            embed.add_field(
                name="What's Included",
                value="• Your profile and preferences\n"
                      "• Events you created or participated in\n"
                      "• Game interests and notifications\n"
                      "• Consent history\n"
                      "• Recent audit log entries",
                inline=False
            )
            
            embed.add_field(
                name="Next Steps",
                value="• Processing typically takes a few minutes\n"
                      "• Check status with `/privacy export_status`\n"
                      "• Download will be available for 30 days\n"
                      "• You'll receive a DM when ready",
                inline=False
            )
            
            embed.set_footer(text="This fulfills your right to data portability under GDPR")
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Export Request Failed",
                description=f"Failed to request data export: {str(e)}",
                color=discord.Color.red()
            )
        
        await ctx.followup.send(embed=embed)
    
    @discord.slash_command(
        name="privacy_export_status",
        description="Check status of your data export request"
    )
    @discord_error_handler
    async def privacy_export_status(
        self,
        ctx: discord.ApplicationContext,
        request_id: discord.Option(
            str,
            description="Export request ID"
        )
    ):
        """
        Check the status of a data export request.
        
        Args:
            request_id: The request ID from your export request
        """
        await ctx.defer()
        
        status = await self.privacy_manager.get_export_status(request_id)
        
        if not status:
            embed = discord.Embed(
                title="❌ Request Not Found",
                description=f"No export request found with ID `{request_id}`",
                color=discord.Color.red()
            )
        else:
            status_colors = {
                "pending": discord.Color.orange(),
                "processing": discord.Color.blue(),
                "completed": discord.Color.green(),
                "failed": discord.Color.red()
            }
            
            embed = discord.Embed(
                title=f"📋 Export Status: {status['status'].title()}",
                description=f"Status of export request `{request_id}`",
                color=status_colors.get(status['status'], discord.Color.grey())
            )
            
            embed.add_field(
                name="Request Details",
                value=f"**Requested:** {status['requested_at'][:19].replace('T', ' ')}\n"
                      f"**Format:** {status['format'].upper()}\n"
                      f"**Status:** {status['status'].title()}",
                inline=True
            )
            
            if status['status'] == 'completed':
                embed.add_field(
                    name="Download Info",
                    value=f"**Completed:** {status['completed_at'][:19].replace('T', ' ')}\n"
                          f"**Expires:** {status['expires_at'][:19].replace('T', ' ')}\n"
                          f"**Ready for download**",
                    inline=True
                )
                
                embed.add_field(
                    name="How to Download",
                    value="Contact a server administrator to access your export file.",
                    inline=False
                )
            
            elif status['status'] == 'failed':
                embed.add_field(
                    name="Error",
                    value="Export processing failed. Please try requesting a new export.",
                    inline=False
                )
        
        await ctx.followup.send(embed=embed)
    
    @discord.slash_command(
        name="privacy_delete",
        description="Request deletion of all your data (Right to be Forgotten)"
    )
    @discord_error_handler
    async def privacy_delete(
        self,
        ctx: discord.ApplicationContext,
        confirm: discord.Option(
            bool,
            description="Confirm you want to delete ALL your data permanently",
            default=False
        )
    ):
        """
        Request deletion of all your personal data.
        
        Args:
            confirm: Must be True to confirm deletion
        """
        await ctx.defer()
        
        if not confirm:
            embed = discord.Embed(
                title="⚠️ Data Deletion Request",
                description="This will permanently delete ALL your data from this server.",
                color=discord.Color.orange()
            )
            
            embed.add_field(
                name="What Will Be Deleted",
                value="• Your user profile and preferences\n"
                      "• All events you created\n"
                      "• Your RSVPs and attendance records\n"
                      "• Game interests and notifications\n"
                      "• Statistics and analytics data",
                inline=False
            )
            
            embed.add_field(
                name="What Will Be Kept",
                value="• Anonymized event data (for server analytics)\n"
                      "• Consent records (for legal compliance)\n"
                      "• Audit logs (anonymized)",
                inline=False
            )
            
            embed.add_field(
                name="⚠️ This Action Cannot Be Undone",
                value="To confirm deletion, run this command again with `confirm: True`",
                inline=False
            )
            
            embed.set_footer(text="This fulfills your right to erasure under GDPR")
            
            await ctx.followup.send(embed=embed)
            return
        
        user_id = str(ctx.author.id)
        guild_id = str(ctx.guild.id)
        
        try:
            # Show confirmation dialog
            view = ConfirmDeletionView(self.privacy_manager, user_id, guild_id)
            
            embed = discord.Embed(
                title="🗑️ Final Confirmation Required",
                description="**This will permanently delete ALL your data.**\n\n"
                           "Are you absolutely sure you want to proceed?",
                color=discord.Color.red()
            )
            
            embed.add_field(
                name="⚠️ Warning",
                value="This action cannot be undone. You will lose all your:\n"
                      "• Profile data and preferences\n"
                      "• Event history and statistics\n"
                      "• Game interests and settings",
                inline=False
            )
            
            await ctx.followup.send(embed=embed, view=view)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Deletion Request Failed",
                description=f"Failed to process deletion request: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.followup.send(embed=embed)


class ConfirmDeletionView(discord.ui.View):
    """Confirmation view for data deletion."""
    
    def __init__(self, privacy_manager: PrivacyManager, user_id: str, guild_id: str):
        super().__init__(timeout=300)  # 5 minute timeout
        self.privacy_manager = privacy_manager
        self.user_id = user_id
        self.guild_id = guild_id
    
    @discord.ui.button(
        label="Delete My Data",
        style=discord.ButtonStyle.danger,
        emoji="🗑️"
    )
    async def confirm_deletion(self, button: discord.ui.Button, interaction: discord.Interaction):
        """Confirm and execute data deletion."""
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                "❌ Only the user who requested deletion can confirm this action.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        
        try:
            # Execute deletion
            deletion_results = await self.privacy_manager.delete_user_data(
                self.user_id,
                self.guild_id,
                keep_anonymized=True
            )
            
            embed = discord.Embed(
                title="✅ Data Deletion Completed",
                description="Your personal data has been permanently deleted.",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="Deletion Summary",
                value=f"**Records Deleted:** {deletion_results['deleted_records']}\n"
                      f"**Records Anonymized:** {deletion_results['anonymized_records']}\n"
                      f"**Completed At:** {deletion_results['deleted_at'][:19].replace('T', ' ')}",
                inline=False
            )
            
            embed.add_field(
                name="What Happened",
                value="• Your profile and personal data were deleted\n"
                      "• Events you created were anonymized\n"
                      "• Your RSVPs were removed from events\n"
                      "• Consent records were marked as deleted user",
                inline=False
            )
            
            embed.set_footer(text="Your right to erasure has been fulfilled")
            
            # Disable all buttons
            for item in self.children:
                item.disabled = True
            
            await interaction.edit_original_response(embed=embed, view=self)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Deletion Failed",
                description=f"Failed to delete your data: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=embed, view=self)
    
    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        emoji="❌"
    )
    async def cancel_deletion(self, button: discord.ui.Button, interaction: discord.Interaction):
        """Cancel data deletion."""
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                "❌ Only the user who requested deletion can cancel this action.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="❌ Deletion Cancelled",
            description="Your data deletion request has been cancelled. No data was deleted.",
            color=discord.Color.blue()
        )
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def on_timeout(self):
        """Handle view timeout."""
        # Disable all buttons
        for item in self.children:
            item.disabled = True


def setup(bot):
    """Set up the Privacy cog."""
    bot.add_cog(PrivacyCog(bot))