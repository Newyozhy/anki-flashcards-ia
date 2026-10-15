import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List

# Path to backend/logs/app.log
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = BACKEND_DIR / "logs"
LOG_FILE = LOGS_DIR / "app.log"

LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5


def setup_logging(log_level: int = logging.INFO) -> None:
    """Configure root and app loggers to output to stdout and rotating file."""
    # Ensure logs directory exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Formatter
    formatter = logging.Formatter(LOG_FORMAT)

    # Console Handler (sys.stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # File Handler with utf-8 encoding and rotation
    file_handler = RotatingFileHandler(
        str(LOG_FILE),
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    # Root Logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    # Remove existing handlers that might conflict
    existing_handler_types = {type(h) for h in root_logger.handlers}
    if RotatingFileHandler not in existing_handler_types:
        root_logger.addHandler(file_handler)
    if logging.StreamHandler not in existing_handler_types:
        root_logger.addHandler(console_handler)

    # Ensure app logger propagates to root
    app_logger = logging.getLogger("app")
    app_logger.setLevel(log_level)


def get_recent_log_lines(max_lines: int = 150) -> List[str]:
    """Read and return the last `max_lines` from the rotating log file."""
    if not LOG_FILE.exists():
        return []

    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return [line.rstrip("\r\n") for line in lines[-max_lines:]]
    except Exception as e:
        return [f"Error reading log file: {str(e)}"]
