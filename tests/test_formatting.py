import unittest

from formatting import extract_json_object, format_final_plan_markdown


class ExtractJsonObjectTests(unittest.TestCase):
    def test_direct_json(self) -> None:
        data = extract_json_object('{"a": 1, "b": "x"}')
        self.assertEqual(data, {"a": 1, "b": "x"})

    def test_json_in_code_fence(self) -> None:
        text = "```json\n{\"k\": [\"v1\", \"v2\"]}\n```"
        data = extract_json_object(text)
        self.assertEqual(data, {"k": ["v1", "v2"]})

    def test_json_with_prefix_suffix(self) -> None:
        text = "Here you go:\n{\"ok\": true}\nThanks!"
        data = extract_json_object(text)
        self.assertEqual(data, {"ok": True})


class FormatFinalPlanMarkdownTests(unittest.TestCase):
    def test_formats_known_sections(self) -> None:
        plan = {
            "summary": "S",
            "cultural_actions": ["A"],
            "compliance_actions": ["B"],
            "design_changes": ["C"],
            "cost_impact": "Low",
            "implementation_steps": ["Step1"],
        }
        md = format_final_plan_markdown(plan, language="en")
        self.assertIn("# Final Localization Plan", md)
        self.assertIn("## Summary", md)
        self.assertIn("- A", md)
        self.assertIn("1. Step1", md)


if __name__ == "__main__":
    unittest.main()
