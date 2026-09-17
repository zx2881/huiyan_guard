from pydantic import ValidationError

from ..integrations.text_client import TextClient, TextServiceError
from ..schemas.inspection import VisualHazard
from ..schemas.workflow import Remediation, RiskAssessment
from .checks import infer_check_id


RULES = {
    "blocked_exit": ("立即移走通道和出口处的物品，恢复完整通行宽度并复查。", "immediate", "立即"),
    "unsafe_wiring": ("立即停止使用相关线路或插排，由具备资质的人员检查并规范布线。", "immediate", "立即"),
    "high_power_appliance": ("立即断电并停止使用违规发热电器，按本校宿舍制度处理。", "immediate", "立即"),
    "socket_cover": ("移除插线板周围覆盖物并断电检查，确认无发热、破损后再决定是否使用。", "high", "当日"),
    "open_flame": ("立即熄灭并移除明火源，清理可燃物，同时开展现场复查。", "immediate", "立即"),
    "flammable_storage": ("立即隔离危险物品并通知宿舍管理人员，按学校危险品制度转移处置。", "immediate", "立即"),
    "fire_equipment_blocked": ("立即清除消防设施前的遮挡物，核对器材在位和外观状态。", "immediate", "立即"),
    "escape_obstacle": ("立即报告宿舍管理部门，移除影响逃生和灭火救援的障碍物。", "immediate", "立即"),
    "fire_door_open": ("移除固定防火门的物品，使常闭式防火门恢复正常关闭。", "high", "当日"),
    "ebike_battery_indoor": ("立即停止室内充电，将车辆或电池转移至学校指定的集中停放充电区域。", "immediate", "立即"),
}


async def remediate_hazard(
    hazard: VisualHazard,
    assessment: RiskAssessment,
    regulations: list[dict],
    client: TextClient,
) -> Remediation:
    if not regulations:
        return Remediation(
            advice="请安全管理员结合现场检查清单核实该项，并记录采取的整改措施。",
            priority="manual_review",
            suggested_deadline="人工核验后确定",
            manual_checks=["确认隐患类型和影响范围", "确认是否存在适用的校级制度"],
            method="rules",
        )
    if client.enabled:
        raw = await client.complete_json(
            (
                "你是校园安全整改建议生成器。建议必须具体、可执行，不得编造法规期限。"
                "suggested_deadline 只能表述项目建议时间，manual_checks 列出需现场核实内容。"
                "只返回 advice、priority、suggested_deadline、manual_checks、method，method 必须为 model。"
            ),
            {
                "hazard": hazard.model_dump(),
                "assessment": assessment.model_dump(),
                "regulations": [
                    {"id": item["id"], "content": item["content"]}
                    for item in regulations
                ],
            },
        )
        try:
            result = Remediation.model_validate(raw)
        except ValidationError as exc:
            raise TextServiceError("文本模型整改建议结果无效") from exc
        if result.method != "model":
            raise TextServiceError("文本模型整改建议缺少正确方法标识")
        return result

    check_id = infer_check_id(hazard)
    if check_id in RULES and regulations:
        advice, priority, deadline = RULES[check_id]
        return Remediation(
            advice=advice,
            priority=priority,
            suggested_deadline=deadline,
            manual_checks=["核实照片外区域是否存在同类问题", "整改后由宿舍管理人员复查"],
            method="rules",
        )
    return Remediation(
        advice="已检索到相关条款，但无法匹配预设整改模板，请安全管理员现场核验。",
        priority="manual_review",
        suggested_deadline="人工核验后确定",
        manual_checks=["确认隐患类型和影响范围", "制定与条款一致的整改措施"],
        method="rules",
    )
