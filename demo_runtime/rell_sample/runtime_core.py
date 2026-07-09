from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adapters.adapter_contract import (
    REQUIRED_CAPABILITIES,
    RellRobotAdapter,
    build_executor_profile,
    clone_executor_profile,
)


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
        self.executor_profile = build_executor_profile(
            "mock_pouring_executor",
            "simulated_robot",
            "fixed_mock",
        )

    def report_capabilities(self) -> list[str]:
        return sorted(REQUIRED_CAPABILITIES)

    def report_executor_profile(self) -> dict[str, Any]:
        return clone_executor_profile(self.executor_profile)

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


class SimulatedPouringRobotAdapter:
    """Low-dimensional robot adapter that derives sensor events from action state."""

    def __init__(self, scenario: str, queue: SerialEventQueue) -> None:
        self.scenario = scenario
        self.queue = queue
        self.sequence = 0
        self.paused = False
        self.confirmation_requests: list[dict[str, Any]] = []
        self.latest_snapshot: dict[str, Any] = {}
        self.robot_state = {
            "spout_to_cup_distance": 8.0,
            "tilt_angle": 0.0,
            "water_flow_rate": 0.0,
            "liquid_level_ml": 0.0,
            "water_surface_gap": 3.0,
            "water_available_ml": 180.0 if scenario != "simulated_no_water" else 0.0,
            "flow_integral_ml": 0.0,
        }
        self.executor_profile = build_executor_profile(
            "simulated_pouring_robot",
            "simulated_robot",
            "wheeled_arm",
        )

    def report_capabilities(self) -> list[str]:
        return sorted(REQUIRED_CAPABILITIES)

    def report_executor_profile(self) -> dict[str, Any]:
        return clone_executor_profile(self.executor_profile)

    def execute_stage_action(self, stage: dict[str, Any], context: dict[str, Any], callback=None) -> None:
        if self.paused:
            return
        stage_id = stage["stage_id"]
        process_instance_id = context["process_instance_id"]
        self._emit(stage_id, "stage_started", process_instance_id, {}, 0)
        if stage_id == "align":
            self._simulate_align(stage_id, process_instance_id)
        elif stage_id == "tilting":
            self._simulate_tilting(stage_id, process_instance_id)
        elif stage_id == "maintain_flow":
            self._simulate_maintain_flow(stage_id, process_instance_id)
        elif stage_id == "return":
            self._simulate_return(stage_id, process_instance_id)
        if callback:
            callback({"stage_id": stage_id, "adapter": "simulated_pouring_robot"})

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

    def _simulate_align(self, stage_id: str, process_instance_id: str) -> None:
        for time_ms, distance in [(250, 5.2), (500, 2.1), (750, 0.4)]:
            self.robot_state["spout_to_cup_distance"] = distance
            self._emit_state(stage_id, process_instance_id, time_ms, "spout_to_cup_distance", distance, "cm", "sim_depth_camera")

    def _simulate_tilting(self, stage_id: str, process_instance_id: str) -> None:
        for time_ms, angle in [(250, 7.0), (500, 14.0), (750, 22.0)]:
            self.robot_state["tilt_angle"] = angle
            self._emit_state(stage_id, process_instance_id, time_ms, "tilt_angle", angle, "degree", "sim_joint_encoder")
        if self.robot_state["water_available_ml"] <= 0:
            self.robot_state["water_flow_rate"] = 0.0
            self._emit_state(stage_id, process_instance_id, 1000, "water_flow_rate", 0.0, "ml_per_second", "sim_flow_model")
            self._emit(
                stage_id,
                "failure_event",
                process_instance_id,
                {"failure_id": "simulated_no_water", "failure_label": "no_flow"},
                1100,
            )
            return
        self.robot_state["water_flow_rate"] = 3.6
        self._emit_state(stage_id, process_instance_id, 1000, "water_flow_rate", 3.6, "ml_per_second", "sim_flow_model")

    def _simulate_maintain_flow(self, stage_id: str, process_instance_id: str) -> None:
        for time_ms, added_ml in [(300, 34.0), (600, 38.0), (900, 42.0)]:
            self.robot_state["liquid_level_ml"] += added_ml
            self.robot_state["flow_integral_ml"] += added_ml
            self.robot_state["water_available_ml"] = max(0.0, self.robot_state["water_available_ml"] - added_ml)
            gap = max(0.35, 3.0 - self.robot_state["liquid_level_ml"] / 42.0)
            self.robot_state["water_surface_gap"] = round(gap, 2)
            self._emit_state(
                stage_id,
                process_instance_id,
                time_ms,
                "water_surface_gap",
                self.robot_state["water_surface_gap"],
                "cm",
                "sim_depth_camera",
            )
        physical_state = "established" if self.robot_state["water_surface_gap"] <= 0.5 else "not_established"
        digital_state = "established" if self.robot_state["flow_integral_ml"] >= 80.0 else "not_established"
        if self.scenario == "simulated_channel_conflict":
            digital_state = "not_established"
        self._emit_observation(
            stage_id,
            process_instance_id,
            1000,
            "cup_has_water",
            "physical_liquid_level",
            physical_state,
            {"water_surface_gap": self.robot_state["water_surface_gap"]},
        )
        self._emit_observation(
            stage_id,
            process_instance_id,
            1100,
            "cup_has_water",
            "digital_flow_integral",
            digital_state,
            {"flow_integral_ml": round(self.robot_state["flow_integral_ml"], 2), "tilt_angle": self.robot_state["tilt_angle"]},
        )

    def _simulate_return(self, stage_id: str, process_instance_id: str) -> None:
        for time_ms, angle in [(250, 12.0), (500, 5.0), (750, 0.5)]:
            self.robot_state["tilt_angle"] = angle
            self._emit_state(stage_id, process_instance_id, time_ms, "tilt_angle", angle, "degree", "sim_joint_encoder")
        self.robot_state["water_flow_rate"] = 0.0
        self._emit_state(stage_id, process_instance_id, 900, "water_flow_rate", 0.0, "ml_per_second", "sim_flow_model")

    def _emit_state(
        self,
        stage_id: str,
        process_instance_id: str,
        time_ms: int,
        variable: str,
        value: Any,
        unit: str,
        source: str,
    ) -> None:
        self._emit(
            stage_id,
            "state_update",
            process_instance_id,
            {"variable": variable, "value": value, "unit": unit, "source": source},
            time_ms,
        )

    def _emit_observation(
        self,
        stage_id: str,
        process_instance_id: str,
        time_ms: int,
        fact_id: str,
        channel_id: str,
        state: str,
        inputs: dict[str, Any],
    ) -> None:
        self._emit(
            stage_id,
            "observation_update",
            process_instance_id,
            {"fact_id": fact_id, "channel_id": channel_id, "state": state, "inputs": inputs},
            time_ms,
        )

    def _emit(
        self,
        stage_id: str,
        event_type: str,
        process_instance_id: str,
        payload: dict[str, Any],
        relative_time_ms: int,
    ) -> None:
        self.sequence += 1
        event = {
            "schema_version": "1.0.0",
            "event_id": f"sim_evt_{self.sequence:04d}",
            "sequence": self.sequence,
            "timestamp": now_iso(),
            "process_instance_id": process_instance_id,
            "stage_id": stage_id,
            "event_type": event_type,
            "payload": {
                **payload,
                "relative_time_ms": relative_time_ms,
                "adapter": "simulated_pouring_robot",
                "scenario": self.scenario,
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
        adapter: RellRobotAdapter,
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
        executor_profile = self.adapter.report_executor_profile()
        required_by_instance = {stage["required_capability"] for stage in self.process_instance["stages"]}
        check_items = {
            "template_exists": self.process_instance.get("process_template_ref") == "pour_water",
            "binding_complete": bool(self.process_instance.get("bound_parameters")),
            "adapter_capabilities": required_by_instance.issubset(capabilities),
            "executor_profile_available": bool(executor_profile.get("executor_id")),
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
            "executor_profile": executor_profile,
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
        payload = event.get("payload", {})
        self.trace.append(
            {
                "event_ref": event["event_id"],
                "consumed_sequence": event["sequence"],
                "before_state": before_state,
                "after_state": after_state,
                "trigger_reason": event["event_type"],
                "payload_summary": summarize_payload(payload),
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


def run_simulated_runtime_sample(data_dir: Path, scenario: str) -> dict[str, Any]:
    queue = SerialEventQueue()
    process_instance = read_json(data_dir / "pour_water_process_instance.json")
    initial_state = read_json(data_dir / "stage_runtime_state_initial.json")
    adapter = SimulatedPouringRobotAdapter(scenario, queue)
    runtime = P016Runtime(process_instance, initial_state, adapter)
    return runtime.run()


def summarize_payload(payload: dict[str, Any]) -> str:
    adapter = payload.get("adapter", "")
    suffix = f" adapter={adapter}" if adapter else ""
    if "variable" in payload:
        return f"{payload['variable']}={payload.get('value')} {payload.get('unit', '')} source={payload.get('source', '')}{suffix}".strip()
    if "fact_id" in payload:
        return f"{payload['fact_id']}:{payload.get('channel_id')}={payload.get('state')}{suffix}"
    if "failure_id" in payload:
        return f"{payload['failure_id']}:{payload.get('failure_label')}{suffix}"
    return suffix.strip()
