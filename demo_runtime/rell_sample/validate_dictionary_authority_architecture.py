from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from concept_core.cognitive_ir import assert_no_surface_text_below_rcir_boundary
from concept_core.dictionary_authority import (
    assert_dictionary_authority_boundary,
    build_dictionary_authority_admission,
    invalidate_dictionary_authority_admission,
)
from concept_core.dictionary_equivalence import build_dictionary_equivalence_receipt
from concept_core.dictionary_frontend import project_analysis_to_machine_dictionary
from embodied_scene import (
    SESSIONS,
    _compose_session_language,
    set_stool,
    start_session,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = (
    ROOT
    / "demo_runtime"
    / "output"
    / "rell_sample"
    / "dictionary_authority"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def compact_case(case_id: str, analysis: dict) -> dict:
    admission = analysis["dictionary_authority_admission"]
    situated = analysis["rcir"]["situated_event_graph"]
    return {
        "case_id": case_id,
        "admission_id": admission["admission_id"],
        "admission_status": admission["admission_status"],
        "semantic_source": admission["authoritative_semantic_source"],
        "fallback_reasons": admission["fallback_reasons"],
        "speech_act": situated.get("speech_act"),
        "operators": [item.get("operator") for item in situated.get("events", [])],
        "reported_event_types": [
            item.get("event_type") for item in situated.get("reported_events", [])
        ],
        "runtime_fact_committed": False,
    }


def main() -> None:
    for schema_name in (
        "dictionary_authority_admission.schema.json",
        "rcir_bundle.schema.json",
    ):
        json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))

    started = start_session("home_humanoid", "hospitality_guest")
    session = SESSIONS[started["session_id"]]
    cases = []

    direct = _compose_session_language(session, "把白色马克杯放到操作台A")
    direct_admission = direct["dictionary_authority_admission"]
    require(
        direct_admission["admission_status"] == "admitted"
        and direct["rcir"]["semantic_authority"][
            "authoritative_semantic_source"
        ]
        == "machine_dictionary",
        f"known command did not enter dictionary authority: {direct_admission}",
    )
    require(
        direct["rcir"]["situated_event_graph"]["authority"][
            "admission_ref"
        ]
        == direct_admission["admission_id"],
        "situated graph did not retain the exact admission reference",
    )
    assert_no_surface_text_below_rcir_boundary(direct["rcir"])
    cases.append(compact_case("direct_place", direct))

    compound = _compose_session_language(
        session,
        "把白色马克杯放到操作台A，然后用透明高脚玻璃杯接一杯水",
    )
    require(
        compound["dictionary_authority_admission"]["admission_status"]
        == "admitted",
        "compound discourse did not enter dictionary authority",
    )
    require(
        [
            item["operator"]
            for item in compound["rcir"]["situated_event_graph"]["events"]
        ]
        == ["place_object", "fill_container"],
        "compound event order changed below dictionary admission",
    )
    require(
        compound["situated_event_frame"]["generated_from_rcir_only"] is True
        and compound["situated_event_frame"]["surface_text_reparsed"] is False
        and compound["runtime_semantic_authority_ref"]
        == compound["dictionary_authority_admission"]["admission_id"]
        and compound["rule_evaluation"]["legacy_semantic_fields_read"] is False
        and all("utterance" not in frame for frame in compound["event_frames"]),
        "a downstream semantic or event-frame compatibility path bypassed admission",
    )
    cases.append(compact_case("compound_sequence", compound))

    query = _compose_session_language(session, "桌子上有什么")
    require(
        query["dictionary_authority_admission"]["admission_status"] == "admitted"
        and query["rcir"]["situated_event_graph"]["query"]["query_type"]
        == "support_inventory",
        "typed state query did not survive dictionary admission",
    )
    cases.append(compact_case("state_query", query))

    report = _compose_session_language(session, "我喝完了")
    report_graph = report["rcir"]["situated_event_graph"]
    require(
        report["dictionary_authority_admission"]["admission_status"] == "admitted"
        and report_graph["speech_act"] == "information_report"
        and report_graph["reported_events"]
        and all(
            item["physical_fact_committed"] is False
            for item in report_graph["reported_events"]
        ),
        "human report was lost or promoted to a physical fact",
    )
    cases.append(compact_case("human_information_report", report))

    projection = deepcopy(direct["machine_dictionary_projection"])
    receipt = deepcopy(direct["machine_dictionary_equivalence"])
    tampered = deepcopy(receipt)
    tampered["status"] = "divergent"
    tampered["eligible_for_authority_promotion"] = False
    rejected = build_dictionary_authority_admission(
        direct,
        projection,
        tampered,
        world_revision=session["world_revision"],
    )
    require(
        rejected["admission_status"] == "fallback"
        and "equivalence_not_established" in rejected["fallback_reasons"],
        "tampered equivalence receipt was admitted",
    )

    ambiguous = deepcopy(projection)
    ambiguous["interpretation_lattice"]["status"] = "unresolved"
    ambiguous["interpretation_lattice"][
        "authoritative_semantic_graph_emitted"
    ] = False
    ambiguity_rejected = build_dictionary_authority_admission(
        direct,
        ambiguous,
        receipt,
        world_revision=session["world_revision"],
    )
    require(
        ambiguity_rejected["admission_status"] == "fallback"
        and "interpretation_lattice_not_resolved"
        in ambiguity_rejected["fallback_reasons"],
        "ambiguous lattice silently became authoritative",
    )

    projection_tamper = deepcopy(projection)
    projection_tamper["semantic_payload"]["canonical_frame"][
        "goal_relation"
    ] = "tampered_goal"
    projection_tamper_rejected = build_dictionary_authority_admission(
        direct,
        projection_tamper,
        receipt,
        world_revision=session["world_revision"],
    )
    require(
        projection_tamper_rejected["admission_status"] == "fallback"
        and "equivalence_projection_digest_mismatch"
        in projection_tamper_rejected["fallback_reasons"],
        "projection changed after equivalence receipt issuance was admitted",
    )

    recovery_projection = deepcopy(projection)
    recovery_projection["recovery_context_projection"] = {
        "status": "active",
        "world_revision": session["world_revision"],
    }
    recovery_rejected = build_dictionary_authority_admission(
        direct,
        recovery_projection,
        receipt,
        world_revision=session["world_revision"],
    )
    require(
        "recovery_did_not_reenter_current_fact_pruning"
        in recovery_rejected["fallback_reasons"],
        "recovery bypassed current fact pruning",
    )
    recovery_analysis = deepcopy(direct)
    recovery_analysis["recovery_context_projection"] = {
        "status": "active",
        "world_revision": session["world_revision"],
        "requires_current_fact_pruning": True,
    }
    recovery_projection = project_analysis_to_machine_dictionary(
        str(recovery_analysis.get("normalized_utterance") or ""),
        recovery_analysis,
        world_revision=session["world_revision"],
    )
    recovery_receipt = build_dictionary_equivalence_receipt(
        recovery_analysis,
        recovery_projection,
        world_revision=session["world_revision"],
    )
    recovery_admitted = build_dictionary_authority_admission(
        recovery_analysis,
        recovery_projection,
        recovery_receipt,
        world_revision=session["world_revision"],
    )
    require(
        recovery_admitted["admission_status"] == "admitted",
        f"revalidated recovery was not admissible: {recovery_admitted}",
    )

    stale = build_dictionary_authority_admission(
        direct,
        projection,
        receipt,
        world_revision=session["world_revision"] + 1,
    )
    require(
        stale["admission_status"] == "fallback"
        and any(
            reason.endswith("world_revision_mismatch")
            for reason in stale["fallback_reasons"]
        ),
        "old semantic dependencies survived a new world revision",
    )
    invalidated = invalidate_dictionary_authority_admission(
        direct_admission,
        current_world_revision=session["world_revision"] + 1,
    )
    require(
        invalidated["admission_status"] == "invalidated"
        and invalidated["semantic_input"] is None
        and invalidated["can_generate_situated_event_graph"] is False,
        "local world-version invalidation retained semantic authority",
    )

    boundary_tamper = deepcopy(direct_admission)
    boundary_tamper["can_control_execution"] = True
    try:
        assert_dictionary_authority_boundary(boundary_tamper)
    except AssertionError as error:
        require(
            str(error) == "dictionary_authority_cannot_control_execution",
            f"unexpected boundary error: {error}",
        )
    else:
        raise AssertionError("dictionary semantic authority gained execution control")

    runtime_revision_before = session["world_revision"]
    set_stool(session["session_id"], "ahead")
    require(
        session["world_revision"] == runtime_revision_before + 1
        and session["current_rcir"] is None
        and session["last_invalidated_dictionary_authority_admission"][
            "admission_status"
        ]
        == "invalidated",
        "runtime world change did not retire the current semantic authority",
    )

    evidence = {
        "schema_version": "1.0.0",
        "evidence_kind": "DictionaryAuthorityArchitectureEvidence",
        "normal_cases": cases,
        "fault_injection": {
            "tampered_receipt_rejected": True,
            "ambiguous_lattice_rejected": True,
            "post_receipt_projection_tamper_rejected": True,
            "recovery_pruning_bypass_rejected": True,
            "world_revision_mismatch_rejected": True,
            "runtime_world_change_retired_current_rcir": True,
            "semantic_authority_cannot_control_execution": True,
        },
        "boundaries": {
            "fact_authority": "WorldFactLedger",
            "control_gateway": "P018",
            "verification_gateway": "P016",
            "surface_text_below_rcir": False,
            "simultaneous_dictionary_and_fallback_authority": False,
        },
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT / "dictionary_authority_evidence.json"
    report_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Dictionary semantic authority architecture validation passed.")
    print({"cases": len(cases), "fault_injections": 7, "report": str(report_path)})


if __name__ == "__main__":
    main()
