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
        "activation_contract": {
            "speech_acts": ["task_request"],
            "operators_any": ["transport_object"],
            "goal_relations_any": ["object_at_target_region"],
        },
        "roles": {
            "tea_vessel": mug.get("entity_id") if mug else None,
            "water_vessel": glass.get("entity_id") if glass else None,
            "water_source": thermos.get("entity_id") if thermos else None,
            "tea_inventory": tea_box.get("entity_id") if tea_box else None,
            "tray": tray.get("entity_id") if tray else None,
            "recipient": guest.get("entity_id") if guest else None,
            "handover_zone": service.get("entity_id") if service else None,
            "trash_bin": trash.get("entity_id") if trash else None,
            "discardables": [item["entity_id"] for item in newspapers],
            "clearance_surface": next((item.get("support_ref") for item in newspapers if item.get("support_ref")), None),
        },
        "nodes": [
            {
                "node_id": "inspect_resources",
                "label": "观察资源与可供性",
                "priority": 10,
                "requires": [],
                "produces": ["resources_grounded", "affordances_grounded"],
                "verification": ["current_world_snapshot_bound"],
                "execution_contract": {
                    "mode": "epistemic",
                    "process_template": "observe_current_world",
                },
            },
            {
                "node_id": "clear_old_newspapers",
                "label": "清理操作台B旧报纸",
                "priority": 20,
                "requires": ["resources_grounded", "newspapers_present", "trash_bin_accepts_discardable"],
                "produces": ["counter_b_footprint_released", "newspapers_discarded"],
                "verification": ["newspapers_not_on_counter_b", "discard_bin_possession_verified"],
                "execution_contract": {
                    "mode": "motion_effect",
                    "process_template": "discard_objects",
                    "target_role": "discardables",
                    "route_roles": ["discardables"],
                    "process_chain": ["collect_discardables", "navigate_to_discard_container", "release_into_container", "verify_discard_relation"],
                    "effects": [
                        {"operator": "move_role_members_to_container", "themes_role": "discardables", "container_role": "trash_bin"}
                    ],
                },
            },
            {
                "node_id": "prepare_black_tea",
                "label": "准备一杯红茶",
                "priority": 30,
                "requires": ["resources_grounded", "black_tea_available", "tea_vessel_suitable"],
                "requires_any": [["brewing_temperature_sufficient", "room_temperature_brewing_authorized"]],
                "produces": ["black_tea_ready"],
                "verification": ["tea_bag_consumed", "liquid_level_verified", "steeping_time_verified"],
                "recovery": ["ask_for_hot_water", "substitute_tea_vessel", "ask_for_tea_substitution"],
                "execution_contract": {
                    "mode": "motion_effect",
                    "process_template": "prepare_infusion",
                    "target_role": "tea_vessel",
                    "route_roles": ["tea_inventory", "tea_vessel", "water_source", "tea_vessel"],
                    "process_chain": ["acquire_tea_bag", "place_tea_bag_in_vessel", "add_bound_water", "verify_liquid_and_steeping_state"],
                    "effects": [
                        {"operator": "decrement_role_inventory", "role": "tea_inventory", "field": "inventory.black_tea", "amount": 1},
                        {"operator": "set_role_fields", "role": "tea_vessel", "fields": {"liquid_state": "filled", "fill_level": 0.7, "contents": "black_tea", "tea_bag_present": True}}
                    ],
                },
            },
            {
                "node_id": "prepare_room_temperature_water",
                "label": "准备一杯常温水",
                "priority": 40,
                "requires": ["resources_grounded", "room_temperature_water_source", "water_vessel_suitable"],
                "produces": ["room_temperature_water_ready"],
                "verification": ["water_level_verified", "temperature_verified"],
                "execution_contract": {
                    "mode": "motion_effect",
                    "process_template": "fill_container",
                    "target_role": "water_source",
                    "route_roles": ["water_vessel", "water_source"],
                    "process_chain": ["position_vessel_at_source", "activate_or_pour_source", "verify_liquid_level", "verify_temperature"],
                    "effects": [
                        {"operator": "copy_role_field", "source_role": "water_source", "source_field": "temperature_c", "target_role": "water_vessel", "target_field": "temperature_c"},
                        {"operator": "set_role_fields", "role": "water_vessel", "fields": {"liquid_state": "filled", "fill_level": 0.75, "contents": "water"}}
                    ],
                },
            },
            {
                "node_id": "acquire_tray",
                "label": "取得托盘",
                "priority": 50,
                "requires": ["resources_grounded", "tray_grounded", "tray_graspable"],
                "produces": ["tray_in_effector"],
                "verification": ["tray_in_effector_verified"],
                "execution_contract": {
                    "mode": "motion_effect",
                    "process_template": "grasp_object",
                    "target_role": "tray",
                    "route_roles": ["tray"],
                    "process_chain": ["navigate_to_tray", "align_free_effector", "grasp_tray", "verify_tray_in_effector"],
                    "effects": [
                        {"operator": "attach_role_to_available_effector", "role": "tray"}
                    ],
                },
            },
            {
                "node_id": "load_tray",
                "label": "将两杯装载到托盘",
                "priority": 60,
                "requires": ["tray_in_effector", "black_tea_ready", "room_temperature_water_ready", "tray_capacity_sufficient"],
                "produces": ["tray_loaded_with_two_cups"],
                "verification": ["load_stable", "all_items_supported_by_tray"],
                "recovery": ["ask_direct_carry_or_alternate_tray"],
                "execution_contract": {
                    "mode": "motion_effect",
                    "process_template": "load_support_carrier",
                    "target_role": "tray",
                    "route_roles": ["tea_vessel", "tray", "water_vessel", "tray"],
                    "process_chain": ["grasp_first_payload", "place_on_carrier", "grasp_second_payload", "place_on_carrier", "verify_non_overlapping_support"],
                    "effects": [
                        {"operator": "support_roles_on_role", "themes_roles": ["tea_vessel", "water_vessel"], "support_role": "tray"}
                    ],
                },
            },
            {
                "node_id": "deliver_tray",
                "label": "端托盘到客人交接区域",
                "priority": 70,
                "requires": ["tray_loaded_with_two_cups", "handover_zone_reachable", "handover_zone_not_used_as_support"],
                "produces": ["tray_at_handover_zone"],
                "verification": ["tray_stable_during_transport"],
                "execution_contract": {
                    "mode": "motion_effect",
                    "process_template": "transport_object",
                    "target_role": "handover_zone",
                    "route_roles": ["handover_zone"],
                    "process_chain": ["retain_carrier_grasp", "navigate_to_handover_zone", "verify_carrier_load_stability"],
                    "effects": [
                        {"operator": "move_role_with_supported_payloads_to_executor", "role": "tray"}
                    ],
                },
            },
            {
                "node_id": "handover_to_guest",
                "label": "将饮品交给客人并保留托盘",
                "priority": 80,
                "requires": ["tray_at_handover_zone", "recipient_ready"],
                "produces": [HOSPITALITY_GOAL],
                "verification": ["payload_possession_verified", "carrier_retention_verified"],
                "execution_contract": {
                    "mode": "motion_effect",
                    "process_template": "handover_object",
                    "target_role": "recipient",
                    "route_roles": ["recipient"],
                    "process_chain": ["verify_recipient_readiness", "transfer_supported_payloads", "retain_carrier", "verify_payload_possession_and_carrier_retention"],
                    "effects": [
                        {
                            "operator": "handover_supported_roles_to_role_retain_carrier",
                            "carrier_role": "tray",
                            "payload_roles": ["tea_vessel", "water_vessel"],
                            "recipient_role": "recipient",
                        }
                    ],
                },
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
        "scheduler_policy": {
            "mode": "verified_fact_driven_interleaving",
            "resolve_goal_affecting_conditions_before_execution": True,
            "maximum_active_motion_nodes": 1,
        },
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
        "world_fact_rules": {
            "newspapers_present": {"operator": "all_members_field_equals_role_ref", "role": "discardables", "field": "support_ref", "value_role": "clearance_surface"},
            "trash_bin_accepts_discardable": {"operator": "field_truthy", "role": "trash_bin", "field": "accepts_discardable"},
            "black_tea_available": {"operator": "field_gte", "role": "tea_inventory", "field": "inventory.black_tea", "value": 1},
            "tea_vessel_suitable": {"operator": "field_equals", "role": "tea_vessel", "field": "tea_suitable", "value": True},
            "brewing_temperature_sufficient": {"operator": "field_gte", "role": "water_source", "field": "temperature_c", "value": brewing_temperature_c},
            "room_temperature_water_source": {"operator": "field_equals", "role": "water_source", "field": "temperature_c", "value": 20},
            "water_vessel_suitable": {"operator": "role_exists", "role": "water_vessel"},
            "tray_grounded": {"operator": "role_exists", "role": "tray"},
            "tray_graspable": {"operator": "role_exists", "role": "tray"},
            "tray_capacity_sufficient": {"operator": "sum_role_footprints_lte_role_field", "member_roles": ["tea_vessel", "water_vessel"], "capacity_role": "tray", "capacity_field": "usable_footprint_m2"},
            "handover_zone_reachable": {"operator": "role_exists", "role": "handover_zone"},
            "handover_zone_not_used_as_support": {"operator": "field_equals", "role": "handover_zone", "field": "stable", "value": False},
            "recipient_ready": {"operator": "field_truthy", "role": "recipient", "field": "handover_ready"}
        },
        "condition_resolutions": {
            "brewing_temperature_sufficient": {
                "priority": 10,
                "question": "当前水源是常温水，不满足红茶浸泡温度。要换热水源，还是允许按常温方式准备？",
                "options": [
                    {
                        "option_id": "provide_hot_water_source",
                        "aliases": ["换热水", "热水源", "换热水壶", "我来换热水"],
                        "requires_world_change": True,
                        "prompt": "请把可用热水源放入当前空间；世界状态更新后我会重新观察温度，不会把口头回答当成物理温度事实。"
                    },
                    {
                        "option_id": "authorize_room_temperature_preparation",
                        "aliases": ["用常温水", "常温水试试", "按常温", "常温方式"],
                        "establishes": ["room_temperature_brewing_authorized"],
                        "acknowledgement": "已把目标约束调整为按常温方式准备；当前水温事实仍保持20°C。"
                    }
                ]
            }
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
