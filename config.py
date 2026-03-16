"""Project configuration and startup validation."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional


class ConfigError(RuntimeError):
    """Raised when required runtime configuration is missing."""


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        # Allow importing this project without optional dev dependencies.
        return
    project_env = Path(__file__).resolve().parent / ".env"
    if project_env.exists():
        load_dotenv(dotenv_path=project_env)
    else:
        load_dotenv()


def _first_env(*names: str, default: Optional[str] = None) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def _env_bool(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, *, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, *, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


_load_dotenv()

# LLM settings (OpenAI-compatible)
LLM_API_KEY = _first_env("LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")
LLM_API_BASE = _first_env(
    "LLM_API_BASE",
    "OPENAI_API_BASE",
    default="http://localhost:8317/v1",
)
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5.2")
LLM_WIRE_API = os.getenv("LLM_WIRE_API", "responses")  # "responses" | "chat_completions"
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "xhigh")
LLM_DISABLE_RESPONSE_STORAGE = _env_bool("LLM_DISABLE_RESPONSE_STORAGE", default=True)
LLM_TEMPERATURE = _env_float("LLM_TEMPERATURE", default=0.7)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")

# Knowledge base storage
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")

# Vision model settings
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
IMAGE_GEN_MODEL = os.getenv("IMAGE_GEN_MODEL", "qwen-image")
IMAGE_GEN_SIZE = os.getenv("IMAGE_GEN_SIZE", "1024*1024")

# Output directory (create lazily to avoid import-time side effects)
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "outputs")

# Runtime helpers
LLM_ENABLE_CACHE = _env_bool("LLM_ENABLE_CACHE", default=True)
LLM_CACHE_DIR = os.getenv("LLM_CACHE_DIR", str(Path(OUTPUT_DIR) / "cache" / "llm"))
LLM_MAX_RETRIES = _env_int("LLM_MAX_RETRIES", default=2)
LLM_RETRY_BACKOFF_SECONDS = _env_float("LLM_RETRY_BACKOFF_SECONDS", default=0.6)
LLM_TIMEOUT_SECONDS = _env_float("LLM_TIMEOUT_SECONDS", default=120.0)
LLM_MAX_OUTPUT_TOKENS = _env_int("LLM_MAX_OUTPUT_TOKENS", default=900)
LLM_PREFLIGHT = _env_bool("LLM_PREFLIGHT", default=True)
LLM_PREFLIGHT_TIMEOUT_SECONDS = _env_float("LLM_PREFLIGHT_TIMEOUT_SECONDS", default=2.0)
LLM_JSON_REPAIR = _env_bool("LLM_JSON_REPAIR", default=True)

# Backward-compatible aliases
OPENAI_API_KEY = LLM_API_KEY
OPENAI_API_BASE = LLM_API_BASE


def ensure_output_dir() -> Path:
    path = Path(OUTPUT_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_run_id(run_id: str) -> str:
    """Return a filesystem-safe run identifier."""
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(run_id or "").strip())
    safe = safe.strip("._-")
    return safe or "run"


def resolve_run_output_dir(run_id: Optional[str]) -> Path:
    """Resolve per-run output directory under OUTPUT_DIR."""
    root = ensure_output_dir()
    if not run_id:
        return root
    safe = sanitize_run_id(run_id)
    path = root / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_required_config(skip_vision: bool = False) -> None:
    """Validate runtime configuration before running the pipeline."""
    missing = []

    if not LLM_API_KEY:
        missing.append("LLM_API_KEY (or DEEPSEEK_API_KEY / OPENAI_API_KEY)")

    if missing:
        missing_text = ", ".join(missing)
        raise ConfigError(
            f"Missing required environment variables: {missing_text}. "
            "Create a .env file from .env.example or export them in your shell."
        )

    if not skip_vision and not DASHSCOPE_API_KEY:
        # Image generation still works in fallback mode, but warn early.
        print(
            "[warning] DASHSCOPE_API_KEY is not set. "
            "Image generation will try LLM_API_BASE first; if unsupported, it falls back to dummy outputs."
        )
