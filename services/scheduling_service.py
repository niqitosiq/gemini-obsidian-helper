import logging
import time
import threading
import schedule
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from typing import Optional, Callable, Dict

from .interfaces import (
    ISchedulingService,
    IConfigService,
    TimeEventCallback,
    FileEventCallback,
    FileEventData,
)

logger = logging.getLogger(__name__)


class _WatchdogHandler(FileSystemEventHandler):
    """Внутренний обработчик событий watchdog."""

    def __init__(self, callback: FileEventCallback):
        self.callback = callback
        logger.debug("WatchdogHandler initialized.")

    def on_any_event(self, event: FileSystemEvent):
        """Перехватывает все события."""
        if event.is_directory and event.event_type == "modified":
            return

        logger.info(
            f"Watchdog event: {event.event_type} - {event.src_path} (is_dir={event.is_directory})"
        )
        event_data: FileEventData = {
            "event_type": event.event_type,
            "src_path": event.src_path,
            "is_directory": event.is_directory,
        }
        try:
            self.callback(event_data)
        except Exception as e:
            logger.error(
                f"Error in file event callback for {event.src_path}: {e}", exc_info=True
            )


class SchedulingServiceImpl(ISchedulingService):
    """Реализация сервиса планирования с использованием schedule и watchdog."""

    def __init__(self, config_service: IConfigService):
        self._config_service = config_service
        self._schedule_thread: Optional[threading.Thread] = None
        self._observer_thread: Optional[threading.Thread] = None
        self._watchdog_observer: Optional[Observer] = None
        self._watchdog_callback: Optional[FileEventCallback] = None
        self._watch_path: Optional[str] = None
        self._running = False
        self._lock = threading.Lock()
        logger.debug("SchedulingService initialized.")

    def _run_scheduler(self):
        """Целевая функция для потока schedule."""
        logger.info("Starting schedule runner thread...")
        while self._running:
            with self._lock:
                schedule.run_pending()
            time.sleep(0.1)
        logger.info("Schedule runner thread stopped.")

    def _run_observer(self):
        """Целевая функция для потока watchdog."""
        if not self._watchdog_observer:
            logger.error("Cannot start observer thread: observer not configured.")
            return
        logger.info(
            f"Starting watchdog observer thread for path: {self._watch_path}..."
        )
        self._watchdog_observer.start()
        try:
            while self._running and self._watchdog_observer.is_alive():
                time.sleep(0.5)
        except Exception as e:
            logger.error(f"Error in watchdog observer thread: {e}", exc_info=True)
        finally:
            if self._watchdog_observer.is_alive():
                self._watchdog_observer.stop()
            self._watchdog_observer.join()
            logger.info("Watchdog observer thread stopped.")

    def schedule_daily(
        self, time_str: str, event_id: str, callback: TimeEventCallback
    ) -> None:
        with self._lock:
            logger.info(f"Scheduling daily job '{event_id}' at {time_str}")
            schedule.every().day.at(time_str).do(callback, event_id=event_id).tag(
                event_id
            )

    def schedule_weekly(
        self,
        weekday_str: str,
        time_str: str,
        event_id: str,
        callback: TimeEventCallback,
    ) -> None:
        with self._lock:
            logger.info(
                f"Scheduling weekly job '{event_id}' on {weekday_str} at {time_str}"
            )
            day_attr = getattr(schedule.every(), weekday_str.lower(), None)
            if day_attr:
                day_attr.at(time_str).do(callback, event_id=event_id).tag(event_id)
            else:
                logger.error(
                    f"Invalid weekday '{weekday_str}' for scheduling event '{event_id}'"
                )

    def schedule_interval(
        self, interval: int, unit: str, event_id: str, callback: TimeEventCallback
    ) -> None:
        with self._lock:
            logger.info(f"Scheduling interval job '{event_id}' every {interval} {unit}")
            job = schedule.every(interval)
            unit_attr = getattr(job, unit.lower(), None)
            if unit_attr:
                unit_attr.do(callback, event_id=event_id).tag(event_id)
            else:
                logger.error(
                    f"Invalid unit '{unit}' for interval scheduling event '{event_id}'"
                )

    def add_job(
        self, schedule_dsl: str, event_id: str, callback: TimeEventCallback
    ) -> bool:
        logger.info(
            f"Attempting to schedule job '{event_id}' with DSL: '{schedule_dsl}'"
        )
        try:
            parts = schedule_dsl.lower().split()
            if len(parts) >= 3 and parts[0] == "daily" and parts[1] == "at":
                time_str = parts[2]
                self.schedule_daily(time_str, event_id, callback)
                return True
            elif (
                len(parts) >= 3
                and parts[0] == "every"
                and parts[2] in ["minute", "minutes", "hour", "hours", "day", "days"]
            ):
                interval = int(parts[1])
                unit = parts[2]
                self.schedule_interval(interval, unit, event_id, callback)
                return True
            else:
                logger.error(
                    f"Could not parse schedule DSL for event '{event_id}': {schedule_dsl}"
                )
                return False
        except Exception as e:
            logger.error(
                f"Error parsing or scheduling DSL for event '{event_id}': {e}",
                exc_info=True,
            )
            return False

    def unschedule(self, event_id: str) -> None:
        with self._lock:
            logger.info(f"Unscheduling job '{event_id}'")
            schedule.clear(event_id)

    def watch_directory(self, path: str, callback: FileEventCallback) -> None:
        if self._watchdog_observer is not None:
            logger.warning(
                f"Watchdog observer already configured for path: {self._watch_path}. Ignoring new request for {path}."
            )
            return

        if not os.path.isdir(path):
            logger.error(
                f"Cannot watch directory: path '{path}' is not a valid directory."
            )
            return

        self._watch_path = path
        self._watchdog_callback = callback
        event_handler = _WatchdogHandler(self._watchdog_callback)
        self._watchdog_observer = Observer()
        self._watchdog_observer.schedule(
            event_handler, self._watch_path, recursive=True
        )
        logger.info(f"Watchdog observer configured for path: {self._watch_path}")

    def start(self) -> None:
        if self._running:
            logger.warning("SchedulingService is already running.")
            return

        logger.info("Starting SchedulingService...")
        self._running = True

        self._schedule_thread = threading.Thread(
            target=self._run_scheduler, daemon=True
        )
        self._schedule_thread.start()

        if self._watchdog_observer:
            self._observer_thread = threading.Thread(
                target=self._run_observer, daemon=True
            )
            self._observer_thread.start()
        else:
            logger.info(
                "Watchdog observer not configured, skipping observer thread start."
            )

    def stop(self) -> None:
        if not self._running:
            logger.warning("SchedulingService is not running.")
            return

        logger.info("Stopping SchedulingService...")
        self._running = False

        if self._observer_thread and self._observer_thread.is_alive():
            self._observer_thread.join(timeout=5)

        if self._schedule_thread and self._schedule_thread.is_alive():
            self._schedule_thread.join(timeout=2)

        with self._lock:
            schedule.clear()

        self._watchdog_observer = None
        self._watch_path = None
        self._watchdog_callback = None
        logger.info("SchedulingService stopped.")
