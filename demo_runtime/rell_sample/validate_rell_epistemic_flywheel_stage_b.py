from __future__ import annotations

from concept_core.epistemic_flywheel import EventHistoryLedger, PatternDiscoveryEngine
from concept_core.rcir_primitives import make_event


def main() -> None:
    ledger = EventHistoryLedger()
    for index, (instance, features, strength) in enumerate((
        ("tray_a", ["compliant_contact", "inside_boundary"], 0.62),
        ("tray_b", ["compliant_contact", "inside_boundary"], 0.70),
        ("tray_c", ["compliant_contact", "inside_boundary", "textured_surface"], 0.78),
    )):
        event = make_event(
            "payload_release_completed",
            participant_refs={"support": instance, "payload": f"payload_{index}"},
            world_revision=index + 1,
            temporal_scope="verified_transition",
            status="observed",
        )
        event["measurements"] = {
            "features": features,
            "effects": ["stable_support_after_release"],
            "strength": strength,
        }
        ledger.append(event)
    engine = PatternDiscoveryEngine()
    engine.ingest_ledger(ledger)
    patterns = engine.query_active_patterns(min_strength=0.6)
    assert len(patterns) == 1
    pattern = patterns[0]
    assert pattern["observed_episodes"] == 3
    assert pattern["cross_instance_count"] == 6
    assert pattern["cross_instance_consistency"] == 2 / 3
    assert pattern["stable_features"] == ["compliant_contact", "inside_boundary"]
    assert pattern["variable_features"] == ["textured_surface"]
    assert pattern["stable_effects"] == ["stable_support_after_release"]
    assert pattern["strength_trend"] == "rising"
    assert pattern["candidate_only"] is True and pattern["runtime_fact_committed"] is False
    assert engine.query_active_patterns(min_strength=0.9) == []
    print("RELL 认识飞轮阶段B校验通过：L1事件已增量形成频率、一致性、稳定/变量特征和强度趋势。")


if __name__ == "__main__":
    main()
