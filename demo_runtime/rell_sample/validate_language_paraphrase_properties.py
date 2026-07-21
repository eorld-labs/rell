from __future__ import annotations

from concept_core.factory_event_units import FACTORY_EVENT_CONCEPT_UNITS
from concept_core.language_concept_composer import compose_language_concepts
from concept_core.perceptual_grounding import load_object_concepts


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


def validate_historical_cross_product() -> int:
    markers = ("刚才", "刚刚", "之前", "先前", "上次", "上回", "方才", "此前")
    verbs = ("拿", "拿起", "取")
    supports = ("桌子", "桌面", "台面")
    forms = (
        lambda marker, verb, support: f"把杯子放到{marker}你{verb}杯子的{support}",
        lambda marker, verb, support: f"把杯子放到{marker}你{verb}它的{support}",
        lambda marker, verb, support: f"把杯子放到{marker}你{verb}的{support}",
    )
    count = 0
    for marker in markers:
        for verb in verbs:
            for support in supports:
                for build in forms:
                    text = build(marker, verb, support)
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
                        f"historical cross-product failed: {text}: {analysis}",
                    )
                    count += 1
    return count


def validate_connector_equivalence() -> int:
    variants = (
        "把杯子放到桌面，然后用高脚杯接水给我",
        "把杯子放到桌面，接着用高脚杯接水给我",
        "把杯子放到桌面，随后用高脚杯接水给我",
        "把杯子放到桌面，再然后用高脚杯接水给我",
        "把杯子放到桌面之后用高脚杯接水给我",
        "把杯子放到桌面以后用高脚杯接水给我",
        "把杯子放到桌面而后用高脚杯接水给我",
        "先把杯子放到桌面再用高脚杯接水给我",
    )
    for text in variants:
        analysis = compose(text)
        frames = analysis.get("event_frames", [])
        require(
            len(frames) == 2
            and (frames[0].get("canonical_frame") or {}).get("operators")
            == ["place_object"]
            and "fill_container"
            in (frames[1].get("canonical_frame") or {}).get("operators", [])
            and analysis["discourse_event_graph"]["edges"][0].get("relation")
            == "sequence",
            f"connector changed the event graph: {text}: {analysis}",
        )
    return len(variants)


def validate_pronoun_cardinality() -> int:
    focus = {
        "entity_ref": "entity_focus_17",
        "concept_id": "concept_fillable_container",
        "label": "当前饮具",
        "display_name": "当前饮具",
        "compatible_kinds": ["graspable_container"],
        "functional_affordances": ["graspable", "receive_liquid"],
    }
    pronouns = ("它", "这个", "那个")
    for pronoun in pronouns:
        resolved = compose(
            f"把{pronoun}放到桌面",
            context_entities=[focus],
        )
        require(
            (resolved.get("role_bindings", {}).get("theme") or {}).get(
                "entity_ref"
            )
            == "entity_focus_17"
            and "pronoun_reference_not_unique"
            not in resolved.get("unresolved_slots", []),
            str(resolved),
        )
        ambiguous = compose(
            f"把{pronoun}放到桌面",
            context_entities=[focus, {**focus, "entity_ref": "entity_focus_18"}],
        )
        require(
            "pronoun_reference_not_unique" in ambiguous.get("unresolved_slots", []),
            str(ambiguous),
        )
    return len(pronouns) * 2


def validate_correction_equivalence() -> int:
    variants = (
        "不是把托盘给我，而是把杯子交给我",
        "并不是把托盘给我，是要把杯子交给我",
        "我的意思是不是把托盘给我而是把杯子交给我",
        "别把托盘给我，改成把杯子交给我",
        "不要把托盘给我，换成把杯子交给我",
    )
    for text in variants:
        analysis = compose(text)
        frames = analysis.get("event_frames", [])
        require(
            len(frames) == 2
            and frames[0].get("discourse_polarity") == "rejected"
            and frames[1].get("discourse_polarity") == "asserted"
            and analysis["discourse_event_graph"]["edges"][0].get("relation")
            == "correction",
            f"correction changed its graph: {text}: {analysis}",
        )
    return len(variants)


def main() -> None:
    counts = {
        "historical_cross_product": validate_historical_cross_product(),
        "connector_equivalence": validate_connector_equivalence(),
        "pronoun_cardinality": validate_pronoun_cardinality(),
        "correction_equivalence": validate_correction_equivalence(),
    }
    print(f"Language paraphrase property validation passed: {counts}")


if __name__ == "__main__":
    main()
