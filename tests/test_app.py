from pathlib import Path
from contextlib import contextmanager

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
import backend.app.main as main_module


def test_health_reports_database_and_unconfigured_vision(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "vision": "unconfigured",
        "vision_provider": "ark",
        "text": "rules",
        "ai_review": "disabled",
        "access": "open",
    }


def test_health_reports_configured_without_calling_provider(tmp_path: Path):
    secret = "audit-secret-that-must-not-be-returned"
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'app.db').as_posix()}",
        upload_dir=(tmp_path / "uploads").as_posix(),
        ark_api_key=secret,
        ark_model="ep-test-only",
        text_api_key=secret,
        text_model="ep-text-test",
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["vision"] == "configured"
    assert response.json()["vision_provider"] == "ark"
    assert response.json()["text"] == "configured"
    assert secret not in response.text
    assert str(tmp_path) not in response.text


def test_health_returns_safe_503_when_database_is_unavailable(
    client, monkeypatch
):
    secret_detail = "C:/private/path?token=should-not-leak"

    @contextmanager
    def unavailable_database(*_args, **_kwargs):
        raise OSError(secret_detail)
        yield

    monkeypatch.setattr(main_module, "conn", unavailable_database)

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unavailable"}
    assert secret_detail not in response.text


def test_health_marks_yolo_as_reserved_until_adapter_is_implemented(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'app.db').as_posix()}",
        upload_dir=(tmp_path / "uploads").as_posix(),
        vision_provider="yolo",
        yolo_model_path="weights/best.pt",
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["vision_provider"] == "yolo"
    assert response.json()["vision"] == "unconfigured"


def test_pages_and_static_asset_are_available(client):
    for path in ("/", "/records", "/report", "/assets/css/common.css"):
        assert client.get(path).status_code == 200


def test_empty_history_and_unknown_inspection(client):
    assert client.get("/api/inspections").json() == []
    response = client.get("/api/inspections/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "巡检记录不存在"}


def test_rejects_invalid_scene_and_mime(client):
    bad_scene = client.post(
        "/api/inspections",
        data={"scene": "office"},
        files={"image": ("sample.jpg", b"image", "image/jpeg")},
    )
    bad_mime = client.post(
        "/api/inspections",
        data={"scene": "dormitory"},
        files={"image": ("sample.txt", b"text", "text/plain")},
    )

    assert bad_scene.status_code == 400
    assert bad_scene.json() == {"detail": "不支持的检查场景"}
    assert bad_mime.status_code == 400
    assert bad_mime.json() == {"detail": "只支持 JPEG、PNG 和 WebP 图片"}


def test_demo_upload_uses_isolated_database_and_upload_directory(
    client, isolated_settings: Settings, image_bytes
):
    payload = image_bytes()
    response = client.post(
        "/api/inspections",
        data={"scene": "dormitory"},
        files={"image": ("sample.jpg", payload, "image/jpeg")},
    )

    assert response.status_code == 200
    created = response.json()
    assert created["status"] == "completed"
    assert created["mode"] == "demo"

    detail = client.get(f"/api/inspections/{created['id']}").json()
    assert detail["scene"] == "dormitory"
    assert detail["hazards"] == []
    assert detail["image_quality"] == "uncertain"
    assert detail["uncertain_items"] == []
    assert "未配置完整" in detail["summary"]
    uploaded_path = isolated_settings.upload_path / detail["image_path"]
    assert uploaded_path.read_bytes() == payload
    assert isolated_settings.database_path.exists()


def test_rejects_fake_image_without_creating_record(client):
    response = client.post(
        "/api/inspections",
        data={"scene": "dormitory"},
        files={"image": ("fake.jpg", b"not-an-image", "image/jpeg")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "图片内容无效或已损坏"}
    assert client.get("/api/inspections").json() == []


def test_rejects_mime_and_actual_format_mismatch(client, image_bytes):
    response = client.post(
        "/api/inspections",
        data={"scene": "dormitory"},
        files={"image": ("wrong.jpg", image_bytes("PNG"), "image/jpeg")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "图片声明类型与实际格式不一致"}


def test_valid_supported_images_are_accepted(client, image_bytes):
    cases = [
        ("JPEG", "image/jpeg", ".jpg"),
        ("PNG", "image/png", ".png"),
        ("WEBP", "image/webp", ".webp"),
    ]
    for format_name, mime, extension in cases:
        response = client.post(
            "/api/inspections",
            data={"scene": "dormitory"},
            files={"image": (f"source{extension}", image_bytes(format_name), mime)},
        )
        assert response.status_code == 200
        detail = client.get(f"/api/inspections/{response.json()['id']}").json()
        assert detail["image_path"].endswith(extension)


def test_dashboard_starts_empty(client):
    response = client.get("/api/dashboard")

    assert response.status_code == 200
    assert response.json() == {
        "total_inspections": 0,
        "total_hazards": 0,
        "risk_distribution": [],
    }
