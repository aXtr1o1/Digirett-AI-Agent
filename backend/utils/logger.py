import logging
import sys
from pathlib import Path
from typing import Optional


class _ColoredFormatter(logging.Formatter):
    """Adds ANSI color codes per log level and OpenTelemetry trace correlation."""

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

        # OpenTelemetry Trace Context Correlation
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            span_ctx = span.get_span_context() if span else None
            if span_ctx and span_ctx.is_valid:
                record.trace_id = f"{span_ctx.trace_id:032x}"
                record.span_id = f"{span_ctx.span_id:016x}"
            else:
                record.trace_id = "0" * 32
                record.span_id = "0" * 16
        except Exception:
            record.trace_id = "0" * 32
            record.span_id = "0" * 16

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