from __future__ import annotations

import re
from typing import Dict, Iterable, List


_PATTERNS = [
    r"需核实",
    r"需要核实",
    r"待核实",
    r"需确认",
    r"待确认",
    r"verify",
    r"to be verified",
    r"tbd",
    r"unknown",
]

_PATTERN_RE = re.compile("|".join(_PATTERNS), re.IGNORECASE)


def _collect_texts(value: object) -> Iterable[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, dict):
        texts: List[str] = []
        for item in value.values():
            texts.extend(_collect_texts(item))
        return texts
    return [str(value)]


def _clean_item(text: str) -> str:
    cleaned = re.sub(r"[（(].*?(需核实|需要核实|待核实|verify|tbd|unknown).*?[)）]", "", text, flags=re.I)
    return cleaned.strip()


def extract_verification_items(payload: Dict[str, object]) -> List[str]:
    items: List[str] = []
    for text in _collect_texts(payload):
        if not text:
            continue
        if _PATTERN_RE.search(text):
            cleaned = _clean_item(text)
            items.append(cleaned or text.strip())
    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped
