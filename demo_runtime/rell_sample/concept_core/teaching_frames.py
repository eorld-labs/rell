from __future__ import annotations

from typing import Any, Callable


STRICT_FOLLOWING_MARKERS = ["按我说", "听我的", "不要自己改", "严格按步骤", "一步一步"]
ALLOW_REORDER_MARKERS = ["你可以自己换个顺序但结果要对", "结果对就行", "可以变通", "你自己决定顺序", "不影响结果就行"]
PREFERENCE_HINTS = [
    ("force_light", ["轻一点", "轻拿", "慢一点"], "advisory"),
    ("need_confirmation", ["等我确认", "先请求我确认", "需要确认", "先别"], "blocking"),
    ("forbid_auto_action", ["不要自动", "别自动"], "blocking"),
]


def _find_sequence_markers(text: str) -> list[str]:
    markers = []
    for marker in ["先", "再", "然后", "接着", "之后"]:
        if marker in text and marker not in markers:
            markers.append(marker)
    return markers


def _extract_preference_constraints(text: str) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = []
    for signal, markers, enforcement in PREFERENCE_HINTS:
        for marker in markers:
            if marker in text:
                constraints.append(
                    {
                        "constraint_type": "human_preference",
                        "signal": signal,
                        "enforcement_policy": enforcement,
                        "source_text": marker,
                    }
                )
                break
    return constraints


def _infer_flexibility_policy(text: str, parsed_steps: list[str]) -> dict[str, Any]:
    if any(marker in text for marker in ALLOW_REORDER_MARKERS):
        return {
            "mode": "allow_local_reorder",
            "rationale": "用户明确允许局部变通，但要求结果保持正确",
            "human_override_required": False,
        }
    if any(marker in text for marker in STRICT_FOLLOWING_MARKERS):
        return {
            "mode": "strict_following",
            "rationale": "用户明确要求严格按教学过程执行",
            "human_override_required": True,
        }
    if parsed_steps:
        return {
            "mode": "ordered_preference_default",
            "rationale": "当前教学中存在明确步骤顺序，默认优先遵循过程顺序",
            "human_override_required": False,
        }
    return {
        "mode": "goal_only",
        "rationale": "当前教学更偏向目标说明，尚未形成完整步骤约束",
        "human_override_required": False,
    }


def _extract_goal_markers(text: str) -> list[str]:
    markers = []
    for marker in ["结果", "完成后", "接完以后", "最后", "目标是"]:
        if marker in text and marker not in markers:
            markers.append(marker)
    return markers


def build_teaching_frame(
    text: str,
    *,
    parse_teaching_steps_fn: Callable[[Any], list[str]],
    infer_goal_fact_fn: Callable[[str], str | None],
    normalize_text_fn: Callable[[str], str],
) -> dict[str, Any]:
    raw_text = (text or "").strip()
    parsed_steps = parse_teaching_steps_fn(raw_text)
    goal_fact = infer_goal_fact_fn(raw_text)
    sequence_markers = _find_sequence_markers(raw_text)
    preference_constraints = _extract_preference_constraints(raw_text)
    flexibility_policy = _infer_flexibility_policy(raw_text, parsed_steps)
    goal_markers = _extract_goal_markers(raw_text)

    return {
        "schema_version": "1.0.0",
        "teaching_frame_version": "v1",
        "source_text": raw_text,
        "normalized_text": normalize_text_fn(raw_text),
        "goal_constraints": {
            "goal_fact": goal_fact,
            "goal_expression_detected": bool(goal_fact or goal_markers),
            "goal_expression_markers": goal_markers,
        },
        "process_constraints": {
            "ordered_steps": parsed_steps,
            "sequence_markers": sequence_markers,
            "process_guidance_strength": "strong" if parsed_steps and sequence_markers else ("medium" if parsed_steps else "weak"),
            "supports_stepwise_execution": bool(parsed_steps),
        },
        "preference_constraints": preference_constraints,
        "flexibility_policy": flexibility_policy,
        "parsed_steps": parsed_steps,
        "teaching_mode": "stepwise_when_possible" if parsed_steps else "goal_or_preference_guidance_only",
    }
