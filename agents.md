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
ollama pull phi4-mini:3.8b-q4_K_M

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
3. `extraction_validation_agent`
4. `route_after_validation` (Halt if identity data is missing/placeholder)
5. `evaluation_agent`
6. `decision_agent`
7. `report_agent` (Mocked)
8. `notification_agent` (Mocked)

Pipeline Visualization:
```
START → extract → [gate] → extraction_validate → [gate] → evaluate → decide → report → notify → END
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

### Extraction Validation Agent (`app/agents/extraction_validation_agent.py`)
- ✅ **Status:** Completed.
- Performs a strict data integrity audit on the `extracted_json`.
- **Functional Orchestration Pattern:** Moves tool-calling logic from the LLM to the system layer. The LLM decides *what* to notify, and Python ensures the notification is sent 100% of the time.
- **Logic Gate:** Rejects applications where `name` or `email` are `null`, empty, or contain generic placeholders (e.g., "user", "candidate").
- **Deterministic Notifications:** Automatically sends a professional email via **Resend** (with CV attachment and metadata) if validation fails.
- **Background Tasks:** Utilizes **FastAPI BackgroundTasks** for non-blocking email delivery.
- **Model:** `phi4-mini:3.8b` · temp `0.0` · locked JSON template
- **Owns state fields:** `is_valid`, `reason`

### Evaluation Agent (`app/agents/evaluation_agent.py`)
- ✅ **Status:** Completed.
- Scores extracted candidate data against a weighted rubric (loaded from state or the default rubric file on disk).
- **Deterministic Scoring:** Uses `score_against_rubric_tool` for per-criterion weighted scoring (0–100).
- **LLM Narrative:** Calls the evaluation model (`EVALUATION_MODEL`) to generate an `overall_summary`, `strengths`, and `gaps`; falls back to a fully deterministic text summary if the model is unavailable.
- **Threshold Handoff:** Reads `pass_threshold` and `review_threshold` from the rubric and forwards them to the Decision Agent via state.
- **Model:** `gemma3:1b-it-q4_K_M` (configurable) · temp `0.1` · top_p `0.2`
- **Owns state fields:** `evaluation_score`, `evaluation_reasoning`, `pass_threshold`, `review_threshold`

### Decision Agent (`app/agents/decision_agent.py`)
- ✅ **Status:** Completed.
- Receives `evaluation_score`, `evaluation_reasoning`, `pass_threshold`, and `review_threshold` from the Evaluation Agent through shared LangGraph state.
- Does not call an LLM or re-evaluate the candidate.
- Uses the custom `decision_rules_tool` from `app/tools/decision_rules.py`.
- Applies deterministic threshold rules:
  - `score >= pass_threshold` → `PASS`
  - `review_threshold <= score < pass_threshold` → `REVIEW`
  - `score < review_threshold` → `FAIL`
- Returns `decision`, `confidence`, and `decision_reason`.
- Owns state fields: `decision`, `confidence`, `decision_reason`.
- Tests: `tests/test_decision_agent.py`.

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
