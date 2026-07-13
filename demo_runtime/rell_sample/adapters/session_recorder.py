from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RobotSessionRecorder:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.records: list[dict[str, Any]] = []

    def record(self, record_type: str, payload: dict[str, Any]) -> None:
        self.records.append({
            "record_index": len(self.records) + 1,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "record_type": record_type,
            "payload": deepcopy(payload),
        })

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "session_id": self.session_id,
            "records": deepcopy(self.records),
            "boundary": {
                "recording_is_not_runtime_truth": True,
                "replay_cannot_arm_real_hardware": True,
            },
        }

    def export(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "RobotSessionRecorder":
        payload = json.loads(path.read_text(encoding="utf-8"))
        recorder = cls(str(payload["session_id"]))
        recorder.records = deepcopy(payload.get("records", []))
        return recorder

    def replay_events(self, queue: Any) -> int:
        count = 0
        for record in self.records:
            if record.get("record_type") != "runtime_event":
                continue
            queue.enqueue(deepcopy(record["payload"]))
            count += 1
        return count
