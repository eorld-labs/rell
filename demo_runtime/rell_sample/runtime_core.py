from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class SerialEventQueue:
    """Single-consumer queue used to keep Runtime state mutations serialized."""

    events: list[dict[str, Any]] = field(default_factory=list)

    def enqueue(self, event: dict[str, Any]) -> None:
        self.events.append(event)

    def pop(self) -> dict[str, Any] | None:
        if not self.events:
            return None
        return self.events.pop(0)

    def clear_state_updates(self) -> None:
        self.events = [event for event in self.events if event["event_type"] != "state_update"]

    def __bool__(self) -> bool:
        return bool(self.events)


class MockRobotAdapter:
    """Timeline-backed adapter that replays stage-relative events into RuntimeEvent form."""

    def __init__(self, timeline: dict[str, Any], queue: SerialEventQueue) -> None:
        self.timeline = timeline
        self.queue = queue
        self.sequence = 0
        self.paused = False
        self.latest_snapshot: dict[str, Any] = {}
        self.confirmation_requests: list[dict[str, Any]] = []

    def report_capabilities(self) -> list[str]:
        return sorted(REQUIRED_CAPABILITIES)

    def execute_stage_action(self, stage: dict[str, Any], context: dict[str, Any], callback=None) -> None:
        if self.paused:
            return
        stage_id = stage["stage_id"]
        stage_events = self.timeline.get("stages", {}).get(stage_id, [])
        for item in stage_events:
            self._emit(stage_id, item, context["process_instance_id"])
        if callback:
            callback({"stage_id": stage_id, "queued_events": len(stage_events)})

    def pause_streams(self, process_instance_id: str) -> None:
        self.paused = True

    def resume_streams(self, process_instance_id: str) -> None:
        self.paused = False

    def get_latest_snapshot(self, process_instance_id: str) -> dict[str, Any]:
        return deepcopy(self.latest_snapshot)

    def stop(self, reason: str, callback=None) -> None:
        result = {"stopped": True, "reason": reason}
        if callback:
            callback(result)

    def request_human_confirmation(self, prompt: str, callback=None) -> None:
        request = {
            "confirmation_id": f"confirm_{len(self.confirmation_requests) + 1}",
            "prompt": prompt,
            "requested_at": now_iso(),
        }
        self.confirmation_requests.append(request)
        if callback:
            callback({"status": "requested", **request})

    def _emit(self, stage_id: str, item: dict[str, Any], process_instance_id: str) -> None:
        self.sequence += 1
        event_type = item["event"]
        payload = {key: value for key, value in item.items() if key not in {"time_ms", "event"}}
        event = {
            "schema_version": "1.0.0",
            "event_id": f"evt_{self.sequence:04d}",
            "sequence": self.sequence,
            "timestamp": now_iso(),
            "process_instance_id": process_instance_id,
            "stage_id": stage_id,
            "event_type": event_type,
            "payload": {
                **payload,
                "relative_time_ms": item["time_ms"],
                "timeline_id": self.timeline["timeline_id"],
            },
        }
        if event_type == "state_update":
            self.latest_snapshot[payload["variable"]] = {
                "value": payload["value"],
                "unit": payload.get("unit"),
                "source": payload.get("source"),
                "updated_at": event["timestamp"],
            }
        self.queue.enqueue(event)


class P016Runtime:
    def __init__(
        self,
        process_instance: dict[str, Any],
        initial_state: dict[str, Any],
        adapter: MockRobotAdapter,
    ) -> None:
        self.process_instance = process_instance
        self.state = deepcopy(initial_state)
        self.adapter = adapter
        self.trace: list[dict[str, Any]] = []
        self.stage_summary: list[dict[str, Any]] = []
        self.fact_channels: dict[str, dict[str, str]] = {}
        self.final_facts: dict[str, str] = {}
        self.last_sequence = -1
        self.outcome = "running"
        self.stop_reason = ""

    def admit(self) -> dict[str, Any]:
        checks = []
        capabilities = set(self.adapter.report_capabilities())
        required_by_instance = {stage["required_capability"] for stage in self.process_instance["stages"]}
        check_items = {
            "template_exists": self.process_instance.get("process_template_ref") == "pour_water",
            "binding_complete": bool(self.process_instance.get("bound_parameters")),
            "adapter_capabilities": required_by_instance.issubset(capabilities),
            "observation_channels": True,
        }
        for check_id, passed in check_items.items():
            checks.append({"check_id": check_id, "passed": passed})
        allowed = all(item["passed"] for item in checks)
        return {
            "schema_version": "1.0.0",
            "task_id": self.process_instance["task_id"],
            "allowed": allowed,
            "decision": "allowed" if allowed else "blocked",
            "checks": checks,
            "missing_items": sorted(required_by_instance - capabilities),
        }

    def run(self) -> dict[str, Any]:
        admission = self.admit()
        if not admission["allowed"]:
            self.outcome = "blocked"
            return self._build_result(admission)

        self.state["runtime_state"] = "running"
        for stage in self.process_instance["stages"]:
            if self.outcome != "running":
                break
            self._run_stage(stage)

        if self.outcome == "running":
            self.outcome = "completed"
            self.state["runtime_state"] = "completed"

        return self._build_result(admission)

    def _run_stage(self, stage: dict[str, Any]) -> None:
        stage_id = stage["stage_id"]
        self.state["current_stage_id"] = stage_id
        self.state["runtime_state"] = "running"
        stage_complete = False
        before_stage = deepcopy(self.state)
        self.adapter.execute_stage_action(stage, {"process_instance_id": self.process_instance["process_instance_id"]})

        while self.adapter.queue:
            event = self.adapter.queue.pop()
            if event is None:
                break
            if event["sequence"] <= self.last_sequence:
                continue
            self.last_sequence = event["sequence"]
            before = self.state["runtime_state"]
            event_type = event["event_type"]
            payload = event["payload"]

            if event_type == "state_update":
                self._apply_state_update(payload)
                stage_complete = self._transition_condition_met(stage_id)
            elif event_type == "observation_update":
                self._apply_observation_update(payload)
                final_state = self._final_fact_state(payload["fact_id"])
                if final_state == "conflicted":
                    self.stage_summary.append(
                        {
                            "stage_id": stage_id,
                            "result": "requires_human_confirmation",
                            "notes": f"{payload['fact_id']} verification conflicted",
                        }
                    )
                    self._enter_human_confirmation(payload["fact_id"], "双通道验真冲突")
                elif stage_id == "maintain_flow" and payload["fact_id"] == "cup_has_water":
                    stage_complete = final_state == "established"
            elif event_type == "failure_event":
                self._handle_failure(stage_id, payload)
            elif event_type == "stage_started":
                self.state["runtime_state"] = "running"

            self._record_trace(event, before, self.state["runtime_state"])
            if self.outcome != "running":
                break
            if stage_complete:
                break

        if self.outcome != "running":
            return
        if stage_complete:
            self.stage_summary.append(
                {
                    "stage_id": stage_id,
                    "result": "completed",
                    "notes": f"{stage.get('transition_condition_ref')} satisfied",
                }
            )
            return

        self.outcome = "failed"
        self.state["runtime_state"] = "failed"
        self.stop_reason = f"stage_not_completed:{stage_id}"
        self.stage_summary.append(
            {
                "stage_id": stage_id,
                "result": "failed",
                "notes": "timeline ended before transition condition or fact verification completed",
            }
        )
        self._record_trace(
            {
                "event_id": f"evt_runtime_{stage_id}_failed",
                "sequence": self.last_sequence + 1,
                "event_type": "runtime_failure",
            },
            before_stage["runtime_state"],
            self.state["runtime_state"],
        )

    def _apply_state_update(self, payload: dict[str, Any]) -> None:
        variable = payload["variable"]
        self.state.setdefault("variables", {})[variable] = {
            "value": payload["value"],
            "unit": payload.get("unit"),
            "source": payload.get("source"),
            "updated_at": now_iso(),
        }
        self.state["updated_at"] = now_iso()

    def _apply_observation_update(self, payload: dict[str, Any]) -> None:
        fact_id = payload["fact_id"]
        channel_id = payload["channel_id"]
        self.fact_channels.setdefault(fact_id, {})[channel_id] = payload["state"]
        final_state = self._final_fact_state(fact_id)
        self.final_facts[fact_id] = final_state
        self.state.setdefault("latest_fact_state", {})[fact_id] = final_state
        self.state["runtime_state"] = "awaiting_fact_verification" if final_state == "unknown" else "running"
        self.state["updated_at"] = now_iso()

    def _final_fact_state(self, fact_id: str) -> str:
        channels = self.fact_channels.get(fact_id, {})
        if not channels:
            return "unknown"
        states = set(channels.values())
        if "conflicted" in states or ("established" in states and "not_established" in states):
            return "conflicted"
        if len(channels) >= 2 and states == {"established"}:
            return "established"
        if "not_established" in states:
            return "not_established"
        return "unknown"

    def _transition_condition_met(self, stage_id: str) -> bool:
        params = self.process_instance["bound_parameters"]
        variables = self.state.get("variables", {})

        def value(name: str) -> Any:
            return variables.get(name, {}).get("value")

        if stage_id == "align":
            distance = value("spout_to_cup_distance")
            return distance is not None and distance <= params.get("DIST_MAX", 0.5)
        if stage_id == "tilting":
            flow = value("water_flow_rate")
            return flow is not None and flow >= params["FLOW_MIN"]
        if stage_id == "maintain_flow":
            return self.final_facts.get("cup_has_water") == "established"
        if stage_id == "return":
            angle = value("tilt_angle")
            flow = value("water_flow_rate")
            return (
                angle is not None
                and flow is not None
                and angle <= params["LEVEL_THRESHOLD"]
                and flow <= params["ZERO_FLOW"]
            )
        return False

    def _handle_failure(self, stage_id: str, payload: dict[str, Any]) -> None:
        retry_count = self.state.setdefault("retry_count", {})
        retry_count[stage_id] = retry_count.get(stage_id, 0) + 1
        max_attempts = self.process_instance.get("recovery_policy", {}).get("max_recovery_attempts", 0)
        if retry_count[stage_id] > max_attempts:
            reason = "恢复次数超过上限"
        else:
            reason = f"触发预设失败标签：{payload.get('failure_label', payload.get('failure_id'))}"
        self._enter_human_confirmation(payload.get("failure_id", stage_id), reason)
        self.stage_summary.append({"stage_id": stage_id, "result": "requires_human_confirmation", "notes": reason})

    def _enter_human_confirmation(self, ref: str, reason: str) -> None:
        self.outcome = "requires_human_confirmation"
        self.stop_reason = reason
        self.state["runtime_state"] = "awaiting_human_confirmation"
        self.state["pending_human_confirmation"] = {
            "confirmation_id": f"confirm_{ref}",
            "prompt": reason,
            "requested_at": now_iso(),
        }
        self.adapter.pause_streams(self.process_instance["process_instance_id"])
        self.adapter.queue.clear_state_updates()
        self.adapter.request_human_confirmation(reason)
        self.state["updated_at"] = now_iso()

    def _record_trace(self, event: dict[str, Any], before_state: str, after_state: str) -> None:
        self.trace.append(
            {
                "event_ref": event["event_id"],
                "consumed_sequence": event["sequence"],
                "before_state": before_state,
                "after_state": after_state,
                "trigger_reason": event["event_type"],
                "recorded_at": now_iso(),
            }
        )

    def _build_result(self, admission: dict[str, Any]) -> dict[str, Any]:
        process_instance_id = self.process_instance["process_instance_id"]
        task_id = self.process_instance["task_id"]
        return {
            "admission_decision": admission,
            "stage_runtime_state": self.state,
            "execution_trace": {
                "schema_version": "1.0.0",
                "task_id": task_id,
                "process_instance_id": process_instance_id,
                "events": self.trace,
            },
            "audit_summary": {
                "schema_version": "1.0.0",
                "task_id": task_id,
                "process_instance_id": process_instance_id,
                "outcome": self.outcome,
                "stage_summary": self.stage_summary,
                "fact_summary": [
                    {
                        "fact_id": fact_id,
                        "state": state,
                        "channel_notes": json.dumps(self.fact_channels.get(fact_id, {}), ensure_ascii=False),
                    }
                    for fact_id, state in sorted(self.final_facts.items())
                ],
                "skill_package_draft_ref": "manual_review_required",
                "stop_reason": self.stop_reason,
            },
        }


def run_runtime_sample(data_dir: Path, timeline_name: str) -> dict[str, Any]:
    queue = SerialEventQueue()
    process_instance = read_json(data_dir / "pour_water_process_instance.json")
    initial_state = read_json(data_dir / "stage_runtime_state_initial.json")
    timeline = read_json(data_dir / timeline_name)
    adapter = MockRobotAdapter(timeline, queue)
    runtime = P016Runtime(process_instance, initial_state, adapter)
    return runtime.run()
