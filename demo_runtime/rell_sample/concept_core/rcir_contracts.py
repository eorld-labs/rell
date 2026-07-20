from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any


CONTRACT_SCHEMA_VERSION = "1.0.0"
NON_TRANSFERABLE_EXPERIENCE_FIELDS = {
    "absolute_world_coordinates",
    "entity_ref",
    "fixed_action_durations",
    "joint_angles",
    "position",
    "robot_joint_angles",
    "single_body_trajectory",
    "source_goal_utterance",
    "surface_form",
    "teacher_key_sequence",
    "trajectory",
    "utterance",
}
OBSERVABLE_ATTRIBUTE_PRIORITY = (
    "color",
    "material",
    "shape",
    "size",
    "transparency",
    "temperature",
    "state",
)


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _candidate_view(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_ref": candidate.get("entity_ref"),
        "observed_attributes": deepcopy(candidate.get("observed_attributes") or {}),
        "world_revision": candidate.get("world_revision"),
    }


def _concept_constraint_view(constraint: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "predicate_type",
        "concept_id",
        "observation_field",
        "value",
        "accepted_observed_values",
        "applies_to_concepts",
        "physical_fact_committed",
    )
    return {
        key: deepcopy(constraint.get(key))
        for key in allowed
        if constraint.get(key) is not None
    }


def build_grounding_clarification_contract(
    role: str,
    candidates: list[dict[str, Any]],
    *,
    world_revision: int,
    accumulated_constraints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Request the smallest observable constraint that can reduce an ambiguity."""
    current = [
        _candidate_view(item)
        for item in candidates
        if item.get("entity_ref")
        and item.get("world_revision") in {None, world_revision}
    ]
    distinguishing = []
    fields = sorted(
        {
            field
            for item in current
            for field, value in item["observed_attributes"].items()
            if value is not None
        },
        key=lambda field: (
            OBSERVABLE_ATTRIBUTE_PRIORITY.index(field)
            if field in OBSERVABLE_ATTRIBUTE_PRIORITY
            else len(OBSERVABLE_ATTRIBUTE_PRIORITY),
            field,
        ),
    )
    for field in fields:
        partitions: dict[str, list[str]] = {}
        for item in current:
            value = item["observed_attributes"].get(field)
            if value is None:
                continue
            partitions.setdefault(str(value), []).append(item["entity_ref"])
        if len(partitions) > 1:
            distinguishing.append(
                {
                    "observation_field": field,
                    "value_partitions": [
                        {"value": value, "candidate_entity_refs": sorted(refs)}
                        for value, refs in sorted(partitions.items())
                    ],
                    "maximum_remaining_candidates": max(map(len, partitions.values())),
                }
            )
    best = min(
        distinguishing,
        key=lambda item: (
            item["maximum_remaining_candidates"],
            fields.index(item["observation_field"]),
        ),
        default=None,
    )
    status = (
        "resolved"
        if len(current) == 1
        else "awaiting_observable_constraint"
        if best
        else "awaiting_new_observation_or_direct_reference"
    )
    contract = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_type": "grounding_clarification",
        "role": role,
        "world_revision": world_revision,
        "status": status,
        "candidate_entity_refs": sorted(item["entity_ref"] for item in current),
        "accumulated_constraints": [
            _concept_constraint_view(item)
            for item in (accumulated_constraints or [])
            if isinstance(item, dict)
        ],
        "requested_constraint": (
            {
                "constraint_type": "observable_attribute",
                "observation_field": best["observation_field"],
                "accepted_values": [
                    item["value"] for item in best["value_partitions"]
                ],
                "minimum_information_required": True,
            }
            if best
            else None
        ),
        "resolution_loop": [
            "request_minimum_observable_constraint",
            "compile_answer_as_concept_constraint",
            "reobserve_current_world_revision",
            "rebind_role",
        ],
        "raw_language_required_downstream": False,
        "runtime_fact_committed": False,
    }
    contract["contract_id"] = "clarify_" + _digest(contract)[:16]
    return contract


def apply_grounding_constraint(
    contract: dict[str, Any],
    *,
    observation_field: str,
    value: Any,
    candidates: list[dict[str, Any]],
    world_revision: int,
) -> dict[str, Any]:
    """Compile a clarification answer into a constraint and re-ground it."""
    if contract.get("world_revision") != world_revision:
        raise ValueError("clarification_world_revision_changed_reobserve_required")
    requested = contract.get("requested_constraint") or {}
    if requested.get("observation_field") != observation_field:
        raise ValueError("clarification_answer_does_not_fill_requested_constraint")
    matched = [
        item
        for item in candidates
        if item.get("entity_ref") in set(contract.get("candidate_entity_refs") or [])
        and (item.get("observed_attributes") or {}).get(observation_field) == value
    ]
    constraint = {
        "predicate_type": "attribute_constraint",
        "observation_field": observation_field,
        "value": value,
        "source": "human_clarification_compiled_to_concept_constraint",
        "physical_fact_committed": False,
    }
    next_contract = build_grounding_clarification_contract(
        str(contract.get("role") or "unknown"),
        matched,
        world_revision=world_revision,
        accumulated_constraints=[
            *deepcopy(contract.get("accumulated_constraints") or []),
            constraint,
        ],
    )
    next_contract["resolved_entity_ref"] = (
        matched[0].get("entity_ref") if len(matched) == 1 else None
    )
    return next_contract


def _role_type_slots(experience: dict[str, Any]) -> list[dict[str, Any]]:
    source = experience.get("source_concept_contract") or {}
    roles = source.get("semantic_roles") or {}
    slots = []
    for role, descriptor in sorted(roles.items()):
        if not isinstance(descriptor, dict):
            continue
        slots.append(
            {
                "role": role,
                "concept_id": descriptor.get("concept_id"),
                "entity_type": descriptor.get("entity_type"),
                "required_affordances": deepcopy(
                    descriptor.get("functional_affordances") or []
                ),
                "binding_scope": "rebind_from_current_world_evidence",
            }
        )
    target = experience.get("target_binding") or {}
    if target.get("concept_id") and not any(
        item.get("role") == "theme" for item in slots
    ):
        slots.append(
            {
                "role": "theme",
                "concept_id": target.get("concept_id"),
                "entity_type": None,
                "required_affordances": [],
                "binding_scope": "rebind_from_current_world_evidence",
            }
        )
    return slots


def build_portable_experience_contract(experience: dict[str, Any]) -> dict[str, Any]:
    """Extract reusable causal invariants without old scene or embodiment bindings."""
    invariant = experience.get("invariant_contract") or {}
    effects = experience.get("effect_contract") or {}
    contract = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_type": "portable_experience",
        "experience_ref": experience.get("experience_id"),
        "goal_fact": experience.get("goal_fact"),
        "role_type_slots": _role_type_slots(experience),
        "operator_invariants": deepcopy(experience.get("process_chain") or []),
        "causal_contract": {
            "requires": deepcopy(
                effects.get("requires")
                or invariant.get("requires")
                or invariant.get("preconditions")
                or []
            ),
            "produces": deepcopy(
                effects.get("produces")
                or effects.get("establishes")
                or invariant.get("produces")
                or []
            ),
            "destroys": deepcopy(
                effects.get("destroys") or invariant.get("destroys") or []
            ),
            "verification": deepcopy(
                effects.get("verification")
                or invariant.get("verification")
                or invariant.get("verification_conditions")
                or []
            ),
            "termination_conditions": deepcopy(
                invariant.get("termination_conditions")
                or ([experience.get("goal_fact")] if experience.get("goal_fact") else [])
            ),
        },
        "process_invariants": {
            "topology": deepcopy(
                invariant.get("topology_invariants")
                or invariant.get("ordered_relations")
                or []
            ),
            "direction_constraints": deepcopy(
                invariant.get("direction_constraints") or []
            ),
            "physical_constraints": deepcopy(
                invariant.get("physical_constraints")
                or invariant.get("invariant_dimensions")
                or []
            ),
        },
        "migration_policy": {
            "rebind_all_roles_from_current_world_evidence": True,
            "replan_motion_for_current_embodiment": True,
            "current_fact_pruning_required": True,
            "non_transferable_fields": sorted(NON_TRANSFERABLE_EXPERIENCE_FIELDS),
        },
    }
    validation = validate_portable_experience_contract(contract)
    if not validation["valid"]:
        raise ValueError(
            "invalid_portable_experience_contract:" + ",".join(validation["errors"])
        )
    contract["contract_digest"] = _digest(contract)
    return contract


def _forbidden_paths(value: Any, path: str = "$") -> list[str]:
    violations = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in NON_TRANSFERABLE_EXPERIENCE_FIELDS:
                violations.append(child_path)
            violations.extend(_forbidden_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_forbidden_paths(child, f"{path}[{index}]"))
    return violations


def validate_portable_experience_contract(contract: dict[str, Any]) -> dict[str, Any]:
    errors = []
    if contract.get("contract_type") != "portable_experience":
        errors.append("contract_type_mismatch")
    violations = _forbidden_paths(contract)
    if violations:
        errors.append("non_transferable_field_leaked:" + "|".join(violations))
    policy = contract.get("migration_policy") or {}
    for flag in (
        "rebind_all_roles_from_current_world_evidence",
        "replan_motion_for_current_embodiment",
        "current_fact_pruning_required",
    ):
        if policy.get(flag) is not True:
            errors.append(f"migration_policy_missing:{flag}")
    for slot in contract.get("role_type_slots") or []:
        if slot.get("binding_scope") != "rebind_from_current_world_evidence":
            errors.append(f"role_binding_not_portable:{slot.get('role')}")
    return {"valid": not errors, "errors": errors}


__all__ = [
    "NON_TRANSFERABLE_EXPERIENCE_FIELDS",
    "apply_grounding_constraint",
    "build_grounding_clarification_contract",
    "build_portable_experience_contract",
    "validate_portable_experience_contract",
]
