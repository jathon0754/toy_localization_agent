import time
import unittest
from unittest.mock import patch

from workflow import run_localization_workflow


class WorkflowResultHookTests(unittest.TestCase):
    def test_emits_partial_results(self) -> None:
        class DummyCultureAgent:
            def __init__(self, country: str):
                self.country = country
                self.log_hook = None

            def run(self, description: str, **kwargs) -> str:
                time.sleep(0.01)
                return (
                    '{'
                    '"colors":["red"],'
                    '"symbols":["sakura"],'
                    '"taboos":["4"],'
                    '"communication_style":"polite",'
                    '"packaging_copy_tone":"simple",'
                    '"notes":"ok"'
                    '}'
                )

        class DummyRegulationAgent:
            def __init__(self, country: str):
                self.country = country
                self.log_hook = None

            def run(self, description: str, **kwargs) -> str:
                time.sleep(0.04)
                return (
                    '{'
                    '"requirements":["req"],'
                    '"design_changes":["change"],'
                    '"labeling":["label"],'
                    '"age_grading":"6+",'
                    '"materials_chemicals":["abs"],'
                    '"notes":"ok"'
                    '}'
                )

        class DummyDesignAgent:
            def __init__(self):
                self.log_hook = None

            def run(self, payload: str) -> str:
                return (
                    '{'
                    '"appearance_changes":["a"],'
                    '"structure_safety_changes":["b"],'
                    '"materials":["m"],'
                    '"cost_impact":"low",'
                    '"tradeoffs":["t"],'
                    '"notes":"ok"'
                    '}'
                )

        class DummyCoordinatorAgent:
            def __init__(self):
                self.log_hook = None

            def run(self, payload: str) -> str:
                return (
                    '{'
                    '"summary":"S",'
                    '"cultural_actions":["c"],'
                    '"compliance_actions":["p"],'
                    '"design_changes":[],'
                    '"must_actions":["m"],'
                    '"should_actions":["s"],'
                    '"could_actions":["c"],'
                    '"cost_impact":"",'
                    '"cost_tooling":"",'
                    '"cost_bom":"",'
                    '"cost_testing":"",'
                    '"cost_schedule":"",'
                    '"implementation_steps":["step1"],'
                    '"risks":["r"],'
                    '"open_questions":[],'
                    '"assumptions":[],'
                    '"verification_required":[]'
                    '}'
                )

        class DummyFeatureAgent:
            def __init__(self):
                self.log_hook = None

            def run(self, payload: str) -> str:
                return (
                    '{'
                    '"intended_age":"6+",'
                    '"target_audience":"kids",'
                    '"assembly_level":"simple",'
                    '"has_small_parts":"yes",'
                    '"battery_type":"AA",'
                    '"power_source":"battery",'
                    '"has_light":"yes",'
                    '"has_sound":"no",'
                    '"has_magnets":"no",'
                    '"has_projectiles":"no",'
                    '"connectivity":"",'
                    '"use_scenario":"home",'
                    '"materials_mentioned":[],'
                    '"safety_risks":[]'
                    '}'
                )

        updates = []

        def hook(update):
            updates.append(update)

        with (
            patch("workflow.FeatureExtractorAgent", DummyFeatureAgent),
            patch("workflow.CultureAgent", DummyCultureAgent),
            patch("workflow.RegulationAgent", DummyRegulationAgent),
            patch("workflow.DesignAgent", DummyDesignAgent),
            patch("workflow.CoordinatorAgent", DummyCoordinatorAgent),
        ):
            result = run_localization_workflow(
                country="japan",
                description="toy",
                skip_vision=True,
                generate_3d=False,
                log_hook=lambda _: None,
                result_hook=hook,
            )

        self.assertTrue(result.success)
        self.assertTrue(result.run_id)
        self.assertIn("culture", result.timings)
        self.assertIn("regulation", result.timings)
        self.assertIn("design", result.timings)
        self.assertIn("coordinator", result.timings)
        self.assertIn("total", result.timings)
        self.assertGreaterEqual(len(updates), 3)
        self.assertTrue(any("culture_data" in update for update in updates))
        self.assertTrue(any("regulation_data" in update for update in updates))
        self.assertTrue(any("final_plan_data" in update for update in updates))
        self.assertTrue(result.feature_data)
        self.assertTrue(result.market_normalized)
        self.assertTrue(result.target_language)


if __name__ == "__main__":
    unittest.main()
