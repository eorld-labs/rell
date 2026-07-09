from __future__ import annotations

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


RUNTIME_EVENT_TYPES = {
    "stage_started",
    "state_update",
    "observation_update",
    "failure_event",
    "human_confirmation",
    "stop",
}


@runtime_checkable
class RellRobotAdapter(Protocol):
    """Contract between P016Runtime and any robot, simulator, or mock adapter."""

    queue: Any

    def report_capabilities(self) -> list[str]:
        """Return capability ids supported by this adapter."""

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
