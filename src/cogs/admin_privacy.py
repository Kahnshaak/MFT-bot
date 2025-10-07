"""
Admin privacy cog for server administrators to manage privacy compliance.
"""

import discord
from discord.ext import commands, tasks
from typing import Optional
from datetime import datetime, timedelta

try:
    from utils.logging_config import LoggerMixin
    from utils.error_handler import discord_error_handler
    from core.privacy_manager import PrivacyManager
    from core.audit_logger import AuditLogger
    from database.manager import DatabaseManager
    from core.permission_decorators import require_permission
except ImportError:
    from src.utils.logging_config import LoggerMixin
    from src.utils.error_handler import discord_error_handler
    from src.core.privacy_manager import PrivacyManager
    from src.core.audit_logger import AuditLogger
    from src.database.manager import DatabaseManager
    from src.core.permission_decorators import require_permission


class AdminPrivacyCog(commands.Cog, LoggerMixin):
    """
    Administrative privacy and compliance commands.
    
    Provides commands for server administrators to:
    - Manage data retention policies
    - Generate compliance reports
    - Handle data export requests
    - Monitor privacy compliance
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.database: DatabaseManager = bot.database
        self.audit_logger: AuditLogger = bot.audit_logger
        self.privacy_manager = PrivacyManager(self.database, self.audit_logger)
        
        # Start background tasks
        self.cleanup_task.start()
    
    def cog_unload(self):
        """Clean up when cog is unloaded."""
        self.cleanup_task.cancel()
    
    @discord.slash_command(
        name="admin_privacy_report",
        description="Generate a privacy compliance report for this server"
    )
    @require_permission("can_manage_guild_config")
    @discord_error_handler
    async def compliance_report(self, ctx: discord.ApplicationContext):
        """Generate a comprehensive privacy compliance report."""
        await ctx.defer()
        
        guild_id = str(ctx.guild.id)
        
        try:
            report = await self.privacy_manager.generate_compliance_report(guild_id)
            
            embed = discord.Embed(
                title="📊 Privacy Compliance Report",
                description=f"Compliance status for **{ctx.guild.name}**",
                color=discord.Color.blue()
            )
            
            # Data summary
            data_summary = report["data_summary"]
            embed.add_field(
                name="📈 Data Overview",
                value=f"**Users:** {data_summary['total_users']:,}\n"
                      f"**Events:** {data_summary['total_events']:,}\n"
                      f"**Notifications:** {data_summary['total_notifications']:,}\n"
                      f"**Audit Logs:** {data_summary['total_audit_logs']:,}",
                inline=True
            )
            
            # Consent summary
            consent_summary = report["consent_summary"]
            consent_text = []
            for consent_type, stats in consent_summary.items():
                total = stats['granted'] + stats['denied']
                if total > 0:
                    consent_text.append(f"**{consent_type.replace('_', ' ').title()}:** {stats['granted']}/{total}")
            
            if consent_text:
                embed.add_field(
                    name="✅ Consent Status",
                    value="\n".join(consent_text[:5]),  # Limit to 5 items
                    inline=True
                )
            
            # Retention status
            retention = report["retention_status"]
            embed.add_field(
                name="🗂️ Data Retention",
                value=f"**Events Due for Cleanup:** {retention['events_due_for_cleanup']}\n"
                      f"**Old Notifications:** {retention['notifications_due_for_cleanup']}\n"
                      f"**Inactive Users:** {retention['inactive_users']}",
                inline=True
            )
            
            # Recent requests
            recent = report["recent_requests"]
            embed.add_field(
                name="📋 Recent Requests (30 days)",
                value=f"**Data Exports:** {recent['data_exports']}\n"
                      f"**Deletion Requests:** {recent['deletion_requests']}",
                inline=True
            )
            
            embed.add_field(
                name="🔧 Actions Available",
                value="• `/admin_privacy cleanup` - Run data cleanup\n"
                      "• `/admin_privacy backup` - Create privacy backup\n"
                      "• `/admin_privacy exports` - Manage export requests",
                inline=False
            )
            
            embed.set_footer(
                text=f"Report generated at {report['generated_at'][:19].replace('T', ' ')} UTC"
            )
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Report Generation Failed",
                description=f"Failed to generate compliance report: {str(e)}",
                color=discord.Color.red()
            )
        
        await ctx.followup.send(embed=embed)
    
    @discord.slash_command(
        name="admin_privacy_cleanup",
        description="Run data retention cleanup policies"
    )
    @require_permission("can_manage_guild_config")
    @discord_error_handler
    async def run_cleanup(self, ctx: discord.ApplicationContext):
        """Run data retention cleanup policies."""
        await ctx.defer()
        
        try:
            results = await self.privacy_manager.apply_retention_policies()
            
            embed = discord.Embed(
                title="🧹 Data Cleanup Completed",
                description="Data retention policies have been applied.",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="📊 Cleanup Summary",
                value=f"**Total Records Deleted:** {results['total_deleted']:,}\n"
                      f"**Policies Applied:** {len(results['policies_applied'])}\n"
                      f"**Started:** {results['started_at'][:19].replace('T', ' ')}\n"
                      f"**Completed:** {results.get('completed_at', 'N/A')[:19].replace('T', ' ')}",
                inline=False
            )
            
            # Show details for each policy
            policy_details = []
            for policy_name, policy_result in results["policies_applied"].items():
                deleted = policy_result.get("deleted", 0)
                if deleted > 0:
                    policy_details.append(f"**{policy_name.replace('_', ' ').title()}:** {deleted:,}")
            
            if policy_details:
                embed.add_field(
                    name="🗂️ Cleanup Details",
                    value="\n".join(policy_details),
                    inline=False
                )
            
            if results.get("errors"):
                embed.add_field(
                    name="⚠️ Errors",
                    value=f"{len(results['errors'])} errors occurred during cleanup",
                    inline=False
                )
                embed.color = discord.Color.orange()
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Cleanup Failed",
                description=f"Failed to run data cleanup: {str(e)}",
                color=discord.Color.red()
            )
        
        await ctx.followup.send(embed=embed)
    
    @discord.slash_command(
        name="admin_privacy_backup",
        description="Create a backup of privacy-related data"
    )
    @require_permission("can_manage_guild_config")
    @discord_error_handler
    async def create_backup(self, ctx: discord.ApplicationContext):
        """Create a backup of privacy-related data."""
        await ctx.defer()
        
        guild_id = str(ctx.guild.id)
        
        try:
            backup_info = await self.privacy_manager.create_privacy_backup(guild_id)
            
            embed = discord.Embed(
                title="💾 Privacy Backup Created",
                description="Privacy-related data has been backed up successfully.",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="📋 Backup Details",
                value=f"**Backup ID:** `{backup_info['backup_id']}`\n"
                      f"**Created:** {backup_info['created_at'][:19].replace('T', ' ')}\n"
                      f"**Files:** {backup_info['file_count']}\n"
                      f"**Size:** {backup_info['total_size']:,} bytes",
                inline=False
            )
            
            # Show collections backed up
            collections_text = []
            for collection, info in backup_info["collections"].items():
                collections_text.append(f"**{collection}:** {info['record_count']:,} records")
            
            embed.add_field(
                name="📁 Collections Backed Up",
                value="\n".join(collections_text),
                inline=False
            )
            
            embed.add_field(
                name="ℹ️ Note",
                value="Backup files are stored securely and contain only privacy-related data. "
                      "Contact system administrator for backup file access.",
                inline=False
            )
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Backup Failed",
                description=f"Failed to create privacy backup: {str(e)}",
                color=discord.Color.red()
            )
        
        await ctx.followup.send(embed=embed)
    
    @discord.slash_command(
        name="admin_privacy_exports",
        description="View and manage data export requests"
    )
    @require_permission("can_manage_guild_config")
    @discord_error_handler
    async def manage_exports(
        self,
        ctx: discord.ApplicationContext,
        status: discord.Option(
            str,
            description="Filter by export status",
            choices=["pending", "processing", "completed", "failed", "all"],
            default="all"
        )
    ):
        """View and manage data export requests."""
        await ctx.defer()
        
        guild_id = str(ctx.guild.id)
        
        try:
            # Get export requests for this guild
            query = {"guild_id": guild_id}
            if status != "all":
                query["status"] = status
            
            exports = await self.database.find_many(
                "data_export_requests",
                query,
                sort=[("requested_at", -1)],
                limit=20
            )
            
            if not exports:
                embed = discord.Embed(
                    title="📋 No Export Requests",
                    description=f"No data export requests found with status: {status}",
                    color=discord.Color.blue()
                )
                await ctx.followup.send(embed=embed)
                return
            
            embed = discord.Embed(
                title="📋 Data Export Requests",
                description=f"Recent export requests for **{ctx.guild.name}**",
                color=discord.Color.blue()
            )
            
            # Group exports by status
            status_groups = {}
            for export in exports:
                export_status = export["status"]
                if export_status not in status_groups:
                    status_groups[export_status] = []
                status_groups[export_status].append(export)
            
            # Show summary
            summary_text = []
            for export_status, export_list in status_groups.items():
                summary_text.append(f"**{export_status.title()}:** {len(export_list)}")
            
            embed.add_field(
                name="📊 Summary",
                value="\n".join(summary_text),
                inline=True
            )
            
            # Show recent exports
            recent_exports = []
            for export in exports[:10]:  # Show last 10
                user_mention = f"<@{export['user_id']}>"
                status_emoji = {
                    "pending": "⏳",
                    "processing": "⚙️",
                    "completed": "✅",
                    "failed": "❌"
                }.get(export["status"], "❓")
                
                recent_exports.append(
                    f"{status_emoji} {user_mention} - {export['format'].upper()} "
                    f"({export['requested_at'][:10]})"
                )
            
            if recent_exports:
                embed.add_field(
                    name="📋 Recent Requests",
                    value="\n".join(recent_exports),
                    inline=False
                )
            
            embed.add_field(
                name="🔧 Management",
                value="• Export files are automatically cleaned up after 30 days\n"
                      "• Users can check status with `/privacy export_status`\n"
                      "• Failed exports can be retried by users",
                inline=False
            )
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Failed to Load Exports",
                description=f"Failed to load export requests: {str(e)}",
                color=discord.Color.red()
            )
        
        await ctx.followup.send(embed=embed)
    
    @discord.slash_command(
        name="admin_privacy_retention",
        description="View current data retention settings"
    )
    @require_permission("can_manage_guild_config")
    @discord_error_handler
    async def retention_settings(self, ctx: discord.ApplicationContext):
        """View current data retention settings."""
        await ctx.defer()
        
        embed = discord.Embed(
            title="🗂️ Data Retention Settings",
            description="Current data retention periods for different data types",
            color=discord.Color.blue()
        )
        
        retention_periods = self.privacy_manager.retention_periods
        
        # Group retention periods by category
        embed.add_field(
            name="📅 Event Data",
            value=f"**Completed Events:** {retention_periods['events']} days\n"
                  f"**Cancelled Events:** {retention_periods['cancelled_events']} days",
            inline=True
        )
        
        embed.add_field(
            name="👤 User Data",
            value=f"**Inactive Users:** {retention_periods['inactive_users']} days",
            inline=True
        )
        
        embed.add_field(
            name="📊 System Data",
            value=f"**Notifications:** {retention_periods['notifications']} days\n"
                  f"**Audit Logs:** {retention_periods['audit_logs']} days\n"
                  f"**Analytics:** {retention_periods['analytics']} days",
            inline=True
        )
        
        embed.add_field(
            name="🔄 Automatic Cleanup",
            value="Data retention policies are automatically applied daily at midnight UTC. "
                  "You can also run cleanup manually with `/admin_privacy cleanup`.",
            inline=False
        )
        
        embed.add_field(
            name="⚖️ Legal Compliance",
            value="These retention periods are set to comply with GDPR and other privacy regulations. "
                  "Audit logs are kept for 7 years as required by law.",
            inline=False
        )
        
        await ctx.followup.send(embed=embed)
    
    @discord.slash_command(
        name="admin_privacy_user",
        description="View privacy information for a specific user"
    )
    @require_permission("can_manage_guild_config")
    @discord_error_handler
    async def user_privacy_info(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Option(
            discord.Member,
            description="User to view privacy information for"
        )
    ):
        """View privacy information for a specific user."""
        await ctx.defer()
        
        user_id = str(user.id)
        guild_id = str(ctx.guild.id)
        
        try:
            # Get user privacy settings
            privacy_settings = await self.privacy_manager.get_privacy_settings(user_id, guild_id)
            consents = await self.privacy_manager.get_all_user_consents(user_id, guild_id)
            
            # Get data summary
            user_profile = await self.database.find_one(
                "users",
                {"user_id": user_id, "guild_id": guild_id}
            )
            
            events_created = await self.database.count_documents(
                "events",
                {"creator_id": user_id, "guild_id": guild_id}
            )
            
            events_participated = await self.database.count_documents(
                "events",
                {
                    "guild_id": guild_id,
                    f"rsvp_data.{user_id}": {"$exists": True}
                }
            )
            
            embed = discord.Embed(
                title=f"🔒 Privacy Info: {user.display_name}",
                description=f"Privacy and data information for {user.mention}",
                color=discord.Color.blue()
            )
            
            # Data summary
            embed.add_field(
                name="📊 Data Summary",
                value=f"**Profile Exists:** {'✅ Yes' if user_profile else '❌ No'}\n"
                      f"**Events Created:** {events_created}\n"
                      f"**Events Participated:** {events_participated}",
                inline=True
            )
            
            # Privacy settings
            settings_text = []
            for setting, value in privacy_settings.items():
                setting_name = setting.replace('_', ' ').replace('allow ', '').title()
                status = "✅ Enabled" if value else "❌ Disabled"
                settings_text.append(f"**{setting_name}:** {status}")
            
            if settings_text:
                embed.add_field(
                    name="⚙️ Privacy Settings",
                    value="\n".join(settings_text),
                    inline=True
                )
            
            # Consent status
            if consents:
                consent_text = []
                for consent_type, granted in consents.items():
                    status = "✅ Granted" if granted else "❌ Denied"
                    consent_text.append(f"**{consent_type.replace('_', ' ').title()}:** {status}")
                
                embed.add_field(
                    name="📋 Consent Status",
                    value="\n".join(consent_text),
                    inline=False
                )
            
            # Recent export requests
            recent_exports = await self.database.find_many(
                "data_export_requests",
                {"user_id": user_id, "guild_id": guild_id},
                sort=[("requested_at", -1)],
                limit=3
            )
            
            if recent_exports:
                export_text = []
                for export in recent_exports:
                    status_emoji = {
                        "pending": "⏳",
                        "processing": "⚙️", 
                        "completed": "✅",
                        "failed": "❌"
                    }.get(export["status"], "❓")
                    
                    export_text.append(
                        f"{status_emoji} {export['format'].upper()} - "
                        f"{export['requested_at'][:10]} ({export['status']})"
                    )
                
                embed.add_field(
                    name="📋 Recent Export Requests",
                    value="\n".join(export_text),
                    inline=False
                )
            
            if user_profile:
                last_active = user_profile.get("statistics", {}).get("last_active")
                if last_active:
                    embed.set_footer(text=f"Last active: {last_active[:19].replace('T', ' ')}")
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Failed to Load User Info",
                description=f"Failed to load privacy information: {str(e)}",
                color=discord.Color.red()
            )
        
        await ctx.followup.send(embed=embed)
    
    @tasks.loop(hours=24)
    async def cleanup_task(self):
        """Daily task to run data retention cleanup."""
        try:
            self.logger.info("Running scheduled data retention cleanup")
            results = await self.privacy_manager.apply_retention_policies()
            
            self.logger.info(
                "Scheduled cleanup completed",
                total_deleted=results.get("total_deleted", 0),
                policies_applied=len(results.get("policies_applied", {}))
            )
            
        except Exception as e:
            self.logger.error(
                "Scheduled cleanup failed",
                error=str(e)
            )
    
    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        """Wait for bot to be ready before starting cleanup task."""
        await self.bot.wait_until_ready()


def setup(bot):
    """Set up the Admin Privacy cog."""
    bot.add_cog(AdminPrivacyCog(bot))