from __future__ import annotations

from typing import Any, Dict, List


def _base_market(code: str) -> str:
    raw = str(code or "").strip().lower()
    return raw.split("-", 1)[0] if "-" in raw else raw


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    output = []
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


BASE_STANDARDS = {
    "usa": [
        "ASTM F963 (toy safety)",
        "CPSIA (consumer product safety)",
        "16 CFR Part 1501 (small parts)",
    ],
    "us": [
        "ASTM F963 (toy safety)",
        "CPSIA (consumer product safety)",
        "16 CFR Part 1501 (small parts)",
    ],
    "uk": [
        "UKCA / EN71 (toy safety)",
    ],
    "gb": [
        "UKCA / EN71 (toy safety)",
    ],
    "eu": [
        "EN71-1/2/3 (toy safety)",
        "REACH (chemicals)",
    ],
    "de": [
        "EN71-1/2/3 (toy safety)",
        "REACH (chemicals)",
    ],
    "fr": [
        "EN71-1/2/3 (toy safety)",
        "REACH (chemicals)",
    ],
    "japan": [
        "ST 2016 (toy safety)",
    ],
    "jp": [
        "ST 2016 (toy safety)",
    ],
    "cn": [
        "GB 6675 (toy safety)",
        "GB/T 19865 (safety warnings)",
    ],
    "saudi": [
        "SASO toy safety requirements (verify)",
    ],
}


def required_tests(market: str, feature_data: Dict[str, Any]) -> List[str]:
    base = _base_market(market)
    items = list(BASE_STANDARDS.get(base, []))

    def flag(field: str) -> str:
        return str(feature_data.get(field) or "").strip().lower()

    if flag("has_small_parts") == "yes":
        items.append("Small parts / choking hazard testing")
    if flag("is_electronic") == "yes":
        items.append("Electrical safety / overheating checks")
        items.append("EMC compliance (electronics)")
    if flag("wireless") == "yes":
        items.append("RF / wireless compliance (Bluetooth/Wi‑Fi)")
    if flag("battery_type") in {"button cell", "coin", "button"}:
        items.append("Button/coin cell safety (ingestion protection)")
    if flag("has_magnets") == "yes":
        items.append("Magnet strength & ingestion risk testing")

    if not items:
        items.append("Verify applicable toy safety standards and labeling requirements.")

    return _dedupe(items)
