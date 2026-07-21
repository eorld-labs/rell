from __future__ import annotations

import json
from pathlib import Path

from concept_core.cognitive_ir import compile_rcir_bundle
from concept_core.rcir_primitives import (
    invalidate_versioned_artifacts,
    validate_primitive,
)
from concept_core.relation_hypothesis import assert_relation_hypothesis_boundary
from embodied_scene import (
    SESSIONS,
    _compose_session_language,
    begin_motion_command,
    start_session,
)


ROOT = Path(__file__).resolve().parents[2]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _validate_declared_shape(instance: dict, schema_name: str) -> None:
    schema = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
    missing = set(schema.get("required", [])) - set(instance)
    extras = set(instance) - set(schema.get("properties", {}))
    require(not missing, f"{schema_name} missing fields: {missing}")
    require(not extras, f"{schema_name} undeclared fields: {extras}")
    source_declaration = (schema.get("properties") or {}).get("source_type") or {}
    if source_declaration.get("enum"):
        require(
            instance.get("source_type") in source_declaration["enum"],
            f"{schema_name} source_type violates enum",
        )


def _analysis(
    destination_affordances: list[str],
    *,
    spatial_relation: str | None = None,
    world_revision: int = 12,
) -> dict:
    destination_role = {
        "role": "destination",
        "concept_id": "concept_destination",
        "functional_affordances": destination_affordances,
        "constraints": [],
    }
    if spatial_relation:
        destination_role.update({
            "spatial_relation": spatial_relation,
            "spatial_relation_basis": "explicit_spatial_marker",
        })
    return {
        "speech_act": "task_request",
        "canonical_frame": {
            "operators": ["place_object"],
            "goal_relation": "object_supported_at_destination",
        },
        "event_candidates": [
            {
                "operator": "place_object",
                "concept_id": "factory_event_place",
                "source": "synthetic_structured_test",
            }
        ],
        "semantic_constraint_frame": {
            "roles": {
                "theme": {
                    "role": "theme",
                    "concept_id": "concept_movable_object",
                    "functional_affordances": ["graspable", "movable"],
                    "constraints": [],
                },
                "destination": destination_role,
            }
        },
        "grounded_intent_frame": {
            "roles": {
                "theme": {
                    "status": "resolved",
                    "world_revision": world_revision,
                    "observation_evidence_set_id": "observation_theme",
                    "binding": {
                        "entity_ref": "entity_cup",
                        "binding_basis": "current_observation_grounding",
                        "evidence_strength": 600,
                    },
                },
                "destination": {
                    "status": "resolved",
                    "world_revision": world_revision,
                    "observation_evidence_set_id": "observation_destination",
                    "binding": {
                        "entity_ref": "entity_workbench",
                        "binding_basis": "current_observation_grounding",
                        "evidence_strength": 600,
                    },
                },
            }
        },
    }


def _compile(
    destination_affordances: list[str],
    *,
    spatial_relation: str | None = None,
    current_facts: list[dict] | None = None,
) -> dict:
    return compile_rcir_bundle(
        "structured test input",
        _analysis(
            destination_affordances,
            spatial_relation=spatial_relation,
        ),
        current_facts=current_facts or [],
        world_revision=12,
        interaction_turn=8,
        interaction_role_bindings={},
    )


def verify_unique_affordance_default() -> dict:
    bundle = _compile(["support_object"])
    grounded = bundle["grounded_causal_graph"]
    workset = grounded["relation_hypothesis_workset"]
    candidate = workset["candidates"][0]
    temporal = candidate["provenance"]["temporal_window"]
    require(
        workset["status"] == "resolved_unique_candidate"
        and candidate["name"] == "supported_by"
        and candidate["provenance"]["inference_kind"]
        == "defaulted_from_affordance"
        and temporal["interaction_turn"] == 8
        and temporal["valid_from_world_revision"] == 12
        and temporal["expires_on_world_revision_change"] is True
        and grounded["ready_for_orchestration"] is True,
        f"unique affordance relation did not resolve safely: {workset}",
    )
    assert_relation_hypothesis_boundary(workset)
    return {
        "selected": candidate["name"],
        "basis": candidate["provenance"]["inference_kind"],
        "temporal_window_bound": True,
    }


def verify_ambiguity_enters_cognitive_inquiry() -> dict:
    bundle = _compile(
        ["support_object", "contains_object_candidate"],
        current_facts=[
            {
                "predicate": "supported_by",
                "subject": "entity_cup",
                "object": "entity_workbench",
                "evidence": "runtime_verified",
                "world_revision": 12,
            }
        ],
    )
    grounded = bundle["grounded_causal_graph"]
    workset = grounded["relation_hypothesis_workset"]
    inquiry = workset.get("inquiry_contract") or {}
    names = {item["name"] for item in workset["candidates"]}
    require(
        workset["status"] == "ambiguous_requires_inquiry"
        and names == {"supported_by", "contained_in"}
        and workset["selected_predicate_ref"] is None
        and inquiry.get("control_gateway") == "P018"
        and inquiry.get("verification_gateway") == "P016"
        and grounded["ready_for_orchestration"] is False
        and grounded["binding_status"] == "incomplete",
        f"relation ambiguity silently became unique: {grounded}",
    )
    assert_relation_hypothesis_boundary(workset)
    return {
        "candidate_relations": sorted(names),
        "inquiry_id": inquiry.get("inquiry_id"),
        "current_verified_relation_did_not_silence_competitor": True,
    }


def verify_explicit_relation_and_schema() -> dict:
    bundle = _compile(
        ["support_object", "contains_object_candidate"],
        spatial_relation="inside_container",
    )
    grounded = bundle["grounded_causal_graph"]
    workset = grounded["relation_hypothesis_workset"]
    candidate = workset["candidates"][0]
    evidence = workset["candidate_evidence"][0]
    _validate_declared_shape(candidate, "rcir_predicate.schema.json")
    _validate_declared_shape(evidence, "rcir_evidence_envelope.schema.json")
    require(validate_primitive(candidate)["valid"], "candidate predicate is invalid")
    require(validate_primitive(evidence)["valid"], "candidate evidence is invalid")
    provenance = candidate.get("provenance") or {}
    temporal = provenance.get("temporal_window") or {}
    require(
        candidate["name"] == "contained_in"
        and candidate["provenance"]["inference_kind"]
        == "explicit_spatial_marker"
        and evidence["source_type"] == "language_instruction"
        and evidence["fact_commit_eligible"] is False
        and set(("inference_kind", "premise_refs", "temporal_window"))
        <= set(provenance)
        and temporal.get("expires_on_world_revision_change") is True
        and grounded["ready_for_orchestration"] is False,
        f"explicit relation was not preserved as a non-factual candidate: {grounded}",
    )
    return {
        "selected": candidate["name"],
        "explicit_constraint_preceded_defaults": True,
        "physical_fact_committed": False,
        "missing_operator_contract_blocked": True,
    }


def verify_carrier_region_language_uses_functional_relation() -> dict:
    bundle = _compile(
        ["support_object", "receive_object", "transport_supported_payload"],
        spatial_relation="inside_container",
    )
    grounded = bundle["grounded_causal_graph"]
    workset = grounded["relation_hypothesis_workset"]
    candidate = workset["candidates"][0]
    require(
        candidate["name"] == "supported_by"
        and candidate["provenance"]["inference_rule"]
        == "inside_region_language_normalized_by_carrier_affordance"
        and grounded["ready_for_orchestration"] is True,
        f"carrier region language ignored functional affordance: {grounded}",
    )
    return {
        "language_region": "inside_container",
        "functional_relation": "supported_by",
        "carrier_affordance_used": True,
    }


def verify_revision_invalidation_and_single_authority() -> dict:
    bundle = _compile(["support_object", "contains_object_candidate"])
    situated_ref = bundle["situated_event_graph"]["graph_id"]
    workset = bundle["grounded_causal_graph"]["relation_hypothesis_workset"]
    artifacts = [
        workset["question_predicate"],
        *workset["candidates"],
        *workset["candidate_evidence"],
        workset["inquiry_contract"],
    ]
    invalidation = invalidate_versioned_artifacts(
        artifacts,
        new_world_revision=13,
        changed_refs={situated_ref},
    )
    require(
        invalidation["invalidated_ids"]
        and workset["ledger_digest_before"] == workset["ledger_digest_after"]
        and workset["ledger_access"] == "read_only_current_projection"
        and workset["fact_write_authority"]
        == "P016_via_WorldFactLedger_only"
        and workset["candidate_memory_lifecycle"]
        == "ephemeral_task_working_memory",
        f"revision or authority boundary failed: {workset}: {invalidation}",
    )
    return {
        "invalidated_artifacts": len(invalidation["invalidated_ids"]),
        "ledger_unchanged": True,
        "fact_writer": workset["fact_write_authority"],
        "candidate_memory": workset["candidate_memory_lifecycle"],
    }


def verify_natural_language_projection_and_runtime_gate() -> dict:
    default_session = start_session("home_humanoid", "hospitality_guest")
    default_runtime = SESSIONS[default_session["session_id"]]
    default_analysis = _compose_session_language(
        default_runtime,
        "把白色马克杯放到操作台B",
    )
    default_workset = default_analysis["rcir"]["grounded_causal_graph"][
        "relation_hypothesis_workset"
    ]
    default_candidate = default_workset["candidates"][0]

    explicit_session = start_session("home_humanoid", "hospitality_guest")
    blocked = begin_motion_command(
        explicit_session["session_id"],
        "把白色马克杯放到操作台A里面",
    )
    clarified = begin_motion_command(
        explicit_session["session_id"],
        "把白色马克杯放到操作台A上面",
    )
    require(
        default_candidate["name"] == "supported_by"
        and default_candidate["provenance"]["inference_kind"]
        == "defaulted_from_affordance"
        and blocked.get("status") == "relation_operator_contract_required"
        and blocked.get("runtime_fact_committed") is False
        and blocked.get("control_gateway") == "P018"
        and clarified.get("status") != "relation_operator_contract_required"
        and SESSIONS[explicit_session["session_id"]].get(
            "relation_hypothesis_dialogue"
        )
        is None,
        f"natural language relation projection bypassed RCIR: {default_workset}: {blocked}",
    )
    return {
        "omitted_marker_default": "supported_by",
        "explicit_inside_relation_preserved": True,
        "unsupported_relation_blocked_before_execution": True,
        "superseded_inquiry_released": True,
    }


def main() -> None:
    report = {
        "unique_affordance_default": verify_unique_affordance_default(),
        "ambiguity_inquiry": verify_ambiguity_enters_cognitive_inquiry(),
        "explicit_relation": verify_explicit_relation_and_schema(),
        "carrier_region_normalization": verify_carrier_region_language_uses_functional_relation(),
        "revision_and_authority": verify_revision_invalidation_and_single_authority(),
        "natural_language_runtime": verify_natural_language_projection_and_runtime_gate(),
    }
    print("RCIR relation hypothesis architecture validation passed.")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
