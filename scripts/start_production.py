import os
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import uvicorn

from backend.app.config import get_settings  # noqa: E402


def main() -> None:
    settings = get_settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=port,
        workers=1,
        proxy_headers=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
