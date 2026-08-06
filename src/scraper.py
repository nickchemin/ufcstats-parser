"""
HTTP client for ufcstats.com featuring automated PoW challenge solving.

ufcstats.com employs a custom SHA-256 proof-of-work challenge:
  1. GET page -> HTML containing nonce and target difficulty
  2. SHA-256 PoW: find n such that sha256(nonce:n) starts with required '0' prefix
  3. POST /__c {nonce, n} -> receive _fmc cookie (valid for 7 days)
  4. Subsequent GET requests with _fmc cookie -> access full HTML content
"""

import asyncio
import hashlib
import logging
from pathlib import Path
import random
import re
import time
from typing import List, Optional, Union

import httpx
import requests
from bs4 import BeautifulSoup

from .utils.logger import get_logger
from .utils.rate_limiter import RateLimiter

logger = get_logger(__name__)

BASE_URL = "http://www.ufcstats.com"
CHALLENGE_ENDPOINT = "/__c"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]


class ProxyManager:
    """Manages a pool of HTTP/HTTPS proxies for IP rotation."""

    def __init__(self, proxies: Optional[List[str]] = None):
        self.proxies = [p.strip() for p in proxies if p.strip()] if proxies else []
        self._index = 0

    def get_proxy(self) -> Optional[str]:
        if not self.proxies:
            return None
        proxy = self.proxies[self._index % len(self.proxies)]
        self._index += 1
        return proxy

    @classmethod
    def from_file(cls, filepath: Union[str, Path]) -> "ProxyManager":
        path = Path(filepath)
        if not path.exists():
            logger.warning(f"Proxy file '{filepath}' not found")
            return cls([])
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
        valid = [l for l in lines if l and not l.startswith("#")]
        logger.info(f"Loaded {len(valid)} proxies from {filepath}")
        return cls(valid)


def _is_challenge_page(html: str) -> bool:
    """Checks whether the HTML response represents a PoW challenge page."""
    return "Checking your browser" in html or "/__c" in html


def _solve_pow(html: str) -> Optional[tuple]:
    """
    Extracts nonce and solves the SHA-256 proof-of-work challenge.

    Returns:
        (nonce, n) tuple or None if challenge parameters are missing.
    """
    nonce_match = re.search(r'nonce="([^"]+)"', html)
    if not nonce_match:
        logger.warning("PoW: nonce not found in HTML response")
        return None

    nonce = nonce_match.group(1)

    diff_match = re.search(r'target=new Array\((\d+)\+1\)', html)
    difficulty = int(diff_match.group(1)) if diff_match else 2
    target_prefix = "0" * difficulty

    logger.debug(f"PoW: nonce={nonce}, difficulty={difficulty}")

    n = 0
    while True:
        digest = hashlib.sha256(f"{nonce}:{n}".encode()).hexdigest()
        if digest.startswith(target_prefix):
            logger.debug(f"PoW solved: n={n}, hash={digest[:16]}...")
            return nonce, n
        n += 1
        if n > 10_000_000:
            logger.error(f"PoW: failed to solve within 10M iterations (difficulty={difficulty})")
            return None


class UFCStatsScraper:
    """
    HTTP scraper client for ufcstats.com providing:
    - Custom SHA-256 PoW challenge resolution & _fmc cookie handling
    - Exponential backoff retry logic
    - Rate limiting
    - Disk cache integration
    """

    def __init__(
        self,
        min_delay: float = 1.5,
        max_delay: float = 3.5,
        max_retries: int = 3,
        cache=None,
        proxy_manager: Optional[ProxyManager] = None,
    ):
        self.rate_limiter = RateLimiter(min_delay=min_delay, max_delay=max_delay)
        self.max_retries = max_retries
        self.cache = cache
        self.proxy_manager = proxy_manager
        self._session = self._create_session()
        self._challenge_solved = False

    def _create_session(self) -> requests.Session:
        """Initializes a requests session with standard browser headers and proxy."""
        s = requests.Session()
        s.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": BASE_URL,
        })
        if self.proxy_manager:
            proxy = self.proxy_manager.get_proxy()
            if proxy:
                s.proxies.update({"http": proxy, "https": proxy})
                logger.info(f"Using proxy for session: {proxy}")
        if self.cache:
            cached_cookie = self.cache.get_cookie("_fmc")
            if cached_cookie:
                s.cookies.set("_fmc", cached_cookie, domain="www.ufcstats.com")
                logger.info("Loaded cached _fmc cookie for session")
        return s

    def _solve_challenge(self, url: str) -> bool:
        """
        Solves the PoW challenge for ufcstats.com:
        GET url -> parse nonce -> solve SHA-256 -> POST /__c -> obtain _fmc cookie

        Returns:
            True if challenge was successfully passed.
        """
        logger.info("Solving ufcstats.com PoW challenge...")
        try:
            r = self._session.get(url, timeout=20)
            html = r.text

            if not _is_challenge_page(html):
                logger.debug("PoW: page accessible directly, challenge not required")
                self._challenge_solved = True
                return True

            result = _solve_pow(html)
            if not result:
                return False

            nonce, n = result

            post_url = BASE_URL + CHALLENGE_ENDPOINT
            r2 = self._session.post(
                post_url,
                data=f"nonce={nonce}&n={n}",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": url,
                    "Origin": BASE_URL,
                },
                timeout=15,
                allow_redirects=False,
            )

            if r2.status_code in (204, 200, 302):
                cookie = self._session.cookies.get("_fmc")
                if cookie:
                    logger.info(f"PoW passed! Obtained _fmc cookie ({r2.status_code})")
                    if self.cache:
                        self.cache.set_cookie("_fmc", cookie)
                    self._challenge_solved = True
                    return True
                else:
                    logger.warning(f"PoW POST returned {r2.status_code} but no _fmc cookie was set")
                    return False
            else:
                logger.warning(f"PoW POST unexpected status code: {r2.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error solving PoW challenge: {e}")
            return False

    def _ensure_challenge_solved(self) -> bool:
        """Ensures valid session authentication before executing requests."""
        if self._challenge_solved:
            return True
        return self._solve_challenge(BASE_URL + "/statistics/events/completed")

    def get(self, url: str, use_cache: bool = True) -> Optional[BeautifulSoup]:
        """
        Fetches HTML from URL and returns parsed BeautifulSoup object.

        Args:
            url: Target URL string.
            use_cache: If True, checks disk cache before fetching.

        Returns:
            BeautifulSoup object or None on failure.
        """
        if use_cache and self.cache:
            cached = self.cache.get(url)
            if cached is not None:
                logger.debug(f"[cache] {url}")
                return BeautifulSoup(cached, "lxml")

        if not self._ensure_challenge_solved():
            logger.error("Failed to solve PoW challenge")
            return None

        self.rate_limiter.wait()

        for attempt in range(1, self.max_retries + 1):
            try:
                if self.proxy_manager:
                    proxy = self.proxy_manager.get_proxy()
                    if proxy:
                        self._session.proxies.update({"http": proxy, "https": proxy})

                logger.debug(f"[GET] {url} (attempt {attempt}/{self.max_retries})")
                response = self._session.get(url, timeout=30)
                response.raise_for_status()
                html = response.text

                if _is_challenge_page(html):
                    logger.warning(f"[attempt {attempt}] Received challenge page again, re-solving...")
                    self._challenge_solved = False
                    if self._solve_challenge(url):
                        self.rate_limiter.wait()
                        response = self._session.get(url, timeout=30)
                        html = response.text
                        if _is_challenge_page(html):
                            raise ValueError("Challenge failed after second attempt")
                    else:
                        raise ValueError("Failed to re-solve challenge")

                if use_cache and self.cache:
                    self.cache.set(url, html)

                if random.random() < 0.15:
                    self._session.headers.update({"User-Agent": random.choice(USER_AGENTS)})

                return BeautifulSoup(html, "lxml")

            except Exception as exc:
                logger.warning(f"[error] attempt {attempt}/{self.max_retries}: {exc}")
                if attempt < self.max_retries:
                    wait = 2 ** attempt + random.uniform(0, 1)
                    logger.info(f"Waiting {wait:.1f}s before retrying...")
                    time.sleep(wait)
                else:
                    logger.error(f"[failed] {url} after {self.max_retries} attempts")
                    return None

    def get_soup(self, path: str, use_cache: bool = True) -> Optional[BeautifulSoup]:
        """Fetches page by relative path from BASE_URL."""
        url = f"{BASE_URL}{path}" if path.startswith("/") else path
        return self.get(url, use_cache=use_cache)

    def close(self):
        """Closes HTTP session."""
        self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class AsyncUFCStatsScraper:
    """
    Asynchronous HTTP scraper client using httpx and asyncio.
    Features:
    - Parallel batch fetching with asyncio.Semaphore concurrency control
    - Asynchronous PoW challenge solver
    - Integration with two-tier FileCache
    - Proxy rotation support via ProxyManager
    """

    def __init__(
        self,
        concurrency: int = 5,
        min_delay: float = 0.2,
        max_delay: float = 0.8,
        max_retries: int = 3,
        cache=None,
        proxy_manager: Optional[ProxyManager] = None,
    ):
        self.semaphore = asyncio.Semaphore(concurrency)
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.cache = cache
        self.proxy_manager = proxy_manager
        self._challenge_solved = False
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            proxy = self.proxy_manager.get_proxy() if self.proxy_manager else None
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Referer": BASE_URL,
            }
            kwargs = {
                "headers": headers,
                "timeout": httpx.Timeout(30.0),
                "follow_redirects": True,
            }
            if proxy:
                kwargs["proxy"] = proxy
                logger.info(f"Async client configured with proxy: {proxy}")
            self._client = httpx.AsyncClient(**kwargs)
            if self.cache:
                cached_cookie = self.cache.get_cookie("_fmc")
                if cached_cookie:
                    self._client.cookies.set("_fmc", cached_cookie)
                    logger.info("Loaded cached _fmc cookie for async client")
        return self._client

    async def _solve_challenge(self, url: str) -> bool:
        logger.info("Solving ufcstats.com PoW challenge (async)...")
        client = await self._get_client()
        try:
            r = await client.get(url)
            html = r.text

            if not _is_challenge_page(html):
                self._challenge_solved = True
                return True

            result = _solve_pow(html)
            if not result:
                return False

            nonce, n = result
            post_url = BASE_URL + CHALLENGE_ENDPOINT
            r2 = await client.post(
                post_url,
                data={"nonce": nonce, "n": str(n)},
                headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": url},
            )

            if r2.status_code in (204, 200, 302):
                cookie = client.cookies.get("_fmc")
                if cookie and self.cache:
                    self.cache.set_cookie("_fmc", cookie)
                logger.info("Async PoW passed! Obtained _fmc cookie")
                self._challenge_solved = True
                return True
            return False
        except Exception as e:
            logger.error(f"Error solving async PoW: {e}")
            return False

    async def _ensure_challenge_solved(self) -> bool:
        if self._challenge_solved:
            return True
        return await self._solve_challenge(BASE_URL + "/statistics/events/completed")

    async def get(self, url: str, use_cache: bool = True) -> Optional[BeautifulSoup]:
        if use_cache and self.cache:
            cached = self.cache.get(url)
            if cached is not None:
                return BeautifulSoup(cached, "lxml")

        async with self.semaphore:
            if not await self._ensure_challenge_solved():
                return None

            delay = random.uniform(self.min_delay, self.max_delay)
            await asyncio.sleep(delay)

            client = await self._get_client()

            for attempt in range(1, self.max_retries + 1):
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    html = r.text

                    if _is_challenge_page(html):
                        self._challenge_solved = False
                        if await self._solve_challenge(url):
                            r = await client.get(url)
                            html = r.text
                        else:
                            raise ValueError("Failed to re-solve challenge in async mode")

                    if use_cache and self.cache:
                        self.cache.set(url, html)

                    return BeautifulSoup(html, "lxml")

                except Exception as exc:
                    logger.warning(f"[async error] {url} (attempt {attempt}/{self.max_retries}): {exc}")
                    if attempt < self.max_retries:
                        if self.proxy_manager and self._client:
                            await self._client.aclose()
                            self._client = None
                        await asyncio.sleep(2 ** attempt)
                    else:
                        return None

    async def get_soup(self, path: str, use_cache: bool = True) -> Optional[BeautifulSoup]:
        url = f"{BASE_URL}{path}" if path.startswith("/") else path
        return await self.get(url, use_cache=use_cache)

    async def get_soups_batch(self, paths: List[str], use_cache: bool = True) -> List[Optional[BeautifulSoup]]:
        """Fetches multiple URLs concurrently using asyncio.gather with exception safety."""
        tasks = [self.get_soup(path, use_cache=use_cache) for path in paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        cleaned = []
        for res in results:
            if isinstance(res, Exception):
                logger.warning(f"Batch request encountered unhandled exception: {res}")
                cleaned.append(None)
            else:
                cleaned.append(res)
        return cleaned

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
