import logging
import json
import os
from typing import Dict, Any

# --- Интерфейсы ---
from services.interfaces import IRecurringEventsEngine

logger = logging.getLogger(__name__)

GLOBAL_EVENTS_CONFIG_PATH = "global_recurring_events.json"


def load_global_events(
    engine: IRecurringEventsEngine, events_dict: Dict[str, Dict[str, Any]]
) -> None:
    """Загружает глобальные события из JSON файла."""
    logger.debug(f"Loading global events from {GLOBAL_EVENTS_CONFIG_PATH}")
    try:
        if os.path.exists(GLOBAL_EVENTS_CONFIG_PATH):
            with open(GLOBAL_EVENTS_CONFIG_PATH, "r", encoding="utf-8") as f:
                global_events = json.load(f)
            logger.info(f"Loaded {len(global_events)} global recurring events")
            for event_id, event_data in global_events.items():
                # Assuming _validate_event_data is a method of the engine or a separate utility
                if engine._validate_event_data(event_id, event_data):
                    event_data["is_global"] = True
                    events_dict[event_id] = event_data
                else:
                    logger.error(
                        f"Invalid event data structure for global event '{event_id}'. Skipping."
                    )
        else:
            logger.info(
                f"Global events file not found: {GLOBAL_EVENTS_CONFIG_PATH}. No global events loaded."
            )
    except Exception as e:
        logger.error(f"Error loading global recurring events: {e}", exc_info=True)
