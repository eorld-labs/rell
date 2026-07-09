from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from runtime_core import MockRobotAdapter, P016Runtime, SerialEventQueue, read_json, run_runtime_sample


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8876

SCENARIOS = {
    "success": "mock_timeline_success.json",
    "no_flow": "mock_timeline_no_flow.json",
    "channel_conflict": "mock_timeline_channel_conflict.json",
}

AUDIT_STORE: dict[str, dict[str, Any]] = {}
STATE_STORE: dict[str, dict[str, Any]] = {}


def admit_process() -> dict[str, Any]:
    queue = SerialEventQueue()
    process_instance = read_json(DATA / "pour_water_process_instance.json")
    initial_state = read_json(DATA / "stage_runtime_state_initial.json")
    timeline = read_json(DATA / "mock_timeline_success.json")
    adapter = MockRobotAdapter(timeline, queue)
    runtime = P016Runtime(process_instance, initial_state, adapter)
    return runtime.admit()


def run_process(scenario: str = "success") -> dict[str, Any]:
    if scenario not in SCENARIOS:
        return {
            "error": "unknown_scenario",
            "allowed_scenarios": sorted(SCENARIOS),
        }
    result = run_runtime_sample(DATA, SCENARIOS[scenario])
    task_id = result["audit_summary"]["task_id"]
    AUDIT_STORE[task_id] = result["audit_summary"]
    STATE_STORE[task_id] = result["stage_runtime_state"]
    return {
        "task_id": task_id,
        "scenario": scenario,
        "audit_summary": result["audit_summary"],
        "stage_runtime_state": result["stage_runtime_state"],
    }


def get_audit(task_id: str) -> dict[str, Any]:
    audit = AUDIT_STORE.get(task_id)
    if not audit:
        return {"error": "audit_not_found", "task_id": task_id}
    return audit


def get_status(task_id: str) -> dict[str, Any]:
    state = STATE_STORE.get(task_id)
    if not state:
        return {"error": "status_not_found", "task_id": task_id}
    return state


class RellSampleHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/health":
            self._send_json({"status": "ok", "service": "rell_sample"})
            return
        if path.startswith("/audit/"):
            task_id = path.removeprefix("/audit/")
            self._send_json(get_audit(task_id), status=200 if task_id in AUDIT_STORE else 404)
            return
        if path.startswith("/process/status/"):
            task_id = path.removeprefix("/process/status/")
            self._send_json(get_status(task_id), status=200 if task_id in STATE_STORE else 404)
            return
        self._send_json({"error": "not_found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()
        if path == "/process/admit":
            self._send_json(admit_process())
            return
        if path == "/process/run":
            result = run_process(body.get("scenario", "success"))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        self._send_json({"error": "not_found"}, status=404)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return {}
        return json.loads(raw)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    server = HTTPServer((DEFAULT_HOST, DEFAULT_PORT), RellSampleHandler)
    print(f"RELL sample API listening on http://{DEFAULT_HOST}:{DEFAULT_PORT}")
    print("Endpoints: POST /process/admit, POST /process/run, GET /audit/{task_id}")
    server.serve_forever()


if __name__ == "__main__":
    main()
