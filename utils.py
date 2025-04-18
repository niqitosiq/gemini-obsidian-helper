import logging
import sys
import config
from datetime import datetime, time


def setup_logging():
    """Sets up basic logging configuration."""
    log_level_name = config.LOG_LEVEL
    log_level = getattr(logging, log_level_name, logging.INFO)  # Default to INFO

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
    # Reduce noise from libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.INFO)
    logging.getLogger("todoist_api").setLevel(logging.INFO)

    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured at level: {log_level_name}")


def is_working_time(
    dt: datetime, work_days: list[int], start_hour: int, end_hour: int
) -> bool:
    """Checks if datetime falls within working hours."""
    if dt.isoweekday() not in work_days:
        return False
    start_time = time(start_hour)
    end_time = time(end_hour)
    return start_time <= dt.time() < end_time
