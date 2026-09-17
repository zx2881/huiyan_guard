import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.database import conn
from backend.app.knowledge.models import RegulationFile
from backend.app.knowledge.retriever import retrieve_regulations
from backend.app.knowledge.importer import import_regulations


REPO_ROOT = Path(__file__).resolve().parents[1]
REGULATIONS = REPO_ROOT / "knowledge" / "dormitory" / "regulations.json"


def test_regulation_file_has_unique_traceable_official_sources():
    data = RegulationFile.model_validate_json(REGULATIONS.read_text(encoding="utf-8"))
    checklist = json.loads(
        (REPO_ROOT / "knowledge" / "dormitory" / "checklist.json").read_text(
            encoding="utf-8"
        )
    )

    assert 20 <= len(data.regulations) <= 30
    assert len({item.id for item in data.regulations}) == len(data.regulations)
    assert {item.source_url.host for item in data.regulations} <= {
        "www.moe.gov.cn",
        "www.samr.gov.cn",
        "www.jiangxia.gov.cn",
    }
    assert all(item.verified_at.isoformat() == "2026-09-17" for item in data.regulations)
    covered_check_ids = {
        check_id for item in data.regulations for check_id in item.check_ids
    }
    assert {item["id"] for item in checklist["items"]} <= covered_check_ids


def test_import_is_idempotent_and_preserves_structured_fields(isolated_settings):
    expected = import_regulations(REGULATIONS, isolated_settings)
    assert import_regulations(REGULATIONS, isolated_settings) == expected

    with conn(isolated_settings) as database:
        count = database.execute("SELECT COUNT(*) n FROM regulations").fetchone()["n"]
        row = database.execute(
            "SELECT * FROM regulations WHERE id='fire-law-28'"
        ).fetchone()
    assert count == expected
    assert row["verified_at"] == "2026-09-17"
    assert "blocked_exit" in json.loads(row["check_ids"])
    assert "堵塞" in json.loads(row["keywords"])


def test_import_rejects_scene_mismatch(tmp_path, isolated_settings):
    raw = json.loads(REGULATIONS.read_text(encoding="utf-8"))
    raw["regulations"][0]["scene"] = "laboratory"
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValidationError):
        import_regulations(invalid, isolated_settings)


def test_import_rejects_unknown_check_id(tmp_path, isolated_settings):
    raw = json.loads(REGULATIONS.read_text(encoding="utf-8"))
    raw["regulations"][0]["check_ids"] = ["not_in_checklist"]
    invalid = tmp_path / "unknown-check.json"
    invalid.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="不存在的检查项"):
        import_regulations(invalid, isolated_settings)


def test_retriever_finds_blocked_exit_rules(isolated_settings):
    import_regulations(REGULATIONS, isolated_settings)

    matches = retrieve_regulations(
        "dormitory",
        "门口堆放多个纸箱，堵住了疏散通道",
        check_id="blocked_exit",
        settings=isolated_settings,
    )

    assert matches
    assert all(item["scene"] == "dormitory" for item in matches)
    assert all(item["score"] > 0 for item in matches)
    assert any(item["id"] == "fire-law-28" for item in matches)
    assert all(item["source_url"].startswith("https://") for item in matches)


def test_retriever_uses_socket_synonyms_without_returning_arbitrary_rule(
    isolated_settings,
):
    import_regulations(REGULATIONS, isolated_settings)

    matches = retrieve_regulations(
        "dormitory",
        "排插被衣服盖住",
        check_id="socket_cover",
        settings=isolated_settings,
    )
    no_match = retrieve_regulations(
        "dormitory", "墙面颜色不均匀", settings=isolated_settings
    )
    wrong_scene = retrieve_regulations(
        "laboratory", "疏散通道被堵塞", settings=isolated_settings
    )

    assert matches
    assert matches[0]["id"] in {"fire-law-27", "moe-fire-13-2", "moe-fire-28-6"}
    assert no_match == []
    assert wrong_scene == []


def test_retriever_finds_ebike_battery_rule(isolated_settings):
    import_regulations(REGULATIONS, isolated_settings)

    matches = retrieve_regulations(
        "dormitory",
        "电动自行车锂电池被带进宿舍充电",
        check_id="ebike_battery_indoor",
        settings=isolated_settings,
    )

    assert matches[0]["id"] == "edu-hazard-guide-3-1-6"
