from __future__ import annotations

from embodied_scene import (
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
    require("container_filled" in stage_facts and "human_received_filled_container" in stage_facts, f"stage facts missing: {stage_facts}")
    return {"scene_id": scene_id, "stage_facts": stage_facts, "route_kinds": route_kinds}


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
    first = begin_motion_command(session_id, "给我接一杯水")
    require(first.get("status") == "motion_started", f"service command was not treated as task-level authorization: {first}")
    active = first
    first_frame = step_motion_command(active["job_id"])
    require(first_frame.get("status") == "frame_verified_and_committed", f"service did not enter motion: {first_frame}")

    set_stool(session_id, "ahead")
    first_replan = step_motion_command(active["job_id"])
    require(first_replan.get("continuation_status") == "same_intent_reobserved_and_replanned", f"first replan lost execution intent: {first_replan}")
    require(first_replan["replacement"].get("preserved_long_horizon_context", {}).get("long_stage_id") == "acquire_container", f"first replan lost long stage: {first_replan}")

    replacement = first_replan["replacement"]
    replacement_frame = step_motion_command(replacement["job_id"])
    require(replacement_frame.get("status") == "frame_verified_and_committed", f"replacement did not enter motion: {replacement_frame}")
    set_stool(session_id, "ahead")
    second_replan = step_motion_command(replacement["job_id"])
    require(second_replan.get("continuation_status") == "same_intent_reobserved_and_replanned", f"second replan lost execution intent: {second_replan}")
    require(second_replan["replacement"].get("preserved_long_horizon_context", {}).get("long_stage_id") == "acquire_container", f"second replan lost long stage: {second_replan}")

    grasped = drain(second_replan["replacement"])
    require(grasped.get("terminal_fact") == "target_object_in_gripper", f"replanned acquisition did not finish: {grasped}")
    require(grasped.get("next_stage_started", {}).get("long_stage", {}).get("stage_id") == "fill_container", f"service stopped after replanned grasp: {grasped}")
    drain_service(grasped["next_stage_started"])
    live = get_session(session_id)
    container = next(item for item in live["runtime_objects"] if item["kind"] == "graspable_container")
    require(container.get("received_by") == "human_a", f"service did not survive repeated replans: {container}")
    return {"first_replan": first_replan["continuation_status"], "second_replan": second_replan["continuation_status"], "terminal_fact": "human_received_filled_container"}


def main() -> None:
    report = {
        "scene_a": complete_authorized_service("home_semantic_3d_a"),
        "scene_b": complete_authorized_service("home_semantic_3d_b"),
        "teaching": verify_teaching_actions(),
        "repeated_obstacle_replanning": verify_repeated_obstacle_replanning(),
    }
    print(report)


if __name__ == "__main__":
    main()
