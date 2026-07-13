from __future__ import annotations

from copy import deepcopy
from typing import Any


class VendorRobotTransportStub:
    """Replace this transport only when a specific robot SDK or ROS2 graph is available."""

    transport_kind = "vendor_sdk_unbound"

    def __init__(self, vendor_name: str, capabilities: list[str]) -> None:
        self.vendor_name = vendor_name
        self.capabilities = sorted(set(capabilities))
        self.connected = False
        self.connection_config: dict[str, Any] = {}

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        self.connection_config = deepcopy(config)
        return {
            "status": "blocked",
            "reason": "real_vendor_sdk_not_bound",
            "vendor_name": self.vendor_name,
            "required_input": ["sdk_or_ros2_endpoint", "authentication_or_node_config", "vendor_command_mapping"],
        }

    def report_capabilities(self) -> list[str]:
        return list(self.capabilities)

    def send_command(self, command: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Bind this method to the selected robot SDK or ROS2 action server during real hardware joint debugging.")

    def cancel(self, command_id: str, reason: str) -> dict[str, Any]:
        raise NotImplementedError("Bind cancellation to the selected robot SDK or ROS2 action server.")

    def emergency_stop(self, reason: str) -> dict[str, Any]:
        raise NotImplementedError("Bind emergency stop to an independently verified hardware stop path.")
