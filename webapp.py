"""FastAPI web frontend for toy localization workflow."""

from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import ConfigError, OUTPUT_DIR, validate_required_config
from knowledge.retriever import CountryKnowledgeRetriever
from workflow import run_localization_workflow


class RunRequest(BaseModel):
    country: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=1, max_length=4000)
    skip_vision: bool = False
    auto_3d: bool = False


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


app = FastAPI(title="Toy Localization Frontend", version="1.0.0")

web_dir = Path(__file__).parent / "web"
assets_dir = web_dir / "assets"
app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    html = (web_dir / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.get("/api/countries")
def countries() -> Dict[str, List[str]]:
    return {"countries": CountryKnowledgeRetriever.available_countries()}


@app.post("/api/run")
def run(payload: RunRequest) -> Dict[str, object]:
    try:
        validate_required_config(skip_vision=payload.skip_vision)
    except ConfigError as exc:
        return {"success": False, "error": str(exc), "logs": [f"[config error] {exc}"]}

    result = run_localization_workflow(
        country=payload.country,
        description=payload.description,
        skip_vision=payload.skip_vision,
        generate_3d=(not payload.skip_vision) and payload.auto_3d,
    )

    response = {
        "success": result.success,
        "final_plan": result.final_plan,
        "refined_prompt": result.refined_prompt,
        "image_path": result.image_path,
        "showcase_path": result.showcase_path,
        "image_url": _to_output_url(result.image_path),
        "showcase_url": _to_output_url(result.showcase_path),
        "logs": result.logs,
        "error": result.error,
    }
    return response


def main() -> None:
    import uvicorn

    uvicorn.run("webapp:app", host="0.0.0.0", port=7860, reload=False)


if __name__ == "__main__":
    main()
