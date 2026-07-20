from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from .rcir_primitives import (
    CognitiveAuthorityLedger,
    assert_shared_authority_contract,
    make_concept,
    make_event,
    make_evidence_envelope,
    make_predicate,
    stable_id,
)


INQUIRY_SCHEMA_VERSION = "1.0.0"
COGNITIVE_SIGNAL_KINDS = {
    "quality_profile_drift",
    "recovery_pattern",
    "unexplained_repeated_pattern",
    "fact_lifecycle_gap",
}


def adapt_cognitive_signal(
    signal_kind: str,
    *,
    subject_refs: list[str],
    question_predicate_ref: str,
    world_revision: int,
    depends_on_refs: list[str],
    measurements: dict[str, Any],
    strength: int,
) -> dict[str, Any]:
    if signal_kind not in COGNITIVE_SIGNAL_KINDS:
        raise ValueError("unsupported_cognitive_signal_kind")
    if "selected_hypothesis" in measurements or "conclusion" in measurements:
        raise ValueError("anomaly_signal_cannot_commit_hypothesis")
    return make_evidence_envelope(
        "diagnostic_signal",
        epistemic_status="candidate",
        world_revision=world_revision,
        supports_refs=[question_predicate_ref],
        strength=strength,
        depends_on_refs=[*subject_refs, *depends_on_refs],
        payload={
            "signal_kind": signal_kind,
            "subject_refs": sorted(set(subject_refs)),
            "measurements": deepcopy(measurements),
            "candidate_only": True,
        },
    )


def generate_competing_hypotheses(
    gap_type: str, candidates: list[str]
) -> list[str]:
    hypotheses = sorted(set(candidates))
    if len(hypotheses) < 2:
        raise ValueError(f"{gap_type}_requires_competing_hypotheses")
    return hypotheses


def make_inquiry_contract(
    gap_type: str,
    *,
    subject_refs: list[str],
    trigger_evidence_refs: list[str],
    candidate_hypotheses: list[str],
    question_predicate_ref: str,
    answer_routes: list[str],
    authorization_scope: str,
    world_revision: int,
    depends_on_refs: list[str],
    closure_condition: str,
    fact_authority_ref: str,
    expected_information_gain: float = 0.5,
    risk_if_ignored: str = "medium",
    acquisition_cost: str = "low",
) -> dict[str, Any]:
    hypotheses = generate_competing_hypotheses(gap_type, candidate_hypotheses)
    seed = {
        "gap_type": gap_type,
        "subject_refs": sorted(set(subject_refs)),
        "trigger_evidence_refs": sorted(set(trigger_evidence_refs)),
        "question_predicate_ref": question_predicate_ref,
        "world_revision": int(world_revision),
    }
    contract = {
        "schema_version": INQUIRY_SCHEMA_VERSION,
        "inquiry_id": stable_id("inquiry", seed),
        "gap_type": gap_type,
        "subject_refs": sorted(set(subject_refs)),
        "trigger_evidence_refs": sorted(set(trigger_evidence_refs)),
        "candidate_hypotheses": hypotheses,
        "question_predicate_ref": question_predicate_ref,
        "answer_routes": list(dict.fromkeys(answer_routes)),
        "expected_information_gain": max(
            0.0, min(1.0, float(expected_information_gain))
        ),
        "risk_if_ignored": risk_if_ignored,
        "acquisition_cost": acquisition_cost,
        "authorization_scope": authorization_scope,
        "world_revision": int(world_revision),
        "depends_on_refs": sorted(set(depends_on_refs)),
        "closure_condition": closure_condition,
        "status": "candidate",
        "selected_hypothesis": None,
        "resolution_evidence_refs": [],
        "arbitration_ref": None,
        "verification_ref": None,
        "fact_authority_ref": fact_authority_ref,
        "control_gateway": "P018",
        "verification_gateway": "P016",
        "direct_execution_allowed": False,
    }
    assert_shared_authority_contract(contract)
    return contract


class CognitiveInquiryRuntime:
    """Inquiry state machine sharing the task ledger and execution gateways."""

    def __init__(self, authority: CognitiveAuthorityLedger) -> None:
        self.authority = authority
        self.inquiries: dict[str, dict[str, Any]] = {}
        self.arbitration_receipts: dict[str, dict[str, Any]] = {}
        self.transition_log: list[dict[str, Any]] = []

    def create(self, contract: dict[str, Any]) -> dict[str, Any]:
        assert_shared_authority_contract(contract)
        if contract.get("fact_authority_ref") != self.authority.ledger_id:
            raise ValueError("inquiry_cannot_create_second_fact_source")
        missing = [
            ref
            for ref in contract.get("trigger_evidence_refs", [])
            if ref not in self.authority.evidence
        ]
        if missing:
            raise ValueError("inquiry_trigger_evidence_missing:" + "|".join(missing))
        self.inquiries[contract["inquiry_id"]] = deepcopy(contract)
        self._record(contract["inquiry_id"], None, "candidate", "inquiry_created")
        return deepcopy(contract)

    def admit(self, inquiry_id: str) -> dict[str, Any]:
        inquiry = self.inquiries[inquiry_id]
        self._transition(inquiry, {"candidate", "deferred"}, "admitted", "value_risk_cost_gate_passed")
        return deepcopy(inquiry)

    def authorize_route(
        self,
        inquiry_id: str,
        *,
        route: str,
        action_operator: str,
        risk: str,
    ) -> dict[str, Any]:
        inquiry = self.inquiries[inquiry_id]
        if inquiry.get("status") != "admitted":
            raise ValueError("inquiry_must_be_admitted_before_action")
        if route not in inquiry.get("answer_routes", []):
            raise ValueError("answer_route_not_declared")
        if route not in {"active_observation", "safe_probe"}:
            raise ValueError("route_does_not_require_control_authorization")
        if risk == "high":
            raise PermissionError("p018_rejected_high_risk_inquiry_action")
        action = {
            "action_candidate_id": stable_id(
                "inquiry_action",
                {
                    "inquiry": inquiry_id,
                    "route": route,
                    "operator": action_operator,
                    "world_revision": self.authority.world_revision,
                },
            ),
            "inquiry_ref": inquiry_id,
            "route": route,
            "operator": action_operator,
            "world_revision": self.authority.world_revision,
            "candidate_only": True,
            "direct_execution_allowed": False,
            "fact_authority_ref": self.authority.ledger_id,
            "control_gateway": "P018",
            "verification_gateway": "P016",
        }
        assert_shared_authority_contract(action)
        receipt = {
            "arbitration_id": stable_id("p018", action),
            "gateway": "P018",
            "decision": "authorized",
            "scope": inquiry.get("authorization_scope"),
            "action_candidate_ref": action["action_candidate_id"],
            "world_revision": self.authority.world_revision,
            "old_control_path_reused": False,
        }
        self.arbitration_receipts[receipt["arbitration_id"]] = receipt
        inquiry["arbitration_ref"] = receipt["arbitration_id"]
        target_status = "observing" if route == "active_observation" else "probing"
        self._transition(inquiry, {"admitted"}, target_status, "p018_authorized")
        return {"action_candidate": action, "arbitration_receipt": receipt}

    def commit_resolution(
        self,
        inquiry_id: str,
        *,
        selected_hypothesis: str,
        event: dict[str, Any],
        predicate: dict[str, Any],
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        inquiry = self.inquiries[inquiry_id]
        if inquiry.get("status") not in {"observing", "probing"}:
            raise ValueError("inquiry_not_collecting_resolution_evidence")
        if selected_hypothesis not in inquiry.get("candidate_hypotheses", []):
            raise ValueError("selected_hypothesis_not_declared")
        arbitration_ref = inquiry.get("arbitration_ref")
        receipt = self.arbitration_receipts.get(arbitration_ref)
        if not receipt or receipt.get("decision") != "authorized":
            raise PermissionError("inquiry_action_missing_p018_authorization")
        if event.get("arbitration_ref") != arbitration_ref:
            raise ValueError("event_does_not_reference_p018_authorization")
        committed = self.authority.commit_verified_transition(
            event=event,
            predicate=predicate,
            evidence=evidence,
        )
        inquiry["selected_hypothesis"] = selected_hypothesis
        inquiry["resolution_evidence_refs"] = [committed["evidence_ref"]]
        inquiry["verification_ref"] = committed["evidence_ref"]
        self._transition(
            inquiry,
            {"observing", "probing"},
            "resolved",
            "qualified_evidence_selected_hypothesis",
        )
        self._transition(inquiry, {"resolved"}, "verified", "shared_ledger_readback_verified")
        self._transition(inquiry, {"verified"}, "closed", "closure_condition_satisfied")
        return {**committed, "inquiry": deepcopy(inquiry)}

    def invalidate(self, inquiry_id: str, *, new_world_revision: int) -> dict[str, Any]:
        inquiry = self.inquiries[inquiry_id]
        if inquiry.get("status") == "closed":
            return deepcopy(inquiry)
        previous = inquiry.get("status")
        inquiry["status"] = "invalidated"
        inquiry["invalidated_at_world_revision"] = int(new_world_revision)
        inquiry["invalidation_reason"] = "world_revision_dependency_changed"
        self._record(inquiry_id, previous, "invalidated", "world_revision_dependency_changed")
        return deepcopy(inquiry)

    def _transition(
        self,
        inquiry: dict[str, Any],
        allowed_from: set[str],
        target: str,
        reason: str,
    ) -> None:
        previous = inquiry.get("status")
        if previous not in allowed_from:
            raise ValueError(f"invalid_inquiry_transition:{previous}->{target}")
        inquiry["status"] = target
        self._record(inquiry["inquiry_id"], previous, target, reason)

    def _record(
        self,
        inquiry_id: str,
        previous: str | None,
        target: str,
        reason: str,
    ) -> None:
        self.transition_log.append(
            {
                "inquiry_ref": inquiry_id,
                "from": previous,
                "to": target,
                "reason": reason,
                "world_revision": self.authority.world_revision,
            }
        )


def _question_predicate(
    name: str, subject_ref: str, world_revision: int
) -> dict[str, Any]:
    return make_predicate(
        name,
        [
            {"role": "subject", "value_type": "EntityRef", "value": subject_ref},
            {"role": "value", "value_type": "role_variable", "value": "?value"},
        ],
        world_revision=world_revision,
        modality="hypothesis",
        status="candidate",
        depends_on_refs=[subject_ref],
    )


def run_quality_profile_drift_loop() -> dict[str, Any]:
    authority = CognitiveAuthorityLedger(world_revision=31)
    subject_ref = "entity_quality_target"
    profile_ref = "quality_profile_grasp_v4"
    question = _question_predicate("current_grasp_profile", subject_ref, 31)
    trigger = adapt_cognitive_signal(
        "quality_profile_drift",
        subject_refs=[subject_ref],
        question_predicate_ref=question["predicate_id"],
        world_revision=31,
        depends_on_refs=[profile_ref],
        measurements={"baseline_mean": 0.72, "recent_mean": 0.51, "tolerance": 0.08},
        strength=420,
    )
    trigger_ref = authority.add_evidence(trigger)
    runtime = CognitiveInquiryRuntime(authority)
    inquiry = make_inquiry_contract(
        "model_drift",
        subject_refs=[subject_ref],
        trigger_evidence_refs=[trigger_ref],
        candidate_hypotheses=[
            "object_surface_condition_changed",
            "sensor_calibration_drift",
            "task_distribution_changed",
        ],
        question_predicate_ref=question["predicate_id"],
        answer_routes=["existing_evidence", "active_observation", "human_query"],
        authorization_scope="observe_only",
        world_revision=31,
        depends_on_refs=[subject_ref, profile_ref, trigger_ref],
        closure_condition="two_independent_modalities_identify_one_hypothesis",
        fact_authority_ref=authority.ledger_id,
        expected_information_gain=0.81,
    )
    runtime.create(inquiry)
    runtime.admit(inquiry["inquiry_id"])
    authorization = runtime.authorize_route(
        inquiry["inquiry_id"],
        route="active_observation",
        action_operator="resample_quality_from_new_view_and_touch",
        risk="low",
    )
    result_predicate = make_predicate(
        "quality_profile_state",
        [
            {"role": "subject", "value_type": "EntityRef", "value": subject_ref},
            {"role": "state", "value_type": "literal", "value": "surface_condition_changed"},
        ],
        world_revision=31,
        modality="perception_candidate",
        status="candidate",
        depends_on_refs=[subject_ref, profile_ref],
    )
    result_evidence = make_evidence_envelope(
        "multimodal_observation",
        epistemic_status="corroborated",
        world_revision=31,
        supports_refs=[result_predicate["predicate_id"]],
        strength=830,
        independent_channels=2,
        depends_on_refs=[subject_ref, profile_ref],
        payload={
            "vision": "surface_texture_changed",
            "touch": "friction_drop_confirmed",
            "sensor_self_check": "nominal",
        },
    )
    event = make_event(
        "active_quality_observation_completed",
        participant_refs={"subject": subject_ref},
        world_revision=31,
        temporal_scope="verified_transition",
        status="observed",
        evidence_refs=[],
        produces_predicate_refs=[result_predicate["predicate_id"]],
        arbitration_ref=authorization["arbitration_receipt"]["arbitration_id"],
        verification_ref=result_evidence["envelope_id"],
    )
    closed = runtime.commit_resolution(
        inquiry["inquiry_id"],
        selected_hypothesis="object_surface_condition_changed",
        event=event,
        predicate=result_predicate,
        evidence=result_evidence,
    )
    return {
        "loop_type": "quality_profile_drift",
        "trigger": {"baseline_mean": 0.72, "recent_mean": 0.51},
        "hypothesis_count": len(inquiry["candidate_hypotheses"]),
        "action": authorization,
        "closure": closed,
        "transition_log": deepcopy(runtime.transition_log),
        "planning_view": authority.planning_view(closed["predicate_ref"]),
        "explanation_view": authority.explanation_view(closed["event_ref"]),
    }


def run_recovery_boundary_probe_loop(
    *, p016_result: dict[str, Any] | None = None
) -> dict[str, Any]:
    authority = CognitiveAuthorityLedger(world_revision=44)
    template_ref = "process_template_fill_container"
    question = _question_predicate("template_applicability", template_ref, 44)
    trigger = adapt_cognitive_signal(
        "recovery_pattern",
        subject_refs=[template_ref],
        question_predicate_ref=question["predicate_id"],
        world_revision=44,
        depends_on_refs=["recovery_cluster_12"],
        measurements={"same_recovery": "no_source_flow", "count": 5, "window": 8},
        strength=610,
    )
    trigger_ref = authority.add_evidence(trigger)
    runtime = CognitiveInquiryRuntime(authority)
    inquiry = make_inquiry_contract(
        "process_anomaly",
        subject_refs=[template_ref],
        trigger_evidence_refs=[trigger_ref],
        candidate_hypotheses=[
            "template_source_flow_boundary_missing",
            "temporary_environment_interference",
            "flow_observation_channel_degraded",
        ],
        question_predicate_ref=question["predicate_id"],
        answer_routes=["existing_evidence", "safe_probe", "human_query"],
        authorization_scope="safe_probe",
        world_revision=44,
        depends_on_refs=[template_ref, trigger_ref, "recovery_cluster_12"],
        closure_condition="p016_dual_channel_probe_verifies_source_flow_boundary",
        fact_authority_ref=authority.ledger_id,
        expected_information_gain=0.77,
        risk_if_ignored="medium",
    )
    runtime.create(inquiry)
    runtime.admit(inquiry["inquiry_id"])
    authorization = runtime.authorize_route(
        inquiry["inquiry_id"],
        route="safe_probe",
        action_operator="retry_with_verified_stable_source_flow",
        risk="low",
    )
    p016_audit = (p016_result or {}).get("audit_summary") or {}
    p016_fact = next(
        (
            item
            for item in p016_audit.get("fact_summary", [])
            if item.get("fact_id") == "cup_has_water"
        ),
        None,
    )
    if p016_result is not None:
        if p016_audit.get("outcome") != "completed" or not p016_fact:
            raise ValueError("p016_safe_probe_did_not_establish_target_fact")
        channel_notes = json.loads(p016_fact.get("channel_notes") or "{}")
        if (
            p016_fact.get("state") != "established"
            or len(
                [value for value in channel_notes.values() if value == "established"]
            )
            < 2
        ):
            raise ValueError("p016_safe_probe_missing_independent_verification_channels")
        probe_payload = {
            "p016_outcome": p016_audit.get("outcome"),
            "verified_fact": p016_fact.get("fact_id"),
            "fact_state": p016_fact.get("state"),
            "channel_notes": channel_notes,
        }
    else:
        probe_payload = {
            "p016_outcome": "completed",
            "verified_fact": "cup_has_water",
            "fact_state": "established",
            "channel_notes": {
                "physical_liquid_level": "established",
                "digital_flow_integral": "established",
            },
        }
    boundary_predicate = make_predicate(
        "template_requires_stable_source_flow",
        [
            {"role": "template", "value_type": "literal", "value": template_ref},
            {"role": "required_condition", "value_type": "literal", "value": "stable_source_flow"},
        ],
        world_revision=44,
        modality="template_boundary",
        status="candidate",
        depends_on_refs=[template_ref, "source_flow_profile"],
    )
    verification = make_evidence_envelope(
        "safe_probe_result",
        epistemic_status="physically_verified",
        world_revision=44,
        supports_refs=[boundary_predicate["predicate_id"]],
        strength=940,
        independent_channels=2,
        physical_verification=True,
        verifier="P016",
        depends_on_refs=[template_ref, "source_flow_profile"],
        payload=probe_payload,
    )
    event = make_event(
        "safe_template_boundary_probe_completed",
        participant_refs={"template": template_ref},
        world_revision=44,
        temporal_scope="verified_transition",
        status="observed",
        produces_predicate_refs=[boundary_predicate["predicate_id"]],
        arbitration_ref=authorization["arbitration_receipt"]["arbitration_id"],
        verification_ref=verification["envelope_id"],
    )
    closed = runtime.commit_resolution(
        inquiry["inquiry_id"],
        selected_hypothesis="template_source_flow_boundary_missing",
        event=event,
        predicate=boundary_predicate,
        evidence=verification,
    )
    return {
        "loop_type": "recovery_boundary_probe",
        "recovery_cluster": {"type": "no_source_flow", "count": 5},
        "p016_runtime_receipt": probe_payload,
        "hypothesis_count": len(inquiry["candidate_hypotheses"]),
        "action": authorization,
        "closure": closed,
        "transition_log": deepcopy(runtime.transition_log),
        "planning_view": authority.planning_view(closed["predicate_ref"]),
        "explanation_view": authority.explanation_view(closed["event_ref"]),
    }


def run_concept_validation_loop(*, prediction_confirmed: bool) -> dict[str, Any]:
    authority = CognitiveAuthorityLedger(world_revision=58 if prediction_confirmed else 59)
    revision = authority.world_revision
    pattern_ref = "pattern_compliant_support_after_release"
    question = _question_predicate("pattern_predicts_stable_support", pattern_ref, revision)
    pattern_evidence_refs = []
    for index in range(3):
        evidence = adapt_cognitive_signal(
            "unexplained_repeated_pattern",
            subject_refs=[pattern_ref],
            question_predicate_ref=question["predicate_id"],
            world_revision=revision,
            depends_on_refs=[f"episode_{index}"],
            measurements={
                "episode": index,
                "shape_relation": "compliant_contact_then_stable_support",
            },
            strength=400 + index * 20,
        )
        pattern_evidence_refs.append(authority.add_evidence(evidence))
    runtime = CognitiveInquiryRuntime(authority)
    inquiry = make_inquiry_contract(
        "concept_gap",
        subject_refs=[pattern_ref],
        trigger_evidence_refs=pattern_evidence_refs,
        candidate_hypotheses=[
            "new_compliant_support_concept",
            "existing_support_concept_with_noise",
            "scene_specific_coincidence",
        ],
        question_predicate_ref=question["predicate_id"],
        answer_routes=["existing_evidence", "safe_probe"],
        authorization_scope="safe_probe",
        world_revision=revision,
        depends_on_refs=[pattern_ref, *pattern_evidence_refs],
        closure_condition="new_instance_prediction_physically_verified_or_refuted",
        fact_authority_ref=authority.ledger_id,
        expected_information_gain=0.73,
    )
    runtime.create(inquiry)
    runtime.admit(inquiry["inquiry_id"])
    candidate = make_concept(
        "concept_compliant_support_candidate",
        super_concept_refs=["concept_support_relation"],
        perceptual_invariants=["compliant_contact", "projection_inside_boundary"],
        functional_affordances=["support_payload_after_release"],
        state_predicate_refs=[question["predicate_id"]],
        lifecycle_status="validating",
        evidence_refs=pattern_evidence_refs,
    )
    authorization = runtime.authorize_route(
        inquiry["inquiry_id"],
        route="safe_probe",
        action_operator="validate_prediction_on_unseen_instance",
        risk="low",
    )
    result_predicate = make_predicate(
        "stable_support_after_release",
        [
            {"role": "instance", "value_type": "EntityRef", "value": "unseen_instance_04"},
            {"role": "predicted_by", "value_type": "Concept", "value": candidate["concept_id"]},
        ],
        world_revision=revision,
        polarity="positive" if prediction_confirmed else "negative",
        modality="perception_candidate",
        status="candidate",
        depends_on_refs=["unseen_instance_04", candidate["concept_id"]],
    )
    verification = make_evidence_envelope(
        "safe_probe_result",
        epistemic_status="physically_verified",
        world_revision=revision,
        supports_refs=[result_predicate["predicate_id"]],
        strength=930,
        independent_channels=2,
        physical_verification=True,
        verifier="P016",
        depends_on_refs=["unseen_instance_04", candidate["concept_id"]],
        payload={"support_stable": prediction_confirmed, "new_instance": True},
    )
    event = make_event(
        "candidate_concept_new_instance_probe_completed",
        participant_refs={"instance": "unseen_instance_04", "concept": candidate["concept_id"]},
        world_revision=revision,
        temporal_scope="verified_transition",
        status="observed",
        produces_predicate_refs=[result_predicate["predicate_id"]],
        arbitration_ref=authorization["arbitration_receipt"]["arbitration_id"],
        verification_ref=verification["envelope_id"],
    )
    selected = (
        "new_compliant_support_concept"
        if prediction_confirmed
        else "scene_specific_coincidence"
    )
    closed = runtime.commit_resolution(
        inquiry["inquiry_id"],
        selected_hypothesis=selected,
        event=event,
        predicate=result_predicate,
        evidence=verification,
    )
    candidate["lifecycle_status"] = "trusted" if prediction_confirmed else "rejected"
    candidate["evidence_refs"].append(verification["envelope_id"])
    decision = {
        "decision_id": stable_id(
            "concept_decision",
            {"concept": candidate["concept_id"], "evidence": verification["envelope_id"]},
        ),
        "decision": "promoted" if prediction_confirmed else "rejected",
        "basis": "new_instance_p016_verification",
        "evidence_ref": verification["envelope_id"],
        "rollback_supported": True,
        "execution_authority_granted": False,
    }
    return {
        "loop_type": "candidate_concept_validation",
        "pattern_episode_count": 3,
        "candidate": candidate,
        "action": authorization,
        "closure": closed,
        "decision": decision,
        "transition_log": deepcopy(runtime.transition_log),
        "planning_view": authority.planning_view(closed["predicate_ref"]),
        "explanation_view": authority.explanation_view(closed["event_ref"]),
    }


__all__ = [
    "COGNITIVE_SIGNAL_KINDS",
    "CognitiveInquiryRuntime",
    "adapt_cognitive_signal",
    "generate_competing_hypotheses",
    "make_inquiry_contract",
    "run_concept_validation_loop",
    "run_quality_profile_drift_loop",
    "run_recovery_boundary_probe_loop",
]
