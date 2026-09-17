import asyncio
import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..config import Settings, get_settings
from ..schemas.inspection import VisualAnalysis
from .vision_errors import (
    VisionNetworkError,
    VisionOutputError,
    VisionProviderError,
    VisionTimeoutError,
)


class VisionClient:
    """火山引擎方舟视觉模型适配器。"""

    provider_name = "ark"

    def __init__(self, settings: Settings | None = None):
        settings = settings or get_settings()
        self.api_key = settings.ark_api_key
        self.base_url = settings.ark_base_url
        self.model = settings.ark_model
        self.request_timeout = settings.vision_request_timeout_seconds
        self.total_timeout = settings.vision_total_timeout_seconds
        self.json_retries = settings.vision_json_retries

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.model)

    async def analyze(
        self, image_path: Path, scene: str, checklist: list[dict]
    ) -> dict:
        if not self.api_key:
            raise VisionProviderError("视觉服务尚未配置 API Key")
        if not self.model:
            raise VisionProviderError("视觉服务尚未配置推理接入点")

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise VisionProviderError("视觉服务运行依赖尚未安装") from exc

        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            max_retries=0,
            timeout=self.request_timeout,
        )
        messages = self._initial_messages(image_path, scene, checklist)
        try:
            result = await asyncio.wait_for(
                self._analyze_with_retries(client, messages),
                timeout=self.total_timeout,
            )
        except asyncio.TimeoutError as exc:
            raise VisionTimeoutError("视觉分析超时，请稍后重试") from exc
        return result.model_dump()

    async def _analyze_with_retries(
        self, client: Any, messages: list[dict]
    ) -> VisualAnalysis:
        last_error = "模型输出不符合约定"
        last_content = ""
        for attempt in range(self.json_retries + 1):
            if attempt:
                messages = [
                    *messages,
                    {"role": "assistant", "content": last_content[:6000]},
                    {
                        "role": "user",
                        "content": (
                            "上一份输出无法通过结构校验，请修正后只返回合法 JSON。"
                            f"错误摘要：{last_error[:2000]}"
                        ),
                    },
                ]
            last_content = await self._request(client, messages)
            try:
                return self._parse_analysis(last_content)
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_error = str(exc)
        raise VisionOutputError("视觉模型连续返回了无法解析的结果")

    async def _request(self, client: Any, messages: list[dict]) -> str:
        try:
            response = await client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=messages,
            )
            return response.choices[0].message.content or "{}"
        except Exception as exc:
            from openai import APIConnectionError, APIStatusError, APITimeoutError
            if isinstance(exc, (APITimeoutError, asyncio.TimeoutError)):
                raise VisionTimeoutError("视觉服务请求超时，请稍后重试") from exc
            if isinstance(exc, APIConnectionError):
                raise VisionNetworkError("无法连接视觉服务，请检查网络后重试") from exc
            if isinstance(exc, APIStatusError):
                raise VisionProviderError("视觉服务暂时无法完成请求") from exc
            raise VisionProviderError("视觉服务调用失败") from exc

    def _initial_messages(
        self, image_path: Path, scene: str, checklist: list[dict]
    ) -> list[dict]:
        mime = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        checklist_text = "\n".join(
            f"- {item.get('id')}: {item.get('name')}：{item.get('instruction')}"
            for item in checklist
        )
        prompt = f"""你是校园安全巡检视觉分析器。检查场景：{scene}。
请严格依据下面的检查清单分析照片，只报告照片中有直接视觉证据支持的内容：
{checklist_text or '- 没有可用检查清单'}

只返回一个合法 JSON 对象，不要返回 Markdown 或其他说明：
{{"image_quality":"good|poor|uncertain","hazards":[{{"check_id":"检查清单ID或null","name":"隐患名称","location":"照片中的具体位置","evidence":"照片中可见的客观证据","confidence":0.0}}],"uncertain_items":["无法确认的项目"],"summary":"当前照片可见范围的简短客观总结"}}

要求：
1. confidence 为 0 到 1 之间的数字。
2. 照片不清晰、角度不足或无法确认时，将项目放入 uncertain_items，不要猜测。
3. 没有明确隐患时 hazards 必须为空数组，不得创建占位隐患。
4. check_id 只能使用上方检查清单中已有的 ID；无法对应时返回 null。
5. 不要生成法规条款、风险等级或整改建议，这些由后续模块处理。
"""
        return [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{encoded}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ]

    @staticmethod
    def _parse_analysis(content: str) -> VisualAnalysis:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("视觉模型返回值不是 JSON 对象")
        return VisualAnalysis.model_validate(data)
