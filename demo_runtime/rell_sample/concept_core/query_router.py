from __future__ import annotations

from typing import Any, Callable

from .concept_evidence import build_concept_evidence_packet
from .concept_units import find_state_concepts_by_text


def _build_concept_resolution_payload(matched_concepts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "matched_state_concepts": [
            {
                "concept_id": item.get("concept_id"),
                "display_name": item.get("display_name"),
                "query_type": item.get("query_type"),
                "source_policy": item.get("source_policy"),
                "source_slots": item.get("source_slots", []),
                "concept_evidence": build_concept_evidence_packet(
                    item,
                    concept_type="state_query_concept",
                    activation_reason="状态提问命中端侧高频查询概念",
                    match_basis=["local_state_query_alias_match", "runtime_snapshot_slot_binding"],
                    confidence=0.96,
                    fallback_policy="answer_from_runtime_snapshot_or_report_unsupported",
                ),
            }
            for item in matched_concepts
        ]
    }


def resolve_runtime_state_query(
    question: str,
    *,
    normalize_text_fn: Callable[[str], str],
    extract_object_constraints_fn: Callable[[str, dict[str, Any]], list[dict[str, Any]]],
    cognitive_model: dict[str, Any],
) -> dict[str, Any]:
    normalized = normalize_text_fn(question)
    object_constraints = extract_object_constraints_fn(question, cognitive_model)
    object_ref = object_constraints[0]["object_ref"] if object_constraints else "object_cup_white_mug"
    matched_concepts = find_state_concepts_by_text(normalized)
    if not matched_concepts:
        return {
            "query_type": "unsupported",
            "route_reason": "no_state_concept_match",
            "concept_resolution": _build_concept_resolution_payload([]),
        }

    matched = matched_concepts[0]
    result = {
        "query_type": matched["query_type"],
        "route_reason": f"matched_{matched['concept_id']}",
        "concept_resolution": _build_concept_resolution_payload(matched_concepts),
    }
    if matched["query_type"] == "liquid_state":
        override = (matched.get("object_overrides") or {}).get(object_ref, {})
        result.update(
            {
                "object_ref": object_ref,
                "positive_fact": override.get("positive_fact", matched.get("default_positive_fact")),
                "negative_fact": override.get("negative_fact", matched.get("default_negative_fact")),
            }
        )
    return result
