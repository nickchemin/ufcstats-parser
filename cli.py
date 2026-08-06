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

from datetime import date
import sqlite3
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
    existing_ids = set(db.get_complete_fighter_ids()) if incremental else set()

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
    existing_ids = set(db.get_complete_fighter_ids()) if incremental else set()

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
# predict-card
# ------------------------------------------------------------------

def _generate_html_fight_report(event_name: str, event_date: str, predictions: list) -> str:
    import html
    cards_html = []
    for item in predictions:
        f = item["fight"]
        f1 = item["fighter1"]
        f2 = item["fighter2"]
        pred = item["prediction"]

        name1 = f"{f1.get('first_name') or ''} {f1.get('last_name') or ''}".strip() or f.get("fighter1_name") or "Fighter 1"
        name2 = f"{f2.get('first_name') or ''} {f2.get('last_name') or ''}".strip() or f.get("fighter2_name") or "Fighter 2"

        p1 = int(round(pred["fighter1_win_probability"] * 100))
        p2 = int(round(pred["fighter2_win_probability"] * 100))
        winner_name = name1 if pred["predicted_winner"] == 1 else name2

        cards_html.append(f"""
        <div class="card">
            <div class="matchup-header">
                <div>
                    <div class="weight-class">{html.escape(str(f.get('weight_class') or 'Bout'))} {'🏆 Title Fight' if f.get('title_fight') else ''}</div>
                    <div class="fighter-names"><span class="f1">{html.escape(name1)}</span> vs <span class="f2">{html.escape(name2)}</span></div>
                </div>
                <div class="winner-badge">Predicted Winner: {html.escape(winner_name)} ({pred['confidence_pct']}%)</div>
            </div>
            <div class="prob-bar">
                <div class="prob-fill f1-fill" style="width: {p1}%;">{p1}%</div>
                <div class="prob-fill f2-fill" style="width: {p2}%;">{p2}%</div>
            </div>
            <table class="tape-table">
                <tr><th>{html.escape(str(f1.get('height_cm') or '--'))} cm</th><th>Height</th><th>{html.escape(str(f2.get('height_cm') or '--'))} cm</th></tr>
                <tr><th>{html.escape(str(f1.get('reach_cm') or '--'))} cm</th><th>Reach</th><th>{html.escape(str(f2.get('reach_cm') or '--'))} cm</th></tr>
                <tr><th>{html.escape(str(f1.get('stance') or '--'))}</th><th>Stance</th><th>{html.escape(str(f2.get('stance') or '--'))}</th></tr>
                <tr><th>{f1.get('wins', 0)}W-{f1.get('losses', 0)}L</th><th>Record</th><th>{f2.get('wins', 0)}W-{f2.get('losses', 0)}L</th></tr>
                <tr><th>{html.escape(str(f1.get('slpm') or '--'))}</th><th>Sig. Strikes / min</th><th>{html.escape(str(f2.get('slpm') or '--'))}</th></tr>
                <tr><th>{html.escape(str(f1.get('td_avg') or '--'))}</th><th>Takedowns / 15m</th><th>{html.escape(str(f2.get('td_avg') or '--'))}</th></tr>
            </table>
        </div>
        """)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>UFC Card Predictions: {html.escape(event_name)}</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 2rem; }}
        h1 {{ text-align: center; color: #f59e0b; margin-bottom: 0.5rem; }}
        .subtitle {{ text-align: center; color: #94a3b8; margin-bottom: 2rem; }}
        .card {{ background: rgba(30, 41, 59, 0.8); border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; border: 1px solid rgba(255, 255, 255, 0.1); box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3); }}
        .matchup-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }}
        .weight-class {{ font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px; }}
        .fighter-names {{ font-size: 1.4rem; font-weight: bold; margin-top: 0.2rem; }}
        .f1 {{ color: #ef4444; }}
        .f2 {{ color: #3b82f6; }}
        .winner-badge {{ background: #10b981; color: #022c22; font-weight: bold; padding: 0.5rem 1rem; border-radius: 20px; font-size: 0.9rem; }}
        .prob-bar {{ display: flex; height: 28px; border-radius: 14px; overflow: hidden; background: #334155; margin: 1rem 0; font-weight: bold; font-size: 0.9rem; line-height: 28px; text-align: center; }}
        .f1-fill {{ background: linear-gradient(90deg, #dc2626, #ef4444); color: white; }}
        .f2-fill {{ background: linear-gradient(90deg, #2563eb, #3b82f6); color: white; }}
        .tape-table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.9rem; }}
        .tape-table th {{ padding: 0.4rem; text-align: center; border-bottom: 1px solid #334155; }}
        .tape-table th:nth-child(2) {{ color: #94a3b8; font-weight: normal; }}
    </style>
</head>
<body>
    <h1>🥊 UFC Fight Card Predictions Report</h1>
    <div class="subtitle">{html.escape(event_name)} | {html.escape(str(event_date))}</div>
    {''.join(cards_html)}
</body>
</html>
"""


def _generate_md_fight_report(event_name: str, event_date: str, predictions: list) -> str:
    lines = [
        f"# 🥊 UFC Fight Card Predictions: {event_name}",
        f"**Event Date**: {event_date}",
        "",
        "| Matchup | Win Probabilities | Predicted Winner | Confidence |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for item in predictions:
        f = item["fight"]
        f1 = item["fighter1"]
        f2 = item["fighter2"]
        pred = item["prediction"]

        name1 = f"{f1.get('first_name') or ''} {f1.get('last_name') or ''}".strip() or f.get("fighter1_name") or "Fighter 1"
        name2 = f"{f2.get('first_name') or ''} {f2.get('last_name') or ''}".strip() or f.get("fighter2_name") or "Fighter 2"

        p1 = int(round(pred["fighter1_win_probability"] * 100))
        p2 = int(round(pred["fighter2_win_probability"] * 100))
        winner_name = name1 if pred["predicted_winner"] == 1 else name2

        lines.append(f"| **{name1}** vs **{name2}** | {p1}% vs {p2}% | **{winner_name}** | {pred['confidence_pct']}% |")

    lines.append("")
    lines.append("## Detailed Matchup Previews")
    lines.append("")

    for item in predictions:
        f1 = item["fighter1"]
        f2 = item["fighter2"]
        pred = item["prediction"]
        name1 = f"{f1.get('first_name') or ''} {f1.get('last_name') or ''}".strip()
        name2 = f"{f2.get('first_name') or ''} {f2.get('last_name') or ''}".strip()

        lines.append(f"### {name1} vs {name2}")
        lines.append(f"- **Predicted Winner**: {name1 if pred['predicted_winner'] == 1 else name2} ({pred['confidence_pct']}%)")
        lines.append(f"- **Tale of the Tape**: Height ({f1.get('height_cm','--')} cm vs {f2.get('height_cm','--')} cm), Reach ({f1.get('reach_cm','--')} cm vs {f2.get('reach_cm','--')} cm), Stance ({f1.get('stance','--')} vs {f2.get('stance','--')})")
        lines.append("")

    return "\n".join(lines)


@cli.command("predict-card")
@click.option("--event-id", "-e", default=None, help="Target Event ID. Auto-detects upcoming if omitted.")
@click.option("--output", "-o", default=None, help="Output report path (e.g. data/predict_card.html)")
@click.option("--format", "fmt", type=click.Choice(["html", "markdown", "json"]), default="html", show_default=True, help="Report output format")
@click.pass_context
def predict_card(ctx, event_id, output, fmt):
    """Generates ML predictions and Tale of the Tape preview report for an entire UFC fight card"""
    db_path = ctx.obj["db_path"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        if not event_id:
            row = conn.execute("SELECT event_id, name, date FROM events WHERE date IS NULL OR date >= date('now') ORDER BY date ASC LIMIT 1").fetchone()
            if not row:
                row = conn.execute("SELECT event_id, name, date FROM events ORDER BY date DESC LIMIT 1").fetchone()
            if not row:
                rich_console.print("[bold red]No events found in database. Please run python cli.py crawl first.[/]")
                return
            event_id = row["event_id"]
            event_name = row["name"]
            event_date = row["date"]
        else:
            row = conn.execute("SELECT event_id, name, date FROM events WHERE event_id = ?", (event_id,)).fetchone()
            event_name = row["name"] if row else event_id
            event_date = row["date"] if row else "TBD"

        rich_console.print(f"[bold cyan]Simulating predictions for fight card: {event_name} ({event_date})[/]")

        fights = conn.execute("SELECT * FROM fights WHERE event_id = ?", (event_id,)).fetchall()
        if not fights:
            rich_console.print(f"[bold red]No fights found in database for event {event_id}.[/]")
            return

        from src.ml.predictor import FightPredictor
        from src.storage.ml_dataset import MLDatasetGenerator

        predictor = FightPredictor(db_path)
        if not predictor.load_model():
            rich_console.print("[yellow]Model not found on disk. Training Ensemble Predictor...[/]")
            predictor.train()
            predictor.save_model()

        generator = MLDatasetGenerator(db_path)
        trackers = generator.get_fighter_trackers()

        today = date.today()
        def get_age(dob_str):
            if not dob_str: return None
            try:
                d = date.fromisoformat(str(dob_str))
                return round((today - d).days / 365.25, 1)
            except Exception:
                return None

        fight_predictions = []

        table = Table(title=f"Predictions for {event_name}", box=box.ROUNDED)
        table.add_column("Matchup", style="bold white")
        table.add_column("Probabilities", style="bold yellow")
        table.add_column("Predicted Winner", style="bold green")
        table.add_column("Confidence", style="bold cyan")

        for fight in fights:
            f1_id = fight["fighter1_id"]
            f2_id = fight["fighter2_id"]

            f1 = conn.execute("SELECT * FROM fighters WHERE fighter_id = ?", (f1_id,)).fetchone() if f1_id else None
            f2 = conn.execute("SELECT * FROM fighters WHERE fighter_id = ?", (f2_id,)).fetchone() if f2_id else None

            d1 = dict(f1) if f1 else {"first_name": fight["fighter1_name"], "last_name": "", "fighter_id": f1_id}
            d2 = dict(f2) if f2 else {"first_name": fight["fighter2_name"], "last_name": "", "fighter_id": f2_id}

            t1 = trackers.get(f1_id, {"elo": 1500.0, "wins": d1.get("wins") or 0, "losses": d1.get("losses") or 0, "streak": 0})
            t2 = trackers.get(f2_id, {"elo": 1500.0, "wins": d2.get("wins") or 0, "losses": d2.get("losses") or 0, "streak": 0})

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

            pred = predictor.predict_matchup(feat1, feat2)
            p1 = round(pred["fighter1_win_probability"] * 100)
            p2 = round(pred["fighter2_win_probability"] * 100)

            name1 = f"{d1.get('first_name') or ''} {d1.get('last_name') or ''}".strip() or fight["fighter1_name"]
            name2 = f"{d2.get('first_name') or ''} {d2.get('last_name') or ''}".strip() or fight["fighter2_name"]

            winner_name = name1 if pred["predicted_winner"] == 1 else name2

            table.add_row(
                f"{name1} vs {name2}",
                f"{p1}% vs {p2}%",
                winner_name,
                f"{pred['confidence_pct']}%"
            )

            fight_predictions.append({
                "fight": dict(fight),
                "fighter1": d1,
                "fighter2": d2,
                "prediction": pred,
            })

        rich_console.print(table)

        if not output:
            output = f"data/predict_card_{event_id}.{fmt}"

        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if fmt == "html":
            content = _generate_html_fight_report(event_name, event_date, fight_predictions)
        elif fmt == "markdown":
            content = _generate_md_fight_report(event_name, event_date, fight_predictions)
        else:
            import json
            content = json.dumps({"event_name": event_name, "event_date": event_date, "predictions": fight_predictions}, indent=2, default=str)
        out_path.write_text(content, encoding="utf-8")

        rich_console.print(f"[bold green]Fight card prediction report exported to -> {out_path.resolve()}[/]")

    finally:
        conn.close()


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    cli(obj={})
