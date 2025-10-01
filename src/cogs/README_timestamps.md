# Timestamps Cog Documentation

The Timestamps cog provides comprehensive timezone conversion and Discord timestamp utilities for the Game Night Bot.

## Features

### 🔄 Time Conversion
- Convert times between any timezones
- Support for natural language time input
- Multiple timezone display
- Interactive conversion tools

### 🌍 Timezone Management
- Comprehensive timezone lookup
- Timezone alias support (EST, PST, GMT, etc.)
- Fuzzy matching for timezone names
- Current time display across timezones

### 📅 Discord Timestamp Generation
- All Discord timestamp formats supported
- Preview functionality
- Copy-paste ready formats
- Automatic timezone handling

### ⏰ Natural Language Parsing
- Parse human-readable time expressions
- Support for relative times ("tomorrow at 8pm")
- Named times (noon, midnight, morning, etc.)
- Multiple date formats

## Commands

### `/convert`
Convert time between timezones.

**Parameters:**
- `time_input` - Time to convert (e.g., "2:30 PM", "tomorrow at 8pm", "14:30")
- `from_timezone` - Source timezone (e.g., "EST", "America/New_York")
- `to_timezone` - Target timezone (optional - shows multiple if not specified)

**Examples:**
```
/convert time_input:2:30 PM from_timezone:EST to_timezone:PST
/convert time_input:tomorrow at 8pm from_timezone:America/New_York
/convert time_input:14:30 from_timezone:UTC to_timezone:Asia/Tokyo
```

### `/timezone`
Look up timezone information.

**Parameters:**
- `timezone` - Timezone to look up (e.g., "EST", "America/New_York")

**Examples:**
```
/timezone timezone:EST
/timezone timezone:America/New_York
/timezone timezone:london
```

### `/timestamp`
Generate Discord timestamp formats.

**Parameters:**
- `time_input` - Time to format (e.g., "2:30 PM tomorrow", "2024-01-15 14:30")
- `timezone` - Timezone for input time (default: UTC)
- `format_type` - Discord timestamp format (optional - shows all if not specified)

**Examples:**
```
/timestamp time_input:tomorrow at 8pm timezone:EST
/timestamp time_input:2024-12-25 15:30 timezone:UTC format_type:Long Date/Time
/timestamp time_input:next friday 7pm timezone:America/New_York
```

### `/timenow`
Show current time in multiple timezones.

**Examples:**
```
/timenow
```

## Supported Time Formats

### Absolute Times
- `2:30 PM`, `14:30`, `2:30:45`
- `12:00 AM` (midnight), `12:00 PM` (noon)
- `0:00` (midnight), `23:59`

### Named Times
- `noon`, `midday` (12:00)
- `midnight` (00:00)
- `morning` (09:00)
- `afternoon` (14:00)
- `evening` (18:00)
- `night` (21:00)

### Relative Times
- `in 30 minutes`, `in 2 hours`, `in 3 days`
- `tomorrow`, `yesterday`, `today`
- `next monday`, `this friday`

### Complete DateTime
- `2024-01-15 14:30:00`
- `01/15/2024 2:30 PM`
- `15-01-2024 14:30`

## Supported Timezones

### Timezone Aliases
The cog supports common timezone abbreviations:

**US Timezones:**
- EST/EDT → America/New_York
- CST/CDT → America/Chicago
- MST/MDT → America/Denver
- PST/PDT → America/Los_Angeles
- AKST/AKDT → America/Anchorage
- HST → Pacific/Honolulu

**European Timezones:**
- GMT/BST → Europe/London
- CET/CEST → Europe/Paris
- EET/EEST → Europe/Helsinki

**Asian Timezones:**
- JST → Asia/Tokyo
- KST → Asia/Seoul
- IST → Asia/Kolkata

**Australian Timezones:**
- AEST/AEDT → Australia/Sydney
- ACST/ACDT → Australia/Adelaide
- AWST → Australia/Perth

### Full Timezone Names
All IANA timezone database names are supported:
- `America/New_York`
- `Europe/London`
- `Asia/Tokyo`
- `Australia/Sydney`
- And many more...

### Fuzzy Matching
The cog supports fuzzy matching for timezone names:
- `new york` → `America/New_York`
- `london` → `Europe/London`
- `tokyo` → `Asia/Tokyo`
- `los angeles` → `America/Los_Angeles`

## Discord Timestamp Formats

The cog generates all Discord timestamp formats:

| Format | Code | Example Output |
|--------|------|----------------|
| Short Time | `t` | `3:30 PM` |
| Long Time | `T` | `3:30:00 PM` |
| Short Date | `d` | `12/25/2024` |
| Long Date | `D` | `December 25, 2024` |
| Short Date/Time | `f` | `December 25, 2024 3:30 PM` |
| Long Date/Time | `F` | `Tuesday, December 25, 2024 3:30 PM` |
| Relative | `R` | `in 2 hours` |

## Interactive Features

### Time Conversion View
When converting times, users get interactive buttons to:
- Convert to other timezones
- Show all Discord timestamp formats
- Copy timestamp codes

### Timezone Lookup Modal
Users can look up timezone information with:
- Current time display
- UTC offset information
- Daylight saving status
- Discord timestamp generation

## Error Handling

The cog provides comprehensive error handling:

### Invalid Time Input
- Clear error messages for malformed times
- Suggestions for correct formats
- Validation of time ranges (0-23 hours, 0-59 minutes)

### Invalid Timezones
- Fuzzy matching suggestions
- Clear error messages
- Tips for finding correct timezone names

### Edge Cases
- Handles daylight saving time transitions
- Validates date ranges
- Proper handling of midnight/noon in 12-hour format

## Usage Examples

### Basic Time Conversion
```
User: /convert time_input:3:30 PM from_timezone:EST to_timezone:PST
Bot: 🔄 Time Conversion
     From: America/New_York
     3:30 PM EST (15:30)
     
     To: America/Los_Angeles  
     12:30 PM PST (12:30)
     
     Discord Timestamp: <t:1234567890:F>
```

### Natural Language Parsing
```
User: /convert time_input:tomorrow at 8pm from_timezone:America/New_York
Bot: 🌍 Time Conversion
     Source: tomorrow at 8pm in America/New_York
     
     UTC: 01:00 AM (next day)
     London: 02:00 AM (next day)
     Tokyo: 10:00 AM (next day)
     ...
```

### Timezone Information
```
User: /timezone timezone:JST
Bot: 🌍 Timezone: Asia/Tokyo
     Current Time: 2024-01-15 22:30:00
     Abbreviation: JST
     UTC Offset: +0900
     Daylight Saving: ❌ Not Active
     Discord Timestamp: <t:1234567890:F>
```

### Discord Timestamp Generation
```
User: /timestamp time_input:2024-12-25 15:30 timezone:UTC
Bot: 📅 Discord Timestamp Formats
     Time: 2024-12-25 15:30:00 UTC
     
     Short Time (t): <t:1735140600:t> → 3:30 PM
     Long Time (T): <t:1735140600:T> → 3:30:00 PM
     Short Date (d): <t:1735140600:d> → 12/25/2024
     ...
```

## Requirements Satisfied

This implementation satisfies the following requirements from the specification:

- **5.1**: Timezone preference system with automatic time conversion
- **5.2**: Timezone conversion helpers for cross-timezone coordination
- **5.5**: Discord timestamp format generation for all supported formats
- **5.6**: Time parsing system for natural language input

## Technical Implementation

### Core Components
- `TimestampsCog`: Main cog class with command handlers
- `TimezoneModal`: Interactive timezone lookup
- `TimeConversionView`: Interactive conversion interface
- `TimezoneConversionModal`: Timezone-to-timezone conversion

### Key Methods
- `parse_time_input()`: Natural language time parsing
- `lookup_timezone()`: Timezone resolution with fuzzy matching
- `convert_time_to_timezone()`: Timezone conversion
- `create_*_embed()`: Discord embed generation

### Dependencies
- `zoneinfo`: Modern timezone handling (Python 3.9+)
- `pytz`: Fallback timezone support
- `discord.py`: Discord integration
- Core bot framework components

## Future Enhancements

Potential improvements for future versions:
- Calendar integration
- Recurring time reminders
- Time zone meeting planner
- Historical timezone data
- Custom timezone aliases per server
- Integration with user profiles for default timezones