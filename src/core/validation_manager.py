"""
Input validation system with comprehensive sanitization rules and validation error handling.
"""

import re
from typing import Any, Dict, List, Optional, Union, Callable
from dataclasses import dataclass
from enum import Enum

from utils.logging_config import get_logger, LoggerMixin
from utils.exceptions import ValidationError, ErrorCode


class ValidationType(Enum):
    """Types of validation rules."""
    
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    EMAIL = "email"
    URL = "url"
    DISCORD_ID = "discord_id"
    TIMEZONE = "timezone"
    DATETIME = "datetime"
    GAME_NAME = "game_name"
    EVENT_TITLE = "event_title"
    EVENT_DESCRIPTION = "event_description"


@dataclass
class ValidationRule:
    """Represents a validation rule for input data."""
    
    field_name: str
    validation_type: ValidationType
    required: bool = True
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    pattern: Optional[str] = None
    forbidden_patterns: Optional[List[str]] = None
    forbidden_chars: Optional[List[str]] = None
    allowed_values: Optional[List[Any]] = None
    custom_validator: Optional[Callable[[Any], bool]] = None
    sanitizer: Optional[Callable[[Any], Any]] = None


class ValidationManager(LoggerMixin):
    """
    Comprehensive input validation and sanitization system.
    """
    
    def __init__(self):
        self._validation_rules: Dict[str, ValidationRule] = {}
        
        # Common patterns
        self.PATTERNS = {
            'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
            'url': r'^https?://(?:[-\w.])+(?:\:[0-9]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:\#(?:[\w.])*)?)?$',
            'discord_id': r'^\d{17,19}$',
            'timezone': r'^[A-Za-z]+/[A-Za-z_]+$',
            'safe_text': r'^[a-zA-Z0-9\s\-_.,!?()]+$'
        }
        
        # Forbidden patterns for security
        self.FORBIDDEN_PATTERNS = [
            r'@everyone',
            r'@here',
            r'<@&\d+>',  # Role mentions
            r'<@!\d+>',  # User mentions
            r'<#\d+>',   # Channel mentions
            r'```.*```', # Code blocks (in some contexts)
            r'discord\.gg/\w+',  # Discord invites
            r'https?://discord\.gg/\w+',  # Discord invite URLs
        ]
        
        # Forbidden characters
        self.FORBIDDEN_CHARS = [
            '\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07',
            '\x08', '\x0b', '\x0c', '\x0e', '\x0f', '\x10', '\x11', '\x12',
            '\x13', '\x14', '\x15', '\x16', '\x17', '\x18', '\x19', '\x1a',
            '\x1b', '\x1c', '\x1d', '\x1e', '\x1f', '\x7f'
        ]
        
        # Set up global rules after patterns are defined
        self._global_rules = self._setup_global_rules()
    
    def _setup_global_rules(self) -> Dict[ValidationType, ValidationRule]:
        """Set up global validation rules for common types."""
        return {
            ValidationType.EVENT_TITLE: ValidationRule(
                field_name="event_title",
                validation_type=ValidationType.EVENT_TITLE,
                min_length=3,
                max_length=100,
                forbidden_patterns=[r'@everyone', r'@here', r'<@&\d+>', r'<@!\d+>'],  # Basic mention protection
                forbidden_chars=['\n', '\r', '\t'],
                sanitizer=self._sanitize_discord_text
            ),
            ValidationType.EVENT_DESCRIPTION: ValidationRule(
                field_name="event_description",
                validation_type=ValidationType.EVENT_DESCRIPTION,
                min_length=0,
                max_length=2000,
                forbidden_patterns=self.FORBIDDEN_PATTERNS[:4],
                sanitizer=self._sanitize_discord_text
            ),
            ValidationType.GAME_NAME: ValidationRule(
                field_name="game_name",
                validation_type=ValidationType.GAME_NAME,
                min_length=1,
                max_length=100,
                forbidden_patterns=self.FORBIDDEN_PATTERNS,
                sanitizer=self._sanitize_game_name
            ),
            ValidationType.DISCORD_ID: ValidationRule(
                field_name="discord_id",
                validation_type=ValidationType.DISCORD_ID,
                pattern=self.PATTERNS['discord_id']
            ),
            ValidationType.EMAIL: ValidationRule(
                field_name="email",
                validation_type=ValidationType.EMAIL,
                pattern=self.PATTERNS['email'],
                max_length=254
            ),
            ValidationType.URL: ValidationRule(
                field_name="url",
                validation_type=ValidationType.URL,
                pattern=self.PATTERNS['url'],
                max_length=2048
            ),
            ValidationType.TIMEZONE: ValidationRule(
                field_name="timezone",
                validation_type=ValidationType.TIMEZONE,
                custom_validator=self._validate_timezone
            )
        }
    
    def register_rule(self, rule: ValidationRule) -> None:
        """
        Register a custom validation rule.
        
        Args:
            rule: ValidationRule to register
        """
        self._validation_rules[rule.field_name] = rule
        self.logger.debug(
            "Registered validation rule",
            field_name=rule.field_name,
            validation_type=rule.validation_type.value
        )
    
    def validate_field(
        self, 
        field_name: str, 
        value: Any, 
        rule: Optional[ValidationRule] = None
    ) -> Any:
        """
        Validate a single field value.
        
        Args:
            field_name: Name of the field being validated
            value: Value to validate
            rule: Optional specific rule to use
            
        Returns:
            Sanitized and validated value
            
        Raises:
            ValidationError: If validation fails
        """
        # Get validation rule
        if rule is None:
            rule = self._get_rule_for_field(field_name)
        
        if rule is None:
            # No specific rule, just basic sanitization
            return self._basic_sanitize(value)
        
        # Check if field is required
        if rule.required and (value is None or value == ""):
            raise ValidationError(
                f"Field '{field_name}' is required",
                field=field_name
            )
        
        # Skip validation if value is None/empty and not required
        if not rule.required and (value is None or value == ""):
            return value
        
        # Type validation and conversion
        validated_value = self._validate_type(value, rule)
        
        # Length and content validation for strings (before sanitization)
        if isinstance(validated_value, str):
            self._validate_string_length(validated_value, rule)
            self._validate_string_content(validated_value, rule)
        
        # Apply sanitization if available (after validation)
        if rule.sanitizer:
            validated_value = rule.sanitizer(validated_value)
        
        # Numeric range validation
        if isinstance(validated_value, (int, float)):
            self._validate_numeric_range(validated_value, rule)
        
        # Pattern validation
        if rule.pattern and isinstance(validated_value, str):
            if not re.match(rule.pattern, validated_value):
                raise ValidationError(
                    f"Field '{field_name}' does not match required pattern",
                    field=field_name
                )
        
        # Allowed values validation
        if rule.allowed_values and validated_value not in rule.allowed_values:
            raise ValidationError(
                f"Field '{field_name}' must be one of: {rule.allowed_values}",
                field=field_name
            )
        
        # Custom validation
        if rule.custom_validator and not rule.custom_validator(validated_value):
            raise ValidationError(
                f"Field '{field_name}' failed custom validation",
                field=field_name
            )
        
        return validated_value
    
    def validate_data(
        self, 
        data: Dict[str, Any], 
        rules: Optional[Dict[str, ValidationRule]] = None
    ) -> Dict[str, Any]:
        """
        Validate a dictionary of data.
        
        Args:
            data: Dictionary of field names to values
            rules: Optional dictionary of field-specific rules
            
        Returns:
            Dictionary of validated and sanitized data
            
        Raises:
            ValidationError: If any field fails validation
        """
        validated_data = {}
        rules = rules or {}
        
        for field_name, value in data.items():
            rule = rules.get(field_name)
            try:
                validated_data[field_name] = self.validate_field(field_name, value, rule)
            except ValidationError as e:
                self.logger.warning(
                    "Field validation failed",
                    field_name=field_name,
                    error=str(e)
                )
                raise
        
        return validated_data
    
    def _get_rule_for_field(self, field_name: str) -> Optional[ValidationRule]:
        """Get validation rule for a field."""
        # Check custom rules first
        if field_name in self._validation_rules:
            return self._validation_rules[field_name]
        
        # Check if field name matches a global rule type
        for validation_type, rule in self._global_rules.items():
            if field_name.endswith(validation_type.value) or field_name == validation_type.value:
                return rule
        
        return None
    
    def _validate_type(self, value: Any, rule: ValidationRule) -> Any:
        """Validate and convert value type."""
        if rule.validation_type == ValidationType.STRING:
            if not isinstance(value, str):
                try:
                    return str(value)
                except (ValueError, TypeError):
                    raise ValidationError(
                        f"Cannot convert value to string",
                        field=rule.field_name
                    )
        
        elif rule.validation_type == ValidationType.INTEGER:
            if not isinstance(value, int):
                try:
                    return int(value)
                except (ValueError, TypeError):
                    raise ValidationError(
                        f"Field '{rule.field_name}' must be an integer",
                        field=rule.field_name
                    )
        
        elif rule.validation_type == ValidationType.FLOAT:
            if not isinstance(value, (int, float)):
                try:
                    return float(value)
                except (ValueError, TypeError):
                    raise ValidationError(
                        f"Field '{rule.field_name}' must be a number",
                        field=rule.field_name
                    )
        
        elif rule.validation_type == ValidationType.BOOLEAN:
            if isinstance(value, bool):
                return value
            elif isinstance(value, str):
                if value.lower() in ('true', '1', 'yes', 'on'):
                    return True
                elif value.lower() in ('false', '0', 'no', 'off'):
                    return False
            raise ValidationError(
                f"Field '{rule.field_name}' must be a boolean",
                field=rule.field_name
            )
        
        return value
    
    def _validate_string_length(self, value: str, rule: ValidationRule) -> None:
        """Validate string length constraints."""
        if rule.min_length is not None and len(value) < rule.min_length:
            raise ValidationError(
                f"Field '{rule.field_name}' must be at least {rule.min_length} characters",
                field=rule.field_name
            )
        
        if rule.max_length is not None and len(value) > rule.max_length:
            raise ValidationError(
                f"Field '{rule.field_name}' must be at most {rule.max_length} characters",
                field=rule.field_name
            )
    
    def _validate_string_content(self, value: str, rule: ValidationRule) -> None:
        """Validate string content for forbidden patterns and characters."""
        # Check forbidden characters
        forbidden_chars = rule.forbidden_chars or []
        for char in forbidden_chars:
            if char in value:
                raise ValidationError(
                    f"Field '{rule.field_name}' contains forbidden character",
                    field=rule.field_name
                )
        
        # Check global forbidden characters
        for char in self.FORBIDDEN_CHARS:
            if char in value:
                raise ValidationError(
                    f"Field '{rule.field_name}' contains invalid character",
                    field=rule.field_name
                )
        
        # Check forbidden patterns
        forbidden_patterns = rule.forbidden_patterns or []
        for pattern in forbidden_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                raise ValidationError(
                    f"Field '{rule.field_name}' contains forbidden content",
                    field=rule.field_name
                )
    
    def _validate_numeric_range(self, value: Union[int, float], rule: ValidationRule) -> None:
        """Validate numeric range constraints."""
        if rule.min_value is not None and value < rule.min_value:
            raise ValidationError(
                f"Field '{rule.field_name}' must be at least {rule.min_value}",
                field=rule.field_name
            )
        
        if rule.max_value is not None and value > rule.max_value:
            raise ValidationError(
                f"Field '{rule.field_name}' must be at most {rule.max_value}",
                field=rule.field_name
            )
    
    def _basic_sanitize(self, value: Any) -> Any:
        """Basic sanitization for unknown fields."""
        if isinstance(value, str):
            # Remove control characters
            sanitized = ''.join(char for char in value if char not in self.FORBIDDEN_CHARS)
            # Basic Discord mention protection
            sanitized = sanitized.replace('@everyone', '@\u200beveryone')
            sanitized = sanitized.replace('@here', '@\u200bhere')
            return sanitized.strip()
        return value
    
    def _sanitize_discord_text(self, value: str) -> str:
        """Sanitize text for Discord display."""
        # Remove control characters
        sanitized = ''.join(char for char in value if char not in self.FORBIDDEN_CHARS)
        
        # Escape Discord mentions
        sanitized = sanitized.replace('@everyone', '@\u200beveryone')
        sanitized = sanitized.replace('@here', '@\u200bhere')
        
        # Remove excessive whitespace
        sanitized = re.sub(r'\s+', ' ', sanitized)
        
        return sanitized.strip()
    
    def _sanitize_game_name(self, value: str) -> str:
        """Sanitize game names."""
        # Basic sanitization
        sanitized = self._sanitize_discord_text(value)
        
        # Normalize common game name variations
        sanitized = re.sub(r'\s+', ' ', sanitized)  # Normalize whitespace
        sanitized = sanitized.title()  # Title case
        
        return sanitized
    
    def _validate_timezone(self, value: str) -> bool:
        """Validate timezone string."""
        try:
            import pytz
            pytz.timezone(value)
            return True
        except:
            return False