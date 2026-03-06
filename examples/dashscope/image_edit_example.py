"""DashScope image editing example."""

import base64
import mimetypes
import os
from pathlib import Path

import dashscope
from dashscope import MultiModalConversation

# Mainland endpoint. For international endpoint use:
# https://dashscope-intl.aliyuncs.com/api/v1
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
dashscope.base_http_api_url = DASHSCOPE_BASE_URL


def encode_file(file_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type or not mime_type.startswith("image/"):
        raise ValueError("Unsupported or unrecognized image format")

    with open(file_path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def main() -> None:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("Please set DASHSCOPE_API_KEY before running this script.")

    default_image = Path(__file__).with_name("sample_input.png")
    image_path = os.getenv("DASHSCOPE_EDIT_IMAGE", str(default_image))
    if not os.path.exists(image_path):
        raise FileNotFoundError(
            f"Input image not found: {image_path}. "
            "Set DASHSCOPE_EDIT_IMAGE to an existing image file."
        )

    image = encode_file(image_path)

    messages = [
        {
            "role": "user",
            "content": [
                {"image": image},
                {
                    "text": "生成一张符合深度图的图像，遵循以下描述：一辆红色的破旧的自行车停在一条泥泞的小路上，背景是茂密的原始森林"
                },
            ],
        }
    ]

    response = MultiModalConversation.call(
        api_key=api_key,
        model="qwen-image-edit-max",
        messages=messages,
        stream=False,
        n=2,
        watermark=False,
        negative_prompt=" ",
        prompt_extend=True,
        size="1536*1024",
    )

    if response.status_code == 200:
        for i, content in enumerate(response.output.choices[0].message.content, start=1):
            print(f"输出图像{i}的URL: {content['image']}")
        return

    print(f"HTTP返回码: {response.status_code}")
    print(f"错误码: {response.code}")
    print(f"错误信息: {response.message}")
    print("请参考文档: https://help.aliyun.com/zh/model-studio/error-code")


if __name__ == "__main__":
    main()
