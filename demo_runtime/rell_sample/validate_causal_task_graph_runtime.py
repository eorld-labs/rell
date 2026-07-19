from __future__ import annotations

from causal_task_graph_runtime import (
    apply_condition_answer,
    causal_graph_activation_matches,
    evaluate_causal_graph,
    initialize_causal_graph_runtime,
    record_graph_facts,
    select_condition_clarification,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    graph = {
        "goal_fact": "bundle_delivered",
        "activation_contract": {
            "speech_acts": ["task_request"],
            "operators_any": ["transport_object"],
            "goal_relations_any": ["object_at_target_region"],
        },
        "roles": {"resource": "resource_a"},
        "world_fact_rules": {
            "resource_present": {"operator": "role_exists", "role": "resource"},
        },
        "condition_resolutions": {
            "quality_sufficient": {
                "priority": 10,
                "question": "允许按当前质量继续吗？",
                "options": [{
                    "option_id": "accept_current_quality",
                    "aliases": ["允许继续"],
                    "establishes": ["quality_exception_authorized"],
                }],
            }
        },
        "nodes": [
            {"node_id": "observe", "priority": 10, "requires": [], "produces": ["resources_grounded"], "execution_contract": {"mode": "epistemic"}},
            {"node_id": "branch_a", "priority": 20, "requires": ["resources_grounded", "resource_present"], "produces": ["branch_a_ready"], "execution_contract": {"mode": "motion_effect"}},
            {"node_id": "branch_b", "priority": 30, "requires": ["resources_grounded"], "requires_any": [["quality_sufficient", "quality_exception_authorized"]], "produces": ["branch_b_ready"], "execution_contract": {"mode": "motion_effect"}},
            {"node_id": "join", "priority": 40, "requires": ["branch_a_ready", "branch_b_ready"], "produces": ["bundle_delivered"], "execution_contract": {"mode": "motion_effect"}},
        ],
    }
    objects = [{"entity_id": "resource_a", "kind": "unfamiliar_resource", "active": True}]
    matching_language = {
        "speech_act": "task_request",
        "event_candidates": [{"operator": "transport_object"}],
        "canonical_frame": {"goal_relation": "object_at_target_region"},
    }
    unrelated_language = {
        "speech_act": "task_request",
        "event_candidates": [{"operator": "place_object"}],
        "canonical_frame": {"goal_relation": "object_supported_at_destination"},
    }
    require(causal_graph_activation_matches(graph, matching_language), "matching composed goal did not activate a generic graph")
    require(not causal_graph_activation_matches(graph, unrelated_language), "scene availability overrode an unrelated composed goal")
    runtime = initialize_causal_graph_runtime(graph, world_revision=0)
    first = evaluate_causal_graph(graph, runtime, objects, world_revision=0)
    require([node["node_id"] for node in first["ready_nodes"]] == ["observe"], f"root epistemic node was not ready: {first}")
    record_graph_facts(runtime, ["resources_grounded"], source="test_epistemic", node_id="observe", world_revision=0, physical_verification=True)
    second = evaluate_causal_graph(graph, runtime, objects, world_revision=0)
    require([node["node_id"] for node in second["ready_nodes"]] == ["branch_a"], f"ready branch calculation ignored a blocked sibling: {second}")
    clarification = select_condition_clarification(graph, second)
    require(clarification and clarification["condition"] == "quality_sufficient", f"generic missing condition was not exposed: {second}")
    runtime["pending_condition"] = clarification
    resolved = apply_condition_answer(graph, runtime, "允许继续", world_revision=0)
    require(resolved["status"] == "condition_resolved" and "quality_exception_authorized" in resolved["established_facts"], f"generic condition answer failed: {resolved}")
    third = evaluate_causal_graph(graph, runtime, objects, world_revision=0)
    require([node["node_id"] for node in third["ready_nodes"]] == ["branch_a", "branch_b"], f"parallel branches were not simultaneously ready: {third}")
    record_graph_facts(runtime, ["branch_a_ready"], source="test_node", node_id="branch_a", world_revision=0, physical_verification=True)
    after_a = evaluate_causal_graph(graph, runtime, objects, world_revision=0)
    require([node["node_id"] for node in after_a["ready_nodes"]] == ["branch_b"] and any(item["node_id"] == "join" for item in after_a["waiting_nodes"]), f"join opened before every predecessor: {after_a}")
    record_graph_facts(runtime, ["branch_b_ready"], source="test_node", node_id="branch_b", world_revision=0, physical_verification=True)
    after_b = evaluate_causal_graph(graph, runtime, objects, world_revision=0)
    require([node["node_id"] for node in after_b["ready_nodes"]] == ["join"], f"join did not open after all predecessors: {after_b}")
    record_graph_facts(runtime, ["bundle_delivered"], source="test_node", node_id="join", world_revision=0, physical_verification=True)
    completed = evaluate_causal_graph(graph, runtime, objects, world_revision=0)
    require(completed["goal_established"], f"generic graph root fact did not terminate: {completed}")
    print({"status": "passed", "ready_parallel": ["branch_a", "branch_b"], "join": "verified_fact_gated", "goal": graph["goal_fact"]})


if __name__ == "__main__":
    main()
