"""Reserved local YOLO inference adapter.

TODO(YOLO): This file is intentionally a placeholder. When model weights, class
labels, and the inference runtime are ready, implement ``analyze`` so it returns
the same structure as the existing ARK adapter:

{
    "image_quality": "good|poor|uncertain",
    "hazards": [
        {"check_id": "...", "name": "...", "location": "...", "evidence": "...", "confidence": 0.0}
    ],
    "uncertain_items": ["..."],
    "summary": "...",
}

Raw YOLO boxes and class IDs must be mapped to checklist ``check_id`` values here. They
must not be exposed directly to routes, reports, or later regulation matching.
"""

from pathlib import Path

from ..config import Settings


class YoloVisionClient:
    """YOLO adapter boundary; not an inference implementation yet."""

    provider_name = "yolo"

    def __init__(self, settings: Settings):
        self.model_path = settings.yolo_model_path
        self.device = settings.yolo_device
        self.confidence_threshold = settings.yolo_confidence_threshold
        self.input_size = settings.yolo_input_size

    @property
    def enabled(self) -> bool:
        # TODO(YOLO): Return True only after weights and a compatible runtime load.
        return False

    async def analyze(
        self, image_path: Path, scene: str, checklist: list[dict]
    ) -> dict:
        raise RuntimeError(
            "已选择 YOLO 视觉提供方，但本地 YOLO 推理适配器尚未实现；"
            "请完成 backend/app/integrations/yolo_client.py 中的 TODO(YOLO)。"
        )
