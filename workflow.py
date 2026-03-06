"""Core workflow orchestration shared by CLI and web UI."""

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from agents.coordinator import CoordinatorAgent
from agents.culture_agent import CultureAgent
from agents.design_agent import DesignAgent
from agents.image_gen import ImageGenAgent
from agents.prompt_refiner import PromptRefinerAgent
from agents.regulation_agent import RegulationAgent
from agents.three_d_gen import ThreeDGenAgent


LogHook = Optional[Callable[[str], None]]


@dataclass
class WorkflowResult:
    success: bool
    final_plan: str = ""
    refined_prompt: str = ""
    image_path: str = ""
    showcase_path: str = ""
    logs: List[str] = field(default_factory=list)
    error: str = ""


def run_localization_workflow(
    country: str,
    description: str,
    *,
    skip_vision: bool,
    generate_3d: bool,
    log_hook: LogHook = None,
) -> WorkflowResult:
    """Run localization workflow and return structured outputs."""

    logs: List[str] = []

    def log(message: str) -> None:
        logs.append(message)
        if log_hook is not None:
            log_hook(message)

    try:
        normalized_country = country.strip().lower()

        log("\n[init] Loading agents...")
        culture_expert = CultureAgent(normalized_country)
        regulation_expert = RegulationAgent(normalized_country)
        design_expert = DesignAgent()
        coordinator = CoordinatorAgent()

        log("\n[culture] Analyzing...")
        culture_suggestion = culture_expert.run(description)
        log("[culture] Done.\n")

        log("[regulation] Analyzing...")
        regulation_suggestion = regulation_expert.run(description)
        log("[regulation] Done.\n")

        design_input = (
            f"Original design: {description}\n"
            f"Culture suggestions: {culture_suggestion}\n"
            f"Regulation suggestions: {regulation_suggestion}"
        )
        log("[design] Building design plan...")
        design_suggestion = design_expert.run(design_input)
        log("[design] Done.\n")

        coordinator_input = (
            f"Original design: {description}\n"
            f"Target market: {normalized_country}\n"
            f"Culture suggestions: {culture_suggestion}\n"
            f"Regulation suggestions: {regulation_suggestion}\n"
            f"Design plan: {design_suggestion}"
        )
        log("[coordinator] Building final plan...")
        final_plan = coordinator.run(coordinator_input)

        refined_prompt = ""
        image_path = ""
        showcase_path = ""

        if skip_vision:
            log("\nVision stage skipped.")
            return WorkflowResult(
                success=True,
                final_plan=final_plan,
                logs=logs,
            )

        log("\n========== VISION STAGE ==========\n")
        log("[prompt-refiner] Generating prompt...")
        refiner = PromptRefinerAgent()
        refined_prompt = refiner.run(
            f"Generate a high quality image prompt from this plan: {final_plan}"
        )
        log("[prompt-refiner] Done.")

        log("[image-gen] Generating concept image...")
        image_gen = ImageGenAgent()
        image_path = image_gen.run(refined_prompt)
        log(f"[image-gen] Concept image saved to: {image_path}")

        if generate_3d:
            log("[3d-gen] Generating 3D model and video/preview...")
            three_d_gen = ThreeDGenAgent()
            showcase_path = three_d_gen.run(image_path)
            log(f"[3d-gen] Showcase saved to: {showcase_path}")
        else:
            log("Skipped 3D generation.")

        log("\nWorkflow finished.")
        return WorkflowResult(
            success=True,
            final_plan=final_plan,
            refined_prompt=refined_prompt,
            image_path=image_path,
            showcase_path=showcase_path,
            logs=logs,
        )
    except Exception as exc:
        error = str(exc)
        log(f"[runtime error] {error}")
        return WorkflowResult(success=False, logs=logs, error=error)
