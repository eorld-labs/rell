from __future__ import annotations

from concept_core.social_relation_grounding import project_social_relation_candidates
from embodied_scene import SESSIONS, _compose_session_language, start_session


def project(utterance: str) -> dict:
    started = start_session("home_humanoid", "hospitality_guest")
    analysis = _compose_session_language(SESSIONS[started["session_id"]], utterance)
    candidates = project_social_relation_candidates(analysis, world_revision=11)
    assert len(candidates) == 1, (utterance, analysis, candidates)
    return candidates[0]


def main() -> None:
    held = project("杯子还在我手里")
    assert held["predicate"] == "held_by"
    assert "p016_physical_verification" in held["required_evidence"]

    owned = project("这是我的杯子")
    assert owned["predicate"] == "owned_by"
    assert owned["evidence_class"] == "social_context"

    accessible = project("我能够得到这个杯子")
    assert accessible["predicate"] == "accessible_to"
    assert accessible["required_evidence"] == ["current_reachability_verification", "permission_policy_verification"]

    for candidate in (held, owned, accessible):
        assert candidate["fact_commit_eligible"] is False
        assert candidate["runtime_fact_committed"] is False
        assert candidate["direct_execution_allowed"] is False
        assert candidate["fact_authority"] == "WorldFactLedger"
    print("RELL 社会关系落地校验通过：持有、所有权和可达性报告均保持候选与证据门。")


if __name__ == "__main__":
    main()
