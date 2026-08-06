"""
Unit tests for FightPredictor ML training, persistence, and symmetry inference module.
"""

from datetime import date
import pytest

from src.storage.models import Event, Fighter, Fight, FighterFightStats
from src.storage.database import Database
from src.ml.predictor import FightPredictor


@pytest.fixture
def predictor_test_db(tmp_path):
    db_file = tmp_path / "predictor_test.db"
    db = Database(str(db_file))

    e1 = Event(event_id="e1", url="http://example.com/e1", name="UFC 1", event_date=date(2022, 1, 1))
    e2 = Event(event_id="e2", url="http://example.com/e2", name="UFC 2", event_date=date(2022, 6, 1))
    e3 = Event(event_id="e3", url="http://example.com/e3", name="UFC 3", event_date=date(2023, 1, 1))
    db.upsert_event(e1)
    db.upsert_event(e2)
    db.upsert_event(e3)

    f1 = Fighter(fighter_id="f1", url="http://example.com/f1", first_name="Jon", last_name="Jones", height_cm=193.0, reach_cm=215.0, stance="Orthodox", dob=date(1987, 7, 19))
    f2 = Fighter(fighter_id="f2", url="http://example.com/f2", first_name="Stipe", last_name="Miocic", height_cm=193.0, reach_cm=203.0, stance="Orthodox", dob=date(1982, 8, 19))
    f3 = Fighter(fighter_id="f3", url="http://example.com/f3", first_name="Francis", last_name="Ngannou", height_cm=193.0, reach_cm=211.0, stance="Southpaw", dob=date(1986, 9, 5))
    db.upsert_fighter(f1)
    db.upsert_fighter(f2)
    db.upsert_fighter(f3)

    fight1 = Fight(fight_id="ft1", url="http://example.com/ft1", event_id="e1", fighter1_id="f1", fighter1_name="F1", fighter2_id="f2", fighter2_name="F2", winner_id="f1", outcome="W", method="KO/TKO")
    fight2 = Fight(fight_id="ft2", url="http://example.com/ft2", event_id="e2", fighter1_id="f2", fighter1_name="F2", fighter2_id="f3", fighter2_name="F3", winner_id="f3", outcome="W", method="KO/TKO")
    fight3 = Fight(fight_id="ft3", url="http://example.com/ft3", event_id="e3", fighter1_id="f1", fighter1_name="F1", fighter2_id="f3", fighter2_name="F3", winner_id="f1", outcome="W", method="Decision")

    db.upsert_fight(fight1)
    db.upsert_fight(fight2)
    db.upsert_fight(fight3)

    s1 = FighterFightStats(fight_id="ft1", fighter_id="f1", corner="red", sig_str_landed=50, sig_str_attempted=80)
    s2 = FighterFightStats(fight_id="ft1", fighter_id="f2", corner="blue", sig_str_landed=20, sig_str_attempted=60)
    db.upsert_fight_stats(s1)
    db.upsert_fight_stats(s2)

    return db


def test_fight_predictor_training(predictor_test_db, tmp_path):
    predictor = FightPredictor(str(predictor_test_db.db_path))
    metrics = predictor.train(test_size=0.3)

    assert "accuracy" in metrics
    assert "roc_auc" in metrics
    assert "log_loss" in metrics
    assert metrics["train_samples"] > 0
    assert "top_features" in metrics

    model_file = tmp_path / "model.json"
    predictor.save_model(str(model_file))
    assert model_file.exists()
    assert (tmp_path / "model.pkl").exists()


def test_fight_predictor_model_persistence(predictor_test_db, tmp_path):
    predictor1 = FightPredictor(str(predictor_test_db.db_path))
    predictor1.train(test_size=0.3)

    model_file = tmp_path / "saved_model.json"
    predictor1.save_model(str(model_file))

    predictor2 = FightPredictor(str(predictor_test_db.db_path))
    loaded = predictor2.load_model(str(model_file))
    assert loaded is True
    assert predictor2.is_trained is True


def test_fight_predictor_symmetry_and_same_fighter(predictor_test_db):
    predictor = FightPredictor(str(predictor_test_db.db_path))
    predictor.train(test_size=0.3)

    f1_feat = {"pre_f1_elo": 1700.0, "reach_cm": 215.0, "height_cm": 193.0, "stance": "Orthodox"}
    f2_feat = {"pre_f2_elo": 1500.0, "reach_cm": 203.0, "height_cm": 193.0, "stance": "Orthodox"}

    # 1. Forward prediction
    p_forward = predictor.predict_matchup(f1_feat, f2_feat)
    p1 = p_forward["fighter1_win_probability"]
    p2 = p_forward["fighter2_win_probability"]

    assert round(p1 + p2, 4) == 1.0

    # 2. Backward prediction (swapped corners)
    p_backward = predictor.predict_matchup(f2_feat, f1_feat)
    p1_swapped = p_backward["fighter1_win_probability"]
    p2_swapped = p_backward["fighter2_win_probability"]

    assert p1 == p2_swapped
    assert p2 == p1_swapped

    # 3. Same fighter against himself
    p_same = predictor.predict_matchup(f1_feat, f1_feat)
    assert p_same["fighter1_win_probability"] == 0.5
    assert p_same["fighter2_win_probability"] == 0.5
