from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SlotSpec:
    slot_id: str
    value_type: str
    role_names: tuple[str, ...]
    candidate_provider: str
    required: bool = True
    auto_bind_unique: bool = True
    priority: int = 50
    required_when: str | None = None


@dataclass(frozen=True)
class ProcessTemplate:
    template_id: str
    operators: tuple[str, ...]
    goal_fact: str
    slots: tuple[SlotSpec, ...]
    causal_preconditions: tuple[dict[str, Any], ...]


PROCESS_TEMPLATES: tuple[ProcessTemplate, ...] = (
    ProcessTemplate(
        "grasp_object",
        ("grasp_object",),
        "object_in_gripper",
        (SlotSpec("theme", "graspable_object", ("theme", "target"), "graspable_objects", priority=10),),
        (
            {"fact": "object_grounded", "producer": "observe_entity"},
            {"fact": "object_within_reach", "producer": "navigate_until_target_within_reach"},
            {"fact": "gripper_available", "producer": "release_or_place_held_object"},
        ),
    ),
    ProcessTemplate(
        "place_object",
        ("place_object",),
        "object_supported_at_destination",
        (
            SlotSpec("theme", "graspable_object", ("theme", "target"), "graspable_objects", priority=10),
            SlotSpec("destination", "support_surface", ("destination",), "support_surfaces", priority=20),
        ),
        (
            {"fact": "object_in_gripper", "producer": "grasp_object"},
            {"fact": "destination_grounded", "producer": "observe_or_clarify_destination"},
            {"fact": "placement_pose_feasible", "producer": "compute_current_body_placement_candidate"},
        ),
    ),
    ProcessTemplate(
        "handover_object",
        ("handover_object",),
        "object_received_by_recipient",
        (
            SlotSpec("theme", "graspable_object", ("theme", "target"), "graspable_objects", priority=10),
            SlotSpec("recipient", "human_recipient", ("recipient",), "human_recipients", priority=20),
        ),
        (
            {"fact": "object_in_gripper", "producer": "grasp_object"},
            {"fact": "recipient_grounded", "producer": "observe_or_clarify_recipient"},
            {"fact": "recipient_ready", "producer": "verify_recipient_readiness"},
            {"fact": "handover_pose_feasible", "producer": "compute_safe_handover_pose"},
        ),
    ),
    ProcessTemplate(
        "transport_object",
        ("transport_object",),
        "object_at_target_region",
        (
            SlotSpec("theme", "graspable_object", ("theme", "target"), "graspable_objects", priority=10),
            SlotSpec("target_region", "semantic_region", ("target_region", "destination"), "semantic_regions", priority=20),
            SlotSpec("transport_mode", "transport_mode", ("transport_mode",), "transport_modes", priority=30),
            SlotSpec("destination", "support_surface", ("destination",), "support_surfaces", required=False, priority=40, required_when="transport_mode=place_at_region"),
        ),
        (
            {"fact": "object_in_gripper", "producer": "grasp_object"},
            {"fact": "route_feasible", "producer": "plan_or_detour_route"},
        ),
    ),
)


_TEMPLATE_BY_ID = {item.template_id: item for item in PROCESS_TEMPLATES}
_TEMPLATE_BY_OPERATOR = {
    operator: item for item in PROCESS_TEMPLATES for operator in item.operators
}


def build_process_template_catalog() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "templates": [
            {
                "template_id": item.template_id,
                "operators": list(item.operators),
                "goal_fact": item.goal_fact,
                "slots": [asdict(slot) for slot in item.slots],
                "causal_preconditions": deepcopy(item.causal_preconditions),
            }
            for item in PROCESS_TEMPLATES
        ],
        "resolution_contract": {
            "templates_declare_slots_not_question_strings": True,
            "questions_are_derived_from_unresolved_slots_and_snapshot_candidates": True,
            "language_never_commits_physical_facts": True,
            "execution_requires_current_world_revalidation": True,
        },
    }


def resolve_process_request(
    utterance: str,
    language_analysis: dict[str, Any],
    *,
    runtime_objects: list[dict[str, Any]],
    runtime_state: dict[str, Any],
    semantic_regions: list[dict[str, Any]],
    executor_profile: dict[str, Any],
    world_revision: int,
    binding_overrides: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    candidates = _template_candidates(utterance, language_analysis)
    if not candidates:
        return None
    selected = candidates[0]
    template = _TEMPLATE_BY_ID[selected["template_id"]]
    bindings: dict[str, dict[str, Any]] = {}
    slot_results = []
    binding_overrides = binding_overrides or {}
    for slot in sorted(template.slots, key=lambda item: item.priority):
        values = _slot_candidates(
            slot,
            utterance,
            language_analysis,
            runtime_objects,
            runtime_state,
            semantic_regions,
            bindings,
        )
        override = binding_overrides.get(slot.slot_id)
        if override:
            values = [item for item in values if item.get("value_ref") == override]
        explicit = [item for item in values if item.get("explicit")]
        usable = explicit or values
        conditionally_required = _conditionally_required(slot, bindings)
        if not slot.required and not conditionally_required and not explicit and not override:
            slot_results.append(_slot_result(slot, "optional_unbound", []))
        elif len(usable) == 1 and slot.auto_bind_unique:
            bindings[slot.slot_id] = deepcopy(usable[0])
            slot_results.append(_slot_result(slot, "bound", usable, usable[0]))
        elif len(usable) > 1:
            slot_results.append(_slot_result(slot, "ambiguous", usable))
        elif slot.required or conditionally_required:
            slot_results.append(_slot_result(slot, "missing", []))
        else:
            slot_results.append(_slot_result(slot, "optional_unbound", []))

    preconditions = _resolve_preconditions(template, bindings, runtime_state, executor_profile, runtime_objects)
    unresolved = [item for item in slot_results if item["status"] in {"ambiguous", "missing"}]
    unsafe = next((item for item in preconditions if item["status"] == "unsafe_conflict"), None)
    template_confirmation_required = bool(selected.get("requires_human_confirmation"))
    if unsafe:
        status = "unsafe_switch"
        next_gap = unsafe
    elif unresolved:
        status = "clarification_required"
        next_gap = sorted(unresolved, key=lambda item: item["priority"])[0]
    elif template_confirmation_required:
        status = "template_confirmation_required"
        next_gap = {
            "kind": "template_mapping",
            "template_id": template.template_id,
            "novel_surface": selected.get("novel_surface"),
        }
    else:
        status = "ready" if all(item["status"] == "satisfied" for item in preconditions) else "subgoals_required"
        next_gap = None
    canonical = _canonical_utterance(template.template_id, bindings)
    return {
        "schema_version": "1.0.0",
        "status": status,
        "template_id": template.template_id,
        "goal_fact": template.goal_fact,
        "template_candidate": deepcopy(selected),
        "template_alternatives": deepcopy(candidates[1:]),
        "bindings": deepcopy(bindings),
        "slot_results": slot_results,
        "precondition_results": preconditions,
        "next_gap": deepcopy(next_gap),
        "question": _render_question(status, next_gap, template, bindings),
        "canonical_utterance": canonical,
        "world_revision": world_revision,
        "candidate_only": True,
        "runtime_fact_committed": False,
        "direct_execution_allowed": False,
    }


def _template_candidates(utterance: str, analysis: dict[str, Any]) -> list[dict[str, Any]]:
    operators = analysis.get("canonical_frame", {}).get("operators", [])
    candidates = []
    for operator in operators:
        template = _TEMPLATE_BY_OPERATOR.get(operator)
        if template:
            candidates.append({
                "template_id": template.template_id,
                "score": 1.0,
                "basis": "recognized_event_operator",
                "requires_human_confirmation": False,
                "novel_surface": None,
            })
    if candidates:
        return _deduplicate_candidates(candidates)
    normalized = re.sub(r"[\s，。！？、,.!?]+", "", utterance)
    has_object = bool(analysis.get("entity_mentions") or analysis.get("role_bindings", {}).get("theme"))
    novel_handover_surface = _novel_surface_before_relation(normalized, "给", analysis) if "给" in normalized else None
    if novel_handover_surface:
        candidates.append({
            "template_id": "handover_object",
            "score": 0.78,
            "basis": "object_plus_recipient_relation_with_unknown_predicate",
            "requires_human_confirmation": True,
            "novel_surface": novel_handover_surface,
        })
    if has_object and any(marker in normalized for marker in ("带到", "拿到", "送到", "端到", "带走", "拿来", "捎到")):
        candidates.append({
            "template_id": "transport_object",
            "score": 0.74,
            "basis": "object_plus_directional_transport_relation",
            "requires_human_confirmation": True,
            "novel_surface": next((item for item in ("带到", "拿到", "送到", "端到", "带走", "拿来", "捎到") if item in normalized), None),
        })
    return _deduplicate_candidates(candidates)


def _deduplicate_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for item in candidates:
        current = by_id.get(item["template_id"])
        if current is None or item["score"] > current["score"]:
            by_id[item["template_id"]] = item
    return sorted(by_id.values(), key=lambda item: item["score"], reverse=True)


def _slot_candidates(
    slot: SlotSpec,
    utterance: str,
    analysis: dict[str, Any],
    runtime_objects: list[dict[str, Any]],
    runtime_state: dict[str, Any],
    semantic_regions: list[dict[str, Any]],
    current_bindings: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    role = next((analysis.get("role_bindings", {}).get(name) for name in slot.role_names if analysis.get("role_bindings", {}).get(name)), {})
    if slot.candidate_provider == "graspable_objects":
        values = [item for item in runtime_objects if item.get("active") is not False and item.get("kind") in {"graspable_object", "graspable_container"}]
        concept_kinds = set(role.get("compatible_kinds", []))
        if concept_kinds:
            values = [item for item in values if item.get("kind") in concept_kinds]
        explicit_ref = role.get("entity_ref")
        return [_entity_value(item, explicit=bool(explicit_ref == item.get("entity_id") or _mentioned(item, utterance))) for item in values]
    if slot.candidate_provider == "human_recipients":
        return [_entity_value(item, explicit=_mentioned(item, utterance)) for item in runtime_objects if item.get("active") is not False and item.get("kind") == "human_recipient"]
    if slot.candidate_provider == "support_surfaces":
        values = [item for item in runtime_objects if item.get("active") is not False and item.get("kind") == "operation_surface"]
        target_region = (current_bindings.get("target_region") or {}).get("value_ref")
        if target_region:
            values = [item for item in values if item.get("region_id") == target_region]
        return [_entity_value(item, explicit=_mentioned(item, utterance)) for item in values]
    if slot.candidate_provider == "semantic_regions":
        return [
            {
                "value_ref": item.get("region_id"),
                "label": item.get("label"),
                "value_type": "semantic_region",
                "explicit": bool(item.get("label") and item["label"] in utterance),
                "evidence": "current_semantic_region_snapshot",
            }
            for item in semantic_regions
        ]
    if slot.candidate_provider == "transport_modes":
        if any(marker in utterance for marker in ("放到", "放在", "送到", "端到")):
            return [{"value_ref": "place_at_region", "label": "送到后放下", "value_type": "transport_mode", "explicit": True, "evidence": "language_result_relation"}]
        if any(marker in utterance for marker in ("拿到", "带到", "带走", "拿来")):
            return [{"value_ref": "retain_holding", "label": "带到后继续拿着", "value_type": "transport_mode", "explicit": True, "evidence": "language_process_relation"}]
        return [
            {"value_ref": "retain_holding", "label": "带到后继续拿着", "value_type": "transport_mode", "explicit": False, "evidence": "template_candidate"},
            {"value_ref": "place_at_region", "label": "送到后放下", "value_type": "transport_mode", "explicit": False, "evidence": "template_candidate"},
        ]
    return []


def _resolve_preconditions(
    template: ProcessTemplate,
    bindings: dict[str, dict[str, Any]],
    runtime_state: dict[str, Any],
    executor_profile: dict[str, Any],
    runtime_objects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    holding = runtime_state.get("holding")
    holding_by_effector = runtime_state.get("holding_by_effector", {})
    free_effector = next((name for name, ref in holding_by_effector.items() if not ref), None)
    theme_ref = (bindings.get("theme") or {}).get("value_ref")
    holding_label = next((item.get("label") for item in runtime_objects if item.get("entity_id") == holding), holding)
    results = []
    for contract in template.causal_preconditions:
        fact = contract["fact"]
        if fact == "object_in_gripper" and theme_ref and holding == theme_ref:
            status = "satisfied"
        elif fact == "gripper_available" and (free_effector or not holding):
            status = "satisfied"
        elif fact == "gripper_available" and theme_ref and holding and holding != theme_ref:
            status = "unsafe_conflict"
        elif fact in {"recipient_ready", "handover_pose_feasible", "placement_pose_feasible", "route_feasible", "object_within_reach", "object_grounded", "destination_grounded", "recipient_grounded"}:
            status = "producible_subgoal"
        elif fact == "object_in_gripper":
            status = "producible_subgoal"
        else:
            status = "unknown"
        results.append({
            "kind": "causal_precondition",
            "fact": fact,
            "status": status,
            "producer": contract.get("producer"),
            "current_holding": holding,
            "current_holding_label": holding_label,
            "executor_supports_producer": contract.get("producer") in set(executor_profile.get("supported_actions", [])) or contract.get("producer") is not None,
        })
    return results


def _slot_result(slot: SlotSpec, status: str, candidates: list[dict[str, Any]], bound: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "kind": "parameter_slot",
        "slot_id": slot.slot_id,
        "value_type": slot.value_type,
        "status": status,
        "priority": slot.priority,
        "candidate_provider": slot.candidate_provider,
        "candidates": deepcopy(candidates),
        "bound_value": deepcopy(bound),
    }


def _conditionally_required(slot: SlotSpec, bindings: dict[str, dict[str, Any]]) -> bool:
    if not slot.required_when or "=" not in slot.required_when:
        return False
    binding_id, expected = slot.required_when.split("=", 1)
    return (bindings.get(binding_id) or {}).get("value_ref") == expected


def _render_question(
    status: str,
    gap: dict[str, Any] | None,
    template: ProcessTemplate,
    bindings: dict[str, dict[str, Any]],
) -> str | None:
    if status == "template_confirmation_required":
        return f"我暂时把“{gap.get('novel_surface') or '这个说法'}”理解为{_goal_description(template.template_id, bindings)}。这个理解对吗？"
    if status == "unsafe_switch":
        return f"我当前还拿着{gap.get('current_holding_label') or '另一个对象'}，没有可用执行器继续当前目标。要先安全放下当前持物吗？"
    if status != "clarification_required" or not gap:
        return None
    slot_id = gap["slot_id"]
    labels = [item.get("label") for item in gap.get("candidates", []) if item.get("label")]
    if slot_id == "theme":
        return f"你想让我操作哪一个？当前候选是：{'、'.join(labels)}。" if labels else "你想让我操作哪个当前可见或可定位的物体？"
    if slot_id == "recipient":
        return f"你想让我交给谁？当前在场候选是：{'、'.join(labels)}。" if labels else "你想让我交给谁？当前还没有可唯一落地的接收者。"
    if slot_id == "destination":
        return f"你想让我放到哪里？当前可放置候选是：{'、'.join(labels)}。" if labels else "你想让我放到哪个可承载位置？"
    if slot_id == "target_region":
        return f"你想让我带到哪个区域？当前区域候选是：{'、'.join(labels)}。" if labels else "你想让我带到哪里？"
    if slot_id == "transport_mode":
        return f"到达后是继续拿着，还是放下？当前候选是：{'、'.join(labels)}。"
    return f"当前过程还缺少参数：{slot_id}。请补充这个值。"


def _goal_description(template_id: str, bindings: dict[str, dict[str, Any]]) -> str:
    theme = (bindings.get("theme") or {}).get("label") or "这个对象"
    if template_id == "handover_object":
        recipient = (bindings.get("recipient") or {}).get("label") or "接收者"
        return f"把{theme}带到{recipient}面前并交给对方"
    if template_id == "transport_object":
        region = (bindings.get("target_region") or {}).get("label") or "目标区域"
        return f"把{theme}带到{region}"
    if template_id == "place_object":
        destination = (bindings.get("destination") or {}).get("label") or "目标承载面"
        return f"把{theme}稳定放到{destination}"
    return f"拿起{theme}"


def _canonical_utterance(template_id: str, bindings: dict[str, dict[str, Any]]) -> str | None:
    theme = (bindings.get("theme") or {}).get("label")
    if not theme:
        return None
    if template_id == "grasp_object":
        return f"拿起{theme}"
    if template_id == "place_object":
        destination = (bindings.get("destination") or {}).get("label")
        return f"把{theme}放到{destination}" if destination else None
    if template_id == "handover_object":
        recipient = (bindings.get("recipient") or {}).get("label")
        return f"把{theme}递给{recipient}" if recipient else None
    if template_id == "transport_object":
        region = (bindings.get("target_region") or {}).get("label")
        mode = (bindings.get("transport_mode") or {}).get("value_ref")
        if region:
            return f"把{theme}{'送到' if mode == 'place_at_region' else '带到'}{region}"
    return None


def _entity_value(item: dict[str, Any], *, explicit: bool) -> dict[str, Any]:
    return {
        "value_ref": item.get("entity_id"),
        "label": item.get("label"),
        "value_type": item.get("kind"),
        "explicit": explicit,
        "evidence": "explicit_language_and_current_snapshot" if explicit else "current_world_snapshot_candidate",
    }


def _mentioned(item: dict[str, Any], utterance: str) -> bool:
    label = str(item.get("label") or "")
    return bool(label and label in utterance)


def _novel_surface_before_relation(text: str, relation: str, analysis: dict[str, Any]) -> str | None:
    residual = text
    for mention in analysis.get("entity_mentions", []):
        alias = str(mention.get("matched_alias") or "")
        if alias:
            residual = residual.replace(alias, "", 1)
    for marker in ("把", "这个", "那个", "它", "人类", "家人", "主人", "用户", "接收人", "我", "现在", "再", "请"):
        residual = residual.replace(marker, "")
    match = re.search(rf"([\u4e00-\u9fff]{{1,2}}){re.escape(relation)}", residual)
    if not match:
        return None
    return match.group(1) + relation
