#!/usr/bin/env python3
"""
Validate Discord UI Components

This script validates all Discord UI components for compliance with
Discord's requirements and best practices.
"""

import ast
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

# Import our audit utilities
sys.path.append(str(Path(__file__).parent))
from discord_ui_audit import DiscordUIAuditor, AuditFinding, AuditSeverity


@dataclass
class CommandInfo:
    """Information about a slash command."""
    name: str
    description: str
    parameters: List[Dict[str, Any]]
    file_path: str
    line_number: int


class DiscordUIValidator:
    """Validates Discord UI components in the codebase."""
    
    def __init__(self):
        self.auditor = DiscordUIAuditor()
        self.findings: List[AuditFinding] = []
        self.commands: List[CommandInfo] = []
    
    def validate_codebase(self, src_dir: Path) -> List[AuditFinding]:
        """Validate the entire codebase for Discord UI issues."""
        
        # Find all Python files in cogs directory
        cog_files = list((src_dir / "cogs").glob("*.py"))
        
        for cog_file in cog_files:
            if cog_file.name.startswith("__"):
                continue
                
            print(f"🔍 Validating {cog_file.name}...")
            self.validate_file(cog_file)
        
        # Validate overall consistency
        self.validate_consistency()
        
        return self.findings
    
    def validate_file(self, file_path: Path):
        """Validate a single Python file."""
        try:
            content = file_path.read_text()
            
            # Parse the file to extract command information
            commands = self.extract_commands(content, str(file_path))
            self.commands.extend(commands)
            
            # Validate each command
            for command in commands:
                self.validate_command(command)
            
            # Validate embeds in the file
            self.validate_embeds_in_file(content, str(file_path))
            
            # Validate UI components
            self.validate_ui_components_in_file(content, str(file_path))
            
        except Exception as e:
            self.findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="File Processing",
                component=str(file_path),
                issue=f"Failed to process file: {e}",
                recommendation="Check file syntax and encoding"
            ))
    
    def extract_commands(self, content: str, file_path: str) -> List[CommandInfo]:
        """Extract slash command information from file content."""
        commands = []
        
        # Pattern to match slash commands
        command_pattern = r'@commands\.slash_command\(\s*(?:name="([^"]+)",?\s*)?(?:description="([^"]+)")?\s*\)'
        app_command_pattern = r'@app_commands\.command\(\s*(?:name="([^"]+)",?\s*)?(?:description="([^"]+)")?\s*\)'
        
        # Find all command decorators
        for pattern in [command_pattern, app_command_pattern]:
            for match in re.finditer(pattern, content, re.MULTILINE):
                name = match.group(1) or "unnamed"
                description = match.group(2) or ""
                line_number = content[:match.start()].count('\n') + 1
                
                # Extract parameters (simplified)
                parameters = self.extract_parameters(content, match.end())
                
                commands.append(CommandInfo(
                    name=name,
                    description=description,
                    parameters=parameters,
                    file_path=file_path,
                    line_number=line_number
                ))
        
        return commands
    
    def extract_parameters(self, content: str, start_pos: int) -> List[Dict[str, Any]]:
        """Extract parameter information from command definition."""
        # This is a simplified extraction - in a real implementation,
        # you'd want to use AST parsing for more accuracy
        parameters = []
        
        # Look for function definition after the decorator
        func_match = re.search(r'async def \w+\([^)]+\):', content[start_pos:start_pos+500])
        if func_match:
            func_def = func_match.group(0)
            
            # Extract parameter names and types (simplified)
            param_pattern = r'(\w+):\s*(\w+(?:\.\w+)*)'
            for param_match in re.finditer(param_pattern, func_def):
                param_name = param_match.group(1)
                param_type = param_match.group(2)
                
                if param_name not in ['self', 'interaction', 'ctx']:
                    parameters.append({
                        'name': param_name,
                        'type': param_type,
                        'description': ''  # Would need to extract from @app_commands.describe
                    })
        
        return parameters
    
    def validate_command(self, command: CommandInfo):
        """Validate a single command."""
        
        # Check command name
        if not command.name or command.name == "unnamed":
            self.findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Command Structure",
                component=f"Command in {Path(command.file_path).name}:{command.line_number}",
                issue="Command has no name",
                recommendation="Add a descriptive command name",
                location=f"{command.file_path}:{command.line_number}"
            ))
        elif len(command.name) > 32:
            self.findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Command Structure",
                component=f"Command: {command.name}",
                issue=f"Command name too long ({len(command.name)}/32)",
                recommendation="Shorten command name to 32 characters or less",
                location=f"{command.file_path}:{command.line_number}"
            ))
        elif not re.match(r'^[a-z0-9_-]+$', command.name):
            self.findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Command Structure",
                component=f"Command: {command.name}",
                issue="Command name contains invalid characters",
                recommendation="Use only lowercase letters, numbers, hyphens, and underscores",
                location=f"{command.file_path}:{command.line_number}"
            ))
        
        # Check command description
        if not command.description:
            self.findings.append(AuditFinding(
                severity=AuditSeverity.WARNING,
                category="Command Documentation",
                component=f"Command: {command.name}",
                issue="Command has no description",
                recommendation="Add a clear, helpful description",
                location=f"{command.file_path}:{command.line_number}"
            ))
        elif len(command.description) > 100:
            self.findings.append(AuditFinding(
                severity=AuditSeverity.ERROR,
                category="Command Documentation",
                component=f"Command: {command.name}",
                issue=f"Description too long ({len(command.description)}/100)",
                recommendation="Shorten description to 100 characters or less",
                location=f"{command.file_path}:{command.line_number}"
            ))
        elif len(command.description) < 10:
            self.findings.append(AuditFinding(
                severity=AuditSeverity.WARNING,
                category="Command Documentation",
                component=f"Command: {command.name}",
                issue="Description is very short",
                recommendation="Provide a more descriptive explanation",
                location=f"{command.file_path}:{command.line_number}"
            ))
        
        # Check parameters
        for param in command.parameters:
            if not param.get('description'):
                self.findings.append(AuditFinding(
                    severity=AuditSeverity.WARNING,
                    category="Parameter Documentation",
                    component=f"Command: {command.name}, Parameter: {param['name']}",
                    issue="Parameter has no description",
                    recommendation="Add @app_commands.describe() with parameter descriptions",
                    location=f"{command.file_path}:{command.line_number}"
                ))
    
    def validate_embeds_in_file(self, content: str, file_path: str):
        """Validate embed usage in a file."""
        
        # Find embed creations
        embed_pattern = r'discord\.Embed\('
        for match in re.finditer(embed_pattern, content):
            line_number = content[:match.start()].count('\n') + 1
            
            # Extract the embed creation (simplified)
            embed_start = match.start()
            embed_end = self.find_matching_paren(content, embed_start + len('discord.Embed(') - 1)
            
            if embed_end:
                embed_code = content[embed_start:embed_end + 1]
                
                # Check for common issues
                if 'color=' not in embed_code:
                    self.findings.append(AuditFinding(
                        severity=AuditSeverity.INFO,
                        category="Embed Styling",
                        component=f"Embed in {Path(file_path).name}:{line_number}",
                        issue="Embed has no color set",
                        recommendation="Set a consistent color for better visual appeal",
                        location=f"{file_path}:{line_number}"
                    ))
                
                if 'timestamp=' not in embed_code:
                    self.findings.append(AuditFinding(
                        severity=AuditSeverity.INFO,
                        category="Embed Consistency",
                        component=f"Embed in {Path(file_path).name}:{line_number}",
                        issue="Embed has no timestamp",
                        recommendation="Add timestamp=datetime.utcnow() for consistency",
                        location=f"{file_path}:{line_number}"
                    ))
    
    def validate_ui_components_in_file(self, content: str, file_path: str):
        """Validate UI components like buttons and modals in a file."""
        
        # Check for button creations
        button_pattern = r'discord\.ui\.Button\('
        for match in re.finditer(button_pattern, content):
            line_number = content[:match.start()].count('\n') + 1
            
            # Extract button creation
            button_start = match.start()
            button_end = self.find_matching_paren(content, button_start + len('discord.ui.Button(') - 1)
            
            if button_end:
                button_code = content[button_start:button_end + 1]
                
                # Check for label or emoji
                if 'label=' not in button_code and 'emoji=' not in button_code:
                    self.findings.append(AuditFinding(
                        severity=AuditSeverity.ERROR,
                        category="Button Accessibility",
                        component=f"Button in {Path(file_path).name}:{line_number}",
                        issue="Button has no label or emoji",
                        recommendation="Add either a text label or emoji for accessibility",
                        location=f"{file_path}:{line_number}"
                    ))
                
                # Check for custom_id on non-link buttons
                if 'style=discord.ButtonStyle.link' not in button_code and 'custom_id=' not in button_code:
                    self.findings.append(AuditFinding(
                        severity=AuditSeverity.WARNING,
                        category="Button Functionality",
                        component=f"Button in {Path(file_path).name}:{line_number}",
                        issue="Non-link button missing custom_id",
                        recommendation="Add custom_id for proper button identification",
                        location=f"{file_path}:{line_number}"
                    ))
        
        # Check for modal creations
        modal_pattern = r'discord\.ui\.Modal\('
        for match in re.finditer(modal_pattern, content):
            line_number = content[:match.start()].count('\n') + 1
            
            modal_start = match.start()
            modal_end = self.find_matching_paren(content, modal_start + len('discord.ui.Modal(') - 1)
            
            if modal_end:
                modal_code = content[modal_start:modal_end + 1]
                
                if 'title=' not in modal_code:
                    self.findings.append(AuditFinding(
                        severity=AuditSeverity.ERROR,
                        category="Modal Accessibility",
                        component=f"Modal in {Path(file_path).name}:{line_number}",
                        issue="Modal has no title",
                        recommendation="Add a descriptive title to the modal",
                        location=f"{file_path}:{line_number}"
                    ))
    
    def find_matching_paren(self, content: str, start: int) -> int:
        """Find the matching closing parenthesis."""
        if start >= len(content) or content[start] != '(':
            return None
        
        count = 1
        i = start + 1
        
        while i < len(content) and count > 0:
            if content[i] == '(':
                count += 1
            elif content[i] == ')':
                count -= 1
            i += 1
        
        return i - 1 if count == 0 else None
    
    def validate_consistency(self):
        """Validate consistency across all commands."""
        
        # Check for duplicate command names
        command_names = {}
        for command in self.commands:
            if command.name in command_names:
                self.findings.append(AuditFinding(
                    severity=AuditSeverity.ERROR,
                    category="Command Consistency",
                    component=f"Command: {command.name}",
                    issue=f"Duplicate command name found in {command.file_path} and {command_names[command.name]}",
                    recommendation="Ensure all command names are unique across the bot"
                ))
            else:
                command_names[command.name] = command.file_path
        
        # Check naming conventions
        naming_issues = []
        for command in self.commands:
            if '_' in command.name and '-' in command.name:
                naming_issues.append(command.name)
        
        if naming_issues:
            self.findings.append(AuditFinding(
                severity=AuditSeverity.WARNING,
                category="Naming Consistency",
                component="Global Commands",
                issue=f"Mixed naming conventions in commands: {', '.join(naming_issues)}",
                recommendation="Use consistent naming convention (prefer hyphens over underscores)"
            ))
    
    def generate_report(self) -> str:
        """Generate a comprehensive validation report."""
        if not self.findings:
            return "✅ All Discord UI components passed validation!"
        
        # Group findings by severity
        by_severity = {}
        for finding in self.findings:
            if finding.severity not in by_severity:
                by_severity[finding.severity] = []
            by_severity[finding.severity].append(finding)
        
        report = ["# Discord UI Validation Report\n"]
        
        # Summary
        total = len(self.findings)
        critical = len(by_severity.get(AuditSeverity.CRITICAL, []))
        errors = len(by_severity.get(AuditSeverity.ERROR, []))
        warnings = len(by_severity.get(AuditSeverity.WARNING, []))
        info = len(by_severity.get(AuditSeverity.INFO, []))
        
        report.append(f"## Summary")
        report.append(f"- **Commands Found:** {len(self.commands)}")
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


def main():
    """Run Discord UI validation."""
    print("🔍 Validating Discord UI components...")
    
    # Get the source directory
    src_dir = Path(__file__).parent.parent
    
    # Create validator and run validation
    validator = DiscordUIValidator()
    findings = validator.validate_codebase(src_dir)
    
    # Generate and display report
    report = validator.generate_report()
    print("\n" + report)
    
    # Save report to file
    report_file = src_dir / "discord_ui_validation_report.md"
    report_file.write_text(report)
    print(f"\n📄 Full report saved to: {report_file}")
    
    # Return appropriate exit code
    critical_errors = sum(1 for f in findings if f.severity in [AuditSeverity.CRITICAL, AuditSeverity.ERROR])
    
    if critical_errors > 0:
        print(f"\n❌ Validation failed with {critical_errors} critical issues")
        return 1
    else:
        print(f"\n✅ Validation passed with {len(findings)} minor issues")
        return 0


if __name__ == "__main__":
    exit(main())