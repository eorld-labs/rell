from __future__ import annotations

from typing import Any, Callable

from .concept_units import build_supported_runtime_questions


def build_released_runtime_query_result(task_id: str, question: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "question": question,
        "answer": "unknown",
        "status": "snapshot_released",
        "reason": "任务期运行时世界状态快照已释放，不再作为当前世界状态查询依据",
        "source": "runtime_world_state_snapshot_only",
    }


def build_unsupported_runtime_query_result(task_id: str, question: str, query: dict[str, Any]) -> dict[str, Any]:
    return {
        "error": "unsupported_runtime_query",
        "task_id": task_id,
        "question": question,
        "supported_queries": build_supported_runtime_questions(),
        "source": "runtime_world_state_snapshot_only",
        "state_concept_resolution": query.get("concept_resolution", {}),
    }


def build_runtime_state_query_result(
    task_id: str,
    question: str,
    state: dict[str, Any],
    query: dict[str, Any],
    *,
    build_runtime_explanation_view_fn: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    established_facts = set(state.get("established_facts", []))
    query_type = query["query_type"]

    if query_type == "liquid_state":
        target_object_ref = query.get("object_ref") or "object_cup_white_mug"
        object_state_facts = set(state.get("object_locations", {}).get(target_object_ref, {}).get("state_facts", []))
        positive_fact = query["positive_fact"]
        negative_fact = query.get("negative_fact")
        positive = positive_fact in object_state_facts or positive_fact in established_facts
        negative = bool(negative_fact) and (negative_fact in object_state_facts or negative_fact in established_facts)
        if positive and negative:
            answer = "conflict"
            reason = f"当前任务期运行时世界状态快照中同时存在 {positive_fact} 与 {negative_fact}"
        elif positive:
            answer = "true"
            reason = f"当前任务期运行时世界状态快照中存在 {positive_fact}"
        elif negative:
            answer = "false"
            reason = f"当前任务期运行时世界状态快照中存在 {negative_fact} 且不存在 {positive_fact}"
        else:
            answer = "unknown"
            reason = f"当前任务期运行时世界状态快照中既无 {positive_fact}" + (f"，也无 {negative_fact}" if negative_fact else "")
        evidence = {
            "object_ref": target_object_ref,
            "object_state_facts": sorted(object_state_facts),
            "established_facts": sorted(established_facts),
            "runtime_world_state_snapshot_id": state.get("runtime_world_state_snapshot_id"),
        }
        source = "runtime_world_state_snapshot_only"
    elif query_type == "holding_state":
        holding = state.get("executor", {}).get("holding", [])
        answer = "none" if not holding else ",".join(holding)
        reason = "当前任务期运行时世界状态快照中的执行体 holding 列表"
        evidence = {
            "holding": holding,
            "runtime_world_state_snapshot_id": state.get("runtime_world_state_snapshot_id"),
        }
        source = "runtime_world_state_snapshot_only"
    elif query_type == "executor_location":
        location_ref = state.get("executor", {}).get("location_ref")
        answer = location_ref or "unknown"
        reason = "当前任务期运行时世界状态快照中的执行体位置"
        evidence = {
            "executor_location_ref": location_ref,
            "runtime_world_state_snapshot_id": state.get("runtime_world_state_snapshot_id"),
        }
        source = "runtime_world_state_snapshot_only"
    elif query_type == "preference_summary":
        active_preferences = state.get("active_preferences", [])
        answer = "none" if not active_preferences else ",".join(item.get("preference_id", "") for item in active_preferences if item.get("preference_id"))
        reason = "当前任务期运行时世界状态快照中的人类偏好约束"
        evidence = {
            "active_preferences": active_preferences,
            "preference_context": state.get("preference_context", {}),
            "runtime_world_state_snapshot_id": state.get("runtime_world_state_snapshot_id"),
        }
        source = "runtime_world_state_snapshot_only"
    elif query_type == "current_action":
        explanation = build_runtime_explanation_view_fn(task_id)
        current_action = ((explanation.get("status_answers") or {}).get("current_action") or {}).get("answer", "unknown") if "error" not in explanation else "unknown"
        action_reason = ((explanation.get("status_answers") or {}).get("current_action") or {}).get("reason", "当前没有足够上下文判断当前动作") if "error" not in explanation else "当前没有足够上下文判断当前动作"
        answer = current_action
        reason = action_reason
        evidence = {
            "current_stage": state.get("current_stage"),
            "completed_stages": state.get("completed_stages", []),
            "runtime_world_state_snapshot_id": state.get("runtime_world_state_snapshot_id"),
        }
        source = "runtime_world_state_snapshot_and_current_runtime_context_only"
    elif query_type == "next_step":
        explanation = build_runtime_explanation_view_fn(task_id)
        next_step_answer = ((explanation.get("status_answers") or {}).get("next_step") or {}).get("answer", "unknown") if "error" not in explanation else "unknown"
        next_step_reason = ((explanation.get("status_answers") or {}).get("next_step") or {}).get("reason", "当前没有足够上下文判断下一步") if "error" not in explanation else "当前没有足够上下文判断下一步"
        if next_step_answer == "unknown" and "目标已达成" in next_step_reason:
            next_step_answer = "none"
        answer = next_step_answer
        reason = next_step_reason
        evidence = {
            "current_stage": state.get("current_stage"),
            "completed_stages": state.get("completed_stages", []),
            "runtime_world_state_snapshot_id": state.get("runtime_world_state_snapshot_id"),
        }
        source = "runtime_world_state_snapshot_and_current_runtime_context_only"
    else:
        answer = "summary"
        reason = "当前任务期运行时世界状态快照摘要"
        evidence = {
            "executor": state.get("executor", {}),
            "established_facts": sorted(established_facts),
            "current_stage": state.get("current_stage"),
            "completed_stages": state.get("completed_stages", []),
            "active_preferences": state.get("active_preferences", []),
            "runtime_world_state_snapshot_id": state.get("runtime_world_state_snapshot_id"),
        }
        source = "runtime_world_state_snapshot_only"

    return {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "question": question,
        "query_type": query_type,
        "answer": answer,
        "status": "resolved_from_runtime_world_state",
        "reason": reason,
        "source": source,
        "evidence": evidence,
        "state_concept_resolution": query.get("concept_resolution", {}),
    }
