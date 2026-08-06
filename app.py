"""
Streamlit Web UI Dashboard for UFCStats Parser & ML Predictor.

Usage:
    streamlit run app.py
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

try:
    import streamlit as st
except ImportError:
    print("[!] Streamlit is not installed. Please run: pip install streamlit")
    sys.exit(1)

from src.storage.database import Database
from src.storage.checker import DatabaseChecker
from src.storage.ml_dataset import MLDatasetGenerator
from src.ml.predictor import FightPredictor

st.set_page_config(
    page_title="UFCStats Analytics & Predictor",
    page_icon="🥊",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = "ufc_data.db"


@st.cache_resource
def get_db():
    return Database(DB_PATH)


@st.cache_resource
def get_predictor():
    p = FightPredictor(DB_PATH)
    p.train(test_size=0.2)
    return p


def main():
    st.sidebar.title("🥊 UFCStats Navigation")
    tab = st.sidebar.radio(
        "Select Dashboard View:",
        ["🥊 Fight Predictor", "📅 Upcoming Cards", "🔍 Fighter Search", "⚙️ System Diagnostics"],
    )

    if not Path(DB_PATH).exists():
        st.warning(f"Database '{DB_PATH}' not found. Please run: `python cli.py crawl --all --limit-events 5` first.")
        return

    db = get_db()
    summary = db.summary()

    if tab == "🥊 Fight Predictor":
        render_predictor_view(db)
    elif tab == "📅 Upcoming Cards":
        render_upcoming_view(db)
    elif tab == "🔍 Fighter Search":
        render_fighter_search_view(db)
    elif tab == "⚙️ System Diagnostics":
        render_diagnostics_view(db, summary)


def render_predictor_view(db):
    st.title("🥊 UFC Fight Matchup Simulator")
    st.caption("Select two fighters to simulate a bout and calculate AI win probabilities with physical & career differentials.")

    fighters = db.get_fighter_ids()
    if len(fighters) < 2:
        st.info("Insufficient fighters stored in database. Crawl profiles first using `python cli.py crawl --fighters`.")
        return

    # Load fighter records
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM fighters ORDER BY first_name ASC").fetchall()
    conn.close()

    fighter_map = {f"{r['first_name'] or ''} {r['last_name'] or ''} ({r['fighter_id']})".strip(): dict(r) for r in rows}
    names = list(fighter_map.keys())

    col1, col2 = st.columns(2)
    with col1:
        f1_name = st.selectbox("Select Fighter 1 (Red Corner):", names, index=0)
    with col2:
        f2_name = st.selectbox("Select Fighter 2 (Blue Corner):", names, index=min(1, len(names) - 1))

    if st.button("⚡ Simulate Fight Matchup", type="primary"):
        f1 = fighter_map[f1_name]
        f2 = fighter_map[f2_name]

        if f1["fighter_id"] == f2["fighter_id"]:
            st.error("Please select two different fighters.")
            return

        h1, h2 = f1.get("height_cm"), f2.get("height_cm")
        r1, r2 = f1.get("reach_cm"), f2.get("reach_cm")
        ape1 = (r1 - h1) if (r1 and h1) else None
        ape2 = (r2 - h2) if (r2 and h2) else None
        st1 = (f1.get("stance") or "").strip().lower()
        st2 = (f2.get("stance") or "").strip().lower()

        feat = {
            "diff_height_cm": (h1 - h2) if (h1 and h2) else 0.0,
            "diff_reach_cm": (r1 - r2) if (r1 and r2) else 0.0,
            "diff_ape_index": (ape1 - ape2) if (ape1 and ape2) else 0.0,
            "is_same_stance": 1 if (st1 and st2 and st1 == st2) else 0,
            "is_orthodox_vs_southpaw": 1 if (set([st1, st2]) == {"orthodox", "southpaw"}) else 0,
            "diff_slpm": (f1.get("slpm") or 0.0) - (f2.get("slpm") or 0.0),
            "diff_str_acc": (f1.get("str_acc") or 0.0) - (f2.get("str_acc") or 0.0),
            "diff_sapm": (f1.get("sapm") or 0.0) - (f2.get("sapm") or 0.0),
            "diff_str_def": (f1.get("str_def") or 0.0) - (f2.get("str_def") or 0.0),
            "diff_td_avg": (f1.get("td_avg") or 0.0) - (f2.get("td_avg") or 0.0),
            "diff_td_acc": (f1.get("td_acc") or 0.0) - (f2.get("td_acc") or 0.0),
            "diff_td_def": (f1.get("td_def") or 0.0) - (f2.get("td_def") or 0.0),
        }

        predictor = get_predictor()
        res = predictor.predict_matchup(feat, {})

        p1 = res["fighter1_win_probability"] * 100
        p2 = res["fighter2_win_probability"] * 100

        st.markdown("---")
        st.subheader(f"Prediction: {'Red Corner (' + f1['last_name'] + ')' if res['predicted_winner'] == 1 else 'Blue Corner (' + f2['last_name'] + ')'}")
        st.caption(f"Confidence Level: {res['confidence_pct']}%")

        m1, m2 = st.columns(2)
        m1.metric(f"🔴 {f1['first_name']} {f1['last_name']}", f"{p1:.1f}% Win Probability")
        m2.metric(f"🔵 {f2['first_name']} {f2['last_name']}", f"{p2:.1f}% Win Probability")

        st.progress(p1 / 100.0)


def render_upcoming_view(db):
    st.title("📅 Upcoming UFC Events")
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    events = conn.execute("SELECT * FROM events WHERE date IS NULL OR date >= date('now') ORDER BY date ASC").fetchall()
    conn.close()

    if not events:
        st.info("No upcoming scheduled events currently found in database.")
        return

    for evt in events:
        with st.expander(f"🏆 {evt['name']} ({evt['date'] or 'TBD'}) - 📍 {evt['location'] or 'Unknown'}"):
            st.write(f"Event ID: `{evt['event_id']}`")


def render_fighter_search_view(db):
    st.title("🔍 Fighter Bio Directory")
    query = st.text_input("Search fighter by name:", "")

    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if query:
        pattern = f"%{query}%"
        rows = conn.execute("SELECT * FROM fighters WHERE first_name LIKE ? OR last_name LIKE ? OR nickname LIKE ? LIMIT 20", (pattern, pattern, pattern)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM fighters LIMIT 20").fetchall()
    conn.close()

    for r in rows:
        st.write(f"**{r['first_name']} {r['last_name']}** ({r['nickname'] or 'No nickname'}) — *{r['stance'] or 'Unknown Stance'}* | Height: {r['height_cm'] or '--'}cm | Record: {r['wins'] or 0}W-{r['losses'] or 0}L")


def render_diagnostics_view(db, summary):
    st.title("⚙️ Database & System Diagnostics")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Events Stored", summary["events"])
    c2.metric("Fights Stored", summary["fights"])
    c3.metric("Fighters Stored", summary["fighters"])
    c4.metric("Round Stats Rows", summary["round_stats_rows"])

    checker = DatabaseChecker(DB_PATH)
    report = checker.run_diagnostics()
    st.markdown("---")
    st.subheader("Data Quality Report")
    st.json(report)


if __name__ == "__main__":
    main()
