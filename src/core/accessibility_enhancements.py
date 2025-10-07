"""
Accessibility enhancements for Discord UI components.
"""

import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from enum import Enum

import discord
from discord.ext import commands

from utils.logging_config import get_logger


class AccessibilityLevel(Enum):
    """Accessibility compliance levels."""
    BASIC = "basic"
    ENHANCED = "enhanced"
    FULL = "full"


class AccessibleEmbed:
    """Enhanced embed builder with accessibility features."""
    
    def __init__(self, title: str = None, description: str = None, color: discord.Color = None):
        self.embed = discord.Embed(title=title, description=description, color=color)
        self.accessibility_level = AccessibilityLevel.ENHANCED
        self.screen_reader_text = []
        
    def add_field(self, name: str, value: str, inline: bool = True, 
                  screen_reader_description: str = None):
        """Add field with optional screen reader description."""
        # Ensure field values aren't too long
        if len(value) > 1024:
            value = value[:1021] + "..."
        
        self.embed.add_field(name=name, value=value, inline=inline)
        
        # Add screen reader context
        if screen_reader_description:
            self.screen_reader_text.append(f"{name}: {screen_reader_description}")
        else:
            # Generate basic screen reader text
            clean_value = value.replace("**", "").replace("*", "").replace("`", "")
            self.screen_reader_text.append(f"{name}: {clean_value}")
        
        return self
    
    def set_footer(self, text: str, icon_url: str = None, 
                   screen_reader_text: str = None):
        """Set footer with screen reader alternative."""
        self.embed.set_footer(text=text, icon_url=icon_url)
        
        if screen_reader_text:
            self.screen_reader_text.append(f"Footer: {screen_reader_text}")
        else:
            self.screen_reader_text.append(f"Footer: {text}")
        
        return self
    
    def set_author(self, name: str, url: str = None, icon_url: str = None,
                   screen_reader_description: str = None):
        """Set author with screen reader description."""
        self.embed.set_author(name=name, url=url, icon_url=icon_url)
        
        if screen_reader_description:
            self.screen_reader_text.append(f"Author: {screen_reader_description}")
        else:
            self.screen_reader_text.append(f"Author: {name}")
        
        return self
    
    def add_accessibility_note(self, note: str):
        """Add accessibility note for screen readers."""
        self.screen_reader_text.append(note)
        return self
    
    def get_screen_reader_summary(self) -> str:
        """Get summary text for screen readers."""
        summary = []
        
        if self.embed.title:
            summary.append(f"Title: {self.embed.title}")
        
        if self.embed.description:
            clean_desc = self.embed.description.replace("**", "").replace("*", "").replace("`", "")
            summary.append(f"Description: {clean_desc}")
        
        summary.extend(self.screen_reader_text)
        
        return " | ".join(summary)
    
    def build(self) -> discord.Embed:
        """Build the final embed."""
        # Add accessibility information to footer if not already set
        if not self.embed.footer.text and self.accessibility_level == AccessibilityLevel.FULL:
            screen_reader_summary = self.get_screen_reader_summary()
            if len(screen_reader_summary) <= 2048:  # Discord embed footer limit
                self.embed.set_footer(text=f"Screen reader: {screen_reader_summary}")
        
        return self.embed


class AccessibleButton(discord.ui.Button):
    """Enhanced button with accessibility features."""
    
    def __init__(
        self,
        label: str,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
        emoji: Union[str, discord.Emoji, discord.PartialEmoji] = None,
        custom_id: str = None,
        url: str = None,
        disabled: bool = False,
        row: int = None,
        # Accessibility enhancements
        aria_label: str = None,
        description: str = None,
        keyboard_shortcut: str = None
    ):
        super().__init__(
            style=style,
            label=label,
            emoji=emoji,
            custom_id=custom_id,
            url=url,
            disabled=disabled,
            row=row
        )
        
        # Accessibility properties
        self.aria_label = aria_label or label
        self.description = description
        self.keyboard_shortcut = keyboard_shortcut
        
        # Enhance label with accessibility info
        if self.description and len(f"{label} - {self.description}") <= 80:
            self.label = f"{label} - {self.description}"
    
    def get_accessibility_info(self) -> str:
        """Get accessibility information for this button."""
        info = [f"Button: {self.aria_label}"]
        
        if self.description:
            info.append(f"Description: {self.description}")
        
        if self.keyboard_shortcut:
            info.append(f"Shortcut: {self.keyboard_shortcut}")
        
        if self.disabled:
            info.append("Status: Disabled")
        
        return " | ".join(info)


class AccessibleSelect(discord.ui.Select):
    """Enhanced select dropdown with accessibility features."""
    
    def __init__(
        self,
        placeholder: str = None,
        min_values: int = 1,
        max_values: int = 1,
        options: List[discord.SelectOption] = None,
        custom_id: str = None,
        row: int = None,
        disabled: bool = False,
        # Accessibility enhancements
        aria_label: str = None,
        instructions: str = None
    ):
        super().__init__(
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            options=options or [],
            custom_id=custom_id,
            row=row,
            disabled=disabled
        )
        
        # Accessibility properties
        self.aria_label = aria_label or placeholder
        self.instructions = instructions
        
        # Enhance placeholder with accessibility info
        if self.instructions:
            enhanced_placeholder = f"{placeholder} - {self.instructions}"
            if len(enhanced_placeholder) <= 150:  # Discord limit
                self.placeholder = enhanced_placeholder
    
    def add_accessible_option(
        self,
        label: str,
        value: str,
        description: str = None,
        emoji: Union[str, discord.Emoji, discord.PartialEmoji] = None,
        default: bool = False,
        # Accessibility enhancements
        detailed_description: str = None
    ):
        """Add option with enhanced accessibility."""
        # Use detailed description if provided, otherwise use regular description
        final_description = detailed_description or description
        
        # Ensure description fits Discord limits
        if final_description and len(final_description) > 100:
            final_description = final_description[:97] + "..."
        
        option = discord.SelectOption(
            label=label,
            value=value,
            description=final_description,
            emoji=emoji,
            default=default
        )
        
        self.add_option(option)
        return self
    
    def get_accessibility_info(self) -> str:
        """Get accessibility information for this select."""
        info = [f"Dropdown: {self.aria_label}"]
        
        if self.instructions:
            info.append(f"Instructions: {self.instructions}")
        
        info.append(f"Options: {len(self.options)} available")
        
        if self.min_values != self.max_values:
            info.append(f"Selection: {self.min_values}-{self.max_values} items")
        
        if self.disabled:
            info.append("Status: Disabled")
        
        return " | ".join(info)


class AccessibleModal(discord.ui.Modal):
    """Enhanced modal with accessibility features."""
    
    def __init__(
        self,
        title: str,
        timeout: float = None,
        custom_id: str = None,
        # Accessibility enhancements
        instructions: str = None,
        completion_message: str = None
    ):
        super().__init__(title=title, timeout=timeout, custom_id=custom_id)
        
        # Accessibility properties
        self.instructions = instructions
        self.completion_message = completion_message or "Form submitted successfully"
        
        # Add instructions as first field if provided
        if self.instructions:
            instruction_field = discord.ui.TextInput(
                label="Instructions (Read Only)",
                default=self.instructions,
                style=discord.TextStyle.paragraph,
                required=False,
                max_length=len(self.instructions)
            )
            instruction_field.disabled = True
            self.add_item(instruction_field)
    
    def add_accessible_text_input(
        self,
        label: str,
        placeholder: str = None,
        default: str = None,
        required: bool = True,
        min_length: int = None,
        max_length: int = None,
        style: discord.TextStyle = discord.TextStyle.short,
        # Accessibility enhancements
        help_text: str = None,
        validation_hint: str = None
    ):
        """Add text input with accessibility enhancements."""
        
        # Enhance placeholder with help text
        enhanced_placeholder = placeholder
        if help_text:
            enhanced_placeholder = f"{placeholder} - {help_text}" if placeholder else help_text
        
        # Add validation hint to label
        enhanced_label = label
        if validation_hint:
            enhanced_label = f"{label} ({validation_hint})"
        
        text_input = discord.ui.TextInput(
            label=enhanced_label,
            placeholder=enhanced_placeholder,
            default=default,
            required=required,
            min_length=min_length,
            max_length=max_length,
            style=style
        )
        
        self.add_item(text_input)
        return text_input


class AccessibilityManager:
    """Manages accessibility features across the bot."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.accessibility_level = AccessibilityLevel.ENHANCED
        self.user_preferences: Dict[str, Dict[str, Any]] = {}
    
    def set_user_accessibility_preferences(
        self,
        user_id: str,
        preferences: Dict[str, Any]
    ):
        """Set accessibility preferences for a user."""
        self.user_preferences[user_id] = preferences
    
    def get_user_accessibility_level(self, user_id: str) -> AccessibilityLevel:
        """Get accessibility level for a user."""
        prefs = self.user_preferences.get(user_id, {})
        level_str = prefs.get('accessibility_level', 'enhanced')
        
        try:
            return AccessibilityLevel(level_str)
        except ValueError:
            return AccessibilityLevel.ENHANCED
    
    def create_accessible_embed(
        self,
        title: str = None,
        description: str = None,
        color: discord.Color = None,
        user_id: str = None
    ) -> AccessibleEmbed:
        """Create an accessible embed."""
        embed = AccessibleEmbed(title, description, color)
        
        if user_id:
            embed.accessibility_level = self.get_user_accessibility_level(user_id)
        
        return embed
    
    def create_accessible_view(
        self,
        timeout: float = 180,
        user_id: str = None
    ) -> discord.ui.View:
        """Create an accessible view."""
        view = discord.ui.View(timeout=timeout)
        
        # Add accessibility metadata
        view._accessibility_level = self.get_user_accessibility_level(user_id) if user_id else AccessibilityLevel.ENHANCED
        view._user_id = user_id
        
        return view
    
    def enhance_embed_accessibility(
        self,
        embed: discord.Embed,
        user_id: str = None
    ) -> discord.Embed:
        """Enhance existing embed with accessibility features."""
        accessibility_level = self.get_user_accessibility_level(user_id) if user_id else AccessibilityLevel.ENHANCED
        
        if accessibility_level == AccessibilityLevel.FULL:
            # Add accessibility information to description
            if embed.description:
                # Count fields and other elements for screen readers
                field_count = len(embed.fields)
                accessibility_info = f"\n\n[Accessibility: This embed has {field_count} fields"
                
                if embed.image.url:
                    accessibility_info += ", 1 image"
                if embed.thumbnail.url:
                    accessibility_info += ", 1 thumbnail"
                if embed.footer.text:
                    accessibility_info += ", footer information"
                
                accessibility_info += "]"
                
                # Add if there's room
                if len(embed.description + accessibility_info) <= 4096:
                    embed.description += accessibility_info
        
        return embed
    
    def create_navigation_help(self, view: discord.ui.View) -> str:
        """Create navigation help text for a view."""
        help_text = ["Navigation help:"]
        
        button_count = sum(1 for item in view.children if isinstance(item, discord.ui.Button))
        select_count = sum(1 for item in view.children if isinstance(item, discord.ui.Select))
        
        if button_count > 0:
            help_text.append(f"• {button_count} button(s) available")
        
        if select_count > 0:
            help_text.append(f"• {select_count} dropdown(s) available")
        
        help_text.append("• Use Tab to navigate between elements")
        help_text.append("• Use Enter or Space to activate buttons")
        
        return " | ".join(help_text)
    
    async def send_accessible_message(
        self,
        interaction: Union[discord.Interaction, discord.ApplicationContext],
        content: str = None,
        embed: discord.Embed = None,
        view: discord.ui.View = None,
        ephemeral: bool = False,
        user_id: str = None
    ):
        """Send message with accessibility enhancements."""
        
        # Enhance embed if provided
        if embed:
            embed = self.enhance_embed_accessibility(embed, user_id)
        
        # Add navigation help for complex views
        if view and len(view.children) > 3:
            nav_help = self.create_navigation_help(view)
            if content:
                content += f"\n\n{nav_help}"
            else:
                content = nav_help
        
        # Send the message
        try:
            if hasattr(interaction, 'response') and not interaction.response.is_done():
                await interaction.response.send_message(
                    content=content,
                    embed=embed,
                    view=view,
                    ephemeral=ephemeral
                )
            else:
                await interaction.followup.send(
                    content=content,
                    embed=embed,
                    view=view,
                    ephemeral=ephemeral
                )
        except Exception as e:
            self.logger.error(f"Error sending accessible message: {e}", exc_info=True)
            raise


# Global accessibility manager instance
accessibility_manager = AccessibilityManager()