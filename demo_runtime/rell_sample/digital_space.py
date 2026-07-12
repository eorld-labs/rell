from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_subject_cognitive_model(prior: dict[str, Any], subject_type: str = "simulated_robot") -> dict[str, Any]:
    conversion = _select_conversion(prior, subject_type)
    regions = prior["semantic_regions"]
    objects = prior.get("space_objects", [])
    relations = prior["spatial_relations"]
    region_ids = {region["region_id"] for region in regions}
    object_ids = {item["object_id"] for item in objects}

    action_nodes = [
        _region_node(region)
        for region in regions
        if _has_any(region, {"traversable", "staying", "interactive", "target_object_location", "task_execution"})
    ]
    action_edges = [
        _relation_edge(relation)
        for relation in relations
        if relation["source_ref"] in region_ids | object_ids
        and relation["target_ref"] in region_ids | object_ids
        and relation["relation_type"] in {"connected", "near", "interaction_reachable", "observation_reachable"}
    ]
    blocked_edges = [
        _relation_edge(relation)
        for relation in relations
        if relation["relation_type"] in {"blocked", "no_entry", "forbidden", "risk"}
    ]

    object_region_index = {
        item["object_id"]: {
            "object_type": item["object_type"],
            "region_ref": item["region_ref"],
            "affordances": item.get("affordances", []),
            "state_facts": item.get("state_facts", []),
        }
        for item in objects
    }
    risk_regions = [
        {
            "region_id": region["region_id"],
            "risk_attributes": sorted(set(region["function_attributes"]) & {"risk", "no_entry", "heat_source"}),
            "confidence": region["confidence"],
            "runtime_policy": "avoid_or_request_confirmation",
        }
        for region in regions
        if _has_any(region, {"risk", "no_entry", "non_traversable"})
    ]
    validation_targets = [
        {
            "target_ref": region["region_id"],
            "reason": "low_confidence_or_runtime_sensitive",
            "confidence": region["confidence"],
        }
        for region in regions
        if region["confidence"] < 0.85 or _has_any(region, {"risk", "target_object_location"})
    ]
    source_bindings = prior.get("binding_candidates", {})
    portable_bindings = {
        **source_bindings,
        "INITIAL_EXECUTOR_REGION": source_bindings.get("WALKABLE_REGION"),
        "TARGET_OPERATION_REGION": source_bindings.get("POUR_OPERATION_REGION"),
        "TARGET_GRASPABLE_CONTAINER": source_bindings.get("CUP_OBJECT"),
        "TARGET_LIQUID_SOURCE_REGION": "region_water_source",
        "SOURCE_LIQUID_RESOURCE_REGION": "region_water_source",
        "TARGET_POUR_DESTINATION_REGION": source_bindings.get("POUR_OPERATION_REGION"),
    }

    return {
        "schema_version": "1.0.0",
        "cognitive_model_id": f"{prior['target_space']['space_id']}_{subject_type}_cognitive_model_v1",
        "prior_ref": prior["prior_id"],
        "subject_type": subject_type,
        "space_region_table": [_region_table_item(region) for region in regions],
        "space_action_graph": {
            "nodes": action_nodes,
            "edges": action_edges,
            "blocked_edges": blocked_edges,
        },
        "semantic_topology_graph": {
            "nodes": [{"node_id": region["region_id"], "node_type": region["region_type"]} for region in regions],
            "edges": [_relation_edge(relation) for relation in relations],
        },
        "task_reachable_graph": {
            "task_type": "pour_water",
            "start_region": prior["binding_candidates"]["WALKABLE_REGION"],
            "required_regions": [
                prior["binding_candidates"]["POUR_OPERATION_REGION"],
                "region_water_source",
                "region_cup_station",
            ],
            "required_objects": [
                prior["binding_candidates"]["CUP_OBJECT"],
                prior["binding_candidates"]["KETTLE_OBJECT"],
            ],
        },
        "risk_region_table": risk_regions,
        "interaction_region_table": [
            _region_table_item(region)
            for region in regions
            if _has_any(region, {"interactive", "target_object_location", "task_execution"})
        ],
        "object_region_index": object_region_index,
        "binding_candidates": portable_bindings,
        "local_environment_summary": {
            "space_id": prior["target_space"]["space_id"],
            "region_count": len(regions),
            "relation_count": len(relations),
            "object_count": len(objects),
            "conversion_rule": conversion["region_mapping_rule"],
            "runtime_use": "provide spatial context for simulated execution, verification, recovery and future learning traces",
        },
        "validation_targets": validation_targets,
    }


def _select_conversion(prior: dict[str, Any], subject_type: str) -> dict[str, Any]:
    for conversion in prior["edge_conversion_info"]:
        if conversion["subject_type"] == subject_type:
            return conversion
    raise ValueError(f"missing edge_conversion_info for subject_type={subject_type}")


def _has_any(region: dict[str, Any], attrs: set[str]) -> bool:
    return bool(set(region.get("function_attributes", [])) & attrs)


def _region_node(region: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": region["region_id"],
        "node_type": region["region_type"],
        "attributes": region["function_attributes"],
        "confidence": region["confidence"],
    }


def _relation_edge(relation: dict[str, Any]) -> dict[str, Any]:
    return {
        "edge_id": relation["relation_id"],
        "source": relation["source_ref"],
        "target": relation["target_ref"],
        "relation_type": relation["relation_type"],
        "weight": relation.get("weight", 1.0),
        "constraint": relation.get("constraint"),
        "confidence": relation["confidence"],
    }


def _region_table_item(region: dict[str, Any]) -> dict[str, Any]:
    return {
        "region_id": region["region_id"],
        "region_type": region["region_type"],
        "function_attributes": region["function_attributes"],
        "permission": region.get("permission"),
        "confidence": region["confidence"],
        "geometry_ref": region["geometry_ref"],
    }
