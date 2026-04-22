# AgentHire — AGENTS.md

## Project Overview

**AgentHire** is a Multi-Agent Application Analysis System built with **FastAPI** + **LangGraph** + **LangChain**.
Accepts PDF, text, or JSON application files, runs them through a specialized agent pipeline,
and produces a structured decision (PASS / FAIL / REVIEW), two reports, and an email notification via **Resend**.
All LLMs run **locally via Ollama** — no paid LLM API keys.

---

## Tech Stack

- **Language:** Python 3.11+
- **Backend:** FastAPI + Uvicorn
- **Agent framework:** LangChain + LangGraph
- **LLM runtime:** Ollama (local)
- **Logging:** Loguru (structured & colorful)
- **OCR:** Pytesseract + Pillow
- **Email:** Resend (`resend` Python SDK)
- **Database:** SQLite
- **Package manager:** UV (`pip install uv`)

---

## Setup Commands

```bash
# Install dependencies
uv sync

# Pull required Ollama models (must have Ollama running locally)
ollama pull hf.co/nimendraai/NuExtract-tiny-Resume-Data-Extractor:Q4_K_M
ollama pull gemma3:1b-it-q4_K_M

# Copy and configure environment variables
cp .env.example .env

# Initialise the SQLite database
python scripts/init_db.py

# Start the API server
uvicorn app.main:app --reload
```

---

## Workflow Order

The workflow follows a sequential path with a conditional quality gate:

1. `extraction_agent`
2. `route_after_extraction` (Halt if extraction fails)
3. `validation_agent`
4. `route_after_validation` (Halt if identity data is missing/placeholder)
5. `evaluation_agent` (Mocked)
6. `decision_agent` (Mocked)
7. `report_agent` (Mocked)
8. `notification_agent` (Mocked)

Pipeline Visualization:
```
START → extract → [gate] → validate → [gate] → evaluate → decide → report → notify → END
```

---

## Agent Responsibilities

### Extraction Agent (`app/agents/extraction_agent.py`)
- ✅ **Status:** Completed.
- Extracts applicant fields (name, email, phone, skills, experience, education) using a multi-layered PDF suite.
- **Advanced PDF Suite:** Layout detection (2-column support), Regex cleaning, and Tesseract OCR fallback.
- **Data Normalization:** Automatically converts empty strings to `null` via Pydantic validators.
- **Model:** `NuExtract-tiny` · temp `0.0` · num_ctx `4096`
- **Owns state fields:** `extracted_json`

### Validation Agent (`app/agents/validation_agent.py`)
- ✅ **Status:** Completed.
- Performs a strict data integrity audit on the `extracted_json`.
- **Logic Gate:** Rejects applications where `name` or `email` are `null`, empty, or contain generic placeholders (e.g., "user", "candidate").
- **Reasoning:** Uses step-by-step logic to ensure deterministic quality checks.
- **Model:** `gemma3:1b` · temp `0.0` · num_predict `150`
- **Owns state fields:** `is_valid`, `validation_reason`

### Evaluation Agent (`app/agents/evaluation_agent.py`)
- 🚧 **Status:** Mocked.
- Scores extracted applicant data against weighted rubric criteria.
- Stores numeric score (0–100) and per-criterion reasoning.

### Decision Agent (`app/agents/decision_agent.py`)
- 🚧 **Status:** Mocked.
- Applies pass/review thresholds to produce `PASS`, `REVIEW`, or `FAIL`.

### Report Agent (`app/agents/report_agent.py`)
- 🚧 **Status:** Mocked.
- Generates structured Markdown reports for both internal use and the applicant.

### Notification Agent (`app/agents/notification_agent.py`)
- 🚧 **Status:** Mocked.
- Dispatches decision updates via the Resend API.

---

## Observability & Logging

- **Structured Logging:** Switched to `Loguru` for readable, color-coded console output.
- **Audit Logs:** Every agent node uses `@traced` to record inputs, outputs, and latency into SQLite.
- **Debug Mode:** `DEBUG_LOGS=true` enables full LLM prompt/response dumps for troubleshooting.
- **PII Masking:** Automatically masks email local parts in all logs.

---

## API Endpoints

| Method | Path | Trigger |
|---|---|---|
| POST | `/upload` | Receives file and starts background workflow |
| GET | `/{id}/status` | Returns full application state |
| GET | `/{id}/logs` | Returns per-agent execution audit log |

---

## Security & Constraints

- **Local-First:** All LLM inference happens on-premises via Ollama.
- **Safety Fallbacks:** Pipeline halts immediately if extraction or validation fails to prevent cascading errors.
- **Timeout Management:** Default timeout increased to 120s to handle complex PDFs on local hardware.
