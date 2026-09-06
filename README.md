# gmail-cli

gmail utlity for agents.

## Features

- **OAuth 2.0 Authentication**: Seamless browser login with automatic token refresh and cached credentials.
- **Search**: Query threads with Gmail's search syntax, pagination, and optional full message payloads (`--full` / `--include-messages`).
- **Cross-Thread Chronological Timeline (`gmail timeline`)**: Flattens messages across multiple threads matching a query into a single chronological sequence.
- **Batch Thread Fetching**: Read multiple threads at once by passing multiple IDs or piping them into `--stdin`.
- **Inline Attachment Text Extraction (`--extract-text` / `--extract-attachments`)**: Extract plain text directly from `.pdf`, `.docx`, `.txt`, `.csv`, and `.md` attachments without saving them to disk first.
