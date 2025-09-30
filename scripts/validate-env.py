#!/usr/bin/env python3
"""
Environment variable validation script for Discord Game Night Bot.
Run this script to validate your environment configuration before deployment.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any
from urllib.parse import urlparse

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from config.settings import Settings
    from core.startup_validator import StartupValidator
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running this script from the project root directory.")
    sys.exit(1)


def validate_environment_file() -> Tuple[bool, List[str]]:
    """Validate .env file exists and is readable."""
    issues = []
    
    env_file = Path(".env")
    if not env_file.exists():
        issues.append("❌ .env file not found. Copy .env.example to .env and configure it.")
        return False, issues
    
    if not env_file.is_file():
        issues.append("❌ .env exists but is not a file.")
        return False, issues
    
    try:
        with open(env_file, 'r') as f:
            content = f.read()
        
        if not content.strip():
            issues.append("❌ .env file is empty.")
            return False, issues
            
        print("✅ .env file found and readable")
        return True, issues
        
    except PermissionError:
        issues.append("❌ Cannot read .env file (permission denied).")
        return False, issues
    except Exception as e:
        issues.append(f"❌ Error reading .env file: {e}")
        return False, issues


def validate_required_variables() -> Tuple[bool, List[str]]:
    """Validate required environment variables."""
    issues = []
    
    required_vars = {
        "DISCORD_TOKEN": {
            "description": "Discord bot token",
            "validation": lambda x: x and (x.startswith("MTM") or x.startswith("Bot ")),
            "error": "Should be a valid Discord bot token"
        },
        "DISCORD_CLIENT_ID": {
            "description": "Discord application client ID", 
            "validation": lambda x: x and x.isdigit() and len(x) >= 17,
            "error": "Should be a numeric Discord application ID"
        },
        "DISCORD_CLIENT_SECRET": {
            "description": "Discord application client secret",
            "validation": lambda x: x and len(x) >= 20,
            "error": "Should be a valid Discord client secret"
        },
        "JWT_SECRET": {
            "description": "JWT secret for web authentication",
            "validation": lambda x: x and len(x) >= 16,
            "error": "Should be at least 16 characters long"
        }
    }
    
    all_valid = True
    
    for var_name, config in required_vars.items():
        value = os.getenv(var_name)
        
        if not value:
            issues.append(f"❌ Missing required variable: {var_name} ({config['description']})")
            all_valid = False
        elif not config["validation"](value):
            issues.append(f"❌ Invalid {var_name}: {config['error']}")
            all_valid = False
        else:
            # Don't print the actual value for security
            print(f"✅ {var_name}: Valid")
    
    return all_valid, issues


def validate_optional_variables() -> Tuple[bool, List[str]]:
    """Validate optional environment variables."""
    issues = []
    warnings = []
    
    optional_vars = {
        "DATABASE_URL": {
            "default": "mongodb://localhost:27017/gamenight_bot",
            "validation": lambda x: urlparse(x).scheme in ["mongodb", "mongodb+srv"],
            "error": "Should be a valid MongoDB connection string"
        },
        "LOG_LEVEL": {
            "default": "INFO",
            "validation": lambda x: x.upper() in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            "error": "Should be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL"
        },
        "WEB_PORT": {
            "default": "8000",
            "validation": lambda x: x.isdigit() and 1 <= int(x) <= 65535,
            "error": "Should be a valid port number (1-65535)"
        },
        "ENVIRONMENT": {
            "default": "development",
            "validation": lambda x: x.lower() in ["development", "production", "testing"],
            "error": "Should be one of: development, production, testing"
        }
    }
    
    all_valid = True
    
    for var_name, config in optional_vars.items():
        value = os.getenv(var_name, config["default"])
        
        if not config["validation"](value):
            issues.append(f"❌ Invalid {var_name}: {config['error']} (current: {value})")
            all_valid = False
        else:
            print(f"✅ {var_name}: {value}")
    
    # Check for common issues
    db_url = os.getenv("DATABASE_URL", "mongodb://localhost:27017/gamenight_bot")
    if "localhost" in db_url and os.getenv("ENVIRONMENT", "development") == "production":
        warnings.append("⚠️  Using localhost database in production environment")
    
    if os.getenv("JWT_SECRET") == "your_jwt_secret_key_here":
        issues.append("❌ JWT_SECRET is still set to default value. Generate a secure secret!")
        all_valid = False
    
    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"  {warning}")
    
    return all_valid, issues


def check_file_permissions() -> Tuple[bool, List[str]]:
    """Check file and directory permissions."""
    issues = []
    
    # Check logs directory
    logs_dir = Path("logs")
    if not logs_dir.exists():
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
            print("✅ Created logs directory")
        except Exception as e:
            issues.append(f"❌ Cannot create logs directory: {e}")
            return False, issues
    
    # Test write permission to logs directory
    try:
        test_file = logs_dir / "test_write.tmp"
        with open(test_file, 'w') as f:
            f.write("test")
        test_file.unlink()
        print("✅ Logs directory is writable")
    except Exception as e:
        issues.append(f"❌ Cannot write to logs directory: {e}")
        return False, issues
    
    # Check src directory exists
    src_dir = Path("src")
    if not src_dir.exists() or not src_dir.is_dir():
        issues.append("❌ src directory not found")
        return False, issues
    
    print("✅ File permissions OK")
    return True, issues


def generate_env_template() -> None:
    """Generate a .env template with secure defaults."""
    import secrets
    
    template = f"""# Discord Bot Configuration (REQUIRED)
DISCORD_TOKEN=your_bot_token_here
DISCORD_CLIENT_ID=your_client_id_here
DISCORD_CLIENT_SECRET=your_client_secret_here

# Database Configuration
DATABASE_URL=mongodb://admin:password@localhost:27017/gamenight_bot?authSource=admin

# Web Dashboard Configuration
JWT_SECRET={secrets.token_urlsafe(32)}
WEB_HOST=0.0.0.0
WEB_PORT=8000

# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE_PATH=logs/gamenight_bot.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5

# Environment
ENVIRONMENT=development

# Security
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000

# Rate Limiting
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_BURST=10
"""
    
    with open(".env.generated", 'w') as f:
        f.write(template)
    
    print("✅ Generated .env.generated with secure defaults")
    print("   Copy this to .env and update the Discord configuration")


async def run_full_validation() -> bool:
    """Run the full startup validation."""
    print("\n🔍 Running comprehensive startup validation...")
    
    try:
        validator = StartupValidator()
        success, results = await validator.validate_all()
        
        if success:
            print("✅ Full validation passed!")
        else:
            print("❌ Full validation failed!")
            validator.print_detailed_report()
        
        return success
        
    except Exception as e:
        print(f"❌ Validation error: {e}")
        return False


def main():
    """Main validation function."""
    print("🔧 Discord Game Night Bot - Environment Validation")
    print("=" * 50)
    
    all_checks_passed = True
    
    # Check .env file
    print("\n📁 Checking .env file...")
    env_ok, env_issues = validate_environment_file()
    if not env_ok:
        for issue in env_issues:
            print(f"  {issue}")
        
        print("\n💡 Generating .env template...")
        generate_env_template()
        all_checks_passed = False
    
    # Load environment variables
    if env_ok:
        from dotenv import load_dotenv
        load_dotenv()
    
    # Check required variables
    print("\n🔑 Checking required environment variables...")
    req_ok, req_issues = validate_required_variables()
    if not req_ok:
        for issue in req_issues:
            print(f"  {issue}")
        all_checks_passed = False
    
    # Check optional variables
    print("\n⚙️  Checking optional environment variables...")
    opt_ok, opt_issues = validate_optional_variables()
    if not opt_ok:
        for issue in opt_issues:
            print(f"  {issue}")
        all_checks_passed = False
    
    # Check file permissions
    print("\n📂 Checking file permissions...")
    perm_ok, perm_issues = check_file_permissions()
    if not perm_ok:
        for issue in perm_issues:
            print(f"  {issue}")
        all_checks_passed = False
    
    # Run full validation if basic checks pass
    if all_checks_passed and env_ok:
        import asyncio
        full_validation_ok = asyncio.run(run_full_validation())
        all_checks_passed = all_checks_passed and full_validation_ok
    
    # Summary
    print("\n" + "=" * 50)
    if all_checks_passed:
        print("🎉 All validation checks passed!")
        print("   Your environment is ready for deployment.")
    else:
        print("❌ Some validation checks failed.")
        print("   Please fix the issues above before deploying.")
        
        print("\n💡 Quick fixes:")
        print("   1. Copy .env.example to .env (or use .env.generated)")
        print("   2. Set your Discord bot token and client credentials")
        print("   3. Ensure MongoDB is running and accessible")
        print("   4. Generate secure secrets for production")
    
    return all_checks_passed


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 Validation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)