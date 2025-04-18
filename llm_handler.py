import logging

# import google.generativeai as genai # Old import
import google.genai as genai  # New import

# import google.api_core.exceptions # Old exception import
from google.genai import (
    types,
)  # Keep relevant sub-imports if needed, adjust path if necessary

# --- NEW: Import specific error type ---
from google.genai import errors as genai_errors
import json
import os
from typing import Optional, Union, List, Dict, Any
from datetime import datetime
import config
import knowledge_base
import todoist_handler


logger = logging.getLogger(__name__)

# --- MODIFICATION: Use Client instead of Model ---
_client: Optional[genai.Client] = None
_model_name = "gemini-2.0-flash"  # Define the model name to use

try:
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set.")
    # --- MODIFICATION: Initialize Client ---
    # genai.configure(api_key=config.GEMINI_API_KEY) # Old configuration
    # _model = genai.GenerativeModel("gemini-1.5-flash") # Old model initx
    _client = genai.Client(api_key=config.GEMINI_API_KEY)
    logger.info(f"Gemini API client configured for model '{_model_name}'.")
except Exception as e:
    logger.critical(f"Critical error configuring Gemini API: {e}", exc_info=True)
    _client = None  # Ensure client is None on error


def assemble_context(
    source: str, conversation_history: Optional[List[str]] = None
) -> str:
    """Assembles context for Gemini prompt based on settings."""
    if not _client:
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
            context_parts.append("- Knowledge Base:")
            context_parts.append(kb_content)  # Append the actual content
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
        context_parts.append("- Todoist Projects:")
        for proj in projects:
            context_parts.append(f"  - ID: {proj['id']}, Name: {proj['name']}")
    else:
        context_parts.append("- Todoist Projects: Could not fetch.")

    # --- NEW: Add Active Tasks to Context ---
    active_tasks = todoist_handler.get_tasks()  # Call the modified function
    if active_tasks:
        context_parts.append("- Active Todoist Tasks:")
        # Limit the number of tasks shown to avoid excessive context length?
        # For now, show all, but consider limiting later if needed.
        for task in active_tasks:
            due_info = ""
            if task.due:
                due_info = f", Due: {task.due.string}"
            duration_info = ""
            if task.duration:
                duration_info = (
                    f", Duration: {task.duration.amount} {task.duration.unit}"
                )
            context_parts.append(
                f"  - ID: {task.id}, Content: '{task.content}'{due_info}{duration_info}"
            )
    else:
        context_parts.append("- Active Todoist Tasks: None found or error fetching.")
    # --- END NEW ---

    context_parts.append("[END CONTEXT]\\n")
    return "\n".join(context_parts)


def analyze_text(
    text: str, source: str, conversation_history: Optional[List[str]] = None
) -> Optional[Dict]:
    """Analyzes text using Gemini with assembled context."""
    if not _client:
        logger.error("Analysis impossible: Gemini client not initialized.")
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

    # --- FIX: Instantiate types.Part directly ---
    contents_for_api = [
        types.Content(
            role="user",
            parts=[
                types.Part(text=f"{full_context}\n{user_prompt}")
            ],  # Instantiate Part directly
        )
    ]

    logger.debug(f"Final Gemini contents (start): {str(contents_for_api)[:500]}...")

    try:
        response = _client.models.generate_content(
            model=_model_name,
            contents=contents_for_api,
            config=(
                types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                )
                if system_instruction
                else types.GenerateContentConfig(response_mime_type="application/json")
            ),
        )
        logger.debug(f"Received Gemini response: {response.text}")

        # --- MODIFICATION: JSON parsing might be simpler if response_mime_type works ---
        # json_response_str = response.text.strip()
        # if json_response_str.startswith("```json"):
        #     json_response_str = json_response_str[7:]
        # if json_response_str.endswith("```"):
        #     json_response_str = json_response_str[:-3]
        # json_response_str = json_response_str.strip()
        # result = json.loads(json_response_str)

        # Attempt direct parsing, fallback to text cleaning
        try:
            json_text = response.text.strip()
            # Clean potential markdown fences
            if json_text.startswith("```json"):
                json_text = json_text[7:]
            if json_text.endswith("```"):
                json_text = json_text[:-3]
            result = json.loads(json_text.strip())

        except (json.JSONDecodeError, AttributeError) as parse_err:
            logger.error(
                f"Failed to parse JSON from Gemini response: {parse_err}. Response text: {getattr(response, 'text', '[NO TEXT]')}"
            )
            return None

        required_keys = ["action", "status"]
        if not all(key in result for key in required_keys):
            logger.error(f"Gemini response missing required keys: {result}")
            return None
        if result["status"] == "incomplete" and not result.get("missing_info"):
            logger.error(
                f"Status 'incomplete' but 'missing_info' missing in Gemini response: {result}"
            )
            result["missing_info"] = ["Need to clarify details"]
            # Adjust clarification question based on language if possible
            result["clarification_question"] = (
                "Не могли бы вы уточнить детали?"
                if any(char in text for char in "абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
                else "Could you please provide more details?"
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
            f"Error decoding JSON from Gemini response: {e}\\nResponse: {getattr(response, 'text', '[NO TEXT]')}",
            exc_info=True,
        )
        return None
    # --- MODIFICATION: Use new exception type ---
    except genai_errors.APIError as e:
        logger.error(f"Gemini API error: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during Gemini call: {e}", exc_info=True)
        return None


def transcribe_audio(audio_file_path: str) -> Optional[str]:
    """Transcribes audio file using Gemini."""
    # --- MODIFICATION: Check _client ---
    if not _client:
        logger.error("Transcription impossible: Gemini client not initialized.")
        return None
    if not os.path.exists(audio_file_path):
        logger.error(f"Audio file for transcription not found: {audio_file_path}")
        return None

    logger.info(f"Loading and transcribing audio file: {audio_file_path}...")
    try:
        # --- MODIFICATION: Use _client.files.upload ---
        # audio_file = genai.upload_file(path=audio_file_path) # Old way
        audio_file = _client.files.upload(file=audio_file_path)  # New way
        logger.debug(f"Audio file uploaded: {audio_file.name}, URI: {audio_file.uri}")

        prompt = "Transcribe this audio file verbatim."
        # --- MODIFICATION: Use _client.models.generate_content ---
        # response = _model.generate_content([prompt, audio_file]) # Old way
        response = _client.models.generate_content(
            model=_model_name,  # Specify model
            contents=[prompt, audio_file],  # Pass prompt and file
        )

        try:
            # --- MODIFICATION: Use _client.files.delete ---
            # genai.delete_file(audio_file.name) # Old way
            _client.files.delete(name=audio_file.name)  # New way
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

    # --- MODIFICATION: Use new exception type ---
    except genai_errors.APIError as e:
        logger.error(f"Gemini API error during audio transcription: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error during audio transcription {audio_file_path}: {e}",
            exc_info=True,
        )
        return None


# --- NEW: Function to get instructions from LLM ---


async def get_instructions(
    user_text: str,
    source: str,
    conversation_history: Optional[List[str]] = None,
    pending_question_key: Optional[str] = None,
    pending_question_context: Optional[Any] = None,
) -> List[Dict]:
    """
    Asks the LLM to generate a sequence of instructions based on user input
    and current state (e.g., pending question).
    """
    if not _client:
        logger.error(
            "Instruction generation impossible: Gemini client not initialized."
        )
        # Return a reply instruction indicating an error
        return [
            {
                "instruction_type": "reply_user",
                "parameters": {"message_text": "Ошибка: Не удалось связаться с LLM."},
            },
            {"instruction_type": "finish_request", "parameters": {}},
        ]

    # Assemble context (now includes active tasks)
    full_context = assemble_context(source, conversation_history)
    if pending_question_key:
        # Include task_id in context if available from the pending question
        task_id_context = ""
        if isinstance(pending_question_context, dict) and pending_question_context.get(
            "task_id"
        ):
            task_id_context = (
                f"\n- Related Task ID: {pending_question_context['task_id']}"
            )

        full_context += f"\n[PENDING QUESTION CONTEXT]\n- State Key: {pending_key}{task_id_context}\n- Details: {json.dumps(pending_question_context, ensure_ascii=False)}\n- User's Answer: {user_text}\n[END PENDING QUESTION CONTEXT]\n"
        user_prompt_header = "USER ANSWER TO PENDING QUESTION:"

    else:
        user_prompt_header = "USER REQUEST:"

    system_instruction = """You are an AI assistant controlling a bot. Your goal is to break down the user's request (or their answer to a previous question) into a sequence of explicit instructions for the bot to execute.

Analyze the request/answer considering the provided CONTEXT (Knowledge Base, projects, Active Todoist Tasks, time, pending question context if any).

Generate a JSON array of instruction objects. Each object must have 'instruction_type' and 'parameters'.

Available Instruction Types:

1.  `create_task`: Creates a new task in Todoist. IMPORTANT: Use this instruction ONLY if you have sufficient details (content, due date/time, optionally duration). If key details like due date/time are missing and not implied by context (e.g., user didn't say 'today'), use `ask_user` first.
    - `parameters`:
        - `content` (str): Task title. Choose a clear and concise name. Include key details like duration if helpful (e.g., 'Велопрогулка 30 мин', 'Проверка почты'). Avoid generic names like 'задача' or 'поездка'.
        - `project_id` (str, optional): ID from CONTEXT. Use 'inbox' if unsure.
        - `due_string` (str, optional): Use Todoist natural language. **Be specific with time (e.g., "tomorrow 9am", "в пятницу 18:00", "2025-05-10 10:00"). Avoid vague terms like "вечером", "утром" unless the user explicitly uses them.** IMPORTANT: Only use recurrence patterns (...) if the user explicitly asks for repetition (...). If the request doesn't clearly state recurrence, create a task for a single instance (...). Do not default to 'today' unless explicitly stated by the user.
        - `priority` (int, optional): 1 (P1) to 4 (P4). Default 4.
        - `duration_minutes` (int, optional): Task duration in minutes. Ensure this matches the task name if duration is included there.
        - `description` (str, optional): Task details.

2.  `update_task`: Modifies an existing task in Todoist.
    - `parameters`:
        - `task_id` (str): The ID of the task to update. **Crucial! Find the correct task ID by matching the user's request with the 'Active Todoist Tasks' list provided in the CONTEXT. If you cannot uniquely identify the task, use `ask_user`. Do NOT guess or use 'unknown'.**
        - `content` (str, optional): New task title.
        - `due_string` (str, optional): New due date/time string. Use Todoist format. **Be specific with time (e.g., "tomorrow 9am", "в пятницу 18:00", "2025-05-10 10:00"). Avoid vague terms like "вечером", "утром".** Set to empty string "" to remove due date.
        - `duration_minutes` (int, optional): New duration in minutes. Set to 0 or null to remove duration.
        - `description` (str, optional): New description.
        - `priority` (int, optional): New priority (1-4).
        - `project_id` (str, optional): New project ID.

3.  `reply_user`: Sends a message back to the user.
    - `parameters`:
        - `message_text` (str): The message to send. Use this to confirm actions taken (like task creation/update) or to explain issues.

4.  `ask_user`: Asks the user a question to get missing information. Use this ONLY if information is absolutely necessary to proceed and cannot be reasonably assumed.
    - `parameters`:
        - `question_text` (str): The question for the user. Use this if `create_task` lacks due date/time (e.g., "На когда запланировать 'Купить шпаклевку'?"). Also use if the `task_id` for `update_task` is unclear or ambiguous based on the context (e.g., "Какую из задач 'Выпить пиво' вы хотите перенести?").
        - `state_key` (str): A unique key describing what you are asking for (e.g., "clarify_due_date_for_task", "clarify_task_for_update", "get_duration_for_report"). The user's next message will be treated as the answer related to this key.
        - `related_data` (dict, optional): Include relevant data like the task content being clarified or potential task matches.

5.  `finish_request`: Signals that the current user request has been fully processed or cannot be processed further. MUST be the LAST instruction in the array if used.
    - `parameters`: {}

Workflow:
- Analyze the user's input.
- Task Creation Flow: Check for details, use `create_task` or `ask_user`.
- Task Update Flow: Identify `task_id` from CONTEXT, use `update_task` or `ask_user`.
- After `create_task` or `update_task`, usually add `reply_user` for confirmation.
- If clarification needed via `ask_user`, stop and wait.
- Always conclude with `finish_request`.
- If input unclear, use `reply_user` to explain and then `finish_request`.

Respond STRICTLY with a JSON array of instruction objects. Ensure the JSON is valid.
"""
    user_prompt = f"{user_prompt_header} {user_text}"

    # --- FIX: Instantiate types.Part directly ---
    contents_for_api = [
        types.Content(
            role="user",
            parts=[types.Part(text=f"{full_context}\n{user_prompt}")],
        )
    ]

    logger.debug(
        f"Generating instructions. Prompt starts with: {str(contents_for_api)[:500]}..."
    )

    try:
        response = await _client.aio.models.generate_content(
            model=_model_name,
            contents=contents_for_api,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
            ),
        )
        logger.debug(f"Received LLM response for instructions: {response.text}")

        try:
            json_text = response.text.strip()
            # Clean potential markdown fences
            if json_text.startswith("```json"):
                json_text = json_text[7:]
            if json_text.endswith("```"):
                json_text = json_text[:-3]
            instructions = json.loads(json_text.strip())

            if not isinstance(instructions, list):
                logger.error(f"LLM instruction response is not a list: {instructions}")
                raise ValueError("LLM response for instructions was not a list.")

            # Basic validation of instruction structure
            for instruction in instructions:
                if (
                    not isinstance(instruction, dict)
                    or "instruction_type" not in instruction
                    or "parameters" not in instruction
                ):
                    logger.error(f"Invalid instruction format: {instruction}")
                    raise ValueError("Invalid instruction format received from LLM.")

            return instructions

        except (json.JSONDecodeError, ValueError, AttributeError) as parse_err:
            logger.error(
                f"Failed to parse JSON instructions from LLM response: {parse_err}. Response text: {getattr(response, 'text', '[NO TEXT]')}"
            )
            # Fallback instruction
            return [
                {
                    "instruction_type": "reply_user",
                    "parameters": {
                        "message_text": "Извините, не смог обработать ответ от LLM. Попробуйте еще раз."
                    },
                },
                {"instruction_type": "finish_request", "parameters": {}},
            ]

    except genai_errors.APIError as e:
        logger.error(
            f"Gemini API error during instruction generation: {e}", exc_info=True
        )
        return [
            {
                "instruction_type": "reply_user",
                "parameters": {"message_text": "Ошибка API при генерации инструкций."},
            },
            {"instruction_type": "finish_request", "parameters": {}},
        ]
    except Exception as e:
        logger.error(
            f"Unexpected error during instruction generation: {e}", exc_info=True
        )
        return [
            {
                "instruction_type": "reply_user",
                "parameters": {
                    "message_text": "Неожиданная ошибка при генерации инструкций."
                },
            },
            {"instruction_type": "finish_request", "parameters": {}},
        ]


# --- Function to parse duration response ---


async def parse_duration_response(text: str) -> Optional[int]:
    """Uses LLM to parse duration in minutes from user's text response."""
    if not _client:
        logger.error("Duration parsing impossible: Gemini client not initialized.")
        return None

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
    # --- FIX: Instantiate types.Part directly ---
    contents_for_api = [
        types.Content(
            role="user",
            parts=[types.Part(text=user_prompt)],  # Instantiate Part directly
        )
    ]

    logger.debug(f"Sending prompt to LLM for duration parsing: {contents_for_api}")

    try:
        response = await _client.aio.models.generate_content(
            model=_model_name,
            contents=contents_for_api,
            config=(
                types.GenerateContentConfig(system_instruction=system_instruction)
                if system_instruction
                else None
            ),
        )

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
            # Try a fallback: maybe it included units?
            try:
                import re

                match = re.match(r"(\d+)", result_text)
                if match:
                    logger.info(f"Falling back to extracted digits: {match.group(1)}")
                    return int(match.group(1))
            except:
                pass  # Ignore fallback errors
            return None  # Treat unexpected responses as failure

    # --- MODIFICATION: Use new exception type ---
    except genai_errors.APIError as e:
        logger.error(f"Gemini API error during duration parsing: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during duration parsing: {e}", exc_info=True)
        return None


# --- Function for Generic Responses ---


async def generate_response(prompt_type: str, data: Dict[str, Any]) -> Optional[str]:
    """Generates various text responses using LLM based on prompt type."""
    if not _client:
        logger.error("Response generation impossible: Gemini client not initialized.")
        return None

    full_context = assemble_context("llm_response_generation")
    logger.debug(f"Assembled context for LLM response generation:\n{full_context}")

    system_instruction = "You are an AI assistant helping a user manage their tasks and schedule. Generate a helpful and concise response based on the request type and provided data. Respond in Russian unless the user context indicates otherwise. Be friendly and encouraging."

    user_prompt = f"Request Type: {prompt_type}\\nData:\\n"
    for key, value in data.items():
        user_prompt += f"- {key}: {json.dumps(value, ensure_ascii=False, indent=2)}\\n"

    # Add specific instructions based on prompt_type
    # ... (prompt examples) ...
    if prompt_type == "schedule_intro":
        user_prompt += "\\nGenerate a short, friendly introductory message for the user's daily schedule, mentioning the day type (workday/weekend) and date."
        user_prompt += f"\\nExample for workday: '🗓 Доброе утро! Вот ваше расписание на сегодня ({datetime.now().strftime('%A, %d.%m.%Y')}):'"
        user_prompt += f"\\nExample for weekend: '🏖 Доброе утро! Сегодня {datetime.now().strftime('%A, %d.%m.%Y')} - выходной день! Вот несколько идей:'"
    elif prompt_type == "schedule_body":
        user_prompt += "\\nGenerate the main body of the schedule message."
        user_prompt += (
            "\\n- If there are scheduled_tasks, list them clearly with times (HH:MM)."
        )
        user_prompt += "\\n- If there are no scheduled_tasks but needs_clarification is true, state that some tasks need duration clarification for planning."
        user_prompt += "\\n- If there are no scheduled_tasks and no clarification needed, state that there are no tasks planned for today (mention if it's a weekend)."
        user_prompt += "\\n- Keep the format clean and easy to read."
        user_prompt += "\\nExample with tasks: '📋 09:00 - Task 1\\n⏰ 11:30 - Task 2 (срок сегодня)'"
        user_prompt += "\\nExample clarification needed: 'Есть задачи на сегодня, но для планирования нужно уточнить их длительность.'"
        user_prompt += (
            "\\nExample empty workday: 'Не нашел задач для планирования на сегодня.'"
        )
        user_prompt += (
            "\\nExample empty weekend: 'Сегодня выходной! Задач нет, можно отдохнуть.'"
        )
    elif prompt_type == "clarify_duration":
        user_prompt += "\\nGenerate a short, polite question asking the user for the estimated duration (in minutes or hours) for the given task_content."
        user_prompt += f"\\nExample: '📝 Про задачу \\\"{data.get('task_content', '...')}\\\": Сколько примерно времени потребуется на ее выполнение?'"
    elif prompt_type == "suggest_schedule_slot":
        user_prompt += "\\nGenerate a message suggesting a specific time slot for a task. Ask the user to confirm via buttons."
        user_prompt += f"\\nExample: '🗓️ Предлагаю запланировать задачу \\\"{data.get('task_content', '...')}\\\" на {data.get('proposed_time', 'HH:MM')} сегодня ({data.get('date', 'YYYY-MM-DD')}). Назначить?'"
    elif prompt_type == "schedule_confirm":
        user_prompt += "\\nGenerate a short confirmation message that the user accepted the schedule suggestion and the task is now scheduled."
        user_prompt += f"\\nExample: '✅ Отлично! Задача \\\"{data.get('task_content', '...')}\\\" запланирована на {data.get('scheduled_time', 'HH:MM')}.'"
    elif prompt_type == "schedule_skip":
        user_prompt += "\\nGenerate a short message acknowledging the user skipped the schedule suggestion for the task."
        user_prompt += f"\\nExample: '👌 Понял, пропускаем задачу \\\"{data.get('task_content', '...')}\\\" сейчас.'"
    elif prompt_type == "task_creation_success":
        user_prompt += "\\nGenerate a confirmation message that a task was successfully created. Include task content, project and due time if available."
        user_prompt += f"\\nExample: '✅ Задача \\\"{data.get('content', '...')}\\\" добавлена в проект \\\"{data.get('project_name', 'Входящие')}\\\" со сроком \\\"{data.get('due_string', 'без срока')}\\\".'"
    elif prompt_type == "task_creation_fail":
        user_prompt += (
            "\\nGenerate a short message indicating that task creation failed."
        )
        user_prompt += f"\\nExample: '❌ Не удалось создать задачу в Todoist.'"
    elif prompt_type == "duration_update_success":
        user_prompt += (
            "\\nGenerate a confirmation message that the task duration was updated."
        )
        user_prompt += f"\\nExample: '✅ Продолжительность задачи обновлена на {data.get('duration_minutes', '...')} минут.'"
    elif prompt_type == "duration_update_fail":
        user_prompt += (
            "\\nGenerate a short message indicating that updating task duration failed."
        )
        user_prompt += f"\\nExample: '❌ Не удалось обновить продолжительность задачи.'"
    elif prompt_type == "general_error":
        user_prompt += "\\nGenerate a generic error message for the user."
        user_prompt += f"\\nExample: 'Произошла ошибка при обработке вашего запроса.'"

    # --- FIX: Instantiate types.Part directly ---
    contents_for_api = [
        types.Content(
            role="user",
            parts=[
                types.Part(text=f"{full_context}\n{user_prompt}")
            ],  # Instantiate Part directly
        )
    ]

    logger.debug(
        f"Final Gemini prompt for response generation (start): {str(contents_for_api)[:500]}..."
    )

    try:
        response = await _client.aio.models.generate_content(
            model=_model_name,
            contents=contents_for_api,
            config=(
                types.GenerateContentConfig(system_instruction=system_instruction)
                if system_instruction
                else None
            ),
        )

        generated_text = response.text.strip()
        logger.debug(f"Received Gemini response for '{prompt_type}': {generated_text}")

        # Basic validation/cleanup
        if not generated_text or len(generated_text) < 5:
            logger.warning(
                f"LLM generated suspiciously short/empty response for {prompt_type}"
            )
            # Return None or a default message based on prompt_type?
            # Let's return None for now, the caller should handle fallbacks.
            return None

        return generated_text

    # --- MODIFICATION: Use new exception type ---
    except genai_errors.APIError as e:
        logger.error(f"Gemini API error during response generation: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during response generation: {e}", exc_info=True)
        return None
