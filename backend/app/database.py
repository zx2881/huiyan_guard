from collections.abc import Iterator
from contextlib import contextmanager
import sqlite3

from .config import Settings, get_settings


@contextmanager
def conn(settings: Settings | None = None) -> Iterator[sqlite3.Connection]:
    """Open a transaction and always close the SQLite connection."""

    database_path = (settings or get_settings()).database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db(settings: Settings | None = None) -> None:
    with conn(settings) as database:
        database.executescript(
            """
            CREATE TABLE IF NOT EXISTS inspections(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scene TEXT NOT NULL,
                image_path TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                error TEXT,
                current_step TEXT NOT NULL DEFAULT 'completed',
                progress INTEGER NOT NULL DEFAULT 100,
                started_at TEXT,
                mode TEXT NOT NULL DEFAULT 'unknown',
                model_info TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS hazards(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inspection_id INTEGER,
                name TEXT,
                location TEXT,
                evidence TEXT,
                risk TEXT,
                advice TEXT,
                regulation TEXT,
                source_url TEXT,
                confidence REAL,
                risk_reason TEXT,
                priority TEXT,
                suggested_deadline TEXT,
                manual_checks TEXT NOT NULL DEFAULT '[]',
                classification_method TEXT,
                remediation_method TEXT,
                source TEXT NOT NULL DEFAULT 'ai',
                human_status TEXT NOT NULL DEFAULT 'pending',
                original_data TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS regulations(
                id TEXT PRIMARY KEY,
                scene TEXT,
                document_title TEXT,
                document_number TEXT,
                source_file TEXT,
                article TEXT,
                content TEXT,
                source_url TEXT,
                verified_at TEXT,
                keywords TEXT NOT NULL DEFAULT '[]',
                check_ids TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS regulation_snapshots(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inspection_id INTEGER NOT NULL,
                hazard_id INTEGER NOT NULL,
                regulation_id TEXT NOT NULL,
                document_title TEXT NOT NULL,
                document_number TEXT,
                article TEXT NOT NULL,
                content TEXT NOT NULL,
                source_url TEXT NOT NULL,
                retrieved_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_snapshots_hazard
                ON regulation_snapshots(hazard_id);
            CREATE TABLE IF NOT EXISTS hazard_actions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inspection_id INTEGER NOT NULL,
                hazard_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                before_data TEXT,
                after_data TEXT NOT NULL,
                note TEXT,
                actor TEXT NOT NULL DEFAULT 'unauthenticated',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_hazard_actions_hazard
                ON hazard_actions(hazard_id);
            """
        )
        existing_columns = {
            row["name"] for row in database.execute("PRAGMA table_info(inspections)")
        }
        migrations = {
            "image_quality": "ALTER TABLE inspections ADD COLUMN image_quality TEXT",
            "uncertain_items": (
                "ALTER TABLE inspections ADD COLUMN uncertain_items "
                "TEXT NOT NULL DEFAULT '[]'"
            ),
            "summary": "ALTER TABLE inspections ADD COLUMN summary TEXT",
            "current_step": (
                "ALTER TABLE inspections ADD COLUMN current_step "
                "TEXT NOT NULL DEFAULT 'completed'"
            ),
            "progress": (
                "ALTER TABLE inspections ADD COLUMN progress "
                "INTEGER NOT NULL DEFAULT 100"
            ),
            "started_at": "ALTER TABLE inspections ADD COLUMN started_at TEXT",
            "mode": (
                "ALTER TABLE inspections ADD COLUMN mode "
                "TEXT NOT NULL DEFAULT 'unknown'"
            ),
            "model_info": "ALTER TABLE inspections ADD COLUMN model_info TEXT",
            "retry_count": (
                "ALTER TABLE inspections ADD COLUMN retry_count "
                "INTEGER NOT NULL DEFAULT 0"
            ),
        }
        for column, statement in migrations.items():
            if column not in existing_columns:
                database.execute(statement)

        regulation_columns = {
            row["name"] for row in database.execute("PRAGMA table_info(regulations)")
        }
        regulation_migrations = {
            "document_number": (
                "ALTER TABLE regulations ADD COLUMN document_number TEXT"
            ),
            "source_file": "ALTER TABLE regulations ADD COLUMN source_file TEXT",
            "verified_at": "ALTER TABLE regulations ADD COLUMN verified_at TEXT",
            "keywords": (
                "ALTER TABLE regulations ADD COLUMN keywords TEXT NOT NULL DEFAULT '[]'"
            ),
            "check_ids": (
                "ALTER TABLE regulations ADD COLUMN check_ids TEXT NOT NULL DEFAULT '[]'"
            ),
        }
        for column, statement in regulation_migrations.items():
            if column not in regulation_columns:
                database.execute(statement)

        hazard_columns = {
            row["name"] for row in database.execute("PRAGMA table_info(hazards)")
        }
        hazard_migrations = {
            "confidence": "ALTER TABLE hazards ADD COLUMN confidence REAL",
            "risk_reason": "ALTER TABLE hazards ADD COLUMN risk_reason TEXT",
            "priority": "ALTER TABLE hazards ADD COLUMN priority TEXT",
            "suggested_deadline": (
                "ALTER TABLE hazards ADD COLUMN suggested_deadline TEXT"
            ),
            "manual_checks": (
                "ALTER TABLE hazards ADD COLUMN manual_checks "
                "TEXT NOT NULL DEFAULT '[]'"
            ),
            "classification_method": (
                "ALTER TABLE hazards ADD COLUMN classification_method TEXT"
            ),
            "remediation_method": (
                "ALTER TABLE hazards ADD COLUMN remediation_method TEXT"
            ),
            "source": (
                "ALTER TABLE hazards ADD COLUMN source TEXT NOT NULL DEFAULT 'ai'"
            ),
            "human_status": (
                "ALTER TABLE hazards ADD COLUMN human_status "
                "TEXT NOT NULL DEFAULT 'pending'"
            ),
            "original_data": "ALTER TABLE hazards ADD COLUMN original_data TEXT",
            "updated_at": "ALTER TABLE hazards ADD COLUMN updated_at TEXT",
        }
        for column, statement in hazard_migrations.items():
            if column not in hazard_columns:
                database.execute(statement)
