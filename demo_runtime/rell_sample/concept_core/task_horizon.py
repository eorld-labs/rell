from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_MAXIMUM_SHORT_CHAIN_NODES = 4


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple, set)) else [value]


def _node_id(node: dict[str, Any], index: int) -> str:
    return str(node.get("node_id") or node.get("stage_id") or f"node_{index}")


def _node_facts(node: dict[str, Any], key: str) -> set[str]:
    value = node.get(key)
    if value is None and key == "produces":
        value = node.get("produces_fact")
    return {str(item) for item in _as_list(value) if item}


def classify_execution_horizon(
    *,
    goal_facts: list[str],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
    join_nodes: list[str] | None = None,
    verified_facts: list[str] | set[str] | None = None,
    unresolved_conditions: list[Any] | None = None,
    decomposition_gaps: list[Any] | None = None,
    lifecycle: str | None = None,
    maximum_short_chain_nodes: int = DEFAULT_MAXIMUM_SHORT_CHAIN_NODES,
    previous_horizon_class: str | None = None,
) -> dict[str, Any]:
    """Classify runtime scope from the remaining causal graph, never text length."""
    verified = {str(item) for item in (verified_facts or []) if item}
    goals = [str(item) for item in goal_facts if item]
    normalized_nodes: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(nodes):
        node = deepcopy(source)
        node_id = _node_id(node, index)
        produces = _node_facts(node, "produces")
        requires = _node_facts(node, "requires")
        completed = bool(
            node.get("status") == "completed"
            or node.get("lifecycle") == "completed"
            or produces and produces.issubset(verified)
        )
        normalized_nodes[node_id] = {
            "node_id": node_id,
            "requires": requires,
            "produces": produces,
            "completed": completed,
        }

    goal_complete = bool(goals and set(goals).issubset(verified))
    if lifecycle == "completed" or goal_complete:
        horizon_class = "completed"
        remaining_ids: set[str] = set()
    else:
        remaining_ids = {
            node_id for node_id, node in normalized_nodes.items()
            if not node["completed"]
        }
        horizon_class = ""

    normalized_edges: set[tuple[str, str]] = set()
    for edge in edges or []:
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if source in remaining_ids and target in remaining_ids and source != target:
            normalized_edges.add((source, target))
    for producer_id in remaining_ids:
        produced = normalized_nodes[producer_id]["produces"]
        if not produced:
            continue
        for consumer_id in remaining_ids:
            if producer_id == consumer_id:
                continue
            if produced & normalized_nodes[consumer_id]["requires"]:
                normalized_edges.add((producer_id, consumer_id))

    incoming = {node_id: 0 for node_id in remaining_ids}
    outgoing = {node_id: 0 for node_id in remaining_ids}
    predecessors: dict[str, list[str]] = {node_id: [] for node_id in remaining_ids}
    for source, target in normalized_edges:
        outgoing[source] += 1
        incoming[target] += 1
        predecessors[target].append(source)

    explicit_joins = {
        node_id for node_id in set(join_nodes or []) & remaining_ids
        if len(normalized_nodes[node_id]["requires"] - verified) > 1
    }
    inferred_joins = {node_id for node_id, count in incoming.items() if count > 1}
    branch_nodes = {node_id for node_id, count in outgoing.items() if count > 1}
    join_ids = explicit_joins | inferred_joins

    depth_cache: dict[str, int] = {}
    visiting: set[str] = set()

    def depth(node_id: str) -> int:
        if node_id in depth_cache:
            return depth_cache[node_id]
        if node_id in visiting:
            return len(remaining_ids) + 1
        visiting.add(node_id)
        value = 1 + max((depth(parent) for parent in predecessors[node_id]), default=0)
        visiting.remove(node_id)
        depth_cache[node_id] = value
        return value

    maximum_depth = max((depth(node_id) for node_id in remaining_ids), default=0)
    unsatisfied_goals = [fact for fact in goals if fact not in verified]
    unresolved_count = len(unresolved_conditions or [])
    decomposition_gap_count = len(decomposition_gaps or [])
    remaining_count = len(remaining_ids)
    single_chain = bool(
        remaining_count
        and not branch_nodes
        and not join_ids
        and all(count <= 1 for count in incoming.values())
        and all(count <= 1 for count in outgoing.values())
    )

    reasons: list[str] = []
    if not horizon_class and decomposition_gap_count:
        horizon_class = "decomposition_required"
        reasons.append("causal_schema_has_unresolved_producers_or_subgoals")
    elif not horizon_class and not remaining_count:
        horizon_class = "decomposition_required"
        reasons.append("goal_not_verified_and_no_executable_causal_nodes_exist")
    elif not horizon_class and remaining_count == 1 and unresolved_count == 0:
        horizon_class = "atomic_action"
        reasons.append("one_remaining_causal_node")
    elif not horizon_class and (
        branch_nodes
        or join_ids
        or len(unsatisfied_goals) > 1
        or unresolved_count
        or remaining_count > maximum_short_chain_nodes
        or maximum_depth > maximum_short_chain_nodes
    ):
        horizon_class = "long_horizon"
        if branch_nodes:
            reasons.append("remaining_graph_contains_parallel_branches")
        if join_ids:
            reasons.append("remaining_graph_contains_causal_joins")
        if len(unsatisfied_goals) > 1:
            reasons.append("multiple_independent_goal_facts_remain")
        if unresolved_count:
            reasons.append("external_or_policy_conditions_remain_open")
        if remaining_count > maximum_short_chain_nodes or maximum_depth > maximum_short_chain_nodes:
            reasons.append("remaining_chain_exceeds_short_horizon_bound")
    elif not horizon_class:
        horizon_class = "short_horizon"
        reasons.append("bounded_single_causal_chain")

    if horizon_class == "completed":
        reasons = ["terminal_goal_facts_verified"]

    memory_contracts = {
        "atomic_action": {
            "retain_until_completion": ["goal_contract", "active_role_bindings", "current_stage"],
            "discard_after_each_stage": ["trajectory", "motion_frames", "candidate_geometry"],
            "release_on_goal_verification": "all_task_execution_details",
        },
        "short_horizon": {
            "retain_until_completion": ["goal_contract", "active_role_bindings", "verified_fact_ledger"],
            "discard_after_each_stage": ["trajectory", "motion_frames", "completed_stage_plan"],
            "release_on_goal_verification": "all_task_execution_details",
        },
        "long_horizon": {
            "retain_until_completion": ["compact_causal_graph", "active_role_bindings", "verified_fact_ledger", "open_conditions"],
            "discard_after_each_stage": ["trajectory", "motion_frames", "completed_leaf_plan"],
            "release_on_goal_verification": "graph_and_task_execution_details_keep_goal_capsule_only",
        },
        "decomposition_required": {
            "retain_until_completion": ["goal_contract", "unresolved_causal_schema"],
            "discard_after_each_stage": ["unverified_candidate_paths"],
            "release_on_goal_verification": "not_applicable_until_decomposed",
        },
        "completed": {
            "retain_until_completion": ["compact_goal_capsule"],
            "discard_after_each_stage": ["all_execution_mechanics"],
            "release_on_goal_verification": "already_released",
        },
    }
    return {
        "schema_version": "1.0.0",
        "horizon_class": horizon_class,
        "classification_basis": "remaining_verified_fact_pruned_causal_topology",
        "reasons": reasons,
        "metrics": {
            "remaining_node_count": remaining_count,
            "remaining_edge_count": len(normalized_edges),
            "maximum_dependency_depth": maximum_depth,
            "branch_node_count": len(branch_nodes),
            "join_node_count": len(join_ids),
            "unsatisfied_goal_count": len(unsatisfied_goals),
            "unresolved_condition_count": unresolved_count,
            "decomposition_gap_count": decomposition_gap_count,
            "single_chain": single_chain,
            "maximum_short_chain_nodes": maximum_short_chain_nodes,
        },
        "remaining_node_ids": sorted(remaining_ids),
        "unsatisfied_goal_facts": unsatisfied_goals,
        "memory_contract": deepcopy(memory_contracts[horizon_class]),
        "dynamic_transition": {
            "previous": previous_horizon_class,
            "current": horizon_class,
            "changed": bool(
                previous_horizon_class
                and previous_horizon_class != horizon_class
            ),
        },
        "utterance_length_used_for_classification": False,
    }


__all__ = ["classify_execution_horizon", "DEFAULT_MAXIMUM_SHORT_CHAIN_NODES"]
