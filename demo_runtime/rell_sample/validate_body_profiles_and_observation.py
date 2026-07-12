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
    print("Body profile and directed observation validation passed.")


if __name__ == "__main__":
    main()
