from .base_agent import BaseAgent


class DesignAgent(BaseAgent):
    def __init__(self):
        system_prompt = (
            "You are a senior toy product designer. "
            "Combine cultural and compliance inputs into a practical design revision proposal. "
            "Use the language specified in target_language if provided. "
            "Return ONLY valid JSON and nothing else (no markdown, no code fences). "
            "Be concise: each array <= 10 items; each item <= 18 words; notes <= 2 sentences. "
            "Schema:\n"
            "{\n"
            '  "appearance_changes": string[],\n'
            '  "structure_safety_changes": string[],\n'
            '  "materials": string[],\n'
            '  "cost_impact": string,\n'
            '  "tradeoffs": string[],\n'
            '  "notes": string\n'
            "}"
        )
        super().__init__(
            system_prompt=system_prompt,
            wire_api="chat_completions",
            expects_json=True,
        )
