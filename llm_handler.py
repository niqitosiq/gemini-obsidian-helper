import logging
import google.generativeai as genai
import google.api_core.exceptions
import json
import os
from typing import Optional, Union, List, Dict
from datetime import datetime
import config
import knowledge_base
import todoist_handler

logger = logging.getLogger(__name__)

# Gemini client setup
_model = None
try:
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set.")
    genai.configure(api_key=config.GEMINI_API_KEY)
    _model = genai.GenerativeModel("gemini-1.5-flash-latest")
    logger.info("Gemini API client configured with model 'gemini-1.5-flash-latest'.")
except Exception as e:
    logger.critical(f"Critical error configuring Gemini API: {e}", exc_info=True)


def assemble_context(
    source: str, conversation_history: Optional[List[str]] = None
) -> str:
    """Assembles context for Gemini prompt based on settings."""
    if not _model:
        return "[Context cannot be assembled: Gemini API Error]"

    logger.debug(f"Assembling context with level: {config.GEMINI_CONTEXT_LEVEL}")
    current_time = datetime.now()
    context_parts = ["[CONTEXT]"]
    context_parts.append(f"- Source: {source}")
    context_parts.append(
        f"- Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    )
    context_parts.append(f"- Current date: {current_time.strftime('%Y-%m-%d')}")

    kb_content = knowledge_base.read_knowledge_base()
    if kb_content:
        if config.GEMINI_CONTEXT_LEVEL != "none":
            context_parts.append("- Knowledge Base (Findings, Preferences, Feedback):")
            context_parts.append(kb_content)
    else:
        context_parts.append("- Knowledge Base: Empty.")

    if (
        config.GEMINI_CONTEXT_LEVEL in ["maximal", "with_conversation"]
        and conversation_history
    ):
        context_parts.append("- Current conversation history:")
        context_parts.extend([f"  - {msg}" for msg in conversation_history])

    projects = todoist_handler.get_projects()
    if projects:
        context_parts.append("- Existing Todoist projects:")
        project_list_str = ", ".join(
            [f"'{p['name']}' (ID: {p['id']})" for p in projects]
        )
        context_parts.append(f"  - [{project_list_str}]")
        context_parts.append("  - 'inbox' (ID: inbox) - use if no project fits.")
    else:
        context_parts.append("- Existing Todoist projects: Failed to retrieve.")

    context_parts.append("[END CONTEXT]\n")
    return "\n".join(context_parts)


def analyze_text(
    text: str, source: str, conversation_history: Optional[List[str]] = None
) -> Optional[Dict]:
    """Analyzes text using Gemini with assembled context."""
    if not _model:
        logger.error("Analysis impossible: Gemini model not initialized.")
        return None

    full_context = assemble_context(source, conversation_history)
    logger.debug(f"Assembled context for Gemini:\n{full_context}")

    system_instruction = """You are an AI assistant helping users manage tasks in Todoist.
Your task is to analyze the USER REQUEST considering the provided CONTEXT (especially Knowledge Base and existing projects).

IMPORTANT: Always respond in the same language as the user's request. If the user writes in Russian, respond in Russian.
If the user writes in English, respond in English.

Extract from the request:
1.  `action`: Main action/task essence (brief, infinitive or noun).
2.  `details`: Additional details, description.
3.  `deadline`: The date/time when the task should be COMPLETED. Use 'YYYY-MM-DD HH:MM' for time, 'YYYY-MM-DD' for date only. For relative times like "tomorrow", convert to actual date. Set null if unclear. IMPORTANT: do not interpret time durations (like "2 hours") as deadlines.
4.  `priority`: Task priority (integer 1-4, where 1 is highest). Determine from keywords (urgent, important), context and Knowledge Base. Default to 4 if unclear.
5.  `estimated_duration_minutes`: How long the task will take to complete (integer minutes). IMPORTANT: When user says something like "2 hours" or "час", this is usually a duration, not a deadline. Convert hours to minutes (e.g., "2 hours" = 120 minutes). If user gives duration in response to a clarification question, this is almost always the task duration.
6.  `project_id`: ID of most suitable existing Todoist project from CONTEXT list. Compare task essence with project names carefully. Use 'inbox' if none fits.
7.  `status`: 'complete' if all info (action, deadline, priority, estimated_duration_minutes, project_id) is extracted and sufficient for task creation, else 'incomplete'.
8.  `missing_info`: Array of strings describing missing information (only if status='incomplete'). Example: ["No deadline specified", "Task duration unclear", "Need to clarify project"].
9.  `clarification_question`: One short, polite question to user to clarify the FIRST item in `missing_info` (only if status='incomplete'). Must be in the same language as the user's request.

Return response STRICTLY in JSON format.
"""
    user_prompt = f"USER REQUEST: {text}"

    full_prompt = (
        f"{system_instruction}\n\n{full_context}\n{user_prompt}\n\nJSON RESPONSE:"
    )
    logger.debug(f"Final Gemini prompt (start): {full_prompt[:500]}...")

    try:
        response = _model.generate_content(full_prompt)
        logger.debug(f"Received Gemini response: {response.text}")

        json_response_str = response.text.strip()
        if json_response_str.startswith("```json"):
            json_response_str = json_response_str[7:]
        if json_response_str.endswith("```"):
            json_response_str = json_response_str[:-3]
        json_response_str = json_response_str.strip()

        result = json.loads(json_response_str)

        required_keys = ["action", "status"]
        if not all(key in result for key in required_keys):
            logger.error(f"Gemini response missing required keys: {result}")
            return None
        if result["status"] == "incomplete" and not result.get("missing_info"):
            logger.error(
                f"Status 'incomplete' but 'missing_info' missing in Gemini response: {result}"
            )
            result["missing_info"] = ["Need to clarify details"]
            result["clarification_question"] = (
                "Could you please provide more details about the task?"
            )

        knowledge_base.log_entry(
            "llm_analysis",
            {
                "input_text": text,
                "source": source,
                "llm_output_status": result.get("status"),
                "extracted_action": result.get("action"),
                "extracted_project": result.get("project_id"),
                "missing_info": result.get("missing_info"),
            },
        )

        return result

    except json.JSONDecodeError as e:
        logger.error(
            f"Error decoding JSON from Gemini response: {e}\nResponse: {response.text}",
            exc_info=True,
        )
        return None
    except google.api_core.exceptions.GoogleAPIError as e:
        logger.error(f"Gemini API error: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during Gemini call: {e}", exc_info=True)
        return None


def transcribe_audio(audio_file_path: str) -> Optional[str]:
    """Transcribes audio file using Gemini."""
    if not _model:
        logger.error("Transcription impossible: Gemini model not initialized.")
        return None
    if not os.path.exists(audio_file_path):
        logger.error(f"Audio file for transcription not found: {audio_file_path}")
        return None

    logger.info(f"Loading and transcribing audio file: {audio_file_path}...")
    try:
        audio_file = genai.upload_file(path=audio_file_path)
        logger.debug(f"Audio file uploaded: {audio_file.name}, URI: {audio_file.uri}")

        prompt = "Transcribe this audio file verbatim."
        response = _model.generate_content([prompt, audio_file])

        try:
            genai.delete_file(audio_file.name)
            logger.debug(f"File {audio_file.name} deleted from Google server.")
        except Exception as delete_e:
            logger.warning(
                f"Failed to delete file {audio_file.name} from Google server: {delete_e}"
            )

        transcribed_text = response.text.strip()
        logger.info(
            f"Audio successfully transcribed (length: {len(transcribed_text)}): {transcribed_text[:100]}..."
        )

        knowledge_base.log_entry(
            "audio_transcribed",
            {
                "file_path": audio_file_path,
                "transcription_length": len(transcribed_text),
            },
        )

        return transcribed_text

    except google.api_core.exceptions.GoogleAPIError as e:
        logger.error(f"Gemini API error during audio transcription: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error during audio transcription {audio_file_path}: {e}",
            exc_info=True,
        )
        return None


def analyze_text_batch(
    text: str, source: str, conversation_history: Optional[List[str]] = None
) -> List[Dict]:
    """Analyzes text and extracts multiple tasks if present."""
    if not _model:
        logger.error("Analysis impossible: Gemini model not initialized.")
        return []

    full_context = assemble_context(source, conversation_history)

    system_instruction = """You are an AI assistant helping users manage tasks in Todoist.
Your task is to analyze the USER REQUEST and split it into separate tasks if multiple tasks are mentioned.
Each task should have its own analysis in the response array.

IMPORTANT: Always respond in the same language as the user's request. If the user writes in Russian, respond in Russian.
If the user writes in English, respond in English.

For EACH TASK in the request, extract:
1.  `action`: Main action/task essence (brief, infinitive or noun).
2.  `details`: Additional details, description.
3.  `deadline`: Desired completion time. Use 'YYYY-MM-DD HH:MM' for time, 'YYYY-MM-DD' for date only. Convert relative ("tomorrow", "in 2 days") to specific date/time. Set null if unclear.
4.  `priority`: Task priority (integer 1-4, where 1 is highest). Determine from keywords (urgent, important), context and Knowledge Base. Default to 4 if unclear.
5.  `estimated_duration_minutes`: Task duration estimate in minutes (integer). Use context, Knowledge Base and common sense. Set null if impossible to estimate.
6.  `project_id`: ID of most suitable existing Todoist project from CONTEXT list. Compare task essence with project names carefully. Use 'inbox' if none fits.
7.  `source_text`: The exact text fragment from the original request that led to identifying this task.
8.  `status`: 'complete' if all info is sufficient for task creation, else 'incomplete'.
9.  `missing_info`: Array of strings describing missing information (only if status='incomplete').
10. `clarification_question`: One short, polite question to clarify the FIRST item in `missing_info` (only if status='incomplete'). Must be in the same language as the user's request.

Return response as an ARRAY of task objects in JSON format, even if there's only one task."""

    user_prompt = f"USER REQUEST: {text}"
    full_prompt = (
        f"{system_instruction}\n\n{full_context}\n{user_prompt}\n\nJSON RESPONSE:"
    )
    logger.debug(
        f"Final Gemini prompt for batch analysis (start): {full_prompt[:500]}..."
    )

    try:
        response = _model.generate_content(full_prompt)
        logger.debug(f"Received Gemini response: {response.text}")

        json_response_str = response.text.strip()
        if json_response_str.startswith("```json"):
            json_response_str = json_response_str[7:]
        if json_response_str.endswith("```"):
            json_response_str = json_response_str[:-3]
        json_response_str = json_response_str.strip()

        tasks = json.loads(json_response_str)
        if not isinstance(tasks, list):
            tasks = [tasks]

        # Validate each task
        valid_tasks = []
        for task in tasks:
            if "action" not in task or "status" not in task:
                logger.warning(f"Invalid task in Gemini response: {task}")
                continue

            if task["status"] == "incomplete" and not task.get("missing_info"):
                task["missing_info"] = ["Need to clarify details"]
                task["clarification_question"] = (
                    "Не могли бы вы уточнить детали задачи?"
                    if any(char in text for char in "абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
                    else "Could you please provide more details about the task?"
                )

            knowledge_base.log_entry(
                "llm_analysis",
                {
                    "input_text": task.get("source_text", text),
                    "source": source,
                    "llm_output_status": task.get("status"),
                    "extracted_action": task.get("action"),
                    "extracted_project": task.get("project_id"),
                    "missing_info": task.get("missing_info"),
                },
            )
            valid_tasks.append(task)

        return valid_tasks

    except json.JSONDecodeError as e:
        logger.error(
            f"Error decoding JSON from Gemini response: {e}\nResponse: {response.text}"
        )
        return []
    except google.api_core.exceptions.GoogleAPIError as e:
        logger.error(f"Gemini API error: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error during Gemini call: {e}")
        return []
