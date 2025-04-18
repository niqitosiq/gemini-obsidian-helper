import logging
from typing import Union, Optional, List
from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Task, Project
from datetime import datetime, timedelta

# --- NEW: Import requests exception ---
from requests.exceptions import HTTPError
import config
import knowledge_base

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
    """Gets list of projects from Todoist."""
    client = _init_api()
    if not client:
        return []
    try:
        logger.debug("Requesting projects from Todoist API...")
        projects_paginator = client.get_projects()
        projects_list_raw = list(projects_paginator)  # Convert paginator

        # --- FIX: Apply nested list detection logic ---
        if projects_list_raw and isinstance(projects_list_raw[0], list):
            logger.warning(
                "Detected nested list structure in projects response. Extracting inner list."
            )
            projects_list = projects_list_raw[0]
            # Further check if the inner elements are Projects
            if projects_list and not isinstance(projects_list[0], Project):
                logger.error(
                    f"Inner list elements are not Project objects, type: {type(projects_list[0])}. Returning empty list."
                )
                return []
        elif projects_list_raw and not isinstance(projects_list_raw[0], Project):
            # Check if the first element of the supposedly flat list is actually a Project
            logger.error(
                f"Expected list of Project objects, but first element is type: {type(projects_list_raw[0])}. Returning empty list."
            )
            return []
        else:
            # Assume it's already a flat list or empty
            projects_list = projects_list_raw
        # --- END FIX ---

        logger.info(f"Retrieved {len(projects_list)} projects from Todoist.")
        result_list = []
        for p in projects_list:
            # This check should now work correctly
            if isinstance(p, Project):
                result_list.append({"id": p.id, "name": p.name})
            else:
                # This warning should ideally not appear anymore
                logger.warning(
                    f"Skipping non-Project item during final processing: {p}"
                )
        return result_list
    except Exception as e:
        logger.error(f"Error getting projects from Todoist: {e}", exc_info=True)
        return []


def get_tasks() -> list[Task]:
    """Gets list of ALL active tasks."""
    client = _init_api()
    if not client:
        return []
    try:
        logger.debug(f"Requesting ALL active tasks from Todoist API...")
        tasks_paginator = client.get_tasks()
        tasks_list_raw = list(tasks_paginator)  # Convert paginator here

        # --- FIX: Check for nested list structure ---
        if tasks_list_raw and isinstance(tasks_list_raw[0], list):
            logger.warning(
                "Detected nested list structure in tasks response. Extracting inner list."
            )
            tasks_list = tasks_list_raw[0]
            # Further check if the inner elements are Tasks
            if tasks_list and not isinstance(tasks_list[0], Task):
                logger.error(
                    f"Inner list elements are not Task objects, type: {type(tasks_list[0])}. Returning empty list."
                )
                return []
        elif tasks_list_raw and not isinstance(tasks_list_raw[0], Task):
            logger.error(
                f"Expected list of Task objects, but first element is type: {type(tasks_list_raw[0])}. Returning empty list."
            )
            return []
        else:
            # Assume it's already a flat list or empty
            tasks_list = tasks_list_raw
        # --- END FIX ---

        logger.info(f"Retrieved {len(tasks_list)} total active tasks from Todoist.")
        # Final type check before returning
        if tasks_list and not isinstance(tasks_list[0], Task):
            logger.error(
                f"Final check failed: List elements are not Task objects. Type: {type(tasks_list[0])}"
            )
            return []

        return tasks_list
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

    task_params = {"content": content}  # Define task_params early for logging
    try:
        # Prepare parameters carefully, excluding None values
        if due_string:
            task_params["due_string"] = due_string
        if priority is not None:
            try:
                priority_int = int(priority)
                if 1 <= priority_int <= 4:
                    task_params["priority"] = priority_int
                else:
                    logger.warning(
                        f"Invalid priority {priority} provided, using default."
                    )
            except (ValueError, TypeError):
                logger.warning(f"Invalid priority type {priority}, using default.")
        if description:
            task_params["description"] = description
        if project_id and project_id != "inbox":
            task_params["project_id"] = project_id
        if duration_minutes is not None and duration_minutes > 0:
            task_params["duration"] = duration_minutes
            task_params["duration_unit"] = "minute"

        logger.info(f"Creating task in Todoist with processed params: {task_params}")

        task = client.add_task(**task_params)
        logger.info(f"Task successfully created in Todoist, ID: {task.id}")
        # Log to knowledge base
        knowledge_base.log_entry(
            "task_created",
            {
                "id": task.id,
                "content": content,
                "project_id": project_id,
                "due": due_string,
                "priority": priority,
                "duration": duration_minutes,
            },
        )
        return task
    # --- MODIFIED: Catch HTTPError specifically to log response ---
    except HTTPError as http_err:
        error_response_text = "No response body available."
        if http_err.response is not None:
            try:
                error_response_text = http_err.response.text
            except Exception as resp_err:
                error_response_text = f"Could not read response body: {resp_err}"
        logger.error(
            f"HTTPError creating task in Todoist with params {task_params}: {http_err}. Response: {error_response_text}",
            exc_info=True,
        )
        return None
    # --- END MODIFIED ---
    except Exception as e:
        # Generic error logging
        logger.error(
            f"Error creating task in Todoist with params {task_params}: {e}",
            exc_info=True,
        )
        return None


def update_task(task_id: str, **kwargs) -> bool:
    """
    Updates a task in Todoist. NOTE: Changing project_id is NOT supported by the API via this method.

    Args:
        task_id: The ID of the task to update.
        **kwargs: Keyword arguments corresponding to Task attributes
                  (e.g., content, due_string, duration_minutes, priority,
                   description). Use None or "" to remove optional fields.
                   `project_id` will be ignored.

    Returns:
        True if update was successful, False otherwise.
    """
    api = _init_api()
    if not api:
        return False

    logger.info(f"Attempting to update task {task_id} with raw args: {kwargs}")

    # --- FIX: Remove project_id handling, log warning if present ---
    update_data = {}
    update_success = True

    try:
        # Prepare data for standard update
        for k, v in kwargs.items():
            if k == "project_id":
                # Log a warning that changing project is not supported here
                logger.warning(
                    f"Ignoring attempt to change project_id for task {task_id} via update_task (not supported)."
                )
                continue  # Skip adding project_id to update_data
            elif k == "due_string":
                update_data["due_string"] = v if v is not None else ""
            elif k == "duration_minutes":
                if v is None or v == 0:
                    update_data["duration"] = None
                    update_data["duration_unit"] = None
                else:
                    update_data["duration"] = v
                    update_data["duration_unit"] = "minute"
            elif k == "priority":
                if v is not None:
                    try:
                        priority_int = int(v)
                        if 1 <= priority_int <= 4:
                            update_data[k] = priority_int
                        else:
                            logger.warning(
                                f"Invalid priority value '{v}' for task {task_id}. Ignoring."
                            )
                    except (ValueError, TypeError):
                        logger.warning(
                            f"Could not convert priority '{v}' to int for task {task_id}. Ignoring."
                        )
            elif v is not None:  # Copy other non-None arguments
                update_data[k] = v

        # --- Perform standard update if there are fields to update ---
        if update_data:
            logger.debug(f"Updating task {task_id} with processed data: {update_data}")
            update_success = api.update_task(task_id=task_id, **update_data)
            if update_success:
                logger.info(f"Successfully updated fields for task {task_id}")
            else:
                # The API method returns bool, not raising exception on logical failure sometimes
                logger.warning(
                    f"Todoist API reported failure updating fields for task {task_id} (returned False)"
                )
                # Attempt to get more info if possible (though update_task doesn't return detailed errors easily)

        else:
            logger.info(f"No valid fields to update for task {task_id}.")
            update_success = True  # No update needed is considered success

        # Return the success status of the update operation
        return update_success

    except HTTPError as http_err:
        # Log HTTPError details
        error_response_text = "No response body available."
        if http_err.response is not None:
            try:
                error_response_text = http_err.response.text
            except Exception as resp_err:
                error_response_text = f"Could not read response body: {resp_err}"
        logger.error(
            f"HTTPError updating task {task_id} with data {update_data}: {http_err}. Response: {error_response_text}",
            exc_info=True,
        )
        return False
    except Exception as e:
        logger.error(f"Generic error updating task {task_id}: {e}", exc_info=True)
        return False
