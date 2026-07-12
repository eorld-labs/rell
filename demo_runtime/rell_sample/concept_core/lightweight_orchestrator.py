from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any


FACT_PRODUCER_CONTRACTS: dict[str, dict[str, Any]] = {
    "object_grounded": {"operator": "observe_entity", "requires": ["sensor_available"], "capability": "active_perception", "execution_kind": "runtime_capability"},
    "target_grounded": {"operator": "observe_entity", "requires": ["sensor_available"], "capability": "active_perception", "execution_kind": "runtime_capability"},
    "device_grounded": {"operator": "observe_entity", "requires": ["sensor_available"], "capability": "active_perception", "execution_kind": "runtime_capability"},
    "destination_grounded": {"operator": "observe_or_clarify_destination", "requires": [], "capability": "active_perception", "execution_kind": "runtime_or_human"},
    "direction_reference_grounded": {"operator": "resolve_reference_frame", "requires": [], "capability": "semantic_clarification", "execution_kind": "human_interaction"},
    "object_within_reach": {"operator": "navigate_until_target_within_reach", "requires": ["object_grounded", "route_feasible"], "capability": "navigate_to_region", "execution_kind": "experience_or_runtime_capability"},
    "gripper_available": {"operator": "release_or_place_held_object", "requires": ["object_in_gripper", "release_space_safe"], "capability": "release_object", "execution_kind": "experience_or_runtime_capability"},
    "object_in_gripper": {"operator": "grasp_object", "requires": ["object_grounded", "object_within_reach", "gripper_available"], "capability": "grasp_object", "execution_kind": "experience_required"},
    "route_feasible": {"operator": "plan_or_detour_route", "requires": [], "capability": "local_obstacle_avoidance", "execution_kind": "runtime_capability"},
    "release_space_safe": {"operator": "find_safe_release_space", "requires": ["sensor_available"], "capability": "active_perception", "execution_kind": "runtime_capability"},
    "placement_pose_feasible": {"operator": "compute_current_body_placement_candidate", "requires": ["destination_grounded"], "capability": "place_object", "execution_kind": "experience_required"},
    "interaction_part_grounded": {"operator": "locate_interaction_part", "requires": ["object_grounded", "sensor_available"], "capability": "active_perception", "execution_kind": "runtime_or_teaching"},
    "control_grounded": {"operator": "locate_device_control", "requires": ["device_grounded", "sensor_available"], "capability": "active_perception", "execution_kind": "runtime_or_teaching"},
    "contact_pose_feasible": {"operator": "compute_safe_contact_pose", "requires": ["object_grounded"], "capability": "apply_controlled_force", "execution_kind": "experience_required"},
    "contaminant_observed": {"operator": "observe_surface_contaminant", "requires": ["target_grounded", "sensor_available"], "capability": "active_perception", "execution_kind": "runtime_capability"},
    "source_contains_material": {"operator": "verify_source_material_state", "requires": ["sensor_available"], "capability": "active_perception", "execution_kind": "runtime_capability"},
    "transfer_path_feasible": {"operator": "plan_material_transfer_alignment", "requires": ["source_contains_material", "destination_grounded"], "capability": "transfer_material", "execution_kind": "experience_required"},
    "safe_to_hold": {"operator": "enter_safe_hold_state", "requires": [], "capability": "stop_current_activity", "execution_kind": "runtime_capability"},
}


def _node_id(operator: str, produces: str) -> str:
    return "subgoal_" + hashlib.sha1(f"{operator}|{produces}".encode("utf-8")).hexdigest()[:10]


def build_lightweight_causal_candidate(
    *,
    goal_concept: dict[str, Any],
    fact_snapshot: dict[str, Any],
    supported_capabilities: list[str],
    available_experience_capabilities: list[str],
) -> dict[str, Any]:
    established = set(fact_snapshot.get("established_facts", []))
    supported = set(supported_capabilities)
    experienced = set(available_experience_capabilities)
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    unresolved: list[dict[str, Any]] = []
    cycles: list[dict[str, Any]] = []

    def ensure_fact(fact: str, stack: list[str]) -> str | None:
        if fact in established:
            return None
        if fact in stack:
            cycles.append({"fact": fact, "stack": stack + [fact]})
            return None
        producer = FACT_PRODUCER_CONTRACTS.get(fact)
        if not producer:
            unresolved.append({"fact": fact, "reason": "no_factory_producer_contract"})
            return None
        node_id = _node_id(producer["operator"], fact)
        if node_id in nodes:
            return node_id
        capability = producer["capability"]
        capability_available = capability in supported
        experience_required = producer["execution_kind"] == "experience_required"
        experience_available = capability in experienced
        if not capability_available:
            gate = "blocked_by_body_capability"
        elif experience_required and not experience_available:
            gate = "blocked_by_missing_experience"
        elif producer["execution_kind"] == "human_interaction":
            gate = "requires_human_interaction"
        else:
            gate = "candidate_ready_for_orchestration"
        nodes[node_id] = {
            "node_id": node_id,
            "operator": producer["operator"],
            "produces_fact": fact,
            "requires": deepcopy(producer["requires"]),
            "required_capability": capability,
            "execution_kind": producer["execution_kind"],
            "capability_available": capability_available,
            "experience_required": experience_required,
            "experience_available": experience_available,
            "gate": gate,
            "candidate_only": True,
        }
        for requirement in producer["requires"]:
            dependency_id = ensure_fact(requirement, stack + [fact])
            if dependency_id:
                edges.append({"from": dependency_id, "to": node_id, "fact": requirement})
        return node_id

    goal_requires = goal_concept.get("effect_contract", {}).get("requires", [])
    goal_node_id = "goal_" + hashlib.sha1(
        f"{goal_concept.get('operator')}|{goal_concept.get('recognized_goal_fact')}".encode("utf-8")
    ).hexdigest()[:10]
    goal_capability = goal_concept.get("required_capability")
    goal_capability_available = goal_capability in supported
    goal_experience_available = goal_capability in experienced
    if not goal_capability_available:
        goal_gate = "blocked_by_body_capability"
    elif not goal_experience_available:
        goal_gate = "blocked_by_missing_experience"
    else:
        goal_gate = "candidate_ready_for_orchestration"
    nodes[goal_node_id] = {
        "node_id": goal_node_id,
        "operator": goal_concept.get("operator"),
        "produces_fact": goal_concept.get("recognized_goal_fact"),
        "requires": deepcopy(goal_requires),
        "required_capability": goal_capability,
        "execution_kind": "experience_required",
        "capability_available": goal_capability_available,
        "experience_required": True,
        "experience_available": goal_experience_available,
        "gate": goal_gate,
        "is_goal_event": True,
        "candidate_only": True,
    }
    for requirement in goal_requires:
        dependency_id = ensure_fact(requirement, [])
        if dependency_id:
            edges.append({"from": dependency_id, "to": goal_node_id, "fact": requirement})

    ordered: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            cycles.append({"node_id": node_id, "reason": "candidate_graph_cycle"})
            return
        visiting.add(node_id)
        for edge in edges:
            if edge["to"] == node_id:
                visit(edge["from"])
        visiting.remove(node_id)
        visited.add(node_id)
        ordered.append(node_id)

    visit(goal_node_id)
    ordered_nodes = [nodes[node_id] for node_id in ordered]
    blocked_nodes = [node for node in ordered_nodes if node["gate"] != "candidate_ready_for_orchestration"]
    return {
        "schema_version": "1.0.0",
        "planner_type": "factory_lightweight_backward_chaining",
        "goal_node_id": goal_node_id,
        "world_revision": fact_snapshot.get("world_revision"),
        "nodes": ordered_nodes,
        "edges": edges,
        "candidate_process_chain": [node["operator"] for node in ordered_nodes],
        "blocked_nodes": blocked_nodes,
        "unresolved_facts": unresolved,
        "cycles": cycles,
        "candidate_status": "blocked_candidate" if blocked_nodes or unresolved or cycles else "candidate_ready_for_runtime_arbitration",
        "candidate_only": True,
        "direct_execution_allowed": False,
        "must_reenter_orchestration_layer": True,
        "must_recheck_world_revision_before_each_node": True,
        "runtime_fact_committed": False,
    }


def build_lightweight_orchestrator_catalog() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "catalog_type": "factory_lightweight_causal_orchestrator",
        "fact_producer_contracts": deepcopy(FACT_PRODUCER_CONTRACTS),
        "boundary": {
            "candidate_only": True,
            "direct_execution_allowed": False,
            "fixed_task_script_forbidden": True,
            "backward_chain_from_current_fact_gap": True,
            "world_revision_recheck_required": True,
        },
    }
