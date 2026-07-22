from __future__ import annotations

from typing import Any


RELATION_PLANS = {
    "near_human": ("navigate_to_relative_human_zone", "executor_distance_within_personal_zone"),
    "in_front_of": ("navigate_to_front_region", "relative_pose_front_bound"),
    "behind": ("navigate_to_rear_region", "relative_pose_rear_bound"),
    "facing": ("orient_toward_reference", "orientation_error_bound"),
}


def build_relative_spatial_plan_contract(analysis: dict[str, Any]) -> dict[str, Any] | None:
    roles = analysis.get("role_bindings") or {}
    relation_role = next(
        (roles.get(name) for name in ("destination", "direction") if (roles.get(name) or {}).get("spatial_relation") in RELATION_PLANS),
        None,
    )
    if not relation_role:
        return None
    relation = relation_role["spatial_relation"]
    process, verification = RELATION_PLANS[relation]
    return {
        "schema_version": "1.0.0",
        "status": "candidate_only",
        "relation": relation,
        "reference": relation_role.get("reference"),
        "process_contract": process,
        "verification_contract": verification,
        "dynamic_reference_frame_required": relation_role.get("reference") == "human_speaker",
        "control_gateway": "P018",
        "verification_gateway": "P016",
        "direct_execution_allowed": False,
        "runtime_fact_committed": False,
    }
