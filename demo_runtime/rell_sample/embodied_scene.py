from __future__ import annotations

import hashlib
import json
import math
import re
from time import perf_counter_ns
from copy import deepcopy
from pathlib import Path
from typing import Any

from concept_core.factory_event_units import FACTORY_EVENT_CONCEPT_UNITS, build_factory_inability_diagnosis, find_factory_event_concepts_by_text
from concept_core.concept_gap_dialogue import continue_concept_gap_dialogue, start_concept_gap_dialogue
from concept_core.contextual_affordance import resolve_contextual_affordance_request
from concept_core.functional_object_reasoning import build_functional_object_catalog, build_functional_profile, evaluate_role_compatibility
from concept_core.factory_state_facts import build_factory_state_catalog, derive_runtime_fact_snapshot, explain_prerequisite_gaps
from concept_core.lightweight_orchestrator import build_lightweight_causal_candidate, build_lightweight_orchestrator_catalog
from concept_core.perceptual_grounding import activate_task_perception, build_open_world_observation, build_task_perception_result, load_object_concepts
from concept_core.visual_concept_packs import build_visual_pack_catalog
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


SCENE_FILES = {
    "home_semantic_3d_a": Path(__file__).resolve().parent / "data" / "embodied_home_scene.json",
    "home_semantic_3d_b": Path(__file__).resolve().parent / "data" / "embodied_home_scene_b.json",
}
SESSIONS: dict[str, dict[str, Any]] = {}
MOTION_JOBS: dict[str, dict[str, Any]] = {}


def load_scene(scene_id: str = "home_semantic_3d_a") -> dict[str, Any]:
    scene_file = SCENE_FILES.get(scene_id)
    if not scene_file:
        raise ValueError(f"unknown_embodied_scene:{scene_id}")
    return json.loads(scene_file.read_text(encoding="utf-8"))


def list_embodied_scenes() -> list[dict[str, Any]]:
    return [
        {
            "scene_id": scene_id,
            "display_name": load_scene(scene_id)["display_name"],
            "scene_role": "training_source" if scene_id.endswith("_a") else "unfamiliar_generalization_target",
        }
        for scene_id in SCENE_FILES
    ]


def _scene_for_session(session: dict[str, Any]) -> dict[str, Any]:
    return load_scene(str(session.get("scene_id") or "home_semantic_3d_a"))


def _manipulator_channels(session: dict[str, Any]) -> list[dict[str, Any]]:
    channels = session.get("executor_profile", {}).get("manipulator_channels", [])
    return channels or [{"channel_id": "primary_gripper", "side": "center"}]


def _holding_by_effector(session: dict[str, Any]) -> dict[str, str | None]:
    state = session["state"]
    holding = state.setdefault("holding_by_effector", {item["channel_id"]: None for item in _manipulator_channels(session)})
    for item in _manipulator_channels(session):
        holding.setdefault(item["channel_id"], None)
    return holding


def _sync_primary_holding(session: dict[str, Any]) -> None:
    holding = _holding_by_effector(session)
    session["state"]["holding"] = next((ref for ref in holding.values() if ref), None)


def _held_effector(session: dict[str, Any], object_ref: str) -> str | None:
    return next((channel for channel, ref in _holding_by_effector(session).items() if ref == object_ref), None)


def _is_held(session: dict[str, Any], object_ref: str) -> bool:
    return _held_effector(session, object_ref) is not None


def _available_effector(session: dict[str, Any]) -> str | None:
    return next((channel for channel, ref in _holding_by_effector(session).items() if ref is None), None)


def start_session(executor_profile_id: str = "home_mobile_manipulator", scene_id: str = "home_semantic_3d_a") -> dict[str, Any]:
    try:
        scene = load_scene(scene_id)
    except ValueError:
        return {"error": "embodied_scene_not_found", "scene_id": scene_id, "available_scenes": list_embodied_scenes()}
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
        "concept_gap_dialogue": None,
        "open_world_observation": None,
        "confirmed_visual_bindings": [],
        "long_horizon_intents": {},
        "active_intent_id": None,
        "intent_activation_stack": [],
    }
    _holding_by_effector(session)
    _sync_primary_holding(session)
    SESSIONS[session_id] = session
    return deepcopy(session)


def _long_intent_view(intent: dict[str, Any]) -> dict[str, Any]:
    return {
        "intent_id": intent["intent_id"],
        "goal_fact": intent["goal_fact"],
        "role_bindings": deepcopy(intent["role_bindings"]),
        "lifecycle": intent["lifecycle"],
        "verified_facts": list(intent["verified_facts"]),
        "current_stage": deepcopy(intent.get("current_stage")),
        "resume_envelope": deepcopy(intent.get("resume_envelope")),
        "trajectory_persisted": False,
    }


def _conceptual_reference_for_entity(entity: dict[str, Any]) -> str:
    """Use a concept alias in derived stages, never an incidental visual label."""
    for concept in load_object_concepts()["concepts"]:
        if entity.get("kind") not in concept.get("compatible_kinds", []):
            continue
        aliases = sorted((alias for alias in concept.get("aliases", []) if len(alias) > 1), key=len, reverse=True)
        if aliases:
            return aliases[0]
    return str(entity.get("label") or "目标对象")


def _create_transfer_intent(session: dict[str, Any], utterance: str) -> dict[str, Any] | None:
    normalized = re.sub(r"[，。！？、,.!?\s]+", "", utterance)
    transfer_tokens = ("放到", "放在", "摆到", "摆在", "搁到", "搁在", "移到", "搬到", "挪到")
    restore_requested = any(token in normalized for token in ("放回", "放回去", "放回原处", "还回去"))
    if not restore_requested and not any(token in normalized for token in transfer_tokens):
        return None
    concepts = load_object_concepts()["concepts"]
    mentioned = [concept for concept in concepts if any(alias and alias in normalized for alias in concept.get("aliases", []))]
    theme_concepts = [concept for concept in mentioned if "graspable" in concept.get("functional_affordances", [])]
    destination_concepts = [concept for concept in mentioned if "support_object" in concept.get("functional_affordances", [])]
    held_ref = session["state"].get("holding")
    held_theme = next((item for item in session["runtime_objects"] if item.get("entity_id") == held_ref), None)
    deictic_theme_requested = any(token in normalized for token in ("它", "这个", "那个", "这东西", "那东西"))
    explicit_destination_entities = [
        item for item in session["runtime_objects"]
        if item.get("active") is not False and item.get("kind") == "operation_surface" and item.get("label") in normalized
    ]
    if not destination_concepts and len(explicit_destination_entities) == 1:
        destination_concepts = [next(concept for concept in concepts if "support_object" in concept.get("functional_affordances", []))]
    acquisition_positions = [normalized.find(token) for token in ("拿过来", "拿来", "拿起", "拿", "取", "抓") if token in normalized]
    acquisition_position = min(acquisition_positions) if acquisition_positions else None
    if len(theme_concepts) > 1 and acquisition_position is not None:
        preceding = [
            concept for concept in theme_concepts
            if any(normalized.find(alias) >= 0 and normalized.find(alias) < acquisition_position for alias in concept.get("aliases", []))
        ]
        if len(preceding) == 1:
            theme_concepts = preceding
    if not theme_concepts and held_theme and (deictic_theme_requested or restore_requested):
        theme_candidates = [held_theme]
    elif len(theme_concepts) == 1:
        theme_candidates = [
            item for item in session["runtime_objects"]
            if item.get("active") is not False and item.get("kind") in theme_concepts[0].get("compatible_kinds", [])
        ]
    else:
        return None
    if restore_requested:
        previous_support_ref = theme_candidates[0].get("last_support_ref") if len(theme_candidates) == 1 else None
        destinations = [item for item in session["runtime_objects"] if item.get("entity_id") == previous_support_ref]
    elif len(destination_concepts) == 1:
        destinations = [
            item for item in session["runtime_objects"]
            if item.get("active") is not False and item.get("kind") in destination_concepts[0].get("compatible_kinds", [])
        ]
    else:
        return None
    if len(explicit_destination_entities) == 1 and not restore_requested:
        destinations = explicit_destination_entities
    if len(theme_candidates) != 1 or len(destinations) != 1:
        return None
    theme, destination = theme_candidates[0], destinations[0]
    if destination["entity_id"] == theme.get("support_ref"):
        return None
    companion_concepts = [concept for concept in theme_concepts if concept["concept_id"] != next((item["concept_id"] for item in theme_concepts if theme["kind"] in item.get("compatible_kinds", [])), None)]
    # Keep every additional mentioned graspable object as a configuration
    # reference when the utterance explicitly requests co-location.
    if "一起" in normalized:
        companion_concepts = [
            concept for concept in mentioned
            if concept["concept_id"] != next((item["concept_id"] for item in mentioned if theme["kind"] in item.get("compatible_kinds", [])), None)
            and "graspable" in concept.get("functional_affordances", [])
        ]
    companion_refs = []
    for concept in companion_concepts:
        candidates = [item for item in session["runtime_objects"] if item.get("active") is not False and item.get("kind") in concept.get("compatible_kinds", [])]
        if len(candidates) == 1:
            companion_refs.append(candidates[0]["entity_id"])
    intent_id = "intent_" + hashlib.sha1(
        f"{session['session_id']}|{theme['entity_id']}|{destination['entity_id']}|{session['world_revision']}".encode("utf-8")
    ).hexdigest()[:12]
    intent = {
        "intent_id": intent_id,
        "intent_type": "verified_object_transfer",
        "source_utterance": utterance,
        "goal_fact": "objects_co_supported_at_destination" if companion_refs else "object_supported_at_destination",
        "role_bindings": {
            "theme": theme["entity_id"],
            "destination": destination["entity_id"],
            **({"companions": companion_refs} if companion_refs else {}),
        },
        "goal_contract": {
            "requires": ["theme_object_grounded", "destination_grounded"],
            "produces": ["object_supported_at_destination", "objects_co_supported_at_destination"] if companion_refs else ["object_supported_at_destination"],
            "verification": ["projection_inside_support_boundary", "support_contact_stable", "gripper_released", "support_occupancy_non_overlapping"] if companion_refs else ["projection_inside_support_boundary", "support_contact_stable", "gripper_released"],
        },
        "dependency_graph": {
            "root": "object_supported_at_destination",
            "nodes": [
                {"stage_id": "acquire_theme", "produces": "object_in_gripper"},
                {"stage_id": "place_at_destination", "requires": "object_in_gripper", "produces": "object_supported_at_destination"},
            ],
        },
        "lifecycle": "active",
        "verified_facts": [],
        "current_stage": None,
        "resume_envelope": None,
        "created_world_revision": session["world_revision"],
    }
    session["long_horizon_intents"][intent_id] = intent
    session["active_intent_id"] = intent_id
    session["intent_activation_stack"] = [intent_id]
    return intent


def _derive_long_intent_stage(session: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
    theme_ref = intent["role_bindings"]["theme"]
    destination_ref = intent["role_bindings"]["destination"]
    theme = next((item for item in session["runtime_objects"] if item["entity_id"] == theme_ref), None)
    destination = next((item for item in session["runtime_objects"] if item["entity_id"] == destination_ref), None)
    if not theme or not destination:
        return {"status": "rebind_required", "reason": "long_intent_role_binding_no_longer_present"}
    theme_reference = _conceptual_reference_for_entity(theme)
    companion_refs = intent["role_bindings"].get("companions", [])
    companions = [item for item in session["runtime_objects"] if item.get("entity_id") in companion_refs]
    companions_ready = all(item.get("support_ref") == destination_ref and not item.get("attached_to_executor") for item in companions)
    if theme.get("support_ref") == destination_ref and not _is_held(session, theme_ref):
        if companions_ready:
            return {"status": "completed", "verified_fact": intent["goal_fact"]}
        return {"status": "rebind_required", "reason": "co_location_reference_not_supported_at_destination"}
    if _is_held(session, theme_ref):
        return {
            "status": "stage_ready",
            "stage_id": "place_at_destination",
            "utterance": f"把{theme_reference}放到{destination['label']}上",
            "required_fact": "object_in_gripper",
            "target_fact": "object_supported_at_destination",
        }
    return {
        "status": "stage_ready",
        "stage_id": "acquire_theme",
        "utterance": f"拿起{theme_reference}",
        "required_fact": "theme_object_grounded",
        "target_fact": "object_in_gripper",
    }


def _prepare_long_intent_stage(session: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
    intent_id = intent["intent_id"]
    stage = _derive_long_intent_stage(session, intent)
    if stage["status"] == "completed":
        intent["lifecycle"] = "completed"
        intent["verified_facts"] = [intent["goal_fact"]]
        intent["current_stage"] = None
        if session.get("active_intent_id") == intent["intent_id"]:
            session["active_intent_id"] = None
            session["intent_activation_stack"] = []
        return {"status": "long_intent_completed", "long_horizon_intent": _long_intent_view(intent)}
    if stage["status"] != "stage_ready":
        intent["lifecycle"] = "awaiting_rebinding"
        return {
            "status": "long_intent_rebinding_required",
            "reason": stage["reason"],
            "long_horizon_intent": _long_intent_view(intent),
        }
    intent["lifecycle"] = "active"
    intent["current_stage"] = deepcopy(stage)
    started = begin_motion_command(session["session_id"], stage["utterance"], internal_stage=True)
    # Candidate generation rolls the short-task session back to avoid committing
    # unverified facts. Continue from the restored live session, not the stale
    # object reference retained by this long-intent helper.
    live_session = SESSIONS[session["session_id"]]
    intent = live_session["long_horizon_intents"][intent_id]
    intent["lifecycle"] = "active"
    intent["current_stage"] = deepcopy(stage)
    immediate = started.get("immediate_result") or {}
    pending = live_session.get("pending_confirmation")
    if pending:
        pending["long_intent_id"] = intent_id
        pending["long_stage_id"] = stage["stage_id"]
        immediate["pending_confirmation"] = deepcopy(pending)
    immediate["long_horizon_intent"] = _long_intent_view(intent)
    immediate["long_stage"] = deepcopy(stage)
    immediate["prompt"] = (
        f"长程目标保持为“将对象放到目标承载面”。当前根据最新世界状态需要先完成阶段：{stage['stage_id']}。"
        + (immediate.get("prompt") or "")
    )
    return {**started, "immediate_result": immediate, "long_horizon_intent": _long_intent_view(intent)}


def _suspend_active_intent(session: dict[str, Any]) -> dict[str, Any] | None:
    intent_id = session.get("active_intent_id")
    intent = (session.get("long_horizon_intents") or {}).get(intent_id)
    if not intent or intent.get("lifecycle") != "active":
        return None
    _revoke_pending_confirmation(session, "long_intent_suspended")
    intent["lifecycle"] = "suspended"
    intent["resume_envelope"] = {
        "goal_fact": intent["goal_fact"],
        "unresolved_goal": intent["goal_fact"],
        "verified_facts": list(intent["verified_facts"]),
        "role_bindings": deepcopy(intent["role_bindings"]),
        "world_revision": session["world_revision"],
        "policy_revision": session["policy_revision"],
        "current_holding": deepcopy(_holding_by_effector(session)),
        "old_path_discarded": True,
    }
    return {
        "status": "long_intent_suspended",
        "prompt": "已挂起当前长程意图并丢弃未执行路径。恢复时我会重新观察对象、持有和承载事实，再推导下一阶段。",
        "long_horizon_intent": _long_intent_view(intent),
        "session": get_session(session["session_id"]),
    }


def _resume_active_intent(session: dict[str, Any]) -> dict[str, Any] | None:
    intent_id = session.get("active_intent_id")
    intent = (session.get("long_horizon_intents") or {}).get(intent_id)
    if not intent or intent.get("lifecycle") != "suspended":
        return None
    return _prepare_long_intent_stage(session, intent)


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


def _recall_trusted_experience(utterance: str) -> dict[str, Any] | None:
    matches = []
    object_concepts = {item["concept_id"]: item for item in load_object_concepts()["concepts"]}
    for experience in load_trusted_experiences():
        # Persisted experiences from older teaching runs may explicitly carry
        # null contracts/bindings. Treat those as non-matchable records rather
        # than allowing an observation query to tear down the request thread.
        source_contract = experience.get("source_concept_contract") or {}
        target_binding = experience.get("target_binding") or {}
        trigger = str(source_contract.get("language_trigger") or "")
        target_concept_id = target_binding.get("concept_id")
        aliases = (object_concepts.get(target_concept_id) or {}).get("aliases", [])
        if trigger and trigger in utterance and any(alias in utterance for alias in aliases):
            matches.append(experience)
    return matches[0] if len(matches) == 1 else None


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

    def compatible_candidates(required_type: str | None) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for entity in mentioned_entities:
            profile = build_functional_profile(entity, object_concepts)
            if session.get("state", {}).get("holding") == entity.get("entity_id"):
                profile["current_relations"] = sorted(set(profile.get("current_relations", [])) | {"held_by_executor"})
            compatibility = evaluate_role_compatibility(profile, required_type) if required_type else {"compatible": True}
            if compatibility.get("compatible") is True:
                candidates.append(entity)
        return candidates

    for role_name, template in roles.items():
        entity_type = template.get("entity_type")
        # Runtime relations and functional role contracts are stronger evidence
        # than mention order. Language position is only a final tie-breaker.
        if entity_type == "held_object" and held:
            grounded[role_name] = held
        elif role_name == "activity" and session.get("active_motion_job_id"):
            grounded[role_name] = session["active_motion_job_id"]
        else:
            candidates = compatible_candidates(entity_type)
            target_ref = target.get("entity_ref") if target else None
            target_candidate = next((item for item in candidates if item["entity_id"] == target_ref), None)
            confirmed_refs = {
                item.get("entity_ref")
                for item in session.get("confirmed_visual_bindings", [])
                if item.get("world_revision") == session.get("world_revision")
            }
            confirmed_candidate = next((item for item in candidates if item["entity_id"] in confirmed_refs), None)
            selected = target_candidate or confirmed_candidate
            if not selected and candidates:
                selected = candidates[-1] if role_name in {"destination", "source"} else candidates[0]
            # Preserve an explicit but incompatible binding as diagnostic
            # evidence. The compatibility gate will reject it and explain the
            # violated role contract instead of misreporting an unknown role.
            if not selected and mentioned_entities:
                selected = mentioned_entities[-1] if role_name in {"destination", "source"} else mentioned_entities[0]
            if selected:
                grounded[role_name] = selected["entity_id"]
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


def build_visual_concept_pack_catalog() -> dict[str, Any]:
    return build_visual_pack_catalog()


def _is_holding_state_query(text: str) -> bool:
    return any(pattern in text for pattern in (
        "拿着什么", "手里有什么", "手上有什么", "手上拿着什么", "手上拿的什么",
        "你拿着什么", "你拿了什么", "你手上有什么", "握着什么", "持有什么",
    ))


def _answer_holding_state_query(session: dict[str, Any]) -> dict[str, Any]:
    holding = _holding_by_effector(session)
    held = [
        (channel, ref, next((item for item in session.get("runtime_objects", []) if item.get("entity_id") == ref), None))
        for channel, ref in holding.items() if ref
    ]
    if held:
        prompt = "我当前持有：" + "；".join(f"{channel}拿着{entity.get('label', ref) if entity else ref}" for channel, ref, entity in held) + "。这些是经过抓取验真建立的当前持有事实。"
        fact = "object_in_gripper"
    else:
        prompt = "我当前没有拿着东西。这个回答来自当前执行体的持有状态。"
        fact = "gripper_empty"
    return {
        "status": "runtime_holding_state_answered",
        "query_type": "holding_state",
        "prompt": prompt,
        "runtime_fact": fact,
        "holding_by_effector": deepcopy(holding),
        "holding_entities": [{"effector": channel, "entity": deepcopy(entity)} for channel, _, entity in held],
        "state_evidence": {
            "source": "current_executor_holding_state",
            "world_revision": session["world_revision"],
            "physical_verification_required_before_state_write": True,
        },
        "candidate_only": False,
        "direct_execution_allowed": False,
        "session": get_session(session["session_id"]),
    }


def _is_restore_request(text: str) -> bool:
    return any(token in text for token in ("放回", "放回去", "放回原处", "还回去"))


def _answer_restore_destination_gap(session: dict[str, Any]) -> dict[str, Any] | None:
    holding_ref = session.get("state", {}).get("holding")
    held = next((item for item in session.get("runtime_objects", []) if item.get("entity_id") == holding_ref), None)
    if not held or held.get("last_support_ref"):
        return None
    return {
        "status": "restore_destination_clarification_required",
        "reason": "held_object_has_no_verified_previous_support_relation",
        "prompt": (
            f"我知道当前手里拿着{held.get('label', holding_ref)}，但它没有已验真的上一承载面，"
            "所以“放回去”还不能唯一决定目的地。请告诉我放到哪里，以及看到什么才算放稳。"
        ),
        "known_state": {"held_object": holding_ref, "previous_support_relation": None},
        "missing_causal_slots": ["destination", "placement_verification"],
        "post_action": {
            "action": "continue_language_teaching_with_destination_and_verification",
            "teaching_available": True,
            "clarification_required": True,
        },
        "candidate_only": True,
        "direct_execution_allowed": False,
        "session": get_session(session["session_id"]),
    }


def _is_object_location_query(text: str) -> bool:
    return (
        _directed_observation_concept(text) is not None
        and any(pattern in text for pattern in ("在哪里", "在哪", "在哪儿", "什么位置", "哪个区域"))
    )


def _answer_object_location_query(session: dict[str, Any], text: str) -> dict[str, Any]:
    directed = _directed_observation_concept(text)
    observation = build_open_world_observation(_scene_for_session(session), session)
    matches = [
        item for item in observation.get("recognized_object_candidates", [])
        if item.get("concept_id") == directed["concept_id"]
    ]
    if not matches:
        return {
            "status": "object_location_not_observed",
            "query_type": "object_location",
            "prompt": f"我已转动视觉扫描当前空间，但没有观察到{directed['matched_alias']}候选，因此不能声称它在哪里。",
            "directed_query": directed,
            "observation_action": {"operator": "scan_current_space_for_object_location", "scene_truth_read_directly": False},
            "active_perception_trace": deepcopy(observation.get("scan_viewpoints", [])),
            "candidate_only": True,
            "direct_execution_allowed": False,
            "session": get_session(session["session_id"]),
        }
    if len(matches) > 1:
        return {
            "status": "object_location_disambiguation_required",
            "query_type": "object_location",
            "prompt": f"我观察到{len(matches)}个{directed['matched_alias']}候选，请用颜色、材质或其他可观察特征指出你问的是哪一个。",
            "directed_query": directed,
            "candidate_options": deepcopy(matches),
            "candidate_only": True,
            "direct_execution_allowed": False,
            "session": get_session(session["session_id"]),
        }
    match = matches[0]
    entity_ref = match["spatial_entity_candidate_ref"]
    runtime_entity = next((item for item in session["runtime_objects"] if item.get("entity_id") == entity_ref), None)
    if _is_held(session, entity_ref):
        location = {"relation": "held_by_executor", "executor_ref": session["executor_profile_id"]}
        prompt = f"{runtime_entity.get('label', directed['matched_alias'])}当前在我手里。这个位置关系来自已经验真的持有事实。"
        evidence_status = "runtime_verified"
    else:
        support_relation = next(
            (item for item in observation.get("spatial_relation_candidates", []) if item.get("subject_entity_ref") == entity_ref),
            None,
        )
        if support_relation:
            support = next(
                (item for item in session["runtime_objects"] if item.get("entity_id") == support_relation["support_entity_ref"]),
                None,
            )
            location = {"relation": "on_top_of", "support_entity_ref": support_relation["support_entity_ref"]}
            prompt = f"我当前观察到{runtime_entity.get('label', directed['matched_alias'])}在{support.get('label', '承载面')}上。这来自当前视觉和支撑拓扑候选，还不是交互后的功能验真事实。"
            evidence_status = "visual_topological_candidate"
        else:
            position = match.get("estimated_position")
            region_id = _region_for(position, _scene_for_session(session)) if position else None
            region = next((item for item in _scene_for_session(session)["semantic_regions"] if item["region_id"] == region_id), None)
            location = {"relation": "inside_region", "region_id": region_id, "estimated_position": deepcopy(position)}
            prompt = f"我当前观察到{runtime_entity.get('label', directed['matched_alias'])}在{(region or {}).get('label', '当前可见区域')}。这是当前视觉空间候选。"
            evidence_status = "visual_spatial_candidate"
    return {
        "status": "object_location_state_answered",
        "query_type": "object_location",
        "prompt": prompt,
        "directed_query": directed,
        "entity_ref": entity_ref,
        "location_binding": location,
        "evidence_status": evidence_status,
        "observation_id": observation["observation_id"],
        "world_revision": session["world_revision"],
        "candidate_only": evidence_status != "runtime_verified",
        "direct_execution_allowed": False,
        "session": get_session(session["session_id"]),
    }


def _is_open_world_observation_query(text: str) -> bool:
    broad = any(pattern in text for pattern in ("看到什么", "看到了什么", "有什么东西", "有哪些东西", "周围有什么"))
    directed = any(pattern in text for pattern in (
        "看得到", "看的到", "能看到", "能看见", "看得见", "有没有看到", "看到吗", "看见吗",
        "看见没", "看到没", "瞧见", "瞧得到", "能不能看到", "能不能看见",
    ))
    # Natural confirmations such as “看到杯子没有” omit the usual question
    # prefix. Keep them on the observation path when a known object concept is
    # present, instead of sending them into task/event parsing.
    colloquial_directed = (
        _directed_observation_concept(text) is not None
        and re.search(r"(?:看到|看见|瞧见).{0,12}(?:没有|吗|么|没)", text) is not None
    )
    # Treat omitted-result forms such as “你看的杯子吗” as the same visual
    # operator. The object concept and interrogative tail provide the semantic
    # evidence; no individual object phrase is enumerated here.
    abbreviated_directed = (
        _directed_observation_concept(text) is not None
        and re.search(r"看[^，。！？!?]{0,16}(?:没有|没|吗|么|呢)", text) is not None
    )
    return broad or directed or colloquial_directed or abbreviated_directed


def _is_object_presence_query(text: str) -> bool:
    directed = _directed_observation_concept(text)
    return bool(
        directed
        and any(pattern in text for pattern in ("有没有", "有无", "是否有"))
        and not any(pattern in text for pattern in ("有没有看到", "是否看到"))
    )


def _directed_observation_concept(text: str) -> dict[str, Any] | None:
    concepts = load_object_concepts()["concepts"]
    matches = [
        (len(alias), concept, alias)
        for concept in concepts
        for alias in concept.get("aliases", [])
        if alias and alias in text
    ]
    if not matches:
        return None
    _, concept, alias = max(matches, key=lambda item: item[0])
    return {"concept_id": concept["concept_id"], "display_name": concept["display_name"], "matched_alias": alias}


def _observation_primitive_contract() -> dict[str, Any]:
    """Expose the factory perceptual primitive without treating vision as a fact write."""
    concept = next(item for item in FACTORY_EVENT_CONCEPT_UNITS if item["concept_id"] == "factory_event_observe")
    effect_contract = concept["concept_kernel"]["effect_contract"]
    return {
        "concept_id": concept["concept_id"],
        "operator": concept["concept_kernel"]["operator"],
        "target_role": "perceivable_entity",
        "requires": deepcopy(effect_contract["requires"]),
        "produces": deepcopy(effect_contract["produces"]),
        "verification": deepcopy(effect_contract["verification"]),
        "evidence_boundary": "visual_observation_candidate_not_runtime_fact",
    }


def _answer_object_presence_query(session: dict[str, Any], text: str) -> dict[str, Any]:
    """Answer a present-world query without inventing an event or task contract."""
    observation = build_open_world_observation(_scene_for_session(session), session)
    directed = _directed_observation_concept(text)
    assert directed is not None
    matches = [
        item for item in observation.get("recognized_object_candidates", [])
        if item.get("concept_id") == directed["concept_id"]
    ]
    observation.update({
        "query_type": "object_presence",
        "status": "object_presence_observed" if matches else "object_presence_not_observed",
        "directed_query": directed,
        "directed_matches": deepcopy(matches),
        "observation_action": {
            "operator": "scan_current_space_before_presence_answer",
            "sensor_frame": "head_rgbd",
            "scene_truth_read_directly": False,
        },
        "factory_perceptual_primitive": _observation_primitive_contract(),
        "active_perception_trace": [
            {"viewpoint": deepcopy(viewpoint), "status": "observation_candidate_collected"}
            for viewpoint in observation.get("scan_viewpoints", [])
        ],
        "candidate_only": True,
        "direct_execution_allowed": False,
        "runtime_fact_committed": False,
        "task_followup": {
            "status": "awaiting_human_goal",
            "prompt": "你希望我对它做什么？",
            "role_binding_requires_current_task_grounding": True,
        },
    })
    if len(matches) == 1:
        observation["prompt"] = (
            f"我先转动视觉观察了当前空间，看到1个{directed['display_name']}候选。"
            f"按当前视觉观察可以回答：这里有{directed['display_name']}。"
            "它目前是观察候选，不是已经验真的功能事实。你希望我对它做什么？"
        )
    elif len(matches) > 1:
        observation["prompt"] = (
            f"我先转动视觉观察了当前空间，看到{len(matches)}个{directed['display_name']}候选。"
            "你希望我对哪一个做什么？可以补充颜色、位置或其他可观察特征。"
        )
        observation["task_followup"]["status"] = "awaiting_target_disambiguation_and_goal"
    else:
        observation["prompt"] = (
            f"我已扫描当前可观察范围，但没有看到{directed['display_name']}候选。"
            "这不等于空间中一定没有，可能在遮挡处或当前视野外。"
        )
        observation["task_followup"]["status"] = "awaiting_reobservation_or_human_guidance"
    return observation


def _answer_observation_query(session: dict[str, Any], text: str) -> dict[str, Any]:
    observation = build_open_world_observation(_scene_for_session(session), session)
    directed = _directed_observation_concept(text)
    observation["observation_action"] = {
        "operator": "scan_current_space_before_answering",
        "sensor_frame": "head_rgbd",
        "viewpoints": deepcopy(observation.get("scan_viewpoints", [])),
        "scene_truth_read_directly": False,
    }
    observation["factory_perceptual_primitive"] = _observation_primitive_contract()
    observation["active_perception_trace"] = [
        {"viewpoint": deepcopy(viewpoint), "status": "observation_candidate_collected"}
        for viewpoint in observation.get("scan_viewpoints", [])
    ]
    if directed:
        query_label = directed.get("matched_alias") or directed["display_name"]
        matches = [
            item for item in observation.get("recognized_object_candidates", [])
            if item.get("concept_id") == directed["concept_id"]
        ]
        confirmed = [
            item for item in session.get("confirmed_visual_bindings", [])
            if item.get("concept_id") == directed["concept_id"]
            and item.get("world_revision") == session["world_revision"]
        ]
        if confirmed:
            observation.update({
                "status": "directed_object_observation_confirmed",
                "directed_query": directed,
                "directed_matches": deepcopy(matches),
                "confirmed_visual_binding": deepcopy(confirmed[0]),
                "prompt": f"我已观察并与你确认，当前空间中有{directed['display_name']}。后续任务会以这个空间绑定为依据。",
            })
            return observation
        pending = {
            "confirmation_id": "confirm_obs_" + hashlib.sha1(
                f"{session['session_id']}|{directed['concept_id']}|{session['world_revision']}".encode("utf-8")
            ).hexdigest()[:12],
            "status": "pending",
            "kind": "observation_candidate",
            "utterance": text,
            "concept_id": directed["concept_id"],
            "concept_display_name": query_label,
            "candidate_refs": [item.get("spatial_entity_candidate_ref") for item in matches],
            "authorized_world_revision": session["world_revision"],
            "policy_binding": _policy_binding(session),
        }
        session["pending_confirmation"] = pending
        observation.update({
            "status": "observation_candidate_confirmation_required",
            "directed_query": directed,
            "directed_matches": deepcopy(matches),
            "pending_confirmation": deepcopy(pending),
            "prompt": (
                f"我先转动视觉观察了当前空间，识别到{len(matches)}个{directed['display_name']}候选。"
                "这是当前视觉候选，还不是经过交互验真的功能事实。"
                f"请确认这个候选是否就是当前空间中的{query_label}。确认后我会把它绑定为空间事实。"
                if matches else
                f"我先转动视觉观察了当前空间，但没有识别到{directed['display_name']}候选。"
                "这表示当前视角和已加载视觉概念没有形成匹配，不等于空间里一定没有。"
            ),
        })
    return observation


def _build_observed_relocation_preview(session: dict[str, Any], text: str) -> dict[str, Any] | None:
    relocation_match = re.search(r"(?:把|将)?苹果(?:从.+?)?(?:放到|放在|摆到|摆在)(?:桌子|桌面|操作台|台面)(?:上|上面)?", text)
    if not relocation_match:
        return None
    # This legacy preview is only useful before a transfer starts. Once P016
    # has verified the object in hand, P018 must continue through the generic
    # placement stage rather than being intercepted by an apple-specific demo.
    if session["state"].get("holding"):
        return None
    observation = session.get("open_world_observation")
    if not observation or observation.get("world_revision") != session["world_revision"]:
        observation = build_open_world_observation(_scene_for_session(session), session)
        session["open_world_observation"] = deepcopy(observation)
    apple = next(
        (item for item in observation.get("recognized_object_candidates", []) if item.get("concept_id") == "concept_edible_apple"),
        None,
    )
    support = next((item for item in session["runtime_objects"] if item.get("kind") == "operation_surface"), None)
    if not apple or not support:
        return None
    fact_snapshot = {
        "world_revision": session["world_revision"],
        "established_facts": ["object_grounded", "destination_grounded", "gripper_empty", "gripper_available", "route_feasible"],
        "negated_facts": ["object_in_gripper"],
    }
    place_concept = next(item for item in FACTORY_EVENT_CONCEPT_UNITS if item["concept_id"] == "factory_event_place")
    goal = {
        "operator": place_concept["concept_kernel"]["operator"],
        "recognized_goal_fact": "object_at_destination",
        "required_capability": place_concept["capability"],
        "effect_contract": deepcopy(place_concept["concept_kernel"]["effect_contract"]),
    }
    supported_capabilities = list(session["executor_profile"].get("supported_actions", [])) + ["active_perception"]
    causal_candidate = build_lightweight_causal_candidate(
        goal_concept=goal,
        fact_snapshot=fact_snapshot,
        supported_capabilities=supported_capabilities,
        available_experience_capabilities=_available_experience_capabilities(session),
        event_concepts=FACTORY_EVENT_CONCEPT_UNITS,
        experience_contracts=_causal_experience_contracts(session),
    )
    return {
        "status": "observed_goal_causal_preview",
        "reason": "current_visual_candidate_plus_spatial_goal_backward_chaining",
        "prompt": "我当前把目标理解为：苹果从地面关系变为由桌面稳定支撑。候选链是先让苹果进入夹爪，再使本体与桌面形成可放置关系，最后放置并验真稳定支撑；缺少的本体能力或经验仍会阻止执行。",
        "observed_target": deepcopy(apple),
        "destination_binding": {
            "entity_ref": support["entity_id"],
            "label": support["label"],
            "binding_source": "current_space_model_candidate",
            "candidate_only": True,
        },
        "goal_contract": {
            "requires": ["object_grounded", "destination_grounded"],
            "produces": ["object_at_destination", "object_supported_at_destination"],
            "destroys": ["object_on_ground", "object_in_gripper"],
            "verification": ["contact_stable", "projection_inside_support_boundary", "gripper_clear_of_object"],
        },
        "causal_candidate": causal_candidate,
        "candidate_only": True,
        "direct_execution_allowed": False,
        "runtime_fact_committed": False,
        "post_action": {
            "action": "reenter_orchestration_after_capability_and_experience_resolution",
            "teaching_available": False,
            "clarification_required": False,
        },
        "session": get_session(session["session_id"]),
    }


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
    if mode not in {"normal", "multiple_cups", "occluded_cup", "relocated_cup", "relocated_apple"}:
        return {"error": "unsupported_perception_scenario", "mode": mode}
    objects = deepcopy(_scene_for_session(session)["objects"])
    cup = next(item for item in objects if item.get("kind") == "graspable_container")
    if mode == "multiple_cups":
        second_cup = deepcopy(cup)
        second_cup.update(
            {
                "entity_id": "cup_b" if cup["entity_id"] == "cup_a" else f"{cup['entity_id']}_perception_variant",
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
    elif mode == "relocated_apple":
        apple = next(item for item in objects if item.get("kind") == "graspable_object")
        apple["position"] = [-4.25, -1.65]
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
        session["state"] = deepcopy(_scene_for_session(session)["initial_state"])
        session["world_revision"] += 1
    gap_dialogue = session.get("concept_gap_dialogue") or {}
    source_contract = deepcopy(gap_dialogue.get("compiled_contract"))
    if source_contract:
        canonical_goal = source_contract.get("effect_contract", {}).get("canonical_goal_fact")
        if not canonical_goal:
            return {
                "status": "teaching_goal_verification_adapter_required",
                "reason": "temporary_goal_has_no_runtime_verification_adapter",
                "prompt": "我已经理解你描述的目标，但当前教学舱还不能验真这个目标状态。不能用一次抓取或移动冒充整个任务成功。",
                "temporary_effect_contract": source_contract,
                "session": get_session(session_id),
            }
        goal_utterance = gap_dialogue.get("source_utterance") or goal_utterance
    contract_target = (source_contract or {}).get("semantic_roles", {}).get("target", {})
    perception_utterance = (
        "拿" + str(contract_target.get("surface_form") or "目标对象")
        if source_contract
        else goal_utterance
    )
    perception = build_task_perception_result(_scene_for_session(session), session, perception_utterance)
    target = None
    if perception and perception["concept_grounding"]["grounding_status"] == "spatially_grounded":
        target = next(
            item for item in perception["concept_grounding"]["candidate_bindings"] if item["role"] == "target"
        )
    if target is None:
        target_concept_id = (perception or {}).get("task_perception_frame", {}).get("target_concept_id")
        target_concept = next(
            (item for item in load_object_concepts()["concepts"] if item.get("concept_id") == target_concept_id),
            None,
        )
        unique_candidates = [
            item for item in session["runtime_objects"]
            if target_concept and item.get("kind") in target_concept.get("compatible_kinds", [])
        ]
        if len(unique_candidates) == 1:
            target = {
                "role": "target",
                "entity_ref": unique_candidates[0]["entity_id"],
                "concept_id": target_concept_id,
                "binding_status": "teaching_candidate_from_unique_concept_instance",
                "runtime_fact_committed": False,
            }
        else:
            return {
                "status": "teaching_target_grounding_required",
                "reason": "teaching_requires_unique_current_target_binding",
                "prompt": perception["prompt"] if perception else "请先说明要教我操作哪个当前对象。",
                "perception": perception,
                "session": get_session(session_id),
            }
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
        "goal_fact": (source_contract or {}).get("effect_contract", {}).get("canonical_goal_fact", {}).get("fact") or "target_object_in_gripper",
        "source_concept_contract": source_contract,
        "perception_activation_source": "compiled_concept_target_role" if source_contract else "goal_utterance",
        "target_binding_status": target.get("binding_status", "spatially_grounded"),
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
        source_concept_contract=teaching.get("source_concept_contract"),
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
    expected_concept = experience.get("target_binding", {}).get("concept_id")
    target_concept = next(
        (item for item in load_object_concepts()["concepts"] if item.get("concept_id") == expected_concept),
        None,
    )
    target_aliases = (target_concept or {}).get("aliases") or ["目标对象"]
    perception = build_task_perception_result(_scene_for_session(session), session, "拿" + str(target_aliases[0]))
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
        "perception_activation_source": "persisted_target_concept_binding",
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
    session["state"] = deepcopy(_scene_for_session(session)["initial_state"])
    _invalidate_perception_history(session, "autonomous_replay_reset")
    session["world_revision"] += 1
    target = next(item for item in session["runtime_objects"] if item["entity_id"] == target_ref)
    support = next(
        (item for item in session["runtime_objects"] if item["entity_id"] == target.get("support_ref")),
        None,
    )
    radius = float(session["executor_profile"]["body_envelope"]["radius_m"])
    start = list(session["state"]["executor_position"])
    envelope = build_effective_execution_envelope(session["executor_profile"], session.get("protection_policy_overlay"))
    planning_radius = radius + envelope["effective_constraints"]["minimum_avoidance_distance_m"]
    reachable_distance = radius + float(session["executor_profile"]["arm_reach_m"])
    if support:
        support_x, support_y = support["position"]
        half_x, half_y = support["size"][0] / 2, support["size"][1] / 2
        clearance = planning_radius + 0.03
        approach_candidates = [
            ([support_x - half_x - clearance, target["position"][1]], []),
            ([support_x + half_x + clearance, target["position"][1]], []),
            ([target["position"][0], support_y - half_y - clearance], [[support_x - half_x - clearance, support_y - half_y - clearance]]),
            ([target["position"][0], support_y + half_y + clearance], [[support_x - half_x - clearance, support_y + half_y + clearance]]),
        ]
        feasible_approaches = []
        for candidate, perimeter_entries in approach_candidates:
            if math.dist(candidate, target["position"]) > reachable_distance:
                continue
            waypoints = perimeter_entries + [candidate]
            segment_start = start
            if any(_first_collision(session, segment_start if index == 0 else waypoints[index - 1], waypoint, planning_radius) for index, waypoint in enumerate(waypoints)):
                continue
            if _collider_at(candidate, planning_radius, session, _scene_for_session(session)):
                continue
            route_length = sum(math.dist(a, b) for a, b in zip([start] + waypoints[:-1], waypoints))
            candidate_plan = {
                "outcome": "verified",
                "route_kind": "support_perimeter_approach" if perimeter_entries else "direct",
                "waypoints": waypoints,
                "path_length_m": route_length,
                "safety_contract": {
                    "planner_world_revision": session["world_revision"],
                    "all_segments_swept_volume_verified": True,
                    "terminal_pose_verified": True,
                    "execution_must_recheck_world_revision": True,
                    "unverified_path_never_becomes_executable_fact": True,
                },
            }
            feasible_approaches.append((route_length, candidate, candidate_plan))
        if not feasible_approaches:
            return {
                "status": "learned_replay_blocked",
                "reason": "no_reachable_collision_free_approach_for_current_target_geometry",
                "approach_candidates": [item[0] for item in approach_candidates],
                "session": get_session(session_id),
            }
        _, approach, plan = min(feasible_approaches, key=lambda item: item[0])
        approach_basis = "current_support_perimeter_candidates_filtered_by_reach_and_motion_verification"
    else:
        target_distance = math.dist(start, target["position"])
        stand_off = min(float(session["executor_profile"]["arm_reach_m"]) * 0.72, max(0.0, target_distance - 0.05))
        ratio = 0.0 if target_distance == 0 else (target_distance - stand_off) / target_distance
        approach = [
            start[0] + (target["position"][0] - start[0]) * ratio,
            start[1] + (target["position"][1] - start[1]) * ratio,
        ]
        approach_basis = "current_target_observation_and_body_reach_envelope"
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
        "approach_basis": approach_basis,
        "human_acceptance_required": not trusted_replay,
        "loaded_trusted_experience_replay": trusted_replay,
    }
    return {
        "status": "learned_replay_started",
        "job_id": job_id,
        "frame_count": len(frames),
        "prompt": f"我会重新绑定当前{target['label']}，按经验不变量和当前本体可达边界自主执行；每一帧仍需通过当前碰撞和策略检查。",
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
    effector = _held_effector(session, target_ref) or _available_effector(session)
    if not effector:
        return {"status": "grasp_blocked", "reason": "gripper_already_holding_incompatible_object", "frames": []}
    previous_support_ref = target.pop("support_ref", None)
    if previous_support_ref:
        target["last_support_ref"] = previous_support_ref
    _holding_by_effector(session)[effector] = target_ref
    _sync_primary_holding(session)
    target["attached_to_executor"] = True
    target["held_by_effector"] = effector
    target["position"] = deepcopy(executor_position)
    target["elevation_m"] = 0.86
    verification = {
        "target_entity_ref": target_ref,
        "effector": effector,
        "first_channel": {"source": "simulated_gripper_aperture_and_contact", "established": True},
        "second_channel": {"source": "simulated_visual_target_follows_end_effector", "established": True},
        "final_fact": "target_object_in_gripper",
        "final_fact_established": True,
        "verification_boundary": "P016_multi_channel_fact_verification",
    }
    return {
        "status": "fact_established",
        "reason": "verified_grasp_completed",
        "prompt": f"{effector}接触与目标随动观测一致，已经验真目标对象在该末端执行器中。",
        "terminal_fact": "target_object_in_gripper",
        "verification_evidence": verification,
        "control_source": source,
        "runtime_objects": deepcopy(session["runtime_objects"]),
        "frames": [],
    }


def _apply_verified_place(session: dict[str, Any], object_ref: str, destination_ref: str, source: str) -> dict[str, Any]:
    objects = {item["entity_id"]: item for item in session["runtime_objects"]}
    held_object = objects.get(object_ref)
    destination = objects.get(destination_ref)
    if not held_object or not destination:
        return {"status": "placement_blocked", "reason": "theme_or_destination_not_available", "frames": []}
    effector = _held_effector(session, object_ref)
    if not effector:
        return {"status": "placement_blocked", "reason": "theme_is_not_currently_held", "frames": []}
    destination_profile = build_functional_profile(destination, load_object_concepts()["concepts"])
    compatibility = evaluate_role_compatibility(destination_profile, "support_or_container")
    if compatibility.get("compatible") is not True:
        return {
            "status": "placement_blocked",
            "reason": "destination_role_contract_not_satisfied",
            "prompt": compatibility.get("reason"),
            "role_compatibility": compatibility,
            "frames": [],
        }
    executor_position = session["state"]["executor_position"]
    footprint_distance = _distance_to_object_footprint(executor_position, destination)
    arm_reach = float(session["executor_profile"]["arm_reach_m"])
    if footprint_distance > arm_reach:
        return {
            "status": "placement_blocked",
            "reason": "destination_outside_current_placement_workspace",
            "prompt": f"目标承载面距当前本体可交互边界 {footprint_distance:.2f} 米，超过手臂可达范围 {arm_reach:.2f} 米。",
            "frames": [],
        }

    # Compute a body-independent support pose from current object and support
    # geometry. The stored fact is relational; this transient pose is not an
    # experience trajectory and is discarded after verification.
    margin_x = (float(destination["size"][0]) - float(held_object["size"][0])) / 2
    margin_y = (float(destination["size"][1]) - float(held_object["size"][1])) / 2
    if margin_x < 0 or margin_y < 0:
        return {
            "status": "placement_blocked",
            "reason": "held_object_does_not_fit_destination_support_boundary",
            "prompt": "当前物体的投影不能完整落入目标承载面，无法形成稳定放置事实。",
            "frames": [],
        }
    occupied = [
        item for item in session["runtime_objects"]
        if item.get("entity_id") != object_ref and item.get("support_ref") == destination_ref and not item.get("attached_to_executor")
    ]
    center_x, center_y = map(float, destination["position"])
    offset_x, offset_y = margin_x * 0.68, margin_y * 0.68
    placement_candidates = [
        [center_x, center_y],
        [center_x - offset_x, center_y], [center_x + offset_x, center_y],
        [center_x, center_y - offset_y], [center_x, center_y + offset_y],
        [center_x - offset_x, center_y - offset_y], [center_x + offset_x, center_y + offset_y],
    ]
    if occupied:
        placement_candidates.sort(
            key=lambda candidate: min(math.dist(candidate, item["position"]) for item in occupied),
            reverse=True,
        )
    placement_position = None
    for candidate in placement_candidates:
        collision = any(
            abs(candidate[0] - float(item["position"][0])) < (float(held_object["size"][0]) + float(item["size"][0])) / 2 + 0.03
            and abs(candidate[1] - float(item["position"][1])) < (float(held_object["size"][1]) + float(item["size"][1])) / 2 + 0.03
            for item in occupied
        )
        if not collision:
            placement_position = candidate
            break
    if placement_position is None:
        return {
            "status": "placement_blocked",
            "reason": "destination_has_no_non_overlapping_placement_pose",
            "prompt": "目标承载面没有可供当前物体稳定放置且不与已有物体重叠的位置。",
            "occupied_object_refs": [item["entity_id"] for item in occupied],
            "frames": [],
        }
    projection_inside = (
        abs(placement_position[0] - destination["position"][0]) <= margin_x
        and abs(placement_position[1] - destination["position"][1]) <= margin_y
    )
    support_contact = True
    release_feasible = _is_held(session, object_ref)
    non_overlapping = all(
        abs(placement_position[0] - float(item["position"][0])) >= (float(held_object["size"][0]) + float(item["size"][0])) / 2 + 0.03
        or abs(placement_position[1] - float(item["position"][1])) >= (float(held_object["size"][1]) + float(item["size"][1])) / 2 + 0.03
        for item in occupied
    )
    verified = projection_inside and support_contact and release_feasible and non_overlapping
    if not verified:
        return {"status": "placement_verification_failed", "reason": "stable_support_relation_not_established", "frames": []}
    # Commit the state transition only after both predicted verification
    # channels pass. Failed candidates leave the runtime facts unchanged.
    held_object["position"] = placement_position
    held_object["elevation_m"] = float(destination["size"][2])
    held_object["support_ref"] = destination_ref
    held_object["last_support_ref"] = destination_ref
    held_object["attached_to_executor"] = False
    held_object.pop("held_by_effector", None)
    _holding_by_effector(session)[effector] = None
    _sync_primary_holding(session)
    return {
        "status": "fact_established",
        "reason": "verified_placement_completed",
        "prompt": f"已将{held_object['label']}放到{destination['label']}，并验真物体投影位于承载边界内、支撑接触稳定且夹爪已经释放。",
        "terminal_fact": "object_supported_at_destination",
        "terminal_fact_binding": {"object_ref": object_ref, "destination_ref": destination_ref},
        "verification_evidence": {
            "first_channel": {"source": "simulated_support_contact_projection_and_occupancy", "established": projection_inside and support_contact and non_overlapping},
            "second_channel": {"source": "simulated_effector_release_and_object_stationarity", "effector": effector, "established": release_feasible and not _is_held(session, object_ref)},
            "final_fact": "object_supported_at_destination",
            "final_fact_established": True,
            "verification_boundary": "P016_multi_channel_fact_verification",
            "support_occupancy": {"occupied_object_refs": [item["entity_id"] for item in occupied], "non_overlapping": non_overlapping},
        },
        "effect_contract_committed": {
            "produces": ["object_at_destination", "object_supported_at_destination", "gripper_empty"],
            "destroys": ["object_in_gripper"],
        },
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


def _distance_to_object_footprint(position: list[float], entity: dict[str, Any]) -> float:
    half_x = float(entity["size"][0]) / 2
    half_y = float(entity["size"][1]) / 2
    dx = max(abs(position[0] - float(entity["position"][0])) - half_x, 0.0)
    dy = max(abs(position[1] - float(entity["position"][1])) - half_y, 0.0)
    return math.hypot(dx, dy)


def _build_object_relative_motion(
    session: dict[str, Any],
    contextual_affordance: dict[str, Any],
    decision_started_ns: int,
) -> dict[str, Any]:
    entity = next(
        item for item in session["runtime_objects"]
        if item["entity_id"] == contextual_affordance["entity_ref"]
    )
    operator = contextual_affordance["operator_candidate"]
    task_perception = contextual_affordance.get("task_perception") or {}
    perception_bindings = task_perception.get("concept_grounding", {}).get("candidate_bindings", [])
    support_binding = next((item for item in perception_bindings if item.get("role") == "support"), None)
    planning_entity = entity
    if operator == "grasp_object" and (support_binding or entity.get("support_ref")):
        support_ref = (support_binding or {}).get("entity_ref") or entity.get("support_ref")
        planning_entity = next(
            (item for item in session["runtime_objects"] if item.get("entity_id") == support_ref),
            entity,
        )
    start = list(session["state"]["executor_position"])
    envelope = build_effective_execution_envelope(
        session["executor_profile"], session.get("protection_policy_overlay")
    )
    constraints = envelope["effective_constraints"]
    planning_radius = constraints["body_radius_m"] + constraints["minimum_avoidance_distance_m"]
    clearance = planning_radius + 0.05
    center_x, center_y = map(float, planning_entity["position"])
    half_x, half_y = float(planning_entity["size"][0]) / 2, float(planning_entity["size"][1]) / 2
    projected_x = min(max(start[0], center_x - half_x), center_x + half_x)
    projected_y = min(max(start[1], center_y - half_y), center_y + half_y)
    side_candidates = [
        {"side": "left", "position": [center_x - half_x - clearance, projected_y]},
        {"side": "right", "position": [center_x + half_x + clearance, projected_y]},
        {"side": "bottom", "position": [projected_x, center_y - half_y - clearance]},
        {"side": "top", "position": [projected_x, center_y + half_y + clearance]},
    ]
    if operator == "avoid":
        # Without a downstream destination, "cleared" means leaving the obstacle's
        # longitudinal projection while retaining a collision-free body envelope.
        if abs(start[0] - center_x) >= abs(start[1] - center_y):
            side_candidates = [item for item in side_candidates if item["side"] in {"bottom", "top"}]
        else:
            side_candidates = [item for item in side_candidates if item["side"] in {"left", "right"}]

    feasible: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for candidate in side_candidates:
        terminal_collider = _collider_at(candidate["position"], planning_radius, session, _scene_for_session(session))
        if terminal_collider:
            rejected.append({**candidate, "reason": "terminal_body_envelope_not_clear", "collider": terminal_collider})
            continue
        plan = _plan_verified_motion(session, start, candidate["position"], planning_radius)
        if plan.get("outcome") != "verified":
            rejected.append({**candidate, "reason": "swept_volume_route_not_clear", "plan": plan})
            continue
        route_length = sum(
            math.dist(a, b) for a, b in zip([start] + plan["waypoints"][:-1], plan["waypoints"])
        )
        feasible.append({**candidate, "plan": plan, "route_length_m": route_length})

    feature_mapping = [
        "基于任务期对象角色选择待建立的对象相对空间事实",
        "基于对象当前几何与本体安全包络生成多个任务期终止位姿候选",
        "对终止位姿及其完整运动路径的本体扫掠体积进行当前世界版本验证",
        "仅将通过编排与治理边界的候选转换为逐帧运动并在末帧验真对象相对事实",
        "未获得安全终止位姿或非空间角色条件不满足时不进入运动控制",
    ]
    if not feasible:
        return {
            **contextual_affordance,
            "status": "contextual_spatial_motion_blocked",
            "reason": "no_collision_free_object_relative_terminal_pose",
            "prompt": f"我认识{entity['label']}在当前任务中的空间角色，但按本体净空找不到可验真的安全终止位置，因此不能执行。",
            "frames": [],
            "object_relative_motion": {
                "planning_radius_m": planning_radius,
                "candidate_count": len(side_candidates),
                "rejected_candidates": rejected,
                "world_revision": session["world_revision"],
            },
            "technical_feature_mapping": feature_mapping,
            "decision_latency": {
                "input_to_spatial_candidate_decision_ms": round((perf_counter_ns() - decision_started_ns) / 1_000_000, 4),
                "clock": "perf_counter_ns_monotonic",
            },
            "session": get_session(session["session_id"]),
        }

    selected = min(feasible, key=lambda item: item["route_length_m"])
    frames: list[dict[str, Any]] = []
    segment_start = start
    current_yaw = float(session["state"]["executor_yaw_deg"])
    for waypoint in selected["plan"]["waypoints"]:
        segment_yaw = math.degrees(math.atan2(waypoint[1] - segment_start[1], waypoint[0] - segment_start[0]))
        if math.dist(segment_start, waypoint) > 0.001 and abs(segment_yaw - current_yaw) > 0.1:
            frames.extend(_rotation_frames(segment_start, current_yaw, segment_yaw))
        count = max(3, int(math.dist(segment_start, waypoint) / 0.05) + 1)
        frames.extend(_with_yaw(_interpolate(segment_start, waypoint, count)[1:], segment_yaw))
        segment_start = waypoint
        current_yaw = segment_yaw
    target_yaw = math.degrees(math.atan2(center_y - segment_start[1], center_x - segment_start[0]))
    if operator in {"navigate_near", "grasp_object", "place_object"} and abs(target_yaw - current_yaw) > 0.1:
        frames.extend(_rotation_frames(segment_start, current_yaw, target_yaw))
    _apply_speed_timing(frames, constraints["max_linear_speed_mps"])
    terminal_position = list(selected["position"])
    terminal_fact = "executor_near_object" if operator in {"navigate_near", "grasp_object", "place_object"} else "executor_cleared_object"
    result = {
        **contextual_affordance,
        "status": "fact_established",
        "reason": "object_relative_spatial_fact_physically_verified",
        "prompt": f"已按{entity['label']}当前几何和我的本体净空完成运动，并验真空间关系。",
        "frames": frames,
        "terminal_fact": terminal_fact,
        "terminal_fact_binding": {"entity_ref": entity["entity_id"], "relation": terminal_fact},
        "terminal_verification": {
            "kind": "object_footprint_clearance",
            "entity_ref": entity["entity_id"],
            "expected_relation": terminal_fact,
            "maximum_near_distance_m": clearance + 0.02,
            "must_be_outside_longitudinal_projection": operator == "avoid",
        },
        "object_relative_motion": {
            "selected_side": selected["side"],
            "selected_terminal_position": terminal_position,
            "route_kind": selected["plan"]["route_kind"],
            "route_length_m": selected["route_length_m"],
            "planning_radius_m": planning_radius,
            "candidate_count": len(side_candidates),
            "rejected_candidates": rejected,
            "motion_safety_contract": selected["plan"]["safety_contract"],
            "world_revision": session["world_revision"],
        },
        "effective_execution_envelope": envelope,
        "orchestration_gate_passed": True,
        "technical_feature_mapping": feature_mapping,
        "decision_latency": {
            "input_to_spatial_candidate_decision_ms": round((perf_counter_ns() - decision_started_ns) / 1_000_000, 4),
            "clock": "perf_counter_ns_monotonic",
        },
        "session": get_session(session["session_id"]),
    }
    if task_perception:
        result.update({
            "task_perception_frame": deepcopy(task_perception.get("task_perception_frame")),
            "active_perception_trace": deepcopy(task_perception.get("active_perception_trace", [])),
            "concept_grounding": deepcopy(task_perception.get("concept_grounding")),
            "perception_observation": deepcopy(task_perception.get("perception_observation")),
            "causal_preview": deepcopy(task_perception.get("causal_preview")),
        })
    if operator == "grasp_object":
        result["post_completion"] = {"action": "grasp", "target_entity_ref": entity["entity_id"], "mode": "direct_task"}
        if not contextual_affordance.get("scoped_authorization_present"):
            pending = _create_pending_confirmation(session, contextual_affordance["task_context"])
            pending["candidate_role_bindings"] = deepcopy(perception_bindings)
            pending["perception_evidence_ref"] = task_perception.get("perception_observation", {}).get("observation_id")
            support_text = f"{planning_entity['label']}上的" if planning_entity is not entity else "当前空间中的"
            center_distance = math.dist(start, entity["position"])
            reachable_distance = float(session["executor_profile"]["body_envelope"]["radius_m"]) + float(session["executor_profile"]["arm_reach_m"])
            reach_gap = center_distance > reachable_distance
            observation_summary = (
                task_perception.get("prompt", "")
                if len(task_perception.get("active_perception_trace", [])) > 1
                else f"我先按抓取目标主动观察，识别到{support_text}{entity['label']}，并把该空间关系绑定到当前世界快照。"
            )
            result.update({
                "status": "requires_human_confirmation",
                "reason": "candidate_route_requires_human_confirmation_before_motion_and_grasp",
                "prompt": (
                    observation_summary
                    + (f"它距当前本体中心约{center_distance:.2f}米，超出当前可达边界{reachable_distance:.2f}米，因此需要先移动到其可抓取范围。" if reach_gap else "它已处于当前本体可达范围。")
                    + f"我已生成无碰撞路径、对准、抓取和末态验真的候选计划。确认执行吗？"
                ),
                "pending_confirmation": deepcopy(pending),
                "frames": [],
                "candidate_execution_plan": {
                    "goal_fact": "target_object_in_gripper",
                    "goal_operator": "grasp_object",
                    "role_bindings": {
                        "target": entity["entity_id"],
                        "support": planning_entity["entity_id"] if planning_entity is not entity else None,
                    },
                    "observed_relation": "target_on_top_of_support" if planning_entity is not entity else "target_spatially_grounded",
                    "required_facts": ["target_object_spatially_grounded", "target_object_within_reach", "gripper_available"],
                    "satisfied_facts": ["target_object_spatially_grounded", "gripper_available"],
                    "missing_precondition": "executor_within_grasp_reach" if reach_gap else None,
                    "candidate_process": (
                        (["navigate_to_support"] if planning_entity is not entity else ["navigate_to_bound_target"])
                        if reach_gap else []
                    ) + ["align_end_effector", "grasp_target", "verify_target_in_gripper"],
                    "body_constraint_basis": {
                        "executor_profile_ref": session["executor_profile_id"],
                        "target_center_distance_m": round(center_distance, 3),
                        "reachable_distance_m": round(reachable_distance, 3),
                    },
                    "route_kind": selected["plan"]["route_kind"],
                    "route_length_m": selected["route_length_m"],
                    "world_revision": session["world_revision"],
                    "candidate_only": True,
                    "direct_execution_allowed": False,
                },
            })
    elif operator == "place_object":
        destination_grounding = contextual_affordance.get("grounding_basis", {})
        result["post_completion"] = {
            "action": "place",
            "object_ref": contextual_affordance["theme_entity_ref"],
            "destination_ref": entity["entity_id"],
            "mode": "direct_task",
        }
        result["placement_candidate"] = {
            "operator": "compute_current_body_placement_candidate",
            "theme_entity_ref": contextual_affordance["theme_entity_ref"],
            "destination_entity_ref": entity["entity_id"],
            "support_boundary_source": "current_runtime_geometry",
            "body_workspace_source": session["executor_profile_id"],
            "candidate_only": not contextual_affordance.get("scoped_authorization_present"),
            "absolute_pose_persisted": False,
        }
        if not contextual_affordance.get("scoped_authorization_present"):
            pending = _create_pending_confirmation(session, contextual_affordance["task_context"])
            result.update({
                "status": "requires_human_confirmation",
                "reason": "candidate_route_and_placement_require_human_confirmation",
                "prompt": (
                    f"我已根据当前持有事实把{next((item['label'] for item in session['runtime_objects'] if item['entity_id'] == contextual_affordance['theme_entity_ref']), '当前物体')}绑定为被放置对象。"
                    + (
                        f"你没有明说目的地；我根据它抓取前最后成立的承载关系，将{entity['label']}弱绑定为放置目标。"
                        if destination_grounding.get("source") == "implicit_previous_verified_support"
                        else f"你没有明说目的地；我按当前空间中最近且功能兼容的承载面，将{entity['label']}弱绑定为放置目标。"
                        if destination_grounding.get("source") == "implicit_nearest_compatible_support_candidate"
                        else f"我把明确提及的{entity['label']}绑定为承载目标。"
                    )
                    + "我已按当前本体可达范围和承载面几何生成移动与稳定放置候选。确认执行吗？"
                ),
                "pending_confirmation": deepcopy(pending),
                "frames": [],
                "candidate_execution_plan": {
                    "goal_fact": "object_supported_at_destination",
                    "roles": {"theme": contextual_affordance["theme_entity_ref"], "destination": entity["entity_id"]},
                    "role_grounding": {
                        "theme": {"source": "current_verified_holding_fact", "binding_strength": "verified"},
                        "destination": {
                            "source": destination_grounding.get("source"),
                            "binding_strength": destination_grounding.get("binding_strength"),
                            "requires_confirmation": destination_grounding.get("requires_confirmation", False),
                        },
                    },
                    "preconditions": ["object_in_gripper", "destination_grounded", "placement_pose_feasible"],
                    "route_kind": selected["plan"]["route_kind"],
                    "route_length_m": selected["route_length_m"],
                    "world_revision": session["world_revision"],
                    "candidate_only": True,
                    "direct_execution_allowed": False,
                },
            })
    session["event_history"].append({
        "utterance": contextual_affordance["task_context"],
        "result": result["status"],
        "terminal_fact": terminal_fact,
        "entity_ref": entity["entity_id"],
    })
    return result


def execute_command(session_id: str, utterance: str, scoped_authorization: dict[str, Any] | None = None) -> dict[str, Any]:
    decision_started_ns = perf_counter_ns()
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    text = utterance.strip()
    if _is_holding_state_query(text):
        return _answer_holding_state_query(session)
    if _is_restore_request(text):
        restore_gap = _answer_restore_destination_gap(session)
        if restore_gap:
            return restore_gap
    if _is_object_location_query(text):
        return _answer_object_location_query(session, text)
    if _is_object_presence_query(text):
        observation = _answer_object_presence_query(session, text)
        session["open_world_observation"] = deepcopy(observation)
        observation["session"] = get_session(session_id)
        return observation
    if _is_open_world_observation_query(text):
        observation = _answer_observation_query(session, text)
        session["open_world_observation"] = deepcopy(observation)
        observation["session"] = get_session(session_id)
        return observation
    active_gap_dialogue = session.get("concept_gap_dialogue") or {}
    if active_gap_dialogue.get("status") == "collecting_minimum_causal_contract":
        continued = continue_concept_gap_dialogue(
            active_gap_dialogue,
            answer=text,
            runtime_objects=session["runtime_objects"],
            object_concepts=load_object_concepts()["concepts"],
            current_world_revision=session["world_revision"],
        )
        session["concept_gap_dialogue"] = continued["dialogue"]
        teaching_available = continued.get("knowledge_self_report", {}).get("next_safe_route") == "offer_embodied_teaching"
        return {
            "status": "temporary_effect_contract_compiled" if continued.get("compiled_contract") else "concept_gap_clarification_required",
            "reason": "unknown_event_multi_turn_causal_analysis",
            "prompt": continued["prompt"],
            "knowledge_self_report": continued.get("knowledge_self_report"),
            "concept_gap_analysis": {
                "dialogue_id": continued["dialogue"]["dialogue_id"],
                "slots": deepcopy(continued["dialogue"]["slots"]),
                "pending_slot": continued["dialogue"].get("pending_slot"),
                "analysis_ms": continued.get("analysis_ms"),
            },
            "temporary_effect_contract": continued.get("compiled_contract"),
            "post_action": {
                "action": "offer_embodied_teaching" if teaching_available else (
                    "await_teaching_goal_verification_adapter" if continued.get("compiled_contract") else "await_clarification_answer"
                ),
                "teaching_available": teaching_available,
                "clarification_required": not continued.get("compiled_contract"),
            },
            "session": get_session(session_id),
        }
    relocation_preview = _build_observed_relocation_preview(session, text)
    if relocation_preview:
        return relocation_preview
    task_perception = build_task_perception_result(_scene_for_session(session), session, text)
    perception_bindings = (
        task_perception.get("concept_grounding", {}).get("candidate_bindings", [])
        if task_perception else []
    )
    if task_perception:
        _invalidate_perception_history(session, "superseded_by_new_goal_directed_observation")
        session["perception_history"].append({
            "utterance": text,
            "observation_id": task_perception["perception_observation"]["observation_id"],
            "grounding_status": task_perception["concept_grounding"]["grounding_status"],
            "candidate_bindings": deepcopy(perception_bindings),
            "relation_evidence": deepcopy(task_perception["concept_grounding"].get("relation_evidence")),
            "world_revision": session["world_revision"],
            "runtime_fact_committed": False,
            "current_use_status": "current_candidate",
        })
    if task_perception and task_perception.get("concept_grounding", {}).get("grounding_status") != "spatially_grounded":
        task_perception["session"] = get_session(session_id)
        return task_perception
    contextual_affordance = resolve_contextual_affordance_request(
        text,
        entities=session["runtime_objects"],
        object_concepts=load_object_concepts()["concepts"],
        executor_profile=session["executor_profile"],
        runtime_state=session["state"],
        governance_overlay=session.get("protection_policy_overlay"),
        scoped_authorization=scoped_authorization,
        confirmed_bindings=session.get("confirmed_visual_bindings", []),
        perception_bindings=perception_bindings,
    )
    if contextual_affordance:
        if task_perception:
            contextual_affordance["task_perception"] = task_perception
        if contextual_affordance["available"] and contextual_affordance["operator_candidate"] in {"navigate_near", "avoid", "grasp_object", "place_object"}:
            return _build_object_relative_motion(session, contextual_affordance, decision_started_ns)
        return {
            **contextual_affordance,
            "prompt": contextual_affordance["explanation"],
            "session": get_session(session_id),
        }
    perception_result = build_task_perception_result(_scene_for_session(session), session, text)
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
        gap_started = start_concept_gap_dialogue(
            utterance=text,
            runtime_objects=session["runtime_objects"],
            object_concepts=load_object_concepts()["concepts"],
            world_revision=session["world_revision"],
        )
        session["concept_gap_dialogue"] = gap_started["dialogue"]
        compiled_contract = gap_started.get("compiled_contract")
        teaching_available = gap_started.get("knowledge_self_report", {}).get("next_safe_route") == "offer_embodied_teaching"
        return {
            "status": "temporary_effect_contract_compiled" if compiled_contract else "concept_gap_clarification_required",
            "reason": "no_stable_factory_event_concept_match",
            "prompt": gap_started["prompt"],
            "knowledge_self_report": gap_started.get("knowledge_self_report"),
            "concept_gap": {
                "utterance": text,
                "understanding_status": "operator_and_goal_fact_unknown",
                "known_state_transition": None,
                "unknown_action_surface": gap_started["analysis"]["unknown_action_surface"],
                "recognized_entities": gap_started["analysis"]["recognized_entities"],
                "known": gap_started["analysis"]["known"],
                "missing_information": gap_started["analysis"]["unknown"],
                "question_selection_policy": gap_started["analysis"]["question_selection_policy"],
                "compositional_analysis": gap_started["analysis"].get("compositional_analysis", {}),
                "analysis_ms": gap_started["analysis"]["analysis_ms"],
                "next_actions": ["answer_minimum_causal_question", "offer_embodied_teaching_after_goal_contract"],
                "candidate_only": True,
                "direct_execution_allowed": False,
            },
            "concept_gap_analysis": {
                "dialogue_id": gap_started["dialogue"]["dialogue_id"],
                "slots": deepcopy(gap_started["dialogue"]["slots"]),
                "pending_slot": gap_started["dialogue"].get("pending_slot"),
                "compositional_analysis": gap_started["analysis"].get("compositional_analysis", {}),
                "analysis_ms": gap_started["analysis"]["analysis_ms"],
            },
            "post_action": {
                "action": "offer_embodied_teaching" if teaching_available else (
                    "await_teaching_goal_verification_adapter" if compiled_contract else "request_goal_clarification_or_offer_embodied_teaching"
                ),
                "teaching_available": teaching_available,
                "clarification_required": not compiled_contract,
            },
            "temporary_effect_contract": compiled_contract,
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
    motion_plan = _plan_verified_motion(session, start, target, planning_radius, preserve_terminal_goal=False)
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
            session["state"]["active_region"] = _region_for(safe_target, _scene_for_session(session))
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
    session["state"]["active_region"] = _region_for(target, _scene_for_session(session))
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


def _context_confirmation_value(utterance: str) -> bool | None:
    normalized = re.sub(r"[\s，。！？、,.!?]+", "", utterance.strip().lower())
    if normalized in {"是的", "对", "对的", "可以", "好的", "好", "正确", "ok", "okay", "没错", "就是", "确认", "行", "嗯", "恩", "是"}:
        return True
    if (normalized.startswith("是") or normalized.startswith("对")) and "可以" in normalized:
        return True
    if "可以" in normalized and any(token in normalized for token in ("直接", "去拿", "执行", "继续")):
        return True
    if normalized in {"不是", "不对", "不可以", "不要", "取消", "否", "不", "错了", "不正确", "no", "不是这个"}:
        return False
    return None


def begin_motion_command(
    session_id: str,
    utterance: str,
    scoped_authorization: dict[str, Any] | None = None,
    internal_stage: bool = False,
) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    text = utterance.strip()
    if text in {"暂停当前任务", "暂停任务", "先别做了"}:
        suspended = _suspend_active_intent(session)
        if suspended:
            return {"status": suspended["status"], "immediate_result": suspended, "session": suspended["session"]}
    if text in {"继续当前任务", "继续任务", "恢复任务"}:
        resumed = _resume_active_intent(session)
        if resumed:
            resumed["immediate_result"]["session"] = get_session(session_id)
            return resumed
    pending = session.get("pending_confirmation")
    confirmation_value = _context_confirmation_value(utterance)
    if pending and confirmation_value is not None and not scoped_authorization:
        confirmed = confirm_pending_motion(session_id, pending["confirmation_id"], confirmation_value)
        if confirmed.get("status") == "observation_candidate_confirmed":
            return {"status": confirmed["status"], "immediate_result": confirmed, "session": confirmed.get("session")}
        return confirmed
    long_intent = None if internal_stage or scoped_authorization else _create_transfer_intent(session, text)
    if long_intent:
        prepared = _prepare_long_intent_stage(session, long_intent)
        prepared["immediate_result"]["session"] = get_session(session_id)
        return prepared
    factory_groundable_task = activate_task_perception(utterance) is not None
    if (
        not factory_groundable_task
        and not (session.get("concept_gap_dialogue") or {}).get("status") == "collecting_minimum_causal_contract"
    ):
        recalled = _recall_trusted_experience(utterance)
        if recalled:
            started = begin_persisted_experience_replay(session_id, recalled["experience_id"])
            started["experience_recall"] = {
                "match_basis": "language_trigger_and_target_concept_alias",
                "experience_id": recalled["experience_id"],
                "candidate_only_before_runtime_rebinding": True,
                "trajectory_reused": False,
            }
            return started
    before = deepcopy(session)
    result = execute_command(session_id, utterance, scoped_authorization)
    pending_confirmation = deepcopy(SESSIONS[session_id].get("pending_confirmation"))
    perception_history = deepcopy(SESSIONS[session_id].get("perception_history", []))
    concept_gap_dialogue = deepcopy(SESSIONS[session_id].get("concept_gap_dialogue"))
    SESSIONS[session_id] = before
    frames = result.get("frames", [])
    if not frames:
        if pending_confirmation:
            SESSIONS[session_id]["pending_confirmation"] = pending_confirmation
        if result.get("task_perception_frame"):
            SESSIONS[session_id]["perception_history"] = perception_history
        if concept_gap_dialogue:
            SESSIONS[session_id]["concept_gap_dialogue"] = concept_gap_dialogue
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
        "post_completion": deepcopy(result.get("post_completion")),
        "execution_intent": _post_completion_signature(result.get("post_completion")),
        "continuation_authorized": _authorization_is_current(before, utterance, scoped_authorization),
        "execution_collision_radius_m": (
            result.get("effective_execution_envelope", {}).get("effective_constraints", {}).get("body_radius_m", 0.0)
            + result.get("effective_execution_envelope", {}).get("effective_constraints", {}).get("minimum_avoidance_distance_m", 0.0)
        ) or before["executor_profile"]["body_envelope"]["radius_m"],
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
    if pending.get("kind") == "observation_candidate":
        if pending.get("authorized_world_revision") != session["world_revision"] or pending.get("policy_binding") != _policy_binding(session):
            _revoke_pending_confirmation(session, "observation_context_changed")
            return {"status": "confirmation_not_current", "reason": "observation_context_changed_before_confirmation", "session": get_session(session_id)}
        ref = next((item for item in session.get("runtime_objects", []) if item.get("entity_id") in pending.get("candidate_refs", [])), None)
        if not ref:
            session["pending_confirmation"] = None
            return {"status": "confirmation_not_current", "reason": "observation_candidate_no_longer_present", "session": get_session(session_id)}
        binding = {
            "concept_id": pending["concept_id"],
            "entity_ref": ref["entity_id"],
            "label": ref.get("label"),
            "world_revision": session["world_revision"],
            "binding_source": "human_confirmed_visual_candidate",
            "candidate_only": False,
            "direct_execution_allowed": False,
            "verification_receipt": {
                "human_semantic_confirmation": True,
                "physical_observation_consistent": True,
                "physical_observation_basis": "current_runtime_entity_present_at_observed_binding",
                "world_revision": session["world_revision"],
            },
        }
        session.setdefault("confirmed_visual_bindings", []).append(binding)
        session["pending_confirmation"] = None
        session["authorization_history"].append({**deepcopy(pending), "status": "observation_confirmed"})
        return {
            "status": "observation_candidate_confirmed",
            "prompt": f"已确认：{binding['label']}是当前空间中的目标对象；人类确认与当前物理观测一致。我会把这个空间绑定用于后续判断。",
            "confirmed_visual_binding": deepcopy(binding),
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
    if result.get("job_id") and pending.get("long_intent_id"):
        job = MOTION_JOBS.get(result["job_id"])
        if job:
            job["long_intent_id"] = pending["long_intent_id"]
            job["long_stage_id"] = pending.get("long_stage_id")
    session["pending_confirmation"] = None
    consumed = {**authorization, "status": "consumed", "consumed_by": result.get("job_id") or "immediate_execution_attempt"}
    session["authorization_history"].append(consumed)
    result["scoped_authorization"] = deepcopy(consumed)
    result["session"] = get_session(session_id)
    if result.get("immediate_result"):
        result["immediate_result"]["session"] = get_session(session_id)
        result["immediate_result"]["scoped_authorization"] = deepcopy(consumed)
    return result


def _post_completion_signature(post_completion: dict[str, Any] | None) -> dict[str, Any]:
    post_completion = post_completion or {}
    action = post_completion.get("action")
    if action == "grasp":
        return {"action": action, "target_entity_ref": post_completion.get("target_entity_ref")}
    if action == "place":
        return {
            "action": action,
            "object_ref": post_completion.get("object_ref"),
            "destination_ref": post_completion.get("destination_ref"),
        }
    return {"action": action}


def _resume_after_local_path_change(job: dict[str, Any], session: dict[str, Any], reason: str, obstacle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Replan geometry while preserving a verified task intent, never a stale trajectory."""
    original_intent = deepcopy(job.get("execution_intent") or _post_completion_signature(job.get("post_completion")))
    if not job.get("continuation_authorized") or not original_intent.get("action"):
        replacement = begin_motion_command(job["session_id"], job["utterance"])
        return {
            "status": "path_invalidated_and_replanned",
            "reason": reason,
            "old_job_id": job["job_id"],
            "blocking_obstacle": obstacle,
            "replacement": replacement,
            "continuation_status": "confirmation_required_for_new_execution_intent",
        }

    continuation_authorization = {
        "status": "authorized",
        "authorization_id": f"continuation_{job['job_id']}",
        "command_hash": _command_hash(job["utterance"]),
        "authorized_world_revision": session["world_revision"],
        "policy_binding": _policy_binding(session),
        "scope": "same_verified_intent_after_local_path_replan",
        "original_execution_intent": original_intent,
    }
    replacement = begin_motion_command(job["session_id"], job["utterance"], continuation_authorization)
    replacement_job = MOTION_JOBS.get(replacement.get("job_id", ""))
    replacement_intent = _post_completion_signature((replacement_job or {}).get("post_completion"))
    if replacement_job and replacement_intent == original_intent:
        replacement["continuation_status"] = "same_intent_reobserved_and_replanned"
        replacement["preserved_execution_intent"] = original_intent
        return {
            "status": "path_invalidated_and_replanned",
            "reason": reason,
            "old_job_id": job["job_id"],
            "blocking_obstacle": obstacle,
            "replacement": replacement,
            "continuation_status": "same_intent_reobserved_and_replanned",
        }

    if replacement_job:
        MOTION_JOBS.pop(replacement_job["job_id"], None)
    immediate = replacement.get("immediate_result") or replacement
    return {
        "status": "task_intent_reconfirmation_required",
        "reason": "local_path_changed_and_execution_intent_could_not_be_preserved",
        "old_job_id": job["job_id"],
        "blocking_obstacle": obstacle,
        "original_execution_intent": original_intent,
        "replacement_candidate": immediate,
        "prompt": "局部路径已经变化，但重新观察后无法确认目标对象和原已确认意图仍一致，因此没有继续执行，请确认新的候选计划。",
        "session": get_session(job["session_id"]),
    }


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
        reason = "runtime_policy_revision_changed" if session["policy_revision"] != job["planned_policy_revision"] else "runtime_world_revision_changed"
        if session["policy_revision"] == job["planned_policy_revision"]:
            return _resume_after_local_path_change(job, session, reason)
        replacement = begin_motion_command(job["session_id"], job["utterance"])
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
    radius = job.get("execution_collision_radius_m", session["executor_profile"]["body_envelope"]["radius_m"])
    collider = _collider_at(frame["position"], radius, session, _scene_for_session(session))
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
        return _resume_after_local_path_change(job, session, "next_frame_swept_body_not_clear", collider)
    session["state"]["executor_position"] = list(frame["position"])
    if frame.get("yaw_deg") is not None:
        session["state"]["executor_yaw_deg"] = frame["yaw_deg"]
    session["state"]["active_region"] = _region_for(frame["position"], _scene_for_session(session))
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
    terminal_verification = result.get("terminal_verification")
    if terminal_verification:
        entity = next(
            (item for item in session["runtime_objects"] if item["entity_id"] == terminal_verification["entity_ref"]),
            None,
        )
        terminal_distance = _distance_to_object_footprint(session["state"]["executor_position"], entity) if entity else math.inf
        relation_verified = bool(entity) and terminal_distance <= terminal_verification["maximum_near_distance_m"]
        if terminal_verification.get("must_be_outside_longitudinal_projection") and entity:
            dx = abs(session["state"]["executor_position"][0] - entity["position"][0])
            dy = abs(session["state"]["executor_position"][1] - entity["position"][1])
            relation_verified = relation_verified and (
                dx > float(entity["size"][0]) / 2 or dy > float(entity["size"][1]) / 2
            )
        result["terminal_verification_evidence"] = {
            "entity_ref": terminal_verification["entity_ref"],
            "object_footprint_distance_m": round(terminal_distance, 4) if math.isfinite(terminal_distance) else None,
            "relation_verified": relation_verified,
            "world_revision": session["world_revision"],
        }
        if not relation_verified:
            result.update({
                "status": "terminal_fact_verification_failed",
                "reason": "object_relative_relation_not_established_at_final_frame",
                "terminal_fact": None,
                "prompt": "运动已经停止，但目标空间关系没有通过末帧验真，不能把它记为事实。",
            })
    if job.get("teaching_action"):
        _record_completed_teaching_motion(session, job, result)
    if (job.get("post_completion") or {}).get("action") == "grasp" and (job.get("post_completion") or {}).get("mode") == "direct_task":
        grasp = _apply_verified_grasp(session, job["post_completion"]["target_entity_ref"], "human_confirmed_candidate_task")
        if grasp.get("status") == "fact_established":
            result.update(grasp)
            result["status"] = "fact_established"
            result["execution_chain"] = ["confirmed_target_binding", "route_replanned_from_current_state", "executor_within_grasp_reach", "grasp_physically_verified"]
        else:
            result = grasp
    elif (job.get("post_completion") or {}).get("action") == "place" and (job.get("post_completion") or {}).get("mode") == "direct_task":
        placement = _apply_verified_place(
            session,
            job["post_completion"]["object_ref"],
            job["post_completion"]["destination_ref"],
            "human_confirmed_candidate_task",
        )
        if placement.get("status") == "fact_established":
            result.update(placement)
            result["status"] = "fact_established"
            result["execution_chain"] = [
                "current_holding_fact_bound_as_theme",
                "compatible_support_bound_as_destination",
                "route_replanned_from_current_state",
                "placement_pose_computed_from_current_geometry",
                "stable_support_relation_physically_verified",
            ]
        else:
            result = placement
    elif (job.get("post_completion") or {}).get("action") == "grasp":
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
    intent = (session.get("long_horizon_intents") or {}).get(job.get("long_intent_id"))
    if intent:
        if result.get("status") == "fact_established":
            stage_outcome = _prepare_long_intent_stage(session, intent)
            result["long_horizon_intent"] = stage_outcome.get("long_horizon_intent", _long_intent_view(intent))
            if stage_outcome.get("status") == "long_intent_completed":
                result["prompt"] = "当前阶段已验真，长程目标的终止事实也已成立。"
            else:
                next_candidate = stage_outcome.get("immediate_result") or {}
                result["next_stage_candidate"] = deepcopy(next_candidate)
                result["candidate_execution_plan"] = deepcopy(next_candidate.get("candidate_execution_plan"))
                result["pending_confirmation"] = deepcopy(next_candidate.get("pending_confirmation"))
                result["prompt"] = (
                    "当前阶段已通过物理验真；长程目标尚未完成。"
                    + (next_candidate.get("prompt") or "我已根据当前状态生成下一阶段候选。")
                )
        else:
            intent["lifecycle"] = "awaiting_correction"
            result["long_horizon_intent"] = _long_intent_view(intent)
    result["session"] = get_session(job["session_id"])
    session["event_history"].append({"utterance": job["utterance"], "result": result.get("status"), "route_kind": result.get("route_kind")})
    return {"status": "motion_completed", "job_id": job_id, "frame": frame, "result": result, "session": get_session(job["session_id"])}


def _first_collision(session: dict[str, Any], start: list[float], target: list[float], radius: float) -> dict[str, Any] | None:
    scene = _scene_for_session(session)
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
    preserve_terminal_goal: bool = True,
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
        safety_contract["terminal_pose_verified"] = _collider_at(target, radius, session, _scene_for_session(session)) is None
        return {"outcome": "verified", "route_kind": "direct", "waypoints": [target], "safety_contract": safety_contract}
    obstacle = direct_collision["obstacle"]
    if obstacle.get("obstacle_class") != "movable_obstacle" or obstacle.get("mode") == "narrow":
        return {"outcome": "blocked", "route_kind": "none", "blocking_collision": direct_collision, "safety_contract": safety_contract}
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for side_name, side_sign in (("left", 1.0), ("right", -1.0)):
        waypoints = _detour_candidate(start, target, obstacle, radius, side_sign, preserve_terminal_goal)
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
        if _collider_at(waypoints[-1], radius, session, _scene_for_session(session)):
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
    preserve_terminal_goal: bool,
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
    # For a goal-directed task, clearing an obstacle is only an intermediate
    # safety condition and the final waypoint remains the original goal. A
    # bare relative-motion request has no external task goal beyond clearance.
    return [before, after_side, after_axis, list(target)] if preserve_terminal_goal else [before, after_side, after_axis]


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
