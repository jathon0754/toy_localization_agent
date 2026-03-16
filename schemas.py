from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Type

try:
    from pydantic import BaseModel, Field, ValidationError
except ImportError:  # pragma: no cover
    BaseModel = object  # type: ignore
    ValidationError = Exception  # type: ignore


_PYDANTIC_V2 = hasattr(BaseModel, "model_validate")


@dataclass(frozen=True)
class SchemaSpec:
    list_fields: Tuple[str, ...]
    text_fields: Tuple[str, ...]
    max_list_items: int
    max_text_chars: int = 480
    max_item_chars: int = 160


def _split_lines(value: str) -> List[str]:
    if "\n" in value:
        return [line.strip() for line in value.splitlines() if line.strip()]
    if "；" in value:
        return [part.strip() for part in value.split("；") if part.strip()]
    if ";" in value:
        return [part.strip() for part in value.split(";") if part.strip()]
    return [value.strip()] if value.strip() else []


def _coerce_list(value: Any, *, max_items: int, max_item_chars: int) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = _split_lines(value)
    else:
        raw_items = [str(value)]
    cleaned: List[str] = []
    for item in raw_items:
        text = str(item).strip()
        if not text:
            continue
        if len(text) > max_item_chars:
            text = text[: max_item_chars - 1] + "…"
        cleaned.append(text)
        if len(cleaned) >= max_items:
            break
    return cleaned


def _coerce_text(value: Any, *, max_chars: int) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
    else:
        text = str(value).strip()
    if len(text) > max_chars:
        return text[: max_chars - 1] + "…"
    return text


def normalize_payload(data: Dict[str, Any], spec: SchemaSpec) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for field in spec.list_fields:
        normalized[field] = _coerce_list(
            data.get(field),
            max_items=spec.max_list_items,
            max_item_chars=spec.max_item_chars,
        )
    for field in spec.text_fields:
        normalized[field] = _coerce_text(data.get(field), max_chars=spec.max_text_chars)
    return normalized


def has_substantive_content(data: Dict[str, Any], spec: SchemaSpec) -> bool:
    for field in spec.list_fields:
        if data.get(field):
            return True
    for field in spec.text_fields:
        if str(data.get(field) or "").strip():
            return True
    return False


def validate_model(model_cls: Type[BaseModel], data: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    try:
        if _PYDANTIC_V2:
            model = model_cls.model_validate(data)
            return model.model_dump(), None
        model = model_cls.parse_obj(data)  # type: ignore[call-arg]
        return model.dict(), None
    except ValidationError as exc:  # pragma: no cover - validation is best-effort
        try:
            model = model_cls()  # type: ignore[call-arg]
            if _PYDANTIC_V2:
                return model.model_dump(), str(exc)
            return model.dict(), str(exc)
        except Exception:
            return {}, str(exc)


def schema_stub(spec: SchemaSpec) -> Dict[str, str]:
    stub: Dict[str, str] = {}
    for field in spec.list_fields:
        stub[field] = "string[]"
    for field in spec.text_fields:
        stub[field] = "string"
    return stub


class CultureOutput(BaseModel):
    colors: List[str] = Field(default_factory=list)
    symbols: List[str] = Field(default_factory=list)
    taboos: List[str] = Field(default_factory=list)
    communication_style: str = ""
    packaging_copy_tone: str = ""
    notes: str = ""

    if _PYDANTIC_V2:
        model_config = {"extra": "ignore"}
    else:
        class Config:
            extra = "ignore"


class RegulationOutput(BaseModel):
    requirements: List[str] = Field(default_factory=list)
    design_changes: List[str] = Field(default_factory=list)
    labeling: List[str] = Field(default_factory=list)
    required_tests: List[str] = Field(default_factory=list)
    age_grading: str = ""
    label_language: str = ""
    materials_chemicals: List[str] = Field(default_factory=list)
    notes: str = ""

    if _PYDANTIC_V2:
        model_config = {"extra": "ignore"}
    else:
        class Config:
            extra = "ignore"


class DesignOutput(BaseModel):
    appearance_changes: List[str] = Field(default_factory=list)
    structure_safety_changes: List[str] = Field(default_factory=list)
    materials: List[str] = Field(default_factory=list)
    cost_impact: str = ""
    tradeoffs: List[str] = Field(default_factory=list)
    notes: str = ""

    if _PYDANTIC_V2:
        model_config = {"extra": "ignore"}
    else:
        class Config:
            extra = "ignore"


class FeatureOutput(BaseModel):
    toy_category: str = ""
    intended_age: str = ""
    age_group: str = ""
    target_audience: str = ""
    assembly_level: str = ""
    is_electronic: str = ""
    has_small_parts: str = ""
    battery_type: str = ""
    power_source: str = ""
    has_light: str = ""
    has_sound: str = ""
    has_magnets: str = ""
    has_projectiles: str = ""
    wireless: str = ""
    connectivity: str = ""
    use_scenario: str = ""
    materials_mentioned: List[str] = Field(default_factory=list)
    safety_risks: List[str] = Field(default_factory=list)

    if _PYDANTIC_V2:
        model_config = {"extra": "ignore"}
    else:
        class Config:
            extra = "ignore"


class CoordinatorOutput(BaseModel):
    summary: str = ""
    compliance_blockers: List[str] = Field(default_factory=list)
    cultural_actions: List[str] = Field(default_factory=list)
    compliance_actions: List[str] = Field(default_factory=list)
    design_changes: List[str] = Field(default_factory=list)
    must_actions: List[str] = Field(default_factory=list)
    should_actions: List[str] = Field(default_factory=list)
    could_actions: List[str] = Field(default_factory=list)
    priority_actions: List[str] = Field(default_factory=list)
    risk_score: str = ""
    cost_impact: str = ""
    cost_estimate: str = ""
    cost_tooling: str = ""
    cost_bom: str = ""
    cost_testing: str = ""
    cost_schedule: str = ""
    timeline_estimate: str = ""
    implementation_steps: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    verification_required: List[str] = Field(default_factory=list)

    if _PYDANTIC_V2:
        model_config = {"extra": "ignore"}
    else:
        class Config:
            extra = "ignore"


CULTURE_SPEC = SchemaSpec(
    list_fields=("colors", "symbols", "taboos"),
    text_fields=("communication_style", "packaging_copy_tone", "notes"),
    max_list_items=8,
)

REGULATION_SPEC = SchemaSpec(
    list_fields=("requirements", "design_changes", "labeling", "required_tests", "materials_chemicals"),
    text_fields=("age_grading", "label_language", "notes"),
    max_list_items=8,
)

DESIGN_SPEC = SchemaSpec(
    list_fields=("appearance_changes", "structure_safety_changes", "materials", "tradeoffs"),
    text_fields=("cost_impact", "notes"),
    max_list_items=10,
)

FEATURE_SPEC = SchemaSpec(
    list_fields=("materials_mentioned", "safety_risks"),
    text_fields=(
        "toy_category",
        "intended_age",
        "age_group",
        "target_audience",
        "assembly_level",
        "is_electronic",
        "has_small_parts",
        "battery_type",
        "power_source",
        "has_light",
        "has_sound",
        "has_magnets",
        "has_projectiles",
        "wireless",
        "connectivity",
        "use_scenario",
    ),
    max_list_items=8,
)

COORDINATOR_SPEC = SchemaSpec(
    list_fields=(
        "compliance_blockers",
        "cultural_actions",
        "compliance_actions",
        "design_changes",
        "must_actions",
        "should_actions",
        "could_actions",
        "priority_actions",
        "implementation_steps",
        "risks",
        "open_questions",
        "assumptions",
        "verification_required",
    ),
    text_fields=(
        "summary",
        "risk_score",
        "cost_impact",
        "cost_estimate",
        "cost_tooling",
        "cost_bom",
        "cost_testing",
        "cost_schedule",
        "timeline_estimate",
    ),
    max_list_items=12,
)
