import json
from typing import Any, Dict, Optional

from .base_agent import BaseAgent
from knowledge.retriever import CountryKnowledgeRetriever


class RegulationAgent(BaseAgent):
    def __init__(self, country: str):
        self.country = country.strip().lower()
        self.knowledge = CountryKnowledgeRetriever(self.country)
        system_prompt = (
            f"You are a toy safety and compliance expert for {self.country}. "
            "Given a toy description, list key compliance requirements and concrete design changes. "
            "Return ONLY valid JSON and nothing else (no markdown, no code fences). "
            "Be concise: each array <= 8 items; each item <= 18 words; notes <= 2 sentences. "
            "Schema:\n"
            "{\n"
            '  "requirements": string[],\n'
            '  "design_changes": string[],\n'
            '  "labeling": string[],\n'
            '  "required_tests": string[],\n'
            '  "age_grading": string,\n'
            '  "label_language": string,\n'
            '  "materials_chemicals": string[],\n'
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
                "Regional regulation/safety reference:\n",
                f"{reference}\n\n",
                "Return ONLY the JSON object that matches the schema in the system prompt.",
            ]
        )
        prompt = "".join(parts)
        return super().run(prompt)
