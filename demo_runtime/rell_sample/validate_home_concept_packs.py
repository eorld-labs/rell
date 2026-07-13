from __future__ import annotations

import json
from pathlib import Path

from concept_core.concept_pack_registry import load_concept_pack_registry, validate_concept_pack_registry
from concept_core.visual_concept_packs import load_visual_concept_packs, match_visual_concept_candidates


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    registry = load_concept_pack_registry(active_domains=("home",))
    report = validate_concept_pack_registry(registry)
    require(report["concept_count"] == 9, f"home concept count changed unexpectedly: {report}")
    require(report["loaded_pack_count"] == 8, f"core plus seven home category packs were not loaded: {report}")
    require(registry["active_domains"] == ["home"], f"home domain was not explicit: {registry}")
    require(registry["storage_boundary"]["concept_kernel_is_not_scene_instance"], f"scene instances entered concept storage: {registry}")
    require(registry["storage_boundary"]["concept_kernel_is_not_action_experience"], f"experiences entered concept storage: {registry}")
    require(registry["storage_boundary"]["functional_claim_requires_runtime_verification"], f"functional claims bypassed verification: {registry}")

    concepts = {item["concept_id"]: item for item in registry["concepts"]}
    legacy_ids = {
        "concept_fillable_container", "concept_support_surface", "concept_edible_apple",
        "concept_water_source_asset", "concept_movable_stool_obstacle", "concept_sofa",
    }
    trial_ids = {"concept_openable_door", "concept_refrigerator", "concept_portable_bottle"}
    require(legacy_ids | trial_ids == set(concepts), f"migration lost or invented concepts: {set(concepts)}")
    require(concepts["concept_fillable_container"]["compatible_kinds"] == ["graspable_container"], "cup grounding contract changed")
    require("support_object" in concepts["concept_support_surface"]["functional_affordances"], "support affordance changed")
    require("blocks_motion" in concepts["concept_movable_stool_obstacle"]["functional_affordances"], "stool obstacle role changed")

    require(concepts["concept_openable_door"]["state_variables"] == ["open", "closed", "partially_open", "locked_unknown"], "door state vocabulary missing")
    require("interior_temperature_not_visually_proven" in concepts["concept_refrigerator"]["physical_properties"], "refrigerator visual boundary missing")
    require("liquid_retention_verified_before_transport" in concepts["concept_portable_bottle"]["runtime_verification_policy"]["functional_checks"], "bottle retention verification missing")
    require(all(concepts[item]["load_policy"] == "domain_resident" for item in trial_ids), "trial concepts are not home resident")
    require(all(concept["direct_execution_allowed"] is False for concept in concepts.values()), "concept kernel gained execution authority")

    core_only = load_concept_pack_registry(active_domains=())
    require(not core_only["concepts"] and core_only["shared_grounding_policy"], f"domain concepts leaked into core: {core_only}")

    visual_packs = load_visual_concept_packs(include_on_demand=True)
    packs_by_id = {item["pack_id"]: item for item in visual_packs}
    for concept in concepts.values():
        for pack_ref in concept.get("perception_adapter_refs", []):
            require(pack_ref in packs_by_id, f"missing visual pack {pack_ref} for {concept['concept_id']}")
            require(packs_by_id[pack_ref]["concept_id"] == concept["concept_id"], f"visual pack points to wrong concept: {pack_ref}")
    for concept_id in trial_ids:
        concept = concepts[concept_id]
        pack = packs_by_id[concept["perception_adapter_refs"][0]]
        observed = {
            "observed_visual_features": pack["recognition_adapter"]["required_observed_features"],
            "observed_color_family": pack["recognition_adapter"]["supporting_color_families"][0],
        }
        candidates = match_visual_concept_candidates(observed, [pack])
        require(candidates and candidates[0]["concept_id"] == concept_id, f"trial visual candidate did not match: {concept_id}")
        require(candidates[0]["candidate_only"] and not candidates[0]["direct_execution_allowed"], f"visual candidate became functional truth: {candidates}")

    production = json.loads((DATA / "visual_concept_production_manifest.json").read_text(encoding="utf-8"))
    production_ids = {item["item_id"]: item.get("concept_id") for item in production["items"]}
    require(production_ids["door"] == "concept_openable_door", "door remained an undefined production gap")
    require(production_ids["refrigerator"] == "concept_refrigerator", "refrigerator remained an undefined production gap")
    require(production_ids["bottle"] == "concept_portable_bottle", "bottle remained an undefined production gap")
    legacy_pointer = json.loads((DATA / "embodied_object_concepts.json").read_text(encoding="utf-8"))
    require(legacy_pointer["status"] == "compatibility_pointer_only", f"flat concept file remained authoritative: {legacy_pointer}")

    print({
        "status": "home_concept_packs_valid",
        "concept_count": report["concept_count"],
        "loaded_pack_count": report["loaded_pack_count"],
        "trial_concepts": sorted(trial_ids),
        "runtime_boundary": "candidate_then_orchestration_and_physical_verification",
    })


if __name__ == "__main__":
    main()
