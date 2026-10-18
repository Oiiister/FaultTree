"""故障树构建：知识图谱 → 故障树 payload，以及导出摘要与 JSON 提示词。"""

import json
import re
from collections import defaultdict, deque
from typing import Any

from lightrag.constants import GRAPH_FIELD_SEP


DEFAULT_FAULT_TREE_CONFIDENCE = 0.9
FAULT_TREE_SUBGRAPH_MAX_DEPTH = 20


FAULT_TREE_JSON_PROMPT = """You are generating a fault-tree triple dataset from retrieved context.

Return exactly one valid JSON object and nothing else.
Do not use Markdown code fences.
Do not add explanatory text before or after the JSON object.

The JSON object must follow this schema exactly:
{
  "triplets": [
    {
            "subject_name": "string",
            "subject_type": "BasicEvent | IntermediateEvent | TopEvent",
            "relation": "resultsIn | jointly_resultsIn",
            "object_name": "string",
            "object_type": "BasicEvent | IntermediateEvent | TopEvent",
            "confidence": 0.0,
            "source": "string"
    }
  ]
}

Rules:
1. Use only facts that are explicitly supported by the retrieved context.
2. triplets must contain only factual fault-tree style triples derived from the context.
3. If the context is insufficient, return {"triplets": []} instead of inventing facts.
4. subject_type and object_type must be one of: BasicEvent, IntermediateEvent, TopEvent.
5. relation must be one of: resultsIn, jointly_resultsIn.
6. confidence must be a number between 0 and 1.
7. source must be a short evidence statement grounded in the retrieved context.
8. The response language must match the user's query language.
"""


def _compose_fault_tree_user_prompt(extra_prompt: str | None) -> str:
    extra_prompt = (extra_prompt or "").strip()
    if not extra_prompt:
        return FAULT_TREE_JSON_PROMPT
    return f"{FAULT_TREE_JSON_PROMPT}\n\nAdditional user requirements:\n{extra_prompt}"


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


def _split_graph_field(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        values: list[str] = []
        for item in raw_value:
            values.extend(_split_graph_field(item))
        return values
    if not isinstance(raw_value, str):
        return []

    return [item.strip() for item in raw_value.split(GRAPH_FIELD_SEP) if item.strip()]


def _normalize_fault_tree_type(raw_type: Any, *, is_top_event: bool = False) -> str:
    if is_top_event:
        return "TopEvent"

    normalized = str(raw_type or "").replace(" ", "").strip().lower()
    mapping = {
        "basicevent": "BasicEvent",
        "intermediateevent": "IntermediateEvent",
        "topevent": "TopEvent",
        "other": "IntermediateEvent",
        "unknown": "IntermediateEvent",
    }
    return mapping.get(normalized, "IntermediateEvent")


def _extract_fault_tree_relation(raw_keywords: Any) -> str | None:
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


async def _resolve_fault_tree_top_event_label(rag, query: str) -> str | None:
    top_event = (query or "").strip()
    if not top_event:
        return None

    if await rag.chunk_entity_relation_graph.has_node(top_event):
        return top_event

    candidates = await rag.chunk_entity_relation_graph.search_labels(top_event, limit=10)
    if not candidates:
        return None

    normalized_query = " ".join(top_event.split()).casefold()
    for candidate in candidates:
        normalized_candidate = " ".join(candidate.split()).casefold()
        if normalized_candidate == normalized_query:
            return candidate

    return None


def _build_fault_tree_distance_map(top_event: str, edges: list[Any]) -> dict[str, int]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)

    distances: dict[str, int] = {top_event: 0}
    queue: deque[str] = deque([top_event])
    while queue:
        node = queue.popleft()
        for neighbor in adjacency.get(node, set()):
            if neighbor in distances:
                continue
            distances[neighbor] = distances[node] + 1
            queue.append(neighbor)

    return distances


def _orient_fault_tree_edge(
    edge: Any,
    top_event: str,
    distances: dict[str, int],
    node_types: dict[str, str],
) -> tuple[str, str]:
    source = edge.source
    target = edge.target
    source_distance = distances.get(source)
    target_distance = distances.get(target)

    if source_distance is not None and target_distance is not None and source_distance != target_distance:
        if source_distance < target_distance:
            return target, source
        return source, target

    if source == top_event:
        return target, source
    if target == top_event:
        return source, target

    priority = {"BasicEvent": 0, "IntermediateEvent": 1, "TopEvent": 2}
    source_type = _normalize_fault_tree_type(node_types.get(source), is_top_event=source == top_event)
    target_type = _normalize_fault_tree_type(node_types.get(target), is_top_event=target == top_event)
    if priority[source_type] != priority[target_type]:
        if priority[source_type] < priority[target_type]:
            return source, target
        return target, source

    return source, target


async def _build_fault_tree_references(
    rag,
    reference_sources: list[dict[str, Any]],
    include_chunk_content: bool,
) -> list[dict[str, Any]]:
    ordered_file_paths: list[str] = []
    file_to_chunk_ids: dict[str, list[str]] = defaultdict(list)

    for source in reference_sources:
        file_paths = source.get("file_paths", [])
        source_ids = source.get("source_ids", [])
        for file_path in file_paths:
            if not file_path or file_path.startswith("..."):
                continue
            if file_path not in ordered_file_paths:
                ordered_file_paths.append(file_path)
            for chunk_id in source_ids:
                if chunk_id and chunk_id not in file_to_chunk_ids[file_path]:
                    file_to_chunk_ids[file_path].append(chunk_id)

    if not ordered_file_paths:
        return []

    file_to_contents: dict[str, list[str]] = defaultdict(list)
    if include_chunk_content:
        chunk_ids: list[str] = []
        for file_path in ordered_file_paths:
            chunk_ids.extend(file_to_chunk_ids.get(file_path, []))
        unique_chunk_ids = list(dict.fromkeys(chunk_ids))
        if unique_chunk_ids:
            chunk_data_list = await rag.text_chunks.get_by_ids(unique_chunk_ids)
            for chunk_id, chunk_data in zip(unique_chunk_ids, chunk_data_list):
                if not chunk_data or "content" not in chunk_data:
                    continue
                file_path = chunk_data.get("file_path")
                if not file_path or file_path.startswith("..."):
                    continue
                content = chunk_data.get("content")
                if content and content not in file_to_contents[file_path]:
                    file_to_contents[file_path].append(content)

    references: list[dict[str, Any]] = []
    for index, file_path in enumerate(ordered_file_paths, start=1):
        references.append(
            {
                "reference_id": str(index),
                "file_path": file_path,
                "content": file_to_contents.get(file_path) if include_chunk_content else None,
            }
        )

    return references


async def _build_fault_tree_payload_from_graph(
    rag,
    top_event_query: str,
    include_chunk_content: bool,
) -> dict[str, Any] | None:
    if not hasattr(rag, "chunk_entity_relation_graph") or not hasattr(
        rag, "get_knowledge_graph"
    ):
        return None

    top_event = await _resolve_fault_tree_top_event_label(rag, top_event_query)
    if not top_event:
        return None

    knowledge_graph = await rag.get_knowledge_graph(
        node_label=top_event,
        max_depth=FAULT_TREE_SUBGRAPH_MAX_DEPTH,
        max_nodes=rag.max_graph_nodes,
    )
    if not knowledge_graph.nodes:
        return None

    node_types = {
        node.id: node.properties.get("entity_type", "IntermediateEvent")
        for node in knowledge_graph.nodes
    }
    distances = _build_fault_tree_distance_map(top_event, knowledge_graph.edges)

    triplets: list[dict[str, Any]] = []
    reference_sources: list[dict[str, Any]] = []
    seen_triplets: set[tuple[str, str, str]] = set()

    for edge in knowledge_graph.edges:
        relation = _extract_fault_tree_relation(edge.properties.get("keywords"))
        if relation is None:
            continue

        subject_name, object_name = _orient_fault_tree_edge(
            edge,
            top_event,
            distances,
            node_types,
        )
        if subject_name == object_name:
            continue

        triplet_key = (subject_name, relation, object_name)
        if triplet_key in seen_triplets:
            continue

        subject_type = _normalize_fault_tree_type(
            node_types.get(subject_name),
            is_top_event=subject_name == top_event,
        )
        object_type = _normalize_fault_tree_type(
            node_types.get(object_name),
            is_top_event=object_name == top_event,
        )

        source = str(edge.properties.get("description") or "").strip()
        if not source:
            source = f"{subject_name} {relation} {object_name}"

        triplets.append(
            {
                "subject_name": subject_name,
                "subject_type": subject_type,
                "relation": relation,
                "object_name": object_name,
                "object_type": object_type,
                "confidence": DEFAULT_FAULT_TREE_CONFIDENCE,
                "source": source,
            }
        )
        seen_triplets.add(triplet_key)
        reference_sources.append(
            {
                "file_paths": _split_graph_field(edge.properties.get("file_path")),
                "source_ids": _split_graph_field(edge.properties.get("source_id")),
            }
        )

    references = await _build_fault_tree_references(
        rag,
        reference_sources,
        include_chunk_content,
    )
    return {"triplets": triplets, "references": references}


def _derive_fault_tree_export_summary(triplets: list[dict[str, Any]]) -> dict[str, Any]:
    event_map: dict[str, dict[str, Any]] = {}
    gate_groups: dict[str, dict[str, Any]] = {}

    for triplet in triplets:
        subject_name = str(triplet.get("subject_name") or "").strip()
        object_name = str(triplet.get("object_name") or "").strip()
        relation = str(triplet.get("relation") or "resultsIn").strip()
        subject_type = str(triplet.get("subject_type") or "IntermediateEvent").strip()
        object_type = str(triplet.get("object_type") or "IntermediateEvent").strip()
        source = str(triplet.get("source") or "").strip()

        if subject_name and subject_name not in event_map:
            event_map[subject_name] = {
                "name": subject_name,
                "event_type": subject_type,
            }
        if object_name and object_name not in event_map:
            event_map[object_name] = {
                "name": object_name,
                "event_type": object_type,
            }

        if not object_name or not subject_name:
            continue

        gate_entry = gate_groups.setdefault(
            object_name,
            {
                "target_event": object_name,
                "gate_type": "AND" if relation == "jointly_resultsIn" else "OR",
                "source_events": [],
                "sources": [],
            },
        )
        if relation != "jointly_resultsIn":
            gate_entry["gate_type"] = "OR"
        if subject_name not in gate_entry["source_events"]:
            gate_entry["source_events"].append(subject_name)
        if source and source not in gate_entry["sources"]:
            gate_entry["sources"].append(source)

    gates: list[dict[str, Any]] = []
    for index, (target_event, gate_entry) in enumerate(gate_groups.items(), start=1):
        gates.append(
            {
                "id": f"gate_{index}",
                "target_event": target_event,
                "gate_type": gate_entry["gate_type"],
                "source_events": gate_entry["source_events"],
                "sources": gate_entry["sources"],
            }
        )

    return {
        "events": list(event_map.values()),
        "gates": gates,
    }
