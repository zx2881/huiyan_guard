import base64
import json
import mimetypes
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class VisionClient:
    """火山引擎方舟视觉模型客户端。"""

    def __init__(self):
        self.api_key = os.getenv("ARK_API_KEY", "").strip()
        self.base_url = os.getenv(
            "ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
        ).strip()
        # 填写方舟控制台中的推理接入点 ID，通常以 ep- 开头。
        self.model = os.getenv("ARK_MODEL", "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.model)

    async def analyze(
        self, image_path: Path, scene: str, checklist: list[dict]
    ) -> dict:
        if not self.api_key:
            raise RuntimeError("未配置 ARK_API_KEY")
        if not self.model:
            raise RuntimeError("未配置 ARK_MODEL（火山方舟推理接入点 ID）")

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "未安装 openai 依赖，请执行 pip install -r requirements.txt"
            ) from exc

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
{{"image_quality":"good|poor|uncertain","hazards":[{{"name":"隐患名称","location":"照片中的具体位置","evidence":"照片中可见的客观证据","confidence":0.0}}],"uncertain_items":["无法确认的项目"]}}

要求：
1. confidence 为 0 到 1 之间的数字。
2. 照片不清晰、角度不足或无法确认时，将项目放入 uncertain_items，不要猜测。
3. 不要生成法规条款、风险等级或整改建议，这些由后续模块处理。
"""

        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        response = await client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
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
            ],
        )

        content = response.choices[0].message.content or "{}"
        data = self._parse_json(content)
        if not isinstance(data.get("hazards", []), list):
            raise ValueError("火山视觉模型返回的 hazards 不是数组")
        if not isinstance(data.get("uncertain_items", []), list):
            raise ValueError("火山视觉模型返回的 uncertain_items 不是数组")
        data.setdefault("image_quality", "uncertain")
        data.setdefault("hazards", [])
        data.setdefault("uncertain_items", [])
        return data

    @staticmethod
    def _parse_json(content: str) -> dict:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("火山视觉模型未返回合法 JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("火山视觉模型返回值不是 JSON 对象")
        return data
