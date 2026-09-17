from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class VisualHazard(StrictModel):
    check_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{2,79}$")
    name: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=200)
    evidence: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)

    @field_validator("name", "location", "evidence")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("文本不得为空")
        return value


class VisualAnalysis(StrictModel):
    image_quality: Literal["good", "poor", "uncertain"]
    hazards: list[VisualHazard]
    uncertain_items: list[str]
    summary: str | None = Field(default=None, max_length=500)

    @field_validator("uncertain_items")
    @classmethod
    def validate_uncertain_items(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            value = value.strip()
            if not value:
                raise ValueError("不确定项不得为空")
            if len(value) > 200:
                raise ValueError("不确定项长度不得超过 200 个字符")
            cleaned.append(value)
        return cleaned

    @field_validator("summary")
    @classmethod
    def strip_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None
