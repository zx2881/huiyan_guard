from fastapi.testclient import TestClient
import pytest
import time

from backend.app.config import Settings
from backend.app.database import conn, init_db
from backend.app.integrations.vision_errors import (
    VisionNetworkError,
    VisionTimeoutError,
)
from backend.app.main import create_app
import backend.app.main as main_module


class FakeAnalyzer:
    provider_name = "test"
    enabled = True

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    async def analyze(self, image_path, scene, checklist):
        if self.error:
            raise self.error
        return self.result


def wait_for_terminal(client, inspection_id: int) -> dict:
    for _ in range(100):
        detail = client.get(f"/api/inspections/{inspection_id}").json()
        if detail["status"] in {"completed", "failed"}:
            return detail
        time.sleep(0.01)
    raise AssertionError("workflow did not reach a terminal state")


def test_visual_result_is_persisted_without_placeholder_hazard(
    client, monkeypatch, image_bytes
):
    analyzer = FakeAnalyzer(
        {
            "image_quality": "poor",
            "hazards": [],
            "uncertain_items": ["插座区域被遮挡"],
            "summary": "照片较暗，未发现明确隐患。",
        }
    )
    monkeypatch.setattr(main_module, "build_vision_analyzer", lambda _settings: analyzer)

    response = client.post(
        "/api/inspections",
        data={"scene": "dormitory"},
        files={"image": ("room.jpg", image_bytes(), "image/jpeg")},
    )

    assert response.status_code == 202
    detail = wait_for_terminal(client, response.json()["id"])
    assert detail["image_quality"] == "poor"
    assert detail["uncertain_items"] == ["插座区域被遮挡"]
    assert detail["summary"] == "照片较暗，未发现明确隐患。"
    assert detail["hazards"] == []
    assert client.get("/api/dashboard").json()["total_hazards"] == 0


@pytest.mark.parametrize(
    "error",
    [
        VisionTimeoutError("视觉分析超时，请稍后重试"),
        VisionNetworkError("无法连接视觉服务，请检查网络后重试"),
    ],
)
def test_vision_failures_have_stable_status_and_failed_record(
    client, monkeypatch, image_bytes, error
):
    analyzer = FakeAnalyzer(error=error)
    monkeypatch.setattr(main_module, "build_vision_analyzer", lambda _settings: analyzer)

    response = client.post(
        "/api/inspections",
        data={"scene": "dormitory"},
        files={"image": ("room.jpg", image_bytes(), "image/jpeg")},
    )

    assert response.status_code == 202
    detail = wait_for_terminal(client, response.json()["id"])
    assert detail["status"] == "failed"
    assert detail["error"] == str(error)


def test_full_workflow_saves_risk_advice_and_regulation_snapshots(
    client, monkeypatch, image_bytes, isolated_settings
):
    analyzer = FakeAnalyzer(
        {
            "image_quality": "good",
            "hazards": [
                {
                    "name": "疏散通道堵塞",
                    "location": "宿舍门口",
                    "evidence": "多个纸箱堆放在门口通道",
                    "confidence": 0.91,
                }
            ],
            "uncertain_items": [],
            "summary": "宿舍门口通道被纸箱占用。",
        }
    )
    monkeypatch.setattr(main_module, "build_vision_analyzer", lambda _settings: analyzer)

    response = client.post(
        "/api/inspections",
        data={"scene": "dormitory"},
        files={"image": ("room.jpg", image_bytes(), "image/jpeg")},
    )
    detail = wait_for_terminal(client, response.json()["id"])

    assert response.status_code == 202
    assert detail["status"] == "completed"
    assert detail["current_step"] == "completed"
    assert detail["progress"] == 100
    assert detail["model_info"] == {
        "vision_provider": "test",
        "text_mode": "rules",
        "ai_review": "disabled",
    }
    assert len(detail["hazards"]) == 1
    hazard = detail["hazards"][0]
    assert hazard["risk"] == "medium"
    assert hazard["classification_method"] == "rules"
    assert hazard["remediation_method"] == "rules"
    assert "移走" in hazard["advice"]
    assert hazard["confidence"] == pytest.approx(0.91)
    assert hazard["regulations"]
    assert all(item["source_url"].startswith("https://") for item in hazard["regulations"])
    snapshot_content = hazard["regulations"][0]["content"]
    with conn(isolated_settings) as database:
        database.execute(
            "UPDATE regulations SET content='updated knowledge' WHERE id=?",
            (hazard["regulations"][0]["regulation_id"],),
        )
    refreshed = client.get(f"/api/inspections/{detail['id']}").json()
    assert refreshed["hazards"][0]["regulations"][0]["content"] == snapshot_content


def test_failed_workflow_can_retry_once_configuration_is_available(
    client, monkeypatch, image_bytes
):
    class FlakyAnalyzer(FakeAnalyzer):
        provider_name = "test"

        def __init__(self):
            super().__init__()
            self.calls = 0

        async def analyze(self, image_path, scene, checklist):
            self.calls += 1
            if self.calls == 1:
                raise VisionNetworkError("视觉服务暂时不可用")
            return {
                "image_quality": "good",
                "hazards": [],
                "uncertain_items": [],
                "summary": "重试后完成。",
            }

    analyzer = FlakyAnalyzer()
    monkeypatch.setattr(main_module, "build_vision_analyzer", lambda _settings: analyzer)
    response = client.post(
        "/api/inspections",
        data={"scene": "dormitory"},
        files={"image": ("room.jpg", image_bytes(), "image/jpeg")},
    )
    inspection_id = response.json()["id"]
    assert wait_for_terminal(client, inspection_id)["status"] == "failed"

    retry = client.post(f"/api/inspections/{inspection_id}/retry")
    completed = wait_for_terminal(client, inspection_id)

    assert retry.status_code == 202
    assert completed["status"] == "completed"
    assert completed["retry_count"] == 1
    assert completed["summary"] == "重试后完成。"


def test_startup_marks_interrupted_work_as_failed(isolated_settings):
    init_db(isolated_settings)
    with conn(isolated_settings) as database:
        inspection_id = database.execute(
            """INSERT INTO inspections(
                scene,image_path,status,created_at,current_step,progress,mode
            ) VALUES(?,?,?,?,?,?,?)""",
            ("dormitory", "missing.jpg", "retrieving", "2026-09-17", "retrieving", 45, "vision"),
        ).lastrowid

    with TestClient(main_module.create_app(isolated_settings)) as restarted:
        detail = restarted.get(f"/api/inspections/{inspection_id}").json()

    assert detail["status"] == "failed"
    assert detail["current_step"] == "failed"
    assert "服务重启" in detail["error"]


def test_upload_byte_and_pixel_limits(tmp_path, image_bytes):
    base = {
        "_env_file": None,
        "database_url": f"sqlite:///{(tmp_path / 'app.db').as_posix()}",
        "upload_dir": (tmp_path / "uploads").as_posix(),
    }
    byte_settings = Settings(**base, max_upload_bytes=20)
    with TestClient(create_app(byte_settings)) as client:
        response = client.post(
            "/api/inspections",
            data={"scene": "dormitory"},
            files={"image": ("room.jpg", image_bytes(), "image/jpeg")},
        )
        assert response.status_code == 413
        assert client.get("/api/inspections").json() == []

    pixel_settings = Settings(**base, max_image_pixels=100)
    with TestClient(create_app(pixel_settings)) as client:
        response = client.post(
            "/api/inspections",
            data={"scene": "dormitory"},
            files={"image": ("room.jpg", image_bytes(size=(20, 20)), "image/jpeg")},
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "图片像素尺寸超过限制"}
        assert client.get("/api/inspections").json() == []
