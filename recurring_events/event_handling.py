import logging
import datetime
import re
import json  # Import the json module
from typing import Dict, Any

# --- DI ---
from dependency_injector.wiring import inject, Provide
from dependency_injector import providers

# --- Интерфейсы ---
from services.interfaces import (
    IRecurringEventsEngine,
    ISchedulingService,
    ILLMService,
    IHistoryService,
    ITelegramService,  # Import ITelegramService instead
)

# Import ReplyToolHandler
from tools.tool_reply import ReplyToolHandler

# Assuming genai_types is available or needs to be imported
from google.genai import types as genai_types  # Uncomment if needed

logger = logging.getLogger(__name__)


def validate_event_data(event_id: str, data: Dict[str, Any]) -> bool:
    """Проверяет наличие обязательных полей в данных события."""
    required_keys = ["schedule_time", "prompt"]
    if not all(key in data for key in required_keys):
        logger.error(
            f"Event '{event_id}' data is missing required keys: {required_keys}. Data: {data}"
        )
        return False
    return True


def schedule_event(
    engine: IRecurringEventsEngine,
    scheduling_service: ISchedulingService,
    event_id: str,
    event_data: Dict[str, Any],
):
    """Регистрирует событие в SchedulingService."""
    schedule_dsl = event_data.get("schedule_time")
    if not schedule_dsl:
        logger.error(f"Cannot schedule event '{event_id}': missing 'schedule_time'.")
        return

    success = scheduling_service.add_job(
        schedule_dsl=schedule_dsl,
        event_id=event_id,
        callback=engine._handle_time_event,  # Call back to the engine's handler
    )
    if success:
        logger.info(
            f"Successfully scheduled event '{event_id}' with rule: {schedule_dsl}"
        )
    else:
        logger.error(f"Failed to schedule event '{event_id}' with rule: {schedule_dsl}")


def handle_time_event(
    engine: IRecurringEventsEngine,
    event_id: str,
    telegram_service: ITelegramService,  # Use telegram_service parameter instead
):
    """Обработчик временного события, вызванный SchedulingService."""
    logger.info(f"Handling scheduled time event: {event_id}; \n{engine._events}\n")
    event_data = engine._events.get(event_id)  # Access events from the engine
    logger.info(f"Event data for '{event_id}': {event_data}")

    if not event_data:
        logger.warning(
            f"Event data not found for triggered event ID: {event_id}. Attempting to reload if file event."
        )
        # Check if it's a file-based event ID and attempt to reload
        match = re.match(r"reminder_(?:30m|5m)_(.+)", event_id)
        if match:
            relative_path = match.group(1)
            try:
                # Use the engine's method which calls vault_tasks.handle_vault_file_event
                engine.handle_vault_file_event(relative_path)
                # Attempt to retrieve event data again after reloading
                event_data = engine._events.get(event_id)
                if event_data:
                    logger.info(
                        f"Successfully reloaded event data for {event_id} after file event."
                    )
                else:
                    logger.error(
                        f"Event data still not found for triggered file event ID after reload attempt: {event_id}"
                    )
                    return
            except Exception as e:
                logger.error(
                    f"Error handling file event reload for {event_id}: {e}",
                    exc_info=True,
                )
                return
        else:
            logger.error(f"Event data not found for triggered event ID: {event_id}")
            return

    execute_event(
        engine,
        event_id,
        event_data,
        telegram_service,  # Pass telegram_service to execute_event
    )
    # Update last_run time only if event_data was successfully retrieved/reloaded
    if event_data:
        event_data["last_run"] = datetime.datetime.now().isoformat()


def execute_event(
    engine: IRecurringEventsEngine,
    event_id: str,
    event_data: Dict[str, Any],
    telegram_service: ITelegramService,  # Use TelegramService instead
):
    """Выполняет логику события (например, отправка напоминания через LLM)."""
    logger.info(f"Executing logic for event: {event_id}")
    prompt_template = event_data.get("prompt", "{event_id}")

    try:
        current_datetime = datetime.datetime.now()
        formatted_prompt = prompt_template.format(
            event_id=event_id,
            date=current_datetime.strftime("%Y-%m-%d"),
            time=current_datetime.strftime("%H:%M"),
        )

        logger.info(
            f"Formatted prompt for event '{event_id}': {formatted_prompt[:100]}..."
        )

        current_history = (
            engine._history_service.get_history()
        )  # Access history from engine
        # Ensure genai_types.Content is correctly used or mocked
        llm_contents = [
            genai_types.Content(
                role=entry["role"],
                parts=[
                    (
                        genai_types.Part(text=p["text"])
                        if isinstance(p, dict) and "text" in p
                        else genai_types.Part(text=str(p))
                    )
                    for p in entry["parts"]
                ],
            )
            for entry in current_history
            if entry.get("parts")
        ]

        # If it's a file event, add the file content to the LLM contents as a text part
        if event_data.get("is_file_event"):
            # Extract the relative file path from the event ID
            match = re.match(r"reminder_(?:30m|5m)_(.+)", event_id)
            if match:
                relative_file_path = match.group(1)
                # Assuming 'vault' is the correct base directory
                file_path = f"vault/{relative_file_path}"
                try:
                    # Read the file content first
                    with open(file_path, "r", encoding="utf-8") as f:
                        file_content = f.read()
                    logger.info(f"Successfully read file content from {file_path}.")

                    # Now, add the prompt and the file content as separate text parts
                    # within the same 'user' message (Content object).
                    llm_contents.append(
                        genai_types.Content(
                            role="user",
                            parts=[
                                genai_types.Part(text=formatted_prompt),
                                # Add file content as another text part, maybe with a header
                                genai_types.Part(
                                    text=f"\n\n--- Content from file: {relative_file_path} ---\n\n{file_content}"
                                ),
                            ],
                        )
                    )
                    logger.info(
                        f"Added file content from {file_path} as text part to LLM contents."
                    )

                except FileNotFoundError:
                    logger.error(
                        f"File not found when trying to read for LLM contents: {file_path}"
                    )
                    # Fallback: Just send the original prompt if file is missing
                    llm_contents.append(
                        genai_types.Content(
                            role="user", parts=[genai_types.Part(text=formatted_prompt)]
                        )
                    )
                except Exception as e:
                    logger.error(
                        f"Error reading file {file_path} for LLM contents: {e}",
                        exc_info=True,
                    )
                    # Fallback: Just send the original prompt on other errors
                    llm_contents.append(
                        genai_types.Content(
                            role="user", parts=[genai_types.Part(text=formatted_prompt)]
                        )
                    )
            else:
                logger.warning(
                    f"Could not extract file path from event ID for file event: {event_id}"
                )
                # Fallback if regex fails
                llm_contents.append(
                    genai_types.Content(
                        role="user", parts=[genai_types.Part(text=formatted_prompt)]
                    )
                )
        else:
            # If not a file event, just add the formatted prompt as text
            llm_contents.append(
                genai_types.Content(
                    role="user", parts=[genai_types.Part(text=formatted_prompt)]
                )
            )

        response = engine._llm_service.call_sync(  # Access LLM service from engine
            contents=llm_contents, response_mime_type="application/json"
        )

        if not response:
            logger.error(f"LLM call failed for event '{event_id}'.")
            return

        llm_text_response = ""
        if hasattr(response, "text") and response.text:
            llm_text_response = response.text
        elif (
            response.parts
            and hasattr(response.parts[0], "text")
            and response.parts[0].text
        ):
            llm_text_response = response.parts[0].text

        if not llm_text_response:
            logger.warning(f"LLM returned empty response for event '{event_id}'.")
            return  # Выходим, если ответ пустой

        logger.debug(
            f"LLM raw response for event '{event_id}': {llm_text_response[:500]}..."
        )

        # 1. Всегда добавляем сырой ответ LLM в историю
        engine._history_service.append_entry(
            {"role": "model", "parts": [{"text": llm_text_response}]}
        )

        # Remove the debug logging line causing AttributeError
        # logger.debug(f"Tool handlers map in execute_event: {engine._tool_handlers_map}")
        # 2. Пытаемся обработать ответ как вызов инструмента (особенно 'reply')
        try:
            parsed_tool_calls = json.loads(llm_text_response)

            if not isinstance(parsed_tool_calls, list):
                logger.warning(
                    f"LLM response for event '{event_id}' was JSON, but not a list. Treating as text."
                )
                # Ничего не делаем, ответ уже в истории
                return

            reply_executed = False
            for tool_call_obj in parsed_tool_calls:
                if (
                    isinstance(tool_call_obj, dict)
                    and tool_call_obj.get("tool") == "reply"
                    and "data" in tool_call_obj
                    and isinstance(tool_call_obj["data"], dict)  # Доп. проверка
                    and "message" in tool_call_obj["data"]
                ):

                    message_to_send = tool_call_obj["data"]["message"]
                    logger.info(
                        f"Found 'reply' tool call in LLM response for event '{event_id}'. Attempting to send..."
                    )

                    # Получаем карту обработчиков инструментов из атрибута движка (ожидаем, что это уже словарь с инстансами)
                    tool_handlers_map = (
                        engine._tool_handlers_map_provider
                    )  # Use directly as dictionary of instances

                    # Получаем инстанс обработчика 'reply' из карты
                    reply_handler_instance = tool_handlers_map.get("reply")

                    # Check if the handler instance was found and is a ReplyToolHandler instance
                    if isinstance(reply_handler_instance, ReplyToolHandler):
                        logger.debug(
                            f"Found ReplyToolHandler instance: {type(reply_handler_instance)}"
                        )
                        try:
                            # Attempting to execute reply handler instance directly
                            # Get user_id from event_data instead of TelegramService
                            user_id_for_reply = event_data.get("user_id")
                            logger.debug(
                                f"User ID for reply from event_data: {user_id_for_reply}"
                            )

                            if (
                                user_id_for_reply
                            ):  # Only execute if user_id is available
                                reply_result = reply_handler_instance.execute(
                                    message=message_to_send,
                                    user_id=user_id_for_reply,  # Pass user_id from event_data
                                )
                                logger.info(
                                    f"Reply tool execution result for event '{event_id}': {reply_result}"
                                )
                            else:
                                logger.warning(
                                    f"Cannot execute reply for event '{event_id}': 'user_id' missing in event_data."
                                )
                                reply_result = {
                                    "sent_directly": False
                                }  # Simulate failure if no user_id
                            # Проверяем, было ли отправлено напрямую
                            if reply_result.get("sent_directly"):
                                reply_executed = True
                            else:
                                # Если не отправлено напрямую (например, нет контекста),
                                # то просто логируем (т.к. из движка отправить некуда)
                                logger.warning(
                                    f"Reply tool for event '{event_id}' could not send message directly. Message content: {message_to_send[:100]}..."
                                )

                        except Exception as handler_exec_err:
                            logger.error(
                                f"Error executing ReplyToolHandler instance for event '{event_id}': {handler_exec_err}",
                                exc_info=True,
                            )
                    else:
                        # This case should ideally not be reached if the map contains instances
                        logger.error(
                            "Reply tool handler not found or is not a valid instance in tool map."
                        )

                    # Обычно достаточно одного reply на событие
                    if reply_executed:
                        break  # Выходим из цикла, если успешно отправили

            if not reply_executed:
                logger.info(
                    f"No executable 'reply' tool call found or executed in LLM response for event '{event_id}'. Response saved to history."
                )

        except json.JSONDecodeError:
            # Если ответ LLM - не JSON, считаем его простым текстом
            logger.info(
                f"LLM response for event '{event_id}' was plain text. Response saved to history."
            )
            # Ничего больше не делаем, текст уже в истории

        except Exception as e:
            # Ловим другие возможные ошибки при обработке ответа
            logger.error(
                f"Error processing LLM tool response for event '{event_id}': {e}",
                exc_info=True,
            )

    except Exception as e:
        # Этот блок остается для перехвата ошибок на более высоком уровне execute_event
        logger.error(f"Error executing event '{event_id}': {e}", exc_info=True)
