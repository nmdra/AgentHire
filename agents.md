# AgentHire Agents

This document describes the application agents used in the AgentHire processing workflow.

## Workflow order

1. `extraction_agent`
2. `evaluation_agent`
3. `decision_agent`
4. `human_review` (only when decision is `REVIEW`)
5. `report_agent`
6. `notification_agent`

## Agent responsibilities

- **Extraction Agent** (`app/agents/extraction_agent.py`)
  - Extracts applicant fields from uploaded files.
  - Persists extracted data to the application record.

- **Evaluation Agent** (`app/agents/evaluation_agent.py`)
  - Loads rubric data.
  - Scores extracted applicant data and stores score/reasoning.

- **Decision Agent** (`app/agents/decision_agent.py`)
  - Applies pass/review thresholds to produce `PASS`, `REVIEW`, or `FAIL`.
  - Stores decision and confidence.

- **Human Review Agent** (`app/agents/human_review_agent.py`)
  - Handles manual-review routing when a case requires review.

- **Report Agent** (`app/agents/report_agent.py`)
  - Generates applicant/internal reports and persists report content.

- **Notification Agent** (`app/agents/notification_agent.py`)
  - Composes and sends decision emails.
  - Persists notification status and records errors for missing recipients.

## Shared behavior

- All agents append audit log entries through shared logging helpers.
- Agent orchestration is defined in `app/graph/workflow.py`.
