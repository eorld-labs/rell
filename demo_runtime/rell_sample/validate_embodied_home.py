from __future__ import annotations

import json
import math
import os
from pathlib import Path

from concept_core.perceptual_grounding import activate_task_perception, ground_task_observations
from embodied_scene import SESSIONS, begin_learned_replay, begin_motion_command, begin_persisted_experience_replay, begin_teaching_control, build_factory_concept_catalog, build_factory_object_catalog, confirm_pending_motion, evaluate_learned_replay, execute_command, finish_embodied_teaching, load_scene, record_teaching_signal, set_perception_scenario, set_protection_policy, set_stool, start_embodied_teaching, start_session, step_motion_command


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

    body_gap = execute_command(zero_id, "擦操作台")
    require(body_gap["factory_concept"]["reason_code"] == "executor_capability_not_available", f"missing body capability was not explained: {body_gap}")
    require(body_gap["post_action"]["human_help_suggested"] and not body_gap["post_action"]["teaching_available"], f"teaching was offered for impossible body capability: {body_gap}")

    role_gap = execute_command(zero_id, "打开冰箱")
    require(role_gap["factory_concept"]["reason_code"] == "required_semantic_roles_not_grounded", f"unknown object was not distinguished from skill absence: {role_gap}")
    require(role_gap["post_action"]["clarification_required"], f"role gap did not ask for grounding: {role_gap}")

    unknown_gap = execute_command(zero_id, "跳起来")
    require(unknown_gap["status"] == "factory_concept_gap", f"unknown event did not expose concept gap: {unknown_gap}")
    require(unknown_gap["concept_gap"]["understanding_status"] == "operator_and_goal_fact_unknown", f"unknown concept overclaimed understanding: {unknown_gap}")
    require(unknown_gap["post_action"]["teaching_available"] and unknown_gap["post_action"]["clarification_required"], f"unknown concept did not enter recoverable post-processing: {unknown_gap}")

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
    teaching_started = start_embodied_teaching(teaching_session["session_id"], "拿杯子")
    require(teaching_started["status"] == "teaching_control_granted", f"teaching authority not granted: {teaching_started}")
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

    cold_session = start_session()
    require(cold_session["available_local_experiences"][0]["experience_id"] == persisted["experience_id"], f"new session did not discover trusted experience: {cold_session}")
    cold_started = begin_persisted_experience_replay(cold_session["session_id"], persisted["experience_id"])
    require(cold_started["status"] == "learned_replay_started", f"cold-start replay did not start: {cold_started}")
    require(cold_started["cold_start_binding"]["trajectory_reused"] is False, f"cold start reused demonstration trajectory: {cold_started}")
    require(cold_started["cold_start_binding"]["current_entity_ref"] == "cup_a", f"cold start did not rebind current cup: {cold_started}")
    cold_completed = drain_motion(cold_started)
    require(cold_completed["result"]["status"] == "fact_established", f"cold-start trusted replay failed: {cold_completed}")
    require(cold_completed["result"]["loaded_from_persistent_store"], f"cold-start provenance missing: {cold_completed}")
    require(cold_completed["result"]["experience"]["status"] == "trusted_local_experience", f"trusted replay incorrectly required promotion again: {cold_completed}")

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
