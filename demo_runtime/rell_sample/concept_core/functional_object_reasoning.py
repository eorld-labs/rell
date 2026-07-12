from __future__ import annotations

from copy import deepcopy
from typing import Any


FUNCTIONAL_ROLE_CONTRACTS: dict[str, dict[str, Any]] = {
    "perceivable_entity": {"required_affordances_any": [], "description": "可被当前传感器形成观测候选"},
    "spatial_target": {"required_affordances_any": ["navigable_target", "interaction_target"], "description": "可形成空间目标绑定"},
    "graspable_object": {"required_affordances_all": ["graspable", "movable"], "forbidden_properties": ["fixed_asset"], "description": "尺寸与质量允许本体抓取且不是固定资产"},
    "held_object": {"required_relations_all": ["held_by_executor"], "description": "当前已被执行体稳定持有"},
    "support_or_container": {"required_affordances_any": ["support_object", "receive_object"], "description": "能稳定支撑或容纳待放置对象"},
    "movable_object": {"required_affordances_all": ["movable"], "forbidden_properties": ["fixed_asset"], "description": "允许在受力后改变位置"},
    "openable_object": {"required_affordances_all": ["openable"], "description": "具有可操作的开放/闭合机构"},
    "controllable_device": {"required_affordances_all": ["device_state_controllable"], "description": "具有可授权改变的设备运行状态"},
    "device_control": {"required_affordances_all": ["control_device_state"], "description": "是设备可感知、可操作的控制部位"},
    "source": {"required_affordances_any": ["provide_water", "provide_material"], "description": "能够提供待转移物质"},
    "destination": {"required_affordances_any": ["receive_liquid", "receive_object", "support_object"], "description": "能够接收目标物质或对象"},
    "cleanable_surface_or_object": {"required_affordances_any": ["cleanable_surface", "cleanable_object"], "description": "表面允许在不受损的情况下清洁"},
}


FACTORY_RELATION_CONCEPTS: list[dict[str, Any]] = [
    {
        "relation_id": "relation_supported_by",
        "display_name": "支撑关系",
        "inverse": "supports",
        "subject_role": "physical_object",
        "object_role": "support_surface",
        "fact_pattern": "{subject}_supported_by_{object}",
        "verification": ["contact_or_small_vertical_gap", "subject_projection_inside_support_boundary", "subject_pose_stable"],
    },
    {
        "relation_id": "relation_contained_in",
        "display_name": "容纳关系",
        "inverse": "contains",
        "subject_role": "physical_object_or_material",
        "object_role": "container",
        "fact_pattern": "{subject}_contained_in_{object}",
        "verification": ["subject_inside_container_boundary", "containment_not_violated"],
    },
    {
        "relation_id": "relation_held_by",
        "display_name": "持有关系",
        "inverse": "holds",
        "subject_role": "graspable_object",
        "object_role": "executor_end_effector",
        "fact_pattern": "{subject}_held_by_{object}",
        "verification": ["gripper_contact_stable", "subject_follows_end_effector"],
    },
    {
        "relation_id": "relation_within_reach",
        "display_name": "可达关系",
        "inverse": None,
        "subject_role": "physical_object",
        "object_role": "executor",
        "fact_pattern": "{subject}_within_reach_of_{object}",
        "verification": ["current_body_workspace_contains_interaction_pose", "collision_free_approach_candidate_exists"],
    },
    {
        "relation_id": "relation_blocks_path",
        "display_name": "路径阻挡关系",
        "inverse": None,
        "subject_role": "physical_body",
        "object_role": "navigation_path",
        "fact_pattern": "{subject}_blocks_{object}",
        "verification": ["swept_body_envelope_intersects_subject", "clearance_below_required_margin"],
    },
    {
        "relation_id": "relation_aligned_with",
        "display_name": "功能对齐关系",
        "inverse": "aligned_with",
        "subject_role": "interaction_part_or_container",
        "object_role": "target_interface",
        "fact_pattern": "{subject}_aligned_with_{object}",
        "verification": ["relative_pose_inside_functional_tolerance", "projected_effect_path_reaches_target"],
    },
    {
        "relation_id": "relation_near",
        "display_name": "邻近关系",
        "inverse": "near",
        "subject_role": "spatial_entity",
        "object_role": "spatial_entity",
        "fact_pattern": "{subject}_near_{object}",
        "verification": ["distance_below_context_threshold"],
    },
]


def build_functional_profile(entity: dict[str, Any], object_concepts: list[dict[str, Any]]) -> dict[str, Any]:
    matched = [item for item in object_concepts if entity.get("kind") in item.get("compatible_kinds", [])]
    affordances = set(entity.get("affordances", []))
    properties = set(entity.get("physical_properties", []))
    current_relations = set(entity.get("current_relations", []))
    for concept in matched:
        affordances.update(concept.get("functional_affordances", []))
        properties.update(concept.get("physical_properties", []))
    if entity.get("fixed"):
        properties.add("fixed_asset")
    else:
        affordances.add("movable")
    if entity.get("kind") not in {"scene_boundary"}:
        affordances.add("interaction_target")
    return {
        "entity_ref": entity.get("entity_id"),
        "label": entity.get("label"),
        "kind": entity.get("kind"),
        "matched_object_concepts": [item["concept_id"] for item in matched],
        "functional_affordances": sorted(affordances),
        "physical_properties": sorted(properties),
        "possible_relations": sorted({relation for concept in matched for relation in concept.get("expected_relations", [])}),
        "current_relations": sorted(current_relations),
        "candidate_only": True,
        "runtime_verified": False,
    }


def evaluate_role_compatibility(profile: dict[str, Any], required_entity_type: str) -> dict[str, Any]:
    contract = FUNCTIONAL_ROLE_CONTRACTS.get(required_entity_type)
    if not contract:
        return {
            "status": "role_contract_not_defined",
            "required_entity_type": required_entity_type,
            "compatible": None,
            "reason": "当前出厂库尚未定义该角色的功能准入条件",
            "candidate_only": True,
        }
    affordances = set(profile.get("functional_affordances", []))
    properties = set(profile.get("physical_properties", []))
    relations = set(profile.get("current_relations", []))
    required_all = set(contract.get("required_affordances_all", []))
    required_any = set(contract.get("required_affordances_any", []))
    required_relations = set(contract.get("required_relations_all", []))
    forbidden = set(contract.get("forbidden_properties", []))
    missing_all = sorted(required_all - affordances)
    missing_any = sorted(required_any) if required_any and not required_any.intersection(affordances) else []
    missing_relations = sorted(required_relations - relations)
    forbidden_present = sorted(forbidden.intersection(properties))
    compatible = not missing_all and not missing_any and not missing_relations and not forbidden_present
    if compatible:
        reason = f"{profile.get('label')}具备承担该角色所需的功能承诺"
    else:
        parts = []
        if missing_all:
            parts.append("缺少功能：" + "、".join(missing_all))
        if missing_any:
            parts.append("至少需要一种功能：" + "、".join(missing_any))
        if missing_relations:
            parts.append("当前关系不成立：" + "、".join(missing_relations))
        if forbidden_present:
            parts.append("存在冲突属性：" + "、".join(forbidden_present))
        reason = f"{profile.get('label')}不能承担该角色：" + "；".join(parts)
    return {
        "status": "compatible_candidate" if compatible else "incompatible",
        "entity_ref": profile.get("entity_ref"),
        "required_entity_type": required_entity_type,
        "role_description": contract["description"],
        "compatible": compatible,
        "reason": reason,
        "missing_affordances": sorted(set(missing_all + missing_any)),
        "missing_relations": missing_relations,
        "forbidden_properties_present": forbidden_present,
        "evidence": {
            "matched_object_concepts": deepcopy(profile.get("matched_object_concepts", [])),
            "functional_affordances": deepcopy(profile.get("functional_affordances", [])),
            "physical_properties": deepcopy(profile.get("physical_properties", [])),
            "current_relations": deepcopy(profile.get("current_relations", [])),
        },
        "candidate_only": True,
        "direct_execution_allowed": False,
    }


def build_functional_object_catalog(object_concepts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "catalog_type": "factory_functional_objects_and_relations",
        "object_concepts": deepcopy(object_concepts),
        "role_contracts": deepcopy(FUNCTIONAL_ROLE_CONTRACTS),
        "relation_concepts": deepcopy(FACTORY_RELATION_CONCEPTS),
        "shared_boundary": {
            "candidate_only": True,
            "direct_execution_allowed": False,
            "appearance_is_not_role_proof": True,
            "runtime_relation_requires_current_observation_or_physical_verification": True,
        },
    }
