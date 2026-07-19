from __future__ import annotations

from embodied_scene import begin_motion_command, get_session, load_scene, start_session, step_motion_command
from hospitality_task_graph import HOSPITALITY_GOAL, build_hospitality_task_graph, unresolved_hospitality_conditions
from hospitality_test_matrix import VARIANTS, validate_hospitality_matrix


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def drain_graph(started: dict) -> tuple[list[str], dict[str, int], dict]:
    node_order = []
    route_segment_counts = {}
    current = started
    final_result = {}
    for _ in range(16):
        job_id = current.get("job_id")
        require(bool(job_id), f"causal graph stage did not start motion: {current}")
        completed = None
        for _ in range(800):
            step = step_motion_command(job_id)
            if step.get("status") == "motion_completed":
                completed = step
                break
            require(step.get("status") == "frame_verified_and_committed", f"graph motion entered unexpected state: {step}")
        require(completed is not None, f"graph motion did not complete: {current}")
        final_result = completed.get("result") or {}
        require(final_result.get("status") == "fact_established", f"graph node failed physical verification: {final_result}")
        node_order.append(final_result.get("graph_node_id"))
        route_segment_counts[final_result.get("graph_node_id")] = len(final_result.get("causal_graph_route_segments", []))
        if (final_result.get("long_horizon_intent") or {}).get("lifecycle") == "completed":
            return node_order, route_segment_counts, final_result
        current = final_result.get("next_stage_started") or {}
    raise AssertionError(f"causal graph exceeded node bound: {node_order}")


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

    graph_session = start_session("home_humanoid", "hospitality_guest")
    task = "客人来了，准备一杯红茶和一杯常温水，用托盘端到服务台。桌上的旧报纸顺手扔了。如果玻璃杯不适合泡茶，换成马克杯。"
    blocked = begin_motion_command(graph_session["session_id"], task)
    require(blocked.get("status") == "causal_graph_clarification_required", f"temperature gap did not block graph execution: {blocked}")
    require((blocked.get("pending_condition") or {}).get("condition") == "brewing_temperature_sufficient", f"wrong graph condition requested: {blocked}")
    inventory_query = begin_motion_command(graph_session["session_id"], "桌子上有什么")
    require(inventory_query.get("status") == "support_inventory_state_answered", f"read-only query was consumed by graph clarification: {inventory_query}")
    require(get_session(graph_session["session_id"]).get("causal_graph_clarification", {}).get("condition") == "brewing_temperature_sufficient", f"query consumed the pending graph condition: {inventory_query}")
    repeated_start = begin_motion_command(graph_session["session_id"], "嗯，开始吧")
    require(repeated_start.get("status") == "causal_graph_clarification_required", f"generic start acknowledgement consumed unresolved condition: {repeated_start}")
    started = begin_motion_command(graph_session["session_id"], "按常温方式准备")
    require(started.get("status") == "motion_started", f"resolved graph did not start first ready node: {started}")
    node_order, route_segment_counts, final_result = drain_graph(started)
    expected_order = [
        "clear_old_newspapers",
        "prepare_black_tea",
        "prepare_room_temperature_water",
        "acquire_tray",
        "load_tray",
        "deliver_tray",
        "handover_to_guest",
    ]
    require(node_order == expected_order, f"causal graph executed in the wrong fact-derived order: {node_order}")
    require(route_segment_counts.get("prepare_black_tea", 0) >= 4 and route_segment_counts.get("load_tray", 0) >= 4, f"compound nodes collapsed into an unobservable state jump: {route_segment_counts}")
    final_intent = final_result["long_horizon_intent"]
    require(final_intent["goal_fact"] == HOSPITALITY_GOAL and final_intent["lifecycle"] == "completed", f"hospitality root fact did not release the intent: {final_result}")
    live = get_session(graph_session["session_id"])
    runtime_objects = {item["entity_id"]: item for item in live["runtime_objects"]}
    require(live["active_intent_id"] is None, f"completed graph remained active: {live}")
    require(runtime_objects["newspaper_a"].get("contained_by") == runtime_objects["newspaper_b"].get("contained_by") == "trash_bin_hospitality", f"discard effects were not committed: {runtime_objects}")
    require(runtime_objects["mug_white"].get("support_ref") == runtime_objects["glass_tall"].get("support_ref") == "wooden_tray", f"join node did not load both vessels: {runtime_objects}")
    require(runtime_objects["wooden_tray"].get("received_by") == "guest", f"terminal handover relation missing: {runtime_objects}")
    post_task = begin_motion_command(
        graph_session["session_id"],
        "客人喝完了，把杯子还是放回桌子上",
    )
    require(post_task.get("status") == "process_slot_clarification_required", f"post-task placement was hijacked by the hospitality graph: {post_task}")
    require(post_task.get("status") != "causal_graph_clarification_required", f"completed graph restarted from a guest mention: {post_task}")
    require(get_session(graph_session["session_id"]).get("active_intent_id") is None, f"ambiguous post-task placement committed a new task snapshot: {post_task}")

    supersede_session = start_session("home_humanoid", "hospitality_guest")
    pending_graph = begin_motion_command(supersede_session["session_id"], task)
    old_intent_id = get_session(supersede_session["session_id"])["active_intent_id"]
    require(pending_graph.get("status") == "causal_graph_clarification_required", f"precondition for supersession test missing: {pending_graph}")
    superseding_task = begin_motion_command(
        supersede_session["session_id"],
        "客人喝完了，把杯子放回桌子上",
    )
    superseded_live = get_session(supersede_session["session_id"])
    require(superseding_task.get("status") == "process_slot_clarification_required", f"new task was consumed as an old graph answer: {superseding_task}")
    require(superseded_live.get("causal_graph_clarification") is None, f"new task left the old condition dialogue active: {superseded_live}")
    require(any(item.get("intent_id") == old_intent_id and item.get("lifecycle") == "superseded" for item in superseded_live.get("released_intent_archive", [])), f"superseded task snapshot was not released: {superseded_live}")
    print({"scene": scene["scene_id"], "goal": graph["goal_fact"], "parallel_branches": graph["parallel_ready_branches"], "execution_order": node_order, "route_segment_counts": route_segment_counts, "missing_conditions": missing, "status": "passed"})


if __name__ == "__main__":
    main()
