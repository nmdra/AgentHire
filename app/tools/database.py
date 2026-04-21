from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY,
                name TEXT,
                email TEXT,
                phone TEXT,
                raw_file_path TEXT NOT NULL,
                extracted_json TEXT,
                evaluation_score REAL,
                evaluation_reasoning TEXT,
                decision TEXT,
                confidence REAL,
                report_applicant TEXT,
                report_internal TEXT,
                notification_status TEXT,
                errors TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                tool_name TEXT,
                input_summary TEXT NOT NULL,
                output_summary TEXT NOT NULL,
                latency_ms INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (application_id) REFERENCES applications(id)
            );
            """
        )
