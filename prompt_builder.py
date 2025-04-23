import logging
import json
from typing import List, Dict, Any
from google.genai import types
from tools import get_tool_definitions
import datetime

logger = logging.getLogger(__name__)


def _format_tool_descriptions(tool_defs: List[Dict[str, Any]]) -> str:
    """
    Formats the tool definitions into a readable string format for the prompt.

    Args:
        tool_defs: List of tool definition dictionaries

    Returns:
        Formatted string of tool descriptions with their parameters
    """
    description_lines = []
    for tool in tool_defs:
        # Format the main tool description line
        description_lines.append(f"- {tool['name']}: {tool['description']}")

        # Format the parameters line
        param_details = []
        required_params = tool.get("required", [])
        for key in tool["parameters"]:
            status = "required" if key in required_params else "optional"
            param_details.append(f"{key} ({status})")

        if param_details:
            description_lines.append(f"  Parameters: {{', '.join(param_details)}}")
        else:
            description_lines.append("  Parameters: None")

    return "\\\\n".join(description_lines)


def _get_task_template() -> str:
    """
    Returns the template for task creation in Obsidian format.
    """
    return """---
title: [Task Title]
allDay: false
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
---

## 📝 Описание
[Detailed description of the task provided by the user]"""


def _get_tool_call_example() -> str:
    """
    Returns an example of a tool call JSON response for creating and linking tasks.
    """
    return """```json
[
    {{
        "tool": "create_file",
        "data": {{
            "file_path": "03 - Tasks/Task A.md",
            "content": "---\\ntitle: Task A\\n...other frontmatter...\\ndepends_on: []\\nblocks: []\\n---\\n\\n## 📝 Описание\\nDescription for Task A"
        }}
    }},
    {{
        "tool": "create_file",
        "data": {{
            "file_path": "03 - Tasks/Task B.md",
            "content": "---\\ntitle: Task B\\n...other frontmatter...\\ndepends_on: []\\nblocks: []\\n---\\n\\n## 📝 Описание\\nDescription for Task B"
        }}
    }},
    {{
        "tool": "modify_file",
        "data": {{
            "file_path": "03 - Tasks/Task A.md",
            "modification": "Add `blocks: [\\\"[[Task B]]\\\"]` to the frontmatter."
        }}
    }},
    {{
        "tool": "modify_file",
        "data": {{
            "file_path": "03 - Tasks/Task B.md",
            "modification": "Add `depends_on: [\\\"[[Task A]]\\\"]` to the frontmatter."
        }}
    }},
    {{
        "tool": "reply",
        "data": {{
            "message": "OK, I've created Task A and Task B and linked them."
        }}
    }}
]
```"""


def _get_instructions() -> str:
    """
    Returns the detailed instructions for the AI assistant on how to handle user requests.
    """
    return """- Analyze the user's request carefully. Identify all distinct actions required (e.g., create multiple files, link them, reply).
- Determine the correct tool and parameters for each action.
- **Chain Commands:** Combine ALL necessary tool calls for a single user request into ONE JSON array response. If a user asks to create two tasks and link them, your response array MUST contain the `create_file` calls for both tasks AND the `modify_file` calls to link them, plus a final `reply` if appropriate. Do NOT perform only part of the request and wait for further instructions.
- **Important:** Ensure all strings within the JSON `data` object are properly escaped. Pay special attention to quotes (`\\\"`) within the `content` for file operations or `message` for replies.
- If creating a task, ensure the file content within the `data` object matches the specified task format. Use the user's input for title, description, date, etc. If details are missing, use sensible defaults or leave fields empty where appropriate (like `date`, `priority`, `startTime`).
- **Task Linking:** When a user requests linking (e.g., "сначала сделай А, потом Б", "свяжи А и Б"), use the `modify_file` tool for **both** tasks within the *same response array* as the creation calls:
    - In Task B's file, add `depends_on: ["[[Task A]]"]` to the frontmatter (or append to the existing list).
    - In Task A's file, add `blocks: ["[[Task B]]"]` to the frontmatter (or append to the existing list).
    - Ensure you use the correct Obsidian link format `[["File Name"]]` without the `.md` extension.
- **Task Completion:** If the user asks to "выполни" (complete/execute) a task, interpret this as a request to mark the task as completed. Use the `modify_file` tool to change the `completed: false` line to `completed: true` in the frontmatter of the relevant task note file.
- Always use relative paths for `file_path` and `folder_path` parameters within the vault context provided.
- Be precise and execute the requested file operations accurately via the tool calls.
- **Always respond in a friendly tone and use Markdown formatting for your replies** when using the 'reply' tool or providing direct text responses."""


def get_system_prompt(context: List[types.Content]) -> str:
    """
    Generates the system prompt for the LLM, emphasizing file management and task creation.
    Incorporates tool definitions directly into the prompt.

    Args:
        context: List of content objects from the conversation context

    Returns:
        Complete system prompt with all necessary instructions and examples
    """
    # Get tool definitions and format them
    tool_defs = get_tool_definitions()
    tool_descriptions = _format_tool_descriptions(tool_defs)

    # Get current date and time
    current_datetime_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build the system prompt by combining all components
    system_prompt = f"""You are an AI assistant designed to manage files within an Obsidian vault.
Your primary functions are file and folder manipulation (create, delete, modify) based on user requests.
You have access to the current content of files from the Obsidian vault, provided at the beginning of the context. Refer to this content when needed.

The current date and time is: {current_datetime_str}

Available Tools:
{tool_descriptions}

Task Creation:
You can also create new task notes in the vault. When asked to create a task, use the `create_file` tool. Format the file content exactly like this example, filling in the details based on the user's request:

{_get_task_template()}

Output Format for Tool Calls:
When you decide to use a tool, your response MUST be a JSON array containing one or more tool call objects. Each object must have two keys:
1.  `tool`: A string representing the exact name of the tool you want to call (e.g., "create_file", "reply", "finish").
2.  `data`: An object containing the parameters required by that specific tool (e.g., {{"file_path": "path/to/file.md", "content": "..."}}). 

Example Of The Response (Creating and Linking Two Tasks):
{_get_tool_call_example()}

Instructions:
{_get_instructions()}
"""
    logger.debug(f"Using system prompt: {system_prompt[:200]}...")
    return system_prompt
