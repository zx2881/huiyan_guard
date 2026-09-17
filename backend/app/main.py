import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import REPO_ROOT, Settings, get_settings
from .database import conn, init_db
from .integrations.text_client import TextClient
from .integrations.vision_factory import build_vision_analyzer
from .knowledge.importer import import_regulations
from .reliability import WriteRateLimiter, basic_auth_valid
from .schemas.human_review import HazardUpdate, ManualHazardCreate
from .utils.images import validate_and_save_image
from .workflow.runner import mark_interrupted_workflows, run_inspection_workflow


FRONTEND_DIR = REPO_ROOT / "frontend"
HAZARD_EDIT_FIELDS = {
    "name",
    "location",
    "evidence",
    "risk",
    "risk_reason",
    "priority",
    "suggested_deadline",
    "advice",
    "manual_checks",
    "human_status",
}


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def index(request: Request) -> FileResponse:
    return FileResponse(request.app.state.frontend_dir / "index.html")


def records_page(request: Request) -> FileResponse:
    return FileResponse(request.app.state.frontend_dir / "records.html")


def report_page(request: Request) -> FileResponse:
    return FileResponse(request.app.state.frontend_dir / "report.html")


def health(request: Request):
    settings = _settings(request)
    try:
        with conn(settings) as database:
            database.execute("SELECT 1").fetchone()
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": "unavailable"},
        )
    return {
        "status": "ok",
        "database": "ok",
        "vision": (
            "configured" if build_vision_analyzer(settings).enabled else "unconfigured"
        ),
        "vision_provider": settings.vision_provider,
        "text": "configured" if TextClient(settings).enabled else "rules",
        "ai_review": (
            "configured"
            if settings.ai_review_ready
            else "misconfigured"
            if settings.enable_ai_review
            else "disabled"
        ),
        "access": "protected" if settings.access_protected else "open",
    }


def _schedule_workflow(
    application: FastAPI,
    inspection_id: int,
    settings: Settings,
    vision,
) -> None:
    task = asyncio.create_task(
        run_inspection_workflow(inspection_id, settings, vision)
    )
    application.state.workflow_tasks.add(task)
    task.add_done_callback(application.state.workflow_tasks.discard)


async def create_inspection(
    request: Request,
    scene: str = Form(...),
    image: UploadFile = File(...),
):
    settings = _settings(request)
    if scene not in ("dormitory", "laboratory"):
        raise HTTPException(400, "不支持的检查场景")
    saved_image = await validate_and_save_image(image, settings)
    now = datetime.now(timezone.utc).isoformat()
    vision = build_vision_analyzer(settings)
    mode = "vision" if vision.enabled else "demo"
    status = "queued" if vision.enabled else "completed"
    try:
        with conn(settings) as database:
            inspection_id = database.execute(
                """INSERT INTO inspections(
                    scene,image_path,status,created_at,completed_at,current_step,
                    progress,started_at,mode,summary,image_quality,uncertain_items
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    scene,
                    saved_image.name,
                    status,
                    now,
                    None if vision.enabled else now,
                    status,
                    0 if vision.enabled else 100,
                    now,
                    mode,
                    None if vision.enabled else _demo_message(settings),
                    None if vision.enabled else "uncertain",
                    "[]",
                ),
            ).lastrowid
    except Exception:
        saved_image.path.unlink(missing_ok=True)
        raise

    if not vision.enabled:
        return {"id": inspection_id, "status": "completed", "mode": "demo"}

    _schedule_workflow(request.app, inspection_id, settings, vision)
    return JSONResponse(
        status_code=202,
        content={"id": inspection_id, "status": "queued", "mode": "vision"},
    )


async def retry_inspection(request: Request, inspection_id: int):
    settings = _settings(request)
    vision = build_vision_analyzer(settings)
    if not vision.enabled:
        raise HTTPException(409, "当前视觉模型未配置，无法重试")
    with conn(settings) as database:
        inspection = database.execute(
            "SELECT * FROM inspections WHERE id=?", (inspection_id,)
        ).fetchone()
        if not inspection:
            raise HTTPException(404, "巡检记录不存在")
        if inspection["status"] != "failed":
            raise HTTPException(409, "只有失败或中断的巡检可以重试")
        if not (settings.upload_path / inspection["image_path"]).is_file():
            raise HTTPException(409, "原始图片不存在，无法重试")
        now = datetime.now(timezone.utc).isoformat()
        database.execute(
            """UPDATE inspections SET
                status='queued',current_step='queued',progress=0,error=NULL,
                completed_at=NULL,started_at=?,retry_count=retry_count+1,
                review_status='disabled',review_summary=NULL,
                review_findings='[]',review_attempts=0,review_redo_count=0
                WHERE id=?""",
            (now, inspection_id),
        )
    _schedule_workflow(request.app, inspection_id, settings, vision)
    return JSONResponse(
        status_code=202,
        content={"id": inspection_id, "status": "queued", "mode": "vision"},
    )


def list_inspections(request: Request):
    with conn(_settings(request)) as database:
        rows = database.execute("SELECT * FROM inspections ORDER BY id DESC")
        return [_inspection_dict(row) for row in rows]


def get_inspection(request: Request, inspection_id: int):
    with conn(_settings(request)) as database:
        inspection = database.execute(
            "SELECT * FROM inspections WHERE id=?", (inspection_id,)
        ).fetchone()
        if not inspection:
            raise HTTPException(404, "巡检记录不存在")
        hazards = database.execute(
            "SELECT * FROM hazards WHERE inspection_id=? ORDER BY id",
            (inspection_id,),
        ).fetchall()
        snapshots = database.execute(
            "SELECT * FROM regulation_snapshots WHERE inspection_id=? ORDER BY id",
            (inspection_id,),
        ).fetchall()
        actions = database.execute(
            "SELECT * FROM hazard_actions WHERE inspection_id=? ORDER BY id",
            (inspection_id,),
        ).fetchall()
    by_hazard: dict[int, list[dict]] = {}
    for snapshot in snapshots:
        item = dict(snapshot)
        by_hazard.setdefault(item["hazard_id"], []).append(item)
    actions_by_hazard: dict[int, list[dict]] = {}
    for action in actions:
        item = _action_dict(action)
        actions_by_hazard.setdefault(item["hazard_id"], []).append(item)
    result = _inspection_dict(inspection)
    result["hazards"] = [
        _hazard_dict(
            hazard,
            by_hazard.get(hazard["id"], []),
            actions_by_hazard.get(hazard["id"], []),
        )
        for hazard in hazards
    ]
    return result


def update_hazard(request: Request, hazard_id: int, payload: HazardUpdate):
    settings = _settings(request)
    values = payload.model_dump(exclude_unset=True)
    note = values.pop("note", None)
    edited_fields = set(values) - {"human_status"}
    if edited_fields and "human_status" not in values:
        values["human_status"] = "corrected"
    now = datetime.now(timezone.utc).isoformat()
    with conn(settings) as database:
        before = database.execute(
            "SELECT * FROM hazards WHERE id=?", (hazard_id,)
        ).fetchone()
        if not before:
            raise HTTPException(404, "隐患记录不存在")
        inspection = database.execute(
            "SELECT mode FROM inspections WHERE id=?", (before["inspection_id"],)
        ).fetchone()
        if inspection and inspection["mode"] == "replay":
            raise HTTPException(409, "离线历史回放为只读记录")
        if values.get("manual_checks") is not None:
            values["manual_checks"] = json.dumps(
                values["manual_checks"], ensure_ascii=False
            )
        assignments = [f"{field}=?" for field in values if field in HAZARD_EDIT_FIELDS]
        assignments.append("updated_at=?")
        parameters = [values[field] for field in values if field in HAZARD_EDIT_FIELDS]
        parameters.extend((now, hazard_id))
        database.execute(
            f"UPDATE hazards SET {','.join(assignments)} WHERE id=?", parameters
        )
        after = database.execute(
            "SELECT * FROM hazards WHERE id=?", (hazard_id,)
        ).fetchone()
        if edited_fields:
            action_type = "corrected"
        else:
            action_type = {
                "confirmed": "confirmed",
                "rejected": "rejected",
                "pending": "reset_pending",
                "corrected": "corrected",
            }.get(values.get("human_status"), "updated")
        database.execute(
            """INSERT INTO hazard_actions(
                inspection_id,hazard_id,action_type,before_data,after_data,
                note,actor,created_at
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                before["inspection_id"],
                hazard_id,
                action_type,
                json.dumps(_review_snapshot(before), ensure_ascii=False),
                json.dumps(_review_snapshot(after), ensure_ascii=False),
                note,
                "unauthenticated",
                now,
            ),
        )
    return {
        "hazard": _hazard_dict(after, [], []),
        "action_type": action_type,
        "updated_at": now,
    }


def create_manual_hazard(
    request: Request,
    inspection_id: int,
    payload: ManualHazardCreate,
):
    settings = _settings(request)
    values = payload.model_dump()
    note = values.pop("note", None)
    now = datetime.now(timezone.utc).isoformat()
    with conn(settings) as database:
        inspection = database.execute(
            "SELECT status,mode FROM inspections WHERE id=?", (inspection_id,)
        ).fetchone()
        if not inspection:
            raise HTTPException(404, "巡检记录不存在")
        if inspection["mode"] == "replay":
            raise HTTPException(409, "离线历史回放为只读记录")
        if inspection["status"] != "completed":
            raise HTTPException(409, "分析完成后才能补录隐患")
        hazard_id = database.execute(
            """INSERT INTO hazards(
                inspection_id,name,location,evidence,risk,advice,regulation,
                source_url,confidence,risk_reason,priority,suggested_deadline,
                manual_checks,classification_method,remediation_method,
                source,human_status,original_data,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                inspection_id,
                values["name"],
                values["location"],
                values["evidence"],
                values["risk"],
                values["advice"],
                values.get("regulation") or "人工补录，未关联知识库条款",
                values.get("source_url") or "",
                None,
                values["risk_reason"],
                values["priority"],
                values["suggested_deadline"],
                json.dumps(values["manual_checks"], ensure_ascii=False),
                "manual",
                "manual",
                "manual",
                "confirmed",
                None,
                now,
            ),
        ).lastrowid
        created = database.execute(
            "SELECT * FROM hazards WHERE id=?", (hazard_id,)
        ).fetchone()
        database.execute(
            """INSERT INTO hazard_actions(
                inspection_id,hazard_id,action_type,before_data,after_data,
                note,actor,created_at
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                inspection_id,
                hazard_id,
                "manual_added",
                None,
                json.dumps(_review_snapshot(created), ensure_ascii=False),
                note,
                "unauthenticated",
                now,
            ),
        )
    return JSONResponse(
        status_code=201,
        content={"hazard": _hazard_dict(created, [], []), "action_type": "manual_added"},
    )


def _inspection_dict(row) -> dict:
    result = dict(row)
    result["uncertain_items"] = _json_list(result.get("uncertain_items"))
    result["review_findings"] = _json_list(result.get("review_findings"))
    try:
        model_info = json.loads(result.get("model_info") or "null")
        result["model_info"] = model_info if isinstance(model_info, dict) else None
    except (json.JSONDecodeError, TypeError):
        result["model_info"] = None
    return result


def _hazard_dict(row, snapshots: list[dict], actions: list[dict]) -> dict:
    result = dict(row)
    result["manual_checks"] = _json_list(result.get("manual_checks"))
    try:
        original_data = json.loads(result.get("original_data") or "null")
        result["original_data"] = (
            original_data if isinstance(original_data, dict) else None
        )
    except (json.JSONDecodeError, TypeError):
        result["original_data"] = None
    result["regulations"] = snapshots
    result["actions"] = actions
    return result


def _review_snapshot(row) -> dict:
    result = {
        field: row[field]
        for field in HAZARD_EDIT_FIELDS
        if field in row.keys()
    }
    result["manual_checks"] = _json_list(result.get("manual_checks"))
    return result


def _action_dict(row) -> dict:
    result = dict(row)
    for field in ("before_data", "after_data"):
        try:
            parsed = json.loads(result.get(field) or "null")
            result[field] = parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            result[field] = None
    return result


def _json_list(value) -> list:
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def dashboard(request: Request):
    with conn(_settings(request)) as database:
        total = database.execute(
            "SELECT COUNT(*) n FROM inspections WHERE mode!='replay'"
        ).fetchone()["n"]
        hazards = database.execute(
            "SELECT COUNT(*) n FROM hazards h JOIN inspections i "
            "ON i.id=h.inspection_id WHERE h.human_status!='rejected' "
            "AND i.mode!='replay'"
        ).fetchone()["n"]
        risks = database.execute(
            "SELECT h.risk,COUNT(*) n FROM hazards h JOIN inspections i "
            "ON i.id=h.inspection_id WHERE h.human_status!='rejected' "
            "AND i.mode!='replay' GROUP BY h.risk"
        ).fetchall()
    return {
        "total_inspections": total,
        "total_hazards": hazards,
        "risk_distribution": [dict(row) for row in risks],
    }


def _demo_message(settings: Settings) -> str:
    if settings.vision_provider == "yolo":
        return "演示模式已选择 YOLO，但本地 YOLO 推理适配器尚未实现，请结合现场复核。"
    return "演示模式未配置完整的火山方舟 API Key 和推理接入点，请结合现场复核。"


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        resolved_settings.upload_path.mkdir(parents=True, exist_ok=True)
        init_db(resolved_settings)
        import_regulations(settings=resolved_settings)
        mark_interrupted_workflows(resolved_settings)
        application.state.workflow_tasks = set()
        yield
        tasks = list(application.state.workflow_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    application = FastAPI(title="慧眼安巡", version="0.8.0", lifespan=lifespan)
    application.state.settings = resolved_settings
    application.state.frontend_dir = FRONTEND_DIR
    application.state.write_rate_limiter = WriteRateLimiter(
        resolved_settings.write_rate_limit_per_minute
    )

    @application.middleware("http")
    async def protect_and_limit(request: Request, call_next):
        settings_for_request = _settings(request)
        if request.url.path != "/api/health" and not basic_auth_valid(
            request.headers.get("Authorization"), settings_for_request
        ):
            return JSONResponse(
                status_code=401,
                content={"detail": "需要访问凭据"},
                headers={"WWW-Authenticate": 'Basic realm="Huiyan Guard"'},
            )
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and (
            request.url.path.startswith("/api/")
        ):
            client_key = request.client.host if request.client else "unknown"
            allowed, retry_after = await request.app.state.write_rate_limiter.allow(
                client_key
            )
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "操作过于频繁，请稍后重试"},
                    headers={"Retry-After": str(retry_after)},
                )
        return await call_next(request)
    application.mount(
        "/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets"
    )
    application.mount(
        "/uploads",
        StaticFiles(directory=resolved_settings.upload_path, check_dir=False),
        name="uploads",
    )
    application.add_api_route("/", index, methods=["GET"])
    application.add_api_route("/records", records_page, methods=["GET"])
    application.add_api_route("/report", report_page, methods=["GET"])
    application.add_api_route("/api/health", health, methods=["GET"])
    application.add_api_route("/api/inspections", create_inspection, methods=["POST"])
    application.add_api_route("/api/inspections", list_inspections, methods=["GET"])
    application.add_api_route(
        "/api/inspections/{inspection_id}", get_inspection, methods=["GET"]
    )
    application.add_api_route(
        "/api/inspections/{inspection_id}/retry",
        retry_inspection,
        methods=["POST"],
    )
    application.add_api_route(
        "/api/inspections/{inspection_id}/hazards",
        create_manual_hazard,
        methods=["POST"],
    )
    application.add_api_route(
        "/api/hazards/{hazard_id}", update_hazard, methods=["PATCH"]
    )
    application.add_api_route("/api/dashboard", dashboard, methods=["GET"])
    return application


app = create_app()
