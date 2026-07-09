from __future__ import annotations

from pathlib import Path

from digital_space import build_subject_cognitive_model, read_json


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    prior = read_json(DATA / "digital_kitchen_semantic_prior.json")
    saved_model = read_json(DATA / "digital_kitchen_cognitive_model.json")

    require(prior["schema_version"].startswith("1."), "semantic prior schema_version must be 1.x.x")
    require(prior["semantic_regions"], "semantic prior must include semantic_regions")
    require(prior["spatial_relations"], "semantic prior must include spatial_relations")
    require(prior["edge_conversion_info"], "semantic prior must include edge_conversion_info")

    region_ids = {region["region_id"] for region in prior["semantic_regions"]}
    object_ids = {item["object_id"] for item in prior.get("space_objects", [])}
    refs = region_ids | object_ids
    for relation in prior["spatial_relations"]:
        require(relation["source_ref"] in refs, f"unknown relation source_ref: {relation['source_ref']}")
        require(relation["target_ref"] in refs, f"unknown relation target_ref: {relation['target_ref']}")

    required_bindings = {"CUP_OBJECT", "KETTLE_OBJECT", "CAMERA_SENSOR", "POUR_OPERATION_REGION", "WALKABLE_REGION"}
    bindings = prior.get("binding_candidates", {})
    require(required_bindings.issubset(bindings), f"missing binding candidates: {sorted(required_bindings - set(bindings))}")
    require(bindings["CUP_OBJECT"] in object_ids, "CUP_OBJECT must reference a known object")
    require(bindings["KETTLE_OBJECT"] in object_ids, "KETTLE_OBJECT must reference a known object")
    require(bindings["CAMERA_SENSOR"] in object_ids, "CAMERA_SENSOR must reference a known object")
    require(bindings["POUR_OPERATION_REGION"] in region_ids, "POUR_OPERATION_REGION must reference a known region")
    require(bindings["WALKABLE_REGION"] in region_ids, "WALKABLE_REGION must reference a known region")

    conversion_subjects = {item["subject_type"] for item in prior["edge_conversion_info"]}
    require("simulated_robot" in conversion_subjects, "semantic prior must support simulated_robot conversion")

    generated_model = build_subject_cognitive_model(prior, subject_type="simulated_robot")
    require(generated_model == saved_model, "saved cognitive model is not reproducible from semantic prior")
    require(generated_model["space_action_graph"]["nodes"], "cognitive model must include action graph nodes")
    require(generated_model["space_action_graph"]["edges"], "cognitive model must include action graph edges")
    require(generated_model["object_region_index"].get(bindings["CUP_OBJECT"]), "cognitive model must index cup object")
    require(generated_model["risk_region_table"], "cognitive model must include risk region table")

    print("Digital space validation passed.")
    print("Validated: P010 semantic prior, simulated_robot cognitive model, pour_water binding candidates.")


if __name__ == "__main__":
    main()
