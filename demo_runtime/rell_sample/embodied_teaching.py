from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from teaching_observation import build_portable_teaching_evidence_summary


def build_pedagogical_signals(
    *,
    signal_types: list[str] | None = None,
    target_experience_ref: str | None = None,
    interruption_occurred: bool = False,
    clarification_occurred: bool = False,
    outcome: str = "in_progress",
) -> dict[str, Any]:
    allowed = {"demonstration", "correction", "boundary_indication", "negative_example", "confirmation"}
    normalized = [item for item in (signal_types or ["demonstration"]) if item in allowed]
    return {
        "signal_types": list(dict.fromkeys(normalized)),
        "target_experience_ref": target_experience_ref,
        "interruption_occurred": bool(interruption_occurred),
        "clarification_occurred": bool(clarification_occurred),
        "outcome": outcome,
    }


def compile_infeasibility_summaries(
    demonstrated_actions: list[dict[str, Any]],
    *,
    concept_id: str,
    world_revision: int | None = None,
    executor_profile: str = "current_executor_profile",
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for action in demonstrated_actions:
        if action.get("verified") or not action.get("failure_reason"):
            continue
        summary = {
            "concept_id": concept_id,
            "action_class": action.get("action_class"),
            "failed_requirement": (action.get("requires") or [None])[0],
            "failed_verification": (action.get("verification") or {}).get("failed_channel")
            if isinstance(action.get("verification"), dict)
            else None,
            "negative_constraint": action.get("failure_reason"),
            "scope": {
                "executor_profile": executor_profile,
                "world_revision": world_revision,
            },
            "evidence": {
                "source": "teaching_action_result",
                "support_count": 1,
                "confidence": 0.72,
            },
            "disposition": "candidate_constraint_pending_revalidation",
        }
        summaries.append(summary)
    return summaries


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
    pedagogical_signals: dict[str, Any] | None = None,
    world_revision: int | None = None,
    observation_packet: dict[str, Any] | None = None,
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
    signals = build_pedagogical_signals(
        signal_types=(pedagogical_signals or {}).get("signal_types"),
        target_experience_ref=(pedagogical_signals or {}).get("target_experience_ref"),
        interruption_occurred=(pedagogical_signals or {}).get("interruption_occurred", False),
        clarification_occurred=(pedagogical_signals or {}).get("clarification_occurred", False),
        outcome="completed_successfully" if successful else "failed",
    )
    infeasibility_summaries = compile_infeasibility_summaries(
        demonstrated_actions,
        concept_id=target_concept_id,
        world_revision=world_revision,
    )
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
        "applicability_constraints": {
            "negative_constraints": infeasibility_summaries,
            "policy": "scoped_candidate_constraints_require_revalidation_before_global_concept_update",
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
            "failed_action_count": len(demonstrated_actions) - len(successful),
            "raw_teleoperation_trace_persisted": False,
        },
        "teaching_evidence_summary": build_portable_teaching_evidence_summary(observation_packet or {}),
        "pedagogical_signals": signals,
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
