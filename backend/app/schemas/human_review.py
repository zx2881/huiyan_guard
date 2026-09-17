from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Risk = Literal["low", "medium", "high", "needs_review"]
Priority = Literal["immediate", "high", "normal", "manual_review"]
HumanStatus = Literal["pending", "confirmed", "corrected", "rejected"]


class ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("name", "location", "evidence", "advice", "risk_reason", check_fields=False)
    @classmethod
    def clean_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("隐患字段不得为空")
        return value


class HazardUpdate(ReviewModel):
    name: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=300)
    evidence: str | None = Field(default=None, max_length=1000)
    risk: Risk | None = None
    risk_reason: str | None = Field(default=None, max_length=500)
    priority: Priority | None = None
    suggested_deadline: str | None = Field(default=None, max_length=100)
    advice: str | None = Field(default=None, max_length=1000)
    manual_checks: list[str] | None = Field(default=None, max_length=10)
    human_status: HumanStatus | None = None
    note: str | None = Field(default=None, max_length=500)

    @field_validator("suggested_deadline", "note")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        return value or None

    @field_validator("manual_checks")
    @classmethod
    def clean_checks(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        cleaned = [item.strip() for item in value if item.strip()]
        if any(len(item) > 300 for item in cleaned):
            raise ValueError("人工核验项过长")
        return cleaned

    @model_validator(mode="after")
    def require_change(self):
        changed = self.model_fields_set - {"note"}
        if not changed:
            raise ValueError("至少需要确认状态或修改一个字段")
        return self


class ManualHazardCreate(ReviewModel):
    name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=300)
    evidence: str = Field(min_length=1, max_length=1000)
    risk: Risk
    risk_reason: str = Field(min_length=1, max_length=500)
    priority: Priority = "manual_review"
    suggested_deadline: str = Field(default="请现场负责人确定", min_length=1, max_length=100)
    advice: str = Field(min_length=1, max_length=1000)
    manual_checks: list[str] = Field(default_factory=list, max_length=10)
    regulation: str | None = Field(default=None, max_length=2000)
    source_url: str | None = Field(default=None, max_length=1000)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("suggested_deadline", "regulation", "source_url", "note")
    @classmethod
    def clean_optional_fields(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        return value or None

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        if value and not value.startswith("https://"):
            raise ValueError("依据链接必须使用 HTTPS")
        return value

    @field_validator("manual_checks")
    @classmethod
    def validate_checks(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if any(len(item) > 300 for item in cleaned):
            raise ValueError("人工核验项过长")
        return cleaned
