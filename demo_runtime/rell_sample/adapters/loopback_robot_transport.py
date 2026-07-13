from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .adapter_contract import GENERAL_EMBODIED_CAPABILITIES, REQUIRED_CAPABILITIES


class LoopbackRobotTransport:
    """Protocol test double. Its evidence is never admissible as physical truth."""

    transport_kind = "loopback_only"

    def __init__(self) -> None:
        self.connected = False
        self.commands: list[dict[str, Any]] = []
        self.cancelled_command_ids: list[str] = []
        self.emergency_stopped = False
        self.world_revision = 1

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        self.connected = True
        return {"status": "connected", "transport_kind": self.transport_kind, "endpoint": config.get("endpoint", "loopback://local")}

    def report_capabilities(self) -> list[str]:
        return sorted(REQUIRED_CAPABILITIES | GENERAL_EMBODIED_CAPABILITIES)

    def send_command(self, command: dict[str, Any]) -> dict[str, Any]:
        if not self.connected:
            return {"status": "rejected", "reason": "transport_not_connected"}
        if self.emergency_stopped:
            return {"status": "rejected", "reason": "transport_emergency_stopped"}
        self.commands.append(deepcopy(command))
        observation = {
            "fact_id": command.get("expected_fact", "stage_effect_unknown"),
            "channel_id": "loopback_protocol_channel",
            "state": "established",
            "confidence": 1.0,
            "sensor_id": "loopback_sensor",
            "frame_id": "camera_front",
            "evidence_scope": "loopback_only_not_physical_evidence",
        }
        return {
            "status": "accepted",
            "command_id": command["command_id"],
            "accepted_at": datetime.now(timezone.utc).isoformat(),
            "telemetry": {
                "world_revision": command["world_revision"],
                "states": [{
                    "variable": "last_completed_operator",
                    "value": command["operator"],
                    "unit": "symbolic",
                    "sensor_id": "loopback_controller",
                    "frame_id": "base_link",
                }],
                "observations": [observation],
            },
            "physical_evidence": False,
        }

    def cancel(self, command_id: str, reason: str) -> dict[str, Any]:
        self.cancelled_command_ids.append(command_id)
        return {"status": "cancelled", "command_id": command_id, "reason": reason}

    def emergency_stop(self, reason: str) -> dict[str, Any]:
        self.emergency_stopped = True
        return {"status": "emergency_stopped", "reason": reason}

    def clear_emergency_stop(self) -> None:
        self.emergency_stopped = False
