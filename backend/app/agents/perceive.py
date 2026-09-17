import json
from pathlib import Path

from pydantic import ValidationError

from ..config import get_settings
from ..integrations.vision_factory import build_vision_analyzer
from ..integrations.vision_provider import VisionAnalyzer
from ..integrations.vision_errors import VisionOutputError
from ..schemas.inspection import VisualAnalysis


def load_checklist(base: Path, scene: str) -> list[dict]:
    path = base / "knowledge" / scene / "checklist.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("items", [])


async def perceive(
    base: Path,
    image_path: Path,
    scene: str,
    client: VisionAnalyzer | None = None,
) -> VisualAnalysis:
    checklist = load_checklist(base, scene)
    analyzer = client or build_vision_analyzer(get_settings())
    raw_result = await analyzer.analyze(image_path, scene, checklist)
    try:
        result = VisualAnalysis.model_validate(raw_result)
    except ValidationError as exc:
        raise VisionOutputError("视觉模型返回的数据结构无效") from exc
    allowed_ids = {item.get("id") for item in checklist}
    if any(
        hazard.check_id is not None and hazard.check_id not in allowed_ids
        for hazard in result.hazards
    ):
        raise VisionOutputError("视觉模型返回了不存在的检查项 ID")
    return result
