# Core Framework Documentation

This directory contains the core framework components for the Discord Game Night Bot. These components provide the foundation for all bot functionality including event handling, security, validation, metrics, and audit logging.

## Components Overview

### 1. Event Bus (`event_bus.py`)
The event bus provides a publish-subscribe pattern for loose coupling between different parts of the bot system.

**Key Features:**
- Typed event handling with `EventType` enum
- Priority-based subscriber ordering
- Middleware support for cross-cutting concerns
- Error isolation between subscribers
- Event history tracking
- Async/await support

**Usage Example:**
```python
# Subscribe to events
event_bus.subscribe(EventType.EVENT_CREATED, my_callback)

# Emit events
await event_bus.emit(
    EventType.EVENT_CREATED,
    {"event_id": "123", "title": "Game Night"},
    source="events_cog",
    guild_id="456",
    user_id="789"
)
```

### 2. Security Manager (`security_manager.py`)
Centralized security management for authentication, authorization, and input validation.

**Key Features:**
- Role-based permission system
- Rate limiting with configurable buckets
- Input validation and sanitization
- Session token management
- CSRF protection
- Audit logging integration

**Usage Example:**
```python
# Configure role permissions
security.configure_role_mapping(guild_id, role_id, {Permission.CREATE_EVENTS})

# Check permissions
security.require_permission(user, guild_id, Permission.CREATE_EVENTS)

# Validate input
clean_input = security.validate_input(user_input, max_length=100)
```

### 3. Permission Decorators (`permission_decorators.py`)
Decorators for easy permission checking and rate limiting on commands.

**Key Features:**
- `@require_permission()` - Require specific permissions
- `@require_any_permission()` - Require any of multiple permissions
- `@rate_limit()` - Apply rate limiting
- `@validate_input()` - Validate command parameters
- Resource ownership checking
- Discord.py command check integration

**Usage Example:**
```python
@require_permission(Permission.CREATE_EVENTS)
@rate_limit(max_requests=5, window_seconds=300)
async def create_event(self, ctx, title: str):
    # Command implementation
    pass
```

### 4. Validation Manager (`validation_manager.py`)
Comprehensive input validation and sanitization system.

**Key Features:**
- Type-based validation rules
- Global validation rules for common types
- Custom validation functions
- Sanitization functions
- Security-focused validation (Discord mentions, etc.)
- Extensible rule system

**Usage Example:**
```python
# Validate a field
validated_title = validation.validate_field("event_title", user_input)

# Validate multiple fields
validated_data = validation.validate_data({
    "title": "Game Night",
    "description": "Weekly game night event"
})
```

### 5. Metrics Collector (`metrics_collector.py`)
Metrics collection system for monitoring bot performance and usage.

**Key Features:**
- Counter, gauge, histogram, and timer metrics
- Command execution tracking
- Error rate monitoring
- Performance statistics
- Exportable metrics data
- Context manager for timing operations

**Usage Example:**
```python
# Record metrics
metrics.record_counter("commands_executed", 1.0, {"command": "create_event"})
metrics.record_gauge("active_events", 42)

# Time operations
with metrics.timer("database_query"):
    result = await database.query()
```

### 6. Health Monitor (`health_monitor.py`)
Health monitoring system with database and Discord API checks.

**Key Features:**
- Configurable health checks
- Database connectivity monitoring
- Discord API health checking
- Memory usage monitoring
- Automatic alerting
- Health status aggregation

**Usage Example:**
```python
# Start monitoring
await health_monitor.start_monitoring(interval_seconds=60)

# Get health status
status = health_monitor.get_overall_health()
summary = health_monitor.get_health_summary()
```

### 7. Audit Logger (`audit_logger.py`)
Audit logging system for tracking administrative actions and security events.

**Key Features:**
- Comprehensive audit event types
- Structured audit logging
- User activity tracking
- Security event monitoring
- Configurable retention policies
- Query and reporting capabilities

**Usage Example:**
```python
# Log audit events
await audit_logger.log_event(
    AuditEventType.EVENT_CREATED,
    "Created new event",
    user_id="123",
    guild_id="456",
    resource_id="event_789"
)

# Get user activity
activity = await audit_logger.get_user_activity("123", days=30)
```

## Integration with Bot

The core framework is integrated into the main bot class (`bot.py`) and provides:

1. **Automatic Error Handling**: Global error handlers that log to metrics and audit systems
2. **Event Bus Middleware**: Automatic metrics recording and audit logging for events
3. **Command Error Handling**: Proper error responses with logging
4. **Health Monitoring**: Automatic health checks and alerting

## Best Practices

### 1. Permission Checking
Always use the permission decorators or security manager for authorization:

```python
# Good
@require_permission(Permission.CREATE_EVENTS)
async def create_event(self, ctx):
    pass

# Also good
security.require_permission(user, guild_id, Permission.CREATE_EVENTS)
```

### 2. Input Validation
Validate all user input using the validation manager:

```python
# Good
validated_title = validation.validate_field("event_title", user_input)

# For complex validation
rule = ValidationRule(
    field_name="custom_field",
    validation_type=ValidationType.STRING,
    min_length=3,
    max_length=100,
    forbidden_patterns=["@everyone"]
)
validated_input = validation.validate_field("custom_field", user_input, rule)
```

### 3. Metrics Recording
Record metrics for important operations:

```python
# Record command execution
await metrics.record_command("create_event", duration, success=True)

# Record business metrics
metrics.record_counter("events_created", 1.0, {"guild_id": guild_id})
```

### 4. Audit Logging
Log important actions for security and compliance:

```python
await audit_logger.log_resource_event(
    AuditEventType.EVENT_CREATED,
    "Created new event",
    user_id=str(user.id),
    guild_id=str(guild.id),
    resource_id=event_id,
    resource_type="event"
)
```

### 5. Event Bus Usage
Use the event bus for loose coupling between components:

```python
# Emit events for other components to react to
await event_bus.emit(
    EventType.EVENT_CREATED,
    {"event_id": event_id, "title": title},
    source="events_cog"
)

# Subscribe to events in other components
event_bus.subscribe(EventType.EVENT_CREATED, self.on_event_created)
```

## Error Handling

The framework provides comprehensive error handling:

1. **Custom Exceptions**: Use the exceptions in `utils/exceptions.py`
2. **Automatic Logging**: Errors are automatically logged with context
3. **User-Friendly Messages**: Exceptions include user-friendly messages
4. **Audit Trail**: Security-relevant errors are logged to audit system

## Configuration

Core framework components are configured through:

1. **Settings**: Environment variables and configuration files
2. **Role Mappings**: Discord role to permission mappings
3. **Validation Rules**: Custom validation rules for specific use cases
4. **Health Checks**: Custom health check functions

## Testing

The framework includes comprehensive tests in `tests/test_core_framework.py`. Run tests with:

```bash
python -m pytest tests/test_core_framework.py -v
```

## Performance Considerations

1. **Event Bus**: Subscribers run concurrently but errors are isolated
2. **Metrics**: Metrics collection is designed to be low-overhead
3. **Validation**: Validation rules are cached and reused
4. **Rate Limiting**: Uses efficient in-memory buckets with cleanup
5. **Health Monitoring**: Configurable intervals to balance monitoring vs. performance

## Security Features

1. **Input Sanitization**: Automatic removal of dangerous content
2. **Permission Enforcement**: Role-based access control
3. **Rate Limiting**: Protection against abuse
4. **Audit Logging**: Complete audit trail of actions
5. **Session Management**: Secure session token handling
6. **CSRF Protection**: Cross-site request forgery protection