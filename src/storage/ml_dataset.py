"""
Machine Learning feature engineering pipeline.

Transforms relational SQLite tables into a flat dataset comparing Fighter 1 vs Fighter 2
with calculated differentials for predictive modeling.
"""

import csv
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import List, Dict, Any, Optional

from ..utils.logger import get_logger

logger = get_logger(__name__)


def _compute_age(dob_str: Optional[str], ref_date_str: Optional[str]) -> Optional[float]:
    """Calculates age in years at the time of the event."""
    if not dob_str or not ref_date_str:
        return None
    try:
        dob = datetime.strptime(dob_str[:10], "%Y-%m-%d")
        ref_date = datetime.strptime(ref_date_str[:10], "%Y-%m-%d")
        delta_days = (ref_date - dob).days
        if delta_days < 0:
            return None
        return round(delta_days / 365.25, 1)
    except ValueError:
        return None


def _safe_sub(val1: Optional[float], val2: Optional[float], round_digits: int = 2) -> Optional[float]:
    """Computes val1 - val2 safely handling None values."""
    if val1 is None or val2 is None:
        return None
    return round(val1 - val2, round_digits)


FEATURE_COLUMNS = [
    "diff_pre_elo",
    "diff_height_cm",
    "diff_weight_kg",
    "diff_reach_cm",
    "diff_ape_index",
    "diff_reach_ratio",
    "diff_age_years",
    "is_same_stance",
    "is_orthodox_vs_southpaw",
    "pre_f1_ufc_debut",
    "pre_f2_ufc_debut",
    "diff_pre_wins",
    "diff_pre_losses",
    "diff_pre_total_fights",
    "diff_pre_win_rate",
    "diff_pre_ko_win_rate",
    "diff_pre_sub_win_rate",
    "diff_pre_finish_win_rate",
    "diff_pre_dec_win_rate",
    "diff_pre_streak",
    "diff_pre_days_since_last_fight",
    "diff_pre_win_rate_last3",
    "diff_slpm",
    "diff_str_acc",
    "diff_sapm",
    "diff_strike_efficiency",
    "diff_str_def",
    "diff_td_avg",
    "diff_td_acc",
    "diff_td_def",
]


class MLDatasetGenerator:
    """Generates ML-ready dataset with comparative differentials and pre-fight rolling metrics."""

    def __init__(self, db_path: str = "ufc_data.db"):
        self.db_path = Path(db_path)

    def build_dataset(self) -> List[Dict[str, Any]]:
        """
        Queries database and builds feature dictionary for each fight matchup.
        Fights are processed in chronological order (event_date ASC) to calculate
        true pre-fight rolling statistics without data leakage.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        try:
            # Query fights joined with event info, ordered chronologically
            fights_query = """
            SELECT 
                f.fight_id, f.event_id, e.date as event_date, f.weight_class,
                f.title_fight, f.is_main_event, f.method, f.method_detail,
                f.round as finish_round, f.time as finish_time,
                f.fighter1_id, f.fighter1_name, f.fighter2_id, f.fighter2_name,
                f.winner_id, f.outcome
            FROM fights f
            LEFT JOIN events e ON f.event_id = e.event_id
            ORDER BY e.date ASC, f.fight_id ASC
            """
            fights = conn.execute(fights_query).fetchall()

            # Index fighters by fighter_id
            fighters_query = "SELECT * FROM fighters"
            fighters_rows = conn.execute(fighters_query).fetchall()
            fighters_map = {row["fighter_id"]: dict(row) for row in fighters_rows}

            # Pre-load fight_stats indexed by (fight_id, fighter_id)
            stats_query = "SELECT * FROM fight_stats"
            stats_rows = conn.execute(stats_query).fetchall()
            fight_stats_map = {}
            for row in stats_rows:
                key = (row["fight_id"], row["fighter_id"])
                fight_stats_map[key] = dict(row)

            # State tracker for each fighter's pre-fight history
            # fid -> { 'history': [...], 'last_date': str, 'streak': int, 'wins': int, 'losses': int, 'draws': int, 'stats': [...], 'elo': float, 'ko_wins': int, 'sub_wins': int, 'dec_wins': int }
            history_tracker: Dict[str, Dict[str, Any]] = {}

            def get_tracker(fid: str) -> Dict[str, Any]:
                if fid not in history_tracker:
                    history_tracker[fid] = {
                        "history": [],
                        "last_date": None,
                        "streak": 0,
                        "wins": 0,
                        "losses": 0,
                        "draws": 0,
                        "stats": [],
                        "elo": 1500.0,
                        "ko_wins": 0,
                        "sub_wins": 0,
                        "dec_wins": 0,
                    }
                return history_tracker[fid]

            dataset = []

            for fight in fights:
                fight_dict = dict(fight)
                fight_id = fight_dict["fight_id"]
                f1_id = fight_dict["fighter1_id"]
                f2_id = fight_dict["fighter2_id"]

                f1 = fighters_map.get(f1_id, {}) if f1_id else {}
                f2 = fighters_map.get(f2_id, {}) if f2_id else {}

                event_date_str = fight_dict["event_date"]
                f1_age = _compute_age(f1.get("dob"), event_date_str)
                f2_age = _compute_age(f2.get("dob"), event_date_str)

                # Target label computation
                winner_id = fight_dict["winner_id"]
                if winner_id == f1_id:
                    target_winner = 1
                elif winner_id == f2_id:
                    target_winner = 0
                else:
                    target_winner = None

                # Compute PRE-FIGHT stats for F1 and F2 (Zero Data Leakage)
                t1 = get_tracker(f1_id) if f1_id else {"wins": 0, "losses": 0, "draws": 0, "streak": 0, "last_date": None, "history": [], "stats": [], "elo": 1500.0, "ko_wins": 0, "sub_wins": 0, "dec_wins": 0}
                t2 = get_tracker(f2_id) if f2_id else {"wins": 0, "losses": 0, "draws": 0, "streak": 0, "last_date": None, "history": [], "stats": [], "elo": 1500.0, "ko_wins": 0, "sub_wins": 0, "dec_wins": 0}

                pre_f1_wins = t1["wins"]
                pre_f1_losses = t1["losses"]
                pre_f1_draws = t1["draws"]
                pre_f1_total = pre_f1_wins + pre_f1_losses + pre_f1_draws
                pre_f1_win_rate = round(pre_f1_wins / pre_f1_total, 3) if pre_f1_total > 0 else None
                pre_f1_streak = t1["streak"]
                pre_f1_elo = round(t1["elo"], 1)

                pre_f1_ko_win_rate = round(t1["ko_wins"] / pre_f1_wins, 3) if pre_f1_wins > 0 else None
                pre_f1_sub_win_rate = round(t1["sub_wins"] / pre_f1_wins, 3) if pre_f1_wins > 0 else None
                pre_f1_dec_win_rate = round(t1["dec_wins"] / pre_f1_wins, 3) if pre_f1_wins > 0 else None

                pre_f2_wins = t2["wins"]
                pre_f2_losses = t2["losses"]
                pre_f2_draws = t2["draws"]
                pre_f2_total = pre_f2_wins + pre_f2_losses + pre_f2_draws
                pre_f2_win_rate = round(pre_f2_wins / pre_f2_total, 3) if pre_f2_total > 0 else None
                pre_f2_streak = t2["streak"]
                pre_f2_elo = round(t2["elo"], 1)

                pre_f2_ko_win_rate = round(t2["ko_wins"] / pre_f2_wins, 3) if pre_f2_wins > 0 else None
                pre_f2_sub_win_rate = round(t2["sub_wins"] / pre_f2_wins, 3) if pre_f2_wins > 0 else None
                pre_f2_dec_win_rate = round(t2["dec_wins"] / pre_f2_wins, 3) if pre_f2_wins > 0 else None

                # Inactivity / Layoff calculation (days since last fight)
                pre_f1_days_since_last = None
                if t1["last_date"] and event_date_str:
                    try:
                        d1 = datetime.strptime(event_date_str[:10], "%Y-%m-%d")
                        d0 = datetime.strptime(t1["last_date"][:10], "%Y-%m-%d")
                        pre_f1_days_since_last = (d1 - d0).days
                    except ValueError:
                        pass

                pre_f2_days_since_last = None
                if t2["last_date"] and event_date_str:
                    try:
                        d1 = datetime.strptime(event_date_str[:10], "%Y-%m-%d")
                        d0 = datetime.strptime(t2["last_date"][:10], "%Y-%m-%d")
                        pre_f2_days_since_last = (d1 - d0).days
                    except ValueError:
                        pass

                # Form over last 3 fights
                h1_last3 = t1["history"][-3:]
                pre_f1_win_rate_last3 = round(sum(1 for x in h1_last3 if x == "win") / len(h1_last3), 3) if h1_last3 else None

                h2_last3 = t2["history"][-3:]
                pre_f2_win_rate_last3 = round(sum(1 for x in h2_last3 if x == "win") / len(h2_last3), 3) if h2_last3 else None

                # Compute pre-fight striking & grappling rates strictly from past fight stats (Zero Data Leakage & Real Absorbed Rates)
                def compute_pre_stats(t_dict: dict):
                    stats_list = t_dict.get("stats", [])
                    if not stats_list:
                        return (None, None, None, None, None, None, None)

                    tot_sl = sum(item.get("own", {}).get("sig_str_landed", 0) for item in stats_list)
                    tot_sa = sum(item.get("own", {}).get("sig_str_attempted", 0) for item in stats_list)
                    tot_tdl = sum(item.get("own", {}).get("td_landed", 0) for item in stats_list)
                    tot_tda = sum(item.get("own", {}).get("td_attempted", 0) for item in stats_list)

                    # Opponent stats against this fighter (for SApM, Striking Defense & Takedown Defense)
                    tot_opp_sl = sum(item.get("opp", {}).get("sig_str_landed", 0) for item in stats_list)
                    tot_opp_sa = sum(item.get("opp", {}).get("sig_str_attempted", 0) for item in stats_list)
                    tot_opp_tdl = sum(item.get("opp", {}).get("td_landed", 0) for item in stats_list)
                    tot_opp_tda = sum(item.get("opp", {}).get("td_attempted", 0) for item in stats_list)

                    tot_mins = max(1.0, len(stats_list) * 10.0)

                    slpm = round(tot_sl / tot_mins, 2)
                    sapm = round(tot_opp_sl / tot_mins, 2)

                    acc_str = round((tot_sl / tot_sa) * 100.0, 1) if tot_sa > 0 else None
                    str_def = round((1.0 - (tot_opp_sl / tot_opp_sa)) * 100.0, 1) if tot_opp_sa > 0 else None

                    acc_td = round((tot_tdl / tot_tda) * 100.0, 1) if tot_tda > 0 else None
                    td_def = round((1.0 - (tot_opp_tdl / tot_opp_tda)) * 100.0, 1) if tot_opp_tda > 0 else None

                    td_avg = round(tot_tdl / (tot_mins / 15.0), 2)

                    return (slpm, acc_str, sapm, str_def, td_avg, acc_td, td_def)

                f1_slpm, f1_str_acc, f1_sapm, f1_str_def, f1_td_avg, f1_td_acc, f1_td_def = compute_pre_stats(t1)
                f2_slpm, f2_str_acc, f2_sapm, f2_str_def, f2_td_avg, f2_td_acc, f2_td_def = compute_pre_stats(t2)

                # Physical ape index, reach ratio & stance flags
                f1_reach = f1.get("reach_cm")
                f1_height = f1.get("height_cm")
                f1_ape_index = round(f1_reach - f1_height, 1) if (f1_reach is not None and f1_height is not None) else None
                f1_reach_ratio = round(f1_reach / f1_height, 3) if (f1_reach and f1_height and f1_height > 0) else None

                f2_reach = f2.get("reach_cm")
                f2_height = f2.get("height_cm")
                f2_ape_index = round(f2_reach - f2_height, 1) if (f2_reach is not None and f2_height is not None) else None
                f2_reach_ratio = round(f2_reach / f2_height, 3) if (f2_reach and f2_height and f2_height > 0) else None

                st1 = (f1.get("stance") or "").strip().lower()
                st2 = (f2.get("stance") or "").strip().lower()
                is_same_stance = 1 if (st1 and st2 and st1 == st2) else 0
                is_orthodox_vs_southpaw = 1 if (set([st1, st2]) == {"orthodox", "southpaw"}) else 0

                pre_f1_finish_win_rate = round((t1["ko_wins"] + t1["sub_wins"]) / pre_f1_wins, 3) if pre_f1_wins > 0 else None
                pre_f2_finish_win_rate = round((t2["ko_wins"] + t2["sub_wins"]) / pre_f2_wins, 3) if pre_f2_wins > 0 else None

                f1_strike_eff = round(f1_slpm / (f1_sapm + 0.1), 2) if (f1_slpm is not None and f1_sapm is not None) else None
                f2_strike_eff = round(f2_slpm / (f2_sapm + 0.1), 2) if (f2_slpm is not None and f2_sapm is not None) else None

                feature_row = {
                    # Context & Identifiers
                    "fight_id": fight_dict["fight_id"],
                    "event_id": fight_dict["event_id"],
                    "event_date": event_date_str,
                    "weight_class": fight_dict["weight_class"],
                    "title_fight": fight_dict["title_fight"],
                    "is_main_event": fight_dict["is_main_event"],

                    # Fighter Info
                    "fighter1_id": f1_id,
                    "fighter1_name": fight_dict["fighter1_name"],
                    "fighter2_id": f2_id,
                    "fighter2_name": fight_dict["fighter2_name"],

                    # Target Variables
                    "target_winner": target_winner,
                    "outcome": fight_dict["outcome"],
                    "method": fight_dict["method"],
                    "finish_round": fight_dict["finish_round"],

                    # ELO Rating Features
                    "pre_f1_elo": pre_f1_elo,
                    "pre_f2_elo": pre_f2_elo,
                    "diff_pre_elo": round(pre_f1_elo - pre_f2_elo, 1),

                    # Physical Attributes & Stance
                    "f1_height_cm": f1.get("height_cm"),
                    "f2_height_cm": f2.get("height_cm"),
                    "diff_height_cm": _safe_sub(f1.get("height_cm"), f2.get("height_cm")),

                    "f1_weight_kg": f1.get("weight_kg"),
                    "f2_weight_kg": f2.get("weight_kg"),
                    "diff_weight_kg": _safe_sub(f1.get("weight_kg"), f2.get("weight_kg")),

                    "f1_reach_cm": f1.get("reach_cm"),
                    "f2_reach_cm": f2.get("reach_cm"),
                    "diff_reach_cm": _safe_sub(f1.get("reach_cm"), f2.get("reach_cm")),

                    "f1_ape_index": f1_ape_index,
                    "f2_ape_index": f2_ape_index,
                    "diff_ape_index": _safe_sub(f1_ape_index, f2_ape_index),

                    "f1_reach_ratio": f1_reach_ratio,
                    "f2_reach_ratio": f2_reach_ratio,
                    "diff_reach_ratio": _safe_sub(f1_reach_ratio, f2_reach_ratio, 3),

                    "f1_age": f1_age,
                    "f2_age": f2_age,
                    "diff_age_years": _safe_sub(f1_age, f2_age),

                    "f1_stance": f1.get("stance"),
                    "f2_stance": f2.get("stance"),
                    "is_same_stance": is_same_stance,
                    "is_orthodox_vs_southpaw": is_orthodox_vs_southpaw,

                    # Pre-Fight Status Flags & Streaks (Zero Data Leakage)
                    "pre_f1_ufc_debut": 1 if pre_f1_total == 0 else 0,
                    "pre_f2_ufc_debut": 1 if pre_f2_total == 0 else 0,

                    "pre_f1_wins": pre_f1_wins,
                    "pre_f2_wins": pre_f2_wins,
                    "diff_pre_wins": pre_f1_wins - pre_f2_wins,

                    "pre_f1_losses": pre_f1_losses,
                    "pre_f2_losses": pre_f2_losses,
                    "diff_pre_losses": pre_f1_losses - pre_f2_losses,

                    "pre_f1_total_fights": pre_f1_total,
                    "pre_f2_total_fights": pre_f2_total,
                    "diff_pre_total_fights": pre_f1_total - pre_f2_total,

                    "pre_f1_win_rate": pre_f1_win_rate,
                    "pre_f2_win_rate": pre_f2_win_rate,
                    "diff_pre_win_rate": _safe_sub(pre_f1_win_rate, pre_f2_win_rate, 3),

                    "pre_f1_ko_win_rate": pre_f1_ko_win_rate,
                    "pre_f2_ko_win_rate": pre_f2_ko_win_rate,
                    "diff_pre_ko_win_rate": _safe_sub(pre_f1_ko_win_rate, pre_f2_ko_win_rate, 3),

                    "pre_f1_sub_win_rate": pre_f1_sub_win_rate,
                    "pre_f2_sub_win_rate": pre_f2_sub_win_rate,
                    "diff_pre_sub_win_rate": _safe_sub(pre_f1_sub_win_rate, pre_f2_sub_win_rate, 3),

                    "pre_f1_finish_win_rate": pre_f1_finish_win_rate,
                    "pre_f2_finish_win_rate": pre_f2_finish_win_rate,
                    "diff_pre_finish_win_rate": _safe_sub(pre_f1_finish_win_rate, pre_f2_finish_win_rate, 3),

                    "pre_f1_dec_win_rate": pre_f1_dec_win_rate,
                    "pre_f2_dec_win_rate": pre_f2_dec_win_rate,
                    "diff_pre_dec_win_rate": _safe_sub(pre_f1_dec_win_rate, pre_f2_dec_win_rate, 3),

                    "pre_f1_streak": pre_f1_streak,
                    "pre_f2_streak": pre_f2_streak,
                    "diff_pre_streak": pre_f1_streak - pre_f2_streak,

                    "pre_f1_days_since_last_fight": pre_f1_days_since_last,
                    "pre_f2_days_since_last_fight": pre_f2_days_since_last,
                    "diff_pre_days_since_last_fight": _safe_sub(pre_f1_days_since_last, pre_f2_days_since_last),

                    "pre_f1_win_rate_last3": pre_f1_win_rate_last3,
                    "pre_f2_win_rate_last3": pre_f2_win_rate_last3,
                    "diff_pre_win_rate_last3": _safe_sub(pre_f1_win_rate_last3, pre_f2_win_rate_last3, 3),

                    # Striking Differentials
                    "f1_slpm": f1_slpm,
                    "f2_slpm": f2_slpm,
                    "diff_slpm": _safe_sub(f1_slpm, f2_slpm),

                    "f1_str_acc": f1_str_acc,
                    "f2_str_acc": f2_str_acc,
                    "diff_str_acc": _safe_sub(f1_str_acc, f2_str_acc),

                    "f1_sapm": f1_sapm,
                    "f2_sapm": f2_sapm,
                    "diff_sapm": _safe_sub(f1_sapm, f2_sapm),

                    "f1_strike_efficiency": f1_strike_eff,
                    "f2_strike_efficiency": f2_strike_eff,
                    "diff_strike_efficiency": _safe_sub(f1_strike_eff, f2_strike_eff),

                    "f1_str_def": f1_str_def,
                    "f2_str_def": f2_str_def,
                    "diff_str_def": _safe_sub(f1_str_def, f2_str_def),

                    # Grappling Differentials
                    "f1_td_avg": f1_td_avg,
                    "f2_td_avg": f2_td_avg,
                    "diff_td_avg": _safe_sub(f1_td_avg, f2_td_avg),

                    "f1_td_acc": f1_td_acc,
                    "f2_td_acc": f2_td_acc,
                    "diff_td_acc": _safe_sub(f1_td_acc, f2_td_acc),

                    "f1_td_def": f1_td_def,
                    "f2_td_def": f2_td_def,
                    "diff_td_def": _safe_sub(f1_td_def, f2_td_def),
                }

                dataset.append(feature_row)

                # UPDATE state tracker for F1 and F2 AFTER computing row features for fight
                method_upper = (fight_dict.get("method") or "").upper()

                # Calculate ELO expectations
                e1 = 1.0 / (1.0 + 10.0 ** ((t2["elo"] - t1["elo"]) / 400.0))
                e2 = 1.0 / (1.0 + 10.0 ** ((t1["elo"] - t2["elo"]) / 400.0))
                k = 32.0

                if winner_id == f1_id:
                    score1, score2 = 1.0, 0.0
                elif winner_id == f2_id:
                    score1, score2 = 0.0, 1.0
                else:
                    score1, score2 = 0.5, 0.5

                s1 = fight_stats_map.get((fight_id, f1_id)) if f1_id else None
                s2 = fight_stats_map.get((fight_id, f2_id)) if f2_id else None

                if f1_id:
                    t1["elo"] = t1["elo"] + k * (score1 - e1)
                    if s1 or s2:
                        t1["stats"].append({"own": s1 or {}, "opp": s2 or {}})
                    if event_date_str:
                        t1["last_date"] = event_date_str
                    if winner_id == f1_id:
                        t1["wins"] += 1
                        t1["streak"] = (t1["streak"] + 1) if t1["streak"] > 0 else 1
                        t1["history"].append("win")
                        if "KO" in method_upper or "TKO" in method_upper:
                            t1["ko_wins"] += 1
                        elif "SUB" in method_upper:
                            t1["sub_wins"] += 1
                        elif "DEC" in method_upper:
                            t1["dec_wins"] += 1
                    elif winner_id == f2_id:
                        t1["losses"] += 1
                        t1["streak"] = (t1["streak"] - 1) if t1["streak"] < 0 else -1
                        t1["history"].append("loss")
                    else:
                        t1["draws"] += 1
                        t1["streak"] = 0
                        t1["history"].append("draw")

                if f2_id:
                    t2["elo"] = t2["elo"] + k * (score2 - e2)
                    if s1 or s2:
                        t2["stats"].append({"own": s2 or {}, "opp": s1 or {}})
                    if event_date_str:
                        t2["last_date"] = event_date_str
                    if winner_id == f2_id:
                        t2["wins"] += 1
                        t2["streak"] = (t2["streak"] + 1) if t2["streak"] > 0 else 1
                        t2["history"].append("win")
                        if "KO" in method_upper or "TKO" in method_upper:
                            t2["ko_wins"] += 1
                        elif "SUB" in method_upper:
                            t2["sub_wins"] += 1
                        elif "DEC" in method_upper:
                            t2["dec_wins"] += 1
                    elif winner_id == f1_id:
                        t2["losses"] += 1
                        t2["streak"] = (t2["streak"] - 1) if t2["streak"] < 0 else -1
                        t2["history"].append("loss")
                    else:
                        t2["draws"] += 1
                        t2["streak"] = 0
                        t2["history"].append("draw")

            self._last_history_tracker = history_tracker
            return dataset
        finally:
            conn.close()

    def get_fighter_trackers(self) -> Dict[str, Dict[str, Any]]:
        """Runs dataset generation and returns pre-fight history tracker state for all fighters."""
        if not getattr(self, "_last_history_tracker", None):
            self.build_dataset()
        return getattr(self, "_last_history_tracker", {})

    def export_ml_dataset(self, output_path: str = "data/ml_dataset.csv", output_format: str = "csv") -> None:
        """Builds dataset and writes output to CSV, JSON, Parquet, or Excel file."""
        dataset = self.build_dataset()
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if not dataset:
            logger.warning("No fights found in database to generate ML dataset")
            return

        fmt = output_format.lower()

        if fmt == "json":
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(dataset, f, ensure_ascii=False, indent=2, default=str)
            logger.info(f"[ML Dataset JSON] Exported {len(dataset)} matchups -> {out_path}")

        elif fmt == "parquet":
            try:
                import pyarrow as pa
                import pyarrow.parquet as pq
                table = pa.Table.from_pylist(dataset)
                pq.write_table(table, out_path)
                logger.info(f"[ML Dataset Parquet] Exported {len(dataset)} matchups -> {out_path}")
            except ImportError:
                logger.error("pyarrow is required for Parquet export. Run: pip install pyarrow")

        elif fmt in ("excel", "xlsx"):
            try:
                from openpyxl import Workbook
                wb = Workbook()
                ws = wb.active
                ws.title = "ML_Dataset"
                headers = list(dataset[0].keys())
                ws.append(headers)
                for r in dataset:
                    ws.append([str(v) if v is not None else "" for v in r.values()])
                wb.save(out_path)
                logger.info(f"[ML Dataset Excel] Exported {len(dataset)} matchups -> {out_path}")
            except ImportError:
                logger.error("openpyxl is required for Excel export. Run: pip install openpyxl")

        else:
            headers = dataset[0].keys()
            with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(dataset)
            logger.info(f"[ML Dataset CSV] Exported {len(dataset)} matchups -> {out_path}")
