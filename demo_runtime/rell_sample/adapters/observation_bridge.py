from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


FACT_STATES = {"established", "not_established", "unknown", "conflict"}


def bridge_robot_telemetry(
    telemetry: dict[str, Any], *, process_instance_id: str, stage_id: str, sequence_start: int = 0
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    world_revision = telemetry.get("world_revision")
    if not isinstance(world_revision, int) or world_revision < 0:
        errors.append({"reason": "world_revision_missing_or_invalid"})

    sequence = sequence_start
    for state in telemetry.get("states", []):
        missing = [field for field in ("variable", "value", "sensor_id", "frame_id") if field not in state]
        if missing:
            errors.append({"reason": "state_observation_incomplete", "missing": missing})
            continue
        sequence += 1
        events.append(_event(
            sequence,
            process_instance_id,
            stage_id,
            "state_update",
            {**deepcopy(state), "world_revision": world_revision},
        ))

    for observation in telemetry.get("observations", []):
        missing = [
            field
            for field in ("fact_id", "channel_id", "state", "confidence", "sensor_id", "frame_id")
            if field not in observation
        ]
        if missing:
            errors.append({"reason": "fact_observation_incomplete", "missing": missing})
            continue
        if observation["state"] not in FACT_STATES:
            errors.append({"reason": "unsupported_fact_state", "state": observation["state"]})
            continue
        confidence = observation["confidence"]
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            errors.append({"reason": "observation_confidence_out_of_range"})
            continue
        sequence += 1
        events.append(_event(
            sequence,
            process_instance_id,
            stage_id,
            "observation_update",
            {
                **deepcopy(observation),
                "world_revision": world_revision,
                "evidence_boundary": "adapter_observation_requires_runtime_fact_arbitration",
                "runtime_fact_committed": False,
            },
        ))
    return {
        "status": "telemetry_bridged" if not errors else "telemetry_rejected",
        "world_revision": world_revision,
        "events": events if not errors else [],
        "next_sequence": sequence_start + (len(events) if not errors else 0),
        "errors": errors,
        "runtime_fact_committed": False,
    }


def _event(sequence: int, process_instance_id: str, stage_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "event_id": f"real_robot_evt_{sequence:06d}",
        "sequence": sequence,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "process_instance_id": process_instance_id,
        "stage_id": stage_id,
        "event_type": event_type,
        "payload": payload,
    }
