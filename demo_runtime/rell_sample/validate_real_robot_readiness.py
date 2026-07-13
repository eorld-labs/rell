from __future__ import annotations

import json
from pathlib import Path

from adapters.adapter_contract import GENERAL_EMBODIED_CAPABILITIES, RellRobotAdapter, RellRobotTransport
from adapters.calibration import validate_robot_calibration
from adapters.loopback_robot_transport import LoopbackRobotTransport
from adapters.real_robot_gateway import RealRobotSafetyGateway
from adapters.session_recorder import RobotSessionRecorder
from adapters.vendor_robot_transport_stub import VendorRobotTransportStub
from runtime_core import SerialEventQueue
from real_robot_service import (
    build_real_robot_readiness_catalog,
    dispatch_real_robot_stage,
    emergency_stop_real_robot_session,
    heartbeat_real_robot_session,
    reset_real_robot_emergency_stop,
    set_real_robot_session_mode,
    start_real_robot_session,
)


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = ROOT.parent / "output" / "rell_sample" / "real_robot_readiness"


PICK_AND_PLACE_STAGES = [
    {"stage_id": "observe", "operator": "observe_target", "target_ref": "object_cup", "expected_fact": "target_object_observed"},
    {"stage_id": "approach", "operator": "navigate_to_target", "target_ref": "object_cup", "expected_fact": "executor_within_grasp_reach"},
    {"stage_id": "align", "operator": "align_end_effector", "target_ref": "object_cup", "expected_fact": "end_effector_aligned_with_target"},
    {"stage_id": "grasp", "operator": "grasp_target", "target_ref": "object_cup", "expected_fact": "target_object_in_gripper", "constraints": {"max_contact_force_n": 8.0}},
    {"stage_id": "verify_grasp", "operator": "verify_target_in_gripper", "target_ref": "object_cup", "expected_fact": "target_object_in_gripper"},
    {"stage_id": "move_to_support", "operator": "navigate_to_destination", "destination_ref": "support_table", "expected_fact": "executor_within_placement_reach", "constraints": {"max_linear_speed_mps": 0.2}},
    {"stage_id": "place", "operator": "place_target", "target_ref": "object_cup", "destination_ref": "support_table", "expected_fact": "target_object_supported_at_destination", "constraints": {"max_contact_force_n": 8.0}},
    {"stage_id": "verify_place", "operator": "verify_target_supported", "target_ref": "object_cup", "destination_ref": "support_table", "expected_fact": "target_object_supported_at_destination"}
]


class ManualClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    template = load_json(DATA / "real_robot_calibration_template.json")
    loopback_calibration = load_json(DATA / "loopback_robot_calibration.json")
    template_check = validate_robot_calibration(template)
    require(not template_check["shadow_ready"], "unmeasured real robot template must fail calibration")
    require(not template_check["armed_ready"], "unverified real robot must never arm")
    loopback_check = validate_robot_calibration(loopback_calibration, allow_loopback_armed=True)
    require(loopback_check["armed_ready"] and loopback_check["loopback_only"], "loopback calibration must be test-ready only")

    clock = ManualClock()
    queue = SerialEventQueue()
    transport = LoopbackRobotTransport()
    require(isinstance(transport, RellRobotTransport), "loopback must satisfy the vendor transport protocol")
    gateway = RealRobotSafetyGateway(queue, transport, loopback_calibration, vendor_name="preflight", clock=clock)
    require(isinstance(gateway, RellRobotAdapter), "gateway must satisfy the runtime adapter protocol")
    require(set(gateway.report_capabilities()).issuperset(GENERAL_EMBODIED_CAPABILITIES), "general embodied capabilities missing")
    require(gateway.report_executor_profile()["reachable_workspace"]["bounds_m"], "reachable workspace must be measured")

    connected = gateway.connect({"endpoint": "loopback://preflight"})
    require(connected["status"] == "connected", "loopback transport must connect")
    context = {"process_instance_id": "real_robot_preflight", "world_revision": 1}

    shadow = gateway.dispatch_stage(PICK_AND_PLACE_STAGES[0], context)
    require(shadow["status"] == "command_shadowed" and not transport.commands, "shadow mode must not send commands")
    require(gateway.set_mode("dry_run")["status"] == "gateway_mode_changed", "dry-run mode must be available")
    dry_run = gateway.dispatch_stage(PICK_AND_PLACE_STAGES[1], context)
    require(dry_run["status"] == "command_dry_run_validated" and not transport.commands, "dry-run must not send commands")
    require(gateway.set_mode("armed").get("error") == "explicit_human_arm_authorization_required", "arming must require explicit authorization")
    gateway.update_heartbeat()
    armed = gateway.set_mode("armed", human_authorized=True)
    require(armed["status"] == "gateway_mode_changed" and not armed["hardware_motion_possible"], "loopback may exercise armed protocol but never real motion")

    receipts = []
    observed_facts = []
    for stage in PICK_AND_PLACE_STAGES:
        gateway.update_heartbeat()
        receipt = gateway.dispatch_stage(stage, context)
        receipts.append(receipt)
        require(receipt["status"] == "accepted", f"preflight stage rejected: {stage['stage_id']}")
        require(receipt["hardware_command_sent"] is False, "loopback must never claim a hardware command was sent")
        require(receipt["observation_bridge"]["runtime_fact_committed"] is False, "adapter observations must remain candidates")
        observed_facts.extend(
            event["payload"]["fact_id"]
            for event in receipt["observation_bridge"]["events"]
            if event["event_type"] == "observation_update"
        )
    require(observed_facts == [stage["expected_fact"] for stage in PICK_AND_PLACE_STAGES], "stage evidence chain mismatch")

    command_count = len(transport.commands)
    replayed = gateway.dispatch_stage(PICK_AND_PLACE_STAGES[-1], context)
    require(replayed["idempotent_replay"] is True and len(transport.commands) == command_count, "duplicate command must be idempotent")
    unsafe_stage = {**PICK_AND_PLACE_STAGES[1], "stage_id": "unsafe_speed", "constraints": {"max_linear_speed_mps": 0.8}}
    unsafe = gateway.dispatch_stage(unsafe_stage, context)
    require(unsafe.get("error") == "command_exceeds_calibrated_safety_limit", "unsafe command must be rejected")
    stale_world = gateway.dispatch_stage({**PICK_AND_PLACE_STAGES[0], "stage_id": "stale_world"}, {**context, "world_revision": 0})
    require(stale_world.get("error") == "command_world_revision_stale", "stale world command must be rejected")

    expiring_command = gateway.compile_stage_command({**PICK_AND_PLACE_STAGES[0], "stage_id": "expired_command"}, context)
    clock.advance(4.0)
    expired = gateway.dispatch_compiled_command(expiring_command)
    require(expired.get("error") == "command_ttl_expired", "expired command must be rejected before transport")

    gateway.update_heartbeat()
    clock.advance(2.0)
    stale = gateway.dispatch_stage({**PICK_AND_PLACE_STAGES[0], "stage_id": "stale_heartbeat"}, context)
    require(stale.get("error") == "robot_heartbeat_stale_emergency_stop_latched", "stale heartbeat must latch emergency stop")
    require(gateway.mode == "shadow" and gateway.emergency_stopped, "heartbeat failure must return gateway to shadow")
    require(gateway.reset_emergency_stop().get("error") == "explicit_human_reset_authorization_required", "stop reset must require human authorization")
    require(gateway.reset_emergency_stop(human_authorized=True)["requires_rearm"], "reset must not silently re-arm")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    recording_path = gateway.recorder.export(OUTPUT / "loopback_joint_debug_recording.json")
    restored = RobotSessionRecorder.load(recording_path)
    replay_queue = SerialEventQueue()
    replay_count = restored.replay_events(replay_queue)
    require(replay_count == len(PICK_AND_PLACE_STAGES) * 2, "state and fact events must be replayable offline")
    readiness = gateway.readiness()
    require(readiness["status"] == "software_preflight_complete_waiting_for_real_robot", "loopback must report the real hardware blocker")
    require("real_robot_transport_not_bound" in readiness["blockers"], "real transport blocker missing")
    require("hardware_calibration_not_verified" in readiness["blockers"], "hardware calibration blocker missing")
    vendor_stub = VendorRobotTransportStub("awaiting_vendor", sorted(GENERAL_EMBODIED_CAPABILITIES))
    require(isinstance(vendor_stub, RellRobotTransport), "vendor stub must satisfy the narrow transport protocol")
    vendor_connection = vendor_stub.connect({})
    require(vendor_connection["reason"] == "real_vendor_sdk_not_bound", "vendor stub must stop at the real SDK boundary")

    service_catalog = build_real_robot_readiness_catalog()
    require(service_catalog["status"] == "software_preflight_complete_waiting_for_real_robot", "service must expose the hardware blocker")
    service_session = start_real_robot_session(transport_type="loopback_preflight")
    service_session_id = service_session["session_id"]
    require(heartbeat_real_robot_session(service_session_id)["status"] == "heartbeat_accepted", "service heartbeat failed")
    service_armed = set_real_robot_session_mode(service_session_id, "armed", human_authorized=True)
    require(service_armed["status"] == "gateway_mode_changed", "service mode transition failed")
    service_dispatch = dispatch_real_robot_stage(
        service_session_id,
        PICK_AND_PLACE_STAGES[0],
        process_instance_id="service_preflight",
        world_revision=1,
    )
    require(service_dispatch["status"] == "accepted", "service dispatch path failed")
    service_stop = emergency_stop_real_robot_session(service_session_id, "preflight_stop_test")
    require(service_stop["gateway_latched"] is True, "service emergency stop failed")
    service_reset = reset_real_robot_emergency_stop(service_session_id, human_authorized=True)
    require(service_reset["requires_rearm"] is True, "service stop reset failed")

    report = {
        "status": "real_robot_software_preflight_passed",
        "stage_chain": [stage["operator"] for stage in PICK_AND_PLACE_STAGES],
        "receipt_count": len(receipts),
        "bridged_fact_candidates": observed_facts,
        "recording_path": str(recording_path),
        "readiness": readiness,
        "service_api_preflight": "passed",
        "next_required_input": ["real_robot_vendor_and_model", "vendor_sdk_or_ros2_interface", "hardware_calibration_measurements"],
    }
    (OUTPUT / "readiness_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
