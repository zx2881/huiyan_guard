import copy
from pathlib import Path

import pytest

from backend.app.evaluation import (
    EvaluationError,
    evaluate,
    load_json,
    render_markdown,
    validate_dataset,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "evaluation" / "examples"


def example_artifacts():
    return (
        load_json(EXAMPLES / "dataset.example.json"),
        load_json(EXAMPLES / "predictions.example.json"),
    )


def test_example_metrics_are_traceable_and_marked_non_evidence():
    dataset, predictions = example_artifacts()

    result = evaluate(dataset, predictions)
    markdown = render_markdown(result)

    assert result["dataset"] == {
        "name": "format-example-only",
        "is_example": True,
        "sample_count": 4,
        "description": "仅用于验证评测格式和指标计算，不包含真实图片或真实模型结论。",
    }
    assert result["metrics"]["hazards"] == {
        "tp": 2,
        "fp": 1,
        "fn": 2,
        "precision": pytest.approx(2 / 3),
        "recall": pytest.approx(1 / 2),
        "f1": pytest.approx(4 / 7),
    }
    assert result["metrics"]["request_failure_rate"] == pytest.approx(0.25)
    assert result["metrics"]["latency_ms"] == {
        "count": 4,
        "p50": 1600.0,
        "p95": 3000.0,
    }
    assert "示例数据，不能作为模型效果结论" in markdown
    assert "example-04" in markdown
    assert "timeout" in markdown


def test_missing_prediction_counts_as_failure_and_false_negative():
    dataset, predictions = example_artifacts()
    predictions["records"] = predictions["records"][:1]

    result = evaluate(dataset, predictions)

    assert result["metrics"]["request_failures"] == 3
    missing = next(
        item for item in result["samples"] if item["sample_id"] == "example-03"
    )
    assert missing["error_category"] == "missing_prediction"
    assert missing["hazards"]["fn"] == 2


def test_dataset_rejects_duplicate_ids_and_parent_paths():
    dataset, _ = example_artifacts()
    duplicate = copy.deepcopy(dataset)
    duplicate["samples"][1]["id"] = duplicate["samples"][0]["id"]
    with pytest.raises(EvaluationError, match="缺失或重复"):
        validate_dataset(duplicate)

    traversal = copy.deepcopy(dataset)
    traversal["samples"][0]["image_path"] = "../private.jpg"
    with pytest.raises(EvaluationError, match="相对路径"):
        validate_dataset(traversal)


def test_predictions_reject_unknown_sample():
    dataset, predictions = example_artifacts()
    predictions["records"][0]["sample_id"] = "unknown"

    with pytest.raises(EvaluationError, match="未知样本"):
        evaluate(dataset, predictions)
