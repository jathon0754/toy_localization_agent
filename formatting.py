from __future__ import annotations

import json
from typing import Any, Dict, Optional


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort extraction of a JSON object from model output."""
    if not text:
        return None

    stripped = text.strip()
    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else None
    except Exception:
        pass

    start = stripped.find("{")
    if start < 0:
        return None

    span = _find_balanced_object_span(stripped, start=start)
    if span is None:
        return None

    candidate = stripped[span[0] : span[1]]
    try:
        value = json.loads(candidate)
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _find_balanced_object_span(text: str, *, start: int) -> Optional[tuple[int, int]]:
    depth = 0
    in_string = False
    escaped = False

    for idx in range(start, len(text)):
        ch = text[idx]

        if in_string:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            depth += 1
            continue

        if ch == "}":
            depth -= 1
            if depth == 0:
                return (start, idx + 1)

    return None


def format_final_plan_markdown(plan: Dict[str, Any], *, language: str = "zh") -> str:
    sections = []

    def add(title: str, body: str) -> None:
        body = (body or "").strip()
        if not body:
            return
        sections.append(f"## {title}\n{body}\n")

    is_zh = (language or "").lower().startswith("zh")

    add("Summary" if not is_zh else "概览", _as_text(plan.get("summary")))
    add("Risk Score" if not is_zh else "风险评分", _as_text(plan.get("risk_score")))
    add(
        "Compliance Blockers" if not is_zh else "合规阻塞",
        _as_bullets(plan.get("compliance_blockers")),
    )
    add(
        "Must Actions" if not is_zh else "必须动作",
        _as_bullets(plan.get("must_actions")),
    )
    add(
        "Should Actions" if not is_zh else "建议动作",
        _as_bullets(plan.get("should_actions")),
    )
    add(
        "Could Actions" if not is_zh else "可选动作",
        _as_bullets(plan.get("could_actions")),
    )
    add(
        "Priority Actions" if not is_zh else "优先级动作",
        _as_bullets(plan.get("priority_actions")),
    )
    add("Cultural Actions" if not is_zh else "文化动作", _as_bullets(plan.get("cultural_actions")))
    add(
        "Compliance Actions" if not is_zh else "合规动作",
        _as_bullets(plan.get("compliance_actions")),
    )
    add("Design Changes" if not is_zh else "设计变更", _as_bullets(plan.get("design_changes")))
    add("Cost Impact" if not is_zh else "成本影响", _as_text(plan.get("cost_impact")))
    add("Cost Estimate" if not is_zh else "成本区间", _as_text(plan.get("cost_estimate")))
    add(
        "Cost Breakdown" if not is_zh else "成本拆分",
        _as_bullets(
            [
                _label_line("tooling", plan.get("cost_tooling"), is_zh),
                _label_line("bom", plan.get("cost_bom"), is_zh),
                _label_line("testing", plan.get("cost_testing"), is_zh),
                _label_line("schedule", plan.get("cost_schedule"), is_zh),
            ]
        ),
    )
    add("Timeline Estimate" if not is_zh else "工期预估", _as_text(plan.get("timeline_estimate")))
    add("Implementation Steps" if not is_zh else "实施步骤", _as_numbered(plan.get("implementation_steps")))
    add("Risks" if not is_zh else "风险", _as_bullets(plan.get("risks")))
    add(
        "Verification Required" if not is_zh else "需核实事项",
        _as_bullets(plan.get("verification_required")),
    )
    add("Open Questions" if not is_zh else "待确认问题", _as_bullets(plan.get("open_questions")))
    add("Assumptions" if not is_zh else "假设", _as_bullets(plan.get("assumptions")))

    if not sections:
        return json.dumps(plan, ensure_ascii=False, indent=2)

    title = "# Final Localization Plan" if not is_zh else "# 本地化计划"
    return f"{title}\n\n" + "\n".join(sections).rstrip() + "\n"


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _as_lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        lines = [line.strip() for line in value.splitlines()]
        return [line for line in lines if line]
    return [str(value).strip()] if str(value).strip() else []


def _as_bullets(value: Any) -> str:
    lines = _as_lines(value)
    return "\n".join(f"- {line}" for line in lines)


def _as_numbered(value: Any) -> str:
    lines = _as_lines(value)
    return "\n".join(f"{idx}. {line}" for idx, line in enumerate(lines, start=1))


def _label_line(key: str, value: Any, is_zh: bool) -> str:
    text = _as_text(value).strip()
    if not text:
        return ""
    labels = {
        "tooling": "模具/工装" if is_zh else "Tooling",
        "bom": "BOM/材料" if is_zh else "BOM/Materials",
        "testing": "测试认证" if is_zh else "Testing/Compliance",
        "schedule": "周期/排期" if is_zh else "Schedule",
    }
    label = labels.get(key, key)
    return f"{label}: {text}"
