from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from .perceptual_grounding import observed_perceptual_attributes


DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "semantic_attribute_concepts.json"


def _normalize(text: str) -> str:
    return re.sub(r"[\s，。！？、,.!?；;：:]+", "", str(text or ""))


@lru_cache(maxsize=1)
def load_semantic_attribute_concepts() -> dict[str, Any]:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def _accepted_observed_values(concept: dict[str, Any], requested: str) -> list[str]:
    """Expand a requested attribute value to its declared semantic descendants."""
    parents = concept.get("value_parents") or {}
    accepted = {requested}
    for candidate in concept.get("values", {}):
        current = candidate
        visited = set()
        while current in parents and current not in visited:
            visited.add(current)
            current = parents[current]
            if current == requested:
                accepted.add(candidate)
                break
    return sorted(accepted)


def build_semantic_constraint_frame(
    utterance: str,
    language_analysis: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compose language into typed predicates without claiming an entity instance."""
    analysis = language_analysis or {}
    normalized = _normalize(utterance)
    roles: dict[str, dict[str, Any]] = {}
    for role_name, role in (analysis.get("role_bindings") or {}).items():
        if not isinstance(role, dict):
            continue
        roles[role_name] = {
            "role": role_name,
            "concept_id": role.get("concept_id"),
            "entity_type": role.get("entity_type"),
            "reference": role.get("reference"),
            "explicit_entity_ref": role.get("entity_ref"),
            "surface": role.get("matched_alias") or role.get("label"),
            "start": role.get("start"),
            "end": role.get("end"),
            "compatible_kinds": deepcopy(role.get("compatible_kinds", [])),
            "functional_affordances": deepcopy(role.get("functional_affordances", [])),
            "relation_predicate": role.get("relation_predicate"),
            "relation_target_role": role.get("relation_target_role"),
            "relation_surface": role.get("relation_surface"),
            "relation_span_start": role.get("relation_span_start"),
            "relation_span_end": role.get("relation_span_end"),
            "constraints": [],
        }

    predicate_candidates = []
    for concept in load_semantic_attribute_concepts().get("attribute_concepts", []):
        for value, aliases in concept.get("values", {}).items():
            for alias in sorted(aliases, key=len, reverse=True):
                start = normalized.find(_normalize(alias))
                if start < 0:
                    continue
                predicate_candidates.append({
                    "predicate_type": "attribute_constraint",
                    "concept_id": concept["concept_id"],
                    "display_name": concept.get("display_name"),
                    "observation_field": concept["observation_field"],
                    "value": value,
                    "accepted_observed_values": _accepted_observed_values(
                        concept, value
                    ),
                    "surface": alias,
                    "start": start,
                    "end": start + len(_normalize(alias)),
                    "applies_to_concepts": deepcopy(concept.get("applies_to_concepts", [])),
                })
                break
    predicates = []
    occupied_by_field: dict[str, list[tuple[int, int]]] = {}
    for predicate in sorted(
        predicate_candidates,
        key=lambda item: (-(item["end"] - item["start"]), item["start"]),
    ):
        field = predicate["observation_field"]
        if any(
            predicate["start"] < end and predicate["end"] > start
            for start, end in occupied_by_field.get(field, [])
        ):
            continue
        predicates.append(predicate)
        occupied_by_field.setdefault(field, []).append((predicate["start"], predicate["end"]))
    predicates.sort(key=lambda item: item["start"])

    for predicate in predicates:
        compatible_roles = [
            role for role in roles.values()
            if not predicate.get("applies_to_concepts")
            or role.get("concept_id") in predicate.get("applies_to_concepts", [])
        ]
        ranked = []
        for role in compatible_roles:
            role_start, role_end = role.get("start"), role.get("end")
            if not isinstance(role_start, int) or not isinstance(role_end, int):
                continue
            span_start = role.get("relation_span_start")
            span_end = role.get("relation_span_end")
            inside_relation_scope = bool(
                isinstance(span_start, int)
                and isinstance(span_end, int)
                and span_start <= predicate["start"]
                and predicate["end"] <= span_end
            )
            overlap = predicate["start"] < role_end and predicate["end"] > role_start
            distance = 0 if overlap else min(abs(predicate["end"] - role_start), abs(role_end - predicate["start"]))
            if inside_relation_scope or overlap or distance <= 6:
                ranked.append((
                    0 if inside_relation_scope else 1,
                    0 if overlap else distance,
                    0 if role["role"] in {"theme", "target"} else 1,
                    role,
                ))
        target_role = min(ranked, key=lambda item: (item[0], item[1], item[2]))[3] if ranked else roles.get("theme") or roles.get("target")
        if target_role:
            target_role["constraints"].append(deepcopy(predicate))
            predicate["role"] = target_role["role"]
        else:
            predicate["role"] = None

    return {
        "schema_version": "1.0.0",
        "utterance": utterance,
        "normalized_utterance": normalized,
        "speech_act": analysis.get("speech_act"),
        "operators": deepcopy((analysis.get("canonical_frame") or {}).get("operators", [])),
        "goal_relation": (analysis.get("canonical_frame") or {}).get("goal_relation"),
        "roles": roles,
        "attribute_predicates": predicates,
        "unresolved_surfaces": deepcopy(analysis.get("unresolved_slots", [])),
        "evidence_boundary": {
            "language_creates_concept_constraints": True,
            "language_does_not_bind_physical_instances": True,
            "language_does_not_commit_runtime_facts": True,
        },
    }


def build_observation_evidence_set(
    runtime_objects: list[dict[str, Any]],
    object_concepts: list[dict[str, Any]],
    *,
    world_revision: int,
    source: str,
) -> dict[str, Any]:
    """Project the current sensor/world adapter view into versioned epistemic evidence."""
    entities = []
    for entity in runtime_objects:
        if entity.get("active") is False:
            continue
        concepts = [
            {
                "concept_id": concept.get("concept_id"),
                "functional_affordances": deepcopy(concept.get("functional_affordances", [])),
                "compatibility_basis": "observed_kind_matches_concept_adapter",
            }
            for concept in object_concepts
            if entity.get("kind") in concept.get("compatible_kinds", [])
        ]
        relations = []
        if entity.get("support_ref"):
            relations.append({"predicate": "supported_by", "object": entity["support_ref"]})
        if entity.get("received_by"):
            relations.append({"predicate": "received_by", "object": entity["received_by"]})
        if entity.get("attached_to_executor") or entity.get("held_by_effector"):
            relations.append({"predicate": "held_by_executor", "object": entity.get("held_by_effector")})
        entities.append({
            "entity_ref": entity.get("entity_id"),
            "current_name_surface": entity.get("label"),
            "kind": entity.get("kind"),
            "concept_candidates": concepts,
            "observed_attributes": observed_perceptual_attributes(entity),
            "observed_relations": relations,
            "estimated_position": deepcopy(entity.get("position")),
            "evidence_source": source,
            "world_revision": world_revision,
        })
    digest = hashlib.sha1(
        json.dumps({"revision": world_revision, "source": source, "entities": entities}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    return {
        "schema_version": "1.0.0",
        "evidence_set_id": f"observation_{digest}",
        "world_revision": world_revision,
        "source": source,
        "entities": entities,
        "epistemic_only": True,
        "changes_execution_state": False,
        "invalid_after_world_revision_change": True,
    }


def ground_semantic_role(
    semantic_frame: dict[str, Any],
    observation_evidence: dict[str, Any],
    role_name: str,
    *,
    candidate_entity_refs: set[str] | None = None,
    confirmed_entity_ref: str | None = None,
) -> dict[str, Any]:
    """Bind one semantic role only through current, version-matched evidence."""
    role = deepcopy((semantic_frame.get("roles") or {}).get(role_name) or {})
    entities = observation_evidence.get("entities", [])
    if candidate_entity_refs is not None:
        entities = [item for item in entities if item.get("entity_ref") in candidate_entity_refs]
    concept_id = role.get("concept_id")
    compatible_kinds = set(role.get("compatible_kinds") or [])
    entity_type = role.get("entity_type")
    if entity_type:
        compatible_kinds.add(entity_type)
    if role.get("reference") in {"human_speaker", "current_human_recipient_role"}:
        compatible_kinds.add("human_recipient")
    if concept_id:
        entities = [
            item for item in entities
            if any(candidate.get("concept_id") == concept_id for candidate in item.get("concept_candidates", []))
        ]
    elif compatible_kinds:
        entities = [item for item in entities if item.get("kind") in compatible_kinds]

    constraints = role.get("constraints") or []
    matched, rejected = [], []
    for entity in entities:
        mismatches = [
            {
                "concept_id": constraint.get("concept_id"),
                "field": constraint.get("observation_field"),
                "requested": constraint.get("value"),
                "observed": (entity.get("observed_attributes") or {}).get(constraint.get("observation_field")),
            }
            for constraint in constraints
            if (entity.get("observed_attributes") or {}).get(
                constraint.get("observation_field")
            ) not in constraint.get("accepted_observed_values", [constraint.get("value")])
        ]
        record = {**deepcopy(entity), "constraint_mismatches": mismatches}
        (rejected if mismatches else matched).append(record)

    normalized_utterance = semantic_frame.get("normalized_utterance") or _normalize(semantic_frame.get("utterance", ""))
    explicit_ref = role.get("explicit_entity_ref")
    ranked = []
    for entity in matched:
        label = _normalize(entity.get("current_name_surface") or "")
        label_positions = [match.start() for match in re.finditer(re.escape(label), normalized_utterance)] if label else []
        role_start = role.get("start")
        label_refers_to_role = bool(
            label_positions
            and (
                not isinstance(role_start, int)
                or any(position <= role_start < position + len(label) for position in label_positions)
            )
        )
        basis, strength = "current_concept_compatible_candidate", 100
        if constraints:
            basis, strength = "concept_constraints_grounded_in_current_observation", 500
        # A descriptive display label such as "白色马克杯" must not become
        # identity evidence once the same phrase has already decomposed into
        # concept predicates. Otherwise an arbitrary UI name breaks a genuine
        # physical tie between two equally matching instances.
        if label_refers_to_role and not constraints:
            basis, strength = "concept_constraints_plus_current_name_reference", 600
        if explicit_ref == entity.get("entity_ref"):
            basis, strength = "context_reference_revalidated_in_current_observation", 650
        if confirmed_entity_ref == entity.get("entity_ref"):
            basis, strength = "human_confirmed_role_revalidated_in_current_observation", 700
        ranked.append({
            **entity,
            "binding_basis": basis,
            "evidence_strength": strength,
            "matched_constraints": deepcopy(constraints),
        })
    strongest = max((item["evidence_strength"] for item in ranked), default=None)
    strongest_candidates = [item for item in ranked if item["evidence_strength"] == strongest] if strongest is not None else []
    status = "resolved" if len(strongest_candidates) == 1 else "ambiguous" if strongest_candidates else "missing"
    return {
        "role": role_name,
        "status": status,
        "binding": deepcopy(strongest_candidates[0]) if status == "resolved" else None,
        "candidate_bindings": deepcopy(strongest_candidates),
        "constraint_rejections": rejected,
        "semantic_role": role,
        "world_revision": observation_evidence.get("world_revision"),
        "observation_evidence_set_id": observation_evidence.get("evidence_set_id"),
        "current_world_revalidated": status == "resolved",
    }


def build_grounded_intent_frame(
    semantic_frame: dict[str, Any],
    observation_evidence: dict[str, Any],
    *,
    role_candidate_refs: dict[str, set[str]] | None = None,
    confirmed_bindings: dict[str, str] | None = None,
) -> dict[str, Any]:
    roles = {}
    for role_name in (semantic_frame.get("roles") or {}):
        roles[role_name] = ground_semantic_role(
            semantic_frame,
            observation_evidence,
            role_name,
            candidate_entity_refs=(role_candidate_refs or {}).get(role_name),
            confirmed_entity_ref=(confirmed_bindings or {}).get(role_name),
        )
    return {
        "schema_version": "1.0.0",
        "semantic_constraint_frame": deepcopy(semantic_frame),
        "observation_evidence_set_id": observation_evidence.get("evidence_set_id"),
        "world_revision": observation_evidence.get("world_revision"),
        "roles": roles,
        "resolved_role_bindings": {
            role_name: result["binding"]["entity_ref"]
            for role_name, result in roles.items()
            if result.get("status") == "resolved" and result.get("binding")
        },
        "unresolved_roles": [
            role_name for role_name, result in roles.items() if result.get("status") != "resolved"
        ],
        "execution_authorized": False,
        "physical_fact_committed": False,
    }
