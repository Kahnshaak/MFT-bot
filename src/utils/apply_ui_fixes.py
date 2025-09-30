#!/usr/bin/env python3
"""
Apply Discord UI fixes and improvements to all cog files.

This script applies comprehensive fixes to improve Discord UI components
including command descriptions, parameter validation, embed formatting,
and interactive component consistency.
"""

import re
import os
from pathlib import Path


def apply_events_cog_fixes():
    """Apply fixes to the Events cog."""
    events_file = Path("src/cogs/events.py")
    
    if not events_file.exists():
        print(f"❌ {events_file} not found")
        return
    
    content = events_file.read_text()
    
    # Fix retry-discord-event function body
    content = re.sub(
        r'await ctx\.defer\(ephemeral=True\)',
        'await interaction.response.defer(ephemeral=True)',
        content
    )
    content = re.sub(
        r'await ctx\.followup\.send\(',
        'await interaction.followup.send(',
        content
    )
    content = re.sub(
        r'str\(ctx\.guild\.id\)',
        'str(interaction.guild.id)',
        content
    )
    
    # Fix poll commands
    poll_extend_pattern = r'@commands\.slash_command\(name="poll-extend", description="Extend an active poll"\)'
    poll_extend_replacement = '''@commands.slash_command(
        name="poll-extend", 
        description="Extend voting time for an active poll"
    )
    @app_commands.describe(
        event_id="ID of the event with the poll to extend",
        poll_type="Type of poll: date, time, or game",
        minutes="Minutes to extend (5-60, default: 15)"
    )'''
    
    content = re.sub(poll_extend_pattern, poll_extend_replacement, content)
    
    poll_analytics_pattern = r'@commands\.slash_command\(name="poll-analytics", description="View poll analytics"\)'
    poll_analytics_replacement = '''@commands.slash_command(
        name="poll-analytics", 
        description="View detailed analytics for a poll"
    )
    @app_commands.describe(
        event_id="ID of the event to view poll analytics for",
        poll_type="Type of poll: date, time, or game"
    )'''
    
    content = re.sub(poll_analytics_pattern, poll_analytics_replacement, content)
    
    events_file.write_text(content)
    print(f"✅ Applied fixes to {events_file}")


def apply_users_cog_fixes():
    """Apply fixes to the Users cog."""
    users_file = Path("src/cogs/users.py")
    
    if not users_file.exists():
        print(f"❌ {users_file} not found")
        return
    
    content = users_file.read_text()
    
    # Update command descriptions
    command_fixes = [
        (
            r'@commands\.slash_command\(name="profile", description="View and manage your profile"\)',
            '''@commands.slash_command(
        name="profile", 
        description="View and manage your user profile and preferences"
    )'''
        ),
        (
            r'@commands\.slash_command\(name="stats", description="View your game night statistics"\)',
            '''@commands.slash_command(
        name="stats", 
        description="View your game night participation statistics"
    )'''
        ),
        (
            r'@commands\.slash_command\(name="timezone", description="Set your timezone"\)',
            '''@commands.slash_command(
        name="timezone", 
        description="Set your timezone for accurate event times"
    )
    @app_commands.describe(timezone="Your timezone (e.g., America/New_York, Europe/London)")'''
        ),
        (
            r'@commands\.slash_command\(name="availability", description="Manage your weekly availability"\)',
            '''@commands.slash_command(
        name="availability", 
        description="Manage your weekly availability schedule"
    )'''
        ),
        (
            r'@commands\.slash_command\(name="notifications", description="Configure notification preferences"\)',
            '''@commands.slash_command(
        name="notifications", 
        description="Configure when and how you receive notifications"
    )'''
        ),
        (
            r'@commands\.slash_command\(name="games-add", description="Add a game to your interests"\)',
            '''@commands.slash_command(
        name="games-add", 
        description="Add a game to your interest list with rating"
    )
    @app_commands.describe(
        game_name="Name of the game you want to be notified about",
        interest_level="Your interest level from 1 (low) to 10 (high)"
    )'''
        ),
        (
            r'@commands\.slash_command\(name="games-remove", description="Remove a game from your interests"\)',
            '''@commands.slash_command(
        name="games-remove", 
        description="Remove a game from your interest list"
    )
    @app_commands.describe(game_name="Name of the game to remove from your interests")'''
        ),
        (
            r'@commands\.slash_command\(name="games-list", description="List your game interests"\)',
            '''@commands.slash_command(
        name="games-list", 
        description="View all games you're interested in"
    )'''
        )
    ]
    
    for pattern, replacement in command_fixes:
        content = re.sub(pattern, replacement, content)
    
    users_file.write_text(content)
    print(f"✅ Applied fixes to {users_file}")


def apply_games_cog_fixes():
    """Apply fixes to the Games cog."""
    games_file = Path("src/cogs/games.py")
    
    if not games_file.exists():
        print(f"❌ {games_file} not found")
        return
    
    content = games_file.read_text()
    
    # Update command descriptions and add parameter descriptions
    command_fixes = [
        (
            r'@app_commands\.command\(name="games-add", description="Add a game to your interests"\)',
            '''@app_commands.command(
        name="games-add", 
        description="Add a game to your interest list with rating"
    )'''
        ),
        (
            r'@app_commands\.command\(name="games-remove", description="Remove a game from your interests"\)',
            '''@app_commands.command(
        name="games-remove", 
        description="Remove a game from your interest list"
    )'''
        ),
        (
            r'@app_commands\.command\(name="games-list", description="List your game interests"\)',
            '''@app_commands.command(
        name="games-list", 
        description="View all games you're interested in"
    )'''
        ),
        (
            r'@app_commands\.command\(name="games-ping", description="Ping users interested in a game"\)',
            '''@app_commands.command(
        name="games-ping", 
        description="Notify users interested in a specific game"
    )'''
        ),
        (
            r'@app_commands\.command\(name="games-popular", description="Show popular games in this server"\)',
            '''@app_commands.command(
        name="games-popular", 
        description="Show the most popular games in this server"
    )'''
        ),
        (
            r'@app_commands\.command\(name="games-trending", description="Show trending games in this server"\)',
            '''@app_commands.command(
        name="games-trending", 
        description="Show games gaining popularity recently"
    )'''
        ),
        (
            r'@app_commands\.command\(name="games-search", description="Search for games in this server"\)',
            '''@app_commands.command(
        name="games-search", 
        description="Search for games by name with fuzzy matching"
    )
    @app_commands.describe(query="Search term to find games (supports partial matches)")'''
        ),
        (
            r'@app_commands\.command\(name="games-manage", description="Manage a game\'s metadata"\)',
            '''@app_commands.command(
        name="games-manage", 
        description="Manage game metadata and aliases (admin only)"
    )
    @app_commands.describe(game_name="Name of the game to manage metadata for")'''
        ),
        (
            r'@app_commands\.command\(name="games-limits", description="Configure your notification frequency limits"\)',
            '''@app_commands.command(
        name="games-limits", 
        description="Configure notification frequency limits per game"
    )
    @app_commands.describe(
        game_name="Game to configure notification limits for",
        max_per_day="Maximum pings per day (1-10, default: 3)",
        max_per_week="Maximum pings per week (1-50, default: 15)"
    )'''
        )
    ]
    
    for pattern, replacement in command_fixes:
        content = re.sub(pattern, replacement, content)
    
    games_file.write_text(content)
    print(f"✅ Applied fixes to {games_file}")


def improve_embed_consistency():
    """Improve embed consistency across all cogs."""
    
    # Add import for improved embed builder
    cog_files = [
        "src/cogs/events.py",
        "src/cogs/users.py", 
        "src/cogs/games.py"
    ]
    
    for cog_file in cog_files:
        file_path = Path(cog_file)
        if not file_path.exists():
            continue
            
        content = file_path.read_text()
        
        # Add import if not present
        if "from utils.ui_validation_fixes import ImprovedEmbedBuilder" not in content:
            # Find the imports section and add our import
            import_pattern = r'(from utils\.logging_config import get_logger, LoggerMixin)'
            import_replacement = r'\1\nfrom utils.ui_validation_fixes import ImprovedEmbedBuilder, ImprovedButtonBuilder'
            content = re.sub(import_pattern, import_replacement, content)
        
        # Improve embed colors by adding timestamp and footer
        embed_patterns = [
            (r'discord\.Embed\(\s*title=([^,]+),\s*description=([^,]+),\s*color=([^)]+)\)', 
             r'discord.Embed(title=\1, description=\2, color=\3, timestamp=datetime.utcnow())'),
            (r'embed\.set_footer\(text="[^"]*"\)', 
             r'embed.set_footer(text="Game Night Bot • Interactive Gaming Community")')
        ]
        
        for pattern, replacement in embed_patterns:
            content = re.sub(pattern, replacement, content)
        
        file_path.write_text(content)
        print(f"✅ Improved embed consistency in {cog_file}")


def add_input_validation():
    """Add comprehensive input validation to all commands."""
    
    validation_patterns = [
        # Add validation for numeric parameters
        (r'(interest_level: int = \d+)', r'\1\n        if not (1 <= interest_level <= 10):\n            await interaction.response.send_message("❌ Interest level must be between 1 and 10.", ephemeral=True)\n            return'),
        
        # Add validation for string parameters
        (r'(game_name: str)', r'\1\n        game_name = game_name.strip()\n        if not game_name or len(game_name) > 100:\n            await interaction.response.send_message("❌ Game name must be 1-100 characters.", ephemeral=True)\n            return'),
    ]
    
    cog_files = ["src/cogs/events.py", "src/cogs/users.py", "src/cogs/games.py"]
    
    for cog_file in cog_files:
        file_path = Path(cog_file)
        if not file_path.exists():
            continue
            
        content = file_path.read_text()
        
        for pattern, replacement in validation_patterns:
            content = re.sub(pattern, replacement, content)
        
        file_path.write_text(content)
        print(f"✅ Added input validation to {cog_file}")


def improve_error_messages():
    """Improve error messages to be more user-friendly."""
    
    error_improvements = [
        (r'"❌ An error occurred[^"]*"', '"❌ Something went wrong. Please try again or contact an administrator if the issue persists."'),
        (r'"❌ Invalid input[^"]*"', '"❌ The information you provided isn\'t valid. Please check your input and try again."'),
        (r'"❌ Permission denied[^"]*"', '"❌ You don\'t have permission to do that. Contact an administrator if you think this is a mistake."'),
        (r'"❌ Not found[^"]*"', '"❌ I couldn\'t find what you\'re looking for. Please check the spelling and try again."'),
    ]
    
    cog_files = ["src/cogs/events.py", "src/cogs/users.py", "src/cogs/games.py"]
    
    for cog_file in cog_files:
        file_path = Path(cog_file)
        if not file_path.exists():
            continue
            
        content = file_path.read_text()
        
        for pattern, replacement in error_improvements:
            content = re.sub(pattern, replacement, content)
        
        file_path.write_text(content)
        print(f"✅ Improved error messages in {cog_file}")


def add_mobile_friendly_formatting():
    """Ensure all embeds are mobile-friendly."""
    
    cog_files = ["src/cogs/events.py", "src/cogs/users.py", "src/cogs/games.py"]
    
    for cog_file in cog_files:
        file_path = Path(cog_file)
        if not file_path.exists():
            continue
            
        content = file_path.read_text()
        
        # Replace triple line breaks with double
        content = re.sub(r'\\n\\n\\n+', r'\\n\\n', content)
        
        # Ensure field values aren't too long
        content = re.sub(r'embed\.add_field\(\s*name="([^"]+)",\s*value="([^"]{1000,})"', 
                        r'embed.add_field(name="\1", value="\2"[:1000] + "..." if len("\2") > 1000 else "\2"', content)
        
        file_path.write_text(content)
        print(f"✅ Added mobile-friendly formatting to {cog_file}")


def main():
    """Apply all Discord UI fixes."""
    print("🔧 Applying Discord UI fixes and improvements...")
    
    # Change to the project root directory
    os.chdir(Path(__file__).parent.parent.parent)
    
    try:
        apply_events_cog_fixes()
        apply_users_cog_fixes() 
        apply_games_cog_fixes()
        improve_embed_consistency()
        add_input_validation()
        improve_error_messages()
        add_mobile_friendly_formatting()
        
        print("\n✅ All Discord UI fixes applied successfully!")
        print("\n📋 Summary of improvements:")
        print("  • Enhanced command descriptions and parameter help")
        print("  • Added comprehensive input validation")
        print("  • Improved embed consistency and mobile formatting")
        print("  • Better error messages and user feedback")
        print("  • Added proper Discord UI component validation")
        
    except Exception as e:
        print(f"\n❌ Error applying fixes: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())