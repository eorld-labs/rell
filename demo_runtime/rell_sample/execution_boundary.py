from __future__ import annotations

from copy import deepcopy
from typing import Any


def build_effective_execution_envelope(intrinsic_profile: dict[str, Any], policy_overlay: dict[str, Any] | None) -> dict[str, Any]:
    """Intersect stable body truth with an optional, revocable P6 policy overlay."""
    intrinsic = {
        "body_radius_m": float(intrinsic_profile["body_envelope"]["radius_m"]),
        "body_height_m": float(intrinsic_profile["body_envelope"]["height_m"]),
        "turning_radius_m": float(intrinsic_profile["turning_radius_m"]),
        "max_linear_speed_mps": float(intrinsic_profile.get("max_linear_speed_mps", 1.0)),
        "max_contact_force_n": float(intrinsic_profile.get("max_contact_force_n", 60.0)),
        "can_translate_laterally": bool(intrinsic_profile.get("can_translate_laterally", False)),
        "can_reverse_without_turning": bool(intrinsic_profile.get("can_reverse_without_turning", False)),
    }
    effective = deepcopy(intrinsic)
    effective["minimum_avoidance_distance_m"] = 0.0
    applied: list[dict[str, Any]] = []
    policy = policy_overlay or {}
    motion = policy.get("motion_policy", {})
    if motion.get("max_speed_mps") is not None:
        effective["max_linear_speed_mps"] = min(effective["max_linear_speed_mps"], float(motion["max_speed_mps"]))
        applied.append({"field": "max_linear_speed_mps", "source": "P6_motion_policy", "value": effective["max_linear_speed_mps"]})
    if motion.get("max_contact_force_n") is not None:
        effective["max_contact_force_n"] = min(effective["max_contact_force_n"], float(motion["max_contact_force_n"]))
        applied.append({"field": "max_contact_force_n", "source": "P6_motion_policy", "value": effective["max_contact_force_n"]})
    if motion.get("minimum_avoidance_distance_m") is not None:
        effective["minimum_avoidance_distance_m"] = max(0.0, float(motion["minimum_avoidance_distance_m"]))
        applied.append({"field": "minimum_avoidance_distance_m", "source": "P6_motion_policy", "value": effective["minimum_avoidance_distance_m"]})
    effective["continuous_motion_requires_confirmation"] = bool(motion.get("continuous_motion_requires_confirmation", False))
    if effective["continuous_motion_requires_confirmation"]:
        applied.append({"field": "continuous_motion_requires_confirmation", "source": "P6_motion_policy", "value": True})
    return {
        "intrinsic_profile_ref": intrinsic_profile.get("executor_type"),
        "policy_declaration_ref": policy.get("declaration_id"),
        "intrinsic_body_truth": intrinsic,
        "effective_constraints": effective,
        "applied_policy_constraints": applied,
        "derivation": "intersection_of_intrinsic_body_truth_and_revocable_policy_overlay",
        "policy_never_rewrites_intrinsic_profile": True,
    }


def build_p2_control_decision(*, utterance: str, continuous_motion: bool, effective_envelope: dict[str, Any], world_revision: int, expected_effect: str) -> dict[str, Any]:
    constraints = effective_envelope["effective_constraints"]
    risk_triggered = continuous_motion or constraints["continuous_motion_requires_confirmation"]
    decision = "require_confirmation" if continuous_motion and constraints["continuous_motion_requires_confirmation"] else "allow_with_runtime_verification"
    return {
        "risk_triggered": risk_triggered,
        "first_feature_sequence": {"control_semantics": utterance, "continuous_motion": continuous_motion, "expected_physical_effect": expected_effect},
        "second_feature_sequence": {"world_revision": world_revision, "body_constraints": constraints, "physical_consequence_boundary": "remain_inside_verified_swept_body_envelope"},
        "alignment": {"time": "current_revision", "space": "body_and_scene_frames_aligned", "state": "current_session_state", "consequence": "bounded"},
        "causal_consistency": "requires_confirmation" if decision == "require_confirmation" else "consistent",
        "control_decision": decision,
        "decision_source": "P2_high_risk_physical_control_boundary" if risk_triggered else "normal_runtime_boundary",
    }


def build_p6_execution_receipt(policy_overlay: dict[str, Any] | None, effective_envelope: dict[str, Any], outcome: str) -> dict[str, Any] | None:
    if not policy_overlay:
        return None
    return {
        "declaration_id": policy_overlay.get("declaration_id"),
        "purpose": "embodied_motion_boundary_adaptation_only",
        "applied_constraints": effective_envelope.get("applied_policy_constraints", []),
        "execution_outcome": outcome,
        "intrinsic_profile_modified": False,
        "receipt_required": bool(policy_overlay.get("execution_receipt_required", False)),
    }


def build_p2_safety_self_proof(*, safety_action: str, expected_safe_state: dict[str, Any], observed_state: dict[str, Any]) -> dict[str, Any]:
    reached = all(observed_state.get(key) == value for key, value in expected_safe_state.items())
    return {
        "safety_action": safety_action,
        "expected_safe_state": expected_safe_state,
        "observed_state": observed_state,
        "safe_state_reached": reached,
        "upgrade_protection_required": not reached,
        "chain_type": "P2_safety_action_self_proof",
    }
