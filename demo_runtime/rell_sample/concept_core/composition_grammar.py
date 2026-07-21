from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any


REFERENT_KINDS = {
    "entity_ref",
    "entity_selector",
    "set_selector",
    "subregion_selector",
    "future_entity_selector",
    "interaction_role",
    "event_role",
}


def _stable_id(prefix: str, value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return prefix + "_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def make_referent_expression(
    kind: str,
    *,
    entity_ref: str | None = None,
    concept_refs: list[str] | None = None,
    constraints: list[dict[str, Any]] | None = None,
    members: list[dict[str, Any]] | None = None,
    parent_ref: dict[str, Any] | None = None,
    generation_condition: dict[str, Any] | None = None,
    interaction_role: str | None = None,
    world_revision: int | None = None,
) -> dict[str, Any]:
    if kind not in REFERENT_KINDS:
        raise ValueError(f"unsupported referent kind: {kind}")
    if kind == "entity_ref" and not entity_ref:
        raise ValueError("entity_ref referent requires an entity_ref")
    if kind != "entity_ref" and entity_ref:
        raise ValueError("selectors must not impersonate a grounded EntityRef")
    if kind == "future_entity_selector" and not generation_condition:
        raise ValueError("future selector requires a generation condition")
    if kind == "set_selector" and not members:
        raise ValueError("set selector requires members")
    if kind == "subregion_selector" and not parent_ref:
        raise ValueError("subregion selector requires a parent referent")
    if kind == "interaction_role" and not interaction_role:
        raise ValueError("interaction role referent requires a role")
    value = {
        "schema_version": "1.0.0",
        "referent_kind": kind,
        "entity_ref": entity_ref,
        "concept_refs": sorted(set(concept_refs or [])),
        "constraints": deepcopy(constraints or []),
        "members": deepcopy(members or []),
        "parent_ref": deepcopy(parent_ref),
        "generation_condition": deepcopy(generation_condition),
        "interaction_role": interaction_role,
        "world_revision": world_revision,
        "grounding_required": kind != "entity_ref",
        "candidate_only": kind != "entity_ref",
        "runtime_fact_committed": False,
    }
    value["referent_id"] = _stable_id("referent", value)
    return value


def build_scope_graph(
    event_refs: list[str],
    attachments: list[dict[str, Any]],
    discourse_edges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    allowed_targets = set(event_refs)
    invalid = [
        item
        for item in attachments
        if item.get("scope") != "global"
        and item.get("target_event_ref") is not None
        and item.get("target_event_ref") not in allowed_targets
    ]
    if invalid:
        raise ValueError(f"scope attachment targets unknown event: {invalid}")
    unresolved = [
        deepcopy(item)
        for item in attachments
        if item.get("scope") != "global"
        and item.get("target_event_ref") is None
    ]
    graph = {
        "schema_version": "1.0.0",
        "scope_kind": "ScopeGraph",
        "event_refs": list(event_refs),
        "attachments": deepcopy(attachments),
        "unresolved_attachments": unresolved,
        "scope_complete": not unresolved,
        "discourse_edges": deepcopy(discourse_edges or []),
        "nearest_event_heuristic_is_authoritative": False,
        "candidate_only": True,
        "runtime_fact_committed": False,
    }
    graph["scope_graph_id"] = _stable_id("scope_graph", graph)
    return graph


def build_interpretation_lattice(
    *,
    source_ref: str,
    candidate_graphs: list[dict[str, Any]],
    world_revision: int,
) -> dict[str, Any]:
    admissible = [item for item in candidate_graphs if item.get("admissible", True)]
    status = "resolved" if len(admissible) == 1 else "unresolved"
    lattice = {
        "schema_version": "1.0.0",
        "lattice_kind": "InterpretationLattice",
        "source_ref": source_ref,
        "world_revision": world_revision,
        "candidates": deepcopy(candidate_graphs),
        "status": status,
        "selected_candidate_ref": admissible[0].get("candidate_id") if status == "resolved" else None,
        "inquiry_contract": None if status == "resolved" else {
            "contract_kind": "InquiryContract",
            "reason": "semantic_interpretation_not_unique",
            "candidate_refs": [item.get("candidate_id") for item in admissible],
            "minimum_information_requested": "typed_discriminating_constraint",
            "world_revision": world_revision,
            "candidate_only": True,
            "runtime_fact_committed": False,
        },
        "authoritative_semantic_graph_emitted": status == "resolved",
        "raw_text_allowed_below_lattice": False,
        "runtime_fact_committed": False,
    }
    lattice["lattice_id"] = _stable_id("interpretation_lattice", lattice)
    return lattice


__all__ = [
    "build_interpretation_lattice",
    "build_scope_graph",
    "make_referent_expression",
]
