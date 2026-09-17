from datetime import datetime, timezone
import json
from pathlib import Path

from ..agents.classify import classify_hazard
from ..agents.checks import infer_check_id
from ..agents.perceive import perceive
from ..agents.remediate import remediate_hazard
from ..config import REPO_ROOT, Settings
from ..database import conn
from ..integrations.text_client import TextClient, TextServiceError
from ..integrations.vision_errors import VisionError
from ..integrations.vision_provider import VisionAnalyzer
from ..knowledge.retriever import retrieve_regulations


STEPS = {
    "queued": 0,
    "perceiving": 15,
    "retrieving": 45,
    "classifying": 65,
    "remediating": 80,
    "completed": 100,
    "failed": 100,
}


def update_step(
    settings: Settings,
    inspection_id: int,
    step: str,
    *,
    error: str | None = None,
) -> None:
    with conn(settings) as database:
        database.execute(
            "UPDATE inspections SET status=?,current_step=?,progress=?,error=? WHERE id=?",
            (step, step, STEPS[step], error, inspection_id),
        )


async def run_inspection_workflow(
    inspection_id: int,
    settings: Settings,
    vision: VisionAnalyzer,
) -> None:
    text_client = TextClient(settings)
    try:
        with conn(settings) as database:
            inspection = database.execute(
                "SELECT * FROM inspections WHERE id=?", (inspection_id,)
            ).fetchone()
            if not inspection:
                return
            image_path = settings.upload_path / inspection["image_path"]
            scene = inspection["scene"]
            old_hazards = database.execute(
                "SELECT id FROM hazards WHERE inspection_id=?", (inspection_id,)
            ).fetchall()
            for row in old_hazards:
                database.execute(
                    "DELETE FROM regulation_snapshots WHERE hazard_id=?", (row["id"],)
                )
            database.execute(
                "DELETE FROM hazards WHERE inspection_id=?", (inspection_id,)
            )

        update_step(settings, inspection_id, "perceiving")
        visual = await perceive(REPO_ROOT, image_path, scene, vision)
        summary = visual.summary or (
            "当前照片可见范围内发现了明确隐患。"
            if visual.hazards
            else "当前照片可见范围内未发现明确隐患。"
        )
        with conn(settings) as database:
            database.execute(
                "UPDATE inspections SET image_quality=?,uncertain_items=?,summary=? "
                "WHERE id=?",
                (
                    visual.image_quality,
                    json.dumps(visual.uncertain_items, ensure_ascii=False),
                    summary,
                    inspection_id,
                ),
            )

        update_step(settings, inspection_id, "retrieving")
        regulations_by_hazard = [
            retrieve_regulations(
                scene,
                f"{hazard.name} {hazard.location} {hazard.evidence}",
                check_id=infer_check_id(hazard),
                settings=settings,
                limit=5,
            )
            for hazard in visual.hazards
        ]

        update_step(settings, inspection_id, "classifying")
        assessments = [
            await classify_hazard(hazard, regulations, text_client)
            for hazard, regulations in zip(
                visual.hazards, regulations_by_hazard, strict=True
            )
        ]

        update_step(settings, inspection_id, "remediating")
        remediations = [
            await remediate_hazard(hazard, assessment, regulations, text_client)
            for hazard, assessment, regulations in zip(
                visual.hazards,
                assessments,
                regulations_by_hazard,
                strict=True,
            )
        ]

        completed_at = datetime.now(timezone.utc).isoformat()
        with conn(settings) as database:
            for hazard, regulations, assessment, remediation in zip(
                visual.hazards,
                regulations_by_hazard,
                assessments,
                remediations,
                strict=True,
            ):
                selected = [
                    item
                    for item in regulations
                    if item["id"] in assessment.regulation_ids
                ]
                first = selected[0] if selected else None
                initial_data = {
                    "name": hazard.name,
                    "location": hazard.location,
                    "evidence": hazard.evidence,
                    "risk": assessment.risk,
                    "risk_reason": assessment.reason,
                    "priority": remediation.priority,
                    "suggested_deadline": remediation.suggested_deadline,
                    "advice": remediation.advice,
                    "manual_checks": remediation.manual_checks,
                    "confidence": hazard.confidence,
                }
                hazard_id = database.execute(
                    """INSERT INTO hazards(
                        inspection_id,name,location,evidence,risk,advice,regulation,
                        source_url,confidence,risk_reason,priority,suggested_deadline,
                        manual_checks,classification_method,remediation_method,
                        source,human_status,original_data,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        inspection_id,
                        hazard.name,
                        hazard.location,
                        hazard.evidence,
                        assessment.risk,
                        remediation.advice,
                        (
                            f"{first['document_title']} {first['article']}："
                            f"{first['content']}"
                            if first
                            else "未检索到适用条款，请人工核验"
                        ),
                        first["source_url"] if first else "",
                        hazard.confidence,
                        assessment.reason,
                        remediation.priority,
                        remediation.suggested_deadline,
                        json.dumps(remediation.manual_checks, ensure_ascii=False),
                        assessment.method,
                        remediation.method,
                        "ai",
                        "pending",
                        json.dumps(initial_data, ensure_ascii=False),
                        completed_at,
                    ),
                ).lastrowid
                for regulation in selected:
                    database.execute(
                        """INSERT INTO regulation_snapshots(
                            inspection_id,hazard_id,regulation_id,document_title,
                            document_number,article,content,source_url,retrieved_at
                        ) VALUES(?,?,?,?,?,?,?,?,?)""",
                        (
                            inspection_id,
                            hazard_id,
                            regulation["id"],
                            regulation["document_title"],
                            regulation["document_number"],
                            regulation["article"],
                            regulation["content"],
                            regulation["source_url"],
                            completed_at,
                        ),
                    )
            database.execute(
                """UPDATE inspections SET
                    status='completed',current_step='completed',progress=100,
                    completed_at=?,error=NULL,model_info=? WHERE id=?""",
                (
                    completed_at,
                    json.dumps(
                        {
                            "vision_provider": vision.provider_name,
                            "text_mode": "model" if text_client.enabled else "rules",
                        },
                        ensure_ascii=False,
                    ),
                    inspection_id,
                ),
            )
    except (VisionError, TextServiceError) as exc:
        update_step(settings, inspection_id, "failed", error=str(exc)[:500])
    except Exception:
        update_step(
            settings,
            inspection_id,
            "failed",
            error="分析流程出现内部错误，请重试或联系管理员",
        )


def mark_interrupted_workflows(settings: Settings) -> int:
    active = ("queued", "analyzing", "perceiving", "retrieving", "classifying", "remediating")
    placeholders = ",".join("?" for _ in active)
    with conn(settings) as database:
        cursor = database.execute(
            f"""UPDATE inspections SET
                status='failed',current_step='failed',progress=100,
                error='服务重启导致分析中断，请点击重试'
                WHERE status IN ({placeholders})""",
            active,
        )
    return cursor.rowcount
