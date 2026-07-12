from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any


def build_teaching_authority(session_id: str, goal_utterance: str, world_revision: int) -> dict[str, Any]:
    authority_id = "teach_auth_" + hashlib.sha1(
        f"{session_id}|{goal_utterance}|{world_revision}".encode("utf-8")
    ).hexdigest()[:12]
    return {
        "authority_id": authority_id,
        "status": "active",
        "controller": "human_teacher",
        "scope": "current_embodied_teaching_session_only",
        "world_revision_at_grant": world_revision,
        "safety_bypass_allowed": False,
        "must_use_executor_adapter": True,
        "revocation_conditions": ["teaching_finished", "human_exit", "policy_changed", "target_binding_invalidated"],
    }


def compile_demonstration_experience(
    *,
    teaching_id: str,
    goal_utterance: str,
    target_concept_id: str,
    target_entity_ref: str,
    demonstrated_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    successful = [item for item in demonstrated_actions if item.get("verified")]
    has_translation = any(item.get("action_class") == "body_relative_translation" for item in successful)
    has_rotation = any(item.get("action_class") == "body_relative_rotation" for item in successful)
    has_grasp = any(item.get("action_class") == "grasp_target" for item in successful)
    process = []
    if has_translation:
        process.append("navigate_until_target_within_reach")
    if has_rotation:
        process.append("orient_executor_within_body_constraints")
    if has_grasp:
        process.extend(["grasp_bound_target", "verify_target_in_gripper"])
    experience_id = "teleop_exp_" + hashlib.sha1(
        f"{teaching_id}|{goal_utterance}|{target_concept_id}|{'|'.join(process)}".encode("utf-8")
    ).hexdigest()[:12]
    return {
        "experience_id": experience_id,
        "source": "human_first_person_teleoperation",
        "source_teaching_id": teaching_id,
        "source_goal_utterance": goal_utterance,
        "status": "candidate_pending_autonomous_replay",
        "target_binding": {
            "concept_id": target_concept_id,
            "demonstration_entity_ref": target_entity_ref,
            "rebind_by_concept_and_current_observation": True,
        },
        "goal_fact": "target_object_in_gripper",
        "process_chain": process,
        "effect_contract": {
            "requires": ["target_object_spatially_grounded", "target_object_within_reach", "gripper_available"],
            "produces": ["target_object_in_gripper"],
            "destroys": ["gripper_empty", "target_object_on_support"],
            "verification": ["gripper_closed_around_target", "target_follows_end_effector"],
        },
        "invariant_contract": {
            "storage_policy": "store_invariants_not_concrete_teleoperation_parameters",
            "topology_invariants": [
                "executor_navigates_until_bound_target_is_within_reach",
                "target_object_transitions_from_support_to_executor_gripper",
            ],
            "direction_and_physical_constraints": [
                "motion_realization_must_follow_current_executor_profile",
                "every_motion_increment_must_pass_current_collision_and_policy_checks",
                "grasp_must_remain_inside_current_reachable_workspace",
            ],
            "fact_termination_conditions": ["target_object_in_gripper_verified_by_independent_channels"],
            "binding_slots": [
                {"slot_id": "TARGET_OBJECT", "required_concept": target_concept_id},
                {"slot_id": "EXECUTOR", "required_capability": "grasp_object"},
            ],
            "forbidden_storage": [
                "absolute_world_coordinates",
                "robot_joint_angles",
                "fixed_action_durations",
                "teacher_key_sequence",
                "single_body_trajectory",
            ],
        },
        "demonstration_summary": {
            "verified_action_count": len(successful),
            "raw_action_count": len(demonstrated_actions),
            "raw_teleoperation_trace_persisted": False,
        },
        "promotion_policy": {
            "requires_autonomous_replay": True,
            "requires_physical_fact_verification": True,
            "requires_human_acceptance": True,
            "direct_concept_promotion_allowed": False,
        },
        "validation_history": [],
    }


def append_validation_result(experience: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(experience)
    updated.setdefault("validation_history", []).append(deepcopy(result))
    return updated
