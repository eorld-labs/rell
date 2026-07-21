from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from .machine_dictionary import dictionary_index


EQUIVALENCE_SCHEMA_VERSION = "1.0.0"


def _stable_id(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "dictionary_equivalence_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _role_signature(role: dict[str, Any]) -> dict[str, Any]:
    entity_ref = role.get("entity_ref") or role.get("value_ref")
    if entity_ref:
        return {"referent_kind": "entity_ref", "entity_ref": str(entity_ref)}
    constraints = [
        {key: deepcopy(value) for key, value in item.items() if key != "candidate_only"}
        for item in (role.get("constraints") or [])
    ]
    for field in ("spatial_relation", "relation_predicate", "quantity_constraint"):
        if role.get(field) is not None:
            constraints.append({"constraint_kind": field, "value": deepcopy(role[field])})
    concept_ref = role.get("concept_id")
    return {
        "referent_kind": "entity_selector",
        "concept_refs": [concept_ref] if concept_ref else [],
        "constraints": constraints,
    }


def _projected_role_signature(referent: dict[str, Any]) -> dict[str, Any]:
    if referent.get("referent_kind") == "entity_ref":
        return {"referent_kind": "entity_ref", "entity_ref": referent.get("entity_ref")}
    return {
        "referent_kind": referent.get("referent_kind"),
        "concept_refs": list(referent.get("concept_refs") or []),
        "constraints": [
            {key: deepcopy(value) for key, value in item.items() if key != "candidate_only"}
            for item in referent.get("constraints", [])
        ],
    }


def _field_result(expected: Any, actual: Any) -> dict[str, Any]:
    equivalent = expected == actual
    return {
        "status": "equivalent" if equivalent else "divergent",
        "expected": deepcopy(expected),
        "actual": deepcopy(actual),
        "blocks_authority_promotion": not equivalent,
    }


def _analysis_frame_signature(frame: dict[str, Any]) -> dict[str, Any]:
    return {
        "operators": list((frame.get("canonical_frame") or {}).get("operators", [])),
        "roles": {
            name: _role_signature(role)
            for name, role in (frame.get("role_bindings") or {}).items()
            if isinstance(role, dict)
        },
        "goal_relation": (frame.get("canonical_frame") or {}).get("goal_relation"),
        "unresolved_variables": list(frame.get("unresolved_slots") or []),
        "reference_referents": deepcopy(
            (frame.get("reference_resolution") or {}).get("referent_expressions", [])
        ),
    }


def _projection_frame_signature(
    projection: dict[str, Any], dictionary: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    return {
        "operators": [
            (dictionary.get(ref) or {}).get("semantic_value")
            for ref in projection.get("operator_refs", [])
        ],
        "roles": {
            name: _projected_role_signature(referent)
            for name, referent in (projection.get("role_referents") or {}).items()
        },
        "goal_relation": projection.get("goal_relation"),
        "unresolved_variables": list(projection.get("unresolved_variables") or []),
        "reference_referents": deepcopy(projection.get("reference_referents") or []),
    }


def build_dictionary_equivalence_receipt(
    analysis: dict[str, Any], projection: dict[str, Any], *, world_revision: int
) -> dict[str, Any]:
    dictionary = dictionary_index()
    expected_operators = list((analysis.get("canonical_frame") or {}).get("operators", []))
    actual_operators = [
        (dictionary.get(ref) or {}).get("semantic_value")
        for ref in projection.get("operator_refs", [])
    ]
    expected_roles = {
        name: _role_signature(role)
        for name, role in (analysis.get("role_bindings") or {}).items()
        if isinstance(role, dict)
    }
    actual_roles = {
        name: _projected_role_signature(referent)
        for name, referent in (projection.get("role_referents") or {}).items()
    }
    expected_modifiers = [
        {
            "dimension": item.get("dimension"),
            "value": item.get("value"),
            "scope": item.get("scope"),
            "event_index": item.get("event_index"),
        }
        for item in (analysis.get("modifier_contract") or {}).get("modifiers", [])
    ]
    event_ref_index = {
        ref: index for index, ref in enumerate((projection.get("scope_graph") or {}).get("event_refs", []))
    }
    actual_modifiers = [
        {
            "dimension": item.get("dimension"),
            "value": item.get("value"),
            "scope": item.get("scope"),
            "event_index": (
                event_ref_index.get(item.get("target_event_ref"))
                if item.get("scope") != "global"
                else None
            ),
        }
        for item in (projection.get("scope_graph") or {}).get("attachments", [])
    ]
    expected_references = deepcopy(
        (analysis.get("reference_resolution") or {}).get("referent_expressions", [])
    )
    expected_discourse = deepcopy(
        (analysis.get("discourse_event_graph") or {}).get("edges", [])
    )
    expected_recovery = deepcopy(analysis.get("recovery_context_projection"))
    fields = {
        "speech_act_and_query": _field_result(
            {
                "speech_act": analysis.get("speech_act")
                or (analysis.get("canonical_frame") or {}).get("speech_act"),
                "query_type": analysis.get("query_type")
                or (analysis.get("canonical_frame") or {}).get("query_type"),
            },
            {
                "speech_act": projection.get("speech_act"),
                "query_type": projection.get("query_type"),
            },
        ),
        "operators": _field_result(expected_operators, actual_operators),
        "roles": _field_result(expected_roles, actual_roles),
        "modifiers_and_scope": _field_result(expected_modifiers, actual_modifiers),
        "goal_relation": _field_result(
            (analysis.get("canonical_frame") or {}).get("goal_relation"),
            projection.get("goal_relation"),
        ),
        "unresolved_variables": _field_result(
            list(analysis.get("unresolved_slots") or []),
            list(projection.get("unresolved_variables") or []),
        ),
        "references": _field_result(
            expected_references, projection.get("reference_referents") or []
        ),
        "discourse_edges": _field_result(
            expected_discourse,
            (projection.get("scope_graph") or {}).get("discourse_edges", []),
        ),
        "recovery_context": _field_result(
            expected_recovery, projection.get("recovery_context_projection")
        ),
        "event_frames": _field_result(
            [
                _analysis_frame_signature(frame)
                for frame in analysis.get("event_frames", [])
            ],
            [
                _projection_frame_signature(frame, dictionary)
                for frame in projection.get("event_frame_projections", [])
            ],
        ),
    }
    divergent = [name for name, result in fields.items() if result["status"] == "divergent"]
    promotion_blockers = list(projection.get("semantic_coverage_gaps") or [])
    promotion_blockers.extend(
        f"divergent_field:{name}" for name in divergent
    )
    if projection.get("missing_operator_semantics"):
        promotion_blockers.append("operator_semantics_missing")
    if projection.get("unresolved_polysemy_count"):
        promotion_blockers.append("polysemy_unresolved")
    if projection.get("unresolved_variables"):
        promotion_blockers.append("semantic_variables_unresolved")
    if not (projection.get("scope_graph") or {}).get("scope_complete"):
        promotion_blockers.append("scope_incomplete")
    if not projection.get("all_event_frames_admissible", True):
        promotion_blockers.append("event_frame_not_admissible")
    if any(
        item.get("requires_confirmation")
        for item in projection.get("reference_referents", [])
    ):
        promotion_blockers.append("reference_confirmation_required")
    promotion_blockers = list(dict.fromkeys(promotion_blockers))
    receipt = {
        "schema_version": EQUIVALENCE_SCHEMA_VERSION,
        "receipt_kind": "MachineDictionaryEquivalenceReceipt",
        "mode": "shadow_equivalence_migration",
        "world_revision": world_revision,
        "projection_lattice_ref": (projection.get("interpretation_lattice") or {}).get("lattice_id"),
        "field_results": fields,
        "status": "equivalent" if not divergent else "divergent",
        "divergent_fields": divergent,
        "promotion_blockers": promotion_blockers,
        "eligible_for_authority_promotion": not promotion_blockers,
        "can_control_execution": False,
        "can_commit_runtime_fact": False,
        "surface_text_reparsed": False,
        "runtime_fact_committed": False,
    }
    receipt["receipt_id"] = _stable_id(receipt)
    return receipt


__all__ = ["build_dictionary_equivalence_receipt"]
