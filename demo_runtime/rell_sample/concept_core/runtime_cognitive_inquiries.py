from __future__ import annotations

from copy import deepcopy
from typing import Any

from .cognitive_inquiry import make_inquiry_contract
from .rcir_primitives import assert_shared_authority_contract, stable_id, validate_primitive


SIGNAL_INQUIRY_POLICIES: dict[str, dict[str, Any]] = {
    "recovery_pattern": {
        "gap_type": "process_anomaly",
        "authorization_scope": "safe_probe",
        "closure_condition": (
            "qualified_evidence_distinguishes_template_boundary_from_"
            "environment_or_verification_failure"
        ),
        "update_target": "process_template_boundary_candidate",
        "risk_if_ignored": "medium",
        "acquisition_cost": "medium",
    },
    "unexplained_repeated_pattern": {
        "gap_type": "concept_gap",
        "authorization_scope": "safe_probe",
        "closure_condition": (
            "prediction_on_a_distinct_instance_is_physically_verified_or_refuted"
        ),
        "update_target": "concept_candidate",
        "risk_if_ignored": "low",
        "acquisition_cost": "medium",
    },
    "quality_profile_drift": {
        "gap_type": "model_drift",
        "authorization_scope": "observe_only",
        "closure_condition": "two_independent_channels_distinguish_drift_cause",
        "update_target": "quality_profile_candidate",
        "risk_if_ignored": "medium",
        "acquisition_cost": "low",
    },
    "fact_lifecycle_gap": {
        "gap_type": "lifecycle_question",
        "authorization_scope": "observe_only",
        "closure_condition": "current_qualified_evidence_confirms_or_invalidates_fact",
        "update_target": "world_fact_candidate",
        "risk_if_ignored": "medium",
        "acquisition_cost": "low",
    },
}


def compile_signal_candidate_to_inquiry(
    signal_candidate: dict[str, Any],
) -> dict[str, Any]:
    """Compile a non-authoritative runtime signal into a structured inquiry."""
    if signal_candidate.get("candidate_only") is not True:
        raise ValueError("cognitive_signal_must_remain_candidate")
    if signal_candidate.get("runtime_fact_committed") is not False:
        raise PermissionError("cognitive_signal_cannot_commit_runtime_fact")
    if signal_candidate.get("current_world_usable") is not True:
        raise ValueError("stale_cognitive_signal_cannot_create_inquiry")
    policy = SIGNAL_INQUIRY_POLICIES.get(signal_candidate.get("signal_kind"))
    if not policy:
        raise ValueError("cognitive_signal_has_no_inquiry_policy")
    question = deepcopy(signal_candidate.get("question_predicate") or {})
    trigger = deepcopy(signal_candidate.get("trigger_evidence") or {})
    if not validate_primitive(question).get("valid"):
        raise ValueError("inquiry_question_predicate_invalid")
    if not validate_primitive(trigger).get("valid"):
        raise ValueError("inquiry_trigger_evidence_invalid")
    revision = int(signal_candidate.get("world_revision", -1))
    authority_ref = str(signal_candidate.get("fact_authority_ref") or "")
    if (
        question.get("world_revision") != revision
        or trigger.get("world_revision") != revision
        or authority_ref not in signal_candidate.get("depends_on_refs", [])
    ):
        raise ValueError("inquiry_inputs_do_not_share_world_authority")
    if question.get("predicate_id") not in trigger.get("supports_refs", []):
        raise ValueError("trigger_evidence_does_not_support_inquiry_question")
    strength = int(trigger.get("strength", 0))
    information_gain = max(0.35, min(0.9, strength / 1000.0))
    contract = make_inquiry_contract(
        policy["gap_type"],
        subject_refs=signal_candidate.get("subject_refs", []),
        trigger_evidence_refs=[trigger["envelope_id"]],
        candidate_hypotheses=signal_candidate.get("candidate_hypotheses", []),
        question_predicate_ref=question["predicate_id"],
        answer_routes=signal_candidate.get("answer_routes", []),
        authorization_scope=policy["authorization_scope"],
        world_revision=revision,
        depends_on_refs=[
            authority_ref,
            signal_candidate["signal_candidate_id"],
            *signal_candidate.get("depends_on_refs", []),
        ],
        closure_condition=policy["closure_condition"],
        fact_authority_ref=authority_ref,
        expected_information_gain=information_gain,
        risk_if_ignored=policy["risk_if_ignored"],
        acquisition_cost=policy["acquisition_cost"],
    )
    return {
        "compiled_inquiry_id": stable_id(
            "compiled_inquiry",
            {
                "inquiry": contract["inquiry_id"],
                "signal": signal_candidate["signal_candidate_id"],
            },
        ),
        "source_signal_candidate_ref": signal_candidate["signal_candidate_id"],
        "pattern_key": signal_candidate.get("pattern_key"),
        "question_predicate": question,
        "trigger_evidence": trigger,
        "inquiry_contract": contract,
        "directed_update_target": policy["update_target"],
        "world_revision": revision,
        "fact_authority_ref": authority_ref,
        "lifecycle_status": "compiled_candidate",
        "current_world_usable": True,
        "candidate_only": True,
        "runtime_fact_committed": False,
        "control_gateway": "P018",
        "verification_gateway": "P016",
        "direct_execution_allowed": False,
    }


def arbitrate_compiled_inquiry(
    compiled: dict[str, Any],
    *,
    task_active: bool,
    natural_observation_expected: bool,
    qualified_answer_evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Select the least disruptive available evidence route without executing it."""
    assert_shared_authority_contract(compiled)
    if compiled.get("current_world_usable") is not True:
        raise ValueError("expired_inquiry_cannot_trigger_action")
    contract = deepcopy(compiled["inquiry_contract"])
    routes = contract.get("answer_routes", [])
    answer_refs = list(dict.fromkeys(qualified_answer_evidence_refs or []))
    selected_route: str | None = None
    reason: str
    if answer_refs and "existing_evidence" in routes:
        selected_route = "existing_evidence"
        reason = "qualified_existing_evidence_available"
    elif natural_observation_expected and "passive_observation" in routes:
        selected_route = "passive_observation"
        reason = "task_expected_to_produce_relevant_evidence"
    elif not task_active and "active_observation" in routes:
        selected_route = "active_observation"
        reason = "low_interference_active_observation_candidate"
    elif not task_active and "safe_probe" in routes:
        selected_route = "safe_probe"
        reason = "idle_window_allows_safe_probe_candidate"
    elif "human_query" in routes and contract.get("expected_information_gain", 0) >= 0.6:
        selected_route = "human_query"
        reason = "human_has_high_value_unavailable_distinguishing_evidence"
    else:
        reason = "deferred_to_avoid_task_interference_or_low_value_acquisition"

    if selected_route == "existing_evidence":
        status = "resolved_pending_shared_ledger_verification"
    elif selected_route == "passive_observation":
        status = "observing"
    elif selected_route == "human_query":
        status = "awaiting_human"
    elif selected_route in {"active_observation", "safe_probe"}:
        status = "admitted_pending_p018"
    else:
        status = "deferred"
    contract["status"] = (
        status if status in {"observing", "awaiting_human", "deferred"} else "admitted"
    )
    route_candidate = None
    if selected_route in {"active_observation", "safe_probe"}:
        route_candidate = {
            "action_candidate_id": stable_id(
                "inquiry_route",
                {
                    "inquiry": contract["inquiry_id"],
                    "route": selected_route,
                    "world_revision": contract["world_revision"],
                },
            ),
            "inquiry_ref": contract["inquiry_id"],
            "route": selected_route,
            "authorization_scope": contract["authorization_scope"],
            "world_revision": contract["world_revision"],
            "fact_authority_ref": contract["fact_authority_ref"],
            "candidate_only": True,
            "runtime_fact_committed": False,
            "control_gateway": "P018",
            "verification_gateway": "P016",
            "direct_execution_allowed": False,
        }
        assert_shared_authority_contract(route_candidate)
    return {
        "decision_id": stable_id(
            "inquiry_arbitration",
            {
                "inquiry": contract["inquiry_id"],
                "route": selected_route or "deferred",
                "world_revision": contract["world_revision"],
            },
        ),
        "inquiry_ref": contract["inquiry_id"],
        "status": status,
        "selected_route": selected_route,
        "reason": reason,
        "qualified_answer_evidence_refs": answer_refs,
        "route_candidate": route_candidate,
        "updated_inquiry_contract": contract,
        "fact_authority_ref": contract["fact_authority_ref"],
        "control_gateway": "P018",
        "verification_gateway": "P016",
        "direct_execution_allowed": False,
        "runtime_fact_committed": False,
    }


def build_directed_inquiry_update(
    compiled: dict[str, Any],
    *,
    selected_hypothesis: str,
    answer_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Route an answer to one declared knowledge target without committing it."""
    assert_shared_authority_contract(compiled)
    if compiled.get("current_world_usable") is not True:
        raise ValueError("invalidated_inquiry_cannot_accept_answer")
    contract = compiled["inquiry_contract"]
    if selected_hypothesis not in contract.get("candidate_hypotheses", []):
        raise ValueError("selected_hypothesis_not_declared")
    validation = validate_primitive(answer_evidence)
    if not validation.get("valid") or answer_evidence.get("type") != "EvidenceEnvelope":
        raise ValueError("inquiry_answer_requires_evidence_envelope")
    if answer_evidence.get("world_revision") != contract.get("world_revision"):
        raise ValueError("inquiry_answer_world_revision_mismatch")
    if contract.get("question_predicate_ref") not in answer_evidence.get(
        "supports_refs", []
    ):
        raise ValueError("answer_evidence_does_not_address_inquiry_question")
    target = compiled["directed_update_target"]
    qualification = answer_evidence.get("qualification") or {}
    physically_verified = bool(
        qualification.get("physical_verification") is True
        and qualification.get("verifier") == "P016"
    )
    corroborated = bool(
        answer_evidence.get("epistemic_status") == "corroborated"
        and int(qualification.get("independent_channels", 0)) >= 2
    )
    if target == "world_fact_candidate":
        ready = answer_evidence.get("fact_commit_eligible") is True
        disposition = (
            "ready_for_fact_authority_submission"
            if ready
            else "insufficient_for_world_fact_submission"
        )
    else:
        ready = physically_verified or corroborated
        disposition = (
            "ready_for_domain_candidate_update"
            if ready
            else "retain_hypothesis_and_collect_more_evidence"
        )
    return {
        "update_proposal_id": stable_id(
            "inquiry_update",
            {
                "inquiry": contract["inquiry_id"],
                "hypothesis": selected_hypothesis,
                "evidence": answer_evidence["envelope_id"],
                "target": target,
            },
        ),
        "inquiry_ref": contract["inquiry_id"],
        "selected_hypothesis": selected_hypothesis,
        "answer_evidence_ref": answer_evidence["envelope_id"],
        "directed_update_target": target,
        "disposition": disposition,
        "ready_for_target_gateway": ready,
        "target_gateway": {
            "world_fact_candidate": "WorldFactLedger",
            "process_template_boundary_candidate": "process_template_registry",
            "concept_candidate": "P012_P019_concept_lifecycle",
            "quality_profile_candidate": "quality_profile_registry",
        }[target],
        "candidate_only": True,
        "runtime_fact_committed": False,
        "control_gateway": "P018",
        "verification_gateway": "P016",
        "direct_execution_allowed": False,
    }


def refresh_runtime_inquiries(
    *,
    signal_candidates: list[dict[str, Any]],
    stored_inquiries: list[dict[str, Any]],
    world_revision: int,
    fact_authority_ref: str,
    task_active: bool,
    natural_observation_expected: bool,
) -> list[dict[str, Any]]:
    """Maintain a bounded, versioned inquiry working set for one session."""
    current_keys: set[tuple[str, int, str]] = set()
    for item in stored_inquiries:
        is_current = bool(
            item.get("world_revision") == world_revision
            and item.get("fact_authority_ref") == fact_authority_ref
        )
        item["current_world_usable"] = is_current
        if not is_current and item.get("lifecycle_status") != "closed":
            item["lifecycle_status"] = "invalidated"
            item["invalidation_reason"] = "world_revision_or_fact_authority_changed"
            contract = item.get("inquiry_contract") or {}
            contract["status"] = "invalidated"
            contract["invalidation_reason"] = item["invalidation_reason"]
            contract["invalidated_at_world_revision"] = world_revision
        current_keys.add(
            (
                str(item.get("source_signal_candidate_ref")),
                int(item.get("world_revision", -1)),
                str(item.get("fact_authority_ref")),
            )
        )
    for signal in signal_candidates:
        if signal.get("current_world_usable") is not True:
            continue
        key = (
            str(signal.get("signal_candidate_id")),
            int(signal.get("world_revision", -1)),
            str(signal.get("fact_authority_ref")),
        )
        if key in current_keys:
            continue
        compiled = compile_signal_candidate_to_inquiry(signal)
        arbitration = arbitrate_compiled_inquiry(
            compiled,
            task_active=task_active,
            natural_observation_expected=natural_observation_expected,
        )
        compiled["inquiry_contract"] = arbitration["updated_inquiry_contract"]
        compiled["arbitration"] = arbitration
        compiled["lifecycle_status"] = arbitration["status"]
        stored_inquiries.append(compiled)
        current_keys.add(key)
    if len(stored_inquiries) > 32:
        del stored_inquiries[:-32]
    return deepcopy(stored_inquiries)


__all__ = [
    "SIGNAL_INQUIRY_POLICIES",
    "arbitrate_compiled_inquiry",
    "build_directed_inquiry_update",
    "compile_signal_candidate_to_inquiry",
    "refresh_runtime_inquiries",
]
