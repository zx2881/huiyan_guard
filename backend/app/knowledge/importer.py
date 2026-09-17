import json
from pathlib import Path

from ..config import REPO_ROOT, Settings, get_settings
from ..database import conn, init_db
from .models import RegulationFile


DEFAULT_SOURCE = REPO_ROOT / "knowledge" / "dormitory" / "regulations.json"


def import_regulations(
    source: Path = DEFAULT_SOURCE, settings: Settings | None = None
) -> int:
    resolved_settings = settings or get_settings()
    raw = json.loads(source.read_text(encoding="utf-8"))
    regulation_file = RegulationFile.model_validate(raw)
    checklist_path = REPO_ROOT / "knowledge" / regulation_file.scene / "checklist.json"
    checklist = json.loads(checklist_path.read_text(encoding="utf-8"))
    known_check_ids = {item["id"] for item in checklist.get("items", [])}
    referenced_check_ids = {
        check_id
        for regulation in regulation_file.regulations
        for check_id in regulation.check_ids
    }
    unknown_check_ids = referenced_check_ids - known_check_ids
    if unknown_check_ids:
        unknown = "、".join(sorted(unknown_check_ids))
        raise ValueError(f"条款引用了不存在的检查项：{unknown}")

    init_db(resolved_settings)
    statement = """
        INSERT INTO regulations(
            id,scene,document_title,document_number,source_file,article,content,
            source_url,verified_at,keywords,check_ids
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            scene=excluded.scene,
            document_title=excluded.document_title,
            document_number=excluded.document_number,
            source_file=excluded.source_file,
            article=excluded.article,
            content=excluded.content,
            source_url=excluded.source_url,
            verified_at=excluded.verified_at,
            keywords=excluded.keywords,
            check_ids=excluded.check_ids
    """
    with conn(resolved_settings) as database:
        for item in regulation_file.regulations:
            database.execute(
                statement,
                (
                    item.id,
                    item.scene,
                    item.document_title,
                    item.document_number,
                    item.source_file,
                    item.article,
                    item.content,
                    str(item.source_url),
                    item.verified_at.isoformat(),
                    json.dumps(item.keywords, ensure_ascii=False),
                    json.dumps(item.check_ids, ensure_ascii=False),
                ),
            )
    return len(regulation_file.regulations)
