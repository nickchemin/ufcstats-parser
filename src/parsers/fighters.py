"""
Parser for fighter listings and detailed profile pages.

Target URLs:
  - List: http://www.ufcstats.com/statistics/fighters?char=<letter>&page=all
  - Profile: http://www.ufcstats.com/fighter-details/<fighter_id>
"""

import re
import string
from typing import List, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..storage.models import Fighter
from ..utils.logger import get_logger

logger = get_logger(__name__)

FIGHTERS_LIST_URL = "/statistics/fighters?char={letter}&page=all"
ALPHABET = string.ascii_lowercase  # a-z


def _extract_fighter_id(url: str) -> str:
    """Extracts fighter ID from profile URL."""
    path = urlparse(url).path
    return path.rstrip("/").split("/")[-1]


def _inches_to_cm(text: str) -> Optional[float]:
    """Converts feet/inches string format '6\' 2"' to cm (187.96)."""
    text = text.strip().replace('"', "").replace("\u2019", "'")
    match = re.match(r"(\d+)'\s*(\d+)?", text)
    if not match:
        return None
    feet = int(match.group(1))
    inches = int(match.group(2)) if match.group(2) else 0
    return round((feet * 12 + inches) * 2.54, 1)


def _lbs_to_kg(text: str) -> Optional[float]:
    """Converts weight string format '155 lbs.' to kg (70.31)."""
    text = text.strip().lower().replace("lbs.", "").replace("lbs", "").strip()
    try:
        return round(float(text) * 0.453592, 1)
    except ValueError:
        return None


def _parse_pct(text: str) -> Optional[float]:
    """Parses percentage string '58%' to float (58.0)."""
    text = text.strip().replace("%", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def _parse_float(text: str) -> Optional[float]:
    text = text.strip()
    if not text or text in ("--", "---"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_fighters_list(soup: BeautifulSoup) -> List[dict]:
    """
    Parses fighter listing page for a specific alphabet character.

    Returns:
        List of dicts containing basic fighter info: {fighter_id, url, first_name, last_name}.
    """
    fighters = []

    table = soup.find("table", class_=re.compile(r"b-statistics__table\b"))
    if not table:
        logger.warning("Fighters listing table not found")
        return fighters

    tbody = table.find("tbody")
    if not tbody:
        return fighters

    rows = tbody.find_all("tr", class_="b-statistics__table-row")
    for row in rows:
        cells = row.find_all("td")
        if not cells:
            continue

        first_link = cells[0].find("a") if cells else None
        if not first_link:
            continue

        url = first_link.get("href", "").strip()
        if not url:
            continue

        fighter_id = _extract_fighter_id(url)
        first_name = cells[0].get_text(strip=True)
        last_name = cells[1].get_text(strip=True) if len(cells) > 1 else ""

        fighters.append(
            {
                "fighter_id": fighter_id,
                "url": url,
                "first_name": first_name,
                "last_name": last_name,
            }
        )

    return fighters


def parse_fighter_profile(soup: BeautifulSoup, fighter_id: str, url: str) -> Optional[Fighter]:
    """
    Parses detailed fighter profile page.

    Args:
        soup: BeautifulSoup object of profile page.
        fighter_id: Fighter ID string.
        url: Profile URL.

    Returns:
        Fighter object populated with profile and career stats.
    """
    try:
        name_el = soup.find("span", class_="b-content__title-highlight")
        full_name = name_el.get_text(strip=True) if name_el else ""
        name_parts = full_name.split(None, 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        nickname_el = soup.find("p", class_="b-content__Nickname")
        nickname = nickname_el.get_text(strip=True).strip('"') if nickname_el else None

        stats_map = {}
        list_items = soup.find_all("li", class_="b-list__box-list-item")
        for item in list_items:
            title_el = item.find("i", class_="b-list__box-item-title")
            if not title_el:
                continue
            key = title_el.get_text(strip=True).rstrip(":").strip().lower()
            value = item.get_text(strip=True).replace(title_el.get_text(strip=True), "").strip()
            stats_map[key] = value

        height_cm = _inches_to_cm(stats_map.get("height", ""))
        weight_kg = _lbs_to_kg(stats_map.get("weight", ""))
        reach_text = stats_map.get("reach", "").replace('"', "").strip()
        reach_cm = round(float(reach_text) * 2.54, 1) if reach_text and reach_text not in ("--", "---") else None
        stance = stats_map.get("stance") or None
        dob_text = stats_map.get("dob", "")
        dob = _parse_date(dob_text)

        wins = losses = draws = no_contests = 0
        record_el = soup.find("span", class_="b-content__title-record")
        if record_el:
            record_text = record_el.get_text(strip=True)
            match = re.search(r"(\d+)-(\d+)-(\d+)(?:\s*\((\d+)\s*NC\))?", record_text)
            if match:
                wins = int(match.group(1))
                losses = int(match.group(2))
                draws = int(match.group(3))
                no_contests = int(match.group(4)) if match.group(4) else 0

        career_stats = {}
        stat_items = soup.find_all("li", class_=re.compile(r"b-list__box-list-item"))
        for item in stat_items:
            title_el = item.find("i", class_=re.compile(r"b-list__box-item-title"))
            if title_el:
                k = title_el.get_text(strip=True).rstrip(":").lower()
                v = item.get_text(strip=True).replace(title_el.get_text(strip=True), "").strip()
                career_stats[k] = v

        return Fighter(
            fighter_id=fighter_id,
            url=url,
            first_name=first_name,
            last_name=last_name,
            nickname=nickname,
            height_cm=height_cm,
            weight_kg=weight_kg,
            reach_cm=reach_cm,
            stance=stance,
            dob=dob,
            wins=wins,
            losses=losses,
            draws=draws,
            no_contests=no_contests,
            slpm=_parse_float(career_stats.get("slpm", "")),
            str_acc=_parse_pct(career_stats.get("str. acc.", "")),
            sapm=_parse_float(career_stats.get("sapm", "")),
            str_def=_parse_pct(career_stats.get("str. def", "")),
            td_avg=_parse_float(career_stats.get("td avg.", "")),
            td_acc=_parse_pct(career_stats.get("td acc.", "")),
            td_def=_parse_pct(career_stats.get("td def.", "")),
            sub_avg=_parse_float(career_stats.get("sub. avg.", "")),
        )

    except Exception as e:
        logger.warning(f"[{fighter_id}] Error parsing profile: {e}")
        return None


def _parse_date(text: str):
    """Parses date string 'Aug 14, 1987' -> date object."""
    from datetime import datetime
    formats = ["%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"]
    for fmt in formats:
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None
