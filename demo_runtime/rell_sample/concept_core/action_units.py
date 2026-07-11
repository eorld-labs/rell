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
        "source_policy": "semantic_only_then_reenter_orchestration",
    },
    {
        "concept_id": "action_concept_pick_up_cup",
        "display_name": "拿起杯子动作概念",
        "step_id": "pick_up_cup",
        "aliases": ["拿起杯子", "拿杯子", "取杯子", "抓取杯子"],
        "capability": "grasp_object",
        "goal_fact_bridge": "cup_in_gripper",
        "source_policy": "semantic_only_then_reenter_orchestration",
    },
    {
        "concept_id": "action_concept_move_to_water_source",
        "display_name": "前往水源处动作概念",
        "step_id": "move_to_water_source",
        "aliases": ["到水源", "去水源", "走到水源", "水源处"],
        "capability": "navigate_to_region",
        "goal_fact_bridge": "executor_at_water_source",
        "source_policy": "semantic_only_then_reenter_orchestration",
    },
    {
        "concept_id": "action_concept_fill_cup",
        "display_name": "接水动作概念",
        "step_id": "fill_cup_at_water_source",
        "aliases": ["接一杯水", "接水", "装水", "取水", "倒杯水"],
        "capability": "fill_container",
        "goal_fact_bridge": "cup_contains_water",
        "source_policy": "semantic_only_then_reenter_orchestration",
    },
    {
        "concept_id": "action_concept_pour_water",
        "display_name": "倒水动作概念",
        "step_id": "pour_water",
        "aliases": ["倒水", "倒一杯水", "给客人倒水"],
        "capability": "pour_container",
        "goal_fact_bridge": "water_poured",
        "source_policy": "semantic_only_then_reenter_orchestration",
    },
    {
        "concept_id": "action_concept_detour_obstacle",
        "display_name": "绕障动作概念",
        "step_id": None,
        "aliases": ["绕开障碍", "绕开", "避开障碍", "绕过去", "避过去"],
        "capability": "local_obstacle_avoidance",
        "goal_fact_bridge": None,
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
