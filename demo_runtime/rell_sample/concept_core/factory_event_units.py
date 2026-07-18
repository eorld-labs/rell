from __future__ import annotations

from copy import deepcopy
from typing import Any


def _event(
    concept_id: str,
    display_name: str,
    operator: str,
    aliases: list[str],
    capability: str,
    roles: dict[str, dict[str, Any]],
    requires: list[str],
    produces: list[str],
    destroys: list[str],
    verification: list[str],
    *,
    postcondition: str,
) -> dict[str, Any]:
    return {
        "concept_id": concept_id,
        "display_name": display_name,
        "step_id": None,
        "aliases": aliases,
        "capability": capability,
        "goal_fact_bridge": produces[0] if produces else None,
        "concept_kernel": {
            "operator": operator,
            "semantic_roles": roles,
            "effect_contract": {
                "requires": requires,
                "produces": produces,
                "destroys": destroys,
                "verification": verification,
            },
        },
        "factory_semantics": {
            "knowledge_origin": "reusable_objective_state_transition",
            "postcondition": postcondition,
            "stores_concrete_trajectory": False,
            "body_independent": True,
        },
        "response_policy": {
            "distinguish_understanding_from_execution_ability": True,
            "explain_missing_roles_capability_experience_verification_or_safety": True,
            "offer_clarification_or_teaching_when_recoverable": True,
        },
        "source_policy": "factory_semantics_only_then_reenter_orchestration",
    }


FACTORY_EVENT_CONCEPT_UNITS: list[dict[str, Any]] = [
    _event(
        "factory_event_observe",
        "观察对象事件概念",
        "observe_entity",
        ["看看", "看一下", "观察", "找找", "找到", "看得到", "看的到", "能看到", "能看见"],
        "active_perception",
        {"object": {"role": "target", "entity_type": "perceivable_entity"}},
        ["sensor_available"],
        ["entity_observation_candidate_available"],
        [],
        ["entity_detected_with_confidence", "observation_bound_to_current_world_revision"],
        postcondition="形成当前世界版本中的对象观测候选，而非直接形成事实",
    ),
    _event(
        "factory_event_navigate",
        "趋近目标事件概念",
        "navigate_to",
        ["走到", "走向", "去到", "前往", "靠近", "过去"],
        "navigate_to_region",
        {"destination": {"role": "target", "entity_type": "spatial_target"}},
        ["destination_grounded", "route_feasible"],
        ["executor_at_destination"],
        ["executor_at_previous_location"],
        ["executor_pose_inside_destination", "route_safety_preserved"],
        postcondition="执行体与目标形成可交互的空间邻近关系",
    ),
    _event(
        "factory_event_orient",
        "朝向改变事件概念",
        "orient_executor",
        ["转向", "转过来", "面向", "朝向", "向左转", "向右转"],
        "relative_move",
        {"direction": {"role": "target_heading", "entity_type": "body_relative_or_world_direction"}},
        ["direction_reference_grounded"],
        ["executor_heading_changed"],
        ["executor_at_previous_heading"],
        ["executor_heading_matches_target"],
        postcondition="执行体正前方从原朝向变为目标朝向，不隐含位移",
    ),
    _event(
        "factory_event_grasp",
        "获取对象事件概念",
        "grasp_object",
        ["拿起", "拿着", "拿住", "抓起", "抓住", "取下", "拿"],
        "grasp_object",
        {"object": {"role": "target", "entity_type": "graspable_object"}},
        ["object_grounded", "object_within_reach", "gripper_available"],
        ["object_in_gripper"],
        ["gripper_empty", "object_at_previous_support"],
        ["gripper_closed_around_object", "object_follows_end_effector"],
        postcondition="对象脱离原支撑并与执行体末端保持共同运动关系",
    ),
    _event(
        "factory_event_release",
        "释放对象事件概念",
        "release_object",
        ["放开", "松开", "撒手", "释放"],
        "release_object",
        {"object": {"role": "target", "entity_type": "held_object"}},
        ["object_in_gripper", "release_space_safe"],
        ["gripper_empty", "object_released"],
        ["object_in_gripper"],
        ["gripper_open", "object_no_longer_follows_end_effector"],
        postcondition="对象不再受夹持约束；不保证对象稳定放置",
    ),
    _event(
        "factory_event_place",
        "放置对象事件概念",
        "place_object",
        ["放到", "放在", "放下", "摆到", "摆在", "搁在"],
        "place_object",
        {
            "object": {"role": "theme", "entity_type": "held_object"},
            "destination": {"role": "target", "entity_type": "support_or_container"},
        },
        ["object_in_gripper", "destination_grounded", "placement_pose_feasible"],
        ["object_at_destination", "gripper_empty"],
        ["object_in_gripper"],
        ["object_supported_at_destination", "gripper_clear_of_object"],
        postcondition="对象由执行体持有转为由目标位置稳定承载",
    ),
    _event(
        "factory_event_handover",
        "对象交付事件概念",
        "handover_object",
        ["递给", "交给", "拿给", "送给", "递过去", "交过去"],
        "handover_object",
        {
            "object": {"role": "theme", "entity_type": "graspable_object"},
            "recipient": {"role": "target", "entity_type": "human_recipient"},
        },
        ["object_in_gripper", "recipient_grounded", "recipient_ready", "handover_pose_feasible"],
        ["object_received_by_recipient", "gripper_empty"],
        ["object_in_gripper"],
        ["effector_release_observed", "recipient_possession_observed"],
        postcondition="对象由执行体持有转为由指定接收者持有，并通过释放与接收状态联合验真",
    ),
    _event(
        "factory_event_transport",
        "对象跨区域运输事件概念",
        "transport_object",
        ["带到", "拿到", "送到", "端到", "带走", "拿来"],
        "navigate_to_region",
        {
            "object": {"role": "theme", "entity_type": "graspable_object"},
            "target_region": {"role": "target", "entity_type": "semantic_region"},
            "transport_mode": {"role": "mode", "entity_type": "retain_holding_or_place"},
        },
        ["object_in_gripper", "target_region_grounded", "route_feasible"],
        ["object_at_target_region"],
        ["object_at_previous_region"],
        ["executor_inside_target_region", "object_remains_bound_to_selected_transport_mode"],
        postcondition="对象随执行体到达目标区域；是否继续持有或稳定放置由任务期模式槽决定",
    ),
    _event(
        "factory_event_push_pull",
        "受力位移事件概念",
        "apply_directional_force",
        ["推", "推开", "拉", "拉开", "拖动", "挪动"],
        "apply_controlled_force",
        {
            "object": {"role": "target", "entity_type": "movable_object"},
            "direction": {"role": "force_direction", "entity_type": "direction"},
        },
        ["object_grounded", "contact_pose_feasible", "force_limit_known"],
        ["object_displaced"],
        ["object_at_previous_pose"],
        ["object_motion_observed", "force_within_limit"],
        postcondition="对象在受控力作用下发生位移且安全约束未被突破",
    ),
    _event(
        "factory_event_open_close",
        "开闭状态事件概念",
        "change_open_state",
        ["打开", "关上", "关闭", "合上"],
        "operate_openable_object",
        {"object": {"role": "target", "entity_type": "openable_object"}},
        ["object_grounded", "interaction_part_grounded", "mechanism_compatible"],
        ["object_open_state_changed"],
        ["object_previous_open_state"],
        ["open_state_sensor_or_visual_confirmation"],
        postcondition="对象在开放与闭合状态之间发生可验真的跃迁",
    ),
    _event(
        "factory_event_activate_deactivate",
        "启停设备事件概念",
        "change_device_activation",
        ["开启", "启动", "关掉", "停止设备", "按开关"],
        "operate_device_control",
        {
            "device": {"role": "target", "entity_type": "controllable_device"},
            "control": {"role": "interaction_part", "entity_type": "device_control"},
        },
        ["device_grounded", "control_grounded", "operation_authorized"],
        ["device_activation_state_changed"],
        ["device_previous_activation_state"],
        ["device_state_feedback_observed"],
        postcondition="设备运行状态发生变化，不能以按下按钮替代设备状态验真",
    ),
    _event(
        "factory_event_transfer",
        "物质转移事件概念",
        "transfer_material",
        ["倒入", "倒进", "倒出来", "装入", "装进", "取出"],
        "transfer_material",
        {
            "material": {"role": "theme", "entity_type": "transferable_material"},
            "source": {"role": "origin", "entity_type": "source"},
            "destination": {"role": "target", "entity_type": "destination"},
        },
        ["source_contains_material", "destination_can_receive_material", "transfer_path_feasible"],
        ["material_at_destination"],
        ["material_at_source"],
        ["material_flow_observed", "destination_state_changed"],
        postcondition="物质从来源转移至目标，来源与目标事实同步更新",
    ),
    _event(
        "factory_event_clean",
        "去除附着物事件概念",
        "remove_surface_contaminant",
        ["擦", "擦掉", "清洁", "清理", "打扫"],
        "clean_surface",
        {
            "target": {"role": "target", "entity_type": "cleanable_surface_or_object"},
            "contaminant": {"role": "removed_material", "entity_type": "undesired_material", "optional": True},
        },
        ["target_grounded", "contaminant_observed", "cleaning_method_compatible"],
        ["target_clean"],
        ["contaminant_on_target"],
        ["contaminant_absent_or_below_threshold", "target_not_damaged"],
        postcondition="目标表面的非期望附着物降低至验收阈值以下",
    ),
    _event(
        "factory_event_stop",
        "停止当前事件概念",
        "stop_current_activity",
        ["停下", "停止", "别做了", "不要做了", "取消"],
        "stop_current_activity",
        {"activity": {"role": "target", "entity_type": "active_process"}},
        ["activity_active"],
        ["activity_stopped", "executor_in_safe_hold_state"],
        ["activity_active"],
        ["motion_or_actuation_zero", "safe_hold_state_verified"],
        postcondition="当前活动终止并进入可验真的安全保持状态",
    ),
    _event(
        "factory_event_wait",
        "等待条件事件概念",
        "wait_until",
        ["等一下", "等等", "等待", "先别动"],
        "wait_until",
        {"condition": {"role": "termination_condition", "entity_type": "fact_or_time_boundary", "optional": True}},
        ["safe_to_hold"],
        ["wait_condition_satisfied"],
        [],
        ["condition_observed_or_human_resume_signal_received"],
        postcondition="保持安全状态直到事实条件或恢复信令成立",
    ),
]


def find_factory_event_concepts_by_text(normalized_text: str) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for unit in FACTORY_EVENT_CONCEPT_UNITS:
        aliases = sorted(unit.get("aliases", []), key=len, reverse=True)
        if any(alias in normalized_text for alias in aliases):
            matched.append(deepcopy(unit))
    return matched


def build_factory_inability_diagnosis(
    concept: dict[str, Any],
    *,
    supported_capabilities: list[str],
    available_experience_capabilities: list[str] | None = None,
    grounded_roles: dict[str, str] | None = None,
    incompatible_roles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    capability = concept["capability"]
    supported = capability in set(supported_capabilities)
    experienced = capability in set(available_experience_capabilities or [])
    role_templates = concept["concept_kernel"]["semantic_roles"]
    grounded_roles = grounded_roles or {}
    incompatible_roles = incompatible_roles or []
    missing_roles = [name for name, template in role_templates.items() if not template.get("optional") and not grounded_roles.get(name)]
    verification = concept["concept_kernel"]["effect_contract"]["verification"]
    if incompatible_roles:
        reason_code = "entity_not_compatible_with_semantic_role"
        next_action = "explain_role_incompatibility_and_request_alternative"
        explanation = "；".join(item["reason"] for item in incompatible_roles)
    elif missing_roles:
        reason_code = "required_semantic_roles_not_grounded"
        next_action = "request_clarification"
        explanation = f"我理解这是“{concept['display_name']}”，但还不知道" + "、".join(missing_roles) + "具体指什么。"
    elif not supported:
        reason_code = "executor_capability_not_available"
        next_action = "explain_body_limit_and_request_compatible_body_or_help"
        explanation = f"我理解这是“{concept['display_name']}”，但当前本体画像没有 {capability} 能力。"
    elif not experienced:
        reason_code = "execution_experience_not_available"
        next_action = "offer_embodied_teaching"
        explanation = f"我理解目标和成功条件，但还没有适用于当前本体与场景的 {capability} 经验。"
    elif not verification:
        reason_code = "verification_channel_not_available"
        next_action = "request_verification_support"
        explanation = "我能形成动作候选，但没有足够验真条件确认结果是否真的成立。"
    else:
        reason_code = "ready_for_orchestration"
        next_action = "reenter_orchestration"
        explanation = "概念、角色、本体能力和经验均已有候选，仍需回到编排层按当前状态判断。"
    return {
        "concept_id": concept["concept_id"],
        "display_name": concept["display_name"],
        "operator": concept["concept_kernel"]["operator"],
        "recognized_goal_fact": concept.get("goal_fact_bridge"),
        "effect_contract": deepcopy(concept["concept_kernel"]["effect_contract"]),
        "reason_code": reason_code,
        "explanation": explanation,
        "missing_roles": missing_roles,
        "incompatible_roles": deepcopy(incompatible_roles),
        "required_capability": capability,
        "executor_capability_available": supported,
        "applicable_experience_available": experienced,
        "next_action": next_action,
        "candidate_only": True,
        "direct_execution_allowed": False,
        "must_reenter_orchestration_layer": True,
    }
