from __future__ import annotations

import hashlib
import json
import platform
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from embodied_scene import (
    MOTION_JOBS,
    begin_motion_command,
    get_session,
    start_session,
    step_motion_command,
)


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
OUTPUT_ROOT = (
    REPO_ROOT / "技术库" / "P020-统一中间表示" / "证据包"
)


CASES = (
    {
        "case_id": "H01",
        "group": "historical_failure",
        "utterance": "用白色马克杯给我接一杯水",
        "kind": "water_delivery",
        "expected_theme": "mug_white",
        "execute": True,
    },
    {
        "case_id": "H02",
        "group": "historical_failure",
        "utterance": "我喝完了，再帮我用白色杯子接一杯水",
        "kind": "water_delivery",
        "expected_theme": "mug_white",
        "setup_human_held_cup": True,
        "execute": True,
    },
    {
        "case_id": "H03",
        "group": "historical_failure",
        "utterance": "好，现在帮我把杯子放到桌子上去，用高脚杯给我倒一杯水",
        "kind": "compound_destination_gap",
        "setup_human_held_cup": True,
    },
    {
        "case_id": "H04",
        "group": "historical_failure",
        "utterance": "用玻璃高脚杯给我倒杯水，放在托盘上拿给我",
        "kind": "carrier_delivery",
        "expected_theme": "glass_tall",
        "execute": True,
    },
    {
        "case_id": "H05",
        "group": "historical_failure",
        "utterance": "我喝完了，再接一杯水。这次把杯子放在托盘里然后给我",
        "kind": "carrier_delivery",
        "expected_theme": "mug_white",
        "setup_human_held_cup": True,
    },
    {
        "case_id": "H06",
        "group": "historical_failure",
        "utterance": "我喝完了，现在把杯子放到刚才你拿杯子的桌子上",
        "kind": "relational_placement",
        "expected_theme": "mug_white",
        "setup_human_held_cup": True,
        "execute": True,
    },
    {
        "case_id": "H07",
        "group": "historical_failure",
        "utterance": "我喝完了，把杯子放在有高脚玻璃杯的桌子上",
        "kind": "relational_placement",
        "expected_theme": "mug_white",
        "setup_human_held_cup": True,
    },
    {
        "case_id": "H08",
        "group": "historical_failure",
        "utterance": "杯子还在我手中，你来拿过去，再把水接了放在托盘上给我",
        "kind": "carrier_delivery",
        "expected_theme": "mug_white",
        "setup_human_held_cup": True,
    },
    {
        "case_id": "U01",
        "group": "unseen_paraphrase",
        "utterance": "劳驾取一杯水送到我手里",
        "kind": "water_delivery",
    },
    {
        "case_id": "U02",
        "group": "unseen_paraphrase",
        "utterance": "拿那只白色的马克杯装水递给我",
        "kind": "water_delivery",
        "expected_theme": "mug_white",
    },
    {
        "case_id": "U03",
        "group": "unseen_paraphrase",
        "utterance": "高脚玻璃杯接好水后搁在木托盘上端来，只把杯子交给我",
        "kind": "carrier_delivery",
        "expected_theme": "glass_tall",
    },
    {
        "case_id": "U04",
        "group": "unseen_paraphrase",
        "utterance": "用高脚杯盛水，托盘承着送来，杯子给我而托盘留在你手上",
        "kind": "carrier_delivery",
        "expected_theme": "glass_tall",
    },
    {
        "case_id": "U05",
        "group": "unseen_paraphrase",
        "utterance": "刚才那杯喝光了，拿我手里的杯子续满再递回来",
        "kind": "water_delivery",
        "expected_theme": "mug_white",
        "setup_human_held_cup": True,
    },
    {
        "case_id": "U06",
        "group": "unseen_paraphrase",
        "utterance": "喝好了，把我手上这只杯子送回原先取它的台面",
        "kind": "relational_placement",
        "expected_theme": "mug_white",
        "setup_human_held_cup": True,
    },
    {
        "case_id": "U07",
        "group": "unseen_paraphrase",
        "utterance": "先把我手里的杯子归还原桌，再换高脚杯接水给我",
        "kind": "compound_destination_gap",
        "setup_human_held_cup": True,
        "destination_resolved": True,
    },
    {
        "case_id": "U08",
        "group": "unseen_paraphrase",
        "utterance": "请用白马克杯盛点常温水送过来",
        "kind": "water_delivery",
        "expected_theme": "mug_white",
    },
)


def immediate(result: dict[str, Any]) -> dict[str, Any]:
    return result.get("immediate_result") or result


def intent_view(result: dict[str, Any]) -> dict[str, Any]:
    return result.get("long_horizon_intent") or immediate(result).get(
        "long_horizon_intent"
    ) or {}


def drain_job(job_id: str, *, max_frames: int = 3000) -> dict[str, Any]:
    for _ in range(max_frames):
        step = step_motion_command(job_id)
        if step.get("status") == "motion_completed":
            return step["result"]
        if step.get("status") == "path_invalidated_and_replanned":
            replacement = step.get("replacement") or {}
            if replacement.get("job_id"):
                job_id = replacement["job_id"]
                continue
            return immediate(replacement)
        if step.get("status") != "frame_verified_and_committed":
            return step
    return {"status": "benchmark_frame_limit_exceeded", "job_id": job_id}


def run_to_terminal(
    session_id: str, started: dict[str, Any], *, max_stages: int = 16
) -> dict[str, Any]:
    current = started
    outcomes = []
    for _ in range(max_stages):
        current_view = immediate(current)
        if (
            current_view.get("status") == "requires_human_confirmation"
            and not current.get("job_id")
        ):
            current = begin_motion_command(session_id, "确认")
            continue
        job_id = current.get("job_id")
        if not job_id:
            return {
                "completed": False,
                "reason": current_view.get("status") or "motion_job_missing",
                "outcomes": outcomes,
            }
        outcome = drain_job(job_id)
        outcomes.append(outcome)
        if outcome.get("status") not in {
            "fact_established",
            "long_intent_stage_completed",
            "long_intent_completed",
        }:
            return {
                "completed": False,
                "reason": outcome.get("status"),
                "outcomes": outcomes,
            }
        next_stage = outcome.get("next_stage_started")
        if next_stage:
            current = next_stage
            continue
        lifecycle = (outcome.get("long_horizon_intent") or {}).get("lifecycle")
        if outcome.get("pending_confirmation") and lifecycle == "active":
            current = begin_motion_command(session_id, "确认")
            continue
        live = get_session(session_id)
        return {
            "completed": live.get("active_intent_id") is None,
            "reason": "terminal_world_state_reached"
            if live.get("active_intent_id") is None
            else "active_intent_remained",
            "outcomes": outcomes,
        }
    return {
        "completed": False,
        "reason": "benchmark_stage_limit_exceeded",
        "outcomes": outcomes,
    }


def setup_human_held_cup(session_id: str) -> dict[str, Any]:
    started = begin_motion_command(session_id, "用白色马克杯给我接一杯水")
    execution = run_to_terminal(session_id, started)
    live = get_session(session_id)
    mug = next(item for item in live["runtime_objects"] if item["entity_id"] == "mug_white")
    return {
        "completed": execution["completed"],
        "mug_received_by_guest": mug.get("received_by") == "guest",
        "terminal_facts": [
            item.get("terminal_fact") for item in execution["outcomes"]
        ],
    }


def score_plan(case: dict[str, Any], started: dict[str, Any]) -> dict[str, Any]:
    view = immediate(started)
    intent = intent_view(started)
    sequence = started.get("compound_command_sequence") or view.get(
        "compound_command_sequence"
    ) or {}
    bindings = intent.get("role_bindings") or {}
    checks: dict[str, bool] = {}
    if case["kind"] == "water_delivery":
        if case.get("expected_theme"):
            checks["goal_relation"] = (
                intent.get("goal_fact") == "human_received_filled_container"
            )
            checks["entered_task_flow"] = view.get("status") in {
                "motion_started",
                "requires_human_confirmation",
            }
            checks["no_container_reprompt"] = view.get("status") not in {
                "role_clarification_required",
                "process_slot_clarification_required",
            }
        else:
            checks["goal_preserved_during_safe_clarification"] = (
                view.get("status") == "role_clarification_required"
                and view.get("known_goal") == "human_received_filled_container"
                and view.get("pending_role") == "theme"
            )
        if case.get("expected_theme"):
            checks["theme_binding"] = bindings.get("theme") == case["expected_theme"]
    elif case["kind"] == "carrier_delivery":
        subtasks = sequence.get("subtasks") or []
        carrier_task = subtasks[0] if len(subtasks) == 1 else {}
        checks.update(
            {
                "single_carrier_goal": len(subtasks) == 1,
                "carrier_task_type": carrier_task.get("subtask_kind")
                == "payload_carrier_delivery",
                "payload_binding": carrier_task.get("payload_ref")
                == case.get("expected_theme"),
                "carrier_binding": carrier_task.get("carrier_ref") == "wooden_tray",
                "carrier_retained": carrier_task.get("delivery_mode")
                == "payload_only_carrier_retained",
                "entered_task_flow": view.get("status") in {
                    "motion_started",
                    "requires_human_confirmation",
                },
            }
        )
    elif case["kind"] == "relational_placement":
        checks.update(
            {
                "goal_relation": intent.get("goal_fact")
                == "object_supported_at_destination",
                "theme_binding": bindings.get("theme") == case.get("expected_theme"),
                "destination_binding": bindings.get("destination")
                == "hospitality_counter_a",
                "source_holder_binding": bindings.get("source_holder") == "guest",
                "entered_task_flow": view.get("status") in {
                    "motion_started",
                    "requires_human_confirmation",
                },
            }
        )
    elif case["kind"] == "compound_destination_gap":
        subtasks = sequence.get("subtasks") or []
        destination_scope_handled = (
            view.get("status") in {"motion_started", "requires_human_confirmation"}
            if case.get("destination_resolved")
            else view.get("status") == "process_slot_clarification_required"
        )
        checks.update(
            {
                "destination_scope_handled": destination_scope_handled,
                "two_subtasks_preserved": len(subtasks) == 2,
                "first_theme_is_current_cup": bool(subtasks)
                and subtasks[0].get("explicit_theme_ref") == "mug_white",
                "first_destination_is_prior_support": bool(subtasks)
                and (
                    not case.get("destination_resolved")
                    or subtasks[0].get("explicit_destination_ref")
                    == "hospitality_counter_a"
                ),
                "second_theme_is_tall_glass": len(subtasks) == 2
                and subtasks[1].get("explicit_theme_ref") == "glass_tall",
            }
        )
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "status": view.get("status"),
        "goal_fact": intent.get("goal_fact"),
        "role_bindings": deepcopy(bindings),
        "compound_summary": {
            "subtask_count": len(sequence.get("subtasks") or []),
            "subtasks": deepcopy(sequence.get("subtasks") or []),
        },
    }


def verify_terminal_world(case: dict[str, Any], session_id: str) -> dict[str, Any]:
    live = get_session(session_id)
    objects = {item["entity_id"]: item for item in live["runtime_objects"]}
    theme = case.get("expected_theme") or "mug_white"
    item = objects.get(theme) or {}
    checks = {"active_intent_released": live.get("active_intent_id") is None}
    if case["kind"] == "water_delivery":
        checks.update(
            {
                "container_filled": item.get("liquid_state") == "filled",
                "human_received": item.get("received_by") == "guest",
            }
        )
    elif case["kind"] == "carrier_delivery":
        tray = objects.get("wooden_tray") or {}
        checks.update(
            {
                "payload_filled": item.get("liquid_state") == "filled",
                "payload_received": item.get("received_by") == "guest",
                "tray_not_transferred": tray.get("received_by") is None,
                "tray_retained_by_executor": tray.get("attached_to_executor") is True,
            }
        )
    elif case["kind"] == "relational_placement":
        checks.update(
            {
                "placed_on_expected_support": item.get("support_ref")
                == "hospitality_counter_a",
                "not_held_by_human": item.get("received_by") is None,
            }
        )
    return {"passed": all(checks.values()), "checks": checks}


def rate(passed: int, total: int) -> float:
    return round(100.0 * passed / total, 1) if total else 0.0


def main() -> None:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    output = OUTPUT_ROOT / f"自然语言变体评估-{timestamp}"
    output.mkdir(parents=True)
    records = []
    for case in CASES:
        session = start_session("home_humanoid", "hospitality_guest")
        session_id = session["session_id"]
        setup = None
        if case.get("setup_human_held_cup"):
            setup = setup_human_held_cup(session_id)
        started = begin_motion_command(session_id, case["utterance"])
        plan = score_plan(case, started)
        execution = None
        terminal = None
        if case.get("execute") and plan["passed"]:
            execution = run_to_terminal(session_id, started)
            terminal = verify_terminal_world(case, session_id)
        record = {
            **case,
            "session_id": session_id,
            "setup": setup,
            "planning": plan,
            "execution": execution,
            "terminal_world_verification": terminal,
            "raw_start_response": deepcopy(started),
        }
        records.append(record)
        (output / "原始案例").mkdir(exist_ok=True)
        (output / "原始案例" / f"{case['case_id']}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    historical = [item for item in records if item["group"] == "historical_failure"]
    unseen = [item for item in records if item["group"] == "unseen_paraphrase"]
    plan_passed = sum(item["planning"]["passed"] for item in records)
    historical_passed = sum(item["planning"]["passed"] for item in historical)
    unseen_passed = sum(item["planning"]["passed"] for item in unseen)
    execution_records = [item for item in records if item["execution"] is not None]
    execution_passed = sum(
        bool(item["execution"]["completed"])
        and bool((item["terminal_world_verification"] or {}).get("passed"))
        for item in execution_records
    )
    summary = {
        "schema_version": "1.0.0",
        "collected_at": datetime.now().astimezone().isoformat(),
        "case_count": len(records),
        "planning_success": {
            "passed": plan_passed,
            "total": len(records),
            "rate_percent": rate(plan_passed, len(records)),
        },
        "historical_failure_retest": {
            "historical_observed_success_rate_percent": 0.0,
            "current_passed": historical_passed,
            "total": len(historical),
            "current_rate_percent": rate(historical_passed, len(historical)),
            "observed_improvement_percentage_points": rate(
                historical_passed, len(historical)
            ),
            "comparison_note": "历史基线来自此前交互日志中的失败结果，不是同一代码环境的A/B重跑。",
        },
        "unseen_paraphrases": {
            "passed": unseen_passed,
            "total": len(unseen),
            "rate_percent": rate(unseen_passed, len(unseen)),
        },
        "end_to_end_sample": {
            "passed": execution_passed,
            "attempted": len(execution_records),
            "rate_percent": rate(execution_passed, len(execution_records)),
        },
        "failed_cases": [
            {
                "case_id": item["case_id"],
                "utterance": item["utterance"],
                "status": item["planning"]["status"],
                "failed_checks": [
                    name
                    for name, passed in item["planning"]["checks"].items()
                    if not passed
                ],
            }
            for item in records
            if not item["planning"]["passed"]
        ],
        "execution_failures": [
            {
                "case_id": item["case_id"],
                "reason": (item["execution"] or {}).get("reason"),
                "terminal_checks": (
                    item["terminal_world_verification"] or {}
                ).get("checks"),
            }
            for item in execution_records
            if not (
                item["execution"]["completed"]
                and (item["terminal_world_verification"] or {}).get("passed")
            )
        ],
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "scene": "hospitality_guest",
            "executor_profile": "home_humanoid",
        },
    }
    (output / "00-评估摘要.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    table_lines = [
        "# 自然语言变体评估",
        "",
        f"- 规划成功率：{summary['planning_success']['passed']}/{summary['planning_success']['total']}（{summary['planning_success']['rate_percent']}%）",
        f"- 历史失败原句复测：{summary['historical_failure_retest']['current_passed']}/{summary['historical_failure_retest']['total']}（提升 {summary['historical_failure_retest']['observed_improvement_percentage_points']} 个百分点）",
        f"- 未见改写句：{summary['unseen_paraphrases']['passed']}/{summary['unseen_paraphrases']['total']}（{summary['unseen_paraphrases']['rate_percent']}%）",
        f"- 端到端抽样：{summary['end_to_end_sample']['passed']}/{summary['end_to_end_sample']['attempted']}（{summary['end_to_end_sample']['rate_percent']}%）",
        "",
        "| 编号 | 分组 | 自然语言 | 规划 | 状态 | 端到端 |",
        "|---|---|---|---:|---|---:|",
    ]
    for item in records:
        execution_label = "未抽样"
        if item["execution"] is not None:
            execution_label = (
                "通过"
                if item["execution"]["completed"]
                and (item["terminal_world_verification"] or {}).get("passed")
                else "失败"
            )
        table_lines.append(
            f"| {item['case_id']} | {item['group']} | {item['utterance']} | "
            f"{'通过' if item['planning']['passed'] else '失败'} | "
            f"{item['planning']['status']} | {execution_label} |"
        )
    table_lines.extend(
        [
            "",
            "## 口径",
            "",
            "规划成功要求目标关系、角色绑定、复合任务结构及交互状态全部满足预设断言。端到端成功还要求动作链结束、活动意图释放，并由最终世界关系验真。历史提升只与用户此前日志中同句失败的观察基线比较，不等同于严格同环境A/B实验。",
        ]
    )
    (output / "01-评估报告.md").write_text(
        "\n".join(table_lines) + "\n", encoding="utf-8"
    )
    checksums = []
    for path in sorted(output.rglob("*")):
        if path.is_file():
            checksums.append(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(output).as_posix()}"
            )
    (output / "SHA256SUMS.txt").write_text(
        "\n".join(checksums) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(output), "summary": summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
