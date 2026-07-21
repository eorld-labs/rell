from __future__ import annotations

from copy import deepcopy
from typing import Any

from .cognitive_inquiry import make_inquiry_contract
from .rcir_primitives import (
    make_evidence_envelope,
    make_predicate,
    stable_digest,
)


RELATION_BY_LANGUAGE_CONSTRAINT = {
    "on_support_surface": "supported_by",
    "inside_container": "contained_in",
    "near_landmark": "near",
}

AFFORDANCE_RELATION_RULES = (
    {
        "predicate": "supported_by",
        "required_any": {"support_object"},
        "rule": "place_on_support_default",
    },
    {
        "predicate": "contained_in",
        "required_any": {
            "contain_object",
            "contains_object_candidate",
            "openable_storage_candidate",
            "receive_inside_object",
        },
        "rule": "place_inside_container_default",
    },
)


def _resolved_entity_ref(
    grounded_graph: dict[str, Any], role_name: str
) -> str | None:
    binding = (grounded_graph.get("role_bindings") or {}).get(role_name) or {}
    if binding.get("status") != "resolved":
        return None
    return binding.get("entity_ref")


def _temporal_window(
    situated_graph: dict[str, Any], *, temporal_anchor_ref: str | None,
    temporal_scope: str = "requested_current_or_future",
) -> dict[str, Any]:
    return {
        "interaction_turn": int(situated_graph.get("interaction_turn") or 0),
        "temporal_scope": temporal_scope,
        "valid_from_world_revision": int(situated_graph.get("world_revision") or 0),
        "valid_until_world_revision": None,
        "temporal_anchor_ref": temporal_anchor_ref,
        "dialogue_distance": 0,
        "expires_on_world_revision_change": True,
    }


def _relation_predicate(
    predicate_name: str,
    *,
    theme_ref: str,
    destination_ref: str,
    world_revision: int,
    situated_graph: dict[str, Any],
    inference_kind: str,
    inference_rule: str,
    premise_refs: list[str],
    strength: int,
    temporal_scope: str = "requested_current_or_future",
) -> dict[str, Any]:
    events = situated_graph.get("events") or []
    temporal_anchor_ref = events[-1].get("event_id") if events else None
    return make_predicate(
        predicate_name,
        [
            {"role": "subject", "value_type": "EntityRef", "value": theme_ref},
            {"role": "object", "value_type": "EntityRef", "value": destination_ref},
        ],
        world_revision=world_revision,
        modality="hypothesis",
        status="candidate",
        depends_on_refs=premise_refs,
        provenance={
            "inference_kind": inference_kind,
            "inference_rule": inference_rule,
            "premise_refs": sorted(set(premise_refs)),
            "strength": strength,
            "temporal_window": _temporal_window(
                situated_graph,
                temporal_anchor_ref=temporal_anchor_ref,
                temporal_scope=temporal_scope,
            ),
        },
    )


def generate_relation_hypothesis_workset(
    situated_graph: dict[str, Any],
    grounded_graph: dict[str, Any],
    world_ledger: dict[str, Any],
) -> dict[str, Any]:
    """Generate ephemeral relation candidates without mutating fact authority."""
    ledger_digest_before = stable_digest(world_ledger)
    world_revision = int(world_ledger.get("world_revision") or 0)
    operators = {
        item.get("operator") for item in situated_graph.get("events", [])
    }
    theme_ref = _resolved_entity_ref(grounded_graph, "theme")
    destination_ref = _resolved_entity_ref(grounded_graph, "destination")
    base = {
        "schema_version": "1.0.0",
        "workset_kind": "relation_hypothesis_workset",
        "world_revision": world_revision,
        "fact_authority_ref": world_ledger.get("ledger_id"),
        "ledger_access": "read_only_current_projection",
        "fact_write_authority": "P016_via_WorldFactLedger_only",
        "candidate_memory_lifecycle": "ephemeral_task_working_memory",
        "direct_execution_allowed": False,
        "runtime_fact_committed": False,
    }
    if "place_object" not in operators or not theme_ref or not destination_ref:
        return {
            **base,
            "status": "not_applicable",
            "candidates": [],
            "selected_predicate_ref": None,
            "inquiry_contract": None,
            "ledger_digest_before": ledger_digest_before,
            "ledger_digest_after": stable_digest(world_ledger),
        }

    destination_role = (situated_graph.get("roles") or {}).get("destination") or {}
    affordances = set(destination_role.get("functional_affordances") or [])
    explicit_constraint = destination_role.get("spatial_relation")
    explicit_predicate = RELATION_BY_LANGUAGE_CONSTRAINT.get(explicit_constraint)
    graph_ref = str(situated_graph.get("graph_id"))
    premise_refs = [graph_ref, theme_ref, destination_ref]
    candidates: list[dict[str, Any]] = []

    if explicit_predicate:
        inference_rule = "language_declared_spatial_relation"
        containment_affordances = {
            "contain_object",
            "contains_object_candidate",
            "openable_storage_candidate",
            "receive_inside_object",
        }
        if (
            explicit_predicate == "contained_in"
            and "transport_supported_payload" in affordances
            and not containment_affordances.intersection(affordances)
        ):
            explicit_predicate = "supported_by"
            inference_rule = "inside_region_language_normalized_by_carrier_affordance"
        candidates.append(
            _relation_predicate(
                explicit_predicate,
                theme_ref=theme_ref,
                destination_ref=destination_ref,
                world_revision=world_revision,
                situated_graph=situated_graph,
                inference_kind="explicit_spatial_marker",
                inference_rule=inference_rule,
                premise_refs=premise_refs,
                strength=900,
            )
        )
    else:
        verified_source_support = next(
            (
                item
                for item in situated_graph.get("historical_event_constraints", [])
                if item.get("relation") == "source_support_of_verified_event"
                and item.get("head_role") == "destination"
            ),
            None,
        )
        if verified_source_support:
            candidates.append(
                _relation_predicate(
                    "supported_by",
                    theme_ref=theme_ref,
                    destination_ref=destination_ref,
                    world_revision=world_revision,
                    situated_graph=situated_graph,
                    inference_kind="verified_event_relation",
                    inference_rule="restore_verified_event_source_support",
                    premise_refs=[*premise_refs, "verified_event:source_support"],
                    strength=750,
                    temporal_scope="reported_past",
                )
            )
        current_relation_names = {
            item.get("predicate")
            for item in world_ledger.get("facts", [])
            if item.get("current_world_usable") is True
            and item.get("subject") == theme_ref
            and item.get("object") == destination_ref
            and item.get("predicate") in {"supported_by", "contained_in", "near"}
        }
        for predicate_name in sorted(current_relation_names):
            candidates.append(
                _relation_predicate(
                    str(predicate_name),
                    theme_ref=theme_ref,
                    destination_ref=destination_ref,
                    world_revision=world_revision,
                    situated_graph=situated_graph,
                    inference_kind="current_verified_relation",
                    inference_rule="reuse_current_verified_relation",
                    premise_refs=[*premise_refs, str(world_ledger.get("ledger_id"))],
                    strength=850,
                )
            )
        for rule in AFFORDANCE_RELATION_RULES:
            if not set(rule["required_any"]).intersection(affordances):
                continue
            candidates.append(
                _relation_predicate(
                    str(rule["predicate"]),
                    theme_ref=theme_ref,
                    destination_ref=destination_ref,
                    world_revision=world_revision,
                    situated_graph=situated_graph,
                    inference_kind="defaulted_from_affordance",
                    inference_rule=str(rule["rule"]),
                    premise_refs=premise_refs,
                    strength=500,
                )
            )

    by_name: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        existing = by_name.get(candidate["name"])
        current_strength = int((candidate.get("provenance") or {}).get("strength") or 0)
        existing_strength = int((existing or {}).get("provenance", {}).get("strength") or 0)
        if existing is None or current_strength > existing_strength:
            by_name[candidate["name"]] = candidate
    candidates = [by_name[name] for name in sorted(by_name)]

    question = make_predicate(
        "intended_spatial_relation",
        [
            {"role": "subject", "value_type": "EntityRef", "value": theme_ref},
            {"role": "destination", "value_type": "EntityRef", "value": destination_ref},
            {"role": "relation", "value_type": "role_variable", "value": "relation"},
        ],
        world_revision=world_revision,
        modality="hypothesis",
        status="candidate",
        depends_on_refs=premise_refs,
    )
    instruction_evidence = make_evidence_envelope(
        "language_instruction",
        epistemic_status="candidate",
        world_revision=world_revision,
        supports_refs=[question["predicate_id"], *[item["predicate_id"] for item in candidates]],
        strength=450,
        current_world_bound=True,
        depends_on_refs=premise_refs,
        payload={
            "situated_graph_ref": graph_ref,
            "temporal_window": _temporal_window(
                situated_graph,
                temporal_anchor_ref=(situated_graph.get("events") or [{}])[-1].get("event_id"),
            ),
        },
    )
    evidence_ref = instruction_evidence["envelope_id"]
    question["evidence_refs"] = [evidence_ref]
    for candidate in candidates:
        candidate["evidence_refs"] = [evidence_ref]

    inquiry = None
    selected_ref = None
    if len(candidates) == 1:
        status = "resolved_unique_candidate"
        selected_ref = candidates[0]["predicate_id"]
    elif len(candidates) > 1:
        status = "ambiguous_requires_inquiry"
        inquiry = make_inquiry_contract(
            "fact_gap",
            subject_refs=[theme_ref, destination_ref],
            trigger_evidence_refs=[evidence_ref],
            candidate_hypotheses=[item["predicate_id"] for item in candidates],
            question_predicate_ref=question["predicate_id"],
            answer_routes=["existing_evidence", "active_observation", "human_query"],
            authorization_scope="observe_only",
            world_revision=world_revision,
            depends_on_refs=[*premise_refs, *[item["predicate_id"] for item in candidates]],
            closure_condition="one_relation_hypothesis_remains_with_current_world_evidence",
            fact_authority_ref=str(world_ledger.get("ledger_id")),
            expected_information_gain=0.8,
            risk_if_ignored="medium",
            acquisition_cost="low",
        )
    else:
        status = "unresolved_missing_relation_contract"

    result = {
        **base,
        "status": status,
        "theme_ref": theme_ref,
        "destination_ref": destination_ref,
        "question_predicate": question,
        "candidates": candidates,
        "candidate_evidence": [instruction_evidence],
        "selected_predicate_ref": selected_ref,
        "inquiry_contract": inquiry,
        "ambiguity_silently_resolved": False,
        "ledger_digest_before": ledger_digest_before,
        "ledger_digest_after": stable_digest(world_ledger),
    }
    if result["ledger_digest_before"] != result["ledger_digest_after"]:
        raise AssertionError("relation_generator_mutated_world_fact_ledger")
    return result


def assert_relation_hypothesis_boundary(workset: dict[str, Any]) -> None:
    if workset.get("status") == "not_applicable":
        return
    if workset.get("ledger_access") != "read_only_current_projection":
        raise AssertionError("relation_generator_requires_read_only_ledger")
    if workset.get("ledger_digest_before") != workset.get("ledger_digest_after"):
        raise AssertionError("relation_generator_mutated_world_fact_ledger")
    if workset.get("runtime_fact_committed") is not False:
        raise AssertionError("relation_hypothesis_committed_runtime_fact")
    if any(
        item.get("fact_commit_eligible") is not False
        for item in workset.get("candidate_evidence", [])
    ):
        raise AssertionError("relation_candidate_evidence_gained_fact_authority")
    candidates = workset.get("candidates") or []
    if len(candidates) > 1:
        if workset.get("selected_predicate_ref") is not None:
            raise AssertionError("ambiguous_relation_silently_became_unique")
        inquiry = workset.get("inquiry_contract") or {}
        if set(inquiry.get("candidate_hypotheses") or []) != {
            item.get("predicate_id") for item in candidates
        }:
            raise AssertionError("ambiguous_relation_missing_inquiry_contract")
