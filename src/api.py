"""
FastAPI REST API server for UFCStats.

Provides HTTP REST endpoints for querying events, fight cards, detailed fight metrics,
fighter profiles, data health diagnostics, and ML matchup datasets.
"""

import sqlite3
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .storage.database import Database
from .storage.checker import DatabaseChecker
from .storage.ml_dataset import MLDatasetGenerator

app = FastAPI(
    title="UFCStats REST API",
    description="High-performance REST API for UFC events, fights, fighter profiles, and ML datasets.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

DB_PATH = "ufc_data.db"


def set_db_path(db_path: str):
    global DB_PATH
    DB_PATH = db_path


def _get_connection(db_path: str = None) -> sqlite3.Connection:
    target = db_path or DB_PATH
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    return conn


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.get("/", tags=["General"])
def root():
    """API root status endpoint."""
    return {
        "name": "UFCStats REST API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": [
            "/api/v1/events",
            "/api/v1/fights/{fight_id}",
            "/api/v1/fighters",
            "/api/v1/fighters/{fighter_id}",
            "/api/v1/ml-dataset",
            "/api/v1/health",
        ],
    }


@app.get("/api/v1/events", tags=["Events"])
def get_events(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    q: Optional[str] = Query(default=None, description="Search event name substring"),
):
    """Retrieves list of UFC events with pagination and optional search query."""
    conn = _get_connection()
    try:
        if q:
            query = "SELECT * FROM events WHERE name LIKE ? ORDER BY date DESC LIMIT ? OFFSET ?"
            rows = conn.execute(query, (f"%{q}%", limit, offset)).fetchall()
        else:
            query = "SELECT * FROM events ORDER BY date DESC LIMIT ? OFFSET ?"
            rows = conn.execute(query, (limit, offset)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/v1/events/{event_id}", tags=["Events"])
def get_event_details(event_id: str):
    """Retrieves single event details and its fight card."""
    conn = _get_connection()
    try:
        event = conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        fights = conn.execute("SELECT * FROM fights WHERE event_id = ?", (event_id,)).fetchall()
        result = dict(event)
        result["fights"] = [dict(f) for f in fights]
        return result
    finally:
        conn.close()


@app.get("/api/v1/fights/{fight_id}", tags=["Fights"])
def get_fight_details(fight_id: str):
    """Retrieves fight outcome, overall totals, and round-by-round statistics."""
    conn = _get_connection()
    try:
        fight = conn.execute("SELECT * FROM fights WHERE fight_id = ?", (fight_id,)).fetchone()
        if not fight:
            raise HTTPException(status_code=404, detail="Fight not found")
        fight_stats = conn.execute("SELECT * FROM fight_stats WHERE fight_id = ?", (fight_id,)).fetchall()
        round_stats = conn.execute("SELECT * FROM round_stats WHERE fight_id = ? ORDER BY round_number, corner", (fight_id,)).fetchall()

        result = dict(fight)
        result["totals"] = [dict(s) for s in fight_stats]
        result["rounds"] = [dict(r) for r in round_stats]
        return result
    finally:
        conn.close()


@app.get("/api/v1/fighters", tags=["Fighters"])
def search_fighters(
    q: Optional[str] = Query(default=None, description="Search fighter name"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Searches and lists fighter profiles."""
    conn = _get_connection()
    try:
        if q:
            query = """
                SELECT * FROM fighters 
                WHERE first_name LIKE ? OR last_name LIKE ? OR nickname LIKE ?
                LIMIT ? OFFSET ?
            """
            pattern = f"%{q}%"
            rows = conn.execute(query, (pattern, pattern, pattern, limit, offset)).fetchall()
        else:
            query = "SELECT * FROM fighters LIMIT ? OFFSET ?"
            rows = conn.execute(query, (limit, offset)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/v1/fighters/{fighter_id}", tags=["Fighters"])
def get_fighter_profile(fighter_id: str):
    """Retrieves detailed fighter bio and career metrics."""
    conn = _get_connection()
    try:
        fighter = conn.execute("SELECT * FROM fighters WHERE fighter_id = ?", (fighter_id,)).fetchone()
        if not fighter:
            raise HTTPException(status_code=404, detail="Fighter profile not found")
        return dict(fighter)
    finally:
        conn.close()


@app.get("/api/v1/ml-dataset", tags=["Machine Learning"])
def get_ml_dataset(limit: int = Query(default=100, ge=1, le=5000)):
    """Generates Machine Learning feature matchup dataset with comparative differentials."""
    generator = MLDatasetGenerator(DB_PATH)
    dataset = generator.build_dataset()
    return dataset[:limit]


@app.get("/api/v1/health", tags=["General"])
def get_health_diagnostics():
    """Returns database data quality & health score metrics."""
    checker = DatabaseChecker(DB_PATH)
    return checker.run_diagnostics()
