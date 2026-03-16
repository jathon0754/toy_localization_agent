from __future__ import annotations

import re
from typing import Dict, Iterable


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_JA_RE = re.compile(r"[\u3040-\u30ff]")
_KO_RE = re.compile(r"[\uac00-\ud7af]")
_ALPHA_RE = re.compile(r"[A-Za-z]")

_SUPPORTED_LANGUAGE_CODES = {
    "zh",
    "en",
    "ja",
    "ko",
    "de",
    "fr",
    "es",
    "it",
    "pt",
    "ar",
}

_MARKET_LANGUAGE_MAP = {
    "usa": "en",
    "us": "en",
    "uk": "en",
    "gb": "en",
    "australia": "en",
    "canada": "en",
    "japan": "ja",
    "jp": "ja",
    "korea": "ko",
    "kr": "ko",
    "cn": "zh",
    "hk": "zh",
    "mo": "zh",
    "tw": "zh",
    "germany": "de",
    "france": "fr",
    "spain": "es",
    "italy": "it",
    "brazil": "pt",
    "portugal": "pt",
    "saudi": "ar",
    "uae": "ar",
}


def detect_target_language(text: str) -> str:
    if _JA_RE.search(text or ""):
        return "ja"
    if _KO_RE.search(text or ""):
        return "ko"
    if _CJK_RE.search(text or ""):
        return "zh"
    return "en"


def normalize_language_code(code: str) -> str:
    raw = str(code or "").strip().lower().replace("_", "-")
    if not raw:
        return ""
    if raw in _SUPPORTED_LANGUAGE_CODES:
        return raw
    if "-" in raw:
        base = raw.split("-", 1)[0]
        if base in _SUPPORTED_LANGUAGE_CODES:
            return base
    return ""


def market_default_language(market: str) -> str:
    base = str(market or "").strip().lower()
    if "-" in base:
        base = base.split("-", 1)[0]
    return _MARKET_LANGUAGE_MAP.get(base, "")


def resolve_target_language(
    market: str, description: str, override: str = "", metadata_language: str = ""
) -> tuple[str, list[str]]:
    notes: list[str] = []
    override_norm = normalize_language_code(override)
    if override and not override_norm:
        notes.append(f"Unknown target_language '{override}', falling back to market/description.")
    if override_norm:
        return override_norm, notes

    metadata_norm = normalize_language_code(metadata_language)
    if metadata_language and not metadata_norm:
        notes.append(
            f"Unknown metadata language '{metadata_language}', falling back to market/description."
        )

    market_lang = market_default_language(market)
    desc_lang = detect_target_language(description)
    if metadata_norm:
        if market_lang and metadata_norm != market_lang:
            notes.append(
                f"Metadata language '{metadata_norm}' differs from market default '{market_lang}'."
            )
        if desc_lang and metadata_norm != desc_lang:
            notes.append(
                f"Description language '{desc_lang}' differs from metadata language '{metadata_norm}'."
            )
        return metadata_norm, notes

    if market_lang:
        if desc_lang and desc_lang != market_lang:
            notes.append(
                f"Description language '{desc_lang}' differs from market default '{market_lang}'."
            )
        return market_lang, notes

    return desc_lang or "en", notes


def _collect_texts(value: object) -> Iterable[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, dict):
        texts = []
        for item in value.values():
            texts.extend(_collect_texts(item))
        return texts
    return [str(value)]


def language_stats(payload: Dict[str, object]) -> Dict[str, int]:
    cjk = 0
    alpha = 0
    for text in _collect_texts(payload):
        cjk += len(_CJK_RE.findall(text))
        cjk += len(_JA_RE.findall(text))
        cjk += len(_KO_RE.findall(text))
        alpha += len(_ALPHA_RE.findall(text))
    return {"cjk": cjk, "alpha": alpha}


def needs_language_normalization(payload: Dict[str, object], target_lang: str) -> bool:
    stats = language_stats(payload)
    cjk = stats["cjk"]
    alpha = stats["alpha"]
    if target_lang in {"zh", "ja", "ko"}:
        return alpha > max(20, cjk * 2)
    if target_lang == "en":
        return cjk > max(10, alpha * 2)
    return False


def language_name(code: str) -> str:
    normalized = normalize_language_code(code)
    if normalized == "zh":
        return "Chinese"
    if normalized == "ja":
        return "Japanese"
    if normalized == "ko":
        return "Korean"
    if normalized == "de":
        return "German"
    if normalized == "fr":
        return "French"
    if normalized == "es":
        return "Spanish"
    if normalized == "it":
        return "Italian"
    if normalized == "pt":
        return "Portuguese"
    if normalized == "ar":
        return "Arabic"
    return "English"
