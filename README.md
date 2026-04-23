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
- ✅ **Extraction Validation Agent**: **Completed**. Reviews the extracted JSON output to verify that critical fields (such as `name` and `email`) are present and valid. Uses a **Functional Orchestration Pattern** to deterministically send professional email alerts via **Resend** if validation fails.
- 🚧 **Evaluation Agent**: **Pending** (Currently Mocked). Evaluates the valid extracted candidate data against a scoring rubric.
- 🚧 **Decision Agent**: **Pending** (Currently Mocked). Makes a final `PASS`, `FAIL`, or `REVIEW` decision based on the evaluation score and parameters.
- 🚧 **Report Agent**: **Pending** (Currently Mocked). Generates structured Markdown reports for both internal HR use and the applicant.
- 🚧 **Notification Agent**: **Pending** (Currently Mocked). Simulates dispatching email updates to the applicant based on the system's decision.

---

## Technology Stack and Libraries

AgentHire is built with a modern, asynchronous, and local-first Python stack:

### Frameworks & Tools
- **FastAPI**: A high-performance async web framework used to expose the HTTP endpoints.
- **LangGraph**: A state-machine orchestration framework from LangChain used to define the sequential and conditional execution pipeline.
- **LangChain (`langchain-ollama`)**: The standardized LLM integration layer for local Ollama inference.
- **Loguru**: Used for structured, colorful, and highly readable application logging.
- **SQLite**: A fast, embedded relational database used for persistence.
- **PyMuPDF & PyMuPDF4LLM**: Advanced PDF parsing tools utilized for high-fidelity text extraction.
- **Pytesseract & Pillow**: OCR (Optical Character Recognition) engine used as a fallback for scanned or image-based PDFs.
- **Pydantic**: Data validation library used to enforce strict JSON structures and normalize input data (e.g., converting empty strings to `null`).
- **Ollama**: The local inference engine ensuring candidate data remains entirely on-premises.

### Language Models Used
- **Extraction Model (`hf.co/nimendraai/NuExtract-tiny-Resume-Data-Extractor:Q4_K_M`)**: A fine-tuned, extremely lightweight model specifically trained to map unstructured resume text into rigid JSON schema templates.
- **Validation Model (`phi4-mini:3.8b-q4_K_M`)**: A lightweight instruct model by Microsoft used for deterministic sanity checks and generating professional notification content.

---

## Architecture (high level)

`Client -> FastAPI API -> LangGraph workflow -> Agent tools -> SQLite + Markdown reports + email`

### Advanced PDF Processing Suite
The extraction layer uses a multi-layered approach to ensure high-quality LLM inputs:
1. **Spatial Layout Detection**: Detects two-column resumes and extracts text logically to prevent column bleed.
2. **Robust Cleaning Pipeline**: Regex-based normalization to remove table artifacts, fix OCR spacing, and standardize bullet points.
3. **OCR Fallback**: If no selectable text is found, the system renders the document and uses Tesseract OCR.
4. **Safety Fallbacks**: Automatically detects "garbled" text and falls back to raw extraction if sophisticated methods fail.

---

## Prerequisites

- Python **3.11+**
- **Ollama** running locally
- **Tesseract OCR** (Required for scanned PDF support):
  - Ubuntu: `sudo apt install tesseract-ocr`
  - macOS: `brew install tesseract`
- (Optional) Resend API key for real email delivery

---

## Installation

```bash
cd /path/to/AgentHire
python -m venv .venv
source .venv/bin/activate
# Use uv for faster dependency management if available:
# uv pip install -e .[dev]
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
| `EXTRACTION_MODEL` | `...NuExtract-tiny...` | Extraction model label |
| `VALIDATION_MODEL` | `phi4-mini:3.8b...` | Validation model label |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | Timeout for model requests |
| `OLLAMA_NUM_CTX` | `4096` | Context window size |
| `DEBUG_LOGS` | `false` | Enable verbose LLM input/output logs |
| `RESEND_API_KEY` | empty | Resend API key (optional) |
| `RESEND_FROM_EMAIL` | `delivered@resend.dev` | Verified sender email |
| `REVIEWER_EMAIL` | `your-mail@gmail.com` | Target for audit notifications |
| `RETRY_ATTEMPTS` | `2` | Retries per workflow node |

---

## Run the API

```bash
uvicorn app.main:app --reload
```

Interactive docs: `http://127.0.0.1:8000/docs`

---

## API guide

### 1) Health check
`curl -s http://127.0.0.1:8000/health`

### 2) Upload + process (background workflow)
```bash
curl -s -X POST "http://127.0.0.1:8000/applications/process" \
  -F "file=@/absolute/path/cv.pdf"
```

### 3) Check status & Audit logs
- Status: `curl -s "http://127.0.0.1:8000/applications/<id>/status"`
- Logs: `curl -s "http://127.0.0.1:8000/applications/<id>/logs"`

---

## Development

Run quality checks:
```bash
python -m ruff check .
python -m mypy app
python -m pytest -q
```
