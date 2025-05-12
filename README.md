# Productive LLM - NestJS Application

This is a TypeScript-based NestJS application that implements the functionality of the original Python project using Domain-Driven Design (DDD) and Command Query Responsibility Segregation (CQRS) principles.

## Project Structure

The project follows a modular architecture with DDD principles:

```
/
├── src/
│   ├── modules/                     # Feature modules
│   │   ├── telegram/                # Telegram bot functionality
│   │   ├── llm/                     # LLM service integration
│   │   ├── vault/                   # Vault file management
│   │   ├── recurring-events/        # Recurring events engine
│   │   └── tools/                   # Tool handlers
│   │
│   ├── shared/                      # Shared code across modules
│   │   ├── domain/                  # Shared domain models
│   │   ├── infrastructure/          # Shared infrastructure
│   │   └── utils/                   # Utility functions
│   │
│   ├── core/                        # Core application code
│   │   ├── cqrs/                    # CQRS implementation
│   │   ├── ddd/                     # DDD base classes
│   │   └── exceptions/              # Exception handling
│   │
│   └── main.ts                      # Application entry point
│
└── test/                            # Tests
```

Each module follows this structure:

```
/module/
├── domain/                # Domain models and entities
│   ├── entities/
│   └── interfaces/
├── application/           # Application services, commands, queries
│   ├── commands/
│   ├── queries/
│   └── services/
├── infrastructure/        # Infrastructure implementations
│   ├── services/
│   ├── adapters/
│   └── repositories/
└── interface/             # Controllers, DTOs, presenters
    ├── controllers/
    ├── dtos/
    └── handlers/
```

## Features

- **Telegram Bot Integration**: Handles messages and commands from Telegram users
- **LLM Integration**: Connects to Google's Gemini API for AI-powered responses
- **Vault Management**: Manages files in an Obsidian-like vault structure
- **Recurring Events**: Schedules and executes recurring tasks and reminders
- **Tool Handlers**: Processes tool calls from the LLM for file operations and other actions

## Installation

1. Clone the repository
2. Install dependencies:
   ```
   npm install
   ```
3. Copy the environment example file and configure it:
   ```
   cp env.example .env
   ```
4. Edit the `.env` file with your API keys and configuration

## Running the Application

Development mode:
```
npm run start:dev
```

Production mode:
```
npm run build
npm run start:prod
```

## Testing

```
npm run test
```

## Architecture Decisions

- **Domain-Driven Design**: The application is structured around business domains with clear boundaries
- **CQRS Pattern**: Commands and queries are separated for better scalability and maintainability
- **Dependency Injection**: NestJS's DI system is used for loose coupling between components
- **Adapter Pattern**: External services are wrapped in adapters for better testability and flexibility

## Contributing

Please read the CONTRIBUTING.md file for details on the contribution process. 