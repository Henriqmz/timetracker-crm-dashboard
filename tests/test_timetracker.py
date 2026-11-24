from pathlib import Path

from app.database import AnalyticsDB
from app.sync_engine import TimeSyncEngine, convert_source_timestamp
from app.totp import generate_totp, verify_totp


def test_totp_generation_and_verification():
    secret = "JBSWY3DPEHPK3PXP"
    ts = 1700000000.0
    code = generate_totp(secret, timestamp=ts)
    assert len(code) == 6
    assert verify_totp(secret, code, timestamp=ts) is True
    assert verify_totp(secret, code, timestamp=ts + 25) is True
    assert verify_totp(secret, "000000", timestamp=ts) is False


def test_timezone_conversion_utc_plus_3_to_brt():
    # 02:00 in UTC+3 corresponds to 20:00 of the previous day in UTC-3
    dt = convert_source_timestamp("2026-10-15T02:00:00", source_offset_hours=3, target_offset_hours=-3)
    assert dt.strftime("%Y-%m-%d %H:%M") == "2026-10-14 20:00"


def test_sync_engine_guardrails_and_aggregations(tmp_path: Path):
    db = AnalyticsDB(tmp_path / "test.db")
    engine = TimeSyncEngine(
        db=db,
        users_map={"u1": "Ana Costa"},
        daily_alert_threshold_minutes=480,
    )
    report = engine.sync_batch(
        [
            {"id": "1", "user_id": "u1", "project_name": "Alpha", "task_title": "Dev", "started_at": "2026-10-12T14:00:00", "duration_minutes": 300},
            {"id": "2", "user_id": "u1", "project_name": "Alpha", "task_title": "", "started_at": "2026-10-12T20:00:00", "duration_minutes": 240},
            {"id": "3", "user_id": "unknown", "project_name": "Beta", "task_title": "X", "started_at": "2026-10-12T15:00:00", "duration_minutes": 60},
        ]
    )
    assert report.synced == 2
    assert report.skipped_unmapped_user == 1
    assert report.alerts_generated == 3  # unmapped user + empty title + >8h daily threshold

    metrics = db.get_dashboard_metrics()
    assert metrics["total_hours"] == 9.0
    assert metrics["by_user"][0]["user_name"] == "Ana Costa"
