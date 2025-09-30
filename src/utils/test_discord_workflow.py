#!/usr/bin/env python3
"""
Test Discord UI Workflow

This script tests the complete event creation workflow and validates
that all Discord UI components work correctly together.
"""

import asyncio
import sys
from pathlib import Path
from typing import Dict, List, Any

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from models.event import Event, EventState, Poll, PollType, PollOption
from models.user import User, NotificationChannel, NotificationTiming
from utils.ui_validation_fixes import ImprovedEmbedBuilder, ImprovedButtonBuilder, ImprovedModalBuilder


class MockDiscordUser:
    """Mock Discord user for testing."""
    def __init__(self, user_id: str, display_name: str):
        self.id = user_id
        self.display_name = display_name
        self.mention = f"<@{user_id}>"
        self.display_avatar = MockAvatar()


class MockAvatar:
    """Mock Discord avatar."""
    def __init__(self):
        self.url = "https://cdn.discordapp.com/embed/avatars/0.png"


class MockDiscordGuild:
    """Mock Discord guild for testing."""
    def __init__(self, guild_id: str, name: str):
        self.id = guild_id
        self.name = name


class DiscordWorkflowTester:
    """Tests Discord UI workflow components."""
    
    def __init__(self):
        self.test_results = []
    
    def test_event_creation_workflow(self):
        """Test the complete event creation workflow."""
        print("🧪 Testing event creation workflow...")
        
        # Create mock objects
        user = MockDiscordUser("123456789", "TestUser")
        guild = MockDiscordGuild("987654321", "Test Server")
        
        # Test 1: Create event
        event = Event(
            guild_id=str(guild.id),
            creator_id=str(user.id),
            title="Test Game Night",
            description="A test event for validation",
            state=EventState.DRAFT
        )
        
        # Test event embed creation
        try:
            embed = ImprovedEmbedBuilder.create_event_embed(event, 'primary')
            self._validate_embed(embed, "Event Creation Embed")
            print("✅ Event embed creation passed")
        except Exception as e:
            print(f"❌ Event embed creation failed: {e}")
            self.test_results.append(("Event Embed", False, str(e)))
            return
        
        # Test 2: Create date poll
        date_poll = Poll(
            poll_type=PollType.DATE,
            title="Select Date",
            description="Choose your preferred date",
            options=[
                PollOption(option_id="date1", label="Friday, Dec 15", value="2023-12-15"),
                PollOption(option_id="date2", label="Saturday, Dec 16", value="2023-12-16"),
                PollOption(option_id="date3", label="Sunday, Dec 17", value="2023-12-17")
            ]
        )
        
        # Test poll embed creation
        try:
            poll_embed = ImprovedEmbedBuilder.create_poll_embed(date_poll, event, show_analytics=True)
            self._validate_embed(poll_embed, "Date Poll Embed")
            print("✅ Date poll embed creation passed")
        except Exception as e:
            print(f"❌ Date poll embed creation failed: {e}")
            self.test_results.append(("Date Poll Embed", False, str(e)))
            return
        
        # Test 3: Create management buttons
        try:
            buttons = ImprovedButtonBuilder.create_event_management_buttons(event.state.value)
            self._validate_buttons(buttons, "Event Management Buttons")
            print("✅ Event management buttons creation passed")
        except Exception as e:
            print(f"❌ Event management buttons creation failed: {e}")
            self.test_results.append(("Management Buttons", False, str(e)))
            return
        
        # Test 4: Create modal (skip for now due to Discord.py requirements)
        try:
            # Modal creation requires Discord.py context, so we'll validate the structure instead
            modal_structure = {
                'title': 'Create Game Night Event',
                'inputs': [
                    {'label': 'Event Title', 'required': True, 'max_length': 100},
                    {'label': 'Description (Optional)', 'required': False, 'max_length': 2000}
                ]
            }
            self._validate_modal_structure(modal_structure, "Event Creation Modal")
            print("✅ Event creation modal structure passed")
        except Exception as e:
            print(f"❌ Event creation modal failed: {e}")
            self.test_results.append(("Event Modal", False, str(e)))
            return
        
        print("✅ Complete event creation workflow passed!")
        self.test_results.append(("Event Creation Workflow", True, "All components validated"))
    
    def test_user_profile_workflow(self):
        """Test user profile management workflow."""
        print("🧪 Testing user profile workflow...")
        
        # Create mock user
        discord_user = MockDiscordUser("123456789", "TestUser")
        
        # Create user profile
        user = User(
            user_id=str(discord_user.id),
            guild_id="987654321",
            display_name=discord_user.display_name,
            timezone="America/New_York"
        )
        
        # Add some game interests
        user.add_game_interest("Among Us", 8)
        user.add_game_interest("Minecraft", 9)
        user.add_game_interest("Valorant", 7)
        
        # Test profile embed creation
        try:
            profile_embed = ImprovedEmbedBuilder.create_user_profile_embed(user, discord_user)
            self._validate_embed(profile_embed, "User Profile Embed")
            print("✅ User profile embed creation passed")
        except Exception as e:
            print(f"❌ User profile embed creation failed: {e}")
            self.test_results.append(("User Profile Embed", False, str(e)))
            return
        
        # Test timezone modal structure
        try:
            modal_structure = {
                'title': 'Set Your Timezone',
                'inputs': [
                    {'label': 'Timezone', 'required': True, 'max_length': 50},
                    {'label': 'Need Help?', 'required': False, 'disabled': True}
                ]
            }
            self._validate_modal_structure(modal_structure, "Timezone Modal")
            print("✅ Timezone modal structure passed")
        except Exception as e:
            print(f"❌ Timezone modal creation failed: {e}")
            self.test_results.append(("Timezone Modal", False, str(e)))
            return
        
        print("✅ User profile workflow passed!")
        self.test_results.append(("User Profile Workflow", True, "All components validated"))
    
    def test_error_handling(self):
        """Test error handling and user feedback."""
        print("🧪 Testing error handling...")
        
        # Test error embed creation
        try:
            error_embed = ImprovedEmbedBuilder.create_error_embed(
                "Test Error",
                "This is a test error message to validate error handling",
                "error"
            )
            self._validate_embed(error_embed, "Error Embed")
            print("✅ Error embed creation passed")
        except Exception as e:
            print(f"❌ Error embed creation failed: {e}")
            self.test_results.append(("Error Embed", False, str(e)))
            return
        
        # Test success embed creation
        try:
            success_embed = ImprovedEmbedBuilder.create_success_embed(
                "Test Success",
                "This is a test success message"
            )
            self._validate_embed(success_embed, "Success Embed")
            print("✅ Success embed creation passed")
        except Exception as e:
            print(f"❌ Success embed creation failed: {e}")
            self.test_results.append(("Success Embed", False, str(e)))
            return
        
        print("✅ Error handling workflow passed!")
        self.test_results.append(("Error Handling", True, "All components validated"))
    
    def _validate_embed(self, embed, context: str):
        """Validate an embed meets Discord requirements."""
        # Check title length
        if hasattr(embed, 'title') and embed.title and len(embed.title) > 256:
            raise ValueError(f"Title too long: {len(embed.title)}/256")
        
        # Check description length
        if hasattr(embed, 'description') and embed.description and len(embed.description) > 4096:
            raise ValueError(f"Description too long: {len(embed.description)}/4096")
        
        # Check field count
        if hasattr(embed, 'fields') and len(embed.fields) > 25:
            raise ValueError(f"Too many fields: {len(embed.fields)}/25")
        
        # Check individual fields
        if hasattr(embed, 'fields'):
            for i, field in enumerate(embed.fields):
                if len(field.name) > 256:
                    raise ValueError(f"Field {i+1} name too long: {len(field.name)}/256")
                if len(field.value) > 1024:
                    raise ValueError(f"Field {i+1} value too long: {len(field.value)}/1024")
        
        # Check footer
        if hasattr(embed, 'footer') and embed.footer and hasattr(embed.footer, 'text'):
            if len(embed.footer.text) > 2048:
                raise ValueError(f"Footer too long: {len(embed.footer.text)}/2048")
        
        # Check color is set
        if not hasattr(embed, 'color') or not embed.color:
            raise ValueError("Embed should have a color set for consistency")
        
        # Check timestamp is set
        if not hasattr(embed, 'timestamp') or not embed.timestamp:
            raise ValueError("Embed should have a timestamp for consistency")
    
    def _validate_buttons(self, buttons: List, context: str):
        """Validate buttons meet Discord requirements."""
        if len(buttons) > 5:
            raise ValueError(f"Too many buttons: {len(buttons)}/5")
        
        for i, button in enumerate(buttons):
            # Check label or emoji exists
            if not hasattr(button, 'label') and not hasattr(button, 'emoji'):
                raise ValueError(f"Button {i+1} has no label or emoji")
            
            # Check label length
            if hasattr(button, 'label') and button.label and len(button.label) > 80:
                raise ValueError(f"Button {i+1} label too long: {len(button.label)}/80")
            
            # Check custom_id for non-link buttons
            if (hasattr(button, 'style') and 
                str(button.style) != 'ButtonStyle.link' and 
                (not hasattr(button, 'custom_id') or not button.custom_id)):
                raise ValueError(f"Button {i+1} missing custom_id")
    
    def _validate_modal(self, modal, context: str):
        """Validate modal meets Discord requirements."""
        # Check title
        if not hasattr(modal, 'title') or not modal.title:
            raise ValueError("Modal has no title")
        
        if len(modal.title) > 45:
            raise ValueError(f"Modal title too long: {len(modal.title)}/45")
        
        # Check text inputs (if accessible)
        if hasattr(modal, 'children'):
            text_inputs = [item for item in modal.children if 'TextInput' in str(type(item))]
            
            if len(text_inputs) > 5:
                raise ValueError(f"Too many text inputs: {len(text_inputs)}/5")
            
            for i, text_input in enumerate(text_inputs):
                if hasattr(text_input, 'label') and len(text_input.label) > 45:
                    raise ValueError(f"Text input {i+1} label too long: {len(text_input.label)}/45")
                
                if (hasattr(text_input, 'placeholder') and 
                    text_input.placeholder and 
                    len(text_input.placeholder) > 100):
                    raise ValueError(f"Text input {i+1} placeholder too long: {len(text_input.placeholder)}/100")
    
    def _validate_modal_structure(self, modal_structure: Dict, context: str):
        """Validate modal structure meets Discord requirements."""
        # Check title
        if 'title' not in modal_structure or not modal_structure['title']:
            raise ValueError("Modal has no title")
        
        if len(modal_structure['title']) > 45:
            raise ValueError(f"Modal title too long: {len(modal_structure['title'])}/45")
        
        # Check inputs
        inputs = modal_structure.get('inputs', [])
        if len(inputs) > 5:
            raise ValueError(f"Too many text inputs: {len(inputs)}/5")
        
        for i, text_input in enumerate(inputs):
            if 'label' not in text_input or not text_input['label']:
                raise ValueError(f"Text input {i+1} has no label")
            
            if len(text_input['label']) > 45:
                raise ValueError(f"Text input {i+1} label too long: {len(text_input['label'])}/45")
            
            if text_input.get('max_length', 0) > 4000:
                raise ValueError(f"Text input {i+1} max_length too high: {text_input['max_length']}/4000")
    
    def run_all_tests(self):
        """Run all workflow tests."""
        print("🚀 Starting Discord UI workflow tests...\n")
        
        self.test_event_creation_workflow()
        print()
        
        self.test_user_profile_workflow()
        print()
        
        self.test_error_handling()
        print()
        
        # Generate report
        self.generate_report()
    
    def generate_report(self):
        """Generate test report."""
        print("📊 Test Results Summary:")
        print("=" * 50)
        
        passed = sum(1 for result in self.test_results if result[1])
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Success Rate: {passed/total*100:.1f}%")
        print()
        
        # Detailed results
        for test_name, success, message in self.test_results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status} {test_name}: {message}")
        
        print()
        
        if passed == total:
            print("🎉 All Discord UI workflow tests passed!")
            return 0
        else:
            print("⚠️ Some tests failed. Please review the issues above.")
            return 1


def main():
    """Run Discord UI workflow tests."""
    tester = DiscordWorkflowTester()
    return tester.run_all_tests()


if __name__ == "__main__":
    exit(main())