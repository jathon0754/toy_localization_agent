from .base_agent import BaseAgent


class PromptRefinerAgent(BaseAgent):
    def __init__(self):
        system_prompt = (
            "You are an image prompt engineer. Convert product design text into a high-quality image prompt. "
            "Include subject details, style, composition, lighting, background, and optional negative prompt."
        )
        super().__init__(system_prompt=system_prompt)