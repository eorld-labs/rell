from __future__ import annotations

from copy import deepcopy
from typing import Any


ARMED_CALIBRATION_STATUSES = {"hardware_verified"}
LOOPBACK_CALIBRATION_STATUSES = {"loopback_verified"}


def validate_robot_calibration(
    calibration: dict[str, Any], *, allow_loopback_armed: bool = False
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    required = {
        "calibration_id",
        "calibration_status",
        "source_scope",
        "frame_graph",
        "body_envelope",
        "reachable_workspace",
        "payload_limit_kg",
        "motion_limits",
        "sensor_frames",
        "end_effector_frames",
    }
    for field in sorted(required - set(calibration)):
        errors.append({"reason": "required_calibration_field_missing", "field": field})

    frame_graph = calibration.get("frame_graph", [])
    frame_ids = set()
    for transform in frame_graph if isinstance(frame_graph, list) else []:
        parent = transform.get("parent_frame")
        child = transform.get("child_frame")
        translation = transform.get("translation_m")
        rotation = transform.get("rotation_xyzw")
        measured_transform = (
            isinstance(translation, list)
            and len(translation) == 3
            and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in translation)
            and isinstance(rotation, list)
            and len(rotation) == 4
            and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in rotation)
        )
        if parent and child and measured_transform:
            frame_ids.update({parent, child})
        else:
            errors.append({"reason": "invalid_frame_transform", "transform": deepcopy(transform)})
    for frame in calibration.get("sensor_frames", []):
        if frame not in frame_ids:
            errors.append({"reason": "sensor_frame_not_in_frame_graph", "frame_id": frame})
    for frame in calibration.get("end_effector_frames", []):
        if frame not in frame_ids:
            errors.append({"reason": "end_effector_frame_not_in_frame_graph", "frame_id": frame})

    envelope = calibration.get("body_envelope", {})
    if not _positive(envelope.get("radius_m")) or not _positive(envelope.get("height_m")):
        errors.append({"reason": "body_envelope_not_measured"})
    workspace = calibration.get("reachable_workspace", {})
    if not workspace.get("frame_id") or not workspace.get("bounds_m"):
        errors.append({"reason": "reachable_workspace_not_measured"})
    if not _positive(calibration.get("payload_limit_kg")):
        errors.append({"reason": "payload_limit_not_measured"})
    limits = calibration.get("motion_limits", {})
    for field in ("max_linear_speed_mps", "max_angular_speed_rps", "max_contact_force_n"):
        if not _positive(limits.get(field)):
            errors.append({"reason": "motion_limit_not_measured", "field": field})

    status = calibration.get("calibration_status")
    source_scope = calibration.get("source_scope")
    loopback_armed = (
        allow_loopback_armed
        and status in LOOPBACK_CALIBRATION_STATUSES
        and source_scope == "loopback_only"
    )
    shadow_ready = not errors
    armed_ready = shadow_ready and (status in ARMED_CALIBRATION_STATUSES or loopback_armed)
    return {
        "status": "calibration_valid" if shadow_ready else "calibration_invalid",
        "calibration_id": calibration.get("calibration_id"),
        "shadow_ready": shadow_ready,
        "armed_ready": armed_ready,
        "hardware_verified": status in ARMED_CALIBRATION_STATUSES,
        "loopback_only": source_scope == "loopback_only",
        "errors": errors,
        "direct_execution_allowed": False,
    }


def _positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
