import asyncio
import inspect
import json
import re
from collections import Counter, defaultdict, deque
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator

from ..utils_api import get_combined_auth_dependency
from lightrag.utils import logger


NodeType = Literal["top", "middle", "basic", "gate"]
GateType = Literal["AND", "OR"]
KgValidationMode = Literal["label", "entity_reference"]
IssueCategory = Literal[
    "structure_integrity",
    "hierarchy_reasonableness",
    "logical_relation_conformity",
    "knowledge_graph_consistency",
]
IssueSeverity = Literal["error", "warning"]

EVENT_NODE_TYPES = {"top", "middle", "basic"}
EVENT_TYPE_RANK = {"top": 2, "middle": 1, "basic": 0}


class FaultTreeNodePayload(BaseModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    type: NodeType
    gate: Optional[GateType] = None
    entity_reference: Optional[str] = Field(
        default=None,
        description="Optional KG entity identifier that should be preferred over label matching.",
    )

    @model_validator(mode="after")
    def validate_gate_type(self):
        if self.type == "gate" and self.gate is None:
            raise ValueError("Gate nodes must provide gate type")
        if self.type != "gate" and self.gate is not None:
            raise ValueError("Only gate nodes can provide gate type")
        return self


class FaultTreeEdgePayload(BaseModel):
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)


class FaultTreeValidationRequest(BaseModel):
    nodes: list[FaultTreeNodePayload] = Field(default_factory=list)
    edges: list[FaultTreeEdgePayload] = Field(default_factory=list)
    enable_kg_validation: bool = Field(
        default=False,
        description="Whether to validate event logic against the current workspace knowledge graph.",
    )
    kg_validation_mode: KgValidationMode = Field(
        default="label",
        description="Preferred KG matching strategy for fault-tree nodes.",
    )
    enable_llm_suggestions: bool = Field(
        default=True,
        description="Whether to enrich rule-based suggestions with LLM phrasing when an LLM is configured.",
    )
    llm_suggestion_timeout: float = Field(
        default=30.0,
        ge=5.0,
        le=300.0,
        description="Per-batch timeout in seconds for LLM suggestion enhancement. "
        "If a batch exceeds this limit, its issues fall back to rule-based suggestions.",
    )
    llm_suggestion_batch_size: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Number of issues per LLM suggestion batch. "
        "Smaller batches enable parallel processing and reduce per-call latency.",
    )


class FaultTreeValidationIssue(BaseModel):
    category: IssueCategory
    code: str
    severity: IssueSeverity
    message: str
    suggestion: str
    evidence: Optional[str] = None
    suggestion_source: Literal["rule", "llm"] = "rule"
    node_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)


class FaultTreeValidationSummary(BaseModel):
    valid: bool
    total_issues: int
    error_count: int
    warning_count: int
    category_counts: dict[str, int]


class FaultTreeValidationResponse(BaseModel):
    summary: FaultTreeValidationSummary
    issues: list[FaultTreeValidationIssue]


def _make_issue(
    category: IssueCategory,
    code: str,
    severity: IssueSeverity,
    message: str,
    suggestion: str,
    *,
    evidence: Optional[str] = None,
    node_ids: Optional[list[str]] = None,
    edge_ids: Optional[list[str]] = None,
) -> FaultTreeValidationIssue:
    return FaultTreeValidationIssue(
        category=category,
        code=code,
        severity=severity,
        message=message,
        suggestion=suggestion,
        evidence=evidence,
        suggestion_source="rule",
        node_ids=node_ids or [],
        edge_ids=edge_ids or [],
    )


def _extract_workspace_from_request(http_request: Request | None) -> str | None:
    if http_request is None:
        return None

    workspace = http_request.headers.get("LIGHTRAG-WORKSPACE", "").strip()
    if not workspace:
        return None

    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", workspace)
    if sanitized != workspace:
        logger.warning(
            "Workspace header '%s' contains invalid characters. Sanitized to '%s'.",
            workspace,
            sanitized,
        )
    return sanitized


async def _get_rag_for_request(rag, get_rag_by_workspace, http_request: Request | None):
    if get_rag_by_workspace is None:
        return rag

    workspace = _extract_workspace_from_request(http_request)
    resolved = get_rag_by_workspace(workspace)
    if inspect.isawaitable(resolved):
        return await resolved
    return resolved


def _extract_first_json_object(raw_text: str) -> dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("LLM returned empty content")

    decoder = json.JSONDecoder()
    direct_candidates = [text]
    direct_candidates.extend(
        block.strip()
        for block in re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
        if block.strip()
    )

    for candidate in direct_candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("No valid JSON object found in LLM response")


def _build_issue_context(
    payload: FaultTreeValidationRequest,
    issue: FaultTreeValidationIssue,
) -> dict[str, Any]:
    node_map = {node.id: node for node in payload.nodes}
    edge_map = {edge.id: edge for edge in payload.edges}

    nodes = []
    for node_id in issue.node_ids:
        node = node_map.get(node_id)
        if node is None:
            nodes.append({"id": node_id, "label": node_id, "type": "unknown"})
            continue
        entry = {
            "id": node.id,
            "label": node.label,
            "type": node.type,
        }
        if node.gate is not None:
            entry["gate"] = node.gate
        nodes.append(entry)

    edges = []
    for edge_id in issue.edge_ids:
        edge = edge_map.get(edge_id)
        if edge is None:
            edges.append({"id": edge_id})
            continue
        source_node = node_map.get(edge.source)
        target_node = node_map.get(edge.target)
        edges.append(
            {
                "id": edge.id,
                "source": edge.source,
                "source_label": source_node.label if source_node else edge.source,
                "target": edge.target,
                "target_label": target_node.label if target_node else edge.target,
            }
        )

    return {
        "category": issue.category,
        "code": issue.code,
        "severity": issue.severity,
        "message": issue.message,
        "current_suggestion": issue.suggestion,
        "evidence": issue.evidence,
        "nodes": nodes,
        "edges": edges,
    }


def _build_validation_response(
    issues: list[FaultTreeValidationIssue],
) -> FaultTreeValidationResponse:
    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    category_counts = Counter(issue.category for issue in issues)
    summary = FaultTreeValidationSummary(
        valid=error_count == 0,
        total_issues=len(issues),
        error_count=error_count,
        warning_count=warning_count,
        category_counts=dict(category_counts),
    )
    return FaultTreeValidationResponse(summary=summary, issues=issues)


def _merge_validation_issues(
    response: FaultTreeValidationResponse,
    issues: list[FaultTreeValidationIssue],
) -> FaultTreeValidationResponse:
    if not issues:
        return response
    return _build_validation_response([*response.issues, *issues])


def _normalize_match_key(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def _extract_graph_relation(raw_keywords: Any) -> str | None:
    if isinstance(raw_keywords, list):
        raw_keywords = ",".join(str(item) for item in raw_keywords if item)

    if not isinstance(raw_keywords, str) or not raw_keywords.strip():
        return None

    for candidate in raw_keywords.split(","):
        keyword = candidate.strip()
        if keyword in {"resultsIn", "jointly_resultsIn"}:
            return keyword
        lowered = keyword.lower()
        if lowered == "resultsin":
            return "resultsIn"
        if lowered == "jointly_resultsin":
            return "jointly_resultsIn"

    return None


async def _resolve_kg_node_identifier(
    kg,
    node: FaultTreeNodePayload,
    *,
    prefer_entity_reference: bool,
) -> tuple[str | None, str | None]:
    candidates: list[str] = []
    if prefer_entity_reference and node.entity_reference:
        candidates.append(node.entity_reference)
    candidates.append(node.label)
    if not prefer_entity_reference and node.entity_reference:
        candidates.append(node.entity_reference)

    seen: set[str] = set()
    for candidate in candidates:
        normalized_candidate = str(candidate or "").strip()
        if not normalized_candidate or normalized_candidate in seen:
            continue
        seen.add(normalized_candidate)
        if await kg.get_node(normalized_candidate):
            return normalized_candidate, None

    search_term = node.entity_reference if prefer_entity_reference and node.entity_reference else node.label
    if not search_term:
        return None, "缺少可用于匹配知识图谱的名称或实体引用。"

    matches = await kg.search_labels(search_term, limit=10)
    normalized_search_term = _normalize_match_key(search_term)
    for match in matches:
        if _normalize_match_key(match) == normalized_search_term:
            return match, None

    return None, f"知识图谱中未找到与“{search_term}”一致的实体。"


async def _validate_fault_tree_with_kg(
    payload: FaultTreeValidationRequest,
    rag,
) -> list[FaultTreeValidationIssue]:
    kg = getattr(rag, "chunk_entity_relation_graph", None) if rag is not None else None
    if kg is None or not payload.nodes:
        return []

    node_map = {node.id: node for node in payload.nodes}
    outgoing: dict[str, list[FaultTreeEdgePayload]] = defaultdict(list)
    for edge in payload.edges:
        if edge.source in node_map and edge.target in node_map:
            outgoing[edge.source].append(edge)

    prefer_entity_reference = payload.kg_validation_mode == "entity_reference"
    issues: list[FaultTreeValidationIssue] = []
    resolved_nodes: dict[str, str] = {}

    for node in payload.nodes:
        if node.type == "gate":
            continue
        matched_identifier, failure_reason = await _resolve_kg_node_identifier(
            kg,
            node,
            prefer_entity_reference=prefer_entity_reference,
        )
        if matched_identifier is None:
            issues.append(
                _make_issue(
                    "knowledge_graph_consistency",
                    "kg_node_unmatched",
                    "warning",
                    f"节点 {node.label} 未在知识图谱中匹配到对应实体。",
                    "请核对节点名称或补充 entity_reference，确保故障树节点能映射到知识图谱实体。",
                    evidence=failure_reason,
                    node_ids=[node.id],
                )
            )
            continue
        resolved_nodes[node.id] = matched_identifier

    for node in payload.nodes:
        if node.type == "gate":
            continue

        parent_kg_id = resolved_nodes.get(node.id)
        if not parent_kg_id:
            continue

        for gate_edge in outgoing.get(node.id, []):
            gate_node = node_map.get(gate_edge.target)
            if gate_node is None or gate_node.type != "gate":
                continue

            child_edges = [edge for edge in outgoing.get(gate_node.id, []) if node_map.get(edge.target) is not None and node_map[edge.target].type != "gate"]
            if not child_edges:
                continue

            expected_relation = "jointly_resultsIn" if gate_node.gate == "AND" else "resultsIn"
            for child_edge in child_edges:
                child_node = node_map[child_edge.target]
                child_kg_id = resolved_nodes.get(child_node.id)
                if not child_kg_id:
                    continue

                forward_edge = await kg.get_edge(child_kg_id, parent_kg_id)
                reverse_edge = await kg.get_edge(parent_kg_id, child_kg_id)
                forward_relation = _extract_graph_relation((forward_edge or {}).get("keywords"))
                reverse_relation = _extract_graph_relation((reverse_edge or {}).get("keywords"))
                related_edge_ids = [gate_edge.id, child_edge.id]
                related_node_ids = [node.id, gate_node.id, child_node.id]

                if forward_relation == expected_relation:
                    continue

                if reverse_relation is not None:
                    issues.append(
                        _make_issue(
                            "knowledge_graph_consistency",
                            "kg_edge_direction_conflict",
                            "warning",
                            f"知识图谱显示 {child_node.label} 与 {node.label} 的因果方向与当前故障树相反。",
                            "请核对该子事件是否应作为父事件的原因，必要时调整故障树方向或补充领域证据。",
                            evidence=f"图谱中存在 {parent_kg_id} -> {child_kg_id} 的 {reverse_relation} 关系，但未找到期望的 {child_kg_id} -> {parent_kg_id} {expected_relation} 关系。",
                            node_ids=related_node_ids,
                            edge_ids=related_edge_ids,
                        )
                    )
                    continue

                if forward_relation is None:
                    issues.append(
                        _make_issue(
                            "knowledge_graph_consistency",
                            "kg_edge_missing_evidence",
                            "warning",
                            f"知识图谱中未找到 {child_node.label} 导致 {node.label} 的直接依据。",
                            "请核对该因果链是否有图谱依据，或补充对应知识后再复核。",
                            evidence=f"未命中 {child_kg_id} -> {parent_kg_id} 的 {expected_relation} 关系。",
                            node_ids=related_node_ids,
                            edge_ids=related_edge_ids,
                        )
                    )
                    continue

                issues.append(
                    _make_issue(
                        "knowledge_graph_consistency",
                        "kg_edge_relation_mismatch",
                        "warning",
                        f"知识图谱中 {child_node.label} 到 {node.label} 的关系类型与当前逻辑门不一致。",
                        "请检查该逻辑门类型是否正确，或核对知识图谱中的关系抽取结果。",
                        evidence=f"命中 {child_kg_id} -> {parent_kg_id} 关系，但图谱关系为 {forward_relation}，期望为 {expected_relation}。",
                        node_ids=related_node_ids,
                        edge_ids=related_edge_ids,
                    )
                )

    return issues


_LLM_SUGGESTION_SYSTEM_PROMPT = (
    "你是故障树校验助手。规则已经判定了问题是否存在，你只能为每个问题生成更自然、"
    "更可执行的中文修改建议。"
)

_LLM_SUGGESTION_INSTRUCTIONS = [
    "你只负责改写已确认存在的问题建议，不要重新判断问题是否成立。",
    "每条建议控制在1到2句话，直接给出修改动作，避免泛泛而谈。",
    "必须保留原始问题的语义边界，不要引入新问题或新节点。",
    "只返回一个 JSON 对象，不要输出 Markdown。",
]


async def _llm_suggest_batch(
    llm_func,
    llm_kwargs: dict[str, Any],
    payload: FaultTreeValidationRequest,
    batch: list[tuple[int, FaultTreeValidationIssue]],
    timeout: float,
) -> dict[int, str]:
    """Call the LLM for a small batch of issues and return {global_index: suggestion}."""
    prompt_payload = {
        "instructions": _LLM_SUGGESTION_INSTRUCTIONS,
        "issues": [
            {"index": global_index, **_build_issue_context(payload, issue)}
            for global_index, issue in batch
        ],
        "response_schema": {
            "suggestions": [{"index": 0, "suggestion": "string"}]
        },
    }
    raw_response = await asyncio.wait_for(
        llm_func(
            json.dumps(prompt_payload, ensure_ascii=False),
            system_prompt=_LLM_SUGGESTION_SYSTEM_PROMPT,
            **llm_kwargs,
        ),
        timeout=timeout,
    )
    parsed = _extract_first_json_object(str(raw_response))
    suggestions = parsed.get("suggestions") if isinstance(parsed, dict) else None
    if not isinstance(suggestions, list):
        return {}

    result: dict[int, str] = {}
    valid_indices = {global_index for global_index, _ in batch}
    for entry in suggestions:
        if not isinstance(entry, dict):
            continue
        index = entry.get("index")
        suggestion = str(entry.get("suggestion") or "").strip()
        if isinstance(index, int) and suggestion and index in valid_indices:
            result[index] = suggestion
    return result


async def _enhance_issue_suggestions_with_llm(
    payload: FaultTreeValidationRequest,
    response: FaultTreeValidationResponse,
    rag,
) -> FaultTreeValidationResponse:
    if not response.issues:
        return response

    llm_func = getattr(rag, "llm_model_func", None) if rag is not None else None
    if llm_func is None:
        return response

    llm_kwargs = dict(getattr(rag, "llm_model_kwargs", {}) or {})
    llm_kwargs.pop("response_format", None)
    llm_kwargs.setdefault("stream", False)

    batch_size = payload.llm_suggestion_batch_size
    timeout = payload.llm_suggestion_timeout
    indexed_issues = list(enumerate(response.issues))

    batches = [
        indexed_issues[i : i + batch_size]
        for i in range(0, len(indexed_issues), batch_size)
    ]

    async def _safe_batch(batch: list[tuple[int, FaultTreeValidationIssue]]) -> dict[int, str]:
        try:
            return await _llm_suggest_batch(llm_func, llm_kwargs, payload, batch, timeout)
        except asyncio.TimeoutError:
            indices = [str(idx) for idx, _ in batch]
            logger.warning(
                "LLM suggestion batch timed out after %.1fs for issue indices [%s], falling back to rule-based.",
                timeout,
                ", ".join(indices),
            )
            return {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM suggestion batch failed: %s", exc)
            return {}

    batch_results = await asyncio.gather(*[_safe_batch(batch) for batch in batches])

    suggestion_map: dict[int, str] = {}
    for partial in batch_results:
        suggestion_map.update(partial)

    if not suggestion_map:
        return response

    enhanced_issues = []
    for index, issue in enumerate(response.issues):
        suggestion = suggestion_map.get(index)
        if suggestion:
            enhanced_issues.append(
                issue.model_copy(
                    update={
                        "suggestion": suggestion,
                        "suggestion_source": "llm",
                    }
                )
            )
        else:
            enhanced_issues.append(issue)
    return response.model_copy(update={"issues": enhanced_issues})


def _validate_fault_tree(payload: FaultTreeValidationRequest) -> FaultTreeValidationResponse:
    issues: list[FaultTreeValidationIssue] = []
    node_map = {node.id: node for node in payload.nodes}
    outgoing: dict[str, list[FaultTreeEdgePayload]] = defaultdict(list)
    incoming: dict[str, list[FaultTreeEdgePayload]] = defaultdict(list)
    pair_counts: Counter[tuple[str, str]] = Counter()

    node_id_counts = Counter(node.id for node in payload.nodes)
    duplicate_node_ids = sorted(node_id for node_id, count in node_id_counts.items() if count > 1)
    if duplicate_node_ids:
        issues.append(
            _make_issue(
                "structure_integrity",
                "duplicate_node_ids",
                "error",
                f"存在重复节点 ID: {', '.join(duplicate_node_ids)}。",
                "请确保每个节点使用唯一 ID，避免校验与标注结果错位。",
                node_ids=duplicate_node_ids,
            )
        )

    edge_id_counts = Counter(edge.id for edge in payload.edges)
    duplicate_edge_ids = sorted(edge_id for edge_id, count in edge_id_counts.items() if count > 1)
    if duplicate_edge_ids:
        issues.append(
            _make_issue(
                "structure_integrity",
                "duplicate_edge_ids",
                "error",
                f"存在重复连线 ID: {', '.join(duplicate_edge_ids)}。",
                "请确保每条连线使用唯一 ID，避免后续问题定位冲突。",
                edge_ids=duplicate_edge_ids,
            )
        )

    for edge in payload.edges:
        pair_counts[(edge.source, edge.target)] += 1
        source_node = node_map.get(edge.source)
        target_node = node_map.get(edge.target)

        if source_node is None or target_node is None:
            missing = []
            if source_node is None:
                missing.append(f"source={edge.source}")
            if target_node is None:
                missing.append(f"target={edge.target}")
            issues.append(
                _make_issue(
                    "structure_integrity",
                    "missing_edge_endpoint",
                    "error",
                    f"连线 {edge.id} 引用了不存在的节点: {', '.join(missing)}。",
                    "请修复缺失节点或删除这条断裂连线。",
                    edge_ids=[edge.id],
                    node_ids=[value.split("=", 1)[1] for value in missing],
                )
            )
            continue

        outgoing[edge.source].append(edge)
        incoming[edge.target].append(edge)

        if edge.source == edge.target:
            issues.append(
                _make_issue(
                    "logical_relation_conformity",
                    "self_loop",
                    "error",
                    f"连线 {edge.id} 构成了节点 {edge.source} 的自环。",
                    "请删除自环，并重新连接到真实的上下游节点。",
                    node_ids=[edge.source],
                    edge_ids=[edge.id],
                )
            )

    duplicate_pairs = [pair for pair, count in pair_counts.items() if count > 1]
    for source_id, target_id in duplicate_pairs:
        duplicated_edges = [
            edge.id
            for edge in payload.edges
            if edge.source == source_id and edge.target == target_id
        ]
        issues.append(
            _make_issue(
                "logical_relation_conformity",
                "duplicate_edge_pair",
                "error",
                f"节点 {source_id} 到 {target_id} 存在重复连线。",
                "请保留单条有效连线，删除其余重复连接。",
                node_ids=[source_id, target_id],
                edge_ids=duplicated_edges,
            )
        )

    if not payload.nodes:
        issues.append(
            _make_issue(
                "structure_integrity",
                "empty_tree",
                "error",
                "当前故障树为空，无法执行结构校验。",
                "请先生成或录入至少一个顶事件及其下游结构。",
            )
        )
    else:
        top_nodes = [node for node in payload.nodes if node.type == "top"]
        if not top_nodes:
            issues.append(
                _make_issue(
                    "hierarchy_reasonableness",
                    "missing_top_event",
                    "error",
                    "故障树缺少顶事件。",
                    "请明确唯一的顶事件，并将其设置为 top 类型。",
                )
            )
        elif len(top_nodes) > 1:
            issues.append(
                _make_issue(
                    "hierarchy_reasonableness",
                    "multiple_top_events",
                    "error",
                    "故障树存在多个顶事件，层级起点不唯一。",
                    "请保留一个顶事件作为根节点，其余节点调整为中间事件或拆分为独立树。",
                    node_ids=[node.id for node in top_nodes],
                )
            )

    for node in payload.nodes:
        in_edges = incoming.get(node.id, [])
        out_edges = outgoing.get(node.id, [])
        degree = len(in_edges) + len(out_edges)

        if degree == 0:
            issues.append(
                _make_issue(
                    "structure_integrity",
                    "isolated_node",
                    "error",
                    f"节点 {node.label} 未与任何结构相连，属于孤立节点。",
                    "请为该节点补充正确的上下游连接，或删除无效孤立节点。",
                    node_ids=[node.id],
                )
            )

        if node.type == "top":
            if in_edges:
                issues.append(
                    _make_issue(
                        "hierarchy_reasonableness",
                        "top_event_has_parent",
                        "error",
                        f"顶事件 {node.label} 不应存在父级输入。",
                        "请移除指向顶事件的上游连线，确保其作为根节点。",
                        node_ids=[node.id],
                        edge_ids=[edge.id for edge in in_edges],
                    )
                )
            if not out_edges:
                issues.append(
                    _make_issue(
                        "structure_integrity",
                        "top_event_without_gate",
                        "error",
                        f"顶事件 {node.label} 下方缺少逻辑门或子事件结构。",
                        "请为顶事件补充分解逻辑门和下游故障事件。",
                        node_ids=[node.id],
                    )
                )
        elif node.type == "basic":
            if out_edges:
                issues.append(
                    _make_issue(
                        "hierarchy_reasonableness",
                        "basic_event_has_children",
                        "error",
                        f"底事件 {node.label} 不应继续向下分解。",
                        "请将该节点改为中间事件，或删除其向下的分解关系。",
                        node_ids=[node.id],
                        edge_ids=[edge.id for edge in out_edges],
                    )
                )
            if not in_edges:
                issues.append(
                    _make_issue(
                        "structure_integrity",
                        "basic_event_without_parent",
                        "warning",
                        f"底事件 {node.label} 缺少上游逻辑门输入。",
                        "请确认该底事件是否应挂接到某个逻辑门下，避免链路断裂。",
                        node_ids=[node.id],
                    )
                )
        elif node.type == "middle":
            if not in_edges:
                issues.append(
                    _make_issue(
                        "hierarchy_reasonableness",
                        "middle_event_without_parent",
                        "warning",
                        f"中间事件 {node.label} 缺少父级逻辑门输入。",
                        "请确认其上游逻辑，或将其调整为顶事件。",
                        node_ids=[node.id],
                    )
                )
            if not out_edges:
                issues.append(
                    _make_issue(
                        "hierarchy_reasonableness",
                        "middle_event_without_children",
                        "warning",
                        f"中间事件 {node.label} 未继续向下分解。",
                        "请确认其是否应改为底事件，或为其补充下游逻辑门。",
                        node_ids=[node.id],
                    )
                )
        else:
            if len(in_edges) != 1:
                issues.append(
                    _make_issue(
                        "logical_relation_conformity",
                        "gate_requires_single_parent_event",
                        "error",
                        f"逻辑门 {node.label} 应只对应一个上游事件。",
                        "请确保每个逻辑门只从一个事件向下展开，避免层级混乱。",
                        node_ids=[node.id],
                        edge_ids=[edge.id for edge in in_edges],
                    )
                )
            if len(out_edges) < 1:
                issues.append(
                    _make_issue(
                        "structure_integrity",
                        "gate_without_children",
                        "error",
                        f"逻辑门 {node.label} 未连接任何下游事件。",
                        "请为该逻辑门补充至少一个下游事件，避免链路断裂。",
                        node_ids=[node.id],
                    )
                )

    for edge in payload.edges:
        source_node = node_map.get(edge.source)
        target_node = node_map.get(edge.target)
        if source_node is None or target_node is None:
            continue

        if source_node.type == "gate" and target_node.type == "gate":
            issues.append(
                _make_issue(
                    "logical_relation_conformity",
                    "gate_to_gate_connection",
                    "error",
                    f"连线 {edge.id} 将逻辑门直接连接到逻辑门。",
                    "请在两个逻辑门之间补充事件节点，保持“事件-逻辑门-事件”的表达形式。",
                    node_ids=[source_node.id, target_node.id],
                    edge_ids=[edge.id],
                )
            )
            continue

        if source_node.type != "gate" and target_node.type != "gate":
            issues.append(
                _make_issue(
                    "logical_relation_conformity",
                    "event_to_event_connection",
                    "error",
                    f"连线 {edge.id} 将事件直接连接到事件。",
                    "请在事件之间插入逻辑门，再表达分解或归并关系。",
                    node_ids=[source_node.id, target_node.id],
                    edge_ids=[edge.id],
                )
            )
            continue

        if source_node.type != "gate" and target_node.type == "gate":
            if source_node.type == "basic":
                issues.append(
                    _make_issue(
                        "hierarchy_reasonableness",
                        "basic_event_feeds_gate",
                        "error",
                        f"底事件 {source_node.label} 不应继续向下连接逻辑门。",
                        "请将该节点改为中间事件，或移除其向下分解关系。",
                        node_ids=[source_node.id, target_node.id],
                        edge_ids=[edge.id],
                    )
                )
        if source_node.type == "gate" and target_node.type != "gate":
            if target_node.type == "top":
                issues.append(
                    _make_issue(
                        "hierarchy_reasonableness",
                        "top_event_as_gate_child",
                        "error",
                        f"顶事件 {target_node.label} 不应作为逻辑门的下游子事件。",
                        "请将顶事件放在树的根部，只允许其向下展开。",
                        node_ids=[source_node.id, target_node.id],
                        edge_ids=[edge.id],
                    )
                )

    # Project event-to-event hierarchy through event -> gate -> event chains.
    for node in payload.nodes:
        if node.type == "gate":
            continue

        for gate_edge in outgoing.get(node.id, []):
            gate_node = node_map.get(gate_edge.target)
            if gate_node is None or gate_node.type != "gate":
                continue
            for child_edge in outgoing.get(gate_node.id, []):
                child_node = node_map.get(child_edge.target)
                if child_node is None or child_node.type == "gate":
                    continue
                parent_rank = EVENT_TYPE_RANK[node.type]
                child_rank = EVENT_TYPE_RANK[child_node.type]
                if child_rank > parent_rank:
                    issues.append(
                        _make_issue(
                            "hierarchy_reasonableness",
                            "event_level_inversion",
                            "error",
                            f"事件 {node.label} 与 {child_node.label} 的层级方向存在倒置。",
                            "请确认父事件层级应高于或等于子事件，避免底事件指向顶事件的错位结构。",
                            node_ids=[node.id, gate_node.id, child_node.id],
                            edge_ids=[gate_edge.id, child_edge.id],
                        )
                    )

    # Directed cycle detection.
    indegree = {node.id: 0 for node in payload.nodes}
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in payload.edges:
        if edge.source not in node_map or edge.target not in node_map:
            continue
        adjacency[edge.source].append(edge.target)
        indegree[edge.target] = indegree.get(edge.target, 0) + 1

    queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for target_id in adjacency.get(current, []):
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                queue.append(target_id)

    if visited != len(indegree):
        cyclic_node_ids = sorted(node_id for node_id, degree in indegree.items() if degree > 0)
        issues.append(
            _make_issue(
                "logical_relation_conformity",
                "cycle_detected",
                "error",
                "故障树中存在闭环，因果链路不再是单向分解结构。",
                "请移除造成回路的连接，确保结构保持有向无环。",
                node_ids=cyclic_node_ids,
            )
        )

    # Reachability from unique top event.
    top_nodes = [node for node in payload.nodes if node.type == "top"]
    if len(top_nodes) == 1:
        root_id = top_nodes[0].id
        reachable = {root_id}
        queue = deque([root_id])
        while queue:
            current = queue.popleft()
            for target_id in adjacency.get(current, []):
                if target_id not in reachable:
                    reachable.add(target_id)
                    queue.append(target_id)
        unreachable_nodes = sorted(node.id for node in payload.nodes if node.id not in reachable)
        if unreachable_nodes:
            issues.append(
                _make_issue(
                    "structure_integrity",
                    "unreachable_subtree",
                    "warning",
                    "存在无法从顶事件遍历到的子树或节点。",
                    "请检查这些节点是否遗漏了与主树的连接，或应删除独立片段。",
                    node_ids=unreachable_nodes,
                )
            )

    return _build_validation_response(issues)


def create_fault_tree_validation_routes(
    api_key: Optional[str] = None,
    rag=None,
    get_rag_by_workspace=None,
):
    router = APIRouter(prefix="/fault-tree", tags=["fault-tree"])
    combined_auth = get_combined_auth_dependency(api_key)

    @router.post(
        "/validate",
        response_model=FaultTreeValidationResponse,
        dependencies=[Depends(combined_auth)],
    )
    async def validate_fault_tree(payload: FaultTreeValidationRequest, request: Request):
        response = _validate_fault_tree(payload)
        current_rag = None
        if payload.enable_kg_validation or payload.enable_llm_suggestions:
            current_rag = await _get_rag_for_request(rag, get_rag_by_workspace, request)

        if payload.enable_kg_validation:
            kg_issues = await _validate_fault_tree_with_kg(payload, current_rag)
            response = _merge_validation_issues(response, kg_issues)

        if not payload.enable_llm_suggestions:
            return response

        return await _enhance_issue_suggestions_with_llm(payload, response, current_rag)

    return router