"""
Adaptive rate limiter to prevent server throttling and bans.
"""

import time
import random
import threading

from .logger import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    Adaptive rate limiter with randomized delays.
    Thread-safe for concurrent request handling.
    """

    def __init__(self, min_delay: float = 1.5, max_delay: float = 3.5):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._last_request_time: float = 0.0
        self._lock = threading.Lock()
        self._request_count = 0

    def wait(self) -> None:
        """Waits necessary duration before allowing the next HTTP request."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time

            delay = random.uniform(self.min_delay, self.max_delay)

            # Insert an extended pause every 50 requests
            if self._request_count > 0 and self._request_count % 50 == 0:
                extra = random.uniform(3.0, 7.0)
                logger.debug(f"Extended pause ({extra:.1f}s) after {self._request_count} requests")
                time.sleep(extra)

            remaining = delay - elapsed
            if remaining > 0:
                time.sleep(remaining)

            self._last_request_time = time.monotonic()
            self._request_count += 1

    @property
    def request_count(self) -> int:
        return self._request_count
