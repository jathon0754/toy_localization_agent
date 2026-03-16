import json
from typing import Any, Dict, Optional

from .base_agent import BaseAgent
from knowledge.retriever import CountryKnowledgeRetriever


class CultureAgent(BaseAgent):
    def __init__(self, country: str):
        self.country = country.strip().lower()
        self.knowledge = CountryKnowledgeRetriever(self.country)
        system_prompt = (
            f"You are a toy localization expert for {self.country}. "
            "Use the provided cultural reference to suggest actionable localization changes. "
            "Return ONLY valid JSON and nothing else (no markdown, no code fences). "
            "Be concise: each array <= 8 items; each item <= 18 words; notes <= 2 sentences. "
            "Schema:\n"
            "{\n"
            '  "colors": string[],\n'
            '  "symbols": string[],\n'
            '  "taboos": string[],\n'
            '  "communication_style": string,\n'
            '  "packaging_copy_tone": string,\n'
            '  "notes": string\n'
            "}"
        )
        super().__init__(
            system_prompt=system_prompt,
            wire_api="chat_completions",
            expects_json=True,
            context_version=self.knowledge.version_tag,
        )

    def run(
        self,
        description: str,
        *,
        feature_data: Optional[Dict[str, Any]] = None,
        language_hint: str = "",
        business_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        reference = self.knowledge.get_reference(description)
        feature_block = ""
        if feature_data:
            feature_block = json.dumps(feature_data, ensure_ascii=False, indent=2)
        context_block = ""
        if business_context:
            context_block = json.dumps(business_context, ensure_ascii=False, indent=2)
        parts = [
            f"Target country: {self.country}\n",
            f"Original toy description:\n{description}\n\n",
            f"Output language: {language_hint or 'auto'}\n\n",
        ]
        if feature_block:
            parts.append(f"Extracted product features:\n{feature_block}\n\n")
        if context_block:
            parts.append(f"Business context:\n{context_block}\n\n")
        parts.extend(
            [
                "Cultural reference:\n",
                f"{reference}\n\n",
                "Return ONLY the JSON object that matches the schema in the system prompt.",
            ]
        )
        prompt = "".join(parts)
        return super().run(prompt)
