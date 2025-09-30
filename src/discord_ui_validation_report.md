# Discord UI Validation Report

## Summary
- **Commands Found:** 22
- **Total Issues:** 18
- **Critical:** 0
- **Errors:** 0
- **Warnings:** 13
- **Info:** 5

## Warning Issues

### Command: event-manage, Parameter: event_id
**Category:** Parameter Documentation
**Issue:** Parameter has no description
**Recommendation:** Add @app_commands.describe() with parameter descriptions
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/events.py:880

### Command: calendar, Parameter: days_ahead
**Category:** Parameter Documentation
**Issue:** Parameter has no description
**Recommendation:** Add @app_commands.describe() with parameter descriptions
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/events.py:1499

### Command: sync-rsvps, Parameter: event_id
**Category:** Parameter Documentation
**Issue:** Parameter has no description
**Recommendation:** Add @app_commands.describe() with parameter descriptions
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/events.py:1590

### Command: retry-discord-event, Parameter: event_id
**Category:** Parameter Documentation
**Issue:** Parameter has no description
**Recommendation:** Add @app_commands.describe() with parameter descriptions
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/events.py:1640

### Command: poll-extend, Parameter: event_id
**Category:** Parameter Documentation
**Issue:** Parameter has no description
**Recommendation:** Add @app_commands.describe() with parameter descriptions
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/events.py:2002

### Command: poll-extend, Parameter: poll_type
**Category:** Parameter Documentation
**Issue:** Parameter has no description
**Recommendation:** Add @app_commands.describe() with parameter descriptions
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/events.py:2002

### Command: poll-extend, Parameter: minutes
**Category:** Parameter Documentation
**Issue:** Parameter has no description
**Recommendation:** Add @app_commands.describe() with parameter descriptions
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/events.py:2002

### Command: poll-analytics, Parameter: event_id
**Category:** Parameter Documentation
**Issue:** Parameter has no description
**Recommendation:** Add @app_commands.describe() with parameter descriptions
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/events.py:2072

### Command: poll-analytics, Parameter: poll_type
**Category:** Parameter Documentation
**Issue:** Parameter has no description
**Recommendation:** Add @app_commands.describe() with parameter descriptions
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/events.py:2072

### Command: games-popular, Parameter: limit
**Category:** Parameter Documentation
**Issue:** Parameter has no description
**Recommendation:** Add @app_commands.describe() with parameter descriptions
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/games.py:735

### Command: games-trending, Parameter: limit
**Category:** Parameter Documentation
**Issue:** Parameter has no description
**Recommendation:** Add @app_commands.describe() with parameter descriptions
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/games.py:772

### Command: games-search, Parameter: query
**Category:** Parameter Documentation
**Issue:** Parameter has no description
**Recommendation:** Add @app_commands.describe() with parameter descriptions
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/games.py:809

### Command: timezone, Parameter: timezone
**Category:** Parameter Documentation
**Issue:** Parameter has no description
**Recommendation:** Add @app_commands.describe() with parameter descriptions
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/users.py:510

## Info Issues

### Embed in users.py:405
**Category:** Embed Consistency
**Issue:** Embed has no timestamp
**Recommendation:** Add timestamp=datetime.utcnow() for consistency
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/users.py:405

### Embed in users.py:667
**Category:** Embed Consistency
**Issue:** Embed has no timestamp
**Recommendation:** Add timestamp=datetime.utcnow() for consistency
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/users.py:667

### Embed in users.py:729
**Category:** Embed Consistency
**Issue:** Embed has no timestamp
**Recommendation:** Add timestamp=datetime.utcnow() for consistency
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/users.py:729

### Embed in users.py:782
**Category:** Embed Consistency
**Issue:** Embed has no timestamp
**Recommendation:** Add timestamp=datetime.utcnow() for consistency
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/users.py:782

### Embed in users.py:827
**Category:** Embed Consistency
**Issue:** Embed has no timestamp
**Recommendation:** Add timestamp=datetime.utcnow() for consistency
**Location:** /home/kahnshaak/Documents/MFT-bot/src/cogs/users.py:827
