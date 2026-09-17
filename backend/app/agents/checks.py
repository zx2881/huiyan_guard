from ..schemas.inspection import VisualHazard


CHECK_TERMS = (
    ("ebike_battery_indoor", ("电动自行车", "电动车", "锂电池", "飞线充电", "室内充电")),
    ("open_flame", ("明火", "蜡烛", "烟头", "吸烟", "酒精炉", "蚊香")),
    ("flammable_storage", ("易燃易爆", "危险品", "汽油", "烟花爆竹")),
    ("fire_door_open", ("防火门", "常闭门", "防火卷帘")),
    ("fire_equipment_blocked", ("消火栓", "灭火器", "消防设施", "消防器材")),
    ("blocked_exit", ("通道", "走廊", "过道", "门口", "安全出口", "堵塞")),
    ("unsafe_wiring", ("私拉乱接", "电线", "线路", "飞线")),
    ("high_power_appliance", ("大功率", "电炉", "热得快", "电热棒")),
    ("socket_cover", ("插线板", "插排", "排插", "接线板")),
    ("escape_obstacle", ("逃生障碍", "铁栅栏", "门窗障碍", "阳台障碍")),
)


def infer_check_id(hazard: VisualHazard) -> str | None:
    if hazard.check_id:
        return hazard.check_id
    text = f"{hazard.name} {hazard.location} {hazard.evidence}".lower()
    for check_id, terms in CHECK_TERMS:
        if any(term in text for term in terms):
            return check_id
    return None
