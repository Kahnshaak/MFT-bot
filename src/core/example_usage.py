"""
Example usage of the core framework components.
This file demonstrates how to use the permission decorators, validation, and other core systems.
"""

import discord
from discord.ext import commands

from core.permission_decorators import require_permission, rate_limit, validate_input
from core.security_manager import Permission
from core.validation_manager import ValidationRule, ValidationType
from utils.exceptions import ValidationError


class ExampleCog(commands.Cog):
    """Example cog showing how to use the core framework."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.slash_command(name="create_event", description="Create a new game night event")
    @require_permission(Permission.CREATE_EVENTS)
    @rate_limit(max_requests=5, window_seconds=300)  # 5 events per 5 minutes
    @validate_input(
        title=ValidationRule(
            field_name="title",
            validation_type=ValidationType.EVENT_TITLE,
            required=True
        ),
        description=ValidationRule(
            field_name="description", 
            validation_type=ValidationType.EVENT_DESCRIPTION,
            required=False
        )
    )
    async def create_event(
        self, 
        ctx: discord.ApplicationContext,
        title: str,
        description: str = None
    ):
        """Create a new event with proper validation and permission checking."""
        
        # The decorators have already:
        # 1. Checked that the user has CREATE_EVENTS permission
        # 2. Applied rate limiting
        # 3. Validated the title and description inputs
        
        # Record metrics
        if self.bot.metrics:
            await self.bot.metrics.record_command(
                command_name="create_event",
                duration=0.5,  # Would measure actual duration
                success=True,
                guild_id=str(ctx.guild.id),
                user_id=str(ctx.author.id)
            )
        
        # Emit event via event bus
        if self.bot.event_bus:
            await self.bot.event_bus.emit(
                event_type=self.bot.event_bus.EventType.EVENT_CREATED,
                data={
                    "title": title,
                    "description": description,
                    "creator_id": str(ctx.author.id)
                },
                source="events_cog",
                guild_id=str(ctx.guild.id),
                user_id=str(ctx.author.id)
            )
        
        # Log audit event
        if self.bot.audit_logger:
            await self.bot.audit_logger.log_resource_event(
                event_type=self.bot.audit_logger.AuditEventType.EVENT_CREATED,
                action=f"Created event: {title}",
                user_id=str(ctx.author.id),
                guild_id=str(ctx.guild.id),
                resource_id="event_123",  # Would be actual event ID
                resource_type="event",
                new_data={"title": title, "description": description}
            )
        
        await ctx.respond(f"✅ Event '{title}' created successfully!")
    
    @commands.slash_command(name="admin_config", description="Configure bot settings")
    @require_permission(Permission.CONFIGURE_BOT)
    async def admin_config(self, ctx: discord.ApplicationContext, setting: str, value: str):
        """Admin-only configuration command."""
        
        # Validate the setting name and value
        try:
            validated_setting = self.bot.validation.validate_field(
                "setting_name", 
                setting,
                ValidationRule(
                    field_name="setting_name",
                    validation_type=ValidationType.STRING,
                    min_length=1,
                    max_length=50,
                    pattern=r'^[a-zA-Z_][a-zA-Z0-9_]*$'  # Valid identifier
                )
            )
            
            validated_value = self.bot.validation.validate_field("setting_value", value)
            
        except ValidationError as e:
            await ctx.respond(f"❌ {e.user_message}", ephemeral=True)
            return
        
        # Log the configuration change
        if self.bot.audit_logger:
            await self.bot.audit_logger.log_event(
                event_type=self.bot.audit_logger.AuditEventType.BOT_CONFIG_CHANGED,
                action=f"Changed setting {validated_setting} to {validated_value}",
                user_id=str(ctx.author.id),
                guild_id=str(ctx.guild.id),
                details={
                    "setting": validated_setting,
                    "old_value": "previous_value",  # Would get from database
                    "new_value": validated_value
                }
            )
        
        await ctx.respond(f"✅ Setting `{validated_setting}` updated to `{validated_value}`")
    
    @commands.slash_command(name="user_stats", description="View your statistics")
    async def user_stats(self, ctx: discord.ApplicationContext):
        """Show user statistics - no special permissions required."""
        
        # This command doesn't need special permissions, just basic rate limiting
        if self.bot.security:
            self.bot.security.check_rate_limit(
                f"user_stats:{ctx.author.id}",
                max_requests=10,
                window_seconds=60
            )
        
        # Get user activity from audit logs
        if self.bot.audit_logger:
            activity = await self.bot.audit_logger.get_user_activity(
                user_id=str(ctx.author.id),
                guild_id=str(ctx.guild.id),
                days=30
            )
            
            embed = discord.Embed(
                title="Your Statistics",
                description=f"Activity over the last 30 days",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Total Events",
                value=activity.get("total_events", 0),
                inline=True
            )
            
            # Show top event types
            event_counts = activity.get("event_counts", {})
            if event_counts:
                top_events = sorted(event_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                top_events_str = "\n".join([f"{event}: {count}" for event, count in top_events])
                embed.add_field(
                    name="Top Activities",
                    value=top_events_str or "None",
                    inline=True
                )
            
            await ctx.respond(embed=embed)
        else:
            await ctx.respond("Statistics are not available at this time.")


def setup(bot):
    """Set up the example cog."""
    bot.add_cog(ExampleCog(bot))