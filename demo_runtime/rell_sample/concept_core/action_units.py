from __future__ import annotations

from copy import deepcopy
from typing import Any


ACTION_CONCEPT_UNITS: list[dict[str, Any]] = [
    {
        "concept_id": "action_concept_move_to_counter",
        "display_name": "前往操作台动作概念",
        "step_id": "move_to_counter",
        "aliases": ["走向操作台", "走到操作台", "到操作台", "去操作台"],
        "capability": "navigate_to_region",
        "goal_fact_bridge": "executor_at_counter",
        "concept_kernel": {
            "operator": "navigate_to",
            "semantic_roles": {
                "destination": {"role": "target", "entity_type": "operation_surface", "default_entity_ref": "region_counter_operation"},
            },
            "effect_contract": {
                "requires": ["target_region_reachable"],
                "produces": ["executor_at_counter"],
                "destroys": ["executor_at_previous_region"],
                "verification": ["executor_pose_inside_target_region"],
            },
        },
        "source_policy": "semantic_only_then_reenter_orchestration",
    },
    {
        "concept_id": "action_concept_pick_up_cup",
        "display_name": "拿起杯子动作概念",
        "step_id": "pick_up_cup",
        "aliases": ["拿起杯子", "拿杯子", "取杯子", "抓取杯子"],
        "capability": "grasp_object",
        "goal_fact_bridge": "cup_in_gripper",
        "concept_kernel": {
            "operator": "grasp_object",
            "semantic_roles": {
                "object": {"role": "target", "entity_type": "fillable_container", "default_entity_ref": "object_cup_white_mug"},
            },
            "effect_contract": {
                "requires": ["gripper_empty", "cup_reachable"],
                "produces": ["cup_in_gripper"],
                "destroys": ["gripper_empty", "cup_at_counter"],
                "verification": ["gripper_holding_cup_observed"],
            },
        },
        "source_policy": "semantic_only_then_reenter_orchestration",
    },
    {
        "concept_id": "action_concept_move_to_water_source",
        "display_name": "前往水源处动作概念",
        "step_id": "move_to_water_source",
        "aliases": ["到水源", "去水源", "走到水源", "水源处"],
        "capability": "navigate_to_region",
        "goal_fact_bridge": "executor_at_water_source",
        "concept_kernel": {
            "operator": "navigate_to",
            "semantic_roles": {
                "destination": {"role": "target", "entity_type": "liquid_source_region", "default_entity_ref": "region_water_source"},
            },
            "effect_contract": {
                "requires": ["target_region_reachable"],
                "produces": ["executor_at_water_source"],
                "destroys": ["executor_at_previous_region"],
                "verification": ["executor_pose_inside_target_region"],
            },
        },
        "source_policy": "semantic_only_then_reenter_orchestration",
    },
    {
        "concept_id": "action_concept_fill_cup",
        "display_name": "接水动作概念",
        "step_id": "fill_cup_at_water_source",
        "aliases": ["接一杯水", "接水", "装水", "取水", "倒杯水"],
        "capability": "fill_container",
        "goal_fact_bridge": "cup_contains_water",
        "concept_kernel": {
            "operator": "fill_container",
            "semantic_roles": {
                "container": {"role": "target", "entity_type": "fillable_container", "default_entity_ref": "object_cup_white_mug"},
                "source": {"role": "origin", "entity_type": "liquid_source", "default_entity_ref": "region_water_source"},
                "material": {"role": "resource", "value": "water"},
            },
            "effect_contract": {
                "requires": ["cup_in_gripper", "executor_at_water_source", "water_source_available"],
                "produces": ["cup_contains_water"],
                "destroys": ["cup_empty"],
                "verification": ["water_flow_observed", "cup_liquid_level_reached"],
            },
        },
        "source_policy": "semantic_only_then_reenter_orchestration",
    },
    {
        "concept_id": "action_concept_pour_water",
        "display_name": "倒水动作概念",
        "step_id": "pour_water",
        "aliases": ["倒水", "倒一杯水", "给客人倒水"],
        "capability": "pour_container",
        "goal_fact_bridge": "water_poured",
        "concept_kernel": {
            "operator": "pour_container",
            "semantic_roles": {
                "container": {"role": "source_container", "entity_type": "fillable_container", "default_entity_ref": "object_cup_white_mug"},
                "material": {"role": "resource", "value": "water"},
                "destination": {"role": "target", "entity_type": "pour_target"},
            },
            "effect_contract": {
                "requires": ["cup_in_gripper", "cup_contains_water", "executor_at_counter"],
                "produces": ["water_poured"],
                "destroys": ["cup_contains_water"],
                "verification": ["pour_flow_observed", "target_received_water"],
            },
        },
        "source_policy": "semantic_only_then_reenter_orchestration",
    },
    {
        "concept_id": "action_concept_detour_obstacle",
        "display_name": "绕障动作概念",
        "step_id": None,
        "aliases": ["绕开障碍", "绕开", "避开障碍", "绕过去", "避过去"],
        "capability": "local_obstacle_avoidance",
        "goal_fact_bridge": None,
        "concept_kernel": {
            "operator": "detour_obstacle",
            "semantic_roles": {
                "obstacle": {"role": "avoidance_target", "entity_type": "obstacle"},
                "route": {"role": "affected_path", "entity_type": "navigation_route"},
            },
            "effect_contract": {
                "requires": ["obstacle_observed", "alternative_route_available"],
                "produces": ["obstacle_bypassed"],
                "destroys": [],
                "verification": ["executor_cleared_obstacle", "route_safety_preserved"],
            },
        },
        "source_policy": "semantic_only_then_reenter_orchestration",
    },
]


def _copy_unit(unit: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(unit)


def find_action_concept_by_step(step_id: str) -> dict[str, Any] | None:
    for unit in ACTION_CONCEPT_UNITS:
        if unit.get("step_id") == step_id:
            return _copy_unit(unit)
    return None


def find_action_concepts_by_text(normalized_text: str) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for unit in ACTION_CONCEPT_UNITS:
        if any(alias in normalized_text for alias in unit.get("aliases", [])):
            matched.append(_copy_unit(unit))
    return matched
