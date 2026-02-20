"""
Structured colored logger for all modules.

Usage:
    from utils.logger import get_logger
    logger = get_logger(__name__)
"""

import logging
import sys
from pathlib import Path
from typing import Optional


class _ColoredFormatter(logging.Formatter):
    """Adds ANSI color codes per log level for terminal readability."""

    COLORS = {
        "DEBUG":    "\033[36m",   # Cyan
        "INFO":     "\033[32m",   # Green
        "WARNING":  "\033[33m",   # Yellow
        "ERROR":    "\033[31m",   # Red
        "CRITICAL": "\033[35m",   # Magenta
        "RESET":    "\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        reset = self.COLORS["RESET"]
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


def setup_logger(
    name: str,
    level: str = "INFO",
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Create a logger with console output and optional file output.

    Args:
        name:     Logger name (pass __name__ from the calling module).
        level:    One of DEBUG / INFO / WARNING / ERROR / CRITICAL.
        log_file: Optional path for a file handler.

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG)
    console.setFormatter(
        _ColoredFormatter(
            fmt="%(levelname)s | %(asctime)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(console)

    # File handler (optional)
    if log_file:
        try:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(
                logging.Formatter(
                    fmt="%(levelname)s | %(asctime)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            logger.addHandler(fh)
        except Exception as exc:
            logger.error(f"Failed to set up file logging: {exc}")

    logger.propagate = False
    return logger


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper — returns the named logger (creates if missing)."""
    return logging.getLogger(name)