# -*- coding: utf-8 -*-
"""Image generation agent with DashScope and fallback output."""

import hashlib
import os

import requests
from langchain.tools import Tool
from PIL import Image

from config import DASHSCOPE_API_KEY, IMAGE_GEN_MODEL, IMAGE_GEN_SIZE, OUTPUT_DIR
from .base_agent import BaseAgent

try:
    from dashscope import ImageSynthesis

    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False
    print("Warning: dashscope is not installed, using dummy image mode.")


def _generate_dummy_image(prompt: str) -> str:
    """Generate a simple gradient image as fallback output."""
    width, height = 512, 512
    img = Image.new("RGB", (width, height), color=(73, 109, 137))

    for x in range(width):
        r = int(73 + (182 * x / width))
        g = int(109 + (146 * x / width))
        b = int(137 + (118 * x / width))
        for y in range(height):
            img.putpixel((x, y), (r, g, b))

    file_hash = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8]
    file_path = os.path.join(OUTPUT_DIR, f"dummy_{file_hash}.png")
    img.save(file_path)
    return file_path


def _download_image_to_output(image_url: str, prompt: str) -> str:
    response = requests.get(image_url, timeout=30)
    response.raise_for_status()

    file_hash = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8]
    file_path = os.path.join(OUTPUT_DIR, f"concept_{file_hash}.png")
    with open(file_path, "wb") as file_obj:
        file_obj.write(response.content)
    return file_path


def generate_image_from_prompt(prompt: str) -> str:
    """Call DashScope text-to-image API and fallback on failure."""
    if not DASHSCOPE_AVAILABLE:
        return _generate_dummy_image(prompt)

    if not DASHSCOPE_API_KEY:
        print("Warning: DASHSCOPE_API_KEY is missing, using dummy image.")
        return _generate_dummy_image(prompt)

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
            print("DashScope returned no image, using dummy image.")
            return _generate_dummy_image(prompt)

        image_url = results[0].url
        return _download_image_to_output(image_url, prompt)
    except Exception as exc:
        print(f"Image generation error: {exc}. Using dummy image.")
        return _generate_dummy_image(prompt)


class ImageGenAgent(BaseAgent):
    def __init__(self):
        tools = [
            Tool(
                name="text_to_image",
                func=generate_image_from_prompt,
                description="Generate a concept image from prompt and return file path.",
            )
        ]
        system_prompt = "Generate a toy concept image based on user prompt and return file path."
        super().__init__(tools, system_prompt)