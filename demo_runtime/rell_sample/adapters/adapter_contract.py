from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol, runtime_checkable


REQUIRED_CAPABILITIES = {
    "align_container",
    "tilt_container",
    "hold_pose",
    "return_to_level",
    "observe_tilt_angle",
    "observe_flow_rate",
    "observe_liquid_level",
    "request_human_confirmation",
}


OPTIONAL_CAPABILITIES = {
    "emergency_stop",
    "read_joint_state",
    "read_depth_frame",
    "read_force_torque",
    "read_gripper_state",
    "stream_vendor_diagnostics",
}


GENERAL_EMBODIED_CAPABILITIES = {
    "observe_target",
    "navigate_to_target",
    "align_end_effector",
    "grasp_target",
    "verify_target_in_gripper",
    "navigate_to_destination",
    "place_target",
    "verify_target_supported",
    "handover_target",
    "request_human_confirmation",
    "cancel_motion",
    "emergency_stop",
}


REAL_ROBOT_OPERATING_MODES = {"shadow", "dry_run", "armed"}


RUNTIME_EVENT_TYPES = {
    "stage_started",
    "state_update",
    "observation_update",
    "failure_event",
    "human_confirmation",
    "stop",
}


def build_executor_profile(
    executor_id: str,
    executor_type: str,
    body_profile: str,
    *,
    supported_actions: list[str] | None = None,
) -> dict[str, Any]:
    """Return the minimal body/capability profile reserved for P008-style subject constraints."""

    return {
        "schema_version": "1.0.0",
        "executor_id": executor_id,
        "executor_type": executor_type,
        "body_profile": body_profile,
        "supported_actions": supported_actions or sorted(REQUIRED_CAPABILITIES),
        "reachable_workspace": {
            "frame_id": "executor_base",
            "shape": "not_modeled_in_stage_one",
            "notes": "Stage one reserves the field for P008 spatial entry constraints; it does not solve IK.",
        },
        "sensor_frames": [
            {"sensor_id": "camera_depth_front", "frame_id": "camera_depth_front_frame"},
            {"sensor_id": "flow_estimator", "frame_id": "digital_estimation_frame"},
        ],
        "end_effector_type": "stage_one_mock_gripper",
        "payload_limit": {"value": 1.0, "unit": "kg"},
        "precision_level": "mock_demonstration",
        "mobility_constraints": {
            "turning_radius": {"value": 0.0, "unit": "m"},
            "step_over_height": {"value": 0.0, "unit": "m"},
        },
        "spatial_entry_constraints": {
            "body_envelope": {"shape": "cylinder", "radius_m": 0.25, "height_m": 1.2},
            "clearance_required_m": 0.1,
        },
    }


def clone_executor_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(profile)


@runtime_checkable
class RellRobotAdapter(Protocol):
    """Contract between P016Runtime and any robot, simulator, or mock adapter."""

    queue: Any

    def report_capabilities(self) -> list[str]:
        """Return capability ids supported by this adapter."""

    def report_executor_profile(self) -> dict[str, Any]:
        """Return the executor body/capability profile used for admission and audit."""

    def execute_stage_action(self, stage: dict[str, Any], context: dict[str, Any], callback=None) -> None:
        """Execute or simulate a physical stage and push RuntimeEvent objects into queue."""

    def pause_streams(self, process_instance_id: str) -> None:
        """Apply backpressure while Runtime is waiting for human confirmation."""

    def resume_streams(self, process_instance_id: str) -> None:
        """Resume event streams after Runtime leaves a paused state."""

    def get_latest_snapshot(self, process_instance_id: str) -> dict[str, Any]:
        """Return the latest adapter-side sensor snapshot."""

    def stop(self, reason: str, callback=None) -> None:
        """Stop execution or request stop from the underlying robot SDK."""

    def request_human_confirmation(self, prompt: str, callback=None) -> None:
        """Request human confirmation without blocking the Runtime event loop."""


@runtime_checkable
class RellRobotTransport(Protocol):
    """Narrow vendor SDK/ROS2 boundary used by RealRobotSafetyGateway."""

    transport_kind: str

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        """Connect to vendor control and telemetry services."""

    def report_capabilities(self) -> list[str]:
        """Report only operations the bound hardware transport can execute."""

    def send_command(self, command: dict[str, Any]) -> dict[str, Any]:
        """Send one admitted command and return its receipt and telemetry."""

    def cancel(self, command_id: str, reason: str) -> dict[str, Any]:
        """Cancel one active vendor command."""

    def emergency_stop(self, reason: str) -> dict[str, Any]:
        """Invoke the vendor emergency-stop path."""
