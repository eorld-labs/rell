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
    if "往前" not in text and "向前" not in text:
        return {
            "status": "teaching_required",
            "reason": "relative_motion_concept_not_grounded",
            "prompt": "请告诉我这个指令相对机器人自身朝向应如何移动。",
            "session": get_session(session_id),
        }
    continuous = any(token in text for token in ("一直", "持续", "不停"))
    distance = 8.0 if continuous else (0.35 if "一点" in text else 0.7)
    start = list(session["state"]["executor_position"])
    yaw = math.radians(session["state"]["executor_yaw_deg"])
    target = [start[0] + math.cos(yaw) * distance, start[1] + math.sin(yaw) * distance]
    profile = session["executor_profile"]
    collision = _first_collision(session, start, target, profile["body_envelope"]["radius_m"])
    obstacle = collision["obstacle"] if collision else None
    frames: list[dict[str, Any]] = []
    route_kind = "direct"
    if obstacle:
        if obstacle.get("obstacle_class") in {"fixed_furniture", "scene_boundary"}:
            safe_target = collision["safe_position"]
            frames = _interpolate(start, safe_target, max(2, min(80, int(math.dist(start, safe_target) / 0.05) + 1)))
            session["state"]["executor_position"] = safe_target
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
        detour = _detour_target(start, target, obstacle, profile["body_envelope"]["radius_m"])
        if obstacle.get("mode") == "narrow" or detour is None:
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
        frames.extend(_interpolate(start, detour, 8))
        frames.extend(_interpolate(detour, target, 8)[1:])
    else:
        frames = _interpolate(start, target, 12)
    session["state"]["executor_position"] = target
    session["state"]["active_region"] = _region_for(target, load_scene())
    result = {
        "status": "fact_established",
        "concept": {
            "concept_id": "relative_forward_motion",
            "reference_frame": "executor_heading",
            "distance_class": "continuous_until_termination" if continuous else ("small_increment" if distance == 0.35 else "normal_increment"),
            "learnable_invariant": "move_forward_relative_to_current_body_heading_until_requested_distance_or_physical_termination"
        },
        "route_kind": route_kind,
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


def _detour_target(start: list[float], target: list[float], obstacle: dict[str, Any], radius: float) -> list[float] | None:
    ox, oy = obstacle["position"]
    dx, dy = target[0] - start[0], target[1] - start[1]
    length = math.hypot(dx, dy) or 1.0
    clearance = radius + 0.55
    return [ox - dy / length * clearance, oy + dx / length * clearance]


def _interpolate(start: list[float], target: list[float], count: int) -> list[dict[str, Any]]:
    return [
        {"progress": index / (count - 1), "position": [start[0] + (target[0] - start[0]) * index / (count - 1), start[1] + (target[1] - start[1]) * index / (count - 1)]}
        for index in range(count)
    ]


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
