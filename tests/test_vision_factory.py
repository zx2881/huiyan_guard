import asyncio

import pytest

from backend.app.config import Settings
from backend.app.integrations.vision_client import VisionClient
from backend.app.integrations.vision_factory import build_vision_analyzer
from backend.app.integrations.yolo_client import YoloVisionClient


def test_factory_returns_ark_adapter_by_default():
    analyzer = build_vision_analyzer(Settings(_env_file=None))

    assert isinstance(analyzer, VisionClient)
    assert analyzer.provider_name == "ark"
    assert not analyzer.enabled


def test_factory_reserves_yolo_adapter_without_loading_a_runtime():
    analyzer = build_vision_analyzer(
        Settings(
            _env_file=None,
            vision_provider="yolo",
            yolo_model_path="weights/best.pt",
            yolo_device="cpu",
        )
    )

    assert isinstance(analyzer, YoloVisionClient)
    assert analyzer.provider_name == "yolo"
    assert not analyzer.enabled
    with pytest.raises(RuntimeError, match="YOLO 推理适配器尚未实现"):
        asyncio.run(analyzer.analyze(__file__, "dormitory", []))
