"""Create the configured visual-inference adapter in one place."""

from ..config import Settings, get_settings
from .vision_client import VisionClient
from .vision_provider import VisionAnalyzer
from .yolo_client import YoloVisionClient


def build_vision_analyzer(settings: Settings | None = None) -> VisionAnalyzer:
    settings = settings or get_settings()
    if settings.vision_provider == "yolo":
        return YoloVisionClient(settings)
    return VisionClient(settings)
