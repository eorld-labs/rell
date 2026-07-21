from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any


AUTHORITY_SCHEMA_VERSION = "1.0.0"


def _stable_id(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "dictionary_admission_" + hashlib.sha1(
        payload.encode("utf-8")
    ).hexdigest()[:16]


def _projection_digest(projection: dict[str, Any]) -> str:
    unsigned = deepcopy(projection)
    unsigned.pop("projection_id", None)
    payload = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _legacy_structured_semantic_adapter(
    analysis: dict[str, Any], *, world_revision: int
) -> dict[str, Any]:
    """Expose only typed legacy fields while keeping surface text above RCIR."""
    allowed = (
        "speech_act",
        "query_type",
        "canonical_frame",
        "semantic_constraint_frame",
        "discourse_roles",
        "event_candidates",
        "reported_event_candidates",
        "historical_event_constraints",
        "event_frames",
        "discourse_event_graph",
        "modifier_contract",
        "reference_resolution",
        "rule_evaluation",
        "unresolved_slots",
        "recovery_context_projection",
    )
    result = {
        key: deepcopy(analysis.get(key))
        for key in allowed
        if analysis.get(key) is not None
    }
    result.update(
        {
            "semantic_input_kind": "legacy_structured_compatibility_adapter",
            "world_revision": world_revision,
            "candidate_only": True,
            "runtime_fact_committed": False,
        }
    )
    return result


def build_dictionary_authority_admission(
    analysis: dict[str, Any],
    projection: dict[str, Any] | None,
    equivalence_receipt: dict[str, Any] | None,
    *,
    world_revision: int,
    mode: str = "controlled_authority_trial",
) -> dict[str, Any]:
    projection = projection or {}
    receipt = equivalence_receipt or {}
    lattice = projection.get("interpretation_lattice") or {}
    blockers: list[str] = []

    if projection.get("projection_kind") != "MachineDictionaryProjection":
        blockers.append("dictionary_projection_missing")
    if receipt.get("receipt_kind") != "MachineDictionaryEquivalenceReceipt":
        blockers.append("equivalence_receipt_missing")
    if receipt.get("status") != "equivalent":
        blockers.append("equivalence_not_established")
    if receipt.get("eligible_for_authority_promotion") is not True:
        blockers.append("projection_not_promotion_eligible")
    if lattice.get("status") != "resolved":
        blockers.append("interpretation_lattice_not_resolved")
    if lattice.get("authoritative_semantic_graph_emitted") is not True:
        blockers.append("interpretation_lattice_has_no_unique_graph")
    if projection.get("unresolved_variables"):
        blockers.append("semantic_variables_unresolved")
    if projection.get("unresolved_polysemy_count"):
        blockers.append("polysemy_unresolved")
    if not (projection.get("scope_graph") or {}).get("scope_complete"):
        blockers.append("scope_incomplete")
    if not projection.get("semantic_payload"):
        blockers.append("typed_semantic_payload_missing")
    if receipt.get("projection_ref") != projection.get("projection_id"):
        blockers.append("equivalence_projection_ref_mismatch")
    if receipt.get("projection_digest") != _projection_digest(projection):
        blockers.append("equivalence_projection_digest_mismatch")

    revision_refs = {
        "projection": projection.get("world_revision"),
        "lattice": lattice.get("world_revision"),
        "receipt": receipt.get("world_revision"),
    }
    for source, revision in revision_refs.items():
        if revision != world_revision:
            blockers.append(f"{source}_world_revision_mismatch")
    semantic_payload = projection.get("semantic_payload") or {}
    grounding_roles = (
        (semantic_payload.get("grounded_intent_frame") or {}).get("roles") or {}
    )
    if any(
        role.get("world_revision") not in {None, world_revision}
        for role in grounding_roles.values()
        if isinstance(role, dict)
    ):
        blockers.append("grounding_binding_world_revision_mismatch")
    process_bindings = (
        (semantic_payload.get("process_template_resolution") or {}).get(
            "bindings"
        )
        or {}
    )
    if any(
        binding.get("observation_world_revision") not in {None, world_revision}
        for binding in process_bindings.values()
        if isinstance(binding, dict)
    ):
        blockers.append("process_binding_world_revision_mismatch")

    recovery = projection.get("recovery_context_projection") or {}
    recovery_active = recovery.get("status") not in {None, "inactive", "closed"}
    if recovery_active and not (
        recovery.get("reentered_current_fact_pruning") is True
        or recovery.get("requires_current_fact_pruning") is True
        or recovery.get("current_world_revalidation_required") is True
    ):
        blockers.append("recovery_did_not_reenter_current_fact_pruning")

    blockers.extend(str(item) for item in receipt.get("promotion_blockers", []))
    blockers = list(dict.fromkeys(blockers))
    admitted = not blockers
    semantic_input = (
        deepcopy(projection["semantic_payload"])
        if admitted
        else _legacy_structured_semantic_adapter(
            analysis, world_revision=world_revision
        )
    )
    semantic_input.update(
        {
            "semantic_input_kind": (
                "machine_dictionary_authoritative_projection"
                if admitted
                else "legacy_structured_compatibility_adapter"
            ),
            "world_revision": world_revision,
            "candidate_only": True,
            "runtime_fact_committed": False,
        }
    )
    admission = {
        "schema_version": AUTHORITY_SCHEMA_VERSION,
        "admission_kind": "DictionaryAuthorityAdmission",
        "mode": mode,
        "admission_status": "admitted" if admitted else "fallback",
        "authoritative_semantic_source": (
            "machine_dictionary"
            if admitted
            else "legacy_structured_compatibility_adapter"
        ),
        "fallback_used": not admitted,
        "fallback_reasons": blockers,
        "dictionary_ref": projection.get("dictionary_ref"),
        "projection_ref": projection.get("projection_id"),
        "projection_digest": receipt.get("projection_digest"),
        "lattice_ref": lattice.get("lattice_id"),
        "equivalence_receipt_ref": receipt.get("receipt_id"),
        "world_revision": world_revision,
        "revision_dependencies": revision_refs,
        "semantic_input": semantic_input,
        "legacy_parser_role": (
            "upstream_dictionary_projection_adapter"
            if admitted
            else "monitored_structured_compatibility_adapter"
        ),
        "downstream_legacy_semantic_fields_allowed": False,
        "downstream_surface_reparse_allowed": False,
        "recovery_reentered_current_fact_pruning": (
            not recovery_active
            or recovery.get("reentered_current_fact_pruning") is True
            or recovery.get("requires_current_fact_pruning") is True
            or recovery.get("current_world_revalidation_required") is True
        ),
        "can_generate_situated_event_graph": True,
        "can_control_execution": False,
        "can_commit_runtime_fact": False,
        "runtime_fact_committed": False,
    }
    admission["admission_id"] = _stable_id(admission)
    return admission


def invalidate_dictionary_authority_admission(
    admission: dict[str, Any], *, current_world_revision: int
) -> dict[str, Any]:
    result = deepcopy(admission)
    if result.get("world_revision") == current_world_revision:
        result["locally_invalidated"] = False
        return result
    result.update(
        {
            "admission_status": "invalidated",
            "authoritative_semantic_source": None,
            "fallback_used": False,
            "fallback_reasons": ["world_revision_changed"],
            "semantic_input": None,
            "locally_invalidated": True,
            "invalidated_by_world_revision": current_world_revision,
            "can_generate_situated_event_graph": False,
            "can_control_execution": False,
            "can_commit_runtime_fact": False,
            "runtime_fact_committed": False,
        }
    )
    return result


def assert_dictionary_authority_boundary(admission: dict[str, Any]) -> None:
    if admission.get("can_control_execution") is not False:
        raise AssertionError("dictionary_authority_cannot_control_execution")
    if admission.get("can_commit_runtime_fact") is not False:
        raise AssertionError("dictionary_authority_cannot_commit_runtime_fact")
    if admission.get("downstream_legacy_semantic_fields_allowed") is not False:
        raise AssertionError("legacy_semantic_fields_bypassed_authority_admission")
    if admission.get("admission_status") == "admitted" and admission.get(
        "fallback_used"
    ):
        raise AssertionError("dictionary_and_fallback_cannot_be_simultaneously_authoritative")
    semantic_input = admission.get("semantic_input") or {}
    if semantic_input.get("world_revision") != admission.get("world_revision"):
        raise AssertionError("semantic_input_world_revision_mismatch")


__all__ = [
    "assert_dictionary_authority_boundary",
    "build_dictionary_authority_admission",
    "invalidate_dictionary_authority_admission",
]
