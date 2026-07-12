from __future__ import annotations

from copy import deepcopy
from typing import Any


STATE_CONCEPT_UNITS: list[dict[str, Any]] = [
    {
        "concept_id": "state_concept_liquid_state",
        "display_name": "液体状态查询概念",
        "query_type": "liquid_state",
        "aliases": ["有没有水", "有水吗", "空的吗", "空没空", "杯中", "杯子里", "壶里"],
        "source_slots": ["object_locations.*.state_facts", "established_facts"],
        "source_policy": "runtime_world_state_snapshot_only",
        "default_positive_fact": "cup_contains_water",
        "default_negative_fact": "cup_empty",
        "object_overrides": {
            "object_kettle_steel_1l": {
                "positive_fact": "kettle_has_water",
                "negative_fact": None,
            }
        },
    },
    {
        "concept_id": "state_concept_holding_state",
        "display_name": "持有状态查询概念",
        "query_type": "holding_state",
        "aliases": ["拿着什么", "手里有什么", "手上有什么", "手上拿着什么", "握着什么", "持有什么"],
        "source_slots": ["executor.holding"],
        "source_policy": "runtime_world_state_snapshot_only",
    },
    {
        "concept_id": "state_concept_executor_location",
        "display_name": "执行体位置查询概念",
        "query_type": "executor_location",
        "aliases": ["在哪", "在哪里", "什么位置", "哪个区域"],
        "source_slots": ["executor.location_ref"],
        "source_policy": "runtime_world_state_snapshot_only",
    },
    {
        "concept_id": "state_concept_preference_summary",
        "display_name": "偏好约束查询概念",
        "query_type": "preference_summary",
        "aliases": ["偏好", "偏好约束", "人类反馈", "用户要求"],
        "source_slots": ["active_preferences", "preference_context"],
        "source_policy": "runtime_world_state_snapshot_only",
    },
    {
        "concept_id": "state_concept_current_action",
        "display_name": "当前动作查询概念",
        "query_type": "current_action",
        "aliases": ["你现在在做什么", "我现在在做什么", "当前在做什么", "现在在做什么"],
        "source_slots": ["current_stage", "runtime_state"],
        "source_policy": "runtime_world_state_snapshot_and_current_runtime_context_only",
    },
    {
        "concept_id": "state_concept_next_step",
        "display_name": "下一步查询概念",
        "query_type": "next_step",
        "aliases": ["下一步做什么", "接下来做什么", "下一步是什么"],
        "source_slots": ["current_stage", "completed_stages", "goal_fact", "available_actions_now"],
        "source_policy": "runtime_world_state_snapshot_and_current_runtime_context_only",
    },
    {
        "concept_id": "state_concept_snapshot_summary",
        "display_name": "运行时快照摘要查询概念",
        "query_type": "snapshot_summary",
        "aliases": ["现在状态", "当前状态", "世界状态"],
        "source_slots": ["executor", "established_facts", "current_stage", "completed_stages", "active_preferences"],
        "source_policy": "runtime_world_state_snapshot_only",
    },
]


def _copy_unit(unit: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(unit)


def find_state_concepts_by_text(normalized_text: str) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for unit in STATE_CONCEPT_UNITS:
        if any(alias in normalized_text for alias in unit.get("aliases", [])):
            matched.append(_copy_unit(unit))
    return matched


def find_state_concepts_by_query_type(query_type: str) -> list[dict[str, Any]]:
    return [_copy_unit(unit) for unit in STATE_CONCEPT_UNITS if unit.get("query_type") == query_type]


def build_supported_runtime_questions() -> list[str]:
    return [
        "当前杯子有没有水",
        "当前水壶里有没有水",
        "我手里拿着什么",
        "我现在在哪",
        "当前偏好约束是什么",
        "你现在在做什么",
        "下一步做什么",
        "当前状态",
    ]
