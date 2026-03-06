from .base_agent import BaseAgent
from knowledge.retriever import CountryKnowledgeRetriever


class RegulationAgent(BaseAgent):
    def __init__(self, country: str):
        self.country = country.strip().lower()
        self.knowledge = CountryKnowledgeRetriever(self.country)
        system_prompt = (
            f"You are a toy safety and compliance expert for {self.country}. "
            "Given a toy description, list key compliance requirements and concrete design changes. "
            "Cover mechanical safety, small parts, sharp edges, materials/chemicals, labeling, and age grading."
        )
        super().__init__(system_prompt=system_prompt)

    def run(self, user_input: str) -> str:
        reference = self.knowledge.get_reference(user_input)
        prompt = (
            f"Target country: {self.country}\n"
            f"Original toy description:\n{user_input}\n\n"
            "Regional regulation/safety reference:\n"
            f"{reference}\n\n"
            "List practical compliance requirements and concrete design changes."
        )
        return super().run(prompt)
