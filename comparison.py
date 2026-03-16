from __future__ import annotations

import time
from typing import Any, Dict, List

from workflow import run_localization_workflow


def _summary_entry(result) -> Dict[str, Any]:
    plan = result.final_plan_data or {}
    return {
        "market": result.market_normalized or result.market_input,
        "status": result.status,
        "risk_score": result.risk_score,
        "risk_level": result.risk_level,
        "cost_estimate": plan.get("cost_estimate") or "",
        "timeline_estimate": plan.get("timeline_estimate") or "",
        "compliance_blockers": result.compliance_blockers,
        "missing_feature_questions": result.missing_feature_questions,
        "market_notes": result.market_notes,
    }


def compare_markets(
    *,
    markets: List[str],
    description: str,
    target_language: str = "",
    go_to_market: str = "",
    price_band: str = "",
    material_constraints: str = "",
    supplier_constraints: str = "",
    cost_ceiling: str = "",
) -> Dict[str, Any]:
    started = time.time()
    results = []
    for market in markets:
        result = run_localization_workflow(
            country=market,
            description=description,
            skip_vision=True,
            generate_3d=False,
            target_language=target_language,
            allow_incomplete=True,
            interactive=False,
            go_to_market=go_to_market,
            price_band=price_band,
            material_constraints=material_constraints,
            supplier_constraints=supplier_constraints,
            cost_ceiling=cost_ceiling,
        )
        results.append(result)

    summary = [_summary_entry(result) for result in results]
    return {
        "success": True,
        "elapsed_seconds": round(time.time() - started, 2),
        "items": summary,
    }
