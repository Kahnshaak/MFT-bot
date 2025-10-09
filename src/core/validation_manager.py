"""
Simple input validation system.
"""

import re
from typing import Any, Dict, Optional

from utils.logging_config import get_logger
from utils.exceptions import ValidationError


class ValidationManager:
    """
    Simple input validation system.
    """
    
    def __init__(self):
        # Basic patterns
        self.PATTERNS = {
            'discord_id': r'^\d{17,19}$',
            'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        }
    
    def validate_string(
        self, 
        value: str, 
        min_length: int = 1, 
        max_length: int = 2000,
        field_name: str = "field"
    ) -> str:
        """
        Validate a string field.
        
        Args:
            value: String to validate
            min_length: Minimum length
            max_length: Maximum length
            field_name: Name of field for error messages
            
        Returns:
            Sanitized string
            
        Raises:
            ValidationError: If validation fails
        """
        if not isinstance(value, str):
            value = str(value)
        
        # Length validation
        if len(value) < min_length:
            raise ValidationError(f"{field_name} must be at least {min_length} characters")
        
        if len(value) > max_length:
            raise ValidationError(f"{field_name} must be at most {max_length} characters")
        
        # Basic sanitization
        sanitized = value.strip()
        
        # Remove Discord mentions
        sanitized = sanitized.replace('@everyone', '@\u200beveryone')
        sanitized = sanitized.replace('@here', '@\u200bhere')
        
        return sanitized
    
    def validate_integer(
        self, 
        value: Any, 
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
        field_name: str = "field"
    ) -> int:
        """
        Validate an integer field.
        
        Args:
            value: Value to validate
            min_value: Minimum value
            max_value: Maximum value
            field_name: Name of field for error messages
            
        Returns:
            Validated integer
            
        Raises:
            ValidationError: If validation fails
        """
        try:
            int_value = int(value)
        except (ValueError, TypeError):
            raise ValidationError(f"{field_name} must be an integer")
        
        if min_value is not None and int_value < min_value:
            raise ValidationError(f"{field_name} must be at least {min_value}")
        
        if max_value is not None and int_value > max_value:
            raise ValidationError(f"{field_name} must be at most {max_value}")
        
        return int_value
    
    def validate_discord_id(self, value: str, field_name: str = "discord_id") -> str:
        """
        Validate a Discord ID.
        
        Args:
            value: Discord ID to validate
            field_name: Name of field for error messages
            
        Returns:
            Validated Discord ID
            
        Raises:
            ValidationError: If validation fails
        """
        if not isinstance(value, str):
            value = str(value)
        
        if not re.match(self.PATTERNS['discord_id'], value):
            raise ValidationError(f"{field_name} must be a valid Discord ID")
        
        return value
    
    def validate_data(self, data: Dict[str, Any], rules: Dict[str, Dict]) -> Dict[str, Any]:
        """
        Validate a dictionary of data.
        
        Args:
            data: Dictionary of field names to values
            rules: Dictionary of field validation rules
            
        Returns:
            Dictionary of validated data
            
        Raises:
            ValidationError: If any field fails validation
        """
        validated_data = {}
        
        for field_name, value in data.items():
            rule = rules.get(field_name, {})
            
            if rule.get('type') == 'string':
                validated_data[field_name] = self.validate_string(
                    value,
                    min_length=rule.get('min_length', 1),
                    max_length=rule.get('max_length', 2000),
                    field_name=field_name
                )
            elif rule.get('type') == 'integer':
                validated_data[field_name] = self.validate_integer(
                    value,
                    min_value=rule.get('min_value'),
                    max_value=rule.get('max_value'),
                    field_name=field_name
                )
            elif rule.get('type') == 'discord_id':
                validated_data[field_name] = self.validate_discord_id(value, field_name)
            else:
                # Basic sanitization for unknown types
                if isinstance(value, str):
                    validated_data[field_name] = self.validate_string(value, field_name=field_name)
                else:
                    validated_data[field_name] = value
        
        return validated_data