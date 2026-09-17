import base64
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def protected_settings(tmp_path: Path, **changes) -> Settings:
    values = {
        "_env_file": None,
        "database_url": f"sqlite:///{(tmp_path / 'app.db').as_posix()}",
        "upload_dir": (tmp_path / "uploads").as_posix(),
        "app_access_username": "reviewer",
        "app_access_password": "safe-password",
    }
    values.update(changes)
    return Settings(**values)


def basic_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_health_stays_public_while_pages_and_api_are_protected(tmp_path):
    with TestClient(create_app(protected_settings(tmp_path))) as client:
        health = client.get("/api/health")
        page = client.get("/")
        wrong = client.get("/api/inspections", headers=basic_header("reviewer", "wrong"))
        allowed = client.get(
            "/api/inspections",
            headers=basic_header("reviewer", "safe-password"),
        )

    assert health.status_code == 200
    assert health.json()["access"] == "protected"
    assert page.status_code == 401
    assert page.headers["www-authenticate"] == 'Basic realm="Huiyan Guard"'
    assert wrong.status_code == 401
    assert allowed.status_code == 200


def test_write_rate_limit_returns_retry_after(tmp_path):
    settings = protected_settings(tmp_path, write_rate_limit_per_minute=1)
    headers = basic_header("reviewer", "safe-password")
    with TestClient(create_app(settings)) as client:
        first = client.post(
            "/api/inspections",
            headers=headers,
            data={"scene": "office"},
            files={"image": ("sample.jpg", b"bad", "image/jpeg")},
        )
        second = client.post(
            "/api/inspections",
            headers=headers,
            data={"scene": "office"},
            files={"image": ("sample.jpg", b"bad", "image/jpeg")},
        )

    assert first.status_code == 400
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) >= 1
    assert second.json() == {"detail": "操作过于频繁，请稍后重试"}
