"""SQLite persistence helpers."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from collections.abc import Iterator

ALLOWED_UPDATE_COLUMNS = {
    "status",
    "extracted_json",
    "evaluation_score",
    "evaluation_reasoning",
    "decision",
    "confidence",
    "decision_reason",
    "report_applicant",
    "report_internal",
    "notification_status",
    "errors",
    "updated_at",
}


@contextmanager
def get_connection(db_path: str) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection configured for row access."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA foreign_keys=ON;")
    try:
        yield connection
    finally:
        connection.close()


def init_database(db_path: str) -> None:
    """Create required application and audit tables."""
    with get_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                status TEXT NOT NULL,
                extracted_json TEXT,
                evaluation_score REAL,
                evaluation_reasoning TEXT,
                decision TEXT,
                confidence REAL,
                decision_reason TEXT,
                report_applicant TEXT,
                report_internal TEXT,
                notification_status TEXT,
                errors TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                input_summary TEXT,
                output_summary TEXT,
                latency_ms REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (application_id) REFERENCES applications(id)
            );
            """
        )
        conn.commit()


def create_application(db_path: str, file_name: str, file_path: str) -> str:
    """Insert a new application row and return its identifier."""
    application_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO applications (id, file_name, file_path, status, created_at, updated_at)
            VALUES (?, ?, ?, 'uploaded', ?, ?)
            """,
            (application_id, file_name, file_path, now, now),
        )
        conn.commit()
    return application_id


def update_application(db_path: str, application_id: str, values: dict[str, Any]) -> None:
    """Update an application row with provided values."""
    if not values:
        return

    serialized: dict[str, Any] = {}
    for key, value in values.items():
        if key in {"extracted_json", "errors"} and value is not None:
            serialized[key] = json.dumps(value)
        else:
            serialized[key] = value

    serialized["updated_at"] = datetime.now(UTC).isoformat()
    unknown_columns = set(serialized).difference(ALLOWED_UPDATE_COLUMNS)
    if unknown_columns:
        raise ValueError(f"Unsupported update column(s): {sorted(unknown_columns)}")

    columns = ", ".join(f"{column} = ?" for column in serialized)
    params = list(serialized.values()) + [application_id]
    with get_connection(db_path) as conn:
        conn.execute(f"UPDATE applications SET {columns} WHERE id = ?", params)
        conn.commit()


def insert_audit_entries(db_path: str, application_id: str, entries: list[dict[str, Any]]) -> None:
    """Insert per-node audit entries for an application."""
    if not entries:
        return

    now = datetime.now(UTC).isoformat()
    rows = [
        (
            application_id,
            str(entry.get("agent_name", "unknown")),
            str(entry.get("tool_name", "unknown")),
            str(entry.get("input_summary", "")),
            str(entry.get("output_summary", "")),
            float(entry.get("latency_ms", 0.0)),
            now,
        )
        for entry in entries
    ]

    with get_connection(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO audit_log (
                application_id, agent_name, tool_name, input_summary, output_summary, latency_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def get_application_status(db_path: str, application_id: str) -> dict[str, Any] | None:
    """Return an application row as a dictionary."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ?",
            (application_id,),
        ).fetchone()

    if row is None:
        return None

    data = dict(row)
    if data.get("extracted_json"):
        data["extracted_json"] = json.loads(data["extracted_json"])
    if data.get("errors"):
        data["errors"] = json.loads(data["errors"])
    return data


def get_application_logs(db_path: str, application_id: str) -> list[dict[str, Any]]:
    """Return audit log rows for a specific application.

    Args:
        db_path: Path to the SQLite database file.
        application_id: Application identifier whose logs should be returned.

    Returns:
        Ordered audit log entries as plain dictionaries.

    Example:
        get_application_logs("agenthire.db", "app-123")
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, application_id, agent_name, tool_name, input_summary,
                   output_summary, latency_ms, created_at
            FROM audit_log
            WHERE application_id = ?
            ORDER BY id
            """,
            (application_id,),
        ).fetchall()

    return [dict(row) for row in rows]
