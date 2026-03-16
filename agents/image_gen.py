# -*- coding: utf-8 -*-
"""Image generation agent with OpenAI-compatible first and fallback outputs."""

import base64
import hashlib
import os
import time
from pathlib import Path
from typing import Optional

import requests
from langchain.tools import Tool
from PIL import Image

from config import (
    DASHSCOPE_API_KEY,
    IMAGE_GEN_MODEL,
    IMAGE_GEN_SIZE,
    LLM_API_BASE,
    LLM_API_KEY,
    LLM_TIMEOUT_SECONDS,
    OUTPUT_DIR,
    ensure_output_dir,
)
from .base_agent import BaseAgent

try:
    from dashscope import ImageSynthesis

    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False
    print("Warning: dashscope is not installed, using dummy image mode.")


def _resolve_output_dir(output_dir: Optional[str]) -> Path:
    if output_dir:
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path
    return ensure_output_dir()


def _generate_dummy_image(prompt: str, *, output_dir: Optional[str] = None) -> str:
    """Generate a simple gradient image as fallback output."""
    output_root = _resolve_output_dir(output_dir)
    file_hash = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8]
    file_path = os.path.join(str(output_root), f"dummy_{file_hash}.png")
    if os.path.exists(file_path):
        return file_path

    width, height = 512, 512
    img = Image.new("RGB", (width, height), color=(73, 109, 137))

    # Fill via column lines to avoid per-pixel loops.
    for x in range(width):
        ratio = x / max(width - 1, 1)
        r = int(73 + (182 * ratio))
        g = int(109 + (146 * ratio))
        b = int(137 + (118 * ratio))
        img.paste((r, g, b), box=(x, 0, x + 1, height))

    img.save(file_path)
    return file_path


def _download_image_to_output(
    image_url: str, prompt: str, *, output_dir: Optional[str] = None
) -> str:
    output_root = _resolve_output_dir(output_dir)
    file_hash = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8]
    file_path = os.path.join(str(output_root), f"concept_{file_hash}.png")
    if os.path.exists(file_path):
        return file_path

    last_exc = None
    response = None
    for attempt in range(3):
        try:
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            if attempt >= 2:
                break
            time.sleep(0.6 * (2**attempt))
    if last_exc is not None or response is None:
        raise last_exc or RuntimeError("Image download failed with no response")
    with open(file_path, "wb") as file_obj:
        file_obj.write(response.content)
    return file_path


def _generate_image_openai(prompt: str, *, output_dir: Optional[str] = None) -> str:
    """Call OpenAI-compatible image API (via LLM_API_BASE) and save to outputs/."""
    output_root = _resolve_output_dir(output_dir)
    file_hash = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8]
    file_path = os.path.join(str(output_root), f"concept_{file_hash}.png")
    if os.path.exists(file_path):
        return file_path

    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:
        raise RuntimeError("openai client is not installed") from exc

    size = (IMAGE_GEN_SIZE or "").replace("*", "x") or "1024x1024"
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_API_BASE, timeout=LLM_TIMEOUT_SECONDS)
    response = client.images.generate(
        model=IMAGE_GEN_MODEL,
        prompt=prompt,
        n=1,
        size=size,
        response_format="b64_json",
    )

    data = getattr(response, "data", None) or []
    if not data:
        raise RuntimeError("Image API returned empty data")

    item = data[0]
    b64_json = getattr(item, "b64_json", None)
    url = getattr(item, "url", None)

    if isinstance(b64_json, str) and b64_json.strip():
        raw = base64.b64decode(b64_json)
        with open(file_path, "wb") as file_obj:
            file_obj.write(raw)
        return file_path

    if isinstance(url, str) and url.strip():
        return _download_image_to_output(url, prompt, output_dir=output_dir)

    raise RuntimeError("Image API returned no url/b64_json")


def generate_image_from_prompt(prompt: str, *, output_dir: Optional[str] = None) -> str:
    """Generate a concept image and return the saved file path.

    Priority:
    1) OpenAI-compatible image endpoint at LLM_API_BASE
    2) DashScope (if installed and DASHSCOPE_API_KEY is set)
    3) Dummy image fallback
    """
    try:
        return _generate_image_openai(prompt, output_dir=output_dir)
    except Exception as exc:
        print(f"Warning: OpenAI-compatible image generation failed: {exc}")

    if not DASHSCOPE_AVAILABLE:
        return _generate_dummy_image(prompt, output_dir=output_dir)

    if not DASHSCOPE_API_KEY:
        return _generate_dummy_image(prompt, output_dir=output_dir)

    try:
        response = ImageSynthesis.call(
            model=IMAGE_GEN_MODEL,
            prompt=prompt,
            n=1,
            size=IMAGE_GEN_SIZE,
            steps=30,
            api_key=DASHSCOPE_API_KEY,
        )

        if getattr(response, "status_code", None) != 200:
            code = getattr(response, "code", "unknown")
            message = getattr(response, "message", "unknown")
            print(f"DashScope API call failed, code: {code}, message: {message}")
            return _generate_dummy_image(prompt)

        results = response.output.results
        if not results:
            return _generate_dummy_image(prompt)

        image_url = results[0].url
        return _download_image_to_output(image_url, prompt, output_dir=output_dir)
    except Exception as exc:
        print(f"Warning: DashScope image generation failed: {exc}")
        return _generate_dummy_image(prompt, output_dir=output_dir)


class ImageGenAgent(BaseAgent):
    def __init__(self, *, output_dir: Optional[str] = None):
        tools = [
            Tool(
                name="text_to_image",
                func=lambda prompt: generate_image_from_prompt(prompt, output_dir=output_dir),
                description="Generate a concept image from prompt and return file path.",
            )
        ]
        system_prompt = "Generate a toy concept image based on user prompt and return file path."
        super().__init__(tools, system_prompt)
