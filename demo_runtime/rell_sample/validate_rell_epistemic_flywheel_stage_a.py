from __future__ import annotations

from concept_core.epistemic_flywheel import ConceptSpace, EventHistoryLedger
from concept_core.rcir_primitives import make_evidence_envelope, make_event, make_predicate


def main() -> None:
    ledger = EventHistoryLedger()
    predicate = make_predicate("stable_support", [], world_revision=3, status="candidate")
    evidence = make_evidence_envelope("p016_physical_verification", epistemic_status="physically_verified", world_revision=3, supports_refs=[predicate["predicate_id"]], strength=900, independent_channels=2, physical_verification=True, verifier="P016")
    event = make_event("support_probe_completed", participant_refs={"theme": "entity_a"}, world_revision=3, temporal_scope="verified_transition", status="observed", produces_predicate_refs=[predicate["predicate_id"]], verification_ref=evidence["envelope_id"])
    for item in (predicate, evidence, event):
        ledger.append(item)
    snapshot = ledger.snapshot()
    assert snapshot["entry_count"] == 3 and snapshot["append_only"] is True
    assert len(list(ledger.replay(3))) == 3
    assert len(ledger.query(participant_ref="entity_a")) == 1
    entries = list(ledger.replay())
    assert entries[1]["previous_digest"] == entries[0]["entry_digest"]
    assert entries[2]["previous_digest"] == entries[1]["entry_digest"]

    base = {
        "concept_id": "concept_support_base",
        "perceptual_invariants": ["contact", "inside_boundary"],
        "functional_affordances": ["support_payload"],
        "effects": ["stable_support"],
        "applicability_constraints": ["low_risk"],
    }
    close = {**base, "concept_id": "concept_support_close", "perceptual_invariants": ["contact", "inside_boundary", "compliant"]}
    remote = {
        "concept_id": "concept_remote",
        "perceptual_invariants": ["visual_marker"],
        "functional_affordances": ["emit_signal"],
        "effects": ["signal_visible"],
        "applicability_constraints": ["powered"],
    }
    space = ConceptSpace([base, close, remote])
    nearest = space.nearest_neighbors(close, top_k=2)
    assert nearest[0][0] == "concept_support_close" and nearest[0][1] == 0.0
    merge = space.propose_merge("concept_support_base", "concept_support_close", threshold=0.2)
    assert merge and merge["direct_dictionary_write_allowed"] is False
    split = space.propose_split("concept_support_base", [base, remote], threshold=0.6)
    assert split and split["direct_dictionary_write_allowed"] is False
    new_ref = space.add_concept({**close, "concept_id": "concept_new"}, admission_ref="dictionary_admission_verified")
    assert space.concepts[new_ref]["dictionary_authority_admission_ref"] == "dictionary_admission_verified"
    print("RELL 认识飞轮阶段A校验通过：事件历史哈希链与概念空间距离/合并/分裂候选均已落地。")


if __name__ == "__main__":
    main()
