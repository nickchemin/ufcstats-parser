"""
Parser for single event page containing fight listings.

Target URL: http://www.ufcstats.com/event-details/<event_id>
"""

import re
from typing import List, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..storage.models import Fight
from ..utils.logger import get_logger

logger = get_logger(__name__)


def _extract_id_from_url(url: str) -> Optional[str]:
    """Extracts entity ID from last path segment of URL."""
    if not url:
        return None
    path = urlparse(url).path
    return path.rstrip("/").split("/")[-1] or None


def parse_event_fights(soup: BeautifulSoup, event_id: str) -> List[Fight]:
    """
    Parses event page and returns list of Fight objects.

    Args:
        soup: BeautifulSoup object of event page.
        event_id: Parent event ID string.

    Returns:
        List of Fight objects.
    """
    fights: List[Fight] = []

    table = soup.find("table", class_=re.compile(r"js-fight-table"))
    if not table:
        logger.warning(f"[{event_id}] Fights table 'js-fight-table' not found")
        return fights

    rows = table.find_all("tr", class_=re.compile(r"js-fight-details-click"))

    for i, row in enumerate(rows):
        try:
            fight = _parse_fight_row(row, event_id, is_main_event=(i == 0))
            if fight:
                fights.append(fight)
        except Exception as e:
            logger.warning(f"[{event_id}] Error parsing row #{i}: {e}")

    logger.info(f"[{event_id}] Found fights: {len(fights)}")
    return fights


def _parse_fight_row(row, event_id: str, is_main_event: bool = False) -> Optional[Fight]:
    """Parses a single fight row from event table."""
    fight_url = row.get("data-link", "").strip()
    if not fight_url or "fight-details" not in fight_url:
        return None

    fight_id = _extract_id_from_url(fight_url)
    if not fight_id:
        return None

    cols = row.find_all("td", recursive=False)
    if not cols:
        cols = row.find_all("td")

    def col_texts(col_idx: int) -> List[str]:
        if col_idx >= len(cols):
            return []
        return [p.get_text(strip=True) for p in cols[col_idx].find_all("p")]

    def col_text(col_idx: int) -> str:
        texts = col_texts(col_idx)
        return texts[0] if texts else ""

    # Column 0: W/L flags
    wl_texts = []
    if cols:
        flags = cols[0].find_all("a", class_="b-flag")
        wl_texts = [f.get_text(strip=True).lower() for f in flags]

    # Column 1: Fighters
    fighter1_name = fighter2_name = None
    fighter1_id = fighter2_id = None
    winner_id = None
    outcome = None

    if len(cols) > 1:
        fighter_col = cols[1]
        fighter_links = fighter_col.find_all("a", href=re.compile(r"fighter-details"))

        if len(fighter_links) >= 1:
            fighter1_id = _extract_id_from_url(fighter_links[0].get("href", ""))
            fighter1_name = fighter_links[0].get_text(strip=True)
        if len(fighter_links) >= 2:
            fighter2_id = _extract_id_from_url(fighter_links[1].get("href", ""))
            fighter2_name = fighter_links[1].get_text(strip=True)

    if "win" in wl_texts:
        idx = wl_texts.index("win")
        winner_id = fighter1_id if idx == 0 else fighter2_id
        outcome = "W"
    elif len(wl_texts) >= 1 and wl_texts[0] in ("draw", "nc"):
        outcome = wl_texts[0].upper()

    # Column 6: Weight Class
    weight_class = col_text(6) or None

    # Column 7: Method
    method_texts = col_texts(7)
    method = method_texts[0] if method_texts else None
    method_detail = method_texts[1] if len(method_texts) > 1 else None

    # Column 8: Round
    round_val = None
    round_text = col_text(8)
    if round_text.isdigit():
        round_val = int(round_text)

    # Column 9: Time
    time_val = col_text(9) or None

    title_fight = bool(weight_class and re.search(r"title|championship", weight_class, re.IGNORECASE))

    return Fight(
        fight_id=fight_id,
        url=fight_url,
        event_id=event_id,
        fighter1_id=fighter1_id,
        fighter1_name=fighter1_name,
        fighter2_id=fighter2_id,
        fighter2_name=fighter2_name,
        winner_id=winner_id,
        outcome=outcome,
        method=method,
        method_detail=method_detail,
        round=round_val,
        time=time_val,
        weight_class=weight_class,
        title_fight=title_fight,
        is_main_event=is_main_event,
    )
