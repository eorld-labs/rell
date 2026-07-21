from __future__ import annotations

from concept_core.factory_event_units import FACTORY_EVENT_CONCEPT_UNITS
from concept_core.language_concept_composer import compose_language_concepts
from concept_core.modifier_composer import compile_modifier_contract
from concept_core.perceptual_grounding import load_object_concepts
from concept_core.reference_resolution import resolve_references
from concept_core.runtime_reasoning import (
    evaluate_runtime_rules,
    explanation_from_structured_state,
)


OBJECT_CONCEPTS = load_object_concepts()["concepts"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def compose(text: str, **kwargs) -> dict:
    return compose_language_concepts(
        text,
        event_concepts=FACTORY_EVENT_CONCEPT_UNITS,
        object_concepts=OBJECT_CONCEPTS,
        **kwargs,
    )


def modifier_values(contract: dict) -> set[tuple[str, str]]:
    return {
        (item.get("dimension"), item.get("value"))
        for item in contract.get("modifiers", [])
    }


def contains_forbidden_surface_key(value: object) -> bool:
    forbidden = {
        "utterance",
        "normalized_utterance",
        "canonical_utterance",
        "surface",
        "matched_surface",
        "label",
    }
    if isinstance(value, dict):
        return any(
            key in forbidden or contains_forbidden_surface_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_forbidden_surface_key(item) for item in value)
    return False


def main() -> None:
    careful = compose("请小心慢慢把白色马克杯拿起来")
    careful_values = modifier_values(careful["modifier_contract"])
    require(("speed", "slow") in careful_values, "slow modifier was not compiled")
    require(("carefulness", "careful") in careful_values, "careful modifier was not compiled")
    require(("politeness", "polite") in careful_values, "politeness modifier was not compiled")
    require(not careful.get("unknown_surface"), f"compiled modifiers leaked into unknown text: {careful}")

    fast_then_slow = compose("快拿杯子，然后慢慢放下")
    values = modifier_values(fast_then_slow["modifier_contract"])
    require(("speed", "fast") in values and ("speed", "slow") in values, f"event-scoped speed failed: {fast_then_slow}")
    require(
        {item.get("event_index") for item in fast_then_slow["modifier_contract"]["modifiers"] if item.get("dimension") == "speed"} == {0, 1},
        f"speed modifiers were not attached to separate events: {fast_then_slow}",
    )

    imminent = compile_modifier_contract("快要把杯子放下了", [{"operator": "place_object", "start": 5, "end": 7}])
    imminent_values = modifier_values(imminent)
    require(("temporal", "imminent") in imminent_values, "快要 must compile as temporal imminence")
    require(("speed", "fast") not in imminent_values, "快要 must not compile as execution speed")

    contradictory = compile_modifier_contract(
        "快点慢点拿杯子", [{"operator": "grasp_object", "start": 4, "end": 5}]
    )
    require(contradictory["conflicts"], "same-event modifier conflict must be explicit")
    require(contradictory["inquiry_contract"], "modifier conflict must enter InquiryContract")

    context = [
        {
            "entity_ref": "mug_white",
            "label": "白色马克杯",
            "focus_source": "verified_holding_fact",
            "functional_affordances": ["movable", "graspable"],
            "world_revision": 7,
        },
        {
            "entity_ref": "tray_wood",
            "label": "木质托盘",
            "focus_source": "dialogue_focus_binding",
            "functional_affordances": ["movable", "support_object"],
            "world_revision": 7,
        },
    ]
    place_event = [{"operator": "place_object", "start": 4, "end": 5}]
    pronoun = resolve_references("把它轻轻放到操作台A", [], context, place_event)
    require(pronoun["resolved_references"][0]["selected"] == "mug_white", f"verified holding fact did not precede salience: {pronoun}")
    require(pronoun["salience_projection"]["persistent_state_source"] is False, "salience became a second state source")

    ambiguous_context = [
        {**context[0], "entity_ref": "mug_left"},
        {**context[0], "entity_ref": "mug_right"},
    ]
    ambiguous = resolve_references("把它放下", [], ambiguous_context, place_event)
    require(not ambiguous["resolved_references"], "same-authority ambiguity silently became unique")
    require(ambiguous["unresolved"] and ambiguous["inquiry_contracts"], "ambiguous reference did not produce InquiryContract")

    lexical_boundary = resolve_references(
        "让苹果和其他水果都在收纳区", [], [], place_event
    )
    require(
        not lexical_boundary["resolved_references"]
        and not lexical_boundary["unresolved"],
        "其他中的他 must not be parsed as a human pronoun",
    )

    intra_turn = compose("归整苹果，让它和其他水果在一起")
    intra_turn_refs = intra_turn["reference_resolution"]["resolved_references"]
    require(
        intra_turn_refs
        and intra_turn_refs[0].get("binding_kind")
        == "intra_turn_concept_coreference"
        and intra_turn_refs[0].get("grounding_required") is True,
        f"intra-turn concept coreference was not preserved for grounding: {intra_turn}",
    )

    possession_context = [
        {
            "entity_ref": "mug_in_human_hand",
            "focus_source": "verified_human_possession_fact",
            "functional_affordances": ["movable", "graspable"],
            "world_revision": 7,
        },
        context[0],
    ]
    possessive = resolve_references("把我手里的杯子拿过去", [], possession_context, place_event)
    require(possessive["resolved_references"][0]["selected"] == "mug_in_human_hand", f"possessive reference was not constrained by verified relation: {possessive}")
    require(possessive["resolved_references"][0]["constraints"][0]["validation_source"] == "WorldFactLedger", "possessive constraint bypassed the ledger")

    rule_analysis = {
        "canonical_frame": {"operators": ["grasp_object"]},
        "role_bindings": {"theme": {"entity_ref": "hot_cup"}},
        "modifier_contract": careful["modifier_contract"],
        "rcir_dialogue_projection": {"human_response": "我理解要拿起杯子。"},
        "rcir": {"bundle_id": "rcir_test"},
    }
    rule = evaluate_runtime_rules(
        rule_analysis,
        [{"entity_id": "hot_cup", "temperature_c": 75.0}],
        {"max_linear_speed_mps": 1.0, "max_contact_force_n": 20.0},
        world_revision=7,
    )
    require(rule["status"] == "blocked", f"P018 safety rule did not block: {rule}")
    require(rule["runtime_fact_committed"] is False and rule["control_gateway"] == "P018", "rule evaluation became fact or bypassed P018")
    require(rule["verification_gateway"] == "P016", "rule path bypassed P016 verification")

    explanation = explanation_from_structured_state(rule_analysis, rule)
    require(explanation["generated_from_rcir_only"] is True, "explanation did not use structured state")
    require(explanation["surface_text_reparsed"] is False, "explanation reparsed surface text")
    require(not contains_forbidden_surface_key(explanation), "surface-language fields leaked into explanation state")

    print("Language modifier/reference architecture validation passed.")
    print({
        "modifier_scope": "passed",
        "temporal_speed_disambiguation": "passed",
        "reference_authority_and_inquiry": "passed",
        "possessive_ledger_constraint": "passed",
        "p018_p016_rule_boundary": "passed",
        "structured_explanation": "passed",
    })


if __name__ == "__main__":
    main()
