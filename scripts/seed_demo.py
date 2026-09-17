from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import get_settings  # noqa: E402
from backend.app.demo_seed import seed_demo_reports  # noqa: E402


def main() -> int:
    settings = get_settings()
    ids = seed_demo_reports(settings)
    print(f"离线历史回放已就绪：{len(ids)} 份报告，编号 {', '.join(map(str, ids))}")
    print("这些记录使用合成示意图，不代表实时 AI 分析或模型准确率。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
