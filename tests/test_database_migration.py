import sqlite3

from backend.app.config import Settings
from backend.app.database import conn, init_db


def test_old_database_is_migrated_without_losing_records(tmp_path):
    database_path = tmp_path / "old.db"
    database = sqlite3.connect(database_path)
    database.execute(
        """CREATE TABLE inspections(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scene TEXT NOT NULL,
        image_path TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        completed_at TEXT,
        error TEXT
        )"""
    )
    database.execute(
        """CREATE TABLE regulations(
        id TEXT PRIMARY KEY,
        scene TEXT,
        document_title TEXT,
        article TEXT,
        content TEXT,
        source_url TEXT
        )"""
    )
    database.execute(
        "INSERT INTO inspections(scene,image_path,status,created_at) VALUES(?,?,?,?)",
        ("dormitory", "old.jpg", "completed", "2026-09-16T00:00:00Z"),
    )
    database.commit()
    database.close()
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{database_path.as_posix()}",
        upload_dir=(tmp_path / "uploads").as_posix(),
    )

    init_db(settings)
    init_db(settings)

    with conn(settings) as migrated:
        columns = {row["name"] for row in migrated.execute("PRAGMA table_info(inspections)")}
        regulation_columns = {
            row["name"] for row in migrated.execute("PRAGMA table_info(regulations)")
        }
        row = migrated.execute("SELECT * FROM inspections WHERE id=1").fetchone()
    assert {"image_quality", "uncertain_items", "summary"} <= columns
    assert {"current_step", "progress", "started_at", "mode", "model_info", "retry_count"} <= columns
    assert row["image_path"] == "old.jpg"
    assert row["uncertain_items"] == "[]"
    assert {"document_number", "source_file", "verified_at", "keywords", "check_ids"} <= regulation_columns
    with conn(settings) as migrated:
        hazard_columns = {
            row["name"] for row in migrated.execute("PRAGMA table_info(hazards)")
        }
        snapshot_table = migrated.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='regulation_snapshots'"
        ).fetchone()
    assert {
        "confidence",
        "risk_reason",
        "priority",
        "suggested_deadline",
        "manual_checks",
        "source",
        "human_status",
        "original_data",
        "updated_at",
    } <= hazard_columns
    assert snapshot_table["name"] == "regulation_snapshots"
    with conn(settings) as migrated:
        action_table = migrated.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='hazard_actions'"
        ).fetchone()
    assert action_table["name"] == "hazard_actions"
