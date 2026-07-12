from __future__ import annotations

import hashlib
import json
import math
from time import perf_counter_ns
from copy import deepcopy
from pathlib import Path
from typing import Any

from concept_core.factory_event_units import FACTORY_EVENT_CONCEPT_UNITS, build_factory_inability_diagnosis, find_factory_event_concepts_by_text
from concept_core.functional_object_reasoning import build_functional_object_catalog, build_functional_profile, evaluate_role_compatibility
from concept_core.factory_state_facts import build_factory_state_catalog, derive_runtime_fact_snapshot, explain_prerequisite_gaps
from concept_core.lightweight_orchestrator import build_lightweight_causal_candidate, build_lightweight_orchestrator_catalog
from concept_core.perceptual_grounding import build_task_perception_result, load_object_concepts
from embodied_teaching import (
    append_validation_result,
    build_pedagogical_signals,
    build_teaching_authority,
    compile_demonstration_experience,
)
from teaching_observation import (
    build_live_first_person_observation_packet,
    finalize_observation_packet,
)

TEACHING_SIGNAL_TYPES = {
    "demonstration",
    "correction",
    "boundary_indication",
    "negative_example",
    "confirmation",
}


def _append_teaching_event(
    teaching: dict[str, Any],
    event_type: str,
    detail: str,
    *,
    stage: str,
    status: str = "recorded",
    world_revision: int | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    events = teaching.setdefault("teaching_events", [])
    event = {
        "sequence": len(events) + 1,
        "event_type": event_type,
        "stage": stage,
        "detail": detail,
        "status": status,
        "candidate_only": status not in {"physical_fact_verified", "trusted_experience_promoted"},
        "runtime_fact_committed": status == "physical_fact_verified",
        "world_revision": world_revision,
    }
    if evidence:
        event["evidence"] = deepcopy(evidence)
    events.append(event)
    return event
from embodied_experience_store import get_trusted_experience, load_trusted_experiences, persist_trusted_experience
from execution_boundary import (
    build_effective_execution_envelope,
    build_p2_control_decision,
    build_p2_safety_self_proof,
    build_p6_execution_receipt,
)


SCENE_FILE = Path(__file__).resolve().parent / "data" / "embodied_home_scene.json"
SESSIONS: dict[str, dict[str, Any]] = {}
MOTION_JOBS: dict[str, dict[str, Any]] = {}


def load_scene() -> dict[str, Any]:
    return json.loads(SCENE_FILE.read_text(encoding="utf-8"))


def start_session(executor_profile_id: str = "home_mobile_manipulator") -> dict[str, Any]:
    scene = load_scene()
    if executor_profile_id not in scene["executor_profiles"]:
        return {"error": "executor_profile_not_found", "executor_profile_id": executor_profile_id}
    session_id = "embodied_" + hashlib.sha1(f"{scene['scene_id']}|{len(SESSIONS) + 1}".encode()).hexdigest()[:12]
    state = deepcopy(scene["initial_state"])
    session = {
        "session_id": session_id,
        "scene_id": scene["scene_id"],
        "executor_profile_id": executor_profile_id,
        "executor_profile": scene["executor_profiles"][executor_profile_id],
        "protection_policy_overlay": None,
        "policy_revision": 0,
        "policy_runtime": {"status": "inactive", "applied_world_revision": None, "revocation_reason": None},
        "pending_confirmation": None,
        "authorization_history": [],
        "perception_history": [],
        "perception_scenario": "normal",
        "runtime_objects": deepcopy(scene["objects"]),
        "teaching_session": None,
        "learned_experience": None,
        "available_local_experiences": _experience_catalog(),
        "state": state,
        "active_obstacles": [],
        "world_revision": 0,
        "event_history": [],
    }
    SESSIONS[session_id] = session
    return deepcopy(session)


def get_session(session_id: str) -> dict[str, Any]:
    return deepcopy(SESSIONS.get(session_id) or {"error": "embodied_session_not_found", "session_id": session_id})


def _experience_catalog() -> list[dict[str, Any]]:
    return [
        {
            "experience_id": item["experience_id"],
            "status": item["status"],
            "source_goal_utterance": item.get("source_goal_utterance"),
            "goal_fact": item.get("goal_fact"),
            "target_concept_id": item.get("target_binding", {}).get("concept_id"),
            "process_chain": deepcopy(item.get("process_chain", [])),
        }
        for item in load_trusted_experiences()
    ]


def _normalize_factory_text(text: str) -> str:
    return "".join(text.strip().lower().split())


def _available_experience_capabilities(session: dict[str, Any]) -> list[str]:
    capabilities: set[str] = set()
    for experience in session.get("available_local_experiences", []):
        process = set(experience.get("process_chain", []))
        if "grasp_bound_target" in process:
            capabilities.add("grasp_object")
        if "navigate_until_target_within_reach" in process:
            capabilities.add("navigate_to_region")
    active = session.get("learned_experience") or {}
    if active.get("status") in {"candidate_pending_autonomous_replay", "trusted_local_experience"}:
        process = set(active.get("process_chain", []))
        if "grasp_bound_target" in process:
            capabilities.add("grasp_object")
        if "navigate_until_target_within_reach" in process:
            capabilities.add("navigate_to_region")
    return sorted(capabilities)


def _causal_experience_contracts(session: dict[str, Any]) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    for catalog_item in session.get("available_local_experiences", []):
        experience = get_trusted_experience(catalog_item["experience_id"])
        if not experience:
            continue
        process = set(experience.get("process_chain", []))
        if "grasp_bound_target" in process:
            capability = "grasp_object"
        elif "navigate_until_target_within_reach" in process:
            capability = "navigate_to_region"
        else:
            capability = None
        contracts.append({**experience, "required_capability": capability})
    return contracts


def _causal_registry_cache_key(experience_contracts: list[dict[str, Any]]) -> str:
    experience_versions = [
        str(item.get("integrity", {}).get("portable_contract_digest") or item.get("experience_id"))
        for item in experience_contracts
    ]
    return "factory_events_v1|" + "|".join(sorted(experience_versions))


def _ground_factory_roles(
    concept: dict[str, Any],
    session: dict[str, Any],
    perception_result: dict[str, Any] | None,
    text: str,
) -> dict[str, str]:
    grounded: dict[str, str] = {}
    bindings = (perception_result or {}).get("concept_grounding", {}).get("candidate_bindings", [])
    target = next((item for item in bindings if item.get("role") == "target"), None)
    held = session.get("state", {}).get("holding")
    roles = concept["concept_kernel"]["semantic_roles"]
    object_concepts = load_object_concepts()["concepts"]
    mentioned_entities: list[dict[str, Any]] = []
    for entity in session.get("runtime_objects", []):
        matching_concepts = [item for item in object_concepts if entity.get("kind") in item.get("compatible_kinds", [])]
        aliases = [alias for item in matching_concepts for alias in item.get("aliases", [])]
        surface_forms = [entity.get("label", ""), *aliases]
        positions = [text.find(form) for form in surface_forms if form and form in text]
        if positions:
            mentioned_entities.append({**entity, "mention_position": min(positions)})
    mentioned_entities.sort(key=lambda item: item["mention_position"])
    for role_name, template in roles.items():
        entity_type = template.get("entity_type")
        if role_name in {"object", "target", "device"} and target:
            grounded[role_name] = target.get("entity_ref")
        elif role_name in {"object", "target", "device"} and mentioned_entities:
            grounded[role_name] = mentioned_entities[0]["entity_id"]
        elif role_name in {"destination", "source"} and mentioned_entities:
            grounded[role_name] = mentioned_entities[-1]["entity_id"]
        elif entity_type == "held_object" and held:
            grounded[role_name] = held
        elif role_name == "activity" and session.get("active_motion_job_id"):
            grounded[role_name] = session["active_motion_job_id"]
    return grounded


def _evaluate_factory_role_compatibility(
    concept: dict[str, Any],
    session: dict[str, Any],
    grounded_roles: dict[str, str],
) -> list[dict[str, Any]]:
    objects = {item["entity_id"]: item for item in session.get("runtime_objects", [])}
    object_concepts = load_object_concepts()["concepts"]
    incompatible: list[dict[str, Any]] = []
    for role_name, entity_ref in grounded_roles.items():
        entity = objects.get(entity_ref)
        required_type = concept["concept_kernel"]["semantic_roles"].get(role_name, {}).get("entity_type")
        if not entity or not required_type:
            continue
        profile = build_functional_profile(entity, object_concepts)
        if session.get("state", {}).get("holding") == entity_ref:
            profile["current_relations"] = sorted(set(profile.get("current_relations", [])) | {"held_by_executor"})
        result = evaluate_role_compatibility(profile, required_type)
        if result.get("compatible") is False:
            incompatible.append({"role": role_name, **result})
    return incompatible


def _build_factory_response(
    session: dict[str, Any],
    text: str,
    concept: dict[str, Any],
    perception_result: dict[str, Any] | None,
    decision_started_ns: int,
) -> dict[str, Any]:
    concept_resolved_ns = perf_counter_ns()
    grounded_roles = _ground_factory_roles(concept, session, perception_result, text)
    fact_snapshot = derive_runtime_fact_snapshot(session, grounded_roles=grounded_roles)
    facts_derived_ns = perf_counter_ns()
    required_facts = concept["concept_kernel"]["effect_contract"].get("requires", [])
    prerequisite_analysis = explain_prerequisite_gaps(required_facts, fact_snapshot)
    supported_capabilities = list(session["executor_profile"].get("supported_actions", []))
    if session.get("executor_profile", {}).get("sensor_frames"):
        supported_capabilities.append("active_perception")
    available_experience_capabilities = _available_experience_capabilities(session)
    diagnosis = build_factory_inability_diagnosis(
        concept,
        supported_capabilities=supported_capabilities,
        available_experience_capabilities=available_experience_capabilities,
        grounded_roles=grounded_roles,
        incompatible_roles=_evaluate_factory_role_compatibility(concept, session, grounded_roles),
    )
    prompts = {
        "request_clarification": diagnosis["explanation"] + " 请指出具体对象、位置或方向。",
        "explain_role_incompatibility_and_request_alternative": diagnosis["explanation"] + " 请换一个具备所需功能的对象。",
        "explain_body_limit_and_request_compatible_body_or_help": diagnosis["explanation"] + " 可以换用具备该能力的本体，或由人协助。",
        "offer_embodied_teaching": diagnosis["explanation"] + " 你可以进入真人教学，示范一次并让我自主复做验真。",
        "request_verification_support": diagnosis["explanation"] + " 请补充可观察的成功标准或人工确认方式。",
        "reenter_orchestration": diagnosis["explanation"],
    }
    recoverable = prerequisite_analysis["recoverable_subgoals"]
    external = prerequisite_analysis["human_or_external_dependencies"]
    gap_suffix = ""
    if recoverable:
        gap_suffix += " 当前可先补：" + "；".join(item["response"] for item in recoverable[:2]) + "。"
    if external:
        gap_suffix += " 仍需外部确认：" + "；".join(item["response"] for item in external[:2]) + "。"
    experience_contracts = _causal_experience_contracts(session)
    causal_candidate = build_lightweight_causal_candidate(
        goal_concept=diagnosis,
        fact_snapshot=fact_snapshot,
        supported_capabilities=supported_capabilities,
        available_experience_capabilities=available_experience_capabilities,
        event_concepts=FACTORY_EVENT_CONCEPT_UNITS,
        experience_contracts=experience_contracts,
        registry_cache_key=_causal_registry_cache_key(experience_contracts),
    )
    decision_completed_ns = perf_counter_ns()
    causal_candidate["decision_latency"] = {
        "concept_and_role_resolution_ms": round((concept_resolved_ns - decision_started_ns) / 1_000_000, 4),
        "runtime_fact_derivation_ms": round((facts_derived_ns - concept_resolved_ns) / 1_000_000, 4),
        "diagnosis_and_orchestration_ms": round((decision_completed_ns - facts_derived_ns) / 1_000_000, 4),
        "input_to_candidate_decision_ms": round((decision_completed_ns - decision_started_ns) / 1_000_000, 4),
        "clock": "perf_counter_ns_monotonic",
    }
    if causal_candidate["candidate_process_chain"]:
        gap_suffix += " 候选因果链：" + " → ".join(causal_candidate["candidate_process_chain"]) + "。"
    return {
        "status": "factory_concept_recognized_execution_gap",
        "reason": diagnosis["reason_code"],
        "prompt": prompts[diagnosis["next_action"]] + gap_suffix,
        "factory_concept": diagnosis,
        "runtime_fact_snapshot": fact_snapshot,
        "prerequisite_analysis": prerequisite_analysis,
        "causal_candidate": causal_candidate,
        "post_action": {
            "action": diagnosis["next_action"],
            "teaching_available": diagnosis["next_action"] == "offer_embodied_teaching",
            "clarification_required": diagnosis["next_action"] == "request_clarification",
            "human_help_suggested": diagnosis["next_action"] == "explain_body_limit_and_request_compatible_body_or_help",
        },
        "perception": perception_result,
        "session": get_session(session["session_id"]),
    }


def build_factory_concept_catalog() -> dict[str, Any]:
    from concept_core.factory_event_units import FACTORY_EVENT_CONCEPT_UNITS

    return {
        "schema_version": "1.0.0",
        "catalog_type": "body_independent_factory_event_concepts",
        "concept_count": len(FACTORY_EVENT_CONCEPT_UNITS),
        "load_policy": "factory_default_for_any_executor_then_bind_current_body_profile",
        "storage_boundary": {
            "contains": ["semantic_roles", "effect_contract", "verification", "inability_response_policy"],
            "forbids": ["absolute_coordinates", "joint_angles", "fixed_duration", "single_body_trajectory"],
            "direct_execution_allowed": False,
        },
        "concepts": [
            {
                "concept_id": item["concept_id"],
                "display_name": item["display_name"],
                "operator": item["concept_kernel"]["operator"],
                "aliases": deepcopy(item["aliases"]),
                "required_capability": item["capability"],
                "semantic_roles": deepcopy(item["concept_kernel"]["semantic_roles"]),
                "effect_contract": deepcopy(item["concept_kernel"]["effect_contract"]),
                "response_policy": deepcopy(item["response_policy"]),
                "candidate_only": True,
                "direct_execution_allowed": False,
            }
            for item in FACTORY_EVENT_CONCEPT_UNITS
        ],
    }


def build_factory_object_catalog() -> dict[str, Any]:
    return build_functional_object_catalog(load_object_concepts()["concepts"])


def build_factory_state_fact_catalog() -> dict[str, Any]:
    return build_factory_state_catalog()


def build_factory_orchestrator_catalog() -> dict[str, Any]:
    return build_lightweight_orchestrator_catalog(FACTORY_EVENT_CONCEPT_UNITS)
def _command_hash(utterance: str) -> str:
    return hashlib.sha256(utterance.strip().encode("utf-8")).hexdigest()[:16]


def _policy_binding(session: dict[str, Any]) -> dict[str, Any]:
    policy = session.get("protection_policy_overlay") or {}
    return {
        "declaration_id": policy.get("declaration_id"),
        "declaration_version": policy.get("declaration_version"),
        "policy_revision": session["policy_revision"],
    }


def _revoke_pending_confirmation(session: dict[str, Any], reason: str) -> None:
    pending = session.get("pending_confirmation")
    if not pending:
        return
    session["authorization_history"].append({**deepcopy(pending), "status": "revoked", "revocation_reason": reason})
    session["pending_confirmation"] = None


def _invalidate_perception_history(session: dict[str, Any], reason: str) -> None:
    for record in session.get("perception_history", []):
        if record.get("current_use_status") == "current_candidate":
            record["current_use_status"] = "stale"
            record["invalidation_reason"] = reason


def _revoke_teaching_authority(session: dict[str, Any], reason: str) -> None:
    teaching = session.get("teaching_session") or {}
    authority = teaching.get("authority") or {}
    if teaching.get("status") != "human_control_active" or authority.get("status") != "active":
        return
    authority["status"] = "revoked"
    authority["revocation_reason"] = reason
    teaching["status"] = "teaching_authority_revoked"


def _create_pending_confirmation(session: dict[str, Any], utterance: str) -> dict[str, Any]:
    confirmation_id = "confirm_" + hashlib.sha1(
        f"{session['session_id']}|{utterance}|{session['world_revision']}|{session['policy_revision']}".encode("utf-8")
    ).hexdigest()[:12]
    pending = {
        "confirmation_id": confirmation_id,
        "status": "pending",
        "utterance": utterance,
        "command_hash": _command_hash(utterance),
        "scope": "single_execution_of_exact_command",
        "authorized_world_revision": session["world_revision"],
        "policy_binding": _policy_binding(session),
        "revocation_conditions": ["world_revision_changed", "policy_changed", "command_changed", "authorization_consumed"],
    }
    session["pending_confirmation"] = pending
    return pending


def _authorization_is_current(session: dict[str, Any], utterance: str, authorization: dict[str, Any] | None) -> bool:
    return bool(
        authorization
        and authorization.get("status") == "authorized"
        and authorization.get("command_hash") == _command_hash(utterance)
        and authorization.get("authorized_world_revision") == session["world_revision"]
        and authorization.get("policy_binding") == _policy_binding(session)
    )


def set_protection_policy(session_id: str, policy_overlay: dict[str, Any] | None) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    _revoke_pending_confirmation(session, "policy_changed")
    _invalidate_perception_history(session, "policy_revision_changed_requires_candidate_recheck")
    _revoke_teaching_authority(session, "policy_changed")
    normalized_policy = deepcopy(policy_overlay) if policy_overlay else None
    next_world_revision = session["world_revision"] + 1
    if normalized_policy:
        normalized_policy.setdefault("declaration_version", 1)
        normalized_policy.setdefault(
            "validity_window",
            {"starts": "on_application", "ends": "when_revoked_or_replaced", "applied_world_revision": next_world_revision},
        )
        normalized_policy.setdefault("revocation_conditions", ["declaration_replaced", "declaration_revoked"])
    session["protection_policy_overlay"] = normalized_policy
    session["policy_revision"] += 1
    session["world_revision"] += 1
    session["policy_runtime"] = {
        "status": "active" if normalized_policy else "revoked",
        "applied_world_revision": next_world_revision if normalized_policy else None,
        "revocation_reason": None if normalized_policy else "explicit_policy_removal",
    }
    return {
        "session": get_session(session_id),
        "effective_execution_envelope": build_effective_execution_envelope(session["executor_profile"], session["protection_policy_overlay"]),
    }


def set_stool(session_id: str, mode: str = "ahead") -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    position = session["state"]["executor_position"]
    yaw = math.radians(session["state"]["executor_yaw_deg"])
    distance = 0.75
    stool_position = [position[0] + math.cos(yaw) * distance, position[1] + math.sin(yaw) * distance]
    session["active_obstacles"] = [{"entity_id": "stool_dynamic", "position": stool_position, "mode": mode}]
    _revoke_pending_confirmation(session, "world_revision_changed")
    _invalidate_perception_history(session, "world_revision_changed")
    session["world_revision"] += 1
    return get_session(session_id)


def set_perception_scenario(session_id: str, mode: str) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    if mode not in {"normal", "multiple_cups", "occluded_cup", "relocated_cup"}:
        return {"error": "unsupported_perception_scenario", "mode": mode}
    objects = deepcopy(load_scene()["objects"])
    cup = next(item for item in objects if item["entity_id"] == "cup_a")
    if mode == "multiple_cups":
        second_cup = deepcopy(cup)
        second_cup.update(
            {
                "entity_id": "cup_b",
                "label": "浅蓝色杯子",
                "position": [4.08, -1.35],
                "color": "#d6e7ef",
                "perceptual_attributes": {"color": "light_blue"},
            }
        )
        objects.append(second_cup)
    elif mode == "occluded_cup":
        cup["occluded_from_viewpoints"] = ["head_center"]
        objects.append(
            {
                "entity_id": "occluder_panel",
                "label": "遮挡板",
                "kind": "visual_occluder",
                "region_id": "kitchen",
                "position": [3.35, -1.28],
                "elevation_m": 0.9,
                "size": [0.08, 0.62, 0.58],
                "color": "#535d64",
                "fixed": False,
            }
        )
    elif mode == "relocated_cup":
        cup["position"] = [4.25, -1.35]
    _revoke_pending_confirmation(session, "world_revision_changed")
    _invalidate_perception_history(session, f"perception_scenario_changed_to_{mode}")
    _revoke_teaching_authority(session, "target_binding_invalidated")
    session["runtime_objects"] = objects
    session["perception_scenario"] = mode
    session["world_revision"] += 1
    return {
        "status": "perception_scenario_applied",
        "mode": mode,
        "runtime_objects": deepcopy(objects),
        "session": get_session(session_id),
    }


def start_embodied_teaching(session_id: str, goal_utterance: str = "拿杯子") -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    previous_teaching = session.get("teaching_session") or {}
    if (session.get("learned_experience") or {}).get("status") == "needs_correction" and previous_teaching.get("target_initial_object_state"):
        target_initial = deepcopy(previous_teaching["target_initial_object_state"])
        session["runtime_objects"] = [
            target_initial if item["entity_id"] == target_initial["entity_id"] else item
            for item in session["runtime_objects"]
        ]
        session["state"] = deepcopy(load_scene()["initial_state"])
        session["world_revision"] += 1
    perception = build_task_perception_result(load_scene(), session, goal_utterance)
    if not perception or perception["concept_grounding"]["grounding_status"] != "spatially_grounded":
        return {
            "status": "teaching_target_grounding_required",
            "reason": "teaching_requires_unique_current_target_binding",
            "prompt": perception["prompt"] if perception else "请先说明要教我操作哪个当前对象。",
            "perception": perception,
            "session": get_session(session_id),
        }
    target = next(
        item for item in perception["concept_grounding"]["candidate_bindings"] if item["role"] == "target"
    )
    target_object = next(item for item in session["runtime_objects"] if item["entity_id"] == target["entity_ref"])
    teaching_id = "embodied_teach_" + hashlib.sha1(
        f"{session_id}|{goal_utterance}|{session['world_revision']}".encode("utf-8")
    ).hexdigest()[:12]
    pedagogical_signals = build_pedagogical_signals(signal_types=["demonstration"])
    observation_packet = build_live_first_person_observation_packet(
        teaching_id=teaching_id,
        goal_utterance=goal_utterance,
        world_revision=session["world_revision"],
        perception=perception,
        pedagogical_signals=pedagogical_signals,
    )
    session["teaching_session"] = {
        "teaching_id": teaching_id,
        "status": "human_control_active",
        "goal_utterance": goal_utterance,
        "goal_fact": "target_object_in_gripper",
        "target_entity_ref": target["entity_ref"],
        "target_concept_id": target["concept_id"],
        "target_initial_object_state": deepcopy(target_object),
        "authority": build_teaching_authority(session_id, goal_utterance, session["world_revision"]),
        "demonstrated_actions": [],
        "teaching_events": [],
        "scoped_constraint_candidates": [],
        "pedagogical_signals": pedagogical_signals,
        "observation_packet": observation_packet,
        "transient_trace_policy": "discard_raw_frames_after_invariant_compilation",
        "safety_and_policy_checks_remain_active": True,
    }
    teaching = session["teaching_session"]
    _append_teaching_event(
        teaching,
        "observation_candidate_created",
        "第一视角观测已适配为 L2 候选，不直接提交运行时事实",
        stage="observation",
        world_revision=session["world_revision"],
    )
    _append_teaching_event(
        teaching,
        "pedagogical_signal_recorded",
        "已记录正例示范信令",
        stage="teaching",
        world_revision=session["world_revision"],
        evidence={"signal_type": "demonstration"},
    )
    _append_teaching_event(
        teaching,
        "teaching_authority_granted",
        "真人临时接管教学控制；本体、安全和策略边界仍然有效",
        stage="teaching",
        world_revision=session["world_revision"],
    )
    return {
        "status": "teaching_control_granted",
        "prompt": "真人教学控制权已临时交给你。我会使用自己的本体和安全边界执行你的控制，并记录验真后的状态跃迁。",
        "teaching_session": deepcopy(session["teaching_session"]),
        "session": get_session(session_id),
    }


def record_teaching_signal(session_id: str, signal_type: str, note: str | None = None) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    teaching = session.get("teaching_session") or {}
    if teaching.get("status") != "human_control_active":
        return {"error": "teaching_session_not_active", "session": get_session(session_id)}
    if signal_type not in TEACHING_SIGNAL_TYPES:
        return {"error": "unsupported_teaching_signal", "signal_type": signal_type}

    signals = teaching.setdefault("pedagogical_signals", build_pedagogical_signals())
    signal_types = signals.setdefault("signal_types", [])
    if signal_type not in signal_types:
        signal_types.append(signal_type)
    target_experience = (session.get("learned_experience") or {}).get("experience_id")
    if signal_type == "correction" and target_experience:
        signals["target_experience_ref"] = target_experience

    evidence: dict[str, Any] = {
        "signal_type": signal_type,
        "note": (note or "").strip() or None,
        "action_index": len(teaching.get("demonstrated_actions", [])) - 1,
        "target_experience_ref": target_experience if signal_type == "correction" else None,
    }
    status = "recorded"
    detail_by_type = {
        "demonstration": "已标记当前片段为正例示范",
        "correction": "已标记当前片段为纠正候选；既有经验不会被直接覆盖",
        "boundary_indication": "已标记当前情境为边界候选；仅在当前世界版本内生效",
        "negative_example": "已标记当前情境为负例候选；不会进入正向过程链",
        "confirmation": "已记录教师确认信令；该信令不能替代自主复做和物理验真",
    }
    if signal_type in {"boundary_indication", "negative_example"}:
        actions = teaching.get("demonstrated_actions", [])
        last_action = actions[-1] if actions else None
        candidate = {
            "constraint_type": signal_type,
            "negative_constraint": evidence["note"] or (last_action or {}).get("failure_reason") or "teacher_indicated_boundary",
            "action_class": (last_action or {}).get("action_class"),
            "scope": {
                "teaching_id": teaching.get("teaching_id"),
                "world_revision": session["world_revision"],
                "executor_profile": session.get("executor_profile", {}).get("body_profile"),
            },
            "disposition": "candidate_constraint_pending_revalidation",
            "positive_process_chain_eligible": False,
        }
        teaching.setdefault("scoped_constraint_candidates", []).append(candidate)
        evidence["constraint_candidate"] = candidate
        if signal_type == "negative_example" and (not last_action or last_action.get("verified")):
            status = "pending_failed_evidence"
            detail_by_type[signal_type] = "负例信令已记录，但尚无失败动作证据；不会写入正向过程链"

    event = _append_teaching_event(
        teaching,
        "pedagogical_signal_recorded",
        detail_by_type[signal_type],
        stage="teaching",
        status=status,
        world_revision=session["world_revision"],
        evidence=evidence,
    )
    return {
        "status": "teaching_signal_recorded",
        "signal": deepcopy(event),
        "teaching_session": deepcopy(teaching),
        "session": get_session(session_id),
    }


def begin_teaching_control(session_id: str, control: str) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    teaching = session.get("teaching_session") or {}
    if teaching.get("status") != "human_control_active" or teaching.get("authority", {}).get("status") != "active":
        return {"error": "teaching_control_authority_not_active", "session": get_session(session_id)}
    if control == "grasp":
        result = _apply_verified_grasp(session, teaching["target_entity_ref"], "human_teleoperation")
        teaching["demonstrated_actions"].append(
            {
                "action_class": "grasp_target",
                "verified": result.get("status") == "fact_established",
                "requires": ["target_object_within_reach", "gripper_available"],
                "produces": ["target_object_in_gripper"],
                "destroys": ["gripper_empty", "target_object_on_support"],
                "verification": deepcopy(result.get("verification_evidence", {})),
                "failure_reason": result.get("reason"),
            }
        )
        _append_teaching_event(
            teaching,
            "teaching_action_verified" if result.get("status") == "fact_established" else "teaching_action_failed",
            "抓取动作已由当前本体执行并验真" if result.get("status") == "fact_established" else "抓取动作未通过当前物理前提",
            stage="teaching",
            status="physical_fact_verified" if result.get("status") == "fact_established" else "candidate_failure_evidence",
            world_revision=session["world_revision"],
            evidence={"action_class": "grasp_target", "terminal_fact": result.get("terminal_fact"), "reason": result.get("reason")},
        )
        result["teaching_session"] = deepcopy(teaching)
        result["session"] = get_session(session_id)
        return {"status": result["status"], "immediate_result": result, "session": get_session(session_id)}
    utterances = {
        "forward": "往前走一点",
        "backward": "往后退一点",
        "turn_left": "向左转",
        "turn_right": "向右转",
    }
    if control not in utterances:
        return {"error": "unsupported_teaching_control", "control": control}
    start_state = deepcopy(session["state"])
    started = begin_motion_command(session_id, utterances[control])
    if started.get("job_id"):
        MOTION_JOBS[started["job_id"]]["teaching_action"] = {
            "control": control,
            "start_state": start_state,
        }
    elif started.get("immediate_result"):
        teaching["demonstrated_actions"].append(
            {
                "action_class": "body_relative_rotation" if control.startswith("turn_") else "body_relative_translation",
                "verified": False,
                "failure_reason": started["immediate_result"].get("reason"),
            }
        )
    started["teaching_session"] = deepcopy(teaching)
    return started


def finish_embodied_teaching(session_id: str) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    teaching = session.get("teaching_session") or {}
    if teaching.get("status") != "human_control_active":
        return {"error": "teaching_session_not_active", "session": get_session(session_id)}
    if session["state"].get("holding") != teaching.get("target_entity_ref"):
        return {
            "status": "teaching_goal_not_verified",
            "reason": "target_object_in_gripper_not_established",
            "prompt": "当前还没有验真目标对象已在夹爪中，不能把未完成操作保存成经验。",
            "session": get_session(session_id),
        }
    teaching["observation_packet"] = finalize_observation_packet(
        teaching.get("observation_packet", {}),
        pedagogical_signals={**teaching.get("pedagogical_signals", {}), "outcome": "completed_successfully"},
    )
    experience = compile_demonstration_experience(
        teaching_id=teaching["teaching_id"],
        goal_utterance=teaching["goal_utterance"],
        target_concept_id=teaching["target_concept_id"],
        target_entity_ref=teaching["target_entity_ref"],
        demonstrated_actions=teaching["demonstrated_actions"],
        pedagogical_signals=teaching.get("pedagogical_signals"),
        world_revision=session["world_revision"],
        observation_packet=teaching.get("observation_packet"),
    )
    signal_constraints = deepcopy(teaching.get("scoped_constraint_candidates", []))
    experience["applicability_constraints"]["negative_constraints"].extend(signal_constraints)
    teaching["status"] = "demonstration_compiled"
    teaching["authority"]["status"] = "consumed"
    teaching["authority"]["revocation_reason"] = "teaching_finished"
    session["learned_experience"] = experience
    _append_teaching_event(
        teaching,
        "causal_contract_compiled",
        "已生成 requires / produces / destroys / verification 因果契约候选",
        stage="compilation",
        status="candidate_contract_compiled",
        world_revision=session["world_revision"],
        evidence={"effect_contract": experience["effect_contract"]},
    )
    _append_teaching_event(
        teaching,
        "demonstration_trace_discarded",
        "绝对坐标、按键、固定时长和单一本体轨迹未进入经验",
        stage="compilation",
        status="transient_trace_discarded",
        world_revision=session["world_revision"],
    )
    return {
        "status": "demonstration_compiled",
        "prompt": "示教已编译为经验不变量，原始按键和逐帧轨迹不会进入经验。现在可以让我从初始状态自主试做。",
        "experience": deepcopy(experience),
        "teaching_session": deepcopy(teaching),
        "session": get_session(session_id),
    }


def begin_persisted_experience_replay(session_id: str, experience_id: str) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    experience = get_trusted_experience(experience_id)
    if not experience:
        return {"error": "trusted_local_experience_not_found", "experience_id": experience_id}
    goal_utterance = str(experience.get("source_goal_utterance") or "拿杯子")
    perception = build_task_perception_result(load_scene(), session, goal_utterance)
    if not perception or perception["concept_grounding"]["grounding_status"] != "spatially_grounded":
        return {
            "status": "persisted_experience_rebinding_required",
            "reason": "current_target_could_not_be_uniquely_rebound",
            "prompt": perception["prompt"] if perception else "已学经验存在，但当前目标还没有唯一落地。",
            "perception": perception,
            "session": get_session(session_id),
        }
    target = next(
        item for item in perception["concept_grounding"]["candidate_bindings"] if item["role"] == "target"
    )
    expected_concept = experience.get("target_binding", {}).get("concept_id")
    if target.get("concept_id") != expected_concept:
        return {
            "status": "persisted_experience_rebinding_required",
            "reason": "current_target_concept_does_not_match_experience_slot",
            "session": get_session(session_id),
        }
    target_object = next(item for item in session["runtime_objects"] if item["entity_id"] == target["entity_ref"])
    loaded = deepcopy(experience)
    loaded.setdefault("validation_history", [])
    session["learned_experience"] = loaded
    session["teaching_session"] = {
        "teaching_id": "cold_start_loaded_experience",
        "status": "loaded_from_persistent_store",
        "goal_utterance": goal_utterance,
        "goal_fact": loaded["goal_fact"],
        "target_entity_ref": target["entity_ref"],
        "target_concept_id": target["concept_id"],
        "target_initial_object_state": deepcopy(target_object),
        "demonstrated_actions": [],
    }
    started = begin_learned_replay(session_id)
    started["loaded_from_persistent_store"] = True
    started["cold_start_binding"] = {
        "experience_id": experience_id,
        "target_concept_id": expected_concept,
        "current_entity_ref": target["entity_ref"],
        "observation_id": perception["perception_observation"]["observation_id"],
        "trajectory_reused": False,
    }
    started["prompt"] = "已从本地经验库载入不变量，并用当前观测重新绑定目标；不会复用示教坐标或轨迹。"
    return started


def begin_learned_replay(session_id: str) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    experience = session.get("learned_experience") or {}
    teaching = session.get("teaching_session") or {}
    if experience.get("status") not in {"candidate_pending_autonomous_replay", "needs_correction", "trusted_local_experience"}:
        return {"error": "learned_experience_not_ready_for_replay", "session": get_session(session_id)}
    trusted_replay = experience.get("status") == "trusted_local_experience"
    target_ref = teaching["target_entity_ref"]
    initial_target = deepcopy(teaching["target_initial_object_state"])
    session["runtime_objects"] = [
        initial_target if item["entity_id"] == target_ref else item
        for item in session["runtime_objects"]
    ]
    session["state"] = deepcopy(load_scene()["initial_state"])
    _invalidate_perception_history(session, "autonomous_replay_reset")
    session["world_revision"] += 1
    target = next(item for item in session["runtime_objects"] if item["entity_id"] == target_ref)
    support = next(
        (item for item in session["runtime_objects"] if item["entity_id"] == target.get("support_ref")),
        None,
    )
    if not support:
        return {"error": "replay_support_binding_missing", "target_ref": target_ref}
    radius = float(session["executor_profile"]["body_envelope"]["radius_m"])
    support_left_edge = support["position"][0] - support["size"][0] / 2
    approach = [support_left_edge - radius - 0.03, target["position"][1]]
    start = list(session["state"]["executor_position"])
    envelope = build_effective_execution_envelope(session["executor_profile"], session.get("protection_policy_overlay"))
    planning_radius = radius + envelope["effective_constraints"]["minimum_avoidance_distance_m"]
    plan = _plan_verified_motion(session, start, approach, planning_radius)
    if plan.get("outcome") != "verified":
        return {
            "status": "learned_replay_blocked",
            "reason": "current_space_cannot_bind_demonstrated_navigation_invariant",
            "plan": plan,
            "session": get_session(session_id),
        }
    frames: list[dict[str, Any]] = []
    segment_start = start
    current_yaw = float(session["state"]["executor_yaw_deg"])
    for waypoint in plan["waypoints"]:
        segment_yaw = math.degrees(math.atan2(waypoint[1] - segment_start[1], waypoint[0] - segment_start[0]))
        if abs(segment_yaw - current_yaw) > 0.1:
            frames.extend(_rotation_frames(segment_start, current_yaw, segment_yaw))
        count = max(3, int(math.dist(segment_start, waypoint) / 0.06) + 1)
        frames.extend(_with_yaw(_interpolate(segment_start, waypoint, count)[1:], segment_yaw))
        segment_start = waypoint
        current_yaw = segment_yaw
    target_yaw = math.degrees(math.atan2(target["position"][1] - approach[1], target["position"][0] - approach[0]))
    if abs(target_yaw - current_yaw) > 0.1:
        frames.extend(_rotation_frames(approach, current_yaw, target_yaw))
    _apply_speed_timing(frames, envelope["effective_constraints"]["max_linear_speed_mps"])
    job_id = "replay_" + hashlib.sha1(
        f"{session_id}|{experience['experience_id']}|{session['world_revision']}".encode("utf-8")
    ).hexdigest()[:12]
    experience["status"] = "trusted_experience_replay_running" if trusted_replay else "autonomous_replay_running"
    _append_teaching_event(
        teaching,
        "autonomous_replay_started",
        "教师控制权已撤销，机器人按不变量重新绑定当前对象并自主试做",
        stage="replay",
        status="verification_pending",
        world_revision=session["world_revision"],
        evidence={"trajectory_reused": False, "experience_id": experience["experience_id"]},
    )
    MOTION_JOBS[job_id] = {
        "job_id": job_id,
        "session_id": session_id,
        "utterance": "自主复做：拿取已绑定目标",
        "status": "running",
        "planned_world_revision": session["world_revision"],
        "planned_policy_revision": session["policy_revision"],
        "frames": frames,
        "next_frame_index": 0,
        "terminal_result": {
            "status": "learned_replay_navigation_complete",
            "route_kind": plan.get("route_kind"),
            "route_evidence": plan.get("safety_contract"),
            "frames": frames,
        },
        "post_completion": {"action": "grasp", "target_entity_ref": target_ref},
        "replay_experience_id": experience["experience_id"],
        "human_acceptance_required": not trusted_replay,
        "loaded_trusted_experience_replay": trusted_replay,
    }
    return {
        "status": "learned_replay_started",
        "job_id": job_id,
        "frame_count": len(frames),
        "prompt": "我会重新绑定当前杯子和操作台，按经验不变量自主执行；每一帧仍需通过当前碰撞和策略检查。",
        "experience": deepcopy(experience),
        "session": get_session(session_id),
    }


def evaluate_learned_replay(session_id: str, accepted: bool) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    experience = session.get("learned_experience") or {}
    teaching = session.get("teaching_session") or {}
    target_ref = teaching.get("target_entity_ref")
    replay_verified = experience.get("status") == "awaiting_human_acceptance" and session["state"].get("holding") == target_ref
    validation = {
        "physical_fact_verified": replay_verified,
        "human_accepted": bool(accepted),
        "outcome": "accepted" if replay_verified and accepted else "needs_correction",
    }
    session["learned_experience"] = append_validation_result(experience, validation)
    if replay_verified and accepted:
        session["learned_experience"]["status"] = "trusted_local_experience"
        persisted = persist_trusted_experience(session["learned_experience"])
        session["available_local_experiences"] = _experience_catalog()
        prompt = "这次自主复做通过了物理验真和你的确认，经验已晋升为本地可信经验。"
        status = "experience_learned"
        _append_teaching_event(
            teaching,
            "human_acceptance_recorded",
            "教师确认自主复做符合教学目标",
            stage="promotion",
            status="accepted",
            world_revision=session["world_revision"],
        )
        _append_teaching_event(
            teaching,
            "trusted_experience_promoted",
            "候选经验已通过自主复做、物理验真和人工验收，晋升为本地可信经验",
            stage="promotion",
            status="trusted_experience_promoted",
            world_revision=session["world_revision"],
        )
    else:
        persisted = None
        session["learned_experience"]["status"] = "needs_correction"
        prompt = "这次结果没有通过完整确认，经验保持候选状态，需要重新教学或纠正。"
        status = "teaching_correction_required"
        _append_teaching_event(
            teaching,
            "human_correction_requested",
            "本次复做未获完整验收，既有候选保留并进入纠正流程",
            stage="promotion",
            status="correction_required",
            world_revision=session["world_revision"],
        )
    return {
        "status": status,
        "prompt": prompt,
        "experience": deepcopy(session["learned_experience"]),
        "persisted_experience": deepcopy(persisted),
        "persistence": {
            "durable": persisted is not None,
            "reload_on_new_session": persisted is not None,
            "raw_teleoperation_trace_persisted": False,
        },
        "session": get_session(session_id),
    }


def _apply_verified_grasp(session: dict[str, Any], target_ref: str, source: str) -> dict[str, Any]:
    target = next((item for item in session["runtime_objects"] if item["entity_id"] == target_ref), None)
    if not target:
        return {"status": "grasp_blocked", "reason": "target_instance_not_available", "frames": []}
    profile = session["executor_profile"]
    executor_position = session["state"]["executor_position"]
    center_distance = math.dist(executor_position, target["position"])
    reachable_distance = float(profile["body_envelope"]["radius_m"]) + float(profile["arm_reach_m"])
    if center_distance > reachable_distance:
        return {
            "status": "grasp_blocked",
            "reason": "target_outside_current_reachable_workspace",
            "prompt": f"目标距离本体中心 {center_distance:.2f} 米，超过当前可达边界 {reachable_distance:.2f} 米，请先靠近。",
            "reach_evidence": {
                "center_distance_m": round(center_distance, 3),
                "reachable_distance_m": round(reachable_distance, 3),
                "executor_profile_ref": session["executor_profile_id"],
            },
            "frames": [],
        }
    if session["state"].get("holding") not in {None, target_ref}:
        return {"status": "grasp_blocked", "reason": "gripper_already_holding_incompatible_object", "frames": []}
    session["state"]["holding"] = target_ref
    target["attached_to_executor"] = True
    target["position"] = deepcopy(executor_position)
    target["elevation_m"] = 0.86
    verification = {
        "target_entity_ref": target_ref,
        "first_channel": {"source": "simulated_gripper_aperture_and_contact", "established": True},
        "second_channel": {"source": "simulated_visual_target_follows_end_effector", "established": True},
        "final_fact": "target_object_in_gripper",
        "final_fact_established": True,
        "verification_boundary": "P016_multi_channel_fact_verification",
    }
    return {
        "status": "fact_established",
        "reason": "verified_grasp_completed",
        "prompt": "夹爪接触与目标随动观测一致，已经验真目标对象在夹爪中。",
        "terminal_fact": "target_object_in_gripper",
        "verification_evidence": verification,
        "control_source": source,
        "runtime_objects": deepcopy(session["runtime_objects"]),
        "frames": [],
    }


def _record_completed_teaching_motion(session: dict[str, Any], job: dict[str, Any], result: dict[str, Any]) -> None:
    teaching = session.get("teaching_session") or {}
    if teaching.get("status") != "human_control_active":
        return
    control = job["teaching_action"]["control"]
    concept = result.get("concept", {})
    action_class = "body_relative_rotation" if control.startswith("turn_") else "body_relative_translation"
    teaching["demonstrated_actions"].append(
        {
            "action_class": action_class,
            "control_semantics": control,
            "relative_direction": concept.get("relative_direction"),
            "body_realization": concept.get("body_realization"),
            "verified": result.get("status") == "fact_established",
            "terminal_fact": result.get("terminal_fact"),
            "start_region": job["teaching_action"]["start_state"].get("active_region"),
            "end_region": session["state"].get("active_region"),
            "transient_execution_evidence": {
                "start_position": deepcopy(job["teaching_action"]["start_state"].get("executor_position")),
                "end_position": deepcopy(session["state"].get("executor_position")),
                "frame_count": len(job["frames"]),
                "persist_into_experience": False,
            },
            "failure_reason": result.get("reason") if result.get("status") != "fact_established" else None,
        }
    )
    _append_teaching_event(
        teaching,
        "teaching_action_verified" if result.get("status") == "fact_established" else "teaching_action_failed",
        "教学动作已由当前本体执行并验真" if result.get("status") == "fact_established" else "教学动作未通过当前物理或策略边界",
        stage="teaching",
        status="physical_fact_verified" if result.get("status") == "fact_established" else "candidate_failure_evidence",
        world_revision=session["world_revision"],
        evidence={"action_class": action_class, "terminal_fact": result.get("terminal_fact"), "reason": result.get("reason")},
    )


def execute_command(session_id: str, utterance: str, scoped_authorization: dict[str, Any] | None = None) -> dict[str, Any]:
    decision_started_ns = perf_counter_ns()
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    text = utterance.strip()
    perception_result = build_task_perception_result(load_scene(), session, text)
    factory_matches = find_factory_event_concepts_by_text(_normalize_factory_text(text))
    if factory_matches:
        concept = factory_matches[0]
        native_relative_motion = concept["concept_id"] == "factory_event_orient" or (
            concept["concept_id"] == "factory_event_navigate" and _relative_direction(text)
        )
        existing_supported_task = bool(
            perception_result
            and perception_result.get("concept_grounding", {}).get("grounding_status") in {
                "spatially_grounded",
                "perception_candidates_available",
                "active_perception_required",
            }
        )
        if not native_relative_motion and not existing_supported_task:
            return _build_factory_response(session, text, concept, perception_result, decision_started_ns)
    if perception_result:
        _invalidate_perception_history(session, "superseded_by_new_task_observation")
        session["perception_history"].append(
            {
                "utterance": text,
                "observation_id": perception_result["perception_observation"]["observation_id"],
                "grounding_status": perception_result["concept_grounding"]["grounding_status"],
                "candidate_bindings": deepcopy(perception_result["concept_grounding"]["candidate_bindings"]),
                "candidate_options": deepcopy(perception_result["concept_grounding"]["candidate_options"]),
                "active_perception_trace": deepcopy(perception_result["active_perception_trace"]),
                "world_revision": session["world_revision"],
                "runtime_fact_committed": False,
                "current_use_status": "current_candidate",
            }
        )
        perception_result["session"] = get_session(session_id)
        return perception_result
    direction = _relative_direction(text)
    if not direction:
        return {
            "status": "factory_concept_gap",
            "reason": "no_stable_factory_event_concept_match",
            "prompt": "我还不能把这句话稳定映射到一个客观状态跃迁，因此不知道成功后世界应发生什么变化。请说明要改变哪个对象的什么状态，或进入真人教学示范一次。",
            "concept_gap": {
                "utterance": text,
                "understanding_status": "operator_and_goal_fact_unknown",
                "known_state_transition": None,
                "missing_information": ["target_entity_or_activity", "expected_postcondition", "verification_condition"],
                "next_actions": ["request_goal_clarification", "offer_embodied_teaching"],
                "candidate_only": True,
                "direct_execution_allowed": False,
            },
            "post_action": {
                "action": "request_goal_clarification_or_offer_embodied_teaching",
                "teaching_available": True,
                "clarification_required": True,
            },
            "session": get_session(session_id),
        }
    rotation_only = direction in {"left", "right"} and "转" in text and not any(token in text for token in ("走", "移动", "前进", "后退"))
    continuous = any(token in text for token in ("一直", "持续", "不停")) and not rotation_only
    distance = 0.0 if rotation_only else (8.0 if continuous else (0.35 if "一点" in text else 0.7))
    start = list(session["state"]["executor_position"])
    profile = session["executor_profile"]
    effective_envelope = build_effective_execution_envelope(profile, session.get("protection_policy_overlay"))
    effective_constraints = effective_envelope["effective_constraints"]
    p2_decision = build_p2_control_decision(
        utterance=text,
        continuous_motion=continuous,
        effective_envelope=effective_envelope,
        world_revision=session["world_revision"],
        expected_effect="body_relative_rotation" if rotation_only else "body_relative_displacement",
        scoped_authorization=scoped_authorization if _authorization_is_current(session, text, scoped_authorization) else None,
    )
    if p2_decision["control_decision"] == "require_confirmation":
        pending = _create_pending_confirmation(session, text)
        result = {
            "status": "requires_human_confirmation",
            "reason": "P6_motion_policy_requires_confirmation_for_continuous_motion",
            "prompt": "当前保护策略要求持续运动前先确认，可以继续吗？",
            "pending_confirmation": deepcopy(pending),
            "effective_execution_envelope": effective_envelope,
            "p2_control_decision": p2_decision,
            "p6_execution_receipt": build_p6_execution_receipt(session.get("protection_policy_overlay"), effective_envelope, "requires_human_confirmation"),
            "frames": [],
            "session": get_session(session_id),
        }
        return result
    body_yaw = float(session["state"]["executor_yaw_deg"])
    if direction == "right":
        motion_yaw = body_yaw - 90.0
        final_yaw = motion_yaw
        body_realization = "clockwise_rotation_in_place" if rotation_only else "clockwise_turn_then_forward"
    elif direction == "left":
        motion_yaw = body_yaw + 90.0
        final_yaw = motion_yaw
        body_realization = "counterclockwise_rotation_in_place" if rotation_only else "counterclockwise_turn_then_forward"
    elif direction == "backward":
        motion_yaw = body_yaw + 180.0
        final_yaw = body_yaw
        body_realization = "reverse_without_turning"
    else:
        motion_yaw = body_yaw
        final_yaw = body_yaw
        body_realization = "forward_drive"
    body_explanations = {
        "clockwise_rotation_in_place": "这是纯转向指令，我会原地向右转，不向前或向后移动。",
        "counterclockwise_rotation_in_place": "这是纯转向指令，我会原地向左转，不向前或向后移动。",
        "clockwise_turn_then_forward": "我的底盘不能横向平移，因此会先向右转，再沿新的前方移动。",
        "counterclockwise_turn_then_forward": "我的底盘不能横向平移，因此会先向左转，再沿新的前方移动。",
        "reverse_without_turning": "我的底盘支持倒车，因此会保持当前朝向向后移动。",
        "forward_drive": "我会沿自己的当前朝向向前移动。",
    }
    yaw = math.radians(motion_yaw)
    target = [start[0] + math.cos(yaw) * distance, start[1] + math.sin(yaw) * distance]
    rotation_frames = _rotation_frames(start, body_yaw, final_yaw) if final_yaw != body_yaw else []
    planning_radius = effective_constraints["body_radius_m"] + effective_constraints["minimum_avoidance_distance_m"]
    motion_plan = _plan_verified_motion(session, start, target, planning_radius)
    collision = motion_plan.get("blocking_collision")
    obstacle = collision["obstacle"] if collision else None
    frames: list[dict[str, Any]] = []
    route_kind = "in_place_rotation" if rotation_only else "direct"
    if obstacle:
        if obstacle.get("obstacle_class") in {"fixed_furniture", "scene_boundary"}:
            safe_target = collision["safe_position"]
            frames = rotation_frames + _with_yaw(
                _interpolate(start, safe_target, max(2, min(80, int(math.dist(start, safe_target) / 0.05) + 1))),
                final_yaw,
            )
            _apply_speed_timing(frames, effective_constraints["max_linear_speed_mps"])
            session["state"]["executor_position"] = safe_target
            session["state"]["executor_yaw_deg"] = final_yaw
            session["state"]["active_region"] = _region_for(safe_target, load_scene())
            result = {
                "status": "stopped_by_physical_obstacle",
                "reason": "body_envelope_contact_with_fixed_scene_geometry",
                "prompt": f"前方是{obstacle['label']}，本体无法继续前进，已在接触前停止。",
                "obstacle": obstacle,
                "contact_evidence": {
                    "detector": "swept_body_envelope",
                    "body_radius_m": profile["body_envelope"]["radius_m"],
                    "motion_terminated_before_penetration": True,
                    "safe_position_is_transient_execution_state": True
                },
                "effective_execution_envelope": effective_envelope,
                "p2_control_decision": p2_decision,
                "frames": frames,
                "terminal_fact": "forward_motion_blocked_by_physical_geometry",
                "session": get_session(session_id),
            }
            result["p2_safety_self_proof"] = build_p2_safety_self_proof(
                safety_action="stop_before_fixed_geometry",
                expected_safe_state={"motion_stopped": True, "penetration": False},
                observed_state={"motion_stopped": True, "penetration": False},
            )
            result["p6_execution_receipt"] = build_p6_execution_receipt(session.get("protection_policy_overlay"), effective_envelope, result["status"])
            session["event_history"].append({"utterance": text, "result": result["status"], "reason": result["reason"], "obstacle": obstacle["entity_id"]})
            return result
        detour_path = motion_plan.get("waypoints")
        if obstacle.get("mode") == "narrow" or detour_path is None:
            result = {
                "status": "requires_human_confirmation",
                "reason": "obstacle_blocks_route_and_no_body_clearance",
                "prompt": "前方凳子无法安全绕开，可以把凳子搬走吗？",
                "obstacle": obstacle,
                "body_constraint": profile["body_envelope"],
                "effective_execution_envelope": effective_envelope,
                "p2_control_decision": p2_decision,
                "frames": [],
                "session": get_session(session_id),
            }
            result["p6_execution_receipt"] = build_p6_execution_receipt(session.get("protection_policy_overlay"), effective_envelope, result["status"])
            session["event_history"].append({"utterance": text, "result": result["status"], "reason": result["reason"]})
            return result
        route_kind = "local_detour"
        frames.extend(rotation_frames)
        route_start = start
        for waypoint in detour_path:
            frames.extend(_with_yaw(_interpolate(route_start, waypoint, 8)[1:], final_yaw))
            route_start = waypoint
        target = detour_path[-1]
    else:
        frames = rotation_frames + _with_yaw(_interpolate(start, target, 12), final_yaw)
    session["state"]["executor_position"] = target
    session["state"]["executor_yaw_deg"] = final_yaw
    session["state"]["active_region"] = _region_for(target, load_scene())
    body_explanation = body_explanations[body_realization]
    if route_kind == "local_detour":
        body_explanation = "我检测到前方凳子，已按本体净空从侧面绕行，并完全越过障碍后回到原行进方向。"
    _apply_speed_timing(frames, effective_constraints["max_linear_speed_mps"])
    result = {
        "status": "fact_established",
        "concept": {
            "concept_id": "body_relative_motion",
            "reference_frame": "executor_heading",
            "relative_direction": direction,
            "body_realization": body_realization,
            "kinematic_model": profile.get("kinematic_model"),
            "lateral_translation_used": False,
            "distance_class": "rotation_only" if rotation_only else ("continuous_until_termination" if continuous else ("small_increment" if distance == 0.35 else "normal_increment")),
            "learnable_invariant": "resolve_relative_direction_in_body_frame_then_select_motion_allowed_by_body_kinematics"
        },
        "route_kind": route_kind,
        "route_evidence": {
            "requested_distance_m": distance,
            "terminal_policy": "requested_rotation" if rotation_only else ("clear_entire_obstacle_body_envelope_before_returning_to_travel_axis" if route_kind == "local_detour" else "requested_relative_displacement"),
            "detour_extended_goal_for_clearance": route_kind == "local_detour",
            "motion_safety_contract": motion_plan.get("safety_contract"),
            "selected_detour_side": motion_plan.get("selected_detour_side"),
            "rejected_alternatives": motion_plan.get("rejected_alternatives", []),
        },
        "body_self_judgment": {
            "explanation": body_explanation,
            "selected_realization": body_realization,
            "rejected_realization": "lateral_translation" if direction in {"left", "right"} and not rotation_only else None,
            "portrait_basis": session["executor_profile_id"],
        },
        "effective_execution_envelope": effective_envelope,
        "p2_control_decision": p2_decision,
        "frames": frames,
        "terminal_fact": "executor_heading_changed" if rotation_only else "executor_relative_displacement_reached",
        "session": get_session(session_id),
    }
    result["p6_execution_receipt"] = build_p6_execution_receipt(session.get("protection_policy_overlay"), effective_envelope, result["status"])
    session["event_history"].append({"utterance": text, "result": result["status"], "route_kind": route_kind})
    return result


def begin_motion_command(session_id: str, utterance: str, scoped_authorization: dict[str, Any] | None = None) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    before = deepcopy(session)
    result = execute_command(session_id, utterance, scoped_authorization)
    pending_confirmation = deepcopy(SESSIONS[session_id].get("pending_confirmation"))
    perception_history = deepcopy(SESSIONS[session_id].get("perception_history", []))
    SESSIONS[session_id] = before
    frames = result.get("frames", [])
    if not frames:
        if pending_confirmation:
            SESSIONS[session_id]["pending_confirmation"] = pending_confirmation
        if result.get("task_perception_frame"):
            SESSIONS[session_id]["perception_history"] = perception_history
        result["session"] = get_session(session_id)
        return {"status": result.get("status"), "immediate_result": result, "session": get_session(session_id)}
    job_id = "motion_" + hashlib.sha1(f"{session_id}|{len(MOTION_JOBS) + 1}".encode()).hexdigest()[:12]
    job = {
        "job_id": job_id,
        "session_id": session_id,
        "utterance": utterance,
        "status": "running",
        "planned_world_revision": before["world_revision"],
        "planned_policy_revision": before["policy_revision"],
        "frames": frames,
        "next_frame_index": 0,
        "terminal_result": result,
    }
    MOTION_JOBS[job_id] = job
    return {
        "status": "motion_started",
        "job_id": job_id,
        "planned_world_revision": job["planned_world_revision"],
        "planned_policy_revision": job["planned_policy_revision"],
        "frame_count": len(frames),
        "body_self_judgment": result.get("body_self_judgment"),
        "route_evidence": result.get("route_evidence"),
        "session": get_session(session_id),
    }


def confirm_pending_motion(session_id: str, confirmation_id: str, approved: bool) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    pending = session.get("pending_confirmation")
    if not pending or pending.get("confirmation_id") != confirmation_id:
        return {
            "status": "confirmation_not_current",
            "reason": "confirmation_missing_revoked_or_replaced",
            "session": get_session(session_id),
        }
    if not approved:
        session["authorization_history"].append({**deepcopy(pending), "status": "denied"})
        session["pending_confirmation"] = None
        return {
            "status": "execution_denied",
            "reason": "human_declined_scoped_execution",
            "prompt": "好的，本次持续运动已取消。",
            "session": get_session(session_id),
        }
    if pending["authorized_world_revision"] != session["world_revision"] or pending["policy_binding"] != _policy_binding(session):
        _revoke_pending_confirmation(session, "authorization_context_changed")
        return {
            "status": "confirmation_not_current",
            "reason": "world_or_policy_context_changed_before_confirmation",
            "prompt": "环境或保护策略已经变化，需要按当前状态重新判断。",
            "session": get_session(session_id),
        }
    authorization = {
        **deepcopy(pending),
        "authorization_id": "auth_" + pending["confirmation_id"].removeprefix("confirm_"),
        "status": "authorized",
    }
    result = begin_motion_command(session_id, pending["utterance"], authorization)
    session = SESSIONS[session_id]
    session["pending_confirmation"] = None
    consumed = {**authorization, "status": "consumed", "consumed_by": result.get("job_id") or "immediate_execution_attempt"}
    session["authorization_history"].append(consumed)
    result["scoped_authorization"] = deepcopy(consumed)
    result["session"] = get_session(session_id)
    if result.get("immediate_result"):
        result["immediate_result"]["session"] = get_session(session_id)
        result["immediate_result"]["scoped_authorization"] = deepcopy(consumed)
    return result


def step_motion_command(job_id: str) -> dict[str, Any]:
    job = MOTION_JOBS.get(job_id)
    if not job:
        return {"error": "motion_job_not_found", "job_id": job_id}
    if job["status"] != "running":
        return {"error": "motion_job_not_running", "status": job["status"], "job_id": job_id}
    session = SESSIONS[job["session_id"]]
    if session["world_revision"] != job["planned_world_revision"] or session["policy_revision"] != job["planned_policy_revision"]:
        job["status"] = "invalidated_by_world_change"
        if job.get("replay_experience_id"):
            experience = session.get("learned_experience") or {}
            experience["status"] = "trusted_local_experience" if job.get("loaded_trusted_experience_replay") else "candidate_pending_autonomous_replay"
            result = {
                "status": "learned_replay_invalidated",
                "reason": "runtime_world_or_policy_revision_changed",
                "prompt": "自主复做期间环境或策略发生变化，旧计划已在最后验真位置终止；需要重新绑定后再试。",
                "frames": [],
                "experience": deepcopy(experience),
                "session": get_session(job["session_id"]),
            }
            return {"status": "motion_completed", "job_id": job_id, "result": result, "session": get_session(job["session_id"])}
        replacement = begin_motion_command(job["session_id"], job["utterance"])
        reason = "runtime_policy_revision_changed" if session["policy_revision"] != job["planned_policy_revision"] else "runtime_world_revision_changed"
        return {
            "status": "path_invalidated_and_replanned",
            "reason": reason,
            "old_job_id": job_id,
            "old_revision": job["planned_world_revision"],
            "new_revision": session["world_revision"],
            "old_policy_revision": job["planned_policy_revision"],
            "new_policy_revision": session["policy_revision"],
            "replacement": replacement,
        }
    frame = job["frames"][job["next_frame_index"]]
    radius = session["executor_profile"]["body_envelope"]["radius_m"]
    collider = _collider_at(frame["position"], radius, session, load_scene())
    if collider:
        job["status"] = "invalidated_by_contact"
        if job.get("replay_experience_id"):
            experience = session.get("learned_experience") or {}
            experience["status"] = "trusted_local_experience" if job.get("loaded_trusted_experience_replay") else "candidate_pending_autonomous_replay"
            result = {
                "status": "learned_replay_invalidated",
                "reason": "next_replay_frame_swept_body_not_clear",
                "prompt": "自主复做的下一帧不再安全，已经停在最后验真位置，需要重新观察和绑定。",
                "blocking_obstacle": collider,
                "frames": [],
                "experience": deepcopy(experience),
                "session": get_session(job["session_id"]),
            }
            return {"status": "motion_completed", "job_id": job_id, "result": result, "session": get_session(job["session_id"])}
        replacement = begin_motion_command(job["session_id"], job["utterance"])
        return {
            "status": "path_invalidated_and_replanned",
            "reason": "next_frame_swept_body_not_clear",
            "old_job_id": job_id,
            "blocking_obstacle": collider,
            "replacement": replacement,
        }
    session["state"]["executor_position"] = list(frame["position"])
    if frame.get("yaw_deg") is not None:
        session["state"]["executor_yaw_deg"] = frame["yaw_deg"]
    session["state"]["active_region"] = _region_for(frame["position"], load_scene())
    job["next_frame_index"] += 1
    if job["next_frame_index"] < len(job["frames"]):
        return {
            "status": "frame_verified_and_committed",
            "job_id": job_id,
            "frame": frame,
            "next_frame_index": job["next_frame_index"],
            "world_revision": session["world_revision"],
            "session": get_session(job["session_id"]),
        }
    job["status"] = "completed"
    result = deepcopy(job["terminal_result"])
    if job.get("teaching_action"):
        _record_completed_teaching_motion(session, job, result)
    if job.get("post_completion", {}).get("action") == "grasp":
        result = _apply_verified_grasp(
            session,
            job["post_completion"]["target_entity_ref"],
            "autonomous_learned_experience_replay",
        )
        experience = session.get("learned_experience") or {}
        replay_validation = {
            "replay_job_id": job_id,
            "physical_fact_verified": result.get("status") == "fact_established",
            "terminal_fact": result.get("terminal_fact"),
            "world_revision": session["world_revision"],
            "human_acceptance_pending": bool(job.get("human_acceptance_required", True)),
            "loaded_from_persistent_store": bool(job.get("loaded_trusted_experience_replay")),
        }
        session["learned_experience"] = append_validation_result(experience, replay_validation)
        _append_teaching_event(
            session.get("teaching_session") or {},
            "physical_verification_passed" if result.get("status") == "fact_established" else "physical_verification_failed",
            "P016 已验真目标物体进入夹爪" if result.get("status") == "fact_established" else "自主复做未建立目标物理事实",
            stage="verification",
            status="physical_fact_verified" if result.get("status") == "fact_established" else "correction_required",
            world_revision=session["world_revision"],
            evidence={"terminal_fact": result.get("terminal_fact"), "verification": result.get("verification_evidence")},
        )
        if result.get("status") == "fact_established" and not job.get("human_acceptance_required", True):
            session["learned_experience"]["status"] = "trusted_local_experience"
        else:
            session["learned_experience"]["status"] = (
                "awaiting_human_acceptance" if result.get("status") == "fact_established" else "needs_correction"
            )
        result["experience"] = deepcopy(session["learned_experience"])
        if result.get("status") == "fact_established" and not job.get("human_acceptance_required", True):
            result["prompt"] = "我已按冷启动加载的可信经验重新绑定当前目标，并完成物理事实验真。"
            result["loaded_from_persistent_store"] = True
        else:
            result["prompt"] = (
                "我已按新绑定自主完成导航和抓取，物理事实已验真。请判断这次是否符合你的教学目标。"
                if result.get("status") == "fact_established"
                else "自主复做没有建立目标事实，需要重新教学或纠正。"
            )
    result["session"] = get_session(job["session_id"])
    session["event_history"].append({"utterance": job["utterance"], "result": result.get("status"), "route_kind": result.get("route_kind")})
    return {"status": "motion_completed", "job_id": job_id, "frame": frame, "result": result, "session": get_session(job["session_id"])}


def _first_collision(session: dict[str, Any], start: list[float], target: list[float], radius: float) -> dict[str, Any] | None:
    scene = load_scene()
    distance = math.dist(start, target)
    sample_count = max(2, int(distance / 0.04) + 1)
    previous = list(start)
    for index in range(1, sample_count):
        ratio = index / (sample_count - 1)
        point = [start[0] + (target[0] - start[0]) * ratio, start[1] + (target[1] - start[1]) * ratio]
        collider = _collider_at(point, radius, session, scene)
        if collider:
            return {"obstacle": collider, "contact_position": point, "safe_position": previous}
        previous = point
    return None


def _plan_verified_motion(
    session: dict[str, Any],
    start: list[float],
    target: list[float],
    radius: float,
) -> dict[str, Any]:
    safety_contract = {
        "planner_world_revision": session["world_revision"],
        "all_segments_swept_volume_verified": True,
        "terminal_pose_verified": False,
        "execution_must_recheck_world_revision": True,
        "unverified_path_never_becomes_executable_fact": True,
    }
    direct_collision = _first_collision(session, start, target, radius)
    if not direct_collision:
        safety_contract["terminal_pose_verified"] = _collider_at(target, radius, session, load_scene()) is None
        return {"outcome": "verified", "route_kind": "direct", "waypoints": [target], "safety_contract": safety_contract}
    obstacle = direct_collision["obstacle"]
    if obstacle.get("obstacle_class") != "movable_obstacle" or obstacle.get("mode") == "narrow":
        return {"outcome": "blocked", "route_kind": "none", "blocking_collision": direct_collision, "safety_contract": safety_contract}
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for side_name, side_sign in (("left", 1.0), ("right", -1.0)):
        waypoints = _detour_candidate(start, target, obstacle, radius, side_sign)
        segment_start = start
        rejection = None
        for segment_index, waypoint in enumerate(waypoints):
            collision = _first_collision(session, segment_start, waypoint, radius)
            if collision:
                rejection = {"side": side_name, "segment_index": segment_index, "blocking_obstacle": collision["obstacle"]}
                break
            segment_start = waypoint
        if rejection:
            rejected.append(rejection)
            continue
        if _collider_at(waypoints[-1], radius, session, load_scene()):
            rejected.append({"side": side_name, "reason": "terminal_pose_not_clear"})
            continue
        route_length = sum(math.dist(a, b) for a, b in zip([start] + waypoints[:-1], waypoints))
        candidates.append({"side": side_name, "waypoints": waypoints, "route_length": route_length})
    if not candidates:
        return {
            "outcome": "blocked",
            "route_kind": "none",
            "blocking_collision": direct_collision,
            "rejected_alternatives": rejected,
            "safety_contract": safety_contract,
        }
    selected = min(candidates, key=lambda item: item["route_length"])
    safety_contract["terminal_pose_verified"] = True
    return {
        "outcome": "verified",
        "route_kind": "local_detour",
        "waypoints": selected["waypoints"],
        "selected_detour_side": selected["side"],
        "rejected_alternatives": rejected,
        "blocking_collision": direct_collision,
        "safety_contract": safety_contract,
    }


def _collider_at(point: list[float], radius: float, session: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any] | None:
    x, y = point
    if x - radius < -5.0 or x + radius > 5.0 or y - radius < -2.3 or y + radius > 2.3:
        return {"entity_id": "home_wall_boundary", "label": "墙体", "obstacle_class": "scene_boundary", "fixed": True}
    for item in scene["objects"]:
        if not item.get("fixed"):
            continue
        ox, oy = item["position"]
        sx, sy = item["size"][:2]
        if abs(x - ox) <= sx / 2 + radius and abs(y - oy) <= sy / 2 + radius:
            return {
                "entity_id": item["entity_id"],
                "label": item["label"],
                "kind": item["kind"],
                "obstacle_class": "fixed_furniture",
                "fixed": True,
            }
    for obstacle in session["active_obstacles"]:
        ox, oy = obstacle["position"]
        if math.hypot(x - ox, y - oy) <= radius + 0.38:
            return {**obstacle, "label": "凳子", "obstacle_class": "movable_obstacle", "fixed": False}
    return None


def _detour_candidate(
    start: list[float],
    target: list[float],
    obstacle: dict[str, Any],
    radius: float,
    side_sign: float,
) -> list[list[float]]:
    ox, oy = obstacle["position"]
    dx, dy = target[0] - start[0], target[1] - start[1]
    length = math.hypot(dx, dy) or 1.0
    forward = [dx / length, dy / length]
    side = [-forward[1] * side_sign, forward[0] * side_sign]
    longitudinal_clearance = radius + 0.46
    lateral_clearance = radius + 0.58
    before = [ox - forward[0] * longitudinal_clearance + side[0] * lateral_clearance, oy - forward[1] * longitudinal_clearance + side[1] * lateral_clearance]
    after_side = [ox + forward[0] * longitudinal_clearance + side[0] * lateral_clearance, oy + forward[1] * longitudinal_clearance + side[1] * lateral_clearance]
    after_axis = [ox + forward[0] * longitudinal_clearance, oy + forward[1] * longitudinal_clearance]
    return [before, after_side, after_axis]


def _interpolate(start: list[float], target: list[float], count: int) -> list[dict[str, Any]]:
    return [
        {"progress": index / (count - 1), "position": [start[0] + (target[0] - start[0]) * index / (count - 1), start[1] + (target[1] - start[1]) * index / (count - 1)]}
        for index in range(count)
    ]


def _with_yaw(frames: list[dict[str, Any]], yaw_deg: float) -> list[dict[str, Any]]:
    return [{**frame, "yaw_deg": yaw_deg} for frame in frames]


def _apply_speed_timing(frames: list[dict[str, Any]], max_speed_mps: float) -> None:
    previous = None
    for frame in frames:
        distance = math.dist(previous, frame["position"]) if previous is not None else 0.0
        frame["duration_ms"] = 45 if distance == 0 else max(25, min(300, round(distance / max_speed_mps * 1000)))
        previous = frame["position"]


def _rotation_frames(position: list[float], start_yaw: float, target_yaw: float) -> list[dict[str, Any]]:
    return [
        {"progress": index / 7, "position": list(position), "yaw_deg": start_yaw + (target_yaw - start_yaw) * index / 7}
        for index in range(1, 8)
    ]


def _relative_direction(text: str) -> str | None:
    if any(token in text for token in ("右边", "右侧", "向右", "往右")):
        return "right"
    if any(token in text for token in ("左边", "左侧", "向左", "往左")):
        return "left"
    if any(token in text for token in ("后边", "后面", "向后", "往后", "后退")):
        return "backward"
    if any(token in text for token in ("前边", "前面", "向前", "往前", "前进")):
        return "forward"
    return None


def _region_for(position: list[float], scene: dict[str, Any]) -> str:
    for region in scene["semantic_regions"]:
        cx, cy = region["center"]
        sx, sy = region["size"]
        if abs(position[0] - cx) <= sx / 2 and abs(position[1] - cy) <= sy / 2:
            return region["region_id"]
    return "transition_space"


def _point_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))
