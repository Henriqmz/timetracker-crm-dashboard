from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .database import AnalyticsDB


@dataclass
class SyncReport:
    synced: int = 0
    skipped_unmapped_user: int = 0
    alerts_generated: int = 0


def convert_source_timestamp(
    iso_timestamp: str,
    source_offset_hours: int = 3,
    target_offset_hours: int = -3,
) -> datetime:
    """Converts naive/offset timestamps from a remote API timezone to local operational timezone."""
    dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=source_offset_hours)))
    target_tz = timezone(timedelta(hours=target_offset_hours))
    return dt.astimezone(target_tz)


class TimeSyncEngine:
    """Synchronizes time entries enforcing strict user mapping and anomaly detection."""

    def __init__(
        self,
        db: AnalyticsDB,
        users_map: dict[str, str],
        source_offset_hours: int = 3,
        target_offset_hours: int = -3,
        daily_alert_threshold_minutes: int = 600,
    ) -> None:
        self.db = db
        self.users_map = users_map
        self.source_offset_hours = source_offset_hours
        self.target_offset_hours = target_offset_hours
        self.daily_alert_threshold_minutes = daily_alert_threshold_minutes

    def sync_batch(self, raw_entries: list[dict[str, Any]]) -> SyncReport:
        report = SyncReport()
        self.db.clear_alerts()
        daily_totals: dict[tuple[str, str], int] = {}

        for raw in raw_entries:
            uid = str(raw.get("user_id", ""))
            # Guardrail: never auto-create unmapped users
            if uid not in self.users_map:
                report.skipped_unmapped_user += 1
                self.db.record_alert(
                    "WARNING",
                    f"Unmapped({uid})",
                    str(raw.get("started_at", ""))[:10],
                    f"Registro {raw.get('id')} ignorado: usuário '{uid}' não cadastrado em users_map.json.",
                )
                report.alerts_generated += 1
                continue

            local_dt = convert_source_timestamp(
                str(raw["started_at"]),
                source_offset_hours=self.source_offset_hours,
                target_offset_hours=self.target_offset_hours,
            )
            work_date = local_dt.strftime("%Y-%m-%d")
            user_name = self.users_map[uid]
            mins = int(raw.get("duration_minutes", 0))
            title = str(raw.get("task_title", "")).strip()

            if not title:
                self.db.record_alert(
                    "WARNING",
                    user_name,
                    work_date,
                    f"Apontamento {raw.get('id')} ({mins} min) sem descrição de tarefa.",
                )
                report.alerts_generated += 1

            self.db.upsert_entry(
                {
                    "entry_id": str(raw["id"]),
                    "user_id": uid,
                    "user_name": user_name,
                    "project_name": str(raw.get("project_name", "Sem Projeto")),
                    "task_title": title or "(Sem descrição)",
                    "work_date": work_date,
                    "duration_minutes": mins,
                    "billable": bool(raw.get("billable", True)),
                }
            )
            daily_totals[(user_name, work_date)] = daily_totals.get((user_name, work_date), 0) + mins
            report.synced += 1

        for (user_name, work_date), total_mins in daily_totals.items():
            if total_mins > self.daily_alert_threshold_minutes:
                self.db.record_alert(
                    "ALERT",
                    user_name,
                    work_date,
                    f"Total diário de {total_mins / 60:.1f}h excede o teto configurado ({self.daily_alert_threshold_minutes / 60:.1f}h).",
                )
                report.alerts_generated += 1

        return report
