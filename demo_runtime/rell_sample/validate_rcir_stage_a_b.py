from __future__ import annotations

import json
from pathlib import Path

from concept_core.cognitive_inquiry import (
    CognitiveInquiryRuntime,
    adapt_cognitive_signal,
    generate_competing_hypotheses,
    make_inquiry_contract,
    run_concept_validation_loop,
    run_quality_profile_drift_loop,
    run_recovery_boundary_probe_loop,
)
from concept_core.cognitive_ir import build_world_fact_ledger
from concept_core.rcir_contracts import build_portable_experience_contract
from concept_core.rcir_primitives import (
    CognitiveAuthorityLedger,
    EntityIdentityRegistry,
    assert_shared_authority_contract,
    invalidate_versioned_artifacts,
    make_concept,
    make_constraint,
    make_entity_ref,
    make_event,
    make_evidence_envelope,
    make_goal,
    make_predicate,
    validate_primitive,
)
from runtime_core import run_simulated_runtime_sample


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
PRIMITIVE_SCHEMAS = {
    "Concept": "rcir_concept.schema.json",
    "EntityRef": "rcir_entity_ref.schema.json",
    "Predicate": "rcir_predicate.schema.json",
    "Event": "rcir_event.schema.json",
    "Goal": "rcir_goal.schema.json",
    "Constraint": "rcir_constraint.schema.json",
    "EvidenceEnvelope": "rcir_evidence_envelope.schema.json",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _artifact_by_id(result: dict, artifact_id: str) -> dict:
    return next(
        item
        for item in result["artifacts"]
        if artifact_id
        in {
            item.get("envelope_id"),
            item.get("predicate_id"),
            item.get("event_id"),
            item.get("goal_id"),
            item.get("constraint_id"),
            item.get("inquiry_id"),
        }
    )


def _require_top_level_schema_shape(
    instance: dict, schema: dict, primitive_type: str
) -> None:
    missing = set(schema.get("required", [])) - set(instance)
    extras = set(instance) - set(schema.get("properties", {}))
    require(not missing, f"{primitive_type} is missing schema fields: {missing}")
    require(not extras, f"{primitive_type} contains undeclared fields: {extras}")
    for key, declaration in schema.get("properties", {}).items():
        if key not in instance:
            continue
        if "const" in declaration:
            require(
                instance[key] == declaration["const"],
                f"{primitive_type}.{key} violates const",
            )
        if "enum" in declaration:
            require(
                instance[key] in declaration["enum"],
                f"{primitive_type}.{key} violates enum",
            )


def verify_formal_schemas_and_relation_table() -> dict:
    schema_required_fields = {}
    sample_evidence = make_evidence_envelope(
        "runtime_snapshot",
        epistemic_status="corroborated",
        world_revision=1,
        supports_refs=["predicate_sample"],
        strength=700,
        depends_on_refs=["entity_sample"],
    )
    sample_predicate = make_predicate(
        "sample_relation",
        [{"role": "theme", "value_type": "EntityRef", "value": "entity_sample"}],
        world_revision=1,
        evidence_refs=[sample_evidence["envelope_id"]],
        depends_on_refs=["entity_sample"],
    )
    samples = {
        "Concept": make_concept(
            "concept_sample",
            super_concept_refs=[],
            perceptual_invariants=["sample_invariant"],
            functional_affordances=["sample_affordance"],
            state_predicate_refs=[sample_predicate["predicate_id"]],
        ),
        "EntityRef": make_entity_ref(
            "entity_sample",
            concept_refs=["concept_sample"],
            identity_anchors=[
                {
                    "anchor_type": "persistent_instance_id",
                    "anchor_value": "sample-1",
                    "modality": "registry",
                }
            ],
            world_revision=1,
        ),
        "Predicate": sample_predicate,
        "Event": make_event(
            "sample_event",
            participant_refs={"theme": "entity_sample"},
            world_revision=1,
            temporal_scope="current",
            produces_predicate_refs=[sample_predicate["predicate_id"]],
        ),
        "Goal": make_goal(
            [sample_predicate["predicate_id"]],
            world_revision=1,
            depends_on_refs=[sample_predicate["predicate_id"]],
        ),
        "Constraint": make_constraint(
            "epistemic",
            scope_ref="entity_sample",
            operator="requires",
            value="sample_observation",
            world_revision=1,
            evidence_refs=[sample_evidence["envelope_id"]],
            depends_on_refs=["entity_sample"],
        ),
        "EvidenceEnvelope": sample_evidence,
    }
    for primitive_type, filename in PRIMITIVE_SCHEMAS.items():
        payload = json.loads((SCHEMAS / filename).read_text(encoding="utf-8"))
        require(
            payload.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
            and payload.get("type") == "object"
            and payload.get("additionalProperties") is False
            and payload.get("properties", {}).get("type", {}).get("const")
            == primitive_type,
            f"primitive schema is not a strict Draft 2020-12 contract: {filename}",
        )
        _require_top_level_schema_shape(samples[primitive_type], payload, primitive_type)
        schema_required_fields[primitive_type] = payload.get("required", [])
    relations = json.loads(
        (SCHEMAS / "rcir_type_relations.json").read_text(encoding="utf-8")
    )
    relation_names = {
        (item["source_type"], item["relation"], item["target_type"])
        for item in relations.get("relation_table", [])
    }
    require(
        len(relation_names) == 7
        and (
            "EvidenceEnvelope",
            "supports_or_refutes",
            "EntityRef|Predicate|Event|Constraint",
        )
        in relation_names
        and "InquiryContract creates a second fact ledger"
        in relations.get("forbidden_relations", []),
        f"type relation table is incomplete: {relations}",
    )
    inquiry_schema = json.loads(
        (SCHEMAS / "inquiry_contract.schema.json").read_text(encoding="utf-8")
    )
    require(
        inquiry_schema.get("properties", {})
        .get("control_gateway", {})
        .get("const")
        == "P018"
        and inquiry_schema.get("properties", {})
        .get("verification_gateway", {})
        .get("const")
        == "P016"
        and inquiry_schema.get("properties", {})
        .get("direct_execution_allowed", {})
        .get("const")
        is False,
        f"inquiry schema does not enforce shared execution gateways: {inquiry_schema}",
    )
    return {
        "primitive_schema_count": len(schema_required_fields),
        "relation_count": len(relation_names),
        "strict_additional_properties": True,
    }


def verify_entity_identity_continuity() -> dict:
    registry = EntityIdentityRegistry()
    entity = make_entity_ref(
        "entity_stable_vessel_17",
        concept_refs=["concept_fillable_container"],
        identity_anchors=[
            {
                "anchor_type": "persistent_instance_id",
                "anchor_value": "scene-object-17",
                "modality": "registry",
            },
            {
                "anchor_type": "geometry_signature",
                "anchor_value": "geometry-93ad",
                "modality": "depth",
            },
        ],
        aliases=[
            {"alias_ref": "alias_original", "modality": "registry", "world_revision": 4}
        ],
        world_revision=4,
    )
    require(validate_primitive(entity)["valid"], f"invalid EntityRef: {entity}")
    registry.register(entity)
    anchor = [
        {
            "anchor_type": "persistent_instance_id",
            "anchor_value": "scene-object-17",
            "modality": "registry",
        }
    ]
    observations = [
        ("registry", "alias_renamed", "stage_inventory", "evidence_registry"),
        ("language", "alias_colloquial", "stage_acquire", "evidence_language"),
        ("vision", "alias_visual_track", "stage_fill", "evidence_vision"),
        ("touch", None, "stage_handover", "evidence_touch"),
    ]
    refs = [
        registry.observe(
            identity_anchors=anchor,
            modality=modality,
            alias_ref=alias,
            world_revision=4,
            stage_ref=stage,
            evidence_ref=evidence,
        )
        for modality, alias, stage, evidence in observations
    ]
    require(
        set(refs) == {entity["entity_ref"]}
        and all(
            receipt.get("identity_changed") is False
            for receipt in registry.observation_receipts
        ),
        f"rename, alias, modality, or stage changed identity: {refs}",
    )
    return {
        "entity_ref": entity["entity_ref"],
        "modalities": [item[0] for item in observations],
        "stages": [item[2] for item in observations],
        "identity_changes": 0,
    }


def verify_evidence_promotion_gate() -> dict:
    authority = CognitiveAuthorityLedger(world_revision=3)
    predicate = make_predicate(
        "container_empty",
        [{"role": "theme", "value_type": "EntityRef", "value": "entity_vessel"}],
        world_revision=3,
        modality="reported_candidate",
        depends_on_refs=["entity_vessel"],
    )
    predicate_ref = authority.submit_predicate_candidate(predicate)
    rejected_sources = []
    for source in ("human_report", "perception_candidate"):
        envelope = make_evidence_envelope(
            source,
            epistemic_status="candidate",
            world_revision=3,
            supports_refs=[predicate_ref],
            strength=300,
            independent_channels=1,
            depends_on_refs=["entity_vessel"],
        )
        evidence_ref = authority.add_evidence(envelope)
        require(
            envelope.get("fact_commit_eligible") is False,
            f"candidate evidence became fact eligible: {envelope}",
        )
        try:
            authority.establish_predicate(predicate_ref, evidence_ref)
        except PermissionError:
            rejected_sources.append(source)
        else:
            raise AssertionError(f"{source} established an execution fact")
    try:
        authority.establish_predicate(predicate_ref, "missing_envelope")
    except ValueError:
        missing_envelope_blocked = True
    else:
        missing_envelope_blocked = False
    p016 = make_evidence_envelope(
        "p016_physical_verification",
        epistemic_status="physically_verified",
        world_revision=3,
        supports_refs=[predicate_ref],
        strength=960,
        independent_channels=2,
        physical_verification=True,
        verifier="P016",
        depends_on_refs=["entity_vessel"],
    )
    established = authority.establish_predicate(
        predicate_ref, authority.add_evidence(p016)
    )
    rcir_ledger = build_world_fact_ledger(
        [
            {
                "predicate": "container_empty",
                "subject": "entity_vessel",
                "object": True,
                "evidence": "human_report",
                "world_revision": 3,
            },
            {
                "predicate": "visible_container",
                "subject": "entity_vessel",
                "object": True,
                "evidence": "perception_candidate",
                "world_revision": 3,
            },
        ],
        world_revision=3,
    )
    require(
        set(rejected_sources) == {"human_report", "perception_candidate"}
        and missing_envelope_blocked
        and established.get("status") == "established"
        and not rcir_ledger.get("authoritative_current_fact_ids"),
        f"evidence promotion boundary failed: {rejected_sources}: {rcir_ledger}",
    )
    return {
        "rejected_sources": sorted(rejected_sources),
        "missing_envelope_blocked": True,
        "qualified_source": p016["source_type"],
        "authoritative_candidates_without_envelope": 0,
    }


def verify_local_world_revision_invalidation() -> dict:
    authority = CognitiveAuthorityLedger(world_revision=8)
    old_evidence = make_evidence_envelope(
        "runtime_snapshot",
        epistemic_status="corroborated",
        world_revision=8,
        supports_refs=["predicate_old"],
        strength=700,
        depends_on_refs=["entity_changed"],
    )
    predicate = make_predicate(
        "supported_by",
        [
            {"role": "theme", "value_type": "EntityRef", "value": "entity_changed"},
            {"role": "support", "value_type": "EntityRef", "value": "surface_a"},
        ],
        world_revision=8,
        modality="current_fact",
        status="established",
        evidence_refs=[old_evidence["envelope_id"]],
        depends_on_refs=["entity_changed"],
    )
    goal = make_goal(
        [predicate["predicate_id"]],
        world_revision=8,
        depends_on_refs=[predicate["predicate_id"]],
        status="active",
    )
    constraint = make_constraint(
        "spatial",
        scope_ref="entity_changed",
        operator="requires",
        value="surface_a",
        world_revision=8,
        evidence_refs=[old_evidence["envelope_id"]],
        depends_on_refs=["entity_changed"],
    )
    unrelated = make_constraint(
        "safety",
        scope_ref="entity_unrelated",
        operator="forbids",
        value="restricted_zone",
        world_revision=8,
        evidence_refs=[],
        depends_on_refs=["entity_unrelated"],
    )
    inquiry = make_inquiry_contract(
        "fact_gap",
        subject_refs=["entity_changed"],
        trigger_evidence_refs=[old_evidence["envelope_id"]],
        candidate_hypotheses=["relation_preserved", "relation_changed"],
        question_predicate_ref=predicate["predicate_id"],
        answer_routes=["active_observation"],
        authorization_scope="observe_only",
        world_revision=8,
        depends_on_refs=[goal["goal_id"], constraint["constraint_id"]],
        closure_condition="current_relation_reobserved",
        fact_authority_ref=authority.ledger_id,
    )
    invalidated = invalidate_versioned_artifacts(
        [old_evidence, predicate, goal, constraint, inquiry, unrelated],
        new_world_revision=9,
        changed_refs={"entity_changed"},
    )
    related_ids = {
        old_evidence["envelope_id"],
        predicate["predicate_id"],
        goal["goal_id"],
        constraint["constraint_id"],
        inquiry["inquiry_id"],
    }
    require(
        related_ids.issubset(set(invalidated["invalidated_ids"]))
        and _artifact_by_id(invalidated, unrelated["constraint_id"]).get("status")
        == "active"
        and invalidated.get("local_invalidation_only") is True,
        f"world revision invalidation was global or incomplete: {invalidated}",
    )
    return {
        "new_world_revision": 9,
        "invalidated_type_count": 5,
        "unrelated_constraint_preserved": True,
        "local_invalidation_only": True,
    }


def verify_shared_event_predicate_evidence_readback() -> dict:
    authority = CognitiveAuthorityLedger(world_revision=12)
    predicate = make_predicate(
        "object_in_gripper",
        [{"role": "theme", "value_type": "EntityRef", "value": "entity_asset"}],
        world_revision=12,
        modality="perception_candidate",
        depends_on_refs=["entity_asset"],
    )
    evidence = make_evidence_envelope(
        "p016_physical_verification",
        epistemic_status="physically_verified",
        world_revision=12,
        supports_refs=[predicate["predicate_id"]],
        strength=980,
        independent_channels=2,
        physical_verification=True,
        verifier="P016",
        depends_on_refs=["entity_asset", "effector_primary"],
    )
    event = make_event(
        "grasp_verified",
        participant_refs={"theme": "entity_asset", "effector": "effector_primary"},
        world_revision=12,
        temporal_scope="verified_transition",
        produces_predicate_refs=[predicate["predicate_id"]],
        arbitration_ref="p018_authorization_12",
        verification_ref=evidence["envelope_id"],
    )
    committed = authority.commit_verified_transition(
        event=event, predicate=predicate, evidence=evidence
    )
    planning = authority.planning_view(committed["predicate_ref"])
    explanation = authority.explanation_view(committed["event_ref"])
    require(
        planning["fact_authority_ref"] == explanation["fact_authority_ref"]
        == authority.ledger_id
        and planning["predicate_ref"] == explanation["predicate_ref"]
        == committed["predicate_ref"]
        and planning["evidence_refs"] == explanation["evidence_refs"]
        == [committed["evidence_ref"]]
        and explanation["event_ref"] == committed["event_ref"],
        f"planner and explanation diverged after verification writeback: {planning}: {explanation}",
    )
    return {
        "event_ref": committed["event_ref"],
        "predicate_ref": committed["predicate_ref"],
        "evidence_ref": committed["evidence_ref"],
        "shared_fact_authority": authority.ledger_id,
    }


def verify_no_secondary_fact_or_control_path() -> dict:
    authority = CognitiveAuthorityLedger(world_revision=20)
    trigger_predicate = make_predicate(
        "unknown_state",
        [{"role": "subject", "value_type": "EntityRef", "value": "entity_unknown"}],
        world_revision=20,
        modality="hypothesis",
        depends_on_refs=["entity_unknown"],
    )
    trigger = make_evidence_envelope(
        "diagnostic_signal",
        epistemic_status="candidate",
        world_revision=20,
        supports_refs=[trigger_predicate["predicate_id"]],
        strength=300,
        depends_on_refs=["entity_unknown"],
    )
    trigger_ref = authority.add_evidence(trigger)
    inquiry = make_inquiry_contract(
        "fact_gap",
        subject_refs=["entity_unknown"],
        trigger_evidence_refs=[trigger_ref],
        candidate_hypotheses=["state_a", "state_b"],
        question_predicate_ref=trigger_predicate["predicate_id"],
        answer_routes=["active_observation"],
        authorization_scope="observe_only",
        world_revision=20,
        depends_on_refs=["entity_unknown", trigger_ref],
        closure_condition="qualified_evidence_obtained",
        fact_authority_ref=authority.ledger_id,
    )
    CognitiveInquiryRuntime(authority).create(inquiry)
    experience = build_portable_experience_contract(
        {
            "experience_id": "experience_shared_authority",
            "goal_fact": "object_supported",
            "process_chain": ["acquire", "place"],
            "effect_contract": {
                "requires": ["object_grounded"],
                "produces": ["object_supported"],
                "verification": ["support_verified"],
            },
            "invariant_contract": {},
        }
    )
    policy = experience["migration_policy"]
    experience_authority = {
        "fact_authority_ref": authority.ledger_id,
        "control_gateway": policy["control_gateway"],
        "verification_gateway": policy["verification_gateway"],
        "direct_execution_allowed": policy["direct_execution_allowed"],
    }
    recovery_authority = {
        "fact_authority_ref": authority.ledger_id,
        "control_gateway": "P018",
        "verification_gateway": "P016",
        "direct_execution_allowed": False,
    }
    for contract in (inquiry, experience_authority, recovery_authority):
        assert_shared_authority_contract(contract)
    bypass = dict(recovery_authority, control_gateway="direct_actuator")
    try:
        assert_shared_authority_contract(bypass)
    except AssertionError:
        bypass_blocked = True
    else:
        bypass_blocked = False
    require(
        bypass_blocked
        and inquiry["fact_authority_ref"]
        == experience_authority["fact_authority_ref"]
        == recovery_authority["fact_authority_ref"],
        "recovery, experience, or inquiry formed a second authority path",
    )
    return {
        "fact_authority_ref": authority.ledger_id,
        "contracts_checked": ["recovery", "experience_recall", "inquiry"],
        "control_bypass_blocked": True,
    }


def _verify_loop_shared_readback(loop: dict) -> None:
    closure = loop["closure"]
    planning = loop["planning_view"]
    explanation = loop["explanation_view"]
    action = loop["action"]
    require(
        closure["inquiry"]["status"] == "closed"
        and action["arbitration_receipt"]["gateway"] == "P018"
        and action["action_candidate"]["direct_execution_allowed"] is False
        and planning["fact_authority_ref"] == explanation["fact_authority_ref"]
        and planning["predicate_ref"] == explanation["predicate_ref"]
        and planning["evidence_refs"] == explanation["evidence_refs"],
        f"inquiry loop did not close through shared authority: {loop}",
    )


def verify_stage_b_inquiry_loops() -> dict:
    try:
        adapt_cognitive_signal(
            "quality_profile_drift",
            subject_refs=["entity_test"],
            question_predicate_ref="predicate_test",
            world_revision=1,
            depends_on_refs=[],
            measurements={"conclusion": "sensor_drift"},
            strength=300,
        )
    except ValueError as error:
        signal_conclusion_blocked = str(error) == "anomaly_signal_cannot_commit_hypothesis"
    else:
        signal_conclusion_blocked = False
    try:
        generate_competing_hypotheses("model_drift", ["only_hypothesis"])
    except ValueError:
        single_hypothesis_blocked = True
    else:
        single_hypothesis_blocked = False
    quality = run_quality_profile_drift_loop()
    p016_probe = run_simulated_runtime_sample(
        Path(__file__).resolve().parent / "data", "simulated_success"
    )
    recovery = run_recovery_boundary_probe_loop(p016_result=p016_probe)
    promoted = run_concept_validation_loop(prediction_confirmed=True)
    rejected = run_concept_validation_loop(prediction_confirmed=False)
    for loop in (quality, recovery, promoted, rejected):
        _verify_loop_shared_readback(loop)
    require(
        signal_conclusion_blocked
        and single_hypothesis_blocked
        and quality["hypothesis_count"] >= 3
        and quality["closure"]["inquiry"]["selected_hypothesis"]
        == "object_surface_condition_changed"
        and recovery["closure"]["inquiry"]["selected_hypothesis"]
        == "template_source_flow_boundary_missing"
        and recovery["explanation_view"]["event"]["verification_ref"]
        == recovery["closure"]["evidence_ref"]
        and recovery["p016_runtime_receipt"]["p016_outcome"] == "completed"
        and len(recovery["p016_runtime_receipt"]["channel_notes"]) >= 2
        and promoted["decision"]["decision"] == "promoted"
        and promoted["candidate"]["lifecycle_status"] == "trusted"
        and rejected["decision"]["decision"] == "rejected"
        and rejected["candidate"]["lifecycle_status"] == "rejected"
        and promoted["candidate"]["execution_authority"] is False
        and rejected["candidate"]["execution_authority"] is False,
        "one or more stage-B cognition loops failed its closure contract",
    )
    return {
        "shared_signal_gate": {
            "signal_cannot_commit_conclusion": True,
            "single_hypothesis_blocked": True,
        },
        "quality_profile_drift": {
            "status": quality["closure"]["inquiry"]["status"],
            "selected_hypothesis": quality["closure"]["inquiry"]["selected_hypothesis"],
            "route": quality["action"]["action_candidate"]["route"],
        },
        "recovery_boundary_probe": {
            "status": recovery["closure"]["inquiry"]["status"],
            "selected_hypothesis": recovery["closure"]["inquiry"]["selected_hypothesis"],
            "verification_gateway": "P016",
        },
        "concept_validation": {
            "confirmed_prediction": promoted["decision"]["decision"],
            "refuted_prediction": rejected["decision"]["decision"],
            "new_instance_verified": True,
        },
    }


def main() -> None:
    report = {
        "stage_a": {
            "schemas": verify_formal_schemas_and_relation_table(),
            "identity": verify_entity_identity_continuity(),
            "evidence_gate": verify_evidence_promotion_gate(),
            "version_invalidation": verify_local_world_revision_invalidation(),
            "shared_readback": verify_shared_event_predicate_evidence_readback(),
            "no_bypass": verify_no_secondary_fact_or_control_path(),
        },
        "stage_b": verify_stage_b_inquiry_loops(),
    }
    print("RCIR stage A/B engineering evidence validation passed.")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
