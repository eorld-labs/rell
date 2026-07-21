from __future__ import annotations

from embodied_scene import (
    SESSIONS,
    begin_motion_command,
    start_session,
    step_motion_command,
)
from evaluate_natural_language_variants import setup_human_held_cup
from concept_core.concept_gap_dialogue import start_concept_gap_dialogue
from concept_core.perceptual_grounding import load_object_concepts


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def immediate(result: dict) -> dict:
    return result.get("immediate_result") or result


def intent(result: dict) -> dict:
    return result.get("long_horizon_intent") or immediate(result).get(
        "long_horizon_intent"
    ) or {}


def prepared_session() -> str:
    session = start_session("home_humanoid", "hospitality_guest")
    setup = setup_human_held_cup(session["session_id"])
    require(setup["completed"], str(setup))
    return session["session_id"]


def validate_historical_runtime_paraphrases() -> None:
    variants = (
        "把杯子放到刚才拿杯子的桌面",
        "把杯子放回你刚刚取它的台面",
        "杯子送回原先拿起来的桌面",
        "把杯子搁到上次取杯子的桌子",
    )
    for utterance in variants:
        session_id = prepared_session()
        started = begin_motion_command(session_id, utterance)
        roles = intent(started).get("role_bindings") or {}
        resolution = started.get("historical_reference_resolution") or immediate(
            started
        ).get("historical_reference_resolution") or {}
        require(
            roles.get("theme") == "mug_white"
            and roles.get("destination") == "hospitality_counter_a"
            and immediate(started).get("status")
            in {"requires_human_confirmation", "motion_started"}
            and resolution.get("surface_text_rewritten") is False,
            f"historical runtime paraphrase failed: {utterance}: {started}",
        )


def validate_compound_runtime_paraphrases() -> None:
    variants = (
        "先把杯子放到刚才拿起来的桌面再用高脚杯接水给我",
        "杯子送回原先拿它的台面，随后高脚杯盛水递给我",
        "把杯子搁回刚才取杯子的桌子，然后换高脚杯装水送来",
    )
    for utterance in variants:
        session_id = prepared_session()
        started = begin_motion_command(session_id, utterance)
        sequence = started.get("compound_command_sequence") or immediate(
            started
        ).get("compound_command_sequence") or {}
        subtasks = sequence.get("subtasks") or []
        require(
            len(subtasks) == 2
            and subtasks[0].get("explicit_theme_ref") == "mug_white"
            and subtasks[0].get("explicit_destination_ref")
            == "hospitality_counter_a"
            and subtasks[1].get("explicit_theme_ref") == "glass_tall",
            f"compound runtime paraphrase lost event scope: {utterance}: {started}",
        )


def validate_compound_task_supersedes_stale_concept_gap() -> None:
    session = start_session("home_humanoid", "hospitality_guest")
    session_id = session["session_id"]
    # Build the exact current relation from the reported case: the guest has
    # the tall glass while the white mug remains a distinct later theme.
    from evaluate_natural_language_variants import run_to_terminal

    setup = run_to_terminal(
        session_id,
        begin_motion_command(session_id, "用高脚玻璃杯给我接一杯水"),
    )
    require(setup["completed"], str(setup))
    live = SESSIONS[session_id]
    stale = start_concept_gap_dialogue(
        utterance="我看还有很大的空间呀",
        runtime_objects=live["runtime_objects"],
        object_concepts=load_object_concepts()["concepts"],
        world_revision=live["world_revision"],
    )
    live["concept_gap_dialogue"] = stale["dialogue"]
    result = begin_motion_command(
        session_id,
        "我喝完了，把我的杯子放到操作台B，然后用白色马克杯给我倒杯水",
    )
    view = immediate(result)
    sequence = result.get("compound_command_sequence") or view.get(
        "compound_command_sequence"
    ) or {}
    subtasks = sequence.get("subtasks") or []
    require(
        len(subtasks) == 2
        and subtasks[0].get("explicit_theme_ref") == "glass_tall"
        and subtasks[0].get("explicit_destination_ref")
        == "hospitality_counter_b"
        and subtasks[1].get("explicit_theme_ref") == "mug_white",
        f"stale concept gap captured structured compound roles: {result}",
    )
    require(
        view.get("status")
        in {"requires_human_confirmation", "motion_started", "fact_established"}
        and SESSIONS[session_id].get("concept_gap_dialogue") is None,
        f"new structured task did not supersede stale concept gap: {result}",
    )
    require(
        (SESSIONS[session_id].get("concept_gap_dialogue_history") or [])[-1].get(
            "status"
        )
        == "superseded_by_new_structured_task",
        "superseded concept gap was not archived",
    )


def validate_deictic_human_proximity_navigation() -> None:
    from evaluate_natural_language_variants import run_to_terminal

    variants = (
        "好，你现在站在我这边来",
        "你站到我身边来",
        "请走到我旁边",
        "靠近我这里",
    )
    for utterance in variants:
        session = start_session("home_humanoid", "hospitality_guest")
        started = begin_motion_command(session["session_id"], utterance)
        require(
            started.get("status") == "motion_started",
            f"human-relative navigation did not start: {utterance}: {started}",
        )
        execution = run_to_terminal(session["session_id"], started)
        terminal = execution["outcomes"][-1]
        require(
            execution["completed"]
            and terminal.get("terminal_fact") == "executor_near_object"
            and (terminal.get("terminal_fact_binding") or {}).get("entity_ref")
            == "guest",
            f"human-relative navigation lost speaker grounding: {utterance}: {execution}",
        )
        language = terminal.get("language_understanding") or {}
        require(
            not language.get("unresolved_slots")
            and language.get("canonical_utterance") == "走到我这边",
            f"human-relative navigation retained a semantic gap: {utterance}: {language}",
        )


def validate_goal_schema_continuation_paraphrases() -> None:
    variants = (
        "照刚才的再来一杯",
        "按刚才那样再接一杯",
        "还是刚才的杯子，续满再递回来",
    )
    for utterance in variants:
        session_id = prepared_session()
        started = begin_motion_command(session_id, utterance)
        active = intent(started)
        require(
            active.get("goal_fact") == "human_received_filled_container"
            and (active.get("role_bindings") or {}).get("theme") == "mug_white"
            and immediate(started).get("status")
            not in {"role_clarification_required", "language_unknown"},
            f"goal-schema continuation failed: {utterance}: {started}",
        )


def validate_outcome_correction_runtime() -> None:
    session = start_session("home_humanoid", "hospitality_guest")
    session_id = session["session_id"]
    live = SESSIONS[session_id]
    objects = {item["entity_id"]: item for item in live["runtime_objects"]}
    objects["glass_tall"]["support_ref"] = "wooden_tray"
    objects["wooden_tray"]["support_ref"] = None
    objects["wooden_tray"]["attached_to_executor"] = True
    objects["wooden_tray"]["held_by_effector"] = "right_hand"
    live["state"]["holding_by_effector"]["right_hand"] = "wooden_tray"
    live["state"]["holding"] = "wooden_tray"
    corrected = begin_motion_command(
        session_id,
        "不是把托盘给我，而是只把杯子交给我，托盘留在你手上",
    )
    applied = corrected.get("task_correction_applied") or immediate(corrected).get(
        "task_correction_applied"
    ) or {}
    require(
        applied.get("correction_type")
        == "payload_transfer_carrier_retention"
        and applied.get("carrier_ref") == "wooden_tray"
        and applied.get("payload_ref") == "glass_tall",
        str(corrected),
    )


def validate_runtime_dialogue_uses_planner_refs() -> None:
    session = start_session("home_humanoid", "hospitality_guest")
    started = begin_motion_command(
        session["session_id"], "请用白色马克杯接水送给我"
    )
    view = immediate(started)
    language = view.get("language_understanding") or {}
    projection = language.get("rcir_dialogue_projection") or {}
    roles = intent(started).get("role_bindings") or {}
    require(
        projection.get("generated_from_rcir_only") is True
        and projection.get("surface_text_reparsed") is False
        and projection.get("resolved_entity_refs", {}).get("theme")
        == roles.get("theme")
        == "mug_white"
        and language.get("canonical_utterance")
        == language.get("semantic_canonical_utterance")
        and language.get("human_understanding_response")
        == projection.get("human_response")
        and language.get("canonical_utterance")
        != language.get("human_understanding_response"),
        str(started),
    )


def _finish_job(started: dict) -> dict:
    if started.get("immediate_result"):
        return started["immediate_result"]
    job_id = started.get("job_id")
    require(bool(job_id), str(started))
    while True:
        step = step_motion_command(job_id)
        if step.get("status") == "motion_completed":
            return step["result"]
        require(
            step.get("status") == "frame_verified_and_committed", str(step)
        )


def validate_region_inventory_query_runtime() -> None:
    session = start_session("home_humanoid", "home_semantic_3d_a")
    session_id = session["session_id"]
    active = begin_motion_command(session_id, "给我接杯水")
    active_intent_id = SESSIONS[session_id].get("active_intent_id")
    require(active.get("job_id") and active_intent_id, str(active))
    answered = begin_motion_command(session_id, "房间里有社么")
    language = answered.get("language_understanding") or {}
    require(
        answered.get("status") == "region_inventory_state_answered"
        and answered.get("region_ref") == "living_room"
        and "apple_a" in answered.get("entity_refs", [])
        and answered.get("runtime_fact_committed") is False
        and answered.get("task_context_preserved") is True
        and SESSIONS[session_id].get("active_intent_id") == active_intent_id
        and language.get("canonical_utterance") == "查看当前区域中的对象"
        and "当前区域里有哪些对象"
        in str(language.get("human_understanding_response"))
        and (language.get("input_normalizations") or [{}])[0].get(
            "canonical"
        )
        == "什么"
        and not SESSIONS[session_id].get("concept_gap_dialogue"),
        str(answered),
    )
    explicit = begin_motion_command(session_id, "厨房里有什么")
    require(
        explicit.get("status") == "region_inventory_state_answered"
        and explicit.get("region_ref") == "kitchen"
        and "cup_a" in explicit.get("entity_refs", [])
        and (explicit.get("language_understanding") or {}).get(
            "canonical_utterance"
        )
        == "查看厨房中的对象",
        str(explicit),
    )


def validate_compound_transition_language_ownership() -> None:
    session = start_session("home_humanoid", "home_semantic_3d_a")
    current = begin_motion_command(
        session["session_id"], "给我接杯水，然后把苹果放到桌子上"
    )
    outcomes = []
    for _ in range(3):
        outcome = _finish_job(current)
        outcomes.append(outcome)
        current = outcome.get("next_stage_started")
        if not current:
            break
    require(len(outcomes) == 3, str(outcomes))
    transition = outcomes[-1]
    language = transition.get("language_understanding") or {}
    projection = language.get("rcir_dialogue_projection") or {}
    require(
        transition.get("terminal_fact") == "human_received_filled_container"
        and language.get("canonical_utterance") == "拿起苹果"
        and projection.get("resolved_entity_refs", {}).get("theme")
        == "apple_a"
        and "苹果" in str(language.get("human_understanding_response"))
        and "白色杯子"
        not in str(language.get("human_understanding_response")),
        str(transition),
    )


def validate_classifier_delivery_and_support_query() -> None:
    for utterance, existential in (
        ("把旧报纸一拿给我", False),
        ("给我一份报纸", True),
    ):
        session = start_session("home_humanoid", "hospitality_guest")
        started = begin_motion_command(session["session_id"], utterance)
        active = intent(started)
        evidence = (active.get("role_binding_evidence") or {}).get(
            "theme", {}
        )
        outcomes = []
        current = started
        while current:
            outcome = _finish_job(current)
            outcomes.append(outcome)
            current = outcome.get("next_stage_started")
        require(
            [item.get("terminal_fact") for item in outcomes]
            == ["target_object_in_gripper", "object_received_by_recipient"]
            and active.get("goal_fact") == "object_received_by_recipient"
            and (active.get("role_bindings") or {}).get("theme")
            == "newspaper_a"
            and all(
                not (item.get("language_understanding") or {}).get(
                    "unresolved_slots"
                )
                for item in outcomes
            )
            and not SESSIONS[session["session_id"]].get(
                "concept_gap_dialogue"
            )
            and (
                not existential
                or evidence.get("selection_policy")
                == "existential_quantity_minimum_current_cost"
            ),
            str({"started": started, "outcomes": outcomes}),
        )

    query_session = start_session("home_humanoid", "hospitality_guest")
    answered = begin_motion_command(
        query_session["session_id"], "操作台B有什么"
    )
    groups = answered.get("inventory_groups") or []
    language = answered.get("language_understanding") or {}
    require(
        answered.get("status") == "support_inventory_state_answered"
        and len(groups) == 1
        and groups[0].get("support_entity_ref") == "hospitality_counter_b"
        and groups[0].get("entity_refs")
        == ["newspaper_a", "newspaper_b"]
        and language.get("canonical_utterance")
        == "查看操作台B上的当前对象"
        and "目标承载面上当前有哪些对象"
        in str(language.get("human_understanding_response")),
        str(answered),
    )


def main() -> None:
    validate_historical_runtime_paraphrases()
    validate_compound_runtime_paraphrases()
    validate_compound_task_supersedes_stale_concept_gap()
    validate_deictic_human_proximity_navigation()
    validate_goal_schema_continuation_paraphrases()
    validate_outcome_correction_runtime()
    validate_runtime_dialogue_uses_planner_refs()
    validate_region_inventory_query_runtime()
    validate_compound_transition_language_ownership()
    validate_classifier_delivery_and_support_query()
    print(
        "Contextual language runtime validation passed: historical reference, "
        "compound scope, goal-schema continuation, outcome correction, "
        "region/support inventory, classifier delivery, and "
        "transition-language ownership."
    )


if __name__ == "__main__":
    main()
