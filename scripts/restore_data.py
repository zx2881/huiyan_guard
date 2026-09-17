import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.backup import restore_backup  # noqa: E402
from backend.app.config import get_settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="恢复慧眼安巡数据库和上传图片")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="确认应用已经停止并允许覆盖当前数据库和图片目录",
    )
    args = parser.parse_args()
    restore_backup(get_settings(), args.source, confirmed=args.confirm)
    print("恢复完成。请启动应用并检查 /api/health 和历史报告。")


if __name__ == "__main__":
    main()
