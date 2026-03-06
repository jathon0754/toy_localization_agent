from .base_agent import BaseAgent


class DesignAgent(BaseAgent):
    def __init__(self):
        system_prompt = (
            "You are a senior toy product designer. "
            "Combine cultural and compliance inputs into a practical design revision proposal. "
            "Include appearance changes, structure/safety changes, materials, and cost impact."
        )
        super().__init__(system_prompt=system_prompt)