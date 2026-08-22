from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEBUI_DIR = ROOT / "lightrag_webui"
NPM_COMMAND = "npm.cmd" if sys.platform.startswith("win") else "npm"


def run_step(title: str, command: list[str], cwd: Path) -> None:
    print(f"\n==> {title}")
    print(" ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run fault-tree validation regression checks."
    )
    parser.add_argument(
        "--with-business-check",
        action="store_true",
        help="Also run the live API business-validation cases after the offline regression suite.",
    )
    parser.add_argument(
        "--business-check-url",
        default="http://127.0.0.1:9621",
        help="Base URL for the live business-validation API checks.",
    )
    parser.add_argument(
        "--business-check-token",
        default=None,
        help="Optional Bearer token for the live business-validation API checks.",
    )
    parser.add_argument(
        "--include-llm-suggestions",
        action="store_true",
        help="Enable LLM suggestion generation during live business-validation checks.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    run_step(
        "Backend fault-tree validation pytest",
        [sys.executable, "-m", "pytest", "tests/test_fault_tree_validation_endpoint.py", "-q"],
        ROOT,
    )
    run_step(
        "Frontend fault-tree validation state regression",
        [NPM_COMMAND, "run", "test:fault-tree-validation"],
        WEBUI_DIR,
    )

    if args.with_business_check:
        business_command = [
            sys.executable,
            "scripts/run_fault_tree_validation_business_check.py",
            args.business_check_url,
        ]
        if args.business_check_token:
            business_command.append(args.business_check_token)
        if args.include_llm_suggestions:
            business_command.append("--include-llm-suggestions")
        run_step(
            "Live fault-tree business validation",
            business_command,
            ROOT,
        )

    print("\nFault-tree validation regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())