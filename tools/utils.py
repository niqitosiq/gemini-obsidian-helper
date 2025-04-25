import logging

logger = logging.getLogger(__name__)


def finish(**kwargs) -> dict:
    """
    Placeholder function for the 'finish' tool.
    Actual logic might be handled elsewhere (e.g., message_processor),
    but this allows the import to succeed.
    """
    logger.info("Executing 'finish' tool function (placeholder).")
    # The message_processor handles the actual history clearing.
    # This function primarily exists to satisfy the container's import.
    return {"status": "finished", "message": "Conversation ended."}


def get_tool_definitions() -> list:
    """
    Returns a list of tool definitions for the LLM prompt.
    (Basic placeholder implementation)
    """
    # TODO: Ideally, load these from the actual tool handlers or a central registry.
    #       This is a simplified version based on the prompt builder usage.
    logger.debug("Getting tool definitions (placeholder)...")
    return [
        {
            "name": "create_file",
            "description": "Creates a new file with the specified content. Overwrites if the file exists.",
            "parameters": {
                "file_path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["file_path", "content"],
        },
        {
            "name": "delete_file",
            "description": "Deletes the specified file.",
            "parameters": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        },
        {
            "name": "modify_file",
            "description": "Modifies an existing file by replacing its content entirely.",
            "parameters": {
                "file_path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["file_path", "content"],
        },
        {
            "name": "create_folder",
            "description": "Creates a new folder (including parent directories if needed).",
            "parameters": {"folder_path": {"type": "string"}},
            "required": ["folder_path"],
        },
        {
            "name": "delete_folder",
            "description": "Deletes the specified folder and its contents recursively.",
            "parameters": {"folder_path": {"type": "string"}},
            "required": ["folder_path"],
        },
        {
            "name": "reply",
            "description": "Sends a text message back to the user.",
            "parameters": {"message": {"type": "string"}},
            "required": ["message"],
        },
        {
            "name": "finish",
            "description": "Ends the current conversation and clears the history.",
            "parameters": {},
            "required": [],
        },
        # Add other tools if necessary
    ]
