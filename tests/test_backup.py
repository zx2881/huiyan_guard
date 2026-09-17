import json
from pathlib import Path

import pytest

from backend.app.backup import create_backup, restore_backup, verify_backup
from backend.app.config import Settings
from backend.app.database import conn, init_db


def backup_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'live' / 'app.db').as_posix()}",
        upload_dir=(tmp_path / "live" / "uploads").as_posix(),
    )


def seed_data(settings: Settings) -> None:
    init_db(settings)
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    (settings.upload_path / "room.jpg").write_bytes(b"original-image")
    with conn(settings) as database:
        database.execute(
            """INSERT INTO inspections(
                scene,image_path,status,created_at,current_step,progress,mode
            ) VALUES(?,?,?,?,?,?,?)""",
            (
                "dormitory",
                "room.jpg",
                "completed",
                "2026-09-17T00:00:00Z",
                "completed",
                100,
                "demo",
            ),
        )


def test_backup_verifies_and_restores_database_and_uploads(tmp_path):
    settings = backup_settings(tmp_path)
    seed_data(settings)
    backup_dir = create_backup(settings, tmp_path / "backups")

    manifest = verify_backup(backup_dir)
    assert manifest["version"] == 1
    assert manifest["uploads"][0]["path"] == "room.jpg"

    with conn(settings) as database:
        database.execute("DELETE FROM inspections")
    (settings.upload_path / "room.jpg").write_bytes(b"changed")
    (settings.upload_path / "extra.jpg").write_bytes(b"extra")

    restore_backup(settings, backup_dir, confirmed=True)

    with conn(settings) as database:
        count = database.execute("SELECT COUNT(*) n FROM inspections").fetchone()["n"]
    assert count == 1
    assert (settings.upload_path / "room.jpg").read_bytes() == b"original-image"
    assert not (settings.upload_path / "extra.jpg").exists()


def test_restore_requires_confirmation_and_rejects_tampered_backup(tmp_path):
    settings = backup_settings(tmp_path)
    seed_data(settings)
    backup_dir = create_backup(settings, tmp_path / "backups")

    with pytest.raises(ValueError, match="显式确认"):
        restore_backup(settings, backup_dir, confirmed=False)

    (backup_dir / "uploads" / "room.jpg").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="校验值"):
        verify_backup(backup_dir)


def test_backup_manifest_contains_no_configuration_or_secrets(tmp_path):
    settings = backup_settings(tmp_path)
    seed_data(settings)
    backup_dir = create_backup(settings, tmp_path / "backups")
    manifest_text = (backup_dir / "manifest.json").read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)

    assert set(manifest) == {"version", "created_at", "database", "uploads"}
    assert "api_key" not in manifest_text.lower()
    assert str(settings.database_path) not in manifest_text
