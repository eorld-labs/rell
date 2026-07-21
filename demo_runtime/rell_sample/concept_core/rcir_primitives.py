from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any


PRIMITIVE_SCHEMA_VERSION = "1.0.0"
FACT_COMMIT_SOURCES = {
    "p016_physical_verification",
    "runtime_snapshot",
    "multimodal_observation",
    "safe_probe_result",
}


def stable_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stable_id(prefix: str, value: Any) -> str:
    return f"{prefix}_{stable_digest(value)[:16]}"


def make_concept(
    concept_id: str,
    *,
    super_concept_refs: list[str],
    perceptual_invariants: list[str],
    functional_affordances: list[str],
    state_predicate_refs: list[str],
    lifecycle_status: str = "candidate",
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": PRIMITIVE_SCHEMA_VERSION,
        "type": "Concept",
        "concept_id": concept_id,
        "super_concept_refs": sorted(set(super_concept_refs)),
        "perceptual_invariants": sorted(set(perceptual_invariants)),
        "functional_affordances": sorted(set(functional_affordances)),
        "state_predicate_refs": sorted(set(state_predicate_refs)),
        "lifecycle_status": lifecycle_status,
        "evidence_refs": sorted(set(evidence_refs or [])),
        "execution_authority": False,
    }


def make_entity_ref(
    entity_ref: str,
    *,
    concept_refs: list[str],
    identity_anchors: list[dict[str, Any]],
    world_revision: int,
    aliases: list[dict[str, Any]] | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    if not identity_anchors:
        raise ValueError("entity_ref_requires_identity_anchor")
    return {
        "schema_version": PRIMITIVE_SCHEMA_VERSION,
        "type": "EntityRef",
        "entity_ref": entity_ref,
        "concept_refs": sorted(set(concept_refs)),
        "identity_anchors": deepcopy(identity_anchors),
        "aliases": deepcopy(aliases or []),
        "world_revision": int(world_revision),
        "status": "current",
        "evidence_refs": sorted(set(evidence_refs or [])),
    }


def _argument(role: str, value: Any, value_type: str) -> dict[str, Any]:
    return {"role": role, "value_type": value_type, "value": deepcopy(value)}


def make_predicate(
    name: str,
    arguments: list[dict[str, Any]],
    *,
    world_revision: int,
    modality: str = "reported_candidate",
    status: str = "candidate",
    polarity: str = "positive",
    evidence_refs: list[str] | None = None,
    depends_on_refs: list[str] | None = None,
) -> dict[str, Any]:
    normalized_arguments = [
        _argument(
            str(item["role"]),
            item.get("value"),
            str(item.get("value_type") or "literal"),
        )
        for item in arguments
    ]
    semantic_key = {
        "name": name,
        "arguments": normalized_arguments,
        "polarity": polarity,
        "world_revision": int(world_revision),
    }
    return {
        "schema_version": PRIMITIVE_SCHEMA_VERSION,
        "type": "Predicate",
        "predicate_id": stable_id("predicate", semantic_key),
        "name": name,
        "arguments": normalized_arguments,
        "polarity": polarity,
        "modality": modality,
        "status": status,
        "world_revision": int(world_revision),
        "evidence_refs": sorted(set(evidence_refs or [])),
        "depends_on_refs": sorted(set(depends_on_refs or [])),
    }


def make_event(
    event_type: str,
    *,
    participant_refs: dict[str, str],
    world_revision: int,
    temporal_scope: str,
    status: str = "candidate",
    actor_ref: str | None = None,
    evidence_refs: list[str] | None = None,
    produces_predicate_refs: list[str] | None = None,
    arbitration_ref: str | None = None,
    verification_ref: str | None = None,
) -> dict[str, Any]:
    seed = {
        "event_type": event_type,
        "participant_refs": participant_refs,
        "world_revision": int(world_revision),
        "temporal_scope": temporal_scope,
        "evidence_refs": sorted(set(evidence_refs or [])),
    }
    return {
        "schema_version": PRIMITIVE_SCHEMA_VERSION,
        "type": "Event",
        "event_id": stable_id("event", seed),
        "event_type": event_type,
        "actor_ref": actor_ref,
        "participant_refs": deepcopy(participant_refs),
        "temporal_scope": temporal_scope,
        "status": status,
        "world_revision": int(world_revision),
        "evidence_refs": sorted(set(evidence_refs or [])),
        "produces_predicate_refs": sorted(set(produces_predicate_refs or [])),
        "arbitration_ref": arbitration_ref,
        "verification_ref": verification_ref,
    }


def make_goal(
    target_predicate_refs: list[str],
    *,
    world_revision: int,
    depends_on_refs: list[str],
    priority: int = 50,
    status: str = "candidate",
    authorization_scope: str = "task_goal",
) -> dict[str, Any]:
    seed = {
        "targets": sorted(set(target_predicate_refs)),
        "world_revision": int(world_revision),
    }
    return {
        "schema_version": PRIMITIVE_SCHEMA_VERSION,
        "type": "Goal",
        "goal_id": stable_id("goal", seed),
        "target_predicate_refs": sorted(set(target_predicate_refs)),
        "status": status,
        "priority": int(priority),
        "world_revision": int(world_revision),
        "depends_on_refs": sorted(set(depends_on_refs)),
        "authorization_scope": authorization_scope,
    }


def make_constraint(
    constraint_type: str,
    *,
    scope_ref: str,
    operator: str,
    value: Any,
    world_revision: int,
    evidence_refs: list[str],
    depends_on_refs: list[str],
    status: str = "active",
) -> dict[str, Any]:
    seed = {
        "constraint_type": constraint_type,
        "scope_ref": scope_ref,
        "operator": operator,
        "value": value,
        "world_revision": int(world_revision),
    }
    return {
        "schema_version": PRIMITIVE_SCHEMA_VERSION,
        "type": "Constraint",
        "constraint_id": stable_id("constraint", seed),
        "constraint_type": constraint_type,
        "scope_ref": scope_ref,
        "operator": operator,
        "value": deepcopy(value),
        "status": status,
        "world_revision": int(world_revision),
        "evidence_refs": sorted(set(evidence_refs)),
        "depends_on_refs": sorted(set(depends_on_refs)),
    }


def _evidence_is_fact_commit_eligible(
    source_type: str,
    epistemic_status: str,
    qualification: dict[str, Any],
) -> bool:
    if source_type not in FACT_COMMIT_SOURCES:
        return False
    if not qualification.get("current_world_bound"):
        return False
    if source_type in {"p016_physical_verification", "safe_probe_result"}:
        return bool(
            epistemic_status == "physically_verified"
            and qualification.get("physical_verification")
            and qualification.get("verifier") == "P016"
        )
    if source_type == "runtime_snapshot":
        return epistemic_status in {"corroborated", "physically_verified"}
    return bool(
        epistemic_status in {"corroborated", "physically_verified"}
        and int(qualification.get("independent_channels", 0)) >= 2
    )


def make_evidence_envelope(
    source_type: str,
    *,
    epistemic_status: str,
    world_revision: int,
    supports_refs: list[str],
    strength: int,
    independent_channels: int = 0,
    physical_verification: bool = False,
    current_world_bound: bool = True,
    verifier: str | None = None,
    depends_on_refs: list[str] | None = None,
    invalid_after_world_revision_change: bool = True,
    payload: Any = None,
) -> dict[str, Any]:
    qualification = {
        "independent_channels": int(independent_channels),
        "physical_verification": bool(physical_verification),
        "current_world_bound": bool(current_world_bound),
        "verifier": verifier,
    }
    seed = {
        "source_type": source_type,
        "epistemic_status": epistemic_status,
        "world_revision": int(world_revision),
        "supports_refs": sorted(set(supports_refs)),
        "qualification": qualification,
        "payload_digest": stable_digest(payload) if payload is not None else None,
    }
    return {
        "schema_version": PRIMITIVE_SCHEMA_VERSION,
        "type": "EvidenceEnvelope",
        "envelope_id": stable_id("evidence", seed),
        "source_type": source_type,
        "epistemic_status": epistemic_status,
        "world_revision": int(world_revision),
        "supports_refs": sorted(set(supports_refs)),
        "strength": max(0, min(1000, int(strength))),
        "qualification": qualification,
        "fact_commit_eligible": _evidence_is_fact_commit_eligible(
            source_type, epistemic_status, qualification
        ),
        "invalidation": {
            "invalid_after_world_revision_change": bool(
                invalid_after_world_revision_change
            ),
            "depends_on_refs": sorted(set(depends_on_refs or [])),
        },
        "payload_digest": stable_digest(payload) if payload is not None else None,
    }


def validate_primitive(value: dict[str, Any]) -> dict[str, Any]:
    errors = []
    primitive_type = value.get("type")
    required_by_type = {
        "Concept": ("concept_id", "lifecycle_status"),
        "EntityRef": ("entity_ref", "identity_anchors", "world_revision"),
        "Predicate": ("predicate_id", "name", "arguments", "evidence_refs"),
        "Event": ("event_id", "event_type", "participant_refs", "evidence_refs"),
        "Goal": ("goal_id", "target_predicate_refs", "depends_on_refs"),
        "Constraint": ("constraint_id", "scope_ref", "depends_on_refs"),
        "EvidenceEnvelope": (
            "envelope_id",
            "source_type",
            "qualification",
            "fact_commit_eligible",
        ),
    }
    if primitive_type not in required_by_type:
        errors.append("unknown_primitive_type")
    else:
        for key in required_by_type[primitive_type]:
            if key not in value:
                errors.append(f"required_field_missing:{primitive_type}:{key}")
    if value.get("schema_version") != PRIMITIVE_SCHEMA_VERSION:
        errors.append("schema_version_mismatch")
    return {"valid": not errors, "errors": errors}


class EntityIdentityRegistry:
    """Keep instance identity separate from names, modalities, and task stages."""

    def __init__(self) -> None:
        self.entities: dict[str, dict[str, Any]] = {}
        self.anchor_index: dict[tuple[str, str], str] = {}
        self.observation_receipts: list[dict[str, Any]] = []

    def register(self, entity: dict[str, Any]) -> str:
        validation = validate_primitive(entity)
        if not validation["valid"] or entity.get("type") != "EntityRef":
            raise ValueError("invalid_entity_ref:" + ",".join(validation["errors"]))
        entity_ref = entity["entity_ref"]
        for anchor in entity["identity_anchors"]:
            key = (anchor["anchor_type"], anchor["anchor_value"])
            existing = self.anchor_index.get(key)
            if existing and existing != entity_ref:
                raise ValueError("identity_anchor_conflict")
            self.anchor_index[key] = entity_ref
        self.entities[entity_ref] = deepcopy(entity)
        return entity_ref

    def observe(
        self,
        *,
        identity_anchors: list[dict[str, Any]],
        modality: str,
        alias_ref: str | None,
        world_revision: int,
        stage_ref: str,
        evidence_ref: str,
    ) -> str:
        refs = {
            self.anchor_index.get((item["anchor_type"], item["anchor_value"]))
            for item in identity_anchors
        } - {None}
        if len(refs) != 1:
            raise ValueError("entity_identity_not_uniquely_grounded")
        entity_ref = next(iter(refs))
        entity = self.entities[entity_ref]
        if alias_ref and not any(
            item.get("alias_ref") == alias_ref
            and item.get("modality") == modality
            for item in entity.get("aliases", [])
        ):
            entity.setdefault("aliases", []).append(
                {
                    "alias_ref": alias_ref,
                    "modality": modality,
                    "world_revision": int(world_revision),
                }
            )
        entity["world_revision"] = int(world_revision)
        entity["status"] = "current"
        if evidence_ref not in entity.setdefault("evidence_refs", []):
            entity["evidence_refs"].append(evidence_ref)
        self.observation_receipts.append(
            {
                "entity_ref": entity_ref,
                "modality": modality,
                "alias_ref": alias_ref,
                "stage_ref": stage_ref,
                "world_revision": int(world_revision),
                "evidence_ref": evidence_ref,
                "identity_changed": False,
            }
        )
        return entity_ref


def invalidate_versioned_artifacts(
    artifacts: list[dict[str, Any]],
    *,
    new_world_revision: int,
    changed_refs: set[str],
) -> dict[str, Any]:
    invalidated_ids: list[str] = []
    active_changed = set(changed_refs)
    pending = [deepcopy(item) for item in artifacts]
    changed = True
    while changed:
        changed = False
        for item in pending:
            artifact_id = next(
                (
                    item.get(key)
                    for key in (
                        "envelope_id",
                        "predicate_id",
                        "event_id",
                        "goal_id",
                        "constraint_id",
                        "inquiry_id",
                    )
                    if item.get(key)
                ),
                None,
            )
            if not artifact_id or artifact_id in invalidated_ids:
                continue
            if int(item.get("world_revision", new_world_revision)) >= new_world_revision:
                continue
            dependencies = set(item.get("depends_on_refs") or [])
            dependencies.update(
                (item.get("invalidation") or {}).get("depends_on_refs") or []
            )
            dependencies.update(item.get("evidence_refs") or [])
            should_invalidate = bool(dependencies & active_changed)
            if not should_invalidate:
                continue
            if item.get("type") == "EvidenceEnvelope":
                item["epistemic_status"] = "invalidated"
                item["fact_commit_eligible"] = False
            else:
                item["status"] = "invalidated"
            item["invalidation_reason"] = "dependency_changed_in_new_world_revision"
            item["invalidated_at_world_revision"] = int(new_world_revision)
            invalidated_ids.append(artifact_id)
            active_changed.add(artifact_id)
            changed = True
    return {
        "world_revision": int(new_world_revision),
        "changed_refs": sorted(changed_refs),
        "invalidated_ids": invalidated_ids,
        "artifacts": pending,
        "local_invalidation_only": True,
    }


class CognitiveAuthorityLedger:
    """The only fact authority used by task planning, inquiry, and explanation."""

    def __init__(
        self, world_revision: int = 0, *, authority_ref: str | None = None
    ) -> None:
        self.world_revision = int(world_revision)
        self.ledger_id = authority_ref or stable_id(
            "ledger", {"authority": "world_fact_ledger", "created": world_revision}
        )
        self.evidence: dict[str, dict[str, Any]] = {}
        self.predicates: dict[str, dict[str, Any]] = {}
        self.events: dict[str, dict[str, Any]] = {}

    def snapshot(self) -> dict[str, Any]:
        """Return indexes that extend, rather than replace, the bound fact ledger."""
        return {
            "fact_authority_ref": self.ledger_id,
            "world_revision": self.world_revision,
            "evidence": deepcopy(self.evidence),
            "predicates": deepcopy(self.predicates),
            "events": deepcopy(self.events),
            "control_gateway": "P018",
            "verification_gateway": "P016",
            "direct_execution_allowed": False,
        }

    def add_evidence(self, envelope: dict[str, Any]) -> str:
        validation = validate_primitive(envelope)
        if not validation["valid"] or envelope.get("type") != "EvidenceEnvelope":
            raise ValueError("invalid_evidence_envelope")
        if envelope.get("world_revision") != self.world_revision:
            raise ValueError("evidence_world_revision_mismatch")
        self.evidence[envelope["envelope_id"]] = deepcopy(envelope)
        return envelope["envelope_id"]

    def submit_predicate_candidate(self, predicate: dict[str, Any]) -> str:
        validation = validate_primitive(predicate)
        if not validation["valid"] or predicate.get("type") != "Predicate":
            raise ValueError("invalid_predicate")
        if predicate.get("status") != "candidate":
            raise ValueError("predicate_submission_must_be_candidate")
        self.predicates[predicate["predicate_id"]] = deepcopy(predicate)
        return predicate["predicate_id"]

    def establish_predicate(
        self, predicate_id: str, evidence_ref: str
    ) -> dict[str, Any]:
        predicate = self.predicates[predicate_id]
        evidence = self.evidence.get(evidence_ref)
        if not evidence:
            raise ValueError("qualified_evidence_envelope_required")
        if evidence.get("fact_commit_eligible") is not True:
            raise PermissionError("evidence_not_eligible_for_execution_fact")
        if evidence.get("world_revision") != self.world_revision:
            raise ValueError("evidence_world_revision_mismatch")
        predicate["status"] = "established"
        predicate["modality"] = "current_fact"
        if evidence_ref not in predicate["evidence_refs"]:
            predicate["evidence_refs"].append(evidence_ref)
        return deepcopy(predicate)

    def commit_verified_transition(
        self,
        *,
        event: dict[str, Any],
        predicate: dict[str, Any],
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        evidence_ref = self.add_evidence(evidence)
        predicate_ref = self.submit_predicate_candidate(predicate)
        established = self.establish_predicate(predicate_ref, evidence_ref)
        committed_event = deepcopy(event)
        if committed_event.get("verification_ref") != evidence_ref:
            raise ValueError("event_verification_ref_must_match_evidence")
        if predicate_ref not in committed_event.get("produces_predicate_refs", []):
            raise ValueError("event_must_reference_produced_predicate")
        committed_event["status"] = "verified"
        if evidence_ref not in committed_event["evidence_refs"]:
            committed_event["evidence_refs"].append(evidence_ref)
        self.events[committed_event["event_id"]] = committed_event
        return {
            "event_ref": committed_event["event_id"],
            "predicate_ref": established["predicate_id"],
            "evidence_ref": evidence_ref,
            "fact_authority_ref": self.ledger_id,
        }

    def planning_view(self, predicate_ref: str) -> dict[str, Any]:
        predicate = deepcopy(self.predicates[predicate_ref])
        return {
            "consumer": "planner",
            "fact_authority_ref": self.ledger_id,
            "predicate_ref": predicate_ref,
            "predicate": predicate,
            "evidence_refs": deepcopy(predicate.get("evidence_refs", [])),
        }

    def explanation_view(self, event_ref: str) -> dict[str, Any]:
        event = deepcopy(self.events[event_ref])
        predicate_ref = event["produces_predicate_refs"][0]
        predicate = deepcopy(self.predicates[predicate_ref])
        return {
            "consumer": "explanation",
            "fact_authority_ref": self.ledger_id,
            "event_ref": event_ref,
            "event": event,
            "predicate_ref": predicate_ref,
            "predicate": predicate,
            "evidence_refs": deepcopy(predicate.get("evidence_refs", [])),
        }


def assert_shared_authority_contract(contract: dict[str, Any]) -> None:
    if not contract.get("fact_authority_ref"):
        raise AssertionError("secondary_or_missing_fact_source")
    if contract.get("control_gateway") != "P018":
        raise AssertionError("control_bypassed_p018")
    if contract.get("verification_gateway") != "P016":
        raise AssertionError("verification_bypassed_p016")
    if contract.get("direct_execution_allowed") is not False:
        raise AssertionError("direct_execution_bypass_detected")


__all__ = [
    "CognitiveAuthorityLedger",
    "EntityIdentityRegistry",
    "assert_shared_authority_contract",
    "invalidate_versioned_artifacts",
    "make_concept",
    "make_constraint",
    "make_entity_ref",
    "make_event",
    "make_evidence_envelope",
    "make_goal",
    "make_predicate",
    "stable_digest",
    "stable_id",
    "validate_primitive",
]
