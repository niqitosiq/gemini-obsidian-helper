import logging
import google.generativeai as genai
import google.api_core.exceptions
import json
import os
from typing import Optional, Union, List, Dict, Any  # Add Any
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
    _model = genai.GenerativeModel("gemini-2.0-flash")
    logger.info("Gemini API client configured with model 'gemini-2.0-flash'. ")
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
3.  `start_time`: The date/time when the task should START. Use 'YYYY-MM-DD HH:MM' for time, 'YYYY-MM-DD' for date only. For relative times like "tomorrow", convert to actual date. Set null if unclear. 
    IMPORTANT START TIME INTERPRETATION RULES:
    - The time the user specifies is usually when they want to START the task, not when it should be completed.
    - When user says "в 6 вечера" or "at 6 PM", this is the starting time for the task.
    - When user says "до 6 вечера" or "by 6 PM", calculate an appropriate start time by subtracting the task duration from this deadline.
    - Don't interpret time durations (like "2 hours" or "час") as start times; these indicate how long the task takes.
4.  `priority`: Task priority (integer 1-4, where 1 is highest). Determine from keywords (urgent, important), context and Knowledge Base. Default to 4 if unclear.
5.  `estimated_duration_minutes`: How long the task will take to complete (integer minutes). IMPORTANT: When user says something like "2 hours" or "час", this is usually a duration, not a deadline. Convert hours to minutes (e.g., "2 hours" = 120 minutes). If user gives duration in response to a clarification question, this is almost always the task duration.
6.  `project_id`: ID of most suitable existing Todoist project from CONTEXT list. Compare task essence with project names carefully. Use 'inbox' if none fits.
7.  `status`: 'complete' if all info (action, start_time, priority, estimated_duration_minutes, project_id) is extracted and sufficient for task creation, else 'incomplete'.
8.  `missing_info`: Array of strings describing missing information (only if status='incomplete'). Example: ["No start time specified", "Task duration unclear", "Need to clarify project"].
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

**DO NOT create tasks for commands like "plan my day", "schedule my day", "распланируй день", "запланируй день", "создай расписание". These are commands, not tasks to be created. If the user request is only such a command, return an empty array `[]`.**

For EACH TASK in the request, extract:
1.  `action`: Main action/task essence (brief, infinitive or noun).
2.  `details`: Additional details, description.
3.  `start_time`: When the task should START. Use 'YYYY-MM-DD HH:MM' for time, 'YYYY-MM-DD' for date only. Convert relative ("tomorrow", "in 2 days") to specific date/time. Set null if unclear.
    IMPORTANT START TIME INTERPRETATION RULES:
    - The time the user specifies is usually when they want to START the task, not when it should be completed.
    - When user says "в 6 вечера" or "at 6 PM", this is the starting time for the task.
    - When user says "до 6 вечера" or "by 6 PM", calculate an appropriate start time by subtracting the task duration from this deadline.
4.  `priority`: Task priority (integer 1-4, where 4 is highest). Determine from keywords (urgent, important), context and Knowledge Base. Default to 4 if unclear.
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


# --- NEW Function to Parse Duration ---
async def parse_duration_response(text: str) -> Optional[int]:
    """Uses LLM to parse duration in minutes from user's text response."""
    if not _model:
        logger.error("Duration parsing impossible: Gemini model not initialized.")
        return None

    # No complex context needed, just the text
    system_instruction = """Your task is to analyze the user's text response, which answers a question about task duration. Extract the duration strictly in TOTAL MINUTES.
- Handle phrases like "полтора часа" (90 minutes), "час" (60 minutes), "2 часа" (120 minutes), "45 минут" (45 minutes).
- If the user provides a range (e.g., "1-2 часа"), try to provide a reasonable average or midpoint in minutes (e.g., 90 minutes).
- If the duration is unclear or cannot be determined, return null.
- Respond ONLY with the integer number of minutes or the word null. Do not add any other text.

Examples:
User text: "где-то полтора часа" -> Response: 90
User text: "минут 20-30" -> Response: 25
User text: "1 час" -> Response: 60
User text: "I don't know" -> Response: null
User text: "maybe 2h" -> Response: 120
User text: "завтра" -> Response: null
"""
    user_prompt = f'User text: "{text}"'
    full_prompt = f"{system_instruction}\n\n{user_prompt}\n\nResponse:"

    logger.debug(f"Sending prompt to LLM for duration parsing: {full_prompt}")

    try:
        response = _model.generate_content(full_prompt)
        result_text = response.text.strip().lower()
        logger.debug(f"Received LLM response for duration parsing: '{result_text}'")

        if result_text == "null":
            return None
        elif result_text.isdigit():
            return int(result_text)
        else:
            logger.warning(
                f"LLM returned non-integer/non-null for duration: '{result_text}'"
            )
            return None  # Treat unexpected responses as failure

    except google.api_core.exceptions.GoogleAPIError as e:
        logger.error(f"Gemini API error during duration parsing: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during duration parsing: {e}", exc_info=True)
        return None


# --- Function for Generic Responses ---
async def generate_response(prompt_type: str, data: Dict[str, Any]) -> Optional[str]:
    """Generates various text responses using LLM based on prompt type."""
    if not _model:
        logger.error("Response generation impossible: Gemini model not initialized.")
        return None

    # Assemble context (might need adjustment based on prompt type)
    # For now, use standard context assembly
    full_context = assemble_context("llm_response_generation")
    logger.debug(f"Assembled context for LLM response generation:\n{full_context}")

    system_instruction = "You are an AI assistant helping a user manage their tasks and schedule. Generate a helpful and concise response based on the request type and provided data. Respond in Russian unless the user context indicates otherwise. Be friendly and encouraging."

    user_prompt = f"Request Type: {prompt_type}\nData:\n"
    # Format data nicely for the prompt
    for key, value in data.items():
        user_prompt += f"- {key}: {json.dumps(value, ensure_ascii=False, indent=2)}\n"  # Use json.dumps for complex data

    # Add specific instructions based on prompt_type
    if prompt_type == "schedule_intro":
        user_prompt += "\nGenerate a short, friendly introductory message for the user's daily schedule, mentioning the day type (workday/weekend) and date."
        user_prompt += f"\nExample for workday: '🗓 Доброе утро! Вот ваше расписание на сегодня (пятница, 18.04.2025):'"
        user_prompt += f"\nExample for weekend: '🏖 Доброе утро! Сегодня пятница, 18.04.2025 - выходной день! Вот несколько идей:'"
    elif prompt_type == "schedule_body":
        user_prompt += "\nGenerate the main body of the schedule message."
        user_prompt += (
            "\n- If there are scheduled_tasks, list them clearly with times (HH:MM)."
        )
        user_prompt += "\n- If there are no scheduled_tasks but needs_clarification is true, state that some tasks need duration clarification for planning."
        user_prompt += "\n- If there are no scheduled_tasks and no clarification needed, state that there are no tasks planned for today (mention if it's a weekend)."
        user_prompt += "\n- Keep the format clean and easy to read."
        user_prompt += "\nExample with tasks: '📋 09:00 - Task 1\\n⏰ 11:30 - Task 2 (срок сегодня)'"
        user_prompt += "\nExample clarification needed: 'Есть задачи на сегодня, но для планирования нужно уточнить их длительность.'"
        user_prompt += (
            "\nExample empty workday: 'Не нашел задач для планирования на сегодня.'"
        )
        user_prompt += (
            "\nExample empty weekend: 'Сегодня выходной! Задач нет, можно отдохнуть.'"
        )
    elif prompt_type == "clarify_duration":
        user_prompt += "\nGenerate a short, polite question asking the user for the estimated duration (in minutes or hours) for the given task_content."
        user_prompt += f"\nExample: '📝 Про задачу \"{data.get('task_content', '...')}\": Сколько примерно времени потребуется на ее выполнение?'"
    # --- NEW Prompt Type ---
    elif prompt_type == "suggest_schedule_slot":
        user_prompt += "\nGenerate a message suggesting a specific time slot for a task. Ask the user to confirm via buttons."
        user_prompt += f"\nExample: '🗓️ Предлагаю запланировать задачу \"{data.get('task_content', '...')}\" на {data.get('proposed_time', 'HH:MM')} сегодня ({data.get('date', 'YYYY-MM-DD')}). Назначить?'"
    # --- NEW Prompt Type ---
    elif prompt_type == "schedule_confirm":
        user_prompt += "\nGenerate a short confirmation message that the user accepted the schedule suggestion and the task is now scheduled."
        user_prompt += f"\nExample: '✅ Отлично! Задача \"{data.get('task_content', '...')}\" запланирована на {data.get('scheduled_time', 'HH:MM')}.'"
    # --- NEW Prompt Type ---
    elif prompt_type == "schedule_skip":
        user_prompt += "\nGenerate a short message acknowledging the user skipped the schedule suggestion for the task."
        user_prompt += f"\nExample: '👌 Понял, пропускаем задачу \"{data.get('task_content', '...')}\" сейчас.'"
    elif prompt_type == "task_creation_success":
        user_prompt += "\nGenerate a confirmation message that a task was successfully created. Include task content, project, and due time if available."
        user_prompt += f"\nExample: '✅ Задача \"{data.get('content', '...')}\" добавлена в проект \"{data.get('project_name', 'Входящие')}\" со сроком \"{data.get('due_string', 'без срока')}\".'"
    elif prompt_type == "task_creation_fail":
        user_prompt += (
            "\nGenerate a short message indicating that task creation failed."
        )
        user_prompt += f"\nExample: '❌ Не удалось создать задачу в Todoist.'"
    elif prompt_type == "duration_update_success":
        user_prompt += (
            "\nGenerate a confirmation message that the task duration was updated."
        )
        user_prompt += f"\nExample: '✅ Продолжительность задачи обновлена на {data.get('duration_minutes', '...')} минут.'"
    elif prompt_type == "duration_update_fail":
        user_prompt += (
            "\nGenerate a short message indicating that updating task duration failed."
        )
        user_prompt += f"\nExample: '❌ Не удалось обновить продолжительность задачи.'"
    elif prompt_type == "general_error":
        user_prompt += "\nGenerate a generic error message for the user."
        user_prompt += f"\nExample: 'Произошла ошибка при обработке вашего запроса.'"
    # Add more prompt types as needed (e.g., reschedule confirmation/error, semantic command errors)

    full_prompt = (
        f"{system_instruction}\n\n{full_context}\n{user_prompt}\n\nGenerated Response:"
    )
    logger.debug(
        f"Final Gemini prompt for response generation (start): {full_prompt[:500]}..."
    )

    try:
        response = _model.generate_content(full_prompt)
        generated_text = response.text.strip()
        logger.debug(f"Received Gemini response for '{prompt_type}': {generated_text}")

        # Basic validation/cleanup
        if not generated_text or len(generated_text) < 5:
            logger.warning(
                f"LLM generated suspiciously short/empty response for {prompt_type}"
            )
            return None  # Indicate failure

        return generated_text

    except google.api_core.exceptions.GoogleAPIError as e:
        logger.error(f"Gemini API error during response generation: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during response generation: {e}", exc_info=True)
        return None
