from __future__ import annotations

from copy import deepcopy

from embodied_scene import (
    SESSIONS,
    _compose_session_language,
    _session_object_language_concepts,
    begin_motion_command,
    get_session,
    set_stool,
    start_session,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_compositional_constraints_not_atomic_instance_alias() -> dict:
    session = start_session("home_humanoid", "hospitality_guest")
    live = SESSIONS[session["session_id"]]
    concepts = _session_object_language_concepts(live)
    container_concept = next(item for item in concepts if item["concept_id"] == "concept_fillable_container")
    require("白色马克杯" not in container_concept.get("aliases", []), f"runtime instance name polluted the reusable concept lexicon: {container_concept}")

    analysis = _compose_session_language(live, "用白色马克杯给我接一杯水")
    frame = analysis["semantic_constraint_frame"]
    theme = frame["roles"]["theme"]
    constraints = {(item["concept_id"], item["value"]) for item in theme["constraints"]}
    require(theme.get("concept_id") == "concept_fillable_container", f"container head concept was lost: {theme}")
    require(("concept_color_family", "white") in constraints and ("concept_container_form", "mug") in constraints, f"modifier concepts were collapsed into an atomic name: {frame}")
    require(theme.get("explicit_entity_ref") is None and frame["evidence_boundary"]["language_does_not_bind_physical_instances"], f"language claimed a physical instance before grounding: {frame}")
    grounding = analysis["grounded_intent_frame"]["roles"]["theme"]
    require(grounding.get("status") == "resolved" and grounding.get("binding", {}).get("entity_ref") == "mug_white", f"composed constraints did not ground in current evidence: {grounding}")
    return {"head_concept": theme["concept_id"], "constraints": sorted(constraints), "entity_ref": "mug_white"}


def verify_instance_rename_does_not_change_concept_grounding() -> dict:
    session = start_session("home_humanoid", "hospitality_guest")
    live = SESSIONS[session["session_id"]]
    mug = next(item for item in live["runtime_objects"] if item["entity_id"] == "mug_white")
    mug["label"] = "未登记饮具甲"
    result = begin_motion_command(session["session_id"], "用乳白色马克杯给我接一杯水")
    intent = result.get("long_horizon_intent") or {}
    evidence = (live.get("long_horizon_intents", {}).get(live.get("active_intent_id")) or {}).get("role_binding_evidence", {}).get("theme", {})
    require(result.get("status") == "motion_started" and intent.get("role_bindings", {}).get("theme") == "mug_white", f"renaming the instance changed concept grounding: {result}")
    require(evidence.get("basis") == "concept_constraints_grounded_in_current_observation", f"renamed instance was not selected from concept predicates: {evidence}")
    return {"renamed_surface": mug["label"], "entity_ref": "mug_white", "basis": evidence["basis"]}


def verify_attribute_subsumption_and_modifier_composition() -> dict:
    session = start_session("home_humanoid", "hospitality_guest")
    live = SESSIONS[session["session_id"]]
    analysis = _compose_session_language(
        live,
        "我喝完了，把杯子放到桌子上有蓝色玻璃高脚杯的桌子上去",
    )
    modifier = analysis["semantic_constraint_frame"]["roles"][
        "destination_relation_object"
    ]
    constraints = {
        item["observation_field"]: item
        for item in modifier.get("constraints", [])
    }
    grounding = analysis["grounded_intent_frame"]["roles"][
        "destination_relation_object"
    ]
    require(
        set(constraints) == {"color", "material", "container_form"},
        f"independently ordered noun modifiers were not composed: {modifier}",
    )
    require(
        set(constraints["color"].get("accepted_observed_values", []))
        == {"blue", "light_blue"},
        f"a requested parent color did not include its declared subtype: {constraints['color']}",
    )
    require(
        grounding.get("status") == "resolved"
        and grounding.get("binding", {}).get("entity_ref") == "glass_tall",
        f"composed parent-color/material/form constraints did not ground: {grounding}",
    )

    narrow_session = start_session("home_humanoid", "hospitality_guest")
    narrow_live = SESSIONS[narrow_session["session_id"]]
    narrow_glass = next(
        item for item in narrow_live["runtime_objects"]
        if item["entity_id"] == "glass_tall"
    )
    narrow_glass["perceptual_attributes"] = {
        "color": "blue",
        "material": "glass",
    }
    narrow = _compose_session_language(
        narrow_live,
        "把杯子放在有浅蓝色玻璃高脚杯的桌子上",
    )
    narrow_grounding = narrow["grounded_intent_frame"]["roles"][
        "destination_relation_object"
    ]
    require(
        narrow_grounding.get("status") == "missing",
        f"a child color request incorrectly accepted its broader parent observation: {narrow_grounding}",
    )
    return {
        "requested_color": "blue",
        "accepted_observed_colors": ["blue", "light_blue"],
        "material": "glass",
        "form": "stemmed_glass",
        "entity_ref": "glass_tall",
        "subsumption_direction_verified": True,
    }


def verify_query_then_task_matches_direct_task() -> dict:
    direct_session = start_session("home_humanoid", "hospitality_guest")
    direct = begin_motion_command(direct_session["session_id"], "用白色马克杯给我接一杯水")
    direct_theme = (direct.get("long_horizon_intent") or {}).get("role_bindings", {}).get("theme")

    observed_session = start_session("home_humanoid", "hospitality_guest")
    query = begin_motion_command(observed_session["session_id"], "桌子上有什么")
    query_result = query.get("immediate_result") or query
    before_task = get_session(observed_session["session_id"])
    observed = begin_motion_command(observed_session["session_id"], "用白色马克杯给我接一杯水")
    observed_theme = (observed.get("long_horizon_intent") or {}).get("role_bindings", {}).get("theme")
    require(query_result.get("status") == "support_inventory_state_answered", f"inventory query did not use current support facts: {query}")
    require(query_result.get("state_evidence", {}).get("epistemic_evidence_refreshed_without_task_control_side_effect") is True, f"read-only query discarded its observation evidence: {query_result}")
    require(before_task.get("active_intent_id") is None and before_task.get("role_clarification_dialogue") is None, f"query changed task control state: {before_task}")
    require(direct_theme == observed_theme == "mug_white", f"prior observation and direct current-world grounding diverged: direct={direct_theme}, observed={observed_theme}")
    return {"direct_theme": direct_theme, "query_then_task_theme": observed_theme}


def verify_equal_concept_evidence_remains_ambiguous() -> dict:
    session = start_session("home_humanoid", "hospitality_guest")
    live = SESSIONS[session["session_id"]]
    first = next(item for item in live["runtime_objects"] if item["entity_id"] == "mug_white")
    second = deepcopy(first)
    second.update({"entity_id": "mug_white_second", "label": "未登记饮具乙", "position": [2.55, -0.9]})
    live["runtime_objects"].append(second)
    result = begin_motion_command(session["session_id"], "用乳白色马克杯给我接一杯水")
    require(result.get("status") == "role_clarification_required", f"equally supported current instances were selected arbitrarily: {result}")
    require({"mug_white", "mug_white_second"}.issubset({item.get("entity_ref") for item in result.get("candidate_options", [])}), f"clarification omitted equally grounded instances: {result}")
    return {"status": result["status"], "equally_grounded": ["mug_white", "mug_white_second"]}


def verify_world_revision_invalidates_epistemic_evidence() -> dict:
    session = start_session("home_humanoid", "hospitality_guest")
    session_id = session["session_id"]
    begin_motion_command(session_id, "桌子上有什么")
    before = get_session(session_id)
    old_id = before["current_observation_evidence"]["evidence_set_id"]
    old_revision = before["world_revision"]
    changed = set_stool(session_id, "ahead")
    require(changed.get("world_revision") == old_revision + 1, f"world perturbation did not advance the snapshot revision: {changed}")
    stale = get_session(session_id)
    require(stale.get("current_observation_evidence") is None, f"old evidence remained current after world revision change: {stale.get('current_observation_evidence')}")
    require(any(item.get("evidence_set_id") == old_id and item.get("current_use_status") == "stale" for item in stale.get("observation_evidence_ledger", [])), f"old evidence was not explicitly invalidated: {stale.get('observation_evidence_ledger')}")
    begin_motion_command(session_id, "桌子上有什么")
    refreshed = get_session(session_id)["current_observation_evidence"]
    require(refreshed.get("world_revision") == old_revision + 1 and refreshed.get("evidence_set_id") != old_id, f"new input reused stale epistemic evidence: {refreshed}")
    return {"old_revision": old_revision, "new_revision": refreshed["world_revision"], "old_evidence_invalidated": True}


def main() -> None:
    report = {
        "concept_composition": verify_compositional_constraints_not_atomic_instance_alias(),
        "attribute_subsumption": verify_attribute_subsumption_and_modifier_composition(),
        "rename_invariance": verify_instance_rename_does_not_change_concept_grounding(),
        "query_task_consistency": verify_query_then_task_matches_direct_task(),
        "equal_evidence_ambiguity": verify_equal_concept_evidence_remains_ambiguous(),
        "world_revision_invalidation": verify_world_revision_invalidates_epistemic_evidence(),
    }
    print("Semantic grounding architecture validation passed.")
    print(report)


if __name__ == "__main__":
    main()
