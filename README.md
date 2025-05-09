# Obsidian Telegram Assistant

A Telegram bot powered by Gemini AI that integrates with Obsidian to help manage and interact with your knowledge base.

## Features

- Telegram bot interface for natural language interactions
- Gemini AI integration for intelligent responses
- Obsidian vault integration for knowledge management
- Recurring events and task scheduling system
- File watching to detect changes in your vault
- Docker-based deployment for easy setup

## How It Works

The main workflow of this assistant is designed to be seamless and intuitive:

1. **Message the Bot**: Send messages to your Telegram bot with tasks, notes, or questions.
2. **Automatic Markdown Creation**: The bot processes your messages and automatically creates or updates markdown files in your Obsidian vault.
3. **Cross-Device Sync**: When your Remotely Save plugin syncs data to other devices, your notes and tasks become available everywhere.
4. **Calendar Integration**: Use the Full Calendar plugin in Obsidian to view and manage tasks and events similar to Todoist, providing a visual timeline of your commitments.
5. **Task Management**: Tasks created via the bot appear in your Tasks plugin lists, allowing you to track and complete them within Obsidian.

This workflow creates a smooth bridge between quick capture via Telegram and organized knowledge management in Obsidian.

## How the AI Prompt System Works

The assistant uses a sophisticated prompt system to process your messages and interact with your Obsidian vault. The core of this system is in the `services/prompt_builder_service.py` file, which builds structured prompts for the Gemini AI model.

### Key Components of the Prompt System

1. **Tool Definitions**: The AI is given access to a set of tools for file operations (create, modify, delete files and folders)
2. **Task Template**: A standardized YAML frontmatter template for creating task files in Obsidian
3. **File Naming Conventions**: Tasks follow the `YYYY-MM-DD Task Name.md` format with proper frontmatter
4. **Intelligent Linking**: The system can establish relationships between tasks using Obsidian's linking system:
   - Task dependencies (`depends_on` and `blocks` relationships)
   - Project organization
   - Calendar integration

### Special Features

- **Task Management**: Create, update, complete and link tasks with natural language commands
- **Daily Notes**: Automatic creation and updating of daily notes
- **Date Handling**: Automatic date assignment based on conversation context
- **Context Awareness**: The system provides the AI with relevant files from your vault for context

When you send a message, the prompt builder constructs a comprehensive system prompt that includes all necessary instructions, templates, and context for the AI to understand and fulfill your request.

## Obsidian Compatibility

This assistant works with Obsidian and has been tested with the following community plugins:

- Remotely Save
- Dataview
- Full Calendar
- Homepage
- Periodic Notes
- Tasks Plugin

These plugins enhance the functionality of the assistant, but are not required for basic operation.

## Prerequisites

- Python 3.11+
- Google Gemini API key
- Telegram Bot Token
- Obsidian vault

## Installation

### Local Installation

1. Clone the repository
   ```bash
   git clone https://github.com/yourusername/obsidian-telegram-assistant.git
   cd obsidian-telegram-assistant
   ```

2. Create a virtual environment
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```

4. Copy the environment example file and configure it
   ```bash
   cp env.example .env
   ```
   Edit the `.env` file with your API keys and settings.

### Docker Installation

1. Clone the repository
   ```bash
   git clone https://github.com/yourusername/obsidian-telegram-assistant.git
   cd obsidian-telegram-assistant
   ```

2. Copy the environment example file and configure it
   ```bash
   cp env.example .env
   ```
   Edit the `.env` file with your API keys and settings.

3. Build and run with Docker Compose
   ```bash
   docker-compose up -d
   ```

## Configuration

All configuration is done through environment variables in the `.env` file:

- `GEMINI_API_KEY`: Your Google Gemini API key
- `GEMINI_MODEL_NAME`: Gemini model to use (default: gemini-2.0-flash)
- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token
- `TELEGRAM_USER_ID`: Your Telegram user ID for access control
- `OBSIDIAN_DAILY_NOTES_FOLDER`: Folder for daily notes in Obsidian
- `OBSIDIAN_VAULT_PATH`: Path to your Obsidian vault

## Usage

After starting the bot:

1. Open a chat with your bot in Telegram
2. Send commands or natural language queries
3. The bot will interact with your Obsidian vault and provide AI-powered responses

## Project Structure

- `main.py`: Entry point and application orchestration
- `telegram_bot.py`: Telegram bot implementation
- `message_processor.py`: Processes messages and invokes the LLM
- `containers.py`: Dependency injection container configuration
- `services/`: Core services for application functionality
- `tools/`: Utility tools for file operations and other tasks
- `recurring_events/`: Manages scheduled and recurring events

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. 