from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
DATA = ROOT / "data"
SCHEMAS = REPO / "schemas"


VERSION_RE = re.compile(r"^1\.\d+\.\d+$")
REQUIRED_CAPABILITIES = {
    "align_container",
    "tilt_container",
    "hold_pose",
    "return_to_level",
    "observe_tilt_angle",
    "observe_flow_rate",
    "observe_liquid_level",
    "request_human_confirmation",
}


JSON_PARSE_ROOTS = [SCHEMAS, DATA]
ALLOWED_TIMELINE_EVENTS = {"stage_started", "state_update", "observation_update", "failure_event"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def require_keys(name: str, payload: dict[str, Any], keys: list[str]) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise AssertionError(f"{name} missing keys: {', '.join(missing)}")


def require_version(name: str, payload: dict[str, Any]) -> None:
    version = payload.get("schema_version")
    if not isinstance(version, str) or not VERSION_RE.match(version):
        raise AssertionError(f"{name} schema_version must match 1.x.x")


def validate_required_json_files() -> None:
    files = [
        SCHEMAS / "mock_timeline.schema.json",
        SCHEMAS / "runtime_event.schema.json",
        SCHEMAS / "stage_runtime_state.schema.json",
        SCHEMAS / "process_instance.schema.json",
        SCHEMAS / "fact_observation_result.schema.json",
        SCHEMAS / "final_establishment_state.schema.json",
        SCHEMAS / "admission_decision.schema.json",
        SCHEMAS / "execution_trace.schema.json",
        SCHEMAS / "audit_summary.schema.json",
        DATA / "pour_water_task_intent.json",
        DATA / "pour_water_process_instance.json",
        DATA / "stage_runtime_state_initial.json",
        DATA / "admission_decision_allowed.json",
        DATA / "mock_timeline_success.json",
        DATA / "mock_timeline_no_flow.json",
        DATA / "mock_timeline_channel_conflict.json",
    ]
    for path in files:
        load_json(path)


def validate_all_json_parse() -> None:
    paths = []
    for root in JSON_PARSE_ROOTS:
        paths.extend(root.rglob("*.json"))
    for path in paths:
        load_json(path)


def validate_process_instance() -> None:
    instance = load_json(DATA / "pour_water_process_instance.json")
    require_version("process_instance", instance)
    require_keys(
        "process_instance",
        instance,
        ["process_instance_id", "process_template_ref", "binding_ref", "task_id", "stages", "bound_parameters"],
    )
    capabilities = {stage["required_capability"] for stage in instance["stages"]}
    missing = capabilities - REQUIRED_CAPABILITIES
    if missing:
        raise AssertionError(f"unknown required capabilities: {sorted(missing)}")
    stage_ids = [stage["stage_id"] for stage in instance["stages"]]
    if stage_ids != ["align", "tilting", "maintain_flow", "return"]:
        raise AssertionError(f"unexpected stage order: {stage_ids}")


def validate_admission() -> None:
    decision = load_json(DATA / "admission_decision_allowed.json")
    require_version("admission_decision", decision)
    require_keys("admission_decision", decision, ["task_id", "allowed", "decision", "checks"])
    if not decision["allowed"] or decision["decision"] != "allowed":
        raise AssertionError("stage zero expected allowed admission decision")
    failed = [check for check in decision["checks"] if not check["passed"]]
    if failed:
        raise AssertionError(f"admission checks failed: {failed}")


def timeline_events(timeline: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for stage_id, stage_events in timeline["stages"].items():
        for index, event in enumerate(stage_events):
            item = dict(event)
            item["stage_id"] = stage_id
            item["index"] = index
            events.append(item)
    return events


def validate_timeline(path: Path) -> None:
    timeline = load_json(path)
    require_version(path.name, timeline)
    require_keys(path.name, timeline, ["$schema", "timeline_id", "process_instance_id", "time_base", "stages"])
    if timeline["$schema"] != "../../../schemas/mock_timeline.schema.json":
        raise AssertionError(f"{path.name} must reference mock_timeline.schema.json")
    if timeline["time_base"] != "stage_started":
        raise AssertionError(f"{path.name} time_base must be stage_started")
    for stage_id, events in timeline["stages"].items():
        times = [event["time_ms"] for event in events]
        if times != sorted(times):
            raise AssertionError(f"{path.name}:{stage_id} events must be sorted by relative time")
        if not events or events[0]["event"] != "stage_started":
            raise AssertionError(f"{path.name}:{stage_id} must start with stage_started")
        for event in events:
            event_type = event.get("event")
            if event_type not in ALLOWED_TIMELINE_EVENTS:
                raise AssertionError(f"{path.name}:{stage_id} unsupported event: {event_type}")
            if event_type == "state_update":
                require_keys(f"{path.name}:{stage_id}:state_update", event, ["variable", "value", "unit", "source"])
            if event_type == "observation_update":
                require_keys(
                    f"{path.name}:{stage_id}:observation_update",
                    event,
                    ["fact_id", "channel_id", "state", "inputs"],
                )
                if event["state"] not in {"established", "not_established", "conflicted", "unknown"}:
                    raise AssertionError(f"{path.name}:{stage_id} invalid observation state: {event['state']}")
            if event_type == "failure_event":
                require_keys(f"{path.name}:{stage_id}:failure_event", event, ["failure_id", "failure_label"])


def validate_timeline_requirements() -> None:
    success = load_json(DATA / "mock_timeline_success.json")
    conflict = load_json(DATA / "mock_timeline_channel_conflict.json")
    no_flow = load_json(DATA / "mock_timeline_no_flow.json")
    for path in [
        DATA / "mock_timeline_success.json",
        DATA / "mock_timeline_no_flow.json",
        DATA / "mock_timeline_channel_conflict.json",
    ]:
        validate_timeline(path)

    success_channels = {
        event["channel_id"]: event["state"]
        for event in timeline_events(success)
        if event["event"] == "observation_update" and event.get("fact_id") == "cup_has_water"
    }
    if success_channels != {"physical_liquid_level": "established", "digital_flow_integral": "established"}:
        raise AssertionError("success timeline must establish cup_has_water in both channels")

    conflict_channels = {
        event["channel_id"]: event["state"]
        for event in timeline_events(conflict)
        if event["event"] == "observation_update" and event.get("fact_id") == "cup_has_water"
    }
    if conflict_channels != {"physical_liquid_level": "established", "digital_flow_integral": "not_established"}:
        raise AssertionError("conflict timeline must contain opposing channel judgments")

    failures = [event for event in timeline_events(no_flow) if event["event"] == "failure_event"]
    if not failures:
        raise AssertionError("no_flow timeline must include failure_event")


def validate_runtime_state_boundary() -> None:
    state = load_json(DATA / "stage_runtime_state_initial.json")
    require_version("stage_runtime_state_initial", state)
    require_keys(
        "stage_runtime_state_initial",
        state,
        ["task_id", "process_instance_id", "runtime_state", "current_stage_id", "variables", "retry_count"],
    )
    if state["runtime_state"] != "admitted" or state["current_stage_id"] != "align":
        raise AssertionError("initial runtime state must start admitted at align")


def main() -> None:
    validate_all_json_parse()
    validate_required_json_files()
    validate_process_instance()
    validate_admission()
    validate_runtime_state_boundary()
    validate_timeline_requirements()
    print("Stage zero validation passed.")
    print("Validated: all JSON parse, schemas, process instance, admission, initial state, success/no_flow/conflict timelines.")


if __name__ == "__main__":
    main()
