import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.knowledge.importer import (  # noqa: E402
    DEFAULT_SOURCE,
    import_regulations,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="校验并导入规章知识库")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    count = import_regulations(args.source)
    print(f"已校验并导入 {count} 条规章：{args.source}")


if __name__ == "__main__":
    main()
