from __future__ import annotations

from embodied_scene import begin_motion_command, execute_command, start_session, step_motion_command


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


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
