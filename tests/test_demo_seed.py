import json

from fastapi.testclient import TestClient

from backend.app.database import conn
from backend.app.demo_seed import DEMO_PREFIX, seed_demo_reports
from backend.app.main import create_app


def test_demo_seed_creates_complete_idempotent_replay(isolated_settings):
    first_ids = seed_demo_reports(isolated_settings)
    second_ids = seed_demo_reports(isolated_settings)

    assert first_ids == second_ids
    assert len(first_ids) == 4
    with conn(isolated_settings) as database:
        inspections = database.execute(
            "SELECT * FROM inspections WHERE mode='replay' ORDER BY id"
        ).fetchall()
        hazards = database.execute(
            "SELECT * FROM hazards WHERE source='replay' ORDER BY id"
        ).fetchall()
        snapshots = database.execute(
            "SELECT * FROM regulation_snapshots WHERE inspection_id IN "
            "(SELECT id FROM inspections WHERE mode='replay')"
        ).fetchall()

    assert len(inspections) == 4
    assert len(hazards) == 4
    assert len(snapshots) == 4
    assert all(row["status"] == "completed" for row in inspections)
    assert all(row["image_path"].startswith(DEMO_PREFIX) for row in inspections)
    assert all(
        json.loads(row["model_info"])["synthetic_image"] is True
        for row in inspections
    )
    assert all(
        (isolated_settings.upload_path / row["image_path"]).is_file()
        for row in inspections
    )

    with TestClient(create_app(isolated_settings)) as client:
        detail = client.get(f"/api/inspections/{first_ids[0]}").json()
        dashboard = client.get("/api/dashboard").json()
        update = client.patch(
            f"/api/hazards/{detail['hazards'][0]['id']}",
            json={"human_status": "confirmed"},
        )
        manual = client.post(
            f"/api/inspections/{first_ids[0]}/hazards",
            json={
                "name": "测试补录",
                "location": "测试位置",
                "evidence": "测试证据",
                "risk": "low",
                "risk_reason": "测试理由",
                "priority": "normal",
                "suggested_deadline": "一周内",
                "advice": "测试建议",
                "manual_checks": [],
            },
        )
    assert detail["mode"] == "replay"
    assert detail["model_info"]["vision_provider"] == "offline_replay"
    assert detail["hazards"][0]["source"] == "replay"
    assert detail["hazards"][0]["regulations"]
    assert dashboard == {
        "total_inspections": 0,
        "total_hazards": 0,
        "risk_distribution": [],
    }
    assert update.status_code == 409
    assert update.json() == {"detail": "离线历史回放为只读记录"}
    assert manual.status_code == 409
