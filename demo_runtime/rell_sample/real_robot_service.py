from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from adapters.loopback_robot_transport import LoopbackRobotTransport
from adapters.real_robot_gateway import RealRobotSafetyGateway
from runtime_core import SerialEventQueue


ROOT = Path(__file__).resolve().parent
LOOPBACK_CALIBRATION = ROOT / "data" / "loopback_robot_calibration.json"
_SESSIONS: dict[str, dict[str, Any]] = {}
_TRANSPORT_FACTORIES: dict[str, Callable[[], Any]] = {}
_LOCK = threading.RLock()


def register_real_robot_transport_factory(vendor_id: str, factory: Callable[[], Any]) -> None:
    """Called by a locally installed, reviewed vendor plugin during process startup."""
    if not vendor_id or not callable(factory):
        raise ValueError("vendor_id_and_callable_factory_required")
    with _LOCK:
        _TRANSPORT_FACTORIES[vendor_id] = factory


def build_real_robot_readiness_catalog() -> dict[str, Any]:
    with _LOCK:
        vendors = sorted(_TRANSPORT_FACTORIES)
    return {
        "schema_version": "1.0.0",
        "status": "software_preflight_complete_waiting_for_real_robot" if not vendors else "vendor_transport_available_for_joint_debug",
        "operating_modes": ["shadow", "dry_run", "armed"],
        "general_stage_chain": [
            "observe_target",
            "navigate_to_target",
            "align_end_effector",
            "grasp_target",
            "verify_target_in_gripper",
            "navigate_to_destination",
            "place_target",
            "verify_target_supported",
        ],
        "registered_vendor_ids": vendors,
        "required_real_hardware_input": [
            "real_robot_vendor_and_model",
            "vendor_sdk_or_ros2_interface",
            "hardware_verified_calibration",
            "independently_verified_emergency_stop",
        ],
        "boundary": {
            "remote_request_cannot_register_code": True,
            "loopback_cannot_claim_physical_evidence": True,
            "runtime_fact_committed_by_gateway": False,
            "direct_execution_allowed": False,
        },
    }


def start_real_robot_session(
    *, transport_type: str, vendor_id: str = "", calibration: dict[str, Any] | None = None
) -> dict[str, Any]:
    if transport_type == "loopback_preflight":
        transport = LoopbackRobotTransport()
        calibration_payload = json.loads(LOOPBACK_CALIBRATION.read_text(encoding="utf-8"))
        vendor_name = "loopback_preflight"
    elif transport_type == "registered_vendor":
        with _LOCK:
            factory = _TRANSPORT_FACTORIES.get(vendor_id)
        if not factory:
            return {
                "error": "real_vendor_transport_factory_not_registered",
                "vendor_id": vendor_id,
                "registered_vendor_ids": sorted(_TRANSPORT_FACTORIES),
            }
        if not isinstance(calibration, dict):
            return {"error": "hardware_calibration_required"}
        transport = factory()
        calibration_payload = deepcopy(calibration)
        vendor_name = vendor_id
    else:
        return {"error": "unsupported_real_robot_transport_type", "allowed": ["loopback_preflight", "registered_vendor"]}

    session_id = "real_robot_session_" + uuid.uuid4().hex[:12]
    queue = SerialEventQueue()
    gateway = RealRobotSafetyGateway(queue, transport, calibration_payload, vendor_name=vendor_name)
    connection = gateway.connect({"endpoint": "loopback://preflight"} if transport_type == "loopback_preflight" else {})
    session = {
        "session_id": session_id,
        "transport_type": transport_type,
        "vendor_id": vendor_name,
        "gateway": gateway,
        "queue": queue,
        "connection": connection,
    }
    with _LOCK:
        _SESSIONS[session_id] = session
    return _session_view(session)


def get_real_robot_session(session_id: str) -> dict[str, Any]:
    session = _get(session_id)
    return _session_view(session) if session else {"error": "real_robot_session_not_found", "session_id": session_id}


def heartbeat_real_robot_session(session_id: str, telemetry: dict[str, Any] | None = None) -> dict[str, Any]:
    session = _get(session_id)
    if not session:
        return {"error": "real_robot_session_not_found", "session_id": session_id}
    result = session["gateway"].update_heartbeat(telemetry)
    return {**result, "session": _session_view(session)}


def set_real_robot_session_mode(session_id: str, mode: str, *, human_authorized: bool = False) -> dict[str, Any]:
    session = _get(session_id)
    if not session:
        return {"error": "real_robot_session_not_found", "session_id": session_id}
    result = session["gateway"].set_mode(mode, human_authorized=human_authorized)
    return {**result, "session": _session_view(session)}


def dispatch_real_robot_stage(
    session_id: str, stage: dict[str, Any], *, process_instance_id: str, world_revision: int
) -> dict[str, Any]:
    session = _get(session_id)
    if not session:
        return {"error": "real_robot_session_not_found", "session_id": session_id}
    result = session["gateway"].dispatch_stage(
        stage,
        {"process_instance_id": process_instance_id, "world_revision": world_revision},
    )
    return {**result, "queued_runtime_event_count": len(session["queue"].events)}


def emergency_stop_real_robot_session(session_id: str, reason: str) -> dict[str, Any]:
    session = _get(session_id)
    if not session:
        return {"error": "real_robot_session_not_found", "session_id": session_id}
    return session["gateway"].emergency_stop(reason)


def reset_real_robot_emergency_stop(session_id: str, *, human_authorized: bool = False) -> dict[str, Any]:
    session = _get(session_id)
    if not session:
        return {"error": "real_robot_session_not_found", "session_id": session_id}
    return session["gateway"].reset_emergency_stop(human_authorized=human_authorized)


def _get(session_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return _SESSIONS.get(session_id)


def _session_view(session: dict[str, Any]) -> dict[str, Any]:
    gateway = session["gateway"]
    return {
        "schema_version": "1.0.0",
        "session_id": session["session_id"],
        "transport_type": session["transport_type"],
        "vendor_id": session["vendor_id"],
        "connection": deepcopy(session["connection"]),
        "gateway_mode": gateway.mode,
        "emergency_stopped": gateway.emergency_stopped,
        "queued_runtime_event_count": len(session["queue"].events),
        "record_count": len(gateway.recorder.records),
        "readiness": gateway.readiness(),
    }
