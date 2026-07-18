from __future__ import annotations

from embodied_scene import begin_motion_command, load_scene, start_session
from hospitality_task_graph import HOSPITALITY_GOAL, build_hospitality_task_graph, unresolved_hospitality_conditions
from hospitality_test_matrix import VARIANTS, validate_hospitality_matrix


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    scene = load_scene("hospitality_guest")
    graph = build_hospitality_task_graph(scene["objects"])
    node_ids = {item["node_id"] for item in graph["nodes"]}
    require(graph["goal_fact"] == HOSPITALITY_GOAL, f"hospitality terminal goal missing: {graph}")
    require({"clear_old_newspapers", "prepare_black_tea", "prepare_room_temperature_water", "acquire_tray"}.issubset(node_ids), f"parallel preparation branches incomplete: {graph}")
    require({"load_tray", "deliver_tray", "handover_to_guest"}.issubset(node_ids), f"terminal join chain incomplete: {graph}")
    require({"clear_old_newspapers", "prepare_black_tea", "prepare_room_temperature_water", "acquire_tray"}.issubset(set(graph["parallel_ready_branches"])), f"parallel-ready branch declaration missing: {graph}")
    require(graph["current_evidence"]["newspaper_count"] == 2, f"newspaper evidence was not grounded: {graph}")
    require(graph["current_evidence"]["service_zone_stable"] is False and graph["current_evidence"]["service_zone_is_handover_zone"] is True, f"handover zone was confused with a support surface: {graph}")
    require(graph["required_conditions"]["brewing_temperature_sufficient"] is False, f"room-temperature water incorrectly passed tea brewing precondition: {graph}")
    missing = unresolved_hospitality_conditions(graph)
    require({item["condition"] for item in missing} == {"brewing_temperature_sufficient"}, f"missing condition questions were not minimal: {missing}")
    session = start_session("home_humanoid", "hospitality_guest")
    matrix = validate_hospitality_matrix(scene)
    require(matrix["variant_count"] == len(VARIANTS) and all(matrix["coverage"].values()), f"hospitality test matrix incomplete: {matrix}")
    water_request = begin_motion_command(session["session_id"], "给我接一杯水")
    require(water_request.get("status") == "role_clarification_required", f"ambiguous water container escaped slot clarification: {water_request}")
    require(water_request.get("pending_role") == "theme", f"water request asked for the wrong slot: {water_request}")
    require({item["entity_ref"] for item in water_request.get("candidate_options", [])} == {"mug_white", "glass_tall"}, f"water container candidates were incomplete: {water_request}")
    resolved = begin_motion_command(session["session_id"], "白色马克杯")
    require(resolved.get("long_horizon_intent", {}).get("role_bindings", {}).get("theme") == "mug_white", f"container answer did not resume the water-delivery goal: {resolved}")
    print({"scene": scene["scene_id"], "goal": graph["goal_fact"], "parallel_branches": graph["parallel_ready_branches"], "missing_conditions": missing, "status": "passed"})


if __name__ == "__main__":
    main()
