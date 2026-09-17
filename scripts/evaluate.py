from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.evaluation import (  # noqa: E402
    EvaluationError,
    capture_predictions,
    evaluate,
    load_json,
    render_markdown,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="运行慧眼安巡离线评测，或从已启动的服务采集真实预测。"
    )
    parser.add_argument("--dataset", type=Path, required=True, help="人工标注评测集 JSON")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--predictions", type=Path, help="已有预测 JSON")
    source.add_argument("--base-url", help="真实运行服务地址，例如 http://127.0.0.1:8000")
    parser.add_argument(
        "--predictions-output",
        type=Path,
        default=Path("evaluation/results/predictions.json"),
        help="使用 --base-url 时保存原始预测的位置",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("evaluation/results/metrics.json"),
        help="机器可读指标输出",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("docs/evaluation.md"),
        help="Markdown 评测记录输出",
    )
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        dataset_path = args.dataset.resolve()
        dataset = load_json(dataset_path)
        if args.base_url:
            predictions = capture_predictions(
                dataset,
                dataset_path,
                base_url=args.base_url,
                username=os.getenv("APP_ACCESS_USERNAME", ""),
                password=os.getenv("APP_ACCESS_PASSWORD", ""),
                poll_interval=args.poll_interval,
                timeout_seconds=args.timeout,
            )
            _write_json(args.predictions_output, predictions)
        else:
            predictions = load_json(args.predictions.resolve())
        result = evaluate(dataset, predictions)
        _write_json(args.json_output, result)
        report_path = args.report.resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_markdown(result), encoding="utf-8")
    except EvaluationError as exc:
        print(f"评测失败：{exc}", file=sys.stderr)
        return 2
    print(
        f"评测完成：{result['dataset']['sample_count']} 个样本，"
        f"报告 {args.report.resolve()}，指标 {args.json_output.resolve()}"
    )
    return 0


def _write_json(path: Path, value: dict) -> None:
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
