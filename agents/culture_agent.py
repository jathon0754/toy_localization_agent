from .base_agent import BaseAgent
from knowledge.retriever import CountryKnowledgeRetriever


class CultureAgent(BaseAgent):
    def __init__(self, country: str):
        self.country = country.strip().lower()
        self.knowledge = CountryKnowledgeRetriever(self.country)
        system_prompt = (
            f"You are a toy localization expert for {self.country}. "
            "Use the provided cultural reference to suggest actionable localization changes, "
            "including colors, symbols, taboos, and communication style."
        )
        super().__init__(system_prompt=system_prompt)

    def run(self, user_input: str) -> str:
        reference = self.knowledge.get_reference(user_input)
        prompt = (
            f"Target country: {self.country}\n"
            f"Original toy description:\n{user_input}\n\n"
            "Cultural reference:\n"
            f"{reference}\n\n"
            "Please provide concise, practical localization suggestions."
        )
        return super().run(prompt)
