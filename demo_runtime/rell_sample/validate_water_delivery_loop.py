from __future__ import annotations

from embodied_scene import (
    SESSIONS,
    begin_motion_command,
    begin_teaching_control,
    finish_embodied_teaching,
    get_session,
    start_embodied_teaching,
    start_session,
    step_motion_command,
    set_stool,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def drain(started: dict) -> dict:
    if started.get("immediate_result"):
        return started["immediate_result"]
    job_id = started.get("job_id")
    require(bool(job_id), f"motion job missing: {started}")
    while True:
        step = step_motion_command(job_id)
        if step.get("status") == "motion_completed":
            return step["result"]
        require(step.get("status") == "frame_verified_and_committed", f"motion failed: {step}")


def drain_service(started: dict) -> list[dict]:
    outcomes = []
    current = started
    while current:
        outcome = drain(current)
        outcomes.append(outcome)
        current = outcome.get("next_stage_started")
    return outcomes


def complete_authorized_service(scene_id: str) -> dict:
    session = start_session("home_humanoid", scene_id)
    session_id = session["session_id"]
    started = begin_motion_command(session_id, "给我接一杯水")
    require(started.get("status") == "motion_started", f"explicit service command did not authorize execution: {started}")
    outcomes = drain_service(started)
    stage_facts = [item.get("terminal_fact") for item in outcomes]
    route_kinds = [item.get("object_relative_motion", {}).get("route_kind") for item in outcomes if item.get("object_relative_motion", {}).get("route_kind")]
    live = get_session(session_id)
    container = next(item for item in live["runtime_objects"] if item["kind"] == "graspable_container")
    recipient = next(item for item in live["runtime_objects"] if item["kind"] == "human_recipient")
    require(container.get("liquid_state") == "filled", f"fill fact missing in {scene_id}: {container}")
    require(container.get("received_by") == recipient["entity_id"], f"handover fact missing in {scene_id}: {container}")
    require(container["entity_id"] in recipient.get("received_object_refs", []), f"recipient possession missing: {recipient}")
    require(live.get("active_intent_id") is None, f"long intent not completed: {live.get('long_horizon_intents')}")
    require(not live.get("long_horizon_intents"), f"completed intent remained eligible for arbitration: {live.get('long_horizon_intents')}")
    completed_intent = live.get("completed_intent_archive", [])[-1]
    require(completed_intent.get("hierarchical_intent_graph", {}).get("lifecycle") == "completed", f"runtime stages did not close the unified hierarchical intent graph: {completed_intent}")
    require(completed_intent.get("arbitration_eligible") is False and completed_intent.get("verified_facts_scope") == "historical_intent_execution_evidence", f"completed facts were not archived with an explicit historical scope: {completed_intent}")
    require("candidate_execution_plan" not in outcomes[-1] and outcomes[-1].get("execution_plan_state") == "released_on_task_completion", f"completed result retained a stale candidate plan: {outcomes[-1]}")
    require("container_filled" in stage_facts and "human_received_filled_container" in stage_facts, f"stage facts missing: {stage_facts}")
    return {"scene_id": scene_id, "stage_facts": stage_facts, "route_kinds": route_kinds, "intent_graph": "completed"}


def verify_compositional_service_language() -> dict:
    forms = (
        "给人类接一杯水",
        "接一杯水给人类",
        "接杯水交给家人",
        "给主人取水",
    )
    results = []
    for utterance in forms:
        session = start_session("home_humanoid", "home_semantic_3d_b")
        started = begin_motion_command(session["session_id"], utterance)
        intent = started.get("long_horizon_intent", {})
        require(intent.get("goal_fact") == "human_received_filled_container", f"service paraphrase did not compose the delivery goal: {utterance}: {started}")
        require(intent.get("role_bindings", {}).get("recipient") == "human_b", f"human recipient role was not grounded: {utterance}: {started}")
        require(started.get("status") == "motion_started", f"composed service goal did not enter causal execution: {utterance}: {started}")
        results.append(utterance)
    return {"accepted_forms": results, "mechanism": "water_effect_plus_transfer_relation_plus_human_recipient_role"}


def verify_water_then_place_composition() -> dict:
    cases = (
        ("home_semantic_3d_a", "去接一杯水然后放在桌子上", "counter_a"),
        ("home_semantic_3d_b", "接杯水放到岛台上", "counter_b"),
    )
    results = []
    for scene_id, utterance, destination_ref in cases:
        session = start_session("home_humanoid", scene_id)
        started = begin_motion_command(session["session_id"], utterance)
        intent = started.get("long_horizon_intent", {})
        require(intent.get("goal_fact") == "filled_container_supported_at_destination", f"water placement goal was not composed: {utterance}: {started}")
        require(intent.get("role_bindings", {}).get("destination") == destination_ref, f"placement destination was not bound: {utterance}: {started}")
        require(started.get("status") == "motion_started", f"missing current holding was treated as a rejection instead of an acquisition stage: {utterance}: {started}")
        outcomes = drain_service(started)
        live = get_session(session["session_id"])
        container = next(item for item in live["runtime_objects"] if item["kind"] == "graspable_container")
        require(container.get("liquid_state") == "filled", f"water fill effect was not verified: {utterance}: {outcomes}")
        require(container.get("support_ref") == destination_ref and not container.get("attached_to_executor"), f"filled container was not stably placed: {utterance}: {outcomes}")
        require(live.get("active_intent_id") is None, f"composed intent did not terminate: {utterance}: {live.get('long_horizon_intents')}")
        results.append({"utterance": utterance, "destination": destination_ref})
    return {"accepted_forms": results, "goal_fact": "filled_container_supported_at_destination"}


def verify_post_handover_reacquisition_and_support_disambiguation() -> dict:
    session = start_session("home_humanoid", "home_semantic_3d_b")
    session_id = session["session_id"]
    drain_service(begin_motion_command(session_id, "给我接一杯水"))

    generic_navigation = begin_motion_command(session_id, "走到桌子旁边去")
    generic_navigation_result = generic_navigation.get("immediate_result") or generic_navigation
    require(generic_navigation_result.get("status") == "contextual_affordance_disambiguation_required", f"generic table navigation did not expose multiple grounded instances: {generic_navigation}")
    require({item["entity_ref"] for item in generic_navigation_result.get("candidate_options", [])} == {"counter_b", "dining_table_b"}, f"table candidates were incomplete: {generic_navigation}")

    generic_transfer = begin_motion_command(session_id, "从人类手上拿杯子放到桌子上去")
    generic_transfer_result = generic_transfer.get("immediate_result") or generic_transfer
    require(generic_transfer_result.get("status") == "perception_disambiguation_required", f"cross-view transfer did not ask only for the ambiguous support: {generic_transfer}")
    require(generic_transfer_result.get("concept_grounding", {}).get("ambiguity_reason") == "multiple_support_candidates", f"cup visibility was incorrectly reported as missing: {generic_transfer}")

    still_generic = begin_motion_command(session_id, "桌子")
    still_generic_result = still_generic.get("immediate_result") or still_generic
    require(still_generic_result.get("status") == "role_clarification_required", f"generic fragment was mistaken for a new concept-gap task: {still_generic}")
    require(still_generic_result.get("pending_role") == "destination", f"clarification lost its question-under-discussion role: {still_generic}")

    exact_transfer = begin_motion_command(session_id, "餐桌")
    exact_result = exact_transfer.get("immediate_result") or exact_transfer
    require(exact_result.get("status") == "requires_human_confirmation", f"exact destination did not enter causal acquisition planning: {exact_transfer}")
    require(exact_transfer.get("role_clarification_resolution", {}).get("entity_ref") == "dining_table_b", f"fragment answer did not fill the pending destination role: {exact_transfer}")
    require(exact_transfer.get("long_horizon_intent", {}).get("role_bindings", {}).get("destination") == "dining_table_b", f"explicit dining table was not bound: {exact_transfer}")
    grasp_started = begin_motion_command(session_id, "确认")
    grasp_completed = drain(grasp_started)
    live = get_session(session_id)
    cup = next(item for item in live["runtime_objects"] if item["entity_id"] == "cup_b")
    recipient = next(item for item in live["runtime_objects"] if item["entity_id"] == "human_b")
    require(cup.get("received_by") is None and cup.get("attached_to_executor") is True, f"reacquisition did not destroy human possession before establishing robot holding: {cup}")
    require("cup_b" not in recipient.get("received_object_refs", []), f"recipient possession list contradicted verified grasp: {recipient}")
    grasp_episode = next(item for item in reversed(live.get("episodic_fact_memory", [])) if item.get("operator") == "grasp_object")
    require(any(fact.get("predicate") == "received_by" for fact in grasp_episode.get("destroys", [])), f"episodic transition omitted destroyed human possession: {grasp_episode}")

    confirmed_session = start_session("home_humanoid", "home_semantic_3d_b")
    confirmed_id = confirmed_session["session_id"]
    drain_service(begin_motion_command(confirmed_id, "给我接一杯水"))
    confirmed_runtime = SESSIONS[confirmed_id]
    confirmed_runtime["confirmed_visual_bindings"].append({
        "concept_id": "concept_support_surface",
        "entity_ref": "counter_b",
        "label": "岛台",
        "world_revision": confirmed_runtime["world_revision"],
        "binding_source": "test_human_confirmed_visual_candidate",
    })
    reported_transfer = begin_motion_command(confirmed_id, "我喝完了，把杯子放到桌子上去")
    reported_result = reported_transfer.get("immediate_result") or reported_transfer
    reported_intent = reported_transfer.get("long_horizon_intent", {})
    require(reported_result.get("status") == "requires_human_confirmation", f"missing robot holding was treated as terminal failure instead of an acquisition precondition: {reported_transfer}")
    require(reported_intent.get("role_bindings", {}).get("source_holder") == "human_b" and reported_intent.get("role_bindings", {}).get("destination") == "counter_b", f"verified holder and confirmed support were not used by the long-horizon solver: {reported_transfer}")
    report_candidates = get_session(confirmed_id).get("human_reported_fact_candidates", [])
    require(report_candidates and report_candidates[-1].get("possible_derived_fact") == "container_empty" and report_candidates[-1].get("runtime_fact_committed") is False, f"drink completion was not retained as a bounded human-reported state candidate: {report_candidates}")

    restore_session = start_session("home_humanoid", "home_semantic_3d_b")
    restore_id = restore_session["session_id"]
    drain_service(begin_motion_command(restore_id, "给我接一杯水"))
    restored = begin_motion_command(restore_id, "我喝完了，把杯子放回桌子上")
    restored_result = restored.get("immediate_result") or restored
    restored_intent = restored.get("long_horizon_intent", {})
    restored_language = restored_intent.get("source_language_frame", {})
    require(restored_result.get("status") == "requires_human_confirmation", f"restore request did not derive reacquisition as the next stage: {restored}")
    require(restored_intent.get("role_bindings", {}).get("source_holder") == "human_b", f"restore request lost the current verified human holder: {restored}")
    require(restored_intent.get("role_bindings", {}).get("destination") == "counter_b", f"restore request did not bind the most recent verified support: {restored}")
    require(restored_language.get("canonical_utterance") == "把杯子放回桌子", f"restore semantics degraded into release or lost its destination: {restored_language}")
    require(restored_language.get("modifiers", {}).get("restore_prior_relation") is True and restored_language.get("destination_binding_policy") == "most_recent_verified_support_relation", f"restore relation was not retained as a historical binding constraint: {restored_language}")

    correction_session = start_session("home_humanoid", "home_semantic_3d_b")
    correction_id = correction_session["session_id"]
    drain_service(begin_motion_command(correction_id, "给我接一杯水"))
    ambiguous_return = begin_motion_command(correction_id, "好了我喝完了，把杯子放到桌子上去")
    ambiguous_result = ambiguous_return.get("immediate_result") or ambiguous_return
    require(ambiguous_result.get("status") == "perception_disambiguation_required", f"generic return destination did not preserve a role question: {ambiguous_return}")
    corrected_return = begin_motion_command(correction_id, "不是这个桌子，是刚才你倒水的时候原来的位置")
    corrected_result = corrected_return.get("immediate_result") or corrected_return
    resolution = corrected_return.get("role_clarification_resolution", {})
    require(corrected_result.get("status") == "requires_human_confirmation", f"relational correction did not resume the suspended task: {corrected_return}")
    require(resolution.get("entity_ref") == "counter_b" and resolution.get("evidence", {}).get("kind") == "most_recent_verified_source_support", f"original location was not grounded from verified episodic support evidence: {corrected_return}")
    require(corrected_return.get("long_horizon_intent", {}).get("role_bindings", {}).get("source_holder") == "human_b", f"corrected return lost the current holder precondition: {corrected_return}")
    require(get_session(correction_id).get("concept_gap_dialogue") is None, f"role correction incorrectly opened a new concept-gap task: {get_session(correction_id).get('concept_gap_dialogue')}")
    return {
        "navigation_candidates": ["counter_b", "dining_table_b"],
        "reacquired_fact": grasp_completed.get("terminal_fact"),
        "reported_drink_state": "candidate_requires_physical_verification",
        "historical_destination_correction": "counter_b",
    }


def verify_contrastive_evidence_gap_dialogue() -> dict:
    session = start_session("home_humanoid", "home_semantic_3d_b")
    session_id = session["session_id"]
    missing = begin_motion_command(session_id, "把黑色的杯子放到餐桌上")
    missing_result = missing.get("immediate_result") or missing
    require(missing_result.get("status") == "evidence_gap_clarification_required", f"attribute mismatch did not become a solvable evidence gap: {missing}")
    require("没有发现符合“黑色”约束" in missing_result.get("prompt", "") and "蓝色陶瓷杯" in missing_result.get("prompt", ""), f"clarification did not contrast requested and observed facts: {missing}")
    dialogue = get_session(session_id).get("evidence_gap_dialogue", {})
    require(dialogue.get("goal", {}).get("goal_fact") == "target_object_in_gripper" and len(dialogue.get("candidate_options", [])) == 1, f"evidence gap lost the original goal or minimum substitute: {dialogue}")

    resumed = begin_motion_command(session_id, "对")
    resumed_result = resumed.get("immediate_result") or resumed
    require(resumed_result.get("status") == "requires_human_confirmation", f"confirmed substitute did not resume causal planning: {resumed}")
    resolution = resumed.get("evidence_gap_resolution", {})
    require(resolution.get("human_confirmed_substitution") and resolution.get("entity_ref") == "cup_b", f"human confirmation did not fill only the missing role binding: {resumed}")
    intent = resumed.get("long_horizon_intent", {})
    require(intent.get("role_bindings", {}).get("theme") == "cup_b" and intent.get("role_bindings", {}).get("destination") == "dining_table_b", f"resumed task changed its object or destination goal: {resumed}")
    return {
        "requested_constraint": "black",
        "observed_substitute": "cup_b",
        "resumed_stage": intent.get("current_stage", {}).get("stage_id"),
    }


def verify_generic_object_handover() -> dict:
    session = start_session("home_humanoid", "home_semantic_3d_a")
    session_id = session["session_id"]
    started = begin_motion_command(session_id, "现在把苹果再递给人类")
    intent = started.get("long_horizon_intent", {})
    require(started.get("status") == "motion_started", f"explicit object handover did not authorize its necessary causal stages: {started}")
    require(intent.get("intent_type") == "verified_object_handover" and intent.get("goal_fact") == "object_received_by_recipient", f"apple handover fell back to a water-specific or unknown task: {started}")
    outcomes = drain_service(started)
    live = get_session(session_id)
    apple = next(item for item in live["runtime_objects"] if item["entity_id"] == "apple_a")
    recipient = next(item for item in live["runtime_objects"] if item["entity_id"] == "human_a")
    require([item.get("terminal_fact") for item in outcomes] == ["target_object_in_gripper", "object_received_by_recipient"], f"generic handover did not derive acquire then transfer stages: {outcomes}")
    require(apple.get("received_by") == "human_a" and "apple_a" in recipient.get("received_object_refs", []), f"recipient possession was not physically verified: {apple}: {recipient}")
    require(live.get("active_intent_id") is None, f"generic handover goal did not terminate after verification: {live.get('long_horizon_intents')}")
    episode = next(item for item in reversed(live.get("episodic_fact_memory", [])) if item.get("operator") == "handover_object")
    require(episode.get("participants", {}).get("theme") == "apple_a" and episode.get("verification_basis") == "effector_release_plus_recipient_possession_tracking", f"object-independent handover transition was not retained: {episode}")
    return {"goal_fact": "object_received_by_recipient", "theme": "apple_a", "recipient": "human_a"}


def verify_teaching_actions() -> dict:
    session = start_session("home_humanoid", "home_semantic_3d_a")
    session_id = session["session_id"]
    started = start_embodied_teaching(session_id, "给我接一杯水")
    require(started.get("status") == "teaching_control_granted", f"water teaching did not start: {started}")
    # Put the body at each interaction boundary; the controls themselves must
    # still establish their facts through the same P016 verification adapters.
    live = get_session(session_id)
    cup = next(item for item in live["runtime_objects"] if item["kind"] == "graspable_container")
    source = next(item for item in live["runtime_objects"] if item["kind"] == "water_source")
    recipient = next(item for item in live["runtime_objects"] if item["kind"] == "human_recipient")
    from embodied_scene import SESSIONS

    runtime = SESSIONS[session_id]
    runtime["state"]["executor_position"] = list(cup["position"])
    grasp = begin_teaching_control(session_id, "grasp")
    require((grasp.get("immediate_result") or grasp).get("status") == "fact_established", f"teaching grasp failed: {grasp}")
    runtime["state"]["executor_position"] = list(source["position"])
    fill = begin_teaching_control(session_id, "fill")
    require((fill.get("immediate_result") or fill).get("terminal_fact") == "container_filled", f"teaching fill failed: {fill}")
    runtime["state"]["executor_position"] = list(recipient["position"])
    handover = begin_teaching_control(session_id, "handover")
    require((handover.get("immediate_result") or handover).get("terminal_fact") == "human_received_filled_container", f"teaching handover failed: {handover}")
    compiled = finish_embodied_teaching(session_id)
    require(compiled.get("status") == "demonstration_compiled", f"service teaching did not compile: {compiled}")
    require(compiled["experience"]["goal_fact"] == "human_received_filled_container", f"wrong teaching goal: {compiled}")
    require(compiled["experience"]["role_binding_contract"]["runtime_rebinding_required"] is True, "service roles were not portable")
    return {"goal_fact": compiled["experience"]["goal_fact"], "process_chain": compiled["experience"]["process_chain"]}


def verify_repeated_obstacle_replanning() -> dict:
    session = start_session("home_humanoid", "home_semantic_3d_a")
    session_id = session["session_id"]
    active = begin_motion_command(session_id, "给我接一杯水")
    require(active.get("status") == "motion_started", f"service command was not treated as task-level authorization: {active}")
    replan_statuses = []
    for index in range(10):
        frame = step_motion_command(active["job_id"])
        require(frame.get("status") == "frame_verified_and_committed", f"replan {index + 1} did not enter motion: {frame}")
        set_stool(session_id, "ahead")
        replanned = step_motion_command(active["job_id"])
        require(replanned.get("continuation_status") == "same_intent_reobserved_and_replanned", f"replan {index + 1} lost execution intent: {replanned}")
        replacement = replanned["replacement"]
        require(replacement.get("preserved_long_horizon_context", {}).get("long_stage_id") == "acquire_container", f"replan {index + 1} lost long stage: {replanned}")
        replan_statuses.append(replanned["continuation_status"])
        active = replacement

    grasped = drain(active)
    require(grasped.get("terminal_fact") == "target_object_in_gripper", f"replanned acquisition did not finish: {grasped}")
    require(grasped.get("next_stage_started", {}).get("long_stage", {}).get("stage_id") == "fill_container", f"service stopped after replanned grasp: {grasped}")
    drain_service(grasped["next_stage_started"])
    live = get_session(session_id)
    container = next(item for item in live["runtime_objects"] if item["kind"] == "graspable_container")
    require(container.get("received_by") == "human_a", f"service did not survive repeated replans: {container}")
    return {"replan_count": len(replan_statuses), "all_preserved": len(set(replan_statuses)) == 1, "terminal_fact": "human_received_filled_container"}


def main() -> None:
    report = {
        "scene_a": complete_authorized_service("home_semantic_3d_a"),
        "scene_b": complete_authorized_service("home_semantic_3d_b"),
        "teaching": verify_teaching_actions(),
        "repeated_obstacle_replanning": verify_repeated_obstacle_replanning(),
        "compositional_service_language": verify_compositional_service_language(),
        "water_then_place_composition": verify_water_then_place_composition(),
        "post_handover_reacquisition": verify_post_handover_reacquisition_and_support_disambiguation(),
        "contrastive_evidence_gap_dialogue": verify_contrastive_evidence_gap_dialogue(),
        "generic_object_handover": verify_generic_object_handover(),
    }
    print(report)


if __name__ == "__main__":
    main()
