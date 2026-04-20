# AgentHire - Multi-Agent Application Analysis System

FastAPI + LangGraph + SQLite implementation of a local-first multi-agent application processing pipeline.

## Features

- `POST /applications/upload`
- `POST /applications/process` (background pipeline)
- `GET /applications/{id}/status`
- `GET /applications/{id}/logs`
- `GET /health`
- 5-agent workflow: extraction, evaluation, decision, report, notification
- SQLite persistence (`applications`, `audit_log`)

## Setup

```bash
cd /path/to/AgentHire
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Run

```bash
uvicorn app.main:app --reload
```

## Email (Resend)

Set environment values before running:

```bash
export RESEND_API_KEY="re_xxx"
export RESEND_FROM_EMAIL="you@your-verified-domain.com"
```

## Ollama Models

```bash
ollama pull smollm:360m
ollama pull gemma3:1b-it-q4_K_M
ollama pull phi4-mini:3.8b-q4_K_M
```

## Test

```bash
pytest -q
```

## Architecture

Client -> FastAPI -> LangGraph state machine -> agents -> SQLite / reports / email

Decision routing:

- PASS -> report -> notify
- FAIL -> report -> notify
- REVIEW -> human_review -> report -> notify

## Team Contribution Matrix (template)

- Student 1: Extraction Agent + `parse_pdf_tool` + extraction tests
- Student 2: Evaluation Agent + `score_against_rubric_tool` + scoring tests
- Student 3: Decision Agent + `apply_decision_rules_tool` + property tests
- Student 4: Report/Notify Agent + `send_email_tool` + notification/report tests

## Troubleshooting

- If `/health` shows `ollama=down`, start Ollama and verify `OLLAMA_BASE_URL`.
- If Resend is not configured, notifications are marked as `queued`.
- If SQLite lock errors appear, avoid concurrent writes to the same DB file.
