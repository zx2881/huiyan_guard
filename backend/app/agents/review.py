from pydantic import ValidationError

from ..integrations.text_client import TextClient, TextServiceError
from ..schemas.inspection import VisualHazard
from ..schemas.workflow import Remediation, ReportReview, RiskAssessment


async def review_report(
    hazards: list[VisualHazard],
    assessments: list[RiskAssessment],
    remediations: list[Remediation],
    regulations_by_hazard: list[list[dict]],
    client: TextClient,
) -> ReportReview:
    if not client.enabled:
        raise TextServiceError("内部复核需要已配置的文本模型")
    items = []
    for index, (hazard, assessment, remediation, regulations) in enumerate(
        zip(
            hazards,
            assessments,
            remediations,
            regulations_by_hazard,
            strict=True,
        )
    ):
        items.append(
            {
                "hazard_index": index,
                "hazard": hazard.model_dump(),
                "assessment": assessment.model_dump(),
                "remediation": remediation.model_dump(),
                "regulations": [
                    {
                        "id": item["id"],
                        "article": item["article"],
                        "content": item["content"],
                    }
                    for item in regulations
                ],
            }
        )
    raw = await client.complete_json(
        (
            "你是校园安全报告内部复核器。逐项检查照片证据是否支持隐患描述、"
            "引用条款是否来自输入且适用、项目内部风险等级是否保守、整改建议是否具体。"
            "不得补充输入外事实。可修正的问题返回 revise；证据不足或必须现场判断返回 "
            "manual_review；全部通过返回 pass。只返回 verdict、summary、findings、method，"
            "method 必须为 model。finding 的 hazard_index 必须对应输入序号。"
        ),
        {"items": items},
    )
    try:
        result = ReportReview.model_validate(raw)
    except ValidationError as exc:
        raise TextServiceError("内部复核结果无效") from exc
    if result.method != "model" or any(
        finding.hazard_index >= len(hazards) for finding in result.findings
    ):
        raise TextServiceError("内部复核引用了不存在的隐患")
    return result
