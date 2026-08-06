"""
SQLite database manager for storing UFC data.

Manages relational tables: events, fighters, fights, fight_stats, round_stats.
Uses upsert logic (ON CONFLICT DO UPDATE) for incremental updates.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, List, Optional

from ..storage.models import Event, Fighter, Fight, FighterFightStats, RoundStats
from ..utils.logger import get_logger

logger = get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id    TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    name        TEXT NOT NULL,
    date        TEXT,
    location    TEXT,
    fights_count INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fighters (
    fighter_id  TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    first_name  TEXT,
    last_name   TEXT,
    nickname    TEXT,
    height_cm   REAL,
    weight_kg   REAL,
    reach_cm    REAL,
    stance      TEXT,
    dob         TEXT,
    wins        INTEGER DEFAULT 0,
    losses      INTEGER DEFAULT 0,
    draws       INTEGER DEFAULT 0,
    no_contests INTEGER DEFAULT 0,
    slpm        REAL,
    str_acc     REAL,
    sapm        REAL,
    str_def     REAL,
    td_avg      REAL,
    td_acc      REAL,
    td_def      REAL,
    sub_avg     REAL,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fights (
    fight_id        TEXT PRIMARY KEY,
    url             TEXT NOT NULL,
    event_id        TEXT NOT NULL,
    fighter1_id     TEXT,
    fighter1_name   TEXT,
    fighter2_id     TEXT,
    fighter2_name   TEXT,
    winner_id       TEXT,
    outcome         TEXT,
    method          TEXT,
    method_detail   TEXT,
    round           INTEGER,
    time            TEXT,
    time_format     TEXT,
    referee         TEXT,
    weight_class    TEXT,
    title_fight     INTEGER DEFAULT 0,
    is_main_event   INTEGER DEFAULT 0,
    bonus           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES events(event_id)
);

CREATE TABLE IF NOT EXISTS fight_stats (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    fight_id                TEXT NOT NULL,
    fighter_id              TEXT,
    fighter_name            TEXT,
    corner                  TEXT NOT NULL,
    kd                      INTEGER DEFAULT 0,
    sig_str_landed          INTEGER DEFAULT 0,
    sig_str_attempted       INTEGER DEFAULT 0,
    total_str_landed        INTEGER DEFAULT 0,
    total_str_attempted     INTEGER DEFAULT 0,
    td_landed               INTEGER DEFAULT 0,
    td_attempted            INTEGER DEFAULT 0,
    sub_att                 INTEGER DEFAULT 0,
    rev                     INTEGER DEFAULT 0,
    ctrl_seconds            INTEGER DEFAULT 0,
    sig_head_landed         INTEGER DEFAULT 0,
    sig_head_attempted      INTEGER DEFAULT 0,
    sig_body_landed         INTEGER DEFAULT 0,
    sig_body_attempted      INTEGER DEFAULT 0,
    sig_leg_landed          INTEGER DEFAULT 0,
    sig_leg_attempted       INTEGER DEFAULT 0,
    sig_distance_landed     INTEGER DEFAULT 0,
    sig_distance_attempted  INTEGER DEFAULT 0,
    sig_clinch_landed       INTEGER DEFAULT 0,
    sig_clinch_attempted    INTEGER DEFAULT 0,
    sig_ground_landed       INTEGER DEFAULT 0,
    sig_ground_attempted    INTEGER DEFAULT 0,
    UNIQUE(fight_id, corner),
    FOREIGN KEY (fight_id) REFERENCES fights(fight_id)
);

CREATE TABLE IF NOT EXISTS round_stats (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    fight_id                TEXT NOT NULL,
    round_number            INTEGER NOT NULL,
    fighter_id              TEXT,
    fighter_name            TEXT,
    corner                  TEXT NOT NULL,
    kd                      INTEGER DEFAULT 0,
    sig_str_landed          INTEGER DEFAULT 0,
    sig_str_attempted       INTEGER DEFAULT 0,
    total_str_landed        INTEGER DEFAULT 0,
    total_str_attempted     INTEGER DEFAULT 0,
    td_landed               INTEGER DEFAULT 0,
    td_attempted            INTEGER DEFAULT 0,
    sub_att                 INTEGER DEFAULT 0,
    rev                     INTEGER DEFAULT 0,
    ctrl_seconds            INTEGER DEFAULT 0,
    sig_head_landed         INTEGER DEFAULT 0,
    sig_head_attempted      INTEGER DEFAULT 0,
    sig_body_landed         INTEGER DEFAULT 0,
    sig_body_attempted      INTEGER DEFAULT 0,
    sig_leg_landed          INTEGER DEFAULT 0,
    sig_leg_attempted       INTEGER DEFAULT 0,
    sig_distance_landed     INTEGER DEFAULT 0,
    sig_distance_attempted  INTEGER DEFAULT 0,
    sig_clinch_landed       INTEGER DEFAULT 0,
    sig_clinch_attempted    INTEGER DEFAULT 0,
    sig_ground_landed       INTEGER DEFAULT 0,
    sig_ground_attempted    INTEGER DEFAULT 0,
    UNIQUE(fight_id, round_number, corner),
    FOREIGN KEY (fight_id) REFERENCES fights(fight_id)
);

CREATE INDEX IF NOT EXISTS idx_fights_event ON fights(event_id);
CREATE INDEX IF NOT EXISTS idx_fights_fighter1 ON fights(fighter1_id);
CREATE INDEX IF NOT EXISTS idx_fights_fighter2 ON fights(fighter2_id);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(date);
CREATE INDEX IF NOT EXISTS idx_fighters_name ON fighters(first_name, last_name);
CREATE INDEX IF NOT EXISTS idx_fight_stats_fight ON fight_stats(fight_id);
CREATE INDEX IF NOT EXISTS idx_round_stats_fight ON round_stats(fight_id);
"""


class Database:
    """SQLite Database manager for UFC data."""

    def __init__(self, db_path: str = "ufc_data.db"):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Initializes tables if they do not exist."""
        with self._connect() as conn:
            conn.executescript(SCHEMA)
        logger.info(f"Database ready: {self.db_path}")

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def upsert_event(self, event: Event) -> None:
        sql = """
        INSERT INTO events (event_id, url, name, date, location, fights_count, updated_at)
        VALUES (:event_id, :url, :name, :event_date, :location, :fights_count, datetime('now'))
        ON CONFLICT(event_id) DO UPDATE SET
            name=excluded.name, date=excluded.date,
            location=excluded.location, fights_count=excluded.fights_count,
            updated_at=excluded.updated_at
        """
        with self._connect() as conn:
            data = event.model_dump()
            data["event_date"] = str(data["event_date"]) if data["event_date"] else None
            conn.execute(sql, data)

    def get_event_ids(self) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT event_id FROM events").fetchall()
            return [r["event_id"] for r in rows]

    # ------------------------------------------------------------------
    # Fighters
    # ------------------------------------------------------------------

    def upsert_fighter(self, fighter: Fighter) -> None:
        sql = """
        INSERT INTO fighters (
            fighter_id, url, first_name, last_name, nickname,
            height_cm, weight_kg, reach_cm, stance, dob,
            wins, losses, draws, no_contests,
            slpm, str_acc, sapm, str_def, td_avg, td_acc, td_def, sub_avg,
            updated_at
        ) VALUES (
            :fighter_id, :url, :first_name, :last_name, :nickname,
            :height_cm, :weight_kg, :reach_cm, :stance, :dob,
            :wins, :losses, :draws, :no_contests,
            :slpm, :str_acc, :sapm, :str_def, :td_avg, :td_acc, :td_def, :sub_avg,
            datetime('now')
        )
        ON CONFLICT(fighter_id) DO UPDATE SET
            first_name=COALESCE(excluded.first_name, fighters.first_name),
            last_name=COALESCE(excluded.last_name, fighters.last_name),
            nickname=COALESCE(excluded.nickname, fighters.nickname),
            height_cm=COALESCE(excluded.height_cm, fighters.height_cm),
            weight_kg=COALESCE(excluded.weight_kg, fighters.weight_kg),
            reach_cm=COALESCE(excluded.reach_cm, fighters.reach_cm),
            stance=COALESCE(excluded.stance, fighters.stance),
            dob=COALESCE(excluded.dob, fighters.dob),
            wins=COALESCE(excluded.wins, fighters.wins),
            losses=COALESCE(excluded.losses, fighters.losses),
            draws=COALESCE(excluded.draws, fighters.draws),
            no_contests=COALESCE(excluded.no_contests, fighters.no_contests),
            slpm=COALESCE(excluded.slpm, fighters.slpm),
            str_acc=COALESCE(excluded.str_acc, fighters.str_acc),
            sapm=COALESCE(excluded.sapm, fighters.sapm),
            str_def=COALESCE(excluded.str_def, fighters.str_def),
            td_avg=COALESCE(excluded.td_avg, fighters.td_avg),
            td_acc=COALESCE(excluded.td_acc, fighters.td_acc),
            td_def=COALESCE(excluded.td_def, fighters.td_def),
            sub_avg=COALESCE(excluded.sub_avg, fighters.sub_avg),
            updated_at=excluded.updated_at
        """
        with self._connect() as conn:
            data = fighter.model_dump()
            data["dob"] = str(data["dob"]) if data["dob"] else None
            conn.execute(sql, data)

    def get_fighter_ids(self) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT fighter_id FROM fighters").fetchall()
            return [r["fighter_id"] for r in rows]

    def get_complete_fighter_ids(self) -> List[str]:
        """Returns list of fighter IDs whose full bio profiles have been parsed into DB."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT fighter_id FROM fighters WHERE height_cm IS NOT NULL OR slpm IS NOT NULL OR stance IS NOT NULL OR wins IS NOT NULL"
            ).fetchall()
            return [r["fighter_id"] for r in rows]

    # ------------------------------------------------------------------
    # Fights
    # ------------------------------------------------------------------

    def upsert_fight(self, fight: Fight) -> None:
        sql = """
        INSERT INTO fights (
            fight_id, url, event_id,
            fighter1_id, fighter1_name, fighter2_id, fighter2_name,
            winner_id, outcome, method, method_detail,
            round, time, time_format, referee, weight_class,
            title_fight, is_main_event, bonus, updated_at
        ) VALUES (
            :fight_id, :url, :event_id,
            :fighter1_id, :fighter1_name, :fighter2_id, :fighter2_name,
            :winner_id, :outcome, :method, :method_detail,
            :round, :time, :time_format, :referee, :weight_class,
            :title_fight, :is_main_event, :bonus, datetime('now')
        )
        ON CONFLICT(fight_id) DO UPDATE SET
            winner_id=excluded.winner_id, outcome=excluded.outcome,
            method=excluded.method, method_detail=excluded.method_detail,
            round=excluded.round, time=excluded.time,
            referee=excluded.referee, weight_class=excluded.weight_class,
            title_fight=excluded.title_fight, is_main_event=excluded.is_main_event,
            bonus=excluded.bonus, updated_at=excluded.updated_at
        """
        with self._connect() as conn:
            data = fight.model_dump()
            data["title_fight"] = int(data["title_fight"])
            data["is_main_event"] = int(data["is_main_event"])
            conn.execute(sql, data)

    def get_fight_ids_for_event(self, event_id: str) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT fight_id FROM fights WHERE event_id=?", (event_id,)
            ).fetchall()
            return [r["fight_id"] for r in rows]

    # ------------------------------------------------------------------
    # Fight Stats
    # ------------------------------------------------------------------

    def upsert_fight_stats(self, stats: FighterFightStats) -> None:
        sql = """
        INSERT INTO fight_stats (
            fight_id, fighter_id, fighter_name, corner,
            kd, sig_str_landed, sig_str_attempted, total_str_landed, total_str_attempted,
            td_landed, td_attempted, sub_att, rev, ctrl_seconds,
            sig_head_landed, sig_head_attempted, sig_body_landed, sig_body_attempted,
            sig_leg_landed, sig_leg_attempted,
            sig_distance_landed, sig_distance_attempted,
            sig_clinch_landed, sig_clinch_attempted,
            sig_ground_landed, sig_ground_attempted
        ) VALUES (
            :fight_id, :fighter_id, :fighter_name, :corner,
            :kd, :sig_str_landed, :sig_str_attempted, :total_str_landed, :total_str_attempted,
            :td_landed, :td_attempted, :sub_att, :rev, :ctrl_seconds,
            :sig_head_landed, :sig_head_attempted, :sig_body_landed, :sig_body_attempted,
            :sig_leg_landed, :sig_leg_attempted,
            :sig_distance_landed, :sig_distance_attempted,
            :sig_clinch_landed, :sig_clinch_attempted,
            :sig_ground_landed, :sig_ground_attempted
        )
        ON CONFLICT(fight_id, corner) DO UPDATE SET
            fighter_id=excluded.fighter_id, kd=excluded.kd,
            sig_str_landed=excluded.sig_str_landed, sig_str_attempted=excluded.sig_str_attempted,
            total_str_landed=excluded.total_str_landed, total_str_attempted=excluded.total_str_attempted,
            td_landed=excluded.td_landed, td_attempted=excluded.td_attempted,
            sub_att=excluded.sub_att, rev=excluded.rev, ctrl_seconds=excluded.ctrl_seconds,
            sig_head_landed=excluded.sig_head_landed, sig_head_attempted=excluded.sig_head_attempted,
            sig_body_landed=excluded.sig_body_landed, sig_body_attempted=excluded.sig_body_attempted,
            sig_leg_landed=excluded.sig_leg_landed, sig_leg_attempted=excluded.sig_leg_attempted,
            sig_distance_landed=excluded.sig_distance_landed,
            sig_distance_attempted=excluded.sig_distance_attempted,
            sig_clinch_landed=excluded.sig_clinch_landed, sig_clinch_attempted=excluded.sig_clinch_attempted,
            sig_ground_landed=excluded.sig_ground_landed, sig_ground_attempted=excluded.sig_ground_attempted
        """
        with self._connect() as conn:
            conn.execute(sql, stats.model_dump())

    def upsert_round_stats(self, stats: RoundStats) -> None:
        sql = """
        INSERT INTO round_stats (
            fight_id, round_number, fighter_id, fighter_name, corner,
            kd, sig_str_landed, sig_str_attempted, total_str_landed, total_str_attempted,
            td_landed, td_attempted, sub_att, rev, ctrl_seconds,
            sig_head_landed, sig_head_attempted, sig_body_landed, sig_body_attempted,
            sig_leg_landed, sig_leg_attempted,
            sig_distance_landed, sig_distance_attempted,
            sig_clinch_landed, sig_clinch_attempted,
            sig_ground_landed, sig_ground_attempted
        ) VALUES (
            :fight_id, :round_number, :fighter_id, :fighter_name, :corner,
            :kd, :sig_str_landed, :sig_str_attempted, :total_str_landed, :total_str_attempted,
            :td_landed, :td_attempted, :sub_att, :rev, :ctrl_seconds,
            :sig_head_landed, :sig_head_attempted, :sig_body_landed, :sig_body_attempted,
            :sig_leg_landed, :sig_leg_attempted,
            :sig_distance_landed, :sig_distance_attempted,
            :sig_clinch_landed, :sig_clinch_attempted,
            :sig_ground_landed, :sig_ground_attempted
        )
        ON CONFLICT(fight_id, round_number, corner) DO UPDATE SET
            kd=excluded.kd, sig_str_landed=excluded.sig_str_landed,
            sig_str_attempted=excluded.sig_str_attempted,
            total_str_landed=excluded.total_str_landed,
            td_landed=excluded.td_landed, td_attempted=excluded.td_attempted,
            sub_att=excluded.sub_att, rev=excluded.rev, ctrl_seconds=excluded.ctrl_seconds
        """
        with self._connect() as conn:
            conn.execute(sql, stats.model_dump())

    # ------------------------------------------------------------------
    # Summary Stats
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """Returns database entity counts."""
        with self._connect() as conn:
            events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            fighters = conn.execute("SELECT COUNT(*) FROM fighters").fetchone()[0]
            fights = conn.execute("SELECT COUNT(*) FROM fights").fetchone()[0]
            rounds = conn.execute("SELECT COUNT(*) FROM round_stats").fetchone()[0]
        return {
            "events": events,
            "fighters": fighters,
            "fights": fights,
            "round_stats_rows": rounds,
        }
