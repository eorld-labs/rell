from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from .rcir_contracts import build_grounding_clarification_contract
from .rcir_primitives import make_evidence_envelope


RCIR_SCHEMA_VERSION = "1.0.0"
EVIDENCE_PRECEDENCE = (
    "current_physically_verified_relation",
    "current_multimodal_observation",
    "explicit_current_language_constraint",
    "active_task_role_binding",
    "recent_verified_episode_capsule",
    "trusted_concept_or_experience",
    "unconstrained_category_candidate",
)
FORBIDDEN_DOWNSTREAM_TEXT_KEYS = {
    "utterance",
    "normalized_utterance",
    "canonical_utterance",
    "source_utterance",
    "surface",
    "matched_surface",
    "current_name_surface",
    "label",
    "question",
}

ARCHITECTURE_INVARIANTS = (
    "language_does_not_commit_physical_fact",
    "perception_candidate_is_not_runtime_fact",
    "downstream_does_not_reparse_surface_text",
    "current_verified_relation_precedes_history_and_category",
    "every_recovery_reenters_current_fact_pruning",
    "qualified_evidence_required_for_execution_fact",
    "versioned_dependency_invalidation_required",
    "shared_event_predicate_evidence_readback",
    "no_secondary_fact_or_control_source",
)


def _stable_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stable_id(prefix: str, value: Any, length: int = 16) -> str:
    return f"{prefix}_{_stable_digest(value)[:length]}"


def _evidence_class(source: str | None) -> tuple[str, int]:
    if source == "runtime_verified":
        return "current_physically_verified_relation", 700
    if source == "runtime_snapshot":
        return "current_runtime_snapshot", 650
    if source in {"sensor_verified", "multimodal_verified"}:
        return "current_multimodal_observation", 600
    return "unclassified_current_evidence", 100


def _fact_evidence_envelope(
    source: str,
    *,
    fact_id: str,
    fact_revision: int,
    world_revision: int,
    strength: int,
) -> dict[str, Any]:
    if source == "runtime_verified":
        source_type = "p016_physical_verification"
        epistemic_status = "physically_verified"
        physical_verification = True
        verifier = "P016"
        independent_channels = 2
    elif source == "runtime_snapshot":
        source_type = "runtime_snapshot"
        epistemic_status = "corroborated"
        physical_verification = False
        verifier = None
        independent_channels = 1
    elif source in {"sensor_verified", "multimodal_verified"}:
        source_type = "multimodal_observation"
        epistemic_status = "corroborated"
        physical_verification = False
        verifier = None
        independent_channels = 2
    elif source == "human_report":
        source_type = "human_report"
        epistemic_status = "candidate"
        physical_verification = False
        verifier = None
        independent_channels = 0
    elif source in {"perception_candidate", "sensor_candidate"}:
        source_type = "perception_candidate"
        epistemic_status = "candidate"
        physical_verification = False
        verifier = None
        independent_channels = 1
    else:
        source_type = "diagnostic_signal"
        epistemic_status = "candidate"
        physical_verification = False
        verifier = None
        independent_channels = 0
    return make_evidence_envelope(
        source_type,
        epistemic_status=epistemic_status,
        world_revision=fact_revision,
        supports_refs=[fact_id],
        strength=strength,
        independent_channels=independent_channels,
        physical_verification=physical_verification,
        current_world_bound=fact_revision == world_revision,
        verifier=verifier,
        depends_on_refs=[fact_id],
        payload={"legacy_source_adapter": source},
    )


def build_world_fact_ledger(
    current_facts: list[dict[str, Any]],
    *,
    world_revision: int,
) -> dict[str, Any]:
    """Compile versioned facts and evidence without display names or language."""
    facts = []
    evidence_by_id: dict[str, dict[str, Any]] = {}
    evidence_adapter_audit: dict[str, dict[str, Any]] = {}
    stale_fact_ids = []
    ordered = sorted(
        current_facts,
        key=lambda item: (
            str(item.get("predicate") or ""),
            str(item.get("subject") or ""),
            str(item.get("object") or ""),
        ),
    )
    for raw in ordered:
        fact_revision = int(raw.get("world_revision", world_revision))
        source = str(raw.get("evidence") or "unknown")
        evidence_class, strength = _evidence_class(source)
        fact_seed = {
            "predicate": raw.get("predicate"),
            "subject": raw.get("subject"),
            "object": raw.get("object"),
            "world_revision": fact_revision,
        }
        fact_id = _stable_id("fact", fact_seed)
        envelope = _fact_evidence_envelope(
            source,
            fact_id=fact_id,
            fact_revision=fact_revision,
            world_revision=world_revision,
            strength=strength,
        )
        evidence_id = envelope["envelope_id"]
        evidence_by_id.setdefault(
            evidence_id,
            envelope,
        )
        evidence_adapter_audit.setdefault(
            evidence_id,
            {
                "envelope_ref": evidence_id,
                "evidence_class": evidence_class,
                "legacy_source_type": source,
            },
        )
        current_eligible = bool(
            fact_revision == world_revision and envelope["fact_commit_eligible"]
        )
        record = {
            "fact_id": fact_id,
            **fact_seed,
            "status": (
                "established"
                if current_eligible
                else "stale"
                if fact_revision != world_revision
                else "candidate_missing_qualified_evidence"
            ),
            "evidence_ref": evidence_id,
            "current_world_usable": current_eligible,
        }
        facts.append(record)
        if fact_revision != world_revision:
            stale_fact_ids.append(fact_id)
    ledger = {
        "schema_version": RCIR_SCHEMA_VERSION,
        "ir_kind": "world_fact_ledger",
        "world_revision": world_revision,
        "facts": facts,
        "evidence": sorted(
            evidence_by_id.values(), key=lambda item: item["envelope_id"]
        ),
        "evidence_source_adapter_audit": sorted(
            evidence_adapter_audit.values(), key=lambda item: item["envelope_ref"]
        ),
        "authoritative_current_fact_ids": [
            item["fact_id"] for item in facts if item["current_world_usable"]
        ],
        "stale_fact_ids": stale_fact_ids,
        "evidence_precedence": list(EVIDENCE_PRECEDENCE),
        "retention_contract": {
            "display_names_included": False,
            "raw_language_included": False,
            "trajectory_included": False,
        },
    }
    ledger["ledger_id"] = _stable_id("ledger", ledger)
    return ledger


def _constraint_view(constraint: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(constraint.get(key))
        for key in (
            "predicate_type",
            "concept_id",
            "observation_field",
            "value",
            "accepted_observed_values",
            "applies_to_concepts",
        )
        if constraint.get(key) is not None
    }


def _role_view(role_name: str, role: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": role_name,
        "concept_id": role.get("concept_id"),
        "entity_type": role.get("entity_type"),
        "deictic_reference": role.get("reference"),
        "compatible_kinds": deepcopy(role.get("compatible_kinds", [])),
        "functional_affordances": deepcopy(
            role.get("functional_affordances", [])
        ),
        "relation_predicate": role.get("relation_predicate"),
        "relation_target_role": role.get("relation_target_role"),
        "constraints": [
            _constraint_view(item) for item in role.get("constraints", [])
        ],
    }


def _role_token(role: str) -> str:
    return f"$role:{role}"


def _goal_facts(
    goal_relation: str | None,
    operators: list[str],
    roles: dict[str, dict[str, Any]],
    discourse_roles: dict[str, dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    theme = _role_token("theme")
    destination = _role_token("destination")
    recipient = _role_token("recipient")
    facts: list[dict[str, Any]] = []
    relation = goal_relation
    if goal_relation == "object_supported_at_destination":
        facts.append({"predicate": "supported_by", "subject": theme, "object": destination})
    elif goal_relation == "object_received_by_recipient":
        facts.append({"predicate": "received_by", "subject": theme, "object": recipient})
    elif goal_relation == "object_in_gripper":
        facts.append({"predicate": "held_by", "subject": theme, "object": "executor"})
    elif goal_relation == "object_at_target_region":
        facts.append({"predicate": "inside_region", "subject": theme, "object": _role_token("target_region")})
    elif goal_relation == "filled_container_supported_at_destination":
        facts.extend([
            {"predicate": "contains_liquid", "subject": theme, "object": "liquid"},
            {"predicate": "supported_by", "subject": theme, "object": destination},
        ])
    elif goal_relation == "human_received_filled_container":
        facts.extend([
            {"predicate": "contains_liquid", "subject": theme, "object": "liquid"},
            {"predicate": "received_by", "subject": theme, "object": recipient},
        ])
    elif goal_relation == "container_filled" or "fill_container" in operators:
        facts.append({"predicate": "contains_liquid", "subject": theme, "object": "liquid"})
        recipient_requested = bool(
            roles.get("recipient")
            or (discourse_roles.get("recipient") or {}).get("reference")
        )
        if recipient_requested:
            relation = "human_received_filled_container"
            facts.append({"predicate": "received_by", "subject": theme, "object": recipient})
        elif roles.get("destination"):
            relation = "filled_container_supported_at_destination"
            facts.append({"predicate": "supported_by", "subject": theme, "object": destination})
    return relation, facts


def build_situated_event_graph(
    utterance: str,
    language_analysis: dict[str, Any],
    *,
    world_revision: int,
    interaction_turn: int,
) -> dict[str, Any]:
    """Compile one authoritative turn graph without retaining surface text."""
    semantic_frame = language_analysis.get("semantic_constraint_frame") or {}
    roles = {
        role_name: _role_view(role_name, role)
        for role_name, role in (semantic_frame.get("roles") or {}).items()
        if isinstance(role, dict)
    }
    discourse_roles = {
        role_name: {
            "role": role_name,
            "deictic_reference": role.get("reference"),
            "relation": role.get("relation"),
            "physical_fact_committed": bool(
                role.get("physical_state_change_committed", False)
            ),
        }
        for role_name, role in (language_analysis.get("discourse_roles") or {}).items()
        if isinstance(role, dict)
    }
    if "recipient" not in roles and discourse_roles.get("recipient"):
        roles["recipient"] = {
            "role": "recipient",
            "concept_id": None,
            "entity_type": "human_recipient",
            "deictic_reference": discourse_roles["recipient"].get(
                "deictic_reference"
            ),
            "compatible_kinds": ["human_recipient"],
            "functional_affordances": [],
            "relation_predicate": None,
            "relation_target_role": None,
            "constraints": [],
        }
    operators = list(
        (language_analysis.get("canonical_frame") or {}).get("operators", [])
    )
    events = [
        {
            "event_id": _stable_id(
                "event",
                {
                    "turn": interaction_turn,
                    "index": index,
                    "operator": item.get("operator"),
                },
            ),
            "operator": item.get("operator"),
            "concept_id": item.get("concept_id"),
            "event_origin": item.get("source"),
            "temporal_scope": "requested_current_or_future",
            "physical_fact_committed": False,
        }
        for index, item in enumerate(language_analysis.get("event_candidates", []))
    ]
    reported_events = [
        {
            "event_id": _stable_id(
                "reported_event",
                {
                    "turn": interaction_turn,
                    "index": index,
                    "operator": item.get("operator"),
                },
            ),
            "event_type": item.get("event_type"),
            "operator": item.get("operator"),
            "candidate_postcondition": item.get("candidate_postcondition"),
            "evidence_class": "human_report",
            "physical_fact_committed": False,
        }
        for index, item in enumerate(
            language_analysis.get("reported_event_candidates", [])
        )
    ]
    historical_constraints = [
        {
            "operator": item.get("operator"),
            "temporal_scope": item.get("temporal_scope"),
            "relation": item.get("relation"),
            "head_role": item.get("head_role"),
            "actor_reference": item.get("actor_reference"),
            "physical_fact_committed": False,
        }
        for item in language_analysis.get("historical_event_constraints", [])
    ]
    goal_relation, goal_facts = _goal_facts(
        (language_analysis.get("canonical_frame") or {}).get("goal_relation"),
        operators,
        roles,
        discourse_roles,
    )
    event_scopes = [
        {
            "scope_id": frame.get("frame_id") or f"scope_{index}",
            "sequence_index": index,
            "operators": deepcopy(
                (frame.get("canonical_frame") or {}).get("operators", [])
            ),
            "goal_relation": (frame.get("canonical_frame") or {}).get(
                "goal_relation"
            ),
            "incoming_discourse_relation": frame.get(
                "incoming_discourse_relation"
            ),
            "discourse_polarity": frame.get("discourse_polarity", "asserted"),
        }
        for index, frame in enumerate(language_analysis.get("event_frames", []))
    ]
    source_ref = "sha256:" + hashlib.sha256(utterance.encode("utf-8")).hexdigest()
    graph = {
        "schema_version": RCIR_SCHEMA_VERSION,
        "ir_kind": "situated_event_graph",
        "world_revision": world_revision,
        "interaction_turn": interaction_turn,
        "source_language": {
            "utterance_ref": source_ref,
            "character_count": len(utterance),
            "raw_text_included": False,
        },
        "speech_act": language_analysis.get("speech_act"),
        "events": events,
        "reported_events": reported_events,
        "historical_event_constraints": historical_constraints,
        "event_scopes": event_scopes,
        "discourse_edges": deepcopy(
            (language_analysis.get("discourse_event_graph") or {}).get(
                "edges", []
            )
        ),
        "roles": roles,
        "discourse_roles": discourse_roles,
        "goal": {
            "goal_relation": goal_relation,
            "fact_candidates": goal_facts,
            "candidate_only": True,
        },
        "unresolved_variables": deepcopy(
            language_analysis.get("unresolved_slots", [])
        ),
        "authority": {
            "authoritative_for_turn": True,
            "downstream_surface_reparse_allowed": False,
            "language_commits_physical_facts": False,
        },
    }
    graph["graph_id"] = _stable_id("situated_graph", graph)
    return graph


def _binding_candidates(
    role_name: str,
    language_analysis: dict[str, Any],
    interaction_role_bindings: dict[str, Any],
    world_revision: int,
) -> list[dict[str, Any]]:
    candidates = []
    relational = (
        (language_analysis.get("context_projection") or {}).get(
            "relational_role_candidates", {}
        ).get(role_name, [])
    )
    if len(relational) == 1:
        item = relational[0]
        candidates.append({
            "entity_ref": item.get("entity_ref"),
            "basis": f"current_verified_relation:{item.get('relation')}",
            "strength": 700,
            "world_revision": item.get("world_revision"),
            "evidence_ref": None,
        })
    grounded = (
        (language_analysis.get("grounded_intent_frame") or {}).get("roles", {})
        .get(role_name, {})
    )
    binding = grounded.get("binding") or {}
    if grounded.get("status") == "resolved" and binding.get("entity_ref"):
        candidates.append({
            "entity_ref": binding.get("entity_ref"),
            "basis": binding.get("binding_basis")
            or "current_observation_grounding",
            "strength": int(binding.get("evidence_strength") or 500),
            "world_revision": grounded.get("world_revision"),
            "evidence_ref": grounded.get("observation_evidence_set_id"),
        })
    process_binding = (
        ((language_analysis.get("process_template_resolution") or {}).get("bindings") or {})
        .get(role_name, {})
    )
    if process_binding.get("value_ref"):
        candidates.append({
            "entity_ref": process_binding.get("value_ref"),
            "basis": process_binding.get("evidence")
            or "process_role_grounding",
            "strength": int(process_binding.get("evidence_strength") or 100),
            "world_revision": process_binding.get("observation_world_revision"),
            "evidence_ref": None,
        })
    semantic_role = (
        (language_analysis.get("semantic_constraint_frame") or {}).get("roles", {})
        .get(role_name, {})
    )
    deictic_ref = semantic_role.get("reference")
    if not deictic_ref:
        deictic_ref = (
            (language_analysis.get("discourse_roles") or {}).get(role_name, {})
            .get("reference")
        )
    resolved_deictic = interaction_role_bindings.get(deictic_ref)
    if resolved_deictic:
        candidates.append({
            "entity_ref": resolved_deictic,
            "basis": "current_deictic_interaction_role",
            "strength": 550,
            "world_revision": world_revision,
            "evidence_ref": None,
        })
    return [
        item for item in candidates
        if item.get("entity_ref")
        and item.get("world_revision") in {None, world_revision}
    ]


def _resolve_role_binding(
    role_name: str,
    language_analysis: dict[str, Any],
    interaction_role_bindings: dict[str, Any],
    world_revision: int,
) -> dict[str, Any]:
    candidates = _binding_candidates(
        role_name,
        language_analysis,
        interaction_role_bindings,
        world_revision,
    )
    if not candidates:
        return {"role": role_name, "status": "unresolved"}
    strongest = max(item["strength"] for item in candidates)
    strongest_candidates = [
        item for item in candidates if item["strength"] == strongest
    ]
    refs = {item["entity_ref"] for item in strongest_candidates}
    if len(refs) != 1:
        return {
            "role": role_name,
            "status": "ambiguous",
            "candidate_entity_refs": sorted(refs),
            "world_revision": world_revision,
        }
    selected = strongest_candidates[0]
    current_relation_refs = {
        item["entity_ref"]
        for item in candidates
        if str(item.get("basis") or "").startswith("current_verified_relation:")
        and item.get("strength") == 700
    }
    if len(current_relation_refs) == 1 and selected["entity_ref"] not in current_relation_refs:
        raise AssertionError(
            "current_verified_relation_must_precede_history_and_category"
        )
    return {
        "role": role_name,
        "status": "resolved",
        "entity_ref": selected["entity_ref"],
        "world_revision": world_revision,
        "evidence": {
            "basis": selected["basis"],
            "strength": selected["strength"],
            "evidence_ref": selected.get("evidence_ref"),
            "current_snapshot_revalidated": True,
            "precedence_assertion": (
                "current_verified_relation_precedes_history_and_category"
                if current_relation_refs
                else "evidence_precedence_applied"
            ),
        },
    }


def _ground_fact(
    fact: dict[str, Any], bindings: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    grounded = deepcopy(fact)
    for field in ("subject", "object"):
        value = grounded.get(field)
        if isinstance(value, str) and value.startswith("$role:"):
            role_name = value.split(":", 1)[1]
            binding = bindings.get(role_name) or {}
            if binding.get("status") == "resolved":
                grounded[field] = binding["entity_ref"]
    grounded["status"] = "goal_candidate"
    return grounded


def build_grounded_causal_graph(
    situated_graph: dict[str, Any],
    language_analysis: dict[str, Any],
    world_ledger: dict[str, Any],
    *,
    interaction_role_bindings: dict[str, Any],
) -> dict[str, Any]:
    world_revision = int(world_ledger["world_revision"])
    role_names = set((situated_graph.get("roles") or {}).keys())
    for fact in (situated_graph.get("goal") or {}).get("fact_candidates", []):
        for value in (fact.get("subject"), fact.get("object")):
            if isinstance(value, str) and value.startswith("$role:"):
                role_names.add(value.split(":", 1)[1])
    bindings = {
        role_name: _resolve_role_binding(
            role_name,
            language_analysis,
            interaction_role_bindings,
            world_revision,
        )
        for role_name in sorted(role_names)
    }
    grounded_goals = [
        _ground_fact(item, bindings)
        for item in (situated_graph.get("goal") or {}).get("fact_candidates", [])
    ]
    operators = [
        item.get("operator") for item in situated_graph.get("events", [])
        if item.get("operator")
    ]
    if (
        any(item.get("predicate") == "received_by" for item in grounded_goals)
        and "handover_object" not in operators
    ):
        operators.append("handover_object")
    nodes = [
        {
            "node_id": _stable_id(
                "causal_node",
                {"graph": situated_graph.get("graph_id"), "index": index, "operator": operator},
            ),
            "operator": operator,
            "sequence_index": index,
            "origin": (
                "language_declared_event"
                if index < len(situated_graph.get("events", []))
                else "goal_relation_completion"
            ),
            "status": "candidate_pending_current_fact_pruning",
            "verification_required": True,
            "candidate_only": True,
        }
        for index, operator in enumerate(operators)
    ]
    edges = [
        {
            "from": nodes[index - 1]["node_id"],
            "to": nodes[index]["node_id"],
            "relation": "ordered_before",
        }
        for index in range(1, len(nodes))
    ]
    current_fact_keys = {
        (item.get("predicate"), item.get("subject"), item.get("object")):
        item.get("fact_id")
        for item in world_ledger.get("facts", [])
        if item.get("current_world_usable")
    }
    satisfied_goal_fact_refs = [
        current_fact_keys[key]
        for item in grounded_goals
        for key in [(item.get("predicate"), item.get("subject"), item.get("object"))]
        if key in current_fact_keys
    ]
    unresolved_roles = [
        role_name for role_name, binding in bindings.items()
        if binding.get("status") != "resolved"
    ]
    clarification_contracts = {}
    grounded_roles = (
        (language_analysis.get("grounded_intent_frame") or {}).get("roles") or {}
    )
    for role_name in unresolved_roles:
        role_grounding = grounded_roles.get(role_name) or {}
        if role_grounding.get("status") != "ambiguous":
            continue
        clarification_contracts[role_name] = build_grounding_clarification_contract(
            role_name,
            role_grounding.get("candidate_bindings") or [],
            world_revision=world_revision,
            accumulated_constraints=[
                _constraint_view(item)
                for item in (
                    (role_grounding.get("semantic_role") or {}).get("constraints")
                    or []
                )
            ],
        )
    graph = {
        "schema_version": RCIR_SCHEMA_VERSION,
        "ir_kind": "grounded_causal_graph",
        "world_revision": world_revision,
        "situated_graph_ref": situated_graph.get("graph_id"),
        "world_ledger_ref": world_ledger.get("ledger_id"),
        "goal_relation": (situated_graph.get("goal") or {}).get("goal_relation"),
        "goal_facts": grounded_goals,
        "role_bindings": bindings,
        "nodes": nodes,
        "edges": edges,
        "satisfied_goal_fact_refs": satisfied_goal_fact_refs,
        "open_conditions": [
            {"kind": "unresolved_role", "role": role_name}
            for role_name in unresolved_roles
        ] + [
            {"kind": "language_constraint", "constraint": item}
            for item in situated_graph.get("unresolved_variables", [])
        ],
        "grounding_clarification_contracts": clarification_contracts,
        "binding_status": "grounded" if not unresolved_roles else "incomplete",
        "ready_for_orchestration": not unresolved_roles,
        "fact_authority_ref": world_ledger.get("ledger_id"),
        "control_gateway": "P018",
        "verification_gateway": "P016",
        "current_fact_pruning_required": True,
        "direct_execution_allowed": False,
        "runtime_fact_committed": False,
    }
    graph["graph_id"] = _stable_id("grounded_graph", graph)
    return graph


def compile_rcir_bundle(
    utterance: str,
    language_analysis: dict[str, Any],
    *,
    current_facts: list[dict[str, Any]],
    world_revision: int,
    interaction_turn: int,
    interaction_role_bindings: dict[str, Any],
) -> dict[str, Any]:
    ledger = build_world_fact_ledger(
        current_facts,
        world_revision=world_revision,
    )
    situated = build_situated_event_graph(
        utterance,
        language_analysis,
        world_revision=world_revision,
        interaction_turn=interaction_turn,
    )
    grounded = build_grounded_causal_graph(
        situated,
        language_analysis,
        ledger,
        interaction_role_bindings=interaction_role_bindings,
    )
    bundle = {
        "schema_version": RCIR_SCHEMA_VERSION,
        "ir_kind": "rell_cognitive_ir_bundle",
        "bundle_id": _stable_id(
            "rcir",
            {
                "situated_graph_ref": situated["graph_id"],
                "world_ledger_ref": ledger["ledger_id"],
                "grounded_graph_ref": grounded["graph_id"],
            },
        ),
        "world_revision": world_revision,
        "interaction_turn": interaction_turn,
        "situated_event_graph": situated,
        "world_fact_ledger": ledger,
        "grounded_causal_graph": grounded,
        "architecture_invariants": {
            "one_turn_one_authoritative_semantic_graph": True,
            "downstream_surface_reparse_allowed": False,
            "language_does_not_commit_physical_fact": True,
            "perception_candidate_is_not_runtime_fact": True,
            "downstream_does_not_reparse_surface_text": True,
            "current_verified_relation_precedes_history_and_category": True,
            "every_recovery_reenters_current_fact_pruning": True,
            "qualified_evidence_required_for_execution_fact": True,
            "versioned_dependency_invalidation_required": True,
            "shared_event_predicate_evidence_readback": True,
            "no_secondary_fact_or_control_source": True,
            "current_world_ledger_is_authoritative": True,
            "every_binding_has_evidence_and_world_revision": True,
            "current_fact_pruning_required_before_execution": True,
        },
    }
    assert_rcir_architecture_invariants(
        bundle,
        observation_evidence=language_analysis.get("observation_evidence"),
    )
    bundle["authority_digest"] = _stable_digest(bundle)
    validation = validate_rcir_bundle(bundle)
    if not validation["valid"]:
        raise ValueError("invalid_rcir_bundle:" + ",".join(validation["errors"]))
    return bundle


def _forbidden_key_paths(value: Any, path: str = "$") -> list[str]:
    violations = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_DOWNSTREAM_TEXT_KEYS:
                violations.append(child_path)
            violations.extend(_forbidden_key_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_forbidden_key_paths(child, f"{path}[{index}]"))
    return violations


def assert_no_surface_text_below_rcir_boundary(value: Any) -> None:
    violations = _forbidden_key_paths(value)
    if violations:
        raise AssertionError("surface_text_below_rcir_boundary:" + "|".join(violations))


def assert_perception_candidate_is_not_runtime_fact(
    observation_evidence: dict[str, Any], world_ledger: dict[str, Any]
) -> None:
    if observation_evidence.get("epistemic_only") is not True:
        raise AssertionError("observation_evidence_must_be_epistemic_only")
    if observation_evidence.get("changes_execution_state") is not False:
        raise AssertionError("observation_candidate_changed_execution_state")
    observation_ref = observation_evidence.get("evidence_set_id")
    authoritative_refs = {
        item.get("evidence_ref")
        for item in world_ledger.get("facts", [])
        if item.get("fact_id")
        in set(world_ledger.get("authoritative_current_fact_ids") or [])
    }
    if observation_ref and observation_ref in authoritative_refs:
        raise AssertionError("perception_candidate_committed_as_runtime_fact")


def assert_rcir_architecture_invariants(
    bundle: dict[str, Any],
    *,
    observation_evidence: dict[str, Any] | None = None,
) -> None:
    assert_no_surface_text_below_rcir_boundary(bundle)
    situated = bundle.get("situated_event_graph") or {}
    event_records = [
        *situated.get("events", []),
        *situated.get("reported_events", []),
        *situated.get("historical_event_constraints", []),
    ]
    if any(item.get("physical_fact_committed") is not False for item in event_records):
        raise AssertionError("language_event_committed_physical_fact")
    ledger = bundle.get("world_fact_ledger") or {}
    if observation_evidence is not None:
        assert_perception_candidate_is_not_runtime_fact(observation_evidence, ledger)
    grounded = bundle.get("grounded_causal_graph") or {}
    if grounded.get("current_fact_pruning_required") is not True:
        raise AssertionError("current_fact_pruning_boundary_missing")
    if any(
        item.get("status") != "candidate_pending_current_fact_pruning"
        for item in grounded.get("nodes", [])
    ):
        raise AssertionError("causal_node_bypassed_current_fact_pruning")
    declared = bundle.get("architecture_invariants") or {}
    missing = [name for name in ARCHITECTURE_INVARIANTS if declared.get(name) is not True]
    if missing:
        raise AssertionError("architecture_invariant_not_declared:" + "|".join(missing))


def validate_rcir_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    errors = []
    if bundle.get("schema_version") != RCIR_SCHEMA_VERSION:
        errors.append("schema_version_mismatch")
    if bundle.get("ir_kind") != "rell_cognitive_ir_bundle":
        errors.append("ir_kind_mismatch")
    revision = bundle.get("world_revision")
    for key in (
        "situated_event_graph",
        "world_fact_ledger",
        "grounded_causal_graph",
    ):
        if (bundle.get(key) or {}).get("world_revision") != revision:
            errors.append(f"world_revision_mismatch:{key}")
    violations = _forbidden_key_paths(bundle)
    if violations:
        errors.append("surface_text_leaked:" + "|".join(violations))
    situated = bundle.get("situated_event_graph") or {}
    if situated.get("source_language", {}).get("raw_text_included") is not False:
        errors.append("raw_language_retained")
    if situated.get("authority", {}).get("language_commits_physical_facts") is not False:
        errors.append("language_fact_boundary_missing")
    try:
        assert_rcir_architecture_invariants(bundle)
    except AssertionError as error:
        errors.append(str(error))
    for binding in (bundle.get("grounded_causal_graph") or {}).get(
        "role_bindings", {}
    ).values():
        if binding.get("status") == "resolved" and (
            binding.get("world_revision") != revision or not binding.get("evidence")
        ):
            errors.append(f"binding_evidence_missing:{binding.get('role')}")
    expected_digest = bundle.get("authority_digest")
    unsigned = deepcopy(bundle)
    unsigned.pop("authority_digest", None)
    if expected_digest != _stable_digest(unsigned):
        errors.append("authority_digest_mismatch")
    return {"valid": not errors, "errors": errors}


def compact_rcir_receipt(
    bundle: dict[str, Any], *, release_reason: str
) -> dict[str, Any]:
    validation = validate_rcir_bundle(bundle)
    if not validation["valid"]:
        raise ValueError("cannot_compact_invalid_rcir_bundle")
    return {
        "schema_version": RCIR_SCHEMA_VERSION,
        "bundle_id": bundle.get("bundle_id"),
        "authority_digest": bundle.get("authority_digest"),
        "world_revision": bundle.get("world_revision"),
        "interaction_turn": bundle.get("interaction_turn"),
        "situated_graph_ref": (
            bundle.get("situated_event_graph") or {}
        ).get("graph_id"),
        "grounded_graph_ref": (
            bundle.get("grounded_causal_graph") or {}
        ).get("graph_id"),
        "release_reason": release_reason,
        "raw_language_included": False,
        "candidate_plan_included": False,
        "trajectory_included": False,
    }


__all__ = [
    "ARCHITECTURE_INVARIANTS",
    "EVIDENCE_PRECEDENCE",
    "FORBIDDEN_DOWNSTREAM_TEXT_KEYS",
    "RCIR_SCHEMA_VERSION",
    "assert_no_surface_text_below_rcir_boundary",
    "assert_perception_candidate_is_not_runtime_fact",
    "assert_rcir_architecture_invariants",
    "build_grounded_causal_graph",
    "build_situated_event_graph",
    "build_world_fact_ledger",
    "compact_rcir_receipt",
    "compile_rcir_bundle",
    "validate_rcir_bundle",
]
