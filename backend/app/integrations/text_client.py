import json
from typing import Any

from ..config import Settings


class TextServiceError(Exception):
    """Safe text service failure without provider response details."""


class TextClient:
    """Optional OpenAI-compatible text model used behind strict agent schemas."""

    def __init__(self, settings: Settings):
        self.api_key = settings.text_api_key
        self.base_url = settings.text_base_url
        self.model = settings.text_model
        self.timeout = settings.text_request_timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.model)

    async def complete_json(self, system: str, payload: dict) -> dict:
        if not self.enabled:
            raise TextServiceError("文本模型尚未配置")
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=0,
            )
            response = await client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False),
                    },
                ],
            )
            result: Any = json.loads(response.choices[0].message.content or "{}")
        except Exception as exc:
            raise TextServiceError("文本模型调用失败") from exc
        if not isinstance(result, dict):
            raise TextServiceError("文本模型返回的数据结构无效")
        return result
