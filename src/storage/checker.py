"""
Database integrity and data quality checker.

Analyzes stored SQLite records to detect orphan foreign keys, missing fighter profiles,
unparsed fight statistics, and data anomalies.
"""

from pathlib import Path
import sqlite3
from typing import Dict, Any, List

from ..utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseChecker:
    """Performs integrity checks and quality diagnostics on UFC SQLite database."""

    def __init__(self, db_path: str = "ufc_data.db"):
        self.db_path = Path(db_path)

    def run_diagnostics(self) -> Dict[str, Any]:
        """
        Executes diagnostic checks across all database tables.

        Returns:
            Dictionary containing diagnostic metrics and issue counts.
        """
        if not self.db_path.exists():
            return {"error": f"Database file not found: {self.db_path}"}

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        try:
            # 1. Row counts
            events_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            fights_count = conn.execute("SELECT COUNT(*) FROM fights").fetchone()[0]
            fighters_count = conn.execute("SELECT COUNT(*) FROM fighters").fetchone()[0]
            fight_stats_count = conn.execute("SELECT COUNT(*) FROM fight_stats").fetchone()[0]
            round_stats_count = conn.execute("SELECT COUNT(*) FROM round_stats").fetchone()[0]

            # 2. Foreign Key & Orphan Checks
            orphan_fights = conn.execute("""
                SELECT COUNT(*) FROM fights 
                WHERE event_id NOT IN (SELECT event_id FROM events)
            """).fetchone()[0]

            orphan_fight_stats = conn.execute("""
                SELECT COUNT(*) FROM fight_stats 
                WHERE fight_id NOT IN (SELECT fight_id FROM fights)
            """).fetchone()[0]

            orphan_round_stats = conn.execute("""
                SELECT COUNT(*) FROM round_stats 
                WHERE fight_id NOT IN (SELECT fight_id FROM fights)
            """).fetchone()[0]

            # 3. Missing Fighter Links
            # Find fighter IDs referenced in fights that are not yet saved in fighters table
            unlinked_fighters_q = """
                SELECT DISTINCT fid FROM (
                    SELECT fighter1_id AS fid FROM fights WHERE fighter1_id IS NOT NULL
                    UNION
                    SELECT fighter2_id AS fid FROM fights WHERE fighter2_id IS NOT NULL
                    UNION
                    SELECT winner_id AS fid FROM fights WHERE winner_id IS NOT NULL
                ) WHERE fid NOT IN (SELECT fighter_id FROM fighters)
            """
            unlinked_fighter_ids = [r[0] for r in conn.execute(unlinked_fighters_q).fetchall()]

            # 4. Incomplete Fight Statistics
            # Fights with completed outcome but no fight_stats rows
            completed_fights_no_stats = conn.execute("""
                SELECT COUNT(*) FROM fights 
                WHERE outcome IN ('W', 'L', 'D', 'NC') 
                AND fight_id NOT IN (SELECT DISTINCT fight_id FROM fight_stats)
            """).fetchone()[0]

            # 5. Fighter Profile Completeness
            fighters_missing_reach = conn.execute("""
                SELECT COUNT(*) FROM fighters WHERE reach_cm IS NULL
            """).fetchone()[0]

            fighters_missing_dob = conn.execute("""
                SELECT COUNT(*) FROM fighters WHERE dob IS NULL
            """).fetchone()[0]

            # 6. Data Sanity Anomaly Checks
            # Strikes landed > attempted
            invalid_strikes = conn.execute("""
                SELECT COUNT(*) FROM fight_stats 
                WHERE sig_str_landed > sig_str_attempted OR total_str_landed > total_str_attempted
            """).fetchone()[0]

            return {
                "db_path": str(self.db_path),
                "counts": {
                    "events": events_count,
                    "fights": fights_count,
                    "fighters": fighters_count,
                    "fight_stats": fight_stats_count,
                    "round_stats": round_stats_count,
                },
                "orphans": {
                    "orphan_fights": orphan_fights,
                    "orphan_fight_stats": orphan_fight_stats,
                    "orphan_round_stats": orphan_round_stats,
                },
                "missing_links": {
                    "unlinked_fighters_count": len(unlinked_fighter_ids),
                    "unlinked_fighter_ids": unlinked_fighter_ids[:10],  # preview first 10
                    "completed_fights_missing_stats": completed_fights_no_stats,
                },
                "profile_coverage": {
                    "missing_reach_count": fighters_missing_reach,
                    "missing_dob_count": fighters_missing_dob,
                },
                "anomalies": {
                    "invalid_strikes_count": invalid_strikes,
                },
                "health_score_pct": self._calculate_health_score(
                    fights_count,
                    completed_fights_no_stats,
                    orphan_fights,
                    orphan_fight_stats,
                    invalid_strikes,
                ),
            }

        finally:
            conn.close()

    def _calculate_health_score(
        self, fights: int, missing_stats: int, orphan_f: int, orphan_s: int, invalid: int
    ) -> float:
        if fights == 0:
            return 100.0
        penalties = (missing_stats * 2.0) + (orphan_f * 5.0) + (orphan_s * 5.0) + (invalid * 10.0)
        score = 100.0 - (penalties / fights * 10)
        return max(0.0, round(score, 1))
