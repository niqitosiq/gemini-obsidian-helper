import logging
import json
import datetime
from typing import List, Dict, Any, Optional

# Импортируем интерфейс, который реализуем, и тип HistoryEntry
from .interfaces import IPromptBuilderService, HistoryEntry

# Импортируем функцию для получения определений инструментов
# TODO: В идеале, определения инструментов тоже должны предоставляться через DI
#       (например, через IToolRegistryService), но пока оставляем прямой импорт.
from tools import get_tool_definitions

logger = logging.getLogger(__name__)


class PromptBuilderServiceImpl(IPromptBuilderService):
    """
    Реализация сервиса для построения системных промптов для LLM.
    Инкапсулирует логику из старого модуля prompt_builder.py.
    """

    def __init__(self):
        """
        Инициализирует сервис. Кэширует определения инструментов при создании.
        """
        # Сервис пока не имеет внешних зависимостей через конструктор,
        # но может получить их позже (например, IConfigService или IToolRegistryService).
        logger.debug("PromptBuilderService initialized.")
        try:
            # Получаем и кэшируем определения инструментов
            self._tool_defs_cache = get_tool_definitions()
            logger.debug(f"Cached {len(self._tool_defs_cache)} tool definitions.")
        except Exception as e:
            logger.error(f"Failed to get or cache tool definitions: {e}", exc_info=True)
            self._tool_defs_cache = []  # Используем пустой список в случае ошибки

    def _format_tool_descriptions(self) -> str:
        """
        Форматирует кэшированные определения инструментов в читаемую строку
        для использования в промпте.
        """
        if not self._tool_defs_cache:
            return "No tools available or failed to load definitions."

        description_lines = []
        for tool in self._tool_defs_cache:
            name = tool.get("name", "unnamed_tool")
            description = tool.get("description", "No description.")
            description_lines.append(f"- {name}: {description}")

            param_details = []
            required_params = tool.get("required", [])
            parameters = tool.get("parameters")  # Получаем словарь параметров

            # Проверяем, что parameters это словарь и не пустой
            if isinstance(parameters, dict) and parameters:
                for key in parameters:
                    status = "required" if key in required_params else "optional"
                    # Можно добавить тип параметра, если он есть в схеме
                    # param_type = parameters[key].get('type', 'any')
                    # param_details.append(f"{key} ({param_type}, {status})")
                    param_details.append(f"{key} ({status})")

            if param_details:
                # Используем join для корректного форматирования списка параметров
                description_lines.append(
                    f"  Parameters: {{ {', '.join(param_details)} }}"
                )
            else:
                description_lines.append("  Parameters: None")

        # Используем '\n' для корректного переноса строк в финальном промпте
        return "\n".join(description_lines)

    def _get_task_template(self) -> str:
        """Возвращает шаблон задачи в формате Obsidian."""
        # Код шаблона взят из оригинального prompt_builder.py
        return """---
title: [Task Title]
allDay: true
date: [YYYY-MM-DD or leave empty]
completed: false
priority: [1-5 or leave empty]
status: [e.g., todo, waiting, in progress - default to todo if unsure]
type: single
depends_on: [] # Optional: Add links like - "[[Other Note Title]]" if mentioned
blocks: [] # Optional: Add links like - "[[Other Note Title]]" if mentioned
startTime: [HH:MM or leave empty]
endTime: [HH:MM or leave empty]
endDate: [YYYY-MM-DD or leave empty]
duration: [HH:MM or leave empty]
---

## 📝 Описание
[Detailed description of the task provided by the user]"""

    def _get_tool_call_example(self) -> str:
        """Возвращает пример JSON для вызова инструментов."""
        # Код примера взят из оригинального prompt_builder.py
        return """```json
[
  {
    "tool": "create_file",
    "data": {
      "file_path": "03 - Tasks/2025-04-25 Task A.md",
      "content": "---\\ntitle: Task A\\nallDay: true\\ndate: 2025-04-25\\ncompleted: false\\nstatus: todo\\ntype: single\\ndepends_on: []\\nblocks: []\\n---\\n\\n## 📝 Описание\\nDescription for Task A"
    }
  },
  {
    "tool": "create_file",
    "data": {
      "file_path": "03 - Tasks/2025-04-26 Task B.md",
      "content": "---\\ntitle: Task B\\nallDay: true\\ndate: 2025-04-26\\ncompleted: false\\nstatus: todo\\ntype: single\\ndepends_on: []\\nblocks: []\\n---\\n\\n## 📝 Описание\\nDescription for Task B"
    }
  },
  {
    "tool": "modify_file",
    "data": {
      "file_path": "03 - Tasks/2025-04-25 Task A.md",
      "content": "---\\ntitle: Task A\\nallDay: true\\ndate: 2025-04-25\\ncompleted: false\\nstatus: todo\\ntype: single\\ndepends_on: []\\nblocks: [\\\"[[2025-04-26 Task B]]\\\"]\\n---\\n\\n## 📝 Описание\\nDescription for Task A"
    }
  },
  {
    "tool": "modify_file",
    "data": {
      "file_path": "03 - Tasks/2025-04-26 Task B.md",
      "content": "---\\ntitle: Task B\\nallDay: true\\ndate: 2025-04-26\\ncompleted: false\\nstatus: todo\\ntype: single\\ndepends_on: [\\\"[[2025-04-25 Task A]]\\\"]\\nblocks: []\\n---\\n\\n## 📝 Описание\\nDescription for Task B"
    }
  },
  {
    "tool": "reply",
    "data": {
      "message": "✅ OK, I've created Task A and Task B and linked them."
    }
  }
]
```"""

    def _get_instructions(self) -> str:
        """Возвращает детальные инструкции для LLM."""
        # Код инструкций взят из оригинального prompt_builder.py
        # Убедитесь, что инструкции соответствуют текущим возможностям и именам инструментов.
        return """- Analyze the user's request carefully. Identify all distinct actions required (e.g., create multiple files, link them, reply).
- Determine the correct tool and parameters for each action based on the 'Available Tools' list.
- **Chain Commands:** Combine ALL necessary tool calls for a single user request into ONE JSON array response. If a user asks to create two tasks and link them, your response array MUST contain the `create_file` calls for both tasks AND the `modify_file` calls to link them, plus a final `reply` if appropriate. Do NOT perform only part of the request and wait for further instructions.
- **Important:** Ensure all strings within the JSON `data` object are properly escaped, especially quotes (`\\\"`) and newlines (`\\n`) within the `content` for file operations or `message` for replies.
- **File Naming Convention:** When creating task files requested by the user, always use the format `YYYY-MM-DD Task Name.md` for the file name, using the date the task is scheduled for. Example: `2025-04-25 Дизайн Макетов.md`. Use today's date if no date is specified.
- **Default Date:** If the date for a task is not specified by the user, always use today's date (provided above) as the default both in the filename and in the frontmatter's `date` field.
- **Task Content:** When using `create_file` for a task, ensure the `content` parameter includes both the YAML frontmatter (using the template provided) and the task description under the `## 📝 Описание` heading. Fill frontmatter fields based on user input, using defaults where appropriate (e.g., `status: todo`, `completed: false`). Leave fields like `priority`, `startTime`, `depends_on`, `blocks` empty if not specified.
- **Task Linking:** When a user requests linking (e.g., "task A depends on B", "B blocks A", "свяжи А и Б"), use the `modify_file` tool for **both** tasks within the *same response array* as the creation calls (if applicable):
    - For "A depends on B": In Task A's file content, add/append `depends_on: ["[[Task B]]"]` to the frontmatter. In Task B's file content, add/append `blocks: ["[[Task A]]"]` to the frontmatter.
    - Ensure you use the correct Obsidian link format `[["File Name"]]` without the `.md` extension within the YAML list. Modify the *entire* content string passed to `modify_file`.
- **Task Completion:** If the user asks to "выполни" or "complete" a task, use the `modify_file` tool. Provide the *entire new content* for the file, changing only the `completed: false` line to `completed: true` in the frontmatter.
- **Task Planning/Estimation:** When asked for planning or time estimation:
    - Analyze the task. Provide realistic time estimates in your `reply`.
    - If creating/modifying the task file, update the `startTime`, `endTime`, or `duration` fields in the frontmatter based on the estimate or user input (e.g., "это займет 2 часа").
    - Schedule tasks logically, avoiding overlap if possible, considering existing tasks (if context allows).
- **File Paths:** Always use relative paths for `file_path` and `folder_path` tool parameters (e.g., `03 - Tasks/My Task.md`, `01 - Projects/New Project`). Do not use absolute paths.
- **Daily Notes/Non-Task Content:** If the user provides general information, observations, or asks to "запиши", create or append to a daily note file.
    - Use the `create_file` or `modify_file` tool.
    - The filename should be `YYYY-MM-DD.md` (using today's date) inside the configured daily notes folder (e.g., `Journal/2025-04-25.md`).
    - Append new content under a timestamp heading (e.g., `## HH:MM`) if the file already exists.
- **Response Style:** Always use the 'reply' tool for your final response to the user. Respond in a friendly, engaging, and conversational tone. Use Markdown and emojis (✅, 📅, 🔗, 🤔, 👍) appropriately. Structure responses clearly, quoting the user's request if helpful, summarizing the action, and mentioning relevant context (like today's date). Use Markdown links for file references (e.g., `[Task A](03%20-%20Tasks/2025-04-25%20Task%20A.md)`) instead of wikilinks in the reply message.
- **Use `finish` Tool:** Only use the `finish` tool if the user explicitly indicates the end of the conversation (e.g., "спасибо, это все", "ok, done")."""

    def build_system_prompt(
        self, history: List[HistoryEntry], vault_context: Optional[str] = None
    ) -> str:
        """
        Строит основной системный промпт, объединяя инструкции,
        описания инструментов, примеры и опциональный контекст хранилища.
        """
        # Получаем компоненты промпта
        tool_descriptions = self._format_tool_descriptions()
        task_template = self._get_task_template()
        tool_example = self._get_tool_call_example()
        instructions = self._get_instructions()

        # Получаем текущую дату и время
        current_datetime_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Формируем строки промпта
        prompt_lines = [
            "You are an AI assistant designed to manage files within an Obsidian vault.",
            "Your primary functions are file and folder manipulation (create, delete, modify) based on user requests, including managing tasks and daily notes.",
            f"\nThe current date and time is: {current_datetime_str}",
        ]

        # Добавляем контекст хранилища, если он есть
        if vault_context:
            prompt_lines.append(
                "\nCurrent content of relevant files from the Obsidian vault is provided below. Refer to this content when needed."
            )
            prompt_lines.append("--- VAULT CONTEXT START ---")
            prompt_lines.append(vault_context)
            prompt_lines.append("--- VAULT CONTEXT END ---\n")
        else:
            prompt_lines.append(
                "\nNo specific vault file context provided for this request."
            )

        # Добавляем остальные части
        prompt_lines.extend(
            [
                "Available Tools:",
                tool_descriptions,
                "\nTask Creation Template:",
                "When asked to create a task, use the `create_file` tool with content formatted like this template:",
                task_template,
                "\nOutput Format for Tool Calls:",
                "Your response MUST be a JSON array containing one or more tool call objects. Each object must have 'tool' (string) and 'data' (object) keys.",
                "\nExample Of Tool Call Response:",
                tool_example,
                "\nInstructions:",
                instructions,
                # Можно добавить секцию с историей сюда, если не передавать ее отдельно
                # "\nConversation History:",
                # ... (форматирование истории) ...
                # "\nYour turn:",
            ]
        )

        # Собираем итоговый промпт
        system_prompt = "\n\n".join(
            prompt_lines
        )  # Используем двойной перенос для лучшей читаемости секций
        logger.debug(f"Built system prompt. Final Length: {len(system_prompt)}")
        # logger.debug(f"System Prompt: {system_prompt}") # Раскомментировать для полной отладки промпта
        return system_prompt
