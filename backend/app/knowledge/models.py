from datetime import date
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator


class Regulation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,79}$")
    scene: Literal["dormitory", "laboratory"]
    document_title: str = Field(min_length=2, max_length=200)
    document_number: str = Field(min_length=1, max_length=100)
    source_file: str = Field(min_length=1, max_length=200)
    article: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=5, max_length=1000)
    source_url: AnyHttpUrl
    verified_at: date
    keywords: list[str] = Field(min_length=1, max_length=30)
    check_ids: list[str] = Field(min_length=1, max_length=20)

    @field_validator(
        "document_title",
        "document_number",
        "source_file",
        "article",
        "content",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("文本字段不得为空")
        return value

    @field_validator("keywords", "check_ids")
    @classmethod
    def clean_unique_list(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip().lower() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("列表项不得为空")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("列表项不得重复")
        return cleaned


class RegulationFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene: Literal["dormitory", "laboratory"]
    regulations: list[Regulation] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_records(self):
        ids = [item.id for item in self.regulations]
        if len(ids) != len(set(ids)):
            raise ValueError("条款 ID 不得重复")
        if any(item.scene != self.scene for item in self.regulations):
            raise ValueError("条款场景必须与文件场景一致")
        return self
