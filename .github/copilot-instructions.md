## 1. Core Principles & Thinking Process (How to "Think" for this Project)

Before generating any code, consider these fundamental principles:

1.  **Understand the Goal:** What specific problem is this code trying to solve? What are the _exact_ requirements mentioned by the user? Ensure the generated code directly addresses the immediate task.
2.  **Adhere Strictly to the Request:** Implement _only_ what the user explicitly asks for. **Do not add unrequested features, functionality, optimizations, or significant architectural changes.** Focus solely on fulfilling the current, specific request. If you identify potential improvements or related necessities (like error handling, validation, logging) not explicitly mentioned, you should point these out or ask the user if they should be included, rather than implementing them preemptively. Your primary goal is to fulfill the stated request accurately.
3.  **Prioritize Clarification over Assumption:** If requirements, context, implementation details, variable names, desired logic, or anything else is unclear or ambiguous based _on the user's request and the surrounding code_, explicitly state the ambiguity and _ask the user for clarification_. Do not invent complex logic, make assumptions about missing details, or guess the intended behavior. It's better to ask than to generate potentially incorrect or unwanted code.
4.  **Context is King:**
    - **Analyze Surroundings:** Look closely at the existing code in the current file and related modules. What patterns, variable names, and functions are already in use?
    - **Fit In:** Strive to make the new code blend seamlessly with the existing codebase. Avoid introducing radically different styles or patterns without a very strong reason. Use existing helper functions, constants, and classes where applicable.
5.  **Simplicity & Clarity (KISS - Keep It Simple, Stupid):**
    - **Prefer Simplicity:** Opt for the most straightforward solution _that fulfills the request_. Avoid unnecessary complexity, clever tricks, or premature optimization.
    - **Readability:** Write code that is easy for _other humans_ to read and understand quickly. Ask yourself: "Would a new team member understand this?"
6.  **Maintainability:**
    - **Future-Proofing:** Write code that will be easy to debug, modify, and extend later. This involves clear naming, logical structure, and appropriate comments.
    - **Modularity:** Break down complex logic into smaller, well-defined functions or methods with clear responsibilities (Single Responsibility Principle).
7.  **Robustness & Error Handling:**
    - **Anticipate Failures:** Consider edge cases, invalid inputs, and potential failures relevant _to the requested task_.
    - **Graceful Handling:** Implement appropriate error handling if it's standard practice for the type of code being generated or if implicitly required by the context (but prefer asking if unsure, see point #3). Don't let errors crash the application silently or unexpectedly. Provide meaningful error messages or logs.
8.  **Security First:**
    - **Assume Zero Trust:** Treat all external input as potentially malicious.
    - **Apply Defenses:** Consistently apply security best practices relevant _to the generated code_ (validate input, sanitize/encode output, use parameterized queries, check authorization, handle secrets securely).
9.  **Consistency:**
    - **Follow Precedent:** Strictly adhere to the project's established conventions for code style, naming, formatting, and architectural patterns. Consistency reduces cognitive load for the team.
    - **Use Established Tools:** Prefer using the project's standard libraries, frameworks, and utility functions over introducing new ones.
10. **Testability:**
    - **Design for Testing:** Write code in a way that makes unit testing easier (e.g., minimize side effects, use dependency injection).
    - **Consider Verification:** Ask yourself: "How would I write a test to verify this code works correctly?"
11. **Don't Repeat Yourself (DRY):**
    - **Reuse Code:** Leverage existing functions, constants, and components whenever possible. Avoid copy-pasting code blocks.

## 2. Applying Principles to Key Areas

These principles should guide suggestions in specific areas:

- **Code Style & Formatting:**
  - **Guideline:** Prioritize consistency above all. Strictly follow the project's linter ([e.g., ESLint, Flake8]) and formatter ([e.g., Prettier, Black]) configurations. Refer to [Link to Style Guide if available].
  - **Why:** Improves readability and collaboration, reduces trivial changes in reviews.
- **Libraries & Frameworks:**
  - **Guideline:** Prefer using the established project toolkit: [List 2-3 key frameworks/libraries, e.g., React, Django, SQLAlchemy, Axios]. Use their features idiomatically. Avoid adding new dependencies unless necessary and discussed.
  - **Why:** Maintains consistency, reduces bloat, leverages team knowledge.
- **Architecture & Structure:**
  - **Guideline:** Adhere to the project's architecture ([e.g., MVC, Layered Architecture, Modular]). Understand the purpose of different layers/modules (e.g., controllers handle HTTP, services contain business logic, repositories handle data access). Keep components focused.
  - **Why:** Ensures organization, scalability, and ease of navigation.
- **Error Handling & Logging:**
  - **Guideline:** Use the project's standard error types and logging mechanism ([e.g., `logger.error()`, specific exception classes]). Log meaningful context. Don't suppress important errors. Implement _as appropriate for the request_ and ask if unsure.
  - **Why:** Crucial for debugging, monitoring, and understanding application behavior.
- **Security Practices:**
  - **Guideline:** Always apply security checks relevant _to the code's context and the request_ (e.g., validate all API inputs, encode data before rendering in HTML, use ORM correctly to prevent SQLi). Refer to project security guidelines if they exist.
  - **Why:** Protects users, data, and the system integrity. This is non-negotiable.
- **Testing:**
  - **Guideline:** Generate code that is inherently testable. Where appropriate, suggest basic test structures using [Jest, pytest, JUnit, etc.]. Focus on pure functions and dependency injection.
  - **Why:** Ensures code correctness, prevents regressions, and facilitates refactoring.
- **Documentation & Comments:**
  - **Guideline:** Add comments to explain the _why_ behind complex or non-obvious code, not just _what_ it does. Follow project standards for docstrings ([e.g., JSDoc, Google Style Python Docstrings]).
  - **Why:** Improves long-term understanding and maintainability.

## 3. General Anti-Patterns to Avoid

Based on the principles above, generally avoid:

- Adding features or logic not explicitly requested by the user.
- Overly complex or obscure one-liners ("clever" code).
- Ignoring or duplicating existing project utilities/functions.
- Hardcoding configuration values, URLs, or sensitive data.
- Leaving large blocks of commented-out code.
- Introducing global state without clear justification.
- Deeply nested conditionals or loops where simpler structures exist.
- Making assumptions when requirements or context are unclear (Ask first!).
