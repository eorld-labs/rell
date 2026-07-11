from __future__ import annotations

import hashlib
from typing import Any, Callable


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def infer_local_concept_gap(
    semantic_request: dict[str, Any],
    concept_resolution: dict[str, Any] | None = None,
    intent_preview: dict[str, Any] | None = None,
) -> list[str]:
    gaps: list[str] = []
    clarification_reason = semantic_request.get("clarification_reason")
    if clarification_reason:
        gaps.append(str(clarification_reason))
    if semantic_request.get("request_type") == "unknown":
        gaps.append("empty_or_unknown_request")
    if semantic_request.get("request_type") == "task_execution":
        resolved_concepts = (concept_resolution or {}).get("resolved_concepts", [])
        action_concepts = (concept_resolution or {}).get("action_concepts", [])
        if not resolved_concepts and not action_concepts:
            gaps.append("no_local_concept_match")
    if (
        intent_preview
        and intent_preview.get("decision") == "unsupported"
        and intent_preview.get("task_type") not in {None, "", "unknown"}
        and not clarification_reason
    ):
        gaps.append(f"intent_{intent_preview.get('task_type', 'unknown')}_unsupported")
    return _unique(gaps)


def build_cloud_recall_packet(
    utterance: str,
    *,
    semantic_request: dict[str, Any],
    concept_resolution: dict[str, Any] | None = None,
    intent_preview: dict[str, Any] | None = None,
    task_id: str | None = None,
    runtime_context_view: dict[str, Any] | None = None,
    normalize_text_fn: Callable[[str], str],
) -> dict[str, Any]:
    local_concept_gap = infer_local_concept_gap(semantic_request, concept_resolution, intent_preview)
    normalized = normalize_text_fn(utterance)
    packet_id = "cloud_recall_" + hashlib.sha1(
        "|".join([task_id or "none", normalized, "|".join(local_concept_gap)]).encode("utf-8")
    ).hexdigest()[:12]
    runtime_summary = {}
    if runtime_context_view and "error" not in runtime_context_view:
        runtime_summary = {
            "goal_fact": runtime_context_view.get("task_context", {}).get("goal_fact"),
            "current_facts": runtime_context_view.get("established_facts", []),
            "current_stage": runtime_context_view.get("task_context", {}).get("current_stage"),
            "runtime_world_state_snapshot_id": runtime_context_view.get("task_context", {}).get("runtime_world_state_snapshot_id"),
        }
    elif intent_preview:
        runtime_summary = {
            "goal_fact": intent_preview.get("goal_fact"),
            "current_facts": [],
            "current_stage": None,
            "runtime_world_state_snapshot_id": None,
        }
    return {
        "schema_version": "1.0.0",
        "packet_id": packet_id,
        "task_id": task_id,
        "utterance": utterance,
        "local_concept_gap": local_concept_gap,
        "runtime_context_summary": runtime_summary,
        "expected_return": [
            "candidate_concepts",
            "candidate_process_chain",
            "clarification_questions",
        ],
        "return_policy": {
            "candidate_only": True,
            "direct_execution_allowed": False,
            "must_reenter_orchestration_layer": True,
        },
    }


def request_cloud_concept_support(
    gap_packet: dict[str, Any],
    *,
    normalize_text_fn: Callable[[str], str],
) -> dict[str, Any]:
    utterance = str(gap_packet.get("utterance") or "")
    normalized = normalize_text_fn(utterance)
    goal_fact = (gap_packet.get("runtime_context_summary") or {}).get("goal_fact")
    gaps = set(gap_packet.get("local_concept_gap") or [])
    candidate_concepts: list[dict[str, Any]] = []
    candidate_process_chain: list[str] = []
    clarification_questions: list[str] = []

    if "deictic_object_without_shared_reference" in gaps:
        clarification_questions.append("你说的是哪一个对象？请补充颜色、位置或名称。")
    if "direction_reference_not_grounded" in gaps:
        clarification_questions.append("你提到的左右前后是相对哪个参照物？")
    if "ambiguous_action_phrase" in gaps:
        clarification_questions.append("你希望我具体做什么动作，以及作用在什么对象上？")

    if "快递" in normalized or "delivery" in normalized:
        candidate_concepts.append(
            {
                "concept_id": "cloud_concept_multi_stage_delivery_candidate",
                "display_name": "多阶段取送任务候选概念",
                "confidence": 0.74,
                "reason": "检测到快递取送类长程任务，建议交给云脑补充多阶段语义拆解。",
            }
        )
        clarification_questions.append("请补充取件位置、目标返回位置，以及是否需要中途交互。")

    if "做饭" in normalized or "煮面" in normalized or "方便面" in normalized:
        candidate_concepts.append(
            {
                "concept_id": "cloud_concept_cooking_assistance_candidate",
                "display_name": "烹饪辅助任务候选概念",
                "confidence": 0.72,
                "reason": "检测到烹饪类复合任务，建议云脑补充更长程的语义拆解。",
            }
        )
        clarification_questions.append("请补充使用哪种热源、是否允许自动开火，以及目标成品状态。")

    if goal_fact == "cup_contains_water":
        candidate_process_chain = [
            "move_to_counter",
            "pick_up_cup",
            "move_to_water_source",
            "fill_cup_at_water_source",
        ]
    elif goal_fact == "water_poured":
        candidate_process_chain = [
            "move_to_counter",
            "pick_up_cup",
            "move_to_water_source",
            "fill_cup_at_water_source",
            "move_to_counter",
            "pour_water",
        ]

    if not candidate_concepts and not clarification_questions and not candidate_process_chain:
        clarification_questions.append("请补充任务目标、关键对象或空间位置，我再给出候选经验和概念。")

    return {
        "schema_version": "1.0.0",
        "cloud_recall_id": "cloud_support_" + hashlib.sha1(str(gap_packet.get("packet_id", "none")).encode("utf-8")).hexdigest()[:12],
        "availability": "simulated_cloud_brain_stub",
        "recall_status": "candidate_only",
        "source_packet_id": gap_packet.get("packet_id"),
        "candidate_concepts": candidate_concepts,
        "candidate_process_chain": candidate_process_chain,
        "clarification_questions": _unique(clarification_questions),
        "requires_local_validation": True,
        "direct_execution_allowed": False,
        "must_reenter_orchestration_layer": True,
    }
