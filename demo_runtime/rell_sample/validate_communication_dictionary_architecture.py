from __future__ import annotations

import json
from pathlib import Path

from concept_core.dictionary_frontend import (
    project_analysis_to_machine_dictionary,
    project_contextual_communication_signal,
)
from concept_core.factory_event_units import FACTORY_EVENT_CONCEPT_UNITS
from concept_core.language_concept_composer import compose_language_concepts
from concept_core.machine_dictionary import dictionary_index, load_machine_dictionary
from concept_core.perceptual_grounding import load_object_concepts
from embodied_scene import (
    SESSIONS,
    _compose_session_language,
    _create_pending_confirmation,
    begin_motion_command,
    start_session,
)


OBJECT_CONCEPTS = load_object_concepts()["concepts"]
ROOT = Path(__file__).resolve().parents[2]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def compose(text: str) -> dict:
    return compose_language_concepts(
        text,
        event_concepts=FACTORY_EVENT_CONCEPT_UNITS,
        object_concepts=OBJECT_CONCEPTS,
    )


def main() -> None:
    dictionary = load_machine_dictionary()
    index = dictionary_index(dictionary)
    kinds = {
        kind: [item for item in dictionary["entries"] if item["entry_kind"] == kind]
        for kind in ("speech_act", "query_contract", "communicative_contract")
    }
    require(len(kinds["speech_act"]) == 9, "speech-act primitive inventory is incomplete")
    require(len(kinds["query_contract"]) == 12, "runtime query contracts are incomplete")
    require(
        len(kinds["communicative_contract"]) == 4,
        "contextual communication contracts are incomplete",
    )
    require(
        all(
            item["fact_commit_authority"] == "none"
            and item.get("communication_contract")
            for values in kinds.values()
            for item in values
        ),
        "a communication entry gained fact authority or lacks a contract",
    )

    query_types = {
        "liquid_state",
        "holding_state",
        "executor_location",
        "preference_summary",
        "current_action",
        "next_step",
        "snapshot_summary",
        "object_location",
        "object_visibility",
        "object_presence",
        "support_inventory",
        "region_inventory",
    }
    for query_type in query_types:
        analysis = {
            "speech_act": "state_query",
            "query_type": query_type,
            "canonical_frame": {
                "speech_act": "state_query",
                "query_type": query_type,
                "operators": [],
                "roles": {},
                "goal_relation": None,
            },
            "role_bindings": {},
            "modifier_contract": {"modifiers": []},
            "reference_resolution": {"referent_expressions": []},
            "unresolved_slots": [],
        }
        projection = project_analysis_to_machine_dictionary(
            "", analysis, world_revision=3
        )
        require(
            projection["speech_act_ref"] == "speech_act.query_state"
            and projection["query_contract_ref"] == f"query.{query_type}"
            and not projection["semantic_coverage_gaps"],
            f"query contract did not compile: {query_type}: {projection}",
        )

    natural_query = compose("桌子上有什么")
    query_projection = project_analysis_to_machine_dictionary(
        natural_query["normalized_utterance"], natural_query, world_revision=3
    )
    require(
        query_projection["query_contract_ref"] == "query.support_inventory"
        and query_projection["unresolved_polysemy_count"] == 0
        and query_projection["interpretation_lattice"]["status"] == "resolved",
        f"support query did not resolve its typed 上 relation: {query_projection}",
    )

    polite_request = compose("请把白色马克杯放到操作台A")
    polite_projection = project_analysis_to_machine_dictionary(
        polite_request["normalized_utterance"], polite_request, world_revision=3
    )
    compositional_group = next(
        (
            item
            for item in polite_projection["surface_candidate_groups"]
            if {
                "speech_act.request_action",
                "modifier.politeness",
            }.issubset(set(item.get("selected_entry_refs") or []))
        ),
        None,
    )
    require(
        compositional_group is not None
        and compositional_group["status"] == "resolved_compositional_bundle",
        f"请 was forced into false exclusive polysemy: {polite_projection}",
    )

    embedded_surface = compose("把白色马克杯对着操作台A放下")
    embedded_projection = project_analysis_to_machine_dictionary(
        embedded_surface["normalized_utterance"],
        embedded_surface,
        world_revision=3,
    )
    require(
        all(
            "speech_act.confirm" not in set(item.get("selected_entry_refs") or [])
            for item in embedded_projection["surface_candidate_groups"]
        ),
        "对 inside a task phrase was silently promoted to confirmation",
    )

    no_context = project_contextual_communication_signal(
        "confirmation", context_ref=None, world_revision=3
    )
    require(
        no_context["status"] == "blocked"
        and "dialogue_context_ref" in no_context["missing_semantics_or_context"],
        "confirmation without a pending contract was accepted",
    )
    correction = project_contextual_communication_signal(
        "correction",
        context_ref="rcir_previous",
        world_revision=3,
        typed_payload={"replacement_compiled": True},
    )
    require(
        correction["status"] == "admissible"
        and correction["requires_reentry_to_current_grounding"] is True
        and correction["runtime_fact_committed"] is False,
        "correction contract bypassed grounding or fact authority",
    )
    report = project_contextual_communication_signal(
        "information_report",
        context_ref=None,
        world_revision=3,
        typed_payload={"reported_predicate_candidate": "container_empty"},
    )
    require(
        report["status"] == "admissible"
        and report["speech_act_ref"] == "speech_act.inform"
        and report["can_commit_runtime_fact"] is False,
        "human information report became a physical fact source",
    )

    session = start_session("home_humanoid", "hospitality_guest")
    live = SESSIONS[session["session_id"]]
    _create_pending_confirmation(live, "走到操作台A")
    confirmed = begin_motion_command(session["session_id"], "对")
    online_confirmation = confirmed.get("communicative_dictionary_projection") or (
        confirmed.get("immediate_result") or {}
    ).get("communicative_dictionary_projection")
    require(
        online_confirmation
        and online_confirmation["speech_act_ref"] == "speech_act.confirm"
        and online_confirmation["communicative_contract_ref"]
        == "communication.confirm_pending"
        and online_confirmation["surface_text_forwarded_downstream"] is False,
        f"online confirmation bypassed the communication dictionary: {confirmed}",
    )

    correction_session = start_session("home_humanoid", "hospitality_guest")
    correction_live = SESSIONS[correction_session["session_id"]]
    correction_live["active_intent_id"] = "intent_correction_target"
    correction_analysis = _compose_session_language(
        correction_live,
        "我的意思是把白色马克杯放到操作台A",
    )
    online_correction = correction_analysis.get(
        "communicative_dictionary_projection"
    ) or {}
    require(
        online_correction.get("status") == "admissible"
        and online_correction.get("context_ref") == "intent_correction_target"
        and online_correction.get("can_control_execution") is False,
        f"online correction was not bound to its superseded context: {online_correction}",
    )

    for ref in (
        "speech_act.query_state",
        "query.support_inventory",
        "communication.correct_semantics",
    ):
        require(ref in index, f"missing communication dictionary entry: {ref}")
    json.loads(
        (ROOT / "schemas" / "communicative_dictionary_projection.schema.json")
        .read_text(encoding="utf-8")
    )
    print("Communication dictionary architecture validation passed.")
    print(
        {
            "speech_act_primitives": len(kinds["speech_act"]),
            "query_contracts": len(kinds["query_contract"]),
            "communicative_contracts": len(kinds["communicative_contract"]),
            "typed_query_projection": len(query_types),
            "compositional_surface_bundle": "passed",
            "contextual_confirmation_and_correction": "passed",
            "fact_and_control_boundary": "passed",
        }
    )


if __name__ == "__main__":
    main()
