import pytest

from scripts import run_fault_tree_validation_business_check as business_check
from scripts import run_fault_tree_validation_regression as regression


@pytest.mark.offline
def test_prepare_case_payload_disables_llm_suggestions_by_default_without_mutating_input():
    payload = {
        "enable_llm_suggestions": True,
        "nodes": [{"id": "top_1", "label": "主泵失效", "type": "top"}],
        "edges": [],
    }

    prepared = business_check.prepare_case_payload(
        payload,
        enable_llm_suggestions=False,
    )

    assert prepared is not payload
    assert prepared["enable_llm_suggestions"] is False
    assert payload["enable_llm_suggestions"] is True


@pytest.mark.offline
def test_prepare_case_payload_can_explicitly_enable_llm_suggestions():
    payload = {
        "enable_llm_suggestions": False,
        "nodes": [],
        "edges": [],
    }

    prepared = business_check.prepare_case_payload(
        payload,
        enable_llm_suggestions=True,
    )

    assert prepared["enable_llm_suggestions"] is True


@pytest.mark.offline
def test_regression_main_omits_llm_flag_from_business_check_by_default(monkeypatch):
    captured_steps = []

    def fake_run_step(title, command, cwd):
        captured_steps.append((title, command, cwd))

    monkeypatch.setattr(regression, "run_step", fake_run_step)

    exit_code = regression.main(["--with-business-check"])

    assert exit_code == 0
    business_step = next(step for step in captured_steps if step[0] == "Live fault-tree business validation")
    assert "--include-llm-suggestions" not in business_step[1]


@pytest.mark.offline
def test_regression_main_passes_llm_flag_when_explicitly_requested(monkeypatch):
    captured_steps = []

    def fake_run_step(title, command, cwd):
        captured_steps.append((title, command, cwd))

    monkeypatch.setattr(regression, "run_step", fake_run_step)

    exit_code = regression.main([
        "--with-business-check",
        "--include-llm-suggestions",
    ])

    assert exit_code == 0
    business_step = next(step for step in captured_steps if step[0] == "Live fault-tree business validation")
    assert business_step[1][-1] == "--include-llm-suggestions"