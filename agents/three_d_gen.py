# -*- coding: utf-8 -*-
"""3D generation agent with DreamGaussian and preview fallback."""

import hashlib
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from langchain.tools import Tool
from PIL import Image, ImageDraw

from config import OUTPUT_DIR, ensure_output_dir
from .base_agent import BaseAgent


def _build_gradient_background(width: int, height: int) -> Image.Image:
    bg = Image.new("RGB", (width, height), color=(235, 238, 242))
    draw = ImageDraw.Draw(bg)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        r = int(235 - 20 * ratio)
        g = int(238 - 12 * ratio)
        b = int(242 - 4 * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    return bg


def _resolve_output_dir(output_dir: Optional[str], image_path: Optional[str] = None) -> Path:
    if output_dir:
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    output_root = ensure_output_dir()
    if image_path:
        try:
            image = Path(image_path).resolve()
            output_root = output_root.resolve()
            image.relative_to(output_root)
            return image.parent
        except Exception:
            return output_root
    return output_root


def _generate_preview_gif(image_path: str, *, output_dir: Optional[str] = None) -> str:
    """Generate a turntable-like GIF as fallback when 3D engine is unavailable."""
    output_root = _resolve_output_dir(output_dir, image_path)
    file_hash = hashlib.md5(image_path.encode("utf-8")).hexdigest()[:8]
    output_path = os.path.join(str(output_root), f"preview_turntable_{file_hash}.gif")
    if os.path.exists(output_path):
        return output_path

    src = Image.open(image_path).convert("RGBA")
    canvas_size = (640, 480)
    frames = []

    for frame_idx in range(18):
        frame = _build_gradient_background(*canvas_size)

        angle = frame_idx * 20
        spin = src.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)

        # Simulate pseudo-depth by oscillating scale.
        scale = 0.42 + 0.04 * math.sin(math.radians(angle))
        target_w = max(1, int(spin.width * scale))
        target_h = max(1, int(spin.height * scale))
        rendered = spin.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)

        x = (canvas_size[0] - target_w) // 2
        y = (canvas_size[1] - target_h) // 2 - 12
        frame.paste(rendered, (x, y), rendered)

        frames.append(frame)

    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=90,
        loop=0,
        disposal=2,
    )
    return output_path


def generate_3d_from_image(image_path: str, *, output_dir: Optional[str] = None) -> str:
    """
    Generate 3D showcase output from a single image.

    If DreamGaussian is not available, fallback to a turntable preview GIF.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Input image not found: {image_path}")

    dreamgaussian_path = shutil.which("dreamgaussian")
    if dreamgaussian_path is None:
        print("未找到DreamGaussian，输出模拟旋转GIF预览。")
        return _generate_preview_gif(image_path, output_dir=output_dir)

    output_root = _resolve_output_dir(output_dir, image_path)
    output_dir = os.path.join(str(output_root), "3d")
    os.makedirs(output_dir, exist_ok=True)
    video_path = os.path.join(output_dir, "video.mp4")
    if os.path.exists(video_path):
        return video_path

    cmd = [
        "python",
        "dreamgaussian/main.py",
        "--config",
        "dreamgaussian/configs/image.yaml",
        f"input={image_path}",
        f"save_path={output_dir}",
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        if os.path.exists(video_path):
            return video_path

        print("DreamGaussian执行完成，但未找到video.mp4，回退到GIF预览。")
        return _generate_preview_gif(image_path, output_dir=output_dir)
    except Exception as exc:
        print(f"3D生成失败: {exc}. 回退到GIF预览。")
        return _generate_preview_gif(image_path, output_dir=output_dir)


class ThreeDGenAgent(BaseAgent):
    def __init__(self, *, output_dir: Optional[str] = None):
        tools = [
            Tool(
                name="single_image_to_3d",
                func=lambda image_path: generate_3d_from_image(image_path, output_dir=output_dir),
                description="Generate a 3D showcase asset path from an input image path.",
            )
        ]
        system_prompt = (
            "Convert a 2D concept image into a 3D showcase output and return the generated file path."
        )
        super().__init__(tools, system_prompt)
