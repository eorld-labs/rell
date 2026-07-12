from __future__ import annotations

import json
import os
from pathlib import Path

from embodied_scene import build_visual_concept_pack_catalog, execute_command, start_session
from visual_concept_pipeline import (
    DeterministicImageProvider,
    add_real_world_calibration,
    compile_concept_kernel_candidate,
    create_production_batch,
    create_generation_request,
    execute_production_batch,
    execute_generation_request,
    get_pipeline_state,
    promote_visual_candidate,
    promote_concept_kernel_candidate,
    release_kernel_candidate_generation,
    review_concept_kernel_candidate,
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

    batch = create_production_batch(sample_count_per_concept=4)
    require(batch["item_count"] == 10, f"daily-life manifest size changed unexpectedly: {batch}")
    require(batch["generation_request_count"] == 5 and batch["concept_gap_count"] == 5, f"known concepts and concept gaps were conflated: {batch}")
    state_before_batch_execution = get_pipeline_state()
    cup_request = next(item for item in state_before_batch_execution["requests"] if item.get("subject_profile", {}).get("item_id") == "cup")
    require(cup_request["subject_profile"]["concrete_label"] == "杯子" and cup_request["subject_profile"]["parent_functional_concept"] == "可盛装容器", f"concrete item and parent concept were conflated: {cup_request}")
    require("杯子" in cup_request["prompt_specs"][0]["prompt"], f"batch provider prompt used only abstract concept name: {cup_request}")
    gaps = state_before_batch_execution["concept_gap_candidates"]
    require({item["display_name"] for item in gaps} == {"碗", "瓶子", "门", "垃圾桶", "冰箱"}, f"concept gap queue incorrect: {gaps}")
    require(all(not item["image_generation_allowed"] for item in gaps), f"images were generated before concept kernels existed: {gaps}")

    bowl_gap = next(item for item in gaps if item["display_name"] == "碗")
    incomplete_kernel = compile_concept_kernel_candidate(
        bowl_gap["gap_id"],
        {"concept_id": "concept_fillable_bowl"},
        source_type="external_model_candidate",
    )
    require(incomplete_kernel.get("error") == "concept_kernel_candidate_contract_invalid", f"incomplete model output became a kernel candidate: {incomplete_kernel}")
    wrong_types = compile_concept_kernel_candidate(
        bowl_gap["gap_id"],
        {
            "concept_id": "concept_wrong_types",
            "display_name": "错误类型候选",
            "aliases": ["候选"],
            "compatible_kinds": ["container"],
            "functional_role_contract": {"roles": ["container"], "affordances": ["receive_material"]},
            "physical_properties_and_boundaries": {"properties": {"shape": "round"}, "safety_boundaries": {"load": "unknown"}},
            "perceptual_invariants": ["open_top"],
            "variable_features": [],
            "expected_relations": [],
            "runtime_verification_policy": {"candidate_checks": ["shape_observed"], "functional_checks": ["capacity_verified"]},
        },
        source_type="external_model_candidate",
    )
    require(wrong_types.get("error") == "concept_kernel_candidate_contract_invalid", f"object-valued model fields bypassed compiler: {wrong_types}")
    quantified_claim = compile_concept_kernel_candidate(
        bowl_gap["gap_id"],
        {
            "concept_id": "concept_quantified_visual_claim",
            "display_name": "量化视觉候选",
            "aliases": ["候选"],
            "compatible_kinds": ["furniture"],
            "functional_role_contract": {"roles": ["support"], "affordances": ["support_load_candidate"]},
            "physical_properties_and_boundaries": {"properties": ["ground_supported"], "safety_boundaries": ["load_capacity_100kg_requires_verification"]},
            "perceptual_invariants": ["support_surface"],
            "variable_features": [],
            "expected_relations": [],
            "runtime_verification_policy": {"candidate_checks": ["structure_observed"], "functional_checks": ["load_capacity_verified"]},
        },
        source_type="external_model_candidate",
    )
    require(quantified_claim.get("error") == "concept_kernel_candidate_contract_invalid", f"quantified visual claim bypassed compiler: {quantified_claim}")
    bowl_kernel = compile_concept_kernel_candidate(
        bowl_gap["gap_id"],
        {
            "concept_id": "concept_fillable_bowl",
            "display_name": "可盛装碗状容器",
            "aliases": ["碗"],
            "compatible_kinds": ["graspable_container"],
            "functional_role_contract": {"roles": ["container", "supportable_object"], "affordances": ["receive_material", "support_contents"]},
            "physical_properties_and_boundaries": {"properties": ["bounded_inner_volume", "open_top"], "safety_boundaries": ["contents_temperature_within_body_limit", "grasp_force_below_damage_limit"]},
            "perceptual_invariants": ["open_top", "bounded_inner_volume", "stable_base"],
            "variable_features": ["color", "material", "size"],
            "expected_relations": ["on_top_of_support"],
            "runtime_verification_policy": {"candidate_checks": ["shape_invariants_observed"], "functional_checks": ["container_role_physically_verified_before_use"]},
        },
        source_type="external_model_candidate",
    )
    require(bowl_kernel["status"] == "awaiting_human_kernel_review" and not bowl_kernel["image_generation_allowed"], f"external model self-approved a concept: {bowl_kernel}")
    blocked_release = release_kernel_candidate_generation(bowl_kernel["kernel_candidate_id"], sample_count=4)
    require(blocked_release.get("error") == "concept_kernel_human_review_required", f"unreviewed kernel released image generation: {blocked_release}")
    reviewed_kernel = review_concept_kernel_candidate(
        bowl_kernel["kernel_candidate_id"],
        approved=True,
        reviewer_ref="validation_human_reviewer",
        functional_role_confirmed=True,
        physical_boundaries_confirmed=True,
    )
    require(reviewed_kernel["image_generation_allowed"] and not reviewed_kernel["runtime_visible"], f"kernel review crossed runtime boundary: {reviewed_kernel}")
    bowl_request = release_kernel_candidate_generation(bowl_kernel["kernel_candidate_id"], sample_count=4)
    require(bowl_request["status"] == "provider_generation_pending" and bowl_request["subject_profile"]["kernel_candidate_id"] == bowl_kernel["kernel_candidate_id"], f"reviewed kernel did not release an auditable image request: {bowl_request}")
    require(not bowl_request["runtime_visible"] and bowl_request["candidate_only"], f"reviewed kernel became runtime truth: {bowl_request}")
    bowl_visual_candidate = execute_generation_request(bowl_request["request_id"], DeterministicImageProvider())
    calibrated_bowl = add_real_world_calibration(
        bowl_visual_candidate["candidate_id"],
        observation_ref="user_image://verified/bowl_1",
        source_type="user_provided_real_image",
        matched_features=["open_top", "bounded_inner_volume", "stable_base"],
        human_confirmed=True,
    )
    require(calibrated_bowl["status"] == "eligible_for_promotion_review", f"real bowl evidence did not calibrate visual candidate: {calibrated_bowl}")
    blocked_visual_promotion = promote_visual_candidate(bowl_visual_candidate["candidate_id"])
    require(blocked_visual_promotion.get("error") == "object_concept_kernel_promotion_required", f"visual adapter outran its object concept kernel: {blocked_visual_promotion}")
    promoted_kernel = promote_concept_kernel_candidate(bowl_kernel["kernel_candidate_id"])
    require(promoted_kernel["status"] == "promoted_object_concept_kernel" and not promoted_kernel["runtime_visible"], f"object kernel promotion crossed deployment boundary: {promoted_kernel}")
    promoted_bowl_visual = promote_visual_candidate(bowl_visual_candidate["candidate_id"])
    require(promoted_bowl_visual["status"] == "promoted_visual_adapter" and not promoted_bowl_visual["runtime_visible"], f"visual adapter did not follow promoted object kernel: {promoted_bowl_visual}")

    class OneRequestFailureProvider(DeterministicImageProvider):
        provider_id = "one_request_failure_test_provider"

        def generate(self, request: dict) -> list[dict]:
            if request["concept_id"] == "concept_support_surface":
                raise RuntimeError("simulated_provider_failure")
            return super().generate(request)

    completed_batch = execute_production_batch(batch["batch_id"], OneRequestFailureProvider())
    require(completed_batch["status"] == "completed_with_failures", f"partial failure was hidden: {completed_batch}")
    require(sum(item["status"] == "provider_failed" for item in completed_batch["results"]) == 1, f"failure isolation count incorrect: {completed_batch}")
    require(sum(item["status"] == "candidate_compiled" for item in completed_batch["results"]) == 4, f"one failure aborted successful concepts: {completed_batch}")
    require(completed_batch["runtime_visible"] is False, f"batch became runtime-visible: {completed_batch}")
    final_state = get_pipeline_state()
    (OUTPUT / "pipeline_report.json").write_text(json.dumps(final_state, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Visual concept side-pipeline validation passed.")
    print(f"Output: {OUTPUT / 'pipeline_report.json'}")


if __name__ == "__main__":
    main()
