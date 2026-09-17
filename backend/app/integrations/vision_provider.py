"""Provider-neutral contract for visual inference.

TODO(YOLO): A YOLO adapter must convert detections into this contract. The rest of
the application must not depend on a provider SDK or raw bounding-box format.
"""

from pathlib import Path
from typing import Protocol


class VisionAnalyzer(Protocol):
    provider_name: str

    @property
    def enabled(self) -> bool:
        """Whether this adapter can perform real inference now."""

    async def analyze(
        self, image_path: Path, scene: str, checklist: list[dict]
    ) -> dict:
        """Return the provider-neutral visual-analysis dictionary."""
