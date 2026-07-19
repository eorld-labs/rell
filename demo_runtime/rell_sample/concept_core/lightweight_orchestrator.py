from __future__ import annotations

import hashlib
from copy import deepcopy
from time import perf_counter_ns
from typing import Any

from .task_horizon import classify_execution_horizon


_REGISTRY_CACHE: dict[str, dict[str, Any]] = {}


ATOMIC_CAUSAL_OPERATORS: list[dict[str, Any]] = [
    {"operator": "observe_entity", "requires": ["sensor_available"], "produces": ["object_grounded", "target_grounded", "device_grounded"], "destroys": [], "capability": "active_perception", "execution_kind": "runtime_capability", "origin": "atomic_perception_mechanism"},
    {"operator": "observe_or_clarify_destination", "requires": [], "produces": ["destination_grounded"], "destroys": [], "capability": "active_perception", "execution_kind": "runtime_or_human", "origin": "atomic_grounding_mechanism"},
    {"operator": "resolve_reference_frame", "requires": [], "produces": ["direction_reference_grounded"], "destroys": [], "capability": "semantic_clarification", "execution_kind": "human_interaction", "origin": "atomic_grounding_mechanism"},
    {"operator": "navigate_until_target_within_reach", "requires": ["object_grounded", "route_feasible"], "produces": ["object_within_reach"], "destroys": ["object_out_of_reach"], "capability": "navigate_to_region", "execution_kind": "experience_or_runtime_capability", "origin": "atomic_spatial_mechanism"},
    {"operator": "plan_or_detour_route", "requires": [], "produces": ["route_feasible"], "destroys": ["route_blocked"], "capability": "local_obstacle_avoidance", "execution_kind": "runtime_capability", "origin": "atomic_spatial_mechanism"},
    {"operator": "find_safe_release_space", "requires": ["sensor_available"], "produces": ["release_space_safe"], "destroys": [], "capability": "active_perception", "execution_kind": "runtime_capability", "origin": "atomic_safety_mechanism"},
    {"operator": "compute_current_body_placement_candidate", "requires": ["destination_grounded"], "produces": ["placement_pose_feasible"], "destroys": [], "capability": "place_object", "execution_kind": "runtime_planning", "origin": "atomic_geometric_mechanism"},
    {"operator": "compute_safe_contact_pose", "requires": ["object_grounded"], "produces": ["contact_pose_feasible"], "destroys": [], "capability": "apply_controlled_force", "execution_kind": "runtime_planning", "origin": "atomic_geometric_mechanism"},
    {"operator": "plan_material_transfer_alignment", "requires": ["source_contains_material", "destination_grounded"], "produces": ["transfer_path_feasible"], "destroys": [], "capability": "transfer_material", "execution_kind": "runtime_planning", "origin": "atomic_geometric_mechanism"},
    {"operator": "locate_interaction_part", "requires": ["object_grounded", "sensor_available"], "produces": ["interaction_part_grounded"], "destroys": [], "capability": "active_perception", "execution_kind": "runtime_or_teaching", "origin": "atomic_perception_mechanism"},
    {"operator": "locate_device_control", "requires": ["device_grounded", "sensor_available"], "produces": ["control_grounded"], "destroys": [], "capability": "active_perception", "execution_kind": "runtime_or_teaching", "origin": "atomic_perception_mechanism"},
    {"operator": "observe_surface_contaminant", "requires": ["target_grounded", "sensor_available"], "produces": ["contaminant_observed"], "destroys": [], "capability": "active_perception", "execution_kind": "runtime_capability", "origin": "atomic_perception_mechanism"},
    {"operator": "verify_source_material_state", "requires": ["sensor_available"], "produces": ["source_contains_material"], "destroys": [], "capability": "active_perception", "execution_kind": "runtime_capability", "origin": "atomic_perception_mechanism"},
    {"operator": "enter_safe_hold_state", "requires": [], "produces": ["safe_to_hold", "activity_stopped"], "destroys": ["activity_active"], "capability": "stop_current_activity", "execution_kind": "runtime_capability", "origin": "atomic_safety_mechanism"},
]


FACT_IMPLICATIONS: dict[str, list[str]] = {
    "gripper_empty": ["gripper_available"],
    "object_in_gripper": ["object_grounded", "object_within_reach"],
    "executor_at_destination": ["route_feasible"],
}


def compile_causal_operator_registry(
    *,
    event_concepts: list[dict[str, Any]],
    experience_contracts: list[dict[str, Any]] | None = None,
    cache_key: str | None = None,
) -> dict[str, Any]:
    if cache_key and cache_key in _REGISTRY_CACHE:
        return _REGISTRY_CACHE[cache_key]
    operators = deepcopy(ATOMIC_CAUSAL_OPERATORS)
    for concept in event_concepts:
        kernel = concept.get("concept_kernel", {})
        effect = kernel.get("effect_contract", {})
        operators.append({
            "operator": kernel.get("operator"),
            "requires": deepcopy(effect.get("requires", [])),
            "produces": deepcopy(effect.get("produces", [])),
            "destroys": deepcopy(effect.get("destroys", [])),
            "verification": deepcopy(effect.get("verification", [])),
            "capability": concept.get("capability"),
            "execution_kind": "experience_required",
            "origin": "factory_event_concept",
            "source_ref": concept.get("concept_id"),
        })
    for experience in experience_contracts or []:
        effect = experience.get("effect_contract", {})
        process_chain = experience.get("process_chain", [])
        operators.append({
            "operator": "replay_invariant_experience:" + str(experience.get("experience_id")),
            "requires": deepcopy(effect.get("requires", [])),
            "produces": deepcopy(effect.get("produces", [])),
            "destroys": deepcopy(effect.get("destroys", [])),
            "verification": deepcopy(effect.get("verification", [])),
            "capability": experience.get("required_capability"),
            "execution_kind": "trusted_experience",
            "origin": "trusted_experience_contract",
            "source_ref": experience.get("experience_id"),
            "abstract_process_chain": deepcopy(process_chain),
        })
    operators = [item for item in operators if item.get("operator") and item.get("produces")]
    producer_index: dict[str, list[int]] = {}
    for index, operator in enumerate(operators):
        for fact in operator["produces"]:
            producer_index.setdefault(fact, []).append(index)
    registry = {
        "operators": operators,
        "producer_index": producer_index,
        "operator_count": len(operators),
        "produced_fact_count": len(producer_index),
        "compiled_from": {
            "atomic_operator_count": len(ATOMIC_CAUSAL_OPERATORS),
            "event_concept_count": len(event_concepts),
            "experience_contract_count": len(experience_contracts or []),
        },
    }
    if cache_key:
        _REGISTRY_CACHE[cache_key] = registry
    return registry


def _node_id(operator: str, produces: str) -> str:
    return "subgoal_" + hashlib.sha1(f"{operator}|{produces}".encode("utf-8")).hexdigest()[:10]


def build_lightweight_causal_candidate(
    *,
    goal_concept: dict[str, Any],
    fact_snapshot: dict[str, Any],
    supported_capabilities: list[str],
    available_experience_capabilities: list[str],
    event_concepts: list[dict[str, Any]],
    experience_contracts: list[dict[str, Any]] | None = None,
    registry_cache_key: str | None = None,
) -> dict[str, Any]:
    started_ns = perf_counter_ns()
    cache_hit = bool(registry_cache_key and registry_cache_key in _REGISTRY_CACHE)
    registry = compile_causal_operator_registry(
        event_concepts=event_concepts,
        experience_contracts=experience_contracts,
        cache_key=registry_cache_key,
    )
    registry_built_ns = perf_counter_ns()
    established = set(fact_snapshot.get("established_facts", []))
    implication_trace: list[dict[str, str]] = []
    changed = True
    while changed:
        changed = False
        for source_fact in list(established):
            for implied_fact in FACT_IMPLICATIONS.get(source_fact, []):
                if implied_fact not in established:
                    established.add(implied_fact)
                    implication_trace.append({"from": source_fact, "to": implied_fact})
                    changed = True
    supported = set(supported_capabilities)
    experienced = set(available_experience_capabilities)
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    unresolved: list[dict[str, Any]] = []
    cycles: list[dict[str, Any]] = []
    producer_index = registry["producer_index"]
    operators = registry["operators"]
    alternatives_considered = 0

    def gate_for(operator: dict[str, Any]) -> tuple[str, bool, bool]:
        capability = operator.get("capability")
        capability_available = not capability or capability in supported
        experience_required = operator.get("execution_kind") == "experience_required"
        experience_available = not experience_required or capability in experienced
        if not capability_available:
            gate = "blocked_by_body_capability"
        elif experience_required and not experience_available:
            gate = "blocked_by_missing_experience"
        elif operator.get("execution_kind") == "human_interaction":
            gate = "requires_human_interaction"
        else:
            gate = "candidate_ready_for_orchestration"
        return gate, capability_available, experience_available

    def producer_score(operator: dict[str, Any]) -> tuple[int, int, int]:
        gate, _, _ = gate_for(operator)
        gate_rank = 0 if gate == "candidate_ready_for_orchestration" else 1
        origin_rank = {"trusted_experience_contract": 0, "atomic_spatial_mechanism": 1, "atomic_perception_mechanism": 1, "atomic_grounding_mechanism": 1, "atomic_safety_mechanism": 1, "factory_event_concept": 2}.get(operator.get("origin"), 3)
        return gate_rank, origin_rank, len(operator.get("requires", []))

    def ensure_fact(fact: str, stack: list[str]) -> str | None:
        nonlocal alternatives_considered
        if fact in established:
            return None
        if fact in stack:
            cycles.append({"fact": fact, "stack": stack + [fact]})
            return None
        candidate_indices = producer_index.get(fact, [])
        alternatives_considered += len(candidate_indices)
        if not candidate_indices:
            unresolved.append({"fact": fact, "reason": "no_registered_causal_operator_produces_fact"})
            return None
        producer = min((operators[index] for index in candidate_indices), key=producer_score)
        node_id = _node_id(producer["operator"], fact)
        if node_id in nodes:
            return node_id
        gate, capability_available, experience_available = gate_for(producer)
        nodes[node_id] = {
            "node_id": node_id,
            "operator": producer["operator"],
            "produces_fact": fact,
            "produces": deepcopy(producer["produces"]),
            "destroys": deepcopy(producer.get("destroys", [])),
            "requires": deepcopy(producer.get("requires", [])),
            "required_capability": producer.get("capability"),
            "execution_kind": producer.get("execution_kind"),
            "operator_origin": producer.get("origin"),
            "source_ref": producer.get("source_ref"),
            "capability_available": capability_available,
            "experience_required": producer.get("execution_kind") == "experience_required",
            "experience_available": experience_available,
            "gate": gate,
            "candidate_only": True,
        }
        for requirement in producer.get("requires", []):
            dependency_id = ensure_fact(requirement, stack + [fact])
            if dependency_id:
                edges.append({"from": dependency_id, "to": node_id, "fact": requirement})
        return node_id

    goal_operator = {
        "operator": goal_concept.get("operator"),
        "requires": goal_concept.get("effect_contract", {}).get("requires", []),
        "produces": goal_concept.get("effect_contract", {}).get("produces", []),
        "destroys": goal_concept.get("effect_contract", {}).get("destroys", []),
        "capability": goal_concept.get("required_capability"),
        "execution_kind": "experience_required",
        "origin": "activated_goal_concept",
    }
    goal_fact = goal_concept.get("recognized_goal_fact")
    goal_node_id = "goal_" + hashlib.sha1(f"{goal_operator['operator']}|{goal_fact}".encode("utf-8")).hexdigest()[:10]
    goal_gate, goal_capability_available, goal_experience_available = gate_for(goal_operator)
    nodes[goal_node_id] = {
        "node_id": goal_node_id,
        "operator": goal_operator["operator"],
        "produces_fact": goal_fact,
        "produces": deepcopy(goal_operator["produces"]),
        "destroys": deepcopy(goal_operator["destroys"]),
        "requires": deepcopy(goal_operator["requires"]),
        "required_capability": goal_operator["capability"],
        "execution_kind": "experience_required",
        "operator_origin": "activated_goal_concept",
        "capability_available": goal_capability_available,
        "experience_required": True,
        "experience_available": goal_experience_available,
        "gate": goal_gate,
        "is_goal_event": True,
        "candidate_only": True,
    }
    for requirement in goal_operator["requires"]:
        dependency_id = ensure_fact(requirement, [])
        if dependency_id:
            edges.append({"from": dependency_id, "to": goal_node_id, "fact": requirement})

    searched_ns = perf_counter_ns()
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
    completed_ns = perf_counter_ns()
    candidate = {
        "schema_version": "2.0.0",
        "planner_type": "contract_compiled_backward_causal_search",
        "goal_node_id": goal_node_id,
        "world_revision": fact_snapshot.get("world_revision"),
        "registry_summary": {key: value for key, value in registry.items() if key not in {"operators", "producer_index"}},
        "fact_implication_trace": implication_trace,
        "nodes": ordered_nodes,
        "edges": edges,
        "candidate_process_chain": [node["operator"] for node in ordered_nodes],
        "blocked_nodes": blocked_nodes,
        "unresolved_facts": unresolved,
        "cycles": cycles,
        "search_metrics": {
            "nodes_explored": len(nodes),
            "edges_created": len(edges),
            "producer_alternatives_considered": alternatives_considered,
            "registry_compile_ms": round((registry_built_ns - started_ns) / 1_000_000, 4),
            "registry_cache_hit": cache_hit,
            "backward_search_ms": round((searched_ns - registry_built_ns) / 1_000_000, 4),
            "topological_sort_ms": round((completed_ns - searched_ns) / 1_000_000, 4),
            "total_solver_ms": round((completed_ns - started_ns) / 1_000_000, 4),
        },
        "candidate_status": "blocked_candidate" if blocked_nodes or unresolved or cycles else "candidate_ready_for_runtime_arbitration",
        "candidate_only": True,
        "direct_execution_allowed": False,
        "must_reenter_orchestration_layer": True,
        "must_recheck_world_revision_before_each_node": True,
        "runtime_fact_committed": False,
    }
    candidate["execution_horizon"] = classify_execution_horizon(
        goal_facts=[goal_fact] if goal_fact else [],
        nodes=ordered_nodes,
        edges=edges,
        verified_facts=established,
        decomposition_gaps=[*unresolved, *cycles],
    )
    return candidate


def build_lightweight_orchestrator_catalog(event_concepts: list[dict[str, Any]]) -> dict[str, Any]:
    registry = compile_causal_operator_registry(event_concepts=event_concepts)
    return {
        "schema_version": "2.0.0",
        "catalog_type": "contract_compiled_causal_operator_registry",
        "atomic_causal_operators": deepcopy(ATOMIC_CAUSAL_OPERATORS),
        "fact_implications": deepcopy(FACT_IMPLICATIONS),
        "registry_summary": {key: value for key, value in registry.items() if key not in {"operators", "producer_index"}},
        "boundary": {
            "candidate_only": True,
            "direct_execution_allowed": False,
            "fixed_task_script_forbidden": True,
            "business_event_specific_solver_code_forbidden": True,
            "event_concepts_register_automatically": True,
            "backward_chain_from_current_fact_gap": True,
            "world_revision_recheck_required": True,
        },
    }
