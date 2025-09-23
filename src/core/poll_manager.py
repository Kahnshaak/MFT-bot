"""
Advanced poll management system with timeout handling, tie-breaking, and analytics.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import uuid

from models.event import Event, Poll, PollOption, PollType, EventState
from core.event_bus import EventBus, EventType
from utils.logging_config import get_logger, LoggerMixin
from utils.exceptions import GameNightBotException, ErrorCode


class TieBreakingMethod(str, Enum):
    """Methods for resolving poll ties."""
    ADMIN_CHOICE = "admin_choice"
    RUNOFF_POLL = "runoff_poll"
    RANDOM_SELECTION = "random_selection"
    EXTEND_VOTING = "extend_voting"


class PollAnalytics:
    """Analytics data for a poll."""
    
    def __init__(self):
        self.total_votes: int = 0
        self.unique_voters: int = 0
        self.voting_patterns: Dict[str, Any] = {}
        self.time_to_vote: Dict[str, float] = {}  # user_id -> seconds to vote
        self.vote_changes: List[Dict[str, Any]] = []
        self.peak_voting_times: List[datetime] = []
    
    def record_vote(self, user_id: str, option_id: str, vote_time: datetime, poll_start: datetime):
        """Record a vote for analytics."""
        self.total_votes += 1
        
        # Calculate time to vote
        time_diff = (vote_time - poll_start).total_seconds()
        self.time_to_vote[user_id] = time_diff
        
        # Track voting patterns
        if user_id not in self.voting_patterns:
            self.voting_patterns[user_id] = []
        self.voting_patterns[user_id].append({
            'option_id': option_id,
            'timestamp': vote_time.isoformat(),
            'time_to_vote': time_diff
        })
    
    def record_vote_change(self, user_id: str, old_option: str, new_option: str, change_time: datetime):
        """Record a vote change for analytics."""
        self.vote_changes.append({
            'user_id': user_id,
            'old_option': old_option,
            'new_option': new_option,
            'timestamp': change_time.isoformat()
        })
    
    def get_summary(self) -> Dict[str, Any]:
        """Get analytics summary."""
        self.unique_voters = len(self.voting_patterns)
        
        avg_time_to_vote = 0
        if self.time_to_vote:
            avg_time_to_vote = sum(self.time_to_vote.values()) / len(self.time_to_vote)
        
        return {
            'total_votes': self.total_votes,
            'unique_voters': self.unique_voters,
            'vote_changes': len(self.vote_changes),
            'average_time_to_vote_seconds': avg_time_to_vote,
            'participation_rate': self.unique_voters  # Will be calculated against total eligible users
        }


class PollTimeout:
    """Manages poll timeout and automatic state transitions."""
    
    def __init__(self, poll_id: str, timeout_seconds: int, callback):
        self.poll_id = poll_id
        self.timeout_seconds = timeout_seconds
        self.callback = callback
        self.task: Optional[asyncio.Task] = None
        self.is_cancelled = False
    
    def start(self):
        """Start the timeout task."""
        if not self.is_cancelled:
            self.task = asyncio.create_task(self._timeout_handler())
    
    async def _timeout_handler(self):
        """Handle poll timeout."""
        try:
            await asyncio.sleep(self.timeout_seconds)
            if not self.is_cancelled:
                await self.callback(self.poll_id)
        except asyncio.CancelledError:
            pass
    
    def cancel(self):
        """Cancel the timeout."""
        self.is_cancelled = True
        if self.task and not self.task.done():
            self.task.cancel()
    
    def extend(self, additional_seconds: int):
        """Extend the timeout by additional seconds."""
        if self.task and not self.task.done():
            self.cancel()
            self.timeout_seconds += additional_seconds
            self.start()


class PollManager(LoggerMixin):
    """
    Advanced poll management system with timeout handling, tie-breaking, and analytics.
    """
    
    def __init__(self, event_bus: EventBus, database_manager):
        self.event_bus = event_bus
        self.database = database_manager
        self.active_timeouts: Dict[str, PollTimeout] = {}
        self.poll_analytics: Dict[str, PollAnalytics] = {}
        self.tie_breaking_polls: Dict[str, str] = {}  # tie_poll_id -> original_poll_id
        
        # Default timeout settings (in seconds)
        self.default_timeouts = {
            PollType.DATE: 3600,  # 1 hour
            PollType.TIME: 1800,  # 30 minutes
            PollType.GAME: 1800   # 30 minutes
        }
        
        # Subscribe to events
        self.event_bus.subscribe(EventType.POLL_CREATED, self._on_poll_created)
        self.event_bus.subscribe(EventType.POLL_VOTE_CAST, self._on_vote_cast)
    
    async def create_poll_with_timeout(
        self,
        event: Event,
        poll_type: PollType,
        title: str,
        options: List[Dict[str, Any]],
        timeout_minutes: Optional[int] = None,
        is_multiple_choice: bool = False,
        custom_options: Optional[Dict[str, Any]] = None
    ) -> Poll:
        """
        Create a poll with automatic timeout handling.
        
        Args:
            event: The event this poll belongs to
            poll_type: Type of poll
            title: Poll title
            options: List of option data
            timeout_minutes: Custom timeout in minutes
            is_multiple_choice: Whether multiple selections are allowed
            custom_options: Additional poll customization options
        """
        # Create poll options
        poll_options = []
        for i, option_data in enumerate(options):
            option = PollOption(
                option_id=str(uuid.uuid4()),
                label=option_data['label'],
                value=option_data['value']
            )
            poll_options.append(option)
        
        # Calculate timeout
        timeout_seconds = self.default_timeouts.get(poll_type, 1800)
        if timeout_minutes:
            timeout_seconds = timeout_minutes * 60
        
        closes_at = datetime.utcnow() + timedelta(seconds=timeout_seconds)
        
        # Create poll
        poll = Poll(
            poll_type=poll_type,
            title=title,
            options=poll_options,
            is_multiple_choice=is_multiple_choice,
            closes_at=closes_at
        )
        
        # Apply custom options
        if custom_options:
            if 'description' in custom_options:
                poll.description = custom_options['description']
        
        # Add poll to event
        event.add_poll(poll)
        
        # Initialize analytics
        poll_id = f"{event.id}_{poll_type.value}"
        self.poll_analytics[poll_id] = PollAnalytics()
        
        # Set up timeout
        timeout_handler = PollTimeout(
            poll_id=poll_id,
            timeout_seconds=timeout_seconds,
            callback=self._handle_poll_timeout
        )
        self.active_timeouts[poll_id] = timeout_handler
        timeout_handler.start()
        
        # Emit poll created event
        await self.event_bus.emit(
            EventType.POLL_CREATED,
            {
                'event_id': str(event.id),
                'poll_type': poll_type.value,
                'timeout_seconds': timeout_seconds,
                'option_count': len(poll_options)
            },
            source='poll_manager',
            guild_id=event.guild_id
        )
        
        self.logger.info(
            f"Created {poll_type.value} poll with {len(poll_options)} options, "
            f"timeout: {timeout_seconds}s"
        )
        
        return poll
    
    async def _handle_poll_timeout(self, poll_id: str):
        """Handle automatic poll timeout."""
        try:
            # Parse poll_id to get event_id and poll_type
            event_id, poll_type_str = poll_id.rsplit('_', 1)
            poll_type = PollType(poll_type_str)
            
            # Get event from database
            event_data = await self.database.events.find_one({'_id': event_id})
            if not event_data:
                self.logger.error(f"Event not found for poll timeout: {event_id}")
                return
            
            event = Event(**event_data)
            poll = event.get_poll(poll_type)
            
            if not poll or not poll.is_active:
                return
            
            self.logger.info(f"Poll timeout reached for {poll_type.value} poll in event {event_id}")
            
            # Check for ties
            winning_options = self._get_winning_options(poll)
            
            if len(winning_options) > 1:
                # Handle tie
                await self._handle_poll_tie(event, poll, winning_options)
            else:
                # Close poll normally
                await self._close_poll_and_advance(event, poll)
            
            # Emit timeout event
            await self.event_bus.emit(
                EventType.POLL_EXPIRED,
                {
                    'event_id': str(event.id),
                    'poll_type': poll_type.value,
                    'had_tie': len(winning_options) > 1,
                    'analytics': self.poll_analytics.get(poll_id, PollAnalytics()).get_summary()
                },
                source='poll_manager',
                guild_id=event.guild_id
            )
            
        except Exception as e:
            self.logger.error(f"Error handling poll timeout: {e}", exc_info=True)
    
    def _get_winning_options(self, poll: Poll) -> List[PollOption]:
        """Get all options tied for the highest vote count."""
        if not poll.options:
            return []
        
        max_votes = max(option.vote_count for option in poll.options)
        return [option for option in poll.options if option.vote_count == max_votes]
    
    async def _handle_poll_tie(self, event: Event, poll: Poll, tied_options: List[PollOption]):
        """Handle a tie in poll results."""
        self.logger.info(f"Handling tie in {poll.poll_type.value} poll with {len(tied_options)} options")
        
        # For now, use admin choice method
        # In a full implementation, this would check guild settings for preferred tie-breaking method
        tie_method = TieBreakingMethod.ADMIN_CHOICE
        
        if tie_method == TieBreakingMethod.ADMIN_CHOICE:
            await self._request_admin_tie_resolution(event, poll, tied_options)
        elif tie_method == TieBreakingMethod.RUNOFF_POLL:
            await self._create_runoff_poll(event, poll, tied_options)
        elif tie_method == TieBreakingMethod.EXTEND_VOTING:
            await self._extend_poll_voting(event, poll)
        else:  # RANDOM_SELECTION
            await self._resolve_tie_randomly(event, poll, tied_options)
    
    async def _request_admin_tie_resolution(self, event: Event, poll: Poll, tied_options: List[PollOption]):
        """Request admin intervention to resolve tie."""
        # Mark poll as needing admin resolution
        poll.is_active = False
        poll.winner_option_id = None  # Clear any previous winner
        
        # Update event in database
        await self.database.events.update_one(
            {'_id': str(event.id)},
            {'$set': event.model_dump()}
        )
        
        # Emit event for admin notification
        await self.event_bus.emit(
            EventType.POLL_COMPLETED,
            {
                'event_id': str(event.id),
                'poll_type': poll.poll_type.value,
                'result': 'tie_needs_admin_resolution',
                'tied_options': [{'id': opt.option_id, 'label': opt.label, 'votes': opt.vote_count} 
                               for opt in tied_options]
            },
            source='poll_manager',
            guild_id=event.guild_id
        )
    
    async def _create_runoff_poll(self, event: Event, original_poll: Poll, tied_options: List[PollOption]):
        """Create a runoff poll with only the tied options."""
        runoff_title = f"Runoff: {original_poll.title}"
        runoff_options = [
            {'label': opt.label, 'value': opt.value}
            for opt in tied_options
        ]
        
        # Create runoff poll with shorter timeout
        runoff_poll = await self.create_poll_with_timeout(
            event=event,
            poll_type=original_poll.poll_type,
            title=runoff_title,
            options=runoff_options,
            timeout_minutes=15,  # Shorter timeout for runoff
            is_multiple_choice=original_poll.is_multiple_choice
        )
        
        # Track that this is a tie-breaking poll
        runoff_poll_id = f"{event.id}_{original_poll.poll_type.value}"
        original_poll_id = f"{event.id}_{original_poll.poll_type.value}_original"
        self.tie_breaking_polls[runoff_poll_id] = original_poll_id
        
        # Close original poll
        original_poll.is_active = False
        
        # Update event
        await self.database.events.update_one(
            {'_id': str(event.id)},
            {'$set': event.model_dump()}
        )
    
    async def _extend_poll_voting(self, event: Event, poll: Poll):
        """Extend poll voting time."""
        extension_minutes = 15
        poll.closes_at = datetime.utcnow() + timedelta(minutes=extension_minutes)
        
        # Extend timeout
        poll_id = f"{event.id}_{poll.poll_type.value}"
        if poll_id in self.active_timeouts:
            self.active_timeouts[poll_id].extend(extension_minutes * 60)
        
        # Update event
        await self.database.events.update_one(
            {'_id': str(event.id)},
            {'$set': event.model_dump()}
        )
        
        # Notify about extension
        await self.event_bus.emit(
            EventType.POLL_UPDATED,
            {
                'event_id': str(event.id),
                'poll_type': poll.poll_type.value,
                'action': 'extended',
                'extension_minutes': extension_minutes
            },
            source='poll_manager',
            guild_id=event.guild_id
        )
    
    async def _resolve_tie_randomly(self, event: Event, poll: Poll, tied_options: List[PollOption]):
        """Resolve tie by random selection."""
        import random
        winner = random.choice(tied_options)
        
        poll.is_active = False
        poll.winner_option_id = winner.option_id
        
        # Update event and advance state
        await self._close_poll_and_advance(event, poll)
        
        # Emit random resolution event
        await self.event_bus.emit(
            EventType.POLL_COMPLETED,
            {
                'event_id': str(event.id),
                'poll_type': poll.poll_type.value,
                'result': 'tie_resolved_randomly',
                'winner': {'id': winner.option_id, 'label': winner.label}
            },
            source='poll_manager',
            guild_id=event.guild_id
        )
    
    async def _close_poll_and_advance(self, event: Event, poll: Poll):
        """Close poll and advance event to next state."""
        # Close poll
        winner_option_id = poll.close_poll()
        
        # Advance event state
        if poll.poll_type == PollType.DATE and event.state == EventState.DATE_POLLING:
            if winner_option_id:
                # Set selected date
                winner_option = poll.get_option_by_id(winner_option_id)
                if winner_option:
                    event.schedule.selected_date = winner_option.value
            event.transition_to(EventState.TIME_POLLING)
            
        elif poll.poll_type == PollType.TIME and event.state == EventState.TIME_POLLING:
            if winner_option_id:
                # Set selected time
                winner_option = poll.get_option_by_id(winner_option_id)
                if winner_option:
                    event.schedule.selected_time = winner_option.value
            event.transition_to(EventState.GAME_POLLING)
            
        elif poll.poll_type == PollType.GAME and event.state == EventState.GAME_POLLING:
            event.transition_to(EventState.SCHEDULED)
        
        # Update event in database
        await self.database.events.update_one(
            {'_id': str(event.id)},
            {'$set': event.model_dump()}
        )
        
        # Clean up timeout
        poll_id = f"{event.id}_{poll.poll_type.value}"
        if poll_id in self.active_timeouts:
            self.active_timeouts[poll_id].cancel()
            del self.active_timeouts[poll_id]
        
        # Emit completion event
        await self.event_bus.emit(
            EventType.POLL_COMPLETED,
            {
                'event_id': str(event.id),
                'poll_type': poll.poll_type.value,
                'winner_option_id': winner_option_id,
                'new_event_state': event.state.value
            },
            source='poll_manager',
            guild_id=event.guild_id
        )
    
    async def _on_poll_created(self, event_data):
        """Handle poll created event."""
        # Initialize notification scheduling for poll reminders
        await self._schedule_poll_reminders(event_data.data)
    
    async def _on_vote_cast(self, event_data):
        """Handle vote cast event for analytics."""
        data = event_data.data
        poll_id = f"{data['event_id']}_{data['poll_type']}"
        
        if poll_id in self.poll_analytics:
            analytics = self.poll_analytics[poll_id]
            analytics.record_vote(
                user_id=data['user_id'],
                option_id=data.get('option_id', data.get('option_ids', [''])[0]),
                vote_time=datetime.utcnow(),
                poll_start=datetime.utcnow()  # This should be stored when poll is created
            )
    
    async def _schedule_poll_reminders(self, poll_data: Dict[str, Any]):
        """Schedule reminder notifications for poll."""
        # This would integrate with the notifications system
        # For now, just emit a notification scheduling event
        await self.event_bus.emit(
            EventType.NOTIFICATION_SCHEDULED,
            {
                'type': 'poll_reminder',
                'event_id': poll_data['event_id'],
                'poll_type': poll_data['poll_type'],
                'reminder_times': ['15_minutes_before', '5_minutes_before']
            },
            source='poll_manager'
        )
    
    async def admin_resolve_tie(self, event_id: str, poll_type: PollType, chosen_option_id: str) -> bool:
        """Allow admin to manually resolve a tie."""
        try:
            # Get event
            event_data = await self.database.events.find_one({'_id': event_id})
            if not event_data:
                return False
            
            event = Event(**event_data)
            poll = event.get_poll(poll_type)
            
            if not poll:
                return False
            
            # Set winner and close poll
            poll.winner_option_id = chosen_option_id
            poll.is_active = False
            
            # Advance event state
            await self._close_poll_and_advance(event, poll)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error in admin tie resolution: {e}", exc_info=True)
            return False
    
    def get_poll_analytics(self, event_id: str, poll_type: PollType) -> Optional[Dict[str, Any]]:
        """Get analytics for a specific poll."""
        poll_id = f"{event_id}_{poll_type.value}"
        if poll_id in self.poll_analytics:
            return self.poll_analytics[poll_id].get_summary()
        return None
    
    async def add_custom_poll_option(self, event_id: str, poll_type: PollType, label: str, value: Any) -> bool:
        """Add a custom option to an active poll."""
        try:
            # Get event
            event_data = await self.database.events.find_one({'_id': event_id})
            if not event_data:
                return False
            
            event = Event(**event_data)
            poll = event.get_poll(poll_type)
            
            if not poll or not poll.is_active:
                return False
            
            # Add new option
            new_option = PollOption(
                option_id=str(uuid.uuid4()),
                label=label,
                value=value
            )
            poll.options.append(new_option)
            
            # Update event in database
            await self.database.events.update_one(
                {'_id': event_id},
                {'$set': event.model_dump()}
            )
            
            # Emit update event
            await self.event_bus.emit(
                EventType.POLL_UPDATED,
                {
                    'event_id': event_id,
                    'poll_type': poll_type.value,
                    'action': 'option_added',
                    'new_option': {'id': new_option.option_id, 'label': label}
                },
                source='poll_manager',
                guild_id=event.guild_id
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error adding custom poll option: {e}", exc_info=True)
            return False
    
    def cleanup_expired_data(self):
        """Clean up expired poll data and analytics."""
        # Remove analytics for polls older than 30 days
        # This would be called periodically by a background task
        cutoff_time = datetime.utcnow() - timedelta(days=30)
        
        expired_polls = []
        for poll_id, analytics in self.poll_analytics.items():
            # Check if poll is old (this is simplified - in reality we'd check creation time)
            if len(analytics.voting_patterns) == 0:  # No recent activity
                expired_polls.append(poll_id)
        
        for poll_id in expired_polls:
            del self.poll_analytics[poll_id]
            if poll_id in self.active_timeouts:
                self.active_timeouts[poll_id].cancel()
                del self.active_timeouts[poll_id]