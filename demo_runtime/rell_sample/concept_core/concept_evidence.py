from __future__ import annotations

import hashlib
from typing import Any


def _stable_id(prefix: str, parts: list[Any]) -> str:
    seed = "|".join(str(part or "") for part in parts)
    return prefix + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def _runtime_binding(runtime_context_view: dict[str, Any] | None) -> dict[str, Any]:
    if not runtime_context_view or "error" in runtime_context_view:
        return {
            "runtime_snapshot_attached": False,
            "runtime_world_state_snapshot_id": None,
            "binding_basis": "semantic_or_alias_match_only",
        }
    task_context = runtime_context_view.get("task_context", {})
    return {
        "runtime_snapshot_attached": True,
        "runtime_world_state_snapshot_id": task_context.get("runtime_world_state_snapshot_id"),
        "current_stage": task_context.get("current_stage"),
        "goal_fact": task_context.get("goal_fact"),
        "binding_basis": "current_task_runtime_world_state_snapshot",
    }


def build_concept_evidence_packet(
    concept: dict[str, Any],
    *,
    concept_type: str,
    activation_reason: str,
    match_basis: list[str],
    confidence: float,
    runtime_context_view: dict[str, Any] | None = None,
    fallback_policy: str = "reenter_orchestration_layer",
) -> dict[str, Any]:
    concept_id = concept.get("concept_id") or concept.get("query_type") or "unknown_concept"
    normalized_confidence = max(0.0, min(1.0, float(confidence)))
    return {
        "schema_version": "1.0.0",
        "evidence_id": _stable_id("concept_evidence_", [concept_type, concept_id, activation_reason, ",".join(match_basis)]),
        "concept_id": concept_id,
        "concept_type": concept_type,
        "activation_reason": activation_reason,
        "match_basis": match_basis,
        "match_confidence": round(normalized_confidence, 2),
        "runtime_binding": _runtime_binding(runtime_context_view),
        "fallback_policy": {
            "policy": fallback_policy,
            "candidate_only": True,
            "direct_execution_allowed": False,
            "must_reenter_orchestration_layer": True,
            "on_insufficient_evidence": "clarify_or_request_cloud_recall_candidate",
        },
        "patent_feature_mapping": [
            "端侧概念内化仅形成候选语义单元",
            "候选内容需回到任务期运行时世界状态快照和编排层校验",
            "概念证据不得直接改写执行控制链路",
        ],
    }


def build_gap_evidence_packet(
    utterance: str,
    *,
    gaps: list[str],
    runtime_context_view: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "evidence_id": _stable_id("concept_gap_", [utterance, ",".join(gaps)]),
        "utterance": utterance,
        "gap_reasons": gaps,
        "match_confidence": 0.0,
        "runtime_binding": _runtime_binding(runtime_context_view),
        "fallback_policy": {
            "policy": "cloud_recall_candidate_or_human_clarification",
            "candidate_only": True,
            "direct_execution_allowed": False,
            "must_reenter_orchestration_layer": True,
            "on_insufficient_evidence": "request_clarification_before_execution",
        },
        "patent_feature_mapping": [
            "本地概念缺口不直接执行",
            "云端补给仅作为候选返回",
            "候选结果必须重新进入编排层和状态优先仲裁",
        ],
    }
