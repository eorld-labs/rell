from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import embodied_scene
from concept_core import make_evidence_envelope
from concept_core.runtime_cognitive_signals import (
    derive_runtime_cognitive_signal_candidates,
)
from concept_core.runtime_cognitive_inquiries import (
    arbitrate_compiled_inquiry,
    build_directed_inquiry_update,
    compile_signal_candidate_to_inquiry,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def diagnostic(index: int, *, world_revision: int = 0) -> dict:
    return {
        "diagnostic_id": f"diagnostic_{world_revision}_{index}",
        "category": "repeated_execution_recovery",
        "stage": "generic_stage",
        "reason": "verification_boundary_not_closed",
        "world_revision": world_revision,
    }


def episode(index: int, theme: str, *, operator: str) -> dict:
    return {
        "episode_id": f"episode_{index}",
        "operator": operator,
        "participants": {"theme": theme},
        "produces": [{"predicate": "generic_effect"}],
        "destroys": [{"predicate": "generic_prior_state"}],
        "world_revision": 0,
    }


def derive(*, diagnostics: list[dict] | None = None, episodes: list[dict] | None = None) -> list[dict]:
    return derive_runtime_cognitive_signal_candidates(
        verified_episodes=episodes or [],
        runtime_diagnostics=diagnostics or [],
        known_operators={"known_operator"},
        world_revision=0,
        fact_authority_ref="ledger_test_authority",
    )


def validate_adapter_contract() -> None:
    require(
        derive(diagnostics=[diagnostic(1), diagnostic(2)]) == [],
        "two recoveries must remain below the cognition threshold",
    )
    recoveries = derive(
        diagnostics=[diagnostic(1), diagnostic(2), diagnostic(3)]
    )
    require(
        len(recoveries) == 1
        and recoveries[0]["signal_kind"] == "recovery_pattern",
        str(recoveries),
    )
    candidate = recoveries[0]
    require(
        candidate["candidate_only"] is True
        and candidate["runtime_fact_committed"] is False
        and candidate["direct_execution_allowed"] is False
        and candidate["inquiry_created"] is False,
        str(candidate),
    )
    require(
        candidate["fact_authority_ref"]
        in candidate["trigger_evidence"]["invalidation"]["depends_on_refs"]
        and candidate["fact_authority_ref"]
        in candidate["question_predicate"]["depends_on_refs"],
        "candidate evidence and question must depend on the sole fact authority",
    )
    known = [
        episode(1, "entity_a", operator="known_operator"),
        episode(2, "entity_b", operator="known_operator"),
        episode(3, "entity_a", operator="known_operator"),
    ]
    require(
        derive(episodes=known) == [],
        "known operator repetition must not invent a concept candidate",
    )
    unknown = [
        episode(1, "entity_a", operator="unknown_operator"),
        episode(2, "entity_b", operator="unknown_operator"),
        episode(3, "entity_a", operator="unknown_operator"),
    ]
    unexplained = derive(episodes=unknown)
    require(
        len(unexplained) == 1
        and unexplained[0]["signal_kind"] == "unexplained_repeated_pattern"
        and {"entity_a", "entity_b"}.issubset(unexplained[0]["subject_refs"]),
        str(unexplained),
    )


def validate_signal_to_inquiry_bridge() -> None:
    recoveries = derive(
        diagnostics=[diagnostic(1), diagnostic(2), diagnostic(3)]
    )
    compiled = compile_signal_candidate_to_inquiry(recoveries[0])
    contract = compiled["inquiry_contract"]
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "schemas" / "inquiry_contract.schema.json")
        .read_text(encoding="utf-8")
    )
    missing_schema_fields = set(schema["required"]) - set(contract)
    unknown_schema_fields = set(contract) - set(schema["properties"])
    require(
        not missing_schema_fields
        and not unknown_schema_fields
        and contract["gap_type"] == "process_anomaly"
        and len(contract["candidate_hypotheses"]) >= 2
        and contract["world_revision"] == recoveries[0]["world_revision"]
        and contract["fact_authority_ref"] == recoveries[0]["fact_authority_ref"]
        and compiled["directed_update_target"]
        == "process_template_boundary_candidate"
        and compiled["runtime_fact_committed"] is False
        and compiled["direct_execution_allowed"] is False,
        str(compiled),
    )
    passive = arbitrate_compiled_inquiry(
        compiled,
        task_active=True,
        natural_observation_expected=True,
    )
    require(
        passive["selected_route"] == "passive_observation"
        and passive["route_candidate"] is None
        and passive["runtime_fact_committed"] is False,
        str(passive),
    )
    probe = arbitrate_compiled_inquiry(
        compiled,
        task_active=False,
        natural_observation_expected=False,
    )
    require(
        probe["selected_route"] == "safe_probe"
        and probe["status"] == "admitted_pending_p018"
        and probe["route_candidate"]["candidate_only"] is True
        and probe["route_candidate"]["control_gateway"] == "P018"
        and probe["route_candidate"]["verification_gateway"] == "P016"
        and probe["route_candidate"]["direct_execution_allowed"] is False,
        str(probe),
    )
    human_report = make_evidence_envelope(
        "human_report",
        epistemic_status="reported",
        world_revision=contract["world_revision"],
        supports_refs=[contract["question_predicate_ref"]],
        strength=320,
        depends_on_refs=contract["depends_on_refs"],
        payload={"reported_answer": "process_template_boundary_missing"},
    )
    report_update = build_directed_inquiry_update(
        compiled,
        selected_hypothesis="process_template_boundary_missing",
        answer_evidence=human_report,
    )
    require(
        report_update["directed_update_target"]
        == "process_template_boundary_candidate"
        and report_update["ready_for_target_gateway"] is False
        and report_update["runtime_fact_committed"] is False,
        str(report_update),
    )
    verified = make_evidence_envelope(
        "safe_probe_result",
        epistemic_status="physically_verified",
        world_revision=contract["world_revision"],
        supports_refs=[contract["question_predicate_ref"]],
        strength=920,
        independent_channels=2,
        physical_verification=True,
        verifier="P016",
        depends_on_refs=contract["depends_on_refs"],
        payload={"template_boundary_reproduced": True},
    )
    verified_update = build_directed_inquiry_update(
        compiled,
        selected_hypothesis="process_template_boundary_missing",
        answer_evidence=verified,
    )
    require(
        verified_update["ready_for_target_gateway"] is True
        and verified_update["target_gateway"] == "process_template_registry"
        and verified_update["candidate_only"] is True
        and verified_update["runtime_fact_committed"] is False,
        str(verified_update),
    )
    stale = deepcopy(compiled)
    stale["current_world_usable"] = False
    try:
        arbitrate_compiled_inquiry(
            stale,
            task_active=False,
            natural_observation_expected=False,
        )
    except ValueError as exc:
        require(
            str(exc) == "expired_inquiry_cannot_trigger_action",
            str(exc),
        )
    else:
        raise AssertionError("stale inquiry generated an action candidate")

    first_pattern = derive(
        episodes=[
            episode(1, "renamed_entity_alpha", operator="novel_relation"),
            episode(2, "renamed_entity_beta", operator="novel_relation"),
            episode(3, "renamed_entity_alpha", operator="novel_relation"),
        ]
    )[0]
    second_pattern = derive(
        episodes=[
            episode(4, "unseen_entity_one", operator="novel_relation"),
            episode(5, "unseen_entity_two", operator="novel_relation"),
            episode(6, "unseen_entity_one", operator="novel_relation"),
        ]
    )[0]
    first_inquiry = compile_signal_candidate_to_inquiry(first_pattern)
    second_inquiry = compile_signal_candidate_to_inquiry(second_pattern)
    require(
        first_pattern["pattern_key"] == second_pattern["pattern_key"]
        and first_inquiry["question_predicate"]["predicate_id"]
        == second_inquiry["question_predicate"]["predicate_id"]
        and first_inquiry["inquiry_contract"]["candidate_hypotheses"]
        == second_inquiry["inquiry_contract"]["candidate_hypotheses"]
        and first_inquiry["directed_update_target"] == "concept_candidate",
        "concept inquiry changed when only instance identities changed",
    )


def validate_session_lifecycle() -> None:
    view = embodied_scene.start_session(
        executor_profile_id="home_humanoid",
        scene_id="home_semantic_3d_a",
    )
    session = embodied_scene.SESSIONS[view["session_id"]]
    session["runtime_diagnostic_history"] = [
        diagnostic(1),
        diagnostic(2),
        diagnostic(3),
    ]
    first = embodied_scene._refresh_runtime_cognitive_signal_candidates(
        session, reason="validator_first_scan"
    )
    second = embodied_scene._refresh_runtime_cognitive_signal_candidates(
        session, reason="validator_duplicate_scan"
    )
    require(len(first) == 1 and len(second) == 1, str(second))
    require(
        len(session["cognitive_inquiry_working_set"]) == 1
        and session["cognitive_inquiry_working_set"][0]["lifecycle_status"]
        == "admitted_pending_p018",
        str(session["cognitive_inquiry_working_set"]),
    )
    original = deepcopy(second[0])
    require(
        original["current_world_usable"] is True
        and original["lifecycle_status"] == "current_candidate",
        str(original),
    )

    session["state"]["active_region"] = "validator_changed_region"
    rebound = embodied_scene._refresh_runtime_cognitive_signal_candidates(
        session, reason="validator_same_revision_authority_change"
    )
    require(len(rebound) == 2, str(rebound))
    require(
        sum(item["current_world_usable"] is True for item in rebound) == 1
        and sum(item["current_world_usable"] is False for item in rebound) == 1,
        "authority replacement in one revision must stale the old candidate and bind a new one",
    )
    require(
        len(session["cognitive_inquiry_working_set"]) == 2
        and sum(
            item["current_world_usable"] is True
            for item in session["cognitive_inquiry_working_set"]
        )
        == 1
        and sum(
            item["lifecycle_status"] == "invalidated"
            for item in session["cognitive_inquiry_working_set"]
        )
        == 1,
        str(session["cognitive_inquiry_working_set"]),
    )

    session["world_revision"] = 1
    session["runtime_diagnostic_history"].extend(
        [diagnostic(1, world_revision=1), diagnostic(2, world_revision=1), diagnostic(3, world_revision=1)]
    )
    revised = embodied_scene._refresh_runtime_cognitive_signal_candidates(
        session, reason="validator_world_revision_change"
    )
    require(len(revised) == 3, str(revised))
    stale = [
        item
        for item in revised
        if item["world_revision"] == 0
        and item["fact_authority_ref"] == original["fact_authority_ref"]
    ][0]
    current = [item for item in revised if item["world_revision"] == 1][0]
    require(
        stale["current_world_usable"] is False
        and stale["invalidated_by_world_change"] is True
        and stale["lifecycle_status"] == "stale_candidate",
        str(stale),
    )
    require(
        current["current_world_usable"] is True
        and current["fact_authority_ref"]
        == session["world_fact_ledger"]["ledger_id"]
        and current["signal_candidate_id"] != original["signal_candidate_id"],
        str(current),
    )


def validate_diagnostic_auto_trigger() -> None:
    view = embodied_scene.start_session(
        executor_profile_id="home_humanoid",
        scene_id="home_semantic_3d_a",
    )
    session = embodied_scene.SESSIONS[view["session_id"]]
    for _ in range(3):
        embodied_scene._attach_runtime_diagnostic(
            {
                "status": "verification_failed",
                "reason": "repeatable_generic_boundary",
            },
            session,
            {"stage_id": "generic_stage"},
        )
    inquiries = session["cognitive_inquiry_working_set"]
    require(
        len(inquiries) == 1
        and inquiries[0]["inquiry_contract"]["gap_type"] == "process_anomaly"
        and inquiries[0]["source_signal_candidate_ref"]
        == session["cognitive_signal_candidates"][0]["signal_candidate_id"]
        and inquiries[0]["runtime_fact_committed"] is False,
        str(inquiries),
    )


def main() -> None:
    validate_adapter_contract()
    validate_signal_to_inquiry_bridge()
    validate_session_lifecycle()
    validate_diagnostic_auto_trigger()
    print(
        "Validated: runtime cognition thresholds, diagnostic auto-trigger, "
        "signal-to-inquiry compilation, "
        "minimum-disturbance arbitration, rename invariance, evidence authority, "
        "no execution rights, and version invalidation."
    )


if __name__ == "__main__":
    main()
