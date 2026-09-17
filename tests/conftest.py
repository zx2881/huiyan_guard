from pathlib import Path
import sys
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import Settings  # noqa: E402
from backend.app.main import create_app  # noqa: E402


@pytest.fixture
def isolated_settings(tmp_path: Path) -> Settings:
    database_path = (tmp_path / "db" / "app.db").as_posix()
    upload_path = (tmp_path / "uploads").as_posix()
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{database_path}",
        upload_dir=upload_path,
        ark_api_key="",
        ark_model="",
    )


@pytest.fixture
def client(isolated_settings: Settings):
    with TestClient(create_app(isolated_settings)) as test_client:
        yield test_client


@pytest.fixture
def image_bytes():
    def build(format_name: str = "JPEG", size: tuple[int, int] = (32, 24)) -> bytes:
        output = BytesIO()
        Image.new("RGB", size, "#3b82f6").save(output, format=format_name)
        return output.getvalue()

    return build
