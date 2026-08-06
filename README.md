# UFCStats Parser & ML Dataset Generator

[![CI Build](https://github.com/nickchemin/ufcstats-parser/actions/workflows/ci.yml/badge.svg)](https://github.com/nickchemin/ufcstats-parser/actions/workflows/ci.yml)
[![Weekly Auto-Scraper](https://github.com/nickchemin/ufcstats-parser/actions/workflows/weekly_scraper.yml/badge.svg)](https://github.com/nickchemin/ufcstats-parser/actions/workflows/weekly_scraper.yml)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-REST%20API-009688.svg)](https://fastapi.tiangolo.com/)

A high-performance Python scraper, data parser, ML feature engineering pipeline, REST API, and CLI toolkit for extracting historical and ongoing fight statistics, detailed round-by-round metrics, and fighter profiles from [ufcstats.com](http://www.ufcstats.com).

Designed for data scientists, sports analysts, and developers building MMA analytics tools, fight predictor models, or archival databases.

---

## Table of Contents

- [Key Features](#key-features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Command Reference](#cli-command-reference)
  - [Crawling Data](#1-crawling-data)
  - [Exporting Data](#2-exporting-data)
  - [Database & Cache Utilities](#3-database--cache-utilities)
- [Database Schema & Architecture](#database-schema--architecture)
- [Technical Highlights](#technical-highlights)
- [Project Structure](#project-structure)
- [License](#license)

---

## Key Features

- **Full Data Coverage**: Scrapes all completed UFC events, individual fight results, granular round-by-round striking & grappling metrics, and complete fighter career profiles.
- **High-Performance Async Engine**: Native `httpx` + `asyncio` parallel scraper (`--async`) with `asyncio.Semaphore` rate limiting for 5x–8x faster batch harvesting.
- **Proxy Rotation Support**: IP rotation via `--proxy` or `--proxy-file` to bypass IP blocks during full historical crawls.
- **Custom Proof-of-Work Bypass**: Natively solves ufcstats.com's custom SHA-256 client challenge in sync/async modes without requiring browser automation (Selenium/Playwright).
- **Two-Tier RAM & Disk Caching**: In-memory LRU cache + file-based disk cache with configurable TTLs to eliminate redundant requests.
- **Incremental Updates**: Detects existing database records with early-stopping to only fetch newly completed events or newly listed fighters.
- **Relational Storage & Export**: Saves directly into a structured **SQLite** database (`WAL` mode) and exports to **JSON**, **CSV**, **Parquet**, and **Excel** files.
- **Adaptive Throttling**: Intelligent rate limiting with randomized delay intervals and automatic session backoff.
- **Rich Terminal UI**: Live progress indicators, colored logs, and formatted data tables powered by `rich` and `click`.

---

## Installation

### Prerequisites

- Python **3.10** or higher
- Git

### Setup

```bash
# Clone the repository
git clone https://github.com/nickchemin/ufcstats-parser.git
cd ufcstats-parser

# Install dependencies
pip install -r requirements.txt
```

---

## Quick Start

Run a test crawl limited to 3 events to verify setup:

```bash
python cli.py crawl --all --limit-events 3
```

Run high-speed async crawl with 5 parallel workers:

```bash
python cli.py crawl --all --async --concurrency 5
```

Export the collected data to CSV and JSON formats:

```bash
python cli.py export --format all --output ./data/
```

Check your database status:

```bash
python cli.py db --stats
```

---

## CLI Command Reference

### 1. Crawling Data

The `crawl` command handles data ingestion from ufcstats.com.

```bash
# Crawl all completed events, fights, round stats, and fighter profiles
python cli.py crawl --all

# High-speed async crawl with parallel workers
python cli.py crawl --all --async --concurrency 5

# Crawl through a proxy or proxy pool list
python cli.py --proxy "http://127.0.0.1:8080" crawl --all
python cli.py --proxy-file proxies.txt crawl --all --async

# Incremental update: fetch only new events and missing fighter profiles (with early stopping)
python cli.py crawl --incremental

# Crawl upcoming scheduled events and fight cards
python cli.py crawl --upcoming

# Crawl a specific event by name or substring
python cli.py crawl --event "UFC 309"

# Crawl fighter profiles directory only (A-Z listing)
python cli.py crawl --fighters

# Fast crawl: skip detailed round-by-round statistics
python cli.py crawl --all --no-fight-details

# Skip full fighter directory crawl
python cli.py crawl --all --no-fighters

# Test crawl: limit the number of events to process (skips full fighter directory)
python cli.py crawl --all --limit-events 5
```

### 2. Exporting Data

The `export` command converts stored SQLite tables into JSON, CSV, Parquet, or Excel formats.

```bash
# Export all tables to all supported formats in ./data/
python cli.py export --format all --output ./data/

# Export specific tables to Apache Parquet binary format
python cli.py export --format parquet --tables events,fights

# Export database tables to an Excel workbook (.xlsx)
python cli.py export --format excel --output ./data/
```

### 3. Machine Learning Dataset Transformation

The `transform` command generates a flat dataset comparing Fighter 1 vs Fighter 2 with calculated physical, record, striking, and grappling feature differentials for predictive modeling.

```bash
# Generate ML dataset in CSV format
python cli.py transform --format csv --output ./data/ml_dataset.csv

# Generate ML dataset in Apache Parquet format
python cli.py transform --format parquet --output ./data/ml_dataset.parquet

# Generate ML dataset in Excel format
python cli.py transform --format excel --output ./data/ml_dataset.xlsx
```

### 4. REST API Server

The `serve` command launches an embedded FastAPI REST server providing HTTP endpoints for events, fights, fighter profiles, ML datasets, and health metrics with interactive Swagger UI.

```bash
# Start REST API server at http://127.0.0.1:8000 (Swagger docs at http://127.0.0.1:8000/docs)
python cli.py serve

# Start REST API server on custom host and port
python cli.py serve --host 0.0.0.0 --port 8080
```

#### 🌐 Live Demo & Free 1-Click Cloud Deployment (Render.com)

- 🚀 **Live Interactive REST API Demo**: [https://ufcstats-parser.onrender.com/docs](https://ufcstats-parser.onrender.com/docs)

You can also host your own instance publicly on [Render.com](https://render.com) using Docker:

[![Deploy to Render](https://img.shields.io/badge/Deploy%20to-Render-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://render.com/deploy?repo=https://github.com/nickchemin/ufcstats-parser)

1. Click the **Deploy to Render** button above (or sign up on [Render.com](https://render.com) for free).
2. Connect your GitHub repository `nickchemin/ufcstats-parser`.
3. Render automatically detects `render.yaml` & `Dockerfile`, builds the service, and provides a free public HTTPS domain with interactive Swagger UI.

### 5. Database & Cache Utilities

```bash
# Run data quality & database integrity diagnostics report
python cli.py check

# View summary metrics of stored events, fights, fighters, and round rows
python cli.py db --stats

# View disk cache size, hit/miss count, and hit rate percentage
python cli.py cache --stats

# Clear all cached HTML files
python cli.py cache --clear
```

### Global Options

```bash
# Set custom request delay range (min/max in seconds)
python cli.py --delay-min 2.0 --delay-max 5.0 crawl --all

# Specify a custom database file path
python cli.py --db my_custom_ufc.db crawl --all

# Specify a custom cache directory
python cli.py --cache-dir ./custom_cache crawl --all

# Enable detailed debug logs
python cli.py -v crawl --all
```

---

## Database Schema & Architecture

The database is built on SQLite using normalized relational tables with `ON CONFLICT` upsert handling:

```
                  ┌──────────────┐
                  │    events    │
                  └──────┬───────┘
                         │ 1
                         │
                         │ N
                  ┌──────┴───────┐
                  │    fights    │
                  └──────┬───────┘
                         │ 1
       ┌─────────────────┴─────────────────┐
       │ N                                 │ N
┌──────┴───────┐                    ┌──────┴───────┐
│ fight_stats  │                    │ round_stats  │
└──────────────┘                    └──────────────┘

┌──────────────┐
│   fighters   │
└──────────────┘
```

### Tables Breakdown

1. **`events`**: Event metadata (`event_id`, `name`, `date`, `location`, `fights_count`).
2. **`fights`**: Matchup details (`fight_id`, `event_id`, `fighter1_id`, `fighter2_id`, `winner_id`, `outcome`, `method`, `round`, `time`, `weight_class`, `title_fight`).
3. **`fight_stats`**: Fight-level overall statistics for each fighter (`kd`, `sig_str_landed`, `sig_str_attempted`, `total_str_landed`, `td_landed`, `ctrl_seconds`, `sig_head`, `sig_body`, `sig_leg`, `distance`, `clinch`, `ground`).
4. **`round_stats`**: Granular statistics broken down by individual round (`round_number`, striking & grappling breakdown per round).
5. **`fighters`**: Fighter career bio & stats (`height_cm`, `weight_kg`, `reach_cm`, `stance`, `dob`, `wins`, `losses`, `draws`, `slpm`, `str_acc`, `sapm`, `str_def`, `td_avg`, `td_acc`, `sub_avg`).

---

## Technical Highlights

### Proof-of-Work Challenge Bypass

Unlike standard Cloudflare setups, `ufcstats.com` serves an inline client-side SHA-256 challenge page. The `UFCStatsScraper` engine automatically:
1. Detects challenge pages and extracts the `nonce` and required difficulty level.
2. Computes the valid SHA-256 hash iteration (`n`).
3. Submits a verification `POST` request to `/__c` to receive the session authentication cookie (`_fmc`).
4. Reuses cookie authentication across all subsequent HTTP requests.

### Performance & Throttling

- **Thread-safe Rate Limiting**: Randomizes delay intervals between 1.5s–3.5s with extended cool-down pauses every 50 requests.
- **WAL Journaling Mode**: SQLite is initialized with `PRAGMA journal_mode=WAL` for concurrent read/write performance.

### Automated Weekly Scraper (CI/CD)

- Includes a GitHub Actions workflow (`.github/workflows/weekly_scraper.yml`) running every Monday at 00:00 UTC.
- Automatically crawls newly completed events, upcoming cards, generates the ML dataset, and uploads the SQLite database & CSV/JSON datasets as downloadable GitHub Action Artifacts.

---

## Project Structure

```
ufcstats-parser/
├── cli.py                    # Main Click CLI application entry point
├── requirements.txt          # Python package dependencies
├── Dockerfile                # Docker container configuration
├── render.yaml               # 1-click cloud deployment config
├── CONTRIBUTING.md           # Open-source contribution guidelines
├── LICENSE                   # MIT License
├── README.md                 # Project documentation
├── examples/
│   └── demo.py               # Machine Learning dataset predictor demo script
└── src/
    ├── __init__.py
    ├── api.py                # FastAPI REST server & Swagger UI engine
    ├── scraper.py            # Custom HTTP client & PoW solver
    ├── parsers/              # HTML parser modules
    │   ├── __init__.py
    │   ├── events.py         # Events listing parser
    │   ├── fights.py         # Event fights list parser
    │   ├── fight_detail.py   # Detailed fight & round metrics parser
    │   └── fighters.py       # Fighter bio & directory parser
    ├── storage/              # Persistence, ML & export layer
    │   ├── __init__.py
    │   ├── models.py         # Pydantic data models
    │   ├── database.py       # SQLite manager & schema definitions
    │   ├── ml_dataset.py     # Feature engineering & ML dataset generator
    │   ├── cache.py          # Disk cache implementation
    │   └── exporter.py       # JSON & CSV export logic
    └── utils/                # Helper utilities
        ├── __init__.py
        ├── logger.py         # Rich logging & progress bar setup
        └── rate_limiter.py   # Adaptive rate limiting implementation
```

---

## License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for more information.
