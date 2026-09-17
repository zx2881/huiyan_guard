import asyncio

import pytest

from backend.app.agents.classify import classify_hazard
from backend.app.agents.remediate import remediate_hazard
from backend.app.config import Settings
from backend.app.integrations.text_client import TextClient, TextServiceError
from backend.app.schemas.inspection import VisualHazard


def _hazard(**changes) -> VisualHazard:
    payload = {
        "check_id": "open_flame",
        "name": "宿舍内存在明火",
        "location": "书桌",
        "evidence": "桌面可见点燃的蜡烛",
        "confidence": 0.9,
    }
    return VisualHazard.model_validate({**payload, **changes})


def _rules_client() -> TextClient:
    return TextClient(Settings(_env_file=None))


def test_rules_require_manual_review_without_regulation():
    assessment = asyncio.run(classify_hazard(_hazard(), [], _rules_client()))
    remediation = asyncio.run(
        remediate_hazard(_hazard(), assessment, [], _rules_client())
    )

    assert assessment.risk == "needs_review"
    assert assessment.regulation_ids == []
    assert remediation.priority == "manual_review"


def test_rules_produce_conservative_action_with_verified_regulation():
    regulations = [
        {
            "id": "rule-1",
            "article": "第二十二条",
            "content": "禁止使用明火",
            "check_ids": ["open_flame"],
        }
    ]

    assessment = asyncio.run(
        classify_hazard(_hazard(), regulations, _rules_client())
    )
    remediation = asyncio.run(
        remediate_hazard(_hazard(), assessment, regulations, _rules_client())
    )

    assert assessment.risk == "high"
    assert "法规处罚等级" in assessment.reason
    assert remediation.priority == "immediate"
    assert "熄灭" in remediation.advice


def test_model_cannot_invent_regulation_id():
    class FakeTextClient:
        enabled = True

        async def complete_json(self, system, payload):
            return {
                "risk": "high",
                "reason": "测试",
                "regulation_ids": ["invented-rule"],
                "method": "model",
            }

    with pytest.raises(TextServiceError, match="不存在的条款"):
        asyncio.run(
            classify_hazard(
                _hazard(),
                [{"id": "real-rule", "article": "一", "content": "正文"}],
                FakeTextClient(),
            )
        )
