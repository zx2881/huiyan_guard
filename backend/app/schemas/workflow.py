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


class ReviewFinding(WorkflowModel):
    hazard_index: int = Field(ge=0)
    area: Literal["evidence", "regulation", "risk", "advice"]
    message: str = Field(min_length=1, max_length=500)

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("复核问题不得为空")
        return value


class ReportReview(WorkflowModel):
    verdict: Literal["pass", "revise", "manual_review"]
    summary: str = Field(min_length=1, max_length=1000)
    findings: list[ReviewFinding] = Field(max_length=10)
    method: Literal["model"]

    @field_validator("summary")
    @classmethod
    def clean_summary(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("复核总结不得为空")
        return value
