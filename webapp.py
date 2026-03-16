"""FastAPI web frontend for toy localization workflow.

This module is importable without FastAPI installed so that unit tests can run in
minimal environments. The ASGI app is created lazily in `create_app()`.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from config import OUTPUT_DIR, ensure_output_dir


def _to_output_url(raw_path: str) -> str:
    if not raw_path:
        return ""

    output_root = Path(OUTPUT_DIR).resolve()
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()

    try:
        rel_path = path.relative_to(output_root)
    except ValueError:
        return ""
    return f"/outputs/{rel_path.as_posix()}"


def create_app() -> Any:
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import HTMLResponse
        from fastapi.staticfiles import StaticFiles
        from pydantic import BaseModel, Field
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "FastAPI dependencies are missing. Install requirements.txt to run the web app."
        ) from exc

    from config import ConfigError, validate_required_config
    from knowledge.retriever import CountryKnowledgeRetriever
    from workflow import run_localization_workflow

    class RunRequest(BaseModel):
        country: str = Field(min_length=1, max_length=50)
        description: str = Field(min_length=1, max_length=4000)
        skip_vision: bool = False
        auto_3d: bool = False
        target_language: Optional[str] = Field(default="", max_length=12)
        allow_incomplete: bool = False
        go_to_market: Optional[str] = Field(default="", max_length=40)
        price_band: Optional[str] = Field(default="", max_length=20)
        material_constraints: Optional[str] = Field(default="", max_length=200)
        supplier_constraints: Optional[str] = Field(default="", max_length=200)
        cost_ceiling: Optional[str] = Field(default="", max_length=80)

    ensure_output_dir()

    app = FastAPI(title="Toy Localization Frontend", version="1.0.0")
    jobs: Dict[str, Dict[str, Any]] = {}

    import json
    import os
    import re
    import threading
    import time
    import uuid

    jobs_lock = threading.Lock()
    max_log_lines = 1200
    job_ttl_seconds = int(os.getenv("WEB_JOB_TTL_SECONDS", "3600") or "3600")
    max_jobs = int(os.getenv("WEB_MAX_JOBS", "64") or "64")
    max_concurrent_jobs = int(os.getenv("WEB_MAX_CONCURRENT_JOBS", "2") or "2")
    job_semaphore = threading.Semaphore(max(1, max_concurrent_jobs))
    history_dir = Path(OUTPUT_DIR) / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    max_history_entries = int(os.getenv("WEB_HISTORY_MAX_ENTRIES", "200") or "200")
    job_id_pattern = re.compile(r"^[0-9a-fA-F]{8,64}$")

    def _history_path(job_id: str) -> Path:
        safe = str(job_id or "").strip()
        if not safe or not job_id_pattern.match(safe):
            raise ValueError("Invalid job id")
        return history_dir / f"{safe}.json"

    def _load_history(job_id: str) -> Optional[Dict[str, Any]]:
        try:
            path = _history_path(job_id)
        except ValueError:
            return None
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _persist_history(snapshot: Dict[str, Any]) -> None:
        try:
            path = _history_path(str(snapshot.get("job_id") or ""))
        except Exception:
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass

    def _prune_history_files() -> None:
        if max_history_entries <= 0:
            return
        try:
            files = sorted(
                history_dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except Exception:
            return

        for path in files[max_history_entries:]:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                continue

    def _prune_jobs() -> None:
        now = time.time()
        expired_ids = []
        for job_id, job in jobs.items():
            updated_at = float(job.get("updated_at") or job.get("created_at") or now)
            if now - updated_at > job_ttl_seconds:
                expired_ids.append(job_id)

        for job_id in expired_ids:
            jobs.pop(job_id, None)

        if len(jobs) <= max_jobs:
            return

        sorted_jobs = sorted(
            jobs.items(),
            key=lambda item: float(item[1].get("updated_at") or item[1].get("created_at") or 0),
        )
        for job_id, _ in sorted_jobs[: max(0, len(jobs) - max_jobs)]:
            jobs.pop(job_id, None)

    def _job_response(job_id: str, job: Dict[str, Any]) -> Dict[str, Any]:
        response: Dict[str, Any] = {
            "success": True,
            "job_id": job_id,
            "status": job.get("status") or "",
            "logs": list(job.get("logs") or []),
            "error": job.get("error") or "",
        }
        if job.get("result"):
            result = job.get("result")
            if isinstance(result, dict):
                response.update(result)
        return response

    def _append_log(job_id: str, message: str) -> None:
        with jobs_lock:
            job = jobs.get(job_id)
            if not job:
                return
            job["logs"].append(message)
            if len(job["logs"]) > max_log_lines:
                job["logs"] = job["logs"][-max_log_lines:]
            job["updated_at"] = time.time()

    def _run_job(job_id: str, payload_data: Dict[str, Any]) -> None:
        job_semaphore.acquire()
        persisted_snapshot: Optional[Dict[str, Any]] = None
        try:
            with jobs_lock:
                job = jobs.get(job_id)
                if not job:
                    return
                job["status"] = "running"
                job["updated_at"] = time.time()
                _persist_history(dict(job))

            def _log_hook(msg: str) -> None:
                _append_log(job_id, msg)

            def _result_hook(update: Dict[str, Any]) -> None:
                if not isinstance(update, dict):
                    return
                with jobs_lock:
                    job = jobs.get(job_id)
                    if not job:
                        return
                    current = job.get("result") or {}
                    if not isinstance(current, dict):
                        current = {}
                    current.update(update)
                    if current.get("image_path"):
                        current["image_url"] = _to_output_url(str(current.get("image_path") or ""))
                    if current.get("showcase_path"):
                        current["showcase_url"] = _to_output_url(
                            str(current.get("showcase_path") or "")
                        )
                    job["result"] = current
                    job["updated_at"] = time.time()

            try:
                result = run_localization_workflow(
                    country=str(payload_data["country"]),
                    description=str(payload_data["description"]),
                    skip_vision=bool(payload_data.get("skip_vision")),
                    generate_3d=(not bool(payload_data.get("skip_vision")))
                    and bool(payload_data.get("auto_3d")),
                    target_language=str(payload_data.get("target_language") or ""),
                    allow_incomplete=bool(payload_data.get("allow_incomplete")),
                    go_to_market=str(payload_data.get("go_to_market") or ""),
                    price_band=str(payload_data.get("price_band") or ""),
                    material_constraints=str(payload_data.get("material_constraints") or ""),
                    supplier_constraints=str(payload_data.get("supplier_constraints") or ""),
                    cost_ceiling=str(payload_data.get("cost_ceiling") or ""),
                    run_id=job_id,
                    log_hook=_log_hook,
                    result_hook=_result_hook,
                )

                response = {
                    "success": result.success,
                    "status": result.status,
                    "run_id": result.run_id,
                    "output_dir": result.output_dir,
                    "market_input": result.market_input,
                    "market_normalized": result.market_normalized,
                    "market_notes": result.market_notes,
                    "market_confidence": result.market_confidence,
                    "target_language": result.target_language,
                    "go_to_market": result.go_to_market,
                    "price_band": result.price_band,
                    "material_constraints": result.material_constraints,
                    "supplier_constraints": result.supplier_constraints,
                    "cost_ceiling": result.cost_ceiling,
                    "allow_incomplete": bool(payload_data.get("allow_incomplete")),
                    "knowledge_versions": result.knowledge_versions,
                    "knowledge_metadata": result.knowledge_metadata,
                    "model_meta": result.model_meta,
                    "feature_suggestion": result.feature_suggestion,
                    "feature_data": result.feature_data,
                    "missing_feature_questions": result.missing_feature_questions,
                    "culture_suggestion": result.culture_suggestion,
                    "culture_data": result.culture_data,
                    "regulation_suggestion": result.regulation_suggestion,
                    "regulation_data": result.regulation_data,
                    "compliance_blockers": result.compliance_blockers,
                    "risk_score": result.risk_score,
                    "risk_level": result.risk_level,
                    "design_suggestion": result.design_suggestion,
                    "design_data": result.design_data,
                    "stage_errors": result.stage_errors,
                    "stage_warnings": result.stage_warnings,
                    "timings": result.timings,
                    "final_plan": result.final_plan,
                    "final_plan_data": result.final_plan_data,
                    "refined_prompt": result.refined_prompt,
                    "image_path": result.image_path,
                    "showcase_path": result.showcase_path,
                    "image_url": _to_output_url(result.image_path),
                    "showcase_url": _to_output_url(result.showcase_path),
                    "logs": result.logs,
                    "error": result.error,
                }

                with jobs_lock:
                    job = jobs.get(job_id)
                    if not job:
                        return
                    job["status"] = result.status if result.success else "error"
                    job["result"] = response
                    job["error"] = result.error
                    job["updated_at"] = time.time()
                    persisted_snapshot = dict(job)
            except Exception as exc:
                with jobs_lock:
                    job = jobs.get(job_id)
                    if not job:
                        return
                    job["status"] = "error"
                    job["error"] = str(exc)
                    job["updated_at"] = time.time()
                    persisted_snapshot = dict(job)
        finally:
            job_semaphore.release()
            if persisted_snapshot is not None:
                _persist_history(persisted_snapshot)
                _prune_history_files()

    web_dir = Path(__file__).parent / "web"
    assets_dir = web_dir / "assets"
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

    @app.get("/", response_class=HTMLResponse)
    def home() -> HTMLResponse:
        html = (web_dir / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(content=html, media_type="text/html; charset=utf-8")

    @app.get("/api/countries")
    def countries() -> Dict[str, Any]:
        return {"countries": CountryKnowledgeRetriever.available_countries()}

    @app.post("/api/run")
    def run(payload: RunRequest) -> Dict[str, Any]:
        try:
            validate_required_config(skip_vision=payload.skip_vision)
        except ConfigError as exc:
            return {"success": False, "error": str(exc), "logs": [f"[config error] {exc}"]}

        run_id = uuid.uuid4().hex
        result = run_localization_workflow(
            country=payload.country,
            description=payload.description,
            skip_vision=payload.skip_vision,
            generate_3d=(not payload.skip_vision) and payload.auto_3d,
            run_id=run_id,
            target_language=payload.target_language or "",
            allow_incomplete=payload.allow_incomplete,
            go_to_market=payload.go_to_market or "",
            price_band=payload.price_band or "",
            material_constraints=payload.material_constraints or "",
            supplier_constraints=payload.supplier_constraints or "",
            cost_ceiling=payload.cost_ceiling or "",
        )

        return {
            "success": result.success,
            "status": result.status,
            "run_id": result.run_id,
            "output_dir": result.output_dir,
            "market_input": result.market_input,
            "market_normalized": result.market_normalized,
            "market_notes": result.market_notes,
            "market_confidence": result.market_confidence,
            "target_language": result.target_language,
            "go_to_market": result.go_to_market,
            "price_band": result.price_band,
            "material_constraints": result.material_constraints,
            "supplier_constraints": result.supplier_constraints,
            "cost_ceiling": result.cost_ceiling,
            "allow_incomplete": payload.allow_incomplete,
            "knowledge_versions": result.knowledge_versions,
            "knowledge_metadata": result.knowledge_metadata,
            "model_meta": result.model_meta,
            "feature_suggestion": result.feature_suggestion,
            "feature_data": result.feature_data,
            "missing_feature_questions": result.missing_feature_questions,
            "culture_suggestion": result.culture_suggestion,
            "culture_data": result.culture_data,
            "regulation_suggestion": result.regulation_suggestion,
            "regulation_data": result.regulation_data,
            "compliance_blockers": result.compliance_blockers,
            "risk_score": result.risk_score,
            "risk_level": result.risk_level,
            "design_suggestion": result.design_suggestion,
            "design_data": result.design_data,
            "stage_errors": result.stage_errors,
            "stage_warnings": result.stage_warnings,
            "timings": result.timings,
            "final_plan": result.final_plan,
            "final_plan_data": result.final_plan_data,
            "refined_prompt": result.refined_prompt,
            "image_path": result.image_path,
            "showcase_path": result.showcase_path,
            "image_url": _to_output_url(result.image_path),
            "showcase_url": _to_output_url(result.showcase_path),
            "logs": result.logs,
            "error": result.error,
        }

    @app.post("/api/run_async")
    def run_async(payload: RunRequest) -> Dict[str, Any]:
        try:
            validate_required_config(skip_vision=payload.skip_vision)
        except ConfigError as exc:
            return {"success": False, "error": str(exc), "logs": [f"[config error] {exc}"]}

        payload_data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        job_id = uuid.uuid4().hex
        with jobs_lock:
            _prune_jobs()
            jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "created_at": time.time(),
                "updated_at": time.time(),
                "payload": payload_data,
                "logs": [],
                "result": {},
                "error": "",
            }
            _persist_history(dict(jobs[job_id]))

        threading.Thread(target=_run_job, args=(job_id, payload_data), daemon=True).start()
        return {"success": True, "job_id": job_id}

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> Dict[str, Any]:
        with jobs_lock:
            _prune_jobs()
            job = jobs.get(job_id)
            if job:
                return _job_response(job_id, job)

        history = _load_history(job_id)
        if not history:
            raise HTTPException(status_code=404, detail="Job not found")
        return _job_response(job_id, history)

    @app.get("/api/history")
    def history(limit: int = 30) -> Dict[str, Any]:
        try:
            limit = int(limit)
        except Exception:
            limit = 30
        limit = max(1, min(limit, 200))

        items: List[Dict[str, Any]] = []
        try:
            files = sorted(
                history_dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:limit]
        except Exception:
            files = []

        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue

            payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
            result = data.get("result") if isinstance(data.get("result"), dict) else {}
            description = str(payload.get("description") or "")
            country = str(payload.get("country") or "")

            items.append(
                {
                    "job_id": str(data.get("job_id") or path.stem),
                    "run_id": str(result.get("run_id") or data.get("job_id") or path.stem),
                    "status": str(data.get("status") or ""),
                    "created_at": float(data.get("created_at") or 0) or None,
                    "updated_at": float(data.get("updated_at") or 0) or None,
                    "country": country,
                    "market_normalized": str(result.get("market_normalized") or country),
                    "target_language": str(result.get("target_language") or ""),
                    "description": description,
                    "skip_vision": bool(payload.get("skip_vision")) if "skip_vision" in payload else None,
                    "auto_3d": bool(payload.get("auto_3d")) if "auto_3d" in payload else None,
                    "allow_incomplete": bool(payload.get("allow_incomplete"))
                    if "allow_incomplete" in payload
                    else None,
                    "go_to_market": str(payload.get("go_to_market") or ""),
                    "price_band": str(payload.get("price_band") or ""),
                    "material_constraints": str(payload.get("material_constraints") or ""),
                    "supplier_constraints": str(payload.get("supplier_constraints") or ""),
                    "cost_ceiling": str(payload.get("cost_ceiling") or ""),
                    "image_url": str(result.get("image_url") or ""),
                    "showcase_url": str(result.get("showcase_url") or ""),
                    "output_dir": str(result.get("output_dir") or ""),
                    "error": str(data.get("error") or ""),
                }
            )

        return {"success": True, "items": items}

    @app.get("/api/history/{job_id}")
    def history_item(job_id: str) -> Dict[str, Any]:
        try:
            path = _history_path(job_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="History not found")

        if not path.exists():
            raise HTTPException(status_code=404, detail="History not found")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Invalid history file: {exc}")

        result = data.get("result")
        if isinstance(result, dict):
            if not result.get("run_id"):
                result["run_id"] = str(data.get("job_id") or path.stem)
            if result.get("image_path") and not result.get("image_url"):
                result["image_url"] = _to_output_url(str(result.get("image_path") or ""))
            if result.get("showcase_path") and not result.get("showcase_url"):
                result["showcase_url"] = _to_output_url(str(result.get("showcase_path") or ""))
            data["result"] = result

        return {"success": True, "job": data}

    return app


try:  # pragma: no cover
    app = create_app()
except Exception:
    app = None


def main() -> None:  # pragma: no cover
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=7860, reload=False)


if __name__ == "__main__":  # pragma: no cover
    main()
