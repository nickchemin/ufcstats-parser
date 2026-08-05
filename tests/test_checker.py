"""
Unit tests for database integrity checker.
"""

from datetime import date
import pytest
from src.storage.models import Event, Fighter, Fight, FighterFightStats
from src.storage.database import Database
from src.storage.checker import DatabaseChecker


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "check_test.db"
    db = Database(str(db_file))

    event = Event(
        event_id="e1",
        url="http://example.com/e1",
        name="UFC 309",
        event_date=date(2024, 11, 16),
    )
    db.upsert_event(event)

    f1 = Fighter(fighter_id="f1", url="http://example.com/f1", first_name="Jon", last_name="Jones")
    db.upsert_fighter(f1)

    fight = Fight(
        fight_id="fight1",
        url="http://example.com/fight1",
        event_id="e1",
        fighter1_id="f1",
        fighter2_id="f2",  # f2 is unlinked (not in fighters table)
        winner_id="f1",
        outcome="W",
    )
    db.upsert_fight(fight)

    stats = FighterFightStats(
        fight_id="fight1",
        fighter_id="f1",
        corner="red",
        sig_str_landed=10,
        sig_str_attempted=15,
    )
    db.upsert_fight_stats(stats)

    return db


def test_database_checker(test_db):
    checker = DatabaseChecker(str(test_db.db_path))
    report = checker.run_diagnostics()

    assert "error" not in report
    assert report["counts"]["events"] == 1
    assert report["counts"]["fights"] == 1
    assert report["counts"]["fighters"] == 1

    assert report["orphans"]["orphan_fights"] == 0
    assert report["orphans"]["orphan_fight_stats"] == 0

    # f2 is unlinked
    assert report["missing_links"]["unlinked_fighters_count"] == 1
    assert "f2" in report["missing_links"]["unlinked_fighter_ids"]

    assert report["anomalies"]["invalid_strikes_count"] == 0
    assert report["health_score_pct"] > 0


def test_database_checker_nonexistent(tmp_path):
    checker = DatabaseChecker(str(tmp_path / "nonexistent.db"))
    report = checker.run_diagnostics()
    assert "error" in report
