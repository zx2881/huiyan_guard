from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .config import Settings
from .database import conn, init_db
from .knowledge.importer import import_regulations


DEMO_PREFIX = "demo-replay-"


DEMO_REPORTS: tuple[dict[str, Any], ...] = (
    {
        "key": "blocked-exit",
        "quality": "good",
        "summary": "离线历史回放示例：示意图中的门口通道被纸箱占用。",
        "uncertain": [],
        "color": "#f3d8c7",
        "hazards": [
            {
                "name": "疏散通道堵塞",
                "location": "宿舍门口",
                "evidence": "示意图中门口通行区域堆放纸箱",
                "risk": "high",
                "risk_reason": "通行受阻可能影响紧急疏散，需现场确认实际宽度。",
                "priority": "立即处理",
                "deadline": "立即清理并现场复核",
                "advice": "移走门口堆放物，保持疏散通道和安全出口畅通。",
                "manual_checks": ["确认通道实际宽度", "确认安全出口可以正常开启"],
                "regulation_id": "moe-fire-16-3",
            }
        ],
    },
    {
        "key": "uncertain-dark",
        "quality": "poor",
        "summary": "离线历史回放示例：画面过暗，未形成明确隐患结论。",
        "uncertain": ["插座区域过暗", "床下区域被遮挡"],
        "color": "#30343b",
        "hazards": [],
    },
    {
        "key": "covered-strip",
        "quality": "fair",
        "summary": "离线历史回放示例：示意图中的插线板被织物覆盖。",
        "uncertain": ["无法从示意图确认插线板额定功率"],
        "color": "#e8dec8",
        "hazards": [
            {
                "name": "插线板被覆盖",
                "location": "书桌下方",
                "evidence": "示意图中织物覆盖插线板及部分电源线",
                "risk": "medium",
                "risk_reason": "覆盖可能影响散热并遮挡线路状态。",
                "priority": "尽快处理",
                "deadline": "当日完成",
                "advice": "移除覆盖物，整理电源线，并由现场人员检查插线板和插头状态。",
                "manual_checks": ["检查插线板是否发热", "核对额定功率和负载"],
                "regulation_id": "fire-law-27",
            }
        ],
    },
    {
        "key": "multi-hazard",
        "quality": "good",
        "summary": "离线历史回放示例：示意图同时展示通道堆物和明火。",
        "uncertain": [],
        "color": "#f1e2cf",
        "hazards": [
            {
                "name": "疏散通道堵塞",
                "location": "宿舍门口",
                "evidence": "示意图中两个箱体占用门口区域",
                "risk": "high",
                "risk_reason": "通道障碍可能影响疏散。",
                "priority": "立即处理",
                "deadline": "立即清理并复核",
                "advice": "立即移走门口箱体，恢复通道畅通。",
                "manual_checks": ["确认清理后通道畅通"],
                "regulation_id": "fire-law-28",
            },
            {
                "name": "宿舍内使用明火",
                "location": "桌面",
                "evidence": "示意图中桌面存在点燃的蜡烛",
                "risk": "high",
                "risk_reason": "明火邻近可燃物，存在火灾风险。",
                "priority": "立即处理",
                "deadline": "立即熄灭并现场复核",
                "advice": "立即熄灭明火，清理附近可燃物，并按宿舍制度处理。",
                "manual_checks": ["确认火源完全熄灭", "检查附近是否有灼烧痕迹"],
                "regulation_id": "moe-fire-22-1",
            },
        ],
    },
)


def seed_demo_reports(settings: Settings) -> list[int]:
    """Create four idempotent, visibly marked offline replay reports."""

    init_db(settings)
    import_regulations(settings=settings)
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    ids: list[int] = []
    with conn(settings) as database:
        for offset, report in enumerate(DEMO_REPORTS):
            image_name = f"{DEMO_PREFIX}{report['key']}.jpg"
            existing = database.execute(
                "SELECT id FROM inspections WHERE mode='replay' AND image_path=?",
                (image_name,),
            ).fetchone()
            image_path = settings.upload_path / image_name
            if not image_path.is_file():
                _draw_demo_image(image_path, report, offset)
            if existing:
                ids.append(existing["id"])
                continue

            created_at = f"2026-09-{13 + offset:02d}T09:00:00+00:00"
            model_info = {
                "vision_provider": "offline_replay",
                "text_mode": "historical_seed",
                "ai_review": "disabled",
                "synthetic_image": True,
            }
            inspection_id = database.execute(
                """INSERT INTO inspections(
                    scene,image_path,status,created_at,completed_at,current_step,
                    progress,started_at,mode,model_info,review_status,summary,
                    image_quality,uncertain_items
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "dormitory",
                    image_name,
                    "completed",
                    created_at,
                    created_at,
                    "completed",
                    100,
                    created_at,
                    "replay",
                    json.dumps(model_info, ensure_ascii=False),
                    "disabled",
                    report["summary"],
                    report["quality"],
                    json.dumps(report["uncertain"], ensure_ascii=False),
                ),
            ).lastrowid
            ids.append(inspection_id)
            for hazard in report["hazards"]:
                regulation = database.execute(
                    "SELECT * FROM regulations WHERE id=?",
                    (hazard["regulation_id"],),
                ).fetchone()
                if not regulation:
                    raise RuntimeError(
                        f"离线回放引用的法规不存在：{hazard['regulation_id']}"
                    )
                original_data = {
                    "name": hazard["name"],
                    "location": hazard["location"],
                    "evidence": hazard["evidence"],
                    "risk": hazard["risk"],
                    "risk_reason": hazard["risk_reason"],
                    "priority": hazard["priority"],
                    "suggested_deadline": hazard["deadline"],
                    "advice": hazard["advice"],
                    "manual_checks": hazard["manual_checks"],
                    "confidence": None,
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
                        hazard["name"],
                        hazard["location"],
                        hazard["evidence"],
                        hazard["risk"],
                        hazard["advice"],
                        f"{regulation['document_title']} {regulation['article']}：{regulation['content']}",
                        regulation["source_url"],
                        None,
                        hazard["risk_reason"],
                        hazard["priority"],
                        hazard["deadline"],
                        json.dumps(hazard["manual_checks"], ensure_ascii=False),
                        "historical_replay",
                        "historical_replay",
                        "replay",
                        "pending",
                        json.dumps(original_data, ensure_ascii=False),
                        created_at,
                    ),
                ).lastrowid
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
                        created_at,
                    ),
                )
    return ids


def _draw_demo_image(path: Path, report: dict[str, Any], index: int) -> None:
    image = Image.new("RGB", (1280, 800), report["color"])
    draw = ImageDraw.Draw(image)
    draw.rectangle((70, 70, 1210, 730), outline="#263238", width=8)
    draw.text((100, 95), "OFFLINE HISTORICAL REPLAY", fill="#b42318")
    draw.text((100, 130), f"DEMO {index + 1}: {report['key']}", fill="#263238")
    if report["key"] in {"blocked-exit", "multi-hazard"}:
        draw.rectangle((840, 180, 1120, 700), outline="#36556b", width=12)
        draw.text((920, 205), "EXIT", fill="#36556b")
        draw.rectangle((690, 520, 900, 700), fill="#b7773c", outline="#6b3e20", width=5)
        draw.rectangle((890, 560, 1080, 700), fill="#c98b4a", outline="#6b3e20", width=5)
    if report["key"] == "covered-strip":
        draw.rectangle((360, 410, 920, 570), fill="#c8b18a", outline="#4e4033", width=6)
        draw.rectangle((500, 470, 780, 530), fill="#3f4c53")
        draw.text((555, 490), "POWER STRIP", fill="#ffffff")
    if report["key"] == "uncertain-dark":
        draw.rectangle((220, 260, 1060, 650), fill="#171a1f")
        draw.text((450, 430), "LOW LIGHT / UNCERTAIN", fill="#8e99a4")
    if report["key"] == "multi-hazard":
        draw.ellipse((260, 410, 360, 610), fill="#f59e0b", outline="#b42318", width=5)
        draw.text((220, 630), "OPEN FLAME", fill="#b42318")
    image.save(path, format="JPEG", quality=88, optimize=True)
