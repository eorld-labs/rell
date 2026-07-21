from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any


def _stable_id(prefix: str, payload: str) -> str:
    return prefix + "_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def evaluate_runtime_rules(
    language_analysis: dict[str, Any],
    runtime_objects: list[dict[str, Any]],
    executor_profile: dict[str, Any],
    *,
    world_revision: int,
) -> dict[str, Any]:
    objects = {item.get("entity_id"): item for item in runtime_objects}
    roles = language_analysis.get("role_bindings") or {}
    theme_ref = (roles.get("theme") or roles.get("target") or {}).get("entity_ref")
    theme = objects.get(theme_ref) or {}
    operators = set((language_analysis.get("canonical_frame") or {}).get("operators", []))
    modifiers = (language_analysis.get("modifier_contract") or {}).get("modifiers", [])
    force_values = {item.get("value") for item in modifiers if item.get("dimension") == "force"}
    triggered, constraints = [], []
    if (
        "grasp_object" in operators
        and float(theme.get("temperature_c") or 0.0) > 60.0
    ):
        triggered.append(
            {
                "rule_id": "builtin_high_temperature_no_unprotected_grasp",
                "rule_type": "prohibition",
                "priority": 100,
                "status": "triggered",
                "consequence": "block_execution",
                "reason": "theme_temperature_exceeds_unprotected_grasp_limit",
                "evidence": {"theme_ref": theme_ref, "temperature_c": theme.get("temperature_c")},
                "override_allowed": False,
            }
        )
    if theme.get("fragility") == "high" and "strong" in force_values:
        triggered.append(
            {
                "rule_id": "builtin_fragile_object_rejects_strong_force",
                "rule_type": "prohibition",
                "priority": 100,
                "status": "triggered",
                "consequence": "block_execution",
                "reason": "strong_force_conflicts_with_fragile_theme",
                "evidence": {"theme_ref": theme_ref, "fragility": "high"},
                "override_allowed": False,
            }
        )
    modifier_constraints = (language_analysis.get("modifier_contract") or {}).get(
        "execution_constraints", {}
    )
    if modifier_constraints.get("minimum_disturbance_requested"):
        constraints.append(
            {
                "constraint": "minimum_disturbance_execution",
                "effect": "tighten_speed_and_contact_envelope",
            }
        )
    if modifier_constraints.get("requested_fast_cannot_exceed_executor_or_policy_limit"):
        constraints.append(
            {
                "constraint": "executor_speed_limit_remains_authoritative",
                "maximum_mps": executor_profile.get("max_linear_speed_mps"),
            }
        )
    if modifier_constraints.get("requested_strong_cannot_raise_contact_force_limit"):
        constraints.append(
            {
                "constraint": "executor_contact_force_limit_remains_authoritative",
                "maximum_n": executor_profile.get("max_contact_force_n"),
            }
        )
    blocked = any(item.get("consequence") == "block_execution" for item in triggered)
    seed = f"{world_revision}|{theme_ref}|{sorted(operators)}|{len(triggered)}"
    return {
        "schema_version": "1.0.0",
        "evaluation_kind": "RuleEvaluation",
        "evaluation_id": _stable_id("rule_evaluation", seed),
        "world_revision": world_revision,
        "status": "blocked" if blocked else "allowed_with_constraints" if constraints else "allowed",
        "triggered_rules": triggered,
        "effective_constraints": constraints,
        "control_gateway": "P018",
        "verification_gateway": "P016",
        "direct_execution_allowed": False,
        "runtime_fact_committed": False,
        "rule_evaluation_is_not_fact_source": True,
    }


def explanation_from_structured_state(
    language_analysis: dict[str, Any], rule_evaluation: dict[str, Any]
) -> dict[str, Any]:
    projection = language_analysis.get("rcir_dialogue_projection") or {}
    understanding = projection.get("human_response") or "我已形成当前任务的结构化理解。"
    if rule_evaluation.get("status") == "blocked":
        reasons = [item.get("reason") for item in rule_evaluation.get("triggered_rules", [])]
        text = "当前任务已理解，但不能执行：" + "；".join(str(item) for item in reasons if item)
        mode = "blocked"
    elif rule_evaluation.get("effective_constraints"):
        text = understanding + " 我会在当前本体和安全策略上限内收紧执行参数。"
        mode = "constrained"
    else:
        text = understanding
        mode = "understood"
    communication_entry_refs = [
        projection.get("speech_act_ref"),
        projection.get("query_contract_ref"),
        projection.get("response_act_ref"),
    ]
    communication_entry_refs = [
        ref for ref in communication_entry_refs if ref
    ]
    return {
        "schema_version": "1.0.0",
        "explanation_kind": "StructuredExplanation",
        "mode": mode,
        "text": text,
        "source_refs": [
            (language_analysis.get("rcir") or {}).get("bundle_id"),
            rule_evaluation.get("evaluation_id"),
            *communication_entry_refs,
        ],
        "communication_entry_refs": communication_entry_refs,
        "generated_from_shared_dictionary_entries": True,
        "generated_from_rcir_only": True,
        "surface_text_reparsed": False,
        "runtime_fact_committed": False,
    }
