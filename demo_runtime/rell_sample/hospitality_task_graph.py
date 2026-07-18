from __future__ import annotations

from copy import deepcopy
from typing import Any


HOSPITALITY_GOAL = "guest_received_black_tea_and_room_temperature_water"


def _by_id(objects: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["entity_id"]: item for item in objects if item.get("entity_id")}


def build_hospitality_task_graph(
    objects: list[dict[str, Any]],
    *,
    brewing_temperature_c: float = 80.0,
) -> dict[str, Any]:
    """Build a causal task graph from current objects and affordances.

    The graph contains no absolute trajectory or object-specific policy. It
    records required conditions and lets the runtime resolver choose which
    ready branch to execute or which missing slot to ask about.
    """
    by_id = _by_id(objects)
    tea_box = next((item for item in objects if item.get("kind") == "tea_inventory"), None)
    thermos = next((item for item in objects if item.get("kind") == "water_source" and item.get("source_kind") == "thermos"), None)
    mug = next((item for item in objects if item.get("kind") == "graspable_container" and item.get("tea_suitable") is True), None)
    glass = next((item for item in objects if item.get("kind") == "graspable_container" and item.get("tea_suitable") is False), None)
    tray = next((item for item in objects if item.get("kind") == "graspable_tray"), None)
    guest = next((item for item in objects if item.get("kind") == "human_recipient"), None)
    service = next((item for item in objects if item.get("kind") == "handover_zone"), None)
    newspapers = [item for item in objects if item.get("kind") == "discardable_object"]
    trash = next((item for item in objects if item.get("kind") == "discard_bin"), None)

    tea_inventory = (tea_box or {}).get("inventory", {})
    cup_area = sum(
        float(item.get("size", [0.0, 0.0])[0]) * float(item.get("size", [0.0, 0.0])[1])
        for item in (mug, glass)
        if item
    )
    tray_area = float((tray or {}).get("usable_footprint_m2", 0.0))
    graph = {
        "schema_version": "1.0.0",
        "intent_type": "hospitality_guest_service",
        "goal_fact": HOSPITALITY_GOAL,
        "roles": {
            "tea_vessel": mug.get("entity_id") if mug else None,
            "water_vessel": glass.get("entity_id") if glass else None,
            "water_source": thermos.get("entity_id") if thermos else None,
            "tray": tray.get("entity_id") if tray else None,
            "recipient": guest.get("entity_id") if guest else None,
            "handover_zone": service.get("entity_id") if service else None,
            "trash_bin": trash.get("entity_id") if trash else None,
        },
        "nodes": [
            {
                "node_id": "inspect_resources",
                "label": "观察资源与可供性",
                "requires": [],
                "produces": ["resources_grounded", "affordances_grounded"],
                "verification": ["current_world_snapshot_bound"],
            },
            {
                "node_id": "clear_old_newspapers",
                "label": "清理操作台B旧报纸",
                "requires": ["resources_grounded", "newspapers_present", "trash_bin_accepts_discardable"],
                "produces": ["counter_b_footprint_released", "newspapers_discarded"],
                "verification": ["newspapers_not_on_counter_b", "discard_bin_possession_verified"],
            },
            {
                "node_id": "prepare_black_tea",
                "label": "准备一杯红茶",
                "requires": ["black_tea_available", "tea_vessel_suitable", "brewing_temperature_sufficient"],
                "produces": ["black_tea_ready"],
                "verification": ["tea_bag_consumed", "liquid_level_verified", "steeping_time_verified"],
                "recovery": ["ask_for_hot_water", "substitute_tea_vessel", "ask_for_tea_substitution"],
            },
            {
                "node_id": "prepare_room_temperature_water",
                "label": "准备一杯常温水",
                "requires": ["room_temperature_water_source", "water_vessel_suitable"],
                "produces": ["room_temperature_water_ready"],
                "verification": ["water_level_verified", "temperature_verified"],
            },
            {
                "node_id": "acquire_tray",
                "label": "取得托盘",
                "requires": ["tray_grounded", "tray_graspable"],
                "produces": ["tray_in_effector"],
                "verification": ["tray_in_effector_verified"],
            },
            {
                "node_id": "load_tray",
                "label": "将两杯装载到托盘",
                "requires": ["tray_in_effector", "black_tea_ready", "room_temperature_water_ready", "tray_capacity_sufficient"],
                "produces": ["tray_loaded_with_two_cups"],
                "verification": ["load_stable", "all_items_supported_by_tray"],
                "recovery": ["ask_direct_carry_or_alternate_tray"],
            },
            {
                "node_id": "deliver_tray",
                "label": "端托盘到客人交接区域",
                "requires": ["tray_loaded_with_two_cups", "handover_zone_reachable", "handover_zone_not_used_as_support"],
                "produces": ["tray_at_handover_zone"],
                "verification": ["tray_stable_during_transport"],
            },
            {
                "node_id": "handover_to_guest",
                "label": "将托盘交给客人",
                "requires": ["tray_at_handover_zone", "recipient_ready"],
                "produces": [HOSPITALITY_GOAL],
                "verification": ["recipient_possession_verified"],
            },
        ],
        "edges": [
            {"from": "inspect_resources", "to": "clear_old_newspapers"},
            {"from": "inspect_resources", "to": "prepare_black_tea"},
            {"from": "inspect_resources", "to": "prepare_room_temperature_water"},
            {"from": "inspect_resources", "to": "acquire_tray"},
            {"from": "clear_old_newspapers", "to": "load_tray"},
            {"from": "prepare_black_tea", "to": "load_tray"},
            {"from": "prepare_room_temperature_water", "to": "load_tray"},
            {"from": "acquire_tray", "to": "load_tray"},
            {"from": "load_tray", "to": "deliver_tray"},
            {"from": "deliver_tray", "to": "handover_to_guest"},
        ],
        "join_nodes": ["load_tray", "deliver_tray", "handover_to_guest"],
        "parallel_ready_branches": ["clear_old_newspapers", "prepare_black_tea", "prepare_room_temperature_water", "acquire_tray"],
        "current_evidence": {
            "black_tea_count": int(tea_inventory.get("black_tea", 0)),
            "green_tea_count": int(tea_inventory.get("green_tea", 0)),
            "water_temperature_c": (thermos or {}).get("temperature_c"),
            "brewing_temperature_c": brewing_temperature_c,
            "tea_vessel_suitable": bool(mug),
            "newspaper_count": len(newspapers),
            "service_zone_stable": bool((service or {}).get("stable", False)),
            "service_zone_is_handover_zone": "handover_zone" in (service or {}).get("affordances", []),
            "tray_usable_footprint_m2": tray_area,
            "required_cup_footprint_m2": round(cup_area, 6),
            "tray_capacity_sufficient": tray_area >= cup_area if tray else False,
        },
        "required_conditions": {
            "black_tea_available": int(tea_inventory.get("black_tea", 0)) > 0,
            "brewing_temperature_sufficient": (thermos or {}).get("temperature_c", -273.15) >= brewing_temperature_c,
            "tray_capacity_sufficient": tray_area >= cup_area if tray else False,
            "handover_zone_not_used_as_support": bool(service) and not bool((service or {}).get("stable", False)),
            "newspapers_need_clearance": bool(newspapers),
        },
    }
    return graph


def unresolved_hospitality_conditions(graph: dict[str, Any]) -> list[dict[str, Any]]:
    conditions = graph.get("required_conditions", {})
    questions = {
        "black_tea_available": "茶包盒里没有红茶包。要用绿茶代替，还是只准备常温水？",
        "brewing_temperature_sufficient": "当前水源是常温水，不满足红茶浸泡温度。要换热水源，还是调整为常温饮品？",
        "tray_capacity_sufficient": "托盘有效承载空间不足以稳定放下两杯。要换托盘，还是改为分别端送？",
    }
    return [
        {"condition": key, "status": "missing", "question": questions.get(key)}
        for key, satisfied in conditions.items()
        if satisfied is False and key in questions
    ]


def build_hospitality_orchestration_view(graph: dict[str, Any]) -> dict[str, Any]:
    """Project causal readiness without pretending that parallel means simultaneous."""
    conditions = graph.get("required_conditions", {})
    blocked_by_node = {
        "prepare_black_tea": [
            name for name in ("black_tea_available", "brewing_temperature_sufficient")
            if conditions.get(name) is False
        ],
        "load_tray": [
            name for name in ("tray_capacity_sufficient",)
            if conditions.get(name) is False
        ],
    }
    ready = []
    blocked = []
    waiting = []
    branch_nodes = set(graph.get("parallel_ready_branches", []))
    for node in graph.get("nodes", []):
        node_id = node["node_id"]
        condition_gaps = blocked_by_node.get(node_id, [])
        if condition_gaps:
            blocked.append({"node_id": node_id, "missing_conditions": condition_gaps})
        elif node_id in branch_nodes:
            ready.append(node_id)
        elif node_id != "inspect_resources":
            waiting.append({"node_id": node_id, "waiting_for": deepcopy(node.get("requires", []))})
    return {
        "goal_fact": graph.get("goal_fact"),
        "ready_nodes": ready,
        "blocked_nodes": blocked,
        "waiting_nodes": waiting,
        "join_nodes": deepcopy(graph.get("join_nodes", [])),
        "scheduling_contract": "ready branches may be interleaved; join nodes require every causal predecessor",
    }


__all__ = [
    "HOSPITALITY_GOAL",
    "build_hospitality_task_graph",
    "build_hospitality_orchestration_view",
    "unresolved_hospitality_conditions",
]
