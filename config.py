"""Project configuration and startup validation."""

import os
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when required runtime configuration is missing."""


load_dotenv()

# LLM settings
OPENAI_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://www.sophnet.com/api/open-apis/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")

# Knowledge base storage
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")

# Vision model settings
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
IMAGE_GEN_MODEL = os.getenv("IMAGE_GEN_MODEL", "qwen-image")
IMAGE_GEN_SIZE = os.getenv("IMAGE_GEN_SIZE", "1024*1024")

# Output directory
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "outputs")
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)


def validate_required_config(skip_vision: bool = False) -> None:
    """Validate runtime configuration before running the pipeline."""
    missing = []

    if not OPENAI_API_KEY:
        missing.append("DEEPSEEK_API_KEY")

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
            "Image generation will fall back to dummy outputs if API calls fail."
        )
