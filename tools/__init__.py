"""
Tool package for interacting with the filesystem and providing responses.
"""

# Import tool functions
from .reply import reply
from .create_file import create_file
from .delete_file import delete_file
from .create_folder import create_folder
from .delete_folder import delete_folder
from .finish import finish
from .modify_file import modify_file

# Define the tools dictionary
tools = {
    "reply": reply,
    "create_file": create_file,
    "delete_file": delete_file,
    "create_folder": create_folder,
    "delete_folder": delete_folder,
    "finish": finish,
    "modify_file": modify_file,
}


# Function to get the tool definitions in a serializable dictionary format
def get_tool_definitions() -> list[dict]:
    """
    Returns the schema/definitions for the available tools as a list of dictionaries.
    Each dictionary contains 'name', 'description', 'parameters', and 'required' keys,
    suitable for serialization or direct use by LLMs expecting this format.
    """
    # Define the structure directly as a list of dictionaries
    tool_defs = [
        {
            "name": "reply",
            "description": "Send a final message response to the user.",
            "parameters": {
                "message": "The message to send."
                # Type: STRING (implied by serialization context)
            },
            "required": ["message"],
        },
        {
            "name": "create_file",
            "description": "Create a new file with specified content.",
            "parameters": {
                "file_path": "The full path where the file should be created.",  # Type: STRING
                "content": "The content to write into the new file.",  # Type: STRING
            },
            "required": ["file_path", "content"],
        },
        {
            "name": "delete_file",
            "description": "Delete a specified file.",
            "parameters": {
                "file_path": "The full path of the file to delete.",  # Type: STRING
            },
            "required": ["file_path"],
        },
        {
            "name": "create_folder",
            "description": "Create a new folder (directory).",
            "parameters": {
                "folder_path": "The full path where the folder should be created.",  # Type: STRING
            },
            "required": ["folder_path"],
        },
        {
            "name": "delete_folder",
            "description": "Delete a specified folder (directory).",
            "parameters": {
                "folder_path": "The full path of the folder to delete.",  # Type: STRING
            },
            "required": ["folder_path"],
        },
        {
            "name": "modify_file",
            "description": "Overwrite an existing file with new content. The 'modification_description' should contain the *full* desired content, including any YAML frontmatter.",  # Updated description
            "parameters": {
                "file_path": "The full path of the file to modify.",  # Type: STRING
                "content": "The full content to write into the file, overwriting the existing content.",  # Updated parameter description
            },
            "required": ["file_path", "content"],
        },
        {
            "name": "finish",
            "description": "Indicate that the conversation is complete and no further action is needed.",
            "parameters": {},  # No parameters
            "required": [],  # No required parameters
        },
    ]
    return tool_defs


__all__ = [
    "reply",
    "create_file",
    "delete_file",
    "create_folder",
    "delete_folder",
    "modify_file",
    "finish",
    "tools",
    "get_tool_definitions",
]
