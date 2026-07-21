from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any


def facts_from_runtime_state(
    runtime_objects: list[dict[str, Any]], runtime_state: dict[str, Any], world_revision: int
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for effector, ref in (runtime_state.get("holding_by_effector") or {}).items():
        if ref:
            facts.append(_fact("held_by", ref, effector, "runtime_verified", world_revision))
    for item in runtime_objects:
        if item.get("active") is False:
            continue
        facts.append(_fact("present_in_world", item.get("entity_id"), item.get("region_id"), "runtime_snapshot", world_revision))
        if item.get("support_ref") and not item.get("attached_to_executor"):
            facts.append(_fact("supported_by", item.get("entity_id"), item.get("support_ref"), "runtime_verified", world_revision))
        if item.get("liquid_state") == "filled":
            facts.append(_fact("contains_liquid", item.get("entity_id"), "water", "runtime_verified", world_revision))
        if item.get("received_by"):
            facts.append(_fact("received_by", item.get("entity_id"), item.get("received_by"), "runtime_verified", world_revision))
    facts.append(_fact("executor_in_region", "executor", runtime_state.get("active_region"), "runtime_verified", world_revision))
    return facts


def compile_situated_event_frame(
    utterance: str,
    language_analysis: dict[str, Any],
    *,
    current_facts: list[dict[str, Any]],
    recent_episodes: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized = re.sub(r"[，。！？、,.!?\s]+", "", utterance)
    roles = deepcopy(language_analysis.get("role_bindings", {}))
    operators = list(language_analysis.get("canonical_frame", {}).get("operators", []))
    goal_relation = language_analysis.get("canonical_frame", {}).get("goal_relation")
    expected = _project_goal_facts(goal_relation, roles)
    temporal_scope = "current"
    if any(marker in normalized for marker in ("刚才", "刚刚", "方才")):
        temporal_scope = "most_recent_verified_past"
    elif any(marker in normalized for marker in ("之前", "先前", "上次", "以前")):
        temporal_scope = "verified_past"
    elif any(marker in normalized for marker in ("之后", "然后", "接着", "完成后")):
        temporal_scope = "ordered_future_stage"
    unresolved = list(dict.fromkeys(language_analysis.get("unresolved_slots", [])))
    reference_queries = []
    if temporal_scope in {"most_recent_verified_past", "verified_past"}:
        mentioned = language_analysis.get("entity_mentions", [])
        for item in mentioned:
            reference_queries.append({
                "entity_concept_id": item.get("concept_id"),
                "surface": item.get("matched_alias"),
                "temporal_scope": temporal_scope,
                "query_over": "verified_episodic_facts",
            })
    reported_state_candidates = []
    human_completion = re.search(
        r"(?:我|人类|用户)(?P<event>[^，,。！？!?]{1,16}?)(?:完了|好了|结束了|完成了)",
        utterance,
    )
    if human_completion:
        reported_state_candidates.append({
            "predicate": "human_participated_event_reported_complete",
            "subject": "human_speaker",
            "event_surface": human_completion.group("event"),
            "status": "human_reported_candidate_requires_context_and_physical_verification",
            "possible_transition": "human_participation_stage_completed",
            "does_not_directly_prove": ["object_location", "object_state", "task_terminal_fact"],
        })
    if re.search(r"(?:喝|饮用)(?:完|光)", normalized):
        theme = roles.get("theme") or roles.get("target") or {}
        reported_state_candidates.append({
            "predicate": "container_contents_consumed",
            "subject": theme.get("entity_ref") or theme.get("concept_id") or theme.get("matched_alias"),
            "reported_by": "human_speaker",
            "status": "human_reported_candidate_requires_physical_verification",
            "possible_derived_fact": "container_empty",
        })
    possession_report = re.search(
        r"(?:还|仍然|仍|依然)?(?:在|由)(?P<holder>我|你|机器人)(?:的)?手(?:里|上|中)(?:拿着|持有)?",
        normalized,
    )
    if possession_report:
        theme = roles.get("theme") or roles.get("target") or {}
        holder_surface = possession_report.group("holder")
        reported_state_candidates.append({
            "predicate": "received_by" if holder_surface == "我" else "held_by",
            "subject": (
                theme.get("entity_ref")
                or theme.get("concept_id")
                or theme.get("matched_alias")
            ),
            "subject_role": "theme",
            "object_role": "human_speaker" if holder_surface == "我" else "executor",
            "reported_by": "human_speaker",
            "status": "human_reported_candidate_requires_physical_verification",
            "does_not_commit_physical_fact": True,
        })
    frame_seed = f"{utterance}|{len(recent_episodes)}|{len(current_facts)}"
    return {
        "schema_version": "1.0.0",
        "frame_id": "event_frame_" + hashlib.sha1(frame_seed.encode("utf-8")).hexdigest()[:12],
        "utterance": utterance,
        "speech_act": language_analysis.get("speech_act"),
        "operators": operators,
        "semantic_roles": roles,
        "spatial_constraints": _spatial_constraints(roles),
        "temporal_scope": temporal_scope,
        "reference_queries": reference_queries,
        "reported_state_candidates": reported_state_candidates,
        "current_fact_snapshot": deepcopy(current_facts),
        "recent_episode_refs": [item.get("episode_id") for item in recent_episodes[-8:]],
        "expected_goal_facts": expected,
        "known_slots": sorted(roles),
        "unresolved_slots": unresolved,
        "interpretation_status": "partial" if unresolved else "composed_candidate",
        "evidence_boundary": {
            "language_creates_goal_candidates": True,
            "language_does_not_commit_physical_facts": True,
            "execution_requires_current_grounding_and_verification": True,
        },
    }


def create_hierarchical_intent_graph(
    graph_id: str,
    *,
    root_goal_facts: list[str],
    stages: list[dict[str, Any]],
) -> dict[str, Any]:
    root_id = f"{graph_id}:root"
    nodes: dict[str, dict[str, Any]] = {
        root_id: _intent_node(root_id, None, "root_goal", root_goal_facts, [], [], "all_children_and_goal_facts")
    }
    previous_id = None
    for index, stage in enumerate(stages):
        node_id = f"{graph_id}:{stage['stage_id']}"
        requires = _as_list(stage.get("requires"))
        produces = _as_list(stage.get("produces"))
        node = _intent_node(node_id, root_id, stage["stage_id"], produces, requires, produces, "verified_goal_facts")
        node["sequence_index"] = index
        node["predecessor_id"] = previous_id
        nodes[node_id] = node
        nodes[root_id]["children"].append(node_id)
        previous_id = node_id
    graph = {
        "schema_version": "1.0.0",
        "graph_id": graph_id,
        "root_node_id": root_id,
        "nodes": nodes,
        "verified_facts": [],
        "active_focus_node_id": nodes[root_id]["children"][0] if nodes[root_id]["children"] else root_id,
        "lifecycle": "active",
        "trajectory_storage_policy": "discard_paths_keep_goals_facts_and_verified_episodes",
    }
    validate_intent_graph(graph)
    return graph


def attach_opportunistic_subgoal(
    graph: dict[str, Any],
    *,
    parent_node_id: str,
    subgoal_id: str,
    goal_facts: list[str],
    requires: list[str],
    compatibility_constraints: list[str],
) -> dict[str, Any]:
    if parent_node_id not in graph["nodes"]:
        raise ValueError("opportunistic_subgoal_parent_missing")
    node_id = f"{graph['graph_id']}:{subgoal_id}"
    node = _intent_node(node_id, parent_node_id, subgoal_id, goal_facts, requires, goal_facts, "verified_goal_facts")
    node.update({
        "origin": "interaction_added_opportunistic_subgoal",
        "compatibility_constraints": list(compatibility_constraints),
        "merge_requires_runtime_arbitration": True,
    })
    graph["nodes"][node_id] = node
    graph["nodes"][parent_node_id]["children"].append(node_id)
    root_goals = graph["nodes"][graph["root_node_id"]]["goal_facts"]
    for fact in goal_facts:
        if fact not in root_goals:
            root_goals.append(fact)
    validate_intent_graph(graph)
    return deepcopy(node)


def decompose_intent_node(
    graph: dict[str, Any], *, parent_node_id: str, stages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if parent_node_id not in graph["nodes"]:
        raise ValueError("decomposition_parent_missing")
    created = []
    previous_id = None
    for index, stage in enumerate(stages):
        node_id = f"{parent_node_id}:{stage['stage_id']}"
        node = _intent_node(
            node_id,
            parent_node_id,
            stage["stage_id"],
            _as_list(stage.get("produces")),
            _as_list(stage.get("requires")),
            _as_list(stage.get("produces")),
            "verified_goal_facts",
        )
        node["sequence_index"] = index
        node["predecessor_id"] = previous_id
        node["scope_relation"] = "local_stage_whose_parent_is_current_global_goal"
        graph["nodes"][node_id] = node
        graph["nodes"][parent_node_id]["children"].append(node_id)
        created.append(deepcopy(node))
        previous_id = node_id
    validate_intent_graph(graph)
    return created


def record_verified_fact(graph: dict[str, Any], fact: str) -> dict[str, Any]:
    if fact not in graph["verified_facts"]:
        graph["verified_facts"].append(fact)
    verified = set(graph["verified_facts"])
    for node in graph["nodes"].values():
        if not node["children"] and set(node["goal_facts"]).issubset(verified):
            node["lifecycle"] = "completed"
    changed = True
    while changed:
        changed = False
        for node in graph["nodes"].values():
            if node["lifecycle"] == "completed" or not node["children"]:
                continue
            children_complete = all(graph["nodes"][child]["lifecycle"] == "completed" for child in node["children"])
            if children_complete and set(node["goal_facts"]).issubset(verified):
                node["lifecycle"] = "completed"
                changed = True
    root = graph["nodes"][graph["root_node_id"]]
    children_complete = all(graph["nodes"][child]["lifecycle"] == "completed" for child in root["children"])
    if children_complete and set(root["goal_facts"]).issubset(verified):
        root["lifecycle"] = "completed"
        graph["lifecycle"] = "completed"
        graph["active_focus_node_id"] = None
    else:
        ready = ready_leaf_nodes(graph)
        graph["active_focus_node_id"] = ready[0]["node_id"] if ready else graph.get("active_focus_node_id")
    return deepcopy(graph)


def ready_leaf_nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    verified = set(graph.get("verified_facts", []))
    ready = []
    for node in graph["nodes"].values():
        if node["children"] or node["lifecycle"] == "completed":
            continue
        predecessor = graph["nodes"].get(node.get("predecessor_id"))
        predecessor_ready = predecessor is None or predecessor.get("lifecycle") == "completed"
        if predecessor_ready and set(node["requires"]).issubset(verified):
            ready.append(node)
    return sorted(ready, key=lambda item: (item.get("sequence_index", 10_000), item["node_id"]))


def focus_scope(graph: dict[str, Any], node_id: str) -> dict[str, Any]:
    node = graph["nodes"][node_id]
    ancestors = []
    parent_id = node.get("parent_id")
    while parent_id:
        ancestors.append(parent_id)
        parent_id = graph["nodes"][parent_id].get("parent_id")
    return {
        "node_id": node_id,
        "is_local_stage_of": ancestors,
        "is_current_global_for_descendants": bool(node["children"]),
        "children": list(node["children"]),
    }


def validate_intent_graph(graph: dict[str, Any]) -> None:
    nodes = graph.get("nodes", {})
    if graph.get("root_node_id") not in nodes:
        raise ValueError("intent_graph_root_missing")
    for node_id, node in nodes.items():
        if node.get("parent_id") and node["parent_id"] not in nodes:
            raise ValueError(f"intent_graph_parent_missing:{node_id}")
        if any(child not in nodes for child in node.get("children", [])):
            raise ValueError(f"intent_graph_child_missing:{node_id}")


def _fact(predicate: str, subject: Any, obj: Any, evidence: str, world_revision: int) -> dict[str, Any]:
    return {"predicate": predicate, "subject": subject, "object": obj, "evidence": evidence, "world_revision": world_revision}


def _project_goal_facts(goal_relation: str | None, roles: dict[str, Any]) -> list[dict[str, Any]]:
    theme = roles.get("theme") or roles.get("target") or {}
    destination = roles.get("destination") or roles.get("target_region") or {}
    recipient = roles.get("recipient") or {}
    theme_ref = theme.get("entity_ref") or theme.get("concept_id") or theme.get("matched_alias")
    destination_ref = destination.get("entity_ref") or destination.get("concept_id") or destination.get("matched_alias")
    recipient_ref = recipient.get("entity_ref") or recipient.get("reference") or recipient.get("matched_alias")
    if goal_relation == "object_supported_at_destination":
        return [{"predicate": "supported_by", "subject": theme_ref, "object": destination_ref, "status": "expected"}]
    if goal_relation == "object_in_gripper":
        return [{"predicate": "held_by_executor", "subject": theme_ref, "object": "executor", "status": "expected"}]
    if goal_relation == "object_received_by_recipient":
        return [{"predicate": "received_by", "subject": theme_ref, "object": recipient_ref, "status": "expected"}]
    if goal_relation == "object_at_target_region":
        return [{"predicate": "inside_region", "subject": theme_ref, "object": destination_ref, "status": "expected"}]
    return []


def _spatial_constraints(roles: dict[str, Any]) -> list[dict[str, Any]]:
    destination = roles.get("destination") or {}
    if not destination:
        return []
    return [{
        "role": "destination",
        "entity_ref": destination.get("entity_ref"),
        "concept_id": destination.get("concept_id"),
        "surface": destination.get("matched_alias") or destination.get("label"),
        "grounding_required": True,
    }]


def _intent_node(
    node_id: str,
    parent_id: str | None,
    label: str,
    goal_facts: list[str],
    requires: list[str],
    produces: list[str],
    completion_rule: str,
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "parent_id": parent_id,
        "label": label,
        "goal_facts": list(goal_facts),
        "requires": list(requires),
        "produces": list(produces),
        "verification": [f"verify:{fact}" for fact in goal_facts],
        "completion_rule": completion_rule,
        "children": [],
        "lifecycle": "pending",
    }


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [str(value)]
