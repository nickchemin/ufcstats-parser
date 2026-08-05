"""
Parser for completed and upcoming UFC events listings.

Target URLs:
  - Completed: http://www.ufcstats.com/statistics/events/completed?page=all
  - Upcoming:  http://www.ufcstats.com/statistics/events/upcoming
"""

import re
from datetime import datetime, date as date_type
from typing import List, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..storage.models import Event
from ..utils.logger import get_logger

logger = get_logger(__name__)

EVENTS_URL = "/statistics/events/completed?page=all"
UPCOMING_URL = "/statistics/events/upcoming"


def _extract_event_id(url: str) -> str:
    """Extracts event ID from URL string."""
    path = urlparse(url).path
    return path.rstrip("/").split("/")[-1]


def _parse_date(text: str) -> Optional[date_type]:
    """Parses date string 'August 01, 2026' -> date object."""
    text = text.strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_events_page(soup: BeautifulSoup) -> List[Event]:
    """
    Parses completed or upcoming events list page and extracts Event objects.

    Args:
        soup: BeautifulSoup parsed HTML object.

    Returns:
        List of Event objects.
    """
    events: List[Event] = []

    table = soup.find("table", class_="b-statistics__table-events")
    if not table:
        logger.warning("Events table 'b-statistics__table-events' not found")
        return events

    rows = table.find_all("tr")

    for row in rows:
        link = row.find("a", href=re.compile(r"event-details"))
        if not link:
            continue

        url = link.get("href", "").strip()
        if not url:
            continue

        event_id = _extract_event_id(url)
        name = link.get_text(strip=True)

        date_span = row.find("span", class_="b-statistics__date")
        event_date = _parse_date(date_span.get_text()) if date_span else None

        cells = row.find_all("td")
        location = None
        if len(cells) >= 2:
            location = cells[1].get_text(strip=True) or None

        events.append(
            Event(
                event_id=event_id,
                url=url,
                name=name,
                event_date=event_date,
                location=location,
            )
        )

    logger.info(f"Found events: {len(events)}")
    return events


def parse_upcoming_events_page(soup: BeautifulSoup) -> List[Event]:
    """Alias for parse_events_page for upcoming events."""
    return parse_events_page(soup)
