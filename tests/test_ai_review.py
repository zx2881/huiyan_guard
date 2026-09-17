import asyncio
import time

from fastapi.testclient import TestClient
import pytest

from backend.app.agents.review import review_report
from backend.app.integrations.text_client import TextServiceError
from backend.app.main import create_app
from backend.app.schemas.inspection import VisualHazard
from backend.app.schemas.workflow import Remediation, RiskAssessment
import backend.app.main as main_module
import backend.app.workflow.runner as runner_module


class FakeAnalyzer:
    provider_name = "test"
    enabled = True

    async def analyze(self, image_path, scene, checklist):
        return {
            "image_quality": "good",
            "hazards": [
                {
                    "check_id": "escape_obstacle",
                    "name": "疏散通道堵塞",
                    "location": "宿舍门口",
                    "evidence": "纸箱占用通道",
                    "confidence": 0.92,
                }
            ],
            "uncertain_items": [],
            "summary": "门口通道存在堆物。",
        }


class RevisingTextClient:
    review_calls = 0
    final_verdict = "pass"

    def __init__(self, settings):
        self.enabled = True

    async def complete_json(self, system, payload):
        if "分级器" in system:
            return {
                "risk": "high",
                "reason": "根据照片证据和输入条款进行项目内部判断。",
                "regulation_ids": [payload["regulations"][0]["id"]],
                "method": "model",
            }
        if "整改建议生成器" in system:
            revised = bool(payload.get("review_feedback"))
            return {
                "advice": "立即清理纸箱并复查通道宽度。" if revised else "清理纸箱。",
                "priority": "immediate",
                "suggested_deadline": "立即",
                "manual_checks": ["确认通道恢复畅通"],
                "method": "model",
            }
        if "内部复核器" in system:
            type(self).review_calls += 1
            if type(self).review_calls == 1:
                return {
                    "verdict": "revise",
                    "summary": "整改建议需要补充复查要求。",
                    "findings": [
                        {
                            "hazard_index": 0,
                            "area": "advice",
                            "message": "补充清理后的通道复查。",
                        }
                    ],
                    "method": "model",
                }
            if type(self).final_verdict == "pass":
                return {
                    "verdict": "pass",
                    "summary": "修正后的报告通过内部复核。",
                    "findings": [],
                    "method": "model",
                }
            return {
                "verdict": "revise",
                "summary": "第二次复核仍未通过。",
                "findings": [
                    {
                        "hazard_index": 0,
                        "area": "advice",
                        "message": "仍需人工判断。",
                    }
                ],
                "method": "model",
            }
        raise AssertionError("unexpected prompt")


def wait_for_terminal(client, inspection_id: int) -> dict:
    for _ in range(100):
        detail = client.get(f"/api/inspections/{inspection_id}").json()
        if detail["status"] in {"completed", "failed"}:
            return detail
        time.sleep(0.01)
    raise AssertionError("workflow did not finish")


def test_internal_review_redoes_once_and_persists_result(
    isolated_settings, monkeypatch, image_bytes
):
    settings = isolated_settings.model_copy(
        update={
            "enable_ai_review": True,
            "text_api_key": "test-key",
            "text_model": "test-model",
        }
    )
    RevisingTextClient.review_calls = 0
    RevisingTextClient.final_verdict = "pass"
    monkeypatch.setattr(main_module, "build_vision_analyzer", lambda _settings: FakeAnalyzer())
    monkeypatch.setattr(runner_module, "TextClient", RevisingTextClient)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/inspections",
            data={"scene": "dormitory"},
            files={"image": ("room.jpg", image_bytes(), "image/jpeg")},
        )
        detail = wait_for_terminal(client, response.json()["id"])

    assert detail["status"] == "completed"
    assert detail["review_status"] == "revised_passed"
    assert detail["review_attempts"] == 2
    assert detail["review_redo_count"] == 1
    assert detail["review_findings"][0]["attempt"] == 1
    assert detail["model_info"]["ai_review"] == "revised_passed"
    assert "复查通道宽度" in detail["hazards"][0]["advice"]
    assert RevisingTextClient.review_calls == 2


def test_internal_review_stops_after_one_redo():
    hazard = VisualHazard(
        check_id="escape_obstacle",
        name="通道堵塞",
        location="门口",
        evidence="纸箱占用通道",
        confidence=0.9,
    )
    assessment = RiskAssessment(
        risk="high",
        reason="内部判断",
        regulation_ids=["rule-1"],
        method="model",
    )
    remediation = Remediation(
        advice="清理通道",
        priority="immediate",
        suggested_deadline="立即",
        manual_checks=[],
        method="model",
    )
    regulations = [[{"id": "rule-1", "article": "第一条", "content": "保持畅通"}]]
    RevisingTextClient.review_calls = 0
    RevisingTextClient.final_verdict = "revise"

    result = asyncio.run(
        runner_module._run_internal_review(
            [hazard],
            [assessment],
            [remediation],
            regulations,
            RevisingTextClient(None),
        )
    )

    assert result[2] == "manual_required"
    assert result[5] == 2
    assert result[6] == 1
    assert RevisingTextClient.review_calls == 2


def test_review_rejects_nonexistent_hazard_index():
    class BadReviewer:
        enabled = True

        async def complete_json(self, system, payload):
            return {
                "verdict": "manual_review",
                "summary": "需要人工处理。",
                "findings": [
                    {"hazard_index": 9, "area": "evidence", "message": "索引错误"}
                ],
                "method": "model",
            }

    hazard = VisualHazard(
        check_id="escape_obstacle",
        name="通道堵塞",
        location="门口",
        evidence="纸箱占用通道",
        confidence=0.9,
    )
    assessment = RiskAssessment(
        risk="high",
        reason="内部判断",
        regulation_ids=["rule-1"],
        method="model",
    )
    remediation = Remediation(
        advice="清理通道",
        priority="immediate",
        suggested_deadline="立即",
        manual_checks=[],
        method="model",
    )
    regulations = [[{"id": "rule-1", "article": "第一条", "content": "保持畅通"}]]

    with pytest.raises(TextServiceError, match="不存在的隐患"):
        asyncio.run(
            review_report(
                [hazard], [assessment], [remediation], regulations, BadReviewer()
            )
        )
