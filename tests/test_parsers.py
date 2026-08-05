"""
Unit tests for HTML parsers (events, fights, fight details, fighters).
"""

from datetime import date
from src.parsers.events import parse_events_page, _parse_date as parse_event_date
from src.parsers.fights import parse_event_fights
from src.parsers.fight_detail import parse_fight_detail
from src.parsers.fighters import (
    parse_fighter_profile,
    _inches_to_cm,
    _lbs_to_kg,
    _parse_pct,
)


def test_parse_events_page(events_soup):
    events = parse_events_page(events_soup)
    assert len(events) == 1

    event = events[0]
    assert event.event_id == "1a50e734bb54861a"
    assert event.name == "UFC 309: Jones vs. Miocic"
    assert event.event_date == date(2024, 11, 16)
    assert event.location == "New York City, New York, USA"


def test_parse_upcoming_events_page(events_soup):
    from src.parsers.events import parse_upcoming_events_page
    events = parse_upcoming_events_page(events_soup)
    assert len(events) == 1
    assert events[0].name == "UFC 309: Jones vs. Miocic"


def test_parse_event_fights(fights_soup):
    fights = parse_event_fights(fights_soup, event_id="1a50e734bb54861a")
    assert len(fights) == 1

    fight = fights[0]
    assert fight.fight_id == "68ae50dbf98dc15f"
    assert fight.fighter1_name == "Jon Jones"
    assert fight.fighter2_name == "Stipe Miocic"
    assert fight.fighter1_id == "f1_id"
    assert fight.fighter2_id == "f2_id"
    assert fight.winner_id == "f1_id"
    assert fight.outcome == "W"
    assert fight.method == "KO/TKO"
    assert fight.method_detail == "Spinning Back Kick"
    assert fight.round == 3
    assert fight.time == "4:29"
    assert fight.weight_class == "Heavyweight"


def test_parse_fight_detail(fight_detail_soup):
    totals, rounds = parse_fight_detail(fight_detail_soup, fight_id="68ae50dbf98dc15f")

    assert len(totals) == 2
    f1_totals = next(s for s in totals if s.corner == "red")
    assert f1_totals.fighter_name == "Jon Jones"
    assert f1_totals.kd == 1
    assert f1_totals.sig_str_landed == 85
    assert f1_totals.sig_str_attempted == 120
    assert f1_totals.sig_str_accuracy == 70.8
    assert f1_totals.total_str_landed == 95
    assert f1_totals.td_landed == 2
    assert f1_totals.ctrl_seconds == 252  # 4:12 -> 252s

    # Sig strikes breakdown
    assert f1_totals.sig_head_landed == 50
    assert f1_totals.sig_body_landed == 20
    assert f1_totals.sig_leg_landed == 15
    assert f1_totals.sig_distance_landed == 40
    assert f1_totals.sig_clinch_landed == 10
    assert f1_totals.sig_ground_landed == 35

    assert len(rounds) == 2
    f1_round1 = next(r for r in rounds if r.corner == "red" and r.round_number == 1)
    assert f1_round1.sig_str_landed == 25
    assert f1_round1.sig_str_attempted == 35
    assert f1_round1.sig_head_landed == 15
    assert f1_round1.ctrl_seconds == 150  # 2:30 -> 150s


def test_parse_fighter_profile(fighter_profile_soup):
    fighter = parse_fighter_profile(
        fighter_profile_soup,
        fighter_id="f1_id",
        url="http://www.ufcstats.com/fighter-details/f1_id",
    )

    assert fighter is not None
    assert fighter.first_name == "Jon"
    assert fighter.last_name == "Jones"
    assert fighter.nickname == "Bones"
    assert fighter.full_name == "Jon Jones"
    assert fighter.wins == 28
    assert fighter.losses == 1
    assert fighter.draws == 0
    assert fighter.no_contests == 1
    assert fighter.record == "28-1-0"

    assert fighter.height_cm == 193.0  # 6' 4" -> 193 cm
    assert fighter.weight_kg == 112.5  # 248 lbs -> 112.5 kg
    assert fighter.reach_cm == 213.4   # 84" -> 213.4 cm
    assert fighter.stance == "Orthodox"
    assert fighter.dob == date(1987, 7, 19)

    assert fighter.slpm == 4.30
    assert fighter.str_acc == 58.0
    assert fighter.sapm == 2.20
    assert fighter.str_def == 64.0
    assert fighter.td_avg == 1.85
    assert fighter.td_acc == 45.0
    assert fighter.td_def == 95.0
    assert fighter.sub_avg == 0.4


def test_conversion_helpers():
    assert _inches_to_cm("6' 0\"") == 182.9
    assert _inches_to_cm("5' 11\"") == 180.3
    assert _inches_to_cm("invalid") is None

    assert _lbs_to_kg("155 lbs.") == 70.3
    assert _lbs_to_kg("205") == 93.0
    assert _lbs_to_kg("invalid") is None

    assert _parse_pct("45%") == 45.0
    assert _parse_pct("invalid") is None

    assert parse_event_date("November 16, 2024") == date(2024, 11, 16)
    assert parse_event_date("invalid") is None
