"""
Unit tests for ProxyManager, FileCache two-tier memory caching, and AsyncUFCStatsScraper.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.scraper import ProxyManager, AsyncUFCStatsScraper
from src.storage.cache import FileCache


def test_proxy_manager_rotation(tmp_path):
    proxies = ["http://1.1.1.1:8080", "http://2.2.2.2:8080"]
    pm = ProxyManager(proxies)

    assert pm.get_proxy() == "http://1.1.1.1:8080"
    assert pm.get_proxy() == "http://2.2.2.2:8080"
    assert pm.get_proxy() == "http://1.1.1.1:8080"

    proxy_file = tmp_path / "proxies.txt"
    proxy_file.write_text("# comment\nhttp://3.3.3.3:8080\n", encoding="utf-8")

    pm_file = ProxyManager.from_file(proxy_file)
    assert pm_file.get_proxy() == "http://3.3.3.3:8080"


def test_file_cache_memory_layer(tmp_path):
    cache = FileCache(cache_dir=str(tmp_path / "cache"), max_memory_items=5)
    url = "http://www.ufcstats.com/test-page"
    html = "<html><body>Test</body></html>"

    cache.set(url, html)

    # First get hits RAM memory cache
    retrieved1 = cache.get(url)
    assert retrieved1 == html

    # Stat check
    stats = cache.stats()
    assert stats["hits"] >= 1

    cache.clear()
    assert cache.get(url) is None


def test_async_scraper_cache_hit(tmp_path):
    cache = FileCache(cache_dir=str(tmp_path / "cache"))
    url = "http://www.ufcstats.com/event-details/12345"
    html = "<html><body>Cached Event</body></html>"
    cache.set(url, html)

    async def _run():
        async with AsyncUFCStatsScraper(cache=cache) as scraper:
            soup = await scraper.get_soup(url)
            assert soup is not None
            assert "Cached Event" in soup.get_text()

    asyncio.run(_run())
