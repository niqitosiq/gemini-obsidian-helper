# This file makes the 'recurring_events' directory a Python package.

from .engine import RecurringEventsEngine
from .global_events import load_global_events
from .vault_tasks import (
    parse_frontmatter,
    extract_and_validate_task_details,
    calculate_reminder_times,
    load_vault_tasks,
    handle_vault_file_event,
    DEFAULT_TASKS_DIR_RELATIVE,  # Expose the constant
)
from .event_handling import (
    validate_event_data,
    schedule_event,
    handle_time_event,
    execute_event,
)

__all__ = [
    "RecurringEventsEngine",
    "load_global_events",
    "parse_frontmatter",
    "extract_and_validate_task_details",
    "calculate_reminder_times",
    "load_vault_tasks",
    "handle_vault_file_event",
    "validate_event_data",
    "schedule_event",
    "handle_time_event",
    "execute_event",
    "DEFAULT_TASKS_DIR_RELATIVE",  # Add to __all__
]
