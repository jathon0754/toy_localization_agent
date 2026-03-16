import json

from .base_agent import BaseAgent


class FeatureExtractorAgent(BaseAgent):
    def __init__(self):
        system_prompt = (
            "You are a product analyst. Extract structured product features from the toy description. "
            "Return ONLY valid JSON and nothing else (no markdown, no code fences). "
            "If a field is unknown, return an empty string or empty array. "
            "Schema:\n"
            "{\n"
            '  "toy_category": string,\n'
            '  "intended_age": string,\n'
            '  "age_group": string,\n'
            '  "target_audience": string,\n'
            '  "assembly_level": string,\n'
            '  "is_electronic": string,\n'
            '  "has_small_parts": string,\n'
            '  "battery_type": string,\n'
            '  "power_source": string,\n'
            '  "has_light": string,\n'
            '  "has_sound": string,\n'
            '  "has_magnets": string,\n'
            '  "has_projectiles": string,\n'
            '  "wireless": string,\n'
            '  "connectivity": string,\n'
            '  "use_scenario": string,\n'
            '  "materials_mentioned": string[],\n'
            '  "safety_risks": string[]\n'
            "}"
        )
        super().__init__(system_prompt=system_prompt, wire_api="chat_completions", expects_json=True)

    def run(self, user_input: str) -> str:
        payload = {"description": user_input}
        prompt = (
            "Extract product features from the following toy description. "
            "Respond using the JSON schema in the system prompt.\n\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )
        return super().run(prompt)
