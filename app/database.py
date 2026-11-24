from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class AnalyticsDB:
    """SQLite storage and reporting layer for synced time entries."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS time_entries (
                    entry_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    project_name TEXT NOT NULL,
                    task_title TEXT NOT NULL,
                    work_date TEXT NOT NULL,
                    duration_minutes INTEGER NOT NULL,
                    billable INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS audit_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    severity TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    work_date TEXT NOT NULL,
                    message TEXT NOT NULL
                );
                """
            )

    def upsert_entry(self, entry: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO time_entries
                (entry_id, user_id, user_name, project_name, task_title, work_date, duration_minutes, billable)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry["entry_id"],
                    entry["user_id"],
                    entry["user_name"],
                    entry["project_name"],
                    entry["task_title"],
                    entry["work_date"],
                    int(entry["duration_minutes"]),
                    1 if entry.get("billable", True) else 0,
                ),
            )

    def record_alert(self, severity: str, user_name: str, work_date: str, message: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_alerts (severity, user_name, work_date, message) VALUES (?, ?, ?, ?)",
                (severity, user_name, work_date, message),
            )

    def clear_alerts(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM audit_alerts")

    def get_dashboard_metrics(self) -> dict[str, Any]:
        with self._connect() as conn:
            by_user = [
                {"user_name": r["user_name"], "hours": round(r["mins"] / 60.0, 2)}
                for r in conn.execute(
                    "SELECT user_name, SUM(duration_minutes) AS mins FROM time_entries GROUP BY user_name ORDER BY mins DESC"
                )
            ]
            by_project = [
                {"project_name": r["project_name"], "hours": round(r["mins"] / 60.0, 2)}
                for r in conn.execute(
                    "SELECT project_name, SUM(duration_minutes) AS mins FROM time_entries GROUP BY project_name ORDER BY mins DESC"
                )
            ]
            by_day = [
                {"work_date": r["work_date"], "hours": round(r["mins"] / 60.0, 2)}
                for r in conn.execute(
                    "SELECT work_date, SUM(duration_minutes) AS mins FROM time_entries GROUP BY work_date ORDER BY work_date ASC"
                )
            ]
            alerts = [
                dict(r)
                for r in conn.execute(
                    "SELECT severity, user_name, work_date, message FROM audit_alerts ORDER BY id DESC LIMIT 20"
                )
            ]
            total_mins = conn.execute("SELECT COALESCE(SUM(duration_minutes), 0) FROM time_entries").fetchone()[0]
            return {
                "total_hours": round(total_mins / 60.0, 2),
                "by_user": by_user,
                "by_project": by_project,
                "by_day": by_day,
                "alerts": alerts,
            }
