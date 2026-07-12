from __future__ import annotations

import os
from pathlib import Path

from embodied_scene import (
    begin_teaching_control,
    finish_embodied_teaching,
    start_embodied_teaching,
    start_session,
    step_motion_command,
    execute_command,
)


OUTPUT = Path(__file__).resolve().parents[1] / "output" / "rell_sample" / "unknown_teaching_loop"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def drain(started: dict) -> dict:
    if started.get("immediate_result"):
        return started["immediate_result"]
    job_id = started.get("job_id")
    require(job_id, f"teaching control did not produce a job: {started}")
    while True:
        step = step_motion_command(job_id)
        if step.get("status") == "motion_completed":
            return step.get("result") or step
        require(step.get("status") == "frame_verified_and_committed", f"teaching frame was not verified: {step}")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    store = OUTPUT / "unused_store.json"
    store.unlink(missing_ok=True)
    os.environ["RELL_EMBODIED_EXPERIENCE_STORE"] = str(store)
    session = start_session(scene_id="home_semantic_3d_a")
    session_id = session["session_id"]

    first = execute_command(session_id, "携来苹果")
    require(first["status"] == "concept_gap_clarification_required", f"unknown action did not ask for its target result: {first}")
    require(first["knowledge_self_report"]["next_safe_route"] == "request_minimum_causal_information", f"unknown self-report skipped causal clarification: {first}")
    second = execute_command(session_id, "让苹果在手中")
    require(second["status"] == "concept_gap_clarification_required", f"unknown action did not ask for verification: {second}")
    third = execute_command(session_id, "以看到苹果在手中为准")
    require(third["status"] == "temporary_effect_contract_compiled", f"minimum causal contract did not compile: {third}")
    require(third["post_action"]["teaching_available"], f"compiled unknown goal did not offer teaching: {third}")
    require(third["knowledge_self_report"]["unknown"], "robot failed to state that physical mechanism remains unknown")
    require(third["temporary_effect_contract"]["direct_execution_allowed"] is False, "temporary unknown contract gained execution authority")

    started = start_embodied_teaching(session_id, "携来苹果")
    require(started["status"] == "teaching_control_granted", f"unknown goal did not enter human teaching: {started}")
    require(started["teaching_session"]["target_binding_status"] == "teaching_candidate_from_unique_concept_instance", f"teaching candidate was not explicitly bounded: {started}")
    # Human demonstration: turn toward +y, move into reach, turn toward -x, then grasp.
    for control in ("turn_left", "forward", "forward", "forward", "forward", "forward", "forward", "forward", "turn_left", "forward", "forward"):
        result = drain(begin_teaching_control(session_id, control))
        require(result.get("status") in {"fact_established", "stopped_by_physical_obstacle"}, f"teaching control bypassed physical adjudication: {result}")
    grasp = begin_teaching_control(session_id, "grasp")["immediate_result"]
    require(grasp["status"] == "fact_established", f"teacher could not complete the demonstrated goal: {grasp}")
    compiled = finish_embodied_teaching(session_id)
    require(compiled["status"] == "demonstration_compiled", f"unknown teaching was not compiled: {compiled}")
    experience = compiled["experience"]
    require(experience["source_concept_contract"]["language_trigger"] == "携来", "unknown language trigger was not retained as candidate provenance")
    require(experience["goal_fact"] == "target_object_in_gripper", "unknown goal was not aligned to the verified state primitive")
    require(experience["invariant_contract"]["storage_policy"] == "store_invariants_not_concrete_teleoperation_parameters", "unknown teaching stored trajectory instead of invariants")
    require(experience["status"] == "candidate_pending_autonomous_replay", "teaching bypassed autonomous replay promotion gate")

    report = {
        "clarification_turns": third["concept_gap_analysis"]["slots"],
        "self_report": third["knowledge_self_report"],
        "teaching_target_binding_status": started["teaching_session"]["target_binding_status"],
        "compiled_experience_id": experience["experience_id"],
        "promotion_status": experience["status"],
        "invariant_contract": experience["invariant_contract"],
    }
    (OUTPUT / "unknown_teaching_report.json").write_text(__import__("json").dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    store.unlink(missing_ok=True)
    os.environ.pop("RELL_EMBODIED_EXPERIENCE_STORE", None)
    print("Unknown teaching loop validation passed.")
    print(f"Output: {OUTPUT / 'unknown_teaching_report.json'}")


if __name__ == "__main__":
    main()
