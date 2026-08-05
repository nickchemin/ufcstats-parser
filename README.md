# UFCStats Parser

A robust Python web scraper and data parser for extracting complete UFC event history, fight metrics, round-by-round statistics, and fighter profiles from [ufcstats.com](http://www.ufcstats.com).

## Features

- **Comprehensive Extraction**: Scrapes events, fight details, detailed striking & grappling metrics (overall & round-by-round), and full fighter bio/career profiles.
- **Automated Anti-Bot Bypass**: Handles custom SHA-256 proof-of-work challenges natively using pure `requests` sessions without requiring heavyweight browser automation tools like Selenium or Playwright.
- **Smart Disk Cache**: Configurable file-based cache with custom TTL settings to avoid redundant network requests.
- **Incremental Crawling**: Supports incremental updates so you only fetch newly added events or fighters.
- **Multi-Format Export**: Export parsed data seamlessly to **SQLite**, **JSON**, or **CSV** formats.
- **Adaptive Rate Limiting**: Built-in randomized request throttling and exponential backoff retry mechanisms.
- **Rich CLI Interface**: Clean command-line tool with live progress bars and structured statistical tables powered by `rich`.

## Quick Start

### Installation

Clone the repository and install requirements:

```bash
git clone https://github.com/your-username/ufcstats-parser.git
cd ufcstats-parser
pip install -r requirements.txt
```

### Usage Examples

#### 1. Test Run (Scrape first N events)

```bash
python cli.py crawl --all --limit-events 3
```

#### 2. Full Crawl (Events, Fights & Fighter Profiles)

```bash
python cli.py crawl --all
```

#### 3. Incremental Update (Only fetch new entries)

```bash
python cli.py crawl --incremental
```

#### 4. Scrape Specific Event by Name

```bash
python cli.py crawl --event "UFC 309"
```

#### 5. Crawl Fighter Profiles Only

```bash
python cli.py crawl --fighters
```

#### 6. Export Data

Export all SQLite tables to JSON and CSV files:

```bash
# Export all tables to JSON and CSV
python cli.py export --format all --output ./data/

# Export specific tables to JSON only
python cli.py export --format json --tables events,fights
```

#### 7. Inspect Cache & Database

```bash
# View database statistics
python cli.py db --stats

# View cache statistics
python cli.py cache --stats

# Clear disk cache
python cli.py cache --clear
```

## CLI Configuration Options

```bash
# Set custom request delay interval (seconds)
python cli.py --delay-min 2.0 --delay-max 4.0 crawl --all

# Specify custom SQLite database path
python cli.py --db custom_ufc.db crawl --all

# Specify custom cache directory
python cli.py --cache-dir /tmp/ufc_cache crawl --all
```

## Database Schema Overview

The default SQLite database (`ufc_data.db`) structures collected data into 5 relational tables:

| Table | Description |
|-------|-------------|
| `events` | UFC event metadata (name, date, location, fight count). |
| `fights` | Individual fight outcomes (fighters, winner, method, finish round/time, weight class, title status). |
| `fighters` | Fighter profile information (height, weight, reach, stance, DOB, record, career striking & grappling averages). |
| `fight_stats` | Fight-level overall totals (knockdowns, significant strikes, total strikes, takedowns, control time, body part & distance breakdown). |
| `round_stats` | Granular round-by-round metrics for every completed round of a fight. |

## Data Metrics Included

- **Striking**: Knockdowns, Significant Strikes (landed/attempted), Total Strikes, Accuracy %.
- **Striking Breakdown**: Head, Body, Leg strikes; Distance, Clinch, Ground strikes.
- **Grappling**: Takedowns (landed/attempted), Accuracy %, Submission Attempts, Reversals, Control Time (seconds).
- **Fighter Profile**: Height (cm), Weight (kg), Reach (cm), Stance, Win/Loss/Draw record, SLpM, SApM, Striking Defense, Takedown Defense, Sub Avg.

## Project Architecture

```
ufcstats-parser/
├── cli.py                        # Command-line interface
├── requirements.txt              # Project dependencies
├── README.md                     # Documentation
└── src/
    ├── scraper.py                # HTTP client & PoW solver
    ├── parsers/
    │   ├── events.py             # Event listing parser
    │   ├── fights.py             # Event fights parser
    │   ├── fight_detail.py       # Fight totals & round-by-round parser
    │   └── fighters.py           # Fighter directory & profile parser
    ├── storage/
    │   ├── models.py             # Pydantic data models
    │   ├── database.py           # SQLite manager with upsert support
    │   ├── cache.py              # File-based cache manager
    │   └── exporter.py           # JSON and CSV export handlers
    └── utils/
        ├── logger.py             # Rich logger setup
        └── rate_limiter.py       # Adaptive rate limiter
```

## Requirements

- Python 3.10+
- `requests`
- `beautifulsoup4`
- `lxml`
- `click`
- `rich`
- `pydantic`

## License

MIT License. See `LICENSE` for details.
