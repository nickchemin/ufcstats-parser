"""
Unit tests for CLI commands and incremental crawler early-stopping logic.
"""

from unittest.mock import MagicMock, patch
from click.testing import CliRunner
from cli import cli, _crawl_all_events
from src.storage.models import Event


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "UFCStats Parser" in result.output


def test_crawl_all_events_incremental_early_stopping():
    mock_scraper = MagicMock()
    mock_db = MagicMock()

    # Mock 10 events returned by parser
    events = [
        Event(event_id=f"evt_{i}", url=f"http://example.com/evt_{i}", name=f"UFC Event {i}")
        for i in range(10)
    ]

    # Pre-populate DB with events evt_1 through evt_9 (so after processing new evt_0, evt_1..5 trigger early stop)
    existing_ids = {f"evt_{i}" for i in range(1, 10)}
    mock_db.get_event_ids.return_value = list(existing_ids)

    with patch("cli.EVENTS_URL", "mock_url"), \
         patch("cli.parse_events_page", return_value=events), \
         patch("cli._process_event") as mock_process_event:
        
        _crawl_all_events(mock_scraper, mock_db, incremental=True, no_fight_details=False, limit_events=None)

        # Only evt_0 should be processed via _process_event because evt_1..evt_5 hit 5 consecutive existing events
        assert mock_process_event.call_count == 1
        processed_event = mock_process_event.call_args[0][2]
        assert processed_event.event_id == "evt_0"


def test_cli_async_crawl(tmp_path):
    db_file = tmp_path / "cli_async_test.db"
    runner = CliRunner()

    with patch("cli._async_crawl_all_events") as mock_async_crawl:
        result = runner.invoke(cli, ["--db", str(db_file), "crawl", "--all", "--async", "--limit-events", "1"])
        assert result.exit_code == 0
        assert mock_async_crawl.called
