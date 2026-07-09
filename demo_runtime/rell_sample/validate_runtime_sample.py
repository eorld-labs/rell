from __future__ import annotations

from pathlib import Path

from runtime_core import run_runtime_sample


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


EXPECTED = {
    "mock_timeline_success.json": ("completed", "completed", "established"),
    "mock_timeline_no_flow.json": ("requires_human_confirmation", "awaiting_human_confirmation", None),
    "mock_timeline_channel_conflict.json": (
        "requires_human_confirmation",
        "awaiting_human_confirmation",
        "conflicted",
    ),
}


def main() -> None:
    for timeline, (expected_outcome, expected_runtime_state, expected_fact_state) in EXPECTED.items():
        result = run_runtime_sample(DATA, timeline)
        audit = result["audit_summary"]
        state = result["stage_runtime_state"]
        if audit["outcome"] != expected_outcome:
            raise AssertionError(f"{timeline} outcome expected {expected_outcome}, got {audit['outcome']}")
        if state["runtime_state"] != expected_runtime_state:
            raise AssertionError(
                f"{timeline} runtime_state expected {expected_runtime_state}, got {state['runtime_state']}"
            )
        facts = {item["fact_id"]: item["state"] for item in audit["fact_summary"]}
        if expected_fact_state and facts.get("cup_has_water") != expected_fact_state:
            raise AssertionError(
                f"{timeline} cup_has_water expected {expected_fact_state}, got {facts.get('cup_has_water')}"
            )
        if expected_outcome == "requires_human_confirmation" and not state.get("pending_human_confirmation"):
            raise AssertionError(f"{timeline} must include pending_human_confirmation")

    print("Runtime sample validation passed.")
    print("Validated: success, no_flow, channel_conflict runtime outcomes.")


if __name__ == "__main__":
    main()
