from __future__ import annotations

import json
import socket
import sys
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES_FILE = ROOT / "scripts" / "fault_tree_validation_business_cases.json"
REQUEST_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_RETRIES = 1


def load_cases() -> list[dict]:
    return json.loads(CASES_FILE.read_text(encoding="utf-8"))


def prepare_case_payload(
    payload: dict,
    *,
    enable_llm_suggestions: bool,
) -> dict:
    prepared = deepcopy(payload)
    prepared["enable_llm_suggestions"] = enable_llm_suggestions
    return prepared


def is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError | socket.timeout):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        return isinstance(reason, TimeoutError | socket.timeout) or "timed out" in str(reason).lower()
    return "timed out" in str(exc).lower()


def post_validation(base_url: str, payload: dict, token: str | None = None) -> dict:
    request = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/fault-tree/validate",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
        method="POST",
    )
    attempts = MAX_TIMEOUT_RETRIES + 1
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            if attempt >= attempts or not is_timeout_error(exc):
                raise
            print(f"Request timed out, retrying ({attempt}/{MAX_TIMEOUT_RETRIES})...")

    raise RuntimeError("unreachable")


def validate_case_result(case: dict, result: dict) -> list[str]:
    expected = case["expected"]
    issues = result.get("issues", [])
    issue_codes = {issue.get("code") for issue in issues}
    summary = result.get("summary", {})
    errors: list[str] = []

    if summary.get("valid") != expected.get("valid"):
      errors.append(f"expected valid={expected.get('valid')} but got {summary.get('valid')}")
    if summary.get("error_count", 0) < expected.get("error_count_min", 0):
      errors.append(
          f"expected error_count >= {expected.get('error_count_min', 0)} but got {summary.get('error_count', 0)}"
      )
    if summary.get("warning_count", 0) < expected.get("warning_count_min", 0):
      errors.append(
          f"expected warning_count >= {expected.get('warning_count_min', 0)} but got {summary.get('warning_count', 0)}"
      )

    missing_codes = [code for code in expected.get("required_issue_codes", []) if code not in issue_codes]
    if missing_codes:
      errors.append(f"missing issue codes: {', '.join(missing_codes)}")

    return errors


def main(argv: list[str]) -> int:
    base_url = argv[1] if len(argv) > 1 else "http://127.0.0.1:9621"
    token = argv[2] if len(argv) > 2 else None
    enable_llm_suggestions = "--include-llm-suggestions" in argv[3:]
    cases = load_cases()

    print(f"Running {len(cases)} fault-tree business validation cases against {base_url}")
    print(
        "LLM suggestions are "
        + ("enabled" if enable_llm_suggestions else "disabled")
        + " for this business-check run."
    )
    failures = 0

    for case in cases:
        print(f"\n==> {case['name']}")
        print(case["description"])
        try:
            result = post_validation(
                base_url,
                prepare_case_payload(
                    case["payload"],
                    enable_llm_suggestions=enable_llm_suggestions,
                ),
                token=token,
            )
        except urllib.error.HTTPError as exc:
            failures += 1
            print(f"HTTP error: {exc.code} {exc.reason}")
            try:
                print(exc.read().decode("utf-8"))
            except Exception:
                pass
            continue
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"Request failed: {exc}")
            continue

        summary = result.get("summary", {})
        print(
            f"summary: valid={summary.get('valid')} errors={summary.get('error_count')} warnings={summary.get('warning_count')} total={summary.get('total_issues')}"
        )
        errors = validate_case_result(case, result)
        if errors:
            failures += 1
            print("status: FAILED")
            for error in errors:
                print(f"  - {error}")
            print("  issue codes:", ", ".join(sorted({issue.get('code', '') for issue in result.get('issues', [])})))
        else:
            print("status: PASSED")

    if failures:
        print(f"\nBusiness validation failed for {failures} case(s).")
        return 1

    print("\nAll fault-tree business validation cases passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))