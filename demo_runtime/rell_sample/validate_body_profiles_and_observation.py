from __future__ import annotations

from embodied_scene import begin_motion_command, execute_command, set_stool, start_session, step_motion_command


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def drain_motion(started: dict) -> dict:
    require(started.get("status") == "motion_started" and started.get("job_id"), f"expected motion job: {started}")
    for _ in range(240):
        completed = step_motion_command(started["job_id"])
        if completed.get("status") == "motion_completed":
            return completed
    raise AssertionError(f"motion did not complete: {started}")


def main() -> None:
    humanoid = start_session(scene_id="home_semantic_3d_b", executor_profile_id="home_humanoid")
    wheeled = start_session(scene_id="home_semantic_3d_b", executor_profile_id="home_mobile_manipulator")
    require(humanoid["executor_profile"]["body_profile"] == "humanoid_biped", f"humanoid profile missing: {humanoid}")
    require(wheeled["executor_profile"]["body_profile"] == "wheeled_dual_arm", f"wheeled profile regressed: {wheeled}")
    observed = execute_command(humanoid["session_id"], "你看得到杯子吗")
    require(observed["status"] == "observation_candidate_confirmation_required", f"directed visual query did not request confirmation: {observed}")
    require(observed["observation_action"]["operator"] == "scan_current_space_before_answering", f"query skipped observation action: {observed}")
    require(len(observed["active_perception_trace"]) == 3, f"observation did not use three viewpoints: {observed}")
    require(len(observed["directed_matches"]) == 1, f"cup visual concept was not recognized: {observed}")
    require(observed["candidate_only"] and not observed["direct_execution_allowed"], f"visual candidate became fact: {observed}")
    # The motion entry point must preserve observation routing even when the
    # trusted experience store contains legacy null contracts or bindings.
    started = begin_motion_command(humanoid["session_id"], "你看得到空间里的杯子吗")
    immediate = started.get("immediate_result", started)
    require(immediate.get("status") == "observation_candidate_confirmation_required", f"motion observation route regressed: {started}")
    colloquial = execute_command(wheeled["session_id"], "看到杯子没有")
    require(colloquial["status"] == "observation_candidate_confirmation_required", f"colloquial observation query misrouted: {colloquial}")
    variant = execute_command(wheeled["session_id"], "你看的到白色杯子吗")
    require(variant["status"] == "observation_candidate_confirmation_required", f"看得到 variant did not enter observe concept: {variant}")
    abbreviated = execute_command(wheeled["session_id"], "你看的杯子吗")
    require(abbreviated["status"] == "observation_candidate_confirmation_required", f"abbreviated visual question did not enter observe concept: {abbreviated}")
    location_session = start_session(scene_id="home_semantic_3d_b", executor_profile_id="home_humanoid")
    cup_location = begin_motion_command(location_session["session_id"], "杯子在哪里")["immediate_result"]
    require(cup_location["status"] == "object_location_state_answered", f"object location query entered task causality: {cup_location}")
    require(cup_location["location_binding"] == {"relation": "on_top_of", "support_entity_ref": "counter_b"}, f"visual topology did not answer cup location: {cup_location}")
    require(cup_location["evidence_status"] == "visual_topological_candidate" and cup_location["candidate_only"], f"visual location was overclaimed as verified: {cup_location}")
    gap_location_session = start_session(scene_id="home_semantic_3d_b", executor_profile_id="home_humanoid")
    unknown_started = begin_motion_command(gap_location_session["session_id"], "归整苹果")
    require(unknown_started["status"] == "concept_gap_clarification_required", f"location bypass precondition did not start: {unknown_started}")
    location_during_gap = begin_motion_command(gap_location_session["session_id"], "杯子在哪里")["immediate_result"]
    require(location_during_gap["status"] == "object_location_state_answered", f"active concept-gap dialogue swallowed a state query: {location_during_gap}")
    require(location_during_gap["session"]["concept_gap_dialogue"]["status"] == "collecting_minimum_causal_contract", f"state query destroyed active clarification context: {location_during_gap}")
    implicit_support_session = start_session(scene_id="home_semantic_3d_b", executor_profile_id="home_humanoid")
    implicit_support = begin_motion_command(implicit_support_session["session_id"], "拿起杯子")
    require(implicit_support["status"] == "requires_human_confirmation", f"goal-driven grasp did not reach arbitration: {implicit_support}")
    implicit_result = implicit_support["immediate_result"]
    implicit_plan = implicit_result["candidate_execution_plan"]
    require(implicit_plan["goal_operator"] == "grasp_object" and implicit_plan["goal_fact"] == "target_object_in_gripper", f"grasp goal was not extracted before planning: {implicit_support}")
    require(implicit_plan["role_bindings"] == {"target": "cup_b", "support": "counter_b"}, f"support relation was not inferred from active perception: {implicit_support}")
    require(implicit_plan["candidate_process"] == ["navigate_to_support", "align_end_effector", "grasp_target", "verify_target_in_gripper"], f"missing facts did not compile a causal candidate chain: {implicit_support}")
    require(implicit_result["concept_grounding"]["relation_evidence"]["relation"] == "on_top_of", f"support binding lacked visual-topological evidence: {implicit_support}")
    require(not implicit_support.get("experience_recall"), f"language-to-experience recall bypassed concept and state grounding: {implicit_support}")
    implicit_grasp_done = drain_motion(begin_motion_command(implicit_support_session["session_id"], "确认"))
    grasped_cup = next(item for item in implicit_grasp_done["session"]["runtime_objects"] if item["entity_id"] == "cup_b")
    require(grasped_cup.get("support_ref") is None and grasped_cup.get("last_support_ref") == "counter_b", f"grasp did not destroy current support while preserving provenance: {implicit_grasp_done}")
    put_down = begin_motion_command(implicit_support_session["session_id"], "放下杯子")
    put_down_result = put_down["immediate_result"]
    require(put_down["status"] == "requires_human_confirmation", f"implicit destination placement bypassed arbitration: {put_down}")
    require(put_down_result["candidate_execution_plan"]["roles"] == {"theme": "cup_b", "destination": "counter_b"}, f"held object and prior support were not rebound by role contract: {put_down}")
    require(put_down_result["grounding_basis"]["source"] == "implicit_previous_verified_support", f"implicit destination did not preserve its inference basis: {put_down}")
    require(put_down_result["candidate_execution_plan"]["role_grounding"]["destination"]["binding_strength"] == "implicit", f"implicit destination was overclaimed as explicit: {put_down}")
    put_down_done = drain_motion(begin_motion_command(implicit_support_session["session_id"], "确认"))
    require(put_down_done["result"]["terminal_fact"] == "object_supported_at_destination" and put_down_done["session"]["state"]["holding"] is None, f"put-down did not establish stable support and destroy holding: {put_down_done}")
    explicit_support_session = start_session(scene_id="home_semantic_3d_b", executor_profile_id="home_humanoid")
    explicit_support = begin_motion_command(explicit_support_session["session_id"], "走到桌子上拿起杯子")
    explicit_plan = explicit_support["immediate_result"]["candidate_execution_plan"]
    require(explicit_support["status"] == "requires_human_confirmation" and explicit_plan["goal_operator"] == "grasp_object", f"last causal operator was not selected as the terminal goal: {explicit_support}")
    require(explicit_plan["role_bindings"] == {"target": "cup_b", "support": "counter_b"}, f"explicit support and target were not jointly grounded: {explicit_support}")
    bare_take_session = start_session(scene_id="home_semantic_3d_b", executor_profile_id="home_humanoid")
    bare_take = begin_motion_command(bare_take_session["session_id"], "去桌子上拿杯子")
    bare_take_result = bare_take["immediate_result"]
    require(bare_take["status"] == "requires_human_confirmation", f"bare take verb stopped at perception instead of planning: {bare_take}")
    require(bare_take_result["operator_candidate"] == "grasp_object", f"earlier navigation token displaced the final grasp goal: {bare_take}")
    require(bare_take_result["candidate_execution_plan"]["role_bindings"] == {"target": "cup_b", "support": "counter_b"}, f"bare take did not jointly ground explicit support and target: {bare_take}")
    obstacle_continuation_session = start_session(scene_id="home_semantic_3d_b", executor_profile_id="home_humanoid")
    obstacle_plan = begin_motion_command(obstacle_continuation_session["session_id"], "去桌子上拿杯子")
    obstacle_started = begin_motion_command(obstacle_continuation_session["session_id"], "确认")
    require(obstacle_started["status"] == "motion_started", f"confirmed grasp did not start before obstacle test: {obstacle_started}")
    require(step_motion_command(obstacle_started["job_id"])["status"] == "frame_verified_and_committed", "grasp did not enter active motion before obstacle insertion")
    set_stool(obstacle_continuation_session["session_id"], "ahead")
    obstacle_replanned = step_motion_command(obstacle_started["job_id"])
    require(obstacle_replanned["status"] == "path_invalidated_and_replanned", f"obstacle did not invalidate stale geometry path: {obstacle_replanned}")
    require(obstacle_replanned["continuation_status"] == "same_intent_reobserved_and_replanned", f"local detour lost the confirmed grasp intent: {obstacle_replanned}")
    obstacle_completed = drain_motion(obstacle_replanned["replacement"])
    require(obstacle_completed["result"]["terminal_fact"] == "target_object_in_gripper", f"detour cleared obstacle but failed to complete the original grasp goal: {obstacle_completed}")
    direct_take_session = start_session(scene_id="home_semantic_3d_b", executor_profile_id="home_humanoid")
    direct_take = begin_motion_command(direct_take_session["session_id"], "去拿杯子")
    require(direct_take["status"] == "requires_human_confirmation" and direct_take["immediate_result"]["operator_candidate"] == "grasp_object", f"short bare take did not use the same terminal-goal paradigm: {direct_take}")
    apple_session = start_session(scene_id="home_semantic_3d_b", executor_profile_id="home_humanoid")
    apple_candidate = begin_motion_command(apple_session["session_id"], "拿起苹果")
    apple_plan = apple_candidate["immediate_result"]["candidate_execution_plan"]
    require(apple_plan["role_bindings"] == {"target": "apple_b", "support": None}, f"grasp paradigm did not generalize to apple: {apple_candidate}")
    require(apple_plan["candidate_process"][0] == "navigate_to_bound_target", f"unsupported apple relation was invented: {apple_candidate}")
    apple_grasp_done = drain_motion(begin_motion_command(apple_session["session_id"], "确认"))
    require(apple_grasp_done["result"]["terminal_fact"] == "target_object_in_gripper", f"apple grasp prerequisite failed: {apple_grasp_done}")
    apple_down = begin_motion_command(apple_session["session_id"], "放下苹果")
    apple_down_result = apple_down["immediate_result"]
    require(apple_down_result["grounding_basis"]["source"] == "implicit_nearest_compatible_support_candidate", f"missing prior support did not fall back to compatible spatial candidate: {apple_down}")
    require(apple_down_result["candidate_execution_plan"]["roles"] == {"theme": "apple_b", "destination": "dining_table_b"}, f"put-down mechanism did not generalize beyond cups: {apple_down}")
    contextual = start_session(scene_id="home_semantic_3d_b", executor_profile_id="home_humanoid")
    first = begin_motion_command(contextual["session_id"], "你看得到空间里的杯子吗")["immediate_result"]
    accepted = begin_motion_command(contextual["session_id"], "对")
    require(accepted.get("status") == "observation_candidate_confirmed", f"contextual confirmation not applied: {accepted}")
    require(accepted["immediate_result"]["confirmed_visual_binding"]["verification_receipt"]["physical_observation_consistent"], f"confirmation lacked physical verification: {accepted}")
    grasp_plan = begin_motion_command(contextual["session_id"], "去拿起那个杯子")
    require(grasp_plan["status"] == "requires_human_confirmation", f"grasp request did not produce candidate execution plan: {grasp_plan}")
    require(grasp_plan["immediate_result"]["candidate_execution_plan"]["missing_precondition"] == "executor_within_grasp_reach", f"causal precondition was not back-chained: {grasp_plan}")
    approved_plan = begin_motion_command(contextual["session_id"], "是的，你可以直接去拿")
    require(approved_plan["status"] == "motion_started", f"contextual route approval did not start motion: {approved_plan}")
    completed = None
    for _ in range(200):
        completed = step_motion_command(approved_plan["job_id"])
        if completed.get("status") == "motion_completed":
            break
    require(completed and completed.get("result", {}).get("terminal_fact") == "target_object_in_gripper", f"causal grasp chain did not verify grasp: {completed}")
    holding_query = execute_command(contextual["session_id"], "现在手上拿着什么")
    require(holding_query["status"] == "runtime_holding_state_answered", f"holding state query did not use runtime state: {holding_query}")
    require(holding_query["runtime_fact"] == "object_in_gripper", f"holding fact was not derived from verified grasp: {holding_query}")
    held_location = execute_command(contextual["session_id"], "杯子在哪里")
    require(held_location["status"] == "object_location_state_answered" and held_location["location_binding"]["relation"] == "held_by_executor", f"verified holding did not override visual support candidate: {held_location}")
    require(held_location["evidence_status"] == "runtime_verified" and not held_location["candidate_only"], f"verified location was downgraded to a visual candidate: {held_location}")
    table_observation = begin_motion_command(contextual["session_id"], "你看得到桌子吗")["immediate_result"]
    require(table_observation["status"] == "observation_candidate_confirmation_required", f"support observation did not request confirmation: {table_observation}")
    require(table_observation["pending_confirmation"]["concept_display_name"] == "桌子", f"support confirmation reused a cup label: {table_observation}")
    require("杯子" not in table_observation["prompt"], f"support prompt was hard-coded to cup: {table_observation}")
    table_accepted = begin_motion_command(contextual["session_id"], "对")
    require(table_accepted.get("status") == "observation_candidate_confirmed", f"support observation was not committed after confirmation: {table_accepted}")
    placement_plan = begin_motion_command(contextual["session_id"], "再放在桌子上")
    require(placement_plan["status"] == "requires_human_confirmation", f"placement did not produce a candidate plan: {placement_plan}")
    roles = placement_plan["immediate_result"]["candidate_execution_plan"]["roles"]
    require(roles == {"theme": "cup_b", "destination": "counter_b"}, f"role contracts did not bind current holding and support destination: {placement_plan}")
    require(placement_plan["immediate_result"]["placement_candidate"]["absolute_pose_persisted"] is False, f"transient placement pose leaked into experience: {placement_plan}")
    placement_started = begin_motion_command(contextual["session_id"], "可以")
    require(placement_started["status"] == "motion_started", f"confirmed placement did not start: {placement_started}")
    placement_completed = None
    for _ in range(200):
        placement_completed = step_motion_command(placement_started["job_id"])
        if placement_completed.get("status") == "motion_completed":
            break
    placement_result = (placement_completed or {}).get("result", {})
    require(placement_result.get("terminal_fact") == "object_supported_at_destination", f"placement support fact was not verified: {placement_completed}")
    require(placement_completed["session"]["state"]["holding"] is None, f"verified placement did not destroy holding fact: {placement_completed}")
    placed_cup = next(item for item in placement_completed["session"]["runtime_objects"] if item["entity_id"] == "cup_b")
    require(placed_cup.get("support_ref") == "counter_b", f"placed object was not rebound to destination support: {placement_completed}")
    print("Body profile and directed observation validation passed.")


if __name__ == "__main__":
    main()
