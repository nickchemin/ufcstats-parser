"""
Parser for detailed fight statistics page.

Target URL: http://www.ufcstats.com/fight-details/<fight_id>

Handles 4 main table sections:
  [0] Totals (entire fight):          Fighter | KD | Sig.Str. | Sig.Str.% | Total Str. | TD | TD% | Sub.Att | Rev. | Ctrl
  [1] Totals by Round:            Same breakdown per round
  [2] Significant Strikes:        Fighter | Sig.Str. | % | Head | Body | Leg | Distance | Clinch | Ground
  [3] Significant Strikes/Round:  Same breakdown per round
"""

import re
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

from ..storage.models import FighterFightStats, RoundStats
from ..utils.logger import get_logger

logger = get_logger(__name__)


def _parse_ctrl(text: str) -> int:
    """Converts control time string '4:32' to seconds (272). Returns 0 for '--'."""
    text = text.strip().replace("---", "").replace("--", "").strip()
    if not text:
        return 0
    parts = text.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return int(parts[0])
    except ValueError:
        return 0


def _parse_int(text: str) -> int:
    """Parses integer value from text string."""
    text = text.strip().replace("---", "0").replace("--", "0")
    try:
        return int(text)
    except ValueError:
        return 0


def _parse_of(text: str) -> Tuple[int, int]:
    """Parses '42 of 100' string format into (landed, attempted) tuple."""
    text = text.strip()
    if not text or text in ("---", "--"):
        return 0, 0
    match = re.match(r"(\d+)\s+of\s+(\d+)", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    try:
        return int(text), 0
    except ValueError:
        return 0, 0


def _get_fighter_names(soup: BeautifulSoup) -> Tuple[Optional[str], Optional[str]]:
    """Extracts fighter names from fight details page header."""
    persons = soup.find_all("div", class_="b-fight-details__person")
    names = []
    for p in persons:
        link = p.find("a", class_="b-link")
        if link:
            names.append(link.get_text(strip=True))
    f1 = names[0] if len(names) > 0 else None
    f2 = names[1] if len(names) > 1 else None
    return f1, f2


def _get_fighter_ids(soup: BeautifulSoup) -> Tuple[Optional[str], Optional[str]]:
    """Extracts fighter IDs from profile links in header."""
    from urllib.parse import urlparse
    persons = soup.find_all("div", class_="b-fight-details__person")
    ids = []
    for p in persons:
        link = p.find("a", class_="b-link", href=re.compile(r"fighter-details"))
        if link:
            path = urlparse(link.get("href", "")).path
            fid = path.rstrip("/").split("/")[-1]
            ids.append(fid)
    f1 = ids[0] if len(ids) > 0 else None
    f2 = ids[1] if len(ids) > 1 else None
    return f1, f2


def _col_val(cols: list, col_idx: int, fighter_idx: int) -> str:
    """Returns text for a specific fighter index from table cell."""
    if col_idx >= len(cols):
        return ""
    paras = cols[col_idx].find_all("p", class_="b-fight-details__table-text")
    if fighter_idx < len(paras):
        return paras[fighter_idx].get_text(strip=True)
    return ""


def parse_fight_detail(
    soup: BeautifulSoup,
    fight_id: str,
) -> Tuple[List[FighterFightStats], List[RoundStats]]:
    """
    Parses fight detail page and returns totals and round-by-round statistics.

    Returns:
        Tuple of (totals_list, rounds_list).
    """
    fighter_names = _get_fighter_names(soup)
    fighter_ids = _get_fighter_ids(soup)

    tables = soup.find_all("table")
    if len(tables) < 1:
        logger.warning(f"[{fight_id}] Statistics tables not found")
        return [], []

    totals = _parse_totals_table(tables[0], fight_id, fighter_names, fighter_ids)
    rounds = _parse_rounds_table(tables[1], fight_id, fighter_names, fighter_ids) if len(tables) > 1 else []

    if len(tables) > 2:
        _add_sig_strikes(tables[2], totals)
    if len(tables) > 3:
        _add_sig_strikes_rounds(tables[3], rounds)

    return totals, rounds


def _parse_totals_table(
    table: Tag,
    fight_id: str,
    fighter_names: Tuple,
    fighter_ids: Tuple,
) -> List[FighterFightStats]:
    """Parses overall totals table."""
    results = []

    data_rows = [
        r for r in table.find_all("tr")
        if "b-fight-details__table-row" in " ".join(r.get("class", []))
        and not r.find("th")
    ]

    for row in data_rows[:1]:
        cols = row.find_all("td")

        for fi in range(2):
            corner = "red" if fi == 0 else "blue"

            kd = _parse_int(_col_val(cols, 1, fi))
            sig_l, sig_a = _parse_of(_col_val(cols, 2, fi))
            total_l, total_a = _parse_of(_col_val(cols, 4, fi))
            td_l, td_a = _parse_of(_col_val(cols, 5, fi))
            sub_att = _parse_int(_col_val(cols, 7, fi))
            rev = _parse_int(_col_val(cols, 8, fi))
            ctrl = _parse_ctrl(_col_val(cols, 9, fi))

            results.append(
                FighterFightStats(
                    fight_id=fight_id,
                    fighter_id=fighter_ids[fi] if fi < len(fighter_ids) else None,
                    fighter_name=fighter_names[fi] if fi < len(fighter_names) else None,
                    corner=corner,
                    kd=kd,
                    sig_str_landed=sig_l,
                    sig_str_attempted=sig_a,
                    total_str_landed=total_l,
                    total_str_attempted=total_a,
                    td_landed=td_l,
                    td_attempted=td_a,
                    sub_att=sub_att,
                    rev=rev,
                    ctrl_seconds=ctrl,
                )
            )

    return results


def _parse_rounds_table(
    table: Tag,
    fight_id: str,
    fighter_names: Tuple,
    fighter_ids: Tuple,
) -> List[RoundStats]:
    """Parses totals by round table."""
    results = []

    data_rows = [
        r for r in table.find_all("tr")
        if "b-fight-details__table-row" in " ".join(r.get("class", []))
        and not r.find("th")
    ]

    for round_num, row in enumerate(data_rows, start=1):
        cols = row.find_all("td")

        for fi in range(2):
            corner = "red" if fi == 0 else "blue"

            kd = _parse_int(_col_val(cols, 1, fi))
            sig_l, sig_a = _parse_of(_col_val(cols, 2, fi))
            total_l, total_a = _parse_of(_col_val(cols, 4, fi))
            td_l, td_a = _parse_of(_col_val(cols, 5, fi))
            sub_att = _parse_int(_col_val(cols, 7, fi))
            rev = _parse_int(_col_val(cols, 8, fi))
            ctrl = _parse_ctrl(_col_val(cols, 9, fi))

            results.append(
                RoundStats(
                    fight_id=fight_id,
                    round_number=round_num,
                    fighter_id=fighter_ids[fi] if fi < len(fighter_ids) else None,
                    fighter_name=fighter_names[fi] if fi < len(fighter_names) else None,
                    corner=corner,
                    kd=kd,
                    sig_str_landed=sig_l,
                    sig_str_attempted=sig_a,
                    total_str_landed=total_l,
                    total_str_attempted=total_a,
                    td_landed=td_l,
                    td_attempted=td_a,
                    sub_att=sub_att,
                    rev=rev,
                    ctrl_seconds=ctrl,
                )
            )

    return results


def _add_sig_strikes(table: Tag, stats_list: List[FighterFightStats]) -> None:
    """Enriches totals stats list with Significant Strikes breakdown data."""
    data_rows = [
        r for r in table.find_all("tr")
        if "b-fight-details__table-row" in " ".join(r.get("class", []))
        and not r.find("th")
    ]

    for row in data_rows[:1]:
        cols = row.find_all("td")
        for fi in range(2):
            corner = "red" if fi == 0 else "blue"
            target = next((s for s in stats_list if s.corner == corner), None)
            if not target:
                continue

            head_l, head_a = _parse_of(_col_val(cols, 3, fi))
            body_l, body_a = _parse_of(_col_val(cols, 4, fi))
            leg_l, leg_a = _parse_of(_col_val(cols, 5, fi))
            dist_l, dist_a = _parse_of(_col_val(cols, 6, fi))
            clinch_l, clinch_a = _parse_of(_col_val(cols, 7, fi))
            ground_l, ground_a = _parse_of(_col_val(cols, 8, fi))

            target.sig_head_landed = head_l
            target.sig_head_attempted = head_a
            target.sig_body_landed = body_l
            target.sig_body_attempted = body_a
            target.sig_leg_landed = leg_l
            target.sig_leg_attempted = leg_a
            target.sig_distance_landed = dist_l
            target.sig_distance_attempted = dist_a
            target.sig_clinch_landed = clinch_l
            target.sig_clinch_attempted = clinch_a
            target.sig_ground_landed = ground_l
            target.sig_ground_attempted = ground_a


def _add_sig_strikes_rounds(table: Tag, rounds: List[RoundStats]) -> None:
    """Enriches round stats list with Significant Strikes by round breakdown data."""
    data_rows = [
        r for r in table.find_all("tr")
        if "b-fight-details__table-row" in " ".join(r.get("class", []))
        and not r.find("th")
    ]

    for round_num, row in enumerate(data_rows, start=1):
        cols = row.find_all("td")
        for fi in range(2):
            corner = "red" if fi == 0 else "blue"
            target = next(
                (r for r in rounds if r.round_number == round_num and r.corner == corner),
                None,
            )
            if not target:
                continue

            head_l, head_a = _parse_of(_col_val(cols, 3, fi))
            body_l, body_a = _parse_of(_col_val(cols, 4, fi))
            leg_l, leg_a = _parse_of(_col_val(cols, 5, fi))
            dist_l, dist_a = _parse_of(_col_val(cols, 6, fi))
            clinch_l, clinch_a = _parse_of(_col_val(cols, 7, fi))
            ground_l, ground_a = _parse_of(_col_val(cols, 8, fi))

            target.sig_head_landed = head_l
            target.sig_head_attempted = head_a
            target.sig_body_landed = body_l
            target.sig_body_attempted = body_a
            target.sig_leg_landed = leg_l
            target.sig_leg_attempted = leg_a
            target.sig_distance_landed = dist_l
            target.sig_distance_attempted = dist_a
            target.sig_clinch_landed = clinch_l
            target.sig_clinch_attempted = clinch_a
            target.sig_ground_landed = ground_l
            target.sig_ground_attempted = ground_a
