from __future__ import annotations

from pathlib import Path

from concept_core.epistemic_flywheel import ConceptSpace, EpistemicLoopEngine, EventHistoryLedger, PatternDiscoveryEngine
from concept_core.runtime_epistemic_adapter import ingest_p016_runtime_result
from runtime_core import run_simulated_runtime_sample


ROOT = Path(__file__).resolve().parent


def main() -> None:
    ledger = EventHistoryLedger()
    for index in range(3):
        result = run_simulated_runtime_sample(ROOT / "data", "simulated_success")
        receipt = ingest_p016_runtime_result(ledger, result, run_ref=f"runtime_run_{index}", world_revision=index + 1)
        assert receipt["current_fact_authority_changed"] is False
    discovery = PatternDiscoveryEngine()
    space = ConceptSpace([{
        "concept_id": "concept_unrelated_navigation",
        "perceptual_invariants": ["route_feasible"],
        "functional_affordances": ["navigate"],
        "effects": ["executor_at_destination"],
        "applicability_constraints": ["mobile_executor"],
    }])
    engine = EpistemicLoopEngine(ledger, discovery, space)
    first = engine.tick()
    fact_inquiry = next(item for item in first["launched"] if item["pattern_signature"].startswith("p016_fact_outcome|"))
    signature = fact_inquiry["pattern_signature"]
    pattern_features = engine._pattern_features(fact_inquiry["pattern"])
    distance_before = space.nearest_neighbors(pattern_features, top_k=1)[0][1]
    resolved = engine.tick({signature: True})
    assert {item["decision"] for item in resolved["resolved"]} == {"promoted"}
    engine.admit_promoted_concept(signature, admission_ref="dictionary_admission_stage_d_verified")
    distance_after = space.nearest_neighbors(pattern_features, top_k=1)[0][1]
    assert distance_after < distance_before and distance_after == 0.0

    repeat_engine = EpistemicLoopEngine(ledger, PatternDiscoveryEngine(), space)
    repeat = repeat_engine.tick()
    explained = next(item for item in repeat["monitored"] if item["pattern_signature"] == signature)
    assert explained["already_explained_by_concept"] is True
    assert all(item["pattern_signature"] != signature for item in repeat["launched"])
    print({
        "status": "RELL认识飞轮阶段D通过",
        "runtime_history_entries": ledger.snapshot()["entry_count"],
        "concept_distance_before": distance_before,
        "concept_distance_after": distance_after,
        "repeat_inquiry_suppressed": True,
    })


if __name__ == "__main__":
    main()
