from __future__ import annotations

import json
from copy import deepcopy

from concept_core.cognitive_ir import (
    assert_perception_candidate_is_not_runtime_fact,
    compile_rcir_bundle,
    validate_rcir_bundle,
)
from concept_core.rcir_contracts import (
    apply_grounding_constraint,
    build_grounding_clarification_contract,
    build_portable_experience_contract,
    validate_portable_experience_contract,
)
from embodied_experience_store import _build_portable_record
from embodied_scene import (
    SESSIONS,
    _compose_session_language,
    begin_motion_command,
    get_session,
    start_session,
)
from validate_water_delivery_loop import drain_service


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_authoritative_bundle_contract() -> dict:
    session = start_session("home_humanoid", "hospitality_guest")
    runtime = SESSIONS[session["session_id"]]
    utterance = "用白色马克杯给我接一杯水"
    analysis = _compose_session_language(runtime, utterance)
    bundle = analysis.get("rcir") or {}
    validation = validate_rcir_bundle(bundle)
    encoded = json.dumps(bundle, ensure_ascii=False, sort_keys=True)
    situated = bundle.get("situated_event_graph") or {}
    ledger = bundle.get("world_fact_ledger") or {}
    grounded = bundle.get("grounded_causal_graph") or {}
    require(validation.get("valid") is True, f"RCIR bundle failed validation: {validation}")
    require(
        utterance not in encoded
        and situated.get("source_language", {}).get("raw_text_included") is False
        and situated.get("authority", {}).get("downstream_surface_reparse_allowed")
        is False,
        f"surface language leaked below the authoritative compiler boundary: {bundle}",
    )
    require(
        all(
            item.get("world_revision") == bundle.get("world_revision")
            for item in ledger.get("facts", [])
            if item.get("current_world_usable")
        )
        and ledger.get("authoritative_current_fact_ids"),
        f"world fact ledger mixed revisions or omitted current facts: {ledger}",
    )
    require(
        grounded.get("goal_relation") == "human_received_filled_container"
        and grounded.get("role_bindings", {}).get("theme", {}).get("entity_ref")
        == "mug_white"
        and grounded.get("role_bindings", {}).get("recipient", {}).get(
            "entity_ref"
        )
        == "guest"
        and grounded.get("current_fact_pruning_required") is True
        and grounded.get("direct_execution_allowed") is False,
        f"language, current grounding, and causal goal did not converge: {grounded}",
    )

    tampered = deepcopy(bundle)
    tampered["grounded_causal_graph"]["role_bindings"]["theme"][
        "entity_ref"
    ] = "forged_entity"
    tamper_validation = validate_rcir_bundle(tampered)
    require(
        "authority_digest_mismatch" in tamper_validation.get("errors", []),
        f"mutated RCIR remained authoritative: {tamper_validation}",
    )
    return {
        "bundle_id": bundle.get("bundle_id"),
        "goal_relation": grounded.get("goal_relation"),
        "theme": "mug_white",
        "recipient": "guest",
        "raw_text_included": False,
        "tamper_detected": True,
    }


def verify_rename_invariance_and_runtime_consumption() -> dict:
    session = start_session("home_humanoid", "hospitality_guest")
    session_id = session["session_id"]
    runtime = SESSIONS[session_id]
    next(
        item for item in runtime["runtime_objects"]
        if item["entity_id"] == "mug_white"
    )["label"] = "未登记饮具甲"
    started = begin_motion_command(
        session_id,
        "用乳白色马克杯给我接一杯水",
    )
    intent = runtime["long_horizon_intents"][runtime["active_intent_id"]]
    evidence = (intent.get("role_binding_evidence") or {}).get("theme") or {}
    require(
        started.get("status") == "motion_started"
        and intent.get("role_bindings", {}).get("theme") == "mug_white"
        and evidence.get("rcir_bundle_id")
        and evidence.get("rcir_authority_digest")
        and evidence.get("current_snapshot_revalidated") is True,
        f"runtime did not consume the authoritative RCIR binding: {started}: {evidence}",
    )
    pruning_audit = intent.get("current_fact_pruning_audit") or {}
    stage = intent.get("current_stage") or {}
    require(
        pruning_audit.get("invariant")
        == "every_recovery_reenters_current_fact_pruning"
        and pruning_audit.get("applied") is True
        and pruning_audit.get("old_path_reused") is False
        and stage.get("current_fact_pruning_applied") is True
        and stage.get("current_fact_pruning_world_revision")
        == runtime.get("world_revision"),
        f"long-intent stage bypassed current-fact pruning: {pruning_audit}: {stage}",
    )
    require(
        any(
            item.get("bundle_id") == evidence.get("rcir_bundle_id")
            and item.get("raw_language_included") is False
            for item in runtime.get("rcir_receipts", [])
        ),
        f"the consumed human-turn RCIR was not compacted before internal execution: {runtime.get('rcir_receipts')}",
    )
    outcomes = drain_service(started)
    completed = get_session(session_id)
    require(
        completed.get("current_rcir") is None
        and completed.get("rcir_receipts")
        and completed["rcir_receipts"][-1].get("trajectory_included") is False
        and completed["rcir_receipts"][-1].get("candidate_plan_included") is False,
        f"completed task retained RCIR working detail: {completed.get('current_rcir')}: {completed.get('rcir_receipts')}",
    )
    return {
        "entity_ref": "mug_white",
        "renamed_instance": True,
        "binding_source": "authoritative_rcir_grounded_causal_graph",
        "stage_facts": [item.get("terminal_fact") for item in outcomes],
        "working_graph_released": True,
    }


def verify_one_authoritative_graph_per_turn() -> dict:
    session = start_session("home_humanoid", "hospitality_guest")
    session_id = session["session_id"]
    runtime = SESSIONS[session_id]
    first = _compose_session_language(runtime, "拿起白色马克杯")["rcir"]
    second = _compose_session_language(runtime, "观察透明高脚玻璃杯")["rcir"]
    require(
        first.get("bundle_id") != second.get("bundle_id")
        and runtime.get("current_rcir", {}).get("bundle_id")
        == second.get("bundle_id")
        and any(
            item.get("bundle_id") == first.get("bundle_id")
            and item.get("release_reason")
            == "superseded_by_new_authoritative_turn"
            for item in runtime.get("rcir_receipts", [])
        ),
        f"multiple turn graphs remained simultaneously authoritative: {runtime.get('current_rcir')}: {runtime.get('rcir_receipts')}",
    )
    return {
        "first_bundle": first.get("bundle_id"),
        "current_bundle": second.get("bundle_id"),
        "single_authority": True,
    }


def verify_grounding_clarification_loop() -> dict:
    candidates = [
        {
            "entity_ref": "entity_a",
            "world_revision": 7,
            "observed_attributes": {"color": "white", "material": "ceramic"},
        },
        {
            "entity_ref": "entity_b",
            "world_revision": 7,
            "observed_attributes": {"color": "clear", "material": "glass"},
        },
    ]
    contract = build_grounding_clarification_contract(
        "theme", candidates, world_revision=7
    )
    requested = contract.get("requested_constraint") or {}
    resolved = apply_grounding_constraint(
        contract,
        observation_field=requested.get("observation_field"),
        value=(requested.get("accepted_values") or [None])[0],
        candidates=candidates,
        world_revision=7,
    )
    require(
        contract.get("status") == "awaiting_observable_constraint"
        and requested.get("minimum_information_required") is True
        and resolved.get("status") == "resolved"
        and resolved.get("resolved_entity_ref") in {"entity_a", "entity_b"}
        and resolved.get("runtime_fact_committed") is False,
        f"generic grounding clarification contract failed: {contract}: {resolved}",
    )
    return {
        "requested_field": requested.get("observation_field"),
        "resolved_entity_ref": resolved.get("resolved_entity_ref"),
        "raw_language_required_downstream": False,
    }


def verify_portable_experience_contract() -> dict:
    experience = {
        "experience_id": "experience_contract_test",
        "status": "trusted_local_experience",
        "source_goal_utterance": "arbitrary source language",
        "target_binding": {"concept_id": "portable_container", "entity_ref": "old_entity"},
        "goal_fact": "payload_delivered",
        "source_concept_contract": {
            "semantic_roles": {
                "theme": {
                    "concept_id": "portable_container",
                    "entity_type": "container",
                    "entity_ref": "old_entity",
                    "surface_form": "old name",
                }
            }
        },
        "process_chain": ["acquire", "transform", "deliver"],
        "effect_contract": {
            "requires": ["theme_grounded"],
            "produces": ["payload_delivered"],
            "verification": ["recipient_possession_verified"],
        },
        "invariant_contract": {
            "storage_policy": "store_invariants_not_concrete_teleoperation_parameters",
            "forbidden_storage": [
                "absolute_world_coordinates",
                "robot_joint_angles",
                "fixed_action_durations",
                "teacher_key_sequence",
                "single_body_trajectory",
            ],
            "topology_invariants": ["acquire_before_transform_before_deliver"],
        },
        "validation_history": [
            {"physical_fact_verified": True, "human_accepted": True}
        ],
    }
    contract = build_portable_experience_contract(experience)
    validation = validate_portable_experience_contract(contract)
    portable_record = _build_portable_record(experience)
    encoded = json.dumps(contract, ensure_ascii=False, sort_keys=True)
    require(
        validation.get("valid") is True
        and "old_entity" not in encoded
        and "arbitrary source language" not in encoded
        and contract.get("migration_policy", {}).get(
            "rebind_all_roles_from_current_world_evidence"
        )
        is True
        and portable_record.get("portable_experience_contract", {}).get(
            "contract_digest"
        )
        and portable_record.get("execution_authority", {}).get("source")
        == "portable_experience_contract",
        f"portable experience contract leaked old bindings: {contract}: {portable_record}",
    )
    return {
        "contract_digest": contract.get("contract_digest"),
        "old_entity_ref_included": False,
        "raw_goal_language_included": False,
    }


def verify_five_architecture_invariants() -> dict:
    session = start_session("home_humanoid", "hospitality_guest")
    runtime = SESSIONS[session["session_id"]]
    analysis = _compose_session_language(runtime, "我已经完成了这个动作")
    bundle = analysis["rcir"]
    situated = bundle["situated_event_graph"]
    require(
        all(
            item.get("physical_fact_committed") is False
            for item in [
                *situated.get("events", []),
                *situated.get("reported_events", []),
                *situated.get("historical_event_constraints", []),
            ]
        ),
        f"language committed a physical fact: {situated}",
    )
    bad_observation = deepcopy(analysis["observation_evidence"])
    bad_observation["changes_execution_state"] = True
    try:
        assert_perception_candidate_is_not_runtime_fact(
            bad_observation, bundle["world_fact_ledger"]
        )
    except AssertionError as error:
        perception_guard = str(error) == "observation_candidate_changed_execution_state"
    else:
        perception_guard = False
    require(perception_guard, "perception candidate was allowed to mutate runtime state")

    relation_analysis = {
        "speech_act": "task_request",
        "canonical_frame": {"operators": ["grasp_object"], "goal_relation": "object_in_gripper"},
        "semantic_constraint_frame": {
            "roles": {"theme": {"role": "theme", "concept_id": "generic_object", "constraints": []}}
        },
        "grounded_intent_frame": {
            "roles": {
                "theme": {
                    "status": "resolved",
                    "world_revision": 11,
                    "observation_evidence_set_id": "observation_current",
                    "binding": {
                        "entity_ref": "category_candidate",
                        "binding_basis": "current_concept_compatible_candidate",
                        "evidence_strength": 100,
                    },
                }
            }
        },
        "context_projection": {
            "relational_role_candidates": {
                "theme": [
                    {"entity_ref": "currently_verified_entity", "relation": "held_by", "world_revision": 11}
                ]
            }
        },
        "observation_evidence": {
            "evidence_set_id": "observation_current",
            "epistemic_only": True,
            "changes_execution_state": False,
        },
    }
    precedence_bundle = compile_rcir_bundle(
        "synthetic boundary input",
        relation_analysis,
        current_facts=[],
        world_revision=11,
        interaction_turn=1,
        interaction_role_bindings={},
    )
    selected = precedence_bundle["grounded_causal_graph"]["role_bindings"]["theme"]
    require(
        selected.get("entity_ref") == "currently_verified_entity"
        and selected.get("evidence", {}).get("precedence_assertion")
        == "current_verified_relation_precedes_history_and_category",
        f"current verified relation did not precede category evidence: {selected}",
    )
    invariants = precedence_bundle.get("architecture_invariants") or {}
    require(
        all(
            invariants.get(name) is True
            for name in (
                "language_does_not_commit_physical_fact",
                "perception_candidate_is_not_runtime_fact",
                "downstream_does_not_reparse_surface_text",
                "current_verified_relation_precedes_history_and_category",
                "every_recovery_reenters_current_fact_pruning",
            )
        ),
        f"priority architecture invariants were not declared: {invariants}",
    )
    return {"priority_invariants": 5, "all_enforced": True}


def main() -> None:
    report = {
        "authoritative_bundle": verify_authoritative_bundle_contract(),
        "runtime_consumption": verify_rename_invariance_and_runtime_consumption(),
        "single_turn_authority": verify_one_authoritative_graph_per_turn(),
        "grounding_clarification": verify_grounding_clarification_loop(),
        "portable_experience": verify_portable_experience_contract(),
        "architecture_invariants": verify_five_architecture_invariants(),
    }
    print("RCIR minimal architecture validation passed.")
    print(report)


if __name__ == "__main__":
    main()
