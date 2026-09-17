import asyncio
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.integrations.vision_client import VisionClient
from backend.app.integrations.vision_errors import VisionNetworkError, VisionOutputError
from backend.app.schemas.inspection import VisualAnalysis


VALID_RESULT = {
    "image_quality": "good",
    "hazards": [
        {
            "name": "通道堵塞",
            "location": "门口",
            "evidence": "纸箱占用通道",
            "confidence": 0.88,
        }
    ],
    "uncertain_items": [],
    "summary": "门口可见纸箱。",
}


@pytest.mark.parametrize(
    "change",
    [
        {"image_quality": "clear"},
        {"hazards": "not-a-list"},
        {"uncertain_items": [""]},
        {"extra": "forbidden"},
        {
            "hazards": [
                {
                    "name": "通道堵塞",
                    "location": "门口",
                    "evidence": "纸箱",
                    "confidence": "0.5",
                }
            ]
        },
        {
            "hazards": [
                {
                    "name": " ",
                    "location": "门口",
                    "evidence": "纸箱",
                    "confidence": 0.5,
                }
            ]
        },
        {
            "hazards": [
                {
                    "name": "通道堵塞",
                    "location": "门口",
                    "evidence": "纸箱",
                    "confidence": 1.1,
                }
            ]
        },
    ],
)
def test_visual_analysis_rejects_invalid_structure(change):
    payload = {**VALID_RESULT, **change}
    with pytest.raises(ValidationError):
        VisualAnalysis.model_validate(payload)


def _client(retries: int = 2) -> VisionClient:
    return VisionClient(
        Settings(
            _env_file=None,
            ark_api_key="test-key",
            ark_model="ep-test",
            vision_json_retries=retries,
        )
    )


def test_markdown_json_is_parsed_and_validated():
    content = "```json\n" + __import__("json").dumps(VALID_RESULT) + "\n```"
    result = VisionClient._parse_analysis(content)
    assert result.hazards[0].name == "通道堵塞"


def test_invalid_output_is_repaired_once():
    client = _client()
    client._request = AsyncMock(
        side_effect=["not-json", __import__("json").dumps(VALID_RESULT)]
    )

    result = asyncio.run(client._analyze_with_retries(None, []))

    assert result.image_quality == "good"
    assert client._request.await_count == 2


def test_invalid_output_stops_after_configured_attempts():
    client = _client(retries=2)
    client._request = AsyncMock(return_value="not-json")

    with pytest.raises(VisionOutputError):
        asyncio.run(client._analyze_with_retries(None, []))

    assert client._request.await_count == 3


def test_network_error_is_not_retried():
    client = _client()
    client._request = AsyncMock(side_effect=VisionNetworkError("network"))

    with pytest.raises(VisionNetworkError):
        asyncio.run(client._analyze_with_retries(None, []))

    assert client._request.await_count == 1
