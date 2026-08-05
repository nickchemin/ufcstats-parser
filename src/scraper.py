"""
HTTP client for ufcstats.com featuring automated PoW challenge solving.

ufcstats.com employs a custom SHA-256 proof-of-work challenge:
  1. GET page -> HTML containing nonce and target difficulty
  2. SHA-256 PoW: find n such that sha256(nonce:n) starts with required '0' prefix
  3. POST /__c {nonce, n} -> receive _fmc cookie (valid for 7 days)
  4. Subsequent GET requests with _fmc cookie -> access full HTML content
"""

import hashlib
import re
import time
import random
import logging
from typing import Optional

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
    ):
        self.rate_limiter = RateLimiter(min_delay=min_delay, max_delay=max_delay)
        self.max_retries = max_retries
        self.cache = cache
        self._session = self._create_session()
        self._challenge_solved = False

    def _create_session(self) -> requests.Session:
        """Initializes a requests session with standard browser headers."""
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
