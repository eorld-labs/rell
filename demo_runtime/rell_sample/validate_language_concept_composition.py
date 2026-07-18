from __future__ import annotations

from statistics import median
from time import perf_counter_ns

from concept_core.factory_event_units import FACTORY_EVENT_CONCEPT_UNITS
from concept_core.language_concept_composer import compose_language_concepts
from concept_core.perceptual_grounding import load_object_concepts
from embodied_scene import SESSIONS, begin_motion_command, confirm_pending_motion, get_session, start_session, step_motion_command


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


def immediate(started: dict) -> dict:
    return started.get("immediate_result") or started


def drain(started: dict) -> dict:
    job_id = started.get("job_id")
    require(bool(job_id), f"expected motion job: {started}")
    for _ in range(320):
        current = step_motion_command(job_id)
        if current.get("status") == "motion_completed":
            return current
    raise AssertionError(f"motion did not complete: {started}")


def main() -> None:
    visibility_forms = ["你看得见苹果吗", "你看得到苹果吗", "你看到苹果了吗", "苹果你能看见吗"]
    visibility = [compose(text) for text in visibility_forms]
    require(all(item["speech_act"] == "state_query" for item in visibility), "visibility paraphrases must remain queries")
    require(all(item["query_type"] == "object_visibility" for item in visibility), "visibility paraphrases must share one query concept")
    require(all(item["canonical_frame"]["operators"] == ["observe_entity"] for item in visibility), "visibility must use the perceptual primitive")
    require(all(item["confidence_band"] == "high" for item in visibility), "composed visibility queries should not require phrase enumeration")

    grasp = compose("麻烦把苹果拾起来")
    require(grasp["canonical_frame"]["operators"] == ["grasp_object"], f"lexical grasp primitive failed: {grasp}")
    require(grasp["canonical_utterance"] == "拿起苹果", f"grasp canonicalization failed: {grasp}")

    transfer = compose("把苹果拿起来放到桌子上")
    require(transfer["canonical_frame"]["operators"] == ["grasp_object", "place_object"], f"composed task order failed: {transfer}")
    require(transfer["canonical_frame"]["goal_relation"] == "object_supported_at_destination", f"goal projection failed: {transfer}")
    require("桌子" in str(transfer["canonical_utterance"]), f"destination role was lost: {transfer}")

    transport_to_support = compose("嗯，把杯子拿到桌子上去")
    require(transport_to_support["canonical_frame"]["operators"] == ["transport_object"], f"transport surface was not recognized: {transport_to_support}")
    require(transport_to_support["role_bindings"].get("destination", {}).get("spatial_relation") == "on_support_surface", f"support topology was not extracted from the result complement: {transport_to_support}")
    require(transport_to_support["canonical_frame"].get("goal_relation") == "object_supported_at_destination" and transport_to_support["canonical_utterance"] == "把杯子放到桌子", f"support transport did not compile to a supported-object terminal fact: {transport_to_support}")
    require(transport_to_support["unknown_surface"] is None and transport_to_support["decision"] == "route_canonical_semantics", f"discourse acknowledgement incorrectly blocked a complete task frame: {transport_to_support}")

    transport_to_region = compose("把苹果带到厨房")
    require(transport_to_region["role_bindings"].get("target_region", {}).get("matched_alias") == "厨房", f"region result complement was not extracted: {transport_to_region}")
    require(transport_to_region["canonical_frame"].get("goal_relation") == "object_at_target_region" and transport_to_region["canonical_utterance"] == "把苹果带到厨房", f"region transport was confused with support placement: {transport_to_region}")

    restore_first = compose("我喝完了，把杯子放回桌子上")
    restore_second = compose("我喝完了，把杯子放回桌子上")
    require(restore_first["canonical_utterance"] == "把杯子放回桌子", f"restore relation degraded into an unbound release: {restore_first}")
    require(restore_first["role_bindings"].get("theme", {}).get("matched_alias") == "杯子" and restore_first["role_bindings"].get("destination", {}).get("matched_alias") == "桌子", f"restore theme and destination were not separated: {restore_first}")
    require(restore_first["modifiers"].get("restore_prior_relation") is True and restore_first["canonical_frame"].get("destination_binding_policy") == "most_recent_verified_support_relation", f"restore did not retain its temporal relation constraint: {restore_first}")
    require(restore_first["confidence"] == restore_second["confidence"] and restore_first["role_bindings"] == restore_second["role_bindings"], f"identical language and context produced non-deterministic semantics: {restore_first}: {restore_second}")

    handover = compose("现在把苹果再递给人类")
    require(handover["speech_act"] == "task_request", f"object handover was not understood as a task: {handover}")
    require(handover["canonical_frame"]["operators"] == ["handover_object"], f"handover language did not reach the generic event primitive: {handover}")
    require(handover["canonical_frame"]["goal_relation"] == "object_received_by_recipient", f"handover goal relation was not projected: {handover}")
    require(handover["role_bindings"].get("theme", {}).get("concept_id") == "concept_edible_apple" and handover["role_bindings"].get("recipient"), f"handover theme and recipient roles were not separated: {handover}")

    prohibited = compose("不要拿杯子")
    require(prohibited["speech_act"] == "prohibition" and prohibited["modifiers"]["negated"], f"negation scope failed: {prohibited}")
    require(prohibited["direct_execution_allowed"] is False, "language composition must never authorize execution")

    pronoun = compose(
        "再把它拿起来",
        context_entities=[{
            "entity_ref": "apple_a",
            "label": "苹果",
            "concept_id": "concept_edible_apple",
            "display_name": "苹果",
            "functional_affordances": ["graspable", "movable"],
            "compatible_kinds": ["graspable_object"],
        }],
    )
    require(not pronoun["unresolved_slots"] and pronoun["role_bindings"].get("theme", {}).get("entity_ref") == "apple_a", f"unique dialogue focus failed: {pronoun}")

    ambiguous_pronoun = compose("把它拿起来", context_entities=[{"entity_ref": "apple_a"}, {"entity_ref": "cup_a"}])
    require("pronoun_reference_not_unique" in ambiguous_pronoun["unresolved_slots"], "ambiguous pronoun must request clarification")

    unknown = compose("端杯子")
    require(unknown["confidence_band"] == "low" and unknown["unknown_surface"] == "端", f"unknown predicate boundary failed: {unknown}")
    definition = compose("端就是拿起的意思")
    require(definition["speech_act"] == "language_teaching", f"explicit language definition was not recognized: {definition}")
    require(definition["definition_candidate"]["operator"] == "grasp_object", f"definition did not bind the known concept kernel: {definition}")

    implicit_place = compose(
        "放到桌子上去",
        context_entities=[{
            "entity_ref": "cup_a",
            "label": "白色杯子",
            "concept_id": "concept_fillable_container",
            "display_name": "可盛装容器",
            "functional_affordances": ["graspable", "receive_liquid"],
            "compatible_kinds": ["graspable_container"],
            "focus_source": "verified_holding_fact",
        }],
    )
    require(implicit_place["canonical_utterance"] == "把白色杯子放到桌子", f"implicit held theme was not recovered from world state: {implicit_place}")
    require(implicit_place["role_bindings"]["theme"]["binding_source"] == "implicit_unique_verified_holding_fact", f"implicit theme lacked verified-state provenance: {implicit_place}")

    reference_session = start_session(executor_profile_id="home_humanoid", scene_id="home_semantic_3d_a")
    reference_candidate = immediate(begin_motion_command(reference_session["session_id"], "把苹果放在刚才放杯子的桌子上"))
    require(reference_candidate["status"] == "language_interpretation_confirmation_required", f"historical relation did not ask only for its unresolved referent: {reference_candidate}")
    historical = reference_candidate.get("historical_reference_candidate", {})
    require(historical.get("destination_entity_ref") == "counter_a", f"known support candidate was not recovered from partial language: {reference_candidate}")
    require(historical.get("evidence_source") == "current_verified_support_relation_without_matching_recent_event", f"weak history evidence was overstated: {reference_candidate}")
    require(not reference_candidate.get("runtime_fact_committed"), f"semantic confirmation candidate became a physical fact: {reference_candidate}")
    reference_resumed = begin_motion_command(reference_session["session_id"], "你刚刚从桌子上拿起过杯子")
    resumed_intent = reference_resumed.get("long_horizon_intent", {})
    require(reference_resumed.get("historical_reference_resolution", {}).get("destination_entity_ref") == "counter_a", f"human relational explanation was mistaken for a new grasp command: {reference_resumed}")
    require(resumed_intent.get("goal_fact") == "object_supported_at_destination", f"confirmed referent did not re-enter ordinary causal planning: {reference_resumed}")
    require(resumed_intent.get("role_bindings", {}).get("theme") == "apple_a" and resumed_intent.get("role_bindings", {}).get("destination") == "counter_a", f"confirmed roles were not preserved: {reference_resumed}")

    missing_session = start_session(executor_profile_id="home_humanoid", scene_id="home_semantic_3d_b")
    missing_runtime = SESSIONS[missing_session["session_id"]]
    missing_cup = next(item for item in missing_runtime["runtime_objects"] if item["entity_id"] == "cup_b")
    missing_cup.pop("support_ref", None)
    missing_cup.pop("last_support_ref", None)
    missing_reference = immediate(begin_motion_command(missing_session["session_id"], "把苹果放在刚才放杯子的桌子上"))
    require(missing_reference["status"] == "relational_reference_clarification_required", f"missing relational role was not asked directly: {missing_reference}")
    require(missing_reference.get("known_roles", {}).get("theme") == "苹果" and missing_reference.get("missing_role") == "destination", f"known and missing language roles were not separated: {missing_reference}")
    explained_reference = begin_motion_command(missing_session["session_id"], "你刚刚从岛台上拿起过杯子")
    require(explained_reference.get("historical_reference_resolution", {}).get("destination_entity_ref") == "counter_b", f"human explanation did not fill only the missing relational role: {explained_reference}")
    require(explained_reference.get("historical_reference_resolution", {}).get("physical_fact_committed") is False, f"human semantic explanation was committed as physical truth: {explained_reference}")

    session = start_session(executor_profile_id="home_humanoid", scene_id="home_semantic_3d_a")
    session_id = session["session_id"]
    no_action = immediate(begin_motion_command(session_id, "不要拿杯子"))
    situated = no_action.get("language_understanding", {}).get("situated_event_frame", {})
    require(situated.get("current_fact_snapshot") and situated.get("evidence_boundary", {}).get("language_does_not_commit_physical_facts"), f"runtime language did not carry current facts with a fact/expectation boundary: {no_action}")
    require(no_action["status"] == "prohibition_understood" and not no_action.get("frames"), f"prohibition leaked into motion: {no_action}")

    gap = immediate(begin_motion_command(session_id, "端杯子"))
    require(gap["status"] == "concept_gap_clarification_required", f"unknown expression must report a bounded gap: {gap}")
    require(gap["language_understanding"]["unknown_surface"] == "端", f"unknown surface was not exposed: {gap}")

    teaching = immediate(begin_motion_command(session_id, "端就是拿起的意思"))
    require(teaching["status"] == "language_adapter_confirmation_required", f"language definition must remain a candidate: {teaching}")
    confirmation_id = teaching["pending_confirmation"]["confirmation_id"]
    resumed = confirm_pending_motion(session_id, confirmation_id, True)
    resumed_result = immediate(resumed)
    require(resumed.get("language_adapter_learned") or resumed_result.get("language_adapter_learned"), f"confirmed definition was not retained: {resumed}")
    require(resumed_result.get("language_understanding", {}).get("operators") == ["grasp_object"], f"learned adapter did not re-enter the normal concept path: {resumed_result}")
    require(resumed_result.get("status") != "concept_gap_clarification_required", f"learned expression returned to the same gap: {resumed_result}")

    motion_confirmation = resumed_result.get("pending_confirmation", {}).get("confirmation_id")
    require(motion_confirmation, f"learned grasp did not return to normal motion authorization: {resumed_result}")
    grasp_started = confirm_pending_motion(session_id, motion_confirmation, True)
    grasp_completed = drain(grasp_started)
    require(grasp_completed.get("result", {}).get("terminal_fact") == "target_object_in_gripper", f"test setup did not establish a held-object fact: {grasp_completed}")
    grasp_memory = get_session(session_id).get("episodic_fact_memory", [])[-1]
    require(grasp_memory.get("operator") == "grasp_object", f"verified grasp was not retained as an episodic event: {grasp_memory}")
    require(grasp_memory.get("before_facts", [{}])[0].get("predicate") == "supported_by" and grasp_memory.get("before_facts", [{}])[0].get("object") == "counter_a", f"grasp source support was not retained for temporal relation queries: {grasp_memory}")

    placement = immediate(begin_motion_command(session_id, "放到桌子上去"))
    placement_language = placement.get("language_understanding", {})
    require(placement_language.get("canonical_utterance") in {"把白色杯子放到桌子", "把杯子放到操作台"}, f"placement roles were not preserved through internal staging: {placement}")
    require(placement.get("status") == "requires_human_confirmation", f"placement did not produce a grounded geometric candidate: {placement}")
    require(placement.get("candidate_execution_plan", {}).get("roles", {}).get("destination") == "counter_a", f"table was not bound as the placement destination: {placement}")
    require(placement.get("candidate_execution_plan", {}).get("role_grounding", {}).get("theme", {}).get("source") == "current_verified_holding_fact", f"execution theme did not come from current holding truth: {placement}")
    require(placement.get("task_perception", {}).get("concept_grounding", {}).get("grounding_status") == "spatially_grounded", f"destination was not actively observed before planning: {placement}")

    samples = []
    for _ in range(300):
        started = perf_counter_ns()
        compose("请把苹果拾起来放到桌子上")
        samples.append((perf_counter_ns() - started) / 1_000_000)
    ordered = sorted(samples)
    p95 = ordered[int(len(ordered) * 0.95) - 1]
    require(p95 < 10.0, f"language composition is too slow for the edge path: p95={p95:.4f}ms")

    print("Language concept composition validation passed.")
    print({
        "visibility_paraphrases": len(visibility_forms),
        "unknown_predicate_learning": "passed",
        "negation_no_motion": "passed",
        "latency_ms": {"median": round(median(samples), 4), "p95": round(p95, 4), "maximum": round(max(samples), 4)},
    })


if __name__ == "__main__":
    main()
