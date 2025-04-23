import logging
import time
import threading
import datetime
import json
import os
import re
import schedule
from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEventHandler,
    FileCreatedEvent,
    FileModifiedEvent,
    FileDeletedEvent,
)
from typing import Dict, List, Any, Optional

from llm_handler import call_llm_sync
from prompt_builder import get_system_prompt
from google.genai import types
from message_processor import _process_llm_response
from config import OBSIDIAN_VAULT_PATH

logger = logging.getLogger(__name__)

# Path to store global recurring events configuration
GLOBAL_EVENTS_CONFIG_PATH = "global_recurring_events.json"


class TaskFileHandler(FileSystemEventHandler):
    """Handles file system events for task files."""

    def __init__(self, engine):
        self.engine = engine

    def on_created(self, event):
        if isinstance(event, FileCreatedEvent) and event.src_path.endswith(".md"):
            logger.info(f"New task file detected: {event.src_path}")
            self.engine.schedule_from_file(event.src_path)

    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent) and event.src_path.endswith(".md"):
            logger.info(f"Task file modified: {event.src_path}")
            self.engine.schedule_from_file(event.src_path)

    def on_deleted(self, event):
        if isinstance(event, FileDeletedEvent) and event.src_path.endswith(".md"):
            logger.info(f"Task file deleted: {event.src_path}")
            # Extract event_id from filename if possible
            filename = os.path.basename(event.src_path)
            event_id = os.path.splitext(filename)[0]
            self.engine.remove_event(event_id)


class RecurringEventsEngine:
    """
    An engine that watches task files in the Obsidian vault
    and schedules recurring events based on their content.
    """

    def __init__(self):
        self.events = {}  # Store event definitions
        self.running = False
        self.thread = None
        self.file_observer = None
        self.load_global_events()

    def load_global_events(self) -> None:
        """Load global recurring events from configuration file."""
        try:
            if os.path.exists(GLOBAL_EVENTS_CONFIG_PATH):
                with open(GLOBAL_EVENTS_CONFIG_PATH, "r", encoding="utf-8") as f:
                    global_events = json.load(f)
                    logger.info(f"Loaded {len(global_events)} global recurring events")

                    # Add global events to our events dictionary
                    for event_id, event_data in global_events.items():
                        self.events[event_id] = event_data
            else:
                logger.info(
                    "No global recurring events configuration found. Creating default."
                )
                # Create a default global events file with a morning greeting example
                default_events = {
                    "morning_greeting": {
                        "schedule_time": "daily at 9:00",
                        "prompt": "Good morning! It's {date}. What are your plans for today?",
                        "description": "Daily morning greeting",
                        "last_run": None,
                        "created_at": datetime.datetime.now().isoformat(),
                    }
                }
                with open(GLOBAL_EVENTS_CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(default_events, f, indent=2, ensure_ascii=False)
                logger.info("Created default global events configuration")

                # Add the default events to our events dictionary
                for event_id, event_data in default_events.items():
                    self.events[event_id] = event_data

        except Exception as e:
            logger.error(f"Error loading global recurring events: {e}", exc_info=True)

    def save_global_events(self) -> None:
        """Save global recurring events to configuration file."""
        try:
            # Filter out task-based events (those with task_file attribute)
            global_events = {
                event_id: event_data
                for event_id, event_data in self.events.items()
                if "task_file" not in event_data
            }

            with open(GLOBAL_EVENTS_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(global_events, f, indent=2, ensure_ascii=False)
            logger.info(
                f"Saved {len(global_events)} global recurring events to configuration"
            )
        except Exception as e:
            logger.error(f"Error saving global recurring events: {e}", exc_info=True)

    def schedule_from_file(self, file_path: str) -> None:
        """
        Parse a task file and schedule events based on its content.

        Args:
            file_path: Path to the task file
        """
        try:
            if not os.path.exists(file_path):
                logger.warning(f"Task file not found: {file_path}")
                return

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Parse the file to extract scheduling information
            event_id = os.path.basename(file_path).rsplit(".", 1)[
                0
            ]  # Use filename without extension as event ID

            # Extract frontmatter using regex
            frontmatter_match = re.search(r"---\s*(.*?)\s*---", content, re.DOTALL)
            if not frontmatter_match:
                logger.warning(f"No frontmatter found in task file: {file_path}")
                return

            frontmatter = frontmatter_match.group(1)

            # Extract schedule information
            schedule_time = None

            # Look for recurrence rule in frontmatter
            recurrence_rule_match = re.search(r"recurrence_rule:\s*(.+)", frontmatter)
            if recurrence_rule_match:
                recurrence_rule = recurrence_rule_match.group(1).strip()

                # Convert recurrence rule to schedule format
                # Example: "Every Monday" -> "every monday at 9:00"
                schedule_time = self._parse_recurrence_rule(recurrence_rule)

            # Look for specific time information
            start_time_match = re.search(r"startTime:\s*(.+)", frontmatter)
            if start_time_match:
                start_time = start_time_match.group(1).strip()
                if schedule_time:
                    # If we have both a recurrence rule and a startTime, use the startTime
                    # Replace any time in the schedule with the startTime
                    schedule_time = re.sub(
                        r"at\s+\d{1,2}:\d{2}", f"at {start_time}", schedule_time
                    )
                else:
                    # Just use the start time for a daily schedule
                    schedule_time = f"daily at {start_time}"

            if not schedule_time:
                logger.warning(f"No scheduling information found in task: {file_path}")
                return

            # Extract task description to use as prompt
            description_match = re.search(
                r"## 📝 Описание\s*(.*?)(?:\s*##|$)", content, re.DOTALL
            )
            prompt = "Remind user for scheduled task"
            if description_match:
                task_description = description_match.group(1).strip()
                prompt = f"Reminder: {task_description}"

            # Get task title
            title_match = re.search(r"title:\s*(.+)", frontmatter)
            task_title = event_id
            if title_match:
                task_title = title_match.group(1).strip()

            # Create an event for this task
            self.events[event_id] = {
                "schedule_time": schedule_time,
                "prompt": f"Task due: {task_title}\n\n{prompt}",
                "description": f"Recurring task: {task_title}",
                "task_file": file_path,  # Store reference to the source file
                "last_run": None,
                "created_at": datetime.datetime.now().isoformat(),
            }

            # If engine is already running, schedule this event immediately
            if self.running:
                self._schedule_event(event_id, self.events[event_id])

            logger.info(
                f"Scheduled recurring event from task: {event_id} at {schedule_time}"
            )

        except Exception as e:
            logger.error(f"Error scheduling from file {file_path}: {e}", exc_info=True)

    def _parse_recurrence_rule(self, rule: str) -> str:
        """
        Convert Obsidian recurrence rule to schedule format.

        Args:
            rule: Recurrence rule from frontmatter

        Returns:
            Schedule time format for the schedule library
        """
        rule = rule.lower()

        # Handle common recurrence patterns
        if "every day" in rule or "daily" in rule:
            return "daily at 9:00"  # Default to 9:00 if no time specified

        weekdays = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        for day in weekdays:
            if day in rule:
                return f"every {day} at 9:00"

        # Handle "every X days/weeks/months"
        interval_match = re.search(r"every\s+(\d+)\s+(day|week|month)", rule)
        if interval_match:
            interval = interval_match.group(1)
            unit = interval_match.group(2)

            # Convert to schedule format
            if unit == "day":
                return f"every {interval} days at 9:00"
            elif unit == "week":
                return f"every {int(interval) * 7} days at 9:00"
            elif unit == "month":
                # Approximate months as 30 days
                return f"every {int(interval) * 30} days at 9:00"

        # Default fallback
        return "daily at 9:00"

    def add_event(
        self, event_id: str, schedule_time: str, prompt: str, description: str = ""
    ) -> bool:
        """
        Add a new recurring event manually.

        Args:
            event_id: Unique identifier for the event
            schedule_time: Cron-like schedule (e.g. "daily at 9:00", "every monday at 8:30")
            prompt: The prompt to send to the LLM
            description: Human-readable description of this event

        Returns:
            bool: True if event was added successfully
        """
        if event_id in self.events:
            logger.warning(f"Overwriting existing event with ID: {event_id}")

        # Clear any existing schedule for this event_id
        schedule.clear(event_id)

        self.events[event_id] = {
            "schedule_time": schedule_time,
            "prompt": prompt,
            "description": description or f"Scheduled event {event_id}",
            "last_run": None,
            "created_at": datetime.datetime.now().isoformat(),
        }

        # Apply the schedule if the engine is already running
        if self.running:
            self._schedule_event(event_id, self.events[event_id])

        self.save_global_events()
        logger.info(f"Added recurring event: {event_id} - {schedule_time}")
        return True

    def remove_event(self, event_id: str) -> bool:
        """
        Remove a recurring event.

        Args:
            event_id: ID of the event to remove

        Returns:
            bool: True if event was removed, False if not found
        """
        if event_id not in self.events:
            logger.warning(f"Event ID not found: {event_id}")
            return False

        # Clear any existing schedule
        schedule.clear(event_id)

        # If this is a global event (not from a task file), save the change
        is_global = "task_file" not in self.events[event_id]

        del self.events[event_id]

        if is_global:
            self.save_global_events()

        logger.info(f"Removed recurring event: {event_id}")
        return True

    def list_events(self) -> List[Dict[str, Any]]:
        """
        List all configured recurring events.

        Returns:
            List of event details with schedule info
        """
        result = []
        for event_id, event in self.events.items():
            result.append(
                {
                    "id": event_id,
                    "schedule": event["schedule_time"],
                    "description": event["description"],
                    "source": event.get("task_file", "global configuration"),
                    "last_run": event["last_run"],
                    "created_at": event["created_at"],
                }
            )
        return result

    def _execute_event(self, event_id: str, event_data: Dict[str, Any]) -> None:
        """
        Execute a scheduled event by sending the prompt to the LLM.

        Args:
            event_id: The ID of the event to execute
            event_data: Event configuration data
        """
        try:
            logger.info(f"Executing scheduled event: {event_id}")

            # Get current date and time
            current_date = datetime.datetime.now().strftime("%Y-%m-%d")
            current_time = datetime.datetime.now().strftime("%H:%M")

            # Extract task information to build the context
            task_title = event_data.get("description", f"Task {event_id}")
            task_description = event_data.get("prompt", "").format(
                date=current_date, time=current_time
            )

            # Use reminder_prompt_builder instead of direct formatting
            from reminder_prompt_builder import build_reminder_context

            # Create task data dictionary
            task_data = {
                "title": task_title,
                "description": task_description,
                "date": current_date,
                "startTime": current_time,
            }

            # If this is from a task file, include the file path
            if "task_file" in event_data:
                task_data["task_file"] = event_data["task_file"]

            # Build the reminder context with conversation history
            context = build_reminder_context(task_data)

            # Prepare system prompt
            # system_prompt = get_system_prompt(context)

            # Call LLM
            logger.info(
                f"Sending scheduled reminder for task {event_id}: {task_title[:100]}..."
            )
            response = call_llm_sync(
                contents=[context],
                response_mime_type="application/json",
            )

            # Process the LLM response to trigger any tool actions
            if response:
                result = _process_llm_response(response)
                logger.info(f"Scheduled event {event_id} completed. Result: {result}")
            else:
                logger.error(f"LLM call failed for scheduled event: {event_id}")

            # Update last_run timestamp
            self.events[event_id]["last_run"] = datetime.datetime.now().isoformat()

            # Save changes if this is a global event
            if "task_file" not in event_data:
                self.save_global_events()

        except Exception as e:
            logger.error(
                f"Error executing scheduled event {event_id}: {e}", exc_info=True
            )

    def _schedule_event(self, event_id: str, event_data: Dict[str, Any]) -> None:
        """
        Apply the scheduling rule for an event.

        Args:
            event_id: The event ID to schedule
            event_data: Event configuration data
        """
        schedule_time = event_data["schedule_time"].lower()

        # Parse schedule_time and set up the job
        try:
            job = None

            # Handle different schedule formats
            if schedule_time.startswith("every"):
                parts = schedule_time.split()

                if len(parts) >= 3 and parts[2] == "at":
                    # Format: "every monday at 10:00"
                    day = parts[1]
                    time_str = parts[3]

                    if day == "monday":
                        job = schedule.every().monday.at(time_str)
                    elif day == "tuesday":
                        job = schedule.every().tuesday.at(time_str)
                    elif day == "wednesday":
                        job = schedule.every().wednesday.at(time_str)
                    elif day == "thursday":
                        job = schedule.every().thursday.at(time_str)
                    elif day == "friday":
                        job = schedule.every().friday.at(time_str)
                    elif day == "saturday":
                        job = schedule.every().saturday.at(time_str)
                    elif day == "sunday":
                        job = schedule.every().sunday.at(time_str)
                    elif day == "day":
                        job = schedule.every().day.at(time_str)
                else:
                    # Format: "every 1 hour"
                    interval = int(parts[1])
                    unit = parts[2]

                    if unit in ["minute", "minutes"]:
                        job = schedule.every(interval).minutes
                    elif unit in ["hour", "hours"]:
                        job = schedule.every(interval).hours
                    elif unit in ["day", "days"]:
                        job = schedule.every(interval).days

            elif schedule_time.startswith("daily at"):
                # Format: "daily at 10:00"
                time_str = schedule_time.split("daily at ")[1].strip()
                # Ensure time format is valid (HH:MM)
                if re.match(r"^\d{1,2}:\d{2}$", time_str):
                    job = schedule.every().day.at(time_str)
                else:
                    logger.error(
                        f"Invalid time format '{time_str}' for event. Must be in format HH:MM"
                    )

            # Set the job to execute this event and tag it with the event_id
            if job:
                job.do(self._execute_event, event_id, event_data).tag(event_id)
                logger.info(f"Scheduled event {event_id} with rule: {schedule_time}")
            else:
                logger.error(
                    f"Could not parse schedule time for event {event_id}: {schedule_time}"
                )

        except Exception as e:
            logger.error(f"Error scheduling event {event_id}: {e}", exc_info=True)

    def scan_task_directory(self, tasks_dir: str = None) -> None:
        """
        Scan the tasks directory for recurring task files.

        Args:
            tasks_dir: The directory to scan, defaults to OBSIDIAN_VAULT_PATH/03 - Tasks
        """
        if not tasks_dir:
            if not OBSIDIAN_VAULT_PATH:
                logger.error("OBSIDIAN_VAULT_PATH is not set, cannot scan tasks")
                return
            tasks_dir = os.path.join(OBSIDIAN_VAULT_PATH, "03 - Tasks")

        if not os.path.isdir(tasks_dir):
            logger.error(f"Tasks directory not found: {tasks_dir}")
            return

        logger.info(f"Scanning for recurring tasks in: {tasks_dir}")

        # Clear existing task-based schedules (but keep global ones)
        task_event_ids = [
            event_id for event_id, event in self.events.items() if "task_file" in event
        ]
        for event_id in task_event_ids:
            schedule.clear(event_id)
            del self.events[event_id]

        # Walk through the directory and process each MD file
        count = 0
        for root, _, files in os.walk(tasks_dir):
            for filename in files:
                if filename.endswith(".md"):
                    file_path = os.path.join(root, filename)
                    self.schedule_from_file(file_path)
                    count += 1

        logger.info(f"Completed task scan, processed {count} files")

    def start(self) -> None:
        """Start the recurring events engine."""
        if self.running:
            logger.warning("Recurring events engine is already running")
            return

        # Scan for task files first
        self.scan_task_directory()

        # Schedule all events
        for event_id, event_data in self.events.items():
            self._schedule_event(event_id, event_data)

        # Start watching for file changes in the tasks directory
        if OBSIDIAN_VAULT_PATH:
            tasks_dir = os.path.join(OBSIDIAN_VAULT_PATH, "03 - Tasks")
            if os.path.isdir(tasks_dir):
                event_handler = TaskFileHandler(self)
                self.file_observer = Observer()
                self.file_observer.schedule(event_handler, tasks_dir, recursive=True)
                self.file_observer.start()
                logger.info(f"Started file observer for: {tasks_dir}")

        # Start the scheduler in a separate thread
        def run_scheduler():
            logger.info("Starting recurring events scheduler thread")
            self.running = True
            while self.running:
                schedule.run_pending()
                time.sleep(1)
            logger.info("Recurring events scheduler thread stopped")

        self.thread = threading.Thread(target=run_scheduler, daemon=True)
        self.thread.start()
        logger.info(f"Recurring events engine started with {len(self.events)} events")

    def stop(self) -> None:
        """Stop the recurring events engine."""
        if not self.running:
            logger.warning("Recurring events engine is not running")
            return

        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

        # Stop file observer
        if self.file_observer and self.file_observer.is_alive():
            self.file_observer.stop()
            self.file_observer.join()

        # Clear all schedules
        schedule.clear()
        logger.info("Recurring events engine stopped")


# Create a singleton instance
_engine_instance = None


def get_engine() -> RecurringEventsEngine:
    """
    Get the singleton instance of the RecurringEventsEngine.

    Returns:
        RecurringEventsEngine: The recurring events engine instance
    """
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = RecurringEventsEngine()
    return _engine_instance
