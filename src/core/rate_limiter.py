"""
Rate limiting and throttling system for resource-intensive operations.
"""

import asyncio
import time
from typing import Dict, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

from utils.logging_config import get_logger, LoggerMixin


class RateLimitStrategy(Enum):
    """Rate limiting strategies."""
    
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"
    LEAKY_BUCKET = "leaky_bucket"


@dataclass
class RateLimitRule:
    """Rate limiting rule configuration."""
    
    name: str
    max_requests: int
    window_seconds: float
    strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW
    burst_allowance: Optional[int] = None
    cooldown_seconds: Optional[float] = None
    
    def __post_init__(self):
        if self.burst_allowance is None:
            self.burst_allowance = max(1, self.max_requests // 4)


@dataclass
class RateLimitState:
    """Current state of rate limiting for a key."""
    
    key: str
    rule: RateLimitRule
    requests: deque = field(default_factory=deque)
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.time)
    blocked_until: Optional[float] = None
    total_requests: int = 0
    blocked_requests: int = 0
    
    def is_blocked(self) -> bool:
        """Check if key is currently blocked."""
        if self.blocked_until is None:
            return False
        return time.time() < self.blocked_until
    
    def block_until(self, until_time: float) -> None:
        """Block key until specified time."""
        self.blocked_until = until_time
    
    def unblock(self) -> None:
        """Remove block from key."""
        self.blocked_until = None


class RateLimiter(LoggerMixin):
    """
    Comprehensive rate limiting system with multiple strategies.
    
    Supports token bucket, sliding window, fixed window, and leaky bucket
    algorithms with per-key tracking and automatic cleanup.
    """
    
    def __init__(self, cleanup_interval: float = 300):
        self.cleanup_interval = cleanup_interval
        
        # Rate limiting rules
        self._rules: Dict[str, RateLimitRule] = {}
        
        # Per-key state tracking
        self._states: Dict[str, RateLimitState] = {}
        
        # Global statistics
        self._total_requests = 0
        self._total_blocked = 0
        
        # Background cleanup
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self) -> None:
        """Start the rate limiter with background cleanup."""
        if self._running:
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self.logger.info("Rate limiter started")
    
    async def stop(self) -> None:
        """Stop the rate limiter."""
        self._running = False
        
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Rate limiter stopped")
    
    def add_rule(self, rule: RateLimitRule) -> None:
        """Add a rate limiting rule."""
        self._rules[rule.name] = rule
        self.logger.info(f"Added rate limit rule: {rule.name} ({rule.max_requests}/{rule.window_seconds}s)")
    
    def remove_rule(self, rule_name: str) -> bool:
        """Remove a rate limiting rule."""
        if rule_name in self._rules:
            del self._rules[rule_name]
            # Clean up states using this rule
            states_to_remove = [
                key for key, state in self._states.items()
                if state.rule.name == rule_name
            ]
            for key in states_to_remove:
                del self._states[key]
            
            self.logger.info(f"Removed rate limit rule: {rule_name}")
            return True
        return False
    
    async def check_rate_limit(
        self,
        rule_name: str,
        key: str,
        cost: int = 1
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Check if request is allowed under rate limit.
        
        Args:
            rule_name: Name of the rate limiting rule
            key: Unique identifier for the rate limit (user_id, ip, etc.)
            cost: Cost of this request (default 1)
            
        Returns:
            Tuple of (allowed, metadata)
        """
        if rule_name not in self._rules:
            self.logger.warning(f"Rate limit rule not found: {rule_name}")
            return True, {"error": "rule_not_found"}
        
        rule = self._rules[rule_name]
        state_key = f"{rule_name}:{key}"
        
        # Get or create state
        if state_key not in self._states:
            self._states[state_key] = RateLimitState(
                key=state_key,
                rule=rule,
                tokens=float(rule.max_requests)
            )
        
        state = self._states[state_key]
        current_time = time.time()
        
        # Check if blocked
        if state.is_blocked():
            state.blocked_requests += 1
            self._total_blocked += 1
            
            return False, {
                "blocked": True,
                "blocked_until": state.blocked_until,
                "retry_after": state.blocked_until - current_time
            }
        
        # Apply rate limiting strategy
        allowed = False
        metadata = {}
        
        if rule.strategy == RateLimitStrategy.TOKEN_BUCKET:
            allowed, metadata = await self._check_token_bucket(state, cost, current_time)
        elif rule.strategy == RateLimitStrategy.SLIDING_WINDOW:
            allowed, metadata = await self._check_sliding_window(state, cost, current_time)
        elif rule.strategy == RateLimitStrategy.FIXED_WINDOW:
            allowed, metadata = await self._check_fixed_window(state, cost, current_time)
        elif rule.strategy == RateLimitStrategy.LEAKY_BUCKET:
            allowed, metadata = await self._check_leaky_bucket(state, cost, current_time)
        
        # Update statistics
        state.total_requests += 1
        self._total_requests += 1
        
        if not allowed:
            state.blocked_requests += 1
            self._total_blocked += 1
            
            # Apply cooldown if configured
            if rule.cooldown_seconds:
                state.block_until(current_time + rule.cooldown_seconds)
                metadata["cooldown_applied"] = True
                metadata["blocked_until"] = state.blocked_until
        
        metadata.update({
            "rule_name": rule_name,
            "key": key,
            "cost": cost,
            "total_requests": state.total_requests,
            "blocked_requests": state.blocked_requests
        })
        
        return allowed, metadata
    
    async def _check_token_bucket(
        self,
        state: RateLimitState,
        cost: int,
        current_time: float
    ) -> tuple[bool, Dict[str, Any]]:
        """Check rate limit using token bucket algorithm."""
        rule = state.rule
        
        # Refill tokens
        time_passed = current_time - state.last_refill
        tokens_to_add = time_passed * (rule.max_requests / rule.window_seconds)
        state.tokens = min(rule.max_requests, state.tokens + tokens_to_add)
        state.last_refill = current_time
        
        # Check if enough tokens
        if state.tokens >= cost:
            state.tokens -= cost
            return True, {
                "tokens_remaining": state.tokens,
                "tokens_max": rule.max_requests
            }
        else:
            return False, {
                "tokens_remaining": state.tokens,
                "tokens_needed": cost,
                "tokens_max": rule.max_requests
            }
    
    async def _check_sliding_window(
        self,
        state: RateLimitState,
        cost: int,
        current_time: float
    ) -> tuple[bool, Dict[str, Any]]:
        """Check rate limit using sliding window algorithm."""
        rule = state.rule
        window_start = current_time - rule.window_seconds
        
        # Remove old requests
        while state.requests and state.requests[0] < window_start:
            state.requests.popleft()
        
        # Count current requests
        current_requests = sum(state.requests) if state.requests else 0
        
        if current_requests + cost <= rule.max_requests:
            # Add request timestamps (with cost)
            for _ in range(cost):
                state.requests.append(current_time)
            
            return True, {
                "requests_in_window": current_requests + cost,
                "requests_max": rule.max_requests,
                "window_reset": current_time + rule.window_seconds
            }
        else:
            return False, {
                "requests_in_window": current_requests,
                "requests_max": rule.max_requests,
                "requests_needed": cost,
                "window_reset": state.requests[0] + rule.window_seconds if state.requests else current_time
            }
    
    async def _check_fixed_window(
        self,
        state: RateLimitState,
        cost: int,
        current_time: float
    ) -> tuple[bool, Dict[str, Any]]:
        """Check rate limit using fixed window algorithm."""
        rule = state.rule
        
        # Calculate current window
        window_start = int(current_time // rule.window_seconds) * rule.window_seconds
        window_end = window_start + rule.window_seconds
        
        # Reset if new window
        if not state.requests or state.requests[-1] < window_start:
            state.requests.clear()
        
        # Count requests in current window
        current_requests = len(state.requests)
        
        if current_requests + cost <= rule.max_requests:
            # Add request timestamps
            for _ in range(cost):
                state.requests.append(current_time)
            
            return True, {
                "requests_in_window": current_requests + cost,
                "requests_max": rule.max_requests,
                "window_reset": window_end
            }
        else:
            return False, {
                "requests_in_window": current_requests,
                "requests_max": rule.max_requests,
                "requests_needed": cost,
                "window_reset": window_end
            }
    
    async def _check_leaky_bucket(
        self,
        state: RateLimitState,
        cost: int,
        current_time: float
    ) -> tuple[bool, Dict[str, Any]]:
        """Check rate limit using leaky bucket algorithm."""
        rule = state.rule
        
        # Calculate leak rate (requests per second)
        leak_rate = rule.max_requests / rule.window_seconds
        
        # Leak tokens
        time_passed = current_time - state.last_refill
        tokens_to_leak = time_passed * leak_rate
        state.tokens = max(0, state.tokens - tokens_to_leak)
        state.last_refill = current_time
        
        # Check if bucket has capacity
        bucket_capacity = rule.max_requests + (rule.burst_allowance or 0)
        
        if state.tokens + cost <= bucket_capacity:
            state.tokens += cost
            return True, {
                "bucket_level": state.tokens,
                "bucket_capacity": bucket_capacity,
                "leak_rate": leak_rate
            }
        else:
            return False, {
                "bucket_level": state.tokens,
                "bucket_capacity": bucket_capacity,
                "overflow": (state.tokens + cost) - bucket_capacity
            }
    
    async def reset_key(self, rule_name: str, key: str) -> bool:
        """Reset rate limit state for a specific key."""
        state_key = f"{rule_name}:{key}"
        
        if state_key in self._states:
            state = self._states[state_key]
            state.requests.clear()
            state.tokens = float(state.rule.max_requests)
            state.last_refill = time.time()
            state.unblock()
            
            self.logger.info(f"Reset rate limit state for {state_key}")
            return True
        
        return False
    
    async def get_key_status(self, rule_name: str, key: str) -> Optional[Dict[str, Any]]:
        """Get current status for a rate limited key."""
        state_key = f"{rule_name}:{key}"
        
        if state_key not in self._states:
            return None
        
        state = self._states[state_key]
        current_time = time.time()
        
        status = {
            "key": key,
            "rule_name": rule_name,
            "total_requests": state.total_requests,
            "blocked_requests": state.blocked_requests,
            "is_blocked": state.is_blocked(),
            "blocked_until": state.blocked_until,
            "strategy": state.rule.strategy.value
        }
        
        # Add strategy-specific information
        if state.rule.strategy == RateLimitStrategy.TOKEN_BUCKET:
            # Update tokens for current display
            time_passed = current_time - state.last_refill
            tokens_to_add = time_passed * (state.rule.max_requests / state.rule.window_seconds)
            current_tokens = min(state.rule.max_requests, state.tokens + tokens_to_add)
            
            status.update({
                "tokens_available": current_tokens,
                "tokens_max": state.rule.max_requests
            })
        
        elif state.rule.strategy == RateLimitStrategy.SLIDING_WINDOW:
            window_start = current_time - state.rule.window_seconds
            # Count requests in current window
            current_requests = sum(1 for req_time in state.requests if req_time >= window_start)
            
            status.update({
                "requests_in_window": current_requests,
                "requests_max": state.rule.max_requests,
                "window_seconds": state.rule.window_seconds
            })
        
        return status
    
    async def get_global_stats(self) -> Dict[str, Any]:
        """Get global rate limiting statistics."""
        active_keys = len(self._states)
        blocked_keys = sum(1 for state in self._states.values() if state.is_blocked())
        
        # Calculate success rate
        success_rate = 0.0
        if self._total_requests > 0:
            success_rate = ((self._total_requests - self._total_blocked) / self._total_requests) * 100
        
        return {
            "total_requests": self._total_requests,
            "total_blocked": self._total_blocked,
            "success_rate": success_rate,
            "active_keys": active_keys,
            "blocked_keys": blocked_keys,
            "rules_count": len(self._rules),
            "rules": list(self._rules.keys())
        }
    
    async def _cleanup_loop(self) -> None:
        """Background task to clean up old state entries."""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_old_states()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in rate limiter cleanup: {e}", exc_info=True)
    
    async def _cleanup_old_states(self) -> None:
        """Remove old and unused state entries."""
        current_time = time.time()
        keys_to_remove = []
        
        for state_key, state in self._states.items():
            # Remove if no recent activity and not blocked
            last_activity = state.last_refill
            if state.requests:
                last_activity = max(last_activity, max(state.requests))
            
            # Clean up if inactive for 2x the window duration
            cleanup_threshold = state.rule.window_seconds * 2
            
            if (current_time - last_activity > cleanup_threshold and 
                not state.is_blocked()):
                keys_to_remove.append(state_key)
        
        for key in keys_to_remove:
            del self._states[key]
        
        if keys_to_remove:
            self.logger.debug(f"Cleaned up {len(keys_to_remove)} old rate limit states")


# Decorator for automatic rate limiting
def rate_limit(rule_name: str, key_func: Optional[Callable] = None, cost: int = 1):
    """
    Decorator to apply rate limiting to functions.
    
    Args:
        rule_name: Name of the rate limiting rule
        key_func: Function to extract rate limit key from arguments
        cost: Cost of the operation
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            # Try to get rate limiter from first argument (usually self)
            rate_limiter = None
            if args and hasattr(args[0], 'rate_limiter'):
                rate_limiter = args[0].rate_limiter
            elif args and hasattr(args[0], 'bot') and hasattr(args[0].bot, 'rate_limiter'):
                rate_limiter = args[0].bot.rate_limiter
            
            if not rate_limiter:
                # No rate limiter available, just execute function
                return await func(*args, **kwargs)
            
            # Extract key
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                # Default key extraction
                key = "global"
                if args and hasattr(args[0], '__class__'):
                    key = f"{args[0].__class__.__name__}"
            
            # Check rate limit
            allowed, metadata = await rate_limiter.check_rate_limit(rule_name, key, cost)
            
            if not allowed:
                from utils.exceptions import RateLimitExceededError
                raise RateLimitExceededError(
                    f"Rate limit exceeded for {rule_name}",
                    metadata=metadata
                )
            
            return await func(*args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            # For sync functions, we can't easily apply async rate limiting
            # This would need to be handled differently in a real implementation
            return func(*args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Common rate limiting rules
COMMON_RULES = {
    "command_execution": RateLimitRule(
        name="command_execution",
        max_requests=10,
        window_seconds=60,
        strategy=RateLimitStrategy.SLIDING_WINDOW,
        cooldown_seconds=5
    ),
    "database_query": RateLimitRule(
        name="database_query",
        max_requests=100,
        window_seconds=60,
        strategy=RateLimitStrategy.TOKEN_BUCKET
    ),
    "discord_api": RateLimitRule(
        name="discord_api",
        max_requests=50,
        window_seconds=60,
        strategy=RateLimitStrategy.LEAKY_BUCKET,
        burst_allowance=10
    ),
    "notification_send": RateLimitRule(
        name="notification_send",
        max_requests=20,
        window_seconds=300,  # 5 minutes
        strategy=RateLimitStrategy.SLIDING_WINDOW
    ),
    "game_ping": RateLimitRule(
        name="game_ping",
        max_requests=5,
        window_seconds=300,  # 5 minutes
        strategy=RateLimitStrategy.FIXED_WINDOW,
        cooldown_seconds=60
    )
}