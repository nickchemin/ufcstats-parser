"""
File-based HTML response cache.

Saves HTML pages on disk indexed by URL hash.
Supports configurable TTLs and cache management.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Optional

from ..utils.logger import get_logger

logger = get_logger(__name__)

# Default TTLs (in seconds)
TTL_EVENTS_LIST = 60 * 60 * 6        # 6 hours
TTL_EVENT_DETAIL = 60 * 60 * 24 * 7  # 7 days
TTL_FIGHT_DETAIL = 60 * 60 * 24 * 30 # 30 days
TTL_FIGHTER = 60 * 60 * 24 * 7       # 7 days


def _url_ttl(url: str) -> int:
    """Determines appropriate TTL based on URL type."""
    if "events/completed" in url or "statistics/fighters" in url:
        return TTL_EVENTS_LIST
    if "event-details" in url:
        return TTL_EVENT_DETAIL
    if "fight-details" in url:
        return TTL_FIGHT_DETAIL
    if "fighter-details" in url:
        return TTL_FIGHTER
    return TTL_EVENT_DETAIL


class FileCache:
    """
    Two-tier cache manager saving HTML content in RAM memory and disk alongside metadata.
    """

    def __init__(self, cache_dir: str = "cache", max_memory_items: int = 500):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache = {}
        self._max_memory_items = max_memory_items
        self._hits = 0
        self._misses = 0

    def _key(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def _html_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.html"

    def _meta_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.meta"

    def get(self, url: str) -> Optional[str]:
        """
        Retrieves cached HTML content or None if missing/expired.
        Checks in-memory cache first, then disk cache.
        """
        key = self._key(url)

        if key in self._memory_cache:
            html, exp_time = self._memory_cache[key]
            if time.time() < exp_time:
                self._hits += 1
                return html
            else:
                del self._memory_cache[key]

        html_path = self._html_path(key)
        meta_path = self._meta_path(key)

        if not html_path.exists() or not meta_path.exists():
            self._misses += 1
            return None

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            age = time.time() - meta["timestamp"]
            ttl = meta.get("ttl", TTL_EVENT_DETAIL)

            if age > ttl:
                logger.debug(f"[cache expired] {url} ({age/3600:.1f}h > {ttl/3600:.1f}h)")
                self._misses += 1
                return None

            html = html_path.read_text(encoding="utf-8")
            if len(self._memory_cache) < self._max_memory_items:
                self._memory_cache[key] = (html, meta["timestamp"] + ttl)

            self._hits += 1
            return html

        except Exception as e:
            logger.warning(f"[cache read error] {url}: {e}")
            self._misses += 1
            return None

    def set(self, url: str, html: str) -> None:
        """Saves HTML string and metadata into memory and disk cache."""
        key = self._key(url)
        ttl = _url_ttl(url)

        if len(self._memory_cache) >= self._max_memory_items:
            self._memory_cache.pop(next(iter(self._memory_cache)))
        self._memory_cache[key] = (html, time.time() + ttl)

        try:
            self._html_path(key).write_text(html, encoding="utf-8")
            meta = {"url": url, "timestamp": time.time(), "ttl": ttl}
            self._meta_path(key).write_text(
                json.dumps(meta, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"[cache write error] {url}: {e}")

    def exists(self, url: str) -> bool:
        """Checks if a valid cache entry exists for the given URL."""
        return self.get(url) is not None

    def invalidate(self, url: str) -> None:
        """Deletes cache entry for a specific URL from memory and disk."""
        key = self._key(url)
        self._memory_cache.pop(key, None)
        for path in [self._html_path(key), self._meta_path(key)]:
            if path.exists():
                path.unlink()

    def clear(self) -> int:
        """Clears all cached files and memory entries. Returns number of removed files."""
        self._memory_cache.clear()
        count = 0
        for f in self.cache_dir.glob("*"):
            f.unlink()
            count += 1
        logger.info(f"Cache cleared: {count} files removed")
        return count

    def stats(self) -> dict:
        """Returns cache usage statistics."""
        html_files = list(self.cache_dir.glob("*.html"))
        total_size = sum(f.stat().st_size for f in html_files)
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0

        return {
            "files": len(html_files),
            "size_mb": round(total_size / 1024 / 1024, 2),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(hit_rate, 1),
        }
