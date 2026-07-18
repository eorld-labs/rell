"""World variants for the ten hospitality stress dimensions.

Variants are derived from the same semantic baseline; they change facts and
capabilities, never the process-template implementation.
"""
from copy import deepcopy


VARIANTS = {
    "base": {},
    "interruption": {"active_obstacle": True, "interruptible": True},
    "failure_recovery": {"induce_container_slip": True, "failure_repeat_count": 3},
    "preference_memory": {"tea_steep_time_min": 2, "preference_alias": "淡一点"},
    "capability_boundary": {"executor_arm_reach_m": 0.45},
    "recipient_ambiguity": {"add_second_guest": True},
    "container_ambiguity": {"add_third_container": True},
    "support_capacity": {"counter_b_limited": True},
    "missing_resources": {"black_tea_count": 0},
    "migration": {"scene_coordinate_frame": "relocated_layout"},
}


def build_hospitality_variant(scene: dict, variant: str) -> dict:
    if variant not in VARIANTS:
        raise ValueError(f"unknown hospitality variant: {variant}")
    result = deepcopy(scene)
    config = VARIANTS[variant]
    result["test_variant"] = variant
    result["test_contract"] = deepcopy(config)
    if config.get("active_obstacle"):
        result.setdefault("initial_state", {})["interruptible"] = True
    if config.get("executor_arm_reach_m"):
        for profile in result.get("executor_profiles", {}).values():
            profile["arm_reach_m"] = config["executor_arm_reach_m"]
    if config.get("black_tea_count") is not None:
        for obj in result.get("objects", []):
            if obj.get("kind") == "tea_inventory":
                obj.setdefault("inventory", {})["black_tea"] = config["black_tea_count"]
    if config.get("add_second_guest"):
        guest = next((o for o in result["objects"] if o.get("kind") == "human_recipient"), None)
        if guest:
            second = deepcopy(guest)
            second["entity_id"] = "guest_secondary"
            second["label"] = "第二位客人"
            second["position"] = [-0.7, -0.15]
            result["objects"].append(second)
    return result


def validate_hospitality_matrix(scene: dict) -> dict:
    variants = {name: build_hospitality_variant(scene, name) for name in VARIANTS}
    return {
        "variant_count": len(variants),
        "variants": sorted(variants),
        "coverage": {name: bool(v.get("test_contract") is not None) for name, v in variants.items()},
    }


__all__ = ["VARIANTS", "build_hospitality_variant", "validate_hospitality_matrix"]
