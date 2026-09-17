import json

from backend.app.database import conn


def seed_completed_inspection(settings, *, with_hazard: bool = True) -> tuple[int, int | None]:
    with conn(settings) as database:
        inspection_id = database.execute(
            """INSERT INTO inspections(
                scene,image_path,status,created_at,completed_at,current_step,
                progress,mode
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                "dormitory",
                "room.jpg",
                "completed",
                "2026-09-17T08:00:00+00:00",
                "2026-09-17T08:01:00+00:00",
                "completed",
                100,
                "vision",
            ),
        ).lastrowid
        if not with_hazard:
            return inspection_id, None
        original = {
            "name": "通道堵塞",
            "location": "门口",
            "evidence": "纸箱占用通道",
            "risk": "medium",
            "advice": "移走纸箱",
        }
        hazard_id = database.execute(
            """INSERT INTO hazards(
                inspection_id,name,location,evidence,risk,advice,regulation,
                source_url,risk_reason,priority,suggested_deadline,
                manual_checks,classification_method,remediation_method,
                source,human_status,original_data,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                inspection_id,
                "通道堵塞",
                "门口",
                "纸箱占用通道",
                "medium",
                "移走纸箱",
                "消防法",
                "https://example.test/rule",
                "内部规则判断",
                "high",
                "24 小时内",
                "[]",
                "rules",
                "rules",
                "ai",
                "pending",
                json.dumps(original, ensure_ascii=False),
                "2026-09-17T08:01:00+00:00",
            ),
        ).lastrowid
    return inspection_id, hazard_id


def test_confirm_and_correct_hazard_preserves_ai_original_and_writes_audit(
    client, isolated_settings
):
    inspection_id, hazard_id = seed_completed_inspection(isolated_settings)

    confirmed = client.patch(
        f"/api/hazards/{hazard_id}",
        json={"human_status": "confirmed", "note": "现场确认"},
    )
    corrected = client.patch(
        f"/api/hazards/{hazard_id}",
        json={"location": "宿舍门内侧", "note": "补充准确位置"},
    )

    assert confirmed.status_code == 200
    assert confirmed.json()["action_type"] == "confirmed"
    assert corrected.status_code == 200
    assert corrected.json()["hazard"]["human_status"] == "corrected"
    detail = client.get(f"/api/inspections/{inspection_id}").json()
    hazard = detail["hazards"][0]
    assert hazard["location"] == "宿舍门内侧"
    assert hazard["original_data"]["location"] == "门口"
    assert [action["action_type"] for action in hazard["actions"]] == [
        "confirmed",
        "corrected",
    ]
    assert hazard["actions"][1]["actor"] == "unauthenticated"
    assert hazard["actions"][1]["before_data"]["location"] == "门口"


def test_rejected_hazard_is_excluded_from_dashboard(client, isolated_settings):
    _, hazard_id = seed_completed_inspection(isolated_settings)
    assert client.get("/api/dashboard").json()["total_hazards"] == 1

    response = client.patch(
        f"/api/hazards/{hazard_id}",
        json={"human_status": "rejected", "note": "现场复核未发现"},
    )

    assert response.status_code == 200
    assert client.get("/api/dashboard").json()["total_hazards"] == 0


def test_manual_hazard_is_confirmed_and_audited(client, isolated_settings):
    inspection_id, _ = seed_completed_inspection(
        isolated_settings, with_hazard=False
    )

    response = client.post(
        f"/api/inspections/{inspection_id}/hazards",
        json={
            "name": "插线板串联",
            "location": "书桌下方",
            "evidence": "两个插线板首尾连接",
            "risk": "high",
            "risk_reason": "现场人工发现存在过载风险",
            "priority": "immediate",
            "suggested_deadline": "立即",
            "advice": "断开串联并由管理人员复查",
            "manual_checks": ["核对负载功率"],
            "note": "AI 未覆盖到桌下区域",
        },
    )

    assert response.status_code == 201
    detail = client.get(f"/api/inspections/{inspection_id}").json()
    hazard = detail["hazards"][0]
    assert hazard["source"] == "manual"
    assert hazard["human_status"] == "confirmed"
    assert hazard["original_data"] is None
    assert hazard["actions"][0]["action_type"] == "manual_added"


def test_review_rejects_empty_change_and_missing_records(client):
    assert client.patch("/api/hazards/999", json={"human_status": "confirmed"}).status_code == 404
    response = client.patch("/api/hazards/999", json={"note": "only a note"})
    assert response.status_code == 422
