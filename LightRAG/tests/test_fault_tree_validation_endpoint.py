from fastapi import FastAPI
from fastapi.testclient import TestClient
import asyncio
import json
import pytest
from types import SimpleNamespace

from lightrag.api.routers.fault_tree_validation_routes import (
    create_fault_tree_validation_routes,
)


app = FastAPI()
app.include_router(create_fault_tree_validation_routes(api_key=None))
client = TestClient(app)


class _FakeGraphStorage:
    def __init__(self, *, nodes=None, edges=None, aliases=None):
        self.nodes = nodes or {}
        self.edges = edges or {}
        self.aliases = aliases or {}

    async def get_node(self, node_id):
        return self.nodes.get(node_id)

    async def get_edge(self, source_node_id, target_node_id):
        return self.edges.get((source_node_id, target_node_id))

    async def search_labels(self, query, limit=10):
        return list(self.aliases.get(query, []))[:limit]


def _build_invalid_payload(**overrides):
    payload = {
        "nodes": [
            {"id": "top_1", "label": "顶事件A", "type": "top"},
            {"id": "top_2", "label": "顶事件B", "type": "top"},
            {"id": "basic_1", "label": "底事件A", "type": "basic"},
            {"id": "middle_1", "label": "中间事件A", "type": "middle"},
            {"id": "gate_1", "label": "OR门", "type": "gate", "gate": "OR"},
            {"id": "isolated_1", "label": "孤立事件", "type": "middle"},
        ],
        "edges": [
            {"id": "edge_1", "source": "top_1", "target": "basic_1"},
            {"id": "edge_2", "source": "basic_1", "target": "gate_1"},
            {"id": "edge_3", "source": "gate_1", "target": "top_1"},
            {"id": "edge_4", "source": "middle_1", "target": "missing_node"},
        ],
    }
    payload.update(overrides)
    return payload


@pytest.mark.offline
def test_fault_tree_validate_accepts_valid_fault_tree_payload():
    response = client.post(
        "/fault-tree/validate",
        json={
            "nodes": [
                {"id": "top_1", "label": "主泵失效", "type": "top"},
                {"id": "gate_1", "label": "OR门", "type": "gate", "gate": "OR"},
                {"id": "middle_1", "label": "供电异常", "type": "middle"},
                {"id": "basic_3", "label": "机械异常", "type": "basic"},
                {"id": "basic_1", "label": "线路短路", "type": "basic"},
                {"id": "basic_2", "label": "保险丝熔断", "type": "basic"},
                {"id": "gate_2", "label": "AND门", "type": "gate", "gate": "AND"},
            ],
            "edges": [
                {"id": "edge_1", "source": "top_1", "target": "gate_1"},
                {"id": "edge_2", "source": "gate_1", "target": "middle_1"},
                {"id": "edge_3", "source": "gate_1", "target": "basic_3"},
                {"id": "edge_4", "source": "middle_1", "target": "gate_2"},
                {"id": "edge_5", "source": "gate_2", "target": "basic_1"},
                {"id": "edge_6", "source": "gate_2", "target": "basic_2"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["valid"] is True
    assert payload["summary"]["error_count"] == 0
    assert payload["issues"] == []


@pytest.mark.offline
def test_fault_tree_validate_accepts_single_child_or_gate_as_valid():
    response = client.post(
        "/fault-tree/validate",
        json={
            "nodes": [
                {"id": "top_1", "label": "设备停机", "type": "top"},
                {"id": "gate_1", "label": "OR门", "type": "gate", "gate": "OR"},
                {"id": "basic_1", "label": "温度传感器信号丢失", "type": "basic"},
            ],
            "edges": [
                {"id": "edge_1", "source": "top_1", "target": "gate_1"},
                {"id": "edge_2", "source": "gate_1", "target": "basic_1"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    issue_codes = {issue["code"] for issue in payload["issues"]}

    assert payload["summary"]["valid"] is True
    assert "gate_with_single_input_path" not in issue_codes
    assert payload["issues"] == []


@pytest.mark.offline
def test_fault_tree_validate_reports_structure_hierarchy_and_logic_issues():
    response = client.post(
        "/fault-tree/validate",
        json=_build_invalid_payload(),
    )

    assert response.status_code == 200
    payload = response.json()
    issue_codes = {issue["code"] for issue in payload["issues"]}

    assert payload["summary"]["valid"] is False
    assert payload["summary"]["error_count"] >= 1
    assert "multiple_top_events" in issue_codes
    assert "event_to_event_connection" in issue_codes
    assert "missing_edge_endpoint" in issue_codes
    assert "isolated_node" in issue_codes
    assert "cycle_detected" in issue_codes


@pytest.mark.offline
def test_fault_tree_validate_enhances_suggestions_with_llm_when_available():
    async def fake_llm_model_func(*args, **kwargs):
        request_payload = json.loads(args[0])
        suggestions = []
        for issue in request_payload["issues"]:
            suggestion = f"请优先处理问题 {issue['code']}。"
            if issue["code"] == "multiple_top_events":
                suggestion = "请先删除重复顶事件，仅保留一个根节点，再把其余顶事件改为中间事件。"
            suggestions.append({"index": issue["index"], "suggestion": suggestion})
        return json.dumps({"suggestions": suggestions}, ensure_ascii=False)

    suggestion_app = FastAPI()
    suggestion_app.include_router(
        create_fault_tree_validation_routes(
            api_key=None,
            rag=SimpleNamespace(llm_model_func=fake_llm_model_func, llm_model_kwargs={}),
        )
    )
    suggestion_client = TestClient(suggestion_app)

    response = suggestion_client.post(
        "/fault-tree/validate",
        json={
            **_build_invalid_payload(),
            "enable_llm_suggestions": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    enhanced_issue = next(issue for issue in payload["issues"] if issue["code"] == "multiple_top_events")
    assert enhanced_issue["suggestion_source"] == "llm"
    assert "仅保留一个根节点" in enhanced_issue["suggestion"]


@pytest.mark.offline
def test_fault_tree_validate_falls_back_to_rule_suggestions_when_llm_generation_fails():
    async def failing_llm_model_func(*args, **kwargs):
        raise RuntimeError("llm unavailable")

    fallback_app = FastAPI()
    fallback_app.include_router(
        create_fault_tree_validation_routes(
            api_key=None,
            rag=SimpleNamespace(llm_model_func=failing_llm_model_func, llm_model_kwargs={}),
        )
    )
    fallback_client = TestClient(fallback_app)

    response = fallback_client.post(
        "/fault-tree/validate",
        json={
            **_build_invalid_payload(),
            "enable_llm_suggestions": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    fallback_issue = next(issue for issue in payload["issues"] if issue["code"] == "multiple_top_events")
    assert fallback_issue["suggestion_source"] == "rule"
    assert "请保留一个顶事件作为根节点" in fallback_issue["suggestion"]


@pytest.mark.offline
def test_fault_tree_validate_appends_kg_warnings_when_enabled():
    kg_app = FastAPI()
    kg_app.include_router(
        create_fault_tree_validation_routes(
            api_key=None,
            rag=SimpleNamespace(
                chunk_entity_relation_graph=_FakeGraphStorage(
                    nodes={
                        "主泵失效": {"entity_type": "TopEvent"},
                        "线路短路": {"entity_type": "BasicEvent"},
                    },
                    edges={
                        ("主泵失效", "线路短路"): {"keywords": "resultsIn"},
                    },
                ),
                llm_model_func=None,
                llm_model_kwargs={},
            ),
        )
    )
    kg_client = TestClient(kg_app)

    response = kg_client.post(
        "/fault-tree/validate",
        json={
            "nodes": [
                {"id": "top_1", "label": "主泵失效", "type": "top"},
                {"id": "gate_1", "label": "OR门", "type": "gate", "gate": "OR"},
                {"id": "basic_1", "label": "线路短路", "type": "basic"},
            ],
            "edges": [
                {"id": "edge_1", "source": "top_1", "target": "gate_1"},
                {"id": "edge_2", "source": "gate_1", "target": "basic_1"},
            ],
            "enable_kg_validation": True,
            "enable_llm_suggestions": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    kg_issue = next(issue for issue in payload["issues"] if issue["code"] == "kg_edge_direction_conflict")
    assert kg_issue["category"] == "knowledge_graph_consistency"
    assert kg_issue["severity"] == "warning"
    assert "图谱中存在 主泵失效 -> 线路短路" in kg_issue["evidence"]


@pytest.mark.offline
def test_fault_tree_validate_keeps_rule_result_when_kg_is_unavailable():
    response = client.post(
        "/fault-tree/validate",
        json={
            "nodes": [
                {"id": "top_1", "label": "主泵失效", "type": "top"},
                {"id": "gate_1", "label": "OR门", "type": "gate", "gate": "OR"},
                {"id": "basic_1", "label": "线路短路", "type": "basic"},
            ],
            "edges": [
                {"id": "edge_1", "source": "top_1", "target": "gate_1"},
                {"id": "edge_2", "source": "gate_1", "target": "basic_1"},
            ],
            "enable_kg_validation": True,
            "enable_llm_suggestions": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["valid"] is True
    assert payload["issues"] == []


@pytest.mark.offline
def test_fault_tree_validate_prefers_entity_reference_for_kg_matching():
    kg_app = FastAPI()
    kg_app.include_router(
        create_fault_tree_validation_routes(
            api_key=None,
            rag=SimpleNamespace(
                chunk_entity_relation_graph=_FakeGraphStorage(
                    nodes={
                        "kg://top-event/main-pump": {"entity_type": "TopEvent"},
                        "kg://event/short-circuit": {"entity_type": "BasicEvent"},
                    },
                    edges={
                        ("kg://event/short-circuit", "kg://top-event/main-pump"): {"keywords": "resultsIn"},
                    },
                ),
                llm_model_func=None,
                llm_model_kwargs={},
            ),
        )
    )
    kg_client = TestClient(kg_app)

    response = kg_client.post(
        "/fault-tree/validate",
        json={
            "nodes": [
                {
                    "id": "top_1",
                    "label": "主泵故障展示名",
                    "type": "top",
                    "entity_reference": "kg://top-event/main-pump",
                },
                {"id": "gate_1", "label": "OR门", "type": "gate", "gate": "OR"},
                {
                    "id": "basic_1",
                    "label": "线路短路展示名",
                    "type": "basic",
                    "entity_reference": "kg://event/short-circuit",
                },
            ],
            "edges": [
                {"id": "edge_1", "source": "top_1", "target": "gate_1"},
                {"id": "edge_2", "source": "gate_1", "target": "basic_1"},
            ],
            "enable_kg_validation": True,
            "kg_validation_mode": "entity_reference",
            "enable_llm_suggestions": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    issue_codes = {issue["code"] for issue in payload["issues"]}

    assert payload["summary"]["valid"] is True
    assert "kg_node_unmatched" not in issue_codes
    assert "kg_edge_missing_evidence" not in issue_codes
    assert payload["issues"] == []


@pytest.mark.offline
def test_fault_tree_validate_entity_reference_overrides_misleading_label_match():
    kg_app = FastAPI()
    kg_app.include_router(
        create_fault_tree_validation_routes(
            api_key=None,
            rag=SimpleNamespace(
                chunk_entity_relation_graph=_FakeGraphStorage(
                    nodes={
                        "错误顶事件": {"entity_type": "TopEvent"},
                        "错误底事件": {"entity_type": "BasicEvent"},
                        "kg://top-event/main-pump": {"entity_type": "TopEvent"},
                        "kg://event/short-circuit": {"entity_type": "BasicEvent"},
                    },
                    edges={
                        ("错误顶事件", "错误底事件"): {"keywords": "resultsIn"},
                        ("kg://event/short-circuit", "kg://top-event/main-pump"): {"keywords": "resultsIn"},
                    },
                ),
                llm_model_func=None,
                llm_model_kwargs={},
            ),
        )
    )
    kg_client = TestClient(kg_app)

    response = kg_client.post(
        "/fault-tree/validate",
        json={
            "nodes": [
                {
                    "id": "top_1",
                    "label": "错误顶事件",
                    "type": "top",
                    "entity_reference": "kg://top-event/main-pump",
                },
                {"id": "gate_1", "label": "OR门", "type": "gate", "gate": "OR"},
                {
                    "id": "basic_1",
                    "label": "错误底事件",
                    "type": "basic",
                    "entity_reference": "kg://event/short-circuit",
                },
            ],
            "edges": [
                {"id": "edge_1", "source": "top_1", "target": "gate_1"},
                {"id": "edge_2", "source": "gate_1", "target": "basic_1"},
            ],
            "enable_kg_validation": True,
            "kg_validation_mode": "entity_reference",
            "enable_llm_suggestions": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    issue_codes = {issue["code"] for issue in payload["issues"]}

    assert payload["summary"]["valid"] is True
    assert "kg_edge_direction_conflict" not in issue_codes
    assert "kg_edge_missing_evidence" not in issue_codes
    assert payload["issues"] == []


@pytest.mark.offline
def test_fault_tree_validate_label_mode_prefers_label_over_entity_reference():
    kg_app = FastAPI()
    kg_app.include_router(
        create_fault_tree_validation_routes(
            api_key=None,
            rag=SimpleNamespace(
                chunk_entity_relation_graph=_FakeGraphStorage(
                    nodes={
                        "错误顶事件": {"entity_type": "TopEvent"},
                        "错误底事件": {"entity_type": "BasicEvent"},
                        "kg://top-event/main-pump": {"entity_type": "TopEvent"},
                        "kg://event/short-circuit": {"entity_type": "BasicEvent"},
                    },
                    edges={
                        ("错误顶事件", "错误底事件"): {"keywords": "resultsIn"},
                        ("kg://event/short-circuit", "kg://top-event/main-pump"): {"keywords": "resultsIn"},
                    },
                ),
                llm_model_func=None,
                llm_model_kwargs={},
            ),
        )
    )
    kg_client = TestClient(kg_app)

    response = kg_client.post(
        "/fault-tree/validate",
        json={
            "nodes": [
                {
                    "id": "top_1",
                    "label": "错误顶事件",
                    "type": "top",
                    "entity_reference": "kg://top-event/main-pump",
                },
                {"id": "gate_1", "label": "OR门", "type": "gate", "gate": "OR"},
                {
                    "id": "basic_1",
                    "label": "错误底事件",
                    "type": "basic",
                    "entity_reference": "kg://event/short-circuit",
                },
            ],
            "edges": [
                {"id": "edge_1", "source": "top_1", "target": "gate_1"},
                {"id": "edge_2", "source": "gate_1", "target": "basic_1"},
            ],
            "enable_kg_validation": True,
            "kg_validation_mode": "label",
            "enable_llm_suggestions": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    issue_codes = {issue["code"] for issue in payload["issues"]}

    assert payload["summary"]["valid"] is True
    assert "kg_edge_direction_conflict" in issue_codes


@pytest.mark.offline
def test_fault_tree_validate_llm_timeout_falls_back_to_rule_suggestions():
    """When the LLM takes longer than llm_suggestion_timeout, issues should keep rule-based suggestions."""

    async def slow_llm_model_func(*args, **kwargs):
        await asyncio.sleep(60)  # simulate a very slow LLM
        return json.dumps({"suggestions": []})

    timeout_app = FastAPI()
    timeout_app.include_router(
        create_fault_tree_validation_routes(
            api_key=None,
            rag=SimpleNamespace(llm_model_func=slow_llm_model_func, llm_model_kwargs={}),
        )
    )
    timeout_client = TestClient(timeout_app)

    response = timeout_client.post(
        "/fault-tree/validate",
        json={
            **_build_invalid_payload(),
            "enable_llm_suggestions": True,
            "llm_suggestion_timeout": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["valid"] is False
    for issue in payload["issues"]:
        assert issue["suggestion_source"] == "rule"


@pytest.mark.offline
def test_fault_tree_validate_llm_batches_issues_independently():
    """Multiple batches should be processed; a failure in one batch should not affect others."""

    call_count = 0

    async def batch_sensitive_llm_func(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        request_payload = json.loads(args[0])
        issues = request_payload["issues"]
        # Fail for any batch containing issue index 0
        if any(issue["index"] == 0 for issue in issues):
            raise RuntimeError("simulated LLM failure for first batch")
        suggestions = [
            {"index": issue["index"], "suggestion": f"LLM建议-{issue['index']}"}
            for issue in issues
        ]
        return json.dumps({"suggestions": suggestions}, ensure_ascii=False)

    batch_app = FastAPI()
    batch_app.include_router(
        create_fault_tree_validation_routes(
            api_key=None,
            rag=SimpleNamespace(llm_model_func=batch_sensitive_llm_func, llm_model_kwargs={}),
        )
    )
    batch_client = TestClient(batch_app)

    response = batch_client.post(
        "/fault-tree/validate",
        json={
            **_build_invalid_payload(),
            "enable_llm_suggestions": True,
            "llm_suggestion_batch_size": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert call_count >= 2, "LLM should have been called multiple times for batched issues"

    # The first issue (index 0) should fall back to rule because its batch failed.
    first_issue = payload["issues"][0]
    assert first_issue["suggestion_source"] == "rule"

    # Later issues in non-failing batches should have LLM suggestions.
    llm_issues = [issue for issue in payload["issues"] if issue["suggestion_source"] == "llm"]
    assert len(llm_issues) > 0, "At least some issues should have LLM suggestions from successful batches"