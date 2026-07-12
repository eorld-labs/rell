from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any


SCENE_FILE = Path(__file__).resolve().parent / "data" / "embodied_home_scene.json"
SESSIONS: dict[str, dict[str, Any]] = {}


def load_scene() -> dict[str, Any]:
    return json.loads(SCENE_FILE.read_text(encoding="utf-8"))


def start_session(executor_profile_id: str = "home_mobile_manipulator") -> dict[str, Any]:
    scene = load_scene()
    if executor_profile_id not in scene["executor_profiles"]:
        return {"error": "executor_profile_not_found", "executor_profile_id": executor_profile_id}
    session_id = "embodied_" + hashlib.sha1(f"{scene['scene_id']}|{len(SESSIONS) + 1}".encode()).hexdigest()[:12]
    state = deepcopy(scene["initial_state"])
    session = {
        "session_id": session_id,
        "scene_id": scene["scene_id"],
        "executor_profile_id": executor_profile_id,
        "executor_profile": scene["executor_profiles"][executor_profile_id],
        "state": state,
        "active_obstacles": [],
        "event_history": [],
    }
    SESSIONS[session_id] = session
    return deepcopy(session)


def get_session(session_id: str) -> dict[str, Any]:
    return deepcopy(SESSIONS.get(session_id) or {"error": "embodied_session_not_found", "session_id": session_id})


def set_stool(session_id: str, mode: str = "ahead") -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    position = session["state"]["executor_position"]
    yaw = math.radians(session["state"]["executor_yaw_deg"])
    distance = 0.75
    stool_position = [position[0] + math.cos(yaw) * distance, position[1] + math.sin(yaw) * distance]
    session["active_obstacles"] = [{"entity_id": "stool_dynamic", "position": stool_position, "mode": mode}]
    return get_session(session_id)


def execute_command(session_id: str, utterance: str) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    text = utterance.strip()
    direction = _relative_direction(text)
    if not direction:
        return {
            "status": "teaching_required",
            "reason": "relative_motion_concept_not_grounded",
            "prompt": "请告诉我这个指令相对机器人自身朝向应如何移动。",
            "session": get_session(session_id),
        }
    continuous = any(token in text for token in ("一直", "持续", "不停"))
    distance = 8.0 if continuous else (0.35 if "一点" in text else 0.7)
    start = list(session["state"]["executor_position"])
    profile = session["executor_profile"]
    body_yaw = float(session["state"]["executor_yaw_deg"])
    if direction == "right":
        motion_yaw = body_yaw - 90.0
        final_yaw = motion_yaw
        body_realization = "clockwise_turn_then_forward"
    elif direction == "left":
        motion_yaw = body_yaw + 90.0
        final_yaw = motion_yaw
        body_realization = "counterclockwise_turn_then_forward"
    elif direction == "backward":
        motion_yaw = body_yaw + 180.0
        final_yaw = body_yaw
        body_realization = "reverse_without_turning"
    else:
        motion_yaw = body_yaw
        final_yaw = body_yaw
        body_realization = "forward_drive"
    body_explanations = {
        "clockwise_turn_then_forward": "我的底盘不能横向平移，因此会先向右转，再沿新的前方移动。",
        "counterclockwise_turn_then_forward": "我的底盘不能横向平移，因此会先向左转，再沿新的前方移动。",
        "reverse_without_turning": "我的底盘支持倒车，因此会保持当前朝向向后移动。",
        "forward_drive": "我会沿自己的当前朝向向前移动。",
    }
    yaw = math.radians(motion_yaw)
    target = [start[0] + math.cos(yaw) * distance, start[1] + math.sin(yaw) * distance]
    rotation_frames = _rotation_frames(start, body_yaw, final_yaw) if final_yaw != body_yaw else []
    collision = _first_collision(session, start, target, profile["body_envelope"]["radius_m"])
    obstacle = collision["obstacle"] if collision else None
    frames: list[dict[str, Any]] = []
    route_kind = "direct"
    if obstacle:
        if obstacle.get("obstacle_class") in {"fixed_furniture", "scene_boundary"}:
            safe_target = collision["safe_position"]
            frames = rotation_frames + _with_yaw(
                _interpolate(start, safe_target, max(2, min(80, int(math.dist(start, safe_target) / 0.05) + 1))),
                final_yaw,
            )
            session["state"]["executor_position"] = safe_target
            session["state"]["executor_yaw_deg"] = final_yaw
            session["state"]["active_region"] = _region_for(safe_target, load_scene())
            result = {
                "status": "stopped_by_physical_obstacle",
                "reason": "body_envelope_contact_with_fixed_scene_geometry",
                "prompt": f"前方是{obstacle['label']}，本体无法继续前进，已在接触前停止。",
                "obstacle": obstacle,
                "contact_evidence": {
                    "detector": "swept_body_envelope",
                    "body_radius_m": profile["body_envelope"]["radius_m"],
                    "motion_terminated_before_penetration": True,
                    "safe_position_is_transient_execution_state": True
                },
                "frames": frames,
                "terminal_fact": "forward_motion_blocked_by_physical_geometry",
                "session": get_session(session_id),
            }
            session["event_history"].append({"utterance": text, "result": result["status"], "reason": result["reason"], "obstacle": obstacle["entity_id"]})
            return result
        detour_path = _detour_path(session, start, target, obstacle, profile["body_envelope"]["radius_m"])
        if obstacle.get("mode") == "narrow" or detour_path is None:
            result = {
                "status": "requires_human_confirmation",
                "reason": "obstacle_blocks_route_and_no_body_clearance",
                "prompt": "前方凳子无法安全绕开，可以把凳子搬走吗？",
                "obstacle": obstacle,
                "body_constraint": profile["body_envelope"],
                "frames": [],
                "session": get_session(session_id),
            }
            session["event_history"].append({"utterance": text, "result": result["status"], "reason": result["reason"]})
            return result
        route_kind = "local_detour"
        frames.extend(rotation_frames)
        route_start = start
        for waypoint in detour_path:
            frames.extend(_with_yaw(_interpolate(route_start, waypoint, 8)[1:], final_yaw))
            route_start = waypoint
        target = detour_path[-1]
    else:
        frames = rotation_frames + _with_yaw(_interpolate(start, target, 12), final_yaw)
    session["state"]["executor_position"] = target
    session["state"]["executor_yaw_deg"] = final_yaw
    session["state"]["active_region"] = _region_for(target, load_scene())
    body_explanation = body_explanations[body_realization]
    if route_kind == "local_detour":
        body_explanation = "我检测到前方凳子，已按本体净空从侧面绕行，并完全越过障碍后回到原行进方向。"
    result = {
        "status": "fact_established",
        "concept": {
            "concept_id": "body_relative_motion",
            "reference_frame": "executor_heading",
            "relative_direction": direction,
            "body_realization": body_realization,
            "kinematic_model": profile.get("kinematic_model"),
            "lateral_translation_used": False,
            "distance_class": "continuous_until_termination" if continuous else ("small_increment" if distance == 0.35 else "normal_increment"),
            "learnable_invariant": "resolve_relative_direction_in_body_frame_then_select_motion_allowed_by_body_kinematics"
        },
        "route_kind": route_kind,
        "route_evidence": {
            "requested_distance_m": distance,
            "terminal_policy": "clear_entire_obstacle_body_envelope_before_returning_to_travel_axis" if route_kind == "local_detour" else "requested_relative_displacement",
            "detour_extended_goal_for_clearance": route_kind == "local_detour",
        },
        "body_self_judgment": {
            "explanation": body_explanation,
            "selected_realization": body_realization,
            "rejected_realization": "lateral_translation" if direction in {"left", "right"} else None,
            "portrait_basis": session["executor_profile_id"],
        },
        "frames": frames,
        "terminal_fact": "executor_relative_displacement_reached",
        "session": get_session(session_id),
    }
    session["event_history"].append({"utterance": text, "result": result["status"], "route_kind": route_kind})
    return result


def _first_collision(session: dict[str, Any], start: list[float], target: list[float], radius: float) -> dict[str, Any] | None:
    scene = load_scene()
    distance = math.dist(start, target)
    sample_count = max(2, int(distance / 0.04) + 1)
    previous = list(start)
    for index in range(1, sample_count):
        ratio = index / (sample_count - 1)
        point = [start[0] + (target[0] - start[0]) * ratio, start[1] + (target[1] - start[1]) * ratio]
        collider = _collider_at(point, radius, session, scene)
        if collider:
            return {"obstacle": collider, "contact_position": point, "safe_position": previous}
        previous = point
    return None


def _collider_at(point: list[float], radius: float, session: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any] | None:
    x, y = point
    if x - radius < -5.0 or x + radius > 5.0 or y - radius < -2.3 or y + radius > 2.3:
        return {"entity_id": "home_wall_boundary", "label": "墙体", "obstacle_class": "scene_boundary", "fixed": True}
    for item in scene["objects"]:
        if not item.get("fixed"):
            continue
        ox, oy = item["position"]
        sx, sy = item["size"][:2]
        if abs(x - ox) <= sx / 2 + radius and abs(y - oy) <= sy / 2 + radius:
            return {
                "entity_id": item["entity_id"],
                "label": item["label"],
                "kind": item["kind"],
                "obstacle_class": "fixed_furniture",
                "fixed": True,
            }
    for obstacle in session["active_obstacles"]:
        ox, oy = obstacle["position"]
        if math.hypot(x - ox, y - oy) <= radius + 0.38:
            return {**obstacle, "label": "凳子", "obstacle_class": "movable_obstacle", "fixed": False}
    return None


def _detour_path(
    session: dict[str, Any],
    start: list[float],
    target: list[float],
    obstacle: dict[str, Any],
    radius: float,
) -> list[list[float]] | None:
    ox, oy = obstacle["position"]
    dx, dy = target[0] - start[0], target[1] - start[1]
    length = math.hypot(dx, dy) or 1.0
    forward = [dx / length, dy / length]
    left = [-forward[1], forward[0]]
    longitudinal_clearance = radius + 0.46
    lateral_clearance = radius + 0.58
    before = [ox - forward[0] * longitudinal_clearance + left[0] * lateral_clearance, oy - forward[1] * longitudinal_clearance + left[1] * lateral_clearance]
    after_side = [ox + forward[0] * longitudinal_clearance + left[0] * lateral_clearance, oy + forward[1] * longitudinal_clearance + left[1] * lateral_clearance]
    after_axis = [ox + forward[0] * longitudinal_clearance, oy + forward[1] * longitudinal_clearance]
    waypoints = [before, after_side, after_axis]
    segment_start = start
    for waypoint in waypoints:
        if _first_collision(session, segment_start, waypoint, radius):
            return None
        segment_start = waypoint
    return waypoints


def _interpolate(start: list[float], target: list[float], count: int) -> list[dict[str, Any]]:
    return [
        {"progress": index / (count - 1), "position": [start[0] + (target[0] - start[0]) * index / (count - 1), start[1] + (target[1] - start[1]) * index / (count - 1)]}
        for index in range(count)
    ]


def _with_yaw(frames: list[dict[str, Any]], yaw_deg: float) -> list[dict[str, Any]]:
    return [{**frame, "yaw_deg": yaw_deg} for frame in frames]


def _rotation_frames(position: list[float], start_yaw: float, target_yaw: float) -> list[dict[str, Any]]:
    return [
        {"progress": index / 7, "position": list(position), "yaw_deg": start_yaw + (target_yaw - start_yaw) * index / 7}
        for index in range(1, 8)
    ]


def _relative_direction(text: str) -> str | None:
    if any(token in text for token in ("右边", "右侧", "向右", "往右")):
        return "right"
    if any(token in text for token in ("左边", "左侧", "向左", "往左")):
        return "left"
    if any(token in text for token in ("后边", "后面", "向后", "往后", "后退")):
        return "backward"
    if any(token in text for token in ("前边", "前面", "向前", "往前", "前进")):
        return "forward"
    return None


def _region_for(position: list[float], scene: dict[str, Any]) -> str:
    for region in scene["semantic_regions"]:
        cx, cy = region["center"]
        sx, sy = region["size"]
        if abs(position[0] - cx) <= sx / 2 and abs(position[1] - cy) <= sy / 2:
            return region["region_id"]
    return "transition_space"


def _point_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))
