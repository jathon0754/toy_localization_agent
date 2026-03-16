from .base_agent import BaseAgent


class JsonRepairAgent(BaseAgent):
    def __init__(self):
        system_prompt = (
            "You are a JSON repair assistant. "
            "Given a target schema and a raw model output, "
            "return ONLY a valid JSON object that matches the schema. "
            "Do not add commentary, markdown, or code fences. "
            "If a field is missing, use an empty string or empty array. "
            "Preserve the original language and avoid inventing new facts."
        )
        super().__init__(system_prompt=system_prompt, wire_api="chat_completions", expects_json=True)
