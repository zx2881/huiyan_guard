import json
from pathlib import Path

from ..integrations.vision_client import VisionClient


def load_checklist(base: Path, scene: str) -> list[dict]:
    path = base / "knowledge" / scene / "checklist.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("items", [])


async def perceive(base: Path, image_path: Path, scene: str) -> dict:
    checklist = load_checklist(base, scene)
    return await VisionClient().analyze(image_path, scene, checklist)
