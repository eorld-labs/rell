from __future__ import annotations

from typing import Any, Callable

from .action_units import find_action_concept_by_step, find_action_concepts_by_text
from .concept_evidence import build_concept_evidence_packet


def _role_binding(
    role_name: str,
    role_template: dict[str, Any],
    *,
    text: str,
    object_constraints: list[dict[str, Any]],
    spatial_constraints: list[dict[str, Any]],
    runtime_context_view: dict[str, Any] | None,
) -> dict[str, Any]:
    binding = {"role": role_template.get("role"), "entity_type": role_template.get("entity_type")}
    explicit_object = object_constraints[0] if object_constraints and role_name in {"container", "object"} else None
    implicit_object_candidate = None
    if role_name == "container" and "一杯水" in text and not any(marker in text for marker in ["杯子", "水杯", "这个杯", "那个杯"]):
        implicit_object_candidate = explicit_object
        explicit_object = None
    explicit_region = spatial_constraints[-1] if spatial_constraints and role_name in {"source", "destination"} else None
    executor = (runtime_context_view or {}).get("executor", {})
    held_objects = executor.get("holding", [])
    inferred_held_object = held_objects[0] if len(held_objects) == 1 and role_name in {"container", "object"} else None
    inferred_region = (
        executor.get("location_ref")
        if role_name in {"source", "destination"} and executor.get("location_ref")
        else None
    )
    if explicit_object:
        binding.update({
            "mention_status": "explicit",
            "grounding_status": "resolved",
            "entity_ref": explicit_object.get("object_ref"),
            "surface_form": explicit_object.get("source_text"),
            "binding_confidence": 0.96,
            "fallback": "none",
        })
    elif explicit_region:
        binding.update({
            "mention_status": "explicit",
            "grounding_status": "resolved",
            "entity_ref": explicit_region.get("region_ref"),
            "surface_form": explicit_region.get("source_text"),
            "binding_confidence": 0.94,
            "fallback": "none",
        })
    elif inferred_held_object:
        binding.update({
            "mention_status": "implicit",
            "grounding_status": "inferred",
            "entity_ref": inferred_held_object,
            "binding_confidence": 0.86,
            "binding_basis": "single_compatible_object_in_executor_holding",
            "fallback": "confirm_if_runtime_state_changes",
        })
    elif implicit_object_candidate:
        binding.update({
            "mention_status": "implicit",
            "grounding_status": "inferred",
            "entity_ref": implicit_object_candidate.get("object_ref"),
            "binding_confidence": 0.74,
            "binding_basis": "single_compatible_object_in_space_model",
            "fallback": "confirm_if_multiple_candidates_appear",
        })
    elif inferred_region and inferred_region == role_template.get("default_entity_ref"):
        binding.update({
            "mention_status": "implicit",
            "grounding_status": "inferred",
            "entity_ref": inferred_region,
            "binding_confidence": 0.84,
            "binding_basis": "executor_current_location_matches_role_default",
            "fallback": "confirm_if_runtime_state_changes",
        })
    elif role_name == "material" and role_template.get("value") and role_template["value"] in {"water"}:
        binding.update({
            "mention_status": "explicit" if "水" in text else "implicit",
            "grounding_status": "resolved_as_type",
            "value": role_template["value"],
            "binding_confidence": 0.98 if "水" in text else 0.72,
            "fallback": "none",
        })
    else:
        binding.update({
            "mention_status": "implicit",
            "grounding_status": "unresolved",
            "entity_ref": None,
            "binding_confidence": 0.0,
            "candidate_policy": "current_held_then_nearby_available" if role_name in {"container", "object"} else "resolve_from_current_space",
            "fallback": "require_confirmation_if_not_unique",
        })
    return binding


def _build_concept_package(
    concept: dict[str, Any],
    *,
    text: str,
    object_constraints: list[dict[str, Any]],
    spatial_constraints: list[dict[str, Any]],
    current_facts: list[str],
    runtime_context_view: dict[str, Any] | None,
) -> dict[str, Any]:
    kernel = concept.get("concept_kernel", {})
    contract = kernel.get("effect_contract", {})
    fact_set = set(current_facts)
    semantic_roles = {
        name: _role_binding(
            name,
            template,
            text=text,
            object_constraints=object_constraints,
            spatial_constraints=spatial_constraints,
            runtime_context_view=runtime_context_view,
        )
        for name, template in kernel.get("semantic_roles", {}).items()
    }
    unresolved_roles = [name for name, binding in semantic_roles.items() if binding.get("grounding_status") == "unresolved"]
    clarification_questions = [f"请确认概念 {concept.get('display_name')} 的 {name} 对应当前空间中的哪个对象或区域。" for name in unresolved_roles]
    return {
        "schema_version": "1.0.0",
        "concept_id": concept.get("concept_id"),
        "language_adapters": {
            "zh-CN": concept.get("aliases", []),
            "role": "trigger_concept_candidate_only",
        },
        "concept_kernel": {
            "operator": kernel.get("operator"),
            "semantic_roles": semantic_roles,
            "effect_contract": contract,
            "applicability_constraints": {
                "required_role_types": {
                    name: template.get("entity_type")
                    for name, template in kernel.get("semantic_roles", {}).items()
                    if template.get("entity_type")
                },
                "requires_runtime_grounding": True,
                "requires_executor_capability": concept.get("capability"),
            },
        },
        "fact_alignment": {
            "current_facts_considered": sorted(fact_set),
            "satisfied_requirements": [fact for fact in contract.get("requires", []) if fact in fact_set],
            "missing_requirements": [fact for fact in contract.get("requires", []) if fact not in fact_set],
            "goal_already_satisfied": any(fact in fact_set for fact in contract.get("produces", [])),
            "projection_only": True,
            "commit_requires_p016_verification": True,
        },
        "grounding_summary": {
            "all_required_roles_grounded": not unresolved_roles,
            "unresolved_roles": unresolved_roles,
            "clarification_required": bool(unresolved_roles),
            "clarification_questions": clarification_questions,
            "execution_gate": "pass_to_orchestration" if not unresolved_roles else "block_before_execution",
        },
        "experience_lookup": {
            "legacy_step_hint": concept.get("step_id"),
            "lookup_by": ["operator", "missing_requirements", "effect_contract.produces"],
            "policy": "resolve_by_current_fact_gaps_not_whole_utterance",
        },
        "candidate_only": True,
        "direct_execution_allowed": False,
        "must_reenter_orchestration_layer": True,
    }


def _build_action_concept_view(
    concept: dict[str, Any],
    *,
    activation_reason: str,
    step_detected_explicitly: bool,
    text: str,
    object_constraints: list[dict[str, Any]],
    spatial_constraints: list[dict[str, Any]],
    current_facts: list[str],
    runtime_context_view: dict[str, Any] | None,
) -> dict[str, Any]:
    match_basis = ["explicit_process_chain_step"] if step_detected_explicitly else ["local_action_alias_match"]
    confidence = 0.92 if step_detected_explicitly else 0.78
    return {
        "concept_id": concept.get("concept_id"),
        "display_name": concept.get("display_name"),
        "step_id": concept.get("step_id"),
        "capability": concept.get("capability"),
        "goal_fact_bridge": concept.get("goal_fact_bridge"),
        "activation_reason": activation_reason,
        "step_detected_explicitly": step_detected_explicitly,
        "source_policy": concept.get("source_policy"),
        "concept_package": _build_concept_package(
            concept,
            text=text,
            object_constraints=object_constraints,
            spatial_constraints=spatial_constraints,
            current_facts=current_facts,
            runtime_context_view=runtime_context_view,
        ),
        "direct_execution_allowed": False,
        "must_reenter_orchestration_layer": True,
        "concept_evidence": build_concept_evidence_packet(
            concept,
            concept_type="action_concept",
            activation_reason=activation_reason,
            match_basis=match_basis,
            confidence=confidence,
            runtime_context_view=runtime_context_view,
        ),
    }


def resolve_action_concepts(
    text: str,
    detected_steps: list[str],
    *,
    normalize_text_fn: Callable[[str], str],
    object_constraints: list[dict[str, Any]] | None = None,
    spatial_constraints: list[dict[str, Any]] | None = None,
    current_facts: list[str] | None = None,
    runtime_context_view: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    normalized = normalize_text_fn(text)
    resolved: list[dict[str, Any]] = []
    seen: set[str] = set()
    object_constraints = object_constraints or []
    spatial_constraints = spatial_constraints or []
    current_facts = current_facts or []

    for step_id in detected_steps:
        concept = find_action_concept_by_step(step_id)
        if not concept or concept["concept_id"] in seen:
            continue
        resolved.append(
            _build_action_concept_view(
                concept,
                activation_reason="显式过程链已识别出该动作步骤",
                step_detected_explicitly=True,
                text=text,
                object_constraints=object_constraints,
                spatial_constraints=spatial_constraints,
                current_facts=current_facts,
                runtime_context_view=runtime_context_view,
            )
        )
        seen.add(concept["concept_id"])

    for concept in find_action_concepts_by_text(normalized):
        if concept["concept_id"] in seen:
            continue
        resolved.append(
            _build_action_concept_view(
                concept,
                activation_reason="自然语言中命中高频动作概念表达",
                step_detected_explicitly=False,
                text=text,
                object_constraints=object_constraints,
                spatial_constraints=spatial_constraints,
                current_facts=current_facts,
                runtime_context_view=runtime_context_view,
            )
        )
        seen.add(concept["concept_id"])

    return resolved
