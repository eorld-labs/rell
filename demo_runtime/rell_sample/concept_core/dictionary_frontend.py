from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from .composition_grammar import (
    build_interpretation_lattice,
    build_scope_graph,
    make_referent_expression,
)
from .machine_dictionary import (
    dictionary_index,
    load_machine_dictionary,
    scan_surface_candidate_groups,
)


def _candidate_id(operator_refs: list[str], role_referents: dict[str, Any]) -> str:
    seed = repr((operator_refs, sorted(role_referents)))
    return "dictionary_candidate_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _semantic_index(dictionary: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for entry in dictionary.get("entries", []):
        result.setdefault(str(entry.get("semantic_value")), []).append(entry)
    return result


def _role_referent(role: dict[str, Any], world_revision: int) -> dict[str, Any]:
    entity_ref = role.get("entity_ref") or role.get("value_ref")
    if entity_ref:
        return make_referent_expression(
            "entity_ref", entity_ref=str(entity_ref), world_revision=world_revision
        )
    concept_ref = role.get("concept_id")
    constraints = deepcopy(role.get("constraints") or [])
    for field in ("spatial_relation", "relation_predicate", "quantity_constraint"):
        if role.get(field) is not None:
            constraints.append(
                {
                    "constraint_kind": field,
                    "value": deepcopy(role.get(field)),
                    "candidate_only": True,
                }
            )
    return make_referent_expression(
        "entity_selector",
        concept_refs=[concept_ref] if concept_ref else [],
        constraints=constraints,
        world_revision=world_revision,
    )


def _resolve_surface_groups_from_analysis(
    groups: list[dict[str, Any]], analysis: dict[str, Any]
) -> list[dict[str, Any]]:
    roles = analysis.get("role_bindings") or {}
    modifiers = (analysis.get("modifier_contract") or {}).get("modifiers", [])
    spatial_values = {
        role.get("spatial_relation") or role.get("relation_predicate")
        for role in roles.values()
        if isinstance(role, dict)
    }
    modifier_values = {item.get("value") for item in modifiers}
    resolved = []
    for group in groups:
        item = deepcopy(group)
        candidates = set(item.get("candidate_entry_refs") or [])
        selected = None
        if "predicate.supported_by" in candidates and spatial_values.intersection(
            {"on_support_surface", "supported_by"}
        ):
            selected = "predicate.supported_by"
        elif "modifier.aspect_attainment" in candidates and "attainment" in modifier_values:
            selected = "modifier.aspect_attainment"
        elif "modifier.direction_upward" in candidates and "upward" in modifier_values:
            selected = "modifier.direction_upward"
        if selected:
            item.update(
                {
                    "status": "resolved_from_composed_semantics",
                    "selected_entry_ref": selected,
                    "resolution_basis": "existing_structured_semantic_constraint",
                }
            )
        resolved.append(item)
    return resolved


def project_analysis_to_machine_dictionary(
    normalized_text: str,
    analysis: dict[str, Any],
    *,
    world_revision: int,
) -> dict[str, Any]:
    dictionary = load_machine_dictionary()
    semantic_index = _semantic_index(dictionary)
    operators = list((analysis.get("canonical_frame") or {}).get("operators", []))
    operator_refs, missing_operators = [], []
    for operator in operators:
        matches = [
            item
            for item in semantic_index.get(operator, [])
            if item.get("entry_kind")
            in {"primitive_operator", "operator_contract", "process_template"}
        ]
        if len(matches) == 1:
            operator_refs.append(matches[0]["entry_id"])
        else:
            missing_operators.append(operator)

    role_referents = {
        name: _role_referent(role, world_revision)
        for name, role in (analysis.get("role_bindings") or {}).items()
        if isinstance(role, dict)
    }
    event_refs = [f"dictionary_event_{index}" for index in range(len(operators))]
    attachments = []
    for modifier in (analysis.get("modifier_contract") or {}).get("modifiers", []):
        event_index = modifier.get("event_index")
        scope = modifier.get("scope", "event")
        attachments.append(
            {
                "modifier_ref": modifier.get("modifier_id"),
                "dimension": modifier.get("dimension"),
                "value": modifier.get("value"),
                "scope": scope,
                "target_event_ref": (
                    event_refs[event_index]
                    if isinstance(event_index, int) and 0 <= event_index < len(event_refs)
                    else None
                ),
                "candidate_only": True,
            }
        )
    scope_graph = build_scope_graph(
        event_refs,
        attachments,
        (analysis.get("discourse_event_graph") or {}).get("edges", []),
    )
    surface_groups = _resolve_surface_groups_from_analysis(
        scan_surface_candidate_groups(normalized_text, payload=dictionary), analysis
    )
    unresolved_polysemy = [
        item
        for item in surface_groups
        if len(set(item.get("candidate_entry_refs") or [])) > 1
        and not item.get("selected_entry_ref")
    ]
    candidate = {
        "candidate_id": _candidate_id(operator_refs, role_referents),
        "operator_refs": operator_refs,
        "role_referents": role_referents,
        "scope_graph_ref": scope_graph["scope_graph_id"],
        "admissible": (
            not missing_operators
            and not unresolved_polysemy
            and scope_graph["scope_complete"]
        ),
        "candidate_only": True,
        "runtime_fact_committed": False,
    }
    lattice = build_interpretation_lattice(
        source_ref="sha256:" + hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
        candidate_graphs=[candidate] if candidate["admissible"] else [],
        world_revision=world_revision,
    )
    return {
        "schema_version": "1.0.0",
        "projection_kind": "MachineDictionaryProjection",
        "mode": "shadow_equivalence_migration",
        "dictionary_ref": dictionary.get("dictionary_id"),
        "operator_refs": operator_refs,
        "missing_operator_semantics": missing_operators,
        "role_referents": role_referents,
        "scope_graph": scope_graph,
        "surface_candidate_groups": surface_groups,
        "unresolved_polysemy_count": len(unresolved_polysemy),
        "interpretation_lattice": lattice,
        "can_control_execution": False,
        "downstream_surface_reparse_allowed": False,
        "runtime_fact_committed": False,
    }


__all__ = ["project_analysis_to_machine_dictionary"]
