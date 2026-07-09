from __future__ import annotations

import json
from pathlib import Path

from runtime_core import run_runtime_sample, write_json


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = ROOT.parent / "output" / "rell_sample"

SCENARIOS = {
    "success": "mock_timeline_success.json",
    "no_flow": "mock_timeline_no_flow.json",
    "channel_conflict": "mock_timeline_channel_conflict.json",
}


def main() -> None:
    summaries = {}
    for scenario, timeline in SCENARIOS.items():
        result = run_runtime_sample(DATA, timeline)
        scenario_dir = OUTPUT / scenario
        write_json(scenario_dir / "admission_decision.json", result["admission_decision"])
        write_json(scenario_dir / "stage_runtime_state.json", result["stage_runtime_state"])
        write_json(scenario_dir / "execution_trace.json", result["execution_trace"])
        write_json(scenario_dir / "audit_summary.json", result["audit_summary"])
        summaries[scenario] = {
            "outcome": result["audit_summary"]["outcome"],
            "runtime_state": result["stage_runtime_state"]["runtime_state"],
            "trace_events": len(result["execution_trace"]["events"]),
            "facts": result["audit_summary"]["fact_summary"],
        }

    write_json(OUTPUT / "summary.json", summaries)
    print("RELL runtime sample completed.")
    print(f"Output: {OUTPUT}")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
