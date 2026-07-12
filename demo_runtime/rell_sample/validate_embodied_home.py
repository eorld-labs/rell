from __future__ import annotations

import json
import math
from pathlib import Path

from embodied_scene import begin_motion_command, execute_command, load_scene, set_stool, start_session, step_motion_command


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

    report = {"scene_id": scene["scene_id"], "direct": direct, "right": right, "backward": backward, "detour": detour, "blocked": blocked, "fixed_furniture_stop": furniture_blocked, "live_replanning": invalidated}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "embodied_home_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Embodied semantic home validation passed.")
    print(f"Output: {OUTPUT / 'embodied_home_report.json'}")


if __name__ == "__main__":
    main()
