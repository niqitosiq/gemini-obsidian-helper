import logging
import json
import asyncio  # Import asyncio
from typing import Optional, Dict, Any, List

# --- DI ---
# Imports removed as injection is no longer used here
# from dependency_injector.wiring import inject, Provide

# from containers import ApplicationContainer # Removed to break circular import
from services.interfaces import (
    ILLMService,
    IVaultService,
    IHistoryService,
    IPromptBuilderService,
    HistoryEntry,
)
from google.genai import types as genai_types

# from containers import get_container  # Moved import inside function

logger = logging.getLogger(__name__)


# @inject decorator removed - dependencies are passed explicitly
def process_user_message(
    user_message: str,
    # --- Dependencies passed as arguments ---
    history_service: IHistoryService,
    llm_service: ILLMService,
    vault_service: IVaultService,
    prompt_builder: IPromptBuilderService,
    tool_handlers_map: dict,
    user_id: int,  # Re-add user_id parameter
) -> Optional[Dict[str, Any]]:
    """
    Обрабатывает сообщение пользователя, используя переданные сервисы.
    Выполняет CQRS-подобное разделение для текстовых ответов и вызовов инструментов.
    """
    logger.info(
        f"Processing user message: {user_message[:100]}... for user_id: {user_id}"
    )  # Add user_id to log

    try:
        # 1. Обновляем историю
        user_entry: HistoryEntry = {"role": "user", "parts": [{"text": user_message}]}
        history_service.append_entry(user_entry)
        current_history = history_service.get_history()

        # 2. Получаем контекст Vault
        vault_files = vault_service.read_all_markdown_files()
        vault_context_str = None
        if vault_files:
            vault_context_parts = [
                f"File: {path}\n\n```\n{content}\n```\n\n"
                for path, content in vault_files.items()
            ]
            vault_context_str = "".join(vault_context_parts)
            if len(vault_context_str) > 150000:
                logger.warning(
                    f"Vault context size is very large (~{len(vault_context_str)} chars). Truncating."
                )
                vault_context_str = vault_context_str[:150000] + "\n... (truncated)"

        # 3. Строим промпт
        system_prompt = prompt_builder.build_system_prompt(
            current_history, vault_context_str
        )

        # 4. Вызываем LLM
        logger.debug("Calling LLM service...")
        api_history_content: List[genai_types.Content] = []
        for entry in current_history:
            # Modify list comprehension to create Part objects directly
            parts_for_api = [
                genai_types.Part(text=p["text"])
                for p in entry.get("parts", [])
                if "text" in p and p["text"] is not None
            ]
            if parts_for_api:
                api_history_content.append(
                    genai_types.Content(role=entry["role"], parts=parts_for_api)
                )

        response = llm_service.call_sync(
            contents=api_history_content,
            system_instruction=system_prompt,
            response_mime_type="application/json",
        )

        if not response:
            logger.error("LLM call failed. Response was None.")
            history_service.append_entry(
                {
                    "role": "model",
                    "parts": [{"text": "[Internal Error: LLM call failed]"}],
                }
            )
            return {"error": "LLM call failed."}

        # 5. Обрабатываем ответ LLM
        final_result_for_user: Optional[Dict[str, Any]] = None
        llm_text_response = ""

        if hasattr(response, "text") and response.text:
            llm_text_response = response.text
        elif (
            response.parts
            and hasattr(response.parts[0], "text")
            and response.parts[0].text
        ):
            llm_text_response = response.parts[0].text
        else:
            logger.error(f"Could not extract text from LLM response: {response}")
            history_service.append_entry(
                {
                    "role": "model",
                    "parts": [
                        {
                            "text": "[Internal Error: Could not extract text from LLM response]"
                        }
                    ],
                }
            )
            return {"error": "Could not extract text from LLM response."}

        logger.debug(f"LLM raw response text: {llm_text_response[:500]}...")

        history_service.append_entry(
            {"role": "model", "parts": [{"text": llm_text_response}]}
        )

        try:
            parsed_tool_calls = json.loads(llm_text_response)

            if not isinstance(parsed_tool_calls, list):
                raise ValueError("Expected JSON array of tool calls")

            logger.info(
                f"LLM response is JSON array with {len(parsed_tool_calls)} potential tool calls."
            )

            tool_execution_results = []
            last_reply_message = None

            for i, tool_call_obj in enumerate(parsed_tool_calls):
                if (
                    not isinstance(tool_call_obj, dict)
                    or "tool" not in tool_call_obj
                    or "data" not in tool_call_obj
                ):
                    logger.error(
                        f"Invalid tool call format at position {i}: {tool_call_obj}"
                    )
                    tool_execution_results.append(
                        {
                            "tool": "invalid",
                            "status": "error",
                            "message": "Invalid format",
                        }
                    )
                    continue

                tool_name = tool_call_obj["tool"]
                tool_args = tool_call_obj["data"]
                logger.info(f"Processing tool call: {tool_name} with args: {tool_args}")

                if tool_name == "finish":
                    logger.info("Executing 'finish' tool: Clearing history.")
                    history_service.clear_history()
                    tool_result = {
                        "status": "finished",
                        "message": "Conversation history cleared.",
                    }
                    tool_execution_results.append({"tool": tool_name, **tool_result})
                    continue

                handler_provider_or_func = tool_handlers_map.get(tool_name)

                if handler_provider_or_func is None:
                    error_msg = f"Unknown tool requested: '{tool_name}'"
                    logger.error(error_msg)
                    tool_result = {"status": "error", "message": error_msg}
                else:
                    try:
                        # Get the provider/factory from the map
                        handler_provider = handler_provider_or_func  # It's already the provider from the map

                        # Use the handler directly from the map
                        handler_instance = (
                            handler_provider  # The map contains instances
                        )

                        tool_result = None
                        # Check if the INSTANCE has an 'execute' method
                        if hasattr(handler_instance, "execute") and callable(
                            handler_instance.execute
                        ):
                            logger.info(
                                f"Executing 'execute' method of tool handler instance for '{tool_name}'..."
                            )
                            # Check if the execute method is async
                            is_async_execute = asyncio.iscoroutinefunction(
                                handler_instance.execute
                            )

                            if is_async_execute:
                                logger.warning(
                                    f"Tool handler '{tool_name}' has an async execute method, but message_processor is sync. Cannot execute correctly."
                                )
                                # TODO: Fix async tool execution in sync context (e.g., make message_processor async or use asyncio.run())
                                # For now, return an error instead of trying to call it incorrectly.
                                tool_result = {
                                    "status": "error",
                                    "message": "Async tool called from sync context (execution skipped)",
                                }
                            else:
                                # Assume it's a sync execute method
                                tool_result = handler_instance.execute(**tool_args)
                        else:
                            error_msg = f"Handler instance for tool '{tool_name}' does not have a callable 'execute' method. Instance: {handler_instance}"
                            logger.error(error_msg)
                            tool_result = {"status": "error", "message": error_msg}

                        logger.info(
                            f"Tool '{tool_name}' execution result: {tool_result}"
                        )

                        if (
                            tool_name == "reply"
                            and isinstance(tool_result, dict)
                            and "message_to_send" in tool_result
                        ):
                            last_reply_message = tool_result["message_to_send"]
                            if tool_result.get("sent_directly", False):
                                logger.info("Reply tool sent message directly.")
                                last_reply_message = None

                    except Exception as e:
                        error_msg = f"Error executing tool '{tool_name}' with args {tool_args}: {e}"
                        logger.error(error_msg, exc_info=True)
                        tool_result = {"status": "error", "message": error_msg}

                tool_result_str = json.dumps(
                    tool_result, ensure_ascii=False, default=str
                )
                history_service.append_entry(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": f"[Tool Response ({tool_name}): {tool_result_str}]"
                            }
                        ],
                    }
                )
                tool_execution_results.append({"tool": tool_name, **tool_result})

            if last_reply_message:
                # final_result_for_user = {"text": last_reply_message}
                pass
            elif tool_execution_results:
                last_tool_res = tool_execution_results[-1]
                status = last_tool_res.get("status", "unknown")
                msg = last_tool_res.get(
                    "message", f"Tool '{last_tool_res.get('tool')}' finished."
                )
                final_result_for_user = {
                    "text": f"Action '{last_tool_res.get('tool')}': {status}. {msg}"
                }
            else:
                final_result_for_user = {
                    "text": "OK."
                }  # Default if no reply and no other result message

        except json.JSONDecodeError:
            logger.info("LLM response is plain text.")
            final_result_for_user = {"text": llm_text_response}

        except Exception as e:
            logger.error(
                f"Unexpected error processing LLM response tools: {e}", exc_info=True
            )
            history_service.append_entry(
                {
                    "role": "model",
                    "parts": [
                        {"text": f"[Internal Error: Tool processing error: {e}]"}
                    ],
                }
            )
            final_result_for_user = {
                "error": f"Unexpected error processing response tools: {e}"
            }

        logger.info(
            f"Finished processing message. Final result for user: {final_result_for_user}"
        )
        return final_result_for_user

    except Exception as e:
        logger.error(f"Unhandled error in process_user_message: {e}", exc_info=True)
        try:
            # Attempt to log error to history even if main processing failed
            history_service.append_entry(
                {
                    "role": "model",
                    "parts": [{"text": f"[Internal Error: Unhandled exception: {e}]"}],
                }
            )
        except Exception as hist_err:
            logger.error(f"Failed to append unhandled error to history: {hist_err}")
        return {"error": "An critical internal error occurred."}
