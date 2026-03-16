# -*- coding: utf-8 -*-
"""CLI entrypoint for toy localization workflow."""

import argparse
import sys


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
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Continue even if critical product details are missing",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Disable interactive prompts for missing details",
    )
    parser.add_argument(
        "--target-language",
        default="",
        help="Override output language, e.g. zh, en, ja (optional)",
    )
    parser.add_argument("--channel", default="", help="Go-to-market channel (e.g. ecommerce, retail)")
    parser.add_argument("--price-band", default="", help="Price band (e.g. budget, mid, premium)")
    parser.add_argument(
        "--material-constraints", default="", help="Material constraints (comma-separated)"
    )
    parser.add_argument(
        "--supplier-constraints", default="", help="Supplier constraints or exclusions"
    )
    parser.add_argument("--cost-ceiling", default="", help="Cost ceiling / BOM limit")
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
    from config import ConfigError, validate_required_config
    from workflow import run_localization_workflow

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
        target_language=args.target_language,
        allow_incomplete=args.allow_incomplete,
        interactive=not args.non_interactive,
        go_to_market=args.channel,
        price_band=args.price_band,
        material_constraints=args.material_constraints,
        supplier_constraints=args.supplier_constraints,
        cost_ceiling=args.cost_ceiling,
        log_hook=print,
    )

    if not result.success:
        return 1
    if result.status == "blocked":
        if result.missing_feature_questions:
            print("\nMissing details:")
            for item in result.missing_feature_questions:
                print(f"- {item}")
        print("\n[blocked] Missing critical details. Re-run with --allow-incomplete to continue.")
        return 2

    def safe_print(text: str) -> None:
        try:
            print(text)
        except UnicodeEncodeError:
            encoded = text.encode(sys.stdout.encoding or "utf-8", errors="replace")
            sys.stdout.buffer.write(encoded + b"\n")
            sys.stdout.flush()

    print("\n========== FINAL PLAN ==========\n")
    if result.run_id:
        print(f"[run_id] {result.run_id}")
    if result.output_dir:
        print(f"[output_dir] {result.output_dir}")
    safe_print(result.final_plan)

    if not args.skip_vision:
        safe_print(f"\nRefined prompt:\n{result.refined_prompt}\n")
        if result.image_path:
            print(f"Concept image saved to: {result.image_path}")
        if result.showcase_path:
            print(f"3D showcase saved to: {result.showcase_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
