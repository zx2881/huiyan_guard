from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RiskAssessment(WorkflowModel):
    risk: Literal["low", "medium", "high", "needs_review"]
    reason: str = Field(min_length=1, max_length=500)
    regulation_ids: list[str] = Field(max_length=5)
    method: Literal["rules", "model"]

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("分级理由不得为空")
        return value


class Remediation(WorkflowModel):
    advice: str = Field(min_length=1, max_length=1000)
    priority: Literal["immediate", "high", "normal", "manual_review"]
    suggested_deadline: str = Field(min_length=1, max_length=100)
    manual_checks: list[str] = Field(max_length=10)
    method: Literal["rules", "model"]

    @field_validator("advice", "suggested_deadline")
    @classmethod
    def clean_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("整改字段不得为空")
        return value
