from __future__ import annotations

import json
from pathlib import Path

from .database import AnalyticsDB
from .sync_engine import TimeSyncEngine


def seed_demo_database(db_path: Path = Path("data/timetracker.db")) -> None:
    """Seeds SQLite with 100% synthetic team time entries for demo & portfolio showcase."""
    users_map = json.loads(Path("users_map.example.json").read_text(encoding="utf-8"))
    db = AnalyticsDB(db_path)
    engine = TimeSyncEngine(db=db, users_map=users_map, source_offset_hours=3, target_offset_hours=-3)

    synthetic_entries = [
        {"id": "t-001", "user_id": "usr_101", "project_name": "Portal E-commerce", "task_title": "Integração Checkout API", "started_at": "2026-10-12T14:00:00", "duration_minutes": 210},
        {"id": "t-002", "user_id": "usr_101", "project_name": "BI Financeiro", "task_title": "Pipeline ETL SQLite", "started_at": "2026-10-12T18:30:00", "duration_minutes": 180},
        {"id": "t-003", "user_id": "usr_102", "project_name": "App Mobile", "task_title": "Autenticação OAuth2", "started_at": "2026-10-12T15:00:00", "duration_minutes": 300},
        {"id": "t-004", "user_id": "usr_103", "project_name": "Portal E-commerce", "task_title": "Testes automatizados", "started_at": "2026-10-13T13:00:00", "duration_minutes": 240},
        {"id": "t-005", "user_id": "usr_104", "project_name": "BI Financeiro", "task_title": "Dashboard KPIs", "started_at": "2026-10-13T16:00:00", "duration_minutes": 270},
        {"id": "t-006", "user_id": "usr_102", "project_name": "App Mobile", "task_title": "Correção de layout responsivo", "started_at": "2026-10-14T14:00:00", "duration_minutes": 390},
        {"id": "t-007", "user_id": "usr_102", "project_name": "App Mobile", "task_title": "Deploy staging e revisão", "started_at": "2026-10-14T21:00:00", "duration_minutes": 260},
        {"id": "t-008", "user_id": "usr_103", "project_name": "Portal E-commerce", "task_title": "", "started_at": "2026-10-15T15:00:00", "duration_minutes": 95},
        {"id": "t-009", "user_id": "usr_999", "project_name": "Externo", "task_title": "Usuário não mapeado", "started_at": "2026-10-15T16:00:00", "duration_minutes": 60},
    ]

    report = engine.sync_batch(synthetic_entries)
    print(
        f"Demo populado em {db_path}: sincronizados={report.synced}, "
        f"ignorados_nao_mapeados={report.skipped_unmapped_user}, alertas={report.alerts_generated}"
    )


if __name__ == "__main__":
    seed_demo_database()
