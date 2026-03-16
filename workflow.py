"""Core workflow orchestration shared by CLI and web UI."""

import json
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from config import (
    EMBEDDING_MODEL,
    IMAGE_GEN_MODEL,
    LLM_API_BASE,
    LLM_JSON_REPAIR,
    LLM_MODEL,
    LLM_WIRE_API,
    resolve_run_output_dir,
)
from agents.coordinator import CoordinatorAgent
from agents.culture_agent import CultureAgent
from agents.design_agent import DesignAgent
from agents.feature_extractor import FeatureExtractorAgent
from agents.json_repair import JsonRepairAgent
from agents.language_normalizer import LanguageNormalizerAgent
from agents.regulation_agent import RegulationAgent
from feature_heuristics import heuristic_features
from formatting import extract_json_object, format_final_plan_markdown
from language_utils import needs_language_normalization, resolve_target_language, market_default_language
from market_normalizer import normalize_market
from regulation_matrix import required_tests as build_required_tests
from verification import extract_verification_items
from schemas import (
    COORDINATOR_SPEC,
    CULTURE_SPEC,
    DESIGN_SPEC,
    FEATURE_SPEC,
    REGULATION_SPEC,
    CoordinatorOutput,
    CultureOutput,
    DesignOutput,
    FeatureOutput,
    RegulationOutput,
    has_substantive_content,
    normalize_payload,
    schema_stub,
    validate_model,
)


LogHook = Optional[Callable[[str], None]]
ResultHook = Optional[Callable[[Dict[str, Any]], None]]


def _build_repair_prompt(label: str, spec: Any, raw_text: str, *, strict: bool = False) -> str:
    schema_hint = json.dumps(schema_stub(spec), ensure_ascii=False, indent=2)
    strict_hint = ""
    if strict:
        strict_hint = (
            "Ensure the JSON contains at least one non-empty field. "
            "If the input is unclear, infer minimal best-effort content rather than leaving fields empty."
        )
    return (
        f"Target schema ({label}):\n{schema_hint}\n\n"
        "Raw output:\n"
        f"{raw_text}\n\n"
        "Return ONLY the JSON object that matches the schema. "
        f"{strict_hint}".strip()
    )


def _parse_and_validate_output(
    raw_text: str,
    *,
    label: str,
    model_cls: Any,
    spec: Any,
    repair_agent: Optional[JsonRepairAgent],
    language_agent: Optional[LanguageNormalizerAgent],
    target_lang: str,
    stage_warnings: Dict[str, str],
    log: Callable[[str], None],
) -> tuple[str, Dict[str, Any]]:
    extracted = extract_json_object(raw_text) if raw_text else None
    normalized = normalize_payload(extracted or {}, spec)
    validated, err = validate_model(model_cls, normalized)
    needs_repair = bool(raw_text and raw_text.strip()) and (
        extracted is None or not has_substantive_content(normalized, spec)
    )

    if (needs_repair or err) and repair_agent is not None:
        try:
            prompt = _build_repair_prompt(label, spec, raw_text)
            log(f"[{label}] JSON invalid, attempting repair...")
            repaired_text = repair_agent.run(prompt)
            repaired_extracted = extract_json_object(repaired_text) or {}
            repaired_normalized = normalize_payload(repaired_extracted, spec)
            repaired_valid, repaired_err = validate_model(model_cls, repaired_normalized)
            if has_substantive_content(repaired_normalized, spec):
                if repaired_err:
                    stage_warnings[f"{label}_schema"] = repaired_err
                stage_warnings[f"{label}_repair"] = "Used repaired JSON output."
                return repaired_text, repaired_valid
            stage_warnings[f"{label}_repair"] = "Repair returned empty payload; retrying strict repair."

            strict_prompt = _build_repair_prompt(label, spec, raw_text, strict=True)
            log(f"[{label}] Attempting strict repair...")
            strict_text = repair_agent.run(strict_prompt)
            strict_extracted = extract_json_object(strict_text) or {}
            strict_normalized = normalize_payload(strict_extracted, spec)
            strict_valid, strict_err = validate_model(model_cls, strict_normalized)
            if has_substantive_content(strict_normalized, spec):
                if strict_err:
                    stage_warnings[f"{label}_schema"] = strict_err
                stage_warnings[f"{label}_repair"] = "Used strict repaired JSON output."
                return strict_text, strict_valid
            stage_warnings[f"{label}_repair"] = "Strict repair returned empty payload; using original."
        except Exception as exc:
            stage_warnings[f"{label}_repair"] = f"Repair failed: {exc}"
    elif err:
        stage_warnings[f"{label}_schema"] = err
    elif needs_repair:
        stage_warnings[f"{label}_schema"] = "JSON payload was empty after parsing."

    if language_agent is not None and target_lang:
        try:
            if needs_language_normalization(validated, target_lang):
                log(f"[{label}] Language mismatch detected, normalizing...")
                normalized_text = language_agent.run(validated, target_lang=target_lang)
                normalized_extracted = extract_json_object(normalized_text) or {}
                normalized_payload = normalize_payload(normalized_extracted, spec)
                normalized_valid, normalized_err = validate_model(model_cls, normalized_payload)
                if normalized_err:
                    stage_warnings[f"{label}_language"] = normalized_err
                if has_substantive_content(normalized_payload, spec):
                    stage_warnings[f"{label}_language"] = "Normalized output language."
                    return normalized_text, normalized_valid
                stage_warnings[f"{label}_language"] = "Language normalization returned empty payload."
        except Exception as exc:
            stage_warnings[f"{label}_language"] = f"Language normalization failed: {exc}"

    if not has_substantive_content(validated, spec):
        stage_warnings[f"{label}_empty"] = "Output was empty after parsing."

    return raw_text, validated


def _is_missing_text(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, list):
        return not any(str(item).strip() for item in value)
    text = str(value).strip().lower()
    return text in {"", "unknown", "tbd", "n/a", "na", "none", "null"}


def _build_missing_feature_items(
    feature_data: Dict[str, Any], target_lang: str
) -> List[Dict[str, str]]:
    if not feature_data:
        return []

    is_zh = (target_lang or "").lower().startswith("zh")
    items: List[Dict[str, str]] = []

    def add(field: str, zh_q: str, en_q: str) -> None:
        items.append({"field": field, "question": zh_q if is_zh else en_q})

    if _is_missing_text(feature_data.get("intended_age")) and _is_missing_text(
        feature_data.get("age_group")
    ):
        add("intended_age", "确认目标年龄段/年龄标识。", "Confirm target age range / age grading.")

    if _is_missing_text(feature_data.get("has_small_parts")):
        add(
            "has_small_parts",
            "是否包含可拆卸小零件（窒息风险）？",
            "Does the toy include small/detachable parts (choking risk)?",
        )

    if str(feature_data.get("is_electronic") or "").strip().lower() == "yes":
        if _is_missing_text(feature_data.get("battery_type")):
            add(
                "battery_type",
                "电池类型（纽扣/AA/可充电）？",
                "Battery type (button cell / AA / rechargeable)?",
            )
        if _is_missing_text(feature_data.get("power_source")):
            add(
                "power_source",
                "电源方式（电池/USB/无）？",
                "Power source (battery / USB / none)?",
            )

    if str(feature_data.get("wireless") or "").strip().lower() == "yes" and _is_missing_text(
        feature_data.get("connectivity")
    ):
        add(
            "connectivity",
            "无线协议（蓝牙/Wi-Fi/2.4G）？",
            "Wireless protocol (Bluetooth / Wi‑Fi / 2.4G)?",
        )

    if _is_missing_text(feature_data.get("materials_mentioned")):
        add(
            "materials_mentioned",
            "主要材料（塑料/木/金属/布料）？",
            "Primary materials (plastic / wood / metal / fabric)?",
        )

    return items


def _normalize_yes_no(value: str) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"y", "yes", "true", "1", "是", "有"}:
        return "yes"
    if raw in {"n", "no", "false", "0", "否", "无"}:
        return "no"
    return raw


def _parse_list_value(value: str) -> List[str]:
    if not value:
        return []
    raw = str(value)
    parts = []
    for sep in (",", "，", ";", "；", "\n"):
        if sep in raw:
            parts = [item.strip() for item in raw.split(sep) if item.strip()]
            if parts:
                return parts
    return [raw.strip()] if raw.strip() else []


def _age_group_from_age_text(value: str) -> str:
    if not value:
        return ""
    for token in value.split():
        token = token.strip()
        if not token:
            continue
        digits = "".join(ch for ch in token if ch.isdigit())
        if not digits:
            continue
        age = int(digits)
        if age <= 2:
            return "0-2"
        if age <= 5:
            return "3-5"
        if age <= 7:
            return "6-7"
        if age <= 9:
            return "8-9"
        return "10+"
    return ""


def _apply_feature_overrides(
    feature_data: Dict[str, Any], overrides: Dict[str, str]
) -> Dict[str, Any]:
    if not overrides:
        return feature_data
    updated = dict(feature_data or {})
    for field, value in overrides.items():
        if field in {"has_small_parts", "is_electronic", "wireless"}:
            updated[field] = _normalize_yes_no(value)
        elif field == "materials_mentioned":
            updated[field] = _parse_list_value(value)
        else:
            updated[field] = str(value).strip()

    if "intended_age" in overrides and not updated.get("age_group"):
        updated["age_group"] = _age_group_from_age_text(str(updated.get("intended_age") or ""))

    if "connectivity" in overrides:
        connectivity = str(updated.get("connectivity") or "").strip().lower()
        if connectivity and connectivity not in {"none", "no", "n/a"}:
            updated["wireless"] = "yes"

    return updated


def _prompt_for_missing_features(
    items: List[Dict[str, str]], target_lang: str
) -> Dict[str, str]:
    if not items:
        return {}
    is_zh = (target_lang or "").lower().startswith("zh")
    print("\n[features] Missing critical details detected.")
    print("Please provide the following to continue.\n" if not is_zh else "请补充以下信息后继续。\n")
    overrides: Dict[str, str] = {}
    for item in items:
        question = item.get("question") or ""
        field = item.get("field") or ""
        if not field:
            continue
        try:
            answer = input(f"- {question} ").strip()
        except EOFError:
            return overrides
        if answer:
            overrides[field] = answer
    return overrides


def _build_compliance_blockers(
    *,
    market: str,
    knowledge_version: str,
    regulation_data: Dict[str, Any],
    target_lang: str,
) -> List[str]:
    is_zh = (target_lang or "").lower().startswith("zh")
    blockers: List[str] = []

    if knowledge_version == "missing":
        blockers.append(
            f"缺少 {market} 本地法规知识库，必须核实玩具安全/标签/化学物质要求。"
            if is_zh
            else f"No local regulation knowledge for {market}; verify toy safety, labeling, and chemical limits."
        )

    if regulation_data is not None:
        has_any = any(
            str(regulation_data.get(key) or "").strip()
            for key in ("age_grading", "notes")
        ) or any(
            regulation_data.get(key)
            for key in ("requirements", "design_changes", "labeling", "materials_chemicals")
        )
        if not has_any:
            blockers.append(
                "法规输出为空，必须补充合规要求。"
                if is_zh
                else "Regulation output is empty; compliance requirements must be supplied."
            )

    return blockers


def _estimate_cost_weight(action: str, *, is_zh: bool) -> str:
    text = str(action or "").lower()
    high_keywords = [
        "tooling",
        "mold",
        "cert",
        "test",
        "battery",
        "electronic",
        "wireless",
        "rf",
        "模具",
        "工装",
        "认证",
        "测试",
        "电池",
        "电子",
        "无线",
        "射频",
    ]
    low_keywords = [
        "label",
        "copy",
        "packaging",
        "color",
        "manual",
        "logo",
        "插图",
        "说明书",
        "包装",
        "颜色",
        "文案",
        "标签",
    ]
    if any(k in text for k in high_keywords):
        return "高" if is_zh else "High"
    if any(k in text for k in low_keywords):
        return "低" if is_zh else "Low"
    return "中" if is_zh else "Medium"


def _build_priority_actions(
    plan_data: Dict[str, Any],
    target_lang: str,
    *,
    compliance_blockers: Optional[List[str]] = None,
    risk_score: int = 0,
) -> List[str]:
    is_zh = (target_lang or "").lower().startswith("zh")
    output: List[str] = []

    blockers = compliance_blockers or []
    if blockers and risk_score >= 70:
        for item in blockers:
            if is_zh:
                output.append(f"P0/高：{item}")
            else:
                output.append(f"P0/High: {item}")

    for label, key in (("P0", "must_actions"), ("P1", "should_actions"), ("P2", "could_actions")):
        for action in plan_data.get(key) or []:
            cost = _estimate_cost_weight(action, is_zh=is_zh)
            if is_zh:
                output.append(f"{label}/{cost}：{action}")
            else:
                output.append(f"{label}/{cost}: {action}")
    return output[:12]


def _estimate_timeline(plan_data: Dict[str, Any], target_lang: str) -> str:
    is_zh = (target_lang or "").lower().startswith("zh")
    if plan_data.get("compliance_actions") or plan_data.get("verification_required") or plan_data.get(
        "cost_testing"
    ):
        return "4-8 周" if is_zh else "4-8 weeks"
    if plan_data.get("design_changes"):
        return "2-4 周" if is_zh else "2-4 weeks"
    if plan_data.get("cultural_actions"):
        return "1-2 周" if is_zh else "1-2 weeks"
    return ""


def _estimate_cost(plan_data: Dict[str, Any], target_lang: str) -> str:
    is_zh = (target_lang or "").lower().startswith("zh")
    impact = str(plan_data.get("cost_impact") or "").lower()
    if any(token in impact for token in ("high", "高")):
        return "高" if is_zh else "High"
    if any(token in impact for token in ("medium", "中")):
        return "中" if is_zh else "Medium"
    if any(token in impact for token in ("low", "低")):
        return "低" if is_zh else "Low"

    actions_text = " ".join(
        str(item)
        for key in ("must_actions", "should_actions", "compliance_actions", "design_changes")
        for item in (plan_data.get(key) or [])
    ).lower()
    if any(k in actions_text for k in ("tooling", "mold", "cert", "test", "battery", "模具", "认证", "测试", "电池")):
        return "高" if is_zh else "High"
    return "中" if is_zh else "Medium"


def _estimate_cost_breakdown(
    plan_data: Dict[str, Any], feature_data: Dict[str, Any], target_lang: str
) -> Dict[str, str]:
    is_zh = (target_lang or "").lower().startswith("zh")

    def level(value: str) -> str:
        if is_zh:
            return value
        return {"高": "High", "中": "Medium", "低": "Low"}.get(value, value)

    tooling = ""
    if plan_data.get("design_changes"):
        tooling = level("中")
    if any(
        "mold" in str(item).lower() or "tooling" in str(item).lower() or "模具" in str(item)
        for item in (plan_data.get("design_changes") or [])
    ):
        tooling = level("高")

    testing = ""
    if plan_data.get("compliance_actions") or plan_data.get("verification_required"):
        testing = level("高")

    bom = ""
    if str(feature_data.get("is_electronic") or "").strip().lower() == "yes":
        bom = level("高")
    elif feature_data.get("materials_mentioned"):
        bom = level("中")

    schedule = ""
    timeline = str(plan_data.get("timeline_estimate") or "").strip()
    if timeline:
        schedule = timeline

    return {
        "cost_tooling": tooling,
        "cost_testing": testing,
        "cost_bom": bom,
        "cost_schedule": schedule,
    }


def _risk_level(score: int, target_lang: str) -> str:
    is_zh = (target_lang or "").lower().startswith("zh")
    if score >= 70:
        return "高" if is_zh else "High"
    if score >= 40:
        return "中" if is_zh else "Medium"
    return "低" if is_zh else "Low"


def _compute_risk_score(
    *,
    missing_items: List[str],
    compliance_blockers: List[str],
    stage_errors: Dict[str, str],
    regulation_data: Dict[str, Any],
    target_lang: str,
) -> tuple[int, str]:
    score = 10
    score += min(40, 10 * len(missing_items))
    score += min(40, 15 * len(compliance_blockers))
    if stage_errors:
        score += 15
    if not regulation_data:
        score += 20
    score = max(0, min(100, score))
    return score, _risk_level(score, target_lang)


def _select_metadata_language(
    culture_meta: Dict[str, str], regulation_meta: Dict[str, str]
) -> tuple[str, list[str]]:
    notes: List[str] = []
    culture_lang = str(culture_meta.get("language") or "").strip()
    regulation_lang = str(regulation_meta.get("language") or "").strip()
    chosen = regulation_lang or culture_lang
    if culture_lang and regulation_lang and culture_lang != regulation_lang:
        notes.append(
            f"Culture metadata language '{culture_lang}' differs from regulation '{regulation_lang}'."
        )
    return chosen, notes


def _resolve_label_language(
    *,
    metadata_language: str,
    market: str,
    target_lang: str,
    stage_warnings: Dict[str, str],
) -> str:
    label_lang = metadata_language or market_default_language(market) or target_lang
    if not label_lang:
        stage_warnings["label_language"] = "Labeling language is unknown; verify local requirements."
    return label_lang


def _ensure_min_content(
    label: str, payload: Dict[str, Any], spec: Any, stage_errors: Dict[str, str]
) -> bool:
    if has_substantive_content(payload, spec):
        return True
    stage_errors[label] = "Empty or non-substantive output."
    return False


def _as_lines(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    text = str(value).strip()
    return [text] if text else []


def _build_visual_constraints(
    culture_data: Dict[str, Any], regulation_data: Dict[str, Any], target_lang: str
) -> str:
    is_zh = (target_lang or "").lower().startswith("zh")
    lines: List[str] = []

    taboos = _as_lines(culture_data.get("taboos") if culture_data else None)
    if taboos:
        joined = "；".join(taboos[:6]) if is_zh else "; ".join(taboos[:6])
        lines.append(("禁止/避免：" if is_zh else "Must avoid: ") + joined)

    symbols = _as_lines(culture_data.get("symbols") if culture_data else None)
    if symbols:
        joined = "；".join(symbols[:6]) if is_zh else "; ".join(symbols[:6])
        lines.append(("建议元素：" if is_zh else "Preferred motifs: ") + joined)

    materials = _as_lines(regulation_data.get("materials_chemicals") if regulation_data else None)
    if materials:
        joined = "；".join(materials[:6]) if is_zh else "; ".join(materials[:6])
        lines.append(("材料/化学限制：" if is_zh else "Material/chemical limits: ") + joined)

    design_changes = _as_lines(regulation_data.get("design_changes") if regulation_data else None)
    if design_changes:
        joined = "；".join(design_changes[:6]) if is_zh else "; ".join(design_changes[:6])
        lines.append(("必须体现的安全要求：" if is_zh else "Must include safety constraints: ") + joined)

    age_grading = str((regulation_data or {}).get("age_grading") or "").strip()
    if age_grading:
        lines.append(("年龄标识：" if is_zh else "Age grading: ") + age_grading)

    labeling = _as_lines(regulation_data.get("labeling") if regulation_data else None)
    if labeling:
        joined = "；".join(labeling[:4]) if is_zh else "; ".join(labeling[:4])
        lines.append(("标签提示：" if is_zh else "Labeling cues: ") + joined)

    return "\n".join(lines).strip()

@dataclass
class WorkflowResult:
    success: bool
    status: str = "done"
    run_id: str = ""
    output_dir: str = ""
    market_input: str = ""
    market_normalized: str = ""
    market_notes: List[str] = field(default_factory=list)
    market_confidence: str = ""
    target_language: str = ""
    go_to_market: str = ""
    price_band: str = ""
    material_constraints: str = ""
    supplier_constraints: str = ""
    cost_ceiling: str = ""
    knowledge_versions: Dict[str, str] = field(default_factory=dict)
    knowledge_metadata: Dict[str, Dict[str, str]] = field(default_factory=dict)
    model_meta: Dict[str, str] = field(default_factory=dict)
    feature_suggestion: str = ""
    feature_data: Dict[str, Any] = field(default_factory=dict)
    missing_feature_questions: List[str] = field(default_factory=list)
    culture_suggestion: str = ""
    culture_data: Dict[str, Any] = field(default_factory=dict)
    regulation_suggestion: str = ""
    regulation_data: Dict[str, Any] = field(default_factory=dict)
    compliance_blockers: List[str] = field(default_factory=list)
    risk_score: int = 0
    risk_level: str = ""
    design_suggestion: str = ""
    design_data: Dict[str, Any] = field(default_factory=dict)
    stage_errors: Dict[str, str] = field(default_factory=dict)
    stage_warnings: Dict[str, str] = field(default_factory=dict)
    timings: Dict[str, float] = field(default_factory=dict)
    final_plan: str = ""
    final_plan_data: Dict[str, Any] = field(default_factory=dict)
    refined_prompt: str = ""
    image_path: str = ""
    showcase_path: str = ""
    logs: List[str] = field(default_factory=list)
    error: str = ""


def run_localization_workflow(
    country: str,
    description: str,
    *,
    skip_vision: bool,
    generate_3d: bool,
    target_language: str = "",
    allow_incomplete: bool = False,
    interactive: bool = False,
    go_to_market: str = "",
    price_band: str = "",
    material_constraints: str = "",
    supplier_constraints: str = "",
    cost_ceiling: str = "",
    run_id: Optional[str] = None,
    log_hook: LogHook = None,
    result_hook: ResultHook = None,
) -> WorkflowResult:
    """Run localization workflow and return structured outputs."""

    logs: List[str] = []
    logs_lock = threading.Lock()
    run_id = (run_id or "").strip() or uuid.uuid4().hex
    run_output_dir = resolve_run_output_dir(run_id)
    timings: Dict[str, float] = {}
    stage_warnings: Dict[str, str] = {}
    missing_feature_questions: List[str] = []
    compliance_blockers: List[str] = []
    workflow_status = "done"
    risk_score_value = 0
    risk_level = ""

    def log(message: str) -> None:
        with logs_lock:
            logs.append(message)
        if log_hook is not None:
            log_hook(message)

    def emit(update: Dict[str, Any]) -> None:
        if result_hook is None:
            return
        try:
            result_hook(update)
        except Exception as exc:
            log(f"[warning] result_hook failed: {exc}")

    try:
        start_time = time.monotonic()
        emit({"run_id": run_id, "output_dir": str(run_output_dir)})
        market_info = normalize_market(country)
        normalized_country = market_info.normalized
        culture_expert = CultureAgent(normalized_country)
        regulation_expert = RegulationAgent(normalized_country)
        design_expert = DesignAgent()
        coordinator = CoordinatorAgent()
        repair_agent = JsonRepairAgent() if LLM_JSON_REPAIR else None
        if repair_agent is not None:
            repair_agent.log_hook = log
        language_agent = LanguageNormalizerAgent()
        language_agent.log_hook = log
        feature_extractor = FeatureExtractorAgent()
        feature_extractor.log_hook = log

        business_context = {
            "go_to_market": go_to_market,
            "price_band": price_band,
            "material_constraints": material_constraints,
            "supplier_constraints": supplier_constraints,
            "cost_ceiling": cost_ceiling,
        }

        knowledge_versions = {
            "culture": getattr(culture_expert.knowledge, "version_tag", ""),
            "regulation": getattr(regulation_expert.knowledge, "version_tag", ""),
        }
        knowledge_metadata = {
            "culture": dict(getattr(culture_expert.knowledge, "metadata", {}) or {}),
            "regulation": dict(getattr(regulation_expert.knowledge, "metadata", {}) or {}),
        }
        metadata_language, metadata_notes = _select_metadata_language(
            knowledge_metadata.get("culture", {}), knowledge_metadata.get("regulation", {})
        )
        target_lang, language_notes = resolve_target_language(
            normalized_country,
            description,
            target_language,
            metadata_language=metadata_language,
        )
        model_meta = {
            "llm_model": LLM_MODEL,
            "llm_api_base": LLM_API_BASE,
            "llm_wire_api": LLM_WIRE_API,
            "embedding_model": EMBEDDING_MODEL,
            "image_gen_model": IMAGE_GEN_MODEL,
        }
        if market_info.notes:
            stage_warnings["market_normalization"] = "; ".join(market_info.notes)
        if metadata_notes:
            stage_warnings["language_metadata"] = "; ".join(metadata_notes)
        if language_notes:
            stage_warnings["language_resolution"] = "; ".join(language_notes)
        emit(
            {
                "run_id": run_id,
                "market_input": market_info.raw,
                "market_normalized": market_info.normalized,
                "market_notes": list(market_info.notes),
                "market_confidence": market_info.confidence,
                "target_language": target_lang,
                "go_to_market": go_to_market,
                "price_band": price_band,
                "material_constraints": material_constraints,
                "supplier_constraints": supplier_constraints,
                "cost_ceiling": cost_ceiling,
                "knowledge_versions": dict(knowledge_versions),
                "knowledge_metadata": dict(knowledge_metadata),
                "model_meta": dict(model_meta),
            }
        )

        log(f"\n[init] Loading agents... (run_id={run_id})")
        log(f"[init] Output dir: {run_output_dir}")
        if market_info.raw != normalized_country:
            log(f"[market] Normalized '{market_info.raw}' -> '{normalized_country}'")
        log(f"[language] Target output language: {target_lang}")

        log("\n[features] Extracting product features...")
        feature_start = time.monotonic()
        feature_suggestion = ""
        feature_data: Dict[str, Any] = {}
        try:
            feature_prompt = f"{description}\n\nOutput language: {target_lang}"
            feature_suggestion = feature_extractor.run(feature_prompt)
            timings["features"] = time.monotonic() - feature_start
        except Exception as exc:
            stage_warnings["feature_extract"] = f"Feature extraction failed: {exc}"
            timings["features"] = time.monotonic() - feature_start

        if feature_suggestion:
            feature_suggestion, feature_data = _parse_and_validate_output(
                feature_suggestion,
                label="features",
                model_cls=FeatureOutput,
                spec=FEATURE_SPEC,
                repair_agent=repair_agent,
                language_agent=language_agent,
                target_lang=target_lang,
                stage_warnings=stage_warnings,
                log=log,
            )

        if not feature_data:
            feature_data = normalize_payload(heuristic_features(description), FEATURE_SPEC)
            stage_warnings["feature_heuristic"] = "Used heuristic feature extraction."

        missing_items = _build_missing_feature_items(feature_data, target_lang)
        missing_feature_questions = [item["question"] for item in missing_items]
        if missing_items:
            stage_warnings["feature_missing"] = "Missing critical product details."

        if missing_items and interactive:
            overrides = _prompt_for_missing_features(missing_items, target_lang)
            if overrides:
                feature_data = _apply_feature_overrides(feature_data, overrides)
                missing_items = _build_missing_feature_items(feature_data, target_lang)
                missing_feature_questions = [item["question"] for item in missing_items]

        if missing_items and not allow_incomplete:
            workflow_status = "blocked"
            log("[features] Blocking workflow due to missing critical product details.")
            risk_score_value, risk_level = _compute_risk_score(
                missing_items=missing_feature_questions,
                compliance_blockers=[],
                stage_errors={},
                regulation_data={},
                target_lang=target_lang,
            )
            emit(
                {
                    "run_id": run_id,
                    "feature_data": feature_data,
                    "missing_feature_questions": list(missing_feature_questions),
                    "stage_warnings": dict(stage_warnings),
                    "status": workflow_status,
                    "risk_score": risk_score_value,
                    "risk_level": risk_level,
                }
            )
            timings["total"] = time.monotonic() - start_time
            return WorkflowResult(
                success=True,
                status=workflow_status,
                run_id=run_id,
                output_dir=str(run_output_dir),
                market_input=market_info.raw,
                market_normalized=market_info.normalized,
                market_notes=list(market_info.notes),
                market_confidence=market_info.confidence,
                target_language=target_lang,
                go_to_market=go_to_market,
                price_band=price_band,
                material_constraints=material_constraints,
                supplier_constraints=supplier_constraints,
                cost_ceiling=cost_ceiling,
                knowledge_versions=knowledge_versions,
                knowledge_metadata=knowledge_metadata,
                model_meta=model_meta,
                feature_suggestion=feature_suggestion,
                feature_data=feature_data,
                missing_feature_questions=missing_feature_questions,
                risk_score=risk_score_value,
                risk_level=risk_level,
                stage_errors={},
                stage_warnings=stage_warnings,
                timings=timings,
                logs=logs,
            )

        emit(
            {
                "run_id": run_id,
                "feature_suggestion": feature_suggestion,
                "feature_data": feature_data,
                "missing_feature_questions": list(missing_feature_questions),
                "status": workflow_status,
                "stage_warnings": dict(stage_warnings),
                "timings": dict(timings),
            }
        )

        log("\n[culture/regulation] Analyzing in parallel...")
        culture_expert.log_hook = log
        regulation_expert.log_hook = log
        design_expert.log_hook = log
        coordinator.log_hook = log

        parallel_start = time.monotonic()
        heartbeat_seconds = 10.0

        results: Dict[str, str] = {}
        stage_errors: Dict[str, str] = {}
        culture_suggestion = ""
        regulation_suggestion = ""
        culture_data: Dict[str, Any] = {}
        regulation_data: Dict[str, Any] = {}
        verification_pool: List[str] = []

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(
                    culture_expert.run,
                    description,
                    feature_data=feature_data,
                    language_hint=target_lang,
                    business_context=business_context,
                ): "culture",
                executor.submit(
                    regulation_expert.run,
                    description,
                    feature_data=feature_data,
                    language_hint=target_lang,
                    business_context=business_context,
                ): "regulation",
            }
            stage_start = {
                "culture": time.monotonic(),
                "regulation": time.monotonic(),
            }
            pending = set(futures.keys())
            last_heartbeat = parallel_start

            while pending:
                done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                for future in done:
                    name = futures[future]
                    try:
                        results[name] = future.result()
                        timings[name] = time.monotonic() - stage_start[name]
                        elapsed_s = time.monotonic() - parallel_start
                        log(f"[{name}] Done ({elapsed_s:.1f}s).")
                    except Exception as exc:
                        stage_errors[name] = str(exc)
                        results[name] = ""
                        timings[name] = time.monotonic() - stage_start[name]
                        elapsed_s = time.monotonic() - parallel_start
                        log(f"[warning] [{name}] Failed after {elapsed_s:.1f}s: {exc}")

                    if name == "culture":
                        culture_suggestion = results[name]
                        (
                            culture_suggestion,
                            culture_data,
                        ) = _parse_and_validate_output(
                            culture_suggestion,
                            label="culture",
                            model_cls=CultureOutput,
                            spec=CULTURE_SPEC,
                            repair_agent=repair_agent,
                            language_agent=language_agent,
                            target_lang=target_lang,
                            stage_warnings=stage_warnings,
                            log=log,
                        )
                        emit(
                            {
                                "run_id": run_id,
                                "culture_suggestion": culture_suggestion,
                                "culture_data": culture_data,
                                "stage_errors": dict(stage_errors),
                                "stage_warnings": dict(stage_warnings),
                                "timings": dict(timings),
                            }
                        )
                    elif name == "regulation":
                        regulation_suggestion = results[name]
                        (
                            regulation_suggestion,
                            regulation_data,
                        ) = _parse_and_validate_output(
                            regulation_suggestion,
                            label="regulation",
                            model_cls=RegulationOutput,
                            spec=REGULATION_SPEC,
                            repair_agent=repair_agent,
                            language_agent=language_agent,
                            target_lang=target_lang,
                            stage_warnings=stage_warnings,
                            log=log,
                        )
                        emit(
                            {
                                "run_id": run_id,
                                "regulation_suggestion": regulation_suggestion,
                                "regulation_data": regulation_data,
                                "stage_errors": dict(stage_errors),
                                "stage_warnings": dict(stage_warnings),
                                "timings": dict(timings),
                            }
                        )

                now = time.monotonic()
                if pending and now - last_heartbeat >= heartbeat_seconds:
                    elapsed_s = now - parallel_start
                    pending_names = ", ".join(sorted(futures[f] for f in pending))
                    log(f"[culture/regulation] Still running... {elapsed_s:.0f}s (pending: {pending_names})")
                    last_heartbeat = now

        culture_suggestion = culture_suggestion or results.get("culture", "")
        regulation_suggestion = regulation_suggestion or results.get("regulation", "")
        log("")

        if not culture_data:
            culture_suggestion, culture_data = _parse_and_validate_output(
                culture_suggestion,
                label="culture",
                model_cls=CultureOutput,
                spec=CULTURE_SPEC,
                repair_agent=repair_agent,
                language_agent=language_agent,
                target_lang=target_lang,
                stage_warnings=stage_warnings,
                log=log,
            )
        if not regulation_data:
            regulation_suggestion, regulation_data = _parse_and_validate_output(
                regulation_suggestion,
                label="regulation",
                model_cls=RegulationOutput,
                spec=REGULATION_SPEC,
                repair_agent=repair_agent,
                language_agent=language_agent,
                target_lang=target_lang,
                stage_warnings=stage_warnings,
                log=log,
            )

        if not regulation_data.get("required_tests"):
            regulation_data["required_tests"] = build_required_tests(normalized_country, feature_data)
        if not str(regulation_data.get("label_language") or "").strip():
            regulation_data["label_language"] = _resolve_label_language(
                metadata_language=metadata_language,
                market=normalized_country,
                target_lang=target_lang,
                stage_warnings=stage_warnings,
            )

        _ensure_min_content("culture", culture_data, CULTURE_SPEC, stage_errors)
        _ensure_min_content("regulation", regulation_data, REGULATION_SPEC, stage_errors)

        compliance_blockers = _build_compliance_blockers(
            market=normalized_country,
            knowledge_version=getattr(regulation_expert.knowledge, "version_tag", ""),
            regulation_data=regulation_data,
            target_lang=target_lang,
        )
        if compliance_blockers:
            stage_warnings["regulation_blockers"] = "Compliance blockers detected."
            if not allow_incomplete:
                workflow_status = "blocked"
                log("[regulation] Compliance blockers detected; marking workflow as blocked.")
        if compliance_blockers:
            emit(
                {
                    "run_id": run_id,
                    "compliance_blockers": list(compliance_blockers),
                    "stage_warnings": dict(stage_warnings),
                    "status": workflow_status,
                }
            )

        risk_score_value, risk_level = _compute_risk_score(
            missing_items=missing_feature_questions,
            compliance_blockers=compliance_blockers,
            stage_errors=stage_errors,
            regulation_data=regulation_data,
            target_lang=target_lang,
        )

        verification_pool.extend(extract_verification_items(feature_data))
        verification_pool.extend(extract_verification_items(culture_data))
        verification_pool.extend(extract_verification_items(regulation_data))
        verification_pool.extend(regulation_data.get("required_tests") or [])
        verification_pool.extend(compliance_blockers)
        verification_pool.extend(market_info.notes)

        def merge_design_into_plan(
            plan_data: Dict[str, Any], design_plan: Dict[str, Any]
        ) -> Dict[str, Any]:
            if not plan_data:
                return {}
            if not design_plan:
                return dict(plan_data)

            merged = dict(plan_data)

            def _as_lines(value: Any) -> List[str]:
                if value is None:
                    return []
                if isinstance(value, list):
                    return [str(item).strip() for item in value if str(item).strip()]
                if isinstance(value, str):
                    return [line.strip() for line in value.splitlines() if line.strip()]
                return [str(value).strip()] if str(value).strip() else []

            combined: List[str] = []
            combined.extend(_as_lines(merged.get("design_changes")))

            for key in ("appearance_changes", "structure_safety_changes", "materials", "tradeoffs"):
                combined.extend(_as_lines(design_plan.get(key)))

            deduped: List[str] = []
            seen = set()
            for item in combined:
                if item in seen:
                    continue
                seen.add(item)
                deduped.append(item)

            if deduped:
                merged["design_changes"] = deduped[:12]

            if not str(merged.get("cost_impact") or "").strip():
                cost = design_plan.get("cost_impact")
                if isinstance(cost, str) and cost.strip():
                    merged["cost_impact"] = cost.strip()

            if not any(merged.get(key) for key in ("must_actions", "should_actions", "could_actions")):
                must = _as_lines(merged.get("compliance_actions"))
                should = _as_lines(merged.get("design_changes"))
                could = _as_lines(merged.get("cultural_actions"))
                if must:
                    merged["must_actions"] = must[:12]
                if should:
                    merged["should_actions"] = should[:12]
                if could:
                    merged["could_actions"] = could[:12]

            return merged

        design_payload: Dict[str, Any] = {
            "original_design": description,
            "target_market": normalized_country,
            "target_language": target_lang,
            "market_input": market_info.raw,
            "market_confidence": market_info.confidence,
            "culture_suggestions": culture_data or culture_suggestion,
            "regulation_suggestions": regulation_data or regulation_suggestion,
            "feature_data": feature_data,
            "business_context": business_context,
            "stage_errors": stage_errors,
        }
        design_input = json.dumps(design_payload, ensure_ascii=False)

        coordinator_payload: Dict[str, Any] = {
            "original_design": description,
            "target_market": normalized_country,
            "target_language": target_lang,
            "market_input": market_info.raw,
            "market_confidence": market_info.confidence,
            "culture_suggestions": culture_data or culture_suggestion,
            "regulation_suggestions": regulation_data or regulation_suggestion,
            "feature_data": feature_data,
            "business_context": business_context,
            "verification_required": verification_pool,
            "compliance_blockers": compliance_blockers,
            "missing_feature_questions": missing_feature_questions,
            "stage_errors": stage_errors,
        }
        coordinator_input = json.dumps(coordinator_payload, ensure_ascii=False)

        log("\n[design/coordinator] Building plan in parallel...")
        plan_start = time.monotonic()
        stage2_results: Dict[str, str] = {}
        design_suggestion = ""
        final_plan_raw = ""
        design_data: Dict[str, Any] = {}
        coordinator_plan_data: Dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(design_expert.run, design_input): "design",
                executor.submit(coordinator.run, coordinator_input): "coordinator",
            }
            stage_start = {
                "design": time.monotonic(),
                "coordinator": time.monotonic(),
            }
            pending = set(futures.keys())
            last_heartbeat = plan_start

            while pending:
                done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                for future in done:
                    name = futures[future]
                    try:
                        stage2_results[name] = future.result()
                        timings[name] = time.monotonic() - stage_start[name]
                        elapsed_s = time.monotonic() - plan_start
                        log(f"[{name}] Done ({elapsed_s:.1f}s).")
                    except Exception as exc:
                        stage_errors[name] = str(exc)
                        stage2_results[name] = ""
                        timings[name] = time.monotonic() - stage_start[name]
                        elapsed_s = time.monotonic() - plan_start
                        log(f"[warning] [{name}] Failed after {elapsed_s:.1f}s: {exc}")

                    if name == "design":
                        design_suggestion = stage2_results[name]
                        (
                            design_suggestion,
                            design_data,
                        ) = _parse_and_validate_output(
                            design_suggestion,
                            label="design",
                            model_cls=DesignOutput,
                            spec=DESIGN_SPEC,
                            repair_agent=repair_agent,
                            language_agent=language_agent,
                            target_lang=target_lang,
                            stage_warnings=stage_warnings,
                            log=log,
                        )
                        emit(
                            {
                                "run_id": run_id,
                                "design_suggestion": design_suggestion,
                                "design_data": design_data,
                                "stage_errors": dict(stage_errors),
                                "stage_warnings": dict(stage_warnings),
                                "timings": dict(timings),
                            }
                        )
                    elif name == "coordinator":
                        final_plan_raw = stage2_results[name]
                        (
                            final_plan_raw,
                            coordinator_plan_data,
                        ) = _parse_and_validate_output(
                            final_plan_raw,
                            label="coordinator",
                            model_cls=CoordinatorOutput,
                            spec=COORDINATOR_SPEC,
                            repair_agent=repair_agent,
                            language_agent=language_agent,
                            target_lang=target_lang,
                            stage_warnings=stage_warnings,
                            log=log,
                        )
                        interim_plan = (
                            format_final_plan_markdown(coordinator_plan_data, language=target_lang)
                            if coordinator_plan_data
                            else final_plan_raw
                        )
                        emit(
                            {
                                "run_id": run_id,
                                "final_plan": interim_plan,
                                "final_plan_data": coordinator_plan_data,
                                "stage_errors": dict(stage_errors),
                                "stage_warnings": dict(stage_warnings),
                                "timings": dict(timings),
                            }
                        )

                now = time.monotonic()
                if pending and now - last_heartbeat >= heartbeat_seconds:
                    elapsed_s = now - plan_start
                    pending_names = ", ".join(sorted(futures[f] for f in pending))
                    log(f"[design/coordinator] Still running... {elapsed_s:.0f}s (pending: {pending_names})")
                    last_heartbeat = now

        design_suggestion = design_suggestion or stage2_results.get("design", "")
        final_plan_raw = final_plan_raw or stage2_results.get("coordinator", "")
        log("")

        if not final_plan_raw.strip():
            raise RuntimeError(stage_errors.get("coordinator") or "CoordinatorAgent returned empty output")

        if not design_data:
            design_suggestion, design_data = _parse_and_validate_output(
                design_suggestion,
                label="design",
                model_cls=DesignOutput,
                spec=DESIGN_SPEC,
                repair_agent=repair_agent,
                language_agent=language_agent,
                target_lang=target_lang,
                stage_warnings=stage_warnings,
                log=log,
            )
        _ensure_min_content("design", design_data, DESIGN_SPEC, stage_errors)
        verification_pool.extend(extract_verification_items(design_data))
        if not coordinator_plan_data:
            final_plan_raw, coordinator_plan_data = _parse_and_validate_output(
                final_plan_raw,
                label="coordinator",
                model_cls=CoordinatorOutput,
                spec=COORDINATOR_SPEC,
                repair_agent=repair_agent,
                language_agent=language_agent,
                target_lang=target_lang,
                stage_warnings=stage_warnings,
                log=log,
            )
        _ensure_min_content("coordinator", coordinator_plan_data, COORDINATOR_SPEC, stage_errors)
        final_plan_data = merge_design_into_plan(coordinator_plan_data, design_data) if coordinator_plan_data else {}
        if compliance_blockers and not final_plan_data.get("compliance_blockers"):
            final_plan_data["compliance_blockers"] = list(compliance_blockers)
        if missing_feature_questions:
            existing_questions = final_plan_data.get("open_questions") or []
            combined_questions = list(existing_questions) + list(missing_feature_questions)
            deduped_questions = list(
                dict.fromkeys(item for item in combined_questions if str(item).strip())
            )
            if deduped_questions:
                final_plan_data["open_questions"] = deduped_questions[:12]
        if not final_plan_data.get("priority_actions"):
            final_plan_data["priority_actions"] = _build_priority_actions(
                final_plan_data,
                target_lang,
                compliance_blockers=compliance_blockers,
                risk_score=risk_score_value,
            )
        if not str(final_plan_data.get("risk_score") or "").strip():
            final_plan_data["risk_score"] = f"{risk_score_value}/100 ({risk_level})"
        if not str(final_plan_data.get("cost_estimate") or "").strip():
            final_plan_data["cost_estimate"] = _estimate_cost(final_plan_data, target_lang)
        if not str(final_plan_data.get("timeline_estimate") or "").strip():
            final_plan_data["timeline_estimate"] = _estimate_timeline(final_plan_data, target_lang)
        breakdown = _estimate_cost_breakdown(final_plan_data, feature_data, target_lang)
        for key, value in breakdown.items():
            if value and not str(final_plan_data.get(key) or "").strip():
                final_plan_data[key] = value

        if final_plan_data is not None and verification_pool:
            existing = final_plan_data.get("verification_required") or []
            combined = list(existing) + list(verification_pool)
            deduped = list(dict.fromkeys(item for item in combined if str(item).strip()))
            if deduped:
                final_plan_data["verification_required"] = deduped[:12]
        final_plan = (
            format_final_plan_markdown(final_plan_data, language=target_lang)
            if final_plan_data
            else final_plan_raw
        )

        emit(
            {
                "run_id": run_id,
                "market_input": market_info.raw,
                "market_normalized": market_info.normalized,
                "market_notes": list(market_info.notes),
                "market_confidence": market_info.confidence,
                "target_language": target_lang,
                "go_to_market": go_to_market,
                "price_band": price_band,
                "material_constraints": material_constraints,
                "supplier_constraints": supplier_constraints,
                "cost_ceiling": cost_ceiling,
                "knowledge_versions": dict(knowledge_versions),
                "knowledge_metadata": dict(knowledge_metadata),
                "model_meta": dict(model_meta),
                "feature_suggestion": feature_suggestion,
                "feature_data": feature_data,
                "missing_feature_questions": list(missing_feature_questions),
                "design_suggestion": design_suggestion,
                "design_data": design_data,
                "compliance_blockers": list(compliance_blockers),
                "risk_score": risk_score_value,
                "risk_level": risk_level,
                "status": workflow_status,
                "final_plan": final_plan,
                "final_plan_data": final_plan_data,
                "stage_errors": dict(stage_errors),
                "stage_warnings": dict(stage_warnings),
                "timings": dict(timings),
            }
        )

        refined_prompt = ""
        image_path = ""
        showcase_path = ""

        vision_blocked = bool(compliance_blockers) and not allow_incomplete
        if skip_vision or vision_blocked:
            if vision_blocked:
                log("\nVision stage skipped due to compliance blockers.")
            else:
                log("\nVision stage skipped.")
            timings["total"] = time.monotonic() - start_time
            return WorkflowResult(
                success=True,
                status=workflow_status,
                run_id=run_id,
                output_dir=str(run_output_dir),
                market_input=market_info.raw,
                market_normalized=market_info.normalized,
                market_notes=list(market_info.notes),
                market_confidence=market_info.confidence,
                target_language=target_lang,
                go_to_market=go_to_market,
                price_band=price_band,
                material_constraints=material_constraints,
                supplier_constraints=supplier_constraints,
                cost_ceiling=cost_ceiling,
                knowledge_versions=knowledge_versions,
                knowledge_metadata=knowledge_metadata,
                model_meta=model_meta,
                feature_suggestion=feature_suggestion,
                feature_data=feature_data,
                missing_feature_questions=missing_feature_questions,
                culture_suggestion=culture_suggestion,
                culture_data=culture_data,
                regulation_suggestion=regulation_suggestion,
                regulation_data=regulation_data,
                compliance_blockers=compliance_blockers,
                risk_score=risk_score_value,
                risk_level=risk_level,
                design_suggestion=design_suggestion,
                design_data=design_data,
                stage_errors=stage_errors,
                stage_warnings=stage_warnings,
                timings=timings,
                final_plan=final_plan,
                final_plan_data=final_plan_data,
                logs=logs,
            )

        log("\n========== VISION STAGE ==========\n")
        log("[prompt-refiner] Generating prompt...")
        from agents.image_gen import ImageGenAgent
        from agents.prompt_refiner import PromptRefinerAgent
        from agents.three_d_gen import ThreeDGenAgent

        refiner = PromptRefinerAgent()
        refiner.log_hook = log
        plan_for_prompt = (
            json.dumps(final_plan_data, ensure_ascii=False) if final_plan_data else final_plan_raw
        )
        constraint_block = _build_visual_constraints(culture_data, regulation_data, target_lang)
        prompt_start = time.monotonic()
        prompt_payload = "Generate a high quality image prompt from this plan JSON:\n"
        prompt_payload += f"{plan_for_prompt}"
        if constraint_block:
            prompt_payload += "\n\nConstraints (must respect):\n" + constraint_block
        refined_prompt = refiner.run(prompt_payload)
        timings["prompt_refiner"] = time.monotonic() - prompt_start
        log("[prompt-refiner] Done.")
        emit({"refined_prompt": refined_prompt, "timings": dict(timings)})

        log("[image-gen] Generating concept image...")
        image_gen = ImageGenAgent(output_dir=str(run_output_dir))
        image_start = time.monotonic()
        image_path = image_gen.run(refined_prompt)
        timings["image_gen"] = time.monotonic() - image_start
        log(f"[image-gen] Concept image saved to: {image_path}")
        emit({"image_path": image_path, "timings": dict(timings)})

        if generate_3d:
            log("[3d-gen] Generating 3D model and video/preview...")
            three_d_gen = ThreeDGenAgent(output_dir=str(run_output_dir))
            three_d_start = time.monotonic()
            showcase_path = three_d_gen.run(image_path)
            timings["three_d_gen"] = time.monotonic() - three_d_start
            log(f"[3d-gen] Showcase saved to: {showcase_path}")
            emit({"showcase_path": showcase_path, "timings": dict(timings)})
        else:
            log("Skipped 3D generation.")

        log("\nWorkflow finished.")
        timings["total"] = time.monotonic() - start_time
        return WorkflowResult(
            success=True,
            status=workflow_status,
            run_id=run_id,
            output_dir=str(run_output_dir),
            market_input=market_info.raw,
            market_normalized=market_info.normalized,
            market_notes=list(market_info.notes),
            market_confidence=market_info.confidence,
            target_language=target_lang,
            go_to_market=go_to_market,
            price_band=price_band,
            material_constraints=material_constraints,
            supplier_constraints=supplier_constraints,
            cost_ceiling=cost_ceiling,
            knowledge_versions=knowledge_versions,
            knowledge_metadata=knowledge_metadata,
            model_meta=model_meta,
            feature_suggestion=feature_suggestion,
            feature_data=feature_data,
            missing_feature_questions=missing_feature_questions,
            culture_suggestion=culture_suggestion,
            culture_data=culture_data,
            regulation_suggestion=regulation_suggestion,
            regulation_data=regulation_data,
            compliance_blockers=compliance_blockers,
            risk_score=risk_score_value,
            risk_level=risk_level,
            design_suggestion=design_suggestion,
            design_data=design_data,
            stage_errors=stage_errors,
            stage_warnings=stage_warnings,
            timings=timings,
            final_plan=final_plan,
            final_plan_data=final_plan_data,
            refined_prompt=refined_prompt,
            image_path=image_path,
            showcase_path=showcase_path,
            logs=logs,
        )
    except Exception as exc:
        error = str(exc)
        log(f"[runtime error] {error}")
        return WorkflowResult(
            success=False,
            status="error",
            run_id=run_id,
            output_dir=str(run_output_dir),
            market_input=market_info.raw if "market_info" in locals() else "",
            market_normalized=market_info.normalized if "market_info" in locals() else "",
            market_notes=list(market_info.notes) if "market_info" in locals() else [],
            market_confidence=market_info.confidence if "market_info" in locals() else "",
            target_language=target_lang if "target_lang" in locals() else "",
            go_to_market=go_to_market if "go_to_market" in locals() else "",
            price_band=price_band if "price_band" in locals() else "",
            material_constraints=material_constraints if "material_constraints" in locals() else "",
            supplier_constraints=supplier_constraints if "supplier_constraints" in locals() else "",
            cost_ceiling=cost_ceiling if "cost_ceiling" in locals() else "",
            knowledge_versions=knowledge_versions if "knowledge_versions" in locals() else {},
            knowledge_metadata=knowledge_metadata if "knowledge_metadata" in locals() else {},
            model_meta=model_meta if "model_meta" in locals() else {},
            feature_suggestion=feature_suggestion if "feature_suggestion" in locals() else "",
            feature_data=feature_data if "feature_data" in locals() else {},
            missing_feature_questions=missing_feature_questions
            if "missing_feature_questions" in locals()
            else [],
            risk_score=risk_score_value if "risk_score_value" in locals() else 0,
            risk_level=risk_level if "risk_level" in locals() else "",
            stage_errors=stage_errors if "stage_errors" in locals() else {},
            stage_warnings=stage_warnings if "stage_warnings" in locals() else {},
            compliance_blockers=compliance_blockers if "compliance_blockers" in locals() else [],
            timings=timings if "timings" in locals() else {},
            logs=logs,
            error=error,
        )
