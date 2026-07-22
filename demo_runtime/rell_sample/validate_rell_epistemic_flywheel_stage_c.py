from __future__ import annotations

from concept_core.epistemic_flywheel import ConceptSpace, EpistemicLoopEngine, EventHistoryLedger, PatternDiscoveryEngine
from concept_core.rcir_primitives import make_event


def main() -> None:
    ledger = EventHistoryLedger()
    for index in range(3):
        event = make_event("novel_release_pattern", participant_refs={"support": f"support_{index}", "payload": f"payload_{index}"}, world_revision=index + 1, temporal_scope="verified_transition", status="observed")
        event["measurements"] = {"features": ["compliant_contact", "inside_boundary"], "effects": ["stable_support_after_release"], "strength": 0.8}
        ledger.append(event)
    space = ConceptSpace([{
        "concept_id": "concept_remote_signal",
        "perceptual_invariants": ["visual_marker"],
        "functional_affordances": ["emit_signal"],
        "effects": ["signal_visible"],
        "applicability_constraints": ["powered"],
    }])
    engine = EpistemicLoopEngine(ledger, PatternDiscoveryEngine(), space)
    first = engine.tick()
    assert len(first["launched"]) == 1
    inquiry = first["launched"][0]
    assert inquiry["status"] == "awaiting_p018_authorized_probe"
    assert inquiry["direct_execution_allowed"] is False
    signature = inquiry["pattern_signature"]
    before_count = len(space.concepts)
    second = engine.tick({signature: True})
    assert second["resolved"] == [{"pattern_signature": signature, "decision": "promoted"}]
    assert signature in second["pending_dictionary_admission"]
    assert len(space.concepts) == before_count
    concept_ref = engine.admit_promoted_concept(signature, admission_ref="dictionary_admission_verified_stage_c")
    assert len(space.concepts) == before_count + 1
    assert space.concepts[concept_ref]["dictionary_authority_admission_ref"] == "dictionary_admission_verified_stage_c"
    assert first["fact_authority"] == "WorldFactLedger"
    assert first["control_gateway"] == "P018" and first["verification_gateway"] == "P016"
    assert 0.2 <= second["meta_params"]["min_investigation_score"] <= 0.95
    print("RELL 认识飞轮阶段C校验通过：L4已完成模式选择、P018/P016探针、待准入晋级和有界元学习。")


if __name__ == "__main__":
    main()
