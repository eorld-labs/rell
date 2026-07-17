from __future__ import annotations

from concept_core.situated_event_reasoning import (
    attach_opportunistic_subgoal,
    compile_situated_event_frame,
    create_hierarchical_intent_graph,
    decompose_intent_node,
    focus_scope,
    ready_leaf_nodes,
    record_verified_fact,
)
from embodied_scene import SESSIONS, _replan_state_fingerprint, _resume_after_local_path_change, start_session


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_situated_language_frame() -> dict:
    analysis = {
        "speech_act": "task_request",
        "canonical_frame": {"operators": ["place_object"], "goal_relation": "object_supported_at_destination"},
        "role_bindings": {
            "theme": {"entity_ref": "apple_a", "concept_id": "concept_edible_apple", "matched_alias": "苹果"},
            "destination": {"concept_id": "concept_support_surface", "matched_alias": "桌子"},
        },
        "entity_mentions": [
            {"concept_id": "concept_edible_apple", "matched_alias": "苹果"},
            {"concept_id": "concept_fillable_container", "matched_alias": "杯子"},
            {"concept_id": "concept_support_surface", "matched_alias": "桌子"},
        ],
        "unresolved_slots": ["historical_support_reference_requires_human_confirmation"],
    }
    frame = compile_situated_event_frame(
        "把苹果放在刚才放杯子的桌子上",
        analysis,
        current_facts=[{"predicate": "present_in_world", "subject": "apple_a", "evidence": "runtime_snapshot"}],
        recent_episodes=[{"episode_id": "episode_grasp_cup_1"}],
    )
    require(frame["operators"] == ["place_object"], f"event operator was not retained: {frame}")
    require(frame["temporal_scope"] == "most_recent_verified_past", f"temporal model was lost: {frame}")
    require(frame["expected_goal_facts"][0]["predicate"] == "supported_by", f"expected world change was not projected: {frame}")
    require(frame["current_fact_snapshot"] and frame["evidence_boundary"]["language_does_not_commit_physical_facts"], f"fact/expectation boundary missing: {frame}")
    return {"frame_id": frame["frame_id"], "unresolved_slots": frame["unresolved_slots"]}


def validate_human_participation_completion_report() -> dict:
    analysis = {
        "speech_act": "task_request",
        "canonical_frame": {"operators": ["place_object"], "goal_relation": "object_supported_at_destination"},
        "role_bindings": {
            "theme": {"entity_ref": "cup_b", "concept_id": "concept_fillable_container", "matched_alias": "杯子"},
            "destination": {"entity_ref": "dining_table_b", "concept_id": "concept_support_surface", "matched_alias": "餐桌"},
        },
        "unresolved_slots": [],
    }
    frame = compile_situated_event_frame(
        "我检查完了，把杯子放到餐桌上",
        analysis,
        current_facts=[{"predicate": "received_by", "subject": "cup_b", "object": "human_b", "evidence": "runtime_verified"}],
        recent_episodes=[],
    )
    completion = next(
        item for item in frame["reported_state_candidates"]
        if item.get("predicate") == "human_participated_event_reported_complete"
    )
    require(completion.get("event_surface") == "检查", f"human-side completed event was not abstracted from the utterance: {frame}")
    require(completion.get("possible_transition") == "human_participation_stage_completed", f"reported completion did not expose a stage-transition candidate: {completion}")
    require("task_terminal_fact" in completion.get("does_not_directly_prove", []), f"human report incorrectly became physical task truth: {completion}")
    return {"predicate": completion["predicate"], "event_surface": completion["event_surface"], "committed": False}


def validate_nested_and_interrupted_intent() -> dict:
    graph = create_hierarchical_intent_graph(
        "trash_round_trip",
        root_goal_facts=["trash_disposed", "executor_home_after_disposal"],
        stages=[
            {"stage_id": "leave_home", "produces": "executor_outside"},
            {"stage_id": "descend", "requires": "executor_outside", "produces": "executor_downstairs"},
            {"stage_id": "dispose_trash", "requires": "executor_downstairs", "produces": "trash_disposed"},
            {"stage_id": "return_home", "requires": "trash_disposed", "produces": "executor_home_after_disposal"},
        ],
    )
    leave_id = "trash_round_trip:leave_home"
    decompose_intent_node(
        graph,
        parent_node_id=leave_id,
        stages=[
            {"stage_id": "take_trash", "requires": "trash_available", "produces": "trash_in_hand"},
            {"stage_id": "open_door", "requires": "trash_in_hand", "produces": "door_open"},
            {"stage_id": "cross_door", "requires": "door_open", "produces": "executor_outside"},
            {"stage_id": "close_door", "requires": "executor_outside", "produces": "door_closed"},
        ],
    )
    scope = focus_scope(graph, leave_id)
    require(scope["is_local_stage_of"] == ["trash_round_trip:root"], f"relative local scope missing: {scope}")
    require(scope["is_current_global_for_descendants"], f"nested stage did not become a global goal for its own execution: {scope}")

    record_verified_fact(graph, "trash_available")
    require(ready_leaf_nodes(graph)[0]["label"] == "take_trash", f"wrong first grounded leaf: {ready_leaf_nodes(graph)}")
    for fact in ("trash_in_hand", "door_open", "executor_outside", "door_closed", "executor_downstairs", "trash_disposed"):
        record_verified_fact(graph, fact)

    added = attach_opportunistic_subgoal(
        graph,
        parent_node_id=graph["root_node_id"],
        subgoal_id="carry_child_item_upstairs",
        goal_facts=["child_item_delivered_upstairs"],
        requires=["trash_disposed", "child_item_available"],
        compatibility_constraints=["shared_with_return_route", "carrying_capacity_available", "sanitary_separation_satisfied"],
    )
    require(added["merge_requires_runtime_arbitration"], f"interaction subgoal bypassed arbitration: {added}")
    require("child_item_delivered_upstairs" in graph["nodes"][graph["root_node_id"]]["goal_facts"], f"accepted subgoal did not extend the unfinished global goal: {graph}")
    record_verified_fact(graph, "child_item_available")
    ready_labels = {item["label"] for item in ready_leaf_nodes(graph)}
    require("return_home" in ready_labels and "carry_child_item_upstairs" in ready_labels, f"return and opportunistic goal were not jointly available for arbitration: {ready_labels}")
    record_verified_fact(graph, "child_item_delivered_upstairs")
    record_verified_fact(graph, "executor_home_after_disposal")
    require(graph["lifecycle"] == "completed", f"verified child and original goal did not close the merged intent: {graph}")
    return {"graph_id": graph["graph_id"], "merged_subgoal": added["node_id"], "lifecycle": graph["lifecycle"]}


def validate_replan_convergence() -> dict:
    started = start_session("home_humanoid", "home_semantic_3d_a")
    session = SESSIONS[started["session_id"]]
    obstacle = next(item for item in session["runtime_objects"] if item["entity_id"] == "sofa_route_a1")
    job = {
        "job_id": "synthetic_stalled_replan",
        "session_id": session["session_id"],
        "utterance": "走到操作台",
        "continuation_authorized": True,
        "execution_intent": {"action": "grasp", "target_entity_ref": "cup_a"},
        "post_completion": {"action": "grasp", "target_entity_ref": "cup_a"},
    }
    fingerprint = _replan_state_fingerprint(job, session, "next_frame_swept_body_not_clear", obstacle)
    job["replan_state_history"] = [fingerprint, fingerprint]
    stopped = _resume_after_local_path_change(job, session, "next_frame_swept_body_not_clear", obstacle)
    result = stopped.get("result", {})
    require(stopped.get("status") == "motion_completed", f"identical replanning state did not terminate the browser loop: {stopped}")
    require(result.get("status") == "replanning_stalled_by_persistent_constraint", f"stalled replanning reason was not exposed: {stopped}")
    require(result.get("replan_convergence", {}).get("new_world_information_observed") is False, f"replanning without new information was misreported: {stopped}")
    return {"status": result["status"], "identical_state_count": result["replan_convergence"]["identical_state_count"]}


def main() -> None:
    report = {
        "situated_language": validate_situated_language_frame(),
        "human_participation_completion": validate_human_participation_completion_report(),
        "nested_interrupted_intent": validate_nested_and_interrupted_intent(),
        "replan_convergence": validate_replan_convergence(),
    }
    print("Situated event and hierarchical intent validation passed.")
    print(report)


if __name__ == "__main__":
    main()
