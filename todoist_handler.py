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


# --- MODIFIED: Remove date range filtering to get all active tasks ---
def get_tasks() -> list[Task]:
    """Gets list of all active (non-completed) tasks."""
    client = _init_api()
    if not client:
        return []
    try:
        logger.debug("Requesting all active tasks from Todoist API...")
        all_active_tasks = client.get_tasks()
        logger.info(f"Retrieved {len(all_active_tasks)} active tasks from Todoist.")
        # No date filtering needed here, get_tasks() returns active ones
        return all_active_tasks
    except Exception as e:
        logger.error(f"Error getting tasks from Todoist: {e}", exc_info=True)
        return []


def create_task(
    content: str,
    due_string: Optional[str] = None,
    priority: Optional[int] = None,
    project_id: Optional[str] = None,
    description: Optional[str] = None,
    duration_minutes: Optional[int] = None,
) -> Optional[Task]:
    """Creates a new task in Todoist."""
    client = _init_api()
    if not client:
        return None
    try:
        # Prepare task parameters
        task_params = {
            "content": content,
            "due_string": due_string,
            "priority": priority,
            "description": description,
        }

        # Add project_id if it's not 'inbox'
        if project_id and project_id != "inbox":
            task_params["project_id"] = project_id

        # Add duration if specified
        if duration_minutes is not None:
            task_params["duration"] = duration_minutes
            task_params["duration_unit"] = "minute"

        logger.info(
            f"Creating task in Todoist: '{content[:50]}...' "
            f"Project: {project_id}, Due: {due_string}, Priority: {priority}, "
            f"Duration: {duration_minutes} minutes"
        )

        task = client.add_task(**task_params)
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


def update_task(task_id: str, **kwargs) -> bool:
    """
    Updates a task in Todoist.

    Args:
        task_id: The ID of the task to update.
        **kwargs: Keyword arguments corresponding to Task attributes
                  (e.g., content, due_string, duration_minutes, priority,
                   description, project_id). Use None or "" to remove optional fields.

    Returns:
        True if update was successful, False otherwise.
    """
    # --- FIX: Call the correct init function ---
    api = _init_api()  # Use _init_api() instead of setup_todoist_api()
    if not api:
        return False

    logger.info(f"Attempting to update task {task_id} with args: {kwargs}")
    try:
        # Prepare data, handle removal logic carefully based on API spec
        update_data = {}
        for k, v in kwargs.items():
            if k == "due_string":
                # API might expect due={'string': '...'} or due_string='...'
                # To remove: due={'string': None} or due_string="" ? Check API docs.
                # Assuming direct due_string works for now, pass "" for removal.
                update_data["due_string"] = (
                    v if v is not None else ""
                )  # Pass "" to try removing
            elif k == "duration_minutes":
                if v is None or v == 0:
                    update_data["duration"] = None
                    update_data["duration_unit"] = None
                else:
                    update_data["duration"] = v
                    update_data["duration_unit"] = "minute"
            elif v is not None:  # Copy other non-None arguments
                update_data[k] = v

        if not update_data:
            logger.warning(f"No valid update arguments provided for task {task_id}")
            return False

        # Make the API call
        is_success = api.update_task(task_id=task_id, **update_data)

        if (
            is_success
        ):  # update_task returns True on success, raises exception on failure
            logger.info(f"Successfully updated task {task_id}")
            return True
        else:
            # This path might not be reachable if exceptions are raised on failure
            logger.warning(
                f"Todoist API reported failure updating task {task_id} (returned False)"
            )
            return False

    except Exception as e:
        logger.error(f"Error updating task {task_id}: {e}", exc_info=True)
        return False
