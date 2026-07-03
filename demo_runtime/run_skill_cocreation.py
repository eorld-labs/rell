from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "skill_data"
OUTPUT_DIR = ROOT / "output" / "skill_cocreation"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def capability_types(robot: dict[str, Any]) -> set[str]:
    return {capability["action_type"] for capability in robot["capabilities"]}


def build_task_plan(scenario: dict[str, Any], robot: dict[str, Any]) -> dict[str, Any]:
    capabilities = capability_types(robot)
    steps = [
        {
            "step_id": "step_001",
            "intent": "扫描桌面空间并建立空间语义上下文",
            "action_type": "scan_space",
            "target_refs": ["desk_surface"],
            "expected_outcome": "space_context_created",
        },
        {
            "step_id": "step_002",
            "intent": "识别并分类桌面对象",
            "action_type": "classify_object",
            "target_refs": [obj["object_id"] for obj in scenario["objects"]],
            "expected_outcome": "objects_classified",
        },
        {
            "step_id": "step_003",
            "intent": "将低风险可移动对象移动到收纳区",
            "action_type": "move_light_object",
            "target_refs": ["obj_mug_001"],
            "expected_outcome": "low_risk_object_moved",
        },
        {
            "step_id": "step_004",
            "intent": "对高敏票据只创建候选动作，不直接移动",
            "action_type": "create_candidate_action",
            "target_refs": ["obj_invoice_001"],
            "expected_outcome": "candidate_action_created",
        },
        {
            "step_id": "step_005",
            "intent": "尝试处理遮挡收纳盒并记录补救经验",
            "action_type": "move_light_object",
            "target_refs": ["obj_box_001"],
            "expected_outcome": "blocked_path_recovered",
        },
        {
            "step_id": "step_006",
            "intent": "请求人类反馈并写入偏好层",
            "action_type": "request_human_feedback",
            "target_refs": ["exp_step_003", "exp_step_004"],
            "expected_outcome": "human_preferences_recorded",
        },
    ]
    for step in steps:
        step["capability_state"] = "available" if step["action_type"] in capabilities else "missing"
        step["governance_policy_ref"] = f"policy_{step['action_type']}"

    return {
        "task_id": "task_office_desk_001",
        "human_goal": scenario["task_goal"],
        "space_context_refs": [scenario["scenario_id"]],
        "robot_ref": robot["robot_id"],
        "steps": steps,
    }


def simulate_step(step: dict[str, Any]) -> dict[str, Any]:
    step_id = step["step_id"]
    if step["capability_state"] == "missing":
        return {
            "outcome_type": "failed",
            "state_delta": "capability_missing",
            "evidence_refs": [f"log_{step_id}"],
        }
    if step_id == "step_004":
        return {
            "outcome_type": "candidate_created",
            "state_delta": "invoice_candidate_created",
            "evidence_refs": ["candidate_invoice_move_001"],
        }
    if step_id == "step_005":
        return {
            "outcome_type": "failed",
            "state_delta": "box_path_blocked",
            "evidence_refs": ["blocked_path_snapshot_001"],
        }
    return {
        "outcome_type": "success",
        "state_delta": step["expected_outcome"],
        "evidence_refs": [f"log_{step_id}"],
    }


def build_experience(step: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    return {
        "experience_id": f"exp_{step['step_id']}",
        "context": {
            "task_ref": "task_office_desk_001",
            "space_refs": ["scn_office_desk_001"],
            "human_intent_ref": "goal_office_desk_organize",
        },
        "action": {
            "action_type": step["action_type"],
            "target_refs": step["target_refs"],
            "parameters": {
                "intent": step["intent"],
                "expected_outcome": step["expected_outcome"],
            },
        },
        "outcome": outcome,
        "governance_ref": {
            "decision_token_ref": f"dt_{step['step_id']}",
            "audit_ref": "skill_audit_office_desk_001",
            "source_chain_ref": f"src_{step['step_id']}",
        },
        "created_at": now_iso(),
    }


def build_recovery_records(experiences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for experience in experiences:
        if experience["outcome"]["outcome_type"] != "failed":
            continue
        records.append(
            {
                "recovery_id": f"rec_{experience['experience_id']}",
                "failed_experience_ref": experience["experience_id"],
                "deviation_context": {
                    "deviation_type": experience["outcome"]["state_delta"],
                    "observed_state": "blocked_or_unavailable",
                    "expected_state": "task_can_continue",
                },
                "recovery_action": {
                    "action_type": "ask_human_to_clear_path",
                    "parameters": {
                        "message": "请移开遮挡物后继续整理。"
                    },
                    "human_intervention": True,
                },
                "recovery_outcome": {
                    "outcome_type": "recovered",
                    "notes": "人工清理遮挡后，技能包记录该场景需要预先检查路径。"
                },
            }
        )
    return records


def build_preference_records() -> list[dict[str, Any]]:
    return [
        {
            "preference_id": "pref_keep_financial_docs_candidate",
            "context_ref": "scn_office_desk_001",
            "experience_ref": "exp_step_004",
            "preference_signal": "forbid",
            "human_feedback": "财务票据不要自动移动，只允许生成候选动作。",
            "applies_to": ["financial_document", "high_sensitivity_document"],
            "strength": 1.0,
            "created_at": now_iso(),
        },
        {
            "preference_id": "pref_accept_mug_storage",
            "context_ref": "scn_office_desk_001",
            "experience_ref": "exp_step_003",
            "preference_signal": "accept",
            "human_feedback": "马克杯移动到收纳区符合预期。",
            "applies_to": ["daily_object", "low_risk"],
            "strength": 0.8,
            "created_at": now_iso(),
        },
    ]


def build_concept_patterns(experiences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "pattern_id": "pattern_safe_desk_organize",
            "concept_labels": ["desk_organize", "candidate_for_sensitive", "recover_blocked_path"],
            "source_experience_refs": [experience["experience_id"] for experience in experiences],
            "generalized_steps": [
                {
                    "step_type": "scan_space",
                    "expected_effect": "space_context_created",
                    "constraints": ["must_run_before_object_actions"],
                },
                {
                    "step_type": "move_low_risk_object",
                    "expected_effect": "object_relocated",
                    "constraints": ["object_sensitivity_low"],
                },
                {
                    "step_type": "candidate_for_sensitive_object",
                    "expected_effect": "candidate_action_created",
                    "constraints": ["object_sensitivity_high"],
                },
                {
                    "step_type": "recover_blocked_path",
                    "expected_effect": "human_clearance_requested",
                    "constraints": ["path_blocked"],
                },
            ],
            "transfer_scope": {
                "applicable_regions": ["office_desk", "home_desk", "front_desk"],
                "excluded_conditions": ["hazardous_object", "unknown_high_payload"],
            },
        }
    ]


def build_skill_package(
    task_plan: dict[str, Any],
    experiences: list[dict[str, Any]],
    recoveries: list[dict[str, Any]],
    preferences: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "skill_id": "skill_desk_organize_basic",
        "name": "基础桌面整理技能",
        "version": "0.1.0",
        "applicable_context": {
            "space_types": ["office_desk", "home_desk"],
            "robot_capabilities": ["scan_space", "classify_object", "move_light_object", "create_candidate_action"],
            "constraints": [
                "high_sensitivity_objects_candidate_only",
                "blocked_path_requires_recovery",
                "human_feedback_required",
            ],
        },
        "steps": [
            {
                "step_id": step["step_id"],
                "action_type": step["action_type"],
                "input_refs": step["target_refs"],
                "expected_outcome": step["expected_outcome"],
                "recovery_refs": [record["recovery_id"] for record in recoveries if step["step_id"] in record["failed_experience_ref"]],
            }
            for step in task_plan["steps"]
            if step["step_id"] != "step_006"
        ],
        "preference_refs": [preference["preference_id"] for preference in preferences],
        "governance_refs": [f"dt_{step['step_id']}" for step in task_plan["steps"]],
        "evidence": {
            "experience_refs": [experience["experience_id"] for experience in experiences],
            "evaluation_refs": ["eval_skill_cocreation_mvp_001"],
            "audit_refs": ["skill_audit_office_desk_001"],
        },
    }


def build_training_session(task_plan: dict[str, Any], experiences: list[dict[str, Any]], recoveries: list[dict[str, Any]], preferences: list[dict[str, Any]]) -> dict[str, Any]:
    events = []
    for experience in experiences:
        events.append({"event_id": f"evt_{experience['experience_id']}", "event_type": "experience_recorded", "ref": experience["experience_id"]})
    for recovery in recoveries:
        events.append({"event_id": f"evt_{recovery['recovery_id']}", "event_type": "recovery_recorded", "ref": recovery["recovery_id"]})
    for preference in preferences:
        events.append({"event_id": f"evt_{preference['preference_id']}", "event_type": "preference_recorded", "ref": preference["preference_id"]})
    return {
        "session_id": "session_office_desk_001",
        "scenario_ref": "scn_office_desk_001",
        "robot_ref": task_plan["robot_ref"],
        "task_plan_ref": task_plan["task_id"],
        "events": events,
        "created_at": now_iso(),
    }


def build_skill_audit(session: dict[str, Any], skill: dict[str, Any], experiences: list[dict[str, Any]], recoveries: list[dict[str, Any]], preferences: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "audit_id": "skill_audit_office_desk_001",
        "session_ref": session["session_id"],
        "skill_ref": skill["skill_id"],
        "summary": {
            "total_steps": 6,
            "experiences": len(experiences),
            "recoveries": len(recoveries),
            "preferences": len(preferences),
            "skill_steps": len(skill["steps"]),
        },
        "evidence_refs": [
            "task_plan.json",
            "training_session.json",
            "experience_records.json",
            "recovery_records.json",
            "preference_records.json",
            "skill_package.json",
        ],
        "created_at": now_iso(),
    }


def run_pipeline() -> dict[str, Any]:
    scenario = read_json(DATA_DIR / "scenario.json")
    robot = read_json(DATA_DIR / "robot_capability.json")
    task_plan = build_task_plan(scenario, robot)

    experiences = [build_experience(step, simulate_step(step)) for step in task_plan["steps"]]
    recoveries = build_recovery_records(experiences)
    preferences = build_preference_records()
    concept_patterns = build_concept_patterns(experiences)
    skill = build_skill_package(task_plan, experiences, recoveries, preferences)
    session = build_training_session(task_plan, experiences, recoveries, preferences)
    audit = build_skill_audit(session, skill, experiences, recoveries, preferences)

    write_json(OUTPUT_DIR / "scenario_context.json", scenario)
    write_json(OUTPUT_DIR / "robot_capability.json", robot)
    write_json(OUTPUT_DIR / "task_plan.json", task_plan)
    write_json(OUTPUT_DIR / "training_session.json", session)
    write_json(OUTPUT_DIR / "experience_records.json", experiences)
    write_json(OUTPUT_DIR / "recovery_records.json", recoveries)
    write_json(OUTPUT_DIR / "preference_records.json", preferences)
    write_json(OUTPUT_DIR / "concept_patterns.json", concept_patterns)
    write_json(OUTPUT_DIR / "skill_package.json", skill)
    write_json(OUTPUT_DIR / "skill_audit.json", audit)
    return audit


def main() -> None:
    audit = run_pipeline()
    print("Skill co-creation demo completed.")
    print(f"Output: {OUTPUT_DIR}")
    print(json.dumps(audit["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
