# AgentHire: Multi-Agent Application Analysis System
## Technical Report

---

## 1. Problem Domain

Recruitment pipelines at scale suffer from two conflicting pressures: the need for consistency and the cost of human review time. Screening hundreds of applications by hand introduces subjectivity, delays, and bottlenecks before any human assessor has even evaluated a single CV.

**AgentHire** addresses this by automating the initial screening pipeline for job applications. The system accepts applicant documents (PDF, plain text, Markdown, or JSON), extracts structured candidate data, validates its integrity, scores it against a configurable rubric, and produces a final recommendation — `PASS`, `REVIEW`, or `FAIL` — together with human-readable reports and email notifications.

A central design constraint is **data sovereignty**: all language model inference runs on a local Ollama instance. No candidate data is transmitted to external LLM providers. This makes the system suitable for organisations with privacy or on-premises deployment requirements.

---

## 2. System Architecture

### 2.1 Technology Stack

| Layer | Technology |
|---|---|
| API / runtime | FastAPI + Uvicorn (Python 3.11+) |
| Agent orchestration | LangGraph (state-machine graph) |
| LLM integration | LangChain + `langchain-ollama` |
| Local LLM inference | Ollama |
| PDF parsing | PyMuPDF, PyMuPDF4LLM, Pytesseract + Pillow |
| Email delivery | Resend Python SDK |
| Persistence | SQLite (WAL mode, foreign keys) |
| Logging | Loguru (structured, colorful, PII-masked) |
| Data validation | Pydantic v2 |
| Package management | UV |

### 2.2 High-Level Architecture

```
Client
  │
  ▼
FastAPI HTTP layer  (POST /applications/process, GET /{id}/status, GET /{id}/logs)
  │  saves file + creates DB row
  ▼
BackgroundTask → LangGraph Workflow
  │
  ├── extraction_agent        → extracted_json
  ├── [gate: status == failed → END]
  ├── extraction_validation_agent → is_valid, validation_reason
  ├── [gate: status == FAILED → END + email alert]
  ├── evaluation_agent        → evaluation_score, evaluation_reasoning
  ├── decision_agent          → decision (PASS/FAIL/REVIEW), confidence
  ├── report_agent            → report_applicant, report_internal
  └── notification_agent      → notification_status
          │
          ▼
       SQLite (applications table + audit_log table)
```

Each agent node writes its own fields back to the shared `ApplicationState` TypedDict and persists intermediate status to SQLite, so the `/status` endpoint always reflects the latest processing stage even while the background task runs.

### 2.3 Multi-Agent Workflow Diagram

```
START
  │
  ▼
┌─────────────────────────┐
│     extraction_agent     │  extracts structured JSON from raw document
└──────────┬──────────────┘
           │  route_after_extraction
    ┌──────┴──────┐
    │ failed?     │
    ▼             ▼
   END    ┌──────────────────────────────┐
          │  extraction_validation_agent  │  audits name + email integrity
          └──────────┬───────────────────┘
                     │  route_after_validation
              ┌──────┴──────┐
              │ FAILED?     │
              ▼             ▼
             END    ┌────────────────┐
                    │ evaluation_agent│  scores against rubric (0–100)
                    └──────┬─────────┘
                           ▼
                    ┌────────────────┐
                    │  decision_agent │  PASS / REVIEW / FAIL
                    └──────┬─────────┘
                           ▼
                    ┌────────────────┐
                    │  report_agent  │  generates Markdown reports
                    └──────┬─────────┘
                           ▼
                    ┌────────────────────┐
                    │  notification_agent │  dispatches email outcome
                    └──────┬─────────────┘
                           ▼
                          END
```

---

## 3. Agent Design

### 3.1 Extraction Agent (`app/agents/extraction_agent.py`)

**Status:** ✅ Fully Implemented

**Purpose:** Convert raw, unstructured applicant documents into a strictly typed JSON object.

**System Prompt / Persona:**
The agent uses `EXTRACTION_PERSONA` (defined in `app/agents/personas.py`), a `PersonaSpec` dataclass that compiles a structured system section containing:
- *Role identity:* "You are the Extraction Agent. You convert raw applicant documents into structured JSON."
- *Scope boundaries:* Only extract facts; do not score, decide, report, or notify.
- *Hard constraints:* No hallucinated fields; use `null` for unknown scalars and `[]` for unknown lists.
- *Output contract:* One valid JSON object matching the extraction schema; no markdown fences or commentary.

The prompt is formatted with the NuExtract template convention:
```
<|input|>
### Template:
{ "name": null, "email": null, ... }
### Text:
<raw resume text>
<|output|>
```

**Reasoning Logic & Interaction Strategy:**
1. The file is read by a format-specific tool (`parse_pdf_tool`, `parse_text_tool`, or `parse_json_tool`).
2. A primary LLM call is made to `NuExtract-tiny` (temperature `0.0`, deterministic) with up to 32,000 characters of input.
3. The response is validated by `CandidateExtraction` (Pydantic model). Empty strings are converted to `null` automatically.
4. A **heuristic extraction** runs in parallel using regex patterns against the raw text.
5. A **completeness scoring function** compares both results and returns the higher-scoring one. The heuristic acts as a safety net for cases where the model produces an empty payload.
6. If both attempts fail, the agent retries once with the validation error appended to the prompt. If still invalid, the node returns `status: failed` and halts the pipeline.

**Constraints:**
- Max input: 32,000 characters (truncated to protect context window)
- Model temperature: `0.0` (fully deterministic)
- Retry limit: 2 attempts

---

### 3.2 Extraction Validation Agent (`app/agents/extraction_validation_agent.py`)

**Status:** ✅ Fully Implemented

**Purpose:** Audit the extracted JSON for identity integrity and trigger alert notifications if validation fails.

**System Prompt / Persona:**
Uses `EXTRACTION_VALIDATION_PERSONA`, which instructs the model to examine `name` and `email` specifically, check for null/empty/generic placeholder values, and if invalid, produce a professional email subject and HTML body.

**Reasoning Logic — Functional Orchestration Pattern:**
This agent implements a deliberate architectural pattern that separates LLM decision-making from action execution:

1. **Deterministic pre-check (Python):** Before calling the LLM, Python code independently checks whether `name` and `email` pass hard rules (non-null, non-empty, non-generic such as "user" or "candidate", valid email format). If both pass, validation is approved immediately — the model is never called. This prevents the model from falsely rejecting valid data.
2. **Model reasoning (LLM call):** Only invoked when the pre-check finds issues. The model receives the extracted JSON and a locked template, producing `is_valid`, `reason`, `email_subject`, and `email_body` as JSON.
3. **Deterministic action (Python):** If `is_valid` is `false`, Python unconditionally calls the `send_email_tool` with the CV attached as a base64-encoded file and metadata appended to the HTML body. The model cannot suppress this action.
4. **FastAPI BackgroundTasks:** If a `background_tasks` handle is present in the state, the email is queued non-blocking. Otherwise it executes synchronously.

**Constraints:**
- Temperature: `0.0` (locked for maximum determinism)
- Output template: locked JSON schema — model cannot deviate from the four expected fields
- Rejection triggers: `name` or `email` are `null`, empty, contain `@` (email in name field), are shorter than 3 characters, or match the generic value set `{user, candidate, unknown, n/a, na, none}`

---

### 3.3 Evaluation Agent (`app/agents/evaluation_agent.py`)

**Status:** ✅ Fully Implemented

**Purpose:** Score the validated candidate profile against a weighted rubric and generate a narrative reasoning summary.

**Interaction Strategy:**
1. The rubric is loaded either from the state (operator-provided override) or the default file (`rubrics/default_rubric.json`).
2. `score_against_rubric_tool` (LangChain `@tool`) performs fully **deterministic, rule-based scoring** across four weighted criteria: Technical Skills (40%), Experience (30%), Communication (20%), Education (10%). No LLM is used at this stage.
3. A secondary **narrative LLM call** to `gemma3:1b-it` generates a human-readable summary including `overall_summary`, `strengths`, and `gaps`.
4. If the narrative call fails or returns invalid JSON, a deterministic fallback constructs the reasoning text from the scoring breakdown directly.
5. The final score (0–100) and formatted reasoning text are stored in the state and persisted.

---

### 3.4 Decision Agent (`app/agents/decision_agent.py`)

**Status:** 🚧 Mocked (scaffold)

**Purpose:** Apply pass/review score thresholds to produce a final `PASS`, `REVIEW`, or `FAIL` decision with a confidence value. Currently returns a static `REVIEW` at confidence `0.7` as a pipeline scaffold.

---

### 3.5 Report Agent (`app/agents/report_agent.py`)

**Status:** 🚧 Mocked (scaffold)

**Purpose:** Generate two Markdown reports — one for the applicant summarising the outcome, one for internal HR containing the full scoring breakdown. Currently produces template strings.

---

### 3.6 Notification Agent (`app/agents/notification_agent.py`)

**Status:** 🚧 Mocked (scaffold)

**Purpose:** Send the applicant an email notification with the pipeline's decision. Currently sets `notification_status: sent` without dispatching a real email.

---

## 4. Custom Tools

All tools are LangChain `@tool`-decorated callables, making them composable in LCEL pipelines and traceable by LangChain's observability layer.

### 4.1 `parse_pdf_tool` (`app/tools/parse_pdf.py`)

Extracts clean text from PDF files through a multi-layered strategy:

| Layer | Mechanism |
|---|---|
| 1 | Two-column layout detection: counts text blocks on each side of the midpoint; if both halves have > 2 blocks, each column is extracted independently and concatenated |
| 2 | PyMuPDF4LLM Markdown extraction for single-column (preserves headings/bullets) |
| 3 | Scanned PDF detection: if < 100 characters of selectable text, Tesseract OCR is applied at 300 DPI |
| 4 | Garble detection: if > 30% non-ASCII characters or fewer than 3 consecutive alpha chars, falls back to raw text |
| 5 | Regex cleaning pipeline: removes table artifacts, normalises bullet points, fixes OCR spacing, collapses blank lines |

**Example usage:**
```python
from app.tools.parse_pdf import parse_pdf_tool
text = parse_pdf_tool.invoke({"path": "uploads/cv.pdf"})
```

### 4.2 `send_email_tool` (`app/tools/email_tool.py`)

Sends HTML email via the Resend Python SDK. Accepts optional file attachment (base64-encoded) and key/value metadata which is appended to the HTML body as a formatted list.

**Example usage:**
```python
from app.tools.email_tool import send_email_tool
result = send_email_tool.invoke({
    "to_email": "reviewer@company.com",
    "subject": "Validation Alert: Missing Name",
    "body": "<p>The extracted CV is missing a valid name.</p>",
    "attachment_path": "uploads/cv.pdf",
    "metadata": {"Application ID": "abc-123", "CV Filename": "cv.pdf"}
})
```
If `RESEND_API_KEY` is not configured, the tool logs a warning and returns early without error, making it safe to run in development environments.

### 4.3 `score_against_rubric_tool` (`app/tools/score_rubric.py`)

Deterministically scores a `CandidateExtraction` object against a validated `RubricPayload`. Each criterion is routed to a specialised scoring function by keyword matching on the criterion name and description:

- **Skills criteria** → `_score_skills`: counts unique skills; base 40 + 10 per skill, capped at 95
- **Experience criteria** → `_score_experience`: counts roles and estimates years; base 20 + role and duration bonuses
- **Education criteria** → `_score_education`: maps degree strings to academic ranks; base 20 + rank and entry bonuses
- **Communication criteria** → `_score_communication`: measures profile completeness fraction and contact point count
- **Generic criteria** → `_score_generic`: uses overall profile completeness

Weights are normalised to sum to 1.0 before applying, so custom rubrics with non-standard weight distributions are handled safely.

**Example usage:**
```python
from app.tools.score_rubric import score_against_rubric_tool
result = score_against_rubric_tool.invoke({
    "extracted_json": {"skills": ["Python", "FastAPI"], "experience": [...]},
    "rubric": {"criteria": [...], "pass_threshold": 75, "review_threshold": 60}
})
# → {"total_score": 72.4, "criterion_breakdown": [...], "pass_threshold": 75, ...}
```

### 4.4 `load_rubric_tool` (`app/tools/load_rubric.py`)

Reads and validates a rubric JSON file from disk, enforcing that criteria weights sum to approximately 1.0 (±0.01 tolerance). The default rubric at `rubrics/default_rubric.json` defines four criteria with weights 0.4 / 0.3 / 0.2 / 0.1.

### 4.5 `parse_text_tool` and `parse_json_tool` (`app/tools/parse_text.py`, `app/tools/parse_json.py`)

Read plain text/Markdown files and JSON structured documents respectively, normalising them to string form for the extraction pipeline.

---

## 5. State Management

### 5.1 Global State Structure

All agents share a single `ApplicationState` TypedDict defined in `app/state.py`:

```python
class ApplicationState(TypedDict, total=False):
    application_id: str          # UUID assigned at upload
    file_path: str               # Path to the uploaded file on disk
    background_tasks: BackgroundTasks | None  # FastAPI handle (not persisted)
    status: str                  # Pipeline stage marker
    rubric: dict[str, object]    # Optional operator rubric override
    extracted_json: dict[str, object]   # Owned by: extraction_agent
    is_valid: bool               # Owned by: extraction_validation_agent
    validation_reason: str       # Owned by: extraction_validation_agent
    evaluation_score: float      # Owned by: evaluation_agent
    evaluation_reasoning: str    # Owned by: evaluation_agent
    decision: Decision           # Owned by: decision_agent ("PASS"/"FAIL"/"REVIEW")
    confidence: float            # Owned by: decision_agent
    decision_reason: str         # Owned by: decision_agent
    report_applicant: str        # Owned by: report_agent
    report_internal: str         # Owned by: report_agent
    notification_status: str     # Owned by: notification_agent
    errors: Annotated[list[str], operator.add]           # Reducer: list append
    audit_log: Annotated[list[dict], operator.add]       # Reducer: list append
```

`total=False` means all fields are optional in the initial state; agents add their own fields as they execute.

### 5.2 Context Passing Between Agents

LangGraph passes the full `ApplicationState` dictionary to every agent node. Each node returns a **partial dictionary** containing only the fields it writes. LangGraph merges the return value into the running state using the field-level reducers:

- `errors` uses `operator.add` — each agent appends its errors without overwriting prior agents' errors.
- `audit_log` uses `operator.add` — execution telemetry accumulates across all nodes.
- All other fields use the default last-write-wins merge.

### 5.3 SQLite Persistence

In addition to in-memory state, every agent calls `update_application()` to persist its fields to SQLite immediately after execution. This ensures the REST status endpoint reflects real-time progress even for long-running pipelines. On workflow completion, `insert_audit_entries()` bulk-inserts the full audit log from the final state.

The database uses WAL journal mode for concurrent read access and enforces foreign key constraints between `applications` and `audit_log`.

### 5.4 Observability — `@traced` Decorator

Every agent function is wrapped with `@traced("agent_name")` from `app/observability.py`. This decorator:
- Records `input_summary`, `output_summary` (truncated to 300 characters), `latency_ms`, and `ok` status.
- Applies PII masking: email local parts are replaced with `****@domain` in all log entries.
- Appends the entry to `audit_log` in the returned state dict.

---

## 6. Evaluation Methodology and Testing

### 6.1 Test Suite Structure

Tests live in `tests/` and are organised by component:

| Test file | Coverage area |
|---|---|
| `test_extraction_agent.py` | Extraction success/failure, retries, heuristic fallback, extra fields, fenced JSON |
| `test_extraction_validation_tool_call.py` | Functional orchestration, email attachment, valid short-circuit |
| `test_evaluation_agent.py` | Rubric loading, scoring, model-backed reasoning, idempotency, missing state |
| `test_workflow.py` | Full end-to-end pipeline with monkeypatched LLM calls |
| `test_parse_pdf_tool.py` / `test_pdf.py` | PDF parser with OCR and column detection |
| `test_api.py` | FastAPI upload, status, and log endpoints |
| `test_ollama_llm.py` | Ollama integration and `extract_first_json` |

Run the full suite:
```bash
python -m pytest -q
```

### 6.2 Key Test Assertions — Extraction Agent

- **Happy path:** `result["status"] == "extracted"` and `result["extracted_json"]["name"] == "Jane Doe"`.
- **Retry on invalid JSON:** Mock returns invalid JSON on call 1, valid on call 2; assert `call_count == 2` and status is `"extracted"`.
- **Failure after retry:** Both calls return invalid JSON; assert `status == "failed"` and error message contains `"Extraction output failed validation"`.
- **Heuristic fallback:** Model returns empty payload; heuristic extracts name and email from labeled text correctly.
- **Unsupported format:** `.docx` path returns `status == "failed"` with `"Unsupported file type"` in errors.
- **Optional fields default to null:** Model omits `phone`; Pydantic validator returns `None` (not an absent key).

### 6.3 Key Test Assertions — Extraction Validation Agent

- **Valid identity short-circuits:** With `name="Jane Doe"` and a real email, `mock_gen_json` is **never called** (`mock_gen_json.called is False`).
- **Functional orchestration with attachment:** Mock model returns `is_valid: false`; assert `mock_resend_send.called` is `True`, attachment filename is `cv.pdf`, content is a base64 string, and metadata appears in the HTML body.

### 6.4 Key Test Assertions — Evaluation Agent

- **Rubric loads correctly:** Default rubric has 4 criteria, `pass_threshold == 75`, `review_threshold == 60`.
- **Weighted score in range:** `0.0 <= total_score <= 100.0` and all criteria have a `reasoning` key.
- **Invalid rubric rejected:** Weight sum > 1.0 raises `ValueError`.
- **Model-backed reasoning:** Agent returns `status == "evaluated"` and narrative text contains the model's `overall_summary`.
- **Fallback reasoning:** If model returns `"not-json"`, result still contains `"Overall summary:"` and `"Criterion breakdown:"`.
- **Idempotency:** Two calls with the same state return identical `evaluation_score` and `evaluation_reasoning`.
- **Missing state guard:** Calling without `extracted_json` results in `status == "failed"` with the expected error message.

### 6.5 End-to-End Workflow Test (`test_workflow.py`)

A single integration test monkeypatches all three LLM calls and the `update_application` persistence call, then invokes `workflow.invoke()`. Assertions:
- `result["status"] == "completed"`
- `result["decision"] == "REVIEW"`
- `result["notification_status"] == "sent"`
- `result["is_valid"] is True`
- `result["evaluation_score"] > 0.0`
- `len(result["audit_log"]) == 6` (one entry per agent node)

### 6.6 Performance and Reliability Notes

- **Local inference latency:** On consumer hardware, `NuExtract-tiny` at Q4_K_M quantisation processes a typical one-page CV in 3–8 seconds. `phi4-mini:3.8b` validation takes 2–5 seconds.
- **Timeout configuration:** Default `OLLAMA_TIMEOUT_SECONDS=120` accommodates complex multi-page PDFs on slower hardware.
- **Retry resilience:** The extraction agent retries once on JSON parse or Pydantic validation errors before falling back to heuristic extraction.
- **Pipeline halting:** Conditional edges after extraction and validation ensure malformed or unidentifiable applications never proceed to scoring, preventing nonsensical decisions from corrupting the audit log.
- **SQLite WAL mode:** Enables concurrent reads (status polling) during background processing without blocking writes.

---

## 7. GitHub Repository

**Repository URL:** [https://github.com/nmdra/AgentHire](https://github.com/nmdra/AgentHire)

The repository contains all source code, tests, default rubric, environment example, and setup scripts. All dependencies are managed by `uv` via `pyproject.toml`.

---

## 8. Individual Contributions

### Agent Developed: Extraction Validation Agent

The **Extraction Validation Agent** (`app/agents/extraction_validation_agent.py`) was developed as an individual contribution. This agent implements the **Functional Orchestration Pattern** — a deliberate architectural design that separates the LLM's reasoning responsibility from the Python system's action responsibility.

Key design decisions made during development:

- A Python-level **identity pre-check** (`_has_real_identity`) runs before any LLM call. If `name` and `email` both pass hard rules, the model is bypassed entirely. This prevents false positives from model hallucination.
- The model is restricted to populating a locked JSON template (`is_valid`, `reason`, `email_subject`, `email_body`) to minimise unparseable output.
- If `is_valid` is `false`, Python **unconditionally** calls `send_email_tool` with the CV attached and structured metadata — the model cannot suppress this action.
- FastAPI `BackgroundTasks` integration queues the email asynchronously when a handle is present in state.

### Tool Implemented: `send_email_tool`

The **`send_email_tool`** (`app/tools/email_tool.py`) was implemented as the individual tool contribution. It wraps the Resend Python SDK as a LangChain `@tool` with:

- A strict Pydantic `EmailInput` schema for type-safe invocation.
- **Base64 file attachment** support: any file on disk is read, encoded, and attached.
- **Metadata injection**: a key/value dictionary is rendered as an HTML list and appended to the email body, providing audit context for reviewers.
- Graceful no-op when `RESEND_API_KEY` is not configured, allowing local development without email credentials.

### Challenges Faced

1. **Preventing model false negatives in validation:** Early iterations allowed the LLM to decide `is_valid: false` even for valid profiles, causing good candidates to be rejected. The solution was to add the deterministic Python pre-check that entirely bypasses the model when identity data is clearly present.

2. **Ensuring deterministic email delivery:** Tool-calling via LangChain's `bind_tools` proved unreliable with small local models — the model would sometimes omit the tool call. The Functional Orchestration Pattern resolved this by moving the email decision into Python logic triggered by the model's `is_valid` boolean output rather than relying on the model to invoke the tool directly.

3. **PDF layout diversity:** Two-column CVs caused garbled text when extracted as a single stream. Detecting the column boundary by counting blocks on each side of the midpoint and extracting each half independently resolved this without requiring any LLM involvement.

---

## 9. Unified Testing Harness

All tests use **pytest** with `monkeypatch` for dependency injection. The shared conventions across the harness are:

- `update_application` is always monkeypatched to a no-op lambda to avoid requiring a live database.
- `generate_json_response` is monkeypatched to return controlled JSON strings, isolating agent logic from Ollama availability.
- `tmp_path` pytest fixtures create isolated file system paths for file-reading tests.
- Each agent's test module provides its own `base_state` fixture that supplies the minimum valid state dictionary for that agent.

Each contributor added test cases validating their own agent's output:

| Contributor | Agent | Test File | Core Assertions |
|---|---|---|---|
| Individual | Extraction Validation | `test_extraction_validation_tool_call.py` | Email sent with attachment on failure; valid data short-circuits model |
| Individual | Extraction | `test_extraction_agent.py` | Retry behaviour, heuristic fallback, file type rejection |
| Individual | Evaluation | `test_evaluation_agent.py` | Rubric scoring, model narrative, idempotency, missing state guard |
| Group | Full workflow | `test_workflow.py` | End-to-end 6-node pipeline with stubbed LLM calls |
