from __future__ import annotations

import math
from copy import deepcopy
from typing import Any


FACTORY_STATE_FACT_CONCEPTS: list[dict[str, Any]] = [
    {"fact_family": "occupancy", "positive": "container_contains_material", "negative": "container_empty", "subject_type": "container", "verification": ["content_sensor_or_visual_level"], "unknown_policy": "absence_of_observation_is_unknown"},
    {"fact_family": "open_state", "positive": "object_open", "negative": "object_closed", "subject_type": "openable_object", "verification": ["joint_or_visual_open_state"], "unknown_policy": "absence_of_observation_is_unknown"},
    {"fact_family": "cleanliness", "positive": "target_clean", "negative": "contaminant_on_target", "subject_type": "cleanable_object", "verification": ["surface_observation_against_threshold"], "unknown_policy": "absence_of_observation_is_unknown"},
    {"fact_family": "holding", "positive": "object_in_gripper", "negative": "gripper_empty", "subject_type": "executor_and_object", "verification": ["gripper_state", "object_follows_end_effector"], "unknown_policy": "derive_from_current_executor_state"},
    {"fact_family": "reachability", "positive": "object_within_reach", "negative": "object_out_of_reach", "subject_type": "executor_and_object", "verification": ["body_workspace_contains_interaction_pose"], "unknown_policy": "recompute_for_current_body_and_world_revision"},
    {"fact_family": "path_feasibility", "positive": "route_feasible", "negative": "route_blocked", "subject_type": "executor_and_route", "verification": ["swept_body_envelope_clear", "policy_clearance_satisfied"], "unknown_policy": "recompute_for_current_body_and_world_revision"},
    {"fact_family": "location", "positive": "executor_at_destination", "negative": "executor_not_at_destination", "subject_type": "executor_and_spatial_target", "verification": ["executor_pose_inside_target_region"], "unknown_policy": "derive_from_current_spatial_binding"},
    {"fact_family": "support", "positive": "object_supported_at_destination", "negative": "object_not_stably_supported", "subject_type": "object_and_support", "verification": ["contact_stable", "projection_inside_support_boundary"], "unknown_policy": "absence_of_observation_is_unknown"},
    {"fact_family": "alignment", "positive": "functional_alignment_satisfied", "negative": "functional_alignment_not_satisfied", "subject_type": "two_functional_interfaces", "verification": ["relative_pose_inside_functional_tolerance"], "unknown_policy": "absence_of_observation_is_unknown"},
    {"fact_family": "activity", "positive": "activity_active", "negative": "activity_stopped", "subject_type": "runtime_process", "verification": ["active_job_and_nonzero_command", "safe_hold_state"], "unknown_policy": "derive_from_current_runtime_job"},
]


FACT_PREREQUISITE_STRATEGIES: dict[str, dict[str, Any]] = {
    "container_grounded": {"kind": "perception_or_clarification", "producer": "observe_or_clarify_container", "response": "先观察并唯一绑定承担盛装角色的对象"},
    "liquid_source_grounded": {"kind": "perception_or_clarification", "producer": "observe_or_clarify_liquid_source", "response": "先观察并唯一绑定符合材料与状态约束的液体来源"},
    "container_at_source": {"kind": "state_derived_subgoal", "producer": "position_container_at_bound_source", "response": "先根据当前本体和世界状态把容器送到已绑定来源的可操作位置"},
    "object_movable": {"kind": "object_compatibility", "producer": None, "response": "先以对象功能、固定关系和受力边界证据确认对象可移动"},
    "current_occupancy_relation_grounded": {"kind": "perception", "producer": "observe_current_occupancy_relation", "response": "先观察并验真对象当前占据的支撑位置与释放范围"},
    "object_grounded": {"kind": "perception", "producer": "observe_entity", "response": "先观察并唯一绑定目标对象"},
    "target_grounded": {"kind": "perception", "producer": "observe_entity", "response": "先观察并唯一绑定清洁或操作目标"},
    "device_grounded": {"kind": "perception", "producer": "observe_entity", "response": "先观察并唯一绑定目标设备"},
    "control_grounded": {"kind": "perception_or_teaching", "producer": "locate_device_control", "response": "先找到设备按钮、旋钮或其他控制部位"},
    "destination_grounded": {"kind": "clarification_or_perception", "producer": "observe_or_clarify_destination", "response": "先确认目标位置或对象"},
    "direction_reference_grounded": {"kind": "clarification", "producer": "resolve_reference_frame", "response": "先确认方向是相对本体还是世界参照"},
    "object_within_reach": {"kind": "state_derived_subgoal", "producer": "navigate_until_target_within_reach", "response": "先移动到目标进入当前本体可达范围"},
    "gripper_available": {"kind": "state_derived_subgoal", "producer": "release_or_place_held_object", "response": "先安全处理当前持物并释放夹爪"},
    "object_in_gripper": {"kind": "state_derived_subgoal", "producer": "grasp_object", "response": "先拿起要操作的对象"},
    "source_contains_material": {"kind": "state_query", "producer": "verify_source_material_state", "response": "先确认来源中确实存在待转移物质"},
    "destination_can_receive_material": {"kind": "object_compatibility", "producer": None, "response": "先确认目标具备接收该物质的功能属性"},
    "transfer_path_feasible": {"kind": "planning", "producer": "plan_material_transfer_alignment", "response": "先建立来源、目标和转移路径的功能对齐"},
    "release_space_safe": {"kind": "perception_and_safety", "producer": "find_safe_release_space", "response": "先确认释放位置不会导致跌落、碰撞或伤害"},
    "route_feasible": {"kind": "planning", "producer": "plan_or_detour_route", "response": "先规划满足本体净空和安全策略的通路"},
    "placement_pose_feasible": {"kind": "planning", "producer": "compute_current_body_placement_candidate", "response": "先生成符合当前本体与目标承载面的放置候选"},
    "recipient_grounded": {"kind": "perception_or_clarification", "producer": "observe_or_clarify_recipient", "response": "先观察并唯一绑定本次对象接收者"},
    "recipient_ready": {"kind": "state_query", "producer": "verify_recipient_readiness", "response": "先确认接收者处于可安全接物状态"},
    "handover_pose_feasible": {"kind": "planning", "producer": "compute_safe_handover_pose", "response": "先生成满足本体、对象和接收者安全边界的交付姿态"},
    "target_region_grounded": {"kind": "semantic_space", "producer": "resolve_semantic_region", "response": "先把目标区域绑定到当前空间语义快照"},
    "contact_pose_feasible": {"kind": "planning", "producer": "compute_safe_contact_pose", "response": "先生成满足本体、对象和碰撞边界的接触姿态"},
    "interaction_part_grounded": {"kind": "perception_or_teaching", "producer": "locate_interaction_part", "response": "先找到把手、按钮或其他交互部位"},
    "mechanism_compatible": {"kind": "object_compatibility", "producer": None, "response": "确认对象机构可由当前本体操作；否则需要换本体或人工协助"},
    "contaminant_observed": {"kind": "perception", "producer": "observe_surface_contaminant", "response": "先观察污物种类、范围和程度；没有证据时不能假定目标脏或干净"},
    "cleaning_method_compatible": {"kind": "object_compatibility_or_teaching", "producer": None, "response": "先确认清洁方式不会损坏目标材质；未知时需要补充教学或人工确认"},
    "operation_authorized": {"kind": "governance", "producer": None, "response": "先取得当前设备与场景所需授权"},
    "force_limit_known": {"kind": "body_and_safety", "producer": None, "response": "先取得对象允许受力和本体施力上限"},
    "activity_active": {"kind": "runtime_state", "producer": None, "response": "当前必须存在正在运行的动作或任务，才能执行停止"},
    "safe_to_hold": {"kind": "safety", "producer": "enter_safe_hold_state", "response": "先进入制动或稳定保持状态"},
    "sensor_available": {"kind": "body_capability", "producer": None, "response": "当前本体需要具备相应传感通道"},
}


def _entity_distance(session: dict[str, Any], entity_ref: str) -> float | None:
    entity = next((item for item in session.get("runtime_objects", []) if item.get("entity_id") == entity_ref), None)
    position = session.get("state", {}).get("executor_position")
    if not entity or not position:
        return None
    return math.dist(position, entity["position"])


def derive_runtime_fact_snapshot(
    session: dict[str, Any],
    *,
    grounded_roles: dict[str, str] | None = None,
) -> dict[str, Any]:
    grounded_roles = grounded_roles or {}
    established: set[str] = set()
    negated: set[str] = set()
    evidence: dict[str, Any] = {}
    holding = session.get("state", {}).get("holding")
    if session.get("executor_profile", {}).get("sensor_frames"):
        established.add("sensor_available")
        evidence["sensor_available"] = {"source": "current_executor_profile.sensor_frames"}
    if holding:
        established.update({"object_in_gripper", "activity_stopped"})
        negated.add("gripper_empty")
        evidence["object_in_gripper"] = {"entity_ref": holding, "source": "current_executor_holding_state"}
    else:
        established.update({"gripper_empty", "gripper_available", "activity_stopped"})
        negated.add("object_in_gripper")
        evidence["gripper_empty"] = {"source": "current_executor_holding_state"}
    target_ref = grounded_roles.get("object") or grounded_roles.get("target") or grounded_roles.get("device")
    if target_ref:
        established.update({"object_grounded", "target_grounded", "device_grounded"})
        distance = _entity_distance(session, target_ref)
        reach = float(session.get("executor_profile", {}).get("arm_reach_m", 0.0))
        if distance is not None:
            if distance <= reach:
                established.add("object_within_reach")
                negated.add("object_out_of_reach")
            else:
                established.add("object_out_of_reach")
                negated.add("object_within_reach")
            evidence["object_within_reach"] = {"entity_ref": target_ref, "distance_m": distance, "arm_reach_m": reach, "source": "current_body_workspace_projection"}
    destination_ref = grounded_roles.get("destination")
    if destination_ref:
        established.add("destination_grounded")
    active_obstacles = session.get("active_obstacles", [])
    if active_obstacles:
        established.add("route_requires_current_planning")
    else:
        established.add("route_feasible")
        negated.add("route_blocked")
        evidence["route_feasible"] = {"source": "no_active_dynamic_obstacle_candidate", "scope": "candidate_until_motion_planner_rechecks"}
    established.add("safe_to_hold")
    return {
        "schema_version": "1.0.0",
        "world_revision": session.get("world_revision"),
        "established_facts": sorted(established),
        "negated_facts": sorted(negated),
        "unknown_policy": "facts_not_in_established_or_negated_sets_remain_unknown",
        "evidence": evidence,
        "candidate_only": True,
        "runtime_fact_commit_requires_verification": True,
    }


def explain_prerequisite_gaps(
    required_facts: list[str],
    fact_snapshot: dict[str, Any],
) -> dict[str, Any]:
    established = set(fact_snapshot.get("established_facts", []))
    negated = set(fact_snapshot.get("negated_facts", []))
    satisfied = [fact for fact in required_facts if fact in established]
    missing = [fact for fact in required_facts if fact not in established]
    gaps = []
    for fact in missing:
        strategy = deepcopy(FACT_PREREQUISITE_STRATEGIES.get(fact) or {
            "kind": "unknown_fact_contract",
            "producer": None,
            "response": "当前出厂事实库还不知道如何建立这一前提，需要澄清或补充教学",
        })
        gaps.append({
            "fact": fact,
            "truth_status": "verified_false" if fact in negated else "unknown_or_not_established",
            **strategy,
        })
    automatic = [item for item in gaps if item.get("producer") and item["kind"] not in {"clarification", "governance"}]
    blocked = [item for item in gaps if not item.get("producer")]
    return {
        "required_facts": deepcopy(required_facts),
        "satisfied_facts": satisfied,
        "missing_facts": missing,
        "gaps": gaps,
        "recoverable_subgoals": automatic,
        "human_or_external_dependencies": blocked,
        "all_prerequisites_satisfied": not missing,
        "candidate_only": True,
        "direct_execution_allowed": False,
    }


def build_factory_state_catalog() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "catalog_type": "factory_state_facts_and_prerequisite_strategies",
        "state_fact_concepts": deepcopy(FACTORY_STATE_FACT_CONCEPTS),
        "prerequisite_strategies": deepcopy(FACT_PREREQUISITE_STRATEGIES),
        "shared_boundary": {
            "closed_world_assumption_forbidden": True,
            "absence_of_observation_is_not_negative_fact": True,
            "world_revision_binding_required": True,
            "candidate_only": True,
            "direct_execution_allowed": False,
        },
    }
