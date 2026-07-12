from __future__ import annotations

import os
from pathlib import Path

from embodied_scene import (
    begin_learned_replay,
    begin_persisted_experience_replay,
    begin_teaching_control,
    evaluate_learned_replay,
    finish_embodied_teaching,
    load_scene,
    start_embodied_teaching,
    start_session,
    step_motion_command,
)


OUTPUT = Path(__file__).resolve().parents[1] / "output" / "rell_sample" / "cross_scene_generalization"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def drain(started: dict) -> dict:
    if started.get("immediate_result"):
        return started["immediate_result"]
    job_id = started.get("job_id")
    require(job_id, f"expected motion job: {started}")
    while True:
        step = step_motion_command(job_id)
        if step.get("status") == "motion_completed":
            return step.get("result") or step
        require(step.get("status") == "frame_verified_and_committed", f"motion failed: {step}")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    store = OUTPUT / "trusted_experiences.json"
    store.unlink(missing_ok=True)
    os.environ["RELL_EMBODIED_EXPERIENCE_STORE"] = str(store)

    scene_a = load_scene("home_semantic_3d_a")
    scene_b = load_scene("home_semantic_3d_b")
    require(scene_a["scene_id"] != scene_b["scene_id"], "training and target scenes must be distinct")
    require(scene_a["objects"] != scene_b["objects"], "target scene must change object layout and appearance")
    apple_a = next(item for item in scene_a["objects"] if item["kind"] == "graspable_object")
    apple_b = next(item for item in scene_b["objects"] if item["kind"] == "graspable_object")
    require(apple_a["position"] != apple_b["position"] and apple_a["color"] != apple_b["color"], "apple binding did not vary across scenes")

    teaching_session = start_session(scene_id="home_semantic_3d_a")
    session_id = teaching_session["session_id"]
    started = start_embodied_teaching(session_id, "拿苹果")
    require(started["status"] == "teaching_control_granted", f"human teaching did not start: {started}")
    # Demonstrate the causal minimum: orient, navigate until reachable, then grasp.
    for control in ("turn_left", "forward", "forward", "forward", "forward", "forward", "forward", "forward", "turn_left", "forward", "forward"):
        result = drain(begin_teaching_control(session_id, control))
        require(result.get("status") in {"fact_established", "stopped_by_physical_obstacle"}, f"teaching control was not physically adjudicated: {result}")
    grasp = begin_teaching_control(session_id, "grasp")
    require(grasp.get("immediate_result", grasp).get("status") == "fact_established", f"human demonstration did not verify grasp: {grasp}")
    compiled = finish_embodied_teaching(session_id)
    require(compiled["status"] == "demonstration_compiled", f"teaching did not compile: {compiled}")
    experience = compiled["experience"]
    require(experience["invariant_contract"]["storage_policy"] == "store_invariants_not_concrete_teleoperation_parameters", "experience storage policy regressed")
    require("absolute_world_coordinates" in experience["invariant_contract"]["forbidden_storage"], "experience retained coordinate-like data")

    replay_started = begin_learned_replay(session_id)
    replay_result = drain(replay_started)
    require(replay_result["status"] == "fact_established", f"same-scene autonomous replay failed: {replay_result}")
    accepted = evaluate_learned_replay(session_id, True)
    require(accepted["status"] == "experience_learned", f"human acceptance did not promote experience: {accepted}")
    experience_id = accepted["persisted_experience"]["experience_id"]

    target_session = start_session(scene_id="home_semantic_3d_b")
    target_started = begin_persisted_experience_replay(target_session["session_id"], experience_id)
    require(target_started["status"] == "learned_replay_started", f"experience did not rebind in unfamiliar scene: {target_started}")
    target_entity = target_started["cold_start_binding"]["current_entity_ref"]
    require(target_entity == apple_b["entity_id"], f"target concept did not bind current scene apple: {target_started}")
    require(target_started["cold_start_binding"]["trajectory_reused"] is False, "replay reused demonstration trajectory")
    target_result = drain(target_started)
    require(target_result["status"] == "fact_established", f"cross-scene replay did not verify target grasp: {target_result}")
    require(target_result["verification_evidence"]["target_entity_ref"] == apple_b["entity_id"], f"cross-scene terminal fact bound wrong entity: {target_result}")

    report = {
        "training_scene": scene_a["scene_id"],
        "target_scene": scene_b["scene_id"],
        "experience_id": experience_id,
        "training_target": apple_a["entity_id"],
        "target_binding": target_entity,
        "trajectory_reused": target_started["cold_start_binding"]["trajectory_reused"],
        "invariant_contract": experience["invariant_contract"],
        "target_terminal_fact": target_result["terminal_fact"],
    }
    (OUTPUT / "cross_scene_report.json").write_text(__import__("json").dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    store.unlink(missing_ok=True)
    os.environ.pop("RELL_EMBODIED_EXPERIENCE_STORE", None)
    print("Cross-scene generalization validation passed.")
    print(f"Output: {OUTPUT / 'cross_scene_report.json'}")


if __name__ == "__main__":
    main()
