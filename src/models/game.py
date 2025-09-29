"""
Game models for game interest tracking and notification system.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set
from pydantic import Field, field_validator

from .base import BaseDocument, ValidationMixin, TimestampMixin


class GameCategory(str, Enum):
    """Game categories for organization."""
    SURVIVAL = "SURVIVAL"
    TABLETOP_RPG = "TABLETOP_RPG"
    PARTY_GAME = "PARTY_GAME"
    COOPERATIVE = "COOPERATIVE"
    COMPETITIVE = "COMPETITIVE"
    OTHER = "OTHER"


class GameAlias(BaseDocument):
    """Alternative names for a game."""
    
    alias: str = Field(..., min_length=1, max_length=100)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score for fuzzy matching")
    
    @field_validator('alias')
    @classmethod
    def validate_alias(cls, v):
        return ValidationMixin.sanitize_text(v, 100)
    
    def validate_data(self) -> None:
        """Validate game alias."""
        if not self.alias.strip():
            raise ValueError("Alias cannot be empty")


class GameStatistics(BaseDocument):
    """Statistics for a game."""
    
    total_interests: int = Field(default=0, ge=0, description="Total users interested")
    total_pings: int = Field(default=0, ge=0, description="Total ping notifications sent")
    total_plays: int = Field(default=0, ge=0, description="Total recorded plays")
    
    # Trending metrics
    recent_interests: int = Field(default=0, ge=0, description="New interests in last 30 days")
    recent_pings: int = Field(default=0, ge=0, description="Pings in last 7 days")
    recent_plays: int = Field(default=0, ge=0, description="Plays in last 30 days")
    
    # Popularity score (calculated field)
    popularity_score: float = Field(default=0.0, ge=0.0, description="Calculated popularity score")
    
    # Last activity tracking
    last_interest_added: Optional[datetime] = Field(None)
    last_ping_sent: Optional[datetime] = Field(None)
    last_play_recorded: Optional[datetime] = Field(None)
    
    def validate_data(self) -> None:
        """Validate game statistics."""
        # Recalculate popularity score
        self.calculate_popularity_score()
    
    def calculate_popularity_score(self) -> None:
        """Calculate popularity score based on various metrics."""
        # Weight factors for different metrics
        interest_weight = 1.0
        ping_weight = 0.5
        play_weight = 2.0
        recent_weight = 1.5
        
        # Base score from total metrics
        base_score = (
            self.total_interests * interest_weight +
            self.total_pings * ping_weight +
            self.total_plays * play_weight
        )
        
        # Recent activity bonus
        recent_bonus = (
            self.recent_interests * interest_weight * recent_weight +
            self.recent_pings * ping_weight * recent_weight +
            self.recent_plays * play_weight * recent_weight
        )
        
        self.popularity_score = base_score + recent_bonus
    
    def update_interest_added(self) -> None:
        """Update statistics for new interest."""
        self.total_interests += 1
        self.recent_interests += 1
        self.last_interest_added = TimestampMixin.utc_now()
        self.calculate_popularity_score()
    
    def update_interest_removed(self) -> None:
        """Update statistics for removed interest."""
        self.total_interests = max(0, self.total_interests - 1)
        self.calculate_popularity_score()
    
    def update_ping_sent(self) -> None:
        """Update statistics for ping sent."""
        self.total_pings += 1
        self.recent_pings += 1
        self.last_ping_sent = TimestampMixin.utc_now()
        self.calculate_popularity_score()
    
    def update_play_recorded(self) -> None:
        """Update statistics for play recorded."""
        self.total_plays += 1
        self.recent_plays += 1
        self.last_play_recorded = TimestampMixin.utc_now()
        self.calculate_popularity_score()


class NotificationFrequencyLimit(BaseDocument):
    """Notification frequency limits for a user and game."""
    
    user_id: str = Field(..., description="Discord user ID")
    game_name: str = Field(..., min_length=1, max_length=100)
    
    # Frequency settings
    max_pings_per_day: int = Field(default=3, ge=0, le=50)
    max_pings_per_week: int = Field(default=7, ge=0, le=100)
    
    # Current counts
    pings_today: int = Field(default=0, ge=0)
    pings_this_week: int = Field(default=0, ge=0)
    
    # Reset tracking
    last_daily_reset: datetime = Field(default_factory=TimestampMixin.utc_now)
    last_weekly_reset: datetime = Field(default_factory=TimestampMixin.utc_now)
    
    @field_validator('user_id')
    @classmethod
    def validate_user_id(cls, v):
        return ValidationMixin.validate_user_id(v)
    
    @field_validator('game_name')
    @classmethod
    def validate_game_name(cls, v):
        return ValidationMixin.sanitize_text(v, 100)
    
    def validate_data(self) -> None:
        """Validate notification frequency limit."""
        if not self.game_name.strip():
            raise ValueError("Game name cannot be empty")
    
    def can_send_ping(self) -> bool:
        """Check if a ping can be sent based on frequency limits."""
        self._reset_counters_if_needed()
        return (
            self.pings_today < self.max_pings_per_day and
            self.pings_this_week < self.max_pings_per_week
        )
    
    def record_ping_sent(self) -> None:
        """Record that a ping was sent."""
        self._reset_counters_if_needed()
        self.pings_today += 1
        self.pings_this_week += 1
        self.update_timestamp()
    
    def _reset_counters_if_needed(self) -> None:
        """Reset counters if time periods have elapsed."""
        now = TimestampMixin.utc_now()
        
        # Check if we need to reset daily counter
        if (now - self.last_daily_reset).days >= 1:
            self.pings_today = 0
            self.last_daily_reset = now
        
        # Check if we need to reset weekly counter
        if (now - self.last_weekly_reset).days >= 7:
            self.pings_this_week = 0
            self.last_weekly_reset = now


class Game(BaseDocument, ValidationMixin, TimestampMixin):
    """
    Game model for tracking games and their metadata.
    
    Stores game information, aliases, categories, and statistics.
    """
    
    guild_id: str = Field(..., description="Discord guild ID")
    name: str = Field(..., min_length=1, max_length=100, description="Primary game name")
    
    # Metadata
    description: Optional[str] = Field(None, max_length=500, description="Game description")
    categories: List[GameCategory] = Field(default_factory=list, description="Game categories")
    tags: List[str] = Field(default_factory=list, description="Custom tags")
    
    # Alternative names for fuzzy matching
    aliases: List[GameAlias] = Field(default_factory=list, description="Alternative names")
    
    # Statistics
    statistics: GameStatistics = Field(default_factory=GameStatistics)
    
    # Configuration
    is_active: bool = Field(default=True, description="Whether game is active for pings")
    created_by: Optional[str] = Field(None, description="User ID who added the game")
    
    @field_validator('guild_id')
    @classmethod
    def validate_guild_id(cls, v):
        return ValidationMixin.validate_guild_id(v)
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        return ValidationMixin.sanitize_text(v, 100)
    
    @field_validator('description')
    @classmethod
    def validate_description(cls, v):
        if v:
            return ValidationMixin.sanitize_text(v, 500)
        return v
    
    @field_validator('tags')
    @classmethod
    def validate_tags(cls, v):
        return [ValidationMixin.sanitize_text(tag, 50) for tag in v if tag.strip()]
    
    def validate_data(self) -> None:
        """Validate game data and business rules."""
        if not self.name.strip():
            raise ValueError("Game name cannot be empty")
        
        # Validate aliases are unique
        alias_names = [alias.alias.lower() for alias in self.aliases]
        if len(alias_names) != len(set(alias_names)):
            raise ValueError("Duplicate aliases not allowed")
        
        # Ensure primary name is not in aliases
        if self.name.lower() in alias_names:
            raise ValueError("Primary name cannot be an alias")
        
        # Limit number of categories and tags
        if len(self.categories) > 5:
            raise ValueError("Maximum 5 categories allowed")
        
        if len(self.tags) > 10:
            raise ValueError("Maximum 10 tags allowed")
        
        if len(self.aliases) > 20:
            raise ValueError("Maximum 20 aliases allowed")
    
    def add_alias(self, alias: str, confidence: float = 1.0) -> bool:
        """Add an alias for the game. Returns True if added, False if already exists."""
        alias = ValidationMixin.sanitize_text(alias, 100)
        
        # Check if alias already exists (case-insensitive)
        for existing_alias in self.aliases:
            if existing_alias.alias.lower() == alias.lower():
                return False
        
        # Check if alias matches primary name
        if alias.lower() == self.name.lower():
            return False
        
        self.aliases.append(GameAlias(alias=alias, confidence=confidence))
        self.update_timestamp()
        return True
    
    def remove_alias(self, alias: str) -> bool:
        """Remove an alias. Returns True if removed, False if not found."""
        for i, existing_alias in enumerate(self.aliases):
            if existing_alias.alias.lower() == alias.lower():
                del self.aliases[i]
                self.update_timestamp()
                return True
        return False
    
    def get_all_names(self) -> List[str]:
        """Get all names (primary + aliases) for the game."""
        names = [self.name]
        names.extend([alias.alias for alias in self.aliases])
        return names
    
    def matches_name(self, search_name: str) -> Optional[float]:
        """
        Check if search name matches this game and return confidence score.
        
        Args:
            search_name: Name to search for
            
        Returns:
            Confidence score (0.0-1.0) if match found, None otherwise
        """
        search_name = search_name.lower().strip()
        
        # Exact match with primary name
        if search_name == self.name.lower():
            return 1.0
        
        # Check aliases
        for alias in self.aliases:
            if search_name == alias.alias.lower():
                return alias.confidence
        
        return None
    
    def fuzzy_match_score(self, search_name: str) -> float:
        """
        Calculate fuzzy match score for search name.
        
        Args:
            search_name: Name to search for
            
        Returns:
            Fuzzy match score (0.0-1.0)
        """
        from difflib import SequenceMatcher
        
        search_name = search_name.lower().strip()
        best_score = 0.0
        
        # Check primary name
        score = SequenceMatcher(None, search_name, self.name.lower()).ratio()
        best_score = max(best_score, score)
        
        # Check aliases
        for alias in self.aliases:
            score = SequenceMatcher(None, search_name, alias.alias.lower()).ratio()
            # Weight by alias confidence
            weighted_score = score * alias.confidence
            best_score = max(best_score, weighted_score)
        
        return best_score
    
    def add_category(self, category: GameCategory) -> bool:
        """Add a category. Returns True if added, False if already exists."""
        if category not in self.categories:
            self.categories.append(category)
            self.update_timestamp()
            return True
        return False
    
    def remove_category(self, category: GameCategory) -> bool:
        """Remove a category. Returns True if removed, False if not found."""
        if category in self.categories:
            self.categories.remove(category)
            self.update_timestamp()
            return True
        return False
    
    def add_tag(self, tag: str) -> bool:
        """Add a tag. Returns True if added, False if already exists."""
        tag = ValidationMixin.sanitize_text(tag, 50)
        if tag and tag.lower() not in [t.lower() for t in self.tags]:
            self.tags.append(tag)
            self.update_timestamp()
            return True
        return False
    
    def remove_tag(self, tag: str) -> bool:
        """Remove a tag. Returns True if removed, False if not found."""
        for i, existing_tag in enumerate(self.tags):
            if existing_tag.lower() == tag.lower():
                del self.tags[i]
                self.update_timestamp()
                return True
        return False
    
    def update_interest_added(self) -> None:
        """Update statistics when someone adds interest."""
        self.statistics.update_interest_added()
        self.update_timestamp()
    
    def update_interest_removed(self) -> None:
        """Update statistics when someone removes interest."""
        self.statistics.update_interest_removed()
        self.update_timestamp()
    
    def update_ping_sent(self) -> None:
        """Update statistics when a ping is sent."""
        self.statistics.update_ping_sent()
        self.update_timestamp()
    
    def update_play_recorded(self) -> None:
        """Update statistics when a play is recorded."""
        self.statistics.update_play_recorded()
        self.update_timestamp()
    
    def is_trending(self, threshold: float = 5.0) -> bool:
        """Check if game is trending based on recent activity."""
        recent_activity = (
            self.statistics.recent_interests +
            self.statistics.recent_pings +
            self.statistics.recent_plays
        )
        return recent_activity >= threshold
    
    def get_display_name(self) -> str:
        """Get display name with trending indicator."""
        name = self.name
        if self.is_trending():
            name += " 🔥"
        return name