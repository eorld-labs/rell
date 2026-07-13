from __future__ import annotations

import hashlib
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .adapter_contract import GENERAL_EMBODIED_CAPABILITIES, REQUIRED_CAPABILITIES, build_executor_profile, clone_executor_profile
from .calibration import validate_robot_calibration
from .observation_bridge import bridge_robot_telemetry
from .session_recorder import RobotSessionRecorder


class RealRobotSafetyGateway:
    def __init__(
        self,
        queue: Any,
        transport: Any,
        calibration: dict[str, Any],
        *,
        vendor_name: str = "unbound_vendor",
        heartbeat_timeout_ms: int = 1500,
        command_ttl_ms: int = 3000,
        clock=None,
    ) -> None:
        self.queue = queue
        self.transport = transport
        self.calibration = deepcopy(calibration)
        self.vendor_name = vendor_name
        self.heartbeat_timeout_ms = heartbeat_timeout_ms
        self.command_ttl_ms = command_ttl_ms
        self.clock = clock or time.monotonic
        self.mode = "shadow"
        self.connected = False
        self.paused = False
        self.emergency_stopped = False
        self.last_heartbeat_at: float | None = None
        self.sequence = 0
        self.latest_snapshot: dict[str, Any] = {}
        self.latest_world_revision: int | None = None
        self.receipts: dict[str, dict[str, Any]] = {}
        self.active_command_id: str | None = None
        self.confirmation_requests: list[dict[str, Any]] = []
        self.recorder = RobotSessionRecorder(f"gateway_{vendor_name}")
        self.executor_profile = self._build_profile()

    @property
    def is_loopback(self) -> bool:
        return getattr(self.transport, "transport_kind", "") == "loopback_only"

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        result = self.transport.connect(config)
        self.connected = result.get("status") == "connected"
        self.last_heartbeat_at = self.clock() if self.connected else None
        self.recorder.record("connection", result)
        return {**result, "gateway_mode": self.mode, "direct_execution_allowed": False}

    def update_heartbeat(self, telemetry: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.connected:
            return {"error": "robot_transport_not_connected"}
        self.last_heartbeat_at = self.clock()
        if telemetry:
            self.latest_snapshot.update(deepcopy(telemetry))
            if isinstance(telemetry.get("world_revision"), int):
                self.latest_world_revision = telemetry["world_revision"]
        return {"status": "heartbeat_accepted", "gateway_mode": self.mode}

    def set_mode(self, mode: str, *, human_authorized: bool = False) -> dict[str, Any]:
        if mode not in {"shadow", "dry_run", "armed"}:
            return {"error": "unsupported_gateway_mode", "allowed_modes": ["shadow", "dry_run", "armed"]}
        calibration = validate_robot_calibration(self.calibration, allow_loopback_armed=self.is_loopback)
        if mode in {"dry_run", "armed"} and not calibration["shadow_ready"]:
            return {"error": "robot_calibration_incomplete", "calibration": calibration}
        if mode == "armed":
            if not self.connected:
                return {"error": "robot_transport_not_connected"}
            if not human_authorized:
                return {"error": "explicit_human_arm_authorization_required"}
            if not calibration["armed_ready"]:
                return {"error": "hardware_verified_calibration_required", "calibration": calibration}
            if not self._heartbeat_current():
                return {"error": "robot_heartbeat_stale"}
            if self.emergency_stopped:
                return {"error": "gateway_emergency_stop_latched"}
        self.mode = mode
        result = {
            "status": "gateway_mode_changed",
            "gateway_mode": mode,
            "loopback_only": self.is_loopback,
            "hardware_motion_possible": mode == "armed" and not self.is_loopback,
        }
        self.recorder.record("mode_change", result)
        return result

    def report_capabilities(self) -> list[str]:
        capabilities = getattr(self.transport, "report_capabilities", None)
        return sorted(set(capabilities() if callable(capabilities) else []))

    def report_executor_profile(self) -> dict[str, Any]:
        return clone_executor_profile(self.executor_profile)

    def execute_stage_action(self, stage: dict[str, Any], context: dict[str, Any], callback=None) -> None:
        result = self.dispatch_stage(stage, context)
        if callback:
            callback(deepcopy(result))

    def dispatch_stage(self, stage: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return self.dispatch_compiled_command(self.compile_stage_command(stage, context))

    def compile_stage_command(self, stage: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return self._compile_command(stage, context)

    def dispatch_compiled_command(self, command: dict[str, Any]) -> dict[str, Any]:
        command_id = command["command_id"]
        if command_id in self.receipts:
            return {**deepcopy(self.receipts[command_id]), "idempotent_replay": True}
        admission = self._admit(command)
        self.recorder.record("command_candidate", command)
        if "error" in admission:
            receipt = {**admission, "command_id": command_id, "gateway_mode": self.mode, "hardware_command_sent": False}
            self.recorder.record("command_rejected", receipt)
            return deepcopy(receipt)
        if self.mode == "shadow":
            receipt = self._non_motion_receipt(command, "command_shadowed")
        elif self.mode == "dry_run":
            receipt = self._non_motion_receipt(command, "command_dry_run_validated")
        else:
            self.active_command_id = command_id
            receipt = self.transport.send_command(command)
            receipt.update({"gateway_mode": self.mode, "hardware_command_sent": not self.is_loopback})
            self.recorder.record("transport_receipt", receipt)
            telemetry = receipt.get("telemetry")
            if receipt.get("status") == "accepted" and isinstance(telemetry, dict):
                bridge = bridge_robot_telemetry(
                    telemetry,
                    process_instance_id=command["process_instance_id"],
                    stage_id=command["stage_id"],
                    sequence_start=self.sequence,
                )
                receipt["observation_bridge"] = bridge
                if bridge["status"] == "telemetry_bridged":
                    self.sequence = bridge["next_sequence"]
                    for event in bridge["events"]:
                        self.queue.enqueue(event)
                        self.recorder.record("runtime_event", event)
                    self.latest_snapshot = deepcopy(telemetry)
                    self.latest_world_revision = bridge["world_revision"]
            self.active_command_id = None
        # Only an accepted transport command is execution-idempotent. Shadow,
        # dry-run and rejected candidates must be re-evaluated after conditions change.
        if self.mode == "armed" and receipt.get("status") == "accepted":
            self.receipts[command_id] = deepcopy(receipt)
        return receipt

    def pause_streams(self, process_instance_id: str) -> None:
        self.paused = True
        self.recorder.record("streams_paused", {"process_instance_id": process_instance_id})

    def resume_streams(self, process_instance_id: str) -> None:
        self.paused = False
        self.recorder.record("streams_resumed", {"process_instance_id": process_instance_id})

    def get_latest_snapshot(self, process_instance_id: str) -> dict[str, Any]:
        return deepcopy(self.latest_snapshot)

    def cancel_active(self, reason: str) -> dict[str, Any]:
        if not self.active_command_id:
            return {"status": "no_active_command", "reason": reason}
        result = self.transport.cancel(self.active_command_id, reason)
        self.recorder.record("command_cancelled", result)
        self.active_command_id = None
        return result

    def stop(self, reason: str, callback=None) -> None:
        result = self.emergency_stop(reason)
        if callback:
            callback(deepcopy(result))

    def emergency_stop(self, reason: str) -> dict[str, Any]:
        self.emergency_stopped = True
        self.mode = "shadow"
        result = self.transport.emergency_stop(reason) if self.connected else {"status": "emergency_stopped", "reason": reason}
        result.update({"gateway_latched": True, "gateway_mode": self.mode})
        self.recorder.record("emergency_stop", result)
        return result

    def reset_emergency_stop(self, *, human_authorized: bool = False) -> dict[str, Any]:
        if not human_authorized:
            return {"error": "explicit_human_reset_authorization_required"}
        self.emergency_stopped = False
        clear = getattr(self.transport, "clear_emergency_stop", None)
        if callable(clear):
            clear()
        result = {"status": "emergency_stop_reset", "gateway_mode": self.mode, "requires_rearm": True}
        self.recorder.record("emergency_stop_reset", result)
        return result

    def request_human_confirmation(self, prompt: str, callback=None) -> None:
        request = {"confirmation_id": f"real_confirm_{len(self.confirmation_requests) + 1}", "prompt": prompt}
        self.confirmation_requests.append(request)
        if callback:
            callback({"status": "requested", **request})

    def readiness(self) -> dict[str, Any]:
        calibration = validate_robot_calibration(self.calibration, allow_loopback_armed=self.is_loopback)
        blockers = []
        if not self.connected:
            blockers.append("robot_transport_not_connected")
        if not calibration["hardware_verified"]:
            blockers.append("hardware_calibration_not_verified")
        if self.is_loopback:
            blockers.append("real_robot_transport_not_bound")
        return {
            "status": "ready_for_real_robot_joint_debug" if not blockers else "software_preflight_complete_waiting_for_real_robot",
            "gateway_mode": self.mode,
            "calibration": calibration,
            "blockers": blockers,
            "software_contract_complete": True,
            "hardware_motion_possible": self.mode == "armed" and not self.is_loopback,
        }

    def _compile_command(self, stage: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        operator = str(stage.get("operator") or stage.get("action") or stage.get("stage_id") or "")
        process_instance_id = str(context.get("process_instance_id", ""))
        stage_id = str(stage.get("stage_id") or operator)
        world_revision = context.get("world_revision")
        seed = "|".join([process_instance_id, stage_id, operator, str(world_revision), str(stage.get("target_ref", ""))])
        return {
            "schema_version": "1.0.0",
            "command_id": "real_cmd_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16],
            "process_instance_id": process_instance_id,
            "stage_id": stage_id,
            "operator": operator,
            "target_ref": stage.get("target_ref"),
            "destination_ref": stage.get("destination_ref"),
            "expected_fact": stage.get("expected_fact"),
            "world_revision": world_revision,
            "constraints": deepcopy(stage.get("constraints", {})),
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "ttl_ms": self.command_ttl_ms,
            "compiled_at_monotonic": self.clock(),
            "candidate_only": True,
        }

    def _admit(self, command: dict[str, Any]) -> dict[str, Any]:
        if command["operator"] not in GENERAL_EMBODIED_CAPABILITIES:
            return {"error": "unsupported_general_embodied_operator", "operator": command["operator"]}
        if not command["process_instance_id"]:
            return {"error": "process_instance_id_required"}
        if not isinstance(command["world_revision"], int) or command["world_revision"] < 0:
            return {"error": "valid_world_revision_required"}
        compiled_at = command.get("compiled_at_monotonic")
        if not isinstance(compiled_at, (int, float)) or (self.clock() - compiled_at) * 1000 > command.get("ttl_ms", 0):
            return {"error": "command_ttl_expired"}
        if self.latest_world_revision is not None and command["world_revision"] < self.latest_world_revision:
            return {
                "error": "command_world_revision_stale",
                "command_world_revision": command["world_revision"],
                "latest_world_revision": self.latest_world_revision,
            }
        if self.paused:
            return {"error": "gateway_streams_paused"}
        if self.emergency_stopped:
            return {"error": "gateway_emergency_stop_latched"}
        limits = self.calibration.get("motion_limits", {})
        constraints = command["constraints"]
        for requested, maximum in (
            (constraints.get("max_linear_speed_mps"), limits.get("max_linear_speed_mps")),
            (constraints.get("max_contact_force_n"), limits.get("max_contact_force_n")),
        ):
            if requested is not None and maximum is not None and requested > maximum:
                return {"error": "command_exceeds_calibrated_safety_limit", "requested": requested, "maximum": maximum}
        if self.mode == "armed" and not self._heartbeat_current():
            self.emergency_stop("heartbeat_timeout_before_command")
            return {"error": "robot_heartbeat_stale_emergency_stop_latched"}
        return {"status": "command_admitted"}

    def _heartbeat_current(self) -> bool:
        return self.last_heartbeat_at is not None and (self.clock() - self.last_heartbeat_at) * 1000 <= self.heartbeat_timeout_ms

    def _non_motion_receipt(self, command: dict[str, Any], status: str) -> dict[str, Any]:
        receipt = {
            "status": status,
            "command_id": command["command_id"],
            "gateway_mode": self.mode,
            "hardware_command_sent": False,
            "runtime_fact_committed": False,
        }
        self.recorder.record(status, receipt)
        return receipt

    def _build_profile(self) -> dict[str, Any]:
        profile = build_executor_profile(
            f"{self.vendor_name}_real_robot",
            "real_robot",
            str(self.calibration.get("body_profile", "vendor_unbound")),
            supported_actions=self.report_capabilities(),
        )
        profile.update({
            "reachable_workspace": deepcopy(self.calibration.get("reachable_workspace")),
            "sensor_frames": [{"sensor_id": item, "frame_id": item} for item in self.calibration.get("sensor_frames", [])],
            "end_effector_type": self.calibration.get("end_effector_type", "vendor_unbound"),
            "payload_limit": {"value": self.calibration.get("payload_limit_kg"), "unit": "kg"},
            "mobility_constraints": deepcopy(self.calibration.get("mobility_constraints", {})),
            "spatial_entry_constraints": {"body_envelope": deepcopy(self.calibration.get("body_envelope"))},
            "calibration_id": self.calibration.get("calibration_id"),
        })
        return profile
