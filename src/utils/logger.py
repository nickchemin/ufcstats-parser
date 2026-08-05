"""
Rich logger configuration and progress indicators.
"""

import logging
import sys

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
    MofNCompleteColumn,
)
from rich.theme import Theme

THEME = Theme(
    {
        "logging.level.debug": "dim cyan",
        "logging.level.info": "bold green",
        "logging.level.warning": "bold yellow",
        "logging.level.error": "bold red",
        "logging.level.critical": "bold white on red",
        "progress.description": "bold white",
        "progress.percentage": "bold cyan",
    }
)

console = Console(theme=THEME)

_configured = False


def setup_logging(level: str = "INFO") -> None:
    """Configures Rich logging for the application."""
    global _configured
    if _configured:
        return

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=console,
                rich_tracebacks=True,
                show_path=False,
                markup=True,
            )
        ],
    )
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Returns a logger configured with Rich handler."""
    setup_logging()
    return logging.getLogger(name)


def make_progress(description: str = "Processing...") -> Progress:
    """Creates a progress bar compatible across operating systems."""
    return Progress(
        TextColumn("[bold white]{task.description}"),
        BarColumn(bar_width=40, style="cyan", complete_style="bold green"),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    )
