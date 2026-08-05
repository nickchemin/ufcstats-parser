"""
Unit tests for Machine Learning dataset generator and feature differential engineering.
"""

from datetime import date
import json
import pytest
from src.storage.models import Event, Fighter, Fight
from src.storage.database import Database
from src.storage.ml_dataset import MLDatasetGenerator, _compute_age, _safe_sub


@pytest.fixture
def populated_db(tmp_path):
    db_file = tmp_path / "ml_test.db"
    db = Database(str(db_file))

    event = Event(
        event_id="e1",
        url="http://example.com/e1",
        name="UFC 309",
        event_date=date(2024, 11, 16),
        location="New York",
    )
    db.upsert_event(event)

    f1 = Fighter(
        fighter_id="f1",
        url="http://example.com/f1",
        first_name="Jon",
        last_name="Jones",
        height_cm=193.0,
        weight_kg=112.5,
        reach_cm=213.4,
        stance="Orthodox",
        dob=date(1987, 7, 19),
        wins=28,
        losses=1,
        slpm=4.30,
        str_acc=58.0,
        sapm=2.20,
        str_def=64.0,
        td_avg=1.85,
        td_acc=45.0,
        td_def=95.0,
        sub_avg=0.4,
    )
    f2 = Fighter(
        fighter_id="f2",
        url="http://example.com/f2",
        first_name="Stipe",
        last_name="Miocic",
        height_cm=193.0,
        weight_kg=106.1,
        reach_cm=203.2,
        stance="Orthodox",
        dob=date(1982, 8, 19),
        wins=20,
        losses=5,
        slpm=4.82,
        str_acc=53.0,
        sapm=3.82,
        str_def=54.0,
        td_avg=1.86,
        td_acc=34.0,
        td_def=68.0,
        sub_avg=0.0,
    )
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
        round=3,
        weight_class="Heavyweight",
    )
    db.upsert_fight(fight)

    return db


def test_helper_functions():
    assert _compute_age("1987-07-19", "2024-11-16") == 37.3
    assert _compute_age(None, "2024-11-16") is None
    assert _compute_age("1987-07-19", None) is None

    assert _safe_sub(10.0, 5.0) == 5.0
    assert _safe_sub(5.0, 10.0) == -5.0
    assert _safe_sub(None, 5.0) is None
    assert _safe_sub(10.0, None) is None


def test_ml_dataset_generation(populated_db):
    generator = MLDatasetGenerator(str(populated_db.db_path))
    dataset = generator.build_dataset()

    assert len(dataset) == 1
    row = dataset[0]

    assert row["fight_id"] == "fight1"
    assert row["fighter1_name"] == "Jon Jones"
    assert row["fighter2_name"] == "Stipe Miocic"
    assert row["target_winner"] == 1

    # Differentials check
    assert row["f1_height_cm"] == 193.0
    assert row["f2_height_cm"] == 193.0
    assert row["diff_height_cm"] == 0.0

    assert row["diff_reach_cm"] == 10.2  # 213.4 - 203.2
    assert row["diff_weight_kg"] == 6.4   # 112.5 - 106.1
    assert row["diff_wins"] == 8           # 28 - 20
    assert row["diff_slpm"] == -0.52       # 4.30 - 4.82
    assert row["diff_str_acc"] == 5.0      # 58 - 53
    assert row["diff_td_def"] == 27.0      # 95 - 68
    assert row["is_same_stance"] == 1


def test_ml_dataset_export(populated_db, tmp_path):
    generator = MLDatasetGenerator(str(populated_db.db_path))

    csv_path = tmp_path / "ml_dataset.csv"
    json_path = tmp_path / "ml_dataset.json"

    generator.export_ml_dataset(str(csv_path), output_format="csv")
    generator.export_ml_dataset(str(json_path), output_format="json")

    assert csv_path.exists()
    assert json_path.exists()

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
        assert len(data) == 1
        assert data[0]["target_winner"] == 1
