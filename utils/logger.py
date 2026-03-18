"""
Structured logging — Rich console + rotating file handler.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from rich.console import Console
from rich.logging import RichHandler
from config.settings import settings

# Fix Windows Unicode issues with Rich
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Force UTF-8 on Windows stdout/stderr
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def setup_logger(name: str = "weather_bot") -> logging.Logger:
    """Create and return a configured logger instance."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # ── Console handler (Rich — with Windows compatibility) ──
    console = Console(force_terminal=True, force_jupyter=False, no_color=False)
    console_handler = RichHandler(
        level=logging.INFO,
        show_time=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
        console=console,
    )
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console_handler)

    # ── File handler (rotating) ──
    file_handler = RotatingFileHandler(
        settings.LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(file_handler)

    return logger


log = setup_logger()
