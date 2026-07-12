from __future__ import annotations

import json
import os
from pathlib import Path

from embodied_scene import build_visual_concept_pack_catalog, execute_command, start_session
from visual_concept_pipeline import (
    DeterministicImageProvider,
    add_real_world_calibration,
    create_generation_request,
    execute_generation_request,
    get_pipeline_state,
    promote_visual_candidate,
)


OUTPUT = Path(__file__).resolve().parents[1] / "output" / "rell_sample" / "visual_concept_pipeline"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    store = OUTPUT / "pipeline_test_store.json"
    store.unlink(missing_ok=True)
    os.environ["RELL_VISUAL_PIPELINE_STORE"] = str(store)

    runtime_catalog_before = build_visual_concept_pack_catalog()
    session = start_session()
    runtime_before = execute_command(session["session_id"], "你现在看到了什么")

    request = create_generation_request("concept_edible_apple", 6)
    require(request["status"] == "provider_generation_pending", f"generation request failed: {request}")
    require(request["runtime_visible"] is False and request["candidate_only"], f"generation request entered runtime: {request}")
    require(len(request["prompt_specs"]) == 6, f"variant prompts missing: {request}")

    candidate = execute_generation_request(request["request_id"], DeterministicImageProvider())
    require(candidate["status"] == "awaiting_real_world_calibration", f"synthetic samples skipped calibration: {candidate}")
    require(len(candidate["synthetic_samples"]) == 6, f"provider images were not compiled: {candidate}")
    require(all(item["evidence_level"] == "S0_synthetic_prior" for item in candidate["synthetic_samples"]), f"synthetic evidence was over-ranked: {candidate}")
    require(not candidate["runtime_visible"] and not candidate["direct_execution_allowed"], f"synthetic candidate polluted runtime: {candidate}")

    early_promotion = promote_visual_candidate(candidate["candidate_id"])
    require(early_promotion.get("error") == "visual_candidate_promotion_requirements_not_met", f"synthetic-only candidate was promoted: {early_promotion}")
    fake_calibration = add_real_world_calibration(
        candidate["candidate_id"],
        observation_ref="synthetic://not-real",
        source_type="synthetic_image_api",
        matched_features=["compact_round_body"],
        human_confirmed=True,
    )
    require(fake_calibration.get("error") == "calibration_source_is_not_real_world_evidence", f"synthetic evidence masqueraded as calibration: {fake_calibration}")

    calibrated = add_real_world_calibration(
        candidate["candidate_id"],
        observation_ref="robot_camera://observation/apple_crop_1",
        source_type="current_robot_camera_verified_crop",
        matched_features=["compact_round_body", "fruit_surface"],
        human_confirmed=True,
    )
    require(calibrated["status"] == "eligible_for_promotion_review", f"real calibration did not unlock review: {calibrated}")
    promoted = promote_visual_candidate(candidate["candidate_id"])
    require(promoted["status"] == "promoted_visual_adapter", f"calibrated candidate was not promoted: {promoted}")
    require(promoted["load_policy"] == "on_demand" and not promoted["runtime_visible"] and not promoted["direct_execution_allowed"], f"promoted adapter hot-mutated runtime or gained execution authority: {promoted}")
    require(promoted["deployment_status"] == "awaiting_controlled_deployment", f"promoted adapter skipped deployment boundary: {promoted}")

    runtime_catalog_after = build_visual_concept_pack_catalog()
    runtime_after = execute_command(session["session_id"], "你现在看到了什么")
    require(runtime_catalog_before == runtime_catalog_after, "side pipeline mutated factory visual packs")
    require(
        [item["concept_id"] for item in runtime_before["recognized_object_candidates"]]
        == [item["concept_id"] for item in runtime_after["recognized_object_candidates"]],
        "side pipeline changed the active runtime during compilation",
    )
    state = get_pipeline_state()
    require(len(state["requests"]) == 1 and len(state["candidates"]) == 1 and len(state["promoted_adapters"]) == 1, f"pipeline audit state incomplete: {state}")
    (OUTPUT / "pipeline_report.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Visual concept side-pipeline validation passed.")
    print(f"Output: {OUTPUT / 'pipeline_report.json'}")


if __name__ == "__main__":
    main()
