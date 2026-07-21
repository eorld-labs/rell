from __future__ import annotations

from copy import deepcopy

import embodied_scene
from concept_core.runtime_cognitive_signals import (
    derive_runtime_cognitive_signal_candidates,
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


def main() -> None:
    validate_adapter_contract()
    validate_session_lifecycle()
    print(
        "Validated: runtime cognition thresholds, deduplication, known-operator "
        "suppression, evidence authority, no execution rights, and version invalidation."
    )


if __name__ == "__main__":
    main()
