from __future__ import annotations

from concept_core.dictionary_frontend import project_analysis_to_machine_dictionary
from concept_core.factory_event_units import FACTORY_EVENT_CONCEPT_UNITS
from concept_core.language_concept_composer import compose_language_concepts
from concept_core.machine_dictionary import (
    audit_event_concept_dictionary_coverage,
    dictionary_index,
    dictionary_modifier_lexicon,
)
from concept_core.perceptual_grounding import load_object_concepts
from concept_core.reference_resolution import resolve_references


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


def main() -> None:
    audit = audit_event_concept_dictionary_coverage(FACTORY_EVENT_CONCEPT_UNITS)
    require(audit["total"] == len(FACTORY_EVENT_CONCEPT_UNITS), "coverage audit skipped registry entries")
    require(
        audit["covered_count"] == audit["total"] == 17,
        f"event registry is not fully mapped into the machine dictionary: {audit}",
    )
    require(audit["conflict_count"] == 0, f"one operator maps to multiple dictionary entries: {audit}")
    require(
        all(item.get("recommended_entry_kind") for item in audit["records"]),
        "missing operator lacks a typed migration destination",
    )
    require(audit["migration_ready"] is True, "dictionary coverage is not migration-ready")
    require(
        audit["can_control_execution"] is False
        and audit["runtime_fact_committed"] is False,
        "coverage auditor became an execution or fact authority",
    )

    lexicon = dictionary_modifier_lexicon()
    modifier_keys = {(item["dimension"], item["value"]) for item in lexicon}
    for expected in {
        ("speed", "fast"),
        ("carefulness", "careful"),
        ("temporal", "immediate_past"),
        ("direction", "return_toward_reference"),
    }:
        require(expected in modifier_keys, f"machine dictionary lacks modifier {expected}")

    analysis = compose("请小心慢慢把白色马克杯放到操作台A")
    projection = project_analysis_to_machine_dictionary(
        analysis["normalized_utterance"], analysis, world_revision=11
    )
    index = dictionary_index()
    projected_operators = [index[ref]["semantic_value"] for ref in projection["operator_refs"]]
    require(
        projected_operators == analysis["canonical_frame"]["operators"],
        f"operator shadow projection diverged: {projection}",
    )
    require(
        set(projection["role_referents"]) == set(analysis["role_bindings"]),
        f"role shadow projection diverged: {projection}",
    )
    lexical_modifiers = [
        item
        for item in analysis["modifier_contract"]["modifiers"]
        if item.get("basis") == "machine_dictionary_closed_class_adapter"
    ]
    require(lexical_modifiers, "modifier compiler did not consume dictionary adapters")
    require(
        all(item.get("dictionary_entry_ref") in index for item in lexical_modifiers),
        f"compiled modifier cannot be traced to dictionary entry: {lexical_modifiers}",
    )
    attachments = projection["scope_graph"]["attachments"]
    require(
        {(item["dimension"], item["value"]) for item in attachments}
        == {
            (item["dimension"], item["value"])
            for item in analysis["modifier_contract"]["modifiers"]
        },
        "modifier scope projection lost a typed modifier",
    )

    context = [
        {
            "entity_ref": "mug_white",
            "label": "白色马克杯",
            "focus_source": "verified_holding_fact",
            "world_revision": 11,
        }
    ]
    resolved = resolve_references(
        "把它放到操作台A",
        [],
        context,
        [{"operator": "place_object", "start": 2, "end": 3}],
    )
    expression = resolved["referent_expressions"][0]
    require(
        expression["referent_expression"]["referent_kind"] == "entity_ref"
        and expression["referent_expression"]["entity_ref"] == "mug_white",
        f"resolved reference did not become an EntityRef expression: {expression}",
    )
    ambiguous = resolve_references(
        "把它放下",
        [],
        [
            {**context[0], "entity_ref": "mug_left"},
            {**context[0], "entity_ref": "mug_right"},
        ],
        [{"operator": "place_object", "start": 2, "end": 3}],
    )
    selector = ambiguous["referent_expressions"][0]["referent_expression"]
    require(
        selector["referent_kind"] == "entity_selector"
        and selector["grounding_required"]
        and selector["runtime_fact_committed"] is False,
        f"ambiguous reference silently became an EntityRef: {selector}",
    )

    require(
        projection["mode"] == "shadow_equivalence_migration"
        and projection["can_control_execution"] is False,
        "equivalence evidence promoted the dictionary path prematurely",
    )
    print("Dictionary coverage and equivalence validation passed.")
    print(
        {
            "event_registry_coverage": {
                "covered": audit["covered_count"],
                "total": audit["total"],
                "missing": audit["missing_count"],
                "conflicts": audit["conflict_count"],
            },
            "modifier_dictionary_single_source": "passed",
            "operator_role_modifier_equivalence": "passed",
            "reference_expression_unification": "passed",
            "shadow_authority_boundary": "passed",
        }
    )


if __name__ == "__main__":
    main()
