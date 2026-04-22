# AgentHire - Multi-Agent Application Analysis System

AgentHire is a local-first recruitment pipeline built with **FastAPI**, **LangGraph**, and **SQLite**.
It accepts an applicant file, runs a multi-agent evaluation workflow in the background, stores state and
audit logs, and generates internal/applicant reports.

## What it does

- Upload and process application files (`.pdf`, `.txt`, `.md`, `.json`)
- Run a multi-agent workflow to evaluate candidates.
- Persist results in SQLite (`applications`, `audit_log`)
- Expose status and audit logs through HTTP endpoints

---

## Current Agent Implementation Status

The workflow involves a series of specialized LLM agents. Here is the current progress of their implementation:

- ✅ **Extraction Agent**: **Completed**. Extracts raw unstructured text from candidate resumes/documents into a strictly typed JSON format using a customized LLM model.
- ✅ **Validation Agent**: **Completed**. Reviews the extracted JSON output to verify that critical fields (such as `name` and `email`) are present and not empty, routing the workflow accordingly.
- 🚧 **Evaluation Agent**: **Pending** (Currently Mocked). Evaluates the valid extracted candidate data against a scoring rubric.
- 🚧 **Decision Agent**: **Pending** (Currently Mocked). Makes a final `PASS`, `FAIL`, or `REVIEW` decision based on the evaluation score and parameters.
- 🚧 **Report Agent**: **Pending** (Currently Mocked). Generates structured Markdown reports for both internal HR use and the applicant.
- 🚧 **Notification Agent**: **Pending** (Currently Mocked). Simulates dispatching email updates to the applicant based on the system's decision.

---

## Technology Stack and Libraries

AgentHire is built with a modern, asynchronous, and local-first Python stack:

### Frameworks & Tools
- **FastAPI**: A high-performance async web framework used to expose the HTTP endpoints for file uploads, status polling, and health checks.
- **LangGraph**: A state-machine orchestration framework from LangChain used to define the sequential and conditional execution pipeline of the agents (the "Workflow").
- **LangChain (`langchain-ollama`)**: The standardized LLM integration layer, used specifically to connect the application code seamlessly to the local Ollama inference server.
- **SQLite**: A fast, embedded relational database used for persistence. It stores the `ApplicationState` between steps and maintains a detailed `audit_log` of every model call and latency.
- **PyMuPDF & PyMuPDF4LLM**: Advanced PDF parsing tools utilized by the extraction layer to convert complex PDF resumes into clean, LLM-readable Markdown text.
- **Pydantic**: A data validation library used to validate and enforce the strict JSON structures returned by the local models before the data moves to the next agent in the pipeline.
- **Ollama**: The local inference engine that serves the large language models. It ensures that candidate data remains entirely on-premises, preventing sensitive information leakage.

### Language Models Used
- **Extraction Model (`hf.co/nimendraai/NuExtract-tiny-Resume-Data-Extractor:Q4_K_M`)**: A fine-tuned, extremely lightweight model specifically trained to map unstructured resume text into rigid JSON schema templates. Used by the Extraction Agent.
- **Validation Model (`gemma3:1b-it-q4_K_M`)**: A lightweight instruct model by Google, optimized for fast and capable reasoning. Used by the Validation Agent to perform sanity checks and logic verification on the extracted JSON.

---

## Architecture (high level)

`Client -> FastAPI API -> LangGraph workflow -> Agent tools -> SQLite + Markdown reports + email`

Decision routing:

- `PASS` -> `report` -> `notify`
- `FAIL` -> `report` -> `notify`
- `REVIEW` -> `report` -> `notify`

---

## Prerequisites

- Python **3.11+**
- (Optional, for local model health checks) Ollama running on localhost
- (Optional, for real email delivery) Resend API key + verified sender

---

## Installation

```bash
cd /path/to/AgentHire
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .[dev]
```

---

## Configuration

Settings are loaded from environment variables and `.env` (if present).

| Variable | Default | Purpose |
|---|---|---|
| `DB_PATH` | `agenthire.db` | SQLite database file path |
| `UPLOADS_DIR` | `uploads` | Stored uploaded files directory |
| `REPORTS_DIR` | `reports` | Generated report files directory |
| `MAX_UPLOAD_SIZE_BYTES` | `10485760` | Max upload size (10 MB) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama base URL |
| `EXTRACTION_MODEL` | `hf.co/nimendraai/NuExtract-tiny-Resume-Data-Extractor:Q4_K_M` | Extraction model label |
| `VALIDATION_MODEL` | `gemma3:1b-it-q4_K_M` | Validation model label |
| `RESEND_API_KEY` | empty | Resend API key (optional) |
| `RESEND_FROM_EMAIL` | `noreply@example.com` | Sender email |
| `RETRY_ATTEMPTS` | `2` | Retries per workflow node |
| `LANGCHAIN_TRACING_V2` | `false` | LangChain tracing toggle |
| `LANGCHAIN_API_KEY` | empty | LangChain API key |
| `LANGCHAIN_PROJECT` | `ctse-assignment2` | LangChain project name |

Example:

```bash
export RESEND_API_KEY="re_xxx"
export RESEND_FROM_EMAIL="you@your-verified-domain.com"
export OLLAMA_BASE_URL="http://localhost:11434"
```

---

## Run the API

```bash
uvicorn app.main:app --reload
```

Base URL: `http://127.0.0.1:8000`

Interactive docs:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

---

## API guide

### 1) Health check

```bash
curl -s http://127.0.0.1:8000/health
```

Returns:

- `api`: API availability
- `db`: SQLite connectivity
- `ollama`: local Ollama reachability

### 2) Upload only (no processing)

```bash
curl -s -X POST "http://127.0.0.1:8000/applications/upload" \
  -F "file=@/absolute/path/application.txt"
```

Response includes:

- `application_id`
- `status` (`uploaded`)

### 3) Upload + process (background workflow)

Without rubric:

```bash
curl -s -X POST "http://127.0.0.1:8000/applications/process" \
  -F "file=@/absolute/path/application.txt"
```

With rubric JSON:

```bash
curl -s -X POST "http://127.0.0.1:8000/applications/process" \
  -F "file=@/absolute/path/application.txt" \
  -F "rubric=@/absolute/path/rubric.json;type=application/json"
```

Response includes:

- `application_id`
- `status` (`processing`)

Rubric shape:

```json
{
  "criteria": [
    { "name": "Technical Skills", "weight": 0.4, "description": "..." },
    { "name": "Experience", "weight": 0.3, "description": "..." },
    { "name": "Communication", "weight": 0.2, "description": "..." },
    { "name": "Education", "weight": 0.1, "description": "..." }
  ],
  "pass_threshold": 65,
  "review_threshold": 60
}
```

Rules:

- `criteria` must not be empty
- weights must sum to between `0.99` and `1.01`
- `pass_threshold >= review_threshold`

### 4) Check processing status

```bash
curl -s "http://127.0.0.1:8000/applications/<application_id>/status"
```

Returns fields such as:

- `evaluation_score`
- `evaluation_reasoning`
- `decision` (`PASS`, `FAIL`, `REVIEW`)
- `confidence`
- `notification_status`
- `errors`

### 5) Read audit logs

```bash
curl -s "http://127.0.0.1:8000/applications/<application_id>/logs"
```

Returns ordered per-agent/tool execution logs including:

- `agent_name`, `tool_name`
- `input_summary`, `output_summary`
- `latency_ms`, `created_at`

---

## File inputs and outputs

### Accepted input file types

- `.pdf`
- `.txt`
- `.md`
- `.json`

### Generated artifacts

- Database: `DB_PATH` (default `agenthire.db`)
- Uploaded files: `UPLOADS_DIR` (default `uploads/`)
- Reports: `REPORTS_DIR` (default `reports/`)
  - `<application_id>_applicant.md`
  - `<application_id>_internal.md`

---

## Local model setup (Ollama)

If you want model-related health checks to return `ok`, pull and run the configured models:

```bash
ollama pull hf.co/nimendraai/NuExtract-tiny-Resume-Data-Extractor:Q4_K_M
ollama pull gemma3:1b-it-q4_K_M
```

---

## Development

Run quality checks:

```bash
python -m ruff check .
python -m mypy app
python -m pytest -q
```

---

## Troubleshooting

- `/health` returns `ollama=down`:
  - Ensure Ollama is running locally and `OLLAMA_BASE_URL` is valid.
- Notifications are `queued`:
  - `RESEND_API_KEY` is unset (expected fallback behavior).
- `Unsupported file type`:
  - Only `.pdf`, `.txt`, `.md`, `.json` are accepted.
- `File too large` or `Rubric file too large`:
  - Increase `MAX_UPLOAD_SIZE_BYTES` or upload smaller files.
- Invalid rubric JSON:
  - Ensure the uploaded rubric is valid JSON with the required schema.
