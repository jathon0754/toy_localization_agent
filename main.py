# -*- coding: utf-8 -*-
"""CLI entrypoint for toy localization workflow."""

import argparse

from config import ConfigError, validate_required_config
from workflow import run_localization_workflow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Toy localization assistant (multi-agent)")
    parser.add_argument("--country", required=True, help="Target country code, e.g. usa, japan")
    parser.add_argument("--description", required=True, help="Original toy description")
    parser.add_argument(
        "--skip-vision",
        action="store_true",
        help="Skip vision generation stage and output text plan only",
    )
    parser.add_argument(
        "--auto-3d",
        action="store_true",
        help="Automatically continue to 3D generation without interactive prompt",
    )
    return parser.parse_args()


def should_generate_3d(auto_3d: bool) -> bool:
    if auto_3d:
        return True

    try:
        choice = input("Continue with 3D video generation? (y/n): ").strip().lower()
    except EOFError:
        print("Non-interactive environment detected, skipping 3D. Use --auto-3d to force.")
        return False

    return choice == "y"


def main() -> int:
    args = parse_args()
    country = args.country.strip().lower()

    try:
        validate_required_config(skip_vision=args.skip_vision)
    except ConfigError as exc:
        print(f"[config error] {exc}")
        return 1

    generate_3d = False if args.skip_vision else should_generate_3d(args.auto_3d)
    result = run_localization_workflow(
        country=country,
        description=args.description,
        skip_vision=args.skip_vision,
        generate_3d=generate_3d,
        log_hook=print,
    )

    if not result.success:
        return 1

    print("\n========== FINAL PLAN ==========\n")
    print(result.final_plan)

    if not args.skip_vision:
        print(f"\nRefined prompt:\n{result.refined_prompt}\n")
        if result.image_path:
            print(f"Concept image saved to: {result.image_path}")
        if result.showcase_path:
            print(f"3D showcase saved to: {result.showcase_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
