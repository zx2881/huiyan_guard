from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import time
from typing import Any


class EvaluationError(ValueError):
    """Raised when an evaluation artifact does not satisfy the public contract."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"无法读取 JSON：{path}") from exc
    if not isinstance(value, dict):
        raise EvaluationError(f"JSON 根节点必须是对象：{path}")
    return value


def validate_dataset(dataset: dict[str, Any]) -> None:
    if dataset.get("schema_version") != 1:
        raise EvaluationError("评测集 schema_version 必须为 1")
    if not _text(dataset.get("name")):
        raise EvaluationError("评测集必须提供 name")
    if not isinstance(dataset.get("is_example"), bool):
        raise EvaluationError("评测集必须用布尔值 is_example 标明是否为格式示例")
    samples = dataset.get("samples")
    if not isinstance(samples, list) or not samples:
        raise EvaluationError("评测集 samples 必须是非空数组")
    aliases = dataset.get("label_aliases", {})
    if not isinstance(aliases, dict) or any(
        not _text(key) or not _text(value) for key, value in aliases.items()
    ):
        raise EvaluationError("label_aliases 必须是非空文本到非空文本的映射")

    seen: set[str] = set()
    for index, sample in enumerate(samples):
        prefix = f"samples[{index}]"
        if not isinstance(sample, dict):
            raise EvaluationError(f"{prefix} 必须是对象")
        sample_id = _text(sample.get("id"))
        if not sample_id or sample_id in seen:
            raise EvaluationError(f"{prefix}.id 缺失或重复")
        seen.add(sample_id)
        if sample.get("split") not in {"smoke", "validation"}:
            raise EvaluationError(f"{prefix}.split 只能是 smoke 或 validation")
        if sample.get("scene") not in {"dormitory", "laboratory"}:
            raise EvaluationError(f"{prefix}.scene 不受支持")
        image_path = _text(sample.get("image_path"))
        if (
            not image_path
            or Path(image_path).is_absolute()
            or ".." in Path(image_path).parts
            or Path(image_path).suffix.casefold()
            not in {".jpg", ".jpeg", ".png", ".webp"}
        ):
            raise EvaluationError(f"{prefix}.image_path 必须是评测集目录内的相对路径")
        source = sample.get("source")
        if (
            not isinstance(source, dict)
            or not _text(source.get("kind"))
            or not _text(source.get("usage_permission"))
        ):
            raise EvaluationError(f"{prefix}.source 必须说明来源类型和可用范围")
        annotations = sample.get("annotations")
        if not isinstance(annotations, dict):
            raise EvaluationError(f"{prefix}.annotations 必须是对象")
        _validate_text_list(annotations.get("hazards"), f"{prefix}.annotations.hazards")
        _validate_text_list(
            annotations.get("uncertain_items", []),
            f"{prefix}.annotations.uncertain_items",
        )


def validate_predictions(predictions: dict[str, Any]) -> None:
    if predictions.get("schema_version") != 1:
        raise EvaluationError("预测文件 schema_version 必须为 1")
    records = predictions.get("records")
    if not isinstance(records, list):
        raise EvaluationError("预测文件 records 必须是数组")
    seen: set[str] = set()
    for index, record in enumerate(records):
        prefix = f"records[{index}]"
        if not isinstance(record, dict):
            raise EvaluationError(f"{prefix} 必须是对象")
        sample_id = _text(record.get("sample_id"))
        if not sample_id or sample_id in seen:
            raise EvaluationError(f"{prefix}.sample_id 缺失或重复")
        seen.add(sample_id)
        if record.get("status") not in {"completed", "failed"}:
            raise EvaluationError(f"{prefix}.status 只能是 completed 或 failed")
        _validate_text_list(record.get("hazards", []), f"{prefix}.hazards")
        _validate_text_list(
            record.get("uncertain_items", []), f"{prefix}.uncertain_items"
        )
        duration = record.get("duration_ms")
        if duration is not None and (
            not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or duration < 0
        ):
            raise EvaluationError(f"{prefix}.duration_ms 必须是非负数或 null")


def evaluate(
    dataset: dict[str, Any], predictions: dict[str, Any]
) -> dict[str, Any]:
    validate_dataset(dataset)
    validate_predictions(predictions)
    if predictions.get("dataset_name") != dataset["name"]:
        raise EvaluationError("预测文件 dataset_name 与评测集 name 不一致")

    aliases = {
        _normalize_label(key): _normalize_label(value)
        for key, value in dataset.get("label_aliases", {}).items()
    }
    record_by_id = {record["sample_id"]: record for record in predictions["records"]}
    known_ids = {sample["id"] for sample in dataset["samples"]}
    unknown = sorted(set(record_by_id) - known_ids)
    if unknown:
        raise EvaluationError(f"预测文件包含未知样本：{', '.join(unknown)}")

    sample_results: list[dict[str, Any]] = []
    for sample in dataset["samples"]:
        record = record_by_id.get(sample["id"])
        if record is None:
            record = {
                "sample_id": sample["id"],
                "status": "failed",
                "hazards": [],
                "uncertain_items": [],
                "duration_ms": None,
                "error_category": "missing_prediction",
            }
        completed = record["status"] == "completed"
        expected = _canonical_counter(sample["annotations"]["hazards"], aliases)
        predicted = _canonical_counter(record.get("hazards", []), aliases) if completed else Counter()
        hazard_counts = _match_counts(expected, predicted)
        expected_uncertain = _canonical_counter(
            sample["annotations"].get("uncertain_items", []), aliases
        )
        predicted_uncertain = _canonical_counter(
            record.get("uncertain_items", []), aliases
        ) if completed else Counter()
        uncertain_counts = _match_counts(expected_uncertain, predicted_uncertain)
        sample_results.append(
            {
                "sample_id": sample["id"],
                "split": sample["split"],
                "status": record["status"],
                "error_category": record.get("error_category"),
                "duration_ms": record.get("duration_ms"),
                "hazards": hazard_counts,
                "uncertain_items": uncertain_counts,
            }
        )

    splits = {
        split: _aggregate([item for item in sample_results if item["split"] == split])
        for split in ("smoke", "validation")
        if any(item["split"] == split for item in sample_results)
    }
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "name": dataset["name"],
            "is_example": bool(dataset.get("is_example", False)),
            "sample_count": len(dataset["samples"]),
            "description": dataset.get("description", ""),
        },
        "model": predictions.get("model", {}),
        "metrics": _aggregate(sample_results),
        "splits": splits,
        "samples": sample_results,
        "metric_policy": {
            "hazard_matching": "规范化标签后一对一精确匹配；label_aliases 只做显式别名归一",
            "failed_requests": "失败或缺失预测按空预测计入漏报，并计入请求失败率",
            "latency": "从提交请求到报告进入 completed/failed 的端到端毫秒数；P95 使用 nearest-rank",
        },
    }


def render_markdown(result: dict[str, Any]) -> str:
    metrics = result["metrics"]
    dataset = result["dataset"]
    lines = ["# 慧眼安巡评测记录", ""]
    if dataset["is_example"]:
        lines.extend(
            [
                "> **示例数据，不能作为模型效果结论。** 本页只验证评测工具、指标口径和报告格式；真实现场标注集尚未导入。",
                "",
            ]
        )
    lines.extend(
        [
            f"- 评测集：`{dataset['name']}`",
            f"- 样本数：{dataset['sample_count']}",
            f"- 生成时间：{result['generated_at']}",
            f"- 模型记录：{_model_text(result.get('model', {}))}",
            "",
            "## 总体指标",
            "",
            "| 指标 | 结果 |",
            "| --- | ---: |",
            f"| 真阳性 / 误报 / 漏报 | {metrics['hazards']['tp']} / {metrics['hazards']['fp']} / {metrics['hazards']['fn']} |",
            f"| 隐患精确率 | {_ratio(metrics['hazards']['precision'])} |",
            f"| 隐患召回率 | {_ratio(metrics['hazards']['recall'])} |",
            f"| 隐患 F1 | {_ratio(metrics['hazards']['f1'])} |",
            f"| 请求失败率 | {_ratio(metrics['request_failure_rate'])} ({metrics['request_failures']}/{metrics['sample_count']}) |",
            f"| 端到端耗时 P50 | {_duration(metrics['latency_ms']['p50'])} |",
            f"| 端到端耗时 P95 | {_duration(metrics['latency_ms']['p95'])} |",
            "",
            "## 分组结果",
            "",
            "| 分组 | 样本 | 精确率 | 召回率 | 失败率 | P50 | P95 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for split, values in result["splits"].items():
        lines.append(
            f"| {split} | {values['sample_count']} | {_ratio(values['hazards']['precision'])} "
            f"| {_ratio(values['hazards']['recall'])} | {_ratio(values['request_failure_rate'])} "
            f"| {_duration(values['latency_ms']['p50'])} | {_duration(values['latency_ms']['p95'])} |"
        )
    lines.extend(
        [
            "",
            "## 逐样本追踪",
            "",
            "| 样本 | 分组 | 状态 | TP | FP | FN | 端到端耗时 | 失败分类 |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for item in result["samples"]:
        lines.append(
            f"| {item['sample_id']} | {item['split']} | {item['status']} "
            f"| {item['hazards']['tp']} | {item['hazards']['fp']} | {item['hazards']['fn']} "
            f"| {_duration(item['duration_ms'])} | {item.get('error_category') or '—'} |"
        )
    lines.extend(
        [
            "",
            "## 统计口径",
            "",
            f"- 隐患匹配：{result['metric_policy']['hazard_matching']}。",
            f"- 请求失败：{result['metric_policy']['failed_requests']}。",
            f"- 耗时：{result['metric_policy']['latency']}。",
            "- 样本图片不写入报告；来源与使用权限保留在本地评测清单中。",
            "- 先固定 validation 标注再调提示词或阈值，不能把验证集重新作为调参集。",
            "",
        ]
    )
    return "\n".join(lines)


def capture_predictions(
    dataset: dict[str, Any],
    dataset_path: Path,
    *,
    base_url: str,
    username: str = "",
    password: str = "",
    poll_interval: float = 0.5,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    """Submit every annotated image and retain only auditable structured outputs."""

    import httpx

    validate_dataset(dataset)
    if bool(username) != bool(password):
        raise EvaluationError("评测访问用户名和密码必须同时提供")
    auth = httpx.BasicAuth(username, password) if username else None
    records: list[dict[str, Any]] = []
    observed_model: dict[str, Any] = {}
    with httpx.Client(base_url=base_url.rstrip("/"), auth=auth, timeout=30.0) as client:
        for sample in dataset["samples"]:
            image_path = _resolved_image(dataset_path.parent, sample["image_path"])
            start = time.monotonic()
            try:
                with image_path.open("rb") as image_file:
                    response = client.post(
                        "/api/inspections",
                        data={"scene": sample["scene"]},
                        files={"image": (image_path.name, image_file, _image_mime(image_path))},
                    )
                response.raise_for_status()
                inspection_id = response.json()["id"]
                while True:
                    detail_response = client.get(f"/api/inspections/{inspection_id}")
                    detail_response.raise_for_status()
                    detail = detail_response.json()
                    if detail.get("status") in {"completed", "failed"}:
                        break
                    if time.monotonic() - start >= timeout_seconds:
                        raise TimeoutError("等待报告终态超时")
                    time.sleep(poll_interval)
                duration_ms = round((time.monotonic() - start) * 1000, 1)
                mode = detail.get("mode")
                completed = detail.get("status") == "completed" and mode == "vision"
                model_info = detail.get("model_info") or {}
                if model_info:
                    observed_model = model_info
                records.append(
                    {
                        "sample_id": sample["id"],
                        "status": "completed" if completed else "failed",
                        "duration_ms": duration_ms,
                        "hazards": [item.get("name", "") for item in detail.get("hazards", []) if item.get("name")],
                        "uncertain_items": detail.get("uncertain_items", []),
                        "error_category": (
                            None
                            if completed
                            else "non_model_mode"
                            if mode != "vision"
                            else "workflow_failed"
                        ),
                    }
                )
            except (OSError, httpx.HTTPError, KeyError, ValueError, TimeoutError) as exc:
                records.append(
                    {
                        "sample_id": sample["id"],
                        "status": "failed",
                        "duration_ms": round((time.monotonic() - start) * 1000, 1),
                        "hazards": [],
                        "uncertain_items": [],
                        "error_category": _error_category(exc),
                    }
                )
    return {
        "schema_version": 1,
        "dataset_name": dataset["name"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": observed_model,
        "records": records,
    }


def _aggregate(items: list[dict[str, Any]]) -> dict[str, Any]:
    hazards = _sum_counts(items, "hazards")
    uncertain = _sum_counts(items, "uncertain_items")
    durations = sorted(
        float(item["duration_ms"])
        for item in items
        if isinstance(item.get("duration_ms"), (int, float))
    )
    failures = sum(item["status"] != "completed" for item in items)
    return {
        "sample_count": len(items),
        "request_failures": failures,
        "request_failure_rate": failures / len(items) if items else None,
        "hazards": _ratios(hazards),
        "uncertain_items": _ratios(uncertain),
        "latency_ms": {
            "count": len(durations),
            "p50": statistics.median(durations) if durations else None,
            "p95": _nearest_rank(durations, 0.95) if durations else None,
        },
    }


def _sum_counts(items: list[dict[str, Any]], field: str) -> dict[str, int]:
    return {
        key: sum(item[field][key] for item in items)
        for key in ("tp", "fp", "fn")
    }


def _ratios(counts: dict[str, int]) -> dict[str, Any]:
    precision_denominator = counts["tp"] + counts["fp"]
    recall_denominator = counts["tp"] + counts["fn"]
    precision = counts["tp"] / precision_denominator if precision_denominator else None
    recall = counts["tp"] / recall_denominator if recall_denominator else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    return {**counts, "precision": precision, "recall": recall, "f1": f1}


def _match_counts(expected: Counter[str], predicted: Counter[str]) -> dict[str, int]:
    true_positive = sum((expected & predicted).values())
    return {
        "tp": true_positive,
        "fp": sum(predicted.values()) - true_positive,
        "fn": sum(expected.values()) - true_positive,
    }


def _canonical_counter(values: list[str], aliases: dict[str, str]) -> Counter[str]:
    normalized = (_normalize_label(value) for value in values)
    return Counter(aliases.get(value, value) for value in normalized)


def _normalize_label(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _validate_text_list(value: Any, field: str) -> None:
    if not isinstance(value, list) or any(not _text(item) for item in value):
        raise EvaluationError(f"{field} 必须是非空文本组成的数组，可为空数组")
    normalized = [_normalize_label(item) for item in value]
    if len(normalized) != len(set(normalized)):
        raise EvaluationError(f"{field} 不能包含重复标签")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _nearest_rank(values: list[float], percentile: float) -> float:
    return values[max(0, math.ceil(percentile * len(values)) - 1)]


def _ratio(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def _duration(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.0f} ms"


def _model_text(model: dict[str, Any]) -> str:
    if not model:
        return "未记录"
    return ", ".join(f"{key}={value}" for key, value in sorted(model.items()))


def _resolved_image(base_dir: Path, relative_path: str) -> Path:
    base = base_dir.resolve()
    path = (base / relative_path).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise EvaluationError(f"评测图片不存在或越出评测目录：{relative_path}")
    return path


def _image_mime(path: Path) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")


def _error_category(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "timeout"
    if "connect" in name or "network" in name:
        return "network"
    if isinstance(exc, OSError):
        return "local_file"
    if isinstance(exc, EvaluationError):
        return "dataset"
    return "request"
