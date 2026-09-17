import json
import re

from ..config import Settings, get_settings
from ..database import conn


SYNONYM_GROUPS = (
    {"通道", "走廊", "过道", "门口", "出口", "疏散", "逃生"},
    {"堵塞", "堵住", "占用", "堆放", "封闭", "阻挡", "障碍物"},
    {"插线板", "排插", "插排", "接线板", "拖线板", "电源板"},
    {"遮挡", "覆盖", "盖住", "埋压", "圈占"},
    {"电线", "线路", "电缆", "飞线", "私拉乱接", "乱接"},
    {"大功率电器", "电炉", "热得快", "电热棒", "电热器"},
    {"明火", "蜡烛", "蚊香", "酒精炉", "吸烟", "烟头"},
    {"易燃易爆", "危险品", "酒精", "汽油", "烟花爆竹"},
    {"消防设施", "灭火器", "消火栓", "消防器材"},
    {"防火门", "常闭门", "消防门"},
    {"电动车", "电动自行车", "锂电池", "电池", "室内充电"},
)


def _normalize(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.lower())


def _expanded_terms(query: str) -> tuple[set[str], set[str]]:
    normalized = _normalize(query)
    direct = {term for group in SYNONYM_GROUPS for term in group if term in normalized}
    expanded = set(direct)
    for group in SYNONYM_GROUPS:
        if direct & group:
            expanded.update(group)
    return direct, expanded


def retrieve_regulations(
    scene: str,
    query: str,
    *,
    check_id: str | None = None,
    limit: int = 3,
    settings: Settings | None = None,
) -> list[dict]:
    """Return scored, traceable clauses; return [] when nothing actually matches."""

    if scene not in {"dormitory", "laboratory"} or not query.strip() or limit <= 0:
        return []
    resolved_settings = settings or get_settings()
    query_normalized = _normalize(query)
    direct_terms, expanded_terms = _expanded_terms(query)
    with conn(resolved_settings) as database:
        rows = database.execute(
            "SELECT * FROM regulations WHERE scene=?", (scene,)
        ).fetchall()

    matches: list[tuple[int, dict]] = []
    for row in rows:
        item = dict(row)
        try:
            keywords = json.loads(item.get("keywords") or "[]")
            check_ids = json.loads(item.get("check_ids") or "[]")
        except (json.JSONDecodeError, TypeError):
            continue
        score = 0
        matched_keywords: list[str] = []
        for keyword in keywords:
            normalized_keyword = _normalize(str(keyword))
            if not normalized_keyword:
                continue
            if normalized_keyword in query_normalized:
                score += 4
                matched_keywords.append(keyword)
            elif keyword in direct_terms:
                score += 3
                matched_keywords.append(keyword)
            elif keyword in expanded_terms:
                score += 1
                matched_keywords.append(keyword)
        if check_id and check_id in check_ids:
            score += 8
        if score <= 0:
            continue
        item["keywords"] = keywords
        item["check_ids"] = check_ids
        item["matched_keywords"] = sorted(set(matched_keywords))
        item["score"] = score
        matches.append((score, item))

    matches.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [item for _, item in matches[:limit]]
