from datetime import datetime, timezone
from pathlib import Path
import shutil
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .agents.perceive import perceive
from .database import conn, init_db
from .integrations.vision_client import VisionClient

app = FastAPI(title="慧眼安巡", version="0.2.0")
BASE = Path(__file__).resolve().parents[2]
FRONT = BASE / "frontend"
UPLOAD_DIR = BASE / "data" / "uploads" / "inspections"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
init_db()


@app.on_event("startup")
def startup():
    init_db()


app.mount("/assets", StaticFiles(directory=FRONT / "assets"), name="assets")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/")
def index():
    return FileResponse(FRONT / "index.html")


@app.get("/records")
def records_page():
    return FileResponse(FRONT / "records.html")


@app.get("/report")
def report_page():
    return FileResponse(FRONT / "report.html")


@app.post("/api/inspections")
async def create_inspection(scene: str = Form(...), image: UploadFile = File(...)):
    if scene not in ("dormitory", "laboratory"):
        raise HTTPException(400, "不支持的检查场景")

    allowed = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    if image.content_type not in allowed:
        raise HTTPException(400, "只支持 JPEG、PNG 和 WebP 图片")

    name = f"{uuid.uuid4().hex}{allowed[image.content_type]}"
    image_path = UPLOAD_DIR / name
    with image_path.open("wb") as output:
        shutil.copyfileobj(image.file, output)

    now = datetime.now(timezone.utc).isoformat()
    client_enabled = VisionClient().enabled
    with conn() as db:
        inspection_id = db.execute(
            "INSERT INTO inspections(scene,image_path,status,created_at) VALUES(?,?,?,?)",
            (scene, name, "analyzing" if client_enabled else "completed", now),
        ).lastrowid

    if not client_enabled:
        with conn() as db:
            db.execute(
                "INSERT INTO hazards(inspection_id,name,location,evidence,risk,advice,regulation,source_url) VALUES(?,?,?,?,?,?,?,?)",
                (inspection_id, "待人工确认的现场风险", "照片中可见区域", "演示模式未配置完整的火山方舟 API Key 和推理接入点，请结合现场复核。", "提示", "配置火山视觉模型后重新上传照片，或由安全管理员现场确认。", "当前知识库未检索到适用条款", ""),
            )
            db.execute("UPDATE inspections SET completed_at=? WHERE id=?", (now, inspection_id))
        return {"id": inspection_id, "status": "completed", "mode": "demo"}

    try:
        result = await perceive(BASE, image_path, scene)
        hazards = result.get("hazards", [])
        uncertain = result.get("uncertain_items", [])
        with conn() as db:
            for hazard in hazards:
                confidence = hazard.get("confidence")
                evidence = hazard.get("evidence") or "暂无证据说明"
                if confidence is not None:
                    evidence = f"{evidence}（模型置信度：{float(confidence):.0%}）"
                db.execute(
                    "INSERT INTO hazards(inspection_id,name,location,evidence,risk,advice,regulation,source_url) VALUES(?,?,?,?,?,?,?,?)",
                    (inspection_id, hazard.get("name") or "未命名隐患", hazard.get("location") or "无法从当前照片确认", evidence, "待分级", "待接入整改建议模型", "待接入规章检索", ""),
                )
            if not hazards:
                summary = "；".join(str(x) for x in uncertain) or "当前照片未发现明确隐患，但不代表整个场所绝对安全。"
                db.execute(
                    "INSERT INTO hazards(inspection_id,name,location,evidence,risk,advice,regulation,source_url) VALUES(?,?,?,?,?,?,?,?)",
                    (inspection_id, "未发现明确隐患", "当前照片可见区域", summary, "未分级", "建议结合现场检查清单继续人工巡检。", "当前知识库未检索到适用条款", ""),
                )
            completed = datetime.now(timezone.utc).isoformat()
            db.execute("UPDATE inspections SET status='completed',completed_at=?,error=NULL WHERE id=?", (completed, inspection_id))
        return {"id": inspection_id, "status": "completed", "mode": "vision"}
    except Exception as exc:
        with conn() as db:
            db.execute("UPDATE inspections SET status='failed',error=? WHERE id=?", (str(exc)[:1000], inspection_id))
        raise HTTPException(502, f"视觉模型分析失败：{exc}") from exc


@app.get("/api/inspections")
def list_inspections():
    with conn() as db:
        return [dict(row) for row in db.execute("SELECT * FROM inspections ORDER BY id DESC")]


@app.get("/api/inspections/{inspection_id}")
def get_inspection(inspection_id: int):
    with conn() as db:
        inspection = db.execute("SELECT * FROM inspections WHERE id=?", (inspection_id,)).fetchone()
        hazards = db.execute("SELECT * FROM hazards WHERE inspection_id=?", (inspection_id,)).fetchall()
    if not inspection:
        raise HTTPException(404, "巡检记录不存在")
    result = dict(inspection)
    result["hazards"] = [dict(hazard) for hazard in hazards]
    return result


@app.get("/api/dashboard")
def dashboard():
    with conn() as db:
        total = db.execute("SELECT COUNT(*) n FROM inspections").fetchone()["n"]
        hazards = db.execute("SELECT COUNT(*) n FROM hazards").fetchone()["n"]
        risks = db.execute("SELECT risk,COUNT(*) n FROM hazards GROUP BY risk").fetchall()
    return {"total_inspections": total, "total_hazards": hazards, "risk_distribution": [dict(row) for row in risks]}
