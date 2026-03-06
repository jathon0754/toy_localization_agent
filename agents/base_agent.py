from typing import Callable, List, Optional

from langchain_openai import ChatOpenAI

from config import LLM_MODEL, OPENAI_API_BASE, OPENAI_API_KEY


class BaseAgent:
    def __init__(self, tools: Optional[List[object]] = None, system_prompt: str = ""):
        self.llm = ChatOpenAI(
            model=LLM_MODEL,
            temperature=0.7,
            openai_api_key=OPENAI_API_KEY,
            base_url=OPENAI_API_BASE,
        )
        self.tools = tools or []
        self.system_prompt = system_prompt

    def _run_single_tool(self, user_input: str) -> str:
        tool = self.tools[0]
        tool_fn: Callable[[str], str] = getattr(tool, "func")
        return tool_fn(user_input)

    def _run_llm(self, user_input: str) -> str:
        messages = []
        if self.system_prompt:
            messages.append(("system", self.system_prompt))
        messages.append(("user", user_input))

        response = self.llm.invoke(messages)
        return response.content if hasattr(response, "content") else str(response)

    def run(self, user_input: str) -> str:
        # If a single tool is attached, call it directly for deterministic behavior.
        if len(self.tools) == 1:
            return self._run_single_tool(user_input)
        return self._run_llm(user_input)