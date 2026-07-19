from __future__ import annotations

from concept_core.task_horizon import classify_execution_horizon
from embodied_scene import begin_motion_command, start_session


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    verbose_single_goal = classify_execution_horizon(
        goal_facts=["object_supported_at_destination"],
        nodes=[
            {"stage_id": "acquire", "produces": "object_in_effector"},
            {
                "stage_id": "place",
                "requires": "object_in_effector",
                "produces": "object_supported_at_destination",
            },
        ],
        verified_facts=[],
    )
    require(
        verbose_single_goal["horizon_class"] == "short_horizon"
        and verbose_single_goal["metrics"]["single_chain"] is True
        and verbose_single_goal["utterance_length_used_for_classification"] is False,
        f"a bounded single relation was not classified as short: {verbose_single_goal}",
    )

    composite_graph = {
        "nodes": [
            {"node_id": "inspect", "produces": ["resources_grounded"]},
            {"node_id": "prepare_a", "requires": ["resources_grounded"], "produces": ["component_a_ready"]},
            {"node_id": "prepare_b", "requires": ["resources_grounded"], "produces": ["component_b_ready"]},
            {"node_id": "assemble", "requires": ["component_a_ready", "component_b_ready"], "produces": ["bundle_ready"]},
            {"node_id": "deliver", "requires": ["bundle_ready"], "produces": ["recipient_received_bundle"]},
        ],
        "edges": [
            {"from": "inspect", "to": "prepare_a"},
            {"from": "inspect", "to": "prepare_b"},
            {"from": "prepare_a", "to": "assemble"},
            {"from": "prepare_b", "to": "assemble"},
            {"from": "assemble", "to": "deliver"},
        ],
    }
    composite = classify_execution_horizon(
        goal_facts=["recipient_received_bundle"],
        nodes=composite_graph["nodes"],
        edges=composite_graph["edges"],
        join_nodes=["assemble"],
        verified_facts=[],
        unresolved_conditions=["preference_or_resource_condition"],
    )
    require(
        composite["horizon_class"] == "long_horizon"
        and composite["metrics"]["branch_node_count"] == 1
        and composite["metrics"]["join_node_count"] == 1,
        f"a branched causal graph was not classified as long: {composite}",
    )

    collapsed = classify_execution_horizon(
        goal_facts=["recipient_received_bundle"],
        nodes=composite_graph["nodes"],
        edges=composite_graph["edges"],
        join_nodes=["assemble"],
        verified_facts=[
            "resources_grounded",
            "component_a_ready",
            "component_b_ready",
            "bundle_ready",
        ],
        previous_horizon_class="long_horizon",
    )
    require(
        collapsed["horizon_class"] == "atomic_action"
        and collapsed["dynamic_transition"] == {
            "previous": "long_horizon",
            "current": "atomic_action",
            "changed": True,
        },
        f"verified facts did not collapse the remaining graph dynamically: {collapsed}",
    )

    multiple_goals = classify_execution_horizon(
        goal_facts=["first_goal", "second_goal"],
        nodes=[
            {"node_id": "first", "produces": ["first_goal"]},
            {"node_id": "second", "produces": ["second_goal"]},
        ],
        verified_facts=[],
    )
    require(
        multiple_goals["horizon_class"] == "long_horizon",
        f"multiple independent goals were reduced to a short task: {multiple_goals}",
    )

    undecomposed = classify_execution_horizon(
        goal_facts=["macro_goal"],
        nodes=[],
        verified_facts=[],
        decomposition_gaps=["no_registered_causal_schema"],
    )
    require(
        undecomposed["horizon_class"] == "decomposition_required"
        and "unresolved_causal_schema" in undecomposed["memory_contract"]["retain_until_completion"],
        f"an unknown macro goal was guessed as short or long before decomposition: {undecomposed}",
    )

    completed = classify_execution_horizon(
        goal_facts=["object_supported_at_destination"],
        nodes=verbose_single_goal.get("nodes", []),
        verified_facts=["object_supported_at_destination"],
    )
    require(
        completed["horizon_class"] == "completed"
        and completed["memory_contract"]["release_on_goal_verification"] == "already_released",
        f"completed task mechanics were not marked for release: {completed}",
    )

    placement_session = start_session("home_humanoid", "home_semantic_3d_a")
    placement = begin_motion_command(
        placement_session["session_id"], "把苹果放到操作台上"
    )
    placement_intent = placement.get("long_horizon_intent") or (
        placement.get("immediate_result") or {}
    ).get("long_horizon_intent") or {}
    require(
        placement_intent.get("execution_horizon", {}).get("horizon_class")
        == "short_horizon",
        f"runtime storage name forced a simple placement to long horizon: {placement}",
    )

    graph_session = start_session("home_humanoid", "hospitality_guest")
    graph_started = begin_motion_command(
        graph_session["session_id"],
        "客人来了，准备一杯红茶和一杯常温水，用托盘端到服务台。桌上的旧报纸顺手扔了。",
    )
    graph_intent = graph_started.get("long_horizon_intent") or (
        graph_started.get("immediate_result") or {}
    ).get("long_horizon_intent") or {}
    require(
        graph_intent.get("execution_horizon", {}).get("horizon_class")
        == "long_horizon",
        f"runtime branched task graph was not classified as long: {graph_started}",
    )
    print({
        "status": "passed",
        "verbose_single_goal": verbose_single_goal["horizon_class"],
        "composite_graph": composite["horizon_class"],
        "collapsed_after_facts": collapsed["horizon_class"],
        "undecomposed_macro_goal": undecomposed["horizon_class"],
        "runtime_placement": placement_intent["execution_horizon"]["horizon_class"],
        "runtime_composite_graph": graph_intent["execution_horizon"]["horizon_class"],
    })


if __name__ == "__main__":
    main()
