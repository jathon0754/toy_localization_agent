import json

from .base_agent import BaseAgent
from language_utils import language_name


class LanguageNormalizerAgent(BaseAgent):
    def __init__(self):
        system_prompt = (
            "You are a localization assistant. "
            "Translate JSON values to the target language while keeping keys and structure unchanged. "
            "Return ONLY valid JSON, no markdown or code fences. "
            "Do not add new facts; preserve the original meaning."
        )
        super().__init__(system_prompt=system_prompt, wire_api="chat_completions", expects_json=True)

    def run(self, payload: dict, *, target_lang: str) -> str:
        lang = language_name(target_lang)
        prompt = (
            f"Target language: {lang}\n"
            "Translate all string values in the JSON below to the target language. "
            "Keep keys and list structure unchanged.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
        return super().run(prompt)
