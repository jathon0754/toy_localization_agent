from __future__ import annotations

import re
from typing import Dict, List


def _has_any(text: str, keywords: List[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _extract_age(text: str) -> str:
    patterns = [
        r"(\d{1,2})\s*\+",
        r"(\d{1,2})\s*岁",
        r"(\d{1,2})\s*歲",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return f"{match.group(1)}+"
    return ""


def _age_group_from_age(age_text: str) -> str:
    if not age_text:
        return ""
    match = re.search(r"(\d{1,2})", age_text)
    if not match:
        return ""
    age = int(match.group(1))
    if age <= 2:
        return "0-2"
    if age <= 5:
        return "3-5"
    if age <= 7:
        return "6-7"
    if age <= 9:
        return "8-9"
    return "10+"


def _guess_toy_category(raw: str, lower: str) -> str:
    if _has_any(raw, ["积木", "拼装", "拼搭", "搭建"]) or _has_any(
        lower, ["construction", "blocks", "lego", "assembly", "buildable"]
    ):
        return "construction"
    if _has_any(raw, ["娃娃", "公仔", "人偶"]) or _has_any(lower, ["doll", "figure"]):
        return "doll/figure"
    if _has_any(raw, ["车", "车辆", "赛车"]) or _has_any(lower, ["vehicle", "car", "truck"]):
        return "vehicle"
    if _has_any(raw, ["毛绒", "布偶", "玩偶"]) or _has_any(lower, ["plush", "soft"]):
        return "plush"
    if _has_any(raw, ["机器人"]) or _has_any(lower, ["robot"]):
        return "robot"
    if _has_any(raw, ["拼图", "益智", "智力"]) or _has_any(lower, ["puzzle", "brain"]):
        return "puzzle/educational"
    if _has_any(raw, ["桌游", "棋", "卡牌"]) or _has_any(
        lower, ["board game", "card game"]
    ):
        return "board game"
    if _has_any(raw, ["手工", "DIY", "手作"]) or _has_any(lower, ["craft", "diy"]):
        return "craft"
    return ""


def _extract_materials(raw: str, lower: str) -> List[str]:
    materials = []
    if _has_any(raw, ["木"]) or _has_any(lower, ["wood", "wooden"]):
        materials.append("wood")
    if _has_any(raw, ["塑料", "塑胶"]) or _has_any(lower, ["plastic"]):
        materials.append("plastic")
    if _has_any(raw, ["金属", "铁", "铝"]) or _has_any(lower, ["metal", "steel", "aluminum"]):
        materials.append("metal")
    if _has_any(raw, ["布", "织物", "纺织", "棉"]) or _has_any(
        lower, ["fabric", "textile", "cloth", "cotton"]
    ):
        materials.append("fabric")
    if _has_any(raw, ["硅胶", "硅橡胶"]) or _has_any(lower, ["silicone"]):
        materials.append("silicone")
    return materials


def _detect_connectivity(raw: str, lower: str) -> str:
    if _has_any(raw, ["蓝牙"]) or _has_any(lower, ["bluetooth"]):
        return "bluetooth"
    if _has_any(raw, ["wifi", "wi-fi", "无线网络"]) or _has_any(lower, ["wifi", "wi-fi"]):
        return "wifi"
    if _has_any(raw, ["APP", "应用"]) or _has_any(lower, ["app", "mobile"]):
        return "app"
    if _has_any(raw, ["遥控", "远程"]) or _has_any(lower, ["remote"]):
        return "remote"
    if _has_any(raw, ["无线"]) or _has_any(lower, ["wireless"]):
        return "wireless"
    return ""


def heuristic_features(description: str) -> Dict[str, object]:
    raw = description or ""
    lower = raw.lower()

    has_light = _has_any(raw, ["发光", "灯", "光效", "亮"]) or _has_any(
        lower, ["led", "light"]
    )
    has_sound = _has_any(raw, ["声音", "音效", "音乐", "语音", "语音控制"]) or _has_any(
        lower, ["sound", "music", "voice"]
    )
    has_magnets = _has_any(raw, ["磁"]) or _has_any(lower, ["magnet"])
    has_projectiles = _has_any(raw, ["发射", "弹", "投射", "射击", "射"]) or _has_any(
        lower, ["projectile", "shoot"]
    )
    assembly = _has_any(raw, ["拼装", "组装", "拼接", "积木", "搭建", "拼搭"]) or _has_any(
        lower, ["assembly", "buildable", "construction"]
    )
    small_parts = _has_any(raw, ["小零件", "细小", "零件"]) or assembly
    battery = _has_any(raw, ["电池", "电源", "充电"]) or _has_any(lower, ["battery"])
    connectivity = _detect_connectivity(raw, lower)
    wireless = bool(connectivity and connectivity != "remote")

    battery_type = ""
    if _has_any(raw, ["纽扣电池", "钮扣电池", "扣式电池"]):
        battery_type = "button cell"
    elif _has_any(raw, ["AA", "AAA", "5号", "7号"]):
        battery_type = "AA/AAA"
    elif _has_any(raw, ["锂电", "充电", "USB"]):
        battery_type = "rechargeable"

    power_source = "battery" if battery else ""
    if battery_type:
        power_source = "battery"

    toy_category = _guess_toy_category(raw, lower)
    intended_age = _extract_age(raw)
    age_group = _age_group_from_age(intended_age)
    is_electronic = "yes" if (battery or has_light or has_sound or wireless) else "no"

    risks = []
    if small_parts:
        risks.append("Small parts / choking hazard")
    if has_light:
        risks.append("LED safety / overheating")
    if has_magnets:
        risks.append("Magnet ingestion risk")
    if has_projectiles:
        risks.append("Projectile safety risk")

    return {
        "toy_category": toy_category,
        "intended_age": intended_age,
        "age_group": age_group,
        "target_audience": "",
        "assembly_level": "assembly required" if assembly else "",
        "is_electronic": is_electronic,
        "has_small_parts": "yes" if small_parts else "no",
        "battery_type": battery_type,
        "power_source": power_source,
        "has_light": "yes" if has_light else "no",
        "has_sound": "yes" if has_sound else "no",
        "has_magnets": "yes" if has_magnets else "no",
        "has_projectiles": "yes" if has_projectiles else "no",
        "wireless": "yes" if wireless else "no",
        "connectivity": connectivity,
        "use_scenario": "",
        "materials_mentioned": _extract_materials(raw, lower),
        "safety_risks": risks,
    }
