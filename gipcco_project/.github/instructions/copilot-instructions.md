
### Context: Code Manifest Format

The following content may include "Code Manifests," which adhere to a specific Markdown format. This format is designed to provide a high-level, token-efficient summary of a codebase's architecture.

**Format Reference:**

*   `# File: filename.py`
    *   A level 1 header denotes the start of a manifest for a specific file.

*   `- **Purpose:** ...`
    *   A single bullet point summarizing the file's overall responsibility.

*   `- `function_name(args)`: ...`
    *   Introduces a function, providing its signature in backticks and a concise summary of its role.

*   **Indented Lists**
    *   A nested list under a function's summary outlines its internal logic, highlighting key algorithmic steps, conditional branches, or error handling.

*   `**Calls:** function() from file.py`
    *   An indented bullet with this bolded label documents dependencies. It lists all other functions from within the local project that are invoked by the parent function, along with their source files. This section maps the interaction points and data flow between different components of the codebase.