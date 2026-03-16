from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from knowledge.retriever import CountryKnowledgeRetriever


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_UNSAFE_TOKENS = ("/", "\\", "..", ":", "\u0000")


@dataclass(frozen=True)
class MarketNormalizationResult:
    raw: str
    normalized: str
    alias_of: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    confidence: str = "low"


def _is_unsafe(value: str) -> bool:
    return any(token in value for token in _UNSAFE_TOKENS)


def _normalize_ascii(value: str) -> str:
    lowered = value.lower().strip()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def _slugify(value: str) -> str:
    lowered = value.lower().strip()
    slug = re.sub(r"[^a-z0-9-]+", "-", lowered)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or lowered


def normalize_market(raw: str, available: Optional[List[str]] = None) -> MarketNormalizationResult:
    if raw is None:
        raise ValueError("Target market cannot be empty.")
    raw_text = str(raw).strip()
    if not raw_text:
        raise ValueError("Target market cannot be empty.")
    if _is_unsafe(raw_text):
        raise ValueError("Invalid target market. Please avoid '/', '\\\\', '..', ':', or null bytes.")

    available = available or CountryKnowledgeRetriever.available_countries()
    available_set = {item.lower() for item in available}

    normalized_ascii = _normalize_ascii(raw_text)
    if normalized_ascii in available_set:
        return MarketNormalizationResult(
            raw=raw_text,
            normalized=normalized_ascii,
            confidence="high",
        )

    alias_map = {
        "usa": ["us", "u.s.", "u.s.a", "united states", "america", "\u7f8e\u56fd", "\u7f8e\u570b", "\u7f8e\u5229\u575a"],
        "japan": ["jp", "\u65e5\u672c", "\u65e5\u672c\u56fd", "\u65e5\u672c\u570b"],
        "saudi": ["saudi", "saudi arabia", "\u6c99\u7279", "\u6c99\u7279\u963f\u62c9\u4f2f"],
        "cn": ["china", "\u4e2d\u56fd", "\u4e2d\u570b", "\u4e2d\u56fd\u5927\u9646", "\u5927\u9646", "\u5185\u5730"],
        "hk": ["hong kong", "hk", "\u9999\u6e2f", "\u9999\u6e2f\u7279\u522b\u884c\u653f\u533a"],
        "mo": ["macau", "mo", "\u6fb3\u95e8", "\u6fb3\u9580"],
        "tw": ["taiwan", "tw", "\u53f0\u6e7e", "\u53f0\u7063", "\u81fa\u7063"],
        "uk": ["united kingdom", "britain", "great britain", "uk", "gb", "\u82f1\u56fd", "\u82f1\u570b"],
    }

    for code, aliases in alias_map.items():
        for alias in aliases:
            if normalized_ascii == _normalize_ascii(alias):
                notes = []
                confidence = "high" if code in available_set else "medium"
                if code not in available_set:
                    notes.append(f"No local knowledge file for '{code}', using generic reference.")
                return MarketNormalizationResult(
                    raw=raw_text,
                    normalized=code,
                    alias_of=alias,
                    notes=notes,
                    confidence=confidence,
                )

    if _CJK_RE.search(raw_text):
        fujian_markers = [
            "\u798f\u5efa",
            "\u798f\u5dde",
            "\u53a6\u95e8",
            "\u5eea\u9580",
            "\u6cc9\u5dde",
            "\u6f33\u5dde",
            "\u8386\u7530",
            "\u9f99\u5ca9",
            "\u9f8d\u5dd6",
            "\u5357\u5e73",
            "\u5b81\u5fb7",
            "\u5be7\u5fb7",
            "\u4e09\u660e",
        ]
        if any(marker in raw_text for marker in fujian_markers):
            preferred = "cn-fujian"
            notes = ["Detected Fujian region; mapped to cn-fujian."]
            if preferred not in available_set:
                preferred = "cn"
                notes.append("No cn-fujian knowledge file; falling back to cn.")
            if preferred not in available_set:
                notes.append(f"No local knowledge file for '{preferred}', using generic reference.")
            return MarketNormalizationResult(
                raw=raw_text,
                normalized=preferred,
                notes=notes,
                confidence="medium",
            )

        notes = ["Detected Chinese locale; mapped to cn."]
        if "cn" not in available_set:
            notes.append("No local knowledge file for 'cn', using generic reference.")
        return MarketNormalizationResult(
            raw=raw_text,
            normalized="cn",
            notes=notes,
            confidence="medium",
        )

    slug = _slugify(raw_text)
    notes = []
    confidence = "low"
    if slug in available_set:
        confidence = "high"
    elif slug != raw_text:
        notes.append("Normalized market code by slugifying input.")
    if slug not in available_set:
        notes.append(f"No local knowledge file for '{slug}', using generic reference.")
    return MarketNormalizationResult(
        raw=raw_text,
        normalized=slug,
        notes=notes,
        confidence=confidence,
    )
