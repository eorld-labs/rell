from __future__ import annotations

import json
import math
from pathlib import Path

from concept_core.perceptual_grounding import activate_task_perception, ground_task_observations
from embodied_scene import begin_motion_command, confirm_pending_motion, execute_command, load_scene, set_protection_policy, set_stool, start_session, step_motion_command


OUTPUT = Path(__file__).resolve().parents[1] / "output" / "rell_sample" / "embodied_home"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
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

    report = {"scene_id": scene["scene_id"], "task_conditioned_perception": perception, "direct": direct, "right": right, "backward": backward, "detour": detour, "blocked": blocked, "fixed_furniture_stop": furniture_blocked, "protected_policy_overlay": {"envelope": envelope, "continuous": protected_continuous, "confirmed": confirmed, "small": protected_small, "policy_change_invalidation": policy_invalidated}, "live_replanning": invalidated}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "embodied_home_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Embodied semantic home validation passed.")
    print(f"Output: {OUTPUT / 'embodied_home_report.json'}")


if __name__ == "__main__":
    main()
