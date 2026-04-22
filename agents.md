# AgentHire — AGENTS.md

## Project Overview

**AgentHire** is a Multi-Agent Application Analysis System built with **FastAPI** + **LangGraph** + **LangChain**.
Accepts PDF, text, or JSON application files, runs them through a 5-agent pipeline,
and produces a structured decision (PASS / FAIL / REVIEW), two reports, and an email notification via **Resend**.
All LLMs run **locally via Ollama** — no paid LLM API keys.

---

## Tech Stack

- **Language:** Python 3.11+
- **Backend:** FastAPI + Uvicorn
- **Agent framework:** LangChain + LangGraph
- **LLM runtime:** Ollama (local)
- **Email:** Resend (`resend` Python SDK)
- **Database:** SQLite + aiosqlite
- **Package manager:** UV (`pip install uv`)
- **Testing:** pytest + Hypothesis

---

## Setup Commands

```bash
# Install dependencies
uv sync

# Pull required Ollama models (must have Ollama running locally)
ollama pull gemma3:1b-it-q4_K_M
ollama pull phi4-mini:3.8b-q4_K_M

# Build the custom extraction model from the Modelfile
ollama create agenthire-extractor -f models/extractor.Modelfile

# Copy and configure environment variables
cp .env.example .env
# Required keys: LANGCHAIN_API_KEY, RESEND_API_KEY, RESEND_FROM_ADDRESS

# Initialise the SQLite database
python scripts/init_db.py

# Start the API server
uvicorn app.main:app --reload --port 8000
```

---

## Repository Structure

```
app/
  main.py                        # FastAPI entrypoint
  state.py                       # ApplicationState TypedDict (shared graph state)
  graph/
    workflow.py                  # LangGraph StateGraph definition and compilation
  agents/
    extraction_agent.py          # Agent 1 — parses uploaded files
    evaluation_agent.py          # Agent 2 — scores against rubric
    decision_agent.py            # Agent 3 — classifies PASS / FAIL / REVIEW
    report_agent.py              # Agent 4 — generates applicant + internal reports
    notification_agent.py        # Agent 5 — sends decision email via Resend
  tools/
    parse_pdf.py                 # parse_pdf_tool
    score_rubric.py              # score_against_rubric_tool
    decision_rules.py            # apply_decision_rules_tool
    send_email.py                # send_email_tool (Resend)
  routers/                       # FastAPI route modules
  database.py                    # SQLite helpers
  observability.py               # @traced decorator for audit logging
tests/
  test_extraction_agent.py
  test_evaluation_agent.py
  test_decision_agent.py
  test_notification_agent.py
scripts/
  init_db.py
```

---

## Workflow Order

1. `extraction_agent`
2. `evaluation_agent`
3. `decision_agent`
4. `report_agent`
5. `notification_agent`

Pipeline is linear with no conditional branches:

```
extract → evaluate → decide → report → notify → END
```

Agent orchestration is defined in `app/graph/workflow.py`.

---

## Agent Responsibilities

### Extraction Agent (`app/agents/extraction_agent.py`)
- Extracts applicant fields (name, email, phone, skills, experience, education) from uploaded files.
- Supports PDF (via PyMuPDF), plain text, and JSON inputs.
- Enforces output against a fixed JSON schema; retries once on validation failure.
- Persists extracted data to the application record.
- **Model:** `agenthire-extractor` (custom Ollama model built from `models/extractor.Modelfile`) · temp `0.0` · format `json`
- **Owns state fields:** `extracted_json`

### Evaluation Agent (`app/agents/evaluation_agent.py`)
- Loads rubric data from `rubric.json` or a caller-supplied override.
- Scores extracted applicant data against weighted rubric criteria (weights must sum to 1.0 ± 0.01).
- Stores numeric score (0–100) and per-criterion reasoning.
- **Model:** `gemma3:1b-it-q4_K_M` · temp `0.1` · format `json`
- **Owns state fields:** `evaluation_score`, `evaluation_reasoning`

### Decision Agent (`app/agents/decision_agent.py`)
- Applies pass/review thresholds to produce `PASS`, `REVIEW`, or `FAIL`.
- Classification is **deterministic Python** — LLM only generates the human-readable reason string.
- Default thresholds: PASS ≥ 75, REVIEW ≥ 60, FAIL < 60. Configurable via rubric.
- Stores decision, confidence (0.0–1.0), and reason.
- **Model:** `phi4-mini:3.8b-q4_K_M` · temp `0.0` · format `json`
- **Owns state fields:** `decision`, `confidence`, `decision_reason`

### Report Agent (`app/agents/report_agent.py`)
- Generates two reports from the full pipeline state:
  - **Applicant report** — warm, professional summary; no raw scores; no internal rubric names.
  - **Internal report** — structured Markdown with full scores, criteria, and recommended actions.
- Persists report content to state and to disk under `reports/`.
- **Model:** `gemma3:1b-it-q4_K_M` · temp `0.3`
- **Owns state fields:** `report_applicant`, `report_internal`

### Notification Agent (`app/agents/notification_agent.py`)
- Composes decision email content from Jinja2 templates (`templates/email_pass.txt`, `email_fail.txt`, `email_review.txt`).
- Sends email via the **Resend** API using `send_email_tool`.
- Persists `notification_status` (`sent` / `failed`) to the application record.
- Records errors for missing or invalid recipient addresses without halting the pipeline.
- **Model:** `smollm:360m` · temp `0.2` (subject line personalisation only; body is always template-driven)
- **Owns state fields:** `notification_status`

---

## Shared Behavior

- All agents append audit log entries through the `@traced` decorator in `app/observability.py`.
- Agent orchestration is defined in `app/graph/workflow.py`.
- Each agent receives the full `ApplicationState` and returns **only the fields it owns** — never mutate another agent's fields.
- `errors` and `audit_log` are append-only (`operator.add`) — agents push entries, never overwrite.

---

## Email — Resend

Email is sent via the [Resend](https://resend.com) Python SDK. Set the following in `.env`:

```bash
RESEND_API_KEY=re_...
RESEND_FROM_ADDRESS=noreply@yourdomain.com
```

The `send_email_tool` in `app/tools/send_email.py` calls `resend.Emails.send()` directly.
Body content is always Jinja2 template-rendered — never LLM-generated — to guarantee safe, consistent messaging.
On API failure the tool returns `status: "failed"` without raising, so the pipeline always completes.

```python
import resend
resend.api_key = os.environ["RESEND_API_KEY"]

resend.Emails.send({
    "from": os.environ["RESEND_FROM_ADDRESS"],
    "to": [to_address],
    "subject": subject,
    "text": body,
})
```

---

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run a single agent's tests
pytest tests/test_extraction_agent.py -v

# Run property-based tests with a fixed seed
pytest tests/test_decision_agent.py --hypothesis-seed=0 -v

# Run with coverage
pytest tests/ --cov=app --cov-report=term-missing
```

All tests must pass before committing. Never merge with a failing suite.

Mock the Resend client in notification tests — do not send live emails in CI:

```python
from unittest.mock import patch

@patch("resend.Emails.send")
def test_sends_email_on_pass(mock_send):
    mock_send.return_value = {"id": "mock-id-123"}
    ...
```

---

## Code Style

- Python 3.11+ type hints on all function signatures — avoid bare `Any`
- Google-style docstrings on all public functions and tools (Args / Returns / Raises / Example)
- Black formatting, line length 88
- All LangChain tools use the `@tool` decorator with strict type hints
- No `print()` statements — use `@traced` from `app/observability.py`
- Secrets via `python-dotenv` only; never hardcode credentials

---

## Tool Development Rules

Every custom tool must have:

1. `@tool` decorator from `langchain.tools`
2. Full type hints on all parameters and return value
3. Google-style docstring with Args, Returns, Raises, and Example sections
4. Typed exception handling (`ValueError`, `FileNotFoundError`, etc.)
5. No side effects outside its stated purpose

---

## Testing Requirements

Each student must contribute tests for their own agent. Minimum 4 test functions per agent, covering at least one edge case and one failure path.

- **Extraction:** LLM-as-a-Judge quality score + schema key validation + missing-field null assertion
- **Evaluation:** Score range check + rubric weight mismatch error + idempotency test
- **Decision:** Hypothesis property-based tests for all three branches + boundary values + invalid input error
- **Report/Notification:** Resend mock test + PII-not-in-logs assertion + template-per-decision-type check

---

## State Management Rules

- `ApplicationState` in `app/state.py` is the single source of truth — do not pass data outside of it
- `errors: Annotated[List[str], operator.add]` — append only, never clear
- `audit_log: Annotated[List[dict], operator.add]` — one entry per agent invocation
- LangGraph `SqliteSaver` checkpoints state to `data/checkpoints.db` — do not delete mid-run

---

## LLMOps / Observability

- `LANGCHAIN_TRACING_V2=true` in `.env` enables LangSmith tracing (free tier)
- Every agent node uses `@traced("agent_name")` from `app/observability.py`
- `audit_log` SQLite table records agent name, tool called, truncated input/output, and latency (ms)
- Mask PII in all log entries — replace email local parts with `****`

---

## API Endpoints

| Method | Path | Trigger |
|---|---|---|
| POST | `/applications/upload` | Extraction Agent |
| POST | `/applications/process` | Full pipeline (async) |
| GET | `/applications/{id}/status` | Poll pipeline state |

---

## Security & Constraints

- **No paid LLM APIs.** Ollama local models only. OpenAI, Anthropic, and Gemini keys are prohibited.
- **No secrets in code.** All credentials via `.env`. `.env` is gitignored.
- File uploads validated for type (PDF / txt / JSON) and size (max 10 MB).
- `RESEND_API_KEY` read from environment only — never logged or included in state.

---

## PR / Commit Guidelines

- Branch naming: `feature/<agent-name>` or `fix/<short-description>`
- Commit messages: `<type>(<scope>): <summary>` — e.g. `feat(notification): switch to Resend SDK`
- Run `pytest tests/ -v` and `black app/ tests/` before every commit
- Each PR must reference which agent/tool it implements and include the corresponding test file
