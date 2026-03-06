from .base_agent import BaseAgent


class CoordinatorAgent(BaseAgent):
    def __init__(self):
        system_prompt = (
            "You are the product manager coordinating expert outputs. "
            "Produce a structured final localization plan with: cultural actions, compliance actions, "
            "design changes, estimated cost impact, and next implementation steps."
        )
        super().__init__(system_prompt=system_prompt)