"""
Unit tests for storage components: Database, FileCache, and Exporter.
"""

from datetime import date
import json
import pytest
from src.storage.models import Event, Fighter, Fight, FighterFightStats, RoundStats
from src.storage.database import Database
from src.storage.cache import FileCache
from src.storage.exporter import Exporter


@pytest.fixture
def tmp_db(tmp_path):
    db_file = tmp_path / "test_ufc.db"
    return Database(str(db_file))


@pytest.fixture
def tmp_cache(tmp_path):
    cache_dir = tmp_path / "cache"
    return FileCache(str(cache_dir))


def test_database_upsert_event(tmp_db):
    event = Event(
        event_id="e1",
        url="http://example.com/e1",
        name="UFC 309",
        event_date=date(2024, 11, 16),
        location="New York",
    )
    tmp_db.upsert_event(event)

    assert "e1" in tmp_db.get_event_ids()

    # Test update via upsert
    event.name = "UFC 309 Updated"
    tmp_db.upsert_event(event)
    summary = tmp_db.summary()
    assert summary["events"] == 1


def test_database_upsert_fighter(tmp_db):
    fighter = Fighter(
        fighter_id="f1",
        url="http://example.com/f1",
        first_name="Jon",
        last_name="Jones",
        wins=28,
        losses=1,
    )
    tmp_db.upsert_fighter(fighter)

    assert "f1" in tmp_db.get_fighter_ids()
    summary = tmp_db.summary()
    assert summary["fighters"] == 1


def test_database_upsert_fight_and_stats(tmp_db):
    event = Event(
        event_id="e1",
        url="http://example.com/e1",
        name="UFC 309",
        event_date=date(2024, 11, 16),
    )
    tmp_db.upsert_event(event)

    fight = Fight(
        fight_id="fight1",
        url="http://example.com/fight1",
        event_id="e1",
        fighter1_name="Jon Jones",
        fighter2_name="Stipe Miocic",
    )
    tmp_db.upsert_fight(fight)
    assert tmp_db.get_fight_ids_for_event("e1") == ["fight1"]

    stats = FighterFightStats(
        fight_id="fight1",
        fighter_name="Jon Jones",
        corner="red",
        kd=1,
        sig_str_landed=85,
        sig_str_attempted=120,
    )
    tmp_db.upsert_fight_stats(stats)

    rnd = RoundStats(
        fight_id="fight1",
        round_number=1,
        fighter_name="Jon Jones",
        corner="red",
        sig_str_landed=25,
        sig_str_attempted=35,
    )
    tmp_db.upsert_round_stats(rnd)

    summary = tmp_db.summary()
    assert summary["fights"] == 1
    assert summary["round_stats_rows"] == 1


def test_file_cache(tmp_cache):
    url = "http://www.ufcstats.com/test-page"
    html_content = "<html><body>Test</body></html>"

    assert tmp_cache.get(url) is None

    tmp_cache.set(url, html_content)
    assert tmp_cache.get(url) == html_content

    stats = tmp_cache.stats()
    assert stats["files"] == 1
    assert stats["hits"] == 1

    cleared = tmp_cache.clear()
    assert cleared == 2  # html + meta files
    assert tmp_cache.get(url) is None


def test_exporter(tmp_db, tmp_path):
    event = Event(
        event_id="e1",
        url="http://example.com/e1",
        name="UFC 309",
        event_date=date(2024, 11, 16),
        location="New York",
    )
    tmp_db.upsert_event(event)

    export_dir = tmp_path / "export_data"
    exporter = Exporter(str(tmp_db.db_path))
    exporter.export_all(str(export_dir))

    json_file = export_dir / "events.json"
    csv_file = export_dir / "events.csv"

    assert json_file.exists()
    assert csv_file.exists()

    with open(json_file, encoding="utf-8") as f:
        data = json.load(f)
        assert len(data) == 1
        assert data[0]["name"] == "UFC 309"
