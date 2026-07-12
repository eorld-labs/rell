from __future__ import annotations

from embodied_scene import begin_motion_command, execute_command, start_session


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    humanoid = start_session(scene_id="home_semantic_3d_b", executor_profile_id="home_humanoid")
    wheeled = start_session(scene_id="home_semantic_3d_b", executor_profile_id="home_mobile_manipulator")
    require(humanoid["executor_profile"]["body_profile"] == "humanoid_biped", f"humanoid profile missing: {humanoid}")
    require(wheeled["executor_profile"]["body_profile"] == "wheeled_dual_arm", f"wheeled profile regressed: {wheeled}")
    observed = execute_command(humanoid["session_id"], "你看得到杯子吗")
    require(observed["status"] == "directed_object_observation_completed", f"directed visual query did not scan: {observed}")
    require(observed["observation_action"]["operator"] == "scan_current_space_before_answering", f"query skipped observation action: {observed}")
    require(len(observed["active_perception_trace"]) == 3, f"observation did not use three viewpoints: {observed}")
    require(len(observed["directed_matches"]) == 1, f"cup visual concept was not recognized: {observed}")
    require(observed["candidate_only"] and not observed["direct_execution_allowed"], f"visual candidate became fact: {observed}")
    # The motion entry point must preserve observation routing even when the
    # trusted experience store contains legacy null contracts or bindings.
    started = begin_motion_command(humanoid["session_id"], "你看得到空间里的杯子吗")
    immediate = started.get("immediate_result", started)
    require(immediate.get("status") == "directed_object_observation_completed", f"motion observation route regressed: {started}")
    print("Body profile and directed observation validation passed.")


if __name__ == "__main__":
    main()
