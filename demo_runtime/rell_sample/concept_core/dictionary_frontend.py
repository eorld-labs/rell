from __future__ import annotations

import hashlib
import json
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


def _candidate_id(
    operator_refs: list[str],
    role_referents: dict[str, Any],
    speech_act_ref: str | None,
    query_contract_ref: str | None,
) -> str:
    seed = repr(
        (
            operator_refs,
            sorted(role_referents),
            speech_act_ref,
            query_contract_ref,
        )
    )
    return "dictionary_candidate_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _semantic_index(dictionary: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for entry in dictionary.get("entries", []):
        result.setdefault(str(entry.get("semantic_value")), []).append(entry)
    return result


def _dictionary_modifier_ref(
    modifier: dict[str, Any], semantic_index: dict[str, list[dict[str, Any]]]
) -> str | None:
    declared_ref = modifier.get("dictionary_entry_ref")
    if declared_ref and any(
        item.get("entry_id") == declared_ref
        for entries in semantic_index.values()
        for item in entries
    ):
        return str(declared_ref)
    matches = [
        item
        for item in semantic_index.get(str(modifier.get("value")), [])
        if item.get("entry_kind") == "modifier"
        and item.get("modifier_dimension") == modifier.get("dimension")
    ]
    return matches[0].get("entry_id") if len(matches) == 1 else None


def _semantic_role_projection(role: dict[str, Any]) -> dict[str, Any]:
    result = {
        key: deepcopy(role.get(key))
        for key in (
            "role",
            "concept_id",
            "entity_ref",
            "value_ref",
            "entity_type",
            "reference",
            "compatible_kinds",
            "functional_affordances",
            "relation_predicate",
            "relation_target_role",
            "spatial_relation",
            "spatial_relation_basis",
            "quantity",
            "classifier",
            "selection_quantifier",
            "constraints",
        )
        if role.get(key) is not None
    }
    return result


def _semantic_event_projection(
    event: dict[str, Any],
    *,
    index: int,
    operator_refs: list[str],
    semantic_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    operator = event.get("operator")
    operator_ref = next(
        (
            ref
            for ref in operator_refs
            if any(
                entry.get("entry_id") == ref
                and entry.get("semantic_value") == operator
                for entry in semantic_index.get(str(operator), [])
            )
        ),
        None,
    )
    return {
        "event_ref": f"dictionary_event_{index}",
        "operator": operator,
        "operator_ref": operator_ref,
        "concept_id": event.get("concept_id"),
        "event_origin": event.get("source"),
        "modifiers": [
            {
                "dictionary_entry_ref": _dictionary_modifier_ref(
                    modifier, semantic_index
                ),
                **{
                    key: deepcopy(modifier.get(key))
                    for key in (
                        "dimension",
                        "value",
                        "scope",
                        "event_index",
                        "basis",
                    )
                },
                "candidate_only": True,
                "runtime_fact_committed": False,
                "direct_execution_allowed": False,
            }
            for modifier in event.get("modifiers", [])
        ],
        "candidate_only": True,
        "runtime_fact_committed": False,
    }


def _grounding_projection(frame: dict[str, Any]) -> dict[str, Any]:
    grounding = frame.get("grounded_intent_frame") or {}
    return {
        "world_revision": grounding.get("world_revision"),
        "roles": {
            role: {
                "status": item.get("status"),
                "world_revision": item.get("world_revision"),
                "observation_evidence_set_id": item.get(
                    "observation_evidence_set_id"
                ),
                "binding": {
                    key: deepcopy((item.get("binding") or {}).get(key))
                    for key in (
                        "entity_ref",
                        "binding_basis",
                        "evidence_strength",
                    )
                    if (item.get("binding") or {}).get(key) is not None
                },
                "candidate_bindings": [
                    {
                        key: deepcopy(candidate.get(key))
                        for key in (
                            "entity_ref",
                            "binding_basis",
                            "evidence_strength",
                        )
                        if candidate.get(key) is not None
                    }
                    for candidate in item.get("candidate_bindings", [])
                ],
            }
            for role, item in (grounding.get("roles") or {}).items()
            if isinstance(item, dict)
        },
        "candidate_only": True,
        "runtime_fact_committed": False,
    }


def _process_resolution_projection(frame: dict[str, Any]) -> dict[str, Any]:
    resolution = frame.get("process_template_resolution") or {}
    return {
        "status": resolution.get("status"),
        "template_id": resolution.get("template_id"),
        "goal_fact": resolution.get("goal_fact"),
        "bindings": {
            role: {
                key: deepcopy(binding.get(key))
                for key in (
                    "value_ref",
                    "value_type",
                    "explicit",
                    "evidence",
                    "evidence_strength",
                    "evidence_sources",
                    "matched_semantic_constraints",
                    "observation_world_revision",
                )
                if binding.get(key) is not None
            }
            for role, binding in (resolution.get("bindings") or {}).items()
            if isinstance(binding, dict)
        },
        "candidate_only": True,
        "runtime_fact_committed": False,
        "direct_execution_allowed": False,
    }


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
    entry_index = dictionary_index()
    roles = analysis.get("role_bindings") or {}
    modifiers = (analysis.get("modifier_contract") or {}).get("modifiers", [])
    spatial_values = {
        role.get("spatial_relation") or role.get("relation_predicate")
        for role in roles.values()
        if isinstance(role, dict)
    }
    modifier_values = {item.get("value") for item in modifiers}
    modifier_pairs = {
        (item.get("dimension"), item.get("value")) for item in modifiers
    }
    speech_act = analysis.get("speech_act") or (
        analysis.get("canonical_frame") or {}
    ).get("speech_act")
    query_type = analysis.get("query_type") or (
        analysis.get("canonical_frame") or {}
    ).get("query_type")
    correction_active = bool(
        (analysis.get("discourse_roles") or {}).get("task_correction")
    )
    operators = set(
        (analysis.get("canonical_frame") or {}).get("operators", [])
    )
    resolved = []
    for group in groups:
        item = deepcopy(group)
        item["selected_entry_ref"] = None
        item["selected_entry_refs"] = []
        item["status"] = "awaiting_typed_composition"
        candidates = set(item.get("candidate_entry_refs") or [])
        selected_refs: set[str] = set()
        for ref in candidates:
            entry = entry_index.get(ref) or {}
            if (
                entry.get("entry_kind") == "speech_act"
                and entry.get("semantic_value") == speech_act
            ):
                selected_refs.add(ref)
            if (
                entry.get("entry_kind") == "query_contract"
                and entry.get("semantic_value") == query_type
            ):
                selected_refs.add(ref)
            if (
                entry.get("entry_kind")
                in {
                    "primitive_operator",
                    "operator_contract",
                    "process_template",
                    "domain_pack_entry",
                }
                and entry.get("semantic_value") in operators
            ):
                selected_refs.add(ref)
            if entry.get("entry_kind") == "modifier" and (
                entry.get("modifier_dimension"), entry.get("modifier_value")
            ) in modifier_pairs:
                selected_refs.add(ref)
            if correction_active and ref in {
                "speech_act.correct",
                "communication.correct_semantics",
            }:
                selected_refs.add(ref)
        if "predicate.supported_by" in candidates and spatial_values.intersection(
            {"on_support_surface", "supported_by"}
        ):
            selected_refs.add("predicate.supported_by")
        elif "predicate.supported_by" in candidates and query_type == "support_inventory":
            selected_refs.add("predicate.supported_by")
        elif "modifier.aspect_attainment" in candidates and "attainment" in modifier_values:
            selected_refs.add("modifier.aspect_attainment")
        elif "modifier.direction_upward" in candidates and "upward" in modifier_values:
            selected_refs.add("modifier.direction_upward")
        if selected_refs:
            ordered_refs = sorted(selected_refs)
            item.update(
                {
                    "status": (
                        "resolved_compositional_bundle"
                        if len(ordered_refs) > 1
                        else "resolved_from_composed_semantics"
                    ),
                    "selected_entry_ref": (
                        ordered_refs[0] if len(ordered_refs) == 1 else None
                    ),
                    "selected_entry_refs": ordered_refs,
                    "resolution_basis": "existing_typed_composed_semantics",
                }
            )
        resolved.append(item)
    return resolved


def project_analysis_to_machine_dictionary(
    normalized_text: str,
    analysis: dict[str, Any],
    *,
    world_revision: int,
    _include_event_frames: bool = True,
) -> dict[str, Any]:
    dictionary = load_machine_dictionary()
    semantic_index = _semantic_index(dictionary)
    operators = list((analysis.get("canonical_frame") or {}).get("operators", []))
    speech_act = analysis.get("speech_act") or (
        analysis.get("canonical_frame") or {}
    ).get("speech_act")
    query_type = analysis.get("query_type") or (
        analysis.get("canonical_frame") or {}
    ).get("query_type")
    semantic_coverage_gaps = []
    speech_act_matches = [
        item
        for item in semantic_index.get(str(speech_act), [])
        if item.get("entry_kind") == "speech_act"
    ]
    query_matches = [
        item
        for item in semantic_index.get(str(query_type), [])
        if item.get("entry_kind") == "query_contract"
    ]
    if speech_act and speech_act != "unknown" and len(speech_act_matches) != 1:
        semantic_coverage_gaps.append("speech_act_semantics_not_dictionary_grounded")
    if query_type and len(query_matches) != 1:
        semantic_coverage_gaps.append("query_semantics_not_dictionary_grounded")
    if speech_act == "unknown":
        semantic_coverage_gaps.append("speech_act_not_resolved")
    if speech_act == "task_request" and not operators and not analysis.get("event_frames"):
        semantic_coverage_gaps.append("event_operator_not_dictionary_grounded")
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
    if not event_refs and analysis.get("reported_event_candidates"):
        event_refs = [
            f"dictionary_reported_event_{index}"
            for index, _ in enumerate(
                analysis.get("reported_event_candidates", [])
            )
        ]
    attachments = []
    for modifier in (analysis.get("modifier_contract") or {}).get("modifiers", []):
        event_index = modifier.get("event_index")
        scope = modifier.get("scope", "event")
        target_event_ref = (
            event_refs[event_index]
            if isinstance(event_index, int) and 0 <= event_index < len(event_refs)
            else None
        )
        if (
            target_event_ref is None
            and not operators
            and scope == "event"
            and len(analysis.get("reported_event_candidates", [])) == 1
        ):
            modifier_span = modifier.get("span") or []
            reported = analysis.get("reported_event_candidates", [])[0]
            reported_span = [reported.get("start"), reported.get("end")]
            if (
                len(modifier_span) == 2
                and all(isinstance(value, int) for value in modifier_span)
                and all(isinstance(value, int) for value in reported_span)
                and modifier_span[0] < reported_span[1]
                and reported_span[0] < modifier_span[1]
            ):
                target_event_ref = event_refs[0]
        attachments.append(
            {
                "modifier_ref": _dictionary_modifier_ref(
                    modifier, semantic_index
                )
                or modifier.get("modifier_id"),
                "dimension": modifier.get("dimension"),
                "value": modifier.get("value"),
                "scope": scope,
                "target_event_ref": target_event_ref,
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
        and not (
            item.get("selected_entry_ref")
            or item.get("selected_entry_refs")
        )
    ]
    speech_act_ref = (
        speech_act_matches[0]["entry_id"]
        if len(speech_act_matches) == 1
        else None
    )
    query_contract_ref = (
        query_matches[0]["entry_id"] if len(query_matches) == 1 else None
    )
    candidate = {
        "candidate_id": _candidate_id(
            operator_refs,
            role_referents,
            speech_act_ref,
            query_contract_ref,
        ),
        "operator_refs": operator_refs,
        "speech_act_ref": speech_act_ref,
        "query_contract_ref": query_contract_ref,
        "role_referents": role_referents,
        "scope_graph_ref": scope_graph["scope_graph_id"],
        "admissible": (
            not missing_operators
            and not semantic_coverage_gaps
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
    event_frame_projections = []
    if _include_event_frames:
        event_frame_projections = [
            project_analysis_to_machine_dictionary(
                str(frame.get("normalized_utterance") or frame.get("utterance") or ""),
                frame,
                world_revision=world_revision,
                _include_event_frames=False,
            )
            for frame in analysis.get("event_frames", [])
        ]
    semantic_roles = {
        name: _semantic_role_projection(role)
        for name, role in (
            (analysis.get("semantic_constraint_frame") or {}).get("roles") or {}
        ).items()
        if isinstance(role, dict)
    }
    semantic_events = [
        _semantic_event_projection(
            event,
            index=index,
            operator_refs=operator_refs,
            semantic_index=semantic_index,
        )
        for index, event in enumerate(analysis.get("event_candidates", []))
    ]
    semantic_payload = {
        "speech_act": speech_act,
        "query_type": query_type,
        "communication_contracts": {
            "speech_act_ref": speech_act_ref,
            "query_contract_ref": query_contract_ref,
        },
        "canonical_frame": {
            "operators": list(operators),
            "goal_relation": (analysis.get("canonical_frame") or {}).get(
                "goal_relation"
            ),
            "destination_binding_policy": (
                analysis.get("canonical_frame") or {}
            ).get("destination_binding_policy"),
            "speech_act": speech_act,
            "query_type": query_type,
        },
        "role_bindings": {
            name: _semantic_role_projection(role)
            for name, role in (analysis.get("role_bindings") or {}).items()
            if isinstance(role, dict)
        },
        "semantic_constraint_frame": {
            "schema_version": (
                analysis.get("semantic_constraint_frame") or {}
            ).get("schema_version", "1.0.0"),
            "roles": semantic_roles,
            "attribute_predicates": deepcopy(
                (analysis.get("semantic_constraint_frame") or {}).get(
                    "attribute_predicates", []
                )
            ),
            "unresolved_surfaces": deepcopy(
                (analysis.get("semantic_constraint_frame") or {}).get(
                    "unresolved_surfaces", []
                )
            ),
            "evidence_boundary": deepcopy(
                (analysis.get("semantic_constraint_frame") or {}).get(
                    "evidence_boundary", {}
                )
            ),
        },
        "grounded_intent_frame": _grounding_projection(analysis),
        "process_template_resolution": _process_resolution_projection(analysis),
        "discourse_roles": {
            name: {
                key: deepcopy(role.get(key))
                for key in (
                    "reference",
                    "relation",
                    "physical_state_change_committed",
                    "subject_role",
                    "object_role",
                    "executor_retention",
                    "task_correction",
                )
                if role.get(key) is not None
            }
            for name, role in (analysis.get("discourse_roles") or {}).items()
            if isinstance(role, dict)
        },
        "event_candidates": semantic_events,
        "reported_event_candidates": [
            {
                key: deepcopy(item.get(key))
                for key in (
                    "event_type",
                    "operator",
                    "candidate_postcondition",
                    "evidence_source",
                    "physical_state_change_committed",
                )
                if item.get(key) is not None
            }
            for item in analysis.get("reported_event_candidates", [])
        ],
        "historical_event_constraints": [
            {
                key: deepcopy(item.get(key))
                for key in (
                    "operator",
                    "temporal_scope",
                    "relation",
                    "head_role",
                    "actor_reference",
                    "theme",
                )
                if item.get(key) is not None
            }
            for item in analysis.get("historical_event_constraints", [])
        ],
        "event_frames": [
            {
                **deepcopy(item.get("semantic_payload") or {}),
                "frame_ref": str(
                    (analysis.get("event_frames", [])[index] or {}).get(
                        "frame_id"
                    )
                    or f"dictionary_frame_{index}"
                ),
                "incoming_discourse_relation": (
                    analysis.get("event_frames", [])[index] or {}
                ).get("incoming_discourse_relation"),
                "discourse_polarity": (
                    analysis.get("event_frames", [])[index] or {}
                ).get("discourse_polarity", "asserted"),
            }
            for index, item in enumerate(event_frame_projections)
        ],
        "discourse_event_graph": {
            "edges": deepcopy(scope_graph.get("discourse_edges") or [])
        },
        "modifier_contract": {
            "contract_id": (analysis.get("modifier_contract") or {}).get(
                "contract_id"
            ),
            "modifiers": [
                {
                    "dictionary_entry_ref": _dictionary_modifier_ref(
                        modifier, semantic_index
                    ),
                    **{
                        key: deepcopy(modifier.get(key))
                        for key in (
                            "dimension",
                            "value",
                            "scope",
                            "event_index",
                            "basis",
                            "runtime_fact_committed",
                            "direct_execution_allowed",
                        )
                    },
                }
                for modifier in (
                    analysis.get("modifier_contract") or {}
                ).get("modifiers", [])
            ],
            "conflicts": deepcopy(
                (analysis.get("modifier_contract") or {}).get("conflicts", [])
            ),
            "inquiry_contract": deepcopy(
                (analysis.get("modifier_contract") or {}).get(
                    "inquiry_contract"
                )
            ),
            "execution_constraints": deepcopy(
                (analysis.get("modifier_contract") or {}).get(
                    "execution_constraints", {}
                )
            ),
            "evidence_boundary": deepcopy(
                (analysis.get("modifier_contract") or {}).get(
                    "evidence_boundary", {}
                )
            ),
        },
        "reference_resolution": {
            key: deepcopy(
                (analysis.get("reference_resolution") or {}).get(key)
            )
            for key in (
                "resolution_id",
                "resolved_references",
                "unresolved",
                "inquiry_contracts",
                "salience_projection",
                "evidence_boundary",
            )
        },
        "rule_evaluation": deepcopy(analysis.get("rule_evaluation") or {}),
        "unresolved_slots": list(analysis.get("unresolved_slots") or []),
        "recovery_context_projection": deepcopy(
            analysis.get("recovery_context_projection")
        ),
        "candidate_only": True,
        "runtime_fact_committed": False,
    }
    result = {
        "schema_version": "1.0.0",
        "projection_kind": "MachineDictionaryProjection",
        "mode": "shadow_equivalence_migration",
        "world_revision": world_revision,
        "dictionary_ref": dictionary.get("dictionary_id"),
        "operator_refs": operator_refs,
        "operator_semantics": operators,
        "speech_act": speech_act,
        "speech_act_ref": speech_act_ref,
        "query_type": query_type,
        "query_contract_ref": query_contract_ref,
        "semantic_coverage_gaps": semantic_coverage_gaps,
        "missing_operator_semantics": missing_operators,
        "goal_relation": (analysis.get("canonical_frame") or {}).get(
            "goal_relation"
        ),
        "unresolved_variables": list(analysis.get("unresolved_slots") or []),
        "role_referents": role_referents,
        "reference_referents": deepcopy(
            (analysis.get("reference_resolution") or {}).get(
                "referent_expressions", []
            )
        ),
        "recovery_context_projection": deepcopy(
            analysis.get("recovery_context_projection")
        ),
        "scope_graph": scope_graph,
        "surface_candidate_groups": surface_groups,
        "unresolved_polysemy_count": len(unresolved_polysemy),
        "interpretation_lattice": lattice,
        "event_frame_projections": event_frame_projections,
        "semantic_payload": semantic_payload,
        "all_event_frames_admissible": all(
            (item.get("interpretation_lattice") or {}).get("status") == "resolved"
            and not item.get("unresolved_variables")
            and all(
                not reference.get("requires_confirmation")
                for reference in item.get("reference_referents", [])
            )
            for item in event_frame_projections
        ),
        "can_control_execution": False,
        "downstream_surface_reparse_allowed": False,
        "runtime_fact_committed": False,
    }
    projection_payload = json.dumps(
        result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    result["projection_id"] = "dictionary_projection_" + hashlib.sha1(
        projection_payload.encode("utf-8")
    ).hexdigest()[:16]
    return result


_CONTEXTUAL_COMMUNICATION_MAP = {
    "confirmation": ("speech_act.confirm", "communication.confirm_pending"),
    "rejection": ("speech_act.reject", "communication.reject_pending"),
    "correction": ("speech_act.correct", "communication.correct_semantics"),
    "clarification_answer": (
        "speech_act.answer_clarification",
        "communication.answer_inquiry",
    ),
    "information_report": ("speech_act.inform", None),
}


def project_contextual_communication_signal(
    signal_kind: str,
    *,
    context_ref: str | None,
    world_revision: int,
    typed_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    speech_act_ref, contract_ref = _CONTEXTUAL_COMMUNICATION_MAP.get(
        signal_kind, (None, None)
    )
    index = dictionary_index()
    missing = []
    if not speech_act_ref or speech_act_ref not in index:
        missing.append("speech_act_entry")
    if contract_ref and contract_ref not in index:
        missing.append("communicative_contract_entry")
    if signal_kind in {
        "confirmation",
        "rejection",
        "correction",
        "clarification_answer",
    } and not context_ref:
        missing.append("dialogue_context_ref")
    return {
        "schema_version": "1.0.0",
        "projection_kind": "CommunicativeDictionaryProjection",
        "mode": "shadow_equivalence_migration",
        "signal_kind": signal_kind,
        "speech_act_ref": speech_act_ref,
        "communicative_contract_ref": contract_ref,
        "context_ref": context_ref,
        "typed_payload": deepcopy(typed_payload or {}),
        "world_revision": world_revision,
        "status": "admissible" if not missing else "blocked",
        "missing_semantics_or_context": missing,
        "can_control_execution": False,
        "can_commit_runtime_fact": False,
        "requires_reentry_to_current_grounding": signal_kind
        in {"correction", "clarification_answer"},
        "surface_text_forwarded_downstream": False,
        "runtime_fact_committed": False,
    }


__all__ = [
    "project_analysis_to_machine_dictionary",
    "project_contextual_communication_signal",
]
