from __future__ import annotations

import json
from pathlib import Path

from api_server import (
    CONCEPT_CANDIDATE_LIBRARY_FILE,
    EXPERIENCE_LIBRARY_FILE,
    dispatch_execution_loop_payload,
    execute_teaching_session_step,
    handle_agent_query,
    inject_runtime_perturbation,
    migrate_experience,
    run_process,
    start_teaching_session,
    teach_experience,
)


OUTPUT = Path(__file__).resolve().parent.parent / "output" / "rell_sample" / "p019_behavior_scenarios"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def restore(path: Path, content: str | None) -> None:
    if content is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(content, encoding="utf-8")


def main() -> None:
    original_experiences = EXPERIENCE_LIBRARY_FILE.read_text(encoding="utf-8") if EXPERIENCE_LIBRARY_FILE.exists() else None
    original_candidates = CONCEPT_CANDIDATE_LIBRARY_FILE.read_text(encoding="utf-8") if CONCEPT_CANDIDATE_LIBRARY_FILE.exists() else None
    report: dict[str, object] = {"schema_version": "1.0.0", "scenarios": {}}

    try:
        unknown_utterance = "把杯子准备好"
        before_teaching = handle_agent_query(unknown_utterance, auto_execute=False)
        before_route = before_teaching.get("route_result", {})
        before_intent = before_route.get("intent_translation", {})
        require(before_intent.get("decision") == "unsupported", f"unknown task must explain it is unsupported: {before_teaching}")
        require(bool(before_intent.get("reason")), f"unknown task must include a reason: {before_teaching}")
        learning_followup = before_route.get("learning_followup", {})
        require(learning_followup.get("status") == "unable_but_teachable", f"unknown task must enter teachable post-processing: {before_teaching}")
        require(bool(learning_followup.get("questions_for_human")), f"unknown task must ask the human how to teach it: {before_teaching}")
        require(before_route.get("cloud_recall_preview", {}).get("should_request_cloud_recall"), f"object recognition alone must not hide an action/experience gap: {before_teaching}")

        teaching = teach_experience(unknown_utterance, ["走向操作台", "拿起杯子"])
        require(teaching.get("decision") == "experience_created", f"human teaching must create experience: {teaching}")
        after_teaching = handle_agent_query(unknown_utterance, scenario="auto", auto_execute=True)
        after_result = after_teaching.get("route_result", {})
        require(after_result.get("audit_summary", {}).get("outcome") == "completed", f"taught task must execute later: {after_teaching}")
        require(after_result.get("intent_translation", {}).get("task_type") == "learned_process_chain", f"rerun must use learned experience: {after_teaching}")
        report["scenarios"]["unknown_teach_reuse"] = {
            "utterance": unknown_utterance,
            "before_teaching": {
                "decision": before_intent.get("decision"),
                "reason": before_intent.get("reason"),
                "cloud_recall_preview": before_route.get("cloud_recall_preview"),
                "learning_followup": learning_followup,
            },
            "teaching": {
                "decision": teaching.get("decision"),
                "experience_id": teaching.get("experience", {}).get("experience_id"),
                "process_chain": teaching.get("experience", {}).get("process_chain", []),
                "goal_fact": teaching.get("experience", {}).get("goal_fact"),
            },
            "after_teaching": {
                "task_type": after_result.get("intent_translation", {}).get("task_type"),
                "process_chain": after_result.get("intent_translation", {}).get("candidate_process_chain", []),
                "outcome": after_result.get("audit_summary", {}).get("outcome"),
            },
        }

        pickup = run_process("auto", "拿起杯子")
        fill = run_process("auto", "到水源处接一杯水")
        require(pickup.get("intent_translation", {}).get("candidate_process_chain") == ["move_to_counter", "pick_up_cup"], f"pickup must infer navigation prerequisite: {pickup}")
        require(fill.get("intent_translation", {}).get("candidate_process_chain") == ["move_to_counter", "pick_up_cup", "move_to_water_source", "fill_cup_at_water_source"], f"fill must infer cup and navigation prerequisites: {fill}")
        report["scenarios"]["stage_goal_causal_completion"] = {
            "pickup": {
                "goal_fact": pickup.get("intent_translation", {}).get("goal_fact"),
                "process_chain": pickup.get("intent_translation", {}).get("candidate_process_chain", []),
                "reasoning": pickup.get("intent_translation", {}).get("causal_plan", {}).get("reasoning", []),
            },
            "fill": {
                "goal_fact": fill.get("intent_translation", {}).get("goal_fact"),
                "process_chain": fill.get("intent_translation", {}).get("candidate_process_chain", []),
                "reasoning": fill.get("intent_translation", {}).get("causal_plan", {}).get("reasoning", []),
            },
        }

        active = start_teaching_session("到水源处接一杯水")
        for step in ["走向操作台", "拿起杯子"]:
            feedback = execute_teaching_session_step(active["session_id"], step)
            require(feedback.get("step_feedback", [{}])[0].get("executed"), f"setup step must execute: {feedback}")
        switch = handle_agent_query("别做了你去拿那个苹果", task_id=active["session_id"], auto_execute=True)
        switch_result = switch.get("route_result", {})
        require(switch_result.get("runtime_event_arbitration", {}).get("decision") == "request_human_confirmation", f"unknown switch while holding cup must request confirmation: {switch}")
        require("object_cup_white_mug" in switch_result.get("runtime_event_arbitration", {}).get("world_state_basis", {}).get("holding_objects", []), f"switch must preserve held object state: {switch}")

        detour = migrate_experience("到水源处接一杯水")
        injection = inject_runtime_perturbation(detour["migration_task_id"], {"kind": "stool_in_walkway_detourable"}, apply_before_step="move_to_water_source")
        dispatch = dispatch_execution_loop_payload(detour["execution_loop_payload"], "robot_sdk")
        move_feedback = next(item for item in dispatch.get("fact_feedback", []) if item.get("step") == "move_to_water_source")
        require(move_feedback.get("preflight_result") == "detour", f"detourable obstacle must trigger local detour: {dispatch}")
        require(dispatch.get("outcome") == "fact_established", f"detour must preserve goal completion: {dispatch}")
        report["scenarios"]["interrupt_and_obstacle"] = {
            "task_switch": {
                "utterance": "别做了你去拿那个苹果",
                "decision": switch_result.get("runtime_event_arbitration", {}).get("decision"),
                "reason": switch_result.get("runtime_event_arbitration", {}).get("reason"),
                "holding_objects": switch_result.get("runtime_event_arbitration", {}).get("world_state_basis", {}).get("holding_objects", []),
                "required_actions": switch_result.get("runtime_event_arbitration", {}).get("required_actions", []),
            },
            "detour": {
                "perturbation": injection.get("injected_perturbation"),
                "preflight_result": move_feedback.get("preflight_result"),
                "route_adjustment": move_feedback.get("route_adjustment"),
                "outcome": dispatch.get("outcome"),
            },
        }

        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / "behavior_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("P019 behavior scenario validation passed.")
        print(f"Output: {OUTPUT / 'behavior_report.json'}")
    finally:
        restore(EXPERIENCE_LIBRARY_FILE, original_experiences)
        restore(CONCEPT_CANDIDATE_LIBRARY_FILE, original_candidates)


if __name__ == "__main__":
    main()
