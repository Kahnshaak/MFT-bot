"""
Discord UI Audit and Validation Utilities

This module provides comprehensive auditing and validation for Discord UI components
including slash commands, embeds, buttons, modals, and other interactive elements.
"""

import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

# Discord imports are optional for this audit module
try:
    import discord
    from discord.ext import commands
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False


class AuditSeverity(Enum):
    """Severity levels for audit findings."""
    INFO = "info"
    WARNING = "warning" 
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditFinding:
    """Represents an audit finding."""
    severity: AuditSeverity
    category: str
    component: str
    issue: str
    recommendation: str
    location: Optional[str] = None


class DiscordUIAuditor:
    """Comprehensive Discord UI auditor."""
    
    # Discord limits and best practices
    LIMITS = {
        'embed_title': 256,
        'embed_description': 4096,
        'embed_field_name': 256,
        'embed_field_value': 1024,
        'embed_fields_max': 25,
        'embed_footer': 2048,
        'embed_author': 256,
        'button_label': 80,
        'select_option_label': 100,
        'select_option_description': 100,
        'modal_title': 45,
        'text_input_label': 45,
        'text_input_placeholder': 100,
        'command_name': 32,
        'command_description': 100,
        'parameter_description': 100,
        'message_content': 2000
    }
    
    def __init__(self):
        self.findings: List[AuditFinding] = []
    
    def audit_slash_command(self, command: Any) -> List[AuditFinding]:
        """Audit a slash command for best practices."""
        findings = []
        
        # Check command name
        if not command.name:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Command Structure",
                component=f"Command: {command.name or 'unnamed'}",
                issue="Command has no name",
                recommendation="Add a descriptive command name"
            ))
        elif len(command.name) > self.LIMITS['command_name']:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Command Structure", 
                component=f"Command: {command.name}",
                issue=f"Command name too long ({len(command.name)}/{self.LIMITS['command_name']})",
                recommendation="Shorten command name to 32 characters or less"
            ))
        elif not re.match(r'^[a-z0-9_-]+$', command.name):
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Command Structure",
                component=f"Command: {command.name}",
                issue="Command name contains invalid characters",
                recommendation="Use only lowercase letters, numbers, hyphens, and underscores"
            ))
        
        # Check command description
        if not command.description:
            findings.append(AuditFinding(
                severity=AuditSeverity.WARNING,
                category="Command Structure",
                component=f"Command: {command.name}",
                issue="Command has no description",
                recommendation="Add a clear, helpful description"
            ))
        elif len(command.description) > self.LIMITS['command_description']:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Command Structure",
                component=f"Command: {command.name}",
                issue=f"Description too long ({len(command.description)}/{self.LIMITS['command_description']})",
                recommendation="Shorten description to 100 characters or less"
            ))
        elif len(command.description) < 10:
            findings.append(AuditFinding(
                severity=AuditSeverity.WARNING,
                category="Command Structure",
                component=f"Command: {command.name}",
                issue="Description is very short",
                recommendation="Provide a more descriptive explanation of what the command does"
            ))
        
        # Check parameters
        if hasattr(command, 'options'):
            for option in command.options:
                findings.extend(self._audit_command_parameter(command.name, option))
        
        return findings
    
    def _audit_command_parameter(self, command_name: str, option) -> List[AuditFinding]:
        """Audit a command parameter."""
        findings = []
        
        # Check parameter description
        if not hasattr(option, 'description') or not option.description:
            findings.append(AuditFinding(
                severity=AuditSeverity.WARNING,
                category="Parameter Documentation",
                component=f"Command: {command_name}, Parameter: {getattr(option, 'name', 'unnamed')}",
                issue="Parameter has no description",
                recommendation="Add @app_commands.describe() with helpful parameter descriptions"
            ))
        elif len(option.description) > self.LIMITS['parameter_description']:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Parameter Documentation",
                component=f"Command: {command_name}, Parameter: {option.name}",
                issue=f"Parameter description too long ({len(option.description)}/{self.LIMITS['parameter_description']})",
                recommendation="Shorten parameter description to 100 characters or less"
            ))
        
        return findings
    
    def audit_embed(self, embed: Any, context: str = "Unknown") -> List[AuditFinding]:
        """Audit a Discord embed for best practices."""
        findings = []
        
        # Check title
        if embed.title and len(embed.title) > self.LIMITS['embed_title']:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Embed Formatting",
                component=f"Embed: {context}",
                issue=f"Title too long ({len(embed.title)}/{self.LIMITS['embed_title']})",
                recommendation="Shorten embed title to 256 characters or less"
            ))
        
        # Check description
        if embed.description and len(embed.description) > self.LIMITS['embed_description']:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Embed Formatting",
                component=f"Embed: {context}",
                issue=f"Description too long ({len(embed.description)}/{self.LIMITS['embed_description']})",
                recommendation="Shorten embed description to 4096 characters or less"
            ))
        
        # Check fields
        if len(embed.fields) > self.LIMITS['embed_fields_max']:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Embed Formatting",
                component=f"Embed: {context}",
                issue=f"Too many fields ({len(embed.fields)}/{self.LIMITS['embed_fields_max']})",
                recommendation="Reduce number of embed fields to 25 or less"
            ))
        
        for i, field in enumerate(embed.fields):
            if len(field.name) > self.LIMITS['embed_field_name']:
                findings.append(AuditFinding(
                    severity=AuditSeverity.ERROR,
                    category="Embed Formatting",
                    component=f"Embed: {context}, Field {i+1}",
                    issue=f"Field name too long ({len(field.name)}/{self.LIMITS['embed_field_name']})",
                    recommendation="Shorten field name to 256 characters or less"
                ))
            
            if len(field.value) > self.LIMITS['embed_field_value']:
                findings.append(AuditFinding(
                    severity=AuditSeverity.ERROR,
                    category="Embed Formatting",
                    component=f"Embed: {context}, Field {i+1}",
                    issue=f"Field value too long ({len(field.value)}/{self.LIMITS['embed_field_value']})",
                    recommendation="Shorten field value to 1024 characters or less"
                ))
        
        # Check footer
        if embed.footer and embed.footer.text and len(embed.footer.text) > self.LIMITS['embed_footer']:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Embed Formatting",
                component=f"Embed: {context}",
                issue=f"Footer too long ({len(embed.footer.text)}/{self.LIMITS['embed_footer']})",
                recommendation="Shorten embed footer to 2048 characters or less"
            ))
        
        # Check color consistency
        if not embed.color:
            findings.append(AuditFinding(
                severity=AuditSeverity.INFO,
                category="Embed Styling",
                component=f"Embed: {context}",
                issue="No color set",
                recommendation="Consider setting a consistent color scheme for better visual appeal"
            ))
        
        # Check mobile-friendly formatting
        if embed.description and '\n\n\n' in embed.description:
            findings.append(AuditFinding(
                severity=AuditSeverity.WARNING,
                category="Mobile Compatibility",
                component=f"Embed: {context}",
                issue="Excessive line breaks may cause poor mobile display",
                recommendation="Use double line breaks (\\n\\n) for spacing instead of triple"
            ))
        
        return findings
    
    def audit_button(self, button: Any, context: str = "Unknown") -> List[AuditFinding]:
        """Audit a Discord button for best practices."""
        findings = []
        
        # Check label length
        if button.label and len(button.label) > self.LIMITS['button_label']:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Button Formatting",
                component=f"Button: {context}",
                issue=f"Label too long ({len(button.label)}/{self.LIMITS['button_label']})",
                recommendation="Shorten button label to 80 characters or less"
            ))
        
        # Check for label or emoji
        if not button.label and not button.emoji:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Button Formatting",
                component=f"Button: {context}",
                issue="Button has no label or emoji",
                recommendation="Add either a text label or emoji to make the button's purpose clear"
            ))
        
        # Check custom_id for persistent buttons
        if hasattr(button, 'style') and str(button.style) != 'ButtonStyle.link' and not getattr(button, 'custom_id', None):
            findings.append(AuditFinding(
                severity=AuditSeverity.WARNING,
                category="Button Functionality",
                component=f"Button: {context}",
                issue="Non-link button missing custom_id",
                recommendation="Add custom_id for proper button identification and persistence"
            ))
        
        return findings
    
    def audit_select_menu(self, select: Any, context: str = "Unknown") -> List[AuditFinding]:
        """Audit a Discord select menu for best practices."""
        findings = []
        
        # Check placeholder
        if not select.placeholder:
            findings.append(AuditFinding(
                severity=AuditSeverity.WARNING,
                category="Select Menu UX",
                component=f"Select: {context}",
                issue="No placeholder text",
                recommendation="Add placeholder text to guide users on what to select"
            ))
        
        # Check options
        if not select.options:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Select Menu Functionality",
                component=f"Select: {context}",
                issue="No options provided",
                recommendation="Add at least one option to the select menu"
            ))
        elif len(select.options) > 25:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Select Menu Functionality",
                component=f"Select: {context}",
                issue=f"Too many options ({len(select.options)}/25)",
                recommendation="Reduce options to 25 or less, or use pagination"
            ))
        
        # Check individual options
        for i, option in enumerate(select.options):
            if len(option.label) > self.LIMITS['select_option_label']:
                findings.append(AuditFinding(
                    severity=AuditSeverity.ERROR,
                    category="Select Menu Formatting",
                    component=f"Select: {context}, Option {i+1}",
                    issue=f"Option label too long ({len(option.label)}/{self.LIMITS['select_option_label']})",
                    recommendation="Shorten option label to 100 characters or less"
                ))
            
            if option.description and len(option.description) > self.LIMITS['select_option_description']:
                findings.append(AuditFinding(
                    severity=AuditSeverity.ERROR,
                    category="Select Menu Formatting",
                    component=f"Select: {context}, Option {i+1}",
                    issue=f"Option description too long ({len(option.description)}/{self.LIMITS['select_option_description']})",
                    recommendation="Shorten option description to 100 characters or less"
                ))
        
        return findings
    
    def audit_modal(self, modal: Any, context: str = "Unknown") -> List[AuditFinding]:
        """Audit a Discord modal for best practices."""
        findings = []
        
        # Check title
        if not modal.title:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Modal Structure",
                component=f"Modal: {context}",
                issue="Modal has no title",
                recommendation="Add a descriptive title to the modal"
            ))
        elif len(modal.title) > self.LIMITS['modal_title']:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Modal Structure",
                component=f"Modal: {context}",
                issue=f"Title too long ({len(modal.title)}/{self.LIMITS['modal_title']})",
                recommendation="Shorten modal title to 45 characters or less"
            ))
        
        # Check text inputs
        text_inputs = [item for item in modal.children if isinstance(item, discord.ui.TextInput)]
        if not text_inputs:
            findings.append(AuditFinding(
                severity=AuditSeverity.WARNING,
                category="Modal Functionality",
                component=f"Modal: {context}",
                issue="Modal has no text inputs",
                recommendation="Add text inputs for user interaction"
            ))
        elif len(text_inputs) > 5:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Modal Functionality",
                component=f"Modal: {context}",
                issue=f"Too many text inputs ({len(text_inputs)}/5)",
                recommendation="Reduce text inputs to 5 or less"
            ))
        
        # Check individual text inputs
        for i, text_input in enumerate(text_inputs):
            findings.extend(self._audit_text_input(text_input, f"{context}, Input {i+1}"))
        
        return findings
    
    def _audit_text_input(self, text_input: Any, context: str) -> List[AuditFinding]:
        """Audit a text input component."""
        findings = []
        
        # Check label
        if not text_input.label:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Text Input Structure",
                component=f"TextInput: {context}",
                issue="Text input has no label",
                recommendation="Add a descriptive label to the text input"
            ))
        elif len(text_input.label) > self.LIMITS['text_input_label']:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Text Input Structure",
                component=f"TextInput: {context}",
                issue=f"Label too long ({len(text_input.label)}/{self.LIMITS['text_input_label']})",
                recommendation="Shorten text input label to 45 characters or less"
            ))
        
        # Check placeholder
        if text_input.placeholder and len(text_input.placeholder) > self.LIMITS['text_input_placeholder']:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Text Input Structure",
                component=f"TextInput: {context}",
                issue=f"Placeholder too long ({len(text_input.placeholder)}/{self.LIMITS['text_input_placeholder']})",
                recommendation="Shorten placeholder to 100 characters or less"
            ))
        
        # Check length constraints
        if text_input.min_length and text_input.max_length and text_input.min_length > text_input.max_length:
            findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Text Input Logic",
                component=f"TextInput: {context}",
                issue="min_length is greater than max_length",
                recommendation="Ensure min_length is less than or equal to max_length"
            ))
        
        return findings
    
    def generate_report(self) -> str:
        """Generate a comprehensive audit report."""
        if not self.findings:
            return "✅ No issues found in Discord UI audit!"
        
        # Group findings by severity
        by_severity = {}
        for finding in self.findings:
            if finding.severity not in by_severity:
                by_severity[finding.severity] = []
            by_severity[finding.severity].append(finding)
        
        report = ["# Discord UI Audit Report\n"]
        
        # Summary
        total = len(self.findings)
        critical = len(by_severity.get(AuditSeverity.CRITICAL, []))
        errors = len(by_severity.get(AuditSeverity.ERROR, []))
        warnings = len(by_severity.get(AuditSeverity.WARNING, []))
        info = len(by_severity.get(AuditSeverity.INFO, []))
        
        report.append(f"## Summary")
        report.append(f"- **Total Issues:** {total}")
        report.append(f"- **Critical:** {critical}")
        report.append(f"- **Errors:** {errors}")
        report.append(f"- **Warnings:** {warnings}")
        report.append(f"- **Info:** {info}\n")
        
        # Detailed findings
        for severity in [AuditSeverity.CRITICAL, AuditSeverity.ERROR, AuditSeverity.WARNING, AuditSeverity.INFO]:
            if severity in by_severity:
                report.append(f"## {severity.value.title()} Issues\n")
                
                for finding in by_severity[severity]:
                    report.append(f"### {finding.component}")
                    report.append(f"**Category:** {finding.category}")
                    report.append(f"**Issue:** {finding.issue}")
                    report.append(f"**Recommendation:** {finding.recommendation}")
                    if finding.location:
                        report.append(f"**Location:** {finding.location}")
                    report.append("")
        
        return "\n".join(report)


def audit_cog_commands(cog: commands.Cog) -> List[AuditFinding]:
    """Audit all commands in a cog."""
    auditor = DiscordUIAuditor()
    findings = []
    
    # Get all slash commands
    for command in cog.get_commands():
        if isinstance(command, commands.SlashCommand):
            findings.extend(auditor.audit_slash_command(command))
    
    return findings


def audit_embed_consistency(embeds: List[Tuple[discord.Embed, str]]) -> List[AuditFinding]:
    """Audit multiple embeds for consistency."""
    auditor = DiscordUIAuditor()
    findings = []
    
    colors = set()
    for embed, context in embeds:
        findings.extend(auditor.audit_embed(embed, context))
        if embed.color:
            colors.add(embed.color.value)
    
    # Check color consistency
    if len(colors) > 5:
        findings.append(AuditFinding(
            severity=AuditSeverity.WARNING,
            category="Design Consistency",
            component="Global Embeds",
            issue=f"Too many different colors used ({len(colors)})",
            recommendation="Establish a consistent color scheme with 3-5 primary colors"
        ))
    
    return findings