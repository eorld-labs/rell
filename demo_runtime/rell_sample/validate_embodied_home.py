from __future__ import annotations

import json
import math
import os
from concept_core.lightweight_orchestrator import build_lightweight_causal_candidate
from concept_core.concept_gap_dialogue import extract_compositional_semantics
from pathlib import Path

from concept_core.perceptual_grounding import activate_task_perception, ground_task_observations
from embodied_scene import SESSIONS, begin_learned_replay, begin_motion_command, begin_persisted_experience_replay, begin_teaching_control, build_factory_concept_catalog, build_factory_object_catalog, build_factory_orchestrator_catalog, build_factory_state_fact_catalog, build_visual_concept_pack_catalog, confirm_pending_motion, evaluate_learned_replay, execute_command, finish_embodied_teaching, load_scene, record_teaching_signal, set_perception_scenario, set_protection_policy, set_stool, start_embodied_teaching, start_session, step_motion_command


OUTPUT = Path(__file__).resolve().parents[1] / "output" / "rell_sample" / "embodied_home"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def drain_motion(started: dict) -> dict:
    job_id = started.get("job_id")
    require(bool(job_id), f"expected motion job: {started}")
    while True:
        step = step_motion_command(job_id)
        if step.get("status") == "motion_completed":
            return step
        require(step.get("status") == "frame_verified_and_committed", f"motion did not commit safely: {step}")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    test_store = OUTPUT / "trusted_local_experience_test_store.json"
    test_store.unlink(missing_ok=True)
    os.environ["RELL_EMBODIED_EXPERIENCE_STORE"] = str(test_store)
    scene = load_scene()
    require(len(scene["semantic_regions"]) >= 3, "home scene needs connected semantic regions")
    require(all(region.get("center") and region.get("size") for region in scene["semantic_regions"]), "semantic regions need 3D volume bindings")
    profile = scene["executor_profiles"]["home_mobile_manipulator"]
    coordinate_contract = scene["coordinate_contract"]
    require(coordinate_contract["semantic_ground_frame"]["left_axis"] == "+y", "body left axis must be semantic +y")
    require(coordinate_contract["threejs_mapping"]["three_z"] == "negative_semantic_y", "render mapping must preserve body left/right handedness")
    require(coordinate_contract["screen_direction_is_not_a_body_direction"], "screen direction must not define body direction")
    require(profile["body_envelope"]["radius_m"] > 0, "body envelope must constrain clearance")
    require(profile["turning_radius_m"] > 0 and profile["arm_reach_m"] > 0, "body portrait must expose mobility and reach")

    factory_catalog = build_factory_concept_catalog()
    require(factory_catalog["concept_count"] >= 13, f"factory event concept skeleton is too narrow: {factory_catalog}")
    require(not factory_catalog["storage_boundary"]["direct_execution_allowed"], f"factory concepts bypass orchestration: {factory_catalog}")
    serialized_factory = json.dumps(factory_catalog, ensure_ascii=False)
    for forbidden in ["absolute_coordinates", "joint_angles", "fixed_duration", "single_body_trajectory"]:
        require(forbidden in serialized_factory, f"factory concept storage boundary omitted {forbidden}: {factory_catalog}")

    object_catalog = build_factory_object_catalog()
    require(len(object_catalog["object_concepts"]) >= 5, f"functional object catalog is too narrow: {object_catalog}")
    require(len(object_catalog["relation_concepts"]) >= 7, f"factory relation skeleton is too narrow: {object_catalog}")
    require(object_catalog["shared_boundary"]["appearance_is_not_role_proof"], f"appearance incorrectly proves functional role: {object_catalog}")
    require(object_catalog["shared_boundary"]["runtime_relation_requires_current_observation_or_physical_verification"], f"possible relation was treated as current fact: {object_catalog}")
    visual_catalog = build_visual_concept_pack_catalog()
    apple_pack = next(item for item in visual_catalog["packs"] if item["concept_id"] == "concept_edible_apple")
    require(apple_pack["load_policy"] == "factory_resident", f"apple visual pack is not factory resident: {visual_catalog}")
    require(not apple_pack["reference_samples"] and not apple_pack["reference_sample_policy"]["single_image_can_define_concept"], f"visual sample was conflated with the apple concept: {apple_pack}")
    require(visual_catalog["boundary"]["visual_pack_is_not_action_experience"], f"visual pack entered experience layer: {visual_catalog}")

    state_catalog = build_factory_state_fact_catalog()
    require(len(state_catalog["state_fact_concepts"]) >= 10, f"factory state fact vocabulary is too narrow: {state_catalog}")
    require(state_catalog["shared_boundary"]["closed_world_assumption_forbidden"], f"state facts used closed-world reasoning: {state_catalog}")
    require(state_catalog["shared_boundary"]["absence_of_observation_is_not_negative_fact"], f"missing observation became a negative fact: {state_catalog}")
    all_factory_requirements = {
        fact
        for concept in factory_catalog["concepts"]
        for fact in concept["effect_contract"].get("requires", [])
    }
    uncovered_requirements = sorted(all_factory_requirements - set(state_catalog["prerequisite_strategies"]))
    require(not uncovered_requirements, f"factory event prerequisites lack recovery strategies: {uncovered_requirements}")

    observation_session = start_session()
    open_observation = execute_command(observation_session["session_id"], "你现在看到了什么")
    apple_observation = next(item for item in open_observation["recognized_object_candidates"] if item["concept_id"] == "concept_edible_apple")
    require(apple_observation["spatial_relation_candidate"] == "on_ground_candidate", f"apple ground relation was not observed: {open_observation}")
    require(apple_observation["observation_source"] == "simulated_rgbd_adapter_without_semantic_label_access", f"recognizer read semantic scene truth: {open_observation}")
    require(open_observation["unknown_object_candidates"], f"open-world observation forced every object into a known class: {open_observation}")
    require(not open_observation["runtime_fact_committed"] and not open_observation["direct_execution_allowed"], f"visual candidate became executable fact: {open_observation}")
    relocation_preview = execute_command(observation_session["session_id"], "把苹果从地上放到桌子上")
    require(relocation_preview["status"] == "observed_goal_causal_preview", f"observed object did not enter causal preview: {relocation_preview}")
    require(relocation_preview["goal_contract"]["destroys"] == ["object_on_ground", "object_in_gripper"], f"relocation goal omitted destroyed facts: {relocation_preview}")
    require(relocation_preview["causal_candidate"]["candidate_process_chain"][-1] == "place_object", f"placement was not the goal operator: {relocation_preview}")
    require("grasp_object" in relocation_preview["causal_candidate"]["candidate_process_chain"], f"solver did not backfill grasp prerequisite: {relocation_preview}")
    place_node = next(item for item in relocation_preview["causal_candidate"]["nodes"] if item["operator"] == "place_object")
    require(place_node["capability_available"] and place_node["gate"] == "blocked_by_missing_experience", f"body capability and placement experience gap were conflated: {relocation_preview}")
    require(not relocation_preview["direct_execution_allowed"], f"visual causal preview executed directly: {relocation_preview}")

    composed = extract_compositional_semantics("如果水果散落，就归整苹果，让苹果和其他水果都在收纳区，看到所有水果都在收纳区就算完成")
    require(composed["precondition_descriptions"] == ["水果散落"], f"precondition connector not parsed: {composed}")
    require(composed["desired_postcondition"] == "苹果和其他水果都在收纳区", f"postcondition connector not parsed: {composed}")
    require(composed["verification_condition"] == "看到所有水果都在收纳区", f"verification connector not parsed: {composed}")
    until_composed = extract_compositional_semantics("归整苹果，直到所有水果都在收纳区为止")
    require(until_composed["desired_postcondition"] == "所有水果都在收纳区" and until_composed["verification_condition"] == "所有水果都在收纳区", f"until boundary did not provide goal and verification: {until_composed}")
    non_terminal_observation = extract_compositional_semantics("归整苹果，看到桌子")
    require(non_terminal_observation["verification_condition"] is None, f"ordinary observation was overinterpreted as verification: {non_terminal_observation}")

    orchestrator_catalog = build_factory_orchestrator_catalog()
    require(orchestrator_catalog["boundary"]["fixed_task_script_forbidden"], f"factory orchestrator regressed to scripts: {orchestrator_catalog}")
    require(orchestrator_catalog["boundary"]["backward_chain_from_current_fact_gap"], f"orchestrator is not fact-gap-driven: {orchestrator_catalog}")
    require(orchestrator_catalog["boundary"]["business_event_specific_solver_code_forbidden"], f"orchestrator still encodes business events in solver: {orchestrator_catalog}")
    require(orchestrator_catalog["boundary"]["event_concepts_register_automatically"], f"event contracts do not auto-register: {orchestrator_catalog}")
    require(orchestrator_catalog["fact_implications"]["gripper_empty"] == ["gripper_available"], f"basic fact implication missing: {orchestrator_catalog}")
    require(orchestrator_catalog["registry_summary"]["compiled_from"]["event_concept_count"] == factory_catalog["concept_count"], f"not all factory events entered causal registry: {orchestrator_catalog}")

    synthetic_event = {
        "concept_id": "synthetic_event_heat_object",
        "display_name": "测试加热事件",
        "capability": "heat_object",
        "concept_kernel": {
            "operator": "heat_object",
            "effect_contract": {
                "requires": ["object_grounded"],
                "produces": ["object_temperature_above_target"],
                "destroys": ["object_temperature_below_target"],
                "verification": ["temperature_sensor_above_target"],
            },
        },
    }
    synthetic_goal = {
        "operator": "serve_warm_object",
        "recognized_goal_fact": "warm_object_served",
        "required_capability": "serve_object",
        "effect_contract": {"requires": ["object_temperature_above_target"], "produces": ["warm_object_served"], "destroys": []},
    }
    synthetic_plan = build_lightweight_causal_candidate(
        goal_concept=synthetic_goal,
        fact_snapshot={"world_revision": 0, "established_facts": ["object_grounded"], "negated_facts": []},
        supported_capabilities=["heat_object", "serve_object"],
        available_experience_capabilities=["heat_object", "serve_object"],
        event_concepts=[synthetic_event],
    )
    require(synthetic_plan["candidate_process_chain"] == ["heat_object", "serve_warm_object"], f"new event contract required solver-specific code: {synthetic_plan}")
    require(not synthetic_plan["unresolved_facts"] and synthetic_plan["candidate_status"] == "candidate_ready_for_runtime_arbitration", f"synthetic contract did not auto-register: {synthetic_plan}")

    zero_experience_session = start_session()
    zero_id = zero_experience_session["session_id"]
    SESSIONS[zero_id]["available_local_experiences"] = []
    understood_without_experience = execute_command(zero_id, "拿起苹果")
    require(understood_without_experience["status"] == "factory_concept_recognized_execution_gap", f"zero-experience robot did not recognize basic event: {understood_without_experience}")
    grasp_diagnosis = understood_without_experience["factory_concept"]
    require(grasp_diagnosis["concept_id"] == "factory_event_grasp", f"wrong factory concept selected: {understood_without_experience}")
    require(grasp_diagnosis["reason_code"] == "execution_experience_not_available", f"experience absence was not distinguished: {understood_without_experience}")
    require(grasp_diagnosis["executor_capability_available"] and not grasp_diagnosis["applicable_experience_available"], f"body capability and experience were conflated: {understood_without_experience}")
    require(understood_without_experience["post_action"]["teaching_available"], f"recoverable gap did not offer teaching: {understood_without_experience}")
    require(not grasp_diagnosis["direct_execution_allowed"], f"factory semantics directly executed without experience: {understood_without_experience}")
    apple_gaps = understood_without_experience["prerequisite_analysis"]
    reach_gap = next(item for item in apple_gaps["gaps"] if item["fact"] == "object_within_reach")
    require(reach_gap["truth_status"] == "verified_false" and reach_gap["producer"] == "navigate_until_target_within_reach", f"out-of-reach object did not generate navigation subgoal: {understood_without_experience}")
    require("object_grounded" in understood_without_experience["runtime_fact_snapshot"]["established_facts"], f"grounded target missing from runtime facts: {understood_without_experience}")
    zero_candidate = understood_without_experience["causal_candidate"]
    require(zero_candidate["candidate_process_chain"] == ["navigate_until_target_within_reach", "grasp_object"], f"fact-gap backward chain is incorrect: {zero_candidate}")
    require(zero_candidate["nodes"][0]["gate"] == "candidate_ready_for_orchestration", f"available navigation subgoal was blocked: {zero_candidate}")
    require(zero_candidate["nodes"][1]["gate"] == "blocked_by_missing_experience", f"missing grasp experience was not gated: {zero_candidate}")
    require(zero_candidate["candidate_only"] and not zero_candidate["direct_execution_allowed"] and not zero_candidate["runtime_fact_committed"], f"candidate plan bypassed runtime verification: {zero_candidate}")
    require(not zero_candidate["cycles"] and not zero_candidate["unresolved_facts"], f"basic grasp chain is structurally incomplete: {zero_candidate}")
    require(zero_candidate["planner_type"] == "contract_compiled_backward_causal_search", f"legacy enumerated solver is still active: {zero_candidate}")
    require(zero_candidate["search_metrics"]["total_solver_ms"] >= 0, f"solver latency audit missing: {zero_candidate}")
    require(zero_candidate["decision_latency"]["input_to_candidate_decision_ms"] >= zero_candidate["search_metrics"]["total_solver_ms"], f"end-to-end decision latency is inconsistent: {zero_candidate}")
    second_zero_result = execute_command(zero_id, "拿起苹果")
    require(second_zero_result["causal_candidate"]["search_metrics"]["registry_cache_hit"], f"unchanged concept and experience contracts were recompiled: {second_zero_result}")

    experienced_session = start_session()
    experienced_result = execute_command(experienced_session["session_id"], "拿起苹果")
    experienced_candidate = experienced_result["causal_candidate"]
    require(experienced_candidate["candidate_process_chain"] == zero_candidate["candidate_process_chain"], f"experience changed causal structure instead of gate state: {experienced_candidate}")
    if experienced_session["available_local_experiences"]:
        require(experienced_candidate["nodes"][-1]["gate"] == "candidate_ready_for_orchestration", f"trusted grasp experience did not unlock candidate gate: {experienced_candidate}")
        require(experienced_candidate["candidate_status"] == "candidate_ready_for_runtime_arbitration", f"fully supported candidate did not reenter arbitration: {experienced_candidate}")
        require(not experienced_candidate["direct_execution_allowed"], f"trusted experience directly executed from concept planner: {experienced_candidate}")

    fixed_asset_gap = execute_command(zero_id, "拿起饮水机")
    require(fixed_asset_gap["factory_concept"]["reason_code"] == "entity_not_compatible_with_semantic_role", f"fixed asset was treated as graspable: {fixed_asset_gap}")
    fixed_incompatibility = fixed_asset_gap["factory_concept"]["incompatible_roles"][0]
    require("fixed_asset" in fixed_incompatibility["forbidden_properties_present"], f"fixed property was not used in role rejection: {fixed_asset_gap}")
    require(set(fixed_incompatibility["missing_affordances"]) == {"graspable", "movable"}, f"grasp role missing affordances not explained: {fixed_asset_gap}")

    support_gap = execute_command(zero_id, "把杯子放到苹果上")
    require(support_gap["factory_concept"]["reason_code"] == "entity_not_compatible_with_semantic_role", f"apple was accepted as support surface: {support_gap}")
    destination_gap = next(item for item in support_gap["factory_concept"]["incompatible_roles"] if item["role"] == "destination")
    require("support_object" in destination_gap["missing_affordances"], f"support affordance gap not exposed: {support_gap}")
    require(all(item["entity_ref"] != "apple_a" for item in support_gap["factory_concept"]["incompatible_roles"] if item["role"] == "object"), f"destination was incorrectly rebound as moved object: {support_gap}")
    require(support_gap["causal_candidate"]["candidate_process_chain"] == ["navigate_until_target_within_reach", "grasp_object", "compute_current_body_placement_candidate", "place_object"], f"geometric placement mechanism missing from causal chain: {support_gap}")

    body_gap = execute_command(zero_id, "擦操作台")
    require(body_gap["factory_concept"]["reason_code"] == "executor_capability_not_available", f"missing body capability was not explained: {body_gap}")
    require(body_gap["post_action"]["human_help_suggested"] and not body_gap["post_action"]["teaching_available"], f"teaching was offered for impossible body capability: {body_gap}")

    role_gap = execute_command(zero_id, "打开冰箱")
    require(role_gap["factory_concept"]["reason_code"] == "required_semantic_roles_not_grounded", f"unknown object was not distinguished from skill absence: {role_gap}")
    require(role_gap["post_action"]["clarification_required"], f"role gap did not ask for grounding: {role_gap}")

    unknown_session = start_session()
    unknown_id = unknown_session["session_id"]
    unknown_gap = execute_command(unknown_id, "归整苹果")
    require(unknown_gap["status"] == "concept_gap_clarification_required", f"unknown event did not expose concept gap: {unknown_gap}")
    require(unknown_gap["concept_gap"]["understanding_status"] == "operator_and_goal_fact_unknown", f"unknown concept overclaimed understanding: {unknown_gap}")
    require(unknown_gap["concept_gap"]["recognized_entities"][0]["entity_ref"] == "apple_a", f"unknown event failed to reuse known object concepts: {unknown_gap}")
    require(unknown_gap["concept_gap"]["unknown_action_surface"] == "归整", f"unknown action surface was not isolated: {unknown_gap}")
    require(unknown_gap["knowledge_self_report"]["known"][0]["value"] == "苹果", f"unknown task did not expose known boundary: {unknown_gap}")
    require(unknown_gap["knowledge_self_report"]["requested_human_input"] == unknown_gap["prompt"], f"unknown task self-report did not request minimum feedback: {unknown_gap}")
    require(not unknown_gap["post_action"]["teaching_available"] and unknown_gap["post_action"]["clarification_required"], f"teaching was offered before goal semantics were understood: {unknown_gap}")
    require(unknown_gap["session"]["concept_gap_dialogue"]["pending_slot"] == "desired_postcondition", f"minimum causal question order incorrect: {unknown_gap}")

    postcondition_answer = execute_command(unknown_id, "苹果和其他水果放在同一个收纳区域")
    require(postcondition_answer["status"] == "concept_gap_clarification_required", f"postcondition answer prematurely compiled contract: {postcondition_answer}")
    require(postcondition_answer["concept_gap_analysis"]["pending_slot"] == "verification_condition", f"verification was not requested next: {postcondition_answer}")
    require(postcondition_answer["concept_gap_analysis"]["slots"]["desired_postcondition"] == "苹果和其他水果放在同一个收纳区域", f"postcondition was not retained: {postcondition_answer}")

    verification_answer = execute_command(unknown_id, "视觉看到所有水果都位于水果收纳区内")
    require(verification_answer["status"] == "temporary_effect_contract_compiled", f"minimum causal slots did not compile temporary contract: {verification_answer}")
    temporary = verification_answer["temporary_effect_contract"]
    require(temporary["language_trigger"] == "归整" and temporary["semantic_roles"]["target"]["entity_ref"] == "apple_a", f"temporary concept lost language or object binding: {temporary}")
    require(temporary["effect_contract"]["human_readable_postcondition"] == "苹果和其他水果放在同一个收纳区域", f"temporary goal fact lost human semantics: {temporary}")
    require(temporary["knowledge_boundary"]["goal_and_verification_understood"] and not temporary["knowledge_boundary"]["operator_mechanism_known"], f"goal understanding was conflated with knowing how: {temporary}")
    require(temporary["knowledge_boundary"]["requires_embodied_teaching"] and not temporary["knowledge_boundary"]["teaching_goal_verification_adapter_available"] and temporary["knowledge_boundary"]["not_promoted_to_factory_library"], f"teaching need and current teaching availability were conflated: {temporary}")
    require(not verification_answer["post_action"]["teaching_available"] and not temporary["direct_execution_allowed"], f"unsupported goal entered teaching without a verifier: {verification_answer}")
    require(verification_answer["knowledge_self_report"]["next_safe_route"] == "teaching_goal_verification_adapter_required", f"unsupported goal did not expose verifier gap: {verification_answer}")

    motion_gap_session = start_session()
    motion_gap_id = motion_gap_session["session_id"]
    motion_gap_first = begin_motion_command(motion_gap_id, "归整苹果")["immediate_result"]
    require(motion_gap_first["status"] == "concept_gap_clarification_required", f"motion entry did not start gap dialogue: {motion_gap_first}")
    require(SESSIONS[motion_gap_id]["concept_gap_dialogue"]["pending_slot"] == "desired_postcondition", f"motion transaction rolled back cognitive dialogue: {SESSIONS[motion_gap_id]}")
    motion_gap_second = begin_motion_command(motion_gap_id, "苹果和其他水果放在同一个收纳区域")["immediate_result"]
    require(motion_gap_second["concept_gap_analysis"]["pending_slot"] == "verification_condition", f"motion entry rerouted clarification answer as a new task: {motion_gap_second}")
    motion_gap_third = begin_motion_command(motion_gap_id, "视觉看到所有水果都位于水果收纳区内")["immediate_result"]
    require(motion_gap_third["status"] == "temporary_effect_contract_compiled", f"motion entry failed multi-turn contract compilation: {motion_gap_third}")

    no_entity_gap = begin_motion_command(start_session()["session_id"], "跳起来")["immediate_result"]
    require(no_entity_gap["status"] == "concept_gap_clarification_required" and "哪个对象" in no_entity_gap["prompt"], f"unknown task without entity crashed or skipped target clarification: {no_entity_gap}")

    one_turn_gap_session = start_session()
    one_turn_gap = begin_motion_command(
        one_turn_gap_session["session_id"],
        "如果水果散落，就归整苹果，让苹果和其他水果都在收纳区，看到所有水果都在收纳区就算完成",
    )["immediate_result"]
    require(one_turn_gap["status"] == "temporary_effect_contract_compiled", f"explicit compositional semantics did not compile in one turn: {one_turn_gap}")
    one_turn_contract = one_turn_gap["temporary_effect_contract"]
    require(one_turn_contract["effect_contract"]["human_readable_postcondition"] == "苹果和其他水果都在收纳区", f"one-turn postcondition lost: {one_turn_contract}")
    require(one_turn_contract["effect_contract"]["verification"] == ["human_described_verification:看到所有水果都在收纳区"], f"one-turn verification lost: {one_turn_contract}")
    require("human_described_precondition:水果散落" in one_turn_contract["effect_contract"]["requires"], f"one-turn precondition lost: {one_turn_contract}")
    require(not one_turn_gap["post_action"]["teaching_available"] and not one_turn_contract["direct_execution_allowed"], f"unsupported one-turn goal entered teaching: {one_turn_gap}")

    pronoun_gap = begin_motion_command(
        start_session()["session_id"],
        "归整苹果，让它和其他水果在一起，视觉看到都在收纳区就算完成",
    )["immediate_result"]
    require(pronoun_gap["status"] == "temporary_effect_contract_compiled", f"local pronoun blocked one-turn contract: {pronoun_gap}")
    require(pronoun_gap["temporary_effect_contract"]["effect_contract"]["human_readable_postcondition"] == "苹果和其他水果在一起", f"local pronoun was not resolved to unique target: {pronoun_gap}")

    perception_session = start_session()
    perception_started = begin_motion_command(perception_session["session_id"], "去桌子上拿杯子")
    perception = perception_started["immediate_result"]
    require(perception["status"] == "perception_grounded_candidate", f"task-conditioned perception did not ground: {perception}")
    require(perception["perception_observation"]["sensor_contract"]["reasoner_scene_truth_access"] is False, f"reasoner bypassed observation DTO: {perception}")
    require(perception["concept_grounding"]["grounding_status"] == "spatially_grounded", f"cup/support relation did not ground: {perception}")
    require(perception["concept_grounding"]["candidate_only"] and not perception["concept_grounding"]["direct_execution_allowed"], f"perception candidate gained execution authority: {perception}")
    require(not perception["concept_grounding"]["runtime_fact_committed"], f"visual candidate was committed as fact: {perception}")
    bound_roles = {item["role"]: item["entity_ref"] for item in perception["concept_grounding"]["candidate_bindings"]}
    require(bound_roles == {"target": "cup_a", "support": "counter_a"}, f"wrong grounded instances: {perception}")
    require(perception["concept_grounding"]["relation_evidence"]["relation"] == "on_top_of", f"support relation evidence missing: {perception}")
    require(perception["perception_observation"]["semantically_suppressed_tracks"], f"task attention did not suppress irrelevant semantics: {perception}")
    require(perception["perception_observation"]["safety_channels_always_on"], f"safety channels were pruned with task attention: {perception}")
    require(perception["causal_preview"]["planning_is_established_fact"] is False, f"causal preview became a future fact: {perception}")
    require(perception_started["session"]["perception_history"][-1]["runtime_fact_committed"] is False, f"session history misreported observation as fact: {perception_started}")
    require(perception_started["session"]["perception_history"][-1]["current_use_status"] == "current_candidate", f"new observation was not eligible for current recheck: {perception_started}")

    changed_perception_session = set_stool(perception_session["session_id"], "ahead")
    require(changed_perception_session["perception_history"][-1]["current_use_status"] == "stale", f"world change did not stale prior grounding: {changed_perception_session}")
    require(changed_perception_session["perception_history"][-1]["invalidation_reason"] == "world_revision_changed", f"stale grounding lacks cause: {changed_perception_session}")

    activation = activate_task_perception("去桌子上拿杯子")
    relation_missing_observation = {**perception["perception_observation"], "relation_candidates": []}
    ungrounded = ground_task_observations(activation, relation_missing_observation)
    require(ungrounded["grounding_status"] == "perceptual_candidate", f"grounder inferred relation outside observation DTO: {ungrounded}")
    require(ungrounded["fallback"] == "active_observation_or_human_disambiguation", f"missing relation did not trigger observation fallback: {ungrounded}")

    perception_safety_session = start_session()
    set_stool(perception_safety_session["session_id"], "ahead")
    perception_with_obstacle = execute_command(perception_safety_session["session_id"], "去桌子上拿杯子")
    require(perception_with_obstacle["perception_observation"]["safety_observations"], f"task attention hid active obstacle: {perception_with_obstacle}")
    require(perception_with_obstacle["perception_observation"]["safety_observations"][0]["semantic_task_relevance"] == "safety_always_on", f"obstacle was not retained as safety input: {perception_with_obstacle}")

    multiple_session = start_session()
    set_perception_scenario(multiple_session["session_id"], "multiple_cups")
    multiple = execute_command(multiple_session["session_id"], "去桌子上拿杯子")
    require(multiple["status"] == "perception_disambiguation_required", f"multiple cups did not require disambiguation: {multiple}")
    require(multiple["concept_grounding"]["ambiguity_reason"] == "multiple_target_candidates", f"wrong ambiguity reason: {multiple}")
    require(multiple["concept_grounding"]["candidate_summary"]["target_count"] == 2, f"both cups were not retained: {multiple}")
    require(len(multiple["concept_grounding"]["candidate_options"]) == 2, f"candidate options missing: {multiple}")
    require(not multiple["concept_grounding"]["candidate_bindings"], f"ambiguous perception selected a cup: {multiple}")
    require(not multiple["concept_grounding"]["runtime_fact_committed"], f"ambiguous candidates became fact: {multiple}")
    selected_white = execute_command(multiple_session["session_id"], "拿白色杯子")
    require(selected_white["status"] == "perception_grounded_candidate", f"attribute clarification did not reground target: {selected_white}")
    require(selected_white["concept_grounding"]["candidate_summary"]["detected_target_count"] == 2, f"clarification hid original candidate set: {selected_white}")
    require(selected_white["concept_grounding"]["candidate_summary"]["target_count"] == 1, f"color constraint did not select exactly one candidate: {selected_white}")
    require(selected_white["concept_grounding"]["candidate_bindings"][0]["entity_ref"] == "cup_a", f"white cup was not selected from current observation: {selected_white}")
    require(selected_white["concept_grounding"]["candidate_bindings"][0]["observed_attributes"]["color"] == "white", f"selection evidence omitted observed color: {selected_white}")
    require(selected_white["concept_grounding"]["constraint_rejections"][0]["entity_ref"] == "cup_b", f"rejected alternative was not preserved: {selected_white}")
    require(selected_white["session"]["perception_history"][-2]["current_use_status"] == "stale", f"ambiguous observation remained current after clarification: {selected_white}")
    require(selected_white["session"]["perception_history"][-1]["current_use_status"] == "current_candidate", f"clarified observation was not current: {selected_white}")

    occluded_session = start_session()
    initial_occluded_position = occluded_session["state"]["executor_position"]
    set_perception_scenario(occluded_session["session_id"], "occluded_cup")
    occluded = execute_command(occluded_session["session_id"], "去桌子上拿杯子")
    require(occluded["status"] == "perception_grounded_candidate", f"active observation did not recover occluded cup: {occluded}")
    require(len(occluded["active_perception_trace"]) == 2, f"occlusion did not trigger viewpoint change: {occluded}")
    require(occluded["active_perception_trace"][0]["ambiguity_reason"] == "target_not_observed", f"initial occlusion was not recorded: {occluded}")
    require(occluded["active_perception_trace"][1]["grounding_status"] == "spatially_grounded", f"alternate viewpoint did not ground cup: {occluded}")
    require(occluded["session"]["state"]["executor_position"] == initial_occluded_position, f"head scan incorrectly moved chassis: {occluded}")
    require("转动头部" in occluded["prompt"], f"body did not explain active observation: {occluded}")

    relocated_session = start_session()
    before_relocation = execute_command(relocated_session["session_id"], "去桌子上拿杯子")
    before_observation_id = before_relocation["perception_observation"]["observation_id"]
    relocation = set_perception_scenario(relocated_session["session_id"], "relocated_cup")
    require(relocation["session"]["perception_history"][-1]["current_use_status"] == "stale", f"relocation did not stale old binding: {relocation}")
    after_relocation = execute_command(relocated_session["session_id"], "去桌子上拿杯子")
    relocated_target = next(item for item in after_relocation["concept_grounding"]["candidate_bindings"] if item["role"] == "target")
    require(relocated_target["estimated_position"] == [4.25, -1.35], f"new cup position was not rebound: {after_relocation}")
    require(after_relocation["perception_observation"]["observation_id"] != before_observation_id, f"relocation reused stale observation identity: {after_relocation}")
    require(after_relocation["session"]["perception_history"][-2]["current_use_status"] == "stale", f"old history became current again: {after_relocation}")
    require(after_relocation["session"]["perception_history"][-1]["current_use_status"] == "current_candidate", f"new binding was not current: {after_relocation}")

    direct_session = start_session()
    direct = execute_command(direct_session["session_id"], "往前走一点")
    require(direct["status"] == "fact_established", f"relative command failed: {direct}")
    require(direct["concept"]["reference_frame"] == "executor_heading", f"command must use body frame: {direct}")
    require(len(direct["frames"]) >= 8, f"continuous feedback frames missing: {direct}")

    right_session = start_session()
    right = execute_command(right_session["session_id"], "往你右边走一点")
    require(right["status"] == "fact_established", f"right-relative command failed: {right}")
    require(right["concept"]["relative_direction"] == "right", f"right body direction not resolved: {right}")
    require(right["concept"]["body_realization"] == "clockwise_turn_then_forward", f"differential drive must turn then move: {right}")
    require(not right["concept"]["lateral_translation_used"], f"differential drive must not strafe: {right}")
    require(right["body_self_judgment"]["rejected_realization"] == "lateral_translation", f"body must explain rejected strafe: {right}")
    require("不能横向平移" in right["body_self_judgment"]["explanation"], f"body explanation missing: {right}")
    require(right["session"]["state"]["executor_yaw_deg"] == -90.0, f"body yaw did not turn right: {right}")
    require(any(frame.get("yaw_deg") not in (None, 0.0) for frame in right["frames"]), f"turn animation frames missing: {right}")

    rotate_session = start_session()
    rotate = execute_command(rotate_session["session_id"], "向右转")
    require(rotate["status"] == "fact_established", f"pure rotation command failed: {rotate}")
    require(rotate["concept"]["body_realization"] == "clockwise_rotation_in_place", f"pure rotation was treated as side translation: {rotate}")
    require(rotate["session"]["state"]["executor_position"] == rotate_session["state"]["executor_position"], f"pure rotation translated body: {rotate}")
    require(rotate["terminal_fact"] == "executor_heading_changed", f"pure rotation terminal fact incorrect: {rotate}")

    signal_session = start_session()
    signal_started = start_embodied_teaching(signal_session["session_id"], "拿杯子")
    initial_events = signal_started["teaching_session"]["teaching_events"]
    require([item["event_type"] for item in initial_events] == ["observation_candidate_created", "pedagogical_signal_recorded", "teaching_authority_granted"], f"teaching timeline did not expose initial gates: {signal_started}")
    failed_signal_grasp = begin_teaching_control(signal_session["session_id"], "grasp")["immediate_result"]
    require(failed_signal_grasp["status"] == "grasp_blocked", f"signal test needs failed physical evidence: {failed_signal_grasp}")
    action_count = len(failed_signal_grasp["teaching_session"]["demonstrated_actions"])
    negative_signal = record_teaching_signal(signal_session["session_id"], "negative_example", "目标尚未进入本体可达范围")
    boundary_signal = record_teaching_signal(signal_session["session_id"], "boundary_indication", "不得越过当前抓取可达边界")
    correction_signal = record_teaching_signal(signal_session["session_id"], "correction")
    confirmation_signal = record_teaching_signal(signal_session["session_id"], "confirmation")
    require(len(confirmation_signal["teaching_session"]["demonstrated_actions"]) == action_count, f"teaching signals polluted positive action chain: {confirmation_signal}")
    constraints = confirmation_signal["teaching_session"]["scoped_constraint_candidates"]
    require(len(constraints) == 2 and all(not item["positive_process_chain_eligible"] for item in constraints), f"negative or boundary evidence entered positive chain: {constraints}")
    require(all(item["scope"]["world_revision"] == signal_session["world_revision"] for item in constraints), f"constraint scope lost world revision: {constraints}")
    require(correction_signal["signal"]["evidence"]["target_experience_ref"] is None, f"correction invented an experience target: {correction_signal}")
    require(confirmation_signal["signal"]["candidate_only"], f"teacher confirmation bypassed verification gates: {confirmation_signal}")

    teaching_session = start_session()
    unfamiliar_task = execute_command(
        teaching_session["session_id"],
        "携来杯子，让杯子在手中，以视觉确认杯子随夹爪移动为准",
    )
    require(unfamiliar_task["status"] == "temporary_effect_contract_compiled", f"unknown phrase did not compile a temporary contract: {unfamiliar_task}")
    require(unfamiliar_task["temporary_effect_contract"]["language_trigger"] == "携来", f"unknown action surface was not retained: {unfamiliar_task}")
    require(unfamiliar_task["temporary_effect_contract"]["effect_contract"]["canonical_goal_fact"]["fact"] == "target_object_in_gripper", f"human goal did not map to holding state primitive: {unfamiliar_task}")
    require(unfamiliar_task["post_action"]["teaching_available"], f"verifiable unknown goal did not expose teaching: {unfamiliar_task}")
    teaching_started = start_embodied_teaching(teaching_session["session_id"], "以视觉确认杯子随夹爪移动为准")
    require(teaching_started["status"] == "teaching_control_granted", f"teaching authority not granted: {teaching_started}")
    require(teaching_started["teaching_session"]["goal_utterance"].startswith("携来杯子"), f"teaching used stale input instead of compiled task: {teaching_started}")
    require(teaching_started["teaching_session"]["source_concept_contract"]["language_trigger"] == "携来", f"teaching lost temporary concept contract: {teaching_started}")
    require(teaching_started["teaching_session"]["perception_activation_source"] == "compiled_concept_target_role", f"teaching perception depended on unknown language trigger: {teaching_started}")
    require(not teaching_started["teaching_session"]["authority"]["safety_bypass_allowed"], f"teaching bypassed safety: {teaching_started}")
    observation_packet = teaching_started["teaching_session"]["observation_packet"]
    require(observation_packet["source"]["source_type"] == "live_first_person_embodied_teaching", f"teaching observation source not normalized: {observation_packet}")
    require(observation_packet["evidence"]["level"] == "L2" and observation_packet["candidate_only"], f"teaching evidence boundary incorrect: {observation_packet}")
    require(observation_packet["temporal_alignment"]["mode"] == "session_window_alignment", f"teaching temporal alignment not explicit: {observation_packet}")
    require(observation_packet["temporal_alignment"]["frame_level_audio_alignment_implemented"] is False, f"teaching packet overclaimed frame alignment: {observation_packet}")
    premature_grasp = begin_teaching_control(teaching_session["session_id"], "grasp")["immediate_result"]
    require(premature_grasp["status"] == "grasp_blocked", f"out-of-reach grasp was accepted: {premature_grasp}")
    for _ in range(17):
        drain_motion(begin_teaching_control(teaching_session["session_id"], "forward"))
    taught_grasp = begin_teaching_control(teaching_session["session_id"], "grasp")["immediate_result"]
    require(taught_grasp["status"] == "fact_established", f"reachable taught grasp failed: {taught_grasp}")
    require(taught_grasp["verification_evidence"]["final_fact_established"], f"taught grasp lacked physical verification: {taught_grasp}")
    compiled = finish_embodied_teaching(teaching_session["session_id"])
    require(compiled["status"] == "demonstration_compiled", f"teaching did not compile: {compiled}")
    contract = compiled["experience"]["invariant_contract"]
    require(compiled["experience"]["source_concept_contract"]["effect_contract"]["canonical_goal_fact"]["fact"] == compiled["experience"]["goal_fact"], f"experience was detached from the taught goal contract: {compiled}")
    require(contract["storage_policy"] == "store_invariants_not_concrete_teleoperation_parameters", f"wrong teaching storage policy: {compiled}")
    require("teacher_key_sequence" in contract["forbidden_storage"], f"teacher keys leaked into experience: {compiled}")
    require(not compiled["experience"]["demonstration_summary"]["raw_teleoperation_trace_persisted"], f"raw trace persisted: {compiled}")
    require(compiled["experience"]["pedagogical_signals"]["signal_types"] == ["demonstration"], f"teaching signal classification missing: {compiled}")
    evidence_summary = compiled["experience"]["teaching_evidence_summary"]
    require(evidence_summary["source_type"] == "live_first_person_embodied_teaching" and not evidence_summary["raw_observations_persisted"], f"teaching evidence summary not portable: {compiled}")
    negative_constraints = compiled["experience"]["applicability_constraints"]["negative_constraints"]
    require(negative_constraints and negative_constraints[0]["disposition"] == "candidate_constraint_pending_revalidation", f"failed teaching action was not compiled into scoped infeasibility evidence: {compiled}")
    require(negative_constraints[0]["scope"]["world_revision"] == teaching_session["world_revision"], f"infeasibility scope lost world revision: {compiled}")
    interrupted_replay = begin_learned_replay(teaching_session["session_id"])
    for _ in range(3):
        require(step_motion_command(interrupted_replay["job_id"])["status"] == "frame_verified_and_committed", f"replay precondition frame failed: {interrupted_replay}")
    set_protection_policy(
        teaching_session["session_id"],
        {"declaration_id": "teaching_replay_revision_test", "motion_policy": {"max_speed_mps": 0.5}},
    )
    invalidated_replay = step_motion_command(interrupted_replay["job_id"])
    require(invalidated_replay["status"] == "motion_completed", f"specialized replay did not terminate on policy change: {invalidated_replay}")
    require(invalidated_replay["result"]["status"] == "learned_replay_invalidated", f"specialized replay fell into ordinary command replanning: {invalidated_replay}")
    set_protection_policy(teaching_session["session_id"], None)
    replay_started = begin_learned_replay(teaching_session["session_id"])
    require(replay_started["status"] == "learned_replay_started", f"learned replay did not start: {replay_started}")
    replay_completed = drain_motion(replay_started)
    require(replay_completed["result"]["status"] == "fact_established", f"autonomous replay failed physical fact: {replay_completed}")
    require(replay_completed["result"]["control_source"] == "autonomous_learned_experience_replay", f"replay control source missing: {replay_completed}")
    learned = evaluate_learned_replay(teaching_session["session_id"], True)
    require(learned["status"] == "experience_learned", f"verified accepted replay was not learned: {learned}")
    require(learned["experience"]["status"] == "trusted_local_experience", f"experience trust state incorrect: {learned}")
    require(learned["persistence"]["durable"] and learned["persistence"]["reload_on_new_session"], f"trusted experience was not durably persisted: {learned}")
    require(test_store.exists(), f"trusted experience store was not created: {learned}")
    final_events = learned["session"]["teaching_session"]["teaching_events"]
    final_event_types = [item["event_type"] for item in final_events]
    for required_event in ["causal_contract_compiled", "demonstration_trace_discarded", "autonomous_replay_started", "physical_verification_passed", "human_acceptance_recorded", "trusted_experience_promoted"]:
        require(required_event in final_event_types, f"teaching timeline missing {required_event}: {final_events}")
    require(final_event_types.index("causal_contract_compiled") < final_event_types.index("autonomous_replay_started") < final_event_types.index("physical_verification_passed") < final_event_types.index("trusted_experience_promoted"), f"teaching promotion gates are out of order: {final_events}")
    promoted_event = next(item for item in final_events if item["event_type"] == "trusted_experience_promoted")
    require(not promoted_event["candidate_only"], f"trusted promotion remained candidate-only: {promoted_event}")
    persisted = learned["persisted_experience"]
    persisted_text = json.dumps(persisted, ensure_ascii=False)
    require("demonstration_entity_ref" not in persisted_text, f"demonstration instance leaked into persistent contract: {persisted}")
    require("entity_ref" not in json.dumps(persisted["source_concept_contract"], ensure_ascii=False), f"temporary target instance leaked into portable concept contract: {persisted}")
    require("source_teaching_id" not in persisted_text and "replay_job_id" not in persisted_text, f"session identifiers leaked into persistent contract: {persisted}")
    require(persisted["target_binding"] == {"concept_id": "concept_fillable_container", "rebind_by_concept_and_current_observation": True}, f"persistent binding is not portable: {persisted}")
    require(persisted["validation_summary"]["accepted_validation_count"] == 1, f"accepted validation summary incorrect: {persisted}")
    require(persisted["pedagogical_signals"] == {"signal_types": ["demonstration"], "interruption_occurred": False, "clarification_occurred": False, "outcome": "completed_successfully"}, f"persistent pedagogical signals were not normalized: {persisted}")
    require(not persisted["teaching_evidence_summary"]["source_identity_persisted"], f"teaching source identity leaked into persistent evidence summary: {persisted}")
    require("source_teaching_id" not in json.dumps(persisted["pedagogical_signals"], ensure_ascii=False), f"teaching session identity leaked into pedagogical signals: {persisted}")

    correction_session = start_session()
    correction_started = start_embodied_teaching(correction_session["session_id"], "拿杯子")
    correction_session_id = correction_session["session_id"]
    # A loaded trusted experience is the correction target, but recording the signal must not overwrite it.
    SESSIONS[correction_session_id]["learned_experience"] = json.loads(json.dumps(persisted, ensure_ascii=False))
    trusted_before_correction = json.dumps(SESSIONS[correction_session_id]["learned_experience"], ensure_ascii=False, sort_keys=True)
    targeted_correction = record_teaching_signal(correction_session_id, "correction", "调整接近方向")
    require(targeted_correction["signal"]["evidence"]["target_experience_ref"] == persisted["experience_id"], f"correction did not reference existing experience: {targeted_correction}")
    require(json.dumps(SESSIONS[correction_session_id]["learned_experience"], ensure_ascii=False, sort_keys=True) == trusted_before_correction, f"correction signal overwrote trusted experience: {targeted_correction}")

    html = (Path(__file__).with_name("embodied_home.html")).read_text(encoding="utf-8")
    require('id="teachingTimeline"' in html and html.count("data-signal=") == 5, "3D page does not expose five teaching signals and timeline")
    require("teachingButton.disabled=!r.post_action?.teaching_available" in html, "teaching button does not revoke stale teachability")

    cold_session = start_session()
    require(cold_session["available_local_experiences"][0]["experience_id"] == persisted["experience_id"], f"new session did not discover trusted experience: {cold_session}")
    relocated = set_perception_scenario(cold_session["session_id"], "relocated_cup")
    relocated_cup = next(item for item in relocated["runtime_objects"] if item["entity_id"] == "cup_a")
    require(relocated_cup["position"] != teaching_session["runtime_objects"][2]["position"], f"cold-start target did not move: {relocated}")
    cold_started = begin_persisted_experience_replay(cold_session["session_id"], persisted["experience_id"])
    require(cold_started["status"] == "learned_replay_started", f"cold-start replay did not start: {cold_started}")
    require(cold_started["cold_start_binding"]["trajectory_reused"] is False, f"cold start reused demonstration trajectory: {cold_started}")
    require(cold_started["cold_start_binding"]["current_entity_ref"] == "cup_a", f"cold start did not rebind current cup: {cold_started}")
    require(cold_started["cold_start_binding"]["trajectory_reused"] is False, f"relocated replay reused teaching trajectory: {cold_started}")
    cold_completed = drain_motion(cold_started)
    require(cold_completed["result"]["status"] == "fact_established", f"cold-start trusted replay failed: {cold_completed}")
    require(cold_completed["result"]["loaded_from_persistent_store"], f"cold-start provenance missing: {cold_completed}")
    require(cold_completed["result"]["experience"]["status"] == "trusted_local_experience", f"trusted replay incorrectly required promotion again: {cold_completed}")

    language_recall_session = start_session()
    set_perception_scenario(language_recall_session["session_id"], "relocated_cup")
    recalled_started = begin_motion_command(language_recall_session["session_id"], "携来杯子")
    require(recalled_started["status"] == "learned_replay_started", f"learned unknown phrase did not recall trusted experience: {recalled_started}")
    require(recalled_started["experience_recall"]["match_basis"] == "language_trigger_and_target_concept_alias", f"experience recall basis missing: {recalled_started}")
    require(not recalled_started["experience_recall"]["trajectory_reused"], f"language recall reused demonstration trajectory: {recalled_started}")
    recalled_completed = drain_motion(recalled_started)
    require(recalled_completed["result"]["status"] == "fact_established", f"learned phrase failed after target relocation: {recalled_completed}")

    revoked_teaching_session = start_session()
    start_embodied_teaching(revoked_teaching_session["session_id"], "拿杯子")
    set_protection_policy(
        revoked_teaching_session["session_id"],
        {"declaration_id": "revoke_active_teaching", "motion_policy": {"max_speed_mps": 0.4}},
    )
    revoked_control = begin_teaching_control(revoked_teaching_session["session_id"], "forward")
    require(revoked_control.get("error") == "teaching_control_authority_not_active", f"policy change left old teaching authority active: {revoked_control}")

    backward_session = start_session()
    backward = execute_command(backward_session["session_id"], "往后退一点")
    require(backward["concept"]["body_realization"] == "reverse_without_turning", f"reverse body capability ignored: {backward}")
    require(backward["session"]["state"]["executor_yaw_deg"] == 0.0, f"reverse should preserve heading: {backward}")

    detour_session = start_session()
    detour_with_stool = set_stool(detour_session["session_id"], "ahead")
    detour = execute_command(detour_session["session_id"], "往前走一点")
    require(detour["route_kind"] == "local_detour", f"stool must trigger detour: {detour}")
    require(len(detour["frames"]) > len(direct["frames"]), f"detour must have a distinct continuous route: {detour}")
    stool_position = detour_with_stool["active_obstacles"][0]["position"]
    combined_radius = profile["body_envelope"]["radius_m"] + 0.38
    frame_clearances = [math.dist(frame["position"], stool_position) for frame in detour["frames"]]
    require(min(frame_clearances) > combined_radius, f"detour frames penetrate stool envelope: {detour}")
    require(detour["session"]["state"]["executor_position"][0] > stool_position[0] + combined_radius, f"detour did not fully pass stool: {detour}")
    require(detour["route_evidence"]["detour_extended_goal_for_clearance"], f"detour terminal policy missing: {detour}")
    require("完全越过障碍" in detour["body_self_judgment"]["explanation"], f"detour completion explanation missing: {detour}")
    safety = detour["route_evidence"]["motion_safety_contract"]
    require(safety["all_segments_swept_volume_verified"] and safety["terminal_pose_verified"], f"motion safety contract incomplete: {detour}")
    require(safety["execution_must_recheck_world_revision"], f"runtime revision gate missing: {detour}")
    require(detour["route_evidence"]["selected_detour_side"] == "left", f"planner did not select feasible side: {detour}")
    require(any(item.get("side") == "right" for item in detour["route_evidence"]["rejected_alternatives"]), f"blocked alternative evidence missing: {detour}")

    blocked_session = start_session()
    set_stool(blocked_session["session_id"], "narrow")
    blocked = execute_command(blocked_session["session_id"], "往前走一点")
    require(blocked["status"] == "requires_human_confirmation", f"narrow obstacle must ask: {blocked}")
    require("搬走" in blocked["prompt"], f"blocked route must ask permission to move stool: {blocked}")
    require(not blocked["frames"], f"blocked command must not animate through obstacle: {blocked}")

    furniture_session = start_session()
    furniture_blocked = execute_command(furniture_session["session_id"], "一直往前走")
    require(furniture_blocked["status"] == "stopped_by_physical_obstacle", f"continuous motion crossed furniture: {furniture_blocked}")
    require(furniture_blocked["obstacle"]["entity_id"] == "counter_a", f"wrong fixed collision target: {furniture_blocked}")
    require(furniture_blocked["contact_evidence"]["motion_terminated_before_penetration"], f"penetration guard missing: {furniture_blocked}")
    first_stop = furniture_blocked["session"]["state"]["executor_position"]
    repeated = execute_command(furniture_session["session_id"], "一直往前走")
    require(repeated["status"] == "stopped_by_physical_obstacle", f"repeated forward crossed furniture: {repeated}")
    require(repeated["session"]["state"]["executor_position"] == first_stop, f"blocked body moved on repeat: {repeated}")
    require(furniture_blocked["p2_safety_self_proof"]["safe_state_reached"], f"P2 safety stop was not self-proven: {furniture_blocked}")
    require(not furniture_blocked["p2_safety_self_proof"]["upgrade_protection_required"], f"successful safety stop requested escalation: {furniture_blocked}")

    protected_session = start_session()
    intrinsic_before = protected_session["executor_profile"]
    protected_policy = {
        "declaration_id": "protected_home_motion_demo",
        "policy_scope": ["embodied_motion"],
        "motion_policy": {
            "max_speed_mps": 0.25,
            "max_contact_force_n": 12.0,
            "minimum_avoidance_distance_m": 0.2,
            "continuous_motion_requires_confirmation": True,
        },
        "execution_receipt_required": True,
    }
    policy_result = set_protection_policy(protected_session["session_id"], protected_policy)
    require(policy_result["session"]["executor_profile"] == intrinsic_before, f"P6 policy rewrote intrinsic profile: {policy_result}")
    envelope = policy_result["effective_execution_envelope"]
    require(envelope["effective_constraints"]["max_linear_speed_mps"] == 0.25, f"P6 speed limit not applied: {envelope}")
    require(envelope["policy_never_rewrites_intrinsic_profile"], f"P6/profile separation missing: {envelope}")
    protected_continuous = execute_command(protected_session["session_id"], "一直往前走")
    require(protected_continuous["status"] == "requires_human_confirmation", f"protected continuous motion bypassed confirmation: {protected_continuous}")
    require(protected_continuous["p2_control_decision"]["control_decision"] == "require_confirmation", f"P2 decision missing: {protected_continuous}")
    pending = protected_continuous["pending_confirmation"]
    require(pending["scope"] == "single_execution_of_exact_command", f"confirmation is not scoped: {pending}")
    require(pending["policy_binding"]["declaration_id"] == protected_policy["declaration_id"], f"confirmation is not policy-bound: {pending}")
    confirmed = confirm_pending_motion(protected_session["session_id"], pending["confirmation_id"], True)
    require(confirmed["status"] == "motion_started", f"approved confirmation did not continue motion: {confirmed}")
    require(confirmed["scoped_authorization"]["status"] == "consumed", f"authorization was not one-use: {confirmed}")
    require(confirmed["scoped_authorization"]["command_hash"] == pending["command_hash"], f"authorization command binding changed: {confirmed}")
    replayed = confirm_pending_motion(protected_session["session_id"], pending["confirmation_id"], True)
    require(replayed["status"] == "confirmation_not_current", f"consumed authorization was reusable: {replayed}")

    stale_session = start_session()
    set_protection_policy(stale_session["session_id"], protected_policy)
    stale_request = execute_command(stale_session["session_id"], "一直往前走")["pending_confirmation"]
    set_stool(stale_session["session_id"], "ahead")
    stale_confirmation = confirm_pending_motion(stale_session["session_id"], stale_request["confirmation_id"], True)
    require(stale_confirmation["status"] == "confirmation_not_current", f"world change did not revoke old confirmation: {stale_confirmation}")
    protected_small = execute_command(protected_session["session_id"], "往前走一点")
    require(protected_small["status"] == "fact_established", f"bounded protected motion should remain executable: {protected_small}")
    require(max(frame["duration_ms"] for frame in protected_small["frames"]) > max(frame["duration_ms"] for frame in direct["frames"]), f"P6 speed limit did not slow execution frames: {protected_small}")
    require(protected_small["p6_execution_receipt"]["declaration_id"] == protected_policy["declaration_id"], f"P6 receipt missing: {protected_small}")
    require(not protected_small["p6_execution_receipt"]["intrinsic_profile_modified"], f"P6 receipt reports profile mutation: {protected_small}")

    policy_change_session = start_session()
    policy_motion = begin_motion_command(policy_change_session["session_id"], "往前走一点")
    set_protection_policy(policy_change_session["session_id"], protected_policy)
    policy_invalidated = step_motion_command(policy_motion["job_id"])
    require(policy_invalidated["status"] == "path_invalidated_and_replanned", f"policy change did not invalidate active motion: {policy_invalidated}")
    require(policy_invalidated["reason"] == "runtime_policy_revision_changed", f"policy invalidation reason missing: {policy_invalidated}")

    live_session = start_session()
    live_started = begin_motion_command(live_session["session_id"], "一直往前走")
    live_job_id = live_started["job_id"]
    for _ in range(8):
        committed = step_motion_command(live_job_id)
        require(committed["status"] == "frame_verified_and_committed", f"initial live frame failed: {committed}")
    live_stool = set_stool(live_session["session_id"], "ahead")
    invalidated = step_motion_command(live_job_id)
    require(invalidated["status"] == "path_invalidated_and_replanned", f"world change did not invalidate path: {invalidated}")
    require(invalidated["reason"] == "runtime_world_revision_changed", f"wrong invalidation reason: {invalidated}")
    replacement = invalidated["replacement"]
    require(replacement.get("job_id"), f"dynamic obstacle did not produce replacement path: {invalidated}")
    replacement_id = replacement["job_id"]
    committed_positions = []
    while True:
        live_step = step_motion_command(replacement_id)
        if live_step.get("frame"):
            committed_positions.append(live_step["frame"]["position"])
        if live_step["status"] == "motion_completed":
            break
        require(live_step["status"] == "frame_verified_and_committed", f"replacement execution failed: {live_step}")
    live_stool_position = live_stool["active_obstacles"][0]["position"]
    require(all(math.dist(position, live_stool_position) > combined_radius for position in committed_positions), f"live replanning committed a penetrating frame: {committed_positions}")

    report = {"scene_id": scene["scene_id"], "task_conditioned_perception": {"normal": perception, "multiple": multiple, "occluded": occluded, "relocated": after_relocation}, "direct": direct, "right": right, "backward": backward, "detour": detour, "blocked": blocked, "fixed_furniture_stop": furniture_blocked, "protected_policy_overlay": {"envelope": envelope, "continuous": protected_continuous, "confirmed": confirmed, "small": protected_small, "policy_change_invalidation": policy_invalidated}, "live_replanning": invalidated}
    (OUTPUT / "embodied_home_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    test_store.unlink(missing_ok=True)
    os.environ.pop("RELL_EMBODIED_EXPERIENCE_STORE", None)
    print("Embodied semantic home validation passed.")
    print(f"Output: {OUTPUT / 'embodied_home_report.json'}")


if __name__ == "__main__":
    main()
