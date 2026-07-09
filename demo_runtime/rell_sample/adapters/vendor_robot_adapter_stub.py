from __future__ import annotations

from copy import deepcopy
from typing import Any

from .adapter_contract import REQUIRED_CAPABILITIES


class VendorRobotAdapterStub:
    """Integration placeholder for replacing SimulatedRobotAdapter with a real robot SDK."""

    def __init__(self, queue: Any, vendor_name: str = "vendor_robot") -> None:
        self.queue = queue
        self.vendor_name = vendor_name
        self.connected = False
        self.paused = False
        self.latest_snapshot: dict[str, Any] = {}
        self.confirmation_requests: list[dict[str, Any]] = []

    def connect(self, config: dict[str, Any]) -> None:
        """Connect to a vendor SDK or middleware in future integration work."""
        self.connected = True
        self.latest_snapshot["connection"] = {
            "vendor_name": self.vendor_name,
            "endpoint": config.get("endpoint", "not_configured"),
            "mode": config.get("mode", "stub"),
        }

    def report_capabilities(self) -> list[str]:
        return sorted(REQUIRED_CAPABILITIES)

    def execute_stage_action(self, stage: dict[str, Any], context: dict[str, Any], callback=None) -> None:
        raise NotImplementedError(
            "VendorRobotAdapterStub is an integration boundary. Map this stage to vendor SDK motion commands."
        )

    def pause_streams(self, process_instance_id: str) -> None:
        self.paused = True

    def resume_streams(self, process_instance_id: str) -> None:
        self.paused = False

    def get_latest_snapshot(self, process_instance_id: str) -> dict[str, Any]:
        return deepcopy(self.latest_snapshot)

    def stop(self, reason: str, callback=None) -> None:
        result = {"stopped": True, "reason": reason, "vendor_name": self.vendor_name}
        if callback:
            callback(result)

    def request_human_confirmation(self, prompt: str, callback=None) -> None:
        request = {"prompt": prompt, "vendor_name": self.vendor_name}
        self.confirmation_requests.append(request)
        if callback:
            callback({"status": "requested", **request})

    def map_vendor_state_to_rell_variables(self, vendor_state: dict[str, Any]) -> dict[str, Any]:
        """Translate vendor SDK state into RELL continuous state variables."""
        return {
            "spout_to_cup_distance": vendor_state.get("spout_to_cup_distance_cm"),
            "tilt_angle": vendor_state.get("tilt_angle_degree"),
            "water_flow_rate": vendor_state.get("flow_rate_ml_per_second"),
            "water_surface_gap": vendor_state.get("water_surface_gap_cm"),
        }

    def map_vendor_fact_observations(self, vendor_state: dict[str, Any]) -> list[dict[str, Any]]:
        """Translate vendor observations into RELL target fact channel judgments."""
        observations = []
        if "water_surface_gap_cm" in vendor_state:
            observations.append(
                {
                    "fact_id": "cup_has_water",
                    "channel_id": "physical_liquid_level",
                    "state": "established" if vendor_state["water_surface_gap_cm"] <= 0.5 else "not_established",
                    "inputs": {"water_surface_gap": vendor_state["water_surface_gap_cm"]},
                }
            )
        if "flow_integral_ml" in vendor_state:
            observations.append(
                {
                    "fact_id": "cup_has_water",
                    "channel_id": "digital_flow_integral",
                    "state": "established" if vendor_state["flow_integral_ml"] >= 80.0 else "not_established",
                    "inputs": {"flow_integral_ml": vendor_state["flow_integral_ml"]},
                }
            )
        return observations
