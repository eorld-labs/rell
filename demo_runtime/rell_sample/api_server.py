from __future__ import annotations

import json
import os
import re
import hashlib
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from concept_core import (
    FACTORY_EVENT_CONCEPT_UNITS,
    build_cloud_recall_packet,
    build_concept_evidence_packet,
    build_concept_lifecycle_view,
    build_gap_evidence_packet,
    build_teaching_frame,
    compose_language_concepts,
    load_object_concepts,
    resolve_action_concepts,
    build_released_runtime_query_result,
    build_runtime_state_query_result,
    build_unsupported_runtime_query_result,
    request_cloud_concept_support,
    record_concept_fallback,
    record_concept_reuse,
    resolve_runtime_state_query,
)
from runtime_core import (
    MockRobotAdapter,
    P016Runtime,
    SerialEventQueue,
    read_json,
    run_runtime_sample,
    run_simulated_runtime_sample,
)
from embodied_scene import execute_command as execute_embodied_command
from embodied_scene import begin_motion_command as begin_embodied_motion
from embodied_scene import begin_teaching_control as begin_embodied_teaching_control
from embodied_scene import build_factory_concept_catalog, build_factory_object_catalog, build_factory_orchestrator_catalog, build_factory_state_fact_catalog, build_visual_concept_pack_catalog
from embodied_scene import begin_learned_replay as begin_embodied_learned_replay
from embodied_scene import begin_persisted_experience_replay as begin_embodied_persisted_replay
from embodied_scene import confirm_pending_motion as confirm_embodied_motion
from embodied_scene import evaluate_learned_replay as evaluate_embodied_learned_replay
from embodied_scene import finish_embodied_teaching as finish_embodied_teaching_session
from embodied_scene import get_session as get_embodied_session
from embodied_scene import list_embodied_scenes, load_scene as load_embodied_scene
from embodied_scene import set_stool as set_embodied_stool
from embodied_scene import set_protection_policy as set_embodied_protection_policy
from embodied_scene import set_perception_scenario as set_embodied_perception_scenario
from embodied_scene import start_session as start_embodied_session
from embodied_scene import start_embodied_teaching as start_embodied_teaching_session
from embodied_scene import record_teaching_signal as record_embodied_teaching_signal
from embodied_scene import step_motion_command as step_embodied_motion
from embodied_experience_store import load_trusted_experiences
from visual_concept_pipeline import (
    DeterministicImageProvider,
    HttpImageGenerationProvider,
    add_real_world_calibration,
    assess_concept_kernel_observation,
    compile_concept_kernel_candidate,
    create_production_batch,
    create_generation_request,
    execute_production_batch,
    execute_generation_request,
    get_pipeline_state,
    ingest_provider_images,
    promote_visual_candidate,
    promote_concept_kernel_candidate,
    release_kernel_candidate_generation,
    review_concept_kernel_candidate,
)
from qwen_visual_adapter import QwenVisualConceptAdapter
from concept_core.concept_teaching_station import (
    assess_concept_invariants,
    attach_concept_observation,
    finish_concept_teaching_session,
    get_concept_teaching_catalog,
    get_concept_teaching_session,
    start_concept_teaching_session,
)
from real_robot_service import (
    build_real_robot_readiness_catalog,
    dispatch_real_robot_stage,
    emergency_stop_real_robot_session,
    get_real_robot_session,
    heartbeat_real_robot_session,
    reset_real_robot_emergency_stop,
    set_real_robot_session_mode,
    start_real_robot_session,
)


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = int(os.environ.get("RELL_SAMPLE_PORT", "8876"))
SPACE_PRIOR_FILE = DATA / "digital_kitchen_semantic_prior.json"
COGNITIVE_MODEL_FILE = DATA / "digital_kitchen_cognitive_model.json"
CORRIDOR_COGNITIVE_MODEL_FILE = DATA / "digital_corridor_cognitive_model.json"
EXPERIENCE_LIBRARY_FILE = DATA / "experience_library.json"
CONCEPT_LIBRARY_FILE = DATA / "concept_library.json"
CONCEPT_CANDIDATE_LIBRARY_FILE = DATA / "concept_candidate_library.json"
PREFERENCE_LIBRARY_FILE = DATA / "preference_record_library.json"
RECOVERY_LIBRARY_FILE = DATA / "recovery_record_library.json"
P017_MINIMAL_LOOP_OUTPUT = ROOT.parent / "output" / "rell_sample" / "p017_minimal_loop"

TIMELINE_SCENARIOS = {
    "success": "mock_timeline_success.json",
    "no_flow": "mock_timeline_no_flow.json",
    "channel_conflict": "mock_timeline_channel_conflict.json",
}
SIMULATED_SCENARIOS = {"simulated_success", "simulated_no_water", "simulated_channel_conflict"}
SCENARIOS = {**TIMELINE_SCENARIOS, **{name: name for name in SIMULATED_SCENARIOS}}

TASK_LIBRARY = {
    "pour_water": {
        "display_name": "倒水",
        "process_template": "pour_water",
        "default_scenario": "simulated_success",
        "required_bindings": ["CUP_OBJECT", "KETTLE_OBJECT", "CAMERA_SENSOR", "POUR_OPERATION_REGION", "WALKABLE_REGION"],
    }
}

PROCESS_CHAIN_KEYWORDS = [
    ("move_to_doorway", ["走到门旁边", "到门旁边", "门旁边", "走到门口", "到门口", "门口"]),
    ("move_to_service_position", ["走到服务位", "到服务位", "服务位", "走到服务为", "到服务为", "服务为"]),
    ("move_to_counter", ["走向操作台", "走到操作台", "到操作台", "去操作台"]),
    ("pick_up_cup", ["拿起杯子", "拿杯子", "取杯子", "抓取杯子"]),
    ("move_to_water_source", ["到水源", "去水源", "走到水源", "水源处"]),
    ("fill_cup_at_water_source", ["接一杯水", "接水", "装水", "取水", "倒杯水"]),
    ("pour_water", ["倒水", "倒一杯水", "给客人倒水"]),
]

REGION_SEMANTIC_ALIASES = {
    "region_doorway": ["门旁边", "门口", "入口", "出入口"],
    "region_service_position": ["服务位", "服务为", "客人旁边", "客人位置", "服务位置"],
    "region_counter_operation": ["操作台", "台面", "工作台", "杯子处"],
    "region_water_source": ["水源处", "水源", "接水处", "水龙头"],
}

OBJECT_SEMANTIC_ALIASES = {
    "object_cup_white_mug": ["杯子", "杯", "水杯"],
    "object_kettle_steel_1l": ["水壶", "壶"],
}

DEFAULT_P012_CONCEPT_LIBRARY = {
    "concept_spatial_region_navigation": {
        "concept_id": "concept_spatial_region_navigation",
        "display_name": "空间目标导航概念",
        "concept_level": "action_way",
        "typical_action": "navigate_to_region",
        "typical_consequence": "executor_at_target_region",
        "usage": "公共空间能力，不作为具体任务经验入库",
        "capability_semantics": ["navigate_to_region"],
        "effect_contract": {
            "produces_facts": ["executor_at_bound_region"],
            "destroys_facts": ["executor_at_previous_region"],
            "state_transition": "executor_location_changes_to_bound_region",
        },
        "applicability_constraints": {
            "requires_space_binding": True,
            "supported_binding_types": ["semantic_region"],
            "required_runtime_facts": [],
            "forbidden_low_level_fields": ["absolute_coordinates", "joint_angles", "trajectory"],
        },
        "runtime_contingency_hints": [
            "路径受阻时回到编排层或局部避障能力，不由概念层直接改写运行时事实",
            "概念层只声明到达目标区域这一必要效果，不声明具体轨迹",
        ],
        "experience_link_policy": {
            "role": "公共能力概念",
            "direct_execution_allowed": False,
            "requires_orchestration": True,
            "preferred_backing": ["经验库", "P016过程模板", "执行层局部能力"],
        },
    },
    "concept_interactive_object_acquisition": {
        "concept_id": "concept_interactive_object_acquisition",
        "display_name": "可交互对象获取概念",
        "concept_level": "task_processing",
        "typical_action": "grasp_object",
        "typical_consequence": "object_in_gripper",
        "usage": "用于从当前空间中定位并获取任务对象",
        "capability_semantics": ["grasp_object"],
        "effect_contract": {
            "produces_facts": ["object_in_gripper"],
            "destroys_facts": ["gripper_empty", "object_at_original_region"],
            "state_transition": "target_object_moves_into_executor_gripper",
        },
        "applicability_constraints": {
            "requires_space_binding": True,
            "supported_binding_types": ["interactive_object"],
            "required_runtime_facts": ["gripper_empty"],
            "forbidden_low_level_fields": ["joint_angles", "gripper_pwm", "trajectory"],
        },
        "runtime_contingency_hints": [
            "对象不可达或抓取失败时输出不可执行或需补充教学，不由概念层臆造成功事实",
            "抓取姿态由执行层或本体局部能力决定，不写入概念层",
        ],
        "experience_link_policy": {
            "role": "对象交互概念",
            "direct_execution_allowed": False,
            "requires_orchestration": True,
            "preferred_backing": ["经验库", "执行层抓取器"],
        },
    },
    "concept_fillable_container": {
        "concept_id": "concept_fillable_container",
        "display_name": "可盛装容器概念",
        "concept_level": "object",
        "typical_action": "fill_container",
        "typical_consequence": "container_contains_liquid",
        "usage": "用于把不同杯子、容器映射到接水经验",
        "capability_semantics": ["fill_container"],
        "effect_contract": {
            "produces_facts": ["container_contains_target_liquid"],
            "destroys_facts": ["container_empty"],
            "state_transition": "target_container_changes_from_empty_to_filled",
        },
        "applicability_constraints": {
            "requires_space_binding": True,
            "supported_binding_types": ["fillable_container"],
            "required_runtime_facts": [],
            "forbidden_low_level_fields": ["fixed_execution_duration", "trajectory", "joint_angles"],
        },
        "runtime_contingency_hints": [
            "容器类型变化时由经验不变量契约重新绑定，不直接复用历史坐标和轨迹",
            "液位或出水状态应由运行时事实回传确认",
        ],
        "experience_link_policy": {
            "role": "对象语义概念",
            "direct_execution_allowed": False,
            "requires_orchestration": True,
            "preferred_backing": ["P017迁移适配", "经验库"],
        },
    },
    "concept_water_resource_zone": {
        "concept_id": "concept_water_resource_zone",
        "display_name": "水源资源区概念",
        "concept_level": "context",
        "typical_action": "use_resource_zone",
        "typical_consequence": "water_resource_available",
        "usage": "用于把不同空间中的水龙头、饮水机或水源点映射为资源区",
        "capability_semantics": ["use_resource_zone", "fill_container"],
        "effect_contract": {
            "produces_facts": ["water_resource_available"],
            "destroys_facts": [],
            "state_transition": "bound_resource_zone_can_supply_liquid",
        },
        "applicability_constraints": {
            "requires_space_binding": True,
            "supported_binding_types": ["semantic_region", "resource_zone"],
            "required_runtime_facts": [],
            "forbidden_low_level_fields": ["absolute_coordinates", "trajectory"],
        },
        "runtime_contingency_hints": [
            "资源区失效或观测冲突时应重新适配，不由概念层保持旧绑定",
            "概念层只声明资源角色，不声明底层阀门或传感器控制细节",
        ],
        "experience_link_policy": {
            "role": "空间资源概念",
            "direct_execution_allowed": False,
            "requires_orchestration": True,
            "preferred_backing": ["P010空间语义", "P017迁移适配"],
        },
    },
    "concept_liquid_transfer_task": {
        "concept_id": "concept_liquid_transfer_task",
        "display_name": "液体转移任务概念",
        "concept_level": "task_processing",
        "typical_action": "pour_container",
        "typical_consequence": "liquid_transferred",
        "usage": "具体倒水类任务经验，由经验库或 P016 过程模板承载",
        "capability_semantics": ["pour_container"],
        "effect_contract": {
            "produces_facts": ["liquid_transferred_to_target"],
            "destroys_facts": ["source_container_contains_liquid"],
            "state_transition": "liquid_moves_from_source_container_to_target",
        },
        "applicability_constraints": {
            "requires_space_binding": True,
            "supported_binding_types": ["task_goal", "interactive_object", "semantic_region"],
            "required_runtime_facts": ["source_container_contains_liquid"],
            "forbidden_low_level_fields": ["trajectory", "joint_angles", "raw_control_signal"],
        },
        "runtime_contingency_hints": [
            "具体倒水路线和容器姿态由经验层和执行层共同决定",
            "若运行时检测到液体未转移成功，应回传事实失败而非默认完成",
        ],
        "experience_link_policy": {
            "role": "任务概念",
            "direct_execution_allowed": False,
            "requires_orchestration": True,
            "preferred_backing": ["经验库", "P016过程模板", "P017迁移适配"],
        },
    },
}

AUDIT_STORE: dict[str, dict[str, Any]] = {}
STATE_STORE: dict[str, dict[str, Any]] = {}
TRACE_STORE: dict[str, dict[str, Any]] = {}
RUNTIME_WORLD_STATE_STORE: dict[str, dict[str, Any]] = {}
EXPERIENCE_GAP_STORE: dict[str, dict[str, Any]] = {}
READAPTATION_STORE: dict[str, dict[str, Any]] = {}
EXECUTION_DISPATCH_STORE: dict[str, dict[str, Any]] = {}
TEACHING_SESSION_STORE: dict[str, dict[str, Any]] = {}
CONCEPT_LIFECYCLE_STORE: dict[str, dict[str, Any]] = {}
CONCEPT_FALLBACK_STORE: dict[str, dict[str, Any]] = {}
GENERALIZATION_RESULT_STORE: dict[str, dict[str, Any]] = {}
PHYSICS_SESSION_STORE: dict[str, dict[str, Any]] = {}


STEP_LIBRARY = {
    "move_to_doorway": {
        "display_name": "走到门旁边",
        "capability": "navigate_to_region",
        "target_region": "region_doorway",
        "requires_facts": [],
        "produces_fact": "executor_at_doorway",
        "destroys_facts": ["executor_at_counter", "executor_at_water_source", "executor_at_service_position"],
    },
    "move_to_service_position": {
        "display_name": "走到服务位",
        "capability": "navigate_to_region",
        "target_region": "region_service_position",
        "requires_facts": [],
        "produces_fact": "executor_at_service_position",
        "destroys_facts": ["executor_at_counter", "executor_at_water_source", "executor_at_doorway"],
    },
    "move_to_counter": {
        "display_name": "走向操作台",
        "capability": "navigate_to_region",
        "target_region": "region_counter_operation",
        "requires_facts": [],
        "produces_fact": "executor_at_counter",
        "destroys_facts": ["executor_at_water_source", "executor_at_doorway", "executor_at_service_position"],
    },
    "pick_up_cup": {
        "display_name": "拿起杯子",
        "capability": "grasp_object",
        "target_object": "object_cup_white_mug",
        "requires_facts": ["executor_at_counter", "cup_at_counter", "gripper_empty"],
        "produces_fact": "cup_in_gripper",
        "destroys_facts": ["cup_at_counter", "gripper_empty"],
    },
    "move_to_water_source": {
        "display_name": "到水源处",
        "capability": "navigate_to_region",
        "target_region": "region_water_source",
        "requires_facts": [],
        "produces_fact": "executor_at_water_source",
        "destroys_facts": ["executor_at_counter", "executor_at_doorway", "executor_at_service_position"],
    },
    "fill_cup_at_water_source": {
        "display_name": "接一杯水",
        "capability": "fill_container",
        "target_region": "region_water_source",
        "requires_facts": ["cup_in_gripper", "executor_at_water_source", "water_source_available"],
        "produces_fact": "cup_contains_water",
        "destroys_facts": ["cup_empty"],
    },
    "pour_water": {
        "display_name": "倒水",
        "capability": "pour_container",
        "target_region": "region_counter_operation",
        "requires_facts": ["cup_in_gripper", "cup_contains_water", "executor_at_counter"],
        "produces_fact": "water_poured",
        "destroys_facts": ["cup_contains_water"],
    },
}

RUNTIME_PERTURBATION_TEMPLATES = {
    "stool_in_walkway_detourable": {
        "label": "过道出现可绕开的凳子",
        "effect_type": "navigation_detour",
        "blocking_level": "soft",
        "detour_available": True,
        "target_steps": ["move_to_counter", "move_to_water_source", "pour_water"],
        "target_regions": ["region_counter_operation", "region_water_source"],
        "recommended_actions": ["detour_and_continue", "refresh_runtime_snapshot_after_step"],
    },
    "stool_blocks_walkway": {
        "label": "过道被凳子完全阻塞",
        "effect_type": "route_block",
        "blocking_level": "hard",
        "detour_available": False,
        "target_steps": ["move_to_counter", "move_to_water_source", "pour_water"],
        "target_regions": ["region_counter_operation", "region_water_source"],
        "recommended_actions": ["trigger_readaptation", "request_human_confirmation", "trigger_supplemental_teaching"],
    },
    "cup_guard_door_closed": {
        "label": "杯子取用位置前的门处于关闭状态",
        "effect_type": "interaction_barrier",
        "blocking_level": "hard",
        "detour_available": False,
        "target_steps": ["pick_up_cup"],
        "target_regions": ["region_counter_operation"],
        "recommended_actions": ["trigger_readaptation", "request_human_confirmation", "trigger_supplemental_teaching"],
    },
    "water_source_door_closed": {
        "label": "水源区前的门处于关闭状态",
        "effect_type": "interaction_barrier",
        "blocking_level": "hard",
        "detour_available": False,
        "target_steps": ["move_to_water_source", "fill_cup_at_water_source"],
        "target_regions": ["region_water_source"],
        "recommended_actions": ["trigger_readaptation", "request_human_confirmation", "search_alternative_experience"],
    },
}


GOAL_FACT_KEYWORDS = [
    ("water_poured", ["倒水", "倒一杯水", "给客人倒水"]),
    ("cup_contains_water", ["接一杯水", "接水", "装水", "取水", "杯子里有水", "杯中有水", "弄杯水", "倒杯水"]),
]

TEACHING_PREFIX_KEYWORDS = ["教你", "我教你", "现在教你", "按我说", "记住这个动作", "记住这个流程"]
CLARIFICATION_KEYWORDS = ["为什么", "为何", "为啥", "原因", "怎么回事"]
CLARIFICATION_TARGET_KEYWORDS = ["不能执行", "不会做", "失败", "冲突", "没成功", "没完成", "不可执行"]
DEICTIC_OBJECT_KEYWORDS = ["那个", "这个", "那本", "这本", "那个东西", "这个东西"]
AMBIGUOUS_ACTION_KEYWORDS = ["弄一下", "处理一下", "搞一下", "安排一下"]
WEAK_DIRECTION_KEYWORDS = ["右边", "左边", "前面", "后面", "那边", "这边"]
INTERRUPT_TASK_KEYWORDS = ["别做了", "先别做", "暂停", "停止", "停下", "取消", "先不要"]
TASK_SWITCH_SIGNAL_KEYWORDS = ["去", "拿", "取", "给", "帮", "送", "放", "搬", "找", "削", "做", "倒", "接"]
LLM_FORBIDDEN_OUTPUT_FIELDS = {
    "absolute_coordinates",
    "joint_angles",
    "trajectory",
    "trajectory_points",
    "low_level_motor_command",
    "motor_command",
    "raw_control_signal",
    "runtime_world_state",
    "runtime_world_state_snapshot",
    "established_facts",
    "object_locations",
    "release_status",
    "release_token",
}
LLM_ALLOWED_CANDIDATE_TYPES = {"intent_frame_patch", "candidate_plan", "clarification_answer"}


def infer_goal_fact(text: str) -> str | None:
    for goal_fact, keywords in GOAL_FACT_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return goal_fact
    return None


def looks_like_new_task_request(utterance: str) -> bool:
    text = (utterance or "").strip()
    if not text:
        return False
    return any(keyword in text for keyword in TASK_SWITCH_SIGNAL_KEYWORDS)


def extract_replacement_task_text(utterance: str) -> str:
    text = (utterance or "").strip()
    for keyword in INTERRUPT_TASK_KEYWORDS:
        text = text.replace(keyword, " ")
    return re.sub(r"^[，,。；;\s]+|[，,。；;\s]+$", "", text)


def infer_goal_fact_from_detected_steps(detected_steps: list[str]) -> str | None:
    if not detected_steps:
        return None
    last_step = detected_steps[-1]
    return STEP_LIBRARY.get(last_step, {}).get("produces_fact")


def _find_alias_mentions(text: str, aliases: list[str]) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    occupied: list[range] = []
    for alias in sorted(aliases, key=len, reverse=True):
        start = text.find(alias)
        while start >= 0:
            end = start + len(alias)
            if not any(start < span.stop and end > span.start for span in occupied):
                mentions.append({"text": alias, "start": start, "end": end})
                occupied.append(range(start, end))
            start = text.find(alias, end)
    return sorted(mentions, key=lambda item: item["start"])


def extract_spatial_constraints(text: str, cognitive_model: dict[str, Any]) -> list[dict[str, Any]]:
    region_index = {item["region_id"]: item for item in cognitive_model.get("space_region_table", [])}
    constraints: list[dict[str, Any]] = []
    for region_id, aliases in REGION_SEMANTIC_ALIASES.items():
        region = region_index.get(region_id)
        if not region:
            continue
        for mention in _find_alias_mentions(text, aliases):
            constraints.append(
                {
                    "constraint_type": "spatial_target",
                    "region_ref": region_id,
                    "region_type": region.get("region_type"),
                    "function_attributes": region.get("function_attributes", []),
                    "permission": region.get("permission"),
                    "source_text": mention["text"],
                    "text_span": [mention["start"], mention["end"]],
                    "concept_tag": "concept_spatial_region_navigation",
                    "required_capability": "navigate_to_region",
                    "binding_source": "p010_subject_cognitive_model",
                }
            )
    constraints.sort(key=lambda item: item["text_span"][0])
    return constraints


def extract_object_constraints(text: str, cognitive_model: dict[str, Any]) -> list[dict[str, Any]]:
    object_index = cognitive_model.get("object_region_index", {})
    constraints: list[dict[str, Any]] = []
    for object_id, aliases in OBJECT_SEMANTIC_ALIASES.items():
        obj = object_index.get(object_id, {})
        for mention in _find_alias_mentions(text, aliases):
            concept_tag = "concept_fillable_container" if "receive_liquid" in obj.get("affordances", []) else "concept_interactive_object_acquisition"
            constraints.append(
                {
                    "constraint_type": "object_target",
                    "object_ref": object_id,
                    "object_type": obj.get("object_type"),
                    "region_ref": obj.get("region_ref"),
                    "affordances": obj.get("affordances", []),
                    "state_facts": obj.get("state_facts", []),
                    "source_text": mention["text"],
                    "text_span": [mention["start"], mention["end"]],
                    "concept_tag": concept_tag,
                    "binding_source": "p010_subject_cognitive_model",
                }
            )
    constraints.sort(key=lambda item: item["text_span"][0])
    merged: dict[str, dict[str, Any]] = {}
    for item in constraints:
        object_ref = item["object_ref"]
        if object_ref not in merged:
            merged[object_ref] = dict(item)
            merged[object_ref]["source_mentions"] = [item["source_text"]]
            continue
        merged[object_ref]["source_mentions"].append(item["source_text"])
        merged[object_ref]["source_text"] = "/".join(dict.fromkeys(merged[object_ref]["source_mentions"]))
    return list(merged.values())


def build_concept_unit_view(
    concept: dict[str, Any],
    activation_reason: str,
    runtime_context_view: dict[str, Any] | None = None,
) -> dict[str, Any]:
    executable_capabilities = {
        item.get("capability")
        for item in (runtime_context_view or {}).get("available_actions_now", [])
        if item.get("capability")
    }
    blocked_capabilities = {
        item.get("capability")
        for item in (runtime_context_view or {}).get("blocked_actions", [])
        if item.get("capability")
    }
    capability_semantics = concept.get("capability_semantics", [])
    currently_executable = sorted(cap for cap in capability_semantics if cap in executable_capabilities)
    currently_blocked = sorted(cap for cap in capability_semantics if cap in blocked_capabilities)
    runtime_binding_status = {
        "status": "semantic_only",
        "currently_executable_capabilities": currently_executable,
        "currently_blocked_capabilities": currently_blocked,
        "requires_orchestration": True,
    }
    if runtime_context_view:
        runtime_binding_status.update(
            {
                "status": "runtime_snapshot_attached",
                "runtime_world_state_snapshot_id": runtime_context_view.get("task_context", {}).get("runtime_world_state_snapshot_id"),
                "goal_fact": runtime_context_view.get("task_context", {}).get("goal_fact"),
            }
        )
    match_basis = ["semantic_constraint_match", "concept_library_unit_match"]
    if runtime_context_view:
        match_basis.append("runtime_snapshot_binding")
    if concept.get("derived_from_experiences"):
        match_basis.append("experience_backed_promoted_concept")
    return {
        "concept_id": concept["concept_id"],
        "display_name": concept["display_name"],
        "concept_level": concept["concept_level"],
        "typical_action": concept.get("typical_action"),
        "typical_consequence": concept.get("typical_consequence"),
        "usage": concept.get("usage"),
        "capability_semantics": capability_semantics,
        "effect_contract": concept.get("effect_contract", {}),
        "applicability_constraints": concept.get("applicability_constraints", {}),
        "runtime_contingency_hints": concept.get("runtime_contingency_hints", []),
        "experience_link_policy": concept.get("experience_link_policy", {}),
        "activation_reason": activation_reason,
        "formation_basis": "情境描述信息、空间语义、对象约束和目标因果事实共同约束；当前样品先以轻量规则抽取候选概念，后续由交互经验记录持续更新",
        "runtime_binding_status": runtime_binding_status,
        "direct_execution_allowed": False,
        "concept_evidence": build_concept_evidence_packet(
            concept,
            concept_type="semantic_concept",
            activation_reason=activation_reason,
            match_basis=match_basis,
            confidence=0.84 if runtime_context_view else 0.8,
            runtime_context_view=runtime_context_view,
        ),
    }


def build_concept_matches(
    text: str,
    goal_fact: str | None,
    spatial_constraints: list[dict[str, Any]],
    object_constraints: list[dict[str, Any]],
    detected_steps: list[str],
    runtime_context_view: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    concept_reasons: dict[str, str] = {}
    if spatial_constraints:
        concept_reasons["concept_spatial_region_navigation"] = "输入中包含显式空间目标，需要复用公共空间导航概念"
    if any(item.get("object_ref") == "object_cup_white_mug" for item in object_constraints):
        concept_reasons["concept_interactive_object_acquisition"] = "输入中包含可交互对象，需要定位并获取任务对象"
        concept_reasons["concept_fillable_container"] = "输入中包含杯子或容器，需要以容器语义承接接水经验"
    if any(item.get("region_ref") == "region_water_source" for item in spatial_constraints) or goal_fact == "cup_contains_water":
        concept_reasons["concept_water_resource_zone"] = "目标事实或空间语义指向水源资源区，需要绑定资源区域语义"
    if goal_fact == "water_poured" or "pour_water" in detected_steps:
        concept_reasons["concept_liquid_transfer_task"] = "目标涉及液体转移，需要由任务概念连接经验层与执行层"

    concept_index = get_concept_library_index()
    matches: list[dict[str, Any]] = []
    for concept_id, reason in concept_reasons.items():
        concept = concept_index.get(concept_id)
        if not concept:
            continue
        matches.append(build_concept_unit_view(concept, reason, runtime_context_view=runtime_context_view))
    for concept in concept_index.values():
        promotion_tags = concept.get("promotion_tags", {})
        if concept.get("concept_id") in concept_reasons:
            continue
        if not promotion_tags:
            continue
        promoted_goal_fact = promotion_tags.get("goal_fact")
        promoted_process_chain = promotion_tags.get("process_chain", [])
        goal_fact_matches = bool(goal_fact and promoted_goal_fact == goal_fact)
        process_overlap = [step for step in detected_steps if step in promoted_process_chain]
        if goal_fact_matches or process_overlap:
            reason_parts = []
            if goal_fact_matches:
                reason_parts.append("已晋升概念的目标事实与当前任务一致")
            if process_overlap:
                reason_parts.append("已晋升概念的过程链与当前输入存在重合步骤")
            matches.append(
                build_concept_unit_view(
                    concept,
                    "；".join(reason_parts),
                    runtime_context_view=runtime_context_view,
                )
            )
    return matches


def build_sequence_constraints(spatial_constraints: list[dict[str, Any]], detected_steps: list[str]) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = []
    for index, item in enumerate(spatial_constraints, start=1):
        constraints.append(
            {
                "order": index,
                "constraint_type": "explicit_spatial_waypoint",
                "target_ref": item["region_ref"],
                "source_text": item["source_text"],
                "required_capability": item["required_capability"],
            }
        )
    if detected_steps:
        constraints.append(
            {
                "order": len(constraints) + 1,
                "constraint_type": "detected_process_order",
                "process_chain": detected_steps,
            }
        )
    return constraints


def build_activation_constraint(text: str) -> dict[str, Any]:
    immediate_markers = [marker for marker in ["现在", "马上", "立即"] if marker in text]
    return {
        "mode": "immediate" if immediate_markers else "default",
        "mention_status": "explicit" if immediate_markers else "implicit",
        "source_text": immediate_markers[0] if immediate_markers else None,
        "arbitration_policy": "enter_p018_runtime_event_arbitration_before_execution",
    }


def build_intent_frame(text: str, cognitive_model: dict[str, Any]) -> dict[str, Any]:
    language_composition = compose_language_concepts(
        text,
        event_concepts=FACTORY_EVENT_CONCEPT_UNITS,
        object_concepts=load_object_concepts()["concepts"],
    )
    interpretation_text = (
        language_composition.get("canonical_utterance")
        if language_composition.get("decision") == "route_canonical_semantics" and language_composition.get("canonical_utterance")
        else text
    )
    detected_steps = detect_process_chain(interpretation_text)
    goal_fact = infer_goal_fact(interpretation_text)
    spatial_constraints = extract_spatial_constraints(text, cognitive_model)
    object_constraints = extract_object_constraints(text, cognitive_model)
    action_concepts = resolve_action_concepts(
        interpretation_text,
        detected_steps,
        normalize_text_fn=normalize_text,
        object_constraints=object_constraints,
        spatial_constraints=spatial_constraints,
        current_facts=sorted(build_world_state_facts(cognitive_model)),
        runtime_context_view=None,
    )
    concept_matches = build_concept_matches(text, goal_fact, spatial_constraints, object_constraints, detected_steps)
    return {
        "schema_version": "1.0.0",
        "translation_mode": "p012_concept_bridge_v1",
        "utterance": text,
        "language_composition": language_composition,
        "interpretation_text": interpretation_text,
        "goal_fact": goal_fact,
        "activation_constraint": build_activation_constraint(text),
        "explicit_process_chain": detected_steps,
        "action_concepts": action_concepts,
        "spatial_constraints": spatial_constraints,
        "object_constraints": object_constraints,
        "concept_matches": concept_matches,
        "sequence_constraints": build_sequence_constraints(spatial_constraints, detected_steps),
        "world_state_facts": sorted(build_world_state_facts(cognitive_model)),
        "planning_policy": {
            "llm_role": "仅生成结构化候选语义，不直接绕过空间语义、概念层和因果层生成最终动作链",
            "space_binding": "空间目标必须回到 P010 主体侧空间认知模型进行绑定",
            "concept_transfer": "公共空间能力由概念层复用，具体任务经验由经验库或 P016 过程模板承载",
        },
    }


def build_semantic_request_frame(
    text: str,
    cognitive_model: dict[str, Any],
    task_id: str | None = None,
    intent_frame: dict[str, Any] | None = None,
) -> dict[str, Any]:
    utterance = (text or "").strip()
    normalized = normalize_text(utterance)
    intent_frame = intent_frame if intent_frame is not None else (build_intent_frame(utterance, cognitive_model) if utterance else None)
    runtime_query = parse_runtime_query(utterance) if utterance else {"query_type": "unsupported"}
    request_type = "task_execution"
    route_reason = "默认按任务执行处理"
    interrupt_requested = bool(task_id and any(keyword in utterance for keyword in INTERRUPT_TASK_KEYWORDS))

    if not utterance:
        request_type = "unknown"
        route_reason = "输入为空"
    elif any(keyword in utterance for keyword in TEACHING_PREFIX_KEYWORDS):
        request_type = "teaching"
        route_reason = "命中教学前缀，进入教学语义路由"
    elif runtime_query.get("query_type") != "unsupported":
        request_type = "state_query"
        route_reason = "命中状态查询模式，进入当前任务快照查询路由"
    elif any(keyword in utterance for keyword in CLARIFICATION_KEYWORDS) and any(keyword in utterance for keyword in CLARIFICATION_TARGET_KEYWORDS):
        request_type = "clarification"
        route_reason = "命中解释性问题模式，进入执行原因说明路由"

    semantic_request_id = "semantic_" + hashlib.sha1(
        "|".join([normalized, task_id or "none", request_type]).encode("utf-8")
    ).hexdigest()[:12]
    complexity_score = len(utterance) + max(0, len(intent_frame.get("explicit_process_chain", [])) * 8) if intent_frame else len(utterance)
    preferred_model_tier = "llm_escalatable" if complexity_score >= 36 or utterance.count("，") + utterance.count(",") >= 2 else "rule_router_only"
    confidence = 0.92
    confidence_reasons: list[str] = []
    alternative_interpretations: list[dict[str, Any]] = []
    clarification_needed = False
    clarification_reason = None
    task_switch_candidate = False

    if request_type == "unknown":
        confidence = 0.05
        clarification_needed = True
        clarification_reason = "empty_input"
        confidence_reasons.append("输入为空，无法判断任务类型")
    elif request_type == "state_query":
        confidence = 0.96
        confidence_reasons.append("命中当前任务期运行时世界状态快照查询模式")
    elif request_type == "clarification":
        confidence = 0.94
        confidence_reasons.append("命中执行原因说明模式")
    elif request_type == "teaching":
        parsed_steps = parse_teaching_steps(utterance)
        confidence = 0.9 if parsed_steps else 0.62
        confidence_reasons.append("命中教学前缀")
        if not parsed_steps:
            clarification_needed = True
            clarification_reason = "teaching_step_not_parsed"
            confidence_reasons.append("教学输入未解析出明确步骤，需要补充更具体示教")
    else:
        if interrupt_requested:
            confidence = 0.97
            clarification_needed = False
            clarification_reason = None
            confidence_reasons.append("命中活动任务运行时中断词，需优先回到事件仲裁层")
        object_constraints = intent_frame.get("object_constraints", []) if intent_frame else []
        spatial_constraints = intent_frame.get("spatial_constraints", []) if intent_frame else []
        detected_steps = intent_frame.get("explicit_process_chain", []) if intent_frame else []
        concept_matches = intent_frame.get("concept_matches", []) if intent_frame else []
        task_switch_candidate = bool(
            task_id
            and not interrupt_requested
            and not detected_steps
            and not concept_matches
            and not object_constraints
            and not spatial_constraints
            and looks_like_new_task_request(utterance)
        )
        if task_switch_candidate:
            confidence = max(confidence, 0.88)
            clarification_needed = False
            clarification_reason = None
            confidence_reasons.append("命中活动任务中的新目标切换表达，需先进入事件仲裁并保留当前持物状态")
        if any(token in utterance for token in DEICTIC_OBJECT_KEYWORDS):
            confidence -= 0.22
            clarification_needed = True
            clarification_reason = "deictic_object_without_shared_reference"
            confidence_reasons.append("存在“那个/这本”等指称，但当前缺少共享指认")
            alternative_interpretations.append(
                {
                    "type": "clarification_needed",
                    "reason": "需要补充对象颜色、位置或名称等共享参照",
                }
            )
        if any(token in utterance for token in AMBIGUOUS_ACTION_KEYWORDS):
            confidence -= 0.18
            clarification_needed = True
            clarification_reason = clarification_reason or "ambiguous_action_phrase"
            confidence_reasons.append("动作表述过于笼统，无法直接映射为稳定任务语义")
        if any(token in utterance for token in WEAK_DIRECTION_KEYWORDS) and not spatial_constraints:
            confidence -= 0.16
            clarification_needed = True
            clarification_reason = clarification_reason or "direction_reference_not_grounded"
            confidence_reasons.append("出现方位描述，但当前未成功绑定到空间语义参照")
        if not interrupt_requested and not task_switch_candidate and not detected_steps and not concept_matches:
            confidence -= 0.2
            clarification_needed = True
            clarification_reason = clarification_reason or "no_process_or_concept_match"
            confidence_reasons.append("既未解析出显式过程链，也未命中概念层候选")
        if object_constraints:
            confidence_reasons.append("已识别任务对象约束")
        if spatial_constraints:
            confidence_reasons.append("已识别空间约束")
        if detected_steps:
            confidence_reasons.append("已识别显式过程链或步骤顺序")
        elif concept_matches:
            confidence_reasons.append("虽未识别显式步骤，但已命中概念层候选，可回编排层判断")
        if len(detected_steps) > 1 and not any(marker in utterance for marker in ["然后", "再", "接着", "之后", "先"]):
            confidence -= 0.08
            confidence_reasons.append("检测到多步动作，但自然语言顺序标记较弱")

    confidence = max(0.05, min(round(confidence, 2), 0.99))
    teaching_frame = None
    if request_type == "teaching":
        teaching_frame = build_teaching_frame(
            utterance,
            parse_teaching_steps_fn=parse_teaching_steps,
            infer_goal_fact_fn=infer_goal_fact,
            normalize_text_fn=normalize_text,
        )

    return {
        "schema_version": "1.0.0",
        "semantic_request_id": semantic_request_id,
        "utterance": utterance,
        "task_id": task_id,
        "request_type": request_type,
        "route_reason": route_reason,
        "router_version": "semantic_router_v1",
        "preferred_model_tier": preferred_model_tier,
        "llm_escalation_allowed": True,
        "intent_confidence": confidence,
        "clarification_needed": clarification_needed,
        "clarification_reason": clarification_reason,
        "interrupt_requested": interrupt_requested,
        "task_switch_candidate": task_switch_candidate,
        "confidence_reasons": confidence_reasons,
        "alternative_interpretations": alternative_interpretations,
        "intent_frame": intent_frame,
        "runtime_query": runtime_query if request_type == "state_query" else None,
        "teaching_plan": {
            "parsed_steps": teaching_frame.get("parsed_steps", []) if teaching_frame else parse_teaching_steps(utterance),
            "teaching_frame": teaching_frame,
            "recommended_endpoint": "/experience/dialogue-teach",
        } if request_type == "teaching" else None,
    }


def build_world_state_facts(cognitive_model: dict[str, Any]) -> set[str]:
    regions = {item["region_id"] for item in cognitive_model.get("space_region_table", [])}
    objects = cognitive_model.get("object_region_index", {})
    bindings = cognitive_model.get("binding_candidates", {})
    facts = {"executor_at_floor_walkway", "gripper_empty"}
    water_source_region = bindings.get("TARGET_LIQUID_SOURCE_REGION") or "region_water_source"
    if water_source_region in regions:
        facts.add("water_source_available")
    cup_ref = bindings.get("TARGET_GRASPABLE_CONTAINER") or "object_cup_white_mug"
    operation_region = bindings.get("TARGET_OPERATION_REGION") or "region_counter_operation"
    cup = objects.get(cup_ref, {})
    if cup.get("region_ref") in {"region_cup_station", operation_region}:
        facts.add("cup_at_counter")
    if "cup_empty" in cup.get("state_facts", []):
        facts.add("cup_empty")
    kettle = objects.get("object_kettle_steel_1l", {})
    if "kettle_has_water" in kettle.get("state_facts", []):
        facts.add("kettle_has_water")
    return facts


def build_initial_runtime_world_state(cognitive_model: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
    object_index = cognitive_model.get("object_region_index", {})
    fact_set = sorted(build_world_state_facts(cognitive_model))
    preference_resolution = resolve_preferences_for_intent(intent, cognitive_model)
    object_locations = {
        object_id: {
            "location_type": "region",
            "location_ref": obj.get("region_ref"),
            "state_facts": obj.get("state_facts", []),
        }
        for object_id, obj in object_index.items()
    }
    return {
        "schema_version": "1.0.0",
        "lifecycle": "ephemeral_task_memory",
        "snapshot_lifecycle_state": "active",
        "release_status": "not_released",
        "release_token": None,
        "persistence_policy": "任务执行期间端侧生成和更新；任务结束后仅关键事件进入 trace 和经验记录，不作为长期世界数据库保存",
        "source_layers": ["p010_subject_cognitive_model", "adapter_observation_stream", "p016_fact_transition"],
        "task_ref": intent.get("experience_id") or intent.get("candidate_process"),
        "executor": {
            "location_type": "region",
            "location_ref": cognitive_model.get("binding_candidates", {}).get("INITIAL_EXECUTOR_REGION", "region_floor_walkway"),
            "holding": [],
        },
        "object_locations": object_locations,
        "established_facts": fact_set,
        "current_stage": None,
        "completed_stages": [],
        "preference_context": {
            "context_ref": preference_resolution.get("context_ref"),
            "scope_tags": preference_resolution.get("scope_tags", []),
            "resolution_policy": "human_preference_records_are_loaded_as_runtime_constraints_without_rewriting_experience_or_concept_layers",
        },
        "active_preferences": preference_resolution.get("preference_records", []),
        "runtime_environment": {
            "active_perturbations": [],
            "scheduled_perturbations": [],
            "perturbation_history": [],
            "last_preflight": None,
            "last_route_adjustment": None,
            "last_blocked_step": None,
        },
    }


def clone_runtime_world_state(state: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(state, ensure_ascii=False))


def get_active_runtime_snapshot(task_id: str | None) -> dict[str, Any] | None:
    if not task_id:
        return None
    current = get_runtime_world_state(task_id)
    if "error" in current:
        return None
    snapshot = current.get("runtime_world_state_snapshot") or {}
    if snapshot.get("release_status") == "released":
        return None
    return snapshot


def ensure_runtime_environment(state: dict[str, Any]) -> dict[str, Any]:
    env = state.setdefault("runtime_environment", {})
    env.setdefault("active_perturbations", [])
    env.setdefault("scheduled_perturbations", [])
    env.setdefault("perturbation_history", [])
    env.setdefault("last_preflight", None)
    env.setdefault("last_route_adjustment", None)
    env.setdefault("last_blocked_step", None)
    return env


def normalize_runtime_perturbation(
    perturbation: dict[str, Any],
    apply_before_step: str | None = None,
) -> dict[str, Any]:
    kind = str(perturbation.get("kind") or perturbation.get("perturbation_type") or "").strip()
    if kind not in RUNTIME_PERTURBATION_TEMPLATES:
        return {"error": "unsupported_runtime_perturbation", "kind": kind, "allowed_kinds": sorted(RUNTIME_PERTURBATION_TEMPLATES)}
    template = RUNTIME_PERTURBATION_TEMPLATES[kind]
    seed = "|".join([kind, apply_before_step or "immediate", json.dumps(perturbation, ensure_ascii=False, sort_keys=True)])
    perturbation_id = "perturb_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    record = {
        "perturbation_id": perturbation_id,
        "kind": kind,
        "label": perturbation.get("label") or template["label"],
        "effect_type": perturbation.get("effect_type") or template["effect_type"],
        "blocking_level": perturbation.get("blocking_level") or template["blocking_level"],
        "detour_available": bool(perturbation.get("detour_available", template["detour_available"])),
        "target_steps": list(perturbation.get("target_steps") or template["target_steps"]),
        "target_regions": list(perturbation.get("target_regions") or template["target_regions"]),
        "recommended_actions": list(perturbation.get("recommended_actions") or template["recommended_actions"]),
        "apply_before_step": apply_before_step,
        "status": "scheduled" if apply_before_step else "active",
        "notes": perturbation.get("notes"),
        "source": perturbation.get("source", "runtime_test_injection"),
        "created_at": "2026-07-10T00:00:00+08:00",
    }
    return record


def runtime_perturbation_applies_to_step(perturbation: dict[str, Any], step: str, meta: dict[str, Any]) -> bool:
    if step in set(perturbation.get("target_steps", [])):
        return True
    target_region = meta.get("target_region")
    if target_region and target_region in set(perturbation.get("target_regions", [])):
        return True
    return False


def activate_scheduled_perturbations_for_step(state: dict[str, Any], step: str) -> list[dict[str, Any]]:
    env = ensure_runtime_environment(state)
    activated: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    for item in env.get("scheduled_perturbations", []):
        if item.get("apply_before_step") == step:
            item["status"] = "active"
            activated.append(item)
            env["active_perturbations"].append(item)
            env["perturbation_history"].append(
                {
                    "event": "activated_before_step",
                    "step": step,
                    "perturbation_id": item.get("perturbation_id"),
                    "kind": item.get("kind"),
                }
            )
        else:
            remaining.append(item)
    env["scheduled_perturbations"] = remaining
    return activated


def evaluate_runtime_step_preflight(state: dict[str, Any], step: str, meta: dict[str, Any]) -> dict[str, Any]:
    env = ensure_runtime_environment(state)
    activated = activate_scheduled_perturbations_for_step(state, step)
    relevant = [
        item
        for item in env.get("active_perturbations", [])
        if runtime_perturbation_applies_to_step(item, step, meta)
    ]
    hard_blockers = [item for item in relevant if item.get("blocking_level") == "hard" or not item.get("detour_available", False)]
    if hard_blockers:
        result = {
            "result": "blocked",
            "step": step,
            "activated_perturbations": activated,
            "blocking_perturbations": hard_blockers,
            "recommended_actions": sorted({action for item in hard_blockers for action in item.get("recommended_actions", [])}),
            "reason": "runtime_environment_changed_and_step_requires_re_adaptation",
        }
        env["last_preflight"] = result
        env["last_blocked_step"] = step
        return result
    detours = [item for item in relevant if item.get("effect_type") == "navigation_detour" and item.get("detour_available")]
    if detours:
        adjustment = {
            "adjustment_type": "local_detour",
            "step": step,
            "preserved_process_chain": True,
            "detour_basis": [item.get("perturbation_id") for item in detours],
            "reason": "runtime_environment_changed_but_local_navigation_can_detour",
        }
        result = {
            "result": "detour",
            "step": step,
            "activated_perturbations": activated,
            "route_adjustment": adjustment,
            "recommended_actions": ["continue_execution", "refresh_runtime_snapshot_after_step"],
        }
        env["last_preflight"] = result
        env["last_route_adjustment"] = adjustment
        return result
    result = {
        "result": "executable",
        "step": step,
        "activated_perturbations": activated,
        "recommended_actions": ["continue_execution"],
    }
    env["last_preflight"] = result
    return result


def build_dynamic_environment_blockers(
    runtime_world_state: dict[str, Any],
    steps: list[str],
) -> list[dict[str, Any]]:
    env = ensure_runtime_environment(runtime_world_state)
    reasons: list[dict[str, Any]] = []
    for step in steps:
        meta = STEP_LIBRARY.get(step, {})
        for item in env.get("active_perturbations", []):
            if not runtime_perturbation_applies_to_step(item, step, meta):
                continue
            if item.get("blocking_level") == "hard" or not item.get("detour_available", False):
                reasons.append(
                    {
                        "reason": "dynamic_environment_blocker",
                        "step": step,
                        "perturbation_id": item.get("perturbation_id"),
                        "perturbation_kind": item.get("kind"),
                        "blocking_level": item.get("blocking_level"),
                    }
                )
    return reasons


def inject_runtime_perturbation(
    task_id: str,
    perturbation: dict[str, Any],
    apply_before_step: str | None = None,
) -> dict[str, Any]:
    current = get_runtime_world_state(task_id)
    if "error" in current:
        return current
    state = current["runtime_world_state_snapshot"]
    env = ensure_runtime_environment(state)
    record = normalize_runtime_perturbation(perturbation, apply_before_step)
    if "error" in record:
        return record
    if record.get("status") == "scheduled":
        env["scheduled_perturbations"].append(record)
        env["perturbation_history"].append(
            {
                "event": "scheduled",
                "perturbation_id": record.get("perturbation_id"),
                "kind": record.get("kind"),
                "apply_before_step": apply_before_step,
            }
        )
    else:
        env["active_perturbations"].append(record)
        env["perturbation_history"].append(
            {
                "event": "activated_immediately",
                "perturbation_id": record.get("perturbation_id"),
                "kind": record.get("kind"),
            }
        )
    RUNTIME_WORLD_STATE_STORE[task_id] = state
    if task_id in STATE_STORE:
        STATE_STORE[task_id]["runtime_world_state"] = state
    return {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "runtime_world_state_snapshot_id": state.get("runtime_world_state_snapshot_id"),
        "injected_perturbation": record,
        "runtime_environment": env,
        "runtime_world_state_snapshot": state,
    }


def apply_step_to_runtime_world_state(
    state: dict[str, Any], step: str, meta: dict[str, Any], sequence: int, binding: dict[str, Any] | None = None
) -> dict[str, Any]:
    before = clone_runtime_world_state(state)
    facts = set(state.get("established_facts", []))
    missing_before = [fact for fact in meta.get("requires_facts", []) if fact not in facts]

    for fact in meta.get("destroys_facts", []):
        facts.discard(fact)
    facts.add(meta["produces_fact"])

    bound_region = (binding or {}).get("space_binding", {}).get("target_ref") or meta.get("target_region")
    bound_object = (binding or {}).get("object_binding", {}).get("target_ref") or meta.get("target_object")
    if meta.get("capability") == "navigate_to_region" and bound_region:
        state["executor"]["location_type"] = "region"
        state["executor"]["location_ref"] = bound_region
    elif step == "pick_up_cup":
        object_id = bound_object or "object_cup_white_mug"
        if object_id not in state["executor"]["holding"]:
            state["executor"]["holding"].append(object_id)
        state["object_locations"].setdefault(object_id, {})
        state["object_locations"][object_id].update({"location_type": "executor_gripper", "location_ref": "gripper"})
    elif step == "fill_cup_at_water_source":
        object_id = next(iter(state.get("executor", {}).get("holding", [])), bound_object or "object_cup_white_mug")
        state["object_locations"].setdefault(object_id, {})
        object_facts = set(state["object_locations"][object_id].get("state_facts", []))
        object_facts.discard("cup_empty")
        object_facts.add("cup_contains_water")
        state["object_locations"][object_id]["state_facts"] = sorted(object_facts)
    elif step == "pour_water":
        object_id = next(iter(state.get("executor", {}).get("holding", [])), bound_object or "object_cup_white_mug")
        state["object_locations"].setdefault(object_id, {})
        object_facts = set(state["object_locations"][object_id].get("state_facts", []))
        object_facts.discard("cup_contains_water")
        object_facts.add("cup_empty")
        state["object_locations"][object_id]["state_facts"] = sorted(object_facts)

    state["established_facts"] = sorted(facts)
    state["current_stage"] = step
    state.setdefault("completed_stages", []).append(step)
    after = clone_runtime_world_state(state)
    return {
        "sequence": sequence,
        "step": step,
        "requires_facts": meta.get("requires_facts", []),
        "missing_before_step": missing_before,
        "destroys_facts": meta.get("destroys_facts", []),
        "produces_fact": meta["produces_fact"],
        "before_facts": before.get("established_facts", []),
        "after_facts": after.get("established_facts", []),
        "before_executor_location": before.get("executor", {}).get("location_ref"),
        "after_executor_location": after.get("executor", {}).get("location_ref"),
        "snapshot_after": after,
    }


def step_already_satisfied_in_runtime_world_state(
    runtime_world_state: dict[str, Any],
    step: str,
    meta: dict[str, Any],
) -> bool:
    facts = set(runtime_world_state.get("established_facts", []))
    produced_fact = meta.get("produces_fact")
    if produced_fact and produced_fact not in facts:
        return False
    if meta.get("capability") == "navigate_to_region" and meta.get("target_region"):
        return runtime_world_state.get("executor", {}).get("location_ref") == meta.get("target_region")
    if step == "pick_up_cup":
        object_id = meta.get("target_object", "object_cup_white_mug")
        return object_id in set(runtime_world_state.get("executor", {}).get("holding", []))
    if step == "fill_cup_at_water_source":
        object_state_facts = set(
            runtime_world_state.get("object_locations", {}).get("object_cup_white_mug", {}).get("state_facts", [])
        )
        return "cup_contains_water" in object_state_facts
    return bool(produced_fact and produced_fact in facts)


def project_process_chain_against_runtime_world_state(
    process_chain: list[str],
    runtime_world_state: dict[str, Any],
) -> dict[str, Any]:
    projected_state = clone_runtime_world_state(runtime_world_state)
    remaining_steps: list[str] = []
    skipped_steps: list[dict[str, Any]] = []
    for step in process_chain:
        meta = STEP_LIBRARY.get(step, {})
        if not meta:
            remaining_steps.append(step)
            continue
        if step_already_satisfied_in_runtime_world_state(projected_state, step, meta):
            skipped_steps.append(
                {
                    "step": step,
                    "produces_fact": meta.get("produces_fact"),
                    "skip_reason": "already_established_in_runtime_world_state_snapshot",
                }
            )
            continue
        remaining_steps.append(step)
        apply_step_to_runtime_world_state(projected_state, step, meta, len(remaining_steps))
    return {
        "continued_process_chain": remaining_steps,
        "skipped_steps": skipped_steps,
        "source_snapshot_id": runtime_world_state.get("runtime_world_state_snapshot_id"),
        "continued_from_facts": list(runtime_world_state.get("established_facts", [])),
        "projected_facts_after_chain": list(projected_state.get("established_facts", [])),
    }


def build_process_registry() -> dict[str, dict[str, Any]]:
    registry = {step_id: dict(meta) for step_id, meta in STEP_LIBRARY.items()}
    for item in load_experience_library().get("experiences", []):
        signature = item.get("causal_signature")
        if not signature or not signature.get("solver_enabled"):
            continue
        registry[item["experience_id"]] = {
            "display_name": item.get("source_utterance", item["experience_id"]),
            "capability": "taught_causal_process",
            "requires_facts": signature.get("requires_facts", []),
            "produces_fact": signature["produces_fact"],
            "destroys_facts": signature.get("destroys_facts", []),
            "expands_to": signature.get("expands_to", item.get("process_chain", [])),
            "source": "experience_library",
        }
    return registry


def solve_causal_process_chain(goal_fact: str, cognitive_model: dict[str, Any]) -> dict[str, Any]:
    initial_facts = build_world_state_facts(cognitive_model)
    state_facts = set(initial_facts)
    plan: list[str] = []
    reasoning: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    registry = build_process_registry()

    producers: dict[str, list[str]] = {}
    for step_id, meta in registry.items():
        producers.setdefault(meta["produces_fact"], []).append(step_id)
    for fact, step_ids in producers.items():
        step_ids.sort(key=lambda step_id: 0 if registry[step_id].get("source") == "experience_library" else 1)

    def ensure_fact(fact: str, stack: list[str]) -> bool:
        if fact in state_facts:
            reasoning.append({"fact": fact, "status": "already_established", "source": "current_world_state"})
            return True
        if fact in stack:
            failures.append({"fact": fact, "reason": "causal_cycle_detected", "stack": stack})
            return False
        candidate_steps = producers.get(fact, [])
        if not candidate_steps:
            failures.append({"fact": fact, "reason": "no_process_produces_fact"})
            return False
        for step_id in candidate_steps:
            meta = registry[step_id]
            local_state = set(state_facts)
            local_plan_len = len(plan)
            local_reasoning_len = len(reasoning)
            local_failures_len = len(failures)
            requirements = meta.get("requires_facts", [])
            if all(ensure_fact(required, stack + [fact]) for required in requirements):
                expanded_steps = meta.get("expands_to") or [step_id]
                plan.extend(expanded_steps)
                for destroyed in meta.get("destroys_facts", []):
                    state_facts.discard(destroyed)
                state_facts.add(meta["produces_fact"])
                reasoning.append(
                    {
                        "fact": fact,
                        "status": "produced",
                        "process": step_id,
                        "requires_facts": requirements,
                        "produces_fact": meta["produces_fact"],
                        "destroys_facts": meta.get("destroys_facts", []),
                        "expanded_process_chain": expanded_steps,
                        "source": meta.get("source", "step_library"),
                    }
                )
                return True
            state_facts.clear()
            state_facts.update(local_state)
            del plan[local_plan_len:]
            del reasoning[local_reasoning_len:]
            del failures[local_failures_len:]
        failures.append({"fact": fact, "reason": "requirements_not_satisfied", "candidate_processes": candidate_steps})
        return False

    solved = ensure_fact(goal_fact, [])
    return {
        "solved": solved,
        "goal_fact": goal_fact,
        "initial_facts": sorted(initial_facts),
        "final_facts": sorted(state_facts),
        "process_chain": plan if solved else [],
        "reasoning": reasoning,
        "failures": failures,
    }


def chain_covers_goal(explicit_chain: list[str], causal_chain: list[str]) -> bool:
    if not explicit_chain or not causal_chain:
        return False
    explicit_set = set(explicit_chain)
    return all(step in explicit_set for step in causal_chain)


def chain_is_causally_supported(explicit_chain: list[str], base_plan: dict[str, Any]) -> bool:
    facts = set(base_plan.get("initial_facts", []))
    for step in explicit_chain:
        meta = STEP_LIBRARY[step]
        missing = [fact for fact in meta.get("requires_facts", []) if fact not in facts]
        if missing:
            return False
        for destroyed in meta.get("destroys_facts", []):
            facts.discard(destroyed)
        facts.add(meta["produces_fact"])
    return True


def build_explicit_causal_plan(goal_fact: str, explicit_chain: list[str], base_plan: dict[str, Any]) -> dict[str, Any]:
    facts = set(base_plan.get("initial_facts", []))
    reasoning: list[dict[str, Any]] = []
    for step in explicit_chain:
        meta = STEP_LIBRARY[step]
        missing = [fact for fact in meta.get("requires_facts", []) if fact not in facts]
        reasoning.append(
            {
                "fact": meta["produces_fact"],
                "status": "explicit_step",
                "process": step,
                "requires_facts": meta.get("requires_facts", []),
                "missing_before_step": missing,
                "produces_fact": meta["produces_fact"],
                "destroys_facts": meta.get("destroys_facts", []),
                "expanded_process_chain": [step],
                "source": "explicit_user_teaching",
            }
        )
        for destroyed in meta.get("destroys_facts", []):
            facts.discard(destroyed)
        facts.add(meta["produces_fact"])
    return {
        "solved": True,
        "goal_fact": goal_fact,
        "initial_facts": base_plan.get("initial_facts", []),
        "final_facts": sorted(facts),
        "process_chain": explicit_chain,
        "reasoning": reasoning,
        "failures": [],
        "plan_source": "explicit_user_teaching",
    }



INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>EORLD-RELL 真实世界经验引擎样品</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #172026;
      --muted: #5d6872;
      --line: #d8dee4;
      --surface: #ffffff;
      --band: #f4f7f8;
      --accent: #1f7a64;
      --warn: #a15c10;
      --bad: #a33636;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      color: var(--ink);
      background: var(--band);
    }
    main {
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0;
      display: grid;
      gap: 16px;
    }
    header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 14px;
    }
    h1 { margin: 0; font-size: 24px; font-weight: 700; letter-spacing: 0; }
    .status-pill {
      min-width: 132px;
      height: 34px;
      border: 1px solid var(--line);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: var(--surface);
      font-size: 14px;
    }
    section {
      background: var(--surface);
      border: 1px solid var(--line);
      padding: 16px;
    }
    .grid {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 16px;
      align-items: start;
    }
    label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 6px; }
    textarea, select, input {
      width: 100%;
      border: 1px solid var(--line);
      color: var(--ink);
      background: #fff;
      font: inherit;
    }
    textarea {
      min-height: 92px;
      resize: vertical;
      padding: 10px;
      line-height: 1.5;
    }
    select {
      height: 38px;
      padding: 0 10px;
      margin-bottom: 12px;
    }
    input {
      height: 38px;
      padding: 0 10px;
      margin-bottom: 12px;
      box-sizing: border-box;
    }
    .actions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .inline-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .inline-actions button {
      height: 30px;
      padding: 0 10px;
      white-space: nowrap;
    }
    button {
      height: 38px;
      border: 1px solid var(--ink);
      background: var(--ink);
      color: #fff;
      font: inherit;
      cursor: pointer;
    }
    button.secondary {
      background: #fff;
      color: var(--ink);
      border-color: var(--line);
    }
    button:disabled {
      opacity: .55;
      cursor: wait;
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 14px;
    }
    .metric {
      border: 1px solid var(--line);
      padding: 10px;
      min-height: 68px;
      background: #fbfcfd;
    }
    .metric span { display: block; color: var(--muted); font-size: 12px; }
    .metric strong { display: block; margin-top: 5px; font-size: 16px; overflow-wrap: anywhere; }
    #taskMetric { font-size: 14px; line-height: 1.25; }
    .runtime {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    .log, .facts {
      border: 1px solid var(--line);
      min-height: 360px;
      max-height: 520px;
      overflow: auto;
      background: #0f171b;
      color: #d8efe8;
      padding: 12px;
      font: 13px/1.55 Consolas, "Microsoft YaHei", monospace;
      white-space: pre-wrap;
    }
    .facts {
      background: #fff;
      color: var(--ink);
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
    }
    .sim {
      border: 1px solid var(--line);
      margin-bottom: 14px;
      display: grid;
      grid-template-columns: minmax(260px, 1.1fr) minmax(220px, .9fr);
      min-height: 230px;
      background: #fbfcfd;
    }
    .scene {
      position: relative;
      overflow: hidden;
      min-height: 230px;
      border-right: 1px solid var(--line);
      background: linear-gradient(#f8fafb 0 72%, #eef3f1 72% 100%);
    }
    .counter {
      position: absolute;
      left: 0;
      right: 0;
      bottom: 34px;
      height: 8px;
      background: #9aa5aa;
    }
    .kettle {
      position: absolute;
      width: 82px;
      height: 92px;
      left: 58px;
      bottom: 46px;
      transform-origin: 74px 82px;
      transform: translateX(var(--kettle-x, 0px)) rotate(var(--kettle-tilt, 0deg));
      transition: transform .18s linear;
    }
    .kettle-body {
      position: absolute;
      left: 8px;
      top: 22px;
      width: 58px;
      height: 58px;
      border: 3px solid #263238;
      background: #dfe8e7;
    }
    .kettle-spout {
      position: absolute;
      right: -4px;
      top: 36px;
      width: 28px;
      height: 10px;
      border-top: 3px solid #263238;
      transform: rotate(-8deg);
    }
    .kettle-handle {
      position: absolute;
      left: -2px;
      top: 36px;
      width: 18px;
      height: 30px;
      border: 3px solid #263238;
      border-right: 0;
    }
    .cup {
      position: absolute;
      left: 278px;
      bottom: 47px;
      width: 78px;
      height: 78px;
      border: 3px solid #263238;
      border-top: 0;
      background: #ffffff;
      overflow: hidden;
      transform: translateX(var(--cup-x, 0px));
      transition: transform .24s linear;
    }
    .cup-water {
      position: absolute;
      left: 0;
      right: 0;
      bottom: 0;
      height: var(--water-level, 0%);
      background: #55a7b5;
      transition: height .18s linear;
    }
    .stream {
      position: absolute;
      left: var(--stream-x, 212px);
      top: 98px;
      width: 8px;
      height: var(--stream-height, 0px);
      background: #55a7b5;
      opacity: var(--stream-opacity, 0);
      transform: rotate(16deg);
      transform-origin: top center;
      transition: height .18s linear, opacity .12s linear;
    }
    .state-panel {
      padding: 12px;
      display: grid;
      gap: 8px;
      align-content: start;
    }
    .state-item {
      border-bottom: 1px solid var(--line);
      padding-bottom: 8px;
      display: flex;
      justify-content: space-between;
      gap: 12px;
      font-size: 14px;
    }
    .state-item span { color: var(--muted); }
    .state-item strong { text-align: right; overflow-wrap: anywhere; }
    .space-map {
      position: relative;
      border: 1px solid var(--line);
      margin-bottom: 14px;
      min-height: 260px;
      background: #f9fbfa;
      overflow: hidden;
    }
    .map-region {
      position: absolute;
      border: 1px solid #7d8c88;
      background: rgba(255,255,255,.75);
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 6px;
      font-size: 12px;
      color: var(--ink);
    }
    .map-walkway { left: 10%; top: 45%; width: 76%; height: 33%; background: #eaf4ef; }
    .map-counter { left: 56%; top: 14%; width: 28%; height: 16%; background: #eef1f5; }
    .map-water { left: 18%; top: 14%; width: 20%; height: 16%; background: #e4f3f7; }
    .map-cup { left: 59%; top: 17%; width: 8%; height: 9%; background: #fff; border-width: 2px; }
    .map-service { left: 72%; top: 58%; width: 15%; height: 16%; border-radius: 999px; background: #fff8e8; }
    .map-door { left: 5%; top: 55%; width: 9%; height: 18%; background: #f4efe6; }
    .map-risk { left: 84%; top: 13%; width: 12%; height: 18%; background: #f9e7e5; border-color: #b66a61; color: #7e2e27; }
    .map-clickable {
      cursor: pointer;
      box-shadow: inset 0 0 0 1px rgba(23,32,38,.06);
    }
    .map-clickable:hover {
      box-shadow: inset 0 0 0 2px var(--accent);
    }
    .map-clickable.active {
      box-shadow: inset 0 0 0 2px var(--accent);
      background: #dfeee7;
    }
    .map-object {
      position: absolute;
      width: 18px;
      height: 18px;
      border: 2px solid #263238;
      background: #fff;
    }
    .map-kettle { left: 28%; top: 19%; }
    .map-sensor { left: 43%; top: 62%; border-radius: 999px; background: #172026; }
    .map-robot {
      position: absolute;
      width: 24px;
      height: 24px;
      border: 2px solid #172026;
      background: var(--accent);
      left: var(--robot-x, 28%);
      top: var(--robot-y, 60%);
      transform: translate(-50%, -50%);
      transition: left .24s linear, top .24s linear;
    }
    .map-cup-item {
      position: absolute;
      width: 18px;
      height: 18px;
      left: var(--cup-map-x, 63%);
      top: var(--cup-map-y, 22%);
      border: 2px solid #263238;
      background: linear-gradient(#fff 0 var(--cup-empty, 100%), #55a7b5 var(--cup-empty, 100%) 100%);
      transform: translate(-50%, -50%);
      transition: left .24s linear, top .24s linear, background .18s linear;
      z-index: 4;
    }
    .map-path {
      position: absolute;
      left: 30%;
      top: 60%;
      width: 36%;
      height: 2px;
      border-top: 2px dashed #7c918a;
      transition: left .24s linear, top .24s linear, width .24s linear, border-color .18s linear;
    }
    .map-path.detour {
      left: 18%;
      top: 72%;
      width: 48%;
      border-top-color: #b8860b;
    }
    .map-path.blocked {
      left: 24%;
      top: 63%;
      width: 22%;
      border-top-color: #b24d4d;
    }
    .map-detour-badge {
      position: absolute;
      right: 10px;
      bottom: 10px;
      padding: 6px 8px;
      border: 1px solid #7d8c88;
      background: rgba(255,255,255,.94);
      font-size: 12px;
      color: var(--ink);
      display: none;
      z-index: 6;
    }
    .map-detour-badge.active {
      display: block;
    }
    .map-detour-badge.detour {
      border-color: #b8860b;
      color: #7a5a00;
      background: #fff7dc;
    }
    .map-detour-badge.blocked {
      border-color: #b24d4d;
      color: #7b2424;
      background: #fdeaea;
    }
    .stage-row {
      border-bottom: 1px solid var(--line);
      padding: 10px 0;
      display: grid;
      gap: 4px;
    }
    .stage-row:last-child { border-bottom: 0; }
    .stage-row strong { font-size: 14px; }
    .stage-row span { color: var(--muted); font-size: 13px; }
    .p017-card {
      border: 1px solid var(--line);
      margin-bottom: 10px;
      padding: 10px;
      display: grid;
      gap: 6px;
      background: #fbfcfc;
    }
    .p017-card summary {
      cursor: pointer;
      font-weight: 700;
      color: var(--ink);
    }
    .p017-card code {
      background: #edf2f1;
      padding: 2px 4px;
    }
    .p017-json {
      margin: 6px 0 0;
      padding: 10px;
      max-height: 260px;
      overflow: auto;
      background: #0f171b;
      color: #d8efe8;
      font: 12px/1.5 Consolas, "Microsoft YaHei", monospace;
      white-space: pre-wrap;
    }
    .ok { color: var(--accent); }
    .warn { color: var(--warn); }
    .bad { color: var(--bad); }
    @media (max-width: 860px) {
      .grid, .runtime, .sim { grid-template-columns: 1fr; }
      .scene { border-right: 0; border-bottom: 1px solid var(--line); }
      .summary { grid-template-columns: 1fr 1fr; }
      header { align-items: start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>EORLD-RELL 真实世界经验引擎样品</h1>
      <a href="/embodied" target="_blank" style="color:#17352a;background:#d7e8dd;padding:8px 12px;border-radius:4px;text-decoration:none;font-size:13px;font-weight:700">进入三维家庭实验场</a>
      <div id="serviceState" class="status-pill">待运行</div>
    </header>
    <div class="grid">
      <section>
        <label for="utterance">任务输入</label>
        <textarea id="utterance">给客人倒一杯水</textarea>
        <label for="scenario">运行场景</label>
        <select id="scenario">
          <option value="auto">自动：翻译层选择</option>
          <option value="simulated_success">模拟执行体：成功倒水</option>
          <option value="simulated_no_water">模拟执行体：壶内无水</option>
          <option value="simulated_channel_conflict">模拟执行体：双通道冲突</option>
          <option value="success">Mock剧本：成功倒水</option>
          <option value="no_flow">Mock剧本：无水流失败</option>
          <option value="channel_conflict">Mock剧本：双通道冲突</option>
        </select>
        <div class="actions">
          <button id="runButton" title="运行过程实例">▶ 运行</button>
          <button id="clearButton" class="secondary" title="清空当前日志">清空</button>
        </div>
        <label for="teachingSteps" style="margin-top:12px;">人工教学步骤</label>
        <textarea id="teachingSteps">走向操作台
拿起杯子
到水源处
接一杯水
倒水</textarea>
        <label for="dialogueTeaching" style="margin-top:12px;">对话教学</label>
        <textarea id="dialogueTeaching">教你：走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水</textarea>
        <div class="actions" style="margin-top:8px;">
          <button id="teachButton" class="secondary" title="将步骤转为候选经验">教学入库</button>
          <button id="dialogueTeachButton" class="secondary" title="从对话中形成候选经验">对话教学</button>
        </div>
        <div class="actions" style="margin-top:8px;">
          <button id="libraryButton" class="secondary" title="查看当前经验库">经验库</button>
          <button id="p017Button" class="secondary" title="查看 P017 六段最小闭环证据">P017 最小闭环</button>
        </div>
        <label for="conceptCandidateId" style="margin-top:12px;">概念候选确认</label>
        <input id="conceptCandidateId" value="" placeholder="留空则自动选择第一个待确认候选" />
        <div class="actions" style="margin-top:8px;">
          <button id="conceptCandidatesButton" class="secondary" title="查看待人工确认的概念候选">概念候选</button>
          <button id="confirmConceptCandidateButton" class="secondary" title="确认当前概念候选并晋升到概念库">确认晋升</button>
        </div>
        <label for="stepwiseTeaching" style="margin-top:12px;">边教边动</label>
        <textarea id="stepwiseTeaching">走向操作台</textarea>
        <div class="actions" style="margin-top:8px;">
          <button id="startTeachingSessionButton" class="secondary" title="启动数字执行主体教学会话">开始会话</button>
          <button id="stepTeachingSessionButton" class="secondary" title="执行本次教学步骤并返回事实反馈">教一步并执行</button>
          <button id="finishTeachingSessionButton" class="secondary" title="确认成功并固化经验">成功入库</button>
        </div>
        <label for="runtimeQuestion" style="margin-top:12px;">状态提问</label>
        <textarea id="runtimeQuestion">当前杯子有没有水</textarea>
        <div class="actions" style="margin-top:8px;">
          <button id="askRuntimeQuestionButton" class="secondary" title="从当前任务期运行时世界状态快照回答问题">问当前状态</button>
        </div>
        <label for="perturbationKind" style="margin-top:12px;">中途扰动 / 偶然层</label>
        <label for="dispatchBackend" style="margin-top:8px;">执行后端</label>
        <select id="dispatchBackend">
          <option value="robot_sdk">逻辑执行适配器</option>
          <option value="mujoco_physics">MuJoCo 物理验真</option>
        </select>
        <label for="physicsExecutorType" style="margin-top:8px;">物理主体</label>
        <select id="physicsExecutorType">
          <option value="mobile_manipulator">移动操作机器人</option>
          <option value="mobile_base">移动底盘</option>
          <option value="fixed_arm">固定机械臂</option>
        </select>
        <label for="migrationSpace" style="margin-top:8px;">经验迁移目标空间</label>
        <select id="migrationSpace">
          <option value="home_a_kitchen">原厨房空间</option>
          <option value="site_b_corridor">走廊饮水区（跨空间）</option>
        </select>
        <select id="perturbationKind">
          <option value="stool_in_walkway_detourable">过道放凳子（可绕开）</option>
          <option value="stool_blocks_walkway">过道凳子完全堵路</option>
          <option value="cup_guard_door_closed">杯子前门关闭</option>
          <option value="water_source_door_closed">水源前门关闭</option>
        </select>
        <label for="perturbationStep" style="margin-top:12px;">在第几步前生效</label>
        <select id="perturbationStep">
          <option value="move_to_counter">move_to_counter</option>
          <option value="pick_up_cup">pick_up_cup</option>
          <option value="move_to_water_source" selected>move_to_water_source</option>
          <option value="fill_cup_at_water_source">fill_cup_at_water_source</option>
          <option value="pour_water">pour_water</option>
        </select>
        <div class="actions" style="margin-top:8px;">
          <button id="preparePerturbationTaskButton" class="secondary" title="创建迁移适配任务，供偶然层注入扰动">准备扰动测试</button>
          <button id="injectPerturbationButton" class="secondary" title="向当前任务期快照注入偶然层扰动">注入扰动</button>
        </div>
        <div class="actions" style="margin-top:8px;">
          <button id="runPerturbationDispatchButton" class="secondary" title="在注入扰动后执行迁移链">执行扰动链</button>
        </div>
        <div class="actions" style="margin-top:8px;">
          <button id="startPhysicsSessionButton" class="secondary" title="创建可在阶段间暂停的 MuJoCo 会话">开始物理会话</button>
          <button id="stepPhysicsSessionButton" class="secondary" title="只执行并验真下一个物理阶段">执行下一阶段</button>
          <button id="interruptPhysicsSessionButton" class="secondary" title="使用主任务输入框中的新指令中断当前物理会话">中断并切换</button>
        </div>
      </section>
      <section>
        <div class="summary">
          <div class="metric"><span>准入</span><strong id="admitMetric">-</strong></div>
          <div class="metric"><span>阶段状态</span><strong id="stateMetric">-</strong></div>
          <div class="metric"><span>运行结果</span><strong id="outcomeMetric">-</strong></div>
          <div class="metric"><span>任务</span><strong id="taskMetric">-</strong></div>
        </div>
        <div class="sim">
          <div id="scene" class="scene">
            <div class="counter"></div>
            <div id="kettle" class="kettle">
              <div class="kettle-body"></div>
              <div class="kettle-spout"></div>
              <div class="kettle-handle"></div>
            </div>
            <div id="stream" class="stream"></div>
            <div id="sceneCup" class="cup"><div id="cupWater" class="cup-water"></div></div>
          </div>
          <div class="state-panel">
            <div class="state-item"><span>壶嘴距离</span><strong id="distanceValue">-</strong></div>
            <div class="state-item"><span>倾角</span><strong id="tiltValue">-</strong></div>
            <div class="state-item"><span>水流速度</span><strong id="flowValue">-</strong></div>
            <div class="state-item"><span>杯中液位</span><strong id="levelValue">-</strong></div>
            <div class="state-item"><span>验真状态</span><strong id="factValue">-</strong></div>
            <div class="state-item"><span>当前经验步骤</span><strong id="learnedStepValue">-</strong></div>
            <div class="state-item"><span>空间目标</span><strong id="targetValue">-</strong></div>
          </div>
        </div>
        <div id="spaceMap" class="space-map">
          <div class="map-region map-water">水源区</div>
          <div class="map-region map-counter">操作台</div>
          <div id="walkwayPerturbRegion" class="map-region map-walkway map-clickable" title="点击预设过道扰动">可行动区</div>
          <div class="map-region map-cup">杯</div>
          <div class="map-region map-service">服务位</div>
          <div id="doorPerturbRegion" class="map-region map-door map-clickable" title="点击预设关门扰动">门</div>
          <div class="map-region map-risk">风险区</div>
          <div id="mapPath" class="map-path"></div>
          <div id="mapDetourBadge" class="map-detour-badge"></div>
          <div class="map-object map-kettle" title="object_kettle_steel_1l"></div>
          <div class="map-object map-sensor" title="sensor_depth_front"></div>
          <div id="mapCupItem" class="map-cup-item" title="object_cup_white_mug"></div>
          <div id="mapRobot" class="map-robot" title="simulated_pouring_robot"></div>
        </div>
        <div class="runtime">
          <div id="log" class="log"></div>
          <div id="facts" class="facts"></div>
        </div>
      </section>
    </div>
  </main>
  <script>
    const runButton = document.getElementById("runButton");
    const teachButton = document.getElementById("teachButton");
    const dialogueTeachButton = document.getElementById("dialogueTeachButton");
    const libraryButton = document.getElementById("libraryButton");
    const p017Button = document.getElementById("p017Button");
    const conceptCandidatesButton = document.getElementById("conceptCandidatesButton");
    const confirmConceptCandidateButton = document.getElementById("confirmConceptCandidateButton");
    const conceptCandidateIdInput = document.getElementById("conceptCandidateId");
    const startTeachingSessionButton = document.getElementById("startTeachingSessionButton");
    const stepTeachingSessionButton = document.getElementById("stepTeachingSessionButton");
    const finishTeachingSessionButton = document.getElementById("finishTeachingSessionButton");
    const askRuntimeQuestionButton = document.getElementById("askRuntimeQuestionButton");
    const preparePerturbationTaskButton = document.getElementById("preparePerturbationTaskButton");
    const injectPerturbationButton = document.getElementById("injectPerturbationButton");
    const runPerturbationDispatchButton = document.getElementById("runPerturbationDispatchButton");
    const startPhysicsSessionButton = document.getElementById("startPhysicsSessionButton");
    const stepPhysicsSessionButton = document.getElementById("stepPhysicsSessionButton");
    const interruptPhysicsSessionButton = document.getElementById("interruptPhysicsSessionButton");
    const perturbationKind = document.getElementById("perturbationKind");
    const migrationSpace = document.getElementById("migrationSpace");
    const dispatchBackend = document.getElementById("dispatchBackend");
    const physicsExecutorType = document.getElementById("physicsExecutorType");
    const perturbationStep = document.getElementById("perturbationStep");
    const walkwayPerturbRegion = document.getElementById("walkwayPerturbRegion");
    const doorPerturbRegion = document.getElementById("doorPerturbRegion");
    const clearButton = document.getElementById("clearButton");
    const logEl = document.getElementById("log");
    const factsEl = document.getElementById("facts");
    const serviceState = document.getElementById("serviceState");
    const admitMetric = document.getElementById("admitMetric");
    const stateMetric = document.getElementById("stateMetric");
    const outcomeMetric = document.getElementById("outcomeMetric");
    const taskMetric = document.getElementById("taskMetric");
    const scene = document.getElementById("scene");
    const distanceValue = document.getElementById("distanceValue");
    const tiltValue = document.getElementById("tiltValue");
    const flowValue = document.getElementById("flowValue");
    const levelValue = document.getElementById("levelValue");
    const factValue = document.getElementById("factValue");
    const learnedStepValue = document.getElementById("learnedStepValue");
    const targetValue = document.getElementById("targetValue");
    const mapRobot = document.getElementById("mapRobot");
    const mapCupItem = document.getElementById("mapCupItem");
    const mapPath = document.getElementById("mapPath");
    const mapDetourBadge = document.getElementById("mapDetourBadge");
    const utteranceInput = document.getElementById("utterance");
    const scenarioSelect = document.getElementById("scenario");
    let currentTeachingSessionId = "";
    let currentConceptCandidateId = "";
    let currentMigrationTaskId = "";
    let currentExecutionLoopPayload = null;
    let currentPhysicsSessionId = null;
    let currentRuntimeWorldState = null;

    const eventLabel = {
      stage_started: "阶段启动",
      state_update: "连续状态变量更新",
      observation_update: "目标因果事实观测",
      failure_event: "失败事件",
      runtime_failure: "Runtime 失败",
      learned_step_executed: "教学经验步骤",
      causal_step_executed: "因果推导步骤"
    };
    const stepDisplayNameMap = {
      move_to_doorway: "走到门旁边",
      move_to_service_position: "走到服务位",
      move_to_counter: "走向操作台",
      pick_up_cup: "拿起杯子",
      move_to_water_source: "到水源处",
      fill_cup_at_water_source: "接一杯水",
      pour_water: "倒水"
    };

    function setText(node, value, className = "") {
      node.textContent = value;
      node.className = className;
    }

    function appendLog(line) {
      logEl.textContent += line + "\\n";
      logEl.scrollTop = logEl.scrollHeight;
    }

    function buildReadableChainUtterance(chain, separator = "，然后") {
      return (chain || []).map(step => stepDisplayNameMap[step] || step).join(separator);
    }

    function clearView(options = {}) {
      const { resetContext = true } = options;
      logEl.textContent = "";
      factsEl.innerHTML = "";
      setText(admitMetric, "-");
      setText(stateMetric, "-");
      setText(outcomeMetric, "-");
      if (resetContext) {
        setText(taskMetric, "-");
      }
      resetScene();
      serviceState.textContent = "待运行";
      if (resetContext) {
        currentTeachingSessionId = "";
        currentConceptCandidateId = "";
        currentMigrationTaskId = "";
        currentExecutionLoopPayload = null;
        currentRuntimeWorldState = null;
      }
      conceptCandidateIdInput.value = "";
    }

    function resetScene() {
      scene.style.setProperty("--kettle-x", "0px");
      scene.style.setProperty("--kettle-tilt", "0deg");
      scene.style.setProperty("--water-level", "0%");
      scene.style.setProperty("--stream-height", "0px");
      scene.style.setProperty("--stream-opacity", "0");
      scene.style.setProperty("--stream-x", "212px");
      scene.style.setProperty("--cup-x", "0px");
      mapRobot.style.setProperty("--robot-x", "28%");
      mapRobot.style.setProperty("--robot-y", "60%");
      mapCupItem.style.setProperty("--cup-map-x", "63%");
      mapCupItem.style.setProperty("--cup-map-y", "22%");
      mapCupItem.style.setProperty("--cup-empty", "100%");
      setText(distanceValue, "-");
      setText(tiltValue, "-");
      setText(flowValue, "-");
      setText(levelValue, "-");
      setText(factValue, "-");
      setText(learnedStepValue, "-");
      setText(targetValue, "-");
      clearRouteAdjustmentVisualization();
    }

    function clearRouteAdjustmentVisualization() {
      mapPath.classList.remove("detour", "blocked");
      mapDetourBadge.classList.remove("active", "detour", "blocked");
      mapDetourBadge.textContent = "";
    }

    function applyRouteAdjustmentVisualization(routeAdjustment, options = {}) {
      clearRouteAdjustmentVisualization();
      if (!routeAdjustment) {
        return;
      }
      const step = routeAdjustment.step || "-";
      const blocked = options.blocked || routeAdjustment.adjustment_type === "blocked";
      const modeClass = blocked ? "blocked" : "detour";
      mapPath.classList.add(modeClass);
      mapDetourBadge.classList.add("active", modeClass);
      mapDetourBadge.textContent = blocked
        ? `阻断：${step} 需重适配`
        : `绕行中：${step} 保持主链`;
    }

    function regionToMapPose(regionRef) {
      const poseMap = {
        region_floor_walkway: { robotX: "28%", robotY: "60%", cupX: "63%", cupY: "22%" },
        region_counter_operation: { robotX: "63%", robotY: "58%", cupX: "63%", cupY: "22%" },
        region_water_source: { robotX: "28%", robotY: "58%", cupX: "29%", cupY: "55%" },
        region_doorway: { robotX: "10%", robotY: "64%", cupX: "63%", cupY: "22%" },
        region_service_position: { robotX: "78%", robotY: "66%", cupX: "63%", cupY: "22%" }
      };
      return poseMap[regionRef] || poseMap.region_floor_walkway;
    }

    function regionToHeldCupPose(regionRef) {
      const poseMap = {
        region_floor_walkway: { cupX: "28%", cupY: "57%" },
        region_counter_operation: { cupX: "63%", cupY: "55%" },
        region_water_source: { cupX: "29%", cupY: "55%" },
        region_doorway: { cupX: "10%", cupY: "61%" },
        region_service_position: { cupX: "78%", cupY: "63%" }
      };
      return poseMap[regionRef] || poseMap.region_floor_walkway;
    }

    function applyRuntimeWorldStateToScene(runtimeWorldState) {
      if (!runtimeWorldState) {
        return;
      }
      resetScene();
      const executor = runtimeWorldState.executor || {};
      const executorPose = regionToMapPose(executor.location_ref);
      mapRobot.style.setProperty("--robot-x", executorPose.robotX);
      mapRobot.style.setProperty("--robot-y", executorPose.robotY);

      const cupState = runtimeWorldState.object_locations?.object_cup_white_mug || {};
      const cupFacts = new Set(cupState.state_facts || []);
      const establishedFacts = new Set(runtimeWorldState.established_facts || []);
      const holdingCup = (executor.holding || []).includes("object_cup_white_mug") || cupState.location_type === "executor_gripper";

      if (holdingCup) {
        const heldCupPose = regionToHeldCupPose(executor.location_ref);
        mapCupItem.style.setProperty("--cup-map-x", heldCupPose.cupX);
        mapCupItem.style.setProperty("--cup-map-y", heldCupPose.cupY);
        scene.style.setProperty("--cup-x", executor.location_ref === "region_water_source" ? "-150px" : "-18px");
        setText(factValue, cupFacts.has("cup_contains_water") || establishedFacts.has("cup_contains_water") ? "cup_contains_water" : "cup_in_gripper");
      } else {
        const cupPose = regionToMapPose(cupState.location_ref);
        mapCupItem.style.setProperty("--cup-map-x", cupPose.cupX);
        mapCupItem.style.setProperty("--cup-map-y", cupPose.cupY);
        scene.style.setProperty("--cup-x", cupState.location_ref === "region_water_source" ? "-150px" : "0px");
        if (establishedFacts.has("cup_at_counter")) {
          setText(factValue, "cup_at_counter");
        }
      }

      if (cupFacts.has("cup_contains_water") || establishedFacts.has("cup_contains_water")) {
        mapCupItem.style.setProperty("--cup-empty", "35%");
        scene.style.setProperty("--water-level", "62%");
        setText(levelValue, "digital fill");
      }
      if (establishedFacts.has("water_poured")) {
        scene.style.setProperty("--stream-height", "70px");
        scene.style.setProperty("--stream-opacity", "1");
        setText(flowValue, "digital pour");
        setText(factValue, "water_poured");
      }
    }

    function readPayloadValue(summary, name) {
      const match = summary.match(new RegExp(name + "=([0-9.\\-]+)"));
      return match ? Number(match[1]) : null;
    }

    function readPayloadToken(summary, name) {
      const match = summary.match(new RegExp(name + "=([^\\\\s]+)"));
      return match ? match[1] : "";
    }

    function moveDigitalActors(robotX, robotY, cupX = null, cupY = null) {
      mapRobot.style.setProperty("--robot-x", robotX);
      mapRobot.style.setProperty("--robot-y", robotY);
      if (cupX && cupY) {
        mapCupItem.style.setProperty("--cup-map-x", cupX);
        mapCupItem.style.setProperty("--cup-map-y", cupY);
      }
    }

    function updateLearnedStepScene(event) {
      const summary = event.payload_summary || "";
      const step = readPayloadToken(summary, "step");
      if (!step) return false;
      const display = readPayloadToken(summary, "display");
      const target = readPayloadToken(summary, "target");
      setText(learnedStepValue, display || step);
      setText(targetValue, target || "-");
      scene.style.setProperty("--stream-height", "0px");
      scene.style.setProperty("--stream-opacity", "0");
      if (step === "move_to_doorway") {
        moveDigitalActors("10%", "64%");
        setText(factValue, "executor_at_doorway");
      } else if (step === "move_to_service_position") {
        moveDigitalActors("78%", "66%");
        setText(factValue, "executor_at_service_position");
      } else if (step === "move_to_counter") {
        moveDigitalActors("63%", "58%");
        scene.style.setProperty("--cup-x", "0px");
        setText(factValue, "executor_at_counter");
      } else if (step === "pick_up_cup") {
        moveDigitalActors("63%", "58%", "63%", "55%");
        scene.style.setProperty("--cup-x", "-18px");
        setText(factValue, "cup_in_gripper");
      } else if (step === "move_to_water_source") {
        moveDigitalActors("28%", "58%", "29%", "55%");
        scene.style.setProperty("--cup-x", "-150px");
        setText(factValue, "executor_at_water_source");
      } else if (step === "fill_cup_at_water_source") {
        moveDigitalActors("28%", "58%", "29%", "55%");
        mapCupItem.style.setProperty("--cup-empty", "35%");
        scene.style.setProperty("--water-level", "62%");
        setText(levelValue, "digital fill");
        setText(factValue, "cup_contains_water");
      } else if (step === "pour_water") {
        moveDigitalActors("63%", "58%", "63%", "55%");
        mapCupItem.style.setProperty("--cup-empty", "35%");
        scene.style.setProperty("--cup-x", "0px");
        scene.style.setProperty("--stream-height", "70px");
        scene.style.setProperty("--stream-opacity", "1");
        setText(flowValue, "digital pour");
        setText(factValue, "water_poured");
      }
      return true;
    }

    function updateSceneFromEvent(event) {
      const summary = event.payload_summary || "";
      if ((event.trigger_reason === "learned_step_executed" || event.trigger_reason === "causal_step_executed" || event.trigger_reason === "continued_runtime_step_executed") && updateLearnedStepScene(event)) {
        return;
      }
      const distance = readPayloadValue(summary, "spout_to_cup_distance");
      if (distance !== null) {
        const x = Math.max(0, Math.min(145, (8 - distance) * 19));
        scene.style.setProperty("--kettle-x", `${x}px`);
        const robotX = Math.max(30, Math.min(63, 30 + (8 - distance) * 4.2));
        mapRobot.style.setProperty("--robot-x", `${robotX}%`);
        mapRobot.style.setProperty("--robot-y", "60%");
        setText(distanceValue, `${distance.toFixed(1)} cm`);
      }
      const tilt = readPayloadValue(summary, "tilt_angle");
      if (tilt !== null) {
        scene.style.setProperty("--kettle-tilt", `${tilt.toFixed(1)}deg`);
        setText(tiltValue, `${tilt.toFixed(1)}°`);
      }
      const flow = readPayloadValue(summary, "water_flow_rate");
      if (flow !== null) {
        scene.style.setProperty("--stream-height", flow > 0 ? "84px" : "0px");
        scene.style.setProperty("--stream-opacity", flow > 0 ? "1" : "0");
        if (flow > 0) {
          mapRobot.style.setProperty("--robot-x", "64%");
          mapRobot.style.setProperty("--robot-y", "36%");
        }
        setText(flowValue, `${flow.toFixed(1)} ml/s`);
      }
      const gap = readPayloadValue(summary, "water_surface_gap");
      if (gap !== null) {
        const level = Math.max(0, Math.min(86, (3 - gap) / 2.65 * 86));
        scene.style.setProperty("--water-level", `${level.toFixed(0)}%`);
        setText(levelValue, `gap ${gap.toFixed(2)} cm`);
      }
      if (summary.includes("cup_has_water")) {
        const value = summary.split("cup_has_water:")[1] || summary;
        setText(factValue, value.replace(" adapter=simulated_pouring_robot", ""));
      }
    }

    function describeTrace(event) {
      const label = eventLabel[event.trigger_reason] || event.trigger_reason;
      const payload = event.payload_summary ? " | " + event.payload_summary : "";
      return `[${String(event.consumed_sequence).padStart(2, "0")}] ${label} | ${event.before_state} -> ${event.after_state}${payload}`;
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function setPerturbationPreset(kind, step) {
      perturbationKind.value = kind;
      perturbationStep.value = step;
      walkwayPerturbRegion.classList.toggle("active", kind.includes("walkway"));
      doorPerturbRegion.classList.toggle("active", kind.includes("door_closed"));
    }

    async function triggerMapPerturbation(kind, step, label) {
      setPerturbationPreset(kind, step);
      appendLog("已从空间图选择偶然层扰动：" + label + "；将直接注入当前任务期快照。");
      await injectPerturbation();
    }

    function rememberMigrationEnvelope(result) {
      currentMigrationTaskId = result.migration_task_id || currentMigrationTaskId;
      currentExecutionLoopPayload = result.execution_loop_payload || currentExecutionLoopPayload;
      if (result.migration_task_id) {
        setText(taskMetric, result.migration_task_id);
      }
    }

    function renderPerturbationFacts(title, payload) {
      const env = payload.runtime_world_state_snapshot?.runtime_environment || payload.runtime_environment || {};
      const perturbation = payload.injected_perturbation || {};
      const rows = [
        `<div class="stage-row"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(payload.task_id || currentMigrationTaskId || "-")}</span></div>`,
        `<div class="stage-row"><strong>扰动类型</strong><span>${escapeHtml(perturbation.kind || "-")} / ${escapeHtml(perturbation.label || "-")}</span></div>`,
        `<div class="stage-row"><strong>生效时机</strong><span>${escapeHtml(perturbation.apply_before_step || "immediate")} / ${escapeHtml(perturbation.status || "-")}</span></div>`,
        `<div class="stage-row"><strong>当前偶然层状态</strong><span>active=${escapeHtml(String((env.active_perturbations || []).length))} / scheduled=${escapeHtml(String((env.scheduled_perturbations || []).length))}</span></div>`
      ];
      if (env.last_preflight) {
        rows.push(`<div class="stage-row"><strong>最近预检</strong><span>${escapeHtml(env.last_preflight.step || "-")} / ${escapeHtml(env.last_preflight.result || "-")}</span></div>`);
      }
      factsEl.innerHTML = rows.join("");
      if (env.last_route_adjustment) {
        applyRouteAdjustmentVisualization(env.last_route_adjustment);
      } else {
        clearRouteAdjustmentVisualization();
      }
    }

    function formatConfidence(value) {
      if (typeof value !== "number" || Number.isNaN(value)) {
        return "-";
      }
      return `${Math.round(value * 100)}%`;
    }

    function confidenceClass(value) {
      if (typeof value !== "number" || Number.isNaN(value)) {
        return "";
      }
      if (value >= 0.75) return "ok";
      if (value >= 0.45) return "warn";
      return "bad";
    }

    function summarizeAlternativeInterpretation(item) {
      if (!item) {
        return "";
      }
      if (typeof item === "string") {
        return item;
      }
      return item.label || item.prompt || item.candidate || item.reason || JSON.stringify(item);
    }

    function summarizeConceptResolution(conceptResolution) {
      const concepts = conceptResolution?.resolved_concepts || [];
      return concepts.map(item => `${item.display_name || item.concept_id}(${item.concept_level || "concept"})`).join(" / ");
    }

    function renderConceptGroundingRows(conceptResolution, groundingGate = null) {
      const rows = [];
      for (const concept of (conceptResolution?.action_concepts || [])) {
        const packageView = concept.concept_package || {};
        const roles = packageView.concept_kernel?.semantic_roles || {};
        const roleSummary = Object.entries(roles).map(([name, binding]) => {
          const target = binding.entity_ref || binding.value || "未落地";
          const basis = binding.binding_basis ? ` / ${binding.binding_basis}` : "";
          return `${name}=${target} [${binding.mention_status || "-"}/${binding.grounding_status || "-"}]${basis}`;
        }).join("；");
        if (roleSummary) {
          rows.push(`<div class="stage-row"><strong>${escapeHtml(concept.display_name || concept.concept_id)}</strong><span>${escapeHtml(roleSummary)}</span></div>`);
        }
        const missing = packageView.fact_alignment?.missing_requirements || [];
        const experienceCandidates = packageView.experience_lookup?.candidates || [];
        if (missing.length) {
          rows.push(`<div class="stage-row"><strong>缺失前提</strong><span>${escapeHtml(missing.join(", "))}</span></div>`);
        }
        if (experienceCandidates.length) {
          const candidates = experienceCandidates.map(item => `${item.candidate_id} -> ${(item.covers_missing_facts || []).join(",")}`).join(" / ");
          rows.push(`<div class="stage-row"><strong>经验候选</strong><span>${escapeHtml(candidates)}</span></div>`);
        }
      }
      const gate = groundingGate || {};
      if (gate.gate_status) {
        rows.push(`<div class="stage-row"><strong>角色落地门控</strong><span>${escapeHtml(gate.gate_status)} / direct_execution_allowed=${escapeHtml(String(gate.direct_execution_allowed))}</span></div>`);
      }
      for (const question of (gate.clarification_questions || [])) {
        rows.push(`<div class="stage-row"><strong>需要确认</strong><span>${escapeHtml(question)}</span></div>`);
      }
      return rows;
    }

    function humanizeSemanticReason(reason) {
      const reasonMap = {
        deictic_object_without_shared_reference: "对象指代未落地",
        direction_reference_not_grounded: "方向参照未落地",
        ambiguous_action_phrase: "动作语义不够明确",
        no_process_or_concept_match: "尚未命中本地过程链或概念",
        teaching_step_not_parsed: "教学步骤尚未解析清楚",
        empty_input: "输入为空",
        empty_or_unknown_request: "输入为空或语义未知",
        no_local_concept_match: "尚未命中本地概念",
        no_local_action_concept_or_experience_match: "已识别对象或场景，但尚无可复用动作概念或任务经验",
        intent_long_chain_delivery_unsupported: "当前长程取送任务仍需外域候选补给",
        intent_risk_area_action_unsupported: "当前风险动作不允许直接进入执行",
        intent_causal_process_chain_unsupported: "当前目标事实尚未补齐可执行过程链",
        intent_process_chain_unsupported: "当前过程链尚未形成可执行闭环",
      };
      return reasonMap[reason] || reason || "-";
    }

    function humanizeSemanticReasonList(items) {
      return (items || []).map(item => humanizeSemanticReason(item)).filter(Boolean);
    }

    function renderSemanticSignalRows(semanticRequest, routeResult = null) {
      const rows = [];
      if (!semanticRequest && !routeResult) {
        return rows;
      }
      const confidence = semanticRequest?.intent_confidence;
      const confidenceReasons = semanticRequest?.confidence_reasons || [];
      const alternativeInterpretations = routeResult?.alternative_interpretations || semanticRequest?.alternative_interpretations || [];
      const conceptResolution = routeResult?.concept_resolution || semanticRequest?.concept_resolution;
      const conceptSummary = summarizeConceptResolution(conceptResolution);
      rows.push(
        `<div class="stage-row"><strong>交互判定</strong><span>${escapeHtml(semanticRequest?.request_type || "-")} / ${escapeHtml(semanticRequest?.preferred_model_tier || "-")}</span></div>`,
        `<div class="stage-row"><strong>意图置信度</strong><span>${escapeHtml(formatConfidence(confidence))}${semanticRequest?.clarification_needed ? " / 需澄清" : " / 可继续"}</span></div>`
      );
      if (semanticRequest?.clarification_reason) {
        rows.push(`<div class="stage-row"><strong>澄清原因</strong><span>${escapeHtml(humanizeSemanticReason(semanticRequest.clarification_reason))}</span></div>`);
      }
      if (routeResult?.clarification_prompt) {
        rows.push(`<div class="stage-row"><strong>澄清提示</strong><span>${escapeHtml(routeResult.clarification_prompt)}</span></div>`);
      }
      if (confidenceReasons.length) {
        rows.push(`<div class="stage-row"><strong>置信依据</strong><span>${escapeHtml(confidenceReasons.join(" / "))}</span></div>`);
      }
      if (alternativeInterpretations.length) {
        rows.push(`<div class="stage-row"><strong>候选解释</strong><span>${escapeHtml(alternativeInterpretations.map(summarizeAlternativeInterpretation).filter(Boolean).join(" / "))}</span></div>`);
      }
      if (conceptSummary) {
        rows.push(`<div class="stage-row"><strong>概念命中</strong><span>${escapeHtml(conceptSummary)}</span></div>`);
      }
      rows.push(...renderConceptGroundingRows(conceptResolution, routeResult?.concept_grounding_gate));
      const followup = routeResult?.learning_followup;
      if (followup) {
        rows.push(
          `<div class="stage-row"><strong>不会原因</strong><span>${escapeHtml(followup.unable_reason || "-")}</span></div>`,
          `<div class="stage-row"><strong>询问人类</strong><span>${escapeHtml((followup.questions_for_human || []).join(" / ") || "-")}</span></div>`,
          `<div class="stage-row"><strong>后置处理</strong><span>${escapeHtml((followup.recommended_next_actions || []).map(item => item.action).join(" / ") || "-")}</span></div>`
        );
      }
      return rows;
    }

    function summarizeCloudRecallConcepts(items) {
      return (items || []).map(item => {
        const name = item.display_name || item.concept_id || "candidate";
        const confidence = typeof item.confidence === "number" ? ` / ${Math.round(item.confidence * 100)}%` : "";
        const reason = item.reason ? ` / ${item.reason}` : "";
        return `${name}${confidence}${reason}`;
      }).join(" || ");
    }

    function renderCloudRecallRows(cloudRecallPreview) {
      const rows = [];
      if (!cloudRecallPreview || !cloudRecallPreview.should_request_cloud_recall) {
        return rows;
      }
      const packet = cloudRecallPreview.cloud_recall_packet || {};
      const result = cloudRecallPreview.cloud_recall_result || {};
      const localGap = humanizeSemanticReasonList(packet.local_concept_gap || []).join(" / ") || "-";
      const candidateChain = (result.candidate_process_chain || []).join(" -> ") || "-";
      const clarificationQuestions = (result.clarification_questions || []).join(" / ") || "-";
      const candidateConcepts = summarizeCloudRecallConcepts(result.candidate_concepts || []);
      const runtimeSummary = packet.runtime_context_summary || {};
      const returnPolicy = packet.return_policy || {};
      rows.push(
        `<div class="stage-row"><strong>云脑补给</strong><span>${escapeHtml(result.availability || "simulated_cloud_brain_stub")} / ${escapeHtml(result.recall_status || "candidate_only")}</span></div>`,
        `<div class="stage-row"><strong>触发原因</strong><span>${escapeHtml(localGap)}</span></div>`,
        `<div class="stage-row"><strong>候选概念</strong><span>${escapeHtml(candidateConcepts || "暂无候选概念")}</span></div>`,
        `<div class="stage-row"><strong>候选链路</strong><span>${escapeHtml(candidateChain)}</span></div>`,
        `<div class="stage-row"><strong>需要澄清</strong><span>${escapeHtml(clarificationQuestions)}</span></div>`,
        `<div class="stage-row"><strong>当前任务摘要</strong><span>goal=${escapeHtml(runtimeSummary.goal_fact || "-")} / stage=${escapeHtml(runtimeSummary.current_stage || "-")} / facts=${escapeHtml((runtimeSummary.current_facts || []).join(", ") || "-")}</span></div>`,
        `<div class="stage-row"><strong>执行边界</strong><span>candidate_only=${escapeHtml(String(returnPolicy.candidate_only ?? result.recall_status === "candidate_only"))} / direct_execution_allowed=${escapeHtml(String(result.direct_execution_allowed))} / must_reenter_orchestration_layer=${escapeHtml(String(result.must_reenter_orchestration_layer))}</span></div>`
      );
      if ((result.candidate_process_chain || []).length) {
        const chainPayload = encodeURIComponent(JSON.stringify(result.candidate_process_chain || []));
        const goalPayload = encodeURIComponent(String(runtimeSummary.goal_fact || ""));
        rows.push(
          `<div class="stage-row"><strong>回编排层</strong><span><div class="inline-actions"><button class="secondary" data-cloud-action="prefill-chain" data-cloud-chain="${chainPayload}" data-cloud-goal="${goalPayload}">回填候选链路</button><button class="secondary" data-cloud-action="preview-chain" data-cloud-chain="${chainPayload}" data-cloud-goal="${goalPayload}">送回编排层试算</button></div></span></div>`
        );
      } else {
        rows.push(`<div class="stage-row"><strong>回编排层</strong><span>当前只有候选概念或澄清问题，需先补足链路后再试算。</span></div>`);
      }
      return rows;
    }

    function renderOrchestrationPreview(envelope, sourceLabel = "cloud_recall_candidate") {
      const routed = envelope?.route_result || envelope || {};
      const semanticRequest = envelope?.semantic_request || routed.semantic_request || {};
      const translated = routed.intent_translation || {};
      const admission = routed.space_admission || {};
      const rows = [
        `<div class="stage-row"><strong>编排层试算</strong><span>${escapeHtml(sourceLabel)} / ${escapeHtml(semanticRequest.request_type || "-")}</span></div>`,
        `<div class="stage-row"><strong>翻译结果</strong><span>${escapeHtml(translated.task_type || routed.decision || "-")} / ${escapeHtml(translated.reason || routed.reason || "-")}</span></div>`,
        `<div class="stage-row"><strong>空间准入</strong><span>${escapeHtml(admission.decision || "-")} / ${escapeHtml(admission.reason || "-")}</span></div>`,
        `<div class="stage-row"><strong>候选过程链</strong><span>${escapeHtml((translated.candidate_process_chain || []).join(" -> ") || "-")}</span></div>`,
        ...renderSemanticSignalRows(semanticRequest, routed),
        ...renderCloudRecallRows(routed.cloud_recall_preview)
      ];
      const bindings = payload.binding_candidate?.step_bindings || [];
      if (bindings.length) {
        rows.push(`<div class="stage-row"><strong>迁移空间</strong><span>${escapeHtml(payload.current_space_semantic_data?.space_id || "-")}</span></div>`);
        for (const binding of bindings) {
          const slot = binding.contract_slot?.slot_id || "-";
          const target = binding.space_binding?.target_ref || binding.object_binding?.target_ref || "未绑定";
          rows.push(`<div class="stage-row"><strong>${escapeHtml(binding.step)}</strong><span>${escapeHtml(slot)} → ${escapeHtml(target)} / ${escapeHtml(binding.capability || "-")}</span></div>`);
        }
      }
      for (const rejected of (payload.binding_candidate?.rejected_candidates || [])) {
        rows.push(`<div class="stage-row"><strong>排除候选</strong><span>${escapeHtml(rejected.slot_id || "-")} / ${escapeHtml(rejected.entity_ref || "-")} / ${escapeHtml(rejected.reason || "-")}</span></div>`);
      }
      for (const ambiguous of (payload.binding_candidate?.ambiguous_bindings || [])) {
        rows.push(`<div class="stage-row"><strong>绑定待确认</strong><span>${escapeHtml(ambiguous.slot_id || "-")} / ${escapeHtml((ambiguous.candidate_refs || []).join(", "))}</span></div>`);
      }
      factsEl.innerHTML = rows.join("");
    }

    function prefillCloudRecallCandidateChain(chain, goalFact = "") {
      const utterance = buildReadableChainUtterance(chain);
      utteranceInput.value = utterance;
      scenarioSelect.value = "auto";
      appendLog("已将云脑候选链路回填到任务输入：" + utterance);
      if (goalFact) {
        appendLog("对应目标事实：" + goalFact);
      }
      setText(stateMetric, "candidate_prefilled", "ok");
      setText(outcomeMetric, "待回编排层试算", "warn");
      serviceState.textContent = "候选已回填";
    }

    async function previewCloudRecallCandidateChain(chain, goalFact = "") {
      const utterance = buildReadableChainUtterance(chain);
      utteranceInput.value = utterance;
      scenarioSelect.value = "auto";
      serviceState.textContent = "编排层试算中";
      appendLog("将云脑候选链路送回编排层试算：" + (chain || []).join(" -> "));
      try {
        const envelope = await fetch("/agent/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ utterance, scenario: "auto", auto_execute: false })
        }).then(r => r.json());
        appendLog("云脑候选回编排层预览：" + JSON.stringify(envelope, null, 2));
        const routed = envelope.route_result || envelope;
        const semanticRequest = envelope.semantic_request || {};
        setText(admitMetric, typeof semanticRequest.intent_confidence === "number" ? formatConfidence(semanticRequest.intent_confidence) : "-", confidenceClass(semanticRequest.intent_confidence));
        setText(stateMetric, routed.intent_translation?.task_type || routed.decision || "preview");
        setText(outcomeMetric, routed.space_admission?.decision || routed.intent_translation?.decision || "preview_only", routed.space_admission?.decision === "allowed" ? "ok" : "warn");
        setText(taskMetric, goalFact || routed.intent_translation?.goal_fact || "-");
        if (!routed.cloud_recall_preview) {
          routed.cloud_recall_preview = {
            should_request_cloud_recall: false,
            cloud_recall_result: {
              candidate_process_chain: chain || [],
              direct_execution_allowed: false,
              must_reenter_orchestration_layer: true,
            },
          };
        }
        renderOrchestrationPreview({ semantic_request: semanticRequest, route_result: routed }, "cloud_recall_candidate");
        serviceState.textContent = "编排层已试算";
      } catch (error) {
        serviceState.textContent = "异常";
        appendLog("云脑候选试算异常：" + error.message);
      }
    }

    function renderRuntimeExplanationRows(explanationView, refusalSource = "") {
      const rows = [];
      if (!explanationView) {
        return rows;
      }
      const taskState = explanationView.time_layers?.task_state || {};
      const sessionState = explanationView.time_layers?.session_state || {};
      const immediateState = explanationView.time_layers?.immediate_state || {};
      const answers = explanationView.status_answers || {};
      rows.push(
        `<div class="stage-row"><strong>状态解释来源</strong><span>${escapeHtml(explanationView.source_policy || "-")}</span></div>`,
        `<div class="stage-row"><strong>当前动作</strong><span>${escapeHtml(answers.current_action?.answer || immediateState.current_action || "-")}</span></div>`,
        `<div class="stage-row"><strong>下一步</strong><span>${escapeHtml(answers.next_step?.answer || taskState.next_step || "-")} / ${escapeHtml(answers.next_step?.reason || taskState.next_step_reason || "-")}</span></div>`,
        `<div class="stage-row"><strong>目标事实</strong><span>${escapeHtml(answers.goal_fact?.answer || taskState.goal_fact || "-")}</span></div>`,
        `<div class="stage-row"><strong>任务进度</strong><span>current=${escapeHtml(taskState.current_stage || "-")} / completed=${escapeHtml((taskState.completed_stages || []).join(" -> ") || "-")}</span></div>`
      );
      if (immediateState.last_blocked_step || immediateState.last_route_adjustment) {
        rows.push(`<div class="stage-row"><strong>即时调整</strong><span>${escapeHtml(immediateState.last_blocked_step || "-")} / ${escapeHtml(immediateState.last_route_adjustment?.adjustment_type || "-")}</span></div>`);
      }
      if ((sessionState.active_preferences || []).length || sessionState.experience_gap_record_id) {
        rows.push(`<div class="stage-row"><strong>会话约束</strong><span>preferences=${escapeHtml(String((sessionState.active_preferences || []).length))} / gap=${escapeHtml(sessionState.experience_gap_record_id || "-")}</span></div>`);
      }
      if (refusalSource) {
        rows.push(`<div class="stage-row"><strong>阻断来源</strong><span>${escapeHtml(refusalSource)}</span></div>`);
      }
      return rows;
    }

    function renderStateQueryResult(envelope, routed, question, taskId) {
      const semanticRequest = envelope?.semantic_request || {};
      setText(admitMetric, formatConfidence(semanticRequest.intent_confidence), confidenceClass(semanticRequest.intent_confidence));
      setText(stateMetric, routed.runtime_explanation_view?.time_layers?.task_state?.current_stage || routed.evidence?.current_stage || "-");
      setText(outcomeMetric, "状态已回答", "ok");
      setText(taskMetric, taskId || currentTeachingSessionId || currentMigrationTaskId || "-");
      const rows = [
        `<div class="stage-row"><strong>状态问题</strong><span>${escapeHtml(routed.question || question)}</span></div>`,
        `<div class="stage-row"><strong>回答</strong><span>${escapeHtml(String(routed.answer))}</span></div>`,
        `<div class="stage-row"><strong>依据</strong><span>${escapeHtml(routed.reason || "-")}</span></div>`,
        `<div class="stage-row"><strong>来源</strong><span>${escapeHtml(routed.source || "-")}</span></div>`,
        ...renderSemanticSignalRows(semanticRequest, routed),
        ...renderCloudRecallRows(routed.cloud_recall_preview),
        ...renderRuntimeExplanationRows(routed.runtime_explanation_view, routed.refusal_source)
      ];
      const evidence = routed.evidence || {};
      if (evidence.object_state_facts) {
        rows.push(`<div class="stage-row"><strong>对象事实</strong><span>${escapeHtml((evidence.object_state_facts || []).join(", "))}</span></div>`);
      }
      if (evidence.established_facts) {
        rows.push(`<div class="stage-row"><strong>已成立事实</strong><span>${escapeHtml((evidence.established_facts || []).join(", "))}</span></div>`);
      }
      if (evidence.holding) {
        rows.push(`<div class="stage-row"><strong>当前持有</strong><span>${escapeHtml((evidence.holding || []).join(", ") || "none")}</span></div>`);
      }
      if (evidence.executor_location_ref) {
        rows.push(`<div class="stage-row"><strong>当前位置</strong><span>${escapeHtml(evidence.executor_location_ref)}</span></div>`);
      }
      if (evidence.current_stage || evidence.completed_stages) {
        rows.push(`<div class="stage-row"><strong>执行进度</strong><span>current=${escapeHtml(evidence.current_stage || "-")} / completed=${escapeHtml((evidence.completed_stages || []).join(" -> ") || "-")}</span></div>`);
      }
      factsEl.innerHTML = rows.join("");
    }

    function renderTeachingRoutePreview(envelope, routed) {
      const semanticRequest = envelope?.semantic_request || {};
      setText(admitMetric, formatConfidence(semanticRequest.intent_confidence), confidenceClass(semanticRequest.intent_confidence));
      setText(stateMetric, routed.decision || "routed_to_teaching", semanticRequest.clarification_needed ? "warn" : "ok");
      setText(outcomeMetric, semanticRequest.clarification_needed ? "待补充教学" : "已理解教学", semanticRequest.clarification_needed ? "warn" : "ok");
      setText(taskMetric, currentTeachingSessionId || currentMigrationTaskId || "-");
      const rows = [
        `<div class="stage-row"><strong>教学复述</strong><span>${escapeHtml(routed.teaching_feedback?.acknowledgement || "-")}</span></div>`,
        `<div class="stage-row"><strong>推荐入口</strong><span>${escapeHtml(routed.recommended_next_endpoint || "-")}</span></div>`,
        `<div class="stage-row"><strong>目标事实</strong><span>${escapeHtml(routed.goal_fact || "-")}</span></div>`,
        `<div class="stage-row"><strong>解析步骤</strong><span>${escapeHtml((routed.parsed_steps || []).join(" -> ") || "-")}</span></div>`,
        ...renderSemanticSignalRows(semanticRequest, routed),
        ...renderCloudRecallRows(routed.cloud_recall_preview)
      ];
      factsEl.innerHTML = rows.join("");
    }

    function describeCausalReasoning(reasoning) {
      return (reasoning || []).map(item => {
        if (item.status === "already_established") {
          return `事实 ${item.fact} 已由当前世界状态确认`;
        }
        const reqs = (item.requires_facts || []).length ? item.requires_facts.join(", ") : "无外部前提";
        const expanded = (item.expanded_process_chain || []).join(" -> ");
        return `为达成 ${item.fact}，调用 ${item.process}；需要 ${reqs}；产出 ${item.produces_fact}` + (expanded ? `；展开为 ${expanded}` : "");
      });
    }

    function renderFacts(result) {
      const audit = result.audit_summary || { stage_summary: [], fact_summary: [] };
      const stages = audit.stage_summary || [];
      const facts = audit.fact_summary || [];
      const rows = [];
      rows.push(...renderSemanticSignalRows(result.semantic_request, result));
      rows.push(...renderCloudRecallRows(result.cloud_recall_preview));
      rows.push(`<div class="stage-row"><strong>阶段结果</strong><span>${stages.length ? "" : "暂无阶段摘要"}</span></div>`);
      if (result.intent_translation) {
        rows.push(`<div class="stage-row"><strong>翻译层</strong><span>${result.intent_translation.task_type}: ${result.intent_translation.reason}</span></div>`);
      }
      const frame = result.intent_translation?.intent_frame;
      if (frame) {
        const spatial = (frame.spatial_constraints || []).map(item => `${item.source_text}->${item.region_ref}`).join(" / ");
        const objects = (frame.object_constraints || []).map(item => `${item.source_text}->${item.object_ref}`).join(" / ");
        const concepts = (frame.concept_matches || []).map(item => `${item.display_name}(${item.concept_level})`).join(" / ");
        rows.push(`<div class="stage-row"><strong>P012 意图帧</strong><span>${frame.translation_mode} / 目标事实：${frame.goal_fact || "-"}</span></div>`);
        rows.push(`<div class="stage-row"><strong>空间约束</strong><span>${escapeHtml(spatial || "未抽取到显式空间目标")}</span></div>`);
        rows.push(`<div class="stage-row"><strong>对象约束</strong><span>${escapeHtml(objects || "未抽取到显式对象目标")}</span></div>`);
        rows.push(`<div class="stage-row"><strong>概念匹配</strong><span>${escapeHtml(concepts || "暂无概念候选")}</span></div>`);
      }
      if (result.intent_translation?.causal_plan) {
        rows.push(`<div class="stage-row"><strong>目标事实</strong><span>${result.intent_translation.goal_fact}</span></div>`);
        rows.push(`<div class="stage-row"><strong>因果链</strong><span>${(result.intent_translation.causal_plan.process_chain || []).join(" -> ")}</span></div>`);
        rows.push(`<div class="stage-row"><strong>初始事实</strong><span>${(result.intent_translation.causal_plan.initial_facts || []).join(", ")}</span></div>`);
        const reasoningRows = describeCausalReasoning(result.intent_translation.causal_plan.reasoning);
        rows.push(`<div class="stage-row"><strong>因果推理展开</strong><span>${reasoningRows.length ? "" : "暂无推理记录"}</span></div>`);
        for (const line of reasoningRows) {
          rows.push(`<div class="stage-row"><strong>推理</strong><span>${escapeHtml(line)}</span></div>`);
        }
      }
      if (result.space_admission) {
        rows.push(`<div class="stage-row"><strong>空间准入</strong><span>${result.space_admission.decision}: ${result.space_admission.reason}</span></div>`);
      }
      const runtimeWorld = result.runtime_world_state || result.stage_runtime_state?.runtime_world_state || result.execution_trace?.runtime_world_state_final;
      if (runtimeWorld) {
        const executor = runtimeWorld.executor || {};
        const holding = (executor.holding || []).join(", ") || "none";
        const facts = (runtimeWorld.established_facts || []).join(", ");
        const activePreferences = runtimeWorld.active_preferences || [];
        rows.push(`<div class="stage-row"><strong>运行时世界状态</strong><span>${runtimeWorld.lifecycle || "ephemeral"} / ${executor.location_ref || "-"}</span></div>`);
        rows.push(`<div class="stage-row"><strong>端侧工作记忆</strong><span>holding=${escapeHtml(holding)}；facts=${escapeHtml(facts)}</span></div>`);
        if (activePreferences.length) {
          rows.push(`<div class="stage-row"><strong>P015 偏好约束</strong><span>${escapeHtml(activePreferences.map(item => item.preference_id).join(", "))}</span></div>`);
        }
        const runtimeEnv = runtimeWorld.runtime_environment || {};
        if ((runtimeEnv.active_perturbations || []).length || (runtimeEnv.scheduled_perturbations || []).length || runtimeEnv.last_preflight) {
          rows.push(`<div class="stage-row"><strong>偶然层扰动</strong><span>active=${escapeHtml(String((runtimeEnv.active_perturbations || []).length))} / scheduled=${escapeHtml(String((runtimeEnv.scheduled_perturbations || []).length))}</span></div>`);
          if (runtimeEnv.last_preflight) {
            rows.push(`<div class="stage-row"><strong>步骤前预检</strong><span>${escapeHtml(runtimeEnv.last_preflight.step || "-")} / ${escapeHtml(runtimeEnv.last_preflight.result || "-")}</span></div>`);
          }
        }
      }
      if (result.stepwise_readaptation) {
        const readapt = result.stepwise_readaptation;
        rows.push(`<div class="stage-row"><strong>重新适配</strong><span>${escapeHtml(readapt.readaptation_id || "-")} / ${escapeHtml(readapt.trigger || "-")}</span></div>`);
        rows.push(`<div class="stage-row"><strong>剩余步骤</strong><span>${escapeHtml((readapt.remaining_steps || []).join(" -> ") || "-")}</span></div>`);
        rows.push(`<div class="stage-row"><strong>刷新可行性</strong><span>${escapeHtml(readapt.execution_feasibility?.result || "-")}</span></div>`);
      }
      if (result.teaching_hint?.teachable) {
        rows.push(`<div class="stage-row"><strong>可教学</strong><span>${result.teaching_hint.reason}</span></div>`);
        rows.push(`<div class="stage-row"><strong>候选链路</strong><span>${(result.teaching_hint.candidate_process_chain || []).join(" -> ")}</span></div>`);
        rows.push(`<div class="stage-row"><strong>下一步</strong><span>当前任务尚未入库，点击“对话教学”或“教学入库”形成经验后再运行。</span></div>`);
      }
      if (result.experience_ref) {
        rows.push(`<div class="stage-row"><strong>经验命中</strong><span>${result.experience_ref}</span></div>`);
      }
      for (const stage of stages) {
        rows.push(`<div class="stage-row"><strong>${stage.stage_id}: ${stage.result}</strong><span>${stage.notes || ""}</span></div>`);
      }
      rows.push(`<div class="stage-row"><strong>事实验真</strong><span>${facts.length ? "" : "暂无事实摘要"}</span></div>`);
      for (const fact of facts) {
        rows.push(`<div class="stage-row"><strong>${fact.fact_id}: ${fact.state}</strong><span>${fact.channel_notes || ""}</span></div>`);
      }
      if (audit.stop_reason) {
        rows.push(`<div class="stage-row"><strong>停止原因</strong><span>${audit.stop_reason}</span></div>`);
      }
      const profile = result.admission_decision?.executor_profile;
      if (profile) {
        rows.push(`<div class="stage-row"><strong>执行体画像</strong><span>${profile.executor_type} / ${profile.body_profile} / ${profile.end_effector_type}</span></div>`);
        rows.push(`<div class="stage-row"><strong>空间约束预留</strong><span>${profile.spatial_entry_constraints?.body_envelope?.shape || "reserved"} envelope, P008 entry constraints reserved</span></div>`);
      }
      const space = result.space_context;
      if (space) {
        rows.push(`<div class="stage-row"><strong>数字空间</strong><span>${space.space_id} / ${space.cognitive_model_id}</span></div>`);
        rows.push(`<div class="stage-row"><strong>空间节点</strong><span>${space.region_count} regions, ${space.relation_count} relations, ${space.object_count} objects</span></div>`);
      }
      factsEl.innerHTML = rows.join("");
    }

    function hydrateTeachingFields(result) {
      const chain = result.teaching_hint?.candidate_process_chain || result.intent_translation?.candidate_process_chain || [];
      if (!chain.length) return;
      const readableSteps = chain.map(step => stepDisplayNameMap[step] || step).join("\\n");
      const utterance = utteranceInput.value.trim();
      if (result.teaching_hint?.teachable || !document.getElementById("teachingSteps").value.trim()) {
        document.getElementById("teachingSteps").value = readableSteps;
      }
      if (result.teaching_hint?.teachable || !document.getElementById("dialogueTeaching").value.trim()) {
        document.getElementById("dialogueTeaching").value = "教你：" + (utterance || buildReadableChainUtterance(chain));
      }
      appendLog("已根据候选链路填充教学区，需教学入库后再执行。");
    }

    function buildStepEventFromFeedback(feedback) {
      const targets = {
        move_to_doorway: "region_doorway",
        move_to_service_position: "region_service_position",
        move_to_counter: "region_counter_operation",
        pick_up_cup: "object_cup_white_mug",
        move_to_water_source: "region_water_source",
        fill_cup_at_water_source: "region_water_source",
        pour_water: "region_counter_operation"
      };
      return {
        trigger_reason: "learned_step_executed",
        payload_summary: `step=${feedback.step} display=${feedback.display_name || feedback.step} target=${targets[feedback.step] || "-"}`
      };
    }

    function renderConceptCandidateRows(candidates) {
      const items = candidates || [];
      if (!items.length) {
        return [`<div class="stage-row"><strong>概念晋升</strong><span>暂无候选</span></div>`];
      }
      const rows = [`<div class="stage-row"><strong>概念晋升</strong><span>已生成 ${items.length} 个待人工确认候选</span></div>`];
      for (const item of items) {
        rows.push(`<div class="stage-row"><strong>${escapeHtml(item.candidate_id || "-")}</strong><span>${escapeHtml(item.proposal_type || "-")} -> ${escapeHtml(item.target_concept_id || "-")}</span></div>`);
      }
      rows.push(`<div class="stage-row"><strong>确认方式</strong><span>调用 POST /concept/candidates/confirm 并传入 candidate_id。</span></div>`);
      return rows;
    }

    function selectConceptCandidate(candidates) {
      const pending = (candidates || []).find(item => item.status !== "promoted");
      const selected = pending || (candidates || [])[0];
      currentConceptCandidateId = selected?.candidate_id || "";
      conceptCandidateIdInput.value = currentConceptCandidateId;
      return selected;
    }

    function renderStepwiseTeaching(result) {
      setText(taskMetric, result.session_id || currentTeachingSessionId || "-");
      setText(stateMetric, result.status || "-");
      const status = result.status || "";
      const ok = status.includes("goal_achieved") || status === "experience_saved";
      const warn = status.includes("awaiting") || status.includes("teaching_in_progress");
      setText(outcomeMetric, ok ? "目标可固化" : status || "-", ok ? "ok" : (warn ? "warn" : ""));
      setText(admitMetric, "digital_executor", "ok");
      const state = result.runtime_world_state_snapshot || {};
      const executor = state.executor || {};
      const feedback = result.step_feedback || [];
      for (const item of feedback) {
        if (item.executed) {
          updateLearnedStepScene(buildStepEventFromFeedback(item));
        }
      }
      const rows = [
        `<div class="stage-row"><strong>边教边动会话</strong><span>${escapeHtml(result.session_id || currentTeachingSessionId || "-")} / ${escapeHtml(status || "-")}</span></div>`,
        `<div class="stage-row"><strong>目标事实</strong><span>${escapeHtml(result.goal_fact || "-")}</span></div>`,
        `<div class="stage-row"><strong>数字执行主体</strong><span>${escapeHtml(executor.location_ref || "-")} / holding=${escapeHtml((executor.holding || []).join(", ") || "none")}</span></div>`,
        `<div class="stage-row"><strong>已教链路</strong><span>${escapeHtml((result.process_chain || []).join(" -> ") || "暂无")}</span></div>`
      ];
      for (const item of feedback) {
        const produced = (item.causal_produced_facts || []).join(", ") || "-";
        const missing = (item.missing_before_step || []).join(", ") || "-";
        const hints = (item.prerequisite_hints || []).map(h => h.suggested_display_name || h.missing_fact).join(" / ");
        rows.push(`<div class="stage-row"><strong>${escapeHtml(item.display_name || item.step)}</strong><span>${item.executed ? "已执行" : "未执行"}；产出=${escapeHtml(produced)}；缺口=${escapeHtml(missing)}${hints ? "；建议先教：" + escapeHtml(hints) : ""}</span></div>`);
      }
      const facts = (state.established_facts || []).join(", ");
      rows.push(`<div class="stage-row"><strong>当前事实</strong><span>${escapeHtml(facts || "-")}</span></div>`);
      factsEl.innerHTML = rows.join("");
    }

    async function runProcess() {
      const activeTaskId = currentTeachingSessionId || currentMigrationTaskId || taskMetric.textContent.trim();
      clearView({ resetContext: false });
      if (currentRuntimeWorldState && activeTaskId) {
        applyRuntimeWorldStateToScene(currentRuntimeWorldState);
      }
      runButton.disabled = true;
      serviceState.textContent = "运行中";
      appendLog("接收任务：" + document.getElementById("utterance").value.trim());
      const utterance = document.getElementById("utterance").value.trim();
      appendLog("统一语义入口解析中...");
      try {
        const previewEnvelope = await fetch("/agent/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ utterance, scenario: "auto", auto_execute: false, task_id: activeTaskId || null })
        }).then(r => r.json());
        appendLog("语义路由结果：" + JSON.stringify(previewEnvelope, null, 2));
        const preview = previewEnvelope.route_result || previewEnvelope;
        const translated = preview.intent_translation || {};
        const admit = preview.space_admission || {};
        const semanticRequest = previewEnvelope.semantic_request || {};
        const runtimeEventArbitration = preview.runtime_event_arbitration || null;
        if (typeof semanticRequest.intent_confidence === "number") {
          setText(admitMetric, formatConfidence(semanticRequest.intent_confidence), confidenceClass(semanticRequest.intent_confidence));
        } else {
          setText(admitMetric, admit.decision || "unknown", admit.allowed ? "ok" : "bad");
        }
        appendLog("空间准入预览：" + JSON.stringify(admit, null, 2));
        appendLog("语义路由：" + (previewEnvelope.semantic_request?.request_type || "unknown") + " / " + (previewEnvelope.semantic_request?.preferred_model_tier || "unknown"));
        if (preview.cloud_recall_preview?.should_request_cloud_recall) {
          const localGap = (preview.cloud_recall_preview.cloud_recall_packet?.local_concept_gap || []).join(" / ");
          const candidateConcepts = (preview.cloud_recall_preview.cloud_recall_result?.candidate_concepts || []).map(item => item.display_name || item.concept_id).join(" / ");
          const candidateChain = (preview.cloud_recall_preview.cloud_recall_result?.candidate_process_chain || []).join(" -> ");
          appendLog("云脑补给桥触发：" + (localGap || "unknown_gap"));
          if (candidateConcepts) {
            appendLog("云脑候选概念：" + candidateConcepts);
          }
          if (candidateChain) {
            appendLog("云脑候选链路：" + candidateChain);
          }
        }

        if (["clarification_required", "concept_grounding_required"].includes(preview.decision)) {
          setText(stateMetric, preview.decision, "warn");
          setText(outcomeMetric, "需要澄清", "warn");
          setText(taskMetric, currentMigrationTaskId || "-");
          factsEl.innerHTML = [
            `<div class="stage-row"><strong>任务澄清</strong><span>${escapeHtml(preview.clarification_prompt || "当前输入还不能直接进入执行，需要先补充共享参照或动作语义。")}</span></div>`,
            ...renderSemanticSignalRows(semanticRequest, preview),
            ...renderCloudRecallRows(preview.cloud_recall_preview)
          ].join("");
          serviceState.textContent = "等待澄清";
          const recallQuestions = preview.cloud_recall_preview?.cloud_recall_result?.clarification_questions || [];
          if (recallQuestions.length) {
            appendLog("云脑候选补给：" + recallQuestions.join(" / "));
          }
          appendLog("当前任务需要先澄清，暂不进入执行。");
          return;
        }

        if (preview.decision === "routed_to_teaching") {
          renderTeachingRoutePreview(previewEnvelope, preview);
          serviceState.textContent = "教学预览";
          appendLog("当前输入已进入教学语义预览。");
          return;
        }

        const scenario = document.getElementById("scenario").value;
        if (admit.allowed && translated.task_type === "pour_water") {
          appendLog("加载过程模板：pour_water");
          appendLog("绑定当前环境：home_a_kitchen_daytime");
        } else if (admit.allowed && translated.task_type === "learned_process_chain") {
          appendLog("加载教学经验链：" + translated.experience_id);
        } else if (admit.allowed && translated.task_type === "causal_process_chain") {
          appendLog("因果层目标事实：" + translated.goal_fact);
          appendLog("因果层生成过程链：" + translated.candidate_process_chain.join(" -> "));
        }
        appendLog("启动场景：" + scenario);
        const executionEnvelope = await fetch("/agent/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ scenario, utterance, auto_execute: true, task_id: activeTaskId || null })
        }).then(r => r.json());
        appendLog("统一入口执行结果：" + JSON.stringify(executionEnvelope, null, 2));
        const result = executionEnvelope.route_result || executionEnvelope;
        result.semantic_request = executionEnvelope.semantic_request || semanticRequest;
        if (!result.cloud_recall_preview && preview.cloud_recall_preview) {
          result.cloud_recall_preview = preview.cloud_recall_preview;
        }

        currentMigrationTaskId = result.task_id || currentMigrationTaskId || activeTaskId || "";
        const runtimeWorldInitial = result.execution_trace?.runtime_world_state_initial || currentRuntimeWorldState;
        const runtimeWorldFinal = result.runtime_world_state || result.stage_runtime_state?.runtime_world_state || result.execution_trace?.runtime_world_state_final || null;
        if (runtimeWorldInitial) {
          applyRuntimeWorldStateToScene(runtimeWorldInitial);
        }
        currentRuntimeWorldState = runtimeWorldFinal || currentRuntimeWorldState;
        setText(taskMetric, result.task_id || currentMigrationTaskId || "-");
        setText(stateMetric, result.stage_runtime_state.runtime_state);
        const outcomeClass = result.audit_summary.outcome === "completed" ? "ok" : (result.audit_summary.outcome === "cannot_do" ? "bad" : "warn");
        setText(outcomeMetric, result.audit_summary.outcome, outcomeClass);

        const events = result.execution_trace.events || [];
        for (const event of events) {
          const delayMs = (event.trigger_reason === "learned_step_executed" || event.trigger_reason === "causal_step_executed") ? 760 : 180;
          await new Promise(resolve => setTimeout(resolve, delayMs));
          appendLog(describeTrace(event));
          updateSceneFromEvent(event);
        }
        renderFacts(result);
        hydrateTeachingFields(result);
        serviceState.textContent = result.audit_summary.outcome === "completed" ? "完成" : (result.audit_summary.outcome === "cannot_do" ? "不会做" : "等待人工确认");
      } catch (error) {
        serviceState.textContent = "异常";
        appendLog("运行异常：" + error.message);
      } finally {
        runButton.disabled = false;
      }
    }

    async function teachExperience() {
      teachButton.disabled = true;
      serviceState.textContent = "教学中";
      const utterance = document.getElementById("utterance").value.trim();
      const steps = document.getElementById("teachingSteps").value.trim();
      appendLog("提交人工教学：" + utterance);
      try {
        const result = await fetch("/experience/teach", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ utterance, steps })
        }).then(r => r.json());
        appendLog("教学结果：" + JSON.stringify(result, null, 2));
        if (result.decision === "experience_created") {
          setText(admitMetric, "learned", "ok");
          setText(stateMetric, "candidate_created", "ok");
          setText(outcomeMetric, "可回放", "ok");
          setText(taskMetric, result.experience.experience_id);
          const signature = result.experience.causal_signature || {};
          const conceptRows = renderConceptCandidateRows(result.concept_promotion_candidates);
          selectConceptCandidate(result.concept_promotion_candidates);
          factsEl.innerHTML = [
            `<div class="stage-row"><strong>经验形成</strong><span>${result.message}</span></div>`,
            `<div class="stage-row"><strong>过程链</strong><span>${result.experience.process_chain.join(" -> ")}</span></div>`,
            `<div class="stage-row"><strong>因果签名</strong><span>requires: ${(signature.requires_facts || []).join(", ") || "none"} / produces: ${signature.produces_fact || "-"}</span></div>`,
            `<div class="stage-row"><strong>不变量契约</strong><span>${result.experience.invariant_contract?.storage_policy || "-"}</span></div>`,
            `<div class="stage-row"><strong>下一步</strong><span>再次点击运行，将由数字执行体按经验链回放。</span></div>`,
            ...conceptRows
          ].join("");
          serviceState.textContent = "已学习";
        } else {
          setText(outcomeMetric, "教学失败", "bad");
          serviceState.textContent = "教学失败";
        }
      } catch (error) {
        serviceState.textContent = "异常";
        appendLog("教学异常：" + error.message);
      } finally {
        teachButton.disabled = false;
      }
    }

    async function teachByDialogue() {
      dialogueTeachButton.disabled = true;
      serviceState.textContent = "对话教学中";
      const utterance = document.getElementById("utterance").value.trim();
      const message = document.getElementById("dialogueTeaching").value.trim() || utterance;
      appendLog("提交对话教学：" + message);
      try {
        const result = await fetch("/experience/dialogue-teach", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ utterance, message })
        }).then(r => r.json());
        appendLog("对话教学结果：" + JSON.stringify(result, null, 2));
        if (result.decision === "experience_created") {
          setText(admitMetric, "learned", "ok");
          setText(stateMetric, "candidate_created", "ok");
          setText(outcomeMetric, "可回放", "ok");
          setText(taskMetric, result.experience.experience_id);
          const signature = result.experience.causal_signature || {};
          const conceptRows = renderConceptCandidateRows(result.concept_promotion_candidates);
          selectConceptCandidate(result.concept_promotion_candidates);
          factsEl.innerHTML = [
            `<div class="stage-row"><strong>经验形成</strong><span>${result.message}</span></div>`,
            `<div class="stage-row"><strong>过程链</strong><span>${result.experience.process_chain.join(" -> ")}</span></div>`,
            `<div class="stage-row"><strong>因果签名</strong><span>requires: ${(signature.requires_facts || []).join(", ") || "none"} / produces: ${signature.produces_fact || "-"}</span></div>`,
            `<div class="stage-row"><strong>不变量契约</strong><span>${result.experience.invariant_contract?.storage_policy || "-"}</span></div>`,
            `<div class="stage-row"><strong>来源</strong><span>dialogue_teaching</span></div>`,
            ...conceptRows
          ].join("");
          serviceState.textContent = "已学习";
        } else {
          setText(outcomeMetric, "教学失败", "bad");
          serviceState.textContent = "教学失败";
        }
      } catch (error) {
        serviceState.textContent = "异常";
        appendLog("对话教学异常：" + error.message);
      } finally {
        dialogueTeachButton.disabled = false;
      }
    }

    async function showExperienceLibrary() {
      const result = await fetch("/experience/library").then(r => r.json());
      appendLog("经验库：" + JSON.stringify(result, null, 2));
      const experiences = result.experiences || [];
      factsEl.innerHTML = experiences.length
        ? experiences.map(item => {
            const signature = item.causal_signature || {};
            const invariant = item.invariant_contract || {};
            return `<div class="stage-row"><strong>${item.experience_id}</strong><span>${item.source_utterance} / ${item.process_chain.join(" -> ")} / produces: ${signature.produces_fact || item.goal_fact} / invariants: ${invariant.storage_policy || "-"}</span></div>`;
          }).join("")
        : `<div class="stage-row"><strong>经验库</strong><span>暂无经验</span></div>`;
    }

    async function showConceptCandidates() {
      conceptCandidatesButton.disabled = true;
      serviceState.textContent = "读取概念候选";
      try {
        const result = await fetch("/concept/candidates").then(r => r.json());
        appendLog("概念候选库：" + JSON.stringify(result, null, 2));
        const candidates = result.concept_candidates || [];
        const selected = selectConceptCandidate(candidates);
        const rows = [
          `<div class="stage-row"><strong>概念候选数量</strong><span>${candidates.length}</span></div>`,
          `<div class="stage-row"><strong>当前候选</strong><span>${escapeHtml(selected?.candidate_id || "暂无待确认候选")}</span></div>`
        ];
        for (const item of candidates) {
          rows.push(`<div class="stage-row"><strong>${escapeHtml(item.candidate_id || "-")}</strong><span>${escapeHtml(item.proposal_type || "-")} / ${escapeHtml(item.target_concept_id || "-")} / ${escapeHtml(item.status || "-")}</span></div>`);
        }
        factsEl.innerHTML = rows.join("");
        serviceState.textContent = "候选已读取";
      } catch (error) {
        serviceState.textContent = "异常";
        appendLog("概念候选读取异常：" + error.message);
      } finally {
        conceptCandidatesButton.disabled = false;
      }
    }

    function pickField(payload, path) {
      return path.split(".").reduce((value, key) => value && value[key], payload);
    }

    async function showP017MinimalLoop() {
      p017Button.disabled = true;
      serviceState.textContent = "读取 P017 证据";
      try {
        const result = await fetch("/p017/minimal-loop").then(r => r.json());
        if (result.error) {
          factsEl.innerHTML = `<div class="stage-row"><strong>P017 最小闭环</strong><span>${escapeHtml(result.error)}：请先运行 python demo_runtime\\rell_sample\\validate_p017_minimal_loop.py</span></div>`;
          appendLog("P017 最小闭环证据读取失败：" + JSON.stringify(result, null, 2));
          return;
        }
        appendLog("P017 最小闭环证据：" + JSON.stringify(result.summary, null, 2));
        setText(admitMetric, "P017", "ok");
        setText(stateMetric, "minimal_loop", "ok");
        setText(outcomeMetric, "evidence_ready", "ok");
        setText(taskMetric, result.summary?.migration_task_id || "-");
        const items = result.evidence_index?.evidence_items || [];
        const files = result.evidence_files || {};
        const rows = [
          `<div class="stage-row"><strong>P017 最小闭环证据</strong><span>${escapeHtml(result.evidence_index?.summary || "六段最小闭环工程证据")}</span></div>`,
          `<div class="stage-row"><strong>输出目录</strong><span>${escapeHtml(result.output_dir || "-")}</span></div>`
        ];
        for (const item of items) {
          const payload = files[item.file] || {};
          const fields = (item.key_fields || []).map(field => {
            const value = pickField(payload, field);
            const text = Array.isArray(value) ? `${value.length} item(s)` : (typeof value === "object" && value ? JSON.stringify(value) : value);
            return `<span><code>${escapeHtml(field)}</code> = ${escapeHtml(text ?? "-")}</span>`;
          }).join("");
          rows.push(`
            <details class="p017-card">
              <summary>${escapeHtml(item.file)}｜${escapeHtml(item.claim_1_step)}</summary>
              <span><strong>技术特征：</strong>${escapeHtml(item.technical_feature)}</span>
              <span><strong>代码来源：</strong>${escapeHtml((item.code_sources || []).join(" / "))}</span>
              <span><strong>审查用途：</strong>${escapeHtml(item.examination_use || "-")}</span>
              <div>${fields}</div>
              <pre class="p017-json">${escapeHtml(JSON.stringify(payload, null, 2))}</pre>
            </details>
          `);
        }
        factsEl.innerHTML = rows.join("");
        serviceState.textContent = "P017 证据就绪";
      } catch (error) {
        serviceState.textContent = "异常";
        appendLog("P017 最小闭环读取异常：" + error.message);
      } finally {
        p017Button.disabled = false;
      }
    }

    async function startStepwiseTeaching() {
      startTeachingSessionButton.disabled = true;
      serviceState.textContent = "启动教学会话";
      const utterance = document.getElementById("utterance").value.trim();
      appendLog("启动边教边动会话：" + utterance);
      try {
        const result = await fetch("/teaching/session/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ utterance, space_id: migrationSpace.value })
        }).then(r => r.json());
        appendLog("边教边动会话：" + JSON.stringify(result, null, 2));
        if (result.error) {
          serviceState.textContent = "会话失败";
          setText(outcomeMetric, "会话失败", "bad");
          return;
        }
        currentTeachingSessionId = result.session_id;
        renderStepwiseTeaching(result);
        serviceState.textContent = "教学会话中";
      } catch (error) {
        serviceState.textContent = "异常";
        appendLog("边教边动启动异常：" + error.message);
      } finally {
        startTeachingSessionButton.disabled = false;
      }
    }

    async function executeStepwiseTeaching() {
      stepTeachingSessionButton.disabled = true;
      serviceState.textContent = "执行教学步骤";
      const teachingInput = document.getElementById("stepwiseTeaching").value.trim();
      appendLog("本次教学步骤：" + teachingInput);
      try {
        if (!currentTeachingSessionId) {
          const startResult = await fetch("/teaching/session/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ utterance: document.getElementById("utterance").value.trim() })
          }).then(r => r.json());
          if (startResult.error) {
            appendLog("自动启动教学会话失败：" + JSON.stringify(startResult, null, 2));
            return;
          }
          currentTeachingSessionId = startResult.session_id;
          appendLog("自动启动教学会话：" + currentTeachingSessionId);
        }
        const result = await fetch("/teaching/session/step", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: currentTeachingSessionId, teaching_input: teachingInput })
        }).then(r => r.json());
        appendLog("教学执行反馈：" + JSON.stringify(result, null, 2));
        if (result.error) {
          serviceState.textContent = "步骤失败";
          setText(outcomeMetric, "步骤失败", "bad");
          return;
        }
        renderStepwiseTeaching(result);
        serviceState.textContent = result.status === "goal_achieved_pending_confirmation" ? "目标已达成" : "等待下一步";
      } catch (error) {
        serviceState.textContent = "异常";
        appendLog("教学步骤异常：" + error.message);
      } finally {
        stepTeachingSessionButton.disabled = false;
      }
    }

    async function finishStepwiseTeaching() {
      finishTeachingSessionButton.disabled = true;
      serviceState.textContent = "固化经验";
      try {
        if (!currentTeachingSessionId) {
          serviceState.textContent = "无会话";
          appendLog("尚未启动边教边动会话。");
          return;
        }
        const result = await fetch("/teaching/session/finish", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: currentTeachingSessionId, success_confirmed: true })
        }).then(r => r.json());
        appendLog("边教边动入库结果：" + JSON.stringify(result, null, 2));
        if (result.error) {
          serviceState.textContent = "入库失败";
          setText(outcomeMetric, "入库失败", "bad");
          return;
        }
        const experience = result.experience_result?.experience;
        setText(stateMetric, result.status || "-");
        setText(outcomeMetric, result.status === "experience_saved" ? "经验已入库" : "未入库", result.status === "experience_saved" ? "ok" : "warn");
        setText(taskMetric, experience?.experience_id || currentTeachingSessionId);
        renderStepwiseTeaching({
          session_id: currentTeachingSessionId,
          status: result.status,
          goal_fact: result.goal_fact,
          process_chain: experience?.process_chain || [],
          runtime_world_state_snapshot: result.runtime_world_state_snapshot,
          step_feedback: []
        });
        if (experience) {
          appendLog("已固化经验：" + experience.experience_id + " / " + experience.process_chain.join(" -> "));
          const conceptCandidates = result.experience_result?.concept_promotion_candidates || [];
          selectConceptCandidate(conceptCandidates);
          for (const item of conceptCandidates) {
            appendLog("概念候选：" + item.candidate_id + " / " + item.proposal_type + " -> " + item.target_concept_id);
          }
        }
        serviceState.textContent = result.status === "experience_saved" ? "已学习" : "已结束";
      } catch (error) {
        serviceState.textContent = "异常";
        appendLog("边教边动入库异常：" + error.message);
      } finally {
        finishTeachingSessionButton.disabled = false;
      }
    }

    async function askRuntimeQuestion() {
      askRuntimeQuestionButton.disabled = true;
      serviceState.textContent = "读取当前状态";
      try {
        const question = document.getElementById("runtimeQuestion").value.trim() || "当前杯子有没有水";
        const taskId = currentTeachingSessionId || currentMigrationTaskId || taskMetric.textContent.trim();
        if (!taskId || taskId === "-") {
          appendLog("当前没有可查询的任务或会话，请先运行或启动教学会话。");
          serviceState.textContent = "缺少上下文";
          return;
        }
        const result = await fetch("/agent/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ task_id: taskId, utterance: question })
        }).then(r => r.json());
        appendLog("状态提问结果：" + JSON.stringify(result, null, 2));
        const routed = result.route_result || result;
        if (result.error || routed.error) {
          serviceState.textContent = "状态异常";
          setText(outcomeMetric, "查询失败", "bad");
          return;
        }
        if (result.semantic_request?.request_type !== "state_query") {
          setText(admitMetric, formatConfidence(result.semantic_request?.intent_confidence), confidenceClass(result.semantic_request?.intent_confidence));
          setText(stateMetric, result.semantic_request?.request_type || "unexpected_route", "warn");
          setText(outcomeMetric, "已转其他语义路由", "warn");
          factsEl.innerHTML = [
            `<div class="stage-row"><strong>当前提问</strong><span>${escapeHtml(question)}</span></div>`,
            ...renderSemanticSignalRows(result.semantic_request || {}, routed)
          ].join("");
          serviceState.textContent = "路由已偏转";
          appendLog("当前输入没有命中状态查询，而是被路由到其他语义通道。");
          return;
        }
        renderStateQueryResult(result, routed, question, taskId);
        serviceState.textContent = "状态已回答";
      } catch (error) {
        serviceState.textContent = "异常";
        appendLog("状态提问异常：" + error.message);
      } finally {
        askRuntimeQuestionButton.disabled = false;
      }
    }

    async function preparePerturbationTask() {
      preparePerturbationTaskButton.disabled = true;
      serviceState.textContent = "准备扰动测试";
      const utterance = document.getElementById("utterance").value.trim();
      appendLog("创建迁移适配任务，用于偶然层扰动测试：" + utterance);
      try {
        const result = await fetch("/experience/migrate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ utterance })
        }).then(r => r.json());
        appendLog("迁移适配结果：" + JSON.stringify(result, null, 2));
        if (result.error || !result.execution_loop_payload) {
          serviceState.textContent = "准备失败";
          setText(outcomeMetric, result.execution_feasibility?.result || "prepare_failed", "bad");
          renderFacts({
            audit_summary: { stage_summary: [], fact_summary: [], stop_reason: result.error || result.execution_feasibility?.result || "prepare_failed" },
            runtime_world_state: result.runtime_world_state_snapshot || result.runtime_world_state,
            intent_translation: result.intent_translation,
            stepwise_readaptation: null
          });
          return;
        }
        rememberMigrationEnvelope(result);
        setText(admitMetric, result.execution_feasibility?.result || "executable", "ok");
        setText(stateMetric, "migration_adapted", "ok");
        setText(outcomeMetric, "ready_for_perturbation", "warn");
        renderPerturbationFacts("扰动测试任务已就绪", result);
        serviceState.textContent = "扰动任务已就绪";
      } catch (error) {
        serviceState.textContent = "异常";
        appendLog("准备扰动任务异常：" + error.message);
      } finally {
        preparePerturbationTaskButton.disabled = false;
      }
    }

    async function injectPerturbation() {
      injectPerturbationButton.disabled = true;
      serviceState.textContent = "注入偶然层扰动";
      try {
        if (!currentMigrationTaskId || !currentExecutionLoopPayload) {
          await preparePerturbationTask();
        }
        if (!currentMigrationTaskId) {
          serviceState.textContent = "无任务";
          return;
        }
        const payload = {
          task_id: currentMigrationTaskId,
          perturbation: { kind: perturbationKind.value },
          apply_before_step: perturbationStep.value
        };
        appendLog("注入偶然层扰动：" + JSON.stringify(payload, null, 2));
        const result = await fetch("/runtime_world_state/perturb", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        }).then(r => r.json());
        appendLog("扰动注入结果：" + JSON.stringify(result, null, 2));
        if (result.error) {
          serviceState.textContent = "注入失败";
          setText(outcomeMetric, "perturb_failed", "bad");
          return;
        }
        setText(stateMetric, "runtime_perturbed", "warn");
        setText(outcomeMetric, result.injected_perturbation?.status || "perturbed", "warn");
        renderPerturbationFacts("偶然层扰动已注入", result);
        serviceState.textContent = "扰动已注入";
      } catch (error) {
        serviceState.textContent = "异常";
        appendLog("扰动注入异常：" + error.message);
      } finally {
        injectPerturbationButton.disabled = false;
      }
    }

    async function runPerturbationDispatch() {
      runPerturbationDispatchButton.disabled = true;
      serviceState.textContent = "执行扰动链";
      try {
        if (!currentMigrationTaskId || !currentExecutionLoopPayload) {
          await preparePerturbationTask();
        }
        if (!currentExecutionLoopPayload) {
          serviceState.textContent = "无执行链";
          return;
        }
        appendLog("执行带扰动的迁移链：" + JSON.stringify(currentExecutionLoopPayload, null, 2));
        const result = await fetch("/execution/dispatch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            execution_loop_payload: currentExecutionLoopPayload,
            executor_type: dispatchBackend.value,
            executor_options: {
              physics_executor_type: physicsExecutorType.value,
              physics_obstacle: perturbationKind.value === "stool_in_walkway_detourable" ? "detourable" :
                (perturbationKind.value === "stool_blocks_walkway" ? "wall" : "none")
            }
          })
        }).then(r => r.json());
        appendLog("扰动执行结果：" + JSON.stringify(result, null, 2));
        if (result.physics_result) {
          appendLog("MuJoCo 物理证据：" + JSON.stringify(result.physics_result, null, 2));
        }
        if (result.error) {
          serviceState.textContent = "执行失败";
          setText(outcomeMetric, "dispatch_failed", "bad");
          return;
        }
        const outcomeClass = result.outcome === "fact_established" ? "ok" : (result.outcome === "readaptation_required" ? "warn" : "bad");
        setText(stateMetric, result.outcome === "readaptation_required" ? "readaptation_required" : "execution_feedback_received", outcomeClass);
        setText(outcomeMetric, result.outcome || "-", outcomeClass);
        setText(taskMetric, result.task_id || currentMigrationTaskId || "-");
        const detourFeedback = (result.fact_feedback || []).find(item => item.route_adjustment);
        const blockedFeedback = (result.fact_feedback || []).find(item => item.preflight_result === "blocked");
        if (detourFeedback?.route_adjustment) {
          applyRouteAdjustmentVisualization(detourFeedback.route_adjustment, { blocked: false });
          appendLog("偶然层处理：保持主链，执行局部绕行 -> " + JSON.stringify(detourFeedback.route_adjustment));
        } else if (blockedFeedback) {
          applyRouteAdjustmentVisualization({ step: blockedFeedback.step, adjustment_type: "blocked" }, { blocked: true });
          appendLog("偶然层处理：当前步骤被阻断，需重新适配 -> " + blockedFeedback.step);
        } else {
          clearRouteAdjustmentVisualization();
        }
        renderFacts({
          audit_summary: {
            stage_summary: (result.fact_feedback || []).map(item => ({
              stage_id: item.step,
              result: item.preflight_result || item.fact_status,
              notes: item.reason || (item.route_adjustment ? JSON.stringify(item.route_adjustment) : "")
            })),
            fact_summary: (result.fact_feedback || []).map(item => ({
              fact_id: item.fact_id || item.step,
              state: item.fact_status,
              channel_notes: item.preflight_result || "-"
            })),
            stop_reason: result.outcome === "readaptation_required" ? "runtime_environment_changed" : null
          },
          runtime_world_state: result.runtime_world_state_snapshot,
          stepwise_readaptation: result.stepwise_readaptation
        });
        serviceState.textContent = result.outcome === "readaptation_required" ? "需要重新适配" : "扰动链已执行";
      } catch (error) {
        serviceState.textContent = "异常";
        appendLog("扰动链执行异常：" + error.message);
      } finally {
        runPerturbationDispatchButton.disabled = false;
      }
    }

    async function confirmConceptCandidate() {
      confirmConceptCandidateButton.disabled = true;
      serviceState.textContent = "确认概念晋升";
      try {
        let candidateId = conceptCandidateIdInput.value.trim() || currentConceptCandidateId;
        if (!candidateId) {
          const pending = await fetch("/concept/candidates").then(r => r.json());
          candidateId = selectConceptCandidate(pending.concept_candidates || [])?.candidate_id || "";
        }
        if (!candidateId) {
          appendLog("当前没有可确认的概念候选。");
          serviceState.textContent = "暂无候选";
          return;
        }
        const result = await fetch("/concept/candidates/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ candidate_id: candidateId, confirmed_by: "demo_ui" })
        }).then(r => r.json());
        appendLog("概念确认结果：" + JSON.stringify(result, null, 2));
        if (result.error) {
          serviceState.textContent = "确认失败";
          setText(outcomeMetric, "确认失败", "bad");
          return;
        }
        currentConceptCandidateId = candidateId;
        conceptCandidateIdInput.value = candidateId;
        setText(stateMetric, "concept_promoted", "ok");
        setText(outcomeMetric, "概念已晋升", "ok");
        setText(taskMetric, result.promoted_concept_id || candidateId);
        const promoted = result.promoted_concept_unit || {};
        const utterance = document.getElementById("utterance").value.trim();
        const verificationTaskId = currentTeachingSessionId || "";
        const verification = await fetch("/concept/resolve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ utterance, task_id: verificationTaskId || null })
        }).then(r => r.json());
        appendLog("概念复用验证：" + JSON.stringify(verification, null, 2));
        const verificationConcepts = verification.resolved_concepts || [];
        const reused = verificationConcepts.some(item => item.concept_id === result.promoted_concept_id);
        const verificationReason = verificationConcepts.find(item => item.concept_id === result.promoted_concept_id)?.activation_reason || "-";
        const rows = [
          `<div class="stage-row"><strong>确认候选</strong><span>${escapeHtml(candidateId)}</span></div>`,
          `<div class="stage-row"><strong>晋升概念</strong><span>${escapeHtml(result.promoted_concept_id || "-")}</span></div>`,
          `<div class="stage-row"><strong>显示名称</strong><span>${escapeHtml(promoted.display_name || "-")}</span></div>`,
          `<div class="stage-row"><strong>能力语义</strong><span>${escapeHtml((promoted.capability_semantics || []).join(", ") || "-")}</span></div>`,
          `<div class="stage-row"><strong>来源经验</strong><span>${escapeHtml(result.source_experience_id || "-")}</span></div>`,
          `<div class="stage-row"><strong>复用验证</strong><span>${reused ? "已命中当前任务解析" : "当前任务未命中该晋升概念"}</span></div>`,
          `<div class="stage-row"><strong>验证依据</strong><span>${escapeHtml(verificationReason)}</span></div>`,
          `<div class="stage-row"><strong>解析概念</strong><span>${escapeHtml(verificationConcepts.map(item => item.concept_id).join(", ") || "-")}</span></div>`
        ];
        factsEl.innerHTML = rows.join("");
        serviceState.textContent = reused ? "晋升并已复用" : "晋升完成";
      } catch (error) {
        serviceState.textContent = "异常";
        appendLog("概念确认异常：" + error.message);
      } finally {
        confirmConceptCandidateButton.disabled = false;
      }
    }

    function selectedPhysicsObstacle() {
      if (perturbationKind.value === "stool_in_walkway_detourable") return "detourable";
      if (perturbationKind.value === "stool_blocks_walkway") return "wall";
      return "none";
    }

    async function startPhysicsSession() {
      if (!currentExecutionLoopPayload) await preparePerturbationTask();
      const result = await fetch("/physics/session/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          execution_loop_payload: currentExecutionLoopPayload,
          executor_options: { physics_executor_type: physicsExecutorType.value, physics_obstacle: "none" }
        })
      }).then(r => r.json());
      if (result.error) {
        appendLog("物理会话启动失败：" + JSON.stringify(result));
        return;
      }
      currentPhysicsSessionId = result.session_id;
      setText(stateMetric, result.status, "warn");
      appendLog("物理会话已启动，暂停在第一阶段前：" + JSON.stringify(result, null, 2));
    }

    async function stepPhysicsSession() {
      if (!currentPhysicsSessionId) await startPhysicsSession();
      if (!currentPhysicsSessionId) return;
      await fetch("/physics/session/perturb", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: currentPhysicsSessionId, obstacle: selectedPhysicsObstacle() })
      });
      const result = await fetch("/physics/session/step", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: currentPhysicsSessionId })
      }).then(r => r.json());
      if (result.error) {
        appendLog("物理阶段拒绝执行：" + JSON.stringify(result, null, 2));
        return;
      }
      const stage = result.last_stage || result.stage_history?.[result.stage_history.length - 1];
      appendLog("MuJoCo 单阶段验真：" + JSON.stringify(stage, null, 2));
      setText(stateMetric, result.status, result.status === "completed" ? "ok" : "warn");
      setText(outcomeMetric, stage?.outcome || result.status, stage?.outcome === "fact_established" ? "ok" : "bad");
    }

    async function interruptPhysicsSession() {
      if (!currentPhysicsSessionId) return;
      const result = await fetch("/physics/session/interrupt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: currentPhysicsSessionId, utterance: utteranceInput.value.trim() })
      }).then(r => r.json());
      appendLog("物理会话中断与重新仲裁：" + JSON.stringify(result, null, 2));
      setText(stateMetric, result.status || "interrupt_failed", result.error ? "bad" : "warn");
    }

    factsEl.addEventListener("click", async (event) => {
      const actionButton = event.target.closest("[data-cloud-action]");
      if (!actionButton) {
        return;
      }
      const chainPayload = actionButton.getAttribute("data-cloud-chain") || "";
      const goalPayload = actionButton.getAttribute("data-cloud-goal") || "";
      let chain = [];
      try {
        chain = JSON.parse(decodeURIComponent(chainPayload || "%5B%5D"));
      } catch (error) {
        appendLog("云脑候选链路解析失败：" + error.message);
        return;
      }
      const goalFact = decodeURIComponent(goalPayload || "");
      if (actionButton.dataset.cloudAction === "prefill-chain") {
        prefillCloudRecallCandidateChain(chain, goalFact);
        return;
      }
      if (actionButton.dataset.cloudAction === "preview-chain") {
        await previewCloudRecallCandidateChain(chain, goalFact);
      }
    });

    runButton.addEventListener("click", runProcess);
    teachButton.addEventListener("click", teachExperience);
    dialogueTeachButton.addEventListener("click", teachByDialogue);
    libraryButton.addEventListener("click", showExperienceLibrary);
    p017Button.addEventListener("click", showP017MinimalLoop);
    conceptCandidatesButton.addEventListener("click", showConceptCandidates);
    confirmConceptCandidateButton.addEventListener("click", confirmConceptCandidate);
    startTeachingSessionButton.addEventListener("click", startStepwiseTeaching);
    stepTeachingSessionButton.addEventListener("click", executeStepwiseTeaching);
    finishTeachingSessionButton.addEventListener("click", finishStepwiseTeaching);
    askRuntimeQuestionButton.addEventListener("click", askRuntimeQuestion);
    preparePerturbationTaskButton.addEventListener("click", preparePerturbationTask);
    injectPerturbationButton.addEventListener("click", injectPerturbation);
    runPerturbationDispatchButton.addEventListener("click", runPerturbationDispatch);
    startPhysicsSessionButton.addEventListener("click", startPhysicsSession);
    stepPhysicsSessionButton.addEventListener("click", stepPhysicsSession);
    interruptPhysicsSessionButton.addEventListener("click", interruptPhysicsSession);
    walkwayPerturbRegion.addEventListener("click", async () => {
      await triggerMapPerturbation("stool_in_walkway_detourable", "move_to_water_source", "过道放凳子（可绕开）");
    });
    doorPerturbRegion.addEventListener("click", async () => {
      await triggerMapPerturbation("cup_guard_door_closed", "pick_up_cup", "杯子前门关闭");
    });
    clearButton.addEventListener("click", clearView);
    clearView();
    setPerturbationPreset(perturbationKind.value, perturbationStep.value);
  </script>
</body>
</html>
"""


def translate_intent(utterance: str) -> dict[str, Any]:
    text = (utterance or "").strip()
    cognitive_model = get_cognitive_model()
    intent_frame = build_intent_frame(text, cognitive_model) if text else None
    semantic_request = build_semantic_request_frame(text, cognitive_model, intent_frame=intent_frame)
    if not text:
        return {
            "schema_version": "1.0.0",
            "utterance": text,
            "task_type": "unknown",
            "decision": "unsupported",
            "reason": "空任务输入",
            "candidate_process": None,
            "intent_frame": intent_frame,
            "semantic_request": semantic_request,
        }
    detected_steps = intent_frame["explicit_process_chain"]
    has_sequence_marker = any(marker in text for marker in ["然后", "再", "接着", "之后", "，", ","])
    if any(keyword in text for keyword in ["快递", "下楼", "电梯", "楼下"]):
        return {
            "schema_version": "1.0.0",
            "utterance": text,
            "task_type": "long_chain_delivery",
            "decision": "unsupported",
            "reason": "长程多过程任务尚未进入第一阶段技能库",
            "candidate_process": None,
            "intent_frame": intent_frame,
            "semantic_request": semantic_request,
        }
    if any(keyword in text for keyword in ["炉灶", "火", "热源"]):
        return {
            "schema_version": "1.0.0",
            "utterance": text,
            "task_type": "risk_area_action",
            "decision": "blocked",
            "reason": "任务涉及数字空间中的风险区域，第一阶段阻断执行",
            "candidate_process": None,
            "intent_frame": intent_frame,
            "semantic_request": semantic_request,
        }
    goal_fact = intent_frame["goal_fact"]
    if goal_fact is None and detected_steps:
        goal_fact = infer_goal_fact_from_detected_steps(detected_steps)
        if goal_fact:
            intent_frame["goal_fact"] = goal_fact
            intent_frame["goal_fact_source"] = "explicit_process_effect_projection"
    should_use_causal_solver = goal_fact is not None
    if should_use_causal_solver:
        causal_plan = solve_causal_process_chain(goal_fact, cognitive_model)
        if causal_plan["solved"]:
            if chain_covers_goal(detected_steps, causal_plan["process_chain"]) and chain_is_causally_supported(detected_steps, causal_plan):
                causal_plan = build_explicit_causal_plan(goal_fact, detected_steps, causal_plan)
            plan_digest = hashlib.sha1((goal_fact + "|" + "|".join(causal_plan["process_chain"])).encode("utf-8")).hexdigest()
            return {
                "schema_version": "1.0.0",
                "utterance": text,
                "task_type": "causal_process_chain",
                "decision": "executable",
                "reason": "保留显式教学路线并完成目标因果事实校验" if causal_plan.get("plan_source") == "explicit_user_teaching" else "目标因果事实经因果层反向搜索形成过程链",
                "candidate_process": "causal_plan_" + plan_digest[:10],
                "candidate_process_chain": causal_plan["process_chain"],
                "experience_id": "causal_plan_" + plan_digest[:10],
                "goal_fact": goal_fact,
                "causal_plan": causal_plan,
                "detected_steps": detected_steps,
                "intent_frame": intent_frame,
                "semantic_request": semantic_request,
            }
        return {
            "schema_version": "1.0.0",
            "utterance": text,
            "task_type": "causal_process_chain",
            "decision": "unsupported",
            "reason": "目标因果事实存在，但因果层无法补齐前提事实",
            "candidate_process": None,
            "candidate_process_chain": [],
            "goal_fact": goal_fact,
            "causal_plan": causal_plan,
            "intent_frame": intent_frame,
            "semantic_request": semantic_request,
        }
    learned = find_learned_experience(text)
    if learned:
        return {
            "schema_version": "1.0.0",
            "utterance": text,
            "task_type": "learned_process_chain",
            "decision": "executable",
            "reason": "命中人工教学形成的数字经验链",
            "candidate_process": learned["experience_id"],
            "candidate_process_chain": learned["process_chain"],
            "experience_id": learned["experience_id"],
            "goal_fact": learned.get("goal_fact", "water_poured"),
            "intent_frame": intent_frame,
            "semantic_request": semantic_request,
        }
    if len(detected_steps) > 1 or (has_sequence_marker and detected_steps and detected_steps != ["pour_water"]):
        return {
            "schema_version": "1.0.0",
            "utterance": text,
            "task_type": "process_chain",
            "decision": "unsupported",
            "reason": "检测到多过程任务链，但未能映射为可求解的目标因果事实",
            "candidate_process": None,
            "candidate_process_chain": detected_steps,
            "unsupported_steps": [step for step in detected_steps if step != "pour_water"],
            "intent_frame": intent_frame,
            "semantic_request": semantic_request,
        }
    if any(keyword in text for keyword in ["倒水", "倒一杯水", "给客人倒水"]):
        scenario = "simulated_success"
        if any(keyword in text for keyword in ["没水", "无水", "空壶"]):
            scenario = "simulated_no_water"
        if any(keyword in text for keyword in ["冲突", "看不清", "遮挡"]):
            scenario = "simulated_channel_conflict"
        return {
            "schema_version": "1.0.0",
            "utterance": text,
            "task_type": "pour_water",
            "decision": "executable",
            "reason": "命中第一阶段倒水技能",
            "candidate_process": "pour_water",
            "recommended_scenario": scenario,
            "goal_fact": "cup_has_water",
            "intent_frame": intent_frame,
            "semantic_request": semantic_request,
        }
    return {
        "schema_version": "1.0.0",
        "utterance": text,
        "task_type": "unknown",
        "decision": "unsupported",
        "reason": "技能库未匹配到可执行过程模板",
        "candidate_process": None,
        "intent_frame": intent_frame,
        "semantic_request": semantic_request,
    }


def detect_process_chain(text: str) -> list[str]:
    steps: list[tuple[int, str]] = []
    for step_id, keywords in PROCESS_CHAIN_KEYWORDS:
        positions = [text.find(keyword) for keyword in keywords if keyword in text]
        if positions:
            steps.append((min(positions), step_id))
    return [step_id for _, step_id in sorted(steps, key=lambda item: item[0])]


def normalize_text(text: str) -> str:
    return re.sub(r"[\s,\uFF0C\u3002\uFF1B;\u3001\uFF1A:\uFF01\uFF1F?!.]+", "", (text or "").lower())



def load_experience_library() -> dict[str, Any]:
    if not EXPERIENCE_LIBRARY_FILE.exists():
        return {"schema_version": "1.0.0", "experiences": []}
    return read_json(EXPERIENCE_LIBRARY_FILE)


def load_concept_library() -> dict[str, Any]:
    if CONCEPT_LIBRARY_FILE.exists():
        raw_library = read_json(CONCEPT_LIBRARY_FILE)
        raw_units = raw_library.get("concept_units", [])
    else:
        raw_library = {"schema_version": "1.0.0"}
        raw_units = list(DEFAULT_P012_CONCEPT_LIBRARY.values())
    concept_units: list[dict[str, Any]] = []
    for raw in raw_units:
        concept_id = raw.get("concept_id")
        if not concept_id:
            continue
        normalized = dict(raw)
        normalized.update(
            {
                "concept_id": concept_id,
                "display_name": raw.get("display_name", concept_id),
                "concept_level": raw.get("concept_level", "unspecified"),
                "typical_action": raw.get("typical_action"),
                "typical_consequence": raw.get("typical_consequence"),
                "usage": raw.get("usage", ""),
                "capability_semantics": raw.get("capability_semantics", []),
                "effect_contract": raw.get("effect_contract", {}),
                "applicability_constraints": raw.get("applicability_constraints", {}),
                "runtime_contingency_hints": raw.get("runtime_contingency_hints", []),
                "experience_link_policy": raw.get("experience_link_policy", {}),
            }
        )
        concept_units.append(normalized)
    return {
        "schema_version": raw_library.get("schema_version", "1.0.0"),
        "concept_units": concept_units,
    }


def save_concept_library(library: dict[str, Any]) -> None:
    CONCEPT_LIBRARY_FILE.write_text(json.dumps(library, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_concept_library_index() -> dict[str, dict[str, Any]]:
    return {item["concept_id"]: item for item in load_concept_library().get("concept_units", [])}


def load_concept_candidate_library() -> dict[str, Any]:
    if not CONCEPT_CANDIDATE_LIBRARY_FILE.exists():
        return {"schema_version": "1.0.0", "concept_candidates": []}
    return read_json(CONCEPT_CANDIDATE_LIBRARY_FILE)


def save_concept_candidate_library(library: dict[str, Any]) -> None:
    CONCEPT_CANDIDATE_LIBRARY_FILE.write_text(json.dumps(library, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_experience_library(library: dict[str, Any]) -> None:
    EXPERIENCE_LIBRARY_FILE.write_text(json.dumps(library, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_recovery_library() -> dict[str, Any]:
    if not RECOVERY_LIBRARY_FILE.exists():
        return {"schema_version": "1.0.0", "recovery_records": []}
    return read_json(RECOVERY_LIBRARY_FILE)


def save_recovery_library(library: dict[str, Any]) -> None:
    RECOVERY_LIBRARY_FILE.write_text(json.dumps(library, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_preference_library() -> dict[str, Any]:
    if not PREFERENCE_LIBRARY_FILE.exists():
        return {"schema_version": "1.0.0", "preference_records": []}
    return read_json(PREFERENCE_LIBRARY_FILE)


def save_preference_library(library: dict[str, Any]) -> None:
    PREFERENCE_LIBRARY_FILE.write_text(json.dumps(library, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_recovery_action(
    outcome: str,
    stop_reason: str | None = None,
    gap_record: dict[str, Any] | None = None,
    readaptation_id: str | None = None,
) -> dict[str, Any]:
    recommended_actions = list(gap_record.get("recommended_actions", [])) if gap_record else []
    if readaptation_id:
        return {
            "action_type": "trigger_readaptation",
            "parameters": {
                "readaptation_id": readaptation_id,
                "recommended_actions": recommended_actions or ["request_human_confirmation", "search_alternative_experience"],
            },
            "human_intervention": True,
        }
    if outcome in {"requires_human_confirmation", "readaptation_required"}:
        return {
            "action_type": "request_human_confirmation",
            "parameters": {
                "reason": stop_reason or outcome,
                "recommended_actions": recommended_actions or ["request_human_confirmation", "terminate_execution"],
            },
            "human_intervention": True,
        }
    if gap_record and any(item in recommended_actions for item in ["trigger_supplemental_teaching", "search_alternative_experience"]):
        return {
            "action_type": "request_teaching_or_alternative_experience",
            "parameters": {
                "reason": stop_reason or outcome,
                "recommended_actions": recommended_actions,
                "experience_gap_record_id": gap_record.get("gap_record_id"),
            },
            "human_intervention": True,
        }
    return {
        "action_type": "record_failure_and_wait",
        "parameters": {
            "reason": stop_reason or outcome,
            "recommended_actions": recommended_actions or ["terminate_execution"],
        },
        "human_intervention": False,
    }


def build_recovery_outcome_type(outcome: str) -> str:
    if outcome in {"recovered"}:
        return "recovered"
    if outcome in {"partially_inexecutable", "partially_recovered"}:
        return "partially_recovered"
    if outcome in {"requires_human_confirmation", "readaptation_required"}:
        return "escalated"
    return "failed"


def persist_recovery_record(
    *,
    task_id: str,
    failed_experience_ref: str,
    deviation_type: str,
    observed_state: str,
    expected_state: str,
    recovery_action: dict[str, Any],
    recovery_outcome_type: str,
    notes: str,
    audit_record_id: str | None = None,
    runtime_world_state_snapshot_id: str | None = None,
    source_refs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seed = "|".join(
        [
            task_id,
            failed_experience_ref,
            deviation_type,
            observed_state,
            expected_state,
            recovery_action.get("action_type", "unknown"),
            recovery_outcome_type,
        ]
    )
    recovery_id = "recovery_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    record = {
        "schema_version": "1.0.0",
        "recovery_id": recovery_id,
        "task_id": task_id,
        "audit_record_id": audit_record_id,
        "runtime_world_state_snapshot_id": runtime_world_state_snapshot_id,
        "failed_experience_ref": failed_experience_ref,
        "deviation_context": {
            "deviation_type": deviation_type,
            "observed_state": observed_state,
            "expected_state": expected_state,
        },
        "recovery_action": recovery_action,
        "recovery_outcome": {
            "outcome_type": recovery_outcome_type,
            "notes": notes,
        },
        "source_refs": source_refs or {},
    }
    library = load_recovery_library()
    records = [item for item in library.get("recovery_records", []) if item.get("recovery_id") != recovery_id]
    records.append(record)
    library["recovery_records"] = records
    save_recovery_library(library)
    return record


def attach_recovery_record_to_context(
    recovery_record: dict[str, Any],
    *,
    task_id: str | None = None,
    audit_record_id: str | None = None,
) -> None:
    recovery_id = recovery_record.get("recovery_id")
    if not recovery_id:
        return
    if task_id and task_id in STATE_STORE:
        state = STATE_STORE[task_id]
        refs = state.setdefault("recovery_record_ids", [])
        if recovery_id not in refs:
            refs.append(recovery_id)
    if task_id and task_id in RUNTIME_WORLD_STATE_STORE:
        runtime_state = RUNTIME_WORLD_STATE_STORE[task_id]
        refs = runtime_state.setdefault("recovery_record_ids", [])
        if recovery_id not in refs:
            refs.append(recovery_id)
    target_audit = None
    if audit_record_id and audit_record_id in AUDIT_STORE:
        target_audit = AUDIT_STORE[audit_record_id]
    elif task_id and task_id in AUDIT_STORE:
        target_audit = AUDIT_STORE[task_id]
    if target_audit is not None:
        refs = target_audit.setdefault("recovery_record_ids", [])
        if recovery_id not in refs:
            refs.append(recovery_id)


def build_recovery_record_for_task(
    *,
    task_id: str,
    failed_experience_ref: str,
    outcome: str,
    stop_reason: str | None,
    expected_state: str,
    observed_state: str,
    audit_record_id: str | None = None,
    runtime_world_state_snapshot_id: str | None = None,
    gap_record: dict[str, Any] | None = None,
    readaptation_id: str | None = None,
    source_refs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recovery_action = build_recovery_action(outcome, stop_reason=stop_reason, gap_record=gap_record, readaptation_id=readaptation_id)
    recovery_outcome_type = build_recovery_outcome_type(outcome)
    notes = stop_reason or outcome
    record = persist_recovery_record(
        task_id=task_id,
        failed_experience_ref=failed_experience_ref,
        deviation_type=stop_reason or outcome,
        observed_state=observed_state,
        expected_state=expected_state,
        recovery_action=recovery_action,
        recovery_outcome_type=recovery_outcome_type,
        notes=notes,
        audit_record_id=audit_record_id,
        runtime_world_state_snapshot_id=runtime_world_state_snapshot_id,
        source_refs=source_refs,
    )
    attach_recovery_record_to_context(record, task_id=task_id, audit_record_id=audit_record_id)
    return record


def get_recovery_record(recovery_id: str) -> dict[str, Any]:
    for item in load_recovery_library().get("recovery_records", []):
        if item.get("recovery_id") == recovery_id:
            return item
    return {"error": "recovery_record_not_found", "recovery_id": recovery_id}


def get_recovery_records_for_task(task_id: str) -> dict[str, Any]:
    items = [item for item in load_recovery_library().get("recovery_records", []) if item.get("task_id") == task_id]
    return {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "recovery_records": items,
    }


def get_preference_context_ref(intent: dict[str, Any], cognitive_model: dict[str, Any] | None = None) -> str:
    environment_summary = (cognitive_model or {}).get("local_environment_summary", {})
    return str(
        intent.get("context_ref")
        or intent.get("space_ref")
        or environment_summary.get("space_id")
        or "global"
    )


def build_preference_scope_tags(intent: dict[str, Any], binding: dict[str, Any] | None = None) -> set[str]:
    tags: set[str] = set()
    goal_fact = intent.get("goal_fact")
    if goal_fact:
        tags.add(f"goal:{goal_fact}")
    task_type = intent.get("task_type")
    if task_type:
        tags.add(f"task_type:{task_type}")
    if binding is None:
        for step in get_process_chain_for_intent(intent):
            tags.add(f"step:{step}")
            meta = STEP_LIBRARY.get(step, {})
            capability = meta.get("capability")
            target_region = meta.get("target_region")
            target_object = meta.get("target_object")
            if capability:
                tags.add(f"capability:{capability}")
            if target_region:
                tags.add(f"region:{target_region}")
            if target_object:
                tags.add(f"object:{target_object}")
    else:
        step = binding.get("step")
        capability = binding.get("capability")
        if step:
            tags.add(f"step:{step}")
        if capability:
            tags.add(f"capability:{capability}")
        object_binding = binding.get("object_binding", {})
        space_binding = binding.get("space_binding", {})
        if object_binding.get("target_ref"):
            tags.add(f"object:{object_binding['target_ref']}")
        if space_binding.get("target_ref"):
            tags.add(f"region:{space_binding['target_ref']}")
    return tags


def resolve_preferences_for_intent(intent: dict[str, Any], cognitive_model: dict[str, Any] | None = None) -> dict[str, Any]:
    context_ref = get_preference_context_ref(intent, cognitive_model)
    scope_tags = build_preference_scope_tags(intent)
    matched_records: list[dict[str, Any]] = []
    for raw in load_preference_library().get("preference_records", []):
        record_context = str(raw.get("context_ref") or "global")
        if record_context not in {context_ref, "global", "*"}:
            continue
        applies_to = [str(item) for item in raw.get("applies_to", []) if str(item).strip()]
        matched_tags = sorted(set(applies_to) & scope_tags)
        if applies_to and not matched_tags:
            continue
        normalized = dict(raw)
        normalized["context_ref"] = record_context
        normalized["applies_to"] = applies_to
        normalized["matched_tags"] = matched_tags
        normalized["enforcement_policy"] = raw.get("enforcement_policy", "advisory")
        matched_records.append(normalized)
    return {
        "context_ref": context_ref,
        "scope_tags": sorted(scope_tags),
        "preference_records": matched_records,
    }


def evaluate_preference_constraints(
    intent: dict[str, Any],
    binding_candidate: dict[str, Any],
    runtime_world_state: dict[str, Any],
) -> dict[str, Any]:
    active_preferences = runtime_world_state.get("active_preferences", [])
    blocking_reasons: list[dict[str, Any]] = []
    advisory_items: list[dict[str, Any]] = []
    advisory_index: set[tuple[str, str]] = set()
    for binding in binding_candidate.get("step_bindings", []):
        binding_tags = build_preference_scope_tags(intent, binding)
        for preference in active_preferences:
            applies_to = set(preference.get("applies_to", []))
            matched_tags = sorted(applies_to & binding_tags) if applies_to else []
            if applies_to and not matched_tags:
                continue
            preference_id = preference.get("preference_id", "unknown_preference")
            signal = preference.get("preference_signal", "prefer")
            enforcement_policy = preference.get("enforcement_policy", "advisory")
            item = {
                "step": binding.get("step"),
                "preference_id": preference_id,
                "preference_signal": signal,
                "matched_tags": matched_tags,
                "human_feedback": preference.get("human_feedback", ""),
                "enforcement_policy": enforcement_policy,
                "strength": preference.get("strength"),
            }
            if enforcement_policy == "blocking" and signal in {"forbid", "reject", "avoid"}:
                blocking_reasons.append({"reason": "human_preference_blocked_step", **item})
                continue
            advisory_key = (preference_id, binding.get("step", ""))
            if advisory_key in advisory_index:
                continue
            advisory_index.add(advisory_key)
            advisory_items.append(item)
    return {
        "blocking_reasons": blocking_reasons,
        "advisory_items": advisory_items,
    }


def record_preference(
    *,
    context_ref: str,
    preference_signal: str,
    human_feedback: str,
    applies_to: list[str] | None = None,
    strength: float | None = None,
    experience_ref: str | None = None,
    enforcement_policy: str = "advisory",
) -> dict[str, Any]:
    applies_to = [str(item).strip() for item in (applies_to or []) if str(item).strip()]
    if preference_signal not in {"accept", "reject", "correct", "avoid", "prefer", "forbid"}:
        return {"error": "unsupported_preference_signal", "preference_signal": preference_signal}
    if enforcement_policy not in {"advisory", "blocking"}:
        return {"error": "unsupported_enforcement_policy", "enforcement_policy": enforcement_policy}
    if not context_ref:
        return {"error": "missing_context_ref"}
    if not human_feedback.strip():
        return {"error": "missing_human_feedback"}
    if strength is None:
        strength = 1.0 if enforcement_policy == "blocking" else 0.8
    if strength < 0 or strength > 1:
        return {"error": "invalid_strength", "strength": strength}
    seed = "|".join(
        [
            context_ref,
            preference_signal,
            enforcement_policy,
            human_feedback.strip(),
            ",".join(sorted(applies_to)),
            experience_ref or "none",
        ]
    )
    preference_id = "pref_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    library = load_preference_library()
    records = [item for item in library.get("preference_records", []) if item.get("preference_id") != preference_id]
    record = {
        "preference_id": preference_id,
        "context_ref": context_ref,
        "experience_ref": experience_ref,
        "preference_signal": preference_signal,
        "human_feedback": human_feedback.strip(),
        "applies_to": applies_to,
        "strength": strength,
        "enforcement_policy": enforcement_policy,
        "created_at": "2026-07-10T00:00:00+08:00",
    }
    records.append(record)
    library["preference_records"] = records
    save_preference_library(library)
    return {
        "schema_version": library.get("schema_version", "1.0.0"),
        "preference_record": record,
        "preference_records": records,
    }


def attach_preference_to_runtime_task(task_id: str, preference_record: dict[str, Any]) -> dict[str, Any]:
    current = get_runtime_world_state(task_id)
    if "error" in current:
        return current
    state = current["runtime_world_state_snapshot"]
    active_preferences = state.setdefault("active_preferences", [])
    if not any(item.get("preference_id") == preference_record.get("preference_id") for item in active_preferences):
        active_preferences.append(dict(preference_record))
    context = state.setdefault("preference_context", {})
    scope_tags = set(context.get("scope_tags", []))
    scope_tags.update(preference_record.get("applies_to", []))
    context["scope_tags"] = sorted(scope_tags)
    RUNTIME_WORLD_STATE_STORE[task_id] = state
    if task_id in STATE_STORE:
        STATE_STORE[task_id]["runtime_world_state"] = state
    return {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "runtime_world_state_snapshot_id": state.get("runtime_world_state_snapshot_id"),
        "active_preferences": active_preferences,
    }


def find_learned_experience(utterance: str) -> dict[str, Any] | None:
    normalized = normalize_text(utterance)
    for item in load_experience_library().get("experiences", []):
        if item.get("status") not in {"candidate_created", "validated_in_digital_space"}:
            continue
        keys = {normalize_text(item.get("source_utterance", ""))}
        keys.update(normalize_text(alias) for alias in item.get("aliases", []))
        if normalized in keys:
            return item
    return None


def parse_teaching_steps(steps: Any) -> list[str]:
    if isinstance(steps, str) and "需要先" in steps:
        prefix, suffix = steps.split("需要先", 1)
        suffix = re.split(r"(接完|完成|以后|之后|。|\.)", suffix, maxsplit=1)[0]
        prerequisite_steps = detect_process_chain(suffix)
        goal_steps = detect_process_chain(prefix)
        parsed_from_causal_sentence: list[str] = []
        for step in prerequisite_steps + goal_steps:
            if step not in parsed_from_causal_sentence:
                parsed_from_causal_sentence.append(step)
        if parsed_from_causal_sentence:
            return parsed_from_causal_sentence
    if isinstance(steps, list):
        raw_steps = [str(item).strip() for item in steps if str(item).strip()]
    else:
        raw_steps = [item.strip() for item in re.split(r"[\n；;]+", str(steps or "")) if item.strip()]
    parsed: list[str] = []
    for raw in raw_steps:
        if raw in STEP_LIBRARY and raw not in parsed:
            parsed.append(raw)
            continue
        detected = detect_process_chain(raw)
        if detected:
            parsed.extend(step for step in detected if step not in parsed)
            continue
        normalized = normalize_text(raw)
        for step_id, meta in STEP_LIBRARY.items():
            if normalize_text(meta["display_name"]) in normalized and step_id not in parsed:
                parsed.append(step_id)
    return parsed


def build_causal_signature(process_chain: list[str]) -> dict[str, Any]:
    known_facts: set[str] = set()
    requires_facts: list[str] = []
    destroys_facts: list[str] = []
    reasoning: list[dict[str, Any]] = []
    for step in process_chain:
        meta = STEP_LIBRARY[step]
        missing_before_step = []
        for fact in meta.get("requires_facts", []):
            if fact not in known_facts and fact not in requires_facts:
                requires_facts.append(fact)
                missing_before_step.append(fact)
        for destroyed in meta.get("destroys_facts", []):
            known_facts.discard(destroyed)
            if destroyed not in destroys_facts:
                destroys_facts.append(destroyed)
        known_facts.add(meta["produces_fact"])
        reasoning.append(
            {
                "step": step,
                "requires_facts": meta.get("requires_facts", []),
                "external_requirements_added": missing_before_step,
                "produces_fact": meta["produces_fact"],
                "destroys_facts": meta.get("destroys_facts", []),
            }
        )
    goal_fact = STEP_LIBRARY[process_chain[-1]]["produces_fact"]
    return {
        "schema_version": "1.0.0",
        "requires_facts": requires_facts,
        "produces_fact": goal_fact,
        "destroys_facts": destroys_facts,
        "expands_to": process_chain,
        "reasoning": reasoning,
        "solver_enabled": goal_fact == "cup_contains_water",
    }


def build_portable_binding_slot(step: str, meta: dict[str, Any]) -> dict[str, Any]:
    slot_specs = {
        "move_to_doorway": ("TARGET_TRANSITION_REGION", "semantic_region", ["traversable", "transition_area"]),
        "move_to_service_position": ("TARGET_SERVICE_REGION", "semantic_region", ["human_service_zone", "interaction_reachable"]),
        "move_to_counter": ("TARGET_OPERATION_REGION", "semantic_region", ["operation_surface", "task_execution"]),
        "pick_up_cup": ("TARGET_GRASPABLE_CONTAINER", "interactive_object", ["graspable", "receive_liquid"]),
        "move_to_water_source": ("TARGET_LIQUID_SOURCE_REGION", "semantic_region", ["resource_zone", "water_resource"]),
        "fill_cup_at_water_source": ("SOURCE_LIQUID_RESOURCE_REGION", "semantic_region", ["water_resource", "interactive"]),
        "pour_water": ("TARGET_POUR_DESTINATION_REGION", "semantic_region", ["operation_surface", "pour_destination"]),
    }
    slot_id, entity_kind, semantic_requirements = slot_specs.get(
        step,
        (f"TARGET_{meta.get('capability', 'CAPABILITY').upper()}", "semantic_entity", [meta.get("capability")]),
    )
    return {
        "slot_id": slot_id,
        "entity_kind": entity_kind,
        "semantic_requirements": [item for item in semantic_requirements if item],
        "required_capability": meta.get("capability"),
    }


def build_invariant_contract(process_chain: list[str]) -> dict[str, Any]:
    topology_invariants: list[dict[str, Any]] = []
    action_constraints: list[dict[str, Any]] = []
    termination_conditions: list[dict[str, Any]] = []
    binding_slots: list[dict[str, Any]] = []
    source_binding_evidence: list[dict[str, Any]] = []

    for step in process_chain:
        meta = STEP_LIBRARY[step]
        target = meta.get("target_region") or meta.get("target_object")
        slot = build_portable_binding_slot(step, meta)
        if not any(item.get("slot_id") == slot["slot_id"] for item in binding_slots):
            binding_slots.append(slot)
        source_binding_evidence.append({"step": step, "slot_id": slot["slot_id"], "source_entity_ref": target})

        if meta["capability"] == "navigate_to_region":
            topology_invariants.append(
                {
                    "step": step,
                    "relation": "executor_reaches_semantic_region",
                    "target_slot": slot["slot_id"],
                    "stored_as": "semantic_region_relation_not_absolute_coordinates",
                }
            )
            action_constraints.append(
                {
                    "step": step,
                    "direction_policy": "navigate_toward_bound_region",
                    "physical_limits": ["respect_walkable_area", "avoid_restricted_region"],
                    "not_stored": ["fixed_path_points", "absolute_pose_sequence"],
                }
            )
        elif step == "pick_up_cup":
            topology_invariants.append(
                {
                    "step": step,
                    "relation": "end_effector_reaches_graspable_object",
                    "target_slot": slot["slot_id"],
                    "stored_as": "object_affordance_and_relative_reach_relation",
                }
            )
            action_constraints.append(
                {
                    "step": step,
                    "direction_policy": "approach_object_until_graspable",
                    "physical_limits": ["respect_gripper_force_limit", "keep_object_stable"],
                    "not_stored": ["fixed_joint_angles", "fixed_gripper_duration"],
                }
            )
        elif step == "fill_cup_at_water_source":
            topology_invariants.append(
                {
                    "step": step,
                    "relation": "container_opening_aligned_with_water_resource",
                    "target_slot": slot["slot_id"],
                    "stored_as": "resource_zone_and_container_topology_not_absolute_pose",
                }
            )
            action_constraints.append(
                {
                    "step": step,
                    "direction_policy": "move_container_into_resource_flow_until_liquid_enters",
                    "physical_limits": ["avoid_overfill", "keep_container_upright_enough_for_stability"],
                    "not_stored": ["fixed_fill_time", "fixed_sensor_value_sequence"],
                }
            )
        elif step == "pour_water":
            topology_invariants.append(
                {
                    "step": step,
                    "relation": "container_spout_or_opening_aligned_with_target_container",
                    "target_slot": slot["slot_id"],
                    "stored_as": "liquid_transfer_topology_not_robot_specific_pose",
                }
            )
            action_constraints.append(
                {
                    "step": step,
                    "direction_policy": "tilt_container_toward_target_until_flow_or_level_condition",
                    "physical_limits": ["max_safe_tilt", "avoid_spill", "maintain_target_alignment"],
                    "not_stored": ["fixed_joint_angle", "fixed_execution_seconds"],
                }
            )

        termination_conditions.append(
            {
                "step": step,
                "terminate_when": f"{meta['produces_fact']} == established",
                "verification_basis": "runtime_world_state_and_observation_channels",
                "not_stored": "fixed_duration",
            }
        )

    return {
        "schema_version": "1.0.0",
        "storage_policy": "store_invariants_not_concrete_parameters",
        "invariant_dimensions": [
            "topology_relation",
            "exploratory_direction_and_physical_constraint",
            "fact_based_termination_condition",
        ],
        "forbidden_storage": [
            "absolute_coordinates",
            "robot_specific_joint_angles",
            "fixed_execution_duration",
            "single_body_trajectory_without_binding_slots",
        ],
        "topology_invariants": topology_invariants,
        "action_constraints": action_constraints,
        "termination_conditions": termination_conditions,
        "binding_slots": binding_slots,
        "source_binding_evidence": source_binding_evidence,
        "runtime_binding": {
            "space_source": "P010 subject cognitive model",
            "concept_source": "P012 concept match",
            "execution_source": "P016 runtime transition and verification",
            "body_specific_solution": "provided_by_robot_adapter_or_vendor_controller",
        },
    }


def infer_base_concept_refs_for_experience(experience: dict[str, Any]) -> list[str]:
    process_chain = experience.get("process_chain", [])
    goal_fact = experience.get("goal_fact")
    base_refs: list[str] = []
    if any(STEP_LIBRARY.get(step, {}).get("capability") == "navigate_to_region" for step in process_chain):
        base_refs.append("concept_spatial_region_navigation")
    if "pick_up_cup" in process_chain:
        base_refs.append("concept_interactive_object_acquisition")
    if "fill_cup_at_water_source" in process_chain:
        base_refs.extend(["concept_fillable_container", "concept_water_resource_zone"])
    if goal_fact == "water_poured" or "pour_water" in process_chain:
        base_refs.append("concept_liquid_transfer_task")
    return list(dict.fromkeys(base_refs))


def build_promoted_task_concept_unit(experience: dict[str, Any], base_concept_refs: list[str]) -> dict[str, Any]:
    process_chain = experience.get("process_chain", [])
    goal_fact = experience.get("goal_fact") or experience.get("causal_signature", {}).get("produces_fact")
    capability_semantics = list(
        dict.fromkeys(STEP_LIBRARY.get(step, {}).get("capability") for step in process_chain if STEP_LIBRARY.get(step, {}).get("capability"))
    )
    invariant_contract = experience.get("invariant_contract", {})
    causal_signature = experience.get("causal_signature", {})
    digest = hashlib.sha1(
        "|".join([experience.get("experience_id", "unknown"), goal_fact or "task", "|".join(process_chain)]).encode("utf-8")
    ).hexdigest()
    concept_id = "concept_promoted_" + (goal_fact or "task") + "_" + digest[:8]
    display_name_map = {
        "cup_contains_water": "接水任务晋升概念",
        "water_poured": "倒水服务任务晋升概念",
    }
    return {
        "concept_id": concept_id,
        "display_name": display_name_map.get(goal_fact, "经验晋升任务概念"),
        "concept_level": "task_processing",
        "typical_action": "experience_promoted_task",
        "typical_consequence": goal_fact or "task_goal_established",
        "usage": "由已验证经验晋升而来，仍需经编排层、空间语义和任务期快照共同约束后使用",
        "capability_semantics": capability_semantics,
        "effect_contract": {
            "produces_facts": [goal_fact] if goal_fact else [],
            "destroys_facts": causal_signature.get("destroys_facts", []),
            "state_transition": "validated_experience_promoted_into_reusable_task_concept",
        },
        "applicability_constraints": {
            "requires_space_binding": True,
            "supported_binding_types": ["task_goal", "semantic_region", "interactive_object"],
            "required_runtime_facts": causal_signature.get("requires_facts", []),
            "forbidden_low_level_fields": invariant_contract.get("forbidden_storage", []),
        },
        "runtime_contingency_hints": [
            "概念晋升后仍不得直接控制执行器，必须回到经验层和编排层判断当前是否可执行",
            "若运行时世界状态快照不支持该过程链，应输出不可执行或请求补充教学，而不是假定任务成立",
        ],
        "experience_link_policy": {
            "role": "经验晋升任务概念",
            "direct_execution_allowed": False,
            "requires_orchestration": True,
            "preferred_backing": ["经验库", "P017迁移适配", "执行层局部能力"],
        },
        "derived_from_experiences": [experience.get("experience_id")],
        "promotion_tags": {
            "goal_fact": goal_fact,
            "process_chain": process_chain,
            "base_concept_refs": base_concept_refs,
            "source_utterance": experience.get("source_utterance"),
        },
    }


def build_concept_promotion_candidates_for_experience(experience: dict[str, Any]) -> list[dict[str, Any]]:
    experience_id = experience.get("experience_id")
    if not experience_id:
        return []
    process_chain = experience.get("process_chain", [])
    goal_fact = experience.get("goal_fact")
    base_concept_refs = infer_base_concept_refs_for_experience(experience)
    candidates: list[dict[str, Any]] = []
    promoted_unit = build_promoted_task_concept_unit(experience, base_concept_refs)
    promoted_candidate_seed = "|".join([experience_id, promoted_unit["concept_id"], "create_promoted_concept_unit"])
    candidates.append(
        {
            "candidate_id": "concept_candidate_" + hashlib.sha1(promoted_candidate_seed.encode("utf-8")).hexdigest()[:12],
            "status": "pending_confirmation",
            "proposal_type": "create_promoted_concept_unit",
            "target_concept_id": promoted_unit["concept_id"],
            "source_experience_id": experience_id,
            "source_utterance": experience.get("source_utterance"),
            "goal_fact": goal_fact,
            "abstract_process_chain": process_chain,
            "base_concept_refs": base_concept_refs,
            "human_confirmation_required": True,
            "promotion_rationale": "该经验已在数字空间中形成稳定过程链和不变量契约，可晋升为可复用任务概念候选",
            "proposed_concept_unit": promoted_unit,
            "created_at": "2026-07-10T00:00:00+08:00",
        }
    )
    for base_concept_id in base_concept_refs:
        strengthen_seed = "|".join([experience_id, base_concept_id, "strengthen_existing_concept"])
        candidates.append(
            {
                "candidate_id": "concept_candidate_" + hashlib.sha1(strengthen_seed.encode("utf-8")).hexdigest()[:12],
                "status": "pending_confirmation",
                "proposal_type": "strengthen_existing_concept",
                "target_concept_id": base_concept_id,
                "source_experience_id": experience_id,
                "source_utterance": experience.get("source_utterance"),
                "goal_fact": goal_fact,
                "abstract_process_chain": process_chain,
                "base_concept_refs": [base_concept_id],
                "human_confirmation_required": True,
                "promotion_rationale": "该经验可作为现有公共概念的新增工程证据，补强概念与真实经验之间的绑定",
                "proposed_update": {
                    "derived_from_experiences_append": [experience_id],
                    "promotion_history_entry": {
                        "source_experience_id": experience_id,
                        "goal_fact": goal_fact,
                        "process_chain": process_chain,
                    },
                },
                "created_at": "2026-07-10T00:00:00+08:00",
            }
        )
    return candidates


def upsert_concept_promotion_candidates(experience: dict[str, Any]) -> list[dict[str, Any]]:
    library = load_concept_candidate_library()
    fresh_candidates = build_concept_promotion_candidates_for_experience(experience)
    source_experience_id = experience.get("experience_id")
    retained_candidates = [
        item
        for item in library.get("concept_candidates", [])
        if not (item.get("source_experience_id") == source_experience_id and item.get("status") != "promoted")
    ]
    candidate_index = {item.get("candidate_id"): item for item in retained_candidates if item.get("candidate_id")}
    for candidate in fresh_candidates:
        candidate_index[candidate["candidate_id"]] = candidate
    library["concept_candidates"] = list(candidate_index.values())
    save_concept_candidate_library(library)
    return fresh_candidates


def get_concept_candidates(source_experience_id: str | None = None, status: str | None = None) -> dict[str, Any]:
    library = load_concept_candidate_library()
    items = library.get("concept_candidates", [])
    if source_experience_id:
        items = [item for item in items if item.get("source_experience_id") == source_experience_id]
    if status:
        items = [item for item in items if item.get("status") == status]
    return {
        "schema_version": library.get("schema_version", "1.0.0"),
        "concept_candidates": items,
    }


def confirm_concept_promotion_candidate(candidate_id: str, confirmed_by: str = "human_reviewer") -> dict[str, Any]:
    candidate_library = load_concept_candidate_library()
    candidates = candidate_library.get("concept_candidates", [])
    candidate = next((item for item in candidates if item.get("candidate_id") == candidate_id), None)
    if not candidate:
        return {"error": "concept_candidate_not_found", "candidate_id": candidate_id}
    if candidate.get("status") == "promoted":
        return {
            "schema_version": "1.0.0",
            "candidate_id": candidate_id,
            "status": "already_promoted",
            "promoted_concept_id": candidate.get("promoted_concept_id") or candidate.get("target_concept_id"),
        }

    concept_library = load_concept_library()
    concept_units = concept_library.get("concept_units", [])
    concept_index = {item.get("concept_id"): item for item in concept_units if item.get("concept_id")}
    promoted_concept_id = candidate.get("target_concept_id")
    promoted_concept_unit: dict[str, Any] | None = None
    if candidate.get("proposal_type") == "create_promoted_concept_unit":
        promoted_concept_unit = candidate.get("proposed_concept_unit", {})
        if not promoted_concept_unit.get("concept_id"):
            return {"error": "invalid_promoted_concept_unit", "candidate_id": candidate_id}
        if promoted_concept_unit["concept_id"] in concept_index:
            existing = concept_index[promoted_concept_unit["concept_id"]]
            existing_refs = existing.get("derived_from_experiences", [])
            for ref in promoted_concept_unit.get("derived_from_experiences", []):
                if ref not in existing_refs:
                    existing_refs.append(ref)
            existing["derived_from_experiences"] = existing_refs
            promoted_concept_unit = existing
        else:
            concept_units.append(promoted_concept_unit)
    elif candidate.get("proposal_type") == "strengthen_existing_concept":
        target_concept_id = candidate.get("target_concept_id")
        target = concept_index.get(target_concept_id)
        if not target:
            return {"error": "target_concept_not_found", "target_concept_id": target_concept_id, "candidate_id": candidate_id}
        derived_refs = target.get("derived_from_experiences", [])
        for ref in candidate.get("proposed_update", {}).get("derived_from_experiences_append", []):
            if ref not in derived_refs:
                derived_refs.append(ref)
        target["derived_from_experiences"] = derived_refs
        history = target.get("promotion_history", [])
        history.append(
            {
                "source_experience_id": candidate.get("source_experience_id"),
                "goal_fact": candidate.get("goal_fact"),
                "process_chain": candidate.get("abstract_process_chain", []),
                "confirmed_by": confirmed_by,
                "confirmed_at": "2026-07-10T00:00:00+08:00",
            }
        )
        target["promotion_history"] = history
        promoted_concept_unit = target
    else:
        return {"error": "unsupported_concept_candidate_type", "candidate_id": candidate_id}

    concept_library["concept_units"] = concept_units
    save_concept_library(concept_library)

    candidate["status"] = "promoted"
    candidate["confirmed_by"] = confirmed_by
    candidate["confirmed_at"] = "2026-07-10T00:00:00+08:00"
    candidate["promoted_concept_id"] = promoted_concept_id
    save_concept_candidate_library(candidate_library)

    experience_library = load_experience_library()
    for item in experience_library.get("experiences", []):
        if item.get("experience_id") != candidate.get("source_experience_id"):
            continue
        promoted_refs = item.setdefault("promoted_concept_refs", [])
        if promoted_concept_id not in promoted_refs:
            promoted_refs.append(promoted_concept_id)
        confirmed_candidates = item.setdefault("confirmed_concept_candidate_ids", [])
        if candidate_id not in confirmed_candidates:
            confirmed_candidates.append(candidate_id)
    save_experience_library(experience_library)

    return {
        "schema_version": "1.0.0",
        "candidate_id": candidate_id,
        "status": "promoted",
        "promoted_concept_id": promoted_concept_id,
        "promoted_concept_unit": promoted_concept_unit,
        "source_experience_id": candidate.get("source_experience_id"),
    }


def teach_experience(utterance: str, steps: Any) -> dict[str, Any]:
    source_utterance = (utterance or "").strip()
    process_chain = parse_teaching_steps(steps)
    teaching_frame = build_teaching_frame(
        str(steps or source_utterance),
        parse_teaching_steps_fn=parse_teaching_steps,
        infer_goal_fact_fn=infer_goal_fact,
        normalize_text_fn=normalize_text,
    )
    if not source_utterance:
        return {"error": "missing_utterance", "message": "教学样本必须包含原始任务输入"}
    if not process_chain:
        return {"error": "missing_steps", "message": "未能从教学步骤中解析出可用过程链"}
    unknown_steps = [step for step in process_chain if step not in STEP_LIBRARY]
    if unknown_steps:
        return {"error": "unknown_steps", "unknown_steps": unknown_steps}
    digest = hashlib.sha1((normalize_text(source_utterance) + "|" + "|".join(process_chain)).encode("utf-8")).hexdigest()
    experience_id = "exp_" + digest[:10]
    created_at = "2026-07-09T00:00:00+08:00"
    causal_signature = build_causal_signature(process_chain)
    invariant_contract = build_invariant_contract(process_chain)
    experience = {
        "experience_id": experience_id,
        "status": "validated_in_digital_space",
        "source_utterance": source_utterance,
        "aliases": [source_utterance],
        "task_type": "learned_process_chain",
        "process_chain": process_chain,
        "teaching_steps": [STEP_LIBRARY[step]["display_name"] for step in process_chain],
        "goal_fact": causal_signature["produces_fact"],
        "causal_signature": causal_signature,
        "invariant_contract": invariant_contract,
        "context": {
            "task_ref": source_utterance,
            "space_refs": ["home_a_kitchen", "semantic_prior_home_a_kitchen_v1"],
            "human_intent_ref": "manual_teaching",
        },
        "action": {
            "action_type": "process_chain",
            "target_slots": [build_portable_binding_slot(step, STEP_LIBRARY[step])["slot_id"] for step in process_chain],
            "parameters": {"source": "manual_teaching", "teaching_frame": teaching_frame},
        },
        "teaching_contract": teaching_frame,
        "outcome": {
            "outcome_type": "candidate_created",
            "state_delta": "manual steps translated into a digital process-chain experience",
            "evidence_refs": ["POST /experience/teach", "GET /experience/library"],
        },
        "governance_ref": {"audit_ref": "teaching_session"},
        "created_at": created_at,
    }
    portability_validation = validate_experience_portability(experience)
    experience["portable_contract_validation"] = portability_validation
    if not portability_validation["accepted_for_public_experience_library"]:
        return {
            "error": "nonportable_experience_rejected",
            "message": "经验包含不可迁移执行细节或不变量契约不完整，未进入公共经验库",
            "portability_validation": portability_validation,
        }
    library = load_experience_library()
    library["experiences"] = [
        item for item in library.get("experiences", []) if item.get("experience_id") != experience_id
    ]
    library["experiences"].append(experience)
    save_experience_library(library)
    concept_candidates = upsert_concept_promotion_candidates(experience)
    return {
        "schema_version": "1.0.0",
        "decision": "experience_created",
        "experience": experience,
        "concept_promotion_candidates": concept_candidates,
        "message": "已形成候选经验，后续相同任务将优先命中该经验链",
    }


def teach_experience_from_dialogue(utterance: str, message: str) -> dict[str, Any]:
    source_utterance = (utterance or "").strip()
    text = (message or "").strip() or source_utterance
    if not text:
        return {"error": "missing_dialogue", "message": "对话教学内容不能为空"}
    cleaned = re.sub(r"^(教你|我教你|现在教你|对话教学)[：:，,\s]*", "", text).strip()
    if not source_utterance:
        source_utterance = cleaned
    result = teach_experience(source_utterance, text)
    if "experience" in result:
        result["experience"]["context"]["human_intent_ref"] = "dialogue_teaching"
        result["experience"]["action"]["parameters"]["source"] = "dialogue_teaching"
        library = load_experience_library()
        library["experiences"] = [
            result["experience"] if item.get("experience_id") == result["experience"]["experience_id"] else item
            for item in library.get("experiences", [])
        ]
        save_experience_library(library)
        result["concept_promotion_candidates"] = upsert_concept_promotion_candidates(result["experience"])
        result["message"] = "已从对话教学形成候选经验，后续相同任务将优先命中该经验链"
    return result


def build_teaching_session_id(utterance: str) -> str:
    seed = "|".join([normalize_text(utterance), str(len(TEACHING_SESSION_STORE) + 1)])
    return "teach_session_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def start_teaching_session(utterance: str, goal_fact: str | None = None) -> dict[str, Any]:
    source_utterance = (utterance or "").strip()
    if not source_utterance:
        return {"error": "missing_utterance", "message": "边教边动会话必须包含任务输入"}
    intent = translate_intent(source_utterance)
    cognitive_model = get_cognitive_model()
    teaching_frame = build_teaching_frame(
        source_utterance,
        parse_teaching_steps_fn=parse_teaching_steps,
        infer_goal_fact_fn=infer_goal_fact,
        normalize_text_fn=normalize_text,
    )
    session_id = build_teaching_session_id(source_utterance)
    target_goal_fact = goal_fact or intent.get("goal_fact") or "cup_contains_water"
    runtime_world_state = build_initial_runtime_world_state(cognitive_model, {**intent, "experience_id": session_id})
    runtime_world_state["teaching_session_id"] = session_id
    runtime_world_state["runtime_world_state_snapshot_id"] = session_id + "_snapshot"
    runtime_world_state["audit_record_id"] = "audit_" + session_id.removeprefix("teach_session_")
    session = {
        "schema_version": "1.0.0",
        "session_id": session_id,
        "mode": "stepwise_teaching_with_digital_executor",
        "source_utterance": source_utterance,
        "intent_translation": intent,
        "teaching_frame": teaching_frame,
        "goal_fact": target_goal_fact,
        "status": "teaching_in_progress",
        "process_chain": [],
        "step_feedback": [],
        "runtime_world_state_snapshot": runtime_world_state,
        "created_at": "2026-07-10T00:00:00+08:00",
    }
    TEACHING_SESSION_STORE[session_id] = session
    RUNTIME_WORLD_STATE_STORE[session_id] = runtime_world_state
    STATE_STORE[session_id] = {
        "schema_version": "1.0.0",
        "task_id": session_id,
        "current_stage_id": None,
        "runtime_state": "stepwise_teaching_started",
        "runtime_world_state": runtime_world_state,
        "goal_fact": target_goal_fact,
    }
    AUDIT_STORE[runtime_world_state["audit_record_id"]] = {
        "schema_version": "1.0.0",
        "audit_record_id": runtime_world_state["audit_record_id"],
        "teaching_session_id": session_id,
        "outcome": "teaching_in_progress",
        "runtime_world_state_snapshot_id": runtime_world_state["runtime_world_state_snapshot_id"],
    }
    return session


def build_prerequisite_hint(missing_facts: list[str]) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for fact in missing_facts:
        producer = next((step_id for step_id, meta in STEP_LIBRARY.items() if meta.get("produces_fact") == fact), None)
        hints.append(
            {
                "missing_fact": fact,
                "suggested_teaching_step": producer,
                "suggested_display_name": STEP_LIBRARY.get(producer, {}).get("display_name") if producer else None,
            }
        )
    return hints


def execute_teaching_session_step(session_id: str, teaching_input: Any) -> dict[str, Any]:
    session = TEACHING_SESSION_STORE.get(session_id)
    if not session:
        return {"error": "teaching_session_not_found", "session_id": session_id}
    if session.get("status") in {"experience_saved", "closed_without_save"}:
        return {"error": "teaching_session_closed", "session_id": session_id, "status": session.get("status")}
    parsed_steps = parse_teaching_steps(teaching_input)
    step_teaching_frame = build_teaching_frame(
        str(teaching_input or ""),
        parse_teaching_steps_fn=parse_teaching_steps,
        infer_goal_fact_fn=infer_goal_fact,
        normalize_text_fn=normalize_text,
    )
    if not parsed_steps:
        return {
            "error": "missing_teaching_step",
            "message": "未能从本次教学中解析出可执行步骤",
            "session_id": session_id,
            "teaching_frame": step_teaching_frame,
        }
    state = session["runtime_world_state_snapshot"]
    feedback_items: list[dict[str, Any]] = []
    for step in parsed_steps:
        meta = STEP_LIBRARY.get(step)
        if not meta:
            feedback_items.append({"step": step, "status": "unknown_step", "message": "当前步骤不在样品步骤库中"})
            continue
        facts = set(state.get("established_facts", []))
        missing_before = [fact for fact in meta.get("requires_facts", []) if fact not in facts]
        if missing_before:
            feedback = {
                "sequence": len(session["step_feedback"]) + len(feedback_items) + 1,
                "step": step,
                "display_name": meta["display_name"],
                "status": "needs_more_teaching",
                "executed": False,
                "missing_before_step": missing_before,
                "prerequisite_hints": build_prerequisite_hint(missing_before),
                "message": "当前前提事实未成立，数字执行主体先反馈缺口，不猜测执行",
                "teaching_frame": step_teaching_frame,
                "runtime_world_state_snapshot": clone_runtime_world_state(state),
            }
            feedback_items.append(feedback)
            session["status"] = "awaiting_teaching_or_confirmation"
            continue
        transition = apply_step_to_runtime_world_state(state, step, meta, len(session["process_chain"]) + 1)
        session["process_chain"].append(step)
        goal_achieved = session["goal_fact"] in set(state.get("established_facts", []))
        feedback = {
            "sequence": len(session["step_feedback"]) + len(feedback_items) + 1,
            "step": step,
            "display_name": meta["display_name"],
            "status": "executed",
            "executed": True,
            "causal_produced_facts": [transition["produces_fact"]],
            "causal_destroyed_facts": transition["destroys_facts"],
            "missing_before_step": transition["missing_before_step"],
            "teaching_frame": step_teaching_frame,
            "before_executor_location": transition["before_executor_location"],
            "after_executor_location": transition["after_executor_location"],
            "goal_fact": session["goal_fact"],
            "goal_achieved": goal_achieved,
            "runtime_world_state_snapshot": transition["snapshot_after"],
        }
        feedback_items.append(feedback)
        session["status"] = "goal_achieved_pending_confirmation" if goal_achieved else "teaching_in_progress"
    session["step_feedback"].extend(feedback_items)
    RUNTIME_WORLD_STATE_STORE[session_id] = state
    STATE_STORE[session_id]["runtime_world_state"] = state
    STATE_STORE[session_id]["current_stage_id"] = session["process_chain"][-1] if session["process_chain"] else None
    STATE_STORE[session_id]["runtime_state"] = session["status"]
    AUDIT_STORE[state["audit_record_id"]].update(
        {
            "outcome": session["status"],
            "process_chain": session["process_chain"],
            "last_step_feedback": feedback_items[-1] if feedback_items else None,
        }
    )
    return {
        "schema_version": "1.0.0",
        "session_id": session_id,
        "status": session["status"],
        "goal_fact": session["goal_fact"],
        "process_chain": session["process_chain"],
        "step_feedback": feedback_items,
        "teaching_frame": session.get("teaching_frame"),
        "runtime_world_state_snapshot": state,
    }


PORTABILITY_FORBIDDEN_KEY_FRAGMENTS = {
    "absolute_coordinate",
    "coordinate_sequence",
    "joint_angle",
    "joint_position",
    "trajectory",
    "fixed_duration",
    "fixed_execution_time",
    "motor_command",
    "raw_control_signal",
}


def find_nonportable_fields(value: Any, path: str = "experience") -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower()
            if any(fragment in normalized_key for fragment in PORTABILITY_FORBIDDEN_KEY_FRAGMENTS):
                violations.append(f"{path}.{key}")
            violations.extend(find_nonportable_fields(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            violations.extend(find_nonportable_fields(item, f"{path}[{index}]"))
    return violations


def find_concrete_normative_entity_refs(value: Any, concrete_refs: set[str], path: str = "experience") -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            violations.extend(find_concrete_normative_entity_refs(item, concrete_refs, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            violations.extend(find_concrete_normative_entity_refs(item, concrete_refs, f"{path}[{index}]"))
    elif isinstance(value, str) and value in concrete_refs:
        violations.append(f"{path}={value}")
    return violations


def validate_experience_portability(experience: dict[str, Any]) -> dict[str, Any]:
    contract = experience.get("invariant_contract", {})
    normative_contract = {key: value for key, value in contract.items() if key != "source_binding_evidence"}
    normative_payload = {
        "action": experience.get("action", {}),
        "causal_signature": experience.get("causal_signature", {}),
        "invariant_contract": normative_contract,
    }
    violations = find_nonportable_fields(normative_payload)
    source_entity_refs = {
        str(item.get("source_entity_ref"))
        for item in contract.get("source_binding_evidence", [])
        if item.get("source_entity_ref")
    }
    concrete_normative_refs = find_concrete_normative_entity_refs(normative_payload, source_entity_refs)
    if concrete_normative_refs:
        violations.append("normative_contract_contains_source_environment_entity_refs")
    required_dimensions = {
        "topology_relation",
        "exploratory_direction_and_physical_constraint",
        "fact_based_termination_condition",
    }
    dimensions = set(contract.get("invariant_dimensions", []))
    if not required_dimensions.issubset(dimensions):
        violations.append("invariant_dimensions_incomplete")
    process_chain = experience.get("process_chain", [])
    if len(contract.get("termination_conditions", [])) != len(process_chain):
        violations.append("fact_termination_conditions_incomplete")
    if not contract.get("binding_slots"):
        violations.append("typed_binding_slots_missing")
    return {
        "status": "portable_contract_valid" if not violations else "rejected_nonportable_experience",
        "accepted_for_public_experience_library": not violations,
        "violations": sorted(set(violations)),
        "concrete_normative_entity_refs": concrete_normative_refs,
        "validated_dimensions": sorted(required_dimensions & dimensions),
        "source_bindings_are_non_normative": True,
    }


def bind_portable_invariant_contract(
    contract: dict[str, Any],
    space_bindings: dict[str, str],
    executor_profile: dict[str, Any],
) -> dict[str, Any]:
    supported_actions = set(executor_profile.get("supported_actions", []))
    bound_slots: list[dict[str, Any]] = []
    missing_slots: list[str] = []
    unsupported_capabilities: list[str] = []
    for slot in contract.get("binding_slots", []):
        slot_id = slot.get("slot_id")
        entity_ref = space_bindings.get(slot_id)
        if not entity_ref:
            missing_slots.append(slot_id)
        required_capability = slot.get("required_capability")
        if required_capability and required_capability not in supported_actions:
            unsupported_capabilities.append(required_capability)
        bound_slots.append({
            "slot_id": slot_id,
            "entity_ref": entity_ref,
            "entity_kind": slot.get("entity_kind"),
            "semantic_requirements": slot.get("semantic_requirements", []),
            "required_capability": required_capability,
        })
    accepted = not missing_slots and not unsupported_capabilities
    return {
        "status": "portable_contract_bound" if accepted else "portable_contract_binding_failed",
        "accepted": accepted,
        "executor_id": executor_profile.get("executor_id"),
        "bound_slots": bound_slots,
        "missing_slots": sorted(set(missing_slots)),
        "unsupported_capabilities": sorted(set(unsupported_capabilities)),
        "binding_policy": "typed_slots_are_rebound_per_space_and_executor_without_rewriting_normative_contract",
    }


def finish_teaching_session(session_id: str, success_confirmed: bool = False) -> dict[str, Any]:
    session = TEACHING_SESSION_STORE.get(session_id)
    if not session:
        return {"error": "teaching_session_not_found", "session_id": session_id}
    if not session.get("process_chain"):
        return {"error": "empty_teaching_session", "message": "还没有成功执行的教学步骤，不能固化经验", "session_id": session_id}
    state = session["runtime_world_state_snapshot"]
    goal_achieved = session["goal_fact"] in set(state.get("established_facts", []))
    if not (goal_achieved or success_confirmed):
        session["status"] = "awaiting_success_confirmation"
        return {
            "schema_version": "1.0.0",
            "session_id": session_id,
            "status": session["status"],
            "goal_fact": session["goal_fact"],
            "goal_achieved": False,
            "message": "目标事实尚未成立；如确已成功，请带 success_confirmed=true 结束会话",
            "runtime_world_state_snapshot": state,
        }
    result = teach_experience(session["source_utterance"], session["process_chain"])
    if "experience" in result:
        result["experience"]["context"]["human_intent_ref"] = "stepwise_teaching_session"
        result["experience"]["action"]["parameters"]["source"] = "stepwise_teaching_session"
        result["experience"]["governance_ref"]["audit_ref"] = state.get("audit_record_id")
        library = load_experience_library()
        library["experiences"] = [
            result["experience"] if item.get("experience_id") == result["experience"]["experience_id"] else item
            for item in library.get("experiences", [])
        ]
        save_experience_library(library)
        result["concept_promotion_candidates"] = upsert_concept_promotion_candidates(result["experience"])
    release = release_runtime_world_state(session_id, "stepwise_teaching_finished")
    session["status"] = "experience_saved" if result.get("decision") == "experience_created" else "closed_without_save"
    session["experience_result"] = result
    session["release_result"] = release
    AUDIT_STORE[state["audit_record_id"]].update(
        {
            "outcome": session["status"],
            "experience_id": result.get("experience", {}).get("experience_id"),
            "release_token": release.get("release_token"),
        }
    )
    return {
        "schema_version": "1.0.0",
        "session_id": session_id,
        "status": session["status"],
        "goal_fact": session["goal_fact"],
        "goal_achieved": goal_achieved,
        "experience_result": result,
        "release_result": release,
        "runtime_world_state_snapshot": RUNTIME_WORLD_STATE_STORE.get(session_id, state),
    }


def get_teaching_session(session_id: str) -> dict[str, Any]:
    session = TEACHING_SESSION_STORE.get(session_id)
    if not session:
        return {"error": "teaching_session_not_found", "session_id": session_id}
    return session


def evaluate_space_admission(intent: dict[str, Any], cognitive_model: dict[str, Any]) -> dict[str, Any]:
    if intent["decision"] != "executable":
        return {
            "allowed": False,
            "decision": intent["decision"],
            "reason": intent["reason"],
            "checks": [{"check_id": "intent_executable", "passed": False, "notes": intent["reason"]}],
        }
    if intent["task_type"] in {"learned_process_chain", "causal_process_chain"}:
        regions = {item["region_id"]: item for item in cognitive_model.get("space_region_table", [])}
        objects = cognitive_model.get("object_region_index", {})
        chain = intent.get("candidate_process_chain", [])
        missing_targets: list[str] = []
        for step in chain:
            meta = STEP_LIBRARY.get(step, {})
            target_region = meta.get("target_region")
            target_object = meta.get("target_object")
            if target_region and target_region not in regions:
                missing_targets.append(target_region)
            if target_object and target_object not in objects:
                missing_targets.append(target_object)
        check_id = "causal_chain_solved" if intent["task_type"] == "causal_process_chain" else "experience_chain_loaded"
        checks = [
            {"check_id": "intent_executable", "passed": True, "notes": intent["reason"]},
            {"check_id": check_id, "passed": bool(chain), "notes": " -> ".join(chain)},
            {"check_id": "digital_space_targets_available", "passed": not missing_targets, "notes": ",".join(missing_targets)},
            {"check_id": "runtime_scope", "passed": True, "notes": "第一阶段以数字执行体回放经验链，不进入真实机器人控制"},
        ]
        allowed = all(item["passed"] for item in checks)
        return {
            "allowed": allowed,
            "decision": "allowed" if allowed else "blocked",
            "reason": "因果过程链已通过数字空间准入" if allowed and intent["task_type"] == "causal_process_chain" else ("教学经验链已通过数字空间准入" if allowed else "过程链缺少空间目标"),
            "checks": checks,
        }
    task = TASK_LIBRARY[intent["task_type"]]
    bindings = cognitive_model.get("binding_candidates", {})
    object_index = cognitive_model.get("object_region_index", {})
    regions = {item["region_id"]: item for item in cognitive_model.get("space_region_table", [])}
    missing_bindings = [name for name in task["required_bindings"] if name not in bindings]
    required_objects = [bindings.get("CUP_OBJECT"), bindings.get("KETTLE_OBJECT"), bindings.get("CAMERA_SENSOR")]
    missing_objects = [item for item in required_objects if item and item not in object_index]
    required_regions = [bindings.get("POUR_OPERATION_REGION"), bindings.get("WALKABLE_REGION")]
    missing_regions = [item for item in required_regions if item and item not in regions]
    risk_regions = cognitive_model.get("risk_region_table", [])
    checks = [
        {"check_id": "intent_executable", "passed": True, "notes": intent["reason"]},
        {"check_id": "space_bindings_complete", "passed": not missing_bindings, "notes": ",".join(missing_bindings)},
        {"check_id": "objects_indexed", "passed": not missing_objects, "notes": ",".join(missing_objects)},
        {"check_id": "required_regions_available", "passed": not missing_regions, "notes": ",".join(missing_regions)},
        {"check_id": "risk_regions_known", "passed": True, "notes": f"{len(risk_regions)} risk region(s) guarded"},
    ]
    allowed = all(item["passed"] for item in checks)
    return {
        "allowed": allowed,
        "decision": "allowed" if allowed else "blocked",
        "reason": "空间上下文满足倒水过程准入" if allowed else "空间上下文缺失必要绑定",
        "checks": checks,
    }


def build_cannot_do_result(utterance: str, intent: dict[str, Any], space_admission: dict[str, Any]) -> dict[str, Any]:
    cognitive_model = get_cognitive_model()
    task_id = "task_unexecutable"
    teaching_hint = None
    if intent.get("task_type") in {"process_chain", "causal_process_chain"}:
        teaching_hint = {
            "teachable": True,
            "reason": "可通过人工步骤教学补齐缺失因果过程",
            "candidate_process_chain": intent.get("candidate_process_chain", []),
            "endpoint": "POST /experience/teach",
        }
    return {
        "task_id": task_id,
        "scenario": "not_executed",
        "intent_translation": intent,
        "space_admission": space_admission,
        "admission_decision": {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "allowed": False,
            "decision": "blocked" if intent["decision"] == "blocked" else "unsupported",
            "checks": space_admission["checks"],
            "missing_items": [intent["reason"]],
        },
        "audit_summary": {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "process_instance_id": "not_created",
            "outcome": "cannot_do",
            "stage_summary": [],
            "fact_summary": [],
            "stop_reason": intent["reason"],
        },
        "stage_runtime_state": {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "process_instance_id": "not_created",
            "current_stage_id": None,
            "runtime_state": "cannot_do",
            "utterance": utterance,
        },
        "execution_trace": {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "process_instance_id": "not_created",
            "events": [],
        },
        "teaching_hint": teaching_hint,
        "space_context": build_space_context(cognitive_model),
    }


def run_process_chain_experience(intent: dict[str, Any], utterance: str, space_admission: dict[str, Any]) -> dict[str, Any]:
    cognitive_model = get_cognitive_model()
    task_id = "task_" + intent["experience_id"]
    events = []
    stage_summary = []
    fact_summary = []
    runtime_world_state = build_initial_runtime_world_state(cognitive_model, intent)
    runtime_world_state_initial = clone_runtime_world_state(runtime_world_state)
    world_state_transitions = []
    before_state = "ready"
    profile = build_default_body_capability_profile()
    stepwise_readaptation = None
    for index, step in enumerate(intent.get("candidate_process_chain", []), start=1):
        meta = STEP_LIBRARY[step]
        preflight = evaluate_runtime_step_preflight(runtime_world_state, step, meta)
        if preflight.get("result") == "blocked":
            remaining_steps = [step] + list(intent.get("candidate_process_chain", [])[index:])
            stepwise_readaptation = build_stepwise_readaptation(
                task_id,
                intent.get("goal_fact"),
                remaining_steps,
                runtime_world_state,
                profile,
            )
            stage_summary.append(
                {
                    "stage_id": step,
                    "result": "blocked",
                    "notes": "运行时环境发生变化，当前步骤需重新适配",
                }
            )
            events.append(
                {
                    "event_id": f"evt_{index:02d}_{step}_blocked",
                    "consumed_sequence": index,
                    "trigger_reason": "step_preflight_blocked",
                    "before_state": before_state,
                    "after_state": "readaptation_required",
                    "payload_summary": f"step={step} blocked_by_runtime_environment readaptation={stepwise_readaptation['readaptation_id']}",
                    "preflight": preflight,
                }
            )
            break
        after_state = f"{step}_completed"
        target = meta.get("target_region") or meta.get("target_object", "unknown_target")
        fact = meta["produces_fact"]
        transition = apply_step_to_runtime_world_state(runtime_world_state, step, meta, index)
        world_state_transitions.append(transition)
        events.append(
            {
                "event_id": f"evt_{index:02d}_{step}",
                "consumed_sequence": index,
                "trigger_reason": "causal_step_executed" if intent["task_type"] == "causal_process_chain" else "learned_step_executed",
                "before_state": before_state,
                "after_state": after_state,
                "payload_summary": (
                    f"step={step} display={meta['display_name']} capability={meta['capability']} "
                    f"target={target} produced_fact={fact} planner={intent['task_type']} adapter=digital_executor "
                    f"runtime_world={transition['before_executor_location']}->{transition['after_executor_location']}"
                ),
                "runtime_world_transition": {
                    "requires_facts": transition["requires_facts"],
                    "missing_before_step": transition["missing_before_step"],
                    "destroys_facts": transition["destroys_facts"],
                    "produces_fact": transition["produces_fact"],
                    "before_facts": transition["before_facts"],
                    "after_facts": transition["after_facts"],
                    "before_executor_location": transition["before_executor_location"],
                    "after_executor_location": transition["after_executor_location"],
                },
                "preflight_result": preflight.get("result"),
                "route_adjustment": preflight.get("route_adjustment"),
            }
        )
        stage_summary.append(
            {
                "stage_id": step,
                "result": "completed",
                "notes": f"{meta['display_name']}；运行时世界状态 {transition['before_executor_location']} -> {transition['after_executor_location']}",
            }
        )
        fact_summary.append({"fact_id": fact, "state": "established", "channel_notes": "digital_space_trace"})
        before_state = after_state
    audit_summary = {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "process_instance_id": intent["experience_id"],
        "outcome": "readaptation_required" if stepwise_readaptation else "completed",
        "stage_summary": stage_summary,
        "fact_summary": fact_summary,
        "stop_reason": None,
        "causal_plan": intent.get("causal_plan"),
        "runtime_world_state_final": runtime_world_state,
    }
    stage_runtime_state = {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "process_instance_id": intent["experience_id"],
        "current_stage_id": runtime_world_state.get("current_stage"),
        "runtime_state": "readaptation_required" if stepwise_readaptation else "completed",
        "utterance": utterance,
        "runtime_world_state": runtime_world_state,
        "execution_feasibility": stepwise_readaptation.get("execution_feasibility", {}) if stepwise_readaptation else None,
        "body_capability_profile": profile,
    }
    execution_trace = {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "process_instance_id": intent["experience_id"],
        "events": events,
        "causal_plan": intent.get("causal_plan"),
        "runtime_world_state_initial": runtime_world_state_initial,
        "runtime_world_state_final": runtime_world_state,
        "runtime_world_state_policy": runtime_world_state["persistence_policy"],
        "stepwise_readaptation": stepwise_readaptation,
    }
    AUDIT_STORE[task_id] = audit_summary
    STATE_STORE[task_id] = stage_runtime_state
    TRACE_STORE[task_id] = execution_trace
    RUNTIME_WORLD_STATE_STORE[task_id] = runtime_world_state
    recovery_record = None
    if stepwise_readaptation:
        gap_record = stepwise_readaptation.get("experience_gap_record")
        recovery_record = build_recovery_record_for_task(
            task_id=task_id,
            failed_experience_ref=intent["experience_id"],
            outcome="readaptation_required",
            stop_reason="step_preflight_blocked",
            expected_state=f"goal_fact:{intent.get('goal_fact') or 'unknown'}",
            observed_state=f"blocked_step:{stepwise_readaptation.get('remaining_steps', ['unknown'])[0]}",
            audit_record_id=task_id,
            runtime_world_state_snapshot_id=runtime_world_state.get("runtime_world_state_snapshot_id"),
            gap_record=gap_record,
            readaptation_id=stepwise_readaptation.get("readaptation_id"),
            source_refs={
                "stepwise_readaptation_id": stepwise_readaptation.get("readaptation_id"),
                "experience_gap_record_id": gap_record.get("gap_record_id") if gap_record else None,
            },
        )
    return {
        "task_id": task_id,
        "scenario": "causal_digital_experience" if intent["task_type"] == "causal_process_chain" else "learned_digital_experience",
        "intent_translation": intent,
        "space_admission": space_admission,
        "admission_decision": {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "allowed": True,
            "decision": "allowed",
            "checks": space_admission["checks"],
            "missing_items": [],
        },
        "audit_summary": audit_summary,
        "stage_runtime_state": stage_runtime_state,
        "execution_trace": execution_trace,
        "runtime_world_state": runtime_world_state,
        "stepwise_readaptation": stepwise_readaptation,
        "recovery_record": recovery_record,
        "experience_ref": intent["experience_id"],
        "space_context": build_space_context(cognitive_model),
    }


def admit_process(utterance: str = "给客人倒一杯水") -> dict[str, Any]:
    queue = SerialEventQueue()
    process_instance = read_json(DATA / "pour_water_process_instance.json")
    initial_state = read_json(DATA / "stage_runtime_state_initial.json")
    timeline = read_json(DATA / "mock_timeline_success.json")
    adapter = MockRobotAdapter(timeline, queue)
    runtime = P016Runtime(process_instance, initial_state, adapter)
    intent = translate_intent(utterance)
    cognitive_model = get_cognitive_model()
    space_admission = evaluate_space_admission(intent, cognitive_model)
    admission = runtime.admit()
    admission["intent_translation"] = intent
    admission["space_admission"] = space_admission
    if not space_admission["allowed"]:
        admission["allowed"] = False
        admission["decision"] = space_admission["decision"]
        admission["checks"].extend(space_admission["checks"])
        admission["missing_items"].append(space_admission["reason"])
    else:
        admission["checks"].extend(space_admission["checks"])
    return admission


def build_space_context(cognitive_model: dict[str, Any]) -> dict[str, Any]:
    return {
        "space_id": cognitive_model["local_environment_summary"]["space_id"],
        "cognitive_model_id": cognitive_model["cognitive_model_id"],
        "region_count": cognitive_model["local_environment_summary"]["region_count"],
        "relation_count": cognitive_model["local_environment_summary"]["relation_count"],
        "object_count": cognitive_model["local_environment_summary"]["object_count"],
        "binding_candidates": cognitive_model["binding_candidates"],
    }


def build_migration_task_id(utterance: str, intent: dict[str, Any]) -> str:
    seed = "|".join(
        [
            normalize_text(utterance),
            intent.get("task_type", "unknown"),
            intent.get("candidate_process") or intent.get("goal_fact") or "none",
        ]
    )
    base = "migration_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    if base not in RUNTIME_WORLD_STATE_STORE and base not in STATE_STORE:
        return base
    suffix = 2
    while True:
        candidate = f"{base}_{suffix}"
        if candidate not in RUNTIME_WORLD_STATE_STORE and candidate not in STATE_STORE:
            return candidate
        suffix += 1


def get_process_chain_for_intent(intent: dict[str, Any]) -> list[str]:
    chain = list(intent.get("candidate_process_chain", []))
    if chain:
        return chain
    if intent.get("task_type") == "pour_water":
        return ["pour_water"]
    candidate = intent.get("candidate_process")
    if candidate in STEP_LIBRARY:
        return [candidate]
    return []


def ensure_runtime_control_state(runtime_world_state: dict[str, Any]) -> dict[str, Any]:
    control = runtime_world_state.setdefault("runtime_control", {})
    control.setdefault("active_task_state", "active")
    control.setdefault("active_task_reason", "runtime_task_active")
    control.setdefault("event_history", [])
    control.setdefault("pending_candidate_task_id", None)
    return control


def build_runtime_event_frame(
    task_id: str,
    utterance: str,
    intent: dict[str, Any],
    runtime_world_state: dict[str, Any],
) -> dict[str, Any]:
    state = STATE_STORE.get(task_id, {})
    audit = AUDIT_STORE.get(task_id, {})
    current_goal_fact = infer_goal_fact_from_task_state(task_id, state, audit)
    requested_goal_fact = intent.get("goal_fact")
    established_facts = set(runtime_world_state.get("established_facts", []))
    process_chain = get_process_chain_for_intent(intent)
    interrupt_requested = any(keyword in (utterance or "") for keyword in INTERRUPT_TASK_KEYWORDS)
    replacement_task_text = extract_replacement_task_text(utterance) if interrupt_requested else ""
    replacement_task_candidate = bool(replacement_task_text and looks_like_new_task_request(replacement_task_text))
    potential_new_task_request = bool(
        not interrupt_requested
        and not requested_goal_fact
        and not process_chain
        and looks_like_new_task_request(utterance)
    )
    holding = list(runtime_world_state.get("executor", {}).get("holding", []))
    current_runtime_state = state.get("runtime_state") or runtime_world_state.get("current_stage") or "unknown"
    return {
        "task_id": task_id,
        "current_goal_fact": current_goal_fact,
        "requested_goal_fact": requested_goal_fact,
        "current_runtime_state": current_runtime_state,
        "current_stage": runtime_world_state.get("current_stage"),
        "completed_stages": list(runtime_world_state.get("completed_stages", [])),
        "established_facts": sorted(established_facts),
        "holding_objects": holding,
        "process_chain": process_chain,
        "interrupt_requested": interrupt_requested,
        "replacement_task_text": replacement_task_text,
        "replacement_task_candidate": replacement_task_candidate,
        "potential_new_task_request": potential_new_task_request,
        "requested_goal_already_satisfied": bool(requested_goal_fact and requested_goal_fact in established_facts),
        "current_goal_already_satisfied": bool(current_goal_fact and current_goal_fact in established_facts),
        "goal_switched": bool(requested_goal_fact and current_goal_fact and requested_goal_fact != current_goal_fact),
        "runtime_world_state_snapshot_id": runtime_world_state.get("runtime_world_state_snapshot_id"),
        "release_status": runtime_world_state.get("release_status"),
    }


def chain_is_compatible_with_current_holding(process_chain: list[str], runtime_world_state: dict[str, Any]) -> bool:
    holding_objects = list(runtime_world_state.get("executor", {}).get("holding", []))
    if not holding_objects or not process_chain:
        return True
    established_facts = set(runtime_world_state.get("established_facts", []))
    for step in process_chain:
        step_meta = STEP_LIBRARY.get(step, {})
        requires_facts = set(step_meta.get("requires_facts", []))
        if "gripper_empty" in requires_facts and "gripper_empty" not in established_facts:
            return False
    return True


def arbitrate_runtime_event(
    task_id: str,
    utterance: str,
    intent: dict[str, Any],
    runtime_world_state: dict[str, Any],
) -> dict[str, Any]:
    frame = build_runtime_event_frame(task_id, utterance, intent, runtime_world_state)
    chain = frame["process_chain"]
    holding_compatible = chain_is_compatible_with_current_holding(chain, runtime_world_state)
    if frame["interrupt_requested"] and not frame["replacement_task_candidate"] and not chain and not frame["requested_goal_fact"]:
        decision = "pause_current_task"
        reason = "explicit_interrupt_without_replacement_goal"
        can_enter_execution = False
        required_actions = ["pause_active_task", "await_next_instruction"]
    elif frame["replacement_task_candidate"] and not chain and not frame["requested_goal_fact"]:
        if frame["holding_objects"]:
            decision = "request_human_confirmation"
            reason = "interrupt_with_unknown_replacement_while_executor_holds_object"
            can_enter_execution = False
            required_actions = ["pause_active_task", "confirm_task_switch", "resolve_held_object_state", "request_teaching_or_object_grounding"]
        else:
            decision = "pause_current_task"
            reason = "interrupt_with_unknown_replacement_requires_clarification"
            can_enter_execution = False
            required_actions = ["pause_active_task", "request_object_grounding", "request_teaching_or_experience"]
    elif frame["potential_new_task_request"]:
        if frame["holding_objects"]:
            decision = "request_human_confirmation"
            reason = "new_task_requested_while_executor_holds_object_and_target_is_not_grounded"
            can_enter_execution = False
            required_actions = ["confirm_task_switch", "resolve_held_object_state", "request_teaching_or_object_grounding"]
        else:
            decision = "request_clarification"
            reason = "new_task_requested_but_target_or_skill_is_not_grounded_in_local_concepts"
            can_enter_execution = False
            required_actions = ["request_object_grounding", "request_teaching_or_experience"]
    elif frame["goal_switched"] or (frame["interrupt_requested"] and (chain or frame["requested_goal_fact"])):
        if frame["holding_objects"] and not holding_compatible:
            decision = "request_human_confirmation"
            reason = "task_switch_requested_while_executor_holds_object"
            can_enter_execution = False
            required_actions = ["confirm_task_switch", "resolve_held_object_state", "reenter_orchestration"]
        elif chain:
            decision = "pause_and_switch_task"
            reason = "new_goal_or_interrupt_requires_new_candidate_chain"
            can_enter_execution = True
            required_actions = ["pause_active_task", "spawn_candidate_from_current_world_state", "dispatch_new_candidate_chain"]
        else:
            decision = "pause_current_task"
            reason = "new_goal_requested_but_no_supported_chain_available"
            can_enter_execution = False
            required_actions = ["pause_active_task", "request_clarification_or_teaching"]
    elif frame["requested_goal_already_satisfied"]:
        decision = "no_new_execution_required"
        reason = "requested_goal_already_satisfied_in_current_world_state"
        can_enter_execution = False
        required_actions = ["report_goal_already_satisfied", "await_next_instruction"]
    elif chain:
        decision = "continue_current_task"
        reason = "next_step_must_be_decided_from_current_world_state"
        can_enter_execution = True
        required_actions = ["project_chain_against_current_world_state", "dispatch_remaining_steps"]
    else:
        decision = "request_clarification"
        reason = "current_world_state_read_but_new_event_still_lacks_executable_chain"
        can_enter_execution = False
        required_actions = ["request_clarification_or_teaching"]
    arbitration_seed = "|".join(
        [
            task_id,
            normalize_text(utterance),
            frame.get("runtime_world_state_snapshot_id") or "none",
            decision,
        ]
    )
    return {
        "schema_version": "1.0.0",
        "arbitration_id": "arbitrate_" + hashlib.sha1(arbitration_seed.encode("utf-8")).hexdigest()[:12],
        "decision": decision,
        "reason": reason,
        "can_enter_execution": can_enter_execution,
        "required_actions": required_actions,
        "holding_chain_compatible": holding_compatible,
        "state_first_principle": "all new events must be judged from current runtime world state before selecting the next action",
        "world_state_basis": {
            "task_id": task_id,
            "runtime_world_state_snapshot_id": frame["runtime_world_state_snapshot_id"],
            "current_goal_fact": frame["current_goal_fact"],
            "requested_goal_fact": frame["requested_goal_fact"],
            "current_runtime_state": frame["current_runtime_state"],
            "current_stage": frame["current_stage"],
            "holding_objects": frame["holding_objects"],
            "established_facts": frame["established_facts"],
        },
        "event_frame": frame,
    }


def apply_runtime_event_arbitration(task_id: str, arbitration: dict[str, Any]) -> dict[str, Any]:
    current = get_runtime_world_state(task_id)
    if "error" in current:
        return current
    runtime_world_state = current["runtime_world_state_snapshot"]
    control = ensure_runtime_control_state(runtime_world_state)
    decision = arbitration.get("decision")
    if decision == "pause_current_task":
        control["active_task_state"] = "paused"
        control["active_task_reason"] = arbitration.get("reason")
        state_runtime = "paused_by_runtime_event"
    elif decision == "pause_and_switch_task":
        control["active_task_state"] = "suspended"
        control["active_task_reason"] = arbitration.get("reason")
        state_runtime = "suspended_for_new_candidate"
    elif decision == "request_human_confirmation":
        control["active_task_state"] = "awaiting_human_confirmation"
        control["active_task_reason"] = arbitration.get("reason")
        state_runtime = "awaiting_human_confirmation"
    else:
        control["active_task_state"] = "active"
        control["active_task_reason"] = arbitration.get("reason", "runtime_task_active")
        state_runtime = STATE_STORE.get(task_id, {}).get("runtime_state") or "active"
    control["event_history"].append(
        {
            "arbitration_id": arbitration.get("arbitration_id"),
            "decision": decision,
            "reason": arbitration.get("reason"),
        }
    )
    RUNTIME_WORLD_STATE_STORE[task_id] = runtime_world_state
    if task_id in STATE_STORE:
        STATE_STORE[task_id]["runtime_world_state"] = runtime_world_state
        STATE_STORE[task_id]["runtime_state"] = state_runtime
        STATE_STORE[task_id]["runtime_event_arbitration"] = arbitration
    return {
        "task_id": task_id,
        "runtime_world_state_snapshot": runtime_world_state,
        "runtime_state": state_runtime,
        "runtime_event_arbitration": arbitration,
    }


def build_runtime_task_id_from_event(source_task_id: str, utterance: str, intent: dict[str, Any]) -> str:
    seed = "|".join(
        [
            source_task_id,
            normalize_text(utterance),
            intent.get("goal_fact") or intent.get("candidate_process") or "none",
        ]
    )
    base = "runtime_task_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    if base not in RUNTIME_WORLD_STATE_STORE and base not in STATE_STORE:
        return base
    suffix = 2
    while True:
        candidate = f"{base}_{suffix}"
        if candidate not in RUNTIME_WORLD_STATE_STORE and candidate not in STATE_STORE:
            return candidate
        suffix += 1


def seed_runtime_task_from_snapshot(
    source_task_id: str,
    utterance: str,
    intent: dict[str, Any],
    runtime_world_state: dict[str, Any],
) -> str:
    new_task_id = build_runtime_task_id_from_event(source_task_id, utterance, intent)
    cloned_state = clone_runtime_world_state(runtime_world_state)
    cloned_state["task_ref"] = new_task_id
    cloned_state["migration_task_id"] = new_task_id
    cloned_state["runtime_world_state_snapshot_id"] = new_task_id + "_snapshot"
    cloned_state["audit_record_id"] = "audit_" + new_task_id.removeprefix("runtime_task_")
    cloned_state["current_stage"] = None
    cloned_state["completed_stages"] = []
    control = ensure_runtime_control_state(cloned_state)
    control["active_task_state"] = "active"
    control["active_task_reason"] = "state_first_switch_spawned_from_existing_runtime_world_state"
    profile = STATE_STORE.get(source_task_id, {}).get("body_capability_profile") or build_default_body_capability_profile()
    RUNTIME_WORLD_STATE_STORE[new_task_id] = cloned_state
    STATE_STORE[new_task_id] = {
        "schema_version": "1.0.0",
        "task_id": new_task_id,
        "source_task_id": source_task_id,
        "current_stage_id": None,
        "runtime_state": "spawned_from_runtime_world_state",
        "runtime_world_state": cloned_state,
        "goal_fact": intent.get("goal_fact"),
        "candidate_process_chain": get_process_chain_for_intent(intent),
        "body_capability_profile": profile,
        "runtime_event_arbitration": {
            "source_task_id": source_task_id,
            "decision": "pause_and_switch_task",
            "reason": "spawn_candidate_from_current_world_state",
        },
    }
    AUDIT_STORE[new_task_id] = {
        "schema_version": "1.0.0",
        "task_id": new_task_id,
        "process_instance_id": intent.get("experience_id") or new_task_id,
        "outcome": "spawned_from_runtime_world_state",
        "stage_summary": [],
        "fact_summary": [],
        "stop_reason": None,
        "runtime_world_state_final": cloned_state,
        "source_task_id": source_task_id,
    }
    TRACE_STORE[new_task_id] = {
        "schema_version": "1.0.0",
        "task_id": new_task_id,
        "process_instance_id": intent.get("experience_id") or new_task_id,
        "events": [],
        "runtime_world_state_initial": clone_runtime_world_state(cloned_state),
        "runtime_world_state_final": clone_runtime_world_state(cloned_state),
        "runtime_world_state_transitions": [],
        "runtime_world_state_policy": cloned_state.get("persistence_policy"),
        "source_task_id": source_task_id,
    }
    return new_task_id


def adapt_intent_to_runtime_world_state(
    intent: dict[str, Any],
    task_id: str | None = None,
    runtime_world_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = runtime_world_state or get_active_runtime_snapshot(task_id)
    if not snapshot:
        return intent
    source_chain = get_process_chain_for_intent(intent)
    if not source_chain:
        return intent
    projection = project_process_chain_against_runtime_world_state(source_chain, snapshot)
    adapted_intent = dict(intent)
    adapted_intent["candidate_process_chain"] = projection["continued_process_chain"]
    adapted_intent["runtime_continuation"] = {
        "continuation_task_id": task_id,
        "source_snapshot_id": projection["source_snapshot_id"],
        "continued_from_facts": projection["continued_from_facts"],
        "skipped_steps": projection["skipped_steps"],
        "projected_facts_after_chain": projection["projected_facts_after_chain"],
    }
    if projection["skipped_steps"]:
        base_reason = adapted_intent.get("reason") or "runtime_continuation"
        adapted_intent["reason"] = base_reason + "；已按当前任务期快照裁剪已成立步骤"
    return adapted_intent


def build_default_body_capability_profile() -> dict[str, Any]:
    profile = MockRobotAdapter(read_json(DATA / "mock_timeline_success.json"), SerialEventQueue()).report_executor_profile()
    step_capabilities = sorted({meta.get("capability") for meta in STEP_LIBRARY.values() if meta.get("capability")})
    profile["supported_actions"] = sorted(set(profile.get("supported_actions", [])) | set(step_capabilities))
    profile["profile_source"] = "stage_one_mock_executor_profile"
    return profile


def continue_runtime_task(
    task_id: str,
    utterance: str,
    intent: dict[str, Any],
    space_admission: dict[str, Any],
) -> dict[str, Any]:
    current = get_runtime_world_state(task_id)
    if "error" in current:
        return current
    runtime_world_state = clone_runtime_world_state(current["runtime_world_state_snapshot"])
    if runtime_world_state.get("release_status") == "released":
        return {
            "error": "runtime_world_state_released",
            "task_id": task_id,
            "release_token": runtime_world_state.get("release_token"),
        }

    adapted_intent = adapt_intent_to_runtime_world_state(intent, task_id=task_id, runtime_world_state=runtime_world_state)
    process_chain = get_process_chain_for_intent(adapted_intent)
    prior_trace = TRACE_STORE.get(task_id, {})
    prior_audit = AUDIT_STORE.get(task_id, {})
    prior_state = STATE_STORE.get(task_id, {})
    prior_events = list(prior_trace.get("events", []))
    stage_summary = list(prior_audit.get("stage_summary", []))
    fact_summary = list(prior_audit.get("fact_summary", []))
    world_state_transitions = list(prior_trace.get("runtime_world_state_transitions", []))
    new_events: list[dict[str, Any]] = []
    profile = prior_state.get("body_capability_profile") or build_default_body_capability_profile()
    stepwise_readaptation = None
    before_state = prior_state.get("runtime_state") or runtime_world_state.get("current_stage") or "ready"
    start_sequence = len(prior_events)

    for offset, step in enumerate(process_chain, start=1):
        meta = STEP_LIBRARY[step]
        preflight = evaluate_runtime_step_preflight(runtime_world_state, step, meta)
        sequence = start_sequence + offset
        if preflight.get("result") == "blocked":
            remaining_steps = [step] + list(process_chain[offset:])
            stepwise_readaptation = build_stepwise_readaptation(
                task_id,
                adapted_intent.get("goal_fact"),
                remaining_steps,
                runtime_world_state,
                profile,
            )
            stage_summary.append(
                {
                    "stage_id": step,
                    "result": "blocked",
                    "notes": "运行时环境变化导致当前步骤需重新适配",
                }
            )
            new_events.append(
                {
                    "event_id": f"evt_{sequence:02d}_{step}_blocked",
                    "consumed_sequence": sequence,
                    "trigger_reason": "step_preflight_blocked",
                    "before_state": before_state,
                    "after_state": "readaptation_required",
                    "payload_summary": f"step={step} blocked_by_runtime_environment readaptation={stepwise_readaptation['readaptation_id']}",
                    "preflight": preflight,
                }
            )
            break
        after_state = f"{step}_completed"
        target = meta.get("target_region") or meta.get("target_object", "unknown_target")
        fact = meta["produces_fact"]
        transition = apply_step_to_runtime_world_state(runtime_world_state, step, meta, sequence)
        world_state_transitions.append(transition)
        new_events.append(
            {
                "event_id": f"evt_{sequence:02d}_{step}",
                "consumed_sequence": sequence,
                "trigger_reason": "continued_runtime_step_executed",
                "before_state": before_state,
                "after_state": after_state,
                "payload_summary": (
                    f"step={step} display={meta['display_name']} capability={meta['capability']} "
                    f"target={target} produced_fact={fact} planner=runtime_continuation adapter=digital_executor "
                    f"runtime_world={transition['before_executor_location']}->{transition['after_executor_location']}"
                ),
                "runtime_world_transition": {
                    "requires_facts": transition["requires_facts"],
                    "missing_before_step": transition["missing_before_step"],
                    "destroys_facts": transition["destroys_facts"],
                    "produces_fact": transition["produces_fact"],
                    "before_facts": transition["before_facts"],
                    "after_facts": transition["after_facts"],
                    "before_executor_location": transition["before_executor_location"],
                    "after_executor_location": transition["after_executor_location"],
                },
                "preflight_result": preflight.get("result"),
                "route_adjustment": preflight.get("route_adjustment"),
            }
        )
        stage_summary.append(
            {
                "stage_id": step,
                "result": "completed",
                "notes": f"{meta['display_name']}；续接执行时世界状态 {transition['before_executor_location']} -> {transition['after_executor_location']}",
            }
        )
        fact_summary.append({"fact_id": fact, "state": "established", "channel_notes": "runtime_continuation_trace"})
        before_state = after_state

    goal_fact = adapted_intent.get("goal_fact") or infer_goal_fact_from_task_state(task_id, prior_state, prior_audit)
    updated_trace_events = prior_events + new_events
    updated_runtime_state = "readaptation_required" if stepwise_readaptation else "completed"
    updated_audit = {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "process_instance_id": prior_audit.get("process_instance_id") or adapted_intent.get("experience_id") or task_id,
        "outcome": updated_runtime_state,
        "stage_summary": stage_summary,
        "fact_summary": fact_summary,
        "stop_reason": "step_preflight_blocked" if stepwise_readaptation else None,
        "causal_plan": adapted_intent.get("causal_plan") or prior_audit.get("causal_plan"),
        "runtime_world_state_final": runtime_world_state,
        "runtime_continuation": adapted_intent.get("runtime_continuation"),
    }
    updated_stage_state = {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "process_instance_id": updated_audit["process_instance_id"],
        "current_stage_id": runtime_world_state.get("current_stage"),
        "runtime_state": updated_runtime_state,
        "utterance": utterance,
        "runtime_world_state": runtime_world_state,
        "goal_fact": goal_fact,
        "candidate_process_chain": process_chain,
        "execution_feasibility": stepwise_readaptation.get("execution_feasibility", {}) if stepwise_readaptation else None,
        "body_capability_profile": profile,
        "experience_gap_record_id": (
            stepwise_readaptation.get("experience_gap_record", {}).get("gap_record_id") if stepwise_readaptation else None
        ),
        "runtime_continuation": adapted_intent.get("runtime_continuation"),
    }
    updated_trace = {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "process_instance_id": updated_audit["process_instance_id"],
        "events": updated_trace_events,
        "causal_plan": adapted_intent.get("causal_plan") or prior_trace.get("causal_plan"),
        "runtime_world_state_initial": prior_trace.get("runtime_world_state_initial") or clone_runtime_world_state(runtime_world_state),
        "runtime_world_state_final": runtime_world_state,
        "runtime_world_state_policy": runtime_world_state.get("persistence_policy"),
        "runtime_world_state_transitions": world_state_transitions,
        "stepwise_readaptation": stepwise_readaptation,
        "runtime_continuation": adapted_intent.get("runtime_continuation"),
    }
    AUDIT_STORE[task_id] = updated_audit
    STATE_STORE[task_id] = updated_stage_state
    TRACE_STORE[task_id] = updated_trace
    RUNTIME_WORLD_STATE_STORE[task_id] = runtime_world_state
    recovery_record = None
    if stepwise_readaptation:
        gap_record = stepwise_readaptation.get("experience_gap_record")
        recovery_record = build_recovery_record_for_task(
            task_id=task_id,
            failed_experience_ref=updated_audit["process_instance_id"],
            outcome="readaptation_required",
            stop_reason="step_preflight_blocked",
            expected_state=f"goal_fact:{goal_fact or 'unknown'}",
            observed_state=f"blocked_step:{stepwise_readaptation.get('remaining_steps', ['unknown'])[0]}",
            audit_record_id=task_id,
            runtime_world_state_snapshot_id=runtime_world_state.get("runtime_world_state_snapshot_id"),
            gap_record=gap_record,
            readaptation_id=stepwise_readaptation.get("readaptation_id"),
            source_refs={
                "stepwise_readaptation_id": stepwise_readaptation.get("readaptation_id"),
                "experience_gap_record_id": gap_record.get("gap_record_id") if gap_record else None,
            },
        )
    return {
        "task_id": task_id,
        "scenario": "runtime_continuation",
        "intent_translation": adapted_intent,
        "space_admission": space_admission,
        "admission_decision": {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "allowed": True,
            "decision": "allowed",
            "checks": space_admission.get("checks", []),
            "missing_items": [],
        },
        "audit_summary": updated_audit,
        "stage_runtime_state": updated_stage_state,
        "execution_trace": {
            **updated_trace,
            "events": new_events,
            "prior_event_count": len(prior_events),
        },
        "recovery_record": recovery_record,
        "runtime_world_state": runtime_world_state,
        "space_context": build_space_context(get_cognitive_model()),
    }


def start_task_from_runtime_world_state(
    source_task_id: str,
    utterance: str,
    intent: dict[str, Any],
    space_admission: dict[str, Any],
) -> dict[str, Any]:
    current = get_runtime_world_state(source_task_id)
    if "error" in current:
        return current
    runtime_world_state = clone_runtime_world_state(current["runtime_world_state_snapshot"])
    new_task_id = seed_runtime_task_from_snapshot(source_task_id, utterance, intent, runtime_world_state)
    return continue_runtime_task(new_task_id, utterance, intent, space_admission)


def build_runtime_event_arbitration_result(
    task_id: str,
    utterance: str,
    intent: dict[str, Any],
    space_admission: dict[str, Any],
    arbitration: dict[str, Any],
) -> dict[str, Any]:
    current = get_runtime_world_state(task_id)
    runtime_world_state = current.get("runtime_world_state_snapshot", {}) if "error" not in current else {}
    runtime_state = STATE_STORE.get(task_id, {}).get("runtime_state") or arbitration.get("decision")
    return {
        "task_id": task_id,
        "scenario": "runtime_event_arbitrated",
        "intent_translation": intent,
        "space_admission": space_admission,
        "audit_summary": {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "process_instance_id": STATE_STORE.get(task_id, {}).get("process_instance_id") or task_id,
            "outcome": arbitration.get("decision"),
            "stage_summary": [],
            "fact_summary": [],
            "stop_reason": arbitration.get("reason"),
            "runtime_world_state_final": runtime_world_state,
        },
        "stage_runtime_state": {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "process_instance_id": STATE_STORE.get(task_id, {}).get("process_instance_id") or task_id,
            "current_stage_id": runtime_world_state.get("current_stage"),
            "runtime_state": runtime_state,
            "utterance": utterance,
            "runtime_world_state": runtime_world_state,
            "goal_fact": intent.get("goal_fact"),
            "candidate_process_chain": get_process_chain_for_intent(intent),
            "runtime_event_arbitration": arbitration,
        },
        "execution_trace": {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "process_instance_id": STATE_STORE.get(task_id, {}).get("process_instance_id") or task_id,
            "events": [
                {
                    "event_id": arbitration.get("arbitration_id"),
                    "consumed_sequence": 0,
                    "trigger_reason": "runtime_event_arbitrated",
                    "before_state": runtime_state,
                    "after_state": runtime_state,
                    "payload_summary": f"decision={arbitration.get('decision')} reason={arbitration.get('reason')}",
                }
            ],
            "runtime_world_state_initial": runtime_world_state,
            "runtime_world_state_final": runtime_world_state,
            "runtime_event_arbitration": arbitration,
        },
        "runtime_world_state": runtime_world_state,
        "runtime_event_arbitration": arbitration,
        "space_context": build_space_context(get_cognitive_model()),
    }


def build_binding_candidates(
    intent: dict[str, Any],
    cognitive_model: dict[str, Any],
    runtime_world_state: dict[str, Any],
    body_capability_profile: dict[str, Any],
    invariant_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    regions = {item["region_id"]: item for item in cognitive_model.get("space_region_table", [])}
    objects = cognitive_model.get("object_region_index", {})
    chain = get_process_chain_for_intent(intent)
    candidate_id = "binding_" + hashlib.sha1(("|".join(chain) or intent.get("task_type", "unknown")).encode("utf-8")).hexdigest()[:10]
    step_bindings: list[dict[str, Any]] = []
    missing_targets: list[dict[str, Any]] = []
    contract = invariant_contract or build_invariant_contract(chain)
    slot_specs = {item.get("slot_id"): item for item in contract.get("binding_slots", [])}
    current_space_slots = cognitive_model.get("binding_candidates", {})
    candidate_sets = cognitive_model.get("binding_candidate_sets", {})
    ambiguous_bindings: list[dict[str, Any]] = []
    rejected_candidates: list[dict[str, Any]] = []
    for step in chain:
        meta = STEP_LIBRARY.get(step, {})
        portable_slot = build_portable_binding_slot(step, meta)
        slot_id = portable_slot["slot_id"]
        slot_spec = slot_specs.get(slot_id, portable_slot)
        slot_candidates = candidate_sets.get(slot_id, [])
        eligible_candidates = [
            item for item in slot_candidates
            if item.get("availability", "available") == "available" and item.get("reachable", True)
        ]
        for item in slot_candidates:
            if item not in eligible_candidates:
                rejected_candidates.append({
                    "slot_id": slot_id,
                    "entity_ref": item.get("entity_ref"),
                    "reason": "unavailable" if item.get("availability") != "available" else "unreachable",
                })
        if len(eligible_candidates) == 1:
            bound_target = eligible_candidates[0].get("entity_ref")
            binding_selection = "unique_eligible_candidate"
        elif len(eligible_candidates) > 1:
            bound_target = None
            binding_selection = "ambiguous_candidates_require_confirmation"
            ambiguous_bindings.append({
                "step": step,
                "slot_id": slot_id,
                "candidate_refs": [item.get("entity_ref") for item in eligible_candidates],
                "recommended_action": "request_human_confirmation",
            })
        else:
            bound_target = None if slot_candidates else current_space_slots.get(slot_id)
            binding_selection = "all_candidates_filtered_out" if slot_candidates else ("declared_default_candidate" if bound_target else "no_candidate")
        binding: dict[str, Any] = {
            "step": step,
            "contract_slot": slot_spec,
            "capability": meta.get("capability"),
            "requires_facts": meta.get("requires_facts", []),
            "produces_fact": meta.get("produces_fact"),
            "destroys_facts": meta.get("destroys_facts", []),
            "binding_selection": binding_selection,
            "eligible_candidate_refs": [item.get("entity_ref") for item in eligible_candidates],
        }
        if slot_spec.get("entity_kind") == "semantic_region":
            if bound_target in regions:
                binding["space_binding"] = {
                    "binding_type": "semantic_region",
                    "slot_id": slot_id,
                    "target_ref": bound_target,
                    "region_type": regions[bound_target].get("region_type"),
                    "mapping_method": "typed_invariant_slot_to_current_space_semantics",
                }
            else:
                missing_targets.append({"step": step, "target_type": "semantic_region", "target_slot": slot_id})
        elif slot_spec.get("entity_kind") == "interactive_object":
            if bound_target in objects:
                binding["object_binding"] = {
                    "binding_type": "interactive_object",
                    "slot_id": slot_id,
                    "target_ref": bound_target,
                    "region_ref": objects[bound_target].get("region_ref"),
                    "mapping_method": "typed_invariant_slot_to_object_affordance",
                }
            else:
                missing_targets.append({"step": step, "target_type": "object", "target_slot": slot_id})
        if meta.get("capability"):
            binding["capability_binding"] = {
                "required_capability": meta["capability"],
                "supported": meta["capability"] in set(body_capability_profile.get("supported_actions", [])),
                "profile_ref": body_capability_profile.get("executor_id"),
            }
        if meta.get("produces_fact"):
            binding["termination_verification"] = {
                "fact": meta["produces_fact"],
                "verification_basis": ["runtime_world_state", "execution_loop_feedback", "human_confirmation_if_needed"],
            }
        step_bindings.append(binding)
    return {
        "binding_candidate_id": candidate_id,
        "generation_basis": [
            "experience_invariant_contract",
            "current_space_semantic_data",
            "body_capability_profile",
            "runtime_world_state_snapshot",
        ],
        "step_bindings": step_bindings,
        "missing_targets": missing_targets,
        "ambiguous_bindings": ambiguous_bindings,
        "rejected_candidates": rejected_candidates,
        "invariant_contract_ref": {
            "storage_policy": contract.get("storage_policy"),
            "binding_slot_ids": [item.get("slot_id") for item in contract.get("binding_slots", [])],
            "source_bindings_used_as_normative": False,
        },
        "runtime_world_state_snapshot_id": runtime_world_state.get("runtime_world_state_snapshot_id"),
    }


def build_execution_feasibility(
    intent: dict[str, Any],
    binding_candidate: dict[str, Any],
    runtime_world_state: dict[str, Any],
    body_capability_profile: dict[str, Any],
) -> dict[str, Any]:
    if intent.get("decision") != "executable":
        return {
            "result": "requires_supplemental_teaching",
            "executable": False,
            "infeasible_reasons": [{"reason": intent.get("reason", "unsupported_intent"), "source": "intent_translation"}],
            "recommended_actions": ["trigger_supplemental_teaching", "search_alternative_experience", "terminate_execution"],
            "executable_steps": [],
            "blocked_steps": [],
        }
    supported_actions = set(body_capability_profile.get("supported_actions", []))
    facts = set(runtime_world_state.get("established_facts", []))
    missing_capabilities: list[dict[str, Any]] = []
    missing_facts: list[dict[str, Any]] = []
    executable_steps: list[str] = []
    blocked_steps: list[str] = []
    dynamic_blockers = build_dynamic_environment_blockers(runtime_world_state, get_process_chain_for_intent(intent))
    dynamic_blocked_steps = {item.get("step") for item in dynamic_blockers if item.get("step")}
    preference_constraints = evaluate_preference_constraints(intent, binding_candidate, runtime_world_state)
    preference_blockers = preference_constraints.get("blocking_reasons", [])
    preference_blocked_steps = {item.get("step") for item in preference_blockers if item.get("step")}
    for binding in binding_candidate.get("step_bindings", []):
        step = binding["step"]
        capability = binding.get("capability")
        step_missing_facts = [fact for fact in binding.get("requires_facts", []) if fact not in facts]
        if capability and capability not in supported_actions:
            missing_capabilities.append({"step": step, "capability": capability})
        if step_missing_facts:
            missing_facts.append({"step": step, "missing_facts": step_missing_facts})
        if step in dynamic_blocked_steps or step in preference_blocked_steps or step_missing_facts or (capability and capability not in supported_actions):
            blocked_steps.append(step)
            continue
        executable_steps.append(step)
        for destroyed in binding.get("destroys_facts", []):
            facts.discard(destroyed)
        produced = binding.get("produces_fact")
        if produced:
            facts.add(produced)
    reasons: list[dict[str, Any]] = []
    for item in binding_candidate.get("missing_targets", []):
        reasons.append({"reason": "missing_binding_target", **item})
    for item in binding_candidate.get("ambiguous_bindings", []):
        reasons.append({"reason": "ambiguous_binding_requires_confirmation", **item})
    for item in missing_capabilities:
        reasons.append({"reason": "missing_body_capability", **item})
    for item in missing_facts:
        reasons.append({"reason": "missing_prerequisite_fact", **item})
    reasons.extend(dynamic_blockers)
    reasons.extend(preference_blockers)
    for item in runtime_world_state.get("runtime_conflicts", []):
        reasons.append({"reason": "runtime_fact_conflict", **item})
    if not reasons:
        result = "executable"
        recommended_actions = ["dispatch_to_execution_loop"]
    elif runtime_world_state.get("runtime_conflicts") or binding_candidate.get("ambiguous_bindings"):
        result = "requires_human_confirmation"
        recommended_actions = ["request_human_confirmation", "trigger_readaptation", "search_alternative_experience", "terminate_execution"]
    elif executable_steps:
        result = "partially_inexecutable"
        recommended_actions = ["downgrade_executable_steps", "request_human_confirmation", "search_alternative_experience"]
    else:
        result = "infeasible"
        recommended_actions = ["request_human_confirmation", "search_alternative_experience", "trigger_supplemental_teaching", "terminate_execution"]
    return {
        "result": result,
        "executable": result == "executable",
        "infeasible_reasons": reasons,
        "recommended_actions": recommended_actions,
        "executable_steps": executable_steps,
        "blocked_steps": blocked_steps,
        "fact_projection_after_executable_steps": sorted(facts),
        "preference_advisories": preference_constraints.get("advisory_items", []),
    }


def build_experience_gap_record(
    migration_task_id: str,
    intent: dict[str, Any],
    binding_candidate: dict[str, Any],
    feasibility: dict[str, Any],
) -> dict[str, Any] | None:
    if feasibility.get("result") == "executable":
        return None
    seed = "|".join(
        [
            migration_task_id,
            feasibility.get("result", "unknown"),
            ",".join(feasibility.get("blocked_steps", [])),
        ]
    )
    gap_record_id = "gap_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    blocked_steps = feasibility.get("blocked_steps", [])
    executable_steps = feasibility.get("executable_steps", [])
    return {
        "schema_version": "1.0.0",
        "gap_record_id": gap_record_id,
        "migration_task_id": migration_task_id,
        "runtime_world_state_snapshot_id": binding_candidate.get("runtime_world_state_snapshot_id"),
        "target_causal_fact": intent.get("goal_fact"),
        "gap_type": feasibility.get("result"),
        "infeasible_reasons": feasibility.get("infeasible_reasons", []),
        "preference_refs": sorted(
            {
                item.get("preference_id")
                for item in feasibility.get("infeasible_reasons", [])
                if item.get("reason") == "human_preference_blocked_step" and item.get("preference_id")
            }
        ),
        "blocked_steps": blocked_steps,
        "executable_steps": executable_steps,
        "recommended_actions": feasibility.get("recommended_actions", []),
        "teaching_request": {
            "endpoint": "POST /experience/teach",
            "reason": "supplement missing process, capability, binding, or verification evidence",
            "candidate_process_chain": get_process_chain_for_intent(intent),
        },
        "alternative_experience_query": {
            "goal_fact": intent.get("goal_fact"),
            "missing_capabilities": [
                item.get("capability")
                for item in feasibility.get("infeasible_reasons", [])
                if item.get("reason") == "missing_body_capability"
            ],
            "missing_targets": [
                item.get("target_ref")
                for item in feasibility.get("infeasible_reasons", [])
                if item.get("reason") == "missing_binding_target"
            ],
        },
        "downgrade_execution_plan": {
            "enabled": bool(executable_steps and blocked_steps),
            "steps": executable_steps,
        },
    }


def build_execution_loop_payload(
    migration_task_id: str,
    intent: dict[str, Any],
    binding_candidate: dict[str, Any],
    feasibility: dict[str, Any],
) -> dict[str, Any] | None:
    if feasibility.get("result") not in {"executable", "partially_inexecutable"}:
        return None
    steps = feasibility.get("executable_steps") or get_process_chain_for_intent(intent)
    return {
        "execution_callback_id": "exec_" + migration_task_id.removeprefix("migration_"),
        "execution_loop_type": "open_execution_loop",
        "target_causal_fact": intent.get("goal_fact"),
        "runtime_world_state_snapshot_id": binding_candidate.get("runtime_world_state_snapshot_id"),
        "execution_step_payload": [
            {
                "step": step,
                "display_name": STEP_LIBRARY.get(step, {}).get("display_name"),
                "capability": STEP_LIBRARY.get(step, {}).get("capability"),
            }
            for step in steps
        ],
        "binding_candidate_payload": binding_candidate,
        "execution_constraints": {
            "must_return_fact_status": True,
            "allowed_feedback": [
                "fact_established",
                "fact_not_established",
                "failure",
                "conflict",
                "recovered",
                "human_confirmation",
            ],
        },
    }


def build_stepwise_readaptation(
    task_id: str,
    target_causal_fact: str | None,
    remaining_steps: list[str],
    runtime_world_state: dict[str, Any],
    body_capability_profile: dict[str, Any],
) -> dict[str, Any]:
    cognitive_model = get_cognitive_model()
    intent = {
        "decision": "executable",
        "task_type": "runtime_readaptation",
        "goal_fact": target_causal_fact,
        "candidate_process_chain": remaining_steps,
    }
    binding_candidate = build_binding_candidates(intent, cognitive_model, runtime_world_state, body_capability_profile)
    feasibility = build_execution_feasibility(intent, binding_candidate, runtime_world_state, body_capability_profile)
    readaptation_seed = "|".join(
        [
            task_id,
            ",".join(remaining_steps),
            runtime_world_state.get("runtime_world_state_snapshot_id", "none"),
            json.dumps(feasibility.get("infeasible_reasons", []), ensure_ascii=False, sort_keys=True),
        ]
    )
    readaptation_id = "readapt_" + hashlib.sha1(readaptation_seed.encode("utf-8")).hexdigest()[:12]
    gap_record = build_experience_gap_record(readaptation_id, intent, binding_candidate, feasibility)
    if gap_record:
        EXPERIENCE_GAP_STORE[gap_record["gap_record_id"]] = gap_record
    record = {
        "schema_version": "1.0.0",
        "readaptation_id": readaptation_id,
        "source_task_id": task_id,
        "trigger": "step_preflight_blocked",
        "remaining_steps": remaining_steps,
        "runtime_world_state_snapshot": clone_runtime_world_state(runtime_world_state),
        "binding_candidate": binding_candidate,
        "execution_feasibility": feasibility,
        "experience_gap_record": gap_record,
        "recommended_next_steps": feasibility.get("recommended_actions", []),
    }
    READAPTATION_STORE[readaptation_id] = record
    return record


def migrate_experience(
    utterance: str = "到水源处接一杯水",
    body_capability_profile: dict[str, Any] | None = None,
    space_id: str | None = None,
) -> dict[str, Any]:
    intent = translate_intent(utterance)
    cognitive_model = get_cognitive_model(space_id)
    migration_task_id = build_migration_task_id(utterance, intent)
    runtime_world_state = build_initial_runtime_world_state(cognitive_model, {**intent, "experience_id": migration_task_id})
    runtime_world_state["migration_task_id"] = migration_task_id
    runtime_world_state["runtime_world_state_snapshot_id"] = migration_task_id + "_snapshot"
    runtime_world_state["audit_record_id"] = "audit_" + migration_task_id.removeprefix("migration_")
    profile = body_capability_profile or build_default_body_capability_profile()
    chain = get_process_chain_for_intent(intent)
    matching_experience = next(
        (item for item in load_experience_library().get("experiences", []) if item.get("experience_id") == intent.get("experience_id")),
        None,
    )
    invariant_contract = (matching_experience or {}).get("invariant_contract") or build_invariant_contract(chain)
    binding_candidate = build_binding_candidates(intent, cognitive_model, runtime_world_state, profile, invariant_contract)
    feasibility = build_execution_feasibility(intent, binding_candidate, runtime_world_state, profile)
    execution_payload = build_execution_loop_payload(migration_task_id, intent, binding_candidate, feasibility)
    gap_record = build_experience_gap_record(migration_task_id, intent, binding_candidate, feasibility)
    if gap_record:
        EXPERIENCE_GAP_STORE[gap_record["gap_record_id"]] = gap_record
    RUNTIME_WORLD_STATE_STORE[migration_task_id] = runtime_world_state
    STATE_STORE[migration_task_id] = {
        "schema_version": "1.0.0",
        "task_id": migration_task_id,
        "current_stage_id": None,
        "runtime_state": "migration_adapted",
        "runtime_world_state": runtime_world_state,
        "goal_fact": intent.get("goal_fact"),
        "candidate_process_chain": get_process_chain_for_intent(intent),
        "execution_feasibility": feasibility,
        "body_capability_profile": profile,
        "experience_gap_record_id": gap_record.get("gap_record_id") if gap_record else None,
        "space_id": cognitive_model.get("local_environment_summary", {}).get("space_id"),
        "experience_invariant_contract": invariant_contract,
        "binding_candidate": binding_candidate,
    }
    AUDIT_STORE[runtime_world_state["audit_record_id"]] = {
        "schema_version": "1.0.0",
        "audit_record_id": runtime_world_state["audit_record_id"],
        "migration_task_id": migration_task_id,
        "runtime_world_state_snapshot_id": runtime_world_state["runtime_world_state_snapshot_id"],
        "binding_candidate_id": binding_candidate["binding_candidate_id"],
        "execution_callback_id": execution_payload.get("execution_callback_id") if execution_payload else None,
        "experience_gap_record_id": gap_record.get("gap_record_id") if gap_record else None,
        "outcome": feasibility["result"],
        "release_status": runtime_world_state["release_status"],
    }
    return {
        "schema_version": "1.0.0",
        "migration_task_id": migration_task_id,
        "intent_translation": intent,
        "current_space_semantic_data": build_space_context(cognitive_model),
        "experience_invariant_contract": invariant_contract,
        "body_capability_profile": profile,
        "runtime_world_state_snapshot": runtime_world_state,
        "binding_candidate": binding_candidate,
        "execution_feasibility": feasibility,
        "experience_gap_record": gap_record,
        "execution_loop_payload": execution_payload,
        "audit_record_id": runtime_world_state["audit_record_id"],
    }


def get_runtime_world_state(task_id: str) -> dict[str, Any]:
    state = RUNTIME_WORLD_STATE_STORE.get(task_id)
    if not state:
        stage_state = STATE_STORE.get(task_id, {})
        state = stage_state.get("runtime_world_state")
    if not state:
        return {"error": "runtime_world_state_not_found", "task_id": task_id}
    return {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "runtime_world_state_snapshot": state,
        "release_status": state.get("release_status", "unknown"),
        "release_token": state.get("release_token"),
        "audit_record_id": state.get("audit_record_id"),
    }


def parse_runtime_query(question: str) -> dict[str, Any]:
    return resolve_runtime_state_query(
        question,
        normalize_text_fn=normalize_text,
        extract_object_constraints_fn=extract_object_constraints,
        cognitive_model=get_cognitive_model(),
    )


def query_runtime_world_state(
    task_id: str,
    question: str = "当前杯子有没有水",
    object_ref: str = "object_cup_white_mug",
) -> dict[str, Any]:
    current = get_runtime_world_state(task_id)
    if "error" in current:
        return current
    state = current["runtime_world_state_snapshot"]
    if state.get("release_status") == "released":
        return build_released_runtime_query_result(task_id, question)

    query = parse_runtime_query(question)
    if query["query_type"] == "unsupported":
        return build_unsupported_runtime_query_result(task_id, question, query)

    return build_runtime_state_query_result(
        task_id,
        question,
        state,
        query,
        build_runtime_explanation_view_fn=build_runtime_explanation_view,
    )


def build_runtime_explanation_view(task_id: str) -> dict[str, Any]:
    current = get_runtime_world_state(task_id)
    if "error" in current:
        return current
    snapshot = current["runtime_world_state_snapshot"]
    stage_state = STATE_STORE.get(task_id, {})
    audit = AUDIT_STORE.get(task_id, {})
    trace = TRACE_STORE.get(task_id, {})
    runtime_environment = snapshot.get("runtime_environment", {})
    current_stage = snapshot.get("current_stage") or stage_state.get("current_stage_id")
    completed_stages = snapshot.get("completed_stages", [])
    established_facts = snapshot.get("established_facts", [])
    runtime_state = stage_state.get("runtime_state") or audit.get("outcome") or "unknown"
    goal_fact = infer_goal_fact_from_task_state(task_id, stage_state, audit)
    available_now, blocked_now = build_llm_action_candidates(snapshot)
    planned_chain = []
    if task_id.startswith("migration_"):
        migration_state = STATE_STORE.get(task_id, {})
        planned_chain = list(migration_state.get("candidate_process_chain", []))
        if not planned_chain:
            feasibility = migration_state.get("execution_feasibility", {})
            if feasibility.get("executable_steps"):
                planned_chain = list(feasibility.get("executable_steps", []))
            elif feasibility.get("blocked_steps"):
                planned_chain = list(feasibility.get("executable_steps", [])) + list(feasibility.get("blocked_steps", []))
    elif audit.get("process_instance_id"):
        intent_chain = TRACE_STORE.get(task_id, {}).get("causal_plan", {})
        if intent_chain and intent_chain.get("process_chain"):
            planned_chain = list(intent_chain.get("process_chain", []))
    last_feedback = snapshot.get("last_execution_fact_feedback", [])
    gap_record_id = stage_state.get("experience_gap_record_id")
    gap_record = EXPERIENCE_GAP_STORE.get(gap_record_id) if gap_record_id else None
    current_action = current_stage or runtime_state

    next_step = None
    next_step_reason = None
    if runtime_state in {"readaptation_required", "awaiting_teaching_or_confirmation"}:
        blocked_step = runtime_environment.get("last_blocked_step")
        next_step = blocked_step or (gap_record.get("blocked_step") if gap_record else None)
        next_step_reason = "当前主链受阻，下一步需先处理缺口或重新适配"
    elif planned_chain:
        next_step = next((step for step in planned_chain if step not in completed_stages), None)
        if next_step:
            next_step_reason = "优先沿当前任务已绑定的过程链选择尚未完成的下一步"
        elif goal_fact and goal_fact in established_facts:
            next_step_reason = "当前目标已达成，等待新的任务指令"
    elif available_now:
        next_step = available_now[0].get("step")
        next_step_reason = "基于当前任务期运行时世界状态快照，该步骤当前满足前提事实"
    elif blocked_now:
        next_step = blocked_now[0].get("step")
        next_step_reason = "存在候选步骤，但仍缺少前提事实"
    elif goal_fact and goal_fact in established_facts:
        next_step_reason = "当前目标已达成，等待新的任务指令"


    display_next_step = next_step
    if display_next_step is None and next_step_reason and "目标已达成" in next_step_reason:
        display_next_step = "none"

    explanation_id = "runtime_explain_" + hashlib.sha1(
        "|".join([task_id, snapshot.get("runtime_world_state_snapshot_id", "none"), runtime_state]).encode("utf-8")
    ).hexdigest()[:12]
    return {
        "schema_version": "1.0.0",
        "explanation_view_id": explanation_id,
        "task_id": task_id,
        "source_policy": "runtime_world_state_snapshot_and_current_runtime_context_only",
        "time_layers": {
            "immediate_state": {
                "current_action": current_action,
                "runtime_state": runtime_state,
                "last_blocked_step": runtime_environment.get("last_blocked_step"),
                "last_route_adjustment": runtime_environment.get("last_route_adjustment"),
            },
            "task_state": {
                "goal_fact": goal_fact,
                "current_stage": current_stage,
                "completed_stages": completed_stages,
                "next_step": next_step,
                "next_step_reason": next_step_reason,
            },
            "session_state": {
                "active_preferences": snapshot.get("active_preferences", []),
                "audit_outcome": audit.get("outcome"),
                "experience_gap_record_id": gap_record_id,
                "recovery_record_ids": stage_state.get("recovery_record_ids", []),
            },
        },
        "status_answers": {
            "current_action": {
                "answer": current_action or "unknown",
                "reason": "来自当前任务期运行时世界状态快照中的 current_stage 与运行时状态",
            },
            "next_step": {
                "answer": display_next_step or "unknown",
                "reason": next_step_reason or "当前没有足够上下文判断下一步",
            },
            "goal_fact": {
                "answer": goal_fact or "unknown",
                "reason": "来自任务上下文与审计/状态推断出的目标因果事实",
            },
        },
        "evidence": {
            "runtime_world_state_snapshot_id": snapshot.get("runtime_world_state_snapshot_id"),
            "current_stage": current_stage,
            "completed_stages": completed_stages,
            "established_facts": established_facts,
            "available_actions_now": available_now,
            "blocked_actions": blocked_now,
            "planned_process_chain": planned_chain,
            "last_execution_fact_feedback": last_feedback,
            "experience_gap_record": gap_record,
        },
    }


def classify_execution_block_source(reason: str | None) -> str:
    normalized = normalize_text(reason or "")
    if any(token in normalized for token in ["preference", "forbid", "blockedstep", "missingrequiredcapability", "missingfact", "steppreflightblocked", "runtimefactconflict"]):
        return "capability_failure"
    if any(token in normalized for token in ["risk", "permission", "governance", "policy", "权限", "治理", "保护策略", "高风险"]):
        return "governance_failure"
    if any(token in normalized for token in ["semantic", "unknown", "clarification", "unsupported"]):
        return "semantic_failure"
    return "capability_failure"


def build_clarification_prompt(semantic_request: dict[str, Any], concept_resolution: dict[str, Any] | None = None) -> str:
    reason = semantic_request.get("clarification_reason")
    if reason == "deictic_object_without_shared_reference":
        return "我还不能确定你说的是哪个对象，请补充颜色、位置或名称。"
    if reason == "direction_reference_not_grounded":
        return "我还不能把方位描述绑定到当前空间参照，请补充更明确的位置或对象特征。"
    if reason == "ambiguous_action_phrase":
        return "我理解到你想让我处理一件事，但动作还不够明确，请直接说出要做的动作。"
    if reason == "teaching_step_not_parsed":
        return "我知道你在教我，但这次还没解析出明确步骤，请再具体说一步。"
    if reason == "no_process_or_concept_match":
        concepts = concept_resolution.get("resolved_concepts", []) if concept_resolution else []
        if concepts:
            return "我只匹配到概念层候选，还缺少足够过程信息，请补充你希望我先做哪一步。"
        return "我还没把这句话稳定映射到任务链，请补充对象、位置或顺序信息。"
    return "我需要你再说明一下任务对象、位置或顺序约束，才能继续判断。"


def build_teaching_acknowledgement(utterance: str, parsed_steps: list[str], semantic_request: dict[str, Any]) -> str:
    if semantic_request.get("clarification_needed"):
        return build_clarification_prompt(semantic_request)
    teaching_frame = ((semantic_request.get("teaching_plan") or {}).get("teaching_frame")) or {}
    flexibility_mode = (teaching_frame.get("flexibility_policy") or {}).get("mode")
    preference_constraints = teaching_frame.get("preference_constraints", [])
    if parsed_steps:
        display_steps = [STEP_LIBRARY.get(step, {}).get("display_name", step) for step in parsed_steps]
        suffix = ""
        if flexibility_mode == "allow_local_reorder":
            suffix = "；你允许我在不破坏结果的前提下做局部变通"
        elif flexibility_mode == "strict_following":
            suffix = "；我会优先严格按这个顺序执行"
        elif preference_constraints:
            suffix = "；我还记录到了本轮教学中的偏好约束"
        return "我理解你这次在教我按这个顺序做：" + " -> ".join(display_steps) + suffix
    goal_fact = semantic_request.get("intent_frame", {}).get("goal_fact")
    if goal_fact:
        return f"我理解你在教我达成目标事实 {goal_fact}，但还缺少更具体的步骤。"
    return "我知道你在教我，但还需要更明确的步骤描述。"


def build_llm_action_candidates(state: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    established_facts = set(state.get("established_facts", []))
    executable_now: list[dict[str, Any]] = []
    needs_preconditions: list[dict[str, Any]] = []
    for step_id, meta in STEP_LIBRARY.items():
        missing_facts = [fact for fact in meta.get("requires_facts", []) if fact not in established_facts]
        item = {
            "step": step_id,
            "display_name": meta.get("display_name"),
            "capability": meta.get("capability"),
            "requires_facts": meta.get("requires_facts", []),
            "missing_facts": missing_facts,
            "produces_fact": meta.get("produces_fact"),
            "destroys_facts": meta.get("destroys_facts", []),
            "target_region": meta.get("target_region"),
            "target_object": meta.get("target_object"),
        }
        if missing_facts:
            needs_preconditions.append(item)
        else:
            executable_now.append(item)
    return executable_now, needs_preconditions


def infer_goal_fact_from_task_state(task_id: str, state: dict[str, Any], audit: dict[str, Any]) -> str | None:
    if state.get("goal_fact"):
        return state["goal_fact"]
    feasibility = state.get("execution_feasibility") or {}
    if feasibility.get("target_causal_fact"):
        return feasibility.get("target_causal_fact")
    causal_plan = audit.get("causal_plan", {})
    if causal_plan.get("goal_fact"):
        return causal_plan.get("goal_fact")
    task_ref = state.get("runtime_world_state", {}).get("task_ref") or state.get("task_ref")
    if isinstance(task_ref, str):
        return infer_goal_fact(task_ref)
    return infer_goal_fact(task_id)


def build_llm_context_view(task_id: str) -> dict[str, Any]:
    current = get_runtime_world_state(task_id)
    if "error" in current:
        return current
    snapshot = current["runtime_world_state_snapshot"]
    stage_state = STATE_STORE.get(task_id, {})
    audit = AUDIT_STORE.get(task_id, {})
    context_view_id = "llm_ctx_" + hashlib.sha1(
        "|".join([task_id, snapshot.get("runtime_world_state_snapshot_id", "none"), snapshot.get("release_status", "unknown")]).encode("utf-8")
    ).hexdigest()[:12]
    if snapshot.get("release_status") == "released":
        return {
            "schema_version": "1.0.0",
            "context_view_id": context_view_id,
            "task_id": task_id,
            "usable_as_current_world_state": False,
            "context_status": "snapshot_released",
            "source_policy": "runtime_world_state_snapshot_only",
            "reason": "任务期运行时世界状态快照已释放，不能再作为当前世界状态提供给模型",
            "snapshot_ref": {
                "runtime_world_state_snapshot_id": snapshot.get("runtime_world_state_snapshot_id"),
                "snapshot_lifecycle_state": snapshot.get("snapshot_lifecycle_state"),
                "release_status": snapshot.get("release_status"),
                "release_token": snapshot.get("release_token"),
            },
            "model_role_constraints": {
                "must_not_assume_unobserved_facts": True,
                "direct_execution_allowed": False,
                "must_reenter_deterministic_validator": True,
            },
        }

    executable_now, needs_preconditions = build_llm_action_candidates(snapshot)
    objects = [
        {
            "object_ref": object_ref,
            "location_type": item.get("location_type"),
            "location_ref": item.get("location_ref"),
            "state_facts": item.get("state_facts", []),
        }
        for object_ref, item in snapshot.get("object_locations", {}).items()
    ]
    return {
        "schema_version": "1.0.0",
        "context_view_id": context_view_id,
        "task_id": task_id,
        "usable_as_current_world_state": True,
        "context_status": "active_snapshot",
        "source_policy": "runtime_world_state_snapshot_only",
        "task_context": {
            "runtime_state": stage_state.get("runtime_state"),
            "goal_fact": infer_goal_fact_from_task_state(task_id, stage_state, audit),
            "current_stage": snapshot.get("current_stage"),
            "completed_stages": snapshot.get("completed_stages", []),
            "snapshot_lifecycle_state": snapshot.get("snapshot_lifecycle_state"),
            "runtime_world_state_snapshot_id": snapshot.get("runtime_world_state_snapshot_id"),
        },
        "executor": snapshot.get("executor", {}),
        "objects": objects,
        "established_facts": snapshot.get("established_facts", []),
        "active_preferences": snapshot.get("active_preferences", []),
        "runtime_environment": snapshot.get("runtime_environment", {}),
        "available_actions_now": executable_now,
        "blocked_actions": needs_preconditions,
        "model_role_constraints": {
            "must_not_assume_unobserved_facts": True,
            "must_not_write_runtime_facts": True,
            "must_not_generate_low_level_control": True,
            "direct_execution_allowed": False,
            "must_reenter_deterministic_validator": True,
            "required_handoff": "candidate_output_must_be_validated_then_reenter_orchestration_layer",
        },
    }


def collect_concept_evidence_packets(
    resolved_concepts: list[dict[str, Any]],
    action_concepts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    for item in [*resolved_concepts, *action_concepts]:
        packet = item.get("concept_evidence")
        if packet:
            packets.append(packet)
    return packets


def attach_missing_fact_experience_candidates(action_concepts: list[dict[str, Any]]) -> None:
    registry = build_process_registry()
    experiences = load_experience_library().get("experiences", [])
    for concept in action_concepts:
        package = concept.get("concept_package", {})
        missing = package.get("fact_alignment", {}).get("missing_requirements", [])
        candidates: list[dict[str, Any]] = []
        for fact in missing:
            for step_id, meta in registry.items():
                if meta.get("produces_fact") != fact:
                    continue
                candidates.append({
                    "candidate_type": "process_producer",
                    "candidate_id": step_id,
                    "covers_missing_facts": [fact],
                    "process_chain": meta.get("expands_to") or [step_id],
                    "source": meta.get("source", "step_library"),
                })
            for experience in experiences:
                reasoning = experience.get("causal_signature", {}).get("reasoning", [])
                covered = [item.get("produces_fact") for item in reasoning if item.get("produces_fact") == fact]
                if not covered:
                    continue
                candidates.append({
                    "candidate_type": "experience_chain",
                    "candidate_id": experience.get("experience_id"),
                    "covers_missing_facts": covered,
                    "process_chain": experience.get("process_chain", []),
                    "source": "experience_library",
                })
        deduplicated: dict[tuple[str, tuple[str, ...], tuple[str, ...]], dict[str, Any]] = {}
        for candidate in candidates:
            key = (
                candidate["candidate_type"],
                tuple(sorted(candidate["covers_missing_facts"])),
                tuple(candidate.get("process_chain", [])),
            )
            existing = deduplicated.get(key)
            if existing:
                existing["covers_missing_facts"] = sorted(set(existing["covers_missing_facts"] + candidate["covers_missing_facts"]))
                existing.setdefault("equivalent_candidate_ids", []).append(candidate["candidate_id"])
            else:
                deduplicated[key] = candidate
        ranked = sorted(
            deduplicated.values(),
            key=lambda item: (
                -len(item["covers_missing_facts"]),
                len(item.get("process_chain", [])),
                0 if item["source"] == "step_library" else 1,
                str(item["candidate_id"]),
            ),
        )
        package.setdefault("experience_lookup", {})["candidates"] = ranked[:5]
        package["experience_lookup"]["selection_basis"] = "missing_fact_producer_coverage"
        package["experience_lookup"]["whole_utterance_match_used"] = False


def build_concept_grounding_gate(concept_resolution: dict[str, Any] | None) -> dict[str, Any]:
    blocked: list[dict[str, Any]] = []
    for concept in (concept_resolution or {}).get("action_concepts", []):
        summary = concept.get("concept_package", {}).get("grounding_summary", {})
        if not summary.get("clarification_required"):
            continue
        blocked.append({
            "concept_id": concept.get("concept_id"),
            "display_name": concept.get("display_name"),
            "unresolved_roles": summary.get("unresolved_roles", []),
            "clarification_questions": summary.get("clarification_questions", []),
        })
    questions = [question for item in blocked for question in item["clarification_questions"]]
    return {
        "gate_status": "blocked" if blocked else "passed",
        "clarification_required": bool(blocked),
        "blocked_concepts": blocked,
        "clarification_questions": questions,
        "direct_execution_allowed": False,
        "must_reenter_orchestration_layer": True,
    }


def build_generalization_result_record(
    task_id: str,
    binding_candidate: dict[str, Any],
    profile: dict[str, Any],
    runtime_world_state: dict[str, Any],
    outcome: str,
    target_fact: str | None,
) -> dict[str, Any]:
    state_meta = STATE_STORE.get(task_id, {})
    record_id = "generalization_" + hashlib.sha1(
        "|".join([task_id, str(state_meta.get("space_id")), str(profile.get("executor_id")), outcome]).encode("utf-8")
    ).hexdigest()[:12]
    record = {
        "schema_version": "1.0.0",
        "generalization_result_id": record_id,
        "migration_task_id": task_id,
        "space_id": state_meta.get("space_id"),
        "executor_id": profile.get("executor_id"),
        "executor_type": profile.get("executor_type") or profile.get("body_profile"),
        "binding_candidate_id": binding_candidate.get("binding_candidate_id"),
        "resolved_bindings": [
            {
                "step": item.get("step"),
                "slot_id": item.get("contract_slot", {}).get("slot_id"),
                "entity_ref": item.get("space_binding", {}).get("target_ref") or item.get("object_binding", {}).get("target_ref"),
                "selection": item.get("binding_selection"),
            }
            for item in binding_candidate.get("step_bindings", [])
        ],
        "rejected_candidates": binding_candidate.get("rejected_candidates", []),
        "ambiguous_bindings": binding_candidate.get("ambiguous_bindings", []),
        "outcome": outcome,
        "target_fact": target_fact,
        "target_fact_established": bool(target_fact and target_fact in set(runtime_world_state.get("established_facts", []))),
        "public_experience_update_policy": "record_validation_history_only_no_single_run_contract_rewrite",
    }
    GENERALIZATION_RESULT_STORE[record_id] = record
    return record


def build_concept_evidence_summary(evidence_packets: list[dict[str, Any]]) -> dict[str, Any]:
    direct_execution_allowed = any(
        packet.get("fallback_policy", {}).get("direct_execution_allowed")
        for packet in evidence_packets
    )
    return {
        "evidence_packet_count": len(evidence_packets),
        "local_concept_ids": [packet.get("concept_id") for packet in evidence_packets],
        "all_candidate_only": all(packet.get("fallback_policy", {}).get("candidate_only") for packet in evidence_packets),
        "direct_execution_allowed": direct_execution_allowed,
        "must_reenter_orchestration_layer": True,
        "evidence_role": "explain_local_concept_match_and_execution_boundary",
    }


def resolve_concepts_for_intent(utterance: str, task_id: str | None = None) -> dict[str, Any]:
    cognitive_model = get_cognitive_model()
    intent_frame = build_intent_frame(utterance, cognitive_model)
    semantic_request = build_semantic_request_frame(
        utterance,
        cognitive_model,
        task_id=task_id,
        intent_frame=intent_frame,
    )
    runtime_context_view = build_llm_context_view(task_id) if task_id else None
    runtime_facts = (
        runtime_context_view.get("established_facts", [])
        if runtime_context_view and "error" not in runtime_context_view
        else sorted(build_world_state_facts(cognitive_model))
    )
    intent_frame["action_concepts"] = resolve_action_concepts(
        utterance,
        intent_frame.get("explicit_process_chain", []),
        normalize_text_fn=normalize_text,
        object_constraints=intent_frame.get("object_constraints", []),
        spatial_constraints=intent_frame.get("spatial_constraints", []),
        current_facts=runtime_facts,
        runtime_context_view=runtime_context_view if runtime_context_view and "error" not in runtime_context_view else None,
    )
    attach_missing_fact_experience_candidates(intent_frame["action_concepts"])
    concept_matches = build_concept_matches(
        utterance,
        intent_frame.get("goal_fact"),
        intent_frame.get("spatial_constraints", []),
        intent_frame.get("object_constraints", []),
        intent_frame.get("explicit_process_chain", []),
        runtime_context_view=runtime_context_view if runtime_context_view and "error" not in runtime_context_view else None,
    )
    resolution_id = "concept_resolution_" + hashlib.sha1(
        "|".join([normalize_text(utterance), task_id or "none"]).encode("utf-8")
    ).hexdigest()[:12]
    action_concepts = intent_frame.get("action_concepts", [])
    evidence_packets = collect_concept_evidence_packets(concept_matches, action_concepts)
    lifecycle = record_concept_reuse(
        CONCEPT_LIFECYCLE_STORE,
        evidence_packets,
        resolution_id=resolution_id,
        task_id=task_id,
    )
    return {
        "schema_version": "1.0.0",
        "resolution_id": resolution_id,
        "utterance": utterance,
        "task_id": task_id,
        "semantic_request": semantic_request,
        "intent_frame_summary": {
            "goal_fact": intent_frame.get("goal_fact"),
            "activation_constraint": intent_frame.get("activation_constraint"),
            "explicit_process_chain": intent_frame.get("explicit_process_chain", []),
            "action_concepts": intent_frame.get("action_concepts", []),
            "spatial_constraints": intent_frame.get("spatial_constraints", []),
            "object_constraints": intent_frame.get("object_constraints", []),
        },
        "action_concepts": action_concepts,
        "resolved_concepts": concept_matches,
        "concept_evidence_packets": evidence_packets,
        "concept_evidence_summary": build_concept_evidence_summary(evidence_packets),
        "concept_lifecycle": lifecycle,
        "runtime_context_view": runtime_context_view,
        "concept_resolution_policy": {
            "concept_layer_role": "提供可复用语义单元，不直接替代经验层、因果层或执行层",
            "direct_execution_allowed": False,
            "must_reenter_orchestration_layer": True,
            "concept_upgrade_policy": "先由示教和经验形成稳定复用模式，再抽象为概念单元",
        },
    }


def build_cloud_recall_preview(
    utterance: str,
    task_id: str | None = None,
    *,
    semantic_request: dict[str, Any] | None = None,
    concept_resolution: dict[str, Any] | None = None,
    intent_preview: dict[str, Any] | None = None,
    runtime_context_view: dict[str, Any] | None = None,
) -> dict[str, Any]:
    semantic_request = semantic_request or build_semantic_request_frame(utterance, get_cognitive_model(), task_id=task_id)
    if concept_resolution is None and semantic_request.get("request_type") in {"task_execution", "teaching"}:
        concept_resolution = resolve_concepts_for_intent(utterance, task_id=task_id)
    intent_preview = intent_preview or (
        translate_intent(utterance) if semantic_request.get("request_type") == "task_execution" else None
    )
    if runtime_context_view is None and task_id:
        runtime_context_view = build_llm_context_view(task_id)

    cloud_recall_packet = build_cloud_recall_packet(
        utterance,
        semantic_request=semantic_request,
        concept_resolution=concept_resolution,
        intent_preview=intent_preview,
        task_id=task_id,
        runtime_context_view=runtime_context_view if runtime_context_view and "error" not in runtime_context_view else None,
        normalize_text_fn=normalize_text,
    )
    should_request = bool(cloud_recall_packet.get("local_concept_gap"))
    gap_evidence = build_gap_evidence_packet(
        utterance,
        gaps=cloud_recall_packet.get("local_concept_gap", []),
        runtime_context_view=runtime_context_view if runtime_context_view and "error" not in runtime_context_view else None,
    )
    fallback_event = record_concept_fallback(
        CONCEPT_FALLBACK_STORE,
        gap_evidence,
        packet_id=cloud_recall_packet.get("packet_id", "unknown"),
        cloud_recall_requested=should_request,
    )
    if not should_request:
        return {
            "schema_version": "1.0.0",
            "should_request_cloud_recall": False,
            "cloud_recall_packet": cloud_recall_packet,
            "concept_gap_evidence": gap_evidence,
            "concept_fallback_event": fallback_event,
            "cloud_recall_result": {
                "schema_version": "1.0.0",
                "availability": "local_concepts_sufficient",
                "recall_status": "not_required",
                "candidate_concepts": [],
                "candidate_process_chain": [],
                "clarification_questions": [],
                "direct_execution_allowed": False,
                "must_reenter_orchestration_layer": True,
            },
        }

    return {
        "schema_version": "1.0.0",
        "should_request_cloud_recall": True,
        "cloud_recall_packet": cloud_recall_packet,
        "concept_gap_evidence": gap_evidence,
        "concept_fallback_event": fallback_event,
        "cloud_recall_result": request_cloud_concept_support(
            cloud_recall_packet,
            normalize_text_fn=normalize_text,
        ),
    }


def build_task_switch_context(task_id: str, utterance: str, arbitration: dict[str, Any]) -> dict[str, Any]:
    runtime_context_view = build_llm_context_view(task_id)
    task_context = runtime_context_view.get("task_context", {}) if "error" not in runtime_context_view else {}
    executor = runtime_context_view.get("executor", {}) if "error" not in runtime_context_view else {}
    local_gap = "unknown_target_or_skill_not_grounded_in_local_concepts"
    if arbitration.get("decision") == "request_human_confirmation":
        local_gap = "held_object_state_must_be_resolved_before_switching_to_unknown_task"
    return {
        "requested_utterance": utterance,
        "current_goal_fact": task_context.get("goal_fact"),
        "current_stage": task_context.get("current_stage"),
        "holding_objects": executor.get("holding", []),
        "executor_location": executor.get("location_ref"),
        "local_gap": local_gap,
        "recommended_actions": arbitration.get("required_actions", []),
        "preview_summary": "检测到新任务切换请求；当前执行体仍处于活动任务上下文中，需先结合持物状态与本地能力缺口做确认或教学。",
    }


def build_learning_followup(utterance: str, intent: dict[str, Any], cloud_recall_preview: dict[str, Any] | None) -> dict[str, Any]:
    clarification_questions = (cloud_recall_preview or {}).get("cloud_recall_result", {}).get("clarification_questions", [])
    if not clarification_questions:
        clarification_questions = ["请告诉我完成这件事需要依次做哪些关键步骤，以及最终什么状态表示任务完成。"]
    return {
        "status": "unable_but_teachable",
        "utterance": utterance,
        "unable_reason": intent.get("reason") or "当前端侧没有能够达成该目标的动作概念或经验",
        "gap_type": "local_action_concept_or_experience_missing",
        "questions_for_human": clarification_questions,
        "recommended_next_actions": [
            {"action": "dialogue_teaching", "endpoint": "/experience/dialogue-teach"},
            {"action": "stepwise_teaching", "endpoint": "/teaching/session/start"},
        ],
        "experience_after_teaching": True,
        "direct_execution_allowed": False,
    }


def build_llm_prompt_contract(utterance: str, task_id: str | None = None) -> dict[str, Any]:
    semantic_request = build_semantic_request_frame(utterance, get_cognitive_model(), task_id=task_id)
    intent_preview = translate_intent(utterance)
    concept_resolution = resolve_concepts_for_intent(utterance, task_id=task_id)
    runtime_context_view = concept_resolution.get("runtime_context_view") if task_id else None
    cloud_recall_preview = build_cloud_recall_preview(
        utterance,
        task_id=task_id,
        semantic_request=semantic_request,
        concept_resolution=concept_resolution,
        intent_preview=intent_preview,
        runtime_context_view=runtime_context_view,
    )
    prompt_contract_id = "llm_prompt_" + hashlib.sha1(
        "|".join([normalize_text(utterance), task_id or "none"]).encode("utf-8")
    ).hexdigest()[:12]
    return {
        "schema_version": "1.0.0",
        "prompt_contract_id": prompt_contract_id,
        "contract_version": "rell_llm_semantic_bridge_v1",
        "utterance": utterance,
        "task_id": task_id,
        "role_definition": {
            "model_role": "仅负责长程或陌生任务的语义理解、候选建议和澄清，不参与连续控制与最终执行决策",
            "execution_boundary": "最终执行必须回到空间语义、本体能力、概念层、经验层、任务期运行时世界状态快照和编排层共同判断",
        },
        "input_packet": {
            "semantic_request": semantic_request,
            "intent_translation_preview": intent_preview,
            "concept_resolution": {
                "resolution_id": concept_resolution.get("resolution_id"),
                "resolved_concept_ids": [item.get("concept_id") for item in concept_resolution.get("resolved_concepts", [])],
                "action_concept_ids": [item.get("concept_id") for item in concept_resolution.get("action_concepts", [])],
            },
            "runtime_context_view": runtime_context_view,
            "cloud_recall_packet": cloud_recall_preview.get("cloud_recall_packet") if cloud_recall_preview.get("should_request_cloud_recall") else None,
        },
        "cloud_recall_policy": {
            "enabled_on_local_gap": True,
            "candidate_only": True,
            "direct_execution_allowed": False,
            "must_reenter_orchestration_layer": True,
        },
        "system_constraints": [
            "不得输出绝对坐标、关节角、轨迹、原始电机控制或其他底层控制字段",
            "不得写入或篡改任务期运行时世界状态快照中的事实",
            "只能输出候选语义、候选过程链或澄清内容，不能直接宣告任务已经执行成功",
            "若缺少上下文，应输出澄清或候选，不得臆造未观测事实",
        ],
        "output_contract": {
            "allowed_candidate_types": sorted(LLM_ALLOWED_CANDIDATE_TYPES),
            "forbidden_output_fields": sorted(LLM_FORBIDDEN_OUTPUT_FIELDS),
            "required_common_fields": ["candidate_type", "confidence"],
            "candidate_plan_fields": ["goal_fact", "candidate_process_chain", "references_to_facts", "confidence"],
            "clarification_fields": ["clarification_question", "answer_text", "confidence"],
            "next_endpoint": "/llm/candidate/validate",
        },
        "handoff_contract": {
            "validator_endpoint": "/llm/candidate/validate",
            "direct_execution_allowed": False,
            "must_reenter_orchestration_layer": True,
            "orchestration_owner": "space_semantics_concept_layer_causal_layer_experience_layer_runtime_world_state",
        },
    }


def build_llm_candidate_intent(utterance: str, task_id: str | None = None) -> dict[str, Any]:
    cognitive_model = get_cognitive_model()
    semantic_request = build_semantic_request_frame(utterance, cognitive_model, task_id=task_id)
    intent_preview = translate_intent(utterance)
    concept_resolution = resolve_concepts_for_intent(utterance, task_id=task_id)
    prompt_contract = build_llm_prompt_contract(utterance, task_id=task_id)
    cloud_recall_preview = build_cloud_recall_preview(
        utterance,
        task_id=task_id,
        semantic_request=semantic_request,
        concept_resolution=concept_resolution,
        intent_preview=intent_preview,
        runtime_context_view=prompt_contract.get("input_packet", {}).get("runtime_context_view"),
    )
    candidate_intent_id = "llm_candidate_" + hashlib.sha1(
        "|".join([normalize_text(utterance), task_id or "none"]).encode("utf-8")
    ).hexdigest()[:12]
    return {
        "schema_version": "1.0.0",
        "candidate_intent_id": candidate_intent_id,
        "utterance": utterance,
        "task_id": task_id,
        "semantic_request": semantic_request,
        "intent_translation_preview": intent_preview,
        "runtime_context_view": prompt_contract.get("input_packet", {}).get("runtime_context_view"),
        "concept_resolution": concept_resolution,
        "cloud_recall_preview": cloud_recall_preview,
        "llm_prompt_contract": prompt_contract,
        "llm_input_contract": {
            "model_role": prompt_contract.get("role_definition", {}).get("model_role"),
            **prompt_contract.get("output_contract", {}),
        },
        "expected_output_schema": {
            "candidate_type": "candidate_plan",
            "goal_fact": intent_preview.get("goal_fact"),
            "candidate_process_chain": intent_preview.get("candidate_process_chain", []),
            "references_to_facts": [],
            "clarification_question": None,
            "confidence": 0.0,
        },
    }


def flatten_candidate_field_paths(value: Any, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            paths.append(next_prefix)
            paths.extend(flatten_candidate_field_paths(item, next_prefix))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            next_prefix = f"{prefix}[{index}]"
            paths.extend(flatten_candidate_field_paths(item, next_prefix))
    return paths


def validate_llm_candidate_output(candidate: Any, task_id: str | None = None) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        return {
            "error": "candidate_must_be_object",
            "received_type": type(candidate).__name__,
        }
    field_paths = flatten_candidate_field_paths(candidate)
    forbidden_hits: list[str] = []
    for path in field_paths:
        normalized_parts = re.split(r"[.\[\]]+", path)
        if any(part in LLM_FORBIDDEN_OUTPUT_FIELDS for part in normalized_parts if part):
            forbidden_hits.append(path)
    candidate_type = candidate.get("candidate_type")
    errors: list[str] = []
    warnings: list[str] = []
    if candidate_type not in LLM_ALLOWED_CANDIDATE_TYPES:
        errors.append(f"unsupported_candidate_type:{candidate_type}")
    if forbidden_hits:
        errors.append("forbidden_output_fields:" + ",".join(sorted(set(forbidden_hits))))

    normalized_candidate = {
        "candidate_type": candidate_type,
        "goal_fact": candidate.get("goal_fact"),
        "candidate_process_chain": candidate.get("candidate_process_chain", []),
        "references_to_facts": candidate.get("references_to_facts", []),
        "clarification_question": candidate.get("clarification_question"),
        "confidence": candidate.get("confidence"),
    }

    if candidate_type == "candidate_plan":
        chain = candidate.get("candidate_process_chain")
        if not isinstance(chain, list) or not chain:
            errors.append("candidate_plan_requires_nonempty_candidate_process_chain")
        else:
            unknown_steps = [step for step in chain if step not in STEP_LIBRARY]
            if unknown_steps:
                errors.append("unknown_process_steps:" + ",".join(unknown_steps))
    if candidate_type == "clarification_answer" and not candidate.get("clarification_question") and not candidate.get("answer_text"):
        errors.append("clarification_answer_requires_clarification_question_or_answer_text")

    if task_id:
        context_view = build_llm_context_view(task_id)
        if context_view.get("context_status") == "snapshot_released":
            warnings.append("runtime_snapshot_already_released")
        elif context_view.get("usable_as_current_world_state"):
            warnings.append("candidate_output_still_must_reenter_orchestration_layer")
            if candidate_type == "candidate_plan":
                executable_now = {item["step"] for item in context_view.get("available_actions_now", [])}
                chain = candidate.get("candidate_process_chain", [])
                if chain and chain[0] not in executable_now:
                    warnings.append(f"first_step_not_executable_now:{chain[0]}")

    validation_id = "llm_validation_" + hashlib.sha1(
        json.dumps(candidate, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    return {
        "schema_version": "1.0.0",
        "validation_id": validation_id,
        "task_id": task_id,
        "accepted_structure": not errors,
        "candidate_type": candidate_type,
        "validation_errors": errors,
        "validation_warnings": warnings,
        "normalized_candidate": normalized_candidate,
        "direct_execution_allowed": False,
        "must_reenter_orchestration_layer": True,
        "validator_policy": {
            "forbidden_output_fields": sorted(LLM_FORBIDDEN_OUTPUT_FIELDS),
            "allowed_candidate_types": sorted(LLM_ALLOWED_CANDIDATE_TYPES),
        },
    }


def explain_execution_context(task_id: str, question: str = "为什么不能执行") -> dict[str, Any]:
    state = STATE_STORE.get(task_id, {})
    audit = AUDIT_STORE.get(task_id, {})
    gap_record_id = state.get("experience_gap_record_id")
    gap_record = EXPERIENCE_GAP_STORE.get(gap_record_id) if gap_record_id else None
    feasibility = state.get("execution_feasibility", {})
    if gap_record:
        reasons = [item.get("reason") for item in gap_record.get("infeasible_reasons", []) if item.get("reason")]
        reason_source = classify_execution_block_source(reasons[0] if reasons else gap_record.get("blocked_reason"))
        return {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "question": question,
            "answer": "当前不能执行，原因来自经验缺口记录",
            "status": "resolved_from_experience_gap",
            "source": "current_runtime_context_only",
            "refusal_source": reason_source,
            "evidence": {
                "gap_record_id": gap_record_id,
                "reasons": reasons,
                "recommended_actions": gap_record.get("recommended_actions", []),
            },
        }
    if feasibility:
        reasons = [item.get("reason") for item in feasibility.get("infeasible_reasons", []) if item.get("reason")]
        reason_source = classify_execution_block_source(reasons[0] if reasons else feasibility.get("result"))
        return {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "question": question,
            "answer": "当前执行受阻，原因来自当前任务执行可行性结果",
            "status": "resolved_from_execution_feasibility",
            "source": "current_runtime_context_only",
            "refusal_source": reason_source,
            "evidence": {
                "result": feasibility.get("result"),
                "reasons": reasons,
                "recommended_actions": feasibility.get("recommended_actions", []),
            },
        }
    if audit.get("outcome") == "requires_human_confirmation":
        return {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "question": question,
            "answer": "当前需要人工确认，原因来自执行闭环返回的冲突或不一致状态",
            "status": "resolved_from_audit",
            "source": "current_runtime_context_only",
            "refusal_source": "capability_failure",
            "evidence": {
                "audit_outcome": audit.get("outcome"),
                "stop_reason": audit.get("stop_reason"),
            },
        }
    return {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "question": question,
        "answer": "当前没有足够的受阻上下文，建议先运行任务或查询任务状态",
        "status": "context_missing",
        "source": "current_runtime_context_only",
        "refusal_source": "semantic_failure",
        "evidence": {
            "audit_outcome": audit.get("outcome"),
            "runtime_state": state.get("runtime_state"),
        },
    }


def handle_agent_query(
    utterance: str,
    task_id: str | None = None,
    scenario: str = "auto",
    auto_execute: bool = False,
) -> dict[str, Any]:
    cognitive_model = get_cognitive_model()
    semantic_request = build_semantic_request_frame(utterance, cognitive_model, task_id=task_id)
    request_type = semantic_request["request_type"]
    concept_resolution = None
    if request_type in {"task_execution", "teaching"}:
        concept_resolution = resolve_concepts_for_intent(utterance, task_id=task_id)
    grounding_gate = build_concept_grounding_gate(concept_resolution)
    if request_type == "task_execution" and grounding_gate.get("clarification_required") and not semantic_request.get("interrupt_requested"):
        semantic_request["clarification_needed"] = True
        semantic_request["clarification_reason"] = "required_concept_role_not_grounded"
        semantic_request["confidence_reasons"].append("概念必需角色尚未落地，执行前必须澄清或确认")
        return {
            "schema_version": "1.0.0",
            "semantic_request": semantic_request,
            "route_result": {
                "schema_version": "1.0.0",
                "decision": "concept_grounding_required",
                "clarification_needed": True,
                "clarification_reason": "required_concept_role_not_grounded",
                "clarification_prompt": grounding_gate.get("clarification_questions", ["请确认任务涉及的对象或区域。"])[0],
                "concept_grounding_gate": grounding_gate,
                "concept_resolution": concept_resolution,
                "auto_execute_blocked": bool(auto_execute),
                "direct_execution_allowed": False,
            },
        }
    if semantic_request.get("clarification_needed") and request_type == "task_execution" and not auto_execute:
        cloud_recall_preview = build_cloud_recall_preview(
            utterance,
            task_id=task_id,
            semantic_request=semantic_request,
            concept_resolution=concept_resolution,
        )
        clarification_result = {
            "schema_version": "1.0.0",
            "decision": "clarification_required",
            "clarification_needed": True,
            "clarification_reason": semantic_request.get("clarification_reason"),
            "clarification_prompt": build_clarification_prompt(semantic_request, concept_resolution),
            "intent_confidence": semantic_request.get("intent_confidence"),
            "alternative_interpretations": semantic_request.get("alternative_interpretations", []),
            "concept_resolution": concept_resolution,
            "cloud_recall_preview": cloud_recall_preview,
        }
        return {
            "schema_version": "1.0.0",
            "semantic_request": semantic_request,
            "route_result": clarification_result,
        }
    if request_type == "state_query":
        if not task_id:
            return {
                "error": "missing_task_id_for_state_query",
                "semantic_request": semantic_request,
            }
        state_query_result = query_runtime_world_state(task_id, utterance)
        explanation_view = build_runtime_explanation_view(task_id)
        result = {
            **state_query_result,
            "runtime_explanation_view": explanation_view if "error" not in explanation_view else None,
        }
        return {"schema_version": "1.0.0", "semantic_request": semantic_request, "route_result": result}
    if request_type == "teaching":
        parsed_steps = semantic_request.get("teaching_plan", {}).get("parsed_steps", [])
        result = {
            "schema_version": "1.0.0",
            "decision": "routed_to_teaching",
            "parsed_steps": parsed_steps,
            "recommended_next_endpoint": semantic_request.get("teaching_plan", {}).get("recommended_endpoint"),
            "goal_fact": semantic_request.get("intent_frame", {}).get("goal_fact"),
            "teaching_frame": semantic_request.get("teaching_plan", {}).get("teaching_frame"),
            "teaching_feedback": {
                "acknowledgement": build_teaching_acknowledgement(utterance, parsed_steps, semantic_request),
                "clarification_needed": semantic_request.get("clarification_needed"),
                "clarification_reason": semantic_request.get("clarification_reason"),
            },
            "concept_resolution": concept_resolution,
        }
        return {"schema_version": "1.0.0", "semantic_request": semantic_request, "route_result": result}
    if request_type == "clarification":
        if not task_id:
            return {"error": "missing_task_id_for_clarification", "semantic_request": semantic_request}
        result = explain_execution_context(task_id, utterance)
        return {"schema_version": "1.0.0", "semantic_request": semantic_request, "route_result": result}
    if request_type == "task_execution":
        if auto_execute:
            result = run_process_with_runtime_context(scenario, utterance, task_id=task_id)
        else:
            intent = adapt_intent_to_runtime_world_state(translate_intent(utterance), task_id=task_id)
            result = {
                "intent_translation": intent,
                "space_admission": evaluate_space_admission(intent, cognitive_model),
                "concept_resolution": concept_resolution,
            }
            snapshot = get_active_runtime_snapshot(task_id)
            if task_id and snapshot:
                arbitration = arbitrate_runtime_event(task_id, utterance, intent, snapshot)
                result["runtime_event_arbitration"] = arbitration
                if semantic_request.get("interrupt_requested") or semantic_request.get("task_switch_candidate"):
                    result["decision"] = arbitration.get("decision")
                    result["space_admission"] = {
                        "allowed": False,
                        "decision": "runtime_event_preview",
                        "reason": arbitration.get("reason"),
                        "checks": [
                            {
                                "check_id": "runtime_event_preview",
                                "passed": True,
                                "notes": arbitration.get("decision"),
                            }
                        ],
                    }
                    if semantic_request.get("task_switch_candidate"):
                        result["task_switch_context"] = build_task_switch_context(task_id, utterance, arbitration)
            if (
                intent.get("decision") != "executable"
                and not semantic_request.get("interrupt_requested")
                and not semantic_request.get("task_switch_candidate")
            ):
                result["cloud_recall_preview"] = build_cloud_recall_preview(
                    utterance,
                    task_id=task_id,
                    semantic_request=semantic_request,
                    concept_resolution=concept_resolution,
                    intent_preview=intent,
                )
                result["learning_followup"] = build_learning_followup(utterance, intent, result["cloud_recall_preview"])
        return {"schema_version": "1.0.0", "semantic_request": semantic_request, "route_result": result}
    return {
        "schema_version": "1.0.0",
        "semantic_request": semantic_request,
        "route_result": {
            "error": "unsupported_semantic_request",
            "utterance": utterance,
        },
    }


def release_runtime_world_state(task_id: str, reason: str = "task_finished") -> dict[str, Any]:
    current = get_runtime_world_state(task_id)
    if "error" in current:
        return current
    state = current["runtime_world_state_snapshot"]
    token_seed = "|".join([task_id, state.get("runtime_world_state_snapshot_id", ""), reason])
    release_token = "release_" + hashlib.sha1(token_seed.encode("utf-8")).hexdigest()[:12]
    state["snapshot_lifecycle_state"] = "released"
    state["release_status"] = "released"
    state["release_reason"] = reason
    state["release_token"] = release_token
    state["released_at"] = "2026-07-10T00:00:00+08:00"
    RUNTIME_WORLD_STATE_STORE[task_id] = state
    if task_id in STATE_STORE:
        STATE_STORE[task_id]["runtime_world_state"] = state
    audit_record_id = state.get("audit_record_id") or "audit_" + task_id.removeprefix("migration_")
    audit = AUDIT_STORE.setdefault(audit_record_id, {"schema_version": "1.0.0", "audit_record_id": audit_record_id})
    audit.update(
        {
            "task_id": task_id,
            "runtime_world_state_snapshot_id": state.get("runtime_world_state_snapshot_id"),
            "release_status": "released",
            "release_token": release_token,
            "release_reason": reason,
        }
    )
    return {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "runtime_world_state_snapshot_id": state.get("runtime_world_state_snapshot_id"),
        "release_status": "released",
        "release_token": release_token,
        "release_reason": reason,
        "audit_record_id": audit_record_id,
    }


def build_runtime_conflict_items(audit: dict[str, Any], trace: dict[str, Any]) -> list[dict[str, Any]]:
    conflict_items: list[dict[str, Any]] = []
    for item in audit.get("fact_summary", []):
        if item.get("state") != "conflicted":
            continue
        conflict_items.append(
            {
                "fact_id": item.get("fact_id"),
                "conflict_state": item.get("state"),
                "channel_notes": item.get("channel_notes"),
                "source": "audit_fact_summary",
            }
        )
    if conflict_items:
        return conflict_items
    observations: dict[str, dict[str, str]] = {}
    for event in trace.get("events", []):
        if event.get("trigger_reason") != "observation_update":
            continue
        summary = event.get("payload_summary", "")
        if ":" not in summary or "=" not in summary:
            continue
        fact_part, state_part = summary.split("=", 1)
        fact_id, channel_id = fact_part.split(":", 1)
        state = state_part.split(" ", 1)[0]
        observations.setdefault(fact_id, {})[channel_id] = state
    for fact_id, channels in observations.items():
        if len(set(channels.values())) > 1:
            conflict_items.append(
                {
                    "fact_id": fact_id,
                    "conflict_state": "conflicted",
                    "channel_notes": json.dumps(channels, ensure_ascii=False, sort_keys=True),
                    "source": "execution_trace_observations",
                }
            )
    return conflict_items


def readapt_runtime_conflict(
    task_id: str,
    utterance: str = "到水源处接一杯水",
    body_capability_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit = AUDIT_STORE.get(task_id)
    trace = TRACE_STORE.get(task_id, {})
    if not audit:
        return {"error": "audit_not_found", "task_id": task_id}
    conflict_items = build_runtime_conflict_items(audit, trace)
    if not conflict_items:
        return {"error": "runtime_conflict_not_found", "task_id": task_id}
    intent = translate_intent(utterance)
    cognitive_model = get_cognitive_model()
    readaptation_seed = "|".join([task_id, normalize_text(utterance), json.dumps(conflict_items, sort_keys=True)])
    readaptation_id = "readapt_" + hashlib.sha1(readaptation_seed.encode("utf-8")).hexdigest()[:12]
    runtime_world_state = build_initial_runtime_world_state(cognitive_model, {**intent, "experience_id": readaptation_id})
    runtime_world_state["migration_task_id"] = readaptation_id
    runtime_world_state["runtime_world_state_snapshot_id"] = readaptation_id + "_snapshot"
    runtime_world_state["audit_record_id"] = "audit_" + readaptation_id.removeprefix("readapt_")
    runtime_world_state["conflict_source_task_id"] = task_id
    runtime_world_state["runtime_conflicts"] = conflict_items
    runtime_world_state["snapshot_revision_reason"] = "execution_loop_returned_conflicting_fact_status"
    profile = body_capability_profile or build_default_body_capability_profile()
    binding_candidate = build_binding_candidates(intent, cognitive_model, runtime_world_state, profile)
    feasibility = build_execution_feasibility(intent, binding_candidate, runtime_world_state, profile)
    gap_record = build_experience_gap_record(readaptation_id, intent, binding_candidate, feasibility)
    if gap_record:
        EXPERIENCE_GAP_STORE[gap_record["gap_record_id"]] = gap_record
    record = {
        "schema_version": "1.0.0",
        "readaptation_id": readaptation_id,
        "source_task_id": task_id,
        "runtime_conflicts": conflict_items,
        "runtime_world_state_snapshot": runtime_world_state,
        "binding_candidate": binding_candidate,
        "execution_feasibility": feasibility,
        "experience_gap_record": gap_record,
        "recommended_next_steps": feasibility.get("recommended_actions", []),
    }
    READAPTATION_STORE[readaptation_id] = record
    RUNTIME_WORLD_STATE_STORE[readaptation_id] = runtime_world_state
    STATE_STORE[readaptation_id] = {
        "schema_version": "1.0.0",
        "task_id": readaptation_id,
        "current_stage_id": None,
        "runtime_state": "readaptation_required",
        "runtime_world_state": runtime_world_state,
        "execution_feasibility": feasibility,
        "body_capability_profile": profile,
        "experience_gap_record_id": gap_record.get("gap_record_id") if gap_record else None,
    }
    AUDIT_STORE[runtime_world_state["audit_record_id"]] = {
        "schema_version": "1.0.0",
        "audit_record_id": runtime_world_state["audit_record_id"],
        "readaptation_id": readaptation_id,
        "source_task_id": task_id,
        "runtime_world_state_snapshot_id": runtime_world_state["runtime_world_state_snapshot_id"],
        "binding_candidate_id": binding_candidate["binding_candidate_id"],
        "experience_gap_record_id": gap_record.get("gap_record_id") if gap_record else None,
        "outcome": feasibility["result"],
        "release_status": runtime_world_state["release_status"],
    }
    recovery_record = build_recovery_record_for_task(
        task_id=readaptation_id,
        failed_experience_ref=task_id,
        outcome=feasibility["result"],
        stop_reason="runtime_fact_conflict",
        expected_state=f"goal_fact:{intent.get('goal_fact') or 'unknown'}",
        observed_state="runtime_conflict_detected",
        audit_record_id=runtime_world_state["audit_record_id"],
        runtime_world_state_snapshot_id=runtime_world_state.get("runtime_world_state_snapshot_id"),
        gap_record=gap_record,
        readaptation_id=readaptation_id,
        source_refs={
            "source_task_id": task_id,
            "runtime_conflicts": conflict_items,
            "experience_gap_record_id": gap_record.get("gap_record_id") if gap_record else None,
        },
    )
    record["recovery_record"] = recovery_record
    return record


def get_experience_gap(gap_record_id: str) -> dict[str, Any]:
    record = EXPERIENCE_GAP_STORE.get(gap_record_id)
    if not record:
        return {"error": "experience_gap_not_found", "gap_record_id": gap_record_id}
    return record


def get_readaptation(readaptation_id: str) -> dict[str, Any]:
    record = READAPTATION_STORE.get(readaptation_id)
    if not record:
        return {"error": "readaptation_not_found", "readaptation_id": readaptation_id}
    return record


def find_task_id_by_snapshot(snapshot_id: str | None) -> str | None:
    if not snapshot_id:
        return None
    for task_id, state in RUNTIME_WORLD_STATE_STORE.items():
        if state.get("runtime_world_state_snapshot_id") == snapshot_id:
            return task_id
    for task_id, stage_state in STATE_STORE.items():
        state = stage_state.get("runtime_world_state", {})
        if state.get("runtime_world_state_snapshot_id") == snapshot_id:
            return task_id
    return None


def run_mujoco_physics_bridge(task_id: str, options: dict[str, Any]) -> dict[str, Any]:
    configured = os.environ.get("RELL_PHYSICS_PYTHON")
    default = Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python310" / "python.exe"
    executable = Path(configured) if configured else default
    if not executable.exists():
        return {"error": "physics_runtime_unavailable", "required_env": "RELL_PHYSICS_PYTHON"}
    state = RUNTIME_WORLD_STATE_STORE.get(task_id, {})
    space_id = state.get("space_id") or STATE_STORE.get(task_id, {}).get("space_id") or "home_a_kitchen"
    request = {
        "layout_id": "corridor_b" if space_id == "site_b_corridor" else "kitchen_a",
        "executor_type": options.get("physics_executor_type", "mobile_manipulator"),
        "obstacle": options.get("physics_obstacle", "none"),
        "steps": options.get("physics_steps", []),
        "initial_state": options.get("physics_initial_state", {}),
    }
    try:
        completed = subprocess.run(
            [str(executable), str(ROOT / "physics_mujoco_bridge.py")],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=20,
            check=True,
        )
        return json.loads(completed.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return {"error": "physics_bridge_failed", "detail": str(exc)}


def dispatch_execution_loop_payload(
    payload: dict[str, Any],
    executor_type: str = "digital_executor",
    executor_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    allowed_executors = {
        "process_template_executor",
        "digital_executor",
        "simulated_robot",
        "ros_controller",
        "robot_sdk",
        "vla_policy",
        "mujoco_physics",
    }
    if executor_type not in allowed_executors:
        return {"error": "unsupported_executor_type", "allowed_executor_types": sorted(allowed_executors)}
    snapshot_id = payload.get("runtime_world_state_snapshot_id")
    task_id = find_task_id_by_snapshot(snapshot_id)
    if not task_id:
        return {"error": "runtime_world_state_not_found", "runtime_world_state_snapshot_id": snapshot_id}
    current = get_runtime_world_state(task_id)
    if "error" in current:
        return current
    state = current["runtime_world_state_snapshot"]
    if state.get("release_status") == "released":
        return {"error": "runtime_world_state_released", "task_id": task_id, "release_token": state.get("release_token")}
    physics_result = None
    if executor_type == "mujoco_physics":
        physics_options = dict(executor_options or {})
        physics_options["physics_steps"] = [
            item.get("step") for item in payload.get("execution_step_payload", []) if item.get("step")
        ]
        physics_result = run_mujoco_physics_bridge(task_id, physics_options)
        if physics_result.get("error"):
            return physics_result
    dispatch_seed = "|".join([payload.get("execution_callback_id", ""), executor_type, snapshot_id or "none"])
    dispatch_id = "dispatch_" + hashlib.sha1(dispatch_seed.encode("utf-8")).hexdigest()[:12]
    feedback: list[dict[str, Any]] = []
    stepwise_readaptation = None
    profile = STATE_STORE.get(task_id, {}).get("body_capability_profile") or build_default_body_capability_profile()
    if physics_result and physics_result.get("outcome") != "fact_established":
        feedback.append(
            {
                "step": "physics_preflight",
                "executor_type": executor_type,
                "fact_status": physics_result.get("outcome", "fact_not_established"),
                "reason": "physics_capability_or_route_not_satisfied",
                "physics_route_evidence": physics_result.get("route_evidence"),
                "missing_capabilities": physics_result.get("missing_capabilities", []),
            }
        )
        outcome = physics_result.get("outcome", "fact_not_established")
        state["last_execution_dispatch_id"] = dispatch_id
        state["last_execution_executor_type"] = executor_type
        state["last_execution_fact_feedback"] = feedback
        RUNTIME_WORLD_STATE_STORE[task_id] = state
        record = {
            "schema_version": "1.0.0",
            "dispatch_id": dispatch_id,
            "task_id": task_id,
            "execution_callback_id": payload.get("execution_callback_id"),
            "executor_type": executor_type,
            "accepted_interface": "open_execution_loop_fact_feedback_v1",
            "target_causal_fact": payload.get("target_causal_fact"),
            "outcome": outcome,
            "fact_feedback": feedback,
            "runtime_world_state_snapshot": state,
            "stepwise_readaptation": None,
            "recovery_record": None,
            "audit_record_id": state.get("audit_record_id"),
            "generalization_result": None,
            "physics_result": physics_result,
        }
        EXECUTION_DISPATCH_STORE[dispatch_id] = record
        return record
    payload_bindings = {
        item.get("step"): item
        for item in payload.get("binding_candidate_payload", {}).get("step_bindings", [])
    }
    physics_stages = {
        item.get("step"): item for item in (physics_result or {}).get("stage_results", [])
    }
    for index, item in enumerate(payload.get("execution_step_payload", []), start=1):
        step = item.get("step")
        meta = STEP_LIBRARY.get(step)
        if not meta:
            feedback.append(
                {
                    "step": step,
                    "fact_status": "failure",
                    "reason": "unknown_step",
                    "executor_type": executor_type,
                }
            )
            continue
        preflight = evaluate_runtime_step_preflight(state, step, meta)
        if preflight.get("result") == "blocked":
            remaining_steps = [step] + [
                rest.get("step")
                for rest in payload.get("execution_step_payload", [])[index:]
                if rest.get("step")
            ]
            stepwise_readaptation = build_stepwise_readaptation(
                task_id,
                payload.get("target_causal_fact"),
                remaining_steps,
                state,
                profile,
            )
            gap_record = stepwise_readaptation.get("experience_gap_record")
            feedback.append(
                {
                    "step": step,
                    "executor_type": executor_type,
                    "fact_status": "human_confirmation",
                    "reason": preflight.get("reason"),
                    "preflight_result": "blocked",
                    "blocking_perturbations": preflight.get("blocking_perturbations", []),
                    "recommended_actions": preflight.get("recommended_actions", []),
                    "readaptation_id": stepwise_readaptation.get("readaptation_id"),
                }
            )
            state["last_execution_dispatch_id"] = dispatch_id
            state["last_execution_executor_type"] = executor_type
            state["last_execution_fact_feedback"] = feedback
            if task_id in STATE_STORE:
                STATE_STORE[task_id]["runtime_world_state"] = state
                STATE_STORE[task_id]["runtime_state"] = "readaptation_required"
                STATE_STORE[task_id]["execution_feasibility"] = stepwise_readaptation.get("execution_feasibility", {})
                STATE_STORE[task_id]["experience_gap_record_id"] = gap_record.get("gap_record_id") if gap_record else None
                STATE_STORE[task_id]["last_readaptation_id"] = stepwise_readaptation.get("readaptation_id")
            break
        transition = apply_step_to_runtime_world_state(state, step, meta, index, payload_bindings.get(step))
        fact_status = "fact_established" if not transition["missing_before_step"] else "fact_not_established"
        feedback.append(
            {
                "step": step,
                "executor_type": executor_type,
                "fact_id": transition["produces_fact"],
                "fact_status": fact_status,
                "causal_produced_facts": [transition["produces_fact"]],
                "causal_destroyed_facts": transition["destroys_facts"],
                "missing_before_step": transition["missing_before_step"],
                "before_executor_location": transition["before_executor_location"],
                "after_executor_location": transition["after_executor_location"],
                "preflight_result": preflight.get("result"),
                "route_adjustment": preflight.get("route_adjustment"),
                "physics_stage": physics_stages.get(step),
            }
        )
    target_fact = payload.get("target_causal_fact")
    established_facts = set(state.get("established_facts", []))
    if physics_result and physics_result.get("outcome") != "fact_established":
        outcome = physics_result.get("outcome", "fact_not_established")
    elif stepwise_readaptation:
        outcome = "readaptation_required"
    else:
        outcome = "fact_established" if target_fact in established_facts else "fact_not_established"
    state["last_execution_dispatch_id"] = dispatch_id
    state["last_execution_executor_type"] = executor_type
    state["last_execution_fact_feedback"] = feedback
    RUNTIME_WORLD_STATE_STORE[task_id] = state
    if task_id in STATE_STORE:
        STATE_STORE[task_id]["runtime_world_state"] = state
        STATE_STORE[task_id]["runtime_state"] = "execution_feedback_received"
        STATE_STORE[task_id]["last_execution_dispatch_id"] = dispatch_id
    audit_record_id = state.get("audit_record_id") or "audit_" + task_id.removeprefix("migration_")
    audit = AUDIT_STORE.setdefault(audit_record_id, {"schema_version": "1.0.0", "audit_record_id": audit_record_id})
    audit.update(
        {
            "task_id": task_id,
            "execution_dispatch_id": dispatch_id,
            "execution_callback_id": payload.get("execution_callback_id"),
            "executor_type": executor_type,
            "outcome": outcome,
            "fact_feedback": feedback,
            "runtime_world_state_snapshot_id": snapshot_id,
            "stepwise_readaptation_id": stepwise_readaptation.get("readaptation_id") if stepwise_readaptation else None,
        }
    )
    recovery_record = None
    if stepwise_readaptation:
        gap_record = stepwise_readaptation.get("experience_gap_record")
        blocked_step = next((item.get("step") for item in feedback if item.get("preflight_result") == "blocked"), None)
        recovery_record = build_recovery_record_for_task(
            task_id=task_id,
            failed_experience_ref=payload.get("execution_callback_id") or task_id,
            outcome=outcome,
            stop_reason="step_preflight_blocked",
            expected_state=f"goal_fact:{target_fact or 'unknown'}",
            observed_state=f"blocked_step:{blocked_step or 'unknown'}",
            audit_record_id=audit_record_id,
            runtime_world_state_snapshot_id=snapshot_id,
            gap_record=gap_record,
            readaptation_id=stepwise_readaptation.get("readaptation_id"),
            source_refs={
                "execution_dispatch_id": dispatch_id,
                "stepwise_readaptation_id": stepwise_readaptation.get("readaptation_id"),
                "experience_gap_record_id": gap_record.get("gap_record_id") if gap_record else None,
            },
        )
    generalization_result = build_generalization_result_record(
        task_id,
        payload.get("binding_candidate_payload", {}),
        profile,
        state,
        outcome,
        target_fact,
    )
    audit["generalization_result_id"] = generalization_result["generalization_result_id"]
    record = {
        "schema_version": "1.0.0",
        "dispatch_id": dispatch_id,
        "task_id": task_id,
        "execution_callback_id": payload.get("execution_callback_id"),
        "executor_type": executor_type,
        "accepted_interface": "open_execution_loop_fact_feedback_v1",
        "target_causal_fact": target_fact,
        "outcome": outcome,
        "fact_feedback": feedback,
        "runtime_world_state_snapshot": state,
        "stepwise_readaptation": stepwise_readaptation,
        "recovery_record": recovery_record,
        "audit_record_id": audit_record_id,
        "generalization_result": generalization_result,
        "physics_result": physics_result,
    }
    EXECUTION_DISPATCH_STORE[dispatch_id] = record
    return record


def get_execution_dispatch(dispatch_id: str) -> dict[str, Any]:
    record = EXECUTION_DISPATCH_STORE.get(dispatch_id)
    if not record:
        return {"error": "execution_dispatch_not_found", "dispatch_id": dispatch_id}
    return record


def start_physics_session(payload: dict[str, Any], options: dict[str, Any] | None = None) -> dict[str, Any]:
    snapshot_id = payload.get("runtime_world_state_snapshot_id")
    task_id = find_task_id_by_snapshot(snapshot_id)
    if not task_id:
        return {"error": "runtime_world_state_not_found", "runtime_world_state_snapshot_id": snapshot_id}
    steps = [item.get("step") for item in payload.get("execution_step_payload", []) if item.get("step")]
    seed = "|".join([task_id, payload.get("execution_callback_id", ""), str(len(PHYSICS_SESSION_STORE) + 1)])
    session_id = "physics_session_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    session = {
        "schema_version": "1.0.0",
        "session_id": session_id,
        "task_id": task_id,
        "status": "paused_between_stages",
        "steps": steps,
        "next_step_index": 0,
        "physics_state": {"location": "start", "holding_cup": False},
        "executor_options": dict(options or {}),
        "stage_history": [],
        "target_causal_fact": payload.get("target_causal_fact"),
        "interruption": None,
    }
    PHYSICS_SESSION_STORE[session_id] = session
    return session


def get_physics_session(session_id: str) -> dict[str, Any]:
    return PHYSICS_SESSION_STORE.get(session_id) or {"error": "physics_session_not_found", "session_id": session_id}


def step_physics_session(session_id: str) -> dict[str, Any]:
    session = PHYSICS_SESSION_STORE.get(session_id)
    if not session:
        return {"error": "physics_session_not_found", "session_id": session_id}
    if session["status"] in {"interrupted", "completed", "blocked"}:
        return {"error": "physics_session_not_stepable", "status": session["status"], "session": session}
    index = session["next_step_index"]
    if index >= len(session["steps"]):
        session["status"] = "completed"
        return session
    step = session["steps"][index]
    options = dict(session["executor_options"])
    options["physics_steps"] = [step]
    options["physics_initial_state"] = session["physics_state"]
    result = run_mujoco_physics_bridge(session["task_id"], options)
    if result.get("error"):
        return result
    stage = (result.get("stage_results") or [{}])[0]
    session["stage_history"].append(stage)
    if stage.get("outcome") != "fact_established":
        session["status"] = "blocked"
        session["blocking_result"] = result
        return session
    session["physics_state"] = stage.get("after_state", session["physics_state"])
    session["next_step_index"] += 1
    session["status"] = "completed" if session["next_step_index"] >= len(session["steps"]) else "paused_between_stages"
    session["last_stage"] = stage
    return session


def perturb_physics_session(session_id: str, obstacle: str) -> dict[str, Any]:
    session = PHYSICS_SESSION_STORE.get(session_id)
    if not session:
        return {"error": "physics_session_not_found", "session_id": session_id}
    if session["status"] != "paused_between_stages":
        return {"error": "physics_session_not_perturbable", "status": session["status"]}
    session["executor_options"]["physics_obstacle"] = obstacle
    session["pending_perturbation"] = {"obstacle": obstacle, "applies_before_step_index": session["next_step_index"]}
    return session


def interrupt_physics_session(session_id: str, utterance: str) -> dict[str, Any]:
    session = PHYSICS_SESSION_STORE.get(session_id)
    if not session:
        return {"error": "physics_session_not_found", "session_id": session_id}
    if session["status"] == "completed":
        return {"error": "physics_session_already_completed", "session": session}
    session["status"] = "interrupted"
    session["interruption"] = {
        "utterance": utterance,
        "decision": "pause_old_task_and_reenter_state_first_arbitration",
        "old_task_fact_commit_blocked": True,
        "resume_requires_new_runtime_snapshot": True,
    }
    return session


def run_process_with_runtime_context(
    scenario: str = "auto",
    utterance: str = "给客人倒一杯水",
    task_id: str | None = None,
) -> dict[str, Any]:
    intent = adapt_intent_to_runtime_world_state(translate_intent(utterance), task_id=task_id)
    snapshot = get_active_runtime_snapshot(task_id)
    if task_id and snapshot:
        arbitration = arbitrate_runtime_event(task_id, utterance, intent, snapshot)
        cognitive_model = get_cognitive_model()
        if arbitration.get("decision") in {"continue_current_task", "pause_and_switch_task"} and arbitration.get("can_enter_execution"):
            space_admission = evaluate_space_admission(intent, cognitive_model)
            if not space_admission["allowed"]:
                return build_cannot_do_result(utterance, intent, space_admission)
        else:
            space_admission = {
                "allowed": False,
                "decision": "state_first_arbitrated",
                "reason": arbitration.get("reason"),
                "checks": [
                    {
                        "check_id": "state_first_runtime_event_arbitration",
                        "passed": False,
                        "notes": arbitration.get("decision"),
                    }
                ],
            }
        if arbitration.get("decision") == "continue_current_task" and arbitration.get("can_enter_execution") and get_process_chain_for_intent(intent):
            return continue_runtime_task(task_id, utterance, intent, space_admission)
        if arbitration.get("decision") == "pause_and_switch_task" and arbitration.get("can_enter_execution") and get_process_chain_for_intent(intent):
            apply_runtime_event_arbitration(task_id, arbitration)
            switched = start_task_from_runtime_world_state(task_id, utterance, intent, space_admission)
            switched["source_runtime_event_arbitration"] = arbitration
            switched["source_task_id"] = task_id
            return switched
        apply_runtime_event_arbitration(task_id, arbitration)
        return build_runtime_event_arbitration_result(task_id, utterance, intent, space_admission, arbitration)
    cognitive_model = get_cognitive_model()
    space_admission = evaluate_space_admission(intent, cognitive_model)
    if not space_admission["allowed"]:
        return build_cannot_do_result(utterance, intent, space_admission)
    return run_process(scenario, utterance)


def run_process(scenario: str = "success", utterance: str = "给客人倒一杯水") -> dict[str, Any]:
    intent = translate_intent(utterance)
    cognitive_model = get_cognitive_model()
    space_admission = evaluate_space_admission(intent, cognitive_model)
    if not space_admission["allowed"]:
        return build_cannot_do_result(utterance, intent, space_admission)
    if scenario in {"auto", "simulated_success"}:
        if intent["task_type"] in {"learned_process_chain", "causal_process_chain"}:
            return run_process_chain_experience(intent, utterance, space_admission)
    if scenario == "auto":
        scenario = intent.get("recommended_scenario", "simulated_success")
    if scenario not in SCENARIOS:
        return {
            "error": "unknown_scenario",
            "allowed_scenarios": sorted(SCENARIOS),
        }
    if scenario in SIMULATED_SCENARIOS:
        result = run_simulated_runtime_sample(DATA, scenario)
    else:
        result = run_runtime_sample(DATA, TIMELINE_SCENARIOS[scenario])
    task_id = result["audit_summary"]["task_id"]
    AUDIT_STORE[task_id] = result["audit_summary"]
    STATE_STORE[task_id] = result["stage_runtime_state"]
    TRACE_STORE[task_id] = result["execution_trace"]
    recovery_record = None
    if result["audit_summary"].get("outcome") != "completed":
        stop_reason = result["audit_summary"].get("stop_reason") or result["audit_summary"].get("outcome")
        expected_fact = next(
            (item.get("fact_id") for item in result["audit_summary"].get("fact_summary", []) if item.get("state") == "conflicted"),
            None,
        ) or intent.get("goal_fact") or "task_goal_not_reached"
        observed_stage = result["stage_runtime_state"].get("current_stage_id") or result["stage_runtime_state"].get("runtime_state") or "unknown"
        recovery_record = build_recovery_record_for_task(
            task_id=task_id,
            failed_experience_ref=result["audit_summary"].get("process_instance_id") or task_id,
            outcome=result["audit_summary"].get("outcome", "failed"),
            stop_reason=stop_reason,
            expected_state=f"goal_fact:{expected_fact}",
            observed_state=f"runtime_state:{observed_stage}",
            audit_record_id=task_id,
            runtime_world_state_snapshot_id=result["stage_runtime_state"].get("runtime_world_state", {}).get("runtime_world_state_snapshot_id"),
            source_refs={
                "scenario": scenario,
                "task_type": intent.get("task_type"),
            },
        )
    return {
        "task_id": task_id,
        "scenario": scenario,
        "intent_translation": intent,
        "space_admission": space_admission,
        "admission_decision": result["admission_decision"],
        "audit_summary": result["audit_summary"],
        "stage_runtime_state": result["stage_runtime_state"],
        "execution_trace": result["execution_trace"],
        "recovery_record": recovery_record,
        "space_context": build_space_context(cognitive_model),
    }


def get_space_prior() -> dict[str, Any]:
    return read_json(SPACE_PRIOR_FILE)


def get_cognitive_model(space_id: str | None = None) -> dict[str, Any]:
    if space_id == "site_b_corridor":
        return read_json(CORRIDOR_COGNITIVE_MODEL_FILE)
    return read_json(COGNITIVE_MODEL_FILE)


def get_audit(task_id: str) -> dict[str, Any]:
    audit = AUDIT_STORE.get(task_id)
    if not audit:
        return {"error": "audit_not_found", "task_id": task_id}
    return audit


def get_status(task_id: str) -> dict[str, Any]:
    state = STATE_STORE.get(task_id)
    if not state:
        return {"error": "status_not_found", "task_id": task_id}
    return state


def get_p017_minimal_loop_evidence() -> dict[str, Any]:
    if not P017_MINIMAL_LOOP_OUTPUT.exists():
        return {
            "error": "p017_minimal_loop_output_not_found",
            "output_dir": str(P017_MINIMAL_LOOP_OUTPUT),
            "validation_command": "python demo_runtime\\rell_sample\\validate_p017_minimal_loop.py",
        }
    required_files = [
        "evidence_index.json",
        "00_summary.json",
        "01_experience_record.json",
        "02_migration_context.json",
        "03_runtime_world_state_snapshot.json",
        "04_binding_and_feasibility.json",
        "04b_alternate_space_binding.json",
        "05_execution_fact_feedback.json",
        "06_release_and_audit.json",
        "07_portability_compilation.json",
    ]
    missing = [name for name in required_files if not (P017_MINIMAL_LOOP_OUTPUT / name).exists()]
    if missing:
        return {
            "error": "p017_minimal_loop_evidence_incomplete",
            "output_dir": str(P017_MINIMAL_LOOP_OUTPUT),
            "missing_files": missing,
            "validation_command": "python demo_runtime\\rell_sample\\validate_p017_minimal_loop.py",
        }
    evidence_files = {name: read_json(P017_MINIMAL_LOOP_OUTPUT / name) for name in required_files if name not in {"evidence_index.json", "00_summary.json"}}
    return {
        "schema_version": "1.0.0",
        "output_dir": str(P017_MINIMAL_LOOP_OUTPUT),
        "validation_command": "python demo_runtime\\rell_sample\\validate_p017_minimal_loop.py",
        "evidence_index": read_json(P017_MINIMAL_LOOP_OUTPUT / "evidence_index.json"),
        "summary": read_json(P017_MINIMAL_LOOP_OUTPUT / "00_summary.json"),
        "evidence_files": evidence_files,
    }


class RellSampleHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._send_html(INDEX_HTML)
            return
        if path == "/embodied":
            self._send_html((ROOT / "embodied_home.html").read_text(encoding="utf-8"))
            return
        if path == "/concept-teaching":
            self._send_html((ROOT / "concept_teaching.html").read_text(encoding="utf-8"))
            return
        if path == "/vendor/three.min.js":
            self._send_javascript((ROOT / "vendor" / "three.min.js").read_text(encoding="utf-8"))
            return
        if path == "/embodied/scene":
            requested_scene = parse_qs(parsed.query).get("scene_id", ["home_semantic_3d_a"])[0]
            try:
                scene = load_embodied_scene(requested_scene)
            except ValueError:
                self._send_json({"error": "embodied_scene_not_found", "scene_id": requested_scene}, status=404)
                return
            self._send_json(scene)
            return
        if path == "/embodied/scenes":
            self._send_json({"scenes": list_embodied_scenes()})
            return
        if path == "/embodied/factory-concepts":
            self._send_json(build_factory_concept_catalog())
            return
        if path == "/embodied/factory-objects":
            self._send_json(build_factory_object_catalog())
            return
        if path == "/embodied/visual-concept-packs":
            self._send_json(build_visual_concept_pack_catalog())
            return
        if path == "/visual-concepts/pipeline":
            self._send_json(get_pipeline_state())
            return
        if path == "/concept-teaching/catalog":
            self._send_json(get_concept_teaching_catalog())
            return
        if path.startswith("/concept-teaching/session/"):
            session_id = path.removeprefix("/concept-teaching/session/")
            result = get_concept_teaching_session(session_id)
            self._send_json(result, status=404 if "error" in result else 200)
            return
        if path == "/embodied/factory-state-facts":
            self._send_json(build_factory_state_fact_catalog())
            return
        if path == "/embodied/factory-orchestrator":
            self._send_json(build_factory_orchestrator_catalog())
            return
        if path == "/embodied/experience/library":
            self._send_json({"schema_version": "1.0.0", "experiences": load_trusted_experiences()})
            return
        if path == "/health":
            self._send_json({"status": "ok", "service": "eorld-rell"})
            return
        if path == "/space/prior":
            self._send_json(get_space_prior())
            return
        if path == "/space/cognitive-model":
            self._send_json(get_cognitive_model())
            return
        if path == "/skills":
            self._send_json({"schema_version": "1.0.0", "skills": TASK_LIBRARY})
            return
        if path == "/experience/library":
            self._send_json(load_experience_library())
            return
        if path == "/recovery/library":
            self._send_json(load_recovery_library())
            return
        if path == "/preference/library":
            self._send_json(load_preference_library())
            return
        if path == "/concept/library":
            self._send_json(load_concept_library())
            return
        if path == "/concept/candidates":
            self._send_json(get_concept_candidates())
            return
        if path == "/p017/minimal-loop":
            result = get_p017_minimal_loop_evidence()
            self._send_json(result, status=404 if "error" in result else 200)
            return
        if path.startswith("/audit/"):
            task_id = path.removeprefix("/audit/")
            self._send_json(get_audit(task_id), status=200 if task_id in AUDIT_STORE else 404)
            return
        if path.startswith("/runtime_world_state/"):
            task_id = path.removeprefix("/runtime_world_state/")
            result = get_runtime_world_state(task_id)
            self._send_json(result, status=404 if "error" in result else 200)
            return
        if path.startswith("/experience/gap/"):
            gap_record_id = path.removeprefix("/experience/gap/")
            result = get_experience_gap(gap_record_id)
            self._send_json(result, status=404 if "error" in result else 200)
            return
        if path.startswith("/recovery/task/"):
            task_id = path.removeprefix("/recovery/task/")
            self._send_json(get_recovery_records_for_task(task_id))
            return
        if path.startswith("/recovery/"):
            recovery_id = path.removeprefix("/recovery/")
            result = get_recovery_record(recovery_id)
            self._send_json(result, status=404 if "error" in result else 200)
            return
        if path.startswith("/runtime_readaptation/"):
            readaptation_id = path.removeprefix("/runtime_readaptation/")
            result = get_readaptation(readaptation_id)
            self._send_json(result, status=404 if "error" in result else 200)
            return
        if path.startswith("/execution/dispatch/"):
            dispatch_id = path.removeprefix("/execution/dispatch/")
            result = get_execution_dispatch(dispatch_id)
            self._send_json(result, status=404 if "error" in result else 200)
            return
        if path == "/real-robot/readiness":
            self._send_json(build_real_robot_readiness_catalog())
            return
        if path.startswith("/real-robot/session/"):
            session_id = path.removeprefix("/real-robot/session/")
            result = get_real_robot_session(session_id)
            self._send_json(result, status=404 if "error" in result else 200)
            return
        if path.startswith("/physics/session/"):
            session_id = path.removeprefix("/physics/session/")
            result = get_physics_session(session_id)
            self._send_json(result, status=404 if "error" in result else 200)
            return
        if path.startswith("/embodied/session/"):
            session_id = path.removeprefix("/embodied/session/")
            result = get_embodied_session(session_id)
            self._send_json(result, status=404 if "error" in result else 200)
            return
        if path.startswith("/teaching/session/"):
            session_id = path.removeprefix("/teaching/session/")
            result = get_teaching_session(session_id)
            self._send_json(result, status=404 if "error" in result else 200)
            return
        if path.startswith("/process/status/"):
            task_id = path.removeprefix("/process/status/")
            self._send_json(get_status(task_id), status=200 if task_id in STATE_STORE else 404)
            return
        self._send_json({"error": "not_found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()
        if path == "/semantic/route":
            utterance = body.get("utterance", "")
            task_id = body.get("task_id")
            cognitive_model = get_cognitive_model()
            intent_frame = build_intent_frame(utterance, cognitive_model) if utterance else None
            result = build_semantic_request_frame(utterance, cognitive_model, task_id=task_id, intent_frame=intent_frame)
            self._send_json(result, status=400 if result.get("request_type") == "unknown" else 200)
            return
        if path == "/agent/query":
            result = handle_agent_query(
                body.get("utterance", ""),
                task_id=body.get("task_id") or body.get("session_id") or body.get("migration_task_id"),
                scenario=body.get("scenario", "auto"),
                auto_execute=bool(body.get("auto_execute", False)),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/llm/context-view":
            task_id = body.get("task_id") or body.get("session_id") or body.get("migration_task_id")
            if not task_id:
                self._send_json({"error": "missing_task_id"}, status=400)
                return
            result = build_llm_context_view(task_id)
            self._send_json(result, status=404 if "error" in result else 200)
            return
        if path == "/llm/prompt-contract":
            result = build_llm_prompt_contract(
                body.get("utterance", ""),
                task_id=body.get("task_id") or body.get("session_id") or body.get("migration_task_id"),
            )
            self._send_json(result, status=400 if not body.get("utterance") else 200)
            return
        if path == "/llm/candidate-intent":
            result = build_llm_candidate_intent(
                body.get("utterance", ""),
                task_id=body.get("task_id") or body.get("session_id") or body.get("migration_task_id"),
            )
            self._send_json(result, status=400 if not body.get("utterance") else 200)
            return
        if path == "/concept/cloud-recall":
            result = build_cloud_recall_preview(
                body.get("utterance", ""),
                task_id=body.get("task_id") or body.get("session_id") or body.get("migration_task_id"),
            )
            self._send_json(result, status=400 if not body.get("utterance") else 200)
            return
        if path == "/concept/lifecycle":
            self._send_json(build_concept_lifecycle_view(CONCEPT_LIFECYCLE_STORE, CONCEPT_FALLBACK_STORE))
            return
        if path == "/concept/resolve":
            result = resolve_concepts_for_intent(
                body.get("utterance", ""),
                task_id=body.get("task_id") or body.get("session_id") or body.get("migration_task_id"),
            )
            self._send_json(result, status=400 if not body.get("utterance") else 200)
            return
        if path == "/concept/candidates/confirm":
            result = confirm_concept_promotion_candidate(
                body.get("candidate_id", ""),
                confirmed_by=body.get("confirmed_by", "human_reviewer"),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/llm/candidate/validate":
            result = validate_llm_candidate_output(
                body.get("candidate"),
                task_id=body.get("task_id") or body.get("session_id") or body.get("migration_task_id"),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/intent/translate":
            intent = translate_intent(body.get("utterance", ""))
            cognitive_model = get_cognitive_model()
            self._send_json({"intent_translation": intent, "space_admission": evaluate_space_admission(intent, cognitive_model)})
            return
        if path == "/process/admit":
            self._send_json(admit_process(body.get("utterance", "给客人倒一杯水")))
            return
        if path == "/process/run":
            result = run_process(body.get("scenario", "success"), body.get("utterance", "给客人倒一杯水"))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/experience/migrate":
            profile = body.get("body_capability_profile")
            result = migrate_experience(
                body.get("utterance", "到水源处接一杯水"),
                profile if isinstance(profile, dict) else None,
                str(body.get("space_id")) if body.get("space_id") else None,
            )
            self._send_json(result)
            return
        if path == "/preference/record":
            context_ref = body.get("context_ref")
            task_id = body.get("task_id") or body.get("session_id") or body.get("migration_task_id")
            if not context_ref and task_id:
                state_result = get_runtime_world_state(task_id)
                if "error" not in state_result:
                    context_ref = state_result.get("runtime_world_state_snapshot", {}).get("preference_context", {}).get("context_ref")
            result = record_preference(
                context_ref=str(context_ref or ""),
                preference_signal=str(body.get("preference_signal") or ""),
                human_feedback=str(body.get("human_feedback") or ""),
                applies_to=body.get("applies_to") if isinstance(body.get("applies_to"), list) else None,
                strength=body.get("strength") if isinstance(body.get("strength"), (int, float)) else None,
                experience_ref=body.get("experience_ref"),
                enforcement_policy=str(body.get("enforcement_policy") or "advisory"),
            )
            if task_id and "error" not in result:
                attachment = attach_preference_to_runtime_task(task_id, result["preference_record"])
                result["runtime_attachment"] = attachment
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/runtime_world_state/release":
            task_id = body.get("task_id") or body.get("migration_task_id")
            if not task_id:
                self._send_json({"error": "missing_task_id"}, status=400)
                return
            result = release_runtime_world_state(task_id, body.get("release_reason", "task_finished"))
            self._send_json(result, status=404 if "error" in result else 200)
            return
        if path == "/runtime_world_state/query":
            task_id = body.get("task_id") or body.get("session_id") or body.get("migration_task_id")
            if not task_id:
                self._send_json({"error": "missing_task_id"}, status=400)
                return
            result = query_runtime_world_state(
                task_id,
                body.get("question", "当前杯子有没有水"),
                body.get("object_ref", "object_cup_white_mug"),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/runtime_world_state/perturb":
            task_id = body.get("task_id") or body.get("session_id") or body.get("migration_task_id") or body.get("source_task_id")
            if not task_id:
                self._send_json({"error": "missing_task_id"}, status=400)
                return
            perturbation = body.get("perturbation")
            if not isinstance(perturbation, dict):
                self._send_json({"error": "missing_perturbation_object"}, status=400)
                return
            result = inject_runtime_perturbation(task_id, perturbation, body.get("apply_before_step"))
            self._send_json(result, status=404 if "error" in result else 200)
            return
        if path == "/runtime_world_state/readapt":
            task_id = body.get("task_id") or body.get("source_task_id")
            if not task_id:
                self._send_json({"error": "missing_task_id"}, status=400)
                return
            profile = body.get("body_capability_profile")
            result = readapt_runtime_conflict(
                task_id,
                body.get("utterance", "到水源处接一杯水"),
                profile if isinstance(profile, dict) else None,
            )
            self._send_json(result, status=404 if "error" in result else 200)
            return
        if path == "/execution/dispatch":
            payload = body.get("execution_loop_payload") or body.get("payload")
            if not isinstance(payload, dict):
                self._send_json({"error": "missing_execution_loop_payload"}, status=400)
                return
            result = dispatch_execution_loop_payload(
                payload,
                body.get("executor_type", "digital_executor"),
                body.get("executor_options", {}),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/real-robot/session/start":
            result = start_real_robot_session(
                transport_type=str(body.get("transport_type", "loopback_preflight")),
                vendor_id=str(body.get("vendor_id", "")),
                calibration=body.get("calibration") if isinstance(body.get("calibration"), dict) else None,
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/real-robot/session/heartbeat":
            result = heartbeat_real_robot_session(
                str(body.get("session_id", "")),
                body.get("telemetry") if isinstance(body.get("telemetry"), dict) else None,
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/real-robot/session/mode":
            result = set_real_robot_session_mode(
                str(body.get("session_id", "")),
                str(body.get("mode", "shadow")),
                human_authorized=bool(body.get("human_authorized", False)),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/real-robot/session/dispatch":
            stage = body.get("stage")
            world_revision = body.get("world_revision")
            if not isinstance(world_revision, int) or isinstance(world_revision, bool):
                self._send_json({"error": "valid_world_revision_required"}, status=400)
                return
            result = dispatch_real_robot_stage(
                str(body.get("session_id", "")),
                stage if isinstance(stage, dict) else {},
                process_instance_id=str(body.get("process_instance_id", "")),
                world_revision=world_revision,
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/real-robot/session/emergency-stop":
            result = emergency_stop_real_robot_session(
                str(body.get("session_id", "")),
                str(body.get("reason", "operator_emergency_stop")),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/real-robot/session/reset-stop":
            result = reset_real_robot_emergency_stop(
                str(body.get("session_id", "")),
                human_authorized=bool(body.get("human_authorized", False)),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/visual-concepts/generation/request":
            result = create_generation_request(
                str(body.get("concept_id", "")),
                int(body.get("sample_count", 8)),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/concept-teaching/session/start":
            result = start_concept_teaching_session(str(body.get("concept_id", "")))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/concept-teaching/session/observe":
            result = attach_concept_observation(
                str(body.get("session_id", "")),
                observation_ref=str(body.get("observation_ref", "")),
                source_type=str(body.get("source_type", "")),
                identity_confirmed=bool(body.get("identity_confirmed", False)),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/concept-teaching/session/assess":
            result = assess_concept_invariants(
                str(body.get("session_id", "")),
                body.get("assessments") if isinstance(body.get("assessments"), list) else [],
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/concept-teaching/session/finish":
            result = finish_concept_teaching_session(str(body.get("session_id", "")))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/visual-concepts/batches/create":
            result = create_production_batch(sample_count_per_concept=int(body.get("sample_count_per_concept", 8)))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/visual-concepts/kernels/compile":
            result = compile_concept_kernel_candidate(
                str(body.get("gap_id", "")),
                body.get("proposal", {}),
                source_type=str(body.get("source_type", "external_model_candidate")),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/visual-concepts/kernels/propose-qwen":
            base_url = os.environ.get("RELL_QWEN_COMPATIBLE_BASE_URL", "")
            api_key = os.environ.get("RELL_QWEN_API_KEY", "")
            model = os.environ.get("RELL_QWEN_VISUAL_MODEL", "")
            if not base_url or not api_key or not model:
                self._send_json({"error": "qwen_visual_provider_not_configured"}, status=400)
                return
            pipeline = get_pipeline_state()
            gap_id = str(body.get("gap_id", ""))
            gap = next((item for item in pipeline["concept_gap_candidates"] if item["gap_id"] == gap_id), None)
            if not gap:
                self._send_json({"error": "visual_concept_gap_not_found", "gap_id": gap_id}, status=400)
                return
            try:
                adapter = QwenVisualConceptAdapter(base_url=base_url, api_key=api_key, model=model)
                result = adapter.propose_kernel(
                    gap,
                    [str(item) for item in body.get("image_refs", [])],
                    language_context=str(body.get("language_context", "")),
                )
            except Exception as error:
                result = {"error": "qwen_visual_candidate_request_failed", "error_type": type(error).__name__}
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/visual-concepts/kernels/review":
            result = review_concept_kernel_candidate(
                str(body.get("kernel_candidate_id", "")),
                approved=bool(body.get("approved", False)),
                reviewer_ref=str(body.get("reviewer_ref", "")),
                review_notes=str(body.get("review_notes", "")),
                functional_role_confirmed=bool(body.get("functional_role_confirmed", False)),
                physical_boundaries_confirmed=bool(body.get("physical_boundaries_confirmed", False)),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/visual-concepts/kernels/assess-observation":
            result = assess_concept_kernel_observation(
                str(body.get("kernel_candidate_id", "")),
                observation_ref=str(body.get("observation_ref", "")),
                source_type=str(body.get("source_type", "")),
                identity_confirmed=bool(body.get("identity_confirmed", False)),
                assessments=body.get("assessments") if isinstance(body.get("assessments"), list) else [],
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/visual-concepts/kernels/promote":
            result = promote_concept_kernel_candidate(str(body.get("kernel_candidate_id", "")))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/visual-concepts/kernels/release-generation":
            result = release_kernel_candidate_generation(
                str(body.get("kernel_candidate_id", "")),
                sample_count=int(body.get("sample_count", 8)),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/visual-concepts/batches/execute":
            provider_kind = str(body.get("provider", "deterministic_test"))
            if provider_kind == "deterministic_test":
                provider = DeterministicImageProvider()
            elif provider_kind == "configured_http":
                endpoint = os.environ.get("RELL_IMAGE_PROVIDER_ENDPOINT")
                if not endpoint:
                    self._send_json({"error": "image_provider_endpoint_not_configured"}, status=400)
                    return
                provider = HttpImageGenerationProvider(endpoint, os.environ.get("RELL_IMAGE_PROVIDER_AUTHORIZATION"))
            else:
                self._send_json({"error": "unsupported_image_provider", "provider": provider_kind}, status=400)
                return
            result = execute_production_batch(str(body.get("batch_id", "")), provider)
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/visual-concepts/generation/execute":
            provider_kind = str(body.get("provider", "deterministic_test"))
            if provider_kind == "deterministic_test":
                provider = DeterministicImageProvider()
            elif provider_kind == "configured_http":
                endpoint = os.environ.get("RELL_IMAGE_PROVIDER_ENDPOINT")
                if not endpoint:
                    self._send_json({"error": "image_provider_endpoint_not_configured"}, status=400)
                    return
                provider = HttpImageGenerationProvider(endpoint, os.environ.get("RELL_IMAGE_PROVIDER_AUTHORIZATION"))
            else:
                self._send_json({"error": "unsupported_image_provider", "provider": provider_kind}, status=400)
                return
            result = execute_generation_request(str(body.get("request_id", "")), provider)
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/visual-concepts/provider-result":
            images = body.get("images")
            result = ingest_provider_images(
                str(body.get("request_id", "")),
                str(body.get("provider_id", "external_image_provider")),
                images if isinstance(images, list) else [],
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/visual-concepts/calibrate":
            result = add_real_world_calibration(
                str(body.get("candidate_id", "")),
                observation_ref=str(body.get("observation_ref", "")),
                source_type=str(body.get("source_type", "")),
                matched_features=body.get("matched_features") if isinstance(body.get("matched_features"), list) else [],
                human_confirmed=bool(body.get("human_confirmed", False)),
                identity_confirmed=body.get("identity_confirmed") if isinstance(body.get("identity_confirmed"), bool) else None,
                visual_invariants_confirmed=body.get("visual_invariants_confirmed") if isinstance(body.get("visual_invariants_confirmed"), bool) else None,
                functional_facts_confirmed=bool(body.get("functional_facts_confirmed", False)),
                uncertain_features=body.get("uncertain_features") if isinstance(body.get("uncertain_features"), list) else [],
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/visual-concepts/promote":
            result = promote_visual_candidate(str(body.get("candidate_id", "")))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/physics/session/start":
            result = start_physics_session(body.get("execution_loop_payload", {}), body.get("executor_options", {}))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/embodied/session/start":
            result = start_embodied_session(
                str(body.get("executor_profile_id", "home_mobile_manipulator")),
                str(body.get("scene_id", "home_semantic_3d_a")),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/embodied/obstacle":
            result = set_embodied_stool(str(body.get("session_id", "")), str(body.get("mode", "ahead")))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/embodied/perception/scenario":
            result = set_embodied_perception_scenario(str(body.get("session_id", "")), str(body.get("mode", "normal")))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/embodied/policy":
            policy = body.get("policy_overlay")
            result = set_embodied_protection_policy(str(body.get("session_id", "")), policy if isinstance(policy, dict) else None)
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/embodied/command":
            result = execute_embodied_command(str(body.get("session_id", "")), str(body.get("utterance", "")))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/embodied/motion/start":
            result = begin_embodied_motion(str(body.get("session_id", "")), str(body.get("utterance", "")))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/embodied/motion/confirm":
            result = confirm_embodied_motion(
                str(body.get("session_id", "")),
                str(body.get("confirmation_id", "")),
                bool(body.get("approved", False)),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/embodied/motion/step":
            result = step_embodied_motion(str(body.get("job_id", "")))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/embodied/teaching/start":
            result = start_embodied_teaching_session(
                str(body.get("session_id", "")),
                str(body.get("goal_utterance", "拿杯子")),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/embodied/teaching/control":
            result = begin_embodied_teaching_control(str(body.get("session_id", "")), str(body.get("control", "")))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/embodied/teaching/signal":
            result = record_embodied_teaching_signal(
                str(body.get("session_id", "")),
                str(body.get("signal_type", "")),
                str(body.get("note", "")) or None,
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/embodied/teaching/finish":
            result = finish_embodied_teaching_session(str(body.get("session_id", "")))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/embodied/teaching/replay":
            result = begin_embodied_learned_replay(str(body.get("session_id", "")))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/embodied/teaching/evaluate":
            result = evaluate_embodied_learned_replay(
                str(body.get("session_id", "")),
                bool(body.get("accepted", False)),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/embodied/experience/replay":
            result = begin_embodied_persisted_replay(
                str(body.get("session_id", "")),
                str(body.get("experience_id", "")),
            )
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/physics/session/step":
            result = step_physics_session(str(body.get("session_id", "")))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/physics/session/perturb":
            result = perturb_physics_session(str(body.get("session_id", "")), str(body.get("obstacle", "none")))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/physics/session/interrupt":
            result = interrupt_physics_session(str(body.get("session_id", "")), str(body.get("utterance", "")))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/experience/teach":
            result = teach_experience(body.get("utterance", ""), body.get("steps", ""))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/experience/dialogue-teach":
            result = teach_experience_from_dialogue(body.get("utterance", ""), body.get("message", ""))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/teaching/session/start":
            result = start_teaching_session(body.get("utterance", ""), body.get("goal_fact"))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/teaching/session/step":
            result = execute_teaching_session_step(body.get("session_id", ""), body.get("teaching_input", body.get("step", "")))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        if path == "/teaching/session/finish":
            result = finish_teaching_session(body.get("session_id", ""), bool(body.get("success_confirmed", False)))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        self._send_json({"error": "not_found"}, status=404)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return {}
        return json.loads(raw)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_html(self, html: str, status: int = 200) -> None:
        encoded = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_javascript(self, source: str, status: int = 200) -> None:
        encoded = source.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    server = ThreadingHTTPServer((DEFAULT_HOST, DEFAULT_PORT), RellSampleHandler)
    server.daemon_threads = True
    print(f"EORLD-RELL sample API listening on http://{DEFAULT_HOST}:{DEFAULT_PORT}")
    print(f"Demo page: http://{DEFAULT_HOST}:{DEFAULT_PORT}/")
    print("Endpoints: POST /semantic/route, POST /agent/query, POST /llm/context-view, POST /llm/prompt-contract, POST /llm/candidate-intent, POST /llm/candidate/validate, POST /concept/cloud-recall, POST /concept/resolve, POST /concept/candidates/confirm, POST /process/admit, POST /process/run, POST /experience/migrate, POST /preference/record, POST /execution/dispatch, POST /runtime_world_state/query, POST /runtime_world_state/perturb, POST /teaching/session/start, GET /recovery/library, GET /recovery/task/{task_id}, GET /recovery/{recovery_id}, GET /preference/library, GET /concept/library, GET /concept/candidates, GET /audit/{task_id}")
    server.serve_forever()


if __name__ == "__main__":
    main()
