from __future__ import annotations

import json
from pathlib import Path

from concept_core.composition_grammar import (
    build_interpretation_lattice,
    build_scope_graph,
    make_referent_expression,
)
from concept_core.machine_dictionary import (
    dictionary_architecture_summary,
    dictionary_index,
    load_machine_dictionary,
    lookup_surface_candidates,
    realize_dictionary_entry,
)
from embodied_scene import SESSIONS, begin_motion_command, start_session


ROOT = Path(__file__).resolve().parents[2]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    dictionary = load_machine_dictionary()
    index = dictionary_index(dictionary)
    summary = dictionary_architecture_summary(dictionary)
    require(summary["core_is_finite"], "core dictionary must be finite")
    require(index["operator.place_object"]["irreducible"] is True, "primitive operator boundary failed")
    require(index["contract.fill_container"]["irreducible"] is False, "operator contract was flattened into a primitive")
    require(index["template.deliver_filled_container"]["entry_kind"] == "process_template", "process template boundary failed")

    polysemy = lookup_surface_candidates("上", payload=dictionary)
    require(polysemy["status"] == "ambiguous", f"polysemy was silently selected: {polysemy}")
    require(len(polysemy["candidates"]) >= 3 and polysemy["selected_entry_ref"] is None, "上 must preserve typed alternatives")
    support = lookup_surface_candidates(
        "上",
        host_classification="support_surface",
        syntactic_position="after_noun",
        payload=dictionary,
    )
    require(support["status"] == "unique" and support["selected_entry_ref"] == "predicate.supported_by", f"typed dictionary selection failed: {support}")
    require(support["runtime_fact_committed"] is False, "dictionary lookup committed a fact")

    canonical = realize_dictionary_entry("operator.place_object", payload=dictionary)
    require(canonical == "放", f"dictionary reverse adapter failed: {canonical}")

    future = make_referent_expression(
        "future_entity_selector",
        concept_refs=["concept_discardable_object"],
        generation_condition={"time_window": "afternoon", "source": "planned_task_byproduct"},
        world_revision=4,
    )
    require(future["entity_ref"] is None and future["grounding_required"], "future selector impersonated an EntityRef")
    try:
        make_referent_expression(
            "future_entity_selector",
            entity_ref="future_garbage",
            generation_condition={"time_window": "afternoon"},
        )
    except ValueError:
        pass
    else:
        raise AssertionError("future selector accepted a current EntityRef")

    scope = build_scope_graph(
        ["event_grasp", "event_place"],
        [
            {"modifier_ref": "modifier_fast", "target_event_ref": "event_grasp", "scope": "event"},
            {"modifier_ref": "modifier_slow", "target_event_ref": "event_place", "scope": "event"},
        ],
        [{"from": "event_grasp", "to": "event_place", "relation": "sequence"}],
    )
    require(scope["nearest_event_heuristic_is_authoritative"] is False, "scope graph retained nearest-event authority")
    unresolved_scope = build_scope_graph(
        [],
        [{"modifier_ref": "modifier_completed", "target_event_ref": None, "scope": "event"}],
    )
    require(
        not unresolved_scope["scope_complete"]
        and unresolved_scope["unresolved_attachments"],
        "missing event scope was guessed or discarded",
    )

    lattice = build_interpretation_lattice(
        source_ref="sha256:test",
        candidate_graphs=[
            {"candidate_id": "candidate_support", "semantic_ref": "predicate.supported_by"},
            {"candidate_id": "candidate_attainment", "semantic_ref": "modifier.aspect_attainment"},
        ],
        world_revision=4,
    )
    require(lattice["status"] == "unresolved", "ambiguous lattice emitted an authoritative graph")
    require(lattice["inquiry_contract"] and not lattice["authoritative_semantic_graph_emitted"], "ambiguous lattice did not enter inquiry")

    for name in (
        "rell_machine_dictionary.schema.json",
        "rcir_referent_expression.schema.json",
        "rcir_interpretation_lattice.schema.json",
        "rcir_scope_graph.schema.json",
    ):
        json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))

    session = start_session("home_humanoid", "hospitality_guest")
    begin_motion_command(
        session["session_id"], "把白色马克杯放到操作台A"
    )
    online = SESSIONS[session["session_id"]]["last_language_understanding"][
        "machine_dictionary_projection"
    ]
    require(
        online["mode"] == "shadow_equivalence_migration"
        and online["can_control_execution"] is False,
        "dictionary migration path gained execution authority",
    )
    require(
        "operator.place_object" in online["operator_refs"],
        f"online language path did not consume the machine dictionary: {online}",
    )
    require(
        online["interpretation_lattice"]["status"] == "resolved",
        f"known online command did not compile through dictionary lattice: {online}",
    )

    print("RELL machine dictionary architecture validation passed.")
    print({
        "core_compound_boundary": "passed",
        "polysemy_candidate_lattice": "passed",
        "future_selector_identity_boundary": "passed",
        "explicit_scope_graph": "passed",
        "dictionary_round_trip": "passed",
        "online_shadow_projection": "passed",
    })


if __name__ == "__main__":
    main()
