from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import uuid

from .config import Settings


BACKUP_VERSION = 1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_database(path: Path) -> None:
    database = sqlite3.connect(path)
    try:
        result = database.execute("PRAGMA quick_check").fetchone()
    finally:
        database.close()
    if not result or result[0] != "ok":
        raise ValueError("备份数据库完整性检查失败")


def create_backup(settings: Settings, output_root: Path) -> Path:
    database_path = settings.database_path
    if not database_path.is_file():
        raise FileNotFoundError("数据库文件不存在，无法备份")
    output_root = output_root.resolve()
    if output_root.is_relative_to(settings.upload_path):
        raise ValueError("备份目录不能位于上传图片目录内")
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    final_dir = output_root / f"huiyan-backup-{timestamp}"
    staging_dir = output_root / f".{final_dir.name}.tmp"
    staging_dir.mkdir()
    try:
        backup_database = staging_dir / "app.db"
        source = sqlite3.connect(database_path)
        target = sqlite3.connect(backup_database)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        _check_database(backup_database)

        backup_uploads = staging_dir / "uploads"
        if settings.upload_path.is_dir():
            shutil.copytree(settings.upload_path, backup_uploads)
        else:
            backup_uploads.mkdir()
        upload_files = []
        for path in sorted(item for item in backup_uploads.rglob("*") if item.is_file()):
            upload_files.append(
                {
                    "path": path.relative_to(backup_uploads).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
        manifest = {
            "version": BACKUP_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": {"file": "app.db", "sha256": _sha256(backup_database)},
            "uploads": upload_files,
        }
        (staging_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        staging_dir.rename(final_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    return final_dir


def verify_backup(source_dir: Path) -> dict:
    source_dir = source_dir.resolve()
    manifest_path = source_dir / "manifest.json"
    database_path = source_dir / "app.db"
    uploads_path = source_dir / "uploads"
    if not manifest_path.is_file() or not database_path.is_file() or not uploads_path.is_dir():
        raise ValueError("备份目录缺少 manifest.json、app.db 或 uploads")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("version") != BACKUP_VERSION:
        raise ValueError("备份版本不受支持")
    expected_database_hash = manifest.get("database", {}).get("sha256")
    if expected_database_hash != _sha256(database_path):
        raise ValueError("备份数据库校验值不一致")
    _check_database(database_path)
    actual_uploads = {
        path.relative_to(uploads_path).as_posix(): {
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in uploads_path.rglob("*")
        if path.is_file()
    }
    expected_uploads = {
        item["path"]: {"size": item["size"], "sha256": item["sha256"]}
        for item in manifest.get("uploads", [])
    }
    if actual_uploads != expected_uploads:
        raise ValueError("备份图片清单或校验值不一致")
    return manifest


def restore_backup(settings: Settings, source_dir: Path, *, confirmed: bool) -> None:
    if not confirmed:
        raise ValueError("恢复操作必须显式确认")
    source_dir = source_dir.resolve()
    if source_dir == settings.upload_path or source_dir.is_relative_to(
        settings.upload_path
    ):
        raise ValueError("恢复源不能位于当前上传图片目录内")
    verify_backup(source_dir)
    database_path = settings.database_path
    upload_path = settings.upload_path
    database_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    new_database = database_path.parent / f".{database_path.name}.restore-{token}"
    old_database = database_path.parent / f".{database_path.name}.previous-{token}"
    new_uploads = upload_path.parent / f".{upload_path.name}.restore-{token}"
    old_uploads = upload_path.parent / f".{upload_path.name}.previous-{token}"
    shutil.copy2(source_dir / "app.db", new_database)
    shutil.copytree(source_dir / "uploads", new_uploads)
    _check_database(new_database)
    had_database = database_path.exists()
    had_uploads = upload_path.exists()
    try:
        if had_database:
            os.replace(database_path, old_database)
        os.replace(new_database, database_path)
        if had_uploads:
            os.replace(upload_path, old_uploads)
        os.replace(new_uploads, upload_path)
    except Exception:
        if database_path.exists():
            database_path.unlink()
        if old_database.exists():
            os.replace(old_database, database_path)
        if upload_path.exists():
            shutil.rmtree(upload_path)
        if old_uploads.exists():
            os.replace(old_uploads, upload_path)
        raise
    finally:
        new_database.unlink(missing_ok=True)
        shutil.rmtree(new_uploads, ignore_errors=True)
    old_database.unlink(missing_ok=True)
    shutil.rmtree(old_uploads, ignore_errors=True)
