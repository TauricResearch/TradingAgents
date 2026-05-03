import logging
import random
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window rate limiter.

    Limits callers to max_calls within any rolling period-second window.
    When the limit is reached, acquire() blocks until a slot opens.
    """

    def __init__(self, max_calls: int, period: float = 60.0):
        self.max_calls = max_calls
        self.period = period
        self._lock = threading.Lock()
        self._calls: deque = deque()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                # Evict timestamps that have left the rolling window
                while self._calls and now - self._calls[0] >= self.period:
                    self._calls.popleft()

                if len(self._calls) < self.max_calls:
                    self._calls.append(now)
                    return

                # Calculate how long until the oldest call exits the window
                wait = self.period - (now - self._calls[0])

            # Release the lock while sleeping so other threads can check too
            if wait > 0:
                logger.info(
                    "Rate limit reached (%d req/%.0fs), waiting %.1fs for next slot",
                    self.max_calls,
                    self.period,
                    wait,
                )
                time.sleep(wait)
            # Re-check after waking — another thread may have taken the slot


def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True if the exception represents an HTTP 429 rate-limit."""
    try:
        import openai
        if isinstance(exc, openai.RateLimitError):
            return True
    except ImportError:
        pass
    try:
        import anthropic
        if isinstance(exc, anthropic.RateLimitError):
            return True
    except ImportError:
        pass
    try:
        from google.api_core.exceptions import ResourceExhausted
        if isinstance(exc, ResourceExhausted):
            return True
    except ImportError:
        pass
    # Generic fallback for any provider that surfaces a status code
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    return status_code == 429


def llm_retry(func, *args, max_retries: int = 5, base_delay: float = 10.0, max_delay: float = 60.0, **kwargs):
    """Call func(*args, **kwargs) with exponential backoff and full jitter on 429 errors.

    Uses full jitter: delay = uniform(0, min(max_delay, base_delay * 2^attempt)).
    Non-rate-limit exceptions propagate immediately.
    """
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            if not _is_rate_limit_error(exc) or attempt == max_retries:
                raise
            cap = min(max_delay, base_delay * (2 ** attempt))
            delay = random.uniform(0, cap)
            logger.warning(
                "LLM rate limited (429), retrying in %.1fs (attempt %d/%d)",
                delay,
                attempt + 1,
                max_retries,
            )
            time.sleep(delay)
