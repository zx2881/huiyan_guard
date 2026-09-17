from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings loaded from environment variables or ``.env``."""

    database_url: str = "sqlite:///./data/app.db"
    upload_dir: str = "./data/uploads/inspections"
    ark_api_key: str = ""
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_model: str = ""
    # TODO(YOLO): Keep this selector stable when the local YOLO adapter is implemented.
    vision_provider: Literal["ark", "yolo"] = "ark"
    # TODO(YOLO): These values are reserved only. No YOLO runtime is loaded yet.
    yolo_model_path: str = ""
    yolo_device: str = "auto"
    yolo_confidence_threshold: float = Field(default=0.25, ge=0, le=1)
    yolo_input_size: int = Field(default=640, ge=32)
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_image_pixels: int = Field(default=25_000_000, gt=0)
    vision_request_timeout_seconds: float = Field(default=30, gt=0)
    vision_total_timeout_seconds: float = Field(default=75, gt=0)
    vision_json_retries: int = Field(default=2, ge=0, le=2)
    text_api_key: str = ""
    text_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    text_model: str = ""
    text_request_timeout_seconds: float = Field(default=30, gt=0)

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        value = value.strip()
        prefix = "sqlite:///"
        if not value.startswith(prefix):
            raise ValueError("DATABASE_URL 目前只支持 sqlite:/// 本地文件格式")
        database_name = value[len(prefix) :]
        if not database_name or database_name == ":memory:":
            raise ValueError("DATABASE_URL 必须指向 SQLite 文件")
        return value

    @field_validator(
        "upload_dir",
        "ark_base_url",
        "ark_api_key",
        "ark_model",
        "yolo_model_path",
        "yolo_device",
        "text_api_key",
        "text_base_url",
        "text_model",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("vision_total_timeout_seconds")
    @classmethod
    def validate_total_timeout(cls, value: float, info) -> float:
        request_timeout = info.data.get("vision_request_timeout_seconds", 30)
        if value < request_timeout:
            raise ValueError("VISION_TOTAL_TIMEOUT_SECONDS 不得小于单次请求超时")
        return value

    @property
    def database_path(self) -> Path:
        raw_path = self.database_url.removeprefix("sqlite:///")
        path = Path(raw_path)
        return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_dir)
        return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
