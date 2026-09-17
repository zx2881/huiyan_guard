from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.config import REPO_ROOT, Settings


def test_default_paths_are_relative_to_repository(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("UPLOAD_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None)

    assert settings.database_path == (REPO_ROOT / "data" / "app.db").resolve()
    assert settings.upload_path == (
        REPO_ROOT / "data" / "uploads" / "inspections"
    ).resolve()


def test_environment_overrides_paths(monkeypatch, tmp_path: Path):
    database_path = (tmp_path / "custom.db").as_posix()
    upload_path = (tmp_path / "custom-uploads").as_posix()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("UPLOAD_DIR", upload_path)

    settings = Settings(_env_file=None)

    assert settings.database_path == Path(database_path).resolve()
    assert settings.upload_path == Path(upload_path).resolve()


@pytest.mark.parametrize(
    "database_url",
    ["postgresql://localhost/huiyan", "sqlite:///:memory:", "sqlite:///"],
)
def test_rejects_unsupported_database_url(database_url: str):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=database_url)


def test_rejects_unknown_vision_provider():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vision_provider="unknown")
