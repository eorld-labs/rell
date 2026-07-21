from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from .semantic_grounding import (
    build_grounded_intent_frame,
    build_observation_evidence_set,
    build_semantic_constraint_frame,
    ground_semantic_role,
)


@dataclass(frozen=True)
class SlotSpec:
    slot_id: str
    value_type: str
    role_names: tuple[str, ...]
    candidate_provider: str
    required: bool = True
    auto_bind_unique: bool = True
    priority: int = 50
    required_when: str | None = None


@dataclass(frozen=True)
class ProcessTemplate:
    template_id: str
    operators: tuple[str, ...]
    goal_fact: str
    slots: tuple[SlotSpec, ...]
    causal_preconditions: tuple[dict[str, Any], ...]


PROCESS_TEMPLATES: tuple[ProcessTemplate, ...] = (
    ProcessTemplate(
        "grasp_object",
        ("grasp_object",),
        "object_in_gripper",
        (SlotSpec("theme", "graspable_object", ("theme", "target"), "graspable_objects", priority=10),),
        (
            {"fact": "object_grounded", "producer": "observe_entity"},
            {"fact": "object_within_reach", "producer": "navigate_until_target_within_reach"},
            {"fact": "gripper_available", "producer": "release_or_place_held_object"},
        ),
    ),
    ProcessTemplate(
        "place_object",
        ("place_object",),
        "object_supported_at_destination",
        (
            SlotSpec("theme", "graspable_object", ("theme", "target"), "graspable_objects", priority=10),
            SlotSpec("destination", "support_surface", ("destination",), "support_surfaces", priority=20),
        ),
        (
            {"fact": "object_in_gripper", "producer": "grasp_object"},
            {"fact": "destination_grounded", "producer": "observe_or_clarify_destination"},
            {"fact": "placement_pose_feasible", "producer": "compute_current_body_placement_candidate"},
        ),
    ),
    ProcessTemplate(
        "handover_object",
        ("handover_object",),
        "object_received_by_recipient",
        (
            SlotSpec("theme", "graspable_object", ("theme", "target"), "graspable_objects", priority=10),
            SlotSpec("recipient", "human_recipient", ("recipient",), "human_recipients", priority=20),
        ),
        (
            {"fact": "object_in_gripper", "producer": "grasp_object"},
            {"fact": "recipient_grounded", "producer": "observe_or_clarify_recipient"},
            {"fact": "recipient_ready", "producer": "verify_recipient_readiness"},
            {"fact": "handover_pose_feasible", "producer": "compute_safe_handover_pose"},
        ),
    ),
    ProcessTemplate(
        "transport_object",
        ("transport_object",),
        "object_at_target_region",
        (
            SlotSpec("theme", "graspable_object", ("theme", "target"), "graspable_objects", priority=10),
            SlotSpec("target_region", "semantic_region", ("target_region", "destination"), "semantic_regions", priority=20),
            SlotSpec("transport_mode", "transport_mode", ("transport_mode",), "transport_modes", priority=30),
            SlotSpec("destination", "support_surface", ("destination",), "support_surfaces", required=False, priority=40, required_when="transport_mode=place_at_region"),
        ),
        (
            {"fact": "object_in_gripper", "producer": "grasp_object"},
            {"fact": "route_feasible", "producer": "plan_or_detour_route"},
        ),
    ),
)


_TEMPLATE_BY_ID = {item.template_id: item for item in PROCESS_TEMPLATES}
_TEMPLATE_BY_OPERATOR = {
    operator: item for item in PROCESS_TEMPLATES for operator in item.operators
}


def build_process_template_catalog() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "templates": [
            {
                "template_id": item.template_id,
                "operators": list(item.operators),
                "goal_fact": item.goal_fact,
                "slots": [asdict(slot) for slot in item.slots],
                "causal_preconditions": deepcopy(item.causal_preconditions),
            }
            for item in PROCESS_TEMPLATES
        ],
        "resolution_contract": {
            "templates_declare_slots_not_question_strings": True,
            "questions_are_derived_from_unresolved_slots_and_snapshot_candidates": True,
            "language_never_commits_physical_facts": True,
            "execution_requires_current_world_revalidation": True,
        },
    }


def resolve_process_request(
    utterance: str,
    language_analysis: dict[str, Any],
    *,
    runtime_objects: list[dict[str, Any]],
    runtime_state: dict[str, Any],
    semantic_regions: list[dict[str, Any]],
    executor_profile: dict[str, Any],
    world_revision: int,
    binding_overrides: dict[str, str] | None = None,
    evidence_bindings: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if not language_analysis.get("semantic_constraint_frame"):
        language_analysis = deepcopy(language_analysis)
        language_analysis["semantic_constraint_frame"] = build_semantic_constraint_frame(utterance, language_analysis)
    if not language_analysis.get("observation_evidence"):
        language_analysis["observation_evidence"] = build_observation_evidence_set(
            runtime_objects,
            _object_concepts_from_language_analysis(language_analysis),
            world_revision=world_revision,
            source="process_resolution_current_world_grounding",
        )
    if not language_analysis.get("grounded_intent_frame"):
        language_analysis["grounded_intent_frame"] = build_grounded_intent_frame(
            language_analysis["semantic_constraint_frame"],
            language_analysis["observation_evidence"],
        )
    candidates = _template_candidates(utterance, language_analysis)
    if not candidates:
        return None
    selected = candidates[0]
    template = _TEMPLATE_BY_ID[selected["template_id"]]
    bindings: dict[str, dict[str, Any]] = {}
    slot_results = []
    binding_overrides = binding_overrides or {}
    evidence_bindings = evidence_bindings or []
    for slot in sorted(template.slots, key=lambda item: item.priority):
        values = _slot_candidates(
            slot,
            utterance,
            language_analysis,
            runtime_objects,
            runtime_state,
            semantic_regions,
            bindings,
            evidence_bindings,
            world_revision,
        )
        override = binding_overrides.get(slot.slot_id)
        if override:
            values = [item for item in values if item.get("value_ref") == override]
            if not values:
                entity = next((item for item in runtime_objects if item.get("entity_id") == override and item.get("active") is not False), None)
                provider_compatible = bool(
                    entity
                    and (
                        slot.candidate_provider == "graspable_objects" and entity.get("fixed") is not True
                        or slot.candidate_provider == "human_recipients" and entity.get("kind") == "human_recipient"
                        or slot.candidate_provider == "support_surfaces" and entity.get("kind") == "operation_surface"
                    )
                )
                if provider_compatible:
                    values = [_entity_value(
                        entity,
                        explicit=True,
                        evidence_bindings=evidence_bindings,
                        world_revision=world_revision,
                        semantic_binding={
                            "binding_basis": "human_confirmed_observed_constraint_substitution",
                            "evidence_strength": 650,
                            "world_revision": world_revision,
                            "matched_constraints": [],
                        },
                    )]
        usable = _non_dominated_evidence(values)
        semantic_role = next(
            (
                (language_analysis.get("role_bindings") or {}).get(name)
                for name in slot.role_names
                if (language_analysis.get("role_bindings") or {}).get(name)
            ),
            {},
        ) or {}
        if (
            len(usable) > 1
            and semantic_role.get("selection_quantifier") == "existential"
            and semantic_role.get("quantity") == 1
        ):
            object_index = {
                item.get("entity_id"): item for item in runtime_objects
            }
            executor_position = runtime_state.get("executor_position") or [0, 0]

            def selection_cost(candidate: dict[str, Any]) -> tuple[float, str]:
                entity = object_index.get(candidate.get("value_ref")) or {}
                position = entity.get("position") or [float("inf"), float("inf")]
                distance_squared = sum(
                    (float(left) - float(right)) ** 2
                    for left, right in zip(position[:2], executor_position[:2])
                )
                return distance_squared, str(candidate.get("value_ref"))

            selected_value = deepcopy(min(usable, key=selection_cost))
            selected_value.update(
                {
                    "selection_policy": "existential_quantity_minimum_current_cost",
                    "selection_quantifier": "existential",
                    "requested_quantity": 1,
                    "human_specific_instance_required": False,
                }
            )
            usable = [selected_value]
        conditionally_required = _conditionally_required(slot, bindings)
        if not slot.required and not conditionally_required and not any(item.get("explicit") for item in usable) and not override:
            slot_results.append(_slot_result(slot, "optional_unbound", []))
        elif len(usable) == 1 and slot.auto_bind_unique:
            bindings[slot.slot_id] = deepcopy(usable[0])
            slot_results.append(_slot_result(slot, "bound", usable, usable[0]))
        elif len(usable) > 1:
            slot_results.append(_slot_result(slot, "ambiguous", usable))
        elif slot.required or conditionally_required:
            slot_results.append(_slot_result(slot, "missing", []))
        else:
            slot_results.append(_slot_result(slot, "optional_unbound", []))

    preconditions = _resolve_preconditions(template, bindings, runtime_state, executor_profile, runtime_objects)
    unresolved = [item for item in slot_results if item["status"] in {"ambiguous", "missing"}]
    unsafe = next((item for item in preconditions if item["status"] == "unsafe_conflict"), None)
    template_confirmation_required = bool(selected.get("requires_human_confirmation"))
    if unsafe:
        status = "unsafe_switch"
        next_gap = unsafe
    elif unresolved:
        status = "clarification_required"
        next_gap = sorted(unresolved, key=lambda item: item["priority"])[0]
        slot = next((item for item in template.slots if item.slot_id == next_gap.get("slot_id")), None)
        role_name = next(
            (name for name in (slot.role_names if slot else ()) if name in (language_analysis.get("grounded_intent_frame") or {}).get("roles", {})),
            next_gap.get("slot_id"),
        )
        role_grounding = ((language_analysis.get("grounded_intent_frame") or {}).get("roles") or {}).get(role_name) or {}
        if role_grounding.get("constraint_rejections"):
            substitute_candidates = [
                {
                    "value_ref": item.get("entity_ref"),
                    "label": item.get("current_name_surface"),
                    "value_type": item.get("kind"),
                    "explicit": False,
                    "evidence": "current_observation_constraint_rejection",
                    "evidence_strength": 0,
                    "observed_attributes": deepcopy(item.get("observed_attributes", {})),
                    "constraint_mismatch": deepcopy(item.get("constraint_mismatches", [])),
                    "requires_human_substitution_confirmation": True,
                }
                for item in role_grounding.get("constraint_rejections", [])
                if item.get("entity_ref")
            ]
            next_gap = {
                **deepcopy(next_gap),
                "kind": "grounding_evidence_slot",
                "required_condition": f"{next_gap.get('slot_id')}_grounded_in_current_world",
                "requested_constraints": deepcopy((role_grounding.get("semantic_role") or {}).get("constraints", [])),
                "constraint_rejections": deepcopy(role_grounding.get("constraint_rejections", [])),
                "candidates": substitute_candidates,
                "observation_evidence_set_id": role_grounding.get("observation_evidence_set_id"),
            }
    elif template_confirmation_required:
        status = "template_confirmation_required"
        next_gap = {
            "kind": "template_mapping",
            "template_id": template.template_id,
            "novel_surface": selected.get("novel_surface"),
        }
    else:
        status = "ready" if all(item["status"] == "satisfied" for item in preconditions) else "subgoals_required"
        next_gap = None
    canonical = _canonical_utterance(template.template_id, bindings)
    return {
        "schema_version": "1.0.0",
        "status": status,
        "template_id": template.template_id,
        "goal_fact": template.goal_fact,
        "template_candidate": deepcopy(selected),
        "template_alternatives": deepcopy(candidates[1:]),
        "bindings": deepcopy(bindings),
        "slot_results": slot_results,
        "precondition_results": preconditions,
        "next_gap": deepcopy(next_gap),
        "question": _render_question(status, next_gap, template, bindings),
        "canonical_utterance": canonical,
        "world_revision": world_revision,
        "candidate_only": True,
        "runtime_fact_committed": False,
        "direct_execution_allowed": False,
    }


def normalize_perception_gap(
    process_resolution: dict[str, Any] | None,
    task_perception: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Project perceptual evidence failures onto declared process slots."""
    process_resolution = process_resolution or {}
    task_perception = task_perception or {}
    template = _TEMPLATE_BY_ID.get(process_resolution.get("template_id"))
    grounding = task_perception.get("concept_grounding") or {}
    if not template or grounding.get("grounding_status") == "spatially_grounded":
        return None
    observed_roles = {item.get("role") for item in grounding.get("candidate_bindings", [])}
    provider_values = {
        "graspable_objects": grounding.get("candidate_options", []) or grounding.get("constraint_rejections", []),
        "support_surfaces": grounding.get("support_candidate_options", []),
    }
    perception_roles = {"graspable_objects": "target", "support_surfaces": "support"}
    for slot in sorted(template.slots, key=lambda item: item.priority):
        observed_role = perception_roles.get(slot.candidate_provider)
        if not observed_role or observed_role in observed_roles:
            continue
        semantic_binding = (process_resolution.get("bindings") or {}).get(slot.slot_id)
        if not semantic_binding and not slot.required:
            continue
        binding_evidence = str((semantic_binding or {}).get("evidence") or "")
        binding_world_revision = (semantic_binding or {}).get(
            "observation_world_revision"
        )
        current_world_revision = process_resolution.get("world_revision")
        if (
            semantic_binding
            and binding_evidence.startswith("current_verified_relation:")
            and binding_world_revision == current_world_revision
        ):
            # A bounded observation may add candidates, but it cannot demote a
            # role already selected by a version-matched, physically verified
            # relation. Otherwise perception becomes a second fact source.
            continue
        candidates = [
            {
                "value_ref": item.get("entity_ref"),
                "label": item.get("label_hint"),
                "value_type": slot.value_type,
                "explicit": False,
                "evidence": "bounded_task_perception_candidate",
                "constraint_mismatch": deepcopy(item.get("mismatched_attributes", [])),
                "observed_attributes": deepcopy(item.get("observed_attributes", {})),
                "estimated_position": deepcopy(item.get("estimated_position")),
            }
            for item in provider_values.get(slot.candidate_provider, [])
            if item.get("entity_ref")
        ]
        gap = {
            "kind": "grounding_evidence_slot",
            "slot_id": slot.slot_id,
            "value_type": slot.value_type,
            "status": "ambiguous" if len(candidates) > 1 else "missing_current_evidence",
            "priority": slot.priority,
            "candidate_provider": f"bounded_perception:{slot.candidate_provider}",
            "candidates": candidates,
            "bound_value": deepcopy(semantic_binding),
            "required_condition": f"{slot.slot_id}_grounded_in_current_world",
            "current_evidence": deepcopy(grounding.get("relation_evidence")),
            "resolution_action": "observe_or_confirm_candidate_without_committing_physical_effect",
        }
        updated = deepcopy(process_resolution)
        updated.update({
            "status": "clarification_required",
            "next_gap": gap,
            "question": (
                task_perception.get("prompt")
                if grounding.get("constraint_rejections") and candidates
                else _render_question("clarification_required", gap, template, updated.get("bindings", {}))
            ),
            "grounding_gap": {
                "required_condition": gap["required_condition"],
                "slot_id": slot.slot_id,
                "candidate_provider": gap["candidate_provider"],
                "candidate_values": deepcopy(candidates),
                "perception_observation_id": task_perception.get("perception_observation", {}).get("observation_id"),
                "language_confirmation_does_not_commit_physical_facts": True,
                "requested_constraints": deepcopy(
                    task_perception.get("task_perception_frame", {}).get("target_constraints", {})
                ),
            },
        })
        return updated
    return None


def _template_candidates(utterance: str, analysis: dict[str, Any]) -> list[dict[str, Any]]:
    operators = analysis.get("canonical_frame", {}).get("operators", [])
    candidates = []
    goal_template = {
        "object_in_gripper": "grasp_object",
        "object_supported_at_destination": "place_object",
        "object_received_by_recipient": "handover_object",
        "object_at_target_region": "transport_object",
    }.get(analysis.get("canonical_frame", {}).get("goal_relation"))
    if goal_template:
        candidates.append({
            "template_id": goal_template,
            "score": 1.1,
            "basis": "terminal_goal_relation_projection",
            "requires_human_confirmation": False,
            "novel_surface": None,
        })
    for operator in operators:
        template = _TEMPLATE_BY_OPERATOR.get(operator)
        if template:
            candidates.append({
                "template_id": template.template_id,
                "score": 1.0,
                "basis": "recognized_event_operator",
                "requires_human_confirmation": False,
                "novel_surface": None,
            })
    if candidates:
        return _deduplicate_candidates(candidates)
    normalized = re.sub(r"[\s，。！？、,.!?]+", "", utterance)
    has_object = bool(analysis.get("entity_mentions") or analysis.get("role_bindings", {}).get("theme"))
    novel_handover_surface = _novel_surface_before_relation(normalized, "给", analysis) if "给" in normalized else None
    if novel_handover_surface:
        candidates.append({
            "template_id": "handover_object",
            "score": 0.78,
            "basis": "object_plus_recipient_relation_with_unknown_predicate",
            "requires_human_confirmation": True,
            "novel_surface": novel_handover_surface,
        })
    if has_object and any(marker in normalized for marker in ("带到", "拿到", "送到", "端到", "带走", "拿来", "捎到")):
        candidates.append({
            "template_id": "transport_object",
            "score": 0.74,
            "basis": "object_plus_directional_transport_relation",
            "requires_human_confirmation": True,
            "novel_surface": next((item for item in ("带到", "拿到", "送到", "端到", "带走", "拿来", "捎到") if item in normalized), None),
        })
    return _deduplicate_candidates(candidates)


def _deduplicate_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for item in candidates:
        current = by_id.get(item["template_id"])
        if current is None or item["score"] > current["score"]:
            by_id[item["template_id"]] = item
    return sorted(by_id.values(), key=lambda item: item["score"], reverse=True)


def _slot_candidates(
    slot: SlotSpec,
    utterance: str,
    analysis: dict[str, Any],
    runtime_objects: list[dict[str, Any]],
    runtime_state: dict[str, Any],
    semantic_regions: list[dict[str, Any]],
    current_bindings: dict[str, dict[str, Any]],
    evidence_bindings: list[dict[str, Any]],
    world_revision: int,
) -> list[dict[str, Any]]:
    role = next((analysis.get("role_bindings", {}).get(name) for name in slot.role_names if analysis.get("role_bindings", {}).get(name)), {})
    if slot.candidate_provider == "graspable_objects":
        values = [
            item for item in runtime_objects
            if item.get("active") is not False
            and item.get("fixed") is not True
            and (
                item.get("kind") in {"graspable_object", "graspable_container"}
                or {"graspable", "movable"}.intersection(item.get("affordances") or [])
                or item.get("fixed") is False
            )
        ]
        concept_kinds = set(role.get("compatible_kinds", []))
        if concept_kinds:
            concept_compatible_values = [item for item in values if item.get("kind") in concept_kinds]
            if concept_compatible_values:
                values = concept_compatible_values
        role_name = next((name for name in slot.role_names if name in (analysis.get("semantic_constraint_frame") or {}).get("roles", {})), slot.slot_id)
        semantic_grounding = ground_semantic_role(
            analysis.get("semantic_constraint_frame") or {},
            analysis.get("observation_evidence") or {},
            role_name,
            candidate_entity_refs={item.get("entity_id") for item in values},
        )
        grounded_candidates = semantic_grounding.get("candidate_bindings", [])
        grounded_by_ref = {item.get("entity_ref"): item for item in grounded_candidates}
        grounded_refs = set(grounded_by_ref)
        if semantic_grounding.get("status") == "missing" and (semantic_grounding.get("semantic_role") or {}).get("constraints"):
            values = []
        elif grounded_refs:
            values = [item for item in values if item.get("entity_id") in grounded_refs]
        return [
            _entity_value(
                item,
                explicit=int((grounded_by_ref.get(item.get("entity_id")) or {}).get("evidence_strength", 0)) >= 500,
                evidence_bindings=evidence_bindings,
                world_revision=world_revision,
                semantic_binding=grounded_by_ref.get(item.get("entity_id")),
                verified_relation=(
                    "held_by_executor"
                    if runtime_state.get("holding") == item.get("entity_id")
                    else "held_by_human"
                    if item.get("received_by")
                    else None
                ),
            )
            for item in values
        ]
    if slot.candidate_provider == "human_recipients":
        values = [
            item for item in runtime_objects
            if item.get("active") is not False and item.get("kind") == "human_recipient"
        ]
        role_name = next((name for name in slot.role_names if name in (analysis.get("semantic_constraint_frame") or {}).get("roles", {})), slot.slot_id)
        semantic_grounding = ground_semantic_role(
            analysis.get("semantic_constraint_frame") or {},
            analysis.get("observation_evidence") or {},
            role_name,
            candidate_entity_refs={item.get("entity_id") for item in values},
        )
        grounded_by_ref = {item.get("entity_ref"): item for item in semantic_grounding.get("candidate_bindings", [])}
        if grounded_by_ref:
            values = [item for item in values if item.get("entity_id") in grounded_by_ref]
        return [
            _entity_value(
                item,
                explicit=int((grounded_by_ref.get(item.get("entity_id")) or {}).get("evidence_strength", 0)) >= 500,
                evidence_bindings=evidence_bindings,
                world_revision=world_revision,
                semantic_binding=grounded_by_ref.get(item.get("entity_id")),
            )
            for item in values
        ]
    if slot.candidate_provider == "support_surfaces":
        values = [item for item in runtime_objects if item.get("active") is not False and item.get("kind") == "operation_surface"]
        target_region = (current_bindings.get("target_region") or {}).get("value_ref")
        if target_region:
            values = [item for item in values if item.get("region_id") == target_region]
        semantic_frame = analysis.get("semantic_constraint_frame") or {}
        observation_evidence = analysis.get("observation_evidence") or {}
        relation_roles = [
            (name, relation_role)
            for name, relation_role in (semantic_frame.get("roles") or {}).items()
            if relation_role.get("relation_target_role") in slot.role_names
            and relation_role.get("relation_predicate") == "supported_by"
        ]
        relational_bindings: dict[str, dict[str, Any]] = {}
        if relation_roles:
            allowed_support_refs = {item.get("entity_id") for item in values}
            for relation_role_name, relation_role in relation_roles:
                modifier_grounding = ground_semantic_role(
                    semantic_frame,
                    observation_evidence,
                    relation_role_name,
                )
                modifier_bindings = modifier_grounding.get("candidate_bindings", [])
                support_refs = {
                    relation.get("object")
                    for modifier in modifier_bindings
                    for relation in modifier.get("observed_relations", [])
                    if relation.get("predicate") == relation_role["relation_predicate"]
                    and relation.get("object")
                }
                allowed_support_refs &= support_refs
                for support_ref in support_refs:
                    relational_bindings[support_ref] = {
                        "binding_basis": "relation_constraint_grounded_in_current_observation",
                        "evidence_strength": 550,
                        "world_revision": observation_evidence.get("world_revision", world_revision),
                        "matched_constraints": [{
                            "predicate_type": "relation_constraint",
                            "predicate": relation_role["relation_predicate"],
                            "target_role": relation_role["relation_target_role"],
                            "modifier_role": relation_role_name,
                            "modifier_entity_refs": [
                                item.get("entity_ref") for item in modifier_bindings
                            ],
                        }],
                    }
            values = [
                item for item in values
                if item.get("entity_id") in allowed_support_refs
            ]
        role_name = next((name for name in slot.role_names if name in (analysis.get("semantic_constraint_frame") or {}).get("roles", {})), slot.slot_id)
        semantic_grounding = ground_semantic_role(
            semantic_frame,
            observation_evidence,
            role_name,
            candidate_entity_refs={item.get("entity_id") for item in values},
        )
        grounded_by_ref = {item.get("entity_ref"): item for item in semantic_grounding.get("candidate_bindings", [])}
        if grounded_by_ref:
            values = [item for item in values if item.get("entity_id") in grounded_by_ref]
        grounded_by_ref.update(relational_bindings)
        return [
            _entity_value(
                item,
                explicit=int((grounded_by_ref.get(item.get("entity_id")) or {}).get("evidence_strength", 0)) >= 500,
                evidence_bindings=evidence_bindings,
                world_revision=world_revision,
                semantic_binding=grounded_by_ref.get(item.get("entity_id")),
            )
            for item in values
        ]
    if slot.candidate_provider == "semantic_regions":
        return [
            {
                "value_ref": item.get("region_id"),
                "label": item.get("label"),
                "value_type": "semantic_region",
                "explicit": bool(item.get("label") and item["label"] in utterance),
                "evidence": "current_semantic_region_snapshot",
            }
            for item in semantic_regions
        ]
    if slot.candidate_provider == "transport_modes":
        if any(marker in utterance for marker in ("放到", "放在", "送到", "端到")):
            return [{"value_ref": "place_at_region", "label": "送到后放下", "value_type": "transport_mode", "explicit": True, "evidence": "language_result_relation"}]
        if any(marker in utterance for marker in ("拿到", "带到", "带走", "拿来")):
            return [{"value_ref": "retain_holding", "label": "带到后继续拿着", "value_type": "transport_mode", "explicit": True, "evidence": "language_process_relation"}]
        return [
            {"value_ref": "retain_holding", "label": "带到后继续拿着", "value_type": "transport_mode", "explicit": False, "evidence": "template_candidate"},
            {"value_ref": "place_at_region", "label": "送到后放下", "value_type": "transport_mode", "explicit": False, "evidence": "template_candidate"},
        ]
    return []


def _resolve_preconditions(
    template: ProcessTemplate,
    bindings: dict[str, dict[str, Any]],
    runtime_state: dict[str, Any],
    executor_profile: dict[str, Any],
    runtime_objects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    holding = runtime_state.get("holding")
    holding_by_effector = runtime_state.get("holding_by_effector", {})
    free_effector = next((name for name, ref in holding_by_effector.items() if not ref), None)
    theme_ref = (bindings.get("theme") or {}).get("value_ref")
    holding_label = next((item.get("label") for item in runtime_objects if item.get("entity_id") == holding), holding)
    results = []
    for contract in template.causal_preconditions:
        fact = contract["fact"]
        if fact == "object_in_gripper" and theme_ref and holding == theme_ref:
            status = "satisfied"
        elif fact == "gripper_available" and (free_effector or not holding):
            status = "satisfied"
        elif fact == "gripper_available" and theme_ref and holding and holding != theme_ref:
            status = "unsafe_conflict"
        elif fact in {"recipient_ready", "handover_pose_feasible", "placement_pose_feasible", "route_feasible", "object_within_reach", "object_grounded", "destination_grounded", "recipient_grounded"}:
            status = "producible_subgoal"
        elif fact == "object_in_gripper":
            status = "producible_subgoal"
        else:
            status = "unknown"
        results.append({
            "kind": "causal_precondition",
            "fact": fact,
            "status": status,
            "producer": contract.get("producer"),
            "current_holding": holding,
            "current_holding_label": holding_label,
            "executor_supports_producer": contract.get("producer") in set(executor_profile.get("supported_actions", [])) or contract.get("producer") is not None,
        })
    return results


def _slot_result(slot: SlotSpec, status: str, candidates: list[dict[str, Any]], bound: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "kind": "parameter_slot",
        "slot_id": slot.slot_id,
        "value_type": slot.value_type,
        "status": status,
        "priority": slot.priority,
        "candidate_provider": slot.candidate_provider,
        "candidates": deepcopy(candidates),
        "bound_value": deepcopy(bound),
    }


def _conditionally_required(slot: SlotSpec, bindings: dict[str, dict[str, Any]]) -> bool:
    if not slot.required_when or "=" not in slot.required_when:
        return False
    binding_id, expected = slot.required_when.split("=", 1)
    return (bindings.get(binding_id) or {}).get("value_ref") == expected


def _render_question(
    status: str,
    gap: dict[str, Any] | None,
    template: ProcessTemplate,
    bindings: dict[str, dict[str, Any]],
) -> str | None:
    if status == "template_confirmation_required":
        return f"我暂时把“{gap.get('novel_surface') or '这个说法'}”理解为{_goal_description(template.template_id, bindings)}。这个理解对吗？"
    if status == "unsafe_switch":
        return f"我当前还拿着{gap.get('current_holding_label') or '另一个对象'}，没有可用执行器继续当前目标。要先安全放下当前持物吗？"
    if status != "clarification_required" or not gap:
        return None
    if gap.get("kind") == "grounding_evidence_slot" and gap.get("constraint_rejections"):
        requested = "、".join(
            str(item.get("surface") or item.get("value"))
            for item in gap.get("requested_constraints", [])
            if item.get("surface") or item.get("value")
        ) or "所述属性"
        labels = [
            item.get("current_name_surface") or item.get("label")
            for item in gap.get("constraint_rejections", [])
            if item.get("current_name_surface") or item.get("label")
        ]
        return (
            f"我按当前空间完成了有界观察，没有发现符合“{requested}”约束的目标；"
            f"但发现了这些同类候选：{'、'.join(labels)}。请指出其中哪一个可以替代，或补充新的可观察特征。"
        )
    slot_id = gap["slot_id"]
    labels = [item.get("label") for item in gap.get("candidates", []) if item.get("label")]
    if slot_id == "theme":
        return f"你想让我操作哪一个？当前候选是：{'、'.join(labels)}。" if labels else "你想让我操作哪个当前可见或可定位的物体？"
    if slot_id == "recipient":
        return f"你想让我交给谁？当前在场候选是：{'、'.join(labels)}。" if labels else "你想让我交给谁？当前还没有可唯一落地的接收者。"
    if slot_id == "destination":
        return f"你想让我放到哪里？当前可放置候选是：{'、'.join(labels)}。" if labels else "你想让我放到哪个可承载位置？"
    if slot_id == "target_region":
        return f"你想让我带到哪个区域？当前区域候选是：{'、'.join(labels)}。" if labels else "你想让我带到哪里？"
    if slot_id == "transport_mode":
        return f"到达后是继续拿着，还是放下？当前候选是：{'、'.join(labels)}。"
    return f"当前过程还缺少参数：{slot_id}。请补充这个值。"


def _goal_description(template_id: str, bindings: dict[str, dict[str, Any]]) -> str:
    theme = (bindings.get("theme") or {}).get("label") or "这个对象"
    if template_id == "handover_object":
        recipient = (bindings.get("recipient") or {}).get("label") or "接收者"
        return f"把{theme}带到{recipient}面前并交给对方"
    if template_id == "transport_object":
        region = (bindings.get("target_region") or {}).get("label") or "目标区域"
        return f"把{theme}带到{region}"
    if template_id == "place_object":
        destination = (bindings.get("destination") or {}).get("label") or "目标承载面"
        return f"把{theme}稳定放到{destination}"
    return f"拿起{theme}"


def _canonical_utterance(template_id: str, bindings: dict[str, dict[str, Any]]) -> str | None:
    theme = (bindings.get("theme") or {}).get("label")
    if not theme:
        return None
    if template_id == "grasp_object":
        return f"拿起{theme}"
    if template_id == "place_object":
        destination = (bindings.get("destination") or {}).get("label")
        return f"把{theme}放到{destination}" if destination else None
    if template_id == "handover_object":
        recipient = (bindings.get("recipient") or {}).get("label")
        return f"把{theme}递给{recipient}" if recipient else None
    if template_id == "transport_object":
        region = (bindings.get("target_region") or {}).get("label")
        mode = (bindings.get("transport_mode") or {}).get("value_ref")
        if region:
            return f"把{theme}{'送到' if mode == 'place_at_region' else '带到'}{region}"
    return None


def _entity_value(
    item: dict[str, Any],
    *,
    explicit: bool,
    evidence_bindings: list[dict[str, Any]],
    world_revision: int,
    verified_relation: str | None = None,
    semantic_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_confirmations = [
        binding for binding in evidence_bindings
        if binding.get("entity_ref") == item.get("entity_id")
        and binding.get("world_revision") == world_revision
    ]
    if verified_relation:
        evidence_kind = f"current_verified_relation:{verified_relation}"
        evidence_strength = 650 if explicit else 450
    elif explicit:
        evidence_kind = (semantic_binding or {}).get("binding_basis") or "semantic_constraints_grounded_in_current_observation"
        evidence_strength = int((semantic_binding or {}).get("evidence_strength") or 500)
    elif current_confirmations:
        strongest_confirmation = max(
            current_confirmations,
            key=lambda binding: int(binding.get("evidence_strength", 400)),
        )
        evidence_kind = strongest_confirmation.get("binding_source") or "current_human_confirmed_binding"
        evidence_strength = int(strongest_confirmation.get("evidence_strength", 400))
    else:
        evidence_kind, evidence_strength = "current_world_snapshot_candidate", 100
    return {
        "value_ref": item.get("entity_id"),
        "label": item.get("label"),
        "value_type": item.get("kind"),
        "explicit": explicit,
        "evidence": evidence_kind,
        "evidence_strength": evidence_strength,
        "evidence_sources": deepcopy(current_confirmations),
        "matched_semantic_constraints": deepcopy((semantic_binding or {}).get("matched_constraints", [])),
        "observation_world_revision": (semantic_binding or {}).get("world_revision", world_revision),
    }


def _object_concepts_from_language_analysis(language_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Recover the object concept adapters already present in the semantic frame."""
    concepts: dict[str, dict[str, Any]] = {}
    for role in (language_analysis.get("role_bindings") or {}).values():
        concept_id = (role or {}).get("concept_id")
        if not concept_id:
            continue
        concepts.setdefault(concept_id, {
            "concept_id": concept_id,
            "compatible_kinds": deepcopy((role or {}).get("compatible_kinds", [])),
            "functional_affordances": deepcopy((role or {}).get("functional_affordances", [])),
        })
    return list(concepts.values())


def _non_dominated_evidence(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only equally strongest current evidence may remain ambiguous."""
    if not values:
        return []
    def strength(item: dict[str, Any]) -> int:
        if item.get("evidence_strength") is not None:
            return int(item["evidence_strength"])
        return 500 if item.get("explicit") else 100

    strongest = max(strength(item) for item in values)
    by_ref: dict[str, dict[str, Any]] = {}
    for item in values:
        if strength(item) != strongest:
            continue
        ref = str(item.get("value_ref"))
        by_ref.setdefault(ref, item)
    return list(by_ref.values())


def _mentioned(item: dict[str, Any], utterance: str) -> bool:
    label = str(item.get("label") or "")
    return bool(label and label in utterance)


def _distinctive_entity_text_match_score(
    item: dict[str, Any], utterance: str, role: dict[str, Any]
) -> int:
    generic_surface = str(role.get("matched_alias") or "")
    surfaces = [str(item.get("label") or ""), *[str(alias) for alias in item.get("language_aliases", [])]]
    best = 0
    for surface in surfaces:
        if not surface:
            continue
        if surface in utterance:
            best = max(best, len(surface))
            continue
        for length in range(len(surface) - 1, 1, -1):
            matches = {
                surface[start:start + length]
                for start in range(len(surface) - length + 1)
                if surface[start:start + length] in utterance
            }
            distinctive = [match for match in matches if match != generic_surface]
            if distinctive:
                best = max(best, length)
                break
    return best


def _role_locally_mentions_entity(item: dict[str, Any], utterance: str, role: dict[str, Any]) -> bool:
    label = str(item.get("label") or "")
    role_start = role.get("start")
    if label and isinstance(role_start, int):
        positions = [match.start() for match in re.finditer(re.escape(label), utterance)]
        if any(position <= role_start < position + len(label) for position in positions):
            return True
    if label and label in utterance and not isinstance(role_start, int):
        return True
    return False


def _novel_surface_before_relation(text: str, relation: str, analysis: dict[str, Any]) -> str | None:
    residual = text
    for mention in analysis.get("entity_mentions", []):
        alias = str(mention.get("matched_alias") or "")
        if alias:
            residual = residual.replace(alias, "", 1)
    for marker in ("把", "这个", "那个", "它", "人类", "家人", "主人", "用户", "接收人", "我", "现在", "再", "请"):
        residual = residual.replace(marker, "")
    match = re.search(rf"([\u4e00-\u9fff]{{1,2}}){re.escape(relation)}", residual)
    if not match:
        return None
    return match.group(1) + relation
