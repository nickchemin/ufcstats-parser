"""
FastAPI REST API server & Web Dashboard for UFCStats.

Provides HTTP REST endpoints for querying events, fight cards, detailed fight metrics,
fighter profiles, matchup predictions, data health diagnostics, and ML matchup datasets.
"""

from datetime import date
import math
from pathlib import Path
import sqlite3
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from anyio import to_thread

from .storage.database import Database
from .storage.checker import DatabaseChecker
from .storage.ml_dataset import MLDatasetGenerator
from .ml.predictor import FightPredictor

app = FastAPI(
    title="UFCStats REST API & Web Dashboard",
    description="High-performance REST API & Interactive Dashboard for UFC events, fights, fighter profiles, and ML prediction.",
    version="1.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

DB_PATH = "ufc_data.db"
WEB_DIR = Path(__file__).parent.parent / "web"
_GLOBAL_PREDICTOR: Optional[FightPredictor] = None
_PRESERVED_TRACKERS: Optional[Dict[str, Any]] = None


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/app", tags=["General"])
    async def serve_web_app():
        """Serves interactive Web UI Dashboard."""
        return FileResponse(WEB_DIR / "index.html")


def set_db_path(db_path: str):
    global DB_PATH, _GLOBAL_PREDICTOR, _PRESERVED_TRACKERS
    DB_PATH = db_path
    _GLOBAL_PREDICTOR = None
    _PRESERVED_TRACKERS = None


def _get_connection(db_path: str = None) -> sqlite3.Connection:
    target = db_path or DB_PATH
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    return conn


def _get_global_predictor() -> FightPredictor:
    global _GLOBAL_PREDICTOR
    if _GLOBAL_PREDICTOR is None:
        _GLOBAL_PREDICTOR = FightPredictor(DB_PATH)
        _GLOBAL_PREDICTOR.load_model()
    return _GLOBAL_PREDICTOR


def _get_fighter_trackers() -> Dict[str, Any]:
    global _PRESERVED_TRACKERS
    if _PRESERVED_TRACKERS is None:
        generator = MLDatasetGenerator(DB_PATH)
        generator.build_dataset()
        _PRESERVED_TRACKERS = getattr(generator, "_last_history_tracker", {})
    return _PRESERVED_TRACKERS


@app.get("/", tags=["General"])
async def root():
    """API root status endpoint."""
    return {
        "name": "UFCStats REST API & Dashboard",
        "version": "1.3.0",
        "web_dashboard": "/app",
        "docs": "/docs",
        "endpoints": [
            "/app",
            "/api/v1/events",
            "/api/v1/events/upcoming",
            "/api/v1/events/{event_id}",
            "/api/v1/fights/{fight_id}",
            "/api/v1/fighters",
            "/api/v1/fighters/{fighter_id}",
            "/api/v1/matchup",
            "/api/v1/predict",
            "/api/v1/ml-dataset",
            "/api/v1/stats/summary",
            "/api/v1/health",
        ],
    }


def _fetch_events(q: Optional[str], limit: int, offset: int):
    conn = _get_connection()
    try:
        if q:
            count = conn.execute("SELECT COUNT(*) FROM events WHERE name LIKE ?", (f"%{q}%",)).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM events WHERE name LIKE ? ORDER BY date DESC LIMIT ? OFFSET ?",
                (f"%{q}%", limit, offset),
            ).fetchall()
        else:
            count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM events ORDER BY date DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()

        page = (offset // limit) + 1
        pages = math.ceil(count / limit) if count > 0 else 1
        return {
            "total": count,
            "page": page,
            "limit": limit,
            "pages": pages,
            "data": [dict(r) for r in rows],
        }
    finally:
        conn.close()


@app.get("/api/v1/events", tags=["Events"])
async def get_events(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    q: Optional[str] = Query(default=None, description="Search event name substring"),
):
    """Retrieves paginated list of UFC events with metadata and optional search query."""
    return await to_thread.run_sync(_fetch_events, q, limit, offset)


def _fetch_upcoming_events():
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM events WHERE date IS NULL OR date >= date('now') ORDER BY date ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/v1/events/upcoming", tags=["Events"])
async def get_upcoming_events():
    """Retrieves list of upcoming scheduled UFC events."""
    return await to_thread.run_sync(_fetch_upcoming_events)


def _fetch_event_details(event_id: str):
    conn = _get_connection()
    try:
        event = conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        if not event:
            return None
        fights = conn.execute("SELECT * FROM fights WHERE event_id = ?", (event_id,)).fetchall()
        result = dict(event)
        result["fights"] = [dict(f) for f in fights]
        return result
    finally:
        conn.close()


@app.get("/api/v1/events/{event_id}", tags=["Events"])
async def get_event_details(event_id: str):
    """Retrieves single event details and its fight card."""
    res = await to_thread.run_sync(_fetch_event_details, event_id)
    if not res:
        raise HTTPException(status_code=404, detail="Event not found")
    return res


def _fetch_fight_details(fight_id: str):
    conn = _get_connection()
    try:
        fight = conn.execute("SELECT * FROM fights WHERE fight_id = ?", (fight_id,)).fetchone()
        if not fight:
            return None
        fight_stats = conn.execute("SELECT * FROM fight_stats WHERE fight_id = ?", (fight_id,)).fetchall()
        round_stats = conn.execute("SELECT * FROM round_stats WHERE fight_id = ? ORDER BY round_number, corner", (fight_id,)).fetchall()

        result = dict(fight)
        result["totals"] = [dict(s) for s in fight_stats]
        result["rounds"] = [dict(r) for r in round_stats]
        return result
    finally:
        conn.close()


@app.get("/api/v1/fights/{fight_id}", tags=["Fights"])
async def get_fight_details(fight_id: str):
    """Retrieves fight outcome, overall totals, and round-by-round statistics."""
    res = await to_thread.run_sync(_fetch_fight_details, fight_id)
    if not res:
        raise HTTPException(status_code=404, detail="Fight not found")
    return res


def _search_fighters(q: Optional[str], limit: int, offset: int):
    conn = _get_connection()
    try:
        if q:
            pattern = f"%{q}%"
            count_query = "SELECT COUNT(*) FROM fighters WHERE first_name LIKE ? OR last_name LIKE ? OR nickname LIKE ?"
            count = conn.execute(count_query, (pattern, pattern, pattern)).fetchone()[0]
            query = """
                SELECT * FROM fighters 
                WHERE first_name LIKE ? OR last_name LIKE ? OR nickname LIKE ?
                LIMIT ? OFFSET ?
            """
            rows = conn.execute(query, (pattern, pattern, pattern, limit, offset)).fetchall()
        else:
            count = conn.execute("SELECT COUNT(*) FROM fighters").fetchone()[0]
            query = "SELECT * FROM fighters LIMIT ? OFFSET ?"
            rows = conn.execute(query, (limit, offset)).fetchall()

        page = (offset // limit) + 1
        pages = math.ceil(count / limit) if count > 0 else 1
        return {
            "total": count,
            "page": page,
            "limit": limit,
            "pages": pages,
            "data": [dict(r) for r in rows],
        }
    finally:
        conn.close()


@app.get("/api/v1/fighters", tags=["Fighters"])
async def search_fighters(
    q: Optional[str] = Query(default=None, description="Search fighter name"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Searches and lists fighter profiles with pagination metadata."""
    return await to_thread.run_sync(_search_fighters, q, limit, offset)


def _fetch_fighter_profile(fighter_id: str):
    conn = _get_connection()
    try:
        fighter = conn.execute("SELECT * FROM fighters WHERE fighter_id = ?", (fighter_id,)).fetchone()
        return dict(fighter) if fighter else None
    finally:
        conn.close()


@app.get("/api/v1/fighters/{fighter_id}", tags=["Fighters"])
async def get_fighter_profile(fighter_id: str):
    """Retrieves detailed fighter bio and career metrics."""
    res = await to_thread.run_sync(_fetch_fighter_profile, fighter_id)
    if not res:
        raise HTTPException(status_code=404, detail="Fighter profile not found")
    return res


def _fetch_matchup(fighter1_id: str, fighter2_id: str):
    conn = _get_connection()
    try:
        f1 = conn.execute("SELECT * FROM fighters WHERE fighter_id = ?", (fighter1_id,)).fetchone()
        f2 = conn.execute("SELECT * FROM fighters WHERE fighter_id = ?", (fighter2_id,)).fetchone()
        if not f1 or not f2:
            return None
        d1, d2 = dict(f1), dict(f2)
        h1 = d1.get("height_cm")
        h2 = d2.get("height_cm")
        r1 = d1.get("reach_cm")
        r2 = d2.get("reach_cm")

        return {
            "fighter1": d1,
            "fighter2": d2,
            "differentials": {
                "height_cm": round(h1 - h2, 1) if h1 and h2 else None,
                "reach_cm": round(r1 - r2, 1) if r1 and r2 else None,
                "ape_index_f1": round(r1 - h1, 1) if r1 and h1 else None,
                "ape_index_f2": round(r2 - h2, 1) if r2 and h2 else None,
                "slpm": round((d1.get("slpm") or 0) - (d2.get("slpm") or 0), 2),
                "td_avg": round((d1.get("td_avg") or 0) - (d2.get("td_avg") or 0), 2),
            },
        }
    finally:
        conn.close()


@app.get("/api/v1/matchup", tags=["Fighters"])
async def get_matchup(
    fighter1_id: str = Query(..., description="Fighter 1 ID"),
    fighter2_id: str = Query(..., description="Fighter 2 ID"),
):
    """Compares two fighters directly and returns physical and career differentials."""
    res = await to_thread.run_sync(_fetch_matchup, fighter1_id, fighter2_id)
    if not res:
        raise HTTPException(status_code=404, detail="One or both fighter profiles not found")
    return res


def _predict_matchup(fighter1_id: str, fighter2_id: str):
    conn = _get_connection()
    try:
        f1 = conn.execute("SELECT * FROM fighters WHERE fighter_id = ?", (fighter1_id,)).fetchone()
        f2 = conn.execute("SELECT * FROM fighters WHERE fighter_id = ?", (fighter2_id,)).fetchone()
        if not f1 or not f2:
            return None
        d1, d2 = dict(f1), dict(f2)

        trackers = _get_fighter_trackers()
        t1 = trackers.get(fighter1_id, {"elo": 1500.0, "wins": d1.get("wins") or 0, "losses": d1.get("losses") or 0, "streak": 0})
        t2 = trackers.get(fighter2_id, {"elo": 1500.0, "wins": d2.get("wins") or 0, "losses": d2.get("losses") or 0, "streak": 0})

        today = date.today()
        def get_age(dob_str):
            if not dob_str: return None
            try:
                d = date.fromisoformat(str(dob_str))
                return round((today - d).days / 365.25, 1)
            except Exception:
                return None

        feat1 = {
            "pre_f1_elo": t1.get("elo", 1500.0),
            "height_cm": d1.get("height_cm"),
            "weight_kg": d1.get("weight_kg"),
            "reach_cm": d1.get("reach_cm"),
            "stance": d1.get("stance"),
            "age": get_age(d1.get("dob")),
            "wins": t1.get("wins", 0),
            "losses": t1.get("losses", 0),
            "streak": t1.get("streak", 0),
            "slpm": d1.get("slpm"),
            "str_acc": d1.get("str_acc"),
            "sapm": d1.get("sapm"),
            "str_def": d1.get("str_def"),
            "td_avg": d1.get("td_avg"),
            "td_acc": d1.get("td_acc"),
            "td_def": d1.get("td_def"),
        }

        feat2 = {
            "pre_f2_elo": t2.get("elo", 1500.0),
            "height_cm": d2.get("height_cm"),
            "weight_kg": d2.get("weight_kg"),
            "reach_cm": d2.get("reach_cm"),
            "stance": d2.get("stance"),
            "age": get_age(d2.get("dob")),
            "wins": t2.get("wins", 0),
            "losses": t2.get("losses", 0),
            "streak": t2.get("streak", 0),
            "slpm": d2.get("slpm"),
            "str_acc": d2.get("str_acc"),
            "sapm": d2.get("sapm"),
            "str_def": d2.get("str_def"),
            "td_avg": d2.get("td_avg"),
            "td_acc": d2.get("td_acc"),
            "td_def": d2.get("td_def"),
        }

        predictor = _get_global_predictor()
        if not predictor.is_trained:
            predictor.load_model()

        prediction = predictor.predict_matchup(feat1, feat2)
        prediction["fighter1"] = d1
        prediction["fighter2"] = d2
        return prediction
    finally:
        conn.close()


@app.get("/api/v1/predict", tags=["Machine Learning"])
async def predict_fight(
    fighter1_id: str = Query(..., description="Fighter 1 ID"),
    fighter2_id: str = Query(..., description="Fighter 2 ID"),
):
    """Predicts win probabilities and matchup outcome between two fighters."""
    res = await to_thread.run_sync(_predict_matchup, fighter1_id, fighter2_id)
    if not res:
        raise HTTPException(status_code=404, detail="One or both fighter profiles not found")

    if not res.get("is_trained", True):
        raise HTTPException(
            status_code=400,
            detail="ML Model is not trained. Please run python cli.py train first to build model parameters.",
        )

    return res


@app.get("/api/v1/ml-dataset", tags=["Machine Learning"])
async def get_ml_dataset(limit: int = Query(default=100, ge=1, le=5000)):
    """Generates Machine Learning feature matchup dataset with comparative differentials."""
    def _gen():
        generator = MLDatasetGenerator(DB_PATH)
        dataset = generator.build_dataset()
        return dataset[:limit]
    return await to_thread.run_sync(_gen)


@app.get("/api/v1/stats/summary", tags=["General"])
async def get_db_summary():
    """Returns database table row counts and summary metrics."""
    def _summary():
        db = Database(DB_PATH)
        return db.summary()
    return await to_thread.run_sync(_summary)


@app.get("/api/v1/health", tags=["General"])
async def get_health_diagnostics():
    """Returns database data quality & health score metrics."""
    def _health():
        checker = DatabaseChecker(DB_PATH)
        return checker.run_diagnostics()
    return await to_thread.run_sync(_health)
