from .base_agent import BaseAgent


class CoordinatorAgent(BaseAgent):
    def __init__(self):
        system_prompt = (
            "You are the product manager coordinating expert outputs. "
            "Use the language specified in target_language if provided. "
            "Return ONLY a valid JSON object and nothing else (no markdown, no code fences). "
            "Be concise: each array <= 12 items; each item <= 18 words; summary/cost_impact <= 3 sentences. "
            "Schema:\n"
            "{\n"
            '  "summary": string,\n'
            '  "compliance_blockers": string[],\n'
            '  "cultural_actions": string[],\n'
            '  "compliance_actions": string[],\n'
            '  "design_changes": string[],\n'
            '  "must_actions": string[],\n'
            '  "should_actions": string[],\n'
            '  "could_actions": string[],\n'
            '  "priority_actions": string[],\n'
            '  "cost_impact": string,\n'
            '  "cost_estimate": string,\n'
            '  "cost_tooling": string,\n'
            '  "cost_bom": string,\n'
            '  "cost_testing": string,\n'
            '  "cost_schedule": string,\n'
            '  "timeline_estimate": string,\n'
            '  "implementation_steps": string[],\n'
            '  "risks": string[],\n'
            '  "open_questions": string[],\n'
            '  "assumptions": string[],\n'
            '  "verification_required": string[]\n'
            "}"
        )
        super().__init__(
            system_prompt=system_prompt,
            wire_api="chat_completions",
            expects_json=True,
        )
