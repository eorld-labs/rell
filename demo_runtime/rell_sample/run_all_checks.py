from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
API_URL = "http://127.0.0.1:8876"


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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
    global API_URL
    print("[check] api_server HTTP smoke")
    port = find_free_port()
    API_URL = f"http://127.0.0.1:{port}"
    env = {**os.environ, "RELL_SAMPLE_PORT": str(port)}
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "api_server.py")],
        cwd=REPO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.8)
        page = get_text("/")
        health = get_json("/health")
        cognitive_model = get_json("/space/cognitive-model")
        p017_loop = get_json("/p017/minimal-loop")
        admit = post_json("/process/admit", {})
        migration = post_json("/experience/migrate", {"utterance": "到水源处接一杯水"})
        migration_state = get_json(f"/runtime_world_state/{migration['migration_task_id']}")
        dispatch = post_json(
            "/execution/dispatch",
            {"execution_loop_payload": migration["execution_loop_payload"], "executor_type": "robot_sdk"},
        )
        dispatch_lookup = get_json(f"/execution/dispatch/{dispatch['dispatch_id']}")
        release = post_json(
            "/runtime_world_state/release",
            {"task_id": migration["migration_task_id"], "release_reason": "http_smoke_finished"},
        )
        run_result = post_json("/process/run", {"scenario": "simulated_channel_conflict"})
        readaptation = post_json(
            "/runtime_world_state/readapt",
            {"task_id": run_result["task_id"], "utterance": "到水源处接一杯水"},
        )
        readaptation_lookup = get_json(f"/runtime_readaptation/{readaptation['readaptation_id']}")
        gap_lookup = None
        if readaptation.get("experience_gap_record"):
            gap_lookup = get_json(f"/experience/gap/{readaptation['experience_gap_record']['gap_record_id']}")
        audit = get_json(f"/audit/{run_result['task_id']}")
        if "RELL 真实世界经验引擎样品" not in page:
            raise AssertionError("demo page did not render")
        if "mapCupItem" not in page or "updateLearnedStepScene" not in page:
            raise AssertionError("demo page did not include learned experience animation mapping")
        if "dialogueTeachButton" not in page:
            raise AssertionError("demo page did not include dialogue teaching entry")
        if "p017Button" not in page:
            raise AssertionError("demo page did not include P017 minimal loop entry")
        if health.get("status") != "ok":
            raise AssertionError(f"health failed: {health}")
        if cognitive_model.get("prior_ref") != "semantic_prior_home_a_kitchen_v1":
            raise AssertionError(f"space cognitive model failed: {cognitive_model}")
        if not p017_loop.get("evidence_index") or len(p017_loop.get("evidence_files", {})) != 6:
            raise AssertionError(f"P017 minimal loop endpoint failed: {p017_loop}")
        if admit.get("decision") != "allowed":
            raise AssertionError(f"admit failed: {admit}")
        if migration.get("execution_feasibility", {}).get("result") != "executable":
            raise AssertionError(f"migration failed: {migration}")
        if migration_state.get("release_status") != "not_released":
            raise AssertionError(f"runtime world state query failed: {migration_state}")
        if dispatch.get("outcome") != "fact_established":
            raise AssertionError(f"execution dispatch failed: {dispatch}")
        if dispatch_lookup.get("dispatch_id") != dispatch["dispatch_id"]:
            raise AssertionError(f"execution dispatch lookup failed: {dispatch_lookup}")
        if release.get("release_status") != "released" or not release.get("release_token"):
            raise AssertionError(f"runtime world state release failed: {release}")
        if run_result["audit_summary"]["outcome"] != "requires_human_confirmation":
            raise AssertionError(f"run failed: {run_result}")
        if readaptation.get("execution_feasibility", {}).get("result") != "requires_human_confirmation":
            raise AssertionError(f"runtime readaptation failed: {readaptation}")
        if readaptation_lookup.get("readaptation_id") != readaptation["readaptation_id"]:
            raise AssertionError(f"runtime readaptation lookup failed: {readaptation_lookup}")
        if gap_lookup and gap_lookup.get("gap_record_id") != readaptation["experience_gap_record"]["gap_record_id"]:
            raise AssertionError(f"experience gap lookup failed: {gap_lookup}")
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
    run_python("validate_digital_space.py")
    run_python("validate_adapter_contract.py")
    run_python("validate_runtime_sample.py")
    run_python("validate_simulated_robot_sample.py")
    run_python("validate_api_sample.py")
    run_python("validate_p017_minimal_loop.py")
    run_http_smoke()
    print("All RELL sample checks passed.")


if __name__ == "__main__":
    main()
