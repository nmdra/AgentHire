from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.constants import MAX_SUMMARY_LENGTH
from app.db.database import connect

ALLOWED_APPLICATION_COLUMNS = {
    "name",
    "email",
    "phone",
    "raw_file_path",
    "extracted_json",
    "evaluation_score",
    "evaluation_reasoning",
    "decision",
    "confidence",
    "report_applicant",
    "report_internal",
    "notification_status",
    "errors",
}
# NOTE: keep this whitelist strict; update_fields builds column assignments dynamically and
# relies on this allow-list to prevent SQL injection through column names.


class ApplicationRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def create_application(self, application_id: str, raw_file_path: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO applications (id, raw_file_path, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (application_id, raw_file_path, now),
            )

    def get_application(self, application_id: str) -> dict[str, Any] | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM applications WHERE id = ?", (application_id,)
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["extracted_json"] = json.loads(data["extracted_json"]) if data["extracted_json"] else None
        data["errors"] = json.loads(data["errors"]) if data["errors"] else []
        return data

    def update_fields(self, application_id: str, **fields: Any) -> None:
        if not fields:
            return
        encoded = dict(fields)
        invalid_keys = set(encoded).difference(ALLOWED_APPLICATION_COLUMNS)
        if invalid_keys:
            raise ValueError(f"Unsupported update fields: {sorted(invalid_keys)}")
        if "extracted_json" in encoded and encoded["extracted_json"] is not None:
            encoded["extracted_json"] = json.dumps(encoded["extracted_json"])
        if "errors" in encoded:
            encoded["errors"] = json.dumps(encoded["errors"])
        # Safe because keys are validated against ALLOWED_APPLICATION_COLUMNS above.
        columns = ", ".join(f"{key} = ?" for key in encoded)
        values = list(encoded.values())
        values.append(application_id)
        with connect(self.db_path) as conn:
            conn.execute(f"UPDATE applications SET {columns} WHERE id = ?", values)

    def append_error(self, application_id: str, message: str) -> None:
        app = self.get_application(application_id)
        if app is None:
            return
        errors = app.get("errors", [])
        errors.append(message)
        self.update_fields(application_id, errors=errors)

    def add_audit_log(
        self,
        application_id: str,
        agent_name: str,
        tool_name: str | None,
        input_summary: str,
        output_summary: str,
        latency_ms: int,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO audit_log (
                    application_id, agent_name, tool_name, input_summary,
                    output_summary, latency_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    application_id,
                    agent_name,
                    tool_name,
                    input_summary[:MAX_SUMMARY_LENGTH],
                    output_summary[:MAX_SUMMARY_LENGTH],
                    latency_ms,
                    now,
                ),
            )

    def list_audit_logs(self, application_id: str) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE application_id = ? ORDER BY id ASC",
                (application_id,),
            ).fetchall()
        return [dict(r) for r in rows]
