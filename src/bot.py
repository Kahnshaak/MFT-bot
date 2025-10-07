"""
Main bot entry point for the Discord Game Night Scheduling Bot.
"""

import asyncio
import logging
import os
import sys
import signal
import time
from typing import Optional

import discord
from discord.ext import commands

# Add src directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.settings import Settings
from core.event_bus import EventBus
from core.security_manager import SecurityManager
from core.metrics_collector import MetricsCollector
from core.health_monitor import HealthMonitor
from core.validation_manager import ValidationManager
from core.audit_logger import AuditLogger
from core.discord_events_manager import DiscordEventsManager
from core.startup_validator import StartupValidator, ValidationError
from core.recovery_manager import RecoveryManager
from core.database_recovery import DatabaseRecoveryManager
from core.state_manager import SystemStateManager
from core.consistency_checker import DataConsistencyChecker
from core.alerting_system import AlertingSystem, DiscordAlertChannel, LogAlertChannel
from core.performance_monitor import PerformanceMonitor
from core.system_status_dashboard import SystemStatusDashboard
from core.log_aggregator import LogAggregator
from core.performance_integration import PerformanceIntegration
from database.manager import DatabaseManager
from database.migrations import initialize_database
from utils.logging_config import setup_logging


class GameNightBot(commands.Bot):
    """Main bot class for the Discord Game Night Scheduling Bot."""
    
    def __init__(self):
        # Set up intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.guild_messages = True
        intents.guild_reactions = True
        
        super().__init__(
            command_prefix='!',  # Fallback prefix, mainly using slash commands
            intents=intents,
            help_command=None
        )
        
        # Initialize core components
        self.settings = Settings()
        self.database: Optional[DatabaseManager] = None
        self.event_bus: Optional[EventBus] = None
        self.security: Optional[SecurityManager] = None
        self.metrics: Optional[MetricsCollector] = None
        self.health_monitor: Optional[HealthMonitor] = None
        self.validation: Optional[ValidationManager] = None
        self.audit_logger: Optional[AuditLogger] = None
        self.discord_events: Optional[DiscordEventsManager] = None
        
        # Enhanced error handling and recovery components
        self.recovery_manager: Optional[RecoveryManager] = None
        self.database_recovery: Optional[DatabaseRecoveryManager] = None
        self.state_manager: Optional[SystemStateManager] = None
        self.consistency_checker: Optional[DataConsistencyChecker] = None
        
        # Monitoring and alerting components
        self.alerting_system: Optional[AlertingSystem] = None
        self.performance_monitor: Optional[PerformanceMonitor] = None
        self.system_dashboard: Optional[SystemStatusDashboard] = None
        self.log_aggregator: Optional[LogAggregator] = None
        
        # Performance optimization integration
        self.performance_integration: Optional[PerformanceIntegration] = None
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
        
        # Enhanced error handling components (initialized in setup_hook)
        self.enhanced_error_handler = None
        self.poll_edge_case_handler = None
        self.degradation_manager = None
        self.event_recovery_manager = None
    
    async def setup_hook(self):
        """Initialize bot components and load cogs."""
        try:
            self.logger.info("Starting bot setup...")
            
            # Initialize performance integration first
            self.performance_integration = PerformanceIntegration(self)
            await self.performance_integration.initialize()
            
            # Initialize database connection with performance optimizations
            self.database = DatabaseManager(
                self.settings.database_url,
                cache_manager=self.performance_integration.cache_manager
            )
            await self.database.connect()
            
            # Initialize database schema and run migrations
            self.logger.info("Initializing database schema...")
            await initialize_database(self.database)
            
            # Initialize core systems
            self.event_bus = EventBus()
            self.security = SecurityManager(self.settings)
            self.metrics = MetricsCollector()
            self.validation = ValidationManager()
            self.audit_logger = AuditLogger(self.database)
            self.health_monitor = HealthMonitor(self.database, self)
            self.discord_events = DiscordEventsManager(self, self.event_bus, self.database)
            
            # Initialize enhanced error handling and recovery systems
            self.recovery_manager = RecoveryManager(self.database, self.event_bus)
            self.database_recovery = DatabaseRecoveryManager(self.database)
            self.state_manager = SystemStateManager(self.database, self.event_bus)
            self.consistency_checker = DataConsistencyChecker(self.database, self.event_bus)
            
            # Initialize enhanced error handling components
            from core.enhanced_error_handler import EnhancedErrorHandler
            from core.poll_edge_case_handler import PollEdgeCaseHandler
            from core.graceful_degradation_manager import GracefulDegradationManager, ServiceType
            from core.event_recovery_manager import EventRecoveryManager
            
            self.enhanced_error_handler = EnhancedErrorHandler(self.recovery_manager, self.event_bus)
            self.poll_edge_case_handler = PollEdgeCaseHandler(self.database, self.event_bus)
            self.degradation_manager = GracefulDegradationManager(self.event_bus)
            self.event_recovery_manager = EventRecoveryManager(self.database, self.event_bus)
            
            # Register health checkers for graceful degradation
            self.degradation_manager.register_health_checker(
                ServiceType.DATABASE,
                self._check_database_health
            )
            self.degradation_manager.register_health_checker(
                ServiceType.DISCORD_API,
                self._check_discord_api_health
            )
            
            # Initialize monitoring and alerting systems
            self.alerting_system = AlertingSystem(self.database)
            self.performance_monitor = PerformanceMonitor(self.metrics)
            self.log_aggregator = LogAggregator(database_manager=self.database)
            
            # Set up alerting channels
            log_channel = LogAlertChannel()
            self.alerting_system.add_channel(log_channel)
            
            # Initialize system dashboard
            self.system_dashboard = SystemStatusDashboard(
                self.health_monitor,
                self.metrics,
                self.performance_monitor,
                self.alerting_system,
                self.database
            )
            
            # Register consistency checkers with recovery manager
            self.recovery_manager.register_consistency_checker(
                self.consistency_checker.run_full_consistency_check
            )
            
            # Start recovery monitoring
            await self.database_recovery.start_recovery_monitoring()
            await self.state_manager.start_state_management()
            
            # Emit system startup event
            await self.event_bus.emit(
                self.event_bus.EventType.SYSTEM_STARTUP,
                {"timestamp": self.event_bus.Event.timestamp}
            )
            
            # Set up event bus middleware for metrics and audit logging
            self.event_bus.add_middleware(self._metrics_middleware)
            self.event_bus.add_middleware(self._audit_middleware)
            
            # Load cogs with error handling
            cogs_to_load = [
                'cogs.events',
                'cogs.users', 
                'cogs.games',
                'cogs.notifications',
                'cogs.timestamps',
                'cogs.admin',
                'cogs.recurring',
                'cogs.monitoring'
            ]
            
            for cog in cogs_to_load:
                try:
                    await self.load_extension(cog)
                    self.logger.info(f"Loaded cog: {cog}")
                except Exception as e:
                    self.logger.error(f"Failed to load cog {cog}: {e}")
                    # Continue loading other cogs
            
            self.logger.info("Bot setup completed successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to setup bot: {e}")
            raise
    
    async def on_ready(self):
        """Called when the bot is ready."""
        self.logger.info(f'{self.user} has connected to Discord!')
        self.logger.info(f'Bot is in {len(self.guilds)} guilds')
        
        # Start health monitoring
        if self.health_monitor:
            await self.health_monitor.start_monitoring()
            
            # Set up health monitoring alerts
            self.health_monitor.register_alert_callback(self._handle_health_alert)
        
        # Start system dashboard
        if self.system_dashboard:
            await self.system_dashboard.start_auto_refresh(30)  # 30 second refresh
        
        # Set up Discord alert channel if admin channel is configured
        admin_channel_id = self.settings.get('ADMIN_CHANNEL_ID')
        if admin_channel_id and self.alerting_system:
            try:
                discord_channel = DiscordAlertChannel(
                    self, 
                    int(admin_channel_id),
                    mention_roles=self.settings.get('ADMIN_ROLE_IDS', [])
                )
                self.alerting_system.add_channel(discord_channel)
                self.logger.info(f"Added Discord alert channel: {admin_channel_id}")
            except Exception as e:
                self.logger.warning(f"Failed to set up Discord alert channel: {e}")
        
        # Run initial consistency check
        if self.consistency_checker:
            try:
                issues = await self.consistency_checker.run_full_consistency_check()
                if issues:
                    self.logger.warning(
                        f"Found {len(issues)} consistency issues on startup"
                    )
                    
                    # Auto-repair critical issues
                    critical_issues = [i for i in issues if i.severity.value == "CRITICAL"]
                    if critical_issues:
                        repair_results = await self.consistency_checker.auto_repair_issues(
                            critical_issues, max_repairs=50
                        )
                        self.logger.info(
                            f"Auto-repaired {repair_results['successful']} critical issues"
                        )
                else:
                    self.logger.info("No consistency issues found on startup")
            except Exception as e:
                self.logger.error(f"Failed to run startup consistency check: {e}")
    
    async def on_error(self, event, *args, **kwargs):
        """Global error handler with enhanced recovery."""
        self.logger.error(f"Error in event {event}", exc_info=True)
        if self.metrics:
            await self.metrics.record_error(event)
        
        # Log security event for critical errors
        if self.audit_logger and event in ['command_error', 'application_command_error']:
            await self.audit_logger.log_security_event(
                event_type=self.audit_logger.AuditEventType.SECURITY_VIOLATION,
                action=f"Unhandled error in {event}",
                severity="medium",
                details={"event": event, "args": str(args)[:500]}
            )
        
        # Emit error event for recovery system
        if self.event_bus:
            await self.event_bus.emit(
                self.event_bus.EventType.ERROR_OCCURRED,
                {
                    "event_name": event,
                    "error_type": "global_error",
                    "args": str(args)[:500],
                    "kwargs": str(kwargs)[:500]
                }
            )
    
    async def _metrics_middleware(self, event):
        """Middleware to record metrics for events."""
        if self.metrics:
            # Record event metrics (non-async call)
            self.metrics.record_counter(
                "event_bus_events_total",
                1.0,
                {"event_type": event.event_type.value, "source": event.source or "unknown"}
            )
        return event
    
    async def _audit_middleware(self, event):
        """Middleware to log audit events."""
        if self.audit_logger:
            # Log certain events to audit log
            audit_worthy_events = [
                "EVENT_CREATED", "EVENT_UPDATED", "EVENT_CANCELLED",
                "USER_PREFERENCES_UPDATED", "ERROR_OCCURRED"
            ]
            
            if event.event_type.value.upper() in audit_worthy_events:
                from core.audit_logger import AuditEventType
                event_type_mapping = {
                    "EVENT_CREATED": AuditEventType.EVENT_CREATED,
                    "EVENT_UPDATED": AuditEventType.EVENT_UPDATED,
                    "EVENT_CANCELLED": AuditEventType.EVENT_CANCELLED,
                    "USER_PREFERENCES_UPDATED": AuditEventType.USER_PROFILE_UPDATED,
                    "ERROR_OCCURRED": AuditEventType.SECURITY_VIOLATION
                }
                
                audit_event_type = event_type_mapping.get(
                    event.event_type.value.upper(),
                    AuditEventType.USER_PROFILE_UPDATED
                )
                
                await self.audit_logger.log_event(
                    event_type=audit_event_type,
                    action=f"Event bus: {event.event_type.value}",
                    user_id=event.user_id,
                    guild_id=event.guild_id,
                    details={"source": event.source, "data": event.data}
                )
        return event
    
    async def _handle_health_alert(self, health_check):
        """Handle health monitoring alerts."""
        if self.alerting_system and health_check.status.value in ['unhealthy', 'degraded']:
            from core.alerting_system import AlertType, AlertSeverity
            
            severity = AlertSeverity.HIGH if health_check.status.value == 'unhealthy' else AlertSeverity.MEDIUM
            
            await self.alerting_system.send_alert(
                alert_type=AlertType.HEALTH_CHECK_FAILED,
                severity=severity,
                title=f"Health Check Alert: {health_check.name}",
                message=health_check.message,
                source="health_monitor",
                details=health_check.details or {}
            )
    
    async def on_command_error(self, ctx, error):
        """Handle command errors with proper logging and metrics."""
        command_name = ctx.command.name if ctx.command else "unknown"
        start_time = getattr(ctx, '_command_start_time', time.time())
        duration = time.time() - start_time
        
        # Record metrics
        if self.metrics:
            await self.metrics.record_command(
                command_name=command_name,
                duration=duration,
                success=False,
                guild_id=str(ctx.guild.id) if ctx.guild else None,
                user_id=str(ctx.author.id)
            )
        
        # Record performance metrics
        if self.performance_monitor:
            await self.performance_monitor.record_operation(
                f"command_{command_name}",
                duration * 1000,  # Convert to milliseconds
                {"success": False, "error_type": type(error).__name__}
            )
        
        # Log to audit system
        if self.audit_logger:
            from core.audit_logger import AuditEventType
            await self.audit_logger.log_security_event(
                event_type=AuditEventType.SECURITY_VIOLATION,
                action=f"Command error: {command_name}",
                user_id=str(ctx.author.id),
                guild_id=str(ctx.guild.id) if ctx.guild else None,
                severity="low",
                details={
                    "command": command_name,
                    "error_type": type(error).__name__,
                    "error_message": str(error)
                }
            )
        
        # Handle specific error types
        from utils.exceptions import (
            PermissionDeniedError, ValidationError, RateLimitedError,
            GameNightBotException
        )
        
        if isinstance(error, commands.CommandNotFound):
            # Ignore command not found errors
            return
        
        elif isinstance(error, PermissionDeniedError):
            await ctx.send(f"❌ {error.user_message}", ephemeral=True)
            
        elif isinstance(error, ValidationError):
            await ctx.send(f"❌ Invalid input: {error.user_message}", ephemeral=True)
            
        elif isinstance(error, RateLimitedError):
            await ctx.send(f"⏰ {error.user_message}", ephemeral=True)
            
        elif isinstance(error, GameNightBotException):
            await ctx.send(f"❌ {error.user_message}", ephemeral=True)
            
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command.", ephemeral=True)
            
        elif isinstance(error, commands.BotMissingPermissions):
            missing_perms = ", ".join(error.missing_permissions)
            await ctx.send(f"❌ I need the following permissions: {missing_perms}", ephemeral=True)
            
        else:
            # Log unexpected errors
            self.logger.error(
                "Unexpected command error",
                command=command_name,
                error=str(error),
                user_id=ctx.author.id,
                guild_id=ctx.guild.id if ctx.guild else None,
                exc_info=True
            )
            await ctx.send("❌ An unexpected error occurred. Please try again later.", ephemeral=True)
    
    async def on_application_command_error(self, interaction, error):
        """Handle application command (slash command) errors."""
        command_name = interaction.command.name if interaction.command else "unknown"
        start_time = getattr(interaction, '_command_start_time', time.time())
        duration = time.time() - start_time
        
        # Record metrics
        if self.metrics:
            await self.metrics.record_command(
                command_name=command_name,
                duration=duration,
                success=False,
                guild_id=str(interaction.guild.id) if interaction.guild else None,
                user_id=str(interaction.user.id)
            )
        
        # Record performance metrics
        if self.performance_monitor:
            await self.performance_monitor.record_operation(
                f"slash_command_{command_name}",
                duration * 1000,  # Convert to milliseconds
                {"success": False, "error_type": type(error).__name__}
            )
        
        # Similar error handling as regular commands
        from utils.exceptions import (
            PermissionDeniedError, ValidationError, RateLimitedError,
            GameNightBotException
        )
        
        try:
            if isinstance(error, PermissionDeniedError):
                await interaction.response.send_message(f"❌ {error.user_message}", ephemeral=True)
                
            elif isinstance(error, ValidationError):
                await interaction.response.send_message(f"❌ Invalid input: {error.user_message}", ephemeral=True)
                
            elif isinstance(error, RateLimitedError):
                await interaction.response.send_message(f"⏰ {error.user_message}", ephemeral=True)
                
            elif isinstance(error, GameNightBotException):
                await interaction.response.send_message(f"❌ {error.user_message}", ephemeral=True)
                
            else:
                self.logger.error(
                    "Unexpected application command error",
                    command=command_name,
                    error=str(error),
                    user_id=interaction.user.id,
                    guild_id=interaction.guild.id if interaction.guild else None,
                    exc_info=True
                )
                
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An unexpected error occurred. Please try again later.", 
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ An unexpected error occurred. Please try again later.", 
                        ephemeral=True
                    )
        except Exception as e:
            self.logger.error(f"Error handling application command error: {e}", exc_info=True)
    
    # Health check methods for graceful degradation
    
    async def _check_database_health(self) -> bool:
        """Check if database is healthy."""
        try:
            if not self.database:
                return False
            return await self.database.ping()
        except Exception:
            return False
    
    async def _check_discord_api_health(self) -> bool:
        """Check if Discord API is healthy."""
        try:
            # Simple check - try to get bot user info
            if self.user:
                return True
            return False
        except Exception:
            return False


async def main():
    """Main entry point with comprehensive startup validation."""
    # Initialize settings first
    try:
        settings = Settings()
    except Exception as e:
        print(f"❌ Failed to load settings: {e}")
        print("Please check your .env file and environment variables.")
        sys.exit(1)
    
    # Set up logging
    try:
        setup_logging(settings)
        logger = logging.getLogger(__name__)
    except Exception as e:
        print(f"❌ Failed to setup logging: {e}")
        sys.exit(1)
    
    logger.info("🚀 Starting Discord Game Night Bot...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Log Level: {settings.log_level}")
    
    # Run startup validation
    try:
        logger.info("Running startup validation...")
        validator = StartupValidator(settings)
        validation_success, validation_results = await validator.validate_all()
        
        if not validation_success:
            logger.error("❌ Startup validation failed!")
            validator.print_detailed_report()
            
            # Check if only Discord validation failed and we're in development
            failed_categories = validation_results.get('summary', {}).get('failed_categories', [])
            discord_only_failure = (
                len(failed_categories) == 1 and 
                'discord' in failed_categories and 
                settings.is_development
            )
            
            if discord_only_failure:
                logger.warning("⚠️  Only Discord validation failed in development mode")
                logger.warning("   This is often due to invalid token or bot not being in any servers")
                logger.warning("   Continuing startup - bot will work for database operations")
            else:
                # Print helpful error messages
                print("\n💡 TROUBLESHOOTING TIPS:")
                print("1. Check your .env file exists and has all required variables")
                print("2. Ensure MongoDB is running and accessible")
                print("3. Verify your Discord bot token is valid")
                print("4. Check file permissions for logs directory")
                print("5. Run 'python -m pip install -r requirements.txt' to install dependencies")
                
                sys.exit(1)
        else:
            logger.info("✅ Startup validation passed!")
        
    except ValidationError as e:
        logger.error(f"❌ Validation error: {e}")
        if hasattr(e, 'details') and e.details:
            logger.error(f"Details: {e.details}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected validation error: {e}")
        sys.exit(1)
    
    # Initialize bot
    bot = None
    try:
        logger.info("Initializing bot...")
        bot = GameNightBot()
        
        # Set up graceful shutdown handlers
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            asyncio.create_task(shutdown_bot(bot))
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start the bot
        logger.info("🎮 Bot starting up...")
        await bot.start(settings.discord_token)
        
    except discord.LoginFailure:
        logger.error("❌ Invalid Discord token. Please check your DISCORD_TOKEN environment variable.")
        sys.exit(1)
    except discord.HTTPException as e:
        logger.error(f"❌ Discord HTTP error: {e}")
        logger.error("This might be a temporary Discord API issue. Please try again later.")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"❌ Bot crashed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await shutdown_bot(bot)


async def shutdown_bot(bot: Optional[GameNightBot]) -> None:
    """Gracefully shutdown the bot and cleanup resources."""
    logger = logging.getLogger(__name__)
    
    if bot:
        try:
            logger.info("Shutting down bot...")
            
            # Emit system shutdown event
            if hasattr(bot, 'event_bus') and bot.event_bus:
                await bot.event_bus.emit(
                    bot.event_bus.EventType.SYSTEM_SHUTDOWN,
                    {"timestamp": time.time()}
                )
            
            # Stop enhanced recovery systems
            if hasattr(bot, 'database_recovery') and bot.database_recovery:
                await bot.database_recovery.stop_recovery_monitoring()
                logger.info("Database recovery monitoring stopped")
            
            if hasattr(bot, 'state_manager') and bot.state_manager:
                await bot.state_manager.stop_state_management()
                logger.info("State management stopped")
            
            # Stop monitoring systems
            if hasattr(bot, 'health_monitor') and bot.health_monitor:
                await bot.health_monitor.stop_monitoring()
            
            if hasattr(bot, 'system_dashboard') and bot.system_dashboard:
                await bot.system_dashboard.stop_auto_refresh()
            
            # Shutdown performance integration
            if hasattr(bot, 'performance_integration') and bot.performance_integration:
                await bot.performance_integration.shutdown()
                logger.info("Performance integration shutdown complete")
            
            # Close database connection
            if hasattr(bot, 'database') and bot.database:
                await bot.database.disconnect()
                logger.info("Database connection closed")
            
            # Close bot connection
            if not bot.is_closed():
                await bot.close()
                logger.info("Bot connection closed")
                
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    logger.info("🛑 Bot shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)