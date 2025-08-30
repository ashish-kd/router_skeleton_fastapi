import time
import asyncio
import logging
import structlog
from typing import Dict, Callable, Any, Optional, List
from datetime import datetime, timedelta
from aiocache import Cache
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError
)
from app.metrics import RETRY_ATTEMPTS, CIRCUIT_BREAKER_TRIPS, RATE_LIMIT_HITS

# Configure structured logging
logger = structlog.get_logger()

# Cache for routing rules and responses
cache = Cache(namespace="router")

# Rate limiting implementation
class RateLimiter:
    def __init__(self, limit_per_second: int = 100, window_size: int = 60):
        self.limit_per_second = limit_per_second
        self.window_size = window_size
        self.windows: Dict[str, Dict[int, int]] = {}
    
    async def check_rate_limit(self, sender_id: str) -> bool:
        """
        Check if sender_id has exceeded rate limit
        Returns True if within limit, False if rate limited
        """
        current_time = int(time.time())
        window_start = current_time - self.window_size
        
        # Initialize window for this sender if not exists
        if sender_id not in self.windows:
            self.windows[sender_id] = {}
            
        # Clean old timestamps
        self.windows[sender_id] = {ts: count for ts, count in self.windows[sender_id].items() 
                                  if ts >= window_start}
        
        # Count total requests in window
        total_requests = sum(self.windows[sender_id].values())
        
        # Check if limit exceeded
        if total_requests >= self.limit_per_second * self.window_size:
            RATE_LIMIT_HITS.labels(sender_id=sender_id).inc()
            return False
            
        # Update counter
        if current_time in self.windows[sender_id]:
            self.windows[sender_id][current_time] += 1
        else:
            self.windows[sender_id][current_time] = 1
            
        return True

# Global rate limiter instance
rate_limiter = RateLimiter()

# Circuit breaker implementation
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_time: int = 30):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failure_counts: Dict[str, int] = {}
        self.circuit_open_until: Dict[str, datetime] = {}
    
    def is_circuit_open(self, agent: str) -> bool:
        """Check if circuit is open (breaker tripped)"""
        if agent in self.circuit_open_until:
            if datetime.now() < self.circuit_open_until[agent]:
                return True
            else:
                # Reset after recovery time
                del self.circuit_open_until[agent]
                self.failure_counts[agent] = 0
        return False
    
    def record_success(self, agent: str) -> None:
        """Record successful call to agent"""
        self.failure_counts[agent] = 0
    
    def record_failure(self, agent: str) -> bool:
        """
        Record failed call to agent
        Returns True if circuit was opened as a result
        """
        if agent not in self.failure_counts:
            self.failure_counts[agent] = 0
            
        self.failure_counts[agent] += 1
        
        if self.failure_counts[agent] >= self.failure_threshold:
            self.circuit_open_until[agent] = datetime.now() + timedelta(seconds=self.recovery_time)
            CIRCUIT_BREAKER_TRIPS.labels(agent=agent).inc()
            logger.warning("Circuit breaker tripped", agent=agent, 
                         until=self.circuit_open_until[agent].isoformat())
            return True
        return False

# Global circuit breaker instance
circuit_breaker = CircuitBreaker()

# Retry decorator with exponential backoff
def with_retry(max_attempts: int = 3, min_wait_ms: int = 100, max_wait_ms: int = 1000):
    """Decorator for functions that should be retried with exponential backoff"""
    def decorator(func):
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=min_wait_ms/1000, max=max_wait_ms/1000),
            retry=retry_if_exception_type((Exception,)),
            reraise=True
        )
        async def wrapper(*args, **kwargs):
            agent = kwargs.get('agent', 'unknown')
            try:
                RETRY_ATTEMPTS.labels(agent=agent, status="attempt").inc()
                result = await func(*args, **kwargs)
                RETRY_ATTEMPTS.labels(agent=agent, status="success").inc()
                return result
            except Exception as e:
                RETRY_ATTEMPTS.labels(agent=agent, status="failure").inc()
                logger.warning("Retry attempt failed", 
                             agent=agent, 
                             error=str(e),
                             retry_attempt=True)
                raise
        return wrapper
    return decorator

# Parallel execution with bounded concurrency
async def execute_parallel(
    func: Callable, 
    items: List[Any], 
    max_concurrency: int = 10,
    timeout: float = 5.0
) -> List[Any]:
    """Execute a function on multiple items with bounded concurrency"""
    semaphore = asyncio.Semaphore(max_concurrency)
    
    async def _wrapped_func(item):
        async with semaphore:
            try:
                return await asyncio.wait_for(func(item), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning("Function execution timed out", item=str(item))
                return None
            except Exception as e:
                logger.error("Error in parallel execution", error=str(e))
                return None
    
    return await asyncio.gather(*(_wrapped_func(item) for item in items), return_exceptions=False)

# Generate trace ID 
def generate_trace_id() -> str:
    """Generate a unique trace ID for request tracing"""
    import uuid
    return uuid.uuid4().hex
