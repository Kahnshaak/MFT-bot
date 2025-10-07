"""
Caching layer for frequently accessed data with TTL and invalidation support.
"""

import asyncio
import time
from typing import Dict, Any, Optional, Set, Callable, Union, List
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

from utils.logging_config import get_logger, LoggerMixin


class CacheStrategy(Enum):
    """Cache eviction strategies."""
    
    LRU = "lru"           # Least Recently Used
    TTL = "ttl"           # Time To Live
    LFU = "lfu"           # Least Frequently Used
    FIFO = "fifo"         # First In First Out


@dataclass
class CacheEntry:
    """Represents a cached entry with metadata."""
    
    key: str
    value: Any
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    ttl: Optional[float] = None
    
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.ttl is None:
            return False
        return time.time() - self.created_at > self.ttl
    
    def touch(self) -> None:
        """Update access metadata."""
        self.last_accessed = time.time()
        self.access_count += 1


class CacheManager(LoggerMixin):
    """
    High-performance caching system with multiple eviction strategies.
    
    Supports TTL, LRU, LFU, and FIFO eviction policies with automatic
    cleanup and memory management.
    """
    
    def __init__(
        self,
        max_size: int = 10000,
        default_ttl: Optional[float] = 3600,  # 1 hour
        strategy: CacheStrategy = CacheStrategy.LRU,
        cleanup_interval: float = 300  # 5 minutes
    ):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.strategy = strategy
        self.cleanup_interval = cleanup_interval
        
        # Storage
        self._cache: Dict[str, CacheEntry] = {}
        self._access_order: Dict[str, float] = {}  # For LRU
        self._insertion_order: Dict[str, float] = {}  # For FIFO
        
        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        
        # Background cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self) -> None:
        """Start the cache manager with background cleanup."""
        if self._running:
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self.logger.info("Cache manager started")
    
    async def stop(self) -> None:
        """Stop the cache manager."""
        self._running = False
        
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Cache manager stopped")
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        entry = self._cache.get(key)
        
        if entry is None:
            self._misses += 1
            return None
        
        if entry.is_expired():
            await self.delete(key)
            self._misses += 1
            return None
        
        # Update access metadata
        entry.touch()
        self._access_order[key] = time.time()
        
        self._hits += 1
        return entry.value
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[float] = None
    ) -> None:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (uses default if None)
        """
        # Use default TTL if not specified
        if ttl is None:
            ttl = self.default_ttl
        
        # Check if we need to evict entries
        if len(self._cache) >= self.max_size and key not in self._cache:
            await self._evict_entries(1)
        
        # Create cache entry
        entry = CacheEntry(
            key=key,
            value=value,
            ttl=ttl
        )
        
        # Store entry
        self._cache[key] = entry
        self._access_order[key] = time.time()
        
        if key not in self._insertion_order:
            self._insertion_order[key] = time.time()
        
        self.logger.debug(f"Cached entry: {key}")
    
    async def delete(self, key: str) -> bool:
        """
        Delete entry from cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if entry was deleted, False if not found
        """
        if key in self._cache:
            del self._cache[key]
            self._access_order.pop(key, None)
            self._insertion_order.pop(key, None)
            self.logger.debug(f"Deleted cache entry: {key}")
            return True
        
        return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache and is not expired."""
        entry = self._cache.get(key)
        if entry is None:
            return False
        
        if entry.is_expired():
            await self.delete(key)
            return False
        
        return True
    
    async def clear(self) -> None:
        """Clear all cache entries."""
        count = len(self._cache)
        self._cache.clear()
        self._access_order.clear()
        self._insertion_order.clear()
        
        self.logger.info(f"Cleared {count} cache entries")
    
    async def get_or_set(
        self,
        key: str,
        factory: Callable,
        ttl: Optional[float] = None
    ) -> Any:
        """
        Get value from cache or set it using factory function.
        
        Args:
            key: Cache key
            factory: Function to generate value if not cached
            ttl: Time to live in seconds
            
        Returns:
            Cached or generated value
        """
        value = await self.get(key)
        
        if value is not None:
            return value
        
        # Generate value
        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()
        
        await self.set(key, value, ttl)
        return value
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching a pattern.
        
        Args:
            pattern: Pattern to match (supports * wildcard)
            
        Returns:
            Number of keys invalidated
        """
        import fnmatch
        
        keys_to_delete = []
        for key in self._cache.keys():
            if fnmatch.fnmatch(key, pattern):
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            await self.delete(key)
        
        self.logger.info(f"Invalidated {len(keys_to_delete)} keys matching pattern: {pattern}")
        return len(keys_to_delete)
    
    async def _evict_entries(self, count: int) -> None:
        """Evict entries based on configured strategy."""
        if not self._cache:
            return
        
        keys_to_evict = []
        
        if self.strategy == CacheStrategy.LRU:
            # Evict least recently used
            sorted_keys = sorted(
                self._access_order.items(),
                key=lambda x: x[1]
            )
            keys_to_evict = [key for key, _ in sorted_keys[:count]]
        
        elif self.strategy == CacheStrategy.LFU:
            # Evict least frequently used
            sorted_entries = sorted(
                self._cache.items(),
                key=lambda x: x[1].access_count
            )
            keys_to_evict = [key for key, _ in sorted_entries[:count]]
        
        elif self.strategy == CacheStrategy.FIFO:
            # Evict first inserted
            sorted_keys = sorted(
                self._insertion_order.items(),
                key=lambda x: x[1]
            )
            keys_to_evict = [key for key, _ in sorted_keys[:count]]
        
        elif self.strategy == CacheStrategy.TTL:
            # Evict expired entries first, then oldest
            expired_keys = []
            for key, entry in self._cache.items():
                if entry.is_expired():
                    expired_keys.append(key)
            
            if len(expired_keys) >= count:
                keys_to_evict = expired_keys[:count]
            else:
                keys_to_evict = expired_keys
                # Add oldest entries to reach count
                remaining = count - len(expired_keys)
                sorted_keys = sorted(
                    [(k, v) for k, v in self._cache.items() if k not in expired_keys],
                    key=lambda x: x[1].created_at
                )
                keys_to_evict.extend([key for key, _ in sorted_keys[:remaining]])
        
        # Evict selected keys
        for key in keys_to_evict:
            await self.delete(key)
            self._evictions += 1
        
        if keys_to_evict:
            self.logger.debug(f"Evicted {len(keys_to_evict)} entries using {self.strategy.value} strategy")
    
    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired entries."""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in cache cleanup: {e}", exc_info=True)
    
    async def _cleanup_expired(self) -> None:
        """Remove expired entries from cache."""
        expired_keys = []
        
        for key, entry in self._cache.items():
            if entry.is_expired():
                expired_keys.append(key)
        
        for key in expired_keys:
            await self.delete(key)
        
        if expired_keys:
            self.logger.debug(f"Cleaned up {len(expired_keys)} expired entries")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "evictions": self._evictions,
            "strategy": self.strategy.value,
            "default_ttl": self.default_ttl
        }
    
    def reset_stats(self) -> None:
        """Reset cache statistics."""
        self._hits = 0
        self._misses = 0
        self._evictions = 0


class NamespacedCache:
    """Cache with namespace support for logical separation."""
    
    def __init__(self, cache_manager: CacheManager, namespace: str):
        self.cache_manager = cache_manager
        self.namespace = namespace
    
    def _make_key(self, key: str) -> str:
        """Create namespaced key."""
        return f"{self.namespace}:{key}"
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from namespaced cache."""
        return await self.cache_manager.get(self._make_key(key))
    
    async def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Set value in namespaced cache."""
        await self.cache_manager.set(self._make_key(key), value, ttl)
    
    async def delete(self, key: str) -> bool:
        """Delete value from namespaced cache."""
        return await self.cache_manager.delete(self._make_key(key))
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in namespaced cache."""
        return await self.cache_manager.exists(self._make_key(key))
    
    async def clear(self) -> None:
        """Clear all entries in this namespace."""
        await self.cache_manager.invalidate_pattern(f"{self.namespace}:*")
    
    async def get_or_set(
        self,
        key: str,
        factory: Callable,
        ttl: Optional[float] = None
    ) -> Any:
        """Get or set value in namespaced cache."""
        return await self.cache_manager.get_or_set(
            self._make_key(key),
            factory,
            ttl
        )


# Specialized caches for common use cases
class UserPreferencesCache(NamespacedCache):
    """Cache for user preferences with automatic invalidation."""
    
    def __init__(self, cache_manager: CacheManager):
        super().__init__(cache_manager, "user_prefs")
        self.default_ttl = 1800  # 30 minutes
    
    async def get_user_preferences(self, user_id: str, guild_id: str) -> Optional[Dict[str, Any]]:
        """Get user preferences from cache."""
        key = f"{guild_id}:{user_id}"
        return await self.get(key)
    
    async def set_user_preferences(
        self,
        user_id: str,
        guild_id: str,
        preferences: Dict[str, Any]
    ) -> None:
        """Set user preferences in cache."""
        key = f"{guild_id}:{user_id}"
        await self.set(key, preferences, self.default_ttl)
    
    async def invalidate_user(self, user_id: str, guild_id: str) -> None:
        """Invalidate specific user's preferences."""
        key = f"{guild_id}:{user_id}"
        await self.delete(key)


class GameListCache(NamespacedCache):
    """Cache for game lists with popularity tracking."""
    
    def __init__(self, cache_manager: CacheManager):
        super().__init__(cache_manager, "games")
        self.default_ttl = 900  # 15 minutes
    
    async def get_guild_games(self, guild_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get guild's game list from cache."""
        return await self.get(f"guild:{guild_id}")
    
    async def set_guild_games(self, guild_id: str, games: List[Dict[str, Any]]) -> None:
        """Set guild's game list in cache."""
        await self.set(f"guild:{guild_id}", games, self.default_ttl)
    
    async def get_popular_games(self, guild_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get popular games from cache."""
        return await self.get(f"popular:{guild_id}")
    
    async def set_popular_games(self, guild_id: str, games: List[Dict[str, Any]]) -> None:
        """Set popular games in cache."""
        await self.set(f"popular:{guild_id}", games, self.default_ttl)
    
    async def invalidate_guild(self, guild_id: str) -> None:
        """Invalidate all game data for a guild."""
        await self.cache_manager.invalidate_pattern(f"games:*:{guild_id}")


class EventCache(NamespacedCache):
    """Cache for event data with state-based invalidation."""
    
    def __init__(self, cache_manager: CacheManager):
        super().__init__(cache_manager, "events")
        self.default_ttl = 600  # 10 minutes
    
    async def get_guild_events(
        self,
        guild_id: str,
        state: Optional[str] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """Get guild events from cache."""
        key = f"guild:{guild_id}"
        if state:
            key += f":{state}"
        return await self.get(key)
    
    async def set_guild_events(
        self,
        guild_id: str,
        events: List[Dict[str, Any]],
        state: Optional[str] = None
    ) -> None:
        """Set guild events in cache."""
        key = f"guild:{guild_id}"
        if state:
            key += f":{state}"
        await self.set(key, events, self.default_ttl)
    
    async def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get specific event from cache."""
        return await self.get(f"event:{event_id}")
    
    async def set_event(self, event_id: str, event_data: Dict[str, Any]) -> None:
        """Set specific event in cache."""
        await self.set(f"event:{event_id}", event_data, self.default_ttl)
    
    async def invalidate_event(self, event_id: str) -> None:
        """Invalidate specific event and related caches."""
        await self.delete(f"event:{event_id}")
        # Also invalidate guild event lists that might contain this event
        # This is a simple approach - could be more sophisticated
        await self.cache_manager.invalidate_pattern("events:guild:*")