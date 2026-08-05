"""
Data export module for JSON and CSV output formats.
"""

import csv
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Any

from ..utils.logger import get_logger

logger = get_logger(__name__)

TABLES = ["events", "fighters", "fights", "fight_stats", "round_stats"]


class Exporter:
    """Exports SQLite data to JSON and CSV formats."""

    def __init__(self, db_path: str = "ufc_data.db"):
        self.db_path = Path(db_path)

    def _load_table(self, table: str) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def export_json(self, output_dir: str = "data", tables: List[str] = None) -> None:
        """Exports specified database tables to JSON files."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        tables = tables or TABLES

        for table in tables:
            rows = self._load_table(table)
            path = out / f"{table}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2, default=str)
            logger.info(f"[JSON] {table}: {len(rows)} records -> {path}")

    def export_csv(self, output_dir: str = "data", tables: List[str] = None) -> None:
        """Exports specified database tables to CSV files."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        tables = tables or TABLES

        for table in tables:
            rows = self._load_table(table)
            if not rows:
                logger.warning(f"[CSV] {table}: empty table")
                continue
            path = out / f"{table}.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            logger.info(f"[CSV] {table}: {len(rows)} records -> {path}")

    def export_all(self, output_dir: str = "data") -> None:
        """Exports all database tables to both JSON and CSV files."""
        logger.info(f"Exporting data to {output_dir}/")
        self.export_json(output_dir)
        self.export_csv(output_dir)
        logger.info("Export completed")
