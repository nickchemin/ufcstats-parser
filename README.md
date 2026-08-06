# 🥊 UFCStats Parser, REST API & Soft-Voting ML Fight Predictor

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-1.3.0-009688.svg)](https://fastapi.tiangolo.com/)
[![Scikit-Learn](https://img.shields.io/badge/scikit--learn-1.9.0-orange.svg)](https://scikit-learn.org/)
[![XGBoost](https://img.shields.io/badge/XGBoost-3.4.0-red.svg)](https://xgboost.readthedocs.io/)
[![LightGBM](https://img.shields.io/badge/LightGBM-4.7.0-blue.svg)](https://lightgbm.readthedocs.io/)

A high-performance, full-stack Python MMA analytics platform featuring:
- **Automated Web Scraper & Crawler**: Custom SHA-256 Proof-of-Work challenge solver, persistent cookie cache, rate limiting, and proxy rotation.
- **Relational SQLite Database**: Normalized schema storing completed/upcoming UFC events, fights, round-by-round striking/grappling metrics, and 4,500+ fighter career profiles.
- **Zero Data Leakage ML Feature Pipeline**: 30 differential features including chronological pre-fight ELO ratings, physical metrics, win streaks, finish ratios, and striking/grappling rates.
- **Soft-Voting ML Ensemble**: Combined **XGBoost** + **LightGBM** + **HistGradientBoosting** + **RandomForest** classifier.
- **Invariant Dual-Pass Symmetrization**: Guarantees $P(F_1) + P(F_2) = 1.0$, identical predictions on corner swapping, and exact 50%/50% probabilities for same-fighter matchups.
- **FastAPI REST API & Interactive Web UI**: Sub-millisecond cached inference, Swagger docs (`/docs`), and a modern Glassmorphism Web Dashboard (`/app`).
- **CLI Toolkit & Card Predictor**: Auto-detects upcoming UFC events, simulates all matchups, and exports interactive HTML preview reports.

---

## 📊 ML Model Performance & Validation

Evaluated on a **strict out-of-time chronological test set** (13,842 training samples, 3,462 test samples) with feature-inverted symmetry data augmentation:

| Evaluation Metric | Test Score | Description |
| :--- | :--- | :--- |
| **ROC-AUC** | **`0.668`** | High discriminative power across historical UFC bouts |
| **Accuracy** | **`61.6%`** | Out-of-time predictive accuracy on completed fights |
| **Log Loss** | `0.651` | Well-calibrated probability distributions |
| **Precision** | `0.616` | Symmetrical class 1 / class 0 precision |
| **Recall** | `0.615` | Balanced true positive rate |
| **F1 Score** | `0.615` | Symmetrical harmonic mean score |

---

## 🌟 Key Features

### 🕸️ Scraper & Data Pipeline
- **PoW Bypass & Cookie Management**: Automatically extracts nonce and solves ufcstats.com's SHA-256 client challenge to acquire and cache `_fmc` cookies.
- **Async & Concurrent Harvesting**: `AsyncUFCStatsScraper` built on `httpx` + `asyncio` for 5x–8x faster batch downloads.
- **Incremental Crawling**: `--incremental` flag detects existing database records with early-stopping to fetch only new events and un-crawled fighter profiles.
- **Data Quality Diagnostics**: Integrated `DatabaseChecker` with data health scoring (100.0% score on full crawl).

### 🤖 Machine Learning Engine
- **30 Feature Differentials**: `diff_pre_elo`, `diff_height_cm`, `diff_weight_kg`, `diff_reach_cm`, `diff_ape_index`, `diff_reach_ratio`, `diff_age_years`, `diff_pre_wins`, `diff_pre_losses`, `diff_pre_win_rate`, `diff_pre_finish_win_rate`, `diff_pre_streak`, `diff_pre_days_since_last_fight`, `diff_slpm`, `diff_str_acc`, `diff_sapm`, `diff_strike_efficiency`, `diff_td_avg`, `diff_td_acc`, `diff_td_def`, stance flags, and debut indicators.
- **Zero Data Leakage**: Pre-fight metrics are computed strictly from historical fights preceding the event date.
- **Model Persistence**: Model weights and tree structures are serialized to `data/fight_predictor_model.pkl` and `data/fight_predictor_model.json`.

### 🌐 REST API & Glassmorphism Dashboard
- **FastAPI Endpoints**: REST API providing paginated access to events, fight details, fighter profiles, matchups, predictions, dataset generation, and health diagnostics.
- **Sub-Millisecond Inference**: Cached `FightPredictor` instance executes predictions in `< 1` ms per request.
- **Glassmorphism Web Dashboard**: Located at `/app`, featuring real-time fight predictor, upcoming card browser, fighter search directory, and system health diagnostics with XSS sanitization.

---

## ⚡ Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/nickchemin/ufcstats-parser.git
cd ufcstats-parser

# Install dependencies
pip install -r requirements.txt
```

### 2. Crawl Database

```bash
# Incremental crawl for new events and un-crawled fighter profiles
python cli.py crawl --incremental

# High-speed asynchronous crawl with 5 parallel workers
python cli.py crawl --all --async --concurrency 5
```

### 3. Train ML Ensemble Predictor

```bash
python cli.py train
```

### 4. Predict an Upcoming UFC Fight Card

```bash
# Auto-detects upcoming UFC card, runs predictions, and exports HTML report
python cli.py predict-card
```

### 5. Launch REST API Server & Web Dashboard

```bash
python cli.py serve --port 8000
```
- **Web UI Dashboard**: `http://localhost:8000/app`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`

---

## 💻 CLI Command Reference

| Command | Arguments / Flags | Description |
| :--- | :--- | :--- |
| `python cli.py crawl` | `--all`, `--incremental`, `--async`, `--concurrency N` | Harvests events, fights, round stats, and fighter profiles |
| `python cli.py train` | `--test-size 0.2`, `--output PATH` | Trains XGBoost/LightGBM Ensemble and saves model binary |
| `python cli.py predict-card` | `--event-id ID`, `--format [html\|markdown\|json]` | Simulates entire fight card and exports HTML/MD preview report |
| `python cli.py export` | `--format [csv\|json\|parquet\|excel]` | Exports raw database tables to structured dataset formats |
| `python cli.py transform` | `--format [csv\|json\|parquet\|excel]` | Exports 30-feature matchup ML dataset |
| `python cli.py check` | N/A | Runs database integrity and health score diagnostics |
| `python cli.py db` | `--stats` | Displays SQLite table row counts and summary metrics |
| `python cli.py cache` | `--stats`, `--clear` | Inspects or clears two-tier disk cache |
| `python cli.py serve` | `--host 127.0.0.1`, `--port 8000` | Launches FastAPI server and Web Dashboard |

---

## 🌐 REST API Endpoint Summary

| HTTP Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/app` | Serves interactive Glassmorphism Web UI Dashboard |
| `GET` | `/api/v1/predict` | Computes ML outcome prediction between 2 fighters (`?fighter1_id=X&fighter2_id=Y`) |
| `GET` | `/api/v1/events` | Paginated list of UFC events with optional search query (`?q=UFC`) |
| `GET` | `/api/v1/events/upcoming` | List of scheduled upcoming UFC events |
| `GET` | `/api/v1/events/{event_id}` | Event details and full fight card |
| `GET` | `/api/v1/fights/{fight_id}` | Fight outcome, totals, and round-by-round statistics |
| `GET` | `/api/v1/fighters` | Search fighter directory with pagination (`?q=Jon`) |
| `GET` | `/api/v1/fighters/{fighter_id}` | Detailed fighter bio and career stats |
| `GET` | `/api/v1/matchup` | Tale of the Tape physical and career differentials |
| `GET` | `/api/v1/ml-dataset` | Generates flat ML feature matchup dataset |
| `GET` | `/api/v1/health` | Data health diagnostics and health score |
| `GET` | `/api/v1/stats/summary` | Database row counts and summary metrics |

---

## 🧪 Testing

Run unit test suite with coverage report:

```bash
pytest
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
