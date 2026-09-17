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


def test_access_credentials_must_be_configured_as_a_pair():
    with pytest.raises(ValidationError, match="必须同时配置"):
        Settings(_env_file=None, app_access_username="reviewer")

    settings = Settings(
        _env_file=None,
        app_access_username=" reviewer ",
        app_access_password=" secret ",
    )
    assert settings.access_protected is True
    assert settings.app_access_username == "reviewer"
    assert settings.app_access_password == "secret"

    with pytest.raises(ValidationError, match="生产启动要求"):
        Settings(_env_file=None, require_access_control=True)


def test_ai_review_requires_text_configuration_to_be_ready():
    assert Settings(_env_file=None, enable_ai_review=True).ai_review_ready is False
    assert Settings(
        _env_file=None,
        enable_ai_review=True,
        text_api_key="secret",
        text_model="review-model",
    ).ai_review_ready is True
