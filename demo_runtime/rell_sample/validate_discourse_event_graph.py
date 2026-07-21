from __future__ import annotations

from concept_core.cognitive_ir import build_situated_event_graph
from concept_core.factory_event_units import FACTORY_EVENT_CONCEPT_UNITS
from concept_core.language_concept_composer import compose_language_concepts
from concept_core.perceptual_grounding import load_object_concepts
from concept_core.rcir_dialogue_realizer import realize_rcir_dialogue


OBJECT_CONCEPTS = load_object_concepts()["concepts"]


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


def frame_operators(analysis: dict) -> list[list[str]]:
    return [
        list((frame.get("canonical_frame") or {}).get("operators", []))
        for frame in analysis.get("event_frames", [])
    ]


def validate_sequence_paraphrases() -> None:
    variants = (
        "把杯子放到桌面，然后用高脚杯接水给我",
        "杯子放到桌面后高脚杯接水给我",
        "先把杯子放到桌面再用高脚杯接水给我",
        "把杯子搁在桌面，随后换高脚杯盛水递给我",
    )
    analyses = [compose(text) for text in variants]
    for text, analysis in zip(variants, analyses):
        require(
            len(frame_operators(analysis)) == 2
            and frame_operators(analysis)[0] == ["place_object"]
            and "fill_container" in frame_operators(analysis)[1]
            and (
                analysis["event_frames"][1].get("discourse_roles") or {}
            ).get("recipient")
            and [
                edge.get("relation")
                for edge in analysis["discourse_event_graph"]["edges"]
            ]
            == ["sequence"],
            f"sequence paraphrase did not compile to the same graph: {text}: {analysis}",
        )
        require(
            (analysis["event_frames"][0].get("role_bindings") or {}).get("theme")
            and (analysis["event_frames"][1].get("role_bindings") or {}).get("theme"),
            f"event-scoped themes were lost: {text}: {analysis}",
        )


def validate_historical_relation_paraphrases() -> None:
    variants = (
        "把杯子放到刚才拿杯子的桌面",
        "把杯子放回你刚刚取它的台面",
        "杯子送回原先拿起来的桌面",
        "把杯子搁到上次取杯子的桌子",
    )
    for text in variants:
        analysis = compose(text)
        constraints = analysis.get("historical_event_constraints", [])
        require(
            len(constraints) == 1
            and constraints[0].get("operator") == "grasp_object"
            and constraints[0].get("relation")
            == "source_support_of_verified_event"
            and (constraints[0].get("theme") or {}).get("concept_id")
            == "concept_fillable_container"
            and (constraints[0].get("head") or {}).get("concept_id")
            == "concept_support_surface",
            f"historical relation paraphrase lost its event roles: {text}: {analysis}",
        )


def validate_typed_role_flow() -> None:
    analysis = compose("高脚杯接好水，然后放到托盘上，随后拿给我")
    frames = analysis.get("event_frames", [])
    require(
        frame_operators(analysis)
        == [["fill_container"], ["place_object"], ["handover_object"]],
        str(analysis),
    )
    themes = [
        (frame.get("role_bindings") or {}).get("theme") or {}
        for frame in frames
    ]
    require(
        all(theme.get("concept_id") == "concept_fillable_container" for theme in themes)
        and themes[1].get("binding_source") == "typed_prior_event_theme_flow"
        and themes[2].get("binding_source") == "typed_prior_event_theme_flow",
        f"omitted themes were not propagated through typed event edges: {analysis}",
    )
    require(
        [edge.get("inherited_roles") for edge in analysis["discourse_event_graph"]["edges"]]
        == [["theme"], ["theme"]],
        str(analysis["discourse_event_graph"]),
    )


def validate_correction_graph() -> None:
    analysis = compose("不是把托盘给我，而是只把杯子交给我")
    frames = analysis.get("event_frames", [])
    require(
        len(frames) == 2
        and frames[0].get("discourse_polarity") == "rejected"
        and frames[1].get("discourse_polarity") == "asserted"
        and analysis["discourse_event_graph"]["edges"][0].get("relation")
        == "correction"
        and (analysis.get("discourse_roles") or {}).get("task_correction"),
        str(analysis),
    )


def validate_rcir_preserves_graph_without_surface_text() -> None:
    analysis = compose("高脚杯接好水，然后放到托盘上，随后拿给我")
    graph = build_situated_event_graph(
        "高脚杯接好水，然后放到托盘上，随后拿给我",
        analysis,
        world_revision=7,
        interaction_turn=3,
    )
    require(
        len(graph["event_scopes"]) == 3
        and len(graph["discourse_edges"]) == 2
        and graph["source_language"]["raw_text_included"] is False
        and all("utterance" not in scope for scope in graph["event_scopes"]),
        str(graph),
    )


def validate_machine_to_human_projection() -> None:
    bundle = {
        "bundle_id": "rcir_test_dialogue",
        "world_revision": 9,
        "situated_event_graph": {
            "graph_id": "situated_test_dialogue",
            "events": [],
            "event_scopes": [
                {
                    "scope_id": "scope_fill",
                    "operators": ["fill_container"],
                    "goal_relation": "container_filled",
                    "discourse_polarity": "asserted",
                },
                {
                    "scope_id": "scope_handover",
                    "operators": ["handover_object"],
                    "goal_relation": "object_received_by_recipient",
                    "discourse_polarity": "asserted",
                },
            ],
            "goal": {"goal_relation": "human_received_filled_container"},
        },
        "grounded_causal_graph": {
            "graph_id": "grounded_test_dialogue",
            "goal_relation": "human_received_filled_container",
            "role_bindings": {
                "theme": {"status": "resolved", "entity_ref": "entity_vessel_17"},
                "recipient": {"status": "resolved", "entity_ref": "human_3"},
            },
            "open_conditions": [],
        },
        "world_fact_ledger": {"ledger_id": "ledger_test_dialogue"},
    }
    first = realize_rcir_dialogue(
        bundle,
        entity_labels={"entity_vessel_17": "白色马克杯", "human_3": "你"},
    )
    renamed = realize_rcir_dialogue(
        bundle,
        entity_labels={"entity_vessel_17": "未登记饮具甲", "human_3": "你"},
    )
    require(
        "白色马克杯" in first["human_response"]
        and "未登记饮具甲" in renamed["human_response"]
        and first["resolved_entity_refs"] == renamed["resolved_entity_refs"]
        and first["source_bundle_ref"] == renamed["source_bundle_ref"]
        and first["generated_from_rcir_only"] is True
        and first["surface_text_reparsed"] is False,
        f"dialogue projection diverged from the authoritative RCIR: {first}, {renamed}",
    )
    incomplete = {
        **bundle,
        "grounded_causal_graph": {
            **bundle["grounded_causal_graph"],
            "goal_relation": "object_supported_at_destination",
            "open_conditions": [
                {"kind": "unresolved_role", "role": "destination"}
            ],
        },
    }
    clarification = realize_rcir_dialogue(
        incomplete,
        entity_labels={"entity_vessel_17": "白色马克杯"},
    )
    require(
        clarification["unresolved_roles"] == ["destination"]
        and "目标位置" in clarification["human_response"],
        str(clarification),
    )


def main() -> None:
    validate_sequence_paraphrases()
    validate_historical_relation_paraphrases()
    validate_typed_role_flow()
    validate_correction_graph()
    validate_rcir_preserves_graph_without_surface_text()
    validate_machine_to_human_projection()
    print(
        "Discourse event graph validation passed: sequence paraphrases, historical "
        "relations, typed ellipsis flow, correction polarity, and RCIR projection."
    )


if __name__ == "__main__":
    main()
