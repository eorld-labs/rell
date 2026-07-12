from __future__ import annotations

from copy import deepcopy
from typing import Any


TASK_OPERATORS = {
    "navigate_near": {
        "tokens": ("走到", "走向", "靠近", "去", "旁边"),
        "role": "spatial_target",
        "required_body_actions": ("navigate_to_region",),
        "required_object_claims": ("ground_supported_large_horizontal_furniture",),
        "governance": "ordinary_navigation",
        "candidate_chain": ("ground_target_instance", "plan_route_to_standoff_pose", "navigate_and_verify_near_relation"),
    },
    "grasp_object": {
        "tokens": ("拿起", "拿上", "抓取", "拾起", "拿住"),
        "role": "grasp_target",
        "required_body_actions": ("grasp_object",),
        "required_object_claims": ("graspable",),
        "governance": "ordinary_manipulation",
        "candidate_chain": ("bind_confirmed_target", "plan_route_to_reach_pose", "grasp_and_verify_target_in_gripper"),
    },
    "avoid": {
        "tokens": ("绕开", "避开", "绕过去"),
        "role": "navigation_obstacle",
        "required_body_actions": ("local_obstacle_avoidance",),
        "required_object_claims": ("occupies_navigation_space_candidate",),
        "governance": "ordinary_navigation",
        "candidate_chain": ("bind_obstacle_geometry", "plan_clearance_route", "verify_body_cleared_obstacle"),
    },
    "sit_on": {
        "tokens": ("坐到", "坐在", "坐上", "坐下"),
        "role": "body_support_candidate",
        "required_body_actions": ("sit_down_on_support",),
        "required_object_claims": ("support_human_sitting", "load_capacity_requires_physical_verification"),
        "governance": "body_load_transfer",
        "candidate_chain": ("verify_body_support_compatibility", "transfer_body_load", "verify_stable_supported_pose"),
    },
    "relocate": {
        "tokens": ("搬开", "搬走", "挪开", "移动"),
        "role": "movable_object_candidate",
        "required_body_actions": ("apply_controlled_force",),
        "required_object_claims": ("movable_requires_physical_verification", "force_limit_requires_physical_verification"),
        "governance": "object_force_application",
        "candidate_chain": ("verify_object_mobility", "verify_force_and_grasp_limits", "relocate_and_verify_clearance"),
    },
    "probe_softness": {
        "tokens": ("摸一下", "摸摸", "软不软", "按一下", "触摸"),
        "role": "tactile_probe_target",
        "required_body_actions": ("controlled_contact_probe",),
        "required_sensors": ("tactile_or_force_feedback",),
        "required_object_claims": ("soft_or_buffered_surface_material",),
        "governance": "low_risk_contact_probe_requires_confirmation",
        "candidate_chain": ("request_contact_probe_authorization", "apply_bounded_probe", "observe_deformation_or_force_response"),
    },
}


def resolve_contextual_affordance_request(
    utterance: str,
    *,
    entities: list[dict[str, Any]],
    object_concepts: list[dict[str, Any]],
    executor_profile: dict[str, Any],
    runtime_state: dict[str, Any],
    governance_overlay: dict[str, Any] | None,
    scoped_authorization: dict[str, Any] | None,
) -> dict[str, Any] | None:
    entity = next(
        (
            item
            for item in entities
            if item.get("label") and item["label"] in utterance
        ),
        None,
    )
    if not entity and any(token in utterance for token in ("拿起", "抓取", "拾起", "拿住")):
        for concept in object_concepts:
            if any(alias and alias in utterance for alias in concept.get("aliases", [])):
                entity = next((item for item in entities if item.get("concept_id") == concept["concept_id"]), None)
                if not entity and concept["concept_id"] == "concept_fillable_container":
                    entity = next((item for item in entities if item.get("kind") == "graspable_container"), None)
                if entity:
                    break
    if not entity:
        return None
    operator = _operator(utterance)
    if not operator:
        return None
    contract = TASK_OPERATORS[operator]
    concept = next(
        (item for item in object_concepts if item["concept_id"] == entity.get("concept_id")),
        None,
    )
    if not concept and entity.get("kind") == "graspable_container":
        concept = next((item for item in object_concepts if item["concept_id"] == "concept_fillable_container"), None)
    if not concept:
        return None
    supported_actions = set(executor_profile.get("supported_actions", []))
    sensors = set(executor_profile.get("sensor_capabilities", []))
    object_claims = set(concept.get("perceptual_invariants", []))
    object_claims.update(concept.get("functional_affordances", []))
    object_claims.update(concept.get("physical_properties", []))
    object_claims.update(concept.get("expected_relations", []))
    missing = []
    for action in contract.get("required_body_actions", ()):
        if action not in supported_actions:
            missing.append({"kind": "body_capability", "condition": action, "reason": "current_body_profile_does_not_support_action"})
    for sensor in contract.get("required_sensors", ()):
        if sensor not in sensors:
            missing.append({"kind": "sensor_capability", "condition": sensor, "reason": "current_body_profile_lacks_verification_channel"})
    for claim in contract.get("required_object_claims", ()):
        if claim not in object_claims or claim.endswith("requires_physical_verification"):
            missing.append({"kind": "object_claim", "condition": claim, "reason": "object_claim_not_physically_verified"})
    if operator == "relocate" and entity.get("fixed"):
        missing.append({"kind": "runtime_object_state", "condition": "current_instance_fixed", "reason": "current_instance_is_bound_as_fixed_furniture"})
    governance_gate = contract["governance"]
    if "requires_confirmation" in governance_gate and not scoped_authorization:
        missing.append({"kind": "governance", "condition": governance_gate, "reason": "scoped_authorization_not_present"})
    available = not missing
    return {
        "status": "contextual_affordance_available" if available else "contextual_affordance_blocked",
        "entity_ref": entity["entity_id"],
        "object_concept_id": concept["concept_id"],
        "operator_candidate": operator,
        "active_role": contract["role"],
        "task_context": utterance,
        "runtime_state_basis": {
            "active_region": runtime_state.get("active_region"),
            "holding": runtime_state.get("holding"),
        },
        "body_profile_basis": {
            "body_profile": executor_profile.get("body_profile"),
            "supported_actions": sorted(supported_actions),
            "sensor_capabilities": sorted(sensors),
        },
        "object_contract_basis": {
            "perceptual_invariants": deepcopy(concept.get("perceptual_invariants", [])),
            "functional_affordances": deepcopy(concept.get("functional_affordances", [])),
            "physical_properties": deepcopy(concept.get("physical_properties", [])),
            "expected_relations": deepcopy(concept.get("expected_relations", [])),
        },
        "runtime_object_state_basis": {
            "fixed": bool(entity.get("fixed")),
            "region_id": entity.get("region_id"),
            "position_available": isinstance(entity.get("position"), list),
            "collision_size_available": isinstance(entity.get("size"), list),
        },
        "governance_gate": governance_gate,
        "scoped_authorization_present": bool(scoped_authorization),
        "available": available,
        "missing_conditions": missing,
        "candidate_process_chain": list(contract["candidate_chain"]),
        "explanation": _explanation(entity["label"], operator, available, missing),
        "role_binding_scope": "current_task_only",
        "base_object_identity_mutated": False,
        "candidate_only": True,
        "direct_execution_allowed": False,
        "must_reenter_orchestration_layer": True,
        "governance_overlay_considered": deepcopy(governance_overlay),
        "technical_feature_mapping": [
            "基于对象契约、本体画像、当前状态、任务情境和治理约束联合确定任务期语义角色",
            "同一对象在不同任务下进行临时角色再绑定且不改写基础对象身份",
            "根据未满足的本体能力、对象声明、当前实例状态和治理条件生成不可执行原因",
            "角色求值结果仅形成候选过程链并重新进入编排与执行验真",
        ],
    }


def _operator(utterance: str) -> str | None:
    matches = []
    for order, (name, contract) in enumerate(TASK_OPERATORS.items()):
        matched = [token for token in contract["tokens"] if token in utterance]
        if matched:
            matches.append((max(map(len, matched)), -order, name))
    return max(matches)[2] if matches else None


def _explanation(label: str, operator: str, available: bool, missing: list[dict[str, str]]) -> str:
    if available:
        return f"当前任务中，{label}可临时绑定为{TASK_OPERATORS[operator]['role']}；仍需回到编排与执行验真后才能动作。"
    reasons = "；".join(_reason_text(item) for item in missing)
    return f"我认识{label}，但当前不能执行该操作：{reasons}。"


def _reason_text(item: dict[str, str]) -> str:
    labels = {
        "body_capability": "本体不具备" + item["condition"],
        "sensor_capability": "缺少" + item["condition"] + "验真通道",
        "object_claim": item["condition"] + "尚未物理验真",
        "governance": "尚未取得" + item["condition"] + "授权",
        "runtime_object_state": "当前实例状态为" + item["condition"],
    }
    return labels[item["kind"]]
