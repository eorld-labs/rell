from __future__ import annotations

from pathlib import Path

from adapters.adapter_contract import REQUIRED_CAPABILITIES, RellRobotAdapter
from adapters.vendor_robot_adapter_stub import VendorRobotAdapterStub
from runtime_core import MockRobotAdapter, SerialEventQueue, SimulatedPouringRobotAdapter, read_json


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
REQUIRED_METHODS = [
    "report_capabilities",
    "execute_stage_action",
    "pause_streams",
    "resume_streams",
    "get_latest_snapshot",
    "stop",
    "request_human_confirmation",
]


def require_adapter_shape(name: str, adapter: object) -> None:
    for method in REQUIRED_METHODS:
        if not callable(getattr(adapter, method, None)):
            raise AssertionError(f"{name} missing adapter method: {method}")
    if not isinstance(adapter, RellRobotAdapter):
        raise AssertionError(f"{name} does not satisfy RellRobotAdapter protocol")
    capabilities = set(adapter.report_capabilities())
    missing = REQUIRED_CAPABILITIES - capabilities
    if missing:
        raise AssertionError(f"{name} missing capabilities: {sorted(missing)}")


def main() -> None:
    timeline = read_json(DATA / "mock_timeline_success.json")
    require_adapter_shape("MockRobotAdapter", MockRobotAdapter(timeline, SerialEventQueue()))
    require_adapter_shape("SimulatedPouringRobotAdapter", SimulatedPouringRobotAdapter("simulated_success", SerialEventQueue()))

    vendor = VendorRobotAdapterStub(SerialEventQueue(), vendor_name="example_vendor")
    vendor.connect({"endpoint": "stub://local", "mode": "contract_test"})
    require_adapter_shape("VendorRobotAdapterStub", vendor)
    mapped = vendor.map_vendor_state_to_rell_variables(
        {
            "spout_to_cup_distance_cm": 0.4,
            "tilt_angle_degree": 22.0,
            "flow_rate_ml_per_second": 3.6,
            "water_surface_gap_cm": 0.35,
            "flow_integral_ml": 114.0,
        }
    )
    if mapped["tilt_angle"] != 22.0 or mapped["water_surface_gap"] != 0.35:
        raise AssertionError(f"vendor state mapping failed: {mapped}")
    observations = vendor.map_vendor_fact_observations({"water_surface_gap_cm": 0.35, "flow_integral_ml": 114.0})
    if len(observations) != 2 or {item["state"] for item in observations} != {"established"}:
        raise AssertionError(f"vendor observation mapping failed: {observations}")

    print("Adapter contract validation passed.")
    print("Validated: MockRobotAdapter, SimulatedPouringRobotAdapter, VendorRobotAdapterStub.")


if __name__ == "__main__":
    main()
