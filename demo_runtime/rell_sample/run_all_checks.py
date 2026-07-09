from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
API_URL = "http://127.0.0.1:8876"


def run_python(script: str) -> None:
    print(f"[check] {script}")
    subprocess.run([sys.executable, str(ROOT / script)], cwd=REPO, check=True)


def post_json(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        f"{API_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(path: str) -> dict:
    with urlopen(f"{API_URL}{path}", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def get_text(path: str) -> str:
    with urlopen(f"{API_URL}{path}", timeout=5) as response:
        return response.read().decode("utf-8")


def run_http_smoke() -> None:
    print("[check] api_server HTTP smoke")
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "api_server.py")],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.8)
        page = get_text("/")
        health = get_json("/health")
        admit = post_json("/process/admit", {})
        run_result = post_json("/process/run", {"scenario": "simulated_channel_conflict"})
        audit = get_json(f"/audit/{run_result['task_id']}")
        if "RELL 真实世界经验引擎样品" not in page:
            raise AssertionError("demo page did not render")
        if health.get("status") != "ok":
            raise AssertionError(f"health failed: {health}")
        if admit.get("decision") != "allowed":
            raise AssertionError(f"admit failed: {admit}")
        if run_result["audit_summary"]["outcome"] != "requires_human_confirmation":
            raise AssertionError(f"run failed: {run_result}")
        if not any(
            "adapter=simulated_pouring_robot" in event.get("payload_summary", "")
            for event in run_result["execution_trace"]["events"]
        ):
            raise AssertionError("HTTP smoke did not use simulated adapter")
        if audit.get("outcome") != "requires_human_confirmation":
            raise AssertionError(f"audit failed: {audit}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
    print("[ok] api_server HTTP smoke")


def main() -> None:
    run_python("validate_stage_zero.py")
    run_python("validate_runtime_sample.py")
    run_python("validate_simulated_robot_sample.py")
    run_python("validate_api_sample.py")
    run_http_smoke()
    print("All RELL sample checks passed.")


if __name__ == "__main__":
    main()
