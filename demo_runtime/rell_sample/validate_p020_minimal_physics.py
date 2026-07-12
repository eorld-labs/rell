from __future__ import annotations

import json
from pathlib import Path

from physics_mujoco_adapter import MujocoEmbodiedAdapter
from api_server import dispatch_execution_loop_payload, migrate_experience


OUTPUT = Path(__file__).resolve().parents[1] / "output" / "rell_sample" / "p020_minimal_physics"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    report = {"engine": "mujoco", "scenarios": {}}
    for layout in ("kitchen_a", "corridor_b"):
        result = MujocoEmbodiedAdapter(layout, "mobile_manipulator").execute_fill_task()
        require(result["outcome"] == "fact_established", f"cross-layout task failed: {result}")
        require(len(result["observations"]) == 2, f"P016 dual-channel verification missing: {result}")
        report["scenarios"][f"{layout}_success"] = result

    detour = MujocoEmbodiedAdapter("kitchen_a", "mobile_manipulator", "detourable").execute_fill_task()
    require(detour["outcome"] == "fact_established", f"detour should preserve goal: {detour}")
    require(detour["route_evidence"]["route_kind"] == "local_detour", f"detour evidence missing: {detour}")
    report["scenarios"]["detourable_obstacle"] = detour

    blocked = MujocoEmbodiedAdapter("kitchen_a", "mobile_manipulator", "wall").execute_fill_task()
    require(blocked["outcome"] == "fact_not_established", f"wall must block: {blocked}")
    report["scenarios"]["non_detourable_obstacle"] = blocked

    for executor, expected in (("mobile_base", "grasp_object"), ("fixed_arm", "navigate_to_region")):
        result = MujocoEmbodiedAdapter("corridor_b", executor).execute_fill_task()
        require(result["outcome"] == "capability_gap", f"capability gate failed: {result}")
        require(expected in result["missing_capabilities"], f"wrong capability gap: {result}")
        report["scenarios"][f"{executor}_gap"] = result

    migration = migrate_experience("到水源处接一杯水", space_id="site_b_corridor")
    dispatch = dispatch_execution_loop_payload(
        migration["execution_loop_payload"],
        "mujoco_physics",
        {"physics_executor_type": "mobile_manipulator", "physics_obstacle": "detourable"},
    )
    require(dispatch["outcome"] == "fact_established", f"API physics dispatch failed: {dispatch}")
    require(dispatch["physics_result"]["engine"] == "mujoco", f"physical evidence missing: {dispatch}")
    report["scenarios"]["api_dispatch_success"] = dispatch["physics_result"]

    blocked_migration = migrate_experience("到水源处接一杯水", space_id="site_b_corridor")
    blocked_dispatch = dispatch_execution_loop_payload(
        blocked_migration["execution_loop_payload"],
        "mujoco_physics",
        {"physics_executor_type": "mobile_base"},
    )
    require(blocked_dispatch["outcome"] == "capability_gap", f"API capability gate failed: {blocked_dispatch}")
    facts = blocked_dispatch["runtime_world_state_snapshot"].get("established_facts", [])
    require("cup_contains_water" not in facts, f"physics failure must not commit target fact: {blocked_dispatch}")
    report["scenarios"]["api_dispatch_capability_gap"] = blocked_dispatch["physics_result"]

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "physics_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("P020 minimal MuJoCo physics validation passed.")
    print(f"Output: {OUTPUT / 'physics_report.json'}")


if __name__ == "__main__":
    main()
