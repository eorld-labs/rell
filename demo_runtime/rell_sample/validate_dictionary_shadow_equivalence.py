from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from concept_core.dictionary_equivalence import build_dictionary_equivalence_receipt
from concept_core.dictionary_frontend import project_analysis_to_machine_dictionary
from concept_core.factory_event_units import FACTORY_EVENT_CONCEPT_UNITS
from concept_core.language_concept_composer import compose_language_concepts
from concept_core.perceptual_grounding import load_object_concepts
from embodied_scene import SESSIONS, _compose_session_language, start_session


OBJECT_CONCEPTS = load_object_concepts()["concepts"]
ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "demo_runtime" / "output" / "rell_sample" / "dictionary_shadow_equivalence"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def compose(text: str, *, context_entities: list[dict] | None = None) -> dict:
    return compose_language_concepts(
        text,
        event_concepts=FACTORY_EVENT_CONCEPT_UNITS,
        object_concepts=OBJECT_CONCEPTS,
        context_entities=context_entities or [],
    )


def receipt(analysis: dict, *, world_revision: int = 12) -> tuple[dict, dict]:
    projection = project_analysis_to_machine_dictionary(
        str(analysis.get("normalized_utterance") or ""),
        analysis,
        world_revision=world_revision,
    )
    return projection, build_dictionary_equivalence_receipt(
        analysis, projection, world_revision=world_revision
    )


def main() -> None:
    case_records: list[dict] = []

    def record(case_id: str, result: dict) -> None:
        case_records.append(
            {
                "case_id": case_id,
                "receipt_id": result["receipt_id"],
                "status": result["status"],
                "eligible_for_authority_promotion": result[
                    "eligible_for_authority_promotion"
                ],
                "divergent_fields": list(result["divergent_fields"]),
                "promotion_blockers": list(result["promotion_blockers"]),
                "field_status": {
                    name: value["status"]
                    for name, value in result["field_results"].items()
                },
                "runtime_fact_committed": False,
            }
        )

    variants = (
        "把杯子放到桌面，然后用高脚杯接水给我",
        "杯子放到桌面后高脚杯接水给我",
        "先把杯子放到桌面再用高脚杯接水给我",
        "把杯子搁在桌面，随后换高脚杯盛水递给我",
    )
    for utterance in variants:
        analysis = compose(utterance)
        projection, result = receipt(analysis)
        require(
            len(analysis.get("event_frames", [])) == 2
            and len(projection.get("event_frame_projections", [])) == 2,
            f"compound discourse was reduced to its first subgoal: {utterance}",
        )
        require(
            result["status"] == "equivalent"
            and result["field_results"]["event_frames"]["status"] == "equivalent",
            f"compound frame shadow projection diverged: {utterance}: {result}",
        )
        record(f"compound_paraphrase_{len(case_records) + 1}", result)

    context = [
        {
            "entity_ref": "mug_white",
            "label": "白色马克杯",
            "focus_source": "verified_holding_fact",
            "world_revision": 12,
        }
    ]
    analysis = compose("把它放到操作台A", context_entities=context)
    projection, result = receipt(analysis)
    require(
        result["field_results"]["references"]["status"] == "equivalent"
        and projection["reference_referents"][0]["referent_expression"]["entity_ref"]
        == "mug_white",
        f"cross-turn EntityRef did not survive shadow projection: {result}",
    )
    record("cross_turn_reference", result)

    ambiguous_context = [
        {**context[0], "entity_ref": "mug_left"},
        {**context[0], "entity_ref": "mug_right"},
    ]
    ambiguous = compose("把它放下", context_entities=ambiguous_context)
    projection, result = receipt(ambiguous)
    require(result["status"] == "equivalent", "equal ambiguity is a compiler divergence")
    require(
        result["eligible_for_authority_promotion"] is False
        and projection["reference_referents"][0]["requires_confirmation"],
        "equal ambiguity was treated as authority-promotion ready",
    )
    record("ambiguous_reference", result)

    query_analysis = compose("桌子上有什么")
    _, query_receipt = receipt(query_analysis)
    require(
        query_receipt["status"] == "equivalent"
        and query_receipt["eligible_for_authority_promotion"] is False
        and "query_semantics_not_dictionary_grounded"
        in query_receipt["promotion_blockers"],
        "field equality hid missing query/communicative dictionary coverage",
    )
    record("state_query_coverage_gap", query_receipt)

    session = start_session("home_humanoid", "hospitality_guest")
    live = SESSIONS[session["session_id"]]
    live["failure_recovery_contract"] = {
        "contract_id": "failure_recovery_equivalence_test",
        "status": "awaiting_recovery_or_replacement_task",
    }
    online = _compose_session_language(live, "把白色马克杯放到操作台A")
    online_receipt = online["machine_dictionary_equivalence"]
    recovery = online_receipt["field_results"]["recovery_context"]
    require(
        recovery["status"] == "equivalent"
        and recovery["actual"]["status"] == "active"
        and recovery["actual"]["raw_failure_text_included"] is False,
        f"recovery context was lost or surface text was retained: {online_receipt}",
    )
    require(
        live["machine_dictionary_equivalence_history"][-1]["receipt_id"]
        == online_receipt["receipt_id"],
        "online equivalence receipt was not retained in bounded session evidence",
    )
    record("active_failure_recovery_context", online_receipt)

    tampered = deepcopy(online["machine_dictionary_projection"])
    tampered["goal_relation"] = "wrong_goal"
    detected = build_dictionary_equivalence_receipt(
        online, tampered, world_revision=int(live.get("world_revision", 0))
    )
    require(
        detected["status"] == "divergent"
        and "goal_relation" in detected["divergent_fields"]
        and detected["eligible_for_authority_promotion"] is False,
        "shadow comparator failed to block a semantic divergence",
    )
    require(
        detected["can_control_execution"] is False
        and detected["can_commit_runtime_fact"] is False
        and detected["surface_text_reparsed"] is False,
        "equivalence evidence crossed its authority boundary",
    )
    record("tampered_goal_divergence", detected)

    json.loads(
        (ROOT / "schemas" / "machine_dictionary_equivalence_receipt.schema.json")
        .read_text(encoding="utf-8")
    )
    report = {
        "schema_version": "1.0.0",
        "report_kind": "MachineDictionaryShadowEquivalenceEvidence",
        "case_count": len(case_records),
        "equivalent_count": sum(
            item["status"] == "equivalent" for item in case_records
        ),
        "divergent_count": sum(
            item["status"] == "divergent" for item in case_records
        ),
        "promotion_ready_count": sum(
            item["eligible_for_authority_promotion"] for item in case_records
        ),
        "authority_boundary": {
            "can_control_execution": False,
            "can_commit_runtime_fact": False,
            "surface_text_reparsed": False,
        },
        "cases": case_records,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT / "shadow_equivalence_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Machine dictionary shadow equivalence validation passed.")
    print(
        {
            "compound_paraphrases": len(variants),
            "event_frames_preserved": 2,
            "cross_turn_reference": "passed",
            "ambiguity_blocks_promotion": "passed",
            "query_coverage_gap_blocks_promotion": "passed",
            "recovery_context_equivalence": "passed",
            "divergence_detection": "passed",
            "authority_boundary": "passed",
            "evidence_report": str(report_path),
        }
    )


if __name__ == "__main__":
    main()
