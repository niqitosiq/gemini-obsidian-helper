import logging
from typing import Union, Optional, List
from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Task, Project
from datetime import datetime, timedelta
import config

logger = logging.getLogger(__name__)
api: Optional[TodoistAPI] = None
_projects_cache: Optional[List[Project]] = None
_projects_cache_time: Optional[datetime] = None
_cache_ttl = timedelta(minutes=15)


def _init_api() -> Optional[TodoistAPI]:
    """Initializes Todoist API client."""
    global api
    if api is None:
        if not config.TODOIST_API_TOKEN:
            logger.error("Todoist API Token not found in configuration.")
            return None
        try:
            api = TodoistAPI(config.TODOIST_API_TOKEN)
            logger.info("Todoist API client initialized.")
        except Exception as e:
            logger.error(f"Error initializing Todoist API: {e}", exc_info=True)
            api = None
    return api


def get_projects() -> list[dict[str, str]]:
    """Returns list of Todoist projects (uses cache)."""
    global _projects_cache, _projects_cache_time
    now = datetime.now()

    if (
        _projects_cache
        and _projects_cache_time
        and (now - _projects_cache_time < _cache_ttl)
    ):
        logger.debug("Returning cached Todoist projects list.")
        return [{"id": p.id, "name": p.name} for p in _projects_cache]

    client = _init_api()
    if not client:
        return []
    try:
        logger.debug("Requesting projects list from Todoist API...")
        projects = client.get_projects()
        _projects_cache = projects
        _projects_cache_time = now
        logger.info(f"Retrieved {len(projects)} projects from Todoist.")
        return [{"id": p.id, "name": p.name} for p in projects]
    except Exception as e:
        logger.error(f"Error getting projects from Todoist: {e}", exc_info=True)
        _projects_cache = None
        _projects_cache_time = None
        return []


def get_tasks(start_date: datetime, end_date: datetime) -> list[Task]:
    """Gets list of active tasks in given date range."""
    client = _init_api()
    if not client:
        return []
    try:
        logger.debug("Requesting active tasks from Todoist API...")
        all_active_tasks = client.get_tasks()
        logger.info(f"Retrieved {len(all_active_tasks)} active tasks from Todoist.")

        tasks_in_range = []
        for task in all_active_tasks:
            if task.due and task.due.datetime:
                try:
                    task_due_dt = datetime.fromisoformat(
                        task.due.datetime.replace("Z", "+00:00")
                    )
                    task_due_dt_naive = task_due_dt.replace(tzinfo=None)
                    if start_date <= task_due_dt_naive < end_date:
                        tasks_in_range.append(task)
                except ValueError:
                    logger.warning(
                        f"Could not parse date for task '{task.content}': {task.due.datetime}"
                    )
            elif task.due and task.due.date:
                try:
                    task_due_d = datetime.fromisoformat(task.due.date).date()
                    if start_date.date() <= task_due_d < end_date.date():
                        pass  # Skip tasks without specific time for now
                except ValueError:
                    logger.warning(
                        f"Could not parse date for task '{task.content}': {task.due.date}"
                    )

        logger.debug(
            f"Found {len(tasks_in_range)} tasks with deadline in range {start_date} - {end_date}."
        )
        return tasks_in_range
    except Exception as e:
        logger.error(f"Error getting tasks from Todoist: {e}", exc_info=True)
        return []


def create_task(
    content: str,
    due_string: Optional[str] = None,
    priority: Optional[int] = None,
    project_id: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[Task]:
    """Creates a new task in Todoist."""
    client = _init_api()
    if not client:
        return None
    try:
        logger.info(
            f"Creating task in Todoist: '{content[:50]}...' "
            f"Project: {project_id}, Due: {due_string}, Priority: {priority}"
        )
        task = client.add_task(
            content=content,
            due_string=due_string,
            priority=priority,
            project_id=project_id if project_id and project_id != "inbox" else None,
            description=description,
        )
        logger.info(f"Task successfully created in Todoist, ID: {task.id}")
        from knowledge_base import log_entry

        log_entry(
            "task_created",
            {
                "id": task.id,
                "content": content,
                "project_id": project_id,
                "due": due_string,
                "priority": priority,
            },
        )
        return task
    except Exception as e:
        logger.error(f"Error creating task in Todoist: {e}", exc_info=True)
        return None
