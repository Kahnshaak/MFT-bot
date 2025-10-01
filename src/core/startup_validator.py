"""
Startup validation system for the Discord Game Night Bot.
Validates environment variables, dependencies, and system requirements before bot startup.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse
import importlib.util

import discord
import motor.motor_asyncio
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

try:
    from config.settings import Settings
    from utils.logging_config import get_logger, LoggerMixin
    from utils.exceptions import GameNightBotException
except ImportError:
    from src.config.settings import Settings
    from src.utils.logging_config import get_logger, LoggerMixin
    from src.utils.exceptions import GameNightBotException


class ValidationError(GameNightBotException):
    """Raised when startup validation fails."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.details = details or {}


class StartupValidator(LoggerMixin):
    """
    Comprehensive startup validation system.
    
    Validates:
    - Environment variables
    - Database connectivity
    - Discord API connectivity
    - Required permissions
    - File system permissions
    - Python dependencies
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        self.validation_results: Dict[str, Dict[str, Any]] = {}
        
    async def validate_all(self) -> Tuple[bool, Dict[str, Any]]:
        """
        Run all validation checks.
        
        Returns:
            Tuple of (success, results_dict)
        """
        self.logger.info("Starting comprehensive startup validation")
        
        validation_steps = [
            ("environment", self._validate_environment),
            ("dependencies", self._validate_dependencies),
            ("filesystem", self._validate_filesystem),
            ("database", self._validate_database),
            ("discord", self._validate_discord),
        ]
        
        all_passed = True
        
        for step_name, validator_func in validation_steps:
            try:
                self.logger.info(f"Validating {step_name}...")
                result = await validator_func()
                self.validation_results[step_name] = {
                    "passed": result,
                    "details": getattr(self, f"_{step_name}_details", {})
                }
                
                if result:
                    self.logger.info(f"✅ {step_name.title()} validation passed")
                else:
                    self.logger.error(f"❌ {step_name.title()} validation failed")
                    all_passed = False
                    
            except Exception as e:
                self.logger.error(f"❌ {step_name.title()} validation error: {e}")
                self.validation_results[step_name] = {
                    "passed": False,
                    "error": str(e),
                    "details": {}
                }
                all_passed = False
        
        # Generate summary
        summary = self._generate_summary()
        
        if all_passed:
            self.logger.info("🎉 All startup validations passed!")
        else:
            self.logger.error("💥 Startup validation failed. See details above.")
            
        return all_passed, {
            "overall_success": all_passed,
            "results": self.validation_results,
            "summary": summary
        }
    
    async def _validate_environment(self) -> bool:
        """Validate environment variables and configuration."""
        self._environment_details = {}
        issues = []
        
        # Required environment variables
        required_vars = {
            "DISCORD_TOKEN": "Discord bot token",
            "DISCORD_CLIENT_ID": "Discord application client ID",
            "DISCORD_CLIENT_SECRET": "Discord application client secret",
            "JWT_SECRET": "JWT secret for web authentication"
        }
        
        # Check required variables
        for var_name, description in required_vars.items():
            value = os.getenv(var_name)
            if not value:
                issues.append(f"Missing required environment variable: {var_name} ({description})")
            elif var_name == "DISCORD_TOKEN" and not value.startswith(("Bot ", "MTM")):
                issues.append(f"Invalid Discord token format. Token should start with 'Bot ' or be a valid bot token")
            elif var_name == "DISCORD_CLIENT_ID" and not value.isdigit():
                issues.append(f"Invalid Discord client ID format. Should be numeric.")
        
        # Validate database URL
        try:
            db_url = self.settings.database_url
            parsed = urlparse(db_url)
            if not parsed.scheme or not parsed.netloc:
                issues.append(f"Invalid database URL format: {db_url}")
            elif parsed.scheme not in ["mongodb", "mongodb+srv"]:
                issues.append(f"Unsupported database scheme: {parsed.scheme}. Only MongoDB is supported.")
        except Exception as e:
            issues.append(f"Error parsing database URL: {e}")
        
        # Validate log level
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.settings.log_level.upper() not in valid_log_levels:
            issues.append(f"Invalid log level: {self.settings.log_level}. Must be one of: {', '.join(valid_log_levels)}")
        
        # Validate numeric settings
        numeric_settings = {
            "web_port": (1, 65535),
            "rate_limit_per_minute": (1, 1000),
            "rate_limit_burst": (1, 100),
            "max_poll_options": (2, 25),
            "default_poll_timeout_hours": (1, 168),  # 1 hour to 1 week
            "notification_retry_attempts": (1, 10),
            "notification_retry_delay": (60, 3600)  # 1 minute to 1 hour
        }
        
        for setting_name, (min_val, max_val) in numeric_settings.items():
            value = getattr(self.settings, setting_name, None)
            if value is not None:
                if not isinstance(value, int) or value < min_val or value > max_val:
                    issues.append(f"Invalid {setting_name}: {value}. Must be between {min_val} and {max_val}")
        
        self._environment_details = {
            "issues": issues,
            "discord_token_present": bool(os.getenv("DISCORD_TOKEN")),
            "database_url": self.settings.database_url,
            "log_level": self.settings.log_level,
            "environment": self.settings.environment
        }
        
        return len(issues) == 0
    
    async def _validate_dependencies(self) -> bool:
        """Validate Python dependencies and imports."""
        self._dependencies_details = {}
        issues = []
        
        # Required packages with minimum versions
        required_packages = {
            "discord": "2.0.0",
            "motor": "3.0.0",
            "pymongo": "4.0.0",
            "fastapi": "0.100.0",
            "uvicorn": "0.20.0",
            "pydantic": "2.0.0",
            "structlog": "23.0.0",
            "python_jose": "3.3.0",
            "passlib": "1.7.0",
            "aiohttp": "3.8.0",
            "python_dotenv": "1.0.0",
            "pytz": "2023.0"
        }
        
        missing_packages = []
        version_issues = []
        
        for package_name, min_version in required_packages.items():
            try:
                # Try to import the package
                if package_name == "python_jose":
                    import jose
                    package = jose
                elif package_name == "python_dotenv":
                    import dotenv
                    package = dotenv
                else:
                    package = __import__(package_name)
                
                # Check version if available
                if hasattr(package, "__version__"):
                    version = package.__version__
                    # Simple version comparison (not perfect but sufficient for basic checks)
                    if version < min_version:
                        version_issues.append(f"{package_name}: {version} < {min_version}")
                        
            except ImportError as e:
                missing_packages.append(f"{package_name}: {e}")
        
        if missing_packages:
            issues.extend([f"Missing package: {pkg}" for pkg in missing_packages])
        
        if version_issues:
            issues.extend([f"Version issue: {issue}" for issue in version_issues])
        
        # Check Python version
        python_version = sys.version_info
        if python_version < (3, 8):
            issues.append(f"Python version {python_version.major}.{python_version.minor} is too old. Minimum required: 3.8")
        
        self._dependencies_details = {
            "issues": issues,
            "python_version": f"{python_version.major}.{python_version.minor}.{python_version.micro}",
            "missing_packages": missing_packages,
            "version_issues": version_issues
        }
        
        return len(issues) == 0
    
    async def _validate_filesystem(self) -> bool:
        """Validate filesystem permissions and required directories."""
        self._filesystem_details = {}
        issues = []
        
        # Required directories
        required_dirs = [
            Path("logs"),
            Path("src"),
            Path("src/cogs"),
            Path("src/models"),
            Path("src/utils"),
            Path("src/core"),
            Path("src/config"),
            Path("src/database")
        ]
        
        # Check directory existence and permissions
        for dir_path in required_dirs:
            if not dir_path.exists():
                try:
                    dir_path.mkdir(parents=True, exist_ok=True)
                    self.logger.info(f"Created missing directory: {dir_path}")
                except Exception as e:
                    issues.append(f"Cannot create directory {dir_path}: {e}")
            elif not dir_path.is_dir():
                issues.append(f"Path exists but is not a directory: {dir_path}")
        
        # Check log file permissions
        log_file_path = Path(self.settings.log_file_path)
        try:
            # Try to create/write to log file
            log_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file_path, 'a') as f:
                f.write("")  # Test write
        except Exception as e:
            issues.append(f"Cannot write to log file {log_file_path}: {e}")
        
        # Check current working directory permissions
        try:
            test_file = Path("startup_test.tmp")
            with open(test_file, 'w') as f:
                f.write("test")
            test_file.unlink()
        except Exception as e:
            issues.append(f"No write permission in current directory: {e}")
        
        self._filesystem_details = {
            "issues": issues,
            "log_file_path": str(log_file_path),
            "current_directory": str(Path.cwd()),
            "directories_checked": [str(d) for d in required_dirs]
        }
        
        return len(issues) == 0
    
    async def _validate_database(self) -> bool:
        """Validate database connectivity and permissions."""
        self._database_details = {}
        issues = []
        
        client = None
        try:
            # Create MongoDB client
            client = motor.motor_asyncio.AsyncIOMotorClient(
                self.settings.database_url,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000
            )
            
            # Test connection
            await client.admin.command('ping')
            
            # Get database
            db_name = urlparse(self.settings.database_url).path.lstrip('/') or 'gamenight_bot'
            database = client[db_name]
            
            # Test basic operations
            test_collection = database.startup_test
            
            # Test insert
            test_doc = {"test": "startup_validation", "timestamp": "now"}
            result = await test_collection.insert_one(test_doc)
            
            # Test find
            found_doc = await test_collection.find_one({"_id": result.inserted_id})
            if not found_doc:
                issues.append("Database insert/find test failed")
            
            # Test update
            await test_collection.update_one(
                {"_id": result.inserted_id},
                {"$set": {"updated": True}}
            )
            
            # Test delete
            await test_collection.delete_one({"_id": result.inserted_id})
            
            # Test index creation (non-critical)
            try:
                await test_collection.create_index("test_field")
            except Exception as e:
                self.logger.warning(f"Index creation test failed (non-critical): {e}")
            
            self._database_details = {
                "connection_successful": True,
                "database_name": db_name,
                "server_info": await client.server_info(),
                "issues": issues
            }
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            issues.append(f"Cannot connect to database: {e}")
            self._database_details = {
                "connection_successful": False,
                "error": str(e),
                "issues": issues
            }
        except Exception as e:
            issues.append(f"Database validation error: {e}")
            self._database_details = {
                "connection_successful": False,
                "error": str(e),
                "issues": issues
            }
        finally:
            if client:
                client.close()
        
        return len(issues) == 0
    
    async def _validate_discord(self) -> bool:
        """Validate Discord API connectivity and bot permissions."""
        self._discord_details = {}
        issues = []
        
        try:
            # Create Discord client for testing
            intents = discord.Intents.default()
            intents.message_content = True
            intents.guilds = True
            
            client = discord.Client(intents=intents)
            
            try:
                # Create a task for the client connection
                connection_task = asyncio.create_task(client.start(self.settings.discord_token))
                
                # Wait for ready event with timeout
                await asyncio.wait_for(
                    self._wait_for_discord_ready(client),
                    timeout=30.0
                )
                
                # Get bot user info
                bot_user = client.user
                if bot_user:
                    self._discord_details.update({
                        "bot_id": bot_user.id,
                        "bot_name": bot_user.name,
                        "bot_discriminator": bot_user.discriminator,
                        "connection_successful": True
                    })
                else:
                    issues.append("Failed to get bot user information")
                
                # Check basic permissions in guilds
                guild_count = len(client.guilds)
                self._discord_details["guild_count"] = guild_count
                
                if guild_count == 0:
                    self.logger.warning("Bot is not in any guilds. This is normal for new bots.")
                
                # Test application info
                try:
                    app_info = await client.application_info()
                    self._discord_details["application_name"] = app_info.name
                    self._discord_details["application_id"] = app_info.id
                except Exception as e:
                    self.logger.warning(f"Could not fetch application info: {e}")
                
            except asyncio.TimeoutError:
                issues.append("Discord connection timeout (30 seconds)")
            except discord.LoginFailure:
                issues.append("Invalid Discord token")
            except discord.HTTPException as e:
                issues.append(f"Discord HTTP error: {e}")
            except Exception as e:
                issues.append(f"Discord connection error: {e}")
            finally:
                # Properly close the client and cancel the connection task
                if not client.is_closed():
                    await client.close()
                
                # Cancel the connection task if it's still running
                if 'connection_task' in locals() and not connection_task.done():
                    connection_task.cancel()
                    try:
                        await connection_task
                    except asyncio.CancelledError:
                        pass
                
        except Exception as e:
            issues.append(f"Discord validation setup error: {e}")
        
        self._discord_details["issues"] = issues
        return len(issues) == 0
    
    async def _wait_for_discord_ready(self, client: discord.Client) -> None:
        """Wait for Discord client to be ready."""
        while not client.is_ready():
            await asyncio.sleep(0.1)
    
    def _generate_summary(self) -> Dict[str, Any]:
        """Generate a summary of validation results."""
        total_checks = len(self.validation_results)
        passed_checks = sum(1 for result in self.validation_results.values() if result["passed"])
        
        failed_categories = [
            category for category, result in self.validation_results.items()
            if not result["passed"]
        ]
        
        return {
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "failed_checks": total_checks - passed_checks,
            "success_rate": f"{(passed_checks / total_checks * 100):.1f}%" if total_checks > 0 else "0%",
            "failed_categories": failed_categories
        }
    
    def print_detailed_report(self) -> None:
        """Print a detailed validation report to console."""
        print("\n" + "="*60)
        print("🔍 STARTUP VALIDATION REPORT")
        print("="*60)
        
        for category, result in self.validation_results.items():
            status = "✅ PASSED" if result["passed"] else "❌ FAILED"
            print(f"\n{category.upper()}: {status}")
            
            if not result["passed"]:
                if "error" in result:
                    print(f"  Error: {result['error']}")
                
                details = result.get("details", {})
                issues = details.get("issues", [])
                if issues:
                    print("  Issues:")
                    for issue in issues:
                        print(f"    • {issue}")
        
        summary = self._generate_summary()
        print(f"\n📊 SUMMARY:")
        print(f"  Total Checks: {summary['total_checks']}")
        print(f"  Passed: {summary['passed_checks']}")
        print(f"  Failed: {summary['failed_checks']}")
        print(f"  Success Rate: {summary['success_rate']}")
        
        if summary['failed_categories']:
            print(f"  Failed Categories: {', '.join(summary['failed_categories'])}")
        
        print("="*60)


async def run_startup_validation(settings: Optional[Settings] = None) -> Tuple[bool, Dict[str, Any]]:
    """
    Convenience function to run startup validation.
    
    Args:
        settings: Optional settings instance
        
    Returns:
        Tuple of (success, results)
    """
    validator = StartupValidator(settings)
    return await validator.validate_all()


if __name__ == "__main__":
    """Run validation as standalone script."""
    async def main():
        try:
            settings = Settings()
            validator = StartupValidator(settings)
            success, results = await validator.validate_all()
            
            validator.print_detailed_report()
            
            if not success:
                sys.exit(1)
            else:
                print("\n🎉 All validations passed! Bot is ready to start.")
                
        except Exception as e:
            print(f"❌ Validation script error: {e}")
            sys.exit(1)
    
    asyncio.run(main())