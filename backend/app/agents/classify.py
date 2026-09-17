from pydantic import ValidationError

from ..integrations.text_client import TextClient, TextServiceError
from ..schemas.inspection import VisualHazard
from ..schemas.workflow import RiskAssessment
from .checks import infer_check_id


HIGH_RISK_CHECKS = {
    "open_flame",
    "flammable_storage",
    "escape_obstacle",
    "ebike_battery_indoor",
}
MEDIUM_RISK_CHECKS = {
    "blocked_exit",
    "unsafe_wiring",
    "high_power_appliance",
    "fire_equipment_blocked",
    "fire_door_open",
    "socket_cover",
}


async def classify_hazard(
    hazard: VisualHazard,
    regulations: list[dict],
    client: TextClient,
    review_feedback: list[str] | None = None,
) -> RiskAssessment:
    allowed_ids = {item["id"] for item in regulations}
    if not regulations:
        return RiskAssessment(
            risk="needs_review",
            reason="未检索到可核验条款，无法自动分级，请安全管理员现场核验。",
            regulation_ids=[],
            method="rules",
        )
    if client.enabled:
        raw = await client.complete_json(
            (
                "你是校园安全报告分级器。只能使用输入中的照片证据和法规记录。"
                "风险等级是项目内部等级，不是法规处罚等级。无充分依据时使用 needs_review。"
                "如输入包含 review_feedback，只修正反馈指出的问题，不得扩展照片事实。"
                "只返回 risk、reason、regulation_ids、method，其中 method 必须为 model。"
            ),
            {
                "hazard": hazard.model_dump(),
                "regulations": [
                    {
                        "id": item["id"],
                        "article": item["article"],
                        "content": item["content"],
                    }
                    for item in regulations
                ],
                "review_feedback": review_feedback or [],
            },
        )
        try:
            result = RiskAssessment.model_validate(raw)
        except ValidationError as exc:
            raise TextServiceError("文本模型分级结果无效") from exc
        if result.method != "model" or not set(result.regulation_ids) <= allowed_ids:
            raise TextServiceError("文本模型引用了不存在的条款")
        return result

    check_id = infer_check_id(hazard)
    if check_id in HIGH_RISK_CHECKS:
        risk = "high"
    elif check_id in MEDIUM_RISK_CHECKS:
        risk = "medium"
    else:
        risk = "needs_review"
    return RiskAssessment(
        risk=risk,
        reason=(
            "依据照片可见证据和已核验条款进行项目内部规则分级；"
            "该等级不等同于法规处罚等级，仍需人工确认现场范围。"
        ),
        regulation_ids=[item["id"] for item in regulations[:3]],
        method="rules",
    )
