from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from api_server import (
    build_binding_candidates,
    build_execution_feasibility,
    build_initial_runtime_world_state,
    build_invariant_contract,
    dispatch_execution_loop_payload,
    get_cognitive_model,
    get_process_chain_for_intent,
    migrate_experience,
    translate_intent,
)


OUTPUT = Path(__file__).resolve().parent.parent / "output" / "rell_sample" / "p017_generalization_pressure"
UTTERANCE = "到水源处接一杯水"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def evaluate(model: dict, profile: dict) -> tuple[dict, dict]:
    intent = translate_intent(UTTERANCE)
    state = build_initial_runtime_world_state(model, intent)
    contract = build_invariant_contract(get_process_chain_for_intent(intent))
    binding = build_binding_candidates(intent, model, state, profile, contract)
    feasibility = build_execution_feasibility(intent, binding, state, profile)
    return binding, feasibility


def main() -> None:
    base_model = get_cognitive_model("site_b_corridor")
    full_profile = {
        "executor_id": "pressure_mobile_manipulator",
        "executor_type": "mobile_manipulator",
        "supported_actions": ["navigate_to_region", "grasp_object", "fill_container", "pour_container"],
    }

    unique_binding, unique_feasibility = evaluate(base_model, full_profile)
    require(unique_feasibility.get("result") == "executable", f"unique eligible candidates must execute: {unique_feasibility}")
    rejected_reasons = {item.get("reason") for item in unique_binding.get("rejected_candidates", [])}
    require({"unreachable", "unavailable"}.issubset(rejected_reasons), f"invalid candidates must be explicitly filtered: {unique_binding}")

    ambiguous_model = deepcopy(base_model)
    ambiguous_model["object_region_index"]["site_b_second_tumbler"] = {
        "object_type": "tumbler",
        "region_ref": "site_b_preparation_surface",
        "affordances": ["receive_liquid", "graspable"],
        "state_facts": ["cup_empty"],
    }
    ambiguous_model["binding_candidate_sets"]["TARGET_GRASPABLE_CONTAINER"][1] = {
        "entity_ref": "site_b_second_tumbler",
        "availability": "available",
        "reachable": True,
        "confidence": 0.94,
    }
    ambiguous_binding, ambiguous_feasibility = evaluate(ambiguous_model, full_profile)
    require(ambiguous_feasibility.get("result") == "requires_human_confirmation", f"two eligible cups must require confirmation: {ambiguous_feasibility}")
    require(ambiguous_binding.get("ambiguous_bindings"), f"ambiguous candidates must be exposed: {ambiguous_binding}")

    unavailable_model = deepcopy(base_model)
    for slot_id in ["TARGET_LIQUID_SOURCE_REGION", "SOURCE_LIQUID_RESOURCE_REGION"]:
        for candidate in unavailable_model["binding_candidate_sets"][slot_id]:
            candidate["availability"] = "unavailable"
    unavailable_binding, unavailable_feasibility = evaluate(unavailable_model, full_profile)
    require(unavailable_feasibility.get("result") in {"partially_inexecutable", "infeasible"}, f"no water source must block full execution: {unavailable_feasibility}")
    require(any(item.get("reason") == "missing_binding_target" for item in unavailable_feasibility.get("infeasible_reasons", [])), f"missing source binding must be explained: {unavailable_feasibility}")

    mobile_base = {"executor_id": "navigation_only_base", "executor_type": "mobile_base", "supported_actions": ["navigate_to_region"]}
    _, mobile_base_feasibility = evaluate(base_model, mobile_base)
    require(any(item.get("capability") == "grasp_object" for item in mobile_base_feasibility.get("infeasible_reasons", [])), f"navigation-only body must report grasp gap: {mobile_base_feasibility}")

    fixed_arm = {"executor_id": "fixed_arm", "executor_type": "fixed_robot_arm", "supported_actions": ["grasp_object", "fill_container", "pour_container"]}
    _, fixed_arm_feasibility = evaluate(base_model, fixed_arm)
    require(any(item.get("capability") == "navigate_to_region" for item in fixed_arm_feasibility.get("infeasible_reasons", [])), f"fixed arm must report navigation gap: {fixed_arm_feasibility}")

    migration = migrate_experience(UTTERANCE, full_profile, "site_b_corridor")
    dispatch = dispatch_execution_loop_payload(migration["execution_loop_payload"], "robot_sdk")
    generalization = dispatch.get("generalization_result", {})
    require(generalization.get("target_fact_established"), f"successful migration must write target-fact result: {dispatch}")
    require(generalization.get("public_experience_update_policy") == "record_validation_history_only_no_single_run_contract_rewrite", f"single result must not rewrite public experience: {generalization}")

    report = {
        "schema_version": "1.0.0",
        "unique_candidate_filtering": {"binding": unique_binding, "feasibility": unique_feasibility},
        "ambiguous_candidate_confirmation": {"binding": ambiguous_binding, "feasibility": ambiguous_feasibility},
        "unavailable_source": {"binding": unavailable_binding, "feasibility": unavailable_feasibility},
        "executor_capability_gaps": {
            "mobile_base": mobile_base_feasibility,
            "fixed_arm": fixed_arm_feasibility,
        },
        "generalization_result_writeback": generalization,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "pressure_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("P017 generalization pressure validation passed.")
    print(f"Output: {OUTPUT / 'pressure_report.json'}")


if __name__ == "__main__":
    main()
