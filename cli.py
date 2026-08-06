"""
Command-Line Interface for UFCStats Parser.

Usage examples:
    python cli.py crawl --all
    python cli.py crawl --incremental
    python cli.py crawl --event "UFC 309"
    python cli.py crawl --fighters
    python cli.py export --format json --output ./data/
    python cli.py export --format csv --output ./data/
    python cli.py export --format all --output ./data/
    python cli.py cache --stats
    python cli.py cache --clear
    python cli.py db --stats
"""

import sys
import time
from pathlib import Path
from typing import List, Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from src.scraper import UFCStatsScraper, AsyncUFCStatsScraper, ProxyManager
from src.storage.cache import FileCache
from src.storage.checker import DatabaseChecker
from src.storage.database import Database
from src.storage.exporter import Exporter
from src.storage.ml_dataset import MLDatasetGenerator
from src.storage.models import Fighter
from src.parsers.events import parse_events_page, parse_upcoming_events_page, EVENTS_URL, UPCOMING_URL
from src.parsers.fights import parse_event_fights
from src.parsers.fight_detail import parse_fight_detail
from src.parsers.fighters import (
    parse_fighters_list,
    parse_fighter_profile,
    FIGHTERS_LIST_URL,
    ALPHABET,
)
from src.utils.logger import get_logger, make_progress, console as rich_console

logger = get_logger(__name__)

BANNER = """
+======================================+
|        UFCStats Parser v1.0          |
|    ufcstats.com data extractor       |
+======================================+"""


def print_banner():
    try:
        print(BANNER)
    except UnicodeEncodeError:
        print("UFCStats Parser v1.0 | ufcstats.com")


# ------------------------------------------------------------------
# CLI Group
# ------------------------------------------------------------------

@click.group()
@click.option("--db", default="ufc_data.db", show_default=True, help="Path to SQLite database file")
@click.option("--cache-dir", default="cache", show_default=True, help="Cache directory path")
@click.option(
    "--delay-min", default=1.5, show_default=True, type=float, help="Minimum request delay (seconds)"
)
@click.option(
    "--delay-max", default=3.5, show_default=True, type=float, help="Maximum request delay (seconds)"
)
@click.option("--proxy", default=None, help="HTTP/HTTPS proxy URL (e.g. http://127.0.0.1:8080)")
@click.option("--proxy-file", default=None, help="Path to text file containing list of proxies")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose debug output")
@click.pass_context
def cli(ctx, db, cache_dir, delay_min, delay_max, proxy, proxy_file, verbose):
    """UFCStats Parser -- Data extraction tool for ufcstats.com"""
    print_banner()
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db
    ctx.obj["cache_dir"] = cache_dir
    ctx.obj["delay_min"] = delay_min
    ctx.obj["delay_max"] = delay_max
    ctx.obj["proxy"] = proxy
    ctx.obj["proxy_file"] = proxy_file
    ctx.obj["verbose"] = verbose

    if verbose:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)


# ------------------------------------------------------------------
# crawl
# ------------------------------------------------------------------

@cli.command()
@click.option("--all", "crawl_all", is_flag=True, help="Full crawl (events + fights + fighters)")
@click.option("--incremental", is_flag=True, help="Crawl only new entries (skip existing in DB)")
@click.option("--upcoming", is_flag=True, help="Crawl upcoming scheduled events and fight cards")
@click.option("--event", "event_name", default=None, help="Crawl specific event by name substring")
@click.option("--fighters", "only_fighters", is_flag=True, help="Crawl fighter profiles only")
@click.option("--no-fight-details", is_flag=True, help="Skip detailed fight round statistics")
@click.option("--no-fighters", is_flag=True, help="Skip crawling full fighter profiles directory")
@click.option("--limit-events", default=None, type=int, help="Limit number of events to process")
@click.option("--async", "use_async", is_flag=True, help="Enable async HTTP scraper for high-speed parallel fetching")
@click.option("--concurrency", default=5, show_default=True, type=int, help="Concurrency limit for async mode")
@click.pass_context
def crawl(ctx, crawl_all, incremental, upcoming, event_name, only_fighters, no_fight_details, no_fighters, limit_events, use_async, concurrency):
    """Crawl data from ufcstats.com"""
    obj = ctx.obj
    cache = FileCache(obj["cache_dir"])
    db = Database(obj["db_path"])

    proxy_manager = None
    if obj.get("proxy_file"):
        proxy_manager = ProxyManager.from_file(obj["proxy_file"])
    elif obj.get("proxy"):
        proxy_manager = ProxyManager([obj["proxy"]])

    if use_async:
        import asyncio
        async_scraper = AsyncUFCStatsScraper(
            concurrency=concurrency,
            min_delay=0.1,
            max_delay=0.5,
            cache=cache,
            proxy_manager=proxy_manager,
        )
        scraper = async_scraper
    else:
        scraper = UFCStatsScraper(
            min_delay=obj["delay_min"],
            max_delay=obj["delay_max"],
            cache=cache,
            proxy_manager=proxy_manager,
        )

    start_time = time.time()

    if use_async:
        import asyncio

        async def _run_async_crawl():
            try:
                if only_fighters:
                    await _async_crawl_fighters(scraper, db, incremental)
                elif upcoming:
                    await _async_crawl_upcoming_events(scraper, db, no_fight_details)
                elif event_name:
                    await _async_crawl_single_event(scraper, db, event_name, no_fight_details)
                elif crawl_all or incremental:
                    await _async_crawl_all_events(scraper, db, incremental, no_fight_details, limit_events)
                    if not no_fighters and limit_events is None:
                        await _async_crawl_fighters(scraper, db, incremental)
                else:
                    click.echo(
                        "Please specify a mode: --all, --incremental, --upcoming, --event <name>, or --fighters\n"
                        "Use --help for command options."
                    )
            finally:
                await scraper.close()

        asyncio.run(_run_async_crawl())
    else:
        try:
            if only_fighters:
                _crawl_fighters(scraper, db, incremental)
            elif upcoming:
                _crawl_upcoming_events(scraper, db, no_fight_details)
            elif event_name:
                _crawl_single_event(scraper, db, event_name, no_fight_details)
            elif crawl_all or incremental:
                _crawl_all_events(scraper, db, incremental, no_fight_details, limit_events)
                if not no_fighters and limit_events is None:
                    _crawl_fighters(scraper, db, incremental)
            else:
                click.echo(
                    "Please specify a mode: --all, --incremental, --upcoming, --event <name>, or --fighters\n"
                    "Use --help for command options."
                )
        finally:
            scraper.close()

    elapsed = time.time() - start_time
    summary = db.summary()
    cache_stats = cache.stats()

    table = Table(title="Crawl Summary", box=box.ROUNDED, style="cyan")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="bold green")

    table.add_row("Events in DB", str(summary["events"]))
    table.add_row("Fights in DB", str(summary["fights"]))
    table.add_row("Fighters in DB", str(summary["fighters"]))
    table.add_row("Round Stats Rows", str(summary["round_stats_rows"]))
    table.add_row("Cache Hits", f"{cache_stats['hits']}")
    table.add_row("Cache Misses", f"{cache_stats['misses']}")
    table.add_row("Cache Size", f"{cache_stats['size_mb']} MB")
    table.add_row("Elapsed Time", f"{elapsed:.1f}s")

    rich_console.print(table)


def _crawl_all_events(scraper, db, incremental, no_fight_details, limit_events):
    """Crawls all events and their fights."""
    logger.info("Fetching events listing...")
    soup = scraper.get_soup(EVENTS_URL)
    if not soup:
        logger.error("Failed to fetch events listing")
        return

    events = parse_events_page(soup)
    if not events:
        logger.error("No events found")
        return

    if limit_events:
        events = events[:limit_events]
        logger.info(f"Limiting crawl to {limit_events} events")

    existing_event_ids = set(db.get_event_ids()) if incremental else set()
    if incremental:
        if not existing_event_ids:
            logger.warning("Database is empty during incremental crawl. Processing listing events.")
        else:
            logger.info(f"Incremental crawl active. {len(existing_event_ids)} existing events found in database.")

    for event in events:
        db.upsert_event(event)

    logger.info(f"Saved events to DB: {len(events)}")

    consecutive_existing = 0
    with make_progress() as progress:
        task = progress.add_task("Processing events", total=len(events))

        for event in events:
            progress.update(task, description=f"[cyan]{event.name[:40]}...")

            if incremental and event.event_id in existing_event_ids:
                logger.debug(f"[skip] {event.name} (already in DB)")
                consecutive_existing += 1
                progress.advance(task)
                if consecutive_existing >= 5:
                    logger.info("Reached 5 consecutive existing events in DB; stopping incremental crawl early.")
                    progress.update(task, completed=len(events))
                    break
                continue

            consecutive_existing = 0
            _process_event(scraper, db, event, no_fight_details)
            progress.advance(task)


def _process_event(scraper, db, event, no_fight_details):
    """Processes a single event: parses fights list and fight details."""
    soup = scraper.get_soup(event.url)
    if not soup:
        logger.warning(f"[{event.name}] Failed to load event page")
        return

    fights = parse_event_fights(soup, event.event_id)
    event.fights_count = len(fights)
    db.upsert_event(event)

    for fight in fights:
        db.upsert_fight(fight)

        # Auto-create fighter stubs if not present in DB
        for fid, fname in [(fight.fighter1_id, fight.fighter1_name), (fight.fighter2_id, fight.fighter2_name)]:
            if fid:
                parts = fname.split() if fname else ["Fighter", fid[:4]]
                first_name = parts[0]
                last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
                db.upsert_fighter(Fighter(
                    fighter_id=fid,
                    url=f"http://www.ufcstats.com/fighter-details/{fid}",
                    first_name=first_name,
                    last_name=last_name,
                ))

        if not no_fight_details:
            fight_soup = scraper.get_soup(fight.url)
            if fight_soup:
                totals, rounds = parse_fight_detail(fight_soup, fight.fight_id)
                for stat in totals:
                    db.upsert_fight_stats(stat)
                for rnd in rounds:
                    db.upsert_round_stats(rnd)


def _crawl_single_event(scraper, db, event_name_query, no_fight_details):
    """Crawls specific events matching name query."""
    logger.info(f"Searching for event matching: '{event_name_query}'")
    soup = scraper.get_soup(EVENTS_URL)
    if not soup:
        logger.error("Failed to load events listing")
        return

    events = parse_events_page(soup)
    matching = [e for e in events if event_name_query.lower() in e.name.lower()]

    if not matching:
        logger.error(f"No events found matching '{event_name_query}'")
        return

    logger.info(f"Found {len(matching)} matching events:")
    for e in matching:
        logger.info(f"  - {e.name} ({e.event_date}) - {e.location}")

    for event in matching:
        db.upsert_event(event)
        _process_event(scraper, db, event, no_fight_details)
        logger.info(f"[OK] Processed {event.name}")


def _crawl_upcoming_events(scraper, db, no_fight_details):
    """Crawls upcoming scheduled events and fight cards."""
    logger.info("Fetching upcoming scheduled events listing...")
    soup = scraper.get_soup(UPCOMING_URL)
    if not soup:
        logger.error("Failed to load upcoming events listing")
        return

    events = parse_upcoming_events_page(soup)
    if not events:
        logger.info("No upcoming events found on ufcstats.com")
        return

    logger.info(f"Found {len(events)} upcoming events:")
    for e in events:
        logger.info(f"  - {e.name} ({e.event_date}) - {e.location}")

    for event in events:
        db.upsert_event(event)
        _process_event(scraper, db, event, no_fight_details)
        logger.info(f"[OK] Processed upcoming event {event.name}")


def _crawl_fighters(scraper, db, incremental):
    """Crawls all fighter profiles alphabetically."""
    logger.info("Starting fighter profiles crawl...")
    existing_ids = set(db.get_fighter_ids()) if incremental else set()

    all_fighter_stubs = []

    with make_progress() as progress:
        alpha_task = progress.add_task("Fetching fighter listing", total=len(ALPHABET))

        for letter in ALPHABET:
            progress.update(alpha_task, description=f"Letter [bold]{letter.upper()}[/]...")
            url = FIGHTERS_LIST_URL.format(letter=letter)
            soup = scraper.get_soup(url)
            if soup:
                stubs = parse_fighters_list(soup)
                all_fighter_stubs.extend(stubs)
            progress.advance(alpha_task)

    logger.info(f"Total fighters listed: {len(all_fighter_stubs)}")

    if incremental:
        new_stubs = [s for s in all_fighter_stubs if s["fighter_id"] not in existing_ids]
        logger.info(f"New fighters to crawl: {len(new_stubs)}")
    else:
        new_stubs = all_fighter_stubs

    with make_progress() as progress:
        task = progress.add_task("Parsing fighter profiles", total=len(new_stubs))

        for stub in new_stubs:
            progress.update(
                task,
                description=f"[cyan]{stub.get('first_name','')} {stub.get('last_name','')}...",
            )
            soup = scraper.get_soup(stub["url"])
            if soup:
                fighter = parse_fighter_profile(soup, stub["fighter_id"], stub["url"])
                if fighter:
                    db.upsert_fighter(fighter)
            progress.advance(task)


async def _async_crawl_all_events(scraper, db, incremental, no_fight_details, limit_events):
    """Crawls all events and their fights asynchronously."""
    logger.info("Fetching events listing (async)...")
    soup = await scraper.get_soup(EVENTS_URL)
    if not soup:
        logger.error("Failed to fetch events listing")
        return

    events = parse_events_page(soup)
    if not events:
        logger.error("No events found")
        return

    if limit_events:
        events = events[:limit_events]
        logger.info(f"Limiting crawl to {limit_events} events")

    existing_event_ids = set(db.get_event_ids()) if incremental else set()
    if incremental and existing_event_ids:
        logger.info(f"Incremental crawl active. {len(existing_event_ids)} existing events found in database.")

    for event in events:
        db.upsert_event(event)

    consecutive_existing = 0
    with make_progress() as progress:
        task = progress.add_task("Processing events (async)", total=len(events))

        for event in events:
            progress.update(task, description=f"[cyan]{event.name[:40]}...")

            if incremental and event.event_id in existing_event_ids:
                consecutive_existing += 1
                progress.advance(task)
                if consecutive_existing >= 5:
                    logger.info("Reached 5 consecutive existing events in DB; stopping incremental crawl early.")
                    progress.update(task, completed=len(events))
                    break
                continue

            consecutive_existing = 0
            await _async_process_event(scraper, db, event, no_fight_details)
            progress.advance(task)


async def _async_process_event(scraper, db, event, no_fight_details):
    """Processes a single event asynchronously: parses fights list and fight details in batches."""
    soup = await scraper.get_soup(event.url)
    if not soup:
        logger.warning(f"[{event.name}] Failed to load event page")
        return

    fights = parse_event_fights(soup, event.event_id)
    event.fights_count = len(fights)
    db.upsert_event(event)

    for fight in fights:
        db.upsert_fight(fight)

        for fid, fname in [(fight.fighter1_id, fight.fighter1_name), (fight.fighter2_id, fight.fighter2_name)]:
            if fid:
                parts = fname.split() if fname else ["Fighter", fid[:4]]
                first_name = parts[0]
                last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
                db.upsert_fighter(Fighter(
                    fighter_id=fid,
                    url=f"http://www.ufcstats.com/fighter-details/{fid}",
                    first_name=first_name,
                    last_name=last_name,
                ))

    if not no_fight_details and fights:
        fight_urls = [fight.url for fight in fights]
        fight_soups = await scraper.get_soups_batch(fight_urls)
        for fight, fight_soup in zip(fights, fight_soups):
            if fight_soup:
                totals, rounds = parse_fight_detail(fight_soup, fight.fight_id)
                for stat in totals:
                    db.upsert_fight_stats(stat)
                for rnd in rounds:
                    db.upsert_round_stats(rnd)


async def _async_crawl_single_event(scraper, db, event_name_query, no_fight_details):
    """Crawls specific events matching name query asynchronously."""
    logger.info(f"Searching for event matching: '{event_name_query}' (async)")
    soup = await scraper.get_soup(EVENTS_URL)
    if not soup:
        logger.error("Failed to load events listing")
        return

    events = parse_events_page(soup)
    matching = [e for e in events if event_name_query.lower() in e.name.lower()]

    if not matching:
        logger.error(f"No events found matching '{event_name_query}'")
        return

    for event in matching:
        db.upsert_event(event)
        await _async_process_event(scraper, db, event, no_fight_details)
        logger.info(f"[OK] Processed {event.name}")


async def _async_crawl_upcoming_events(scraper, db, no_fight_details):
    """Crawls upcoming scheduled events asynchronously."""
    logger.info("Fetching upcoming scheduled events listing (async)...")
    soup = await scraper.get_soup(UPCOMING_URL)
    if not soup:
        logger.error("Failed to load upcoming events listing")
        return

    events = parse_upcoming_events_page(soup)
    if not events:
        logger.info("No upcoming events found on ufcstats.com")
        return

    for event in events:
        db.upsert_event(event)
        await _async_process_event(scraper, db, event, no_fight_details)
        logger.info(f"[OK] Processed upcoming event {event.name}")


async def _async_crawl_fighters(scraper, db, incremental):
    """Crawls all fighter profiles alphabetically asynchronously in batches."""
    logger.info("Starting fighter profiles crawl (async)...")
    existing_ids = set(db.get_fighter_ids()) if incremental else set()

    all_fighter_stubs = []
    alpha_urls = [FIGHTERS_LIST_URL.format(letter=letter) for letter in ALPHABET]
    alpha_soups = await scraper.get_soups_batch(alpha_urls)
    for soup in alpha_soups:
        if soup:
            stubs = parse_fighters_list(soup)
            all_fighter_stubs.extend(stubs)

    logger.info(f"Total fighters listed: {len(all_fighter_stubs)}")
    if incremental:
        new_stubs = [s for s in all_fighter_stubs if s["fighter_id"] not in existing_ids]
        logger.info(f"New fighters to crawl: {len(new_stubs)}")
    else:
        new_stubs = all_fighter_stubs

    batch_size = 20
    with make_progress() as progress:
        task = progress.add_task("Parsing fighter profiles (async)", total=len(new_stubs))
        for i in range(0, len(new_stubs), batch_size):
            batch = new_stubs[i:i + batch_size]
            urls = [s["url"] for s in batch]
            soups = await scraper.get_soups_batch(urls)
            for stub, soup in zip(batch, soups):
                if soup:
                    fighter = parse_fighter_profile(soup, stub["fighter_id"], stub["url"])
                    if fighter:
                        db.upsert_fighter(fighter)
                progress.advance(task)


# ------------------------------------------------------------------
# export
# ------------------------------------------------------------------

@cli.command()
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "csv", "parquet", "excel", "all"], case_sensitive=False),
    default="all",
    show_default=True,
    help="Export format",
)
@click.option("--output", "-o", default="data", show_default=True, help="Output directory path")
@click.option(
    "--tables",
    default=None,
    help="Comma-separated table names to export (e.g. events,fights)",
)
@click.pass_context
def export(ctx, fmt, output, tables):
    """Export database content to JSON/CSV/Parquet/Excel files"""
    db_path = ctx.obj["db_path"]
    exporter = Exporter(db_path)
    table_list = [t.strip() for t in tables.split(",")] if tables else None

    if fmt in ("json", "all"):
        exporter.export_json(output, table_list)
    if fmt in ("csv", "all"):
        exporter.export_csv(output, table_list)
    if fmt in ("parquet", "all"):
        exporter.export_parquet(output, table_list)
    if fmt in ("excel", "all"):
        exporter.export_excel(output, table_list)

    rich_console.print(f"[bold green]Export complete -> {Path(output).resolve()}[/]")


# ------------------------------------------------------------------
# transform
# ------------------------------------------------------------------

@cli.command()
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["csv", "json", "parquet", "excel"], case_sensitive=False),
    default="csv",
    show_default=True,
    help="Output dataset format",
)
@click.option(
    "--output",
    "-o",
    default="data/ml_dataset.csv",
    show_default=True,
    help="Output file path",
)
@click.pass_context
def transform(ctx, fmt, output):
    """Generate ML-ready matchup dataset with feature differentials"""
    db_path = ctx.obj["db_path"]
    generator = MLDatasetGenerator(db_path)
    generator.export_ml_dataset(output_path=output, output_format=fmt)
    rich_console.print(f"[bold green]ML dataset generated -> {Path(output).resolve()}[/]")


# ------------------------------------------------------------------
# train
# ------------------------------------------------------------------

@cli.command()
@click.option(
    "--output",
    "-o",
    default="data/fight_predictor_model.json",
    show_default=True,
    help="Output model parameters JSON path",
)
@click.option("--test-size", default=0.2, show_default=True, type=float, help="Test set split fraction")
@click.pass_context
def train(ctx, output, test_size):
    """Train ML fight outcome prediction model and evaluate metrics"""
    from src.ml.predictor import FightPredictor

    db_path = ctx.obj["db_path"]
    predictor = FightPredictor(db_path)
    rich_console.print("[bold green]Training Fight Outcome ML Predictor...[/]")

    metrics = predictor.train(test_size=test_size)

    if "error" in metrics:
        rich_console.print(f"[bold red]{metrics['error']}[/]")
        return

    table = Table(title="Model Evaluation Metrics (Out-of-Time Test Set)", box=box.ROUNDED)
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="bold green")

    table.add_row("Training Samples", str(metrics["train_samples"]))
    table.add_row("Test Samples", str(metrics["test_samples"]))
    table.add_row("Accuracy", f"{metrics['accuracy']:.1f}%")
    table.add_row("ROC-AUC", f"{metrics['roc_auc']:.3f}")
    table.add_row("Log Loss", f"{metrics['log_loss']:.3f}")
    table.add_row("Precision", f"{metrics['precision']:.3f}")
    table.add_row("Recall", f"{metrics['recall']:.3f}")
    table.add_row("F1 Score", f"{metrics['f1_score']:.3f}")

    rich_console.print(table)

    predictor.save_model(output)
    rich_console.print(f"[bold green]Model saved -> {Path(output).resolve()}[/]")


# ------------------------------------------------------------------
# cache
# ------------------------------------------------------------------

@cli.command()
@click.option("--stats", is_flag=True, help="Display cache statistics")
@click.option("--clear", is_flag=True, help="Clear all cached files")
@click.pass_context
def cache(ctx, stats, clear):
    """Manage disk cache"""
    fc = FileCache(ctx.obj["cache_dir"])

    if stats:
        s = fc.stats()
        table = Table(title="Cache Statistics", box=box.ROUNDED)
        table.add_column("Metric", style="bold")
        table.add_column("Value", style="green")
        table.add_row("Cached Files", str(s["files"]))
        table.add_row("Total Size", f"{s['size_mb']} MB")
        table.add_row("Cache Hits", str(s["hits"]))
        table.add_row("Cache Misses", str(s["misses"]))
        table.add_row("Hit Rate", f"{s['hit_rate_pct']}%")
        rich_console.print(table)

    if clear:
        if click.confirm("Are you sure you want to clear the cache?"):
            count = fc.clear()
            rich_console.print(f"[bold green]Cleared {count} files[/]")


# ------------------------------------------------------------------
# db
# ------------------------------------------------------------------

@cli.command()
@click.option("--stats", is_flag=True, help="Display database statistics")
@click.pass_context
def db(ctx, stats):
    """Inspect database status"""
    database = Database(ctx.obj["db_path"])

    if stats:
        s = database.summary()
        table = Table(title=f"Database: {ctx.obj['db_path']}", box=box.ROUNDED)
        table.add_column("Table", style="bold")
        table.add_column("Row Count", style="green")
        table.add_row("Events", str(s["events"]))
        table.add_row("Fighters", str(s["fighters"]))
        table.add_row("Fights", str(s["fights"]))
        table.add_row("Round Stats Rows", str(s["round_stats_rows"]))
        rich_console.print(table)


# ------------------------------------------------------------------
# check
# ------------------------------------------------------------------

@cli.command()
@click.pass_context
def check(ctx):
    """Check database integrity and data quality diagnostics"""
    checker = DatabaseChecker(ctx.obj["db_path"])
    report = checker.run_diagnostics()

    if "error" in report:
        rich_console.print(f"[bold red]{report['error']}[/]")
        return

    table = Table(title=f"Data Quality & Integrity Report ({report['db_path']})", box=box.ROUNDED)
    table.add_column("Diagnostic Check", style="bold white")
    table.add_column("Status / Count", style="cyan")

    table.add_row("Health Score", f"[bold green]{report['health_score_pct']}%[/]")
    table.add_row("Orphan Fights", str(report['orphans']['orphan_fights']))
    table.add_row("Orphan Fight Stats", str(report['orphans']['orphan_fight_stats']))
    table.add_row("Orphan Round Stats", str(report['orphans']['orphan_round_stats']))
    table.add_row("Unlinked Fighter IDs", str(report['missing_links']['unlinked_fighters_count']))
    table.add_row("Completed Fights Missing Stats", str(report['missing_links']['completed_fights_missing_stats']))
    table.add_row("Fighters Missing Reach", str(report['profile_coverage']['missing_reach_count']))
    table.add_row("Fighters Missing DOB", str(report['profile_coverage']['missing_dob_count']))
    table.add_row("Invalid Strike Anomalies", str(report['anomalies']['invalid_strikes_count']))

    rich_console.print(table)


# ------------------------------------------------------------------
# serve
# ------------------------------------------------------------------

@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Host address to bind HTTP server")
@click.option("--port", default=8000, show_default=True, type=int, help="Port to bind HTTP server")
@click.pass_context
def serve(ctx, host, port):
    """Start embedded FastAPI REST API server with interactive Swagger UI"""
    try:
        import uvicorn
        from src.api import app, set_db_path
    except ImportError:
        rich_console.print("[bold red]FastAPI and Uvicorn are required for REST API. Run: pip install fastapi uvicorn[/]")
        return

    set_db_path(ctx.obj["db_path"])
    rich_console.print(f"[bold green]Starting UFCStats REST API server at http://{host}:{port}[/]")
    rich_console.print(f"[bold cyan]Interactive Swagger UI available at http://{host}:{port}/docs[/]")
    uvicorn.run(app, host=host, port=port, log_level="info")


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    cli(obj={})
