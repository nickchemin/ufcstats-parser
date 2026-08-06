"""
Unit tests for FastAPI REST API endpoints using TestClient.
"""

from datetime import date
import pytest
from fastapi.testclient import TestClient

from src.storage.models import Event, Fighter, Fight, FighterFightStats
from src.storage.database import Database
from src.api import app, set_db_path


@pytest.fixture
def api_test_db(tmp_path):
    db_file = tmp_path / "api_test.db"
    db = Database(str(db_file))

    event = Event(
        event_id="e1",
        url="http://example.com/e1",
        name="UFC 309: Jones vs. Miocic",
        event_date=date(2024, 11, 16),
        location="New York",
    )
    db.upsert_event(event)

    f1 = Fighter(fighter_id="f1", url="http://example.com/f1", first_name="Jon", last_name="Jones", height_cm=193.0, reach_cm=215.0)
    f2 = Fighter(fighter_id="f2", url="http://example.com/f2", first_name="Stipe", last_name="Miocic", height_cm=193.0, reach_cm=203.0)
    db.upsert_fighter(f1)
    db.upsert_fighter(f2)

    fight = Fight(
        fight_id="fight1",
        url="http://example.com/fight1",
        event_id="e1",
        fighter1_id="f1",
        fighter1_name="Jon Jones",
        fighter2_id="f2",
        fighter2_name="Stipe Miocic",
        winner_id="f1",
        outcome="W",
        method="KO/TKO",
    )
    db.upsert_fight(fight)

    stats = FighterFightStats(
        fight_id="fight1",
        fighter_id="f1",
        corner="red",
        sig_str_landed=85,
        sig_str_attempted=120,
    )
    db.upsert_fight_stats(stats)

    set_db_path(str(db_file))
    return db


@pytest.fixture
def client(api_test_db):
    return TestClient(app)


def test_root_endpoint(client):
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert "version" in data
    assert data["docs"] == "/docs"


def test_get_events(client):
    res = client.get("/api/v1/events")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert len(data["data"]) == 1
    assert data["data"][0]["event_id"] == "e1"


def test_get_upcoming_events(client):
    res = client.get("/api/v1/events/upcoming")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)


def test_get_event_details(client):
    res = client.get("/api/v1/events/e1")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "UFC 309: Jones vs. Miocic"
    assert len(data["fights"]) == 1

    notFound = client.get("/api/v1/events/nonexistent")
    assert notFound.status_code == 404


def test_get_fight_details(client):
    res = client.get("/api/v1/fights/fight1")
    assert res.status_code == 200
    data = res.json()
    assert data["fighter1_name"] == "Jon Jones"
    assert len(data["totals"]) == 1

    notFound = client.get("/api/v1/fights/nonexistent")
    assert notFound.status_code == 404


def test_search_fighters(client):
    res = client.get("/api/v1/fighters?q=Jon")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert len(data["data"]) == 1
    assert data["data"][0]["last_name"] == "Jones"


def test_get_fighter_profile(client):
    res = client.get("/api/v1/fighters/f1")
    assert res.status_code == 200
    data = res.json()
    assert data["first_name"] == "Jon"

    notFound = client.get("/api/v1/fighters/nonexistent")
    assert notFound.status_code == 404


def test_get_matchup(client):
    res = client.get("/api/v1/matchup?fighter1_id=f1&fighter2_id=f2")
    assert res.status_code == 200
    data = res.json()
    assert data["fighter1"]["first_name"] == "Jon"
    assert data["fighter2"]["first_name"] == "Stipe"
    assert "differentials" in data
    assert data["differentials"]["reach_cm"] == 12.0


def test_get_ml_dataset(client):
    res = client.get("/api/v1/ml-dataset")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["target_winner"] == 1
    assert "pre_f1_elo" in data[0]


def test_get_db_summary(client):
    res = client.get("/api/v1/stats/summary")
    assert res.status_code == 200
    data = res.json()
    assert "events" in data
    assert data["events"] == 1


def test_get_health(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert "health_score_pct" in data
