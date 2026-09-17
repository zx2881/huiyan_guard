import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.backup import create_backup, verify_backup  # noqa: E402
from backend.app.config import get_settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="一致性备份慧眼安巡 SQLite 与上传图片")
    parser.add_argument("--output", type=Path, default=Path("backups"))
    args = parser.parse_args()
    backup_dir = create_backup(get_settings(), args.output)
    manifest = verify_backup(backup_dir)
    print(f"备份完成：{backup_dir}")
    print(f"图片文件：{len(manifest['uploads'])}")


if __name__ == "__main__":
    main()
