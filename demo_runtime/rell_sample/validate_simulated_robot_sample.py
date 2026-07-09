from __future__ import annotations

from pathlib import Path

from runtime_core import run_simulated_runtime_sample


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

EXPECTED = {
    "simulated_success": ("completed", "completed", "established"),
    "simulated_no_water": ("requires_human_confirmation", "awaiting_human_confirmation", None),
    "simulated_channel_conflict": ("requires_human_confirmation", "awaiting_human_confirmation", "conflicted"),
}


def main() -> None:
    for scenario, (expected_outcome, expected_runtime_state, expected_fact_state) in EXPECTED.items():
        result = run_simulated_runtime_sample(DATA, scenario)
        audit = result["audit_summary"]
        state = result["stage_runtime_state"]
        trace = result["execution_trace"]["events"]
        if audit["outcome"] != expected_outcome:
            raise AssertionError(f"{scenario} outcome expected {expected_outcome}, got {audit['outcome']}")
        if state["runtime_state"] != expected_runtime_state:
            raise AssertionError(
                f"{scenario} runtime_state expected {expected_runtime_state}, got {state['runtime_state']}"
            )
        if not any("adapter=simulated_pouring_robot" in event.get("payload_summary", "") for event in trace):
            raise AssertionError(f"{scenario} must contain simulated adapter trace payloads")
        facts = {item["fact_id"]: item["state"] for item in audit["fact_summary"]}
        if expected_fact_state and facts.get("cup_has_water") != expected_fact_state:
            raise AssertionError(
                f"{scenario} cup_has_water expected {expected_fact_state}, got {facts.get('cup_has_water')}"
            )

    print("Simulated robot sample validation passed.")
    print("Validated: simulated_success, simulated_no_water, simulated_channel_conflict.")


if __name__ == "__main__":
    main()
