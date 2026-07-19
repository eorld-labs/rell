from __future__ import annotations

from copy import deepcopy
from typing import Any


def initialize_causal_graph_runtime(graph: dict[str, Any], *, world_revision: int) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "graph_goal_fact": graph.get("goal_fact"),
        "world_revision_at_start": world_revision,
        "fact_ledger": {},
        "node_states": {
            node["node_id"]: {
                "status": "pending",
                "attempt_count": 0,
                "last_reason": None,
            }
            for node in graph.get("nodes", [])
        },
        "active_node_id": None,
        "pending_condition": None,
        "completed_node_order": [],
        "scheduler_revision": 0,
    }


def record_graph_facts(
    runtime: dict[str, Any],
    facts: list[str],
    *,
    source: str,
    node_id: str | None = None,
    world_revision: int | None = None,
    physical_verification: bool = False,
) -> None:
    for fact in facts:
        runtime.setdefault("fact_ledger", {})[fact] = {
            "state": "established",
            "source": source,
            "node_id": node_id,
            "world_revision": world_revision,
            "physical_verification": physical_verification,
        }
    runtime["scheduler_revision"] = int(runtime.get("scheduler_revision", 0)) + 1


def established_graph_facts(runtime: dict[str, Any]) -> set[str]:
    return {
        fact
        for fact, evidence in runtime.get("fact_ledger", {}).items()
        if evidence.get("state") == "established"
    }


def _role_entities(
    graph: dict[str, Any], runtime_objects: list[dict[str, Any]], role_name: str
) -> list[dict[str, Any]]:
    refs = (graph.get("roles") or {}).get(role_name)
    if not isinstance(refs, list):
        refs = [refs] if refs else []
    index = {
        item.get("entity_id"): item
        for item in runtime_objects
        if item.get("entity_id") and item.get("active") is not False
    }
    return [index[ref] for ref in refs if ref in index]


def _nested_value(entity: dict[str, Any], path: str) -> Any:
    value: Any = entity
    for part in str(path or "").split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def evaluate_world_fact_rules(
    graph: dict[str, Any], runtime_objects: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for fact, rule in (graph.get("world_fact_rules") or {}).items():
        entities = _role_entities(graph, runtime_objects, str(rule.get("role") or ""))
        operator = rule.get("operator")
        expected = rule.get("value")
        observed: Any = None
        established = False
        if operator == "role_exists":
            observed = len(entities)
            established = observed >= int(rule.get("minimum_count", 1))
        elif operator == "all_role_members_exist":
            refs = (graph.get("roles") or {}).get(rule.get("role")) or []
            refs = refs if isinstance(refs, list) else [refs]
            observed = len(entities)
            established = bool(refs) and observed == len(refs)
        elif operator == "field_equals":
            observed = _nested_value(entities[0], rule.get("field")) if entities else None
            established = observed == expected
        elif operator == "field_truthy":
            observed = _nested_value(entities[0], rule.get("field")) if entities else None
            established = bool(observed)
        elif operator == "field_gte":
            observed = _nested_value(entities[0], rule.get("field")) if entities else None
            established = observed is not None and float(observed) >= float(expected)
        elif operator == "field_lte":
            observed = _nested_value(entities[0], rule.get("field")) if entities else None
            established = observed is not None and float(observed) <= float(expected)
        elif operator == "all_members_field_equals":
            observed = [_nested_value(item, rule.get("field")) for item in entities]
            established = bool(entities) and all(value == expected for value in observed)
        elif operator == "all_members_field_equals_role_ref":
            expected_entities = _role_entities(
                graph, runtime_objects, str(rule.get("value_role") or "")
            )
            expected = expected_entities[0].get("entity_id") if len(expected_entities) == 1 else None
            observed = [_nested_value(item, rule.get("field")) for item in entities]
            established = bool(entities) and expected is not None and all(value == expected for value in observed)
        elif operator == "sum_role_footprints_lte_role_field":
            member_entities = [
                entity
                for role_name in rule.get("member_roles", [])
                for entity in _role_entities(graph, runtime_objects, str(role_name))
            ]
            capacity_entities = _role_entities(
                graph, runtime_objects, str(rule.get("capacity_role") or "")
            )
            required = sum(
                float((entity.get("size") or [0.0, 0.0])[0])
                * float((entity.get("size") or [0.0, 0.0])[1])
                for entity in member_entities
            )
            capacity = (
                _nested_value(capacity_entities[0], rule.get("capacity_field"))
                if len(capacity_entities) == 1 else None
            )
            observed = {"required_footprint_m2": round(required, 6), "capacity_m2": capacity}
            expected = "required_footprint_m2 <= capacity_m2"
            established = bool(member_entities) and capacity is not None and required <= float(capacity)
        elif operator == "computed_boolean":
            observed = bool(rule.get("current_value"))
            established = observed
        results[fact] = {
            "state": "established" if established else "not_established",
            "source": "current_world_fact_rule",
            "operator": operator,
            "role": rule.get("role"),
            "observed": deepcopy(observed),
            "expected": deepcopy(expected),
        }
    return results


def refresh_world_facts(
    graph: dict[str, Any],
    runtime: dict[str, Any],
    runtime_objects: list[dict[str, Any]],
    *,
    world_revision: int,
) -> dict[str, dict[str, Any]]:
    evaluated = evaluate_world_fact_rules(graph, runtime_objects)
    for fact, evidence in evaluated.items():
        existing = runtime.setdefault("fact_ledger", {}).get(fact)
        if evidence["state"] == "established":
            runtime["fact_ledger"][fact] = {
                **evidence,
                "world_revision": world_revision,
                "physical_verification": True,
            }
        elif existing and existing.get("source") == "current_world_fact_rule":
            runtime["fact_ledger"][fact] = {
                **evidence,
                "world_revision": world_revision,
                "physical_verification": True,
            }
    return evaluated


def _missing_requirements(node: dict[str, Any], established: set[str]) -> tuple[list[str], list[list[str]]]:
    missing_all = [fact for fact in node.get("requires", []) if fact not in established]
    missing_any = [
        list(group)
        for group in node.get("requires_any", [])
        if not any(fact in established for fact in group)
    ]
    return missing_all, missing_any


def evaluate_causal_graph(
    graph: dict[str, Any],
    runtime: dict[str, Any],
    runtime_objects: list[dict[str, Any]],
    *,
    world_revision: int,
) -> dict[str, Any]:
    world_facts = refresh_world_facts(
        graph, runtime, runtime_objects, world_revision=world_revision
    )
    established = established_graph_facts(runtime)
    producer_by_fact = {
        fact: node["node_id"]
        for node in graph.get("nodes", [])
        for fact in node.get("produces", [])
    }
    resolutions = graph.get("condition_resolutions") or {}
    ready, blocked, waiting, completed = [], [], [], []
    for node in graph.get("nodes", []):
        node_id = node["node_id"]
        state = runtime.setdefault("node_states", {}).setdefault(
            node_id, {"status": "pending", "attempt_count": 0, "last_reason": None}
        )
        produces = set(node.get("produces", []))
        if produces and produces.issubset(established):
            state["status"] = "completed"
            completed.append(node_id)
            continue
        if runtime.get("active_node_id") == node_id:
            state["status"] = "active"
            continue
        missing_all, missing_any = _missing_requirements(node, established)
        missing = list(missing_all)
        for group in missing_any:
            missing.extend(group)
        resolvable = [fact for fact in missing if fact in resolutions]
        supported_alternative_facts = {
            fact
            for group in missing_any
            if any(
                candidate in producer_by_fact or candidate in resolutions
                for candidate in group
            )
            for fact in group
        }
        impossible = [
            fact for fact in missing
            if fact not in producer_by_fact
            and (world_facts.get(fact) or {}).get("state") != "established"
            and fact not in resolutions
            and fact not in supported_alternative_facts
        ]
        if resolvable or impossible:
            state["status"] = "blocked"
            state["last_reason"] = "missing_causal_precondition"
            blocked.append({
                "node_id": node_id,
                "missing_facts": list(dict.fromkeys(missing)),
                "resolvable_conditions": list(dict.fromkeys(resolvable)),
                "impossible_facts": list(dict.fromkeys(impossible)),
            })
        elif missing:
            state["status"] = "waiting"
            waiting.append({
                "node_id": node_id,
                "waiting_for": list(dict.fromkeys(missing)),
                "producer_nodes": sorted({producer_by_fact[fact] for fact in missing if fact in producer_by_fact}),
            })
        else:
            state["status"] = "ready"
            state["last_reason"] = None
            ready.append(node)
    ready.sort(key=lambda node: (int(node.get("priority", 100)), node["node_id"]))
    return {
        "goal_fact": graph.get("goal_fact"),
        "goal_established": graph.get("goal_fact") in established,
        "established_facts": sorted(established),
        "ready_nodes": [deepcopy(node) for node in ready],
        "blocked_nodes": blocked,
        "waiting_nodes": waiting,
        "completed_nodes": completed,
        "active_node_id": runtime.get("active_node_id"),
        "scheduler_revision": runtime.get("scheduler_revision", 0),
    }


def select_condition_clarification(
    graph: dict[str, Any], evaluation: dict[str, Any]
) -> dict[str, Any] | None:
    resolutions = graph.get("condition_resolutions") or {}
    candidates = []
    for blocked in evaluation.get("blocked_nodes", []):
        for fact in blocked.get("resolvable_conditions", []):
            resolution = resolutions.get(fact)
            if resolution:
                candidates.append({
                    "condition": fact,
                    "node_id": blocked["node_id"],
                    **deepcopy(resolution),
                })
    if not candidates:
        return None
    candidates.sort(key=lambda item: (int(item.get("priority", 100)), item["condition"]))
    return candidates[0]


def apply_condition_answer(
    graph: dict[str, Any], runtime: dict[str, Any], answer: str, *, world_revision: int
) -> dict[str, Any]:
    pending = runtime.get("pending_condition") or {}
    condition = pending.get("condition")
    resolution = (graph.get("condition_resolutions") or {}).get(condition) or {}
    normalized = "".join(str(answer or "").split())
    for option in resolution.get("options", []):
        if not any("".join(str(alias).split()) in normalized for alias in option.get("aliases", [])):
            continue
        if option.get("requires_world_change"):
            return {
                "status": "condition_world_change_required",
                "condition": condition,
                "option_id": option.get("option_id"),
                "prompt": option.get("prompt") or "请先改变当前物理条件，我会在世界版本更新后重新观察。",
            }
        record_graph_facts(
            runtime,
            list(option.get("establishes", [])),
            source="human_resolved_goal_constraint",
            world_revision=world_revision,
            physical_verification=False,
        )
        runtime["pending_condition"] = None
        return {
            "status": "condition_resolved",
            "condition": condition,
            "option_id": option.get("option_id"),
            "established_facts": list(option.get("establishes", [])),
            "prompt": option.get("acknowledgement"),
        }
    return {
        "status": "condition_answer_not_resolved",
        "condition": condition,
        "prompt": resolution.get("question") or "请补充解决这个前提所需的信息。",
    }


__all__ = [
    "apply_condition_answer",
    "established_graph_facts",
    "evaluate_causal_graph",
    "evaluate_world_fact_rules",
    "initialize_causal_graph_runtime",
    "record_graph_facts",
    "refresh_world_facts",
    "select_condition_clarification",
]
