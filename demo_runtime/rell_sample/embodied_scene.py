from __future__ import annotations

import hashlib
import heapq
import json
import math
import re
from datetime import datetime, timezone
from time import perf_counter_ns
from copy import deepcopy
from pathlib import Path
from typing import Any

from concept_core.factory_event_units import FACTORY_EVENT_CONCEPT_UNITS, build_factory_inability_diagnosis, find_factory_event_concepts_by_text
from concept_core.concept_gap_dialogue import continue_concept_gap_dialogue, start_concept_gap_dialogue
from concept_core.contextual_affordance import resolve_contextual_affordance_request
from concept_core.context_projection import build_context_projection, compact_intent_capsule
from concept_core.functional_object_reasoning import build_functional_object_catalog, build_functional_profile, evaluate_role_compatibility
from concept_core.factory_state_facts import build_factory_state_catalog, derive_runtime_fact_snapshot, explain_prerequisite_gaps
from concept_core.lightweight_orchestrator import build_lightweight_causal_candidate, build_lightweight_orchestrator_catalog
from concept_core.language_concept_composer import compose_language_concepts, normalize_language_text
from concept_core.perceptual_grounding import COLOR_ALIASES, COLOR_NAMES, activate_task_perception, build_open_world_observation, build_task_perception_result, load_object_concepts, observed_perceptual_attributes
from concept_core.process_template_resolver import normalize_perception_gap, resolve_process_request
from concept_core.semantic_grounding import (
    build_grounded_intent_frame,
    build_observation_evidence_set,
    build_semantic_constraint_frame,
    ground_semantic_role,
)
from concept_core.situated_event_reasoning import (
    compile_situated_event_frame,
    create_hierarchical_intent_graph,
    facts_from_runtime_state,
    record_verified_fact as record_intent_verified_fact,
)
from concept_core.visual_concept_packs import build_visual_pack_catalog
from causal_task_graph_runtime import (
    apply_condition_answer,
    causal_graph_activation_matches,
    established_graph_facts,
    evaluate_causal_graph,
    initialize_causal_graph_runtime,
    record_graph_facts,
    select_condition_clarification,
)
from hospitality_task_graph import (
    build_hospitality_orchestration_view,
    build_hospitality_task_graph,
    unresolved_hospitality_conditions,
)
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
    "hospitality_guest": Path(__file__).resolve().parent / "data" / "hospitality_guest_scene.json",
}
SESSIONS: dict[str, dict[str, Any]] = {}
MOTION_JOBS: dict[str, dict[str, Any]] = {}
RUNTIME_DEBUG_LOG = Path(__file__).resolve().parent / "runtime_debug.jsonl"


def _debug_runtime(event: str, session: dict[str, Any], **details: Any) -> None:
    """Append a compact server-side trace without changing task state."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "session_id": session.get("session_id"),
        "active_intent_id": session.get("active_intent_id"),
        "world_revision": session.get("world_revision"),
        "role_dialogue": bool(session.get("role_clarification_dialogue")),
        "details": details,
    }
    intent = (session.get("long_horizon_intents") or {}).get(session.get("active_intent_id"))
    if intent:
        record["intent"] = {
            "lifecycle": intent.get("lifecycle"),
            "stage": (intent.get("current_stage") or {}).get("stage_id"),
            "verified_facts": list(intent.get("verified_facts", [])),
            "role_bindings": deepcopy(intent.get("role_bindings", {})),
        }
    try:
        with RUNTIME_DEBUG_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _attach_runtime_diagnostic(result: dict[str, Any], session: dict[str, Any], stage: dict[str, Any] | None = None) -> dict[str, Any]:
    """Promote any non-success stop into an explainable, recoverable event."""
    status = str(result.get("status") or "")
    if status in {"fact_established", "motion_completed", "stage_ready", "role_clarification_required"}:
        return result
    if result.get("runtime_diagnostic"):
        return result
    reason = result.get("reason") or result.get("error") or status or "unknown_failure"
    category = "unknown_runtime_failure"
    if "reach" in reason or "terminal_pose" in reason:
        category = "capability_or_terminal_pose_boundary"
    elif "collision" in reason or "blocked" in reason or "obstacle" in reason:
        category = "route_or_collision_blocked"
    elif "precondition" in reason or "ground" in reason:
        category = "missing_causal_precondition"
    elif "ambig" in reason or "candidate" in reason:
        category = "role_or_perception_ambiguity"
    diagnostic = {
        "category": category,
        "stage": (stage or {}).get("stage_id") or result.get("stage_id"),
        "reason": reason,
        "evidence": {
            "entity_ref": result.get("entity_ref") or result.get("target_entity_ref"),
            "blocking_entity": result.get("blocking_entity") or result.get("collider", {}).get("entity_id"),
            "world_revision": session.get("world_revision"),
            "rejected_candidates": (result.get("object_relative_motion") or {}).get("rejected_candidates", []),
        },
        "recovery_options": result.get("next_safe_actions") or [
            "继续观察当前世界状态",
            "改变目标或移除阻碍",
            "向人类询问缺失的最小条件",
        ],
        "requires_human_input": category in {"capability_or_terminal_pose_boundary", "missing_causal_precondition", "unknown_runtime_failure"},
    }
    result["runtime_diagnostic"] = diagnostic
    session["last_runtime_diagnostic"] = deepcopy(diagnostic)
    if not result.get("prompt"):
        result["prompt"] = (
            f"当前阶段{diagnostic['stage'] or '未命名'}已暂停。"
            f"原因：{reason}。"
            f"下一步：{'；'.join(diagnostic['recovery_options'])}。"
        )
    return result
_LANGUAGE_OBJECT_CONCEPT_CACHE: list[dict[str, Any]] | None = None


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
    if executor_profile_id not in scene["executor_profiles"] and scene_id == "hospitality_guest":
        # Scene transitions may preserve the previous page's body query. The
        # hospitality scene has one declared embodiment, so bind it explicitly
        # instead of returning an unusable session to the frontend.
        available_profiles = list(scene["executor_profiles"])
        if len(available_profiles) == 1:
            executor_profile_id = available_profiles[0]
    if executor_profile_id not in scene["executor_profiles"]:
        return {"error": "executor_profile_not_found", "executor_profile_id": executor_profile_id}
    language_concepts = _language_object_concepts()
    compose_language_concepts(
        "",
        event_concepts=FACTORY_EVENT_CONCEPT_UNITS,
        object_concepts=language_concepts,
    )
    session_id = "embodied_" + hashlib.sha1(f"{scene['scene_id']}|{len(SESSIONS) + 1}".encode()).hexdigest()[:12]
    state = deepcopy(scene["initial_state"])
    human_participant_refs = [
        item.get("entity_id")
        for item in scene["objects"]
        if item.get("active") is not False
        and item.get("kind") == "human_recipient"
        and item.get("entity_id")
    ]
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
        "interaction_role_bindings": {
            "human_speaker": human_participant_refs[0]
            if len(human_participant_refs) == 1 else None,
        },
        "teaching_session": None,
        "learned_experience": None,
        "available_local_experiences": _experience_catalog(),
        "state": state,
        "active_obstacles": [],
        "world_revision": 0,
        "event_history": [],
        "episodic_fact_memory": [],
        "interaction_turn": 0,
        "last_context_projection": None,
        "concept_gap_dialogue": None,
        "open_world_observation": None,
        "confirmed_visual_bindings": [],
        "language_adapters": [],
        "language_interpretation_history": [],
        "dialogue_focus_entities": [],
        "last_language_understanding": None,
        "current_observation_evidence": None,
        "observation_evidence_ledger": [],
        "grounded_intent_frame_history": [],
        "long_horizon_intents": {},
        "completed_intent_archive": [],
        "active_intent_id": None,
        "intent_activation_stack": [],
        "compound_command_sequence": None,
        "relational_reference_dialogue": None,
        "situated_event_frame_history": [],
        "role_clarification_dialogue": None,
        "evidence_gap_dialogue": None,
        "process_gap_dialogue": None,
        "human_reported_fact_candidates": [],
        "causal_graph_clarification": None,
    }
    if scene_id == "hospitality_guest":
        hospitality_graph = build_hospitality_task_graph(session["runtime_objects"])
        session["task_graph"] = hospitality_graph
        session["task_graph_unresolved_conditions"] = unresolved_hospitality_conditions(hospitality_graph)
        session["task_graph_orchestration"] = build_hospitality_orchestration_view(hospitality_graph)
        session["task_graph_state"] = "awaiting_condition_resolution" if session["task_graph_unresolved_conditions"] else "ready_for_orchestration"
    _holding_by_effector(session)
    _sync_primary_holding(session)
    SESSIONS[session_id] = session
    return deepcopy(session)


def _long_intent_view(intent: dict[str, Any]) -> dict[str, Any]:
    return {
        "intent_id": intent["intent_id"],
        "intent_type": intent.get("intent_type"),
        "goal_fact": intent["goal_fact"],
        "role_bindings": deepcopy(intent["role_bindings"]),
        "source_language_frame": deepcopy(intent.get("source_language_frame")),
        "lifecycle": intent["lifecycle"],
        "verified_facts": list(intent["verified_facts"]),
        "verified_facts_scope": "historical_intent_execution_evidence",
        "current_world_facts_rederived_before_arbitration": True,
        "current_stage": deepcopy(intent.get("current_stage")),
        "resume_envelope": deepcopy(intent.get("resume_envelope")),
        "trajectory_persisted": False,
        "hierarchical_intent_graph": deepcopy(intent.get("hierarchical_intent_graph")),
        "causal_graph_runtime": deepcopy(intent.get("causal_graph_runtime")),
    }


def _archive_and_release_task_context(
    session: dict[str, Any],
    intent: dict[str, Any],
    *,
    lifecycle: str,
    release_reason: str,
    archive_key: str,
) -> dict[str, Any]:
    capsule = compact_intent_capsule(
        intent,
        world_revision=int(session.get("world_revision", 0)),
        lifecycle=lifecycle,
        release_reason=release_reason,
    )
    archive = session.setdefault(archive_key, [])
    archive.append(capsule)
    if len(archive) > 16:
        del archive[:-16]

    runtime_index = {
        item.get("entity_id"): item
        for item in session.get("runtime_objects", [])
        if item.get("entity_id") and item.get("active") is not False
    }
    concepts = _language_object_concepts()
    role_refs = []
    for value in (intent.get("role_bindings") or {}).values():
        values = value if isinstance(value, list) else [value]
        role_refs.extend(ref for ref in values if isinstance(ref, str))
    terminal_focus = []
    for ref in dict.fromkeys(role_refs):
        entity = runtime_index.get(ref)
        if not entity:
            continue
        concept = next(
            (
                item for item in concepts
                if entity.get("kind") in item.get("compatible_kinds", [])
            ),
            {},
        )
        terminal_focus.append({
            "entity_ref": ref,
            "label": entity.get("label"),
            "concept_id": concept.get("concept_id"),
            "display_name": concept.get("display_name") or entity.get("label"),
            "compatible_kinds": list(concept.get("compatible_kinds", [entity.get("kind")])),
            "functional_affordances": list(concept.get("functional_affordances", [])),
            "focus_source": "released_task_terminal_role",
            "world_revision": session.get("world_revision"),
            "created_turn": int(session.get("interaction_turn", 0)),
            "expires_after_turn": int(session.get("interaction_turn", 0)) + 4,
        })
        if len(terminal_focus) >= 4:
            break
    session["dialogue_focus_entities"] = terminal_focus

    # Task mechanics are disposable. Physical effects remain in runtime_objects
    # and verified causal transitions remain only as compact episode capsules.
    for key in (
        "event_history",
        "perception_history",
        "confirmed_visual_bindings",
        "language_interpretation_history",
        "grounded_intent_frame_history",
        "situated_event_frame_history",
        "observation_evidence_ledger",
        "human_reported_fact_candidates",
    ):
        session[key] = []
    session["current_observation_evidence"] = None
    session["last_language_understanding"] = None
    session["pending_confirmation"] = None
    session["pending_water_container_ref"] = None
    session["open_world_observation"] = None
    terminal_roles = {
        f"terminal_role_{index}": {
            "entity_ref": item.get("entity_ref"),
            "compatible_kinds": item.get("compatible_kinds", []),
        }
        for index, item in enumerate(terminal_focus)
        if item.get("entity_ref")
    }
    projection = build_context_projection(
        {"role_bindings": terminal_roles, "entity_mentions": [], "event_candidates": []},
        runtime_objects=session.get("runtime_objects", []),
        current_facts=facts_from_runtime_state(
            session.get("runtime_objects", []),
            session.get("state", {}),
            int(session.get("world_revision", 0)),
        ),
        active_intent=None,
        recent_episodes=session.get("episodic_fact_memory", []),
        recent_intent_capsules=session.get("completed_intent_archive", []),
        interaction_role_bindings=session.get("interaction_role_bindings", {}),
        dialogue_focus_entities=terminal_focus,
        world_revision=int(session.get("world_revision", 0)),
        current_turn=int(session.get("interaction_turn", 0)),
    )
    projection.setdefault("retention_contract", {})[
        "completed_task_snapshot_released"
    ] = True
    session["last_context_projection"] = projection
    for key in (
        "concept_gap_dialogue",
        "relational_reference_dialogue",
        "role_clarification_dialogue",
        "evidence_gap_dialogue",
        "process_gap_dialogue",
        "causal_graph_clarification",
    ):
        session[key] = None
    return capsule


def _attach_hierarchical_intent_graph(intent: dict[str, Any]) -> None:
    dependency = intent.get("dependency_graph", {})
    intent["hierarchical_intent_graph"] = create_hierarchical_intent_graph(
        intent["intent_id"],
        root_goal_facts=[intent["goal_fact"]],
        stages=dependency.get("nodes", []),
    )


def _conceptual_reference_for_entity(entity: dict[str, Any]) -> str:
    """Use a concept alias in derived stages, never an incidental visual label."""
    for concept in load_object_concepts()["concepts"]:
        if entity.get("kind") not in concept.get("compatible_kinds", []):
            continue
        concept_properties = set(concept.get("physical_properties", []))
        if entity.get("affordances") or (
            entity.get("fixed") is False and "fixed_asset" in concept_properties
        ):
            return str(entity.get("label") or concept.get("display_name") or "目标对象")
        aliases = sorted((alias for alias in concept.get("aliases", []) if len(alias) > 1), key=len, reverse=True)
        if aliases:
            return aliases[0]
    return str(entity.get("label") or "目标对象")


def _create_transfer_intent(
    session: dict[str, Any], utterance: str, language_analysis: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    normalized = re.sub(r"[，。！？、,.!?\s]+", "", utterance)
    transfer_tokens = ("放到", "放在", "摆到", "摆在", "搁到", "搁在", "移到", "搬到", "挪到")
    restore_requested = any(token in normalized for token in ("放回", "放回去", "放回原处", "还回去"))
    if not restore_requested and not any(token in normalized for token in transfer_tokens):
        return None
    concepts = load_object_concepts()["concepts"]
    process_resolution = (language_analysis or {}).get("process_template_resolution") or {}
    process_bindings = process_resolution.get("bindings", {}) if process_resolution.get("template_id") == "place_object" else {}
    resolved_theme_binding = process_bindings.get("theme") or {}
    resolved_destination_binding = process_bindings.get("destination") or {}
    # Process bindings exist only after the shared grounder has reduced the
    # current, version-matched candidate set to one entity. Their evidence
    # strength describes how the referent was selected, not whether a
    # candidate intent may be formed; execution authorization remains separate.
    resolved_theme_ref = resolved_theme_binding.get("value_ref")
    resolved_destination_ref = resolved_destination_binding.get("value_ref")
    runtime_index = {item.get("entity_id"): item for item in session.get("runtime_objects", [])}
    semantic_roles = ((language_analysis or {}).get("semantic_constraint_frame") or {}).get("roles", {})
    for role_name, resolved_ref in (("theme", resolved_theme_ref), ("destination", resolved_destination_ref)):
        if not resolved_ref:
            continue
        semantic_kinds = set((semantic_roles.get(role_name) or {}).get("compatible_kinds") or [])
        resolved_entity = runtime_index.get(resolved_ref)
        if semantic_kinds and (not resolved_entity or resolved_entity.get("kind") not in semantic_kinds):
            if role_name == "theme":
                resolved_theme_ref = None
            else:
                resolved_destination_ref = None
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
    if resolved_theme_ref:
        theme_candidates = [
            item for item in session["runtime_objects"]
            if item.get("active") is not False and item.get("entity_id") == resolved_theme_ref
        ]
    elif not theme_concepts and held_theme and (deictic_theme_requested or restore_requested):
        theme_candidates = [held_theme]
    elif len(theme_concepts) == 1:
        theme_candidates = [
            item for item in session["runtime_objects"]
            if item.get("active") is not False and item.get("kind") in theme_concepts[0].get("compatible_kinds", [])
        ]
        perception_activation = activate_task_perception(utterance)
        target_constraints = (perception_activation or {}).get("target_constraints", {})
        if target_constraints:
            theme_candidates = [
                item for item in theme_candidates
                if all(observed_perceptual_attributes(item).get(key) == value for key, value in target_constraints.items())
            ]
    else:
        return None
    if resolved_destination_ref and not restore_requested:
        destinations = [
            item for item in session["runtime_objects"]
            if item.get("active") is not False and item.get("entity_id") == resolved_destination_ref
        ]
    elif restore_requested:
        previous_support_ref = theme_candidates[0].get("last_support_ref") if len(theme_candidates) == 1 else None
        destinations = [item for item in session["runtime_objects"] if item.get("entity_id") == previous_support_ref]
    elif len(destination_concepts) == 1:
        destinations = [
            item for item in session["runtime_objects"]
            if item.get("active") is not False and item.get("kind") in destination_concepts[0].get("compatible_kinds", [])
        ]
    else:
        return None
    if resolved_destination_ref:
        pass
    elif len(explicit_destination_entities) == 1 and not restore_requested:
        destinations = explicit_destination_entities
    elif not restore_requested and len(destinations) > 1:
        confirmed_destination_refs = {
            item.get("entity_ref")
            for item in session.get("confirmed_visual_bindings", [])
            if item.get("concept_id") == "concept_support_surface"
            and item.get("world_revision") == session["world_revision"]
            and item.get("entity_ref")
        }
        confirmed_destinations = [
            item for item in destinations if item.get("entity_id") in confirmed_destination_refs
        ]
        if len(confirmed_destinations) == 1:
            destinations = confirmed_destinations
    if resolved_theme_ref:
        theme_candidates = [item for item in theme_candidates if item.get("entity_id") == resolved_theme_ref]
    if resolved_destination_ref:
        destinations = [item for item in destinations if item.get("entity_id") == resolved_destination_ref]
    if len(theme_candidates) != 1 or len(destinations) != 1:
        return None
    theme, destination = theme_candidates[0], destinations[0]
    source_holder_ref = theme.get("received_by")
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
            **({"source_holder": source_holder_ref} if source_holder_ref else {}),
            **({"companions": companion_refs} if companion_refs else {}),
        },
        "role_binding_evidence": deepcopy(process_bindings),
        "source_language_frame": {
            "utterance": utterance,
            "canonical_utterance": (language_analysis or {}).get("canonical_utterance"),
            "semantic_roles": deepcopy((language_analysis or {}).get("role_bindings", {})),
            "modifiers": deepcopy((language_analysis or {}).get("modifiers", {})),
            "destination_binding_policy": deepcopy(
                (language_analysis or {}).get("canonical_frame", {}).get("destination_binding_policy")
            ),
            "context_projection": deepcopy((language_analysis or {}).get("context_projection")),
            "fact_effect": "language_binds_goal_and_roles_but_does_not_commit_physical_facts",
        },
        "goal_contract": {
            "requires": ["theme_object_grounded", "destination_grounded"],
            "produces": ["object_supported_at_destination", "objects_co_supported_at_destination"] if companion_refs else ["object_supported_at_destination"],
            "verification": ["projection_inside_support_boundary", "support_contact_stable", "gripper_released", "support_occupancy_non_overlapping"] if companion_refs else ["projection_inside_support_boundary", "support_contact_stable", "gripper_released"],
        },
        "dependency_graph": {
            "root": "object_supported_at_destination",
            "nodes": [
                {
                    "stage_id": "acquire_theme",
                    **({"requires": "object_received_by_current_holder"} if source_holder_ref else {}),
                    "produces": "object_in_gripper",
                },
                {"stage_id": "place_at_destination", "requires": "object_in_gripper", "produces": "object_supported_at_destination"},
            ],
        },
        "lifecycle": "active",
        "verified_facts": [],
        "current_stage": None,
        "resume_envelope": None,
        "created_world_revision": session["world_revision"],
    }
    _attach_hierarchical_intent_graph(intent)
    session["long_horizon_intents"][intent_id] = intent
    session["active_intent_id"] = intent_id
    session["intent_activation_stack"] = [intent_id]
    return intent


def _create_object_handover_intent(
    session: dict[str, Any], utterance: str, language_analysis: dict[str, Any]
) -> dict[str, Any] | None:
    resolution = language_analysis.get("process_template_resolution") or {}
    if resolution.get("template_id") != "handover_object" or resolution.get("status") not in {"ready", "subgoals_required"}:
        return None
    bindings = resolution.get("bindings", {})
    theme_ref = (bindings.get("theme") or {}).get("value_ref")
    recipient_ref = (bindings.get("recipient") or {}).get("value_ref")
    theme = next((item for item in session["runtime_objects"] if item.get("entity_id") == theme_ref), None)
    recipient = next((item for item in session["runtime_objects"] if item.get("entity_id") == recipient_ref), None)
    if not theme or not recipient:
        return None
    source_holder_ref = theme.get("received_by")
    intent_id = "intent_" + hashlib.sha1(
        f"{session['session_id']}|object_handover|{theme['entity_id']}|{recipient['entity_id']}|{session['world_revision']}".encode("utf-8")
    ).hexdigest()[:12]
    intent = {
        "intent_id": intent_id,
        "intent_type": "verified_object_handover",
        "source_utterance": utterance,
        "goal_fact": "object_received_by_recipient",
        "role_bindings": {
            "theme": theme["entity_id"],
            "recipient": recipient["entity_id"],
            **({"source_holder": source_holder_ref} if source_holder_ref else {}),
        },
        "goal_contract": {
            "requires": ["theme_object_grounded", "recipient_grounded", "recipient_ready"],
            "produces": ["object_received_by_recipient"],
            "verification": ["effector_release_observed", "recipient_possession_observed"],
        },
        "dependency_graph": {
            "root": "object_received_by_recipient",
            "nodes": [
                {
                    "stage_id": "acquire_theme",
                    **({"requires": "object_received_by_current_holder"} if source_holder_ref else {}),
                    "produces": "object_in_gripper",
                },
                {
                    "stage_id": "handover_to_recipient",
                    "requires": "object_in_gripper",
                    "produces": "object_received_by_recipient",
                },
            ],
        },
        "lifecycle": "active",
        "verified_facts": [],
        "current_stage": None,
        "resume_envelope": None,
        "created_world_revision": session["world_revision"],
        "task_level_authorization": {
            "source": "explicit_human_imperative",
            "scope": "ordinary_object_handover_goal_and_necessary_causal_stages",
            "goal_fact": "object_received_by_recipient",
            "role_bindings": {"theme": theme["entity_id"], "recipient": recipient["entity_id"]},
            "stage_by_stage_reconfirmation_required": False,
            "revocation_conditions": ["role_binding_ambiguity", "goal_change", "known_safety_conflict", "policy_requires_confirmation"],
        },
    }
    _attach_hierarchical_intent_graph(intent)
    session["long_horizon_intents"][intent_id] = intent
    session["active_intent_id"] = intent_id
    session["intent_activation_stack"] = [intent_id]
    return intent


def _create_transport_intent(
    session: dict[str, Any], utterance: str, language_analysis: dict[str, Any]
) -> dict[str, Any] | None:
    resolution = language_analysis.get("process_template_resolution") or {}
    if resolution.get("template_id") != "transport_object" or resolution.get("status") not in {"ready", "subgoals_required"}:
        return None
    bindings = resolution.get("bindings", {})
    theme_ref = (bindings.get("theme") or {}).get("value_ref")
    region_ref = (bindings.get("target_region") or {}).get("value_ref")
    mode = (bindings.get("transport_mode") or {}).get("value_ref")
    destination_ref = (bindings.get("destination") or {}).get("value_ref")
    if not theme_ref or not region_ref or mode not in {"retain_holding", "place_at_region"}:
        return None
    if mode == "place_at_region" and not destination_ref:
        return None
    theme = next((item for item in session["runtime_objects"] if item.get("entity_id") == theme_ref), None)
    if not theme:
        return None
    intent_id = "intent_" + hashlib.sha1(
        f"{session['session_id']}|transport|{theme_ref}|{region_ref}|{mode}|{destination_ref}|{session['world_revision']}".encode("utf-8")
    ).hexdigest()[:12]
    nodes = [
        {"stage_id": "acquire_theme", "produces": "object_in_gripper"},
        {"stage_id": "transport_to_region", "requires": "object_in_gripper", "produces": "object_at_target_region"},
    ]
    if mode == "place_at_region":
        nodes.append({"stage_id": "place_at_region", "requires": "object_at_target_region", "produces": "object_supported_at_destination"})
    intent = {
        "intent_id": intent_id,
        "intent_type": "verified_object_transport",
        "source_utterance": utterance,
        "goal_fact": "object_supported_at_destination" if mode == "place_at_region" else "object_at_target_region",
        "role_bindings": {
            "theme": theme_ref,
            "target_region": region_ref,
            "transport_mode": mode,
            **({"destination": destination_ref} if destination_ref else {}),
        },
        "goal_contract": {
            "requires": ["theme_object_grounded", "target_region_grounded", "route_feasible"],
            "produces": ["object_at_target_region"] + (["object_supported_at_destination"] if destination_ref else []),
            "verification": ["executor_inside_target_region", "object_remains_bound_to_selected_transport_mode"],
        },
        "dependency_graph": {"root": "object_at_target_region", "nodes": nodes},
        "lifecycle": "active",
        "verified_facts": [],
        "current_stage": None,
        "resume_envelope": None,
        "created_world_revision": session["world_revision"],
        "task_level_authorization": {
            "source": "explicit_human_imperative",
            "scope": "ordinary_object_transport_goal_and_necessary_causal_stages",
            "goal_fact": "object_at_target_region",
            "role_bindings": {"theme": theme_ref, "target_region": region_ref, "transport_mode": mode},
            "stage_by_stage_reconfirmation_required": False,
            "revocation_conditions": ["role_binding_ambiguity", "goal_change", "known_safety_conflict", "policy_requires_confirmation"],
        },
    }
    _attach_hierarchical_intent_graph(intent)
    session["long_horizon_intents"][intent_id] = intent
    session["active_intent_id"] = intent_id
    session["intent_activation_stack"] = [intent_id]
    return intent


def _water_delivery_goal_semantics(
    session: dict[str, Any],
    utterance: str,
    language_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose a service goal from effects and roles, independent of word order."""
    normalized = re.sub(r"[，。！？、,.!?\s]+", "", utterance)
    analysis = language_analysis or {}
    discourse_roles = analysis.get("discourse_roles") or {}
    beneficiary_requested = (
        (discourse_roles.get("beneficiary") or {}).get("reference")
        == "human_speaker"
    )
    deictic_recipient_requested = (
        (discourse_roles.get("recipient") or {}).get("reference")
        == "human_speaker"
    )
    recent_goal_capsules = (
        (analysis.get("context_projection") or {}).get("recent_goal_capsules") or []
    )
    recent_water_goal = next(
        (
            capsule for capsule in reversed(recent_goal_capsules)
            if capsule.get("goal_fact") == "human_received_filled_container"
        ),
        None,
    )
    omitted_content = any(
        item.get("slot") == "theme_content"
        and item.get("status") == "omitted_head_requires_contextual_goal_schema"
        for item in analysis.get("ellipsis_candidates", [])
    )
    water_effect_requested = any(token in normalized for token in ("接水", "取水", "倒水", "装水", "一杯水")) or bool(
        re.search(r"(?:接|取|倒|装)(?:一)?杯水", normalized)
    )
    if omitted_content and recent_water_goal:
        water_effect_requested = True
    transfer_relation_requested = (
        any(token in normalized for token in ("给", "交给", "递给", "送给", "拿给"))
        or beneficiary_requested
        or bool(recent_water_goal and omitted_content)
    )
    recipients = [
        item for item in session["runtime_objects"]
        if item.get("active") is not False and item.get("kind") == "human_recipient"
    ]
    explicit_recipient_refs = [item["entity_id"] for item in recipients if str(item.get("label") or "") in normalized]
    deictic_human_reference = any(token in normalized for token in ("给我", "交给我", "递给我", "送给我", "拿给我"))
    speaker_ref = (session.get("interaction_role_bindings") or {}).get("human_speaker")
    if (beneficiary_requested or deictic_recipient_requested or deictic_human_reference) and speaker_ref:
        explicit_recipient_refs = list(dict.fromkeys([*explicit_recipient_refs, speaker_ref]))
    generic_human_reference = any(token in normalized for token in ("人类", "人", "家人", "主人", "用户", "客人", "接收人"))
    recipient_role_requested = bool(
        explicit_recipient_refs
        or deictic_human_reference
        or deictic_recipient_requested
        or beneficiary_requested
        or generic_human_reference
        or (recent_water_goal and omitted_content)
    )
    placement_relation_requested = any(token in normalized for token in ("放到", "放在", "摆到", "摆在", "搁到", "搁在"))
    support_concepts = [
        concept for concept in load_object_concepts()["concepts"]
        if "support_object" in concept.get("functional_affordances", [])
    ]
    support_role_requested = any(
        alias and alias in normalized
        for concept in support_concepts
        for alias in concept.get("aliases", [])
    )
    support_entities = [
        item for item in session["runtime_objects"]
        if item.get("active") is not False and item.get("kind") == "operation_surface"
    ]
    explicit_destination_refs = [
        item["entity_id"] for item in support_entities if str(item.get("label") or "") in normalized
    ]
    support_role_requested = support_role_requested or bool(explicit_destination_refs)
    if not explicit_destination_refs and support_role_requested:
        confirmed_support_refs = [
            item.get("entity_ref") for item in session.get("confirmed_visual_bindings", [])
            if item.get("concept_id") == "concept_support_surface"
            and item.get("world_revision") == session["world_revision"]
            and item.get("entity_ref")
        ]
        if len(set(confirmed_support_refs)) == 1:
            explicit_destination_refs = list(set(confirmed_support_refs))
        elif len(support_entities) == 1:
            explicit_destination_refs = [support_entities[0]["entity_id"]]
    goal_fact = None
    if water_effect_requested and transfer_relation_requested and recipient_role_requested:
        goal_fact = "human_received_filled_container"
    elif water_effect_requested and placement_relation_requested and support_role_requested:
        goal_fact = "filled_container_supported_at_destination"
    return {
        "water_effect_requested": water_effect_requested,
        "transfer_relation_requested": transfer_relation_requested,
        "recipient_role_requested": recipient_role_requested,
        "beneficiary_role_requested": beneficiary_requested,
        "goal_schema_continued_from_recent_capsule": bool(recent_water_goal and omitted_content),
        "explicit_recipient_refs": explicit_recipient_refs,
        "placement_relation_requested": placement_relation_requested,
        "support_role_requested": support_role_requested,
        "explicit_destination_refs": explicit_destination_refs,
        "goal_fact": goal_fact,
    }


def _resolve_current_role_binding(
    session: dict[str, Any],
    utterance: str,
    candidates: list[dict[str, Any]],
    *,
    role: str,
    language_analysis: dict[str, Any] | None = None,
    confirmed_entity_ref: str | None = None,
) -> dict[str, Any]:
    """Compatibility facade over the single concept-to-instance grounder."""
    current_candidates = [item for item in candidates if item.get("active") is not False]
    analysis = language_analysis or {}
    current_by_ref = {item.get("entity_id"): item for item in current_candidates}
    # The unified process resolver may already have reduced a concept role by
    # a current verified relation (for example, the only object possessed by
    # the addressed human). Do not discard that stronger binding and restart
    # from category cardinality. Revalidate it against this world revision and
    # the caller's candidate domain before accepting it.
    process_binding = (
        ((analysis.get("process_template_resolution") or {}).get("bindings") or {}).get(role)
        or {}
    )
    composed_binding = (analysis.get("role_bindings") or {}).get(role) or {}
    resolved_ref = process_binding.get("value_ref") or composed_binding.get("entity_ref")
    binding_revision = process_binding.get("observation_world_revision")
    if binding_revision is None:
        binding_revision = (analysis.get("observation_evidence") or {}).get("world_revision")
    if (
        not confirmed_entity_ref
        and resolved_ref in current_by_ref
        and binding_revision == session.get("world_revision")
    ):
        return {
            "status": "resolved",
            "entity": current_by_ref[resolved_ref],
            "entity_ref": resolved_ref,
            "evidence": {
                "basis": process_binding.get("evidence") or "composed_current_world_role_binding",
                "strength": int(process_binding.get("evidence_strength") or 0),
                "world_revision": binding_revision,
                "observation_evidence_set_id": (analysis.get("observation_evidence") or {}).get("evidence_set_id"),
                "matched_constraints": deepcopy(process_binding.get("matched_semantic_constraints", [])),
                "current_snapshot_revalidated": True,
            },
            "compatible_candidates": deepcopy(current_candidates),
            "grounded_role": {
                "status": "resolved",
                "binding": deepcopy(process_binding),
                "source": "unified_process_binding_revalidated_in_current_snapshot",
            },
        }
    relational_candidates = (
        ((analysis.get("context_projection") or {}).get("relational_role_candidates") or {}).get(role)
        or []
    )
    valid_relational = [
        item
        for item in relational_candidates
        if item.get("entity_ref") in current_by_ref
        and item.get("world_revision") == session.get("world_revision")
    ]
    if not confirmed_entity_ref and len(valid_relational) == 1:
        relational = valid_relational[0]
        entity_ref = relational["entity_ref"]
        return {
            "status": "resolved",
            "entity": current_by_ref[entity_ref],
            "entity_ref": entity_ref,
            "evidence": {
                "basis": f"current_verified_relation:{relational.get('relation')}",
                "strength": 475,
                "world_revision": relational.get("world_revision"),
                "observation_evidence_set_id": (analysis.get("observation_evidence") or {}).get("evidence_set_id"),
                "matched_constraints": [{
                    "predicate": relational.get("relation"),
                    "object": relational.get("relation_object_ref"),
                }],
                "current_snapshot_revalidated": True,
            },
            "compatible_candidates": deepcopy(current_candidates),
            "grounded_role": {
                "status": "resolved",
                "binding": deepcopy(relational),
                "source": "context_projection_current_relation",
            },
        }
    semantic_frame = analysis.get("semantic_constraint_frame") or build_semantic_constraint_frame(utterance, analysis)
    observation_evidence = analysis.get("observation_evidence") or _current_observation_evidence(
        session,
        source="role_binding_current_world_grounding",
        persist=True,
    )
    grounded = ground_semantic_role(
        semantic_frame,
        observation_evidence,
        role,
        candidate_entity_refs={item.get("entity_id") for item in current_candidates},
        confirmed_entity_ref=confirmed_entity_ref,
    )
    binding = grounded.get("binding") or {}
    entity = current_by_ref.get(binding.get("entity_ref"))
    return {
        "status": "resolved" if grounded.get("status") == "resolved" else (
            "ambiguous" if grounded.get("status") == "ambiguous" else "unresolved"
        ),
        "entity": entity,
        "entity_ref": binding.get("entity_ref"),
        "evidence": {
            "basis": binding.get("binding_basis") or "no_unique_concept_grounding",
            "strength": int(binding.get("evidence_strength") or 0),
            "world_revision": grounded.get("world_revision"),
            "observation_evidence_set_id": grounded.get("observation_evidence_set_id"),
            "matched_constraints": deepcopy(binding.get("matched_constraints", [])),
            "current_snapshot_revalidated": grounded.get("current_world_revalidated", False),
        },
        "compatible_candidates": deepcopy(current_candidates),
        "grounded_role": grounded,
    }


def _create_water_delivery_intent(
    session: dict[str, Any],
    utterance: str,
    language_analysis: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Bind service roles from the current world; never encode a demonstrated route."""
    existing = (session.get("long_horizon_intents") or {}).get(session.get("active_intent_id"))
    if (
        existing
        and existing.get("goal_fact") == "human_received_filled_container"
        and existing.get("lifecycle") in {"active", "awaiting_correction", "suspended"}
        and (existing.get("role_bindings") or {}).get("theme")
    ):
        # A repeated utterance is a continuation of the same causal contract.
        # Never replace it with a fresh intent whose verified_facts ledger is
        # empty after a terminal-frame failure.
        return existing
    pending_container_ref = session.get("pending_water_container_ref")
    goal_semantics = _water_delivery_goal_semantics(
        session, utterance, language_analysis
    )
    # During clarification recovery the original goal is already known. The
    # answer may be classified as a generic grasp utterance, but that lexical
    # downgrade must not erase the pending service-goal contract.
    if pending_container_ref and goal_semantics["goal_fact"] is None:
        goal_semantics = {
            **goal_semantics,
            "goal_fact": "human_received_filled_container",
            "water_effect_requested": True,
            "transfer_relation_requested": True,
            "recipient_role_requested": True,
        }
    if goal_semantics["goal_fact"] != "human_received_filled_container":
        return None
    containers = [item for item in session["runtime_objects"] if item.get("active") is not False and item.get("kind") == "graspable_container"]
    # Role evidence is resolved and revalidated against the current snapshot
    # before candidate cardinality is allowed to trigger clarification.
    container_resolution = _resolve_current_role_binding(
        session,
        utterance,
        containers,
        role="theme",
        language_analysis=language_analysis,
        confirmed_entity_ref=pending_container_ref,
    )
    if container_resolution.get("entity"):
        containers = [container_resolution["entity"]]
    sources = [item for item in session["runtime_objects"] if item.get("active") is not False and item.get("kind") == "water_source"]
    recipients = [item for item in session["runtime_objects"] if item.get("active") is not False and item.get("kind") == "human_recipient"]
    if goal_semantics["explicit_recipient_refs"]:
        recipients = [item for item in recipients if item["entity_id"] in goal_semantics["explicit_recipient_refs"]]
    if len(containers) != 1 or len(sources) != 1 or len(recipients) != 1:
        return None
    container, source, recipient = containers[0], sources[0], recipients[0]
    intent_id = "intent_" + hashlib.sha1(
        f"{session['session_id']}|water_delivery|{container['entity_id']}|{source['entity_id']}|{recipient['entity_id']}|{session['world_revision']}".encode("utf-8")
    ).hexdigest()[:12]
    intent = {
        "intent_id": intent_id,
        "intent_type": "verified_water_delivery",
        "source_utterance": utterance,
        "composed_goal_semantics": deepcopy(goal_semantics),
        "goal_fact": "human_received_filled_container",
        "role_bindings": {
            "theme": container["entity_id"],
            "source": source["entity_id"],
            "recipient": recipient["entity_id"],
        },
        "role_binding_evidence": {
            "theme": deepcopy(container_resolution.get("evidence", {})),
        },
        "source_language_frame": {
            "utterance": utterance,
            "semantic_constraint_frame": deepcopy((language_analysis or {}).get("semantic_constraint_frame")),
            "grounded_role_bindings": deepcopy(
                ((language_analysis or {}).get("grounded_intent_frame") or {}).get("resolved_role_bindings", {})
            ),
            "context_projection": deepcopy((language_analysis or {}).get("context_projection")),
            "world_revision": session.get("world_revision"),
            "language_binds_constraints_not_physical_facts": True,
        },
        "goal_contract": {
            "requires": ["container_grounded", "water_source_grounded", "recipient_grounded"],
            "produces": ["human_received_filled_container"],
            "verification": ["container_fill_independently_verified", "handover_release_verified", "recipient_possession_verified"],
        },
        "dependency_graph": {
            "root": "human_received_filled_container",
            "nodes": [
                {"stage_id": "acquire_container", "produces": "container_in_effector"},
                {"stage_id": "fill_container", "requires": "container_in_effector", "produces": "container_filled"},
                {"stage_id": "handover_to_recipient", "requires": "container_filled", "produces": "human_received_filled_container"},
            ],
        },
        "lifecycle": "active",
        "verified_facts": [],
        "current_stage": None,
        "resume_envelope": None,
        "created_world_revision": session["world_revision"],
        "task_level_authorization": {
            "source": "explicit_human_imperative",
            "scope": "ordinary_water_delivery_goal_and_necessary_causal_stages",
            "goal_fact": "human_received_filled_container",
            "role_bindings": {"theme": container["entity_id"], "source": source["entity_id"], "recipient": recipient["entity_id"]},
            "stage_by_stage_reconfirmation_required": False,
            "revocation_conditions": ["role_binding_ambiguity", "goal_change", "known_safety_conflict", "policy_requires_confirmation"],
        },
    }
    _attach_hierarchical_intent_graph(intent)
    session["long_horizon_intents"][intent_id] = intent
    session["active_intent_id"] = intent_id
    session["intent_activation_stack"] = [intent_id]
    if pending_container_ref:
        session.pop("pending_water_container_ref", None)
    return intent


def _create_hospitality_intent(
    session: dict[str, Any],
    utterance: str,
    language_analysis: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Create the composite guest-service intent from the live task graph."""
    if session.get("scene_id") != "hospitality_guest":
        return None
    graph = build_hospitality_task_graph(session["runtime_objects"])
    if not causal_graph_activation_matches(graph, language_analysis):
        return None
    intent_id = "intent_hospitality_" + hashlib.sha1(
        f"{session['session_id']}|{session['world_revision']}|{graph['goal_fact']}".encode("utf-8")
    ).hexdigest()[:12]
    intent = {
        "intent_id": intent_id,
        "intent_type": "hospitality_guest_service",
        "source_utterance": utterance,
        "goal_fact": graph["goal_fact"],
        "role_bindings": deepcopy(graph.get("roles", {})),
        "task_graph": graph,
        "dependency_graph": {"nodes": deepcopy(graph.get("nodes", [])), "edges": deepcopy(graph.get("edges", [])), "join_nodes": deepcopy(graph.get("join_nodes", []))},
        "lifecycle": "active",
        "verified_facts": [],
        "current_stage": None,
        "created_world_revision": session["world_revision"],
        "causal_graph_runtime": initialize_causal_graph_runtime(
            graph, world_revision=session["world_revision"]
        ),
        "task_level_authorization": {
            "source": "explicit_human_imperative",
            "scope": "causal_task_graph_and_necessary_verified_nodes",
            "stage_by_stage_reconfirmation_required": False,
        },
    }
    session.setdefault("long_horizon_intents", {})[intent_id] = intent
    session["active_intent_id"] = intent_id
    session["intent_activation_stack"] = [intent_id]
    return intent


def _create_water_placement_intent(
    session: dict[str, Any],
    utterance: str,
    language_analysis: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Compose filling and placement effects into one state-driven intent."""
    goal_semantics = _water_delivery_goal_semantics(
        session, utterance, language_analysis
    )
    if goal_semantics["goal_fact"] != "filled_container_supported_at_destination":
        return None
    containers = [item for item in session["runtime_objects"] if item.get("active") is not False and item.get("kind") == "graspable_container"]
    sources = [item for item in session["runtime_objects"] if item.get("active") is not False and item.get("kind") == "water_source"]
    destinations = [
        item for item in session["runtime_objects"]
        if item.get("entity_id") in goal_semantics["explicit_destination_refs"]
    ]
    if len(containers) != 1 or len(sources) != 1 or len(destinations) != 1:
        return None
    container, source, destination = containers[0], sources[0], destinations[0]
    intent_id = "intent_" + hashlib.sha1(
        f"{session['session_id']}|water_placement|{container['entity_id']}|{source['entity_id']}|{destination['entity_id']}|{session['world_revision']}".encode("utf-8")
    ).hexdigest()[:12]
    intent = {
        "intent_id": intent_id,
        "intent_type": "verified_water_placement",
        "source_utterance": utterance,
        "composed_goal_semantics": deepcopy(goal_semantics),
        "goal_fact": "filled_container_supported_at_destination",
        "role_bindings": {
            "theme": container["entity_id"],
            "source": source["entity_id"],
            "destination": destination["entity_id"],
        },
        "goal_contract": {
            "requires": ["container_grounded", "water_source_grounded", "destination_grounded"],
            "produces": ["container_filled", "object_supported_at_destination", "filled_container_supported_at_destination"],
            "verification": ["container_fill_independently_verified", "projection_inside_support_boundary", "support_contact_stable", "gripper_released"],
        },
        "dependency_graph": {
            "root": "filled_container_supported_at_destination",
            "nodes": [
                {"stage_id": "acquire_container", "produces": "container_in_effector"},
                {"stage_id": "fill_container", "requires": "container_in_effector", "produces": "container_filled"},
                {"stage_id": "place_filled_container", "requires": "container_filled", "produces": "filled_container_supported_at_destination"},
            ],
        },
        "lifecycle": "active",
        "verified_facts": [],
        "current_stage": None,
        "resume_envelope": None,
        "created_world_revision": session["world_revision"],
        "task_level_authorization": {
            "source": "explicit_human_imperative",
            "scope": "ordinary_water_placement_goal_and_necessary_causal_stages",
            "goal_fact": "filled_container_supported_at_destination",
            "role_bindings": {"theme": container["entity_id"], "source": source["entity_id"], "destination": destination["entity_id"]},
            "stage_by_stage_reconfirmation_required": False,
            "revocation_conditions": ["role_binding_ambiguity", "goal_change", "known_safety_conflict", "policy_requires_confirmation"],
        },
    }
    _attach_hierarchical_intent_graph(intent)
    session["long_horizon_intents"][intent_id] = intent
    session["active_intent_id"] = intent_id
    session["intent_activation_stack"] = [intent_id]
    return intent


def _derive_long_intent_stage(session: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
    if intent.get("intent_type") == "verified_object_transport":
        bindings = intent["role_bindings"]
        theme = next((item for item in session["runtime_objects"] if item.get("entity_id") == bindings["theme"]), None)
        region = next((item for item in _scene_for_session(session)["semantic_regions"] if item.get("region_id") == bindings["target_region"]), None)
        destination = next((item for item in session["runtime_objects"] if item.get("entity_id") == bindings.get("destination")), None)
        if not theme or not region:
            return {"status": "rebind_required", "reason": "object_transport_role_binding_no_longer_present"}
        mode = bindings["transport_mode"]
        if mode == "place_at_region" and destination and theme.get("support_ref") == destination["entity_id"] and not _is_held(session, theme["entity_id"]):
            return {"status": "completed", "verified_fact": "object_supported_at_destination"}
        if mode == "retain_holding" and _is_held(session, theme["entity_id"]) and session["state"].get("active_region") == region["region_id"]:
            return {"status": "completed", "verified_fact": "object_at_target_region"}
        if not _is_held(session, theme["entity_id"]):
            return {
                "status": "stage_ready", "stage_id": "acquire_theme",
                "utterance": f"拿起{_conceptual_reference_for_entity(theme)}",
                "required_fact": "theme_object_grounded", "target_fact": "object_in_gripper",
            }
        if session["state"].get("active_region") != region["region_id"]:
            return {
                "status": "stage_ready", "stage_id": "transport_to_region",
                "utterance": f"带着{_conceptual_reference_for_entity(theme)}走到{region['label']}",
                "required_fact": "object_in_gripper", "target_fact": "object_at_target_region",
            }
        if mode == "place_at_region" and destination:
            return {
                "status": "stage_ready", "stage_id": "place_at_region",
                "utterance": f"把{_conceptual_reference_for_entity(theme)}放到{destination['label']}",
                "required_fact": "object_at_target_region", "target_fact": "object_supported_at_destination",
            }
        return {"status": "completed", "verified_fact": "object_at_target_region"}
    if intent.get("intent_type") == "verified_object_handover":
        bindings = intent["role_bindings"]
        objects = {item["entity_id"]: item for item in session["runtime_objects"]}
        theme = objects.get(bindings["theme"])
        recipient = objects.get(bindings["recipient"])
        if not theme or not recipient:
            return {"status": "rebind_required", "reason": "object_handover_role_binding_no_longer_present"}
        if theme.get("received_by") == recipient["entity_id"] and not _is_held(session, theme["entity_id"]):
            return {"status": "completed", "verified_fact": "object_received_by_recipient"}
        if not _is_held(session, theme["entity_id"]):
            source_holder_ref = theme.get("received_by")
            source_holder = objects.get(source_holder_ref)
            return {
                "status": "stage_ready",
                "stage_id": "acquire_theme",
                "utterance": (
                    f"从{source_holder['label']}手上拿起{_conceptual_reference_for_entity(theme)}"
                    if source_holder else f"拿起{_conceptual_reference_for_entity(theme)}"
                ),
                "required_fact": "object_received_by_current_holder" if source_holder else "theme_object_grounded",
                "target_fact": "object_in_gripper",
            }
        return {
            "status": "stage_ready",
            "stage_id": "handover_to_recipient",
            "utterance": f"把{_conceptual_reference_for_entity(theme)}递给{recipient['label']}",
            "required_fact": "object_in_gripper",
            "target_fact": "object_received_by_recipient",
        }
    if intent.get("intent_type") in {"verified_water_delivery", "verified_water_placement"}:
        bindings = intent["role_bindings"]
        objects = {item["entity_id"]: item for item in session["runtime_objects"]}
        container = objects.get(bindings["theme"])
        source = objects.get(bindings["source"])
        recipient = objects.get(bindings.get("recipient"))
        destination = objects.get(bindings.get("destination"))
        final_role = recipient if intent.get("intent_type") == "verified_water_delivery" else destination
        if not container or not source or not final_role:
            return {"status": "rebind_required", "reason": "water_delivery_role_binding_no_longer_present"}
        if intent.get("intent_type") == "verified_water_delivery" and intent.get("goal_fact") in intent.get("verified_facts", []):
            return {"status": "completed", "verified_fact": intent["goal_fact"]}
        if intent.get("intent_type") == "verified_water_placement" and intent.get("goal_fact") in intent.get("verified_facts", []):
            return {"status": "completed", "verified_fact": intent["goal_fact"]}
        # Once acquisition has been verified, a failed fill attempt must not
        # regress to acquire_container. Keep the causal stage locked and ask
        # for re-observation/retry if the live holding sensor is inconclusive.
        if (
            "container_in_effector" in intent.get("verified_facts", [])
            and "container_filled" not in intent.get("verified_facts", [])
        ):
            return {
                "status": "stage_ready",
                "stage_id": "fill_container",
                "utterance": "fill_container",
                "required_fact": "container_in_effector",
                "target_fact": "container_filled",
                "stage_lock": "acquisition_verified_no_regression",
            }
        if not _is_held(session, container["entity_id"]):
            if "container_in_effector" in intent.get("verified_facts", []):
                return {
                    "status": "awaiting_correction",
                    "reason": "verified_holding_fact_conflicts_with_current_physical_observation",
                    "stage_id": "fill_container",
                    "prompt": "任务记录显示杯子曾经已在执行器中，但当前物理观测无法确认仍由本体持有。我不会擅自重新抓取；请让我重新观察手部，或确认杯子是否仍在手中。",
                    "fact_conflict": {
                        "verified_fact": "container_in_effector",
                        "current_observation": "container_not_confirmed_in_effector",
                        "entity_ref": container["entity_id"],
                    },
                    "next_safe_actions": ["重新观察手部和杯子", "确认杯子是否仍在手中", "确认后再继续接水"],
                }
            return {
                "status": "stage_ready", "stage_id": "acquire_container", "utterance": f"拿起{_conceptual_reference_for_entity(container)}",
                "required_fact": "container_grounded", "target_fact": "container_in_effector",
            }
        # A fill fact is task-scoped evidence. A container may still look full
        # because of a prior task, but that observation cannot satisfy the new
        # "fill water" stage until this task independently verifies it.
        if "container_filled" not in intent.get("verified_facts", []):
            return {
                "status": "stage_ready", "stage_id": "fill_container", "utterance": f"到{source['label']}给{container['label']}接水",
                "required_fact": "container_in_effector", "target_fact": "container_filled",
            }
        if intent.get("intent_type") == "verified_water_delivery":
            return {
                "status": "stage_ready", "stage_id": "handover_to_recipient", "utterance": f"把{container['label']}交给{recipient['label']}",
                "required_fact": "container_filled", "target_fact": "human_received_filled_container",
            }
        return {
            "status": "stage_ready", "stage_id": "place_filled_container", "utterance": f"把{_conceptual_reference_for_entity(container)}放到{destination['label']}上",
            "required_fact": "container_filled", "target_fact": "filled_container_supported_at_destination",
        }
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
    source_holder_ref = intent.get("role_bindings", {}).get("source_holder")
    source_holder = next(
        (item for item in session["runtime_objects"] if item.get("entity_id") == source_holder_ref),
        None,
    )
    return {
        "status": "stage_ready",
        "stage_id": "acquire_theme",
        "utterance": (
            f"从{source_holder['label']}手上拿起{theme_reference}"
            if source_holder and theme.get("received_by") == source_holder_ref
            else f"拿起{theme_reference}"
        ),
        "required_fact": "object_received_by_current_holder" if source_holder and theme.get("received_by") == source_holder_ref else "theme_object_grounded",
        "target_fact": "object_in_gripper",
    }


def _derive_causal_graph_stage(session: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
    graph = intent.get("task_graph") or {}
    runtime = intent.get("causal_graph_runtime")
    if not runtime:
        runtime = initialize_causal_graph_runtime(graph, world_revision=session["world_revision"])
        intent["causal_graph_runtime"] = runtime
    while True:
        evaluation = evaluate_causal_graph(
            graph,
            runtime,
            session.get("runtime_objects", []),
            world_revision=session["world_revision"],
        )
        intent["task_graph_evaluation"] = deepcopy(evaluation)
        if evaluation.get("goal_established"):
            return {"status": "completed", "verified_fact": graph.get("goal_fact")}

        automatic = next(
            (
                node for node in evaluation.get("ready_nodes", [])
                if (node.get("execution_contract") or {}).get("mode") == "epistemic"
            ),
            None,
        )
        if automatic:
            node_id = automatic["node_id"]
            record_graph_facts(
                runtime,
                list(automatic.get("produces", [])),
                source="current_world_snapshot_epistemic_verification",
                node_id=node_id,
                world_revision=session["world_revision"],
                physical_verification=True,
            )
            runtime["node_states"][node_id]["status"] = "completed"
            if node_id not in runtime["completed_node_order"]:
                runtime["completed_node_order"].append(node_id)
            for fact in automatic.get("produces", []):
                if fact not in intent["verified_facts"]:
                    intent["verified_facts"].append(fact)
            continue

        clarification = select_condition_clarification(graph, evaluation)
        if (
            clarification
            and (graph.get("scheduler_policy") or {}).get(
                "resolve_goal_affecting_conditions_before_execution", False
            )
        ):
            runtime["pending_condition"] = deepcopy(clarification)
            session["causal_graph_clarification"] = {
                "intent_id": intent["intent_id"],
                "condition": clarification["condition"],
                "node_id": clarification["node_id"],
                "question": clarification.get("question"),
                "world_revision": session["world_revision"],
            }
            intent["lifecycle"] = "awaiting_correction"
            intent["current_stage"] = None
            return {
                "status": "causal_graph_clarification_required",
                "reason": "goal_affecting_causal_precondition_unresolved",
                "prompt": clarification.get("question"),
                "pending_condition": deepcopy(clarification),
                "task_graph_evaluation": deepcopy(evaluation),
                "long_horizon_intent": _long_intent_view(intent),
            }

        ready = evaluation.get("ready_nodes", [])
        if ready:
            node = ready[0]
            node_id = node["node_id"]
            runtime["active_node_id"] = node_id
            runtime["node_states"][node_id]["status"] = "active"
            runtime["node_states"][node_id]["attempt_count"] = int(
                runtime["node_states"][node_id].get("attempt_count", 0)
            ) + 1
            contract = deepcopy(node.get("execution_contract") or {})
            produces = list(node.get("produces", []))
            return {
                "status": "stage_ready",
                "stage_id": node_id,
                "graph_node_id": node_id,
                "utterance": f"执行任务图节点：{node.get('label', node_id)}",
                "required_fact": list(node.get("requires", [])),
                "target_fact": produces[-1] if produces else None,
                "produces_facts": produces,
                "verification": deepcopy(node.get("verification", [])),
                "execution_contract": contract,
                "scheduler_basis": "current_verified_graph_facts",
            }

        reason = "causal_graph_waiting_for_predecessors"
        if evaluation.get("blocked_nodes"):
            reason = "causal_graph_has_unresolved_noninteractive_preconditions"
        return {
            "status": "awaiting_correction",
            "reason": reason,
            "task_graph_evaluation": deepcopy(evaluation),
            "prompt": "当前因果图没有可安全执行的节点；我已保留任务事实，请补充缺失条件或等待世界状态变化。",
        }


def _prepare_long_intent_stage(session: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
    intent_id = intent["intent_id"]
    if intent.get("causal_graph_runtime") is not None:
        stage = _derive_causal_graph_stage(session, intent)
        if stage.get("status") == "causal_graph_clarification_required":
            stage["session"] = get_session(session["session_id"])
            return stage
        if stage.get("status") == "awaiting_correction":
            intent["lifecycle"] = "awaiting_correction"
            intent["current_stage"] = None
            return {
                **stage,
                "long_horizon_intent": _long_intent_view(intent),
                "session": get_session(session["session_id"]),
            }
    else:
        stage = None
    verified = set(intent.get("verified_facts", []))
    # P018 step-6 pruning is mandatory on every resume/replan path, including
    # experience replay. A completed acquisition fact removes both navigation
    # and grasp from the candidate chain; recovery resumes at fill_container.
    if stage is None and (
        intent.get("intent_type") == "verified_water_delivery"
        and "container_in_effector" in verified
        and "container_filled" not in verified
    ):
        bindings = intent.get("role_bindings") or {}
        objects = {item.get("entity_id"): item for item in session.get("runtime_objects", [])}
        source = objects.get(bindings.get("source"))
        container = objects.get(bindings.get("theme"))
        stage = {
            "status": "stage_ready",
            "stage_id": "fill_container",
            "utterance": f"到{source.get('label', '水源')}给{container.get('label', '容器')}接水" if source and container else "fill_container",
            "required_fact": "container_in_effector",
            "target_fact": "container_filled",
            "pruned_steps": ["navigate_to_container", "grasp_container"],
            "resume_basis": "current_verified_task_facts",
        }
    elif stage is None:
        stage = _derive_long_intent_stage(session, intent)
    _debug_runtime("stage_pruned", session, intent_id=intent_id, stage=stage.get("stage_id"), pruned_steps=stage.get("pruned_steps", []), resume_basis=stage.get("resume_basis"))
    if stage["status"] == "completed":
        intent["lifecycle"] = "completed"
        if intent["goal_fact"] not in intent["verified_facts"]:
            intent["verified_facts"].append(intent["goal_fact"])
        intent["current_stage"] = None
        if session.get("active_intent_id") == intent["intent_id"]:
            session["active_intent_id"] = None
            session["intent_activation_stack"] = []
        completed_view = _long_intent_view(intent)
        completed_view.update({
            "closed_world_revision": session["world_revision"],
            "arbitration_eligible": False,
            "snapshot_state": "released_from_active_arbitration",
        })
        _archive_and_release_task_context(
            session,
            intent,
            lifecycle="completed",
            release_reason="goal_fact_physically_verified",
            archive_key="completed_intent_archive",
        )
        session.get("long_horizon_intents", {}).pop(intent["intent_id"], None)
        compound_next = _advance_compound_command_sequence(
            session, intent["intent_id"]
        )
        return {
            "status": "long_intent_completed",
            "long_horizon_intent": completed_view,
            "compound_next_started": compound_next,
        }
    if stage["status"] != "stage_ready":
        intent["lifecycle"] = "awaiting_rebinding"
        return {
            "status": "long_intent_rebinding_required",
            "reason": stage["reason"],
            "long_horizon_intent": _long_intent_view(intent),
        }
    intent["lifecycle"] = "active"
    intent["current_stage"] = deepcopy(stage)
    graph = intent.get("hierarchical_intent_graph") or {}
    graph_node = (graph.get("nodes") or {}).get(f"{intent_id}:{stage['stage_id']}")
    if graph_node:
        graph_node["lifecycle"] = "active"
        graph["active_focus_node_id"] = graph_node["node_id"]
    stage_authorization = None
    if intent.get("task_level_authorization", {}).get("stage_by_stage_reconfirmation_required") is False:
        stage_authorization = {
            "status": "authorized",
            "authorization_id": f"task_goal_{intent_id}_{stage['stage_id']}",
            "command_hash": _command_hash(stage["utterance"]),
            "authorized_world_revision": session["world_revision"],
            "policy_binding": _policy_binding(session),
            "scope": "necessary_stage_of_explicitly_authorized_long_horizon_goal",
            "long_intent_id": intent_id,
            "long_stage_id": stage["stage_id"],
            # Carry the resolved task roles into the internal stage command.
            # The stage must not rediscover an already confirmed object.
            "role_bindings": deepcopy(intent.get("role_bindings", {})),
            "role_binding_evidence": deepcopy(intent.get("role_binding_evidence", {})),
        }
    started = begin_motion_command(
        session["session_id"],
        stage["utterance"],
        scoped_authorization=stage_authorization,
        internal_stage=True,
        grounded_role_bindings={
            **deepcopy(intent.get("role_bindings", {})),
            "_evidence": deepcopy(intent.get("role_binding_evidence", {})),
        },
    )
    # Candidate generation rolls the short-task session back to avoid committing
    # unverified facts. Continue from the restored live session, not the stale
    # object reference retained by this long-intent helper.
    live_session = SESSIONS[session["session_id"]]
    intent = live_session["long_horizon_intents"][intent_id]
    intent["lifecycle"] = "active"
    intent["current_stage"] = deepcopy(stage)
    graph = intent.get("hierarchical_intent_graph") or {}
    graph_node = (graph.get("nodes") or {}).get(f"{intent_id}:{stage['stage_id']}")
    if graph_node:
        graph_node["lifecycle"] = "active"
        graph["active_focus_node_id"] = graph_node["node_id"]
    stage_execution_plan = None
    if started.get("job_id"):
        job = MOTION_JOBS.get(started["job_id"])
        if job:
            job["long_intent_id"] = intent_id
            job["long_stage_id"] = stage["stage_id"]
            stage_execution_plan = deepcopy((job.get("terminal_result") or {}).get("candidate_execution_plan"))
    if stage_execution_plan:
        started["candidate_execution_plan"] = stage_execution_plan
    immediate = started.get("immediate_result") or {}
    _attach_runtime_diagnostic(immediate, live_session, stage)
    # The internal motion response may carry a plan for the motion primitive
    # that just completed. Re-project it onto the newly selected long-horizon
    # stage so the UI cannot display an obsolete acquire plan while the task
    # is already in fill_container.
    if stage.get("stage_id") == "fill_container":
        immediate["candidate_execution_plan"] = {
            "goal_fact": "container_filled",
            "goal_operator": "fill_container",
            "candidate_process": ["navigate_to_water_source", "align_container_under_outlet", "activate_flow", "verify_container_filled"],
            "required_facts": ["container_in_effector"],
            "satisfied_facts": ["container_in_effector"],
            "missing_precondition": None,
            "candidate_only": False,
            "runtime_fact_committed": False,
        }
    elif stage.get("stage_id") == "acquire_container":
        immediate["candidate_execution_plan"] = {
            "goal_fact": "container_in_effector",
            "goal_operator": "grasp_container",
            "candidate_process": ["navigate_to_container", "align_end_effector", "grasp_container", "verify_container_in_effector"],
            "required_facts": ["container_grounded"],
            "satisfied_facts": [],
            "missing_precondition": None,
            "candidate_only": False,
            "runtime_fact_committed": False,
        }
    pending = live_session.get("pending_confirmation")
    if pending:
        pending["long_intent_id"] = intent_id
        pending["long_stage_id"] = stage["stage_id"]
        pending["role_bindings"] = deepcopy(intent.get("role_bindings", {}))
        pending["role_binding_evidence"] = deepcopy(intent.get("role_binding_evidence", {}))
        immediate["pending_confirmation"] = deepcopy(pending)
    immediate["long_horizon_intent"] = _long_intent_view(intent)
    immediate["long_stage"] = deepcopy(stage)
    goal_summary = (
        "把接好的水交给人" if intent.get("intent_type") == "verified_water_delivery"
        else "把接好的水稳定放到目标承载面" if intent.get("intent_type") == "verified_water_placement"
        else "把指定对象交给接收者" if intent.get("intent_type") == "verified_object_handover"
        else "把指定对象运输到目标区域" if intent.get("intent_type") == "verified_object_transport"
        else "将对象放到目标承载面"
    )
    immediate["runtime_trace"] = {
        "session_id": session["session_id"],
        "intent_id": intent_id,
        "world_revision": session["world_revision"],
        "theme_ref": (intent.get("role_bindings") or {}).get("theme"),
        "role_clarification_active": bool(live_session.get("role_clarification_dialogue")),
    }
    immediate["prompt"] = (
        f"长程目标保持为“{goal_summary}”。当前根据最新世界状态需要先完成阶段：{stage['stage_id']}。"
        + (immediate.get("prompt") or "")
    )
    if started.get("immediate_result") is not None:
        return {**started, "immediate_result": immediate, "long_horizon_intent": _long_intent_view(intent)}
    return {**started, "long_horizon_intent": _long_intent_view(intent), "long_stage": deepcopy(stage)}


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
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    if session.get("scene_id") == "hospitality_guest":
        # Re-derive task prerequisites from the live world; never expose a stale
        # planning snapshot after an object is moved, discarded, or filled.
        graph = build_hospitality_task_graph(session["runtime_objects"])
        session["task_graph"] = graph
        session["task_graph_unresolved_conditions"] = unresolved_hospitality_conditions(graph)
        session["task_graph_orchestration"] = build_hospitality_orchestration_view(graph)
        session["task_graph_state"] = "awaiting_condition_resolution" if session["task_graph_unresolved_conditions"] else "ready_for_orchestration"
    return deepcopy(session)


def get_hospitality_task_graph(session_id: str) -> dict[str, Any]:
    """Return the live hospitality graph and its minimum unresolved conditions."""
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    if session.get("scene_id") != "hospitality_guest":
        return {"error": "hospitality_task_graph_not_available", "scene_id": session.get("scene_id")}
    live = get_session(session_id)
    return {
        "session_id": session_id,
        "scene_id": live["scene_id"],
        "goal_fact": live["task_graph"]["goal_fact"],
        "task_graph": live["task_graph"],
        "unresolved_conditions": live["task_graph_unresolved_conditions"],
        "orchestration": live["task_graph_orchestration"],
        "state": live["task_graph_state"],
    }


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


def _language_object_concepts() -> list[dict[str, Any]]:
    global _LANGUAGE_OBJECT_CONCEPT_CACHE
    if _LANGUAGE_OBJECT_CONCEPT_CACHE is None:
        _LANGUAGE_OBJECT_CONCEPT_CACHE = load_object_concepts()["concepts"]
    return _LANGUAGE_OBJECT_CONCEPT_CACHE


def _session_object_language_concepts(session: dict[str, Any]) -> list[dict[str, Any]]:
    # Concepts contain reusable lexical and causal invariants only. Runtime
    # entity names are reference evidence and must be resolved by grounding,
    # never promoted into the concept lexicon.
    return deepcopy(_language_object_concepts())


def _current_observation_evidence(
    session: dict[str, Any],
    *,
    source: str,
    persist: bool,
) -> dict[str, Any]:
    evidence = build_observation_evidence_set(
        session.get("runtime_objects", []),
        _language_object_concepts(),
        world_revision=int(session.get("world_revision", 0)),
        source=source,
    )
    if persist:
        session["current_observation_evidence"] = deepcopy(evidence)
        ledger = session.setdefault("observation_evidence_ledger", [])
        if not ledger or ledger[-1].get("evidence_set_id") != evidence.get("evidence_set_id"):
            ledger.append(deepcopy(evidence))
        if len(ledger) > 8:
            del ledger[:-8]
    return evidence


def _language_context_entities(session: dict[str, Any]) -> list[dict[str, Any]]:
    concepts = _language_object_concepts()
    concept_index = {item["concept_id"]: item for item in concepts}
    runtime_index = {item["entity_id"]: item for item in session.get("runtime_objects", [])}
    focused: dict[str, dict[str, Any]] = {}

    for ref in _holding_by_effector(session).values():
        if ref and ref in runtime_index:
            entity = runtime_index[ref]
            matching = [item for item in concepts if entity.get("kind") in item.get("compatible_kinds", [])]
            concept = matching[0] if len(matching) == 1 else {}
            focused[ref] = {
                "entity_ref": ref,
                "label": entity.get("label"),
                "concept_id": concept.get("concept_id"),
                "display_name": concept.get("display_name") or entity.get("label"),
                "functional_affordances": deepcopy(concept.get("functional_affordances", [])),
                "compatible_kinds": deepcopy(concept.get("compatible_kinds", [entity.get("kind")])),
                "focus_source": "verified_holding_fact",
            }
    for binding in session.get("confirmed_visual_bindings", []):
        if binding.get("world_revision") != session["world_revision"]:
            continue
        ref = binding.get("entity_ref")
        concept = concept_index.get(binding.get("concept_id"), {})
        if ref:
            # A historical visual confirmation must not downgrade the stronger,
            # currently verified fact that this entity is held by an effector.
            focused.setdefault(ref, {
                "entity_ref": ref,
                "label": binding.get("label"),
                "concept_id": binding.get("concept_id"),
                "display_name": concept.get("display_name") or binding.get("label"),
                "functional_affordances": deepcopy(concept.get("functional_affordances", [])),
                "compatible_kinds": deepcopy(concept.get("compatible_kinds", [])),
                "focus_source": "human_confirmed_visual_binding",
            })
    current_turn = int(session.get("interaction_turn", 0))
    for item in session.get("dialogue_focus_entities", []):
        if int(item.get("expires_after_turn", current_turn)) < current_turn:
            continue
        if item.get("entity_ref") and item.get("world_revision", session["world_revision"]) != session["world_revision"]:
            continue
        key = str(item.get("entity_ref") or item.get("concept_id") or item.get("label"))
        if key:
            focused.setdefault(key, deepcopy(item))
    return list(focused.values())


def _project_resolved_process_roles(
    session: dict[str, Any], analysis: dict[str, Any], resolution: dict[str, Any] | None
) -> None:
    if analysis.get("speech_act") != "task_request" or not resolution:
        return
    if resolution.get("status") not in {"resolved", "subgoals_required"}:
        return
    bindings = resolution.get("bindings") or {}
    if not bindings:
        return
    concepts = load_object_concepts()["concepts"]
    runtime_index = {item.get("entity_id"): item for item in session.get("runtime_objects", [])}
    projected: dict[str, dict[str, Any]] = {}
    for role_name, binding in bindings.items():
        entity = runtime_index.get(binding.get("value_ref"))
        if not entity:
            continue
        semantic_role = ((analysis.get("semantic_constraint_frame") or {}).get("roles") or {}).get(role_name) or {}
        semantic_kinds = set(semantic_role.get("compatible_kinds") or [])
        if semantic_kinds and entity.get("kind") not in semantic_kinds:
            # Executability cannot replace an explicitly understood but
            # incompatible role with another current-world entity.
            continue
        compatible = [concept for concept in concepts if entity.get("kind") in concept.get("compatible_kinds", [])]
        concept = compatible[0] if len(compatible) == 1 else {}
        affordances = set(concept.get("functional_affordances", []))
        affordances.update(entity.get("affordances") or [])
        if entity.get("fixed") is False:
            affordances.add("movable")
        projected[role_name] = {
            "entity_ref": entity.get("entity_id"),
            "concept_id": concept.get("concept_id"),
            "display_name": entity.get("label") or concept.get("display_name"),
            "matched_alias": entity.get("label"),
            "compatible_kinds": [entity.get("kind")],
            "functional_affordances": sorted(affordances),
            "source": "resolved_process_instance_binding",
            "binding_evidence": deepcopy(binding),
        }
    if not projected:
        return
    analysis.setdefault("role_bindings", {}).update(deepcopy(projected))
    analysis.setdefault("canonical_frame", {}).setdefault("roles", {}).update(deepcopy(projected))
    for role in projected.values():
        if not any(item.get("entity_ref") == role.get("entity_ref") for item in analysis.get("entity_mentions", [])):
            analysis.setdefault("entity_mentions", []).append(deepcopy(role))
    historical_relation_policy = (
        analysis.get("canonical_frame", {}).get("destination_binding_policy")
        == "most_recent_verified_support_relation"
    )
    explicit_concept_mentions = [
        item for item in analysis.get("entity_mentions", [])
        if item.get("source") == "object_concept_language_adapter"
    ]
    process_projection_covers_explicit_roles = len(explicit_concept_mentions) <= len(bindings)
    if (
        len(projected) == len(bindings)
        and process_projection_covers_explicit_roles
        and resolution.get("canonical_utterance")
        and not historical_relation_policy
    ):
        analysis["canonical_utterance"] = resolution["canonical_utterance"]
        analysis["decision"] = "route_canonical_semantics"


def _compose_session_language(session: dict[str, Any], utterance: str) -> dict[str, Any]:
    analysis = compose_language_concepts(
        utterance,
        event_concepts=FACTORY_EVENT_CONCEPT_UNITS,
        object_concepts=_session_object_language_concepts(session),
        context_entities=_language_context_entities(session),
        learned_adapters=session.get("language_adapters", []),
    )
    semantic_frame = build_semantic_constraint_frame(utterance, analysis)
    observation_evidence = _current_observation_evidence(
        session,
        source="input_triggered_current_world_grounding",
        persist=True,
    )
    grounded_frame = build_grounded_intent_frame(semantic_frame, observation_evidence)
    analysis["semantic_constraint_frame"] = semantic_frame
    analysis["observation_evidence"] = observation_evidence
    analysis["grounded_intent_frame"] = grounded_frame
    analysis["process_template_resolution"] = resolve_process_request(
        utterance,
        analysis,
        runtime_objects=session.get("runtime_objects", []),
        runtime_state=session.get("state", {}),
        semantic_regions=_scene_for_session(session).get("semantic_regions", []),
        executor_profile=session.get("executor_profile", {}),
        world_revision=session.get("world_revision", 0),
        evidence_bindings=_process_slot_evidence_bindings(session, analysis),
    )
    scoped_event_frames = []
    for event_frame in analysis.get("event_frames", []):
        frame = deepcopy(event_frame)
        frame_semantic = build_semantic_constraint_frame(frame["utterance"], frame)
        frame_grounded = build_grounded_intent_frame(frame_semantic, observation_evidence)
        frame["semantic_constraint_frame"] = frame_semantic
        frame["observation_evidence"] = observation_evidence
        frame["grounded_intent_frame"] = frame_grounded
        frame["process_template_resolution"] = resolve_process_request(
            frame["utterance"],
            frame,
            runtime_objects=session.get("runtime_objects", []),
            runtime_state=session.get("state", {}),
            semantic_regions=_scene_for_session(session).get("semantic_regions", []),
            executor_profile=session.get("executor_profile", {}),
            world_revision=session.get("world_revision", 0),
            evidence_bindings=_process_slot_evidence_bindings(session, frame),
        )
        _project_resolved_process_roles(
            session, frame, frame["process_template_resolution"]
        )
        scoped_event_frames.append(frame)
    analysis["event_frames"] = scoped_event_frames
    gap_dialogue_collecting = (
        (session.get("concept_gap_dialogue") or {}).get("status")
        == "collecting_minimum_causal_contract"
    )
    if not gap_dialogue_collecting:
        _project_resolved_process_roles(session, analysis, analysis["process_template_resolution"])
    current_facts = facts_from_runtime_state(
        session.get("runtime_objects", []),
        session.get("state", {}),
        session.get("world_revision", 0),
    )
    active_intent = (session.get("long_horizon_intents") or {}).get(
        session.get("active_intent_id")
    )
    context_projection = build_context_projection(
        analysis,
        runtime_objects=session.get("runtime_objects", []),
        current_facts=current_facts,
        active_intent=active_intent,
        recent_episodes=session.get("episodic_fact_memory", []),
        recent_intent_capsules=session.get("completed_intent_archive", []),
        interaction_role_bindings=session.get("interaction_role_bindings", {}),
        dialogue_focus_entities=session.get("dialogue_focus_entities", []),
        world_revision=int(session.get("world_revision", 0)),
        current_turn=int(session.get("interaction_turn", 0)),
    )
    analysis["context_projection"] = context_projection
    session["last_context_projection"] = deepcopy(context_projection)
    contextual_goals = {
        item.get("goal_fact")
        for item in context_projection.get("recent_goal_capsules", [])
        if item.get("goal_fact")
    }
    if analysis.get("ellipsis_candidates") and len(contextual_goals) == 1:
        contextual_goal = next(iter(contextual_goals))
        analysis["contextual_goal_resolution"] = {
            "status": "resolved_from_unique_recent_goal_schema",
            "goal_fact": contextual_goal,
            "role_bindings_reused": False,
            "verified_facts_reused": False,
            "current_world_rebinding_required": True,
        }
        analysis["speech_act"] = "task_request"
        analysis.setdefault("canonical_frame", {})["speech_act"] = "task_request"
        analysis["canonical_frame"]["goal_relation"] = contextual_goal
        analysis["unresolved_slots"] = [
            slot for slot in analysis.get("unresolved_slots", [])
            if slot not in {"event_or_query_concept_not_resolved", "event_operator_not_resolved"}
        ]
        analysis["decision"] = "route_contextually_resolved_goal_schema"
        analysis["confidence"] = max(float(analysis.get("confidence") or 0.0), 0.86)
        analysis["confidence_band"] = "high"
    situated_frame = compile_situated_event_frame(
        utterance,
        analysis,
        current_facts=context_projection["current_world_facts"],
        recent_episodes=context_projection["recent_episode_capsules"],
    )
    analysis["situated_event_frame"] = situated_frame
    grounded_history = session.setdefault("grounded_intent_frame_history", [])
    grounded_history.append(deepcopy(grounded_frame))
    if len(grounded_history) > 16:
        del grounded_history[:-16]
    frame_history = session.setdefault("situated_event_frame_history", [])
    frame_history.append(deepcopy(situated_frame))
    if len(frame_history) > 16:
        del frame_history[:-16]
    for candidate in situated_frame.get("reported_state_candidates", []):
        session.setdefault("human_reported_fact_candidates", []).append({
            **deepcopy(candidate),
            "source_frame_id": situated_frame["frame_id"],
            "world_revision": session["world_revision"],
            "runtime_fact_committed": False,
        })
    session["last_language_understanding"] = _language_understanding_view(analysis)
    grounded_focus = [
        result.get("binding")
        for result in (grounded_frame.get("roles") or {}).values()
        if result.get("status") == "resolved" and result.get("binding")
    ]
    explicit_mentions = [item for item in analysis.get("entity_mentions", []) if item.get("source") == "object_concept_language_adapter"]
    if grounded_focus:
        session["dialogue_focus_entities"] = [
            {
                "entity_ref": item.get("entity_ref"),
                "label": item.get("current_name_surface"),
                "concept_id": next(
                    (candidate.get("concept_id") for candidate in item.get("concept_candidates", [])),
                    None,
                ),
                "display_name": item.get("current_name_surface"),
                "compatible_kinds": [item.get("kind")],
                "functional_affordances": sorted({
                    affordance
                    for candidate in item.get("concept_candidates", [])
                    for affordance in candidate.get("functional_affordances", [])
                }),
                "focus_source": "current_grounded_intent_frame",
                "world_revision": observation_evidence.get("world_revision"),
                "created_turn": int(session.get("interaction_turn", 0)),
                "expires_after_turn": int(session.get("interaction_turn", 0)) + 4,
            }
            for item in grounded_focus
        ]
    elif explicit_mentions:
        session["dialogue_focus_entities"] = [
            {
                "concept_id": item.get("concept_id"),
                "display_name": item.get("display_name"),
                "label": item.get("matched_alias"),
                "functional_affordances": deepcopy(item.get("functional_affordances", [])),
                "compatible_kinds": deepcopy(item.get("compatible_kinds", [])),
                "focus_source": "latest_explicit_language_mention",
                "world_revision": session.get("world_revision"),
                "created_turn": int(session.get("interaction_turn", 0)),
                "expires_after_turn": int(session.get("interaction_turn", 0)) + 4,
            }
            for item in explicit_mentions
        ]
    return analysis


def _language_understanding_view(analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "speech_act": analysis.get("speech_act"),
        "query_type": analysis.get("query_type"),
        "operators": analysis.get("canonical_frame", {}).get("operators", []),
        "recognized_entities": [
            item.get("matched_alias") or item.get("label") or item.get("display_name")
            for item in analysis.get("entity_mentions", [])
        ],
        "role_bindings": deepcopy(analysis.get("role_bindings", {})),
        "canonical_utterance": analysis.get("canonical_utterance"),
        "unknown_surface": analysis.get("unknown_surface"),
        "unresolved_slots": deepcopy(analysis.get("unresolved_slots", [])),
        "confidence": analysis.get("confidence"),
        "confidence_band": analysis.get("confidence_band"),
        "decision": analysis.get("decision"),
        "candidate_only": True,
        "runtime_fact_committed": False,
        "situated_event_frame": deepcopy(analysis.get("situated_event_frame")),
        "process_template_resolution": deepcopy(analysis.get("process_template_resolution")),
        "semantic_constraint_frame": deepcopy(analysis.get("semantic_constraint_frame")),
        "grounded_intent_frame": deepcopy(analysis.get("grounded_intent_frame")),
        "context_projection": deepcopy(analysis.get("context_projection")),
        "discourse_roles": deepcopy(analysis.get("discourse_roles", {})),
        "ellipsis_candidates": deepcopy(analysis.get("ellipsis_candidates", [])),
        "contextual_goal_resolution": deepcopy(analysis.get("contextual_goal_resolution")),
        "event_frames": [
            {
                "frame_id": frame.get("frame_id"),
                "clause_index": frame.get("clause_index"),
                "utterance": frame.get("utterance"),
                "operators": deepcopy((frame.get("canonical_frame") or {}).get("operators", [])),
                "goal_relation": (frame.get("canonical_frame") or {}).get("goal_relation"),
                "role_bindings": deepcopy(frame.get("role_bindings", {})),
                "attribute_predicates": deepcopy(
                    (frame.get("semantic_constraint_frame") or {}).get("attribute_predicates", [])
                ),
            }
            for frame in analysis.get("event_frames", [])
        ],
    }


def _event_frame_bound_ref(frame: dict[str, Any], role: str = "theme") -> str | None:
    process_binding = (
        ((frame.get("process_template_resolution") or {}).get("bindings") or {}).get(role)
        or {}
    )
    grounded_binding = (
        ((frame.get("grounded_intent_frame") or {}).get("roles") or {}).get(role)
        or {}
    ).get("binding") or {}
    return process_binding.get("value_ref") or grounded_binding.get("entity_ref")


def _independent_event_frames(
    utterance: str, analysis: dict[str, Any]
) -> list[dict[str, Any]]:
    frames = list(analysis.get("event_frames", []))
    if len(frames) < 2 or "一起" in utterance:
        return []
    bound_themes = [
        ref for ref in (_event_frame_bound_ref(frame) for frame in frames) if ref
    ]
    # A single causal chain such as "pick up X, then place it" remains one
    # intent. Distinct currently grounded themes require independent role
    # scopes and therefore an ordered compound sequence.
    if len(set(bound_themes)) < 2:
        return []
    return frames


def _compound_sequence_view(sequence: dict[str, Any] | None) -> dict[str, Any] | None:
    if not sequence:
        return None
    return {
        "sequence_id": sequence.get("sequence_id"),
        "status": sequence.get("status"),
        "current_subtask_index": sequence.get("current_subtask_index"),
        "subtasks": [
            {
                "subtask_id": item.get("subtask_id"),
                "status": item.get("status"),
                "operators": deepcopy(item.get("operators", [])),
                "goal_relation": item.get("goal_relation"),
                "explicit_theme_ref": item.get("explicit_theme_ref"),
            }
            for item in sequence.get("subtasks", [])
        ],
        "retention_contract": {
            "completed_subtask_language_released": True,
            "physical_facts_rederived_before_each_subtask": True,
            "old_role_bindings_not_reused_as_current_facts": True,
        },
    }


def _dispatch_compound_subtask(session: dict[str, Any]) -> dict[str, Any] | None:
    sequence = session.get("compound_command_sequence") or {}
    index = int(sequence.get("current_subtask_index", 0))
    subtasks = sequence.get("subtasks", [])
    if sequence.get("status") != "active" or index >= len(subtasks):
        return None
    subtask = subtasks[index]
    sequence["dispatching"] = True
    try:
        started = begin_motion_command(
            session["session_id"],
            subtask["utterance"],
            compound_dispatch=True,
        )
    finally:
        session = SESSIONS.get(session["session_id"], session)
        live_sequence = session.get("compound_command_sequence") or sequence
        live_sequence["dispatching"] = False
    sequence = session.get("compound_command_sequence") or sequence
    subtask = sequence["subtasks"][index]
    subtask["status"] = "active"
    subtask["intent_id"] = session.get("active_intent_id")
    started["compound_command_sequence"] = _compound_sequence_view(sequence)
    _debug_runtime(
        "compound_subtask_dispatched",
        session,
        sequence_id=sequence.get("sequence_id"),
        subtask_id=subtask.get("subtask_id"),
        operators=subtask.get("operators", []),
        explicit_theme_ref=subtask.get("explicit_theme_ref"),
    )
    return started


def _start_compound_command_sequence(
    session: dict[str, Any], utterance: str, analysis: dict[str, Any]
) -> dict[str, Any] | None:
    frames = _independent_event_frames(utterance, analysis)
    if not frames:
        return None
    sequence_id = "compound_" + hashlib.sha1(
        f"{session['session_id']}|{session['interaction_turn']}|{utterance}".encode("utf-8")
    ).hexdigest()[:12]
    sequence = {
        "sequence_id": sequence_id,
        "status": "active",
        "source_utterance_hash": hashlib.sha1(utterance.encode("utf-8")).hexdigest(),
        "current_subtask_index": 0,
        "dispatching": False,
        "subtasks": [
            {
                "subtask_id": f"{sequence_id}:{index}",
                "utterance": frame["utterance"],
                "operators": deepcopy((frame.get("canonical_frame") or {}).get("operators", [])),
                "goal_relation": (frame.get("canonical_frame") or {}).get("goal_relation"),
                "explicit_theme_ref": _event_frame_bound_ref(frame),
                "status": "pending",
                "intent_id": None,
            }
            for index, frame in enumerate(frames)
        ],
    }
    session["compound_command_sequence"] = sequence
    _debug_runtime(
        "compound_sequence_created",
        session,
        sequence_id=sequence_id,
        subtask_count=len(sequence["subtasks"]),
    )
    return _dispatch_compound_subtask(session)


def _advance_compound_command_sequence(
    session: dict[str, Any], completed_intent_id: str | None
) -> dict[str, Any] | None:
    sequence = session.get("compound_command_sequence") or {}
    if sequence.get("status") != "active" or sequence.get("dispatching"):
        return None
    index = int(sequence.get("current_subtask_index", 0))
    subtasks = sequence.get("subtasks", [])
    if index >= len(subtasks):
        return None
    current = subtasks[index]
    expected_intent_id = current.get("intent_id")
    if expected_intent_id and completed_intent_id and expected_intent_id != completed_intent_id:
        return None
    current["status"] = "completed"
    current["utterance"] = None
    current["intent_id"] = None
    sequence["current_subtask_index"] = index + 1
    if sequence["current_subtask_index"] >= len(subtasks):
        sequence["status"] = "completed"
        completed_view = _compound_sequence_view(sequence)
        session["compound_command_sequence"] = None
        return {"status": "compound_sequence_completed", "compound_command_sequence": completed_view}
    return _dispatch_compound_subtask(session)


def _append_verified_episode(
    session: dict[str, Any],
    *,
    operator: str,
    participants: dict[str, Any],
    before_facts: list[dict[str, Any]],
    produces: list[dict[str, Any]],
    destroys: list[dict[str, Any]],
    verification_basis: str,
) -> dict[str, Any]:
    memory = session.setdefault("episodic_fact_memory", [])
    sequence = len(memory) + 1
    episode = {
        "episode_id": f"episode_{session['session_id']}_{sequence}",
        "sequence": sequence,
        "temporal_scope": "verified_runtime_past",
        "operator": operator,
        "participants": deepcopy(participants),
        "before_facts": deepcopy(before_facts),
        "produces": deepcopy(produces),
        "destroys": deepcopy(destroys),
        "verification_basis": verification_basis,
        "world_revision": session["world_revision"],
        "raw_trajectory_persisted": False,
    }
    memory.append(episode)
    if len(memory) > 32:
        del memory[:-32]
    return episode


def _query_recent_support_episode(session: dict[str, Any], object_ref: str) -> dict[str, Any] | None:
    for episode in reversed(session.get("episodic_fact_memory", [])):
        if episode.get("participants", {}).get("theme") != object_ref:
            continue
        for fact in [*episode.get("produces", []), *episode.get("before_facts", [])]:
            if fact.get("predicate") == "supported_by" and fact.get("subject") == object_ref and fact.get("object"):
                return {
                    "destination_ref": fact["object"],
                    "episode_id": episode["episode_id"],
                    "operator": episode["operator"],
                    "fact_position": "effect" if fact in episode.get("produces", []) else "pre_action_fact",
                    "evidence_source": (
                        "recent_verified_placement_event"
                        if episode["operator"] == "place_object"
                        else "recent_verified_grasp_source_fact"
                    ),
                }
    return None


def _entity_matches_semantic_role(entity: dict[str, Any] | None, role: dict[str, Any] | None) -> bool:
    if not entity or not role:
        return False
    compatible_kinds = set(role.get("compatible_kinds") or [])
    return not compatible_kinds or entity.get("kind") in compatible_kinds


def _resolve_recent_verified_event_referent(
    session: dict[str, Any], analysis: dict[str, Any]
) -> dict[str, Any] | None:
    """Resolve discourse referents from verified episodes without reviving old world facts."""
    frame = analysis.get("situated_event_frame") or {}
    if frame.get("temporal_scope") not in {"most_recent_verified_past", "verified_past"}:
        return None
    requested_operators = {
        operator for operator in frame.get("operators", [])
        if operator not in {"observe_entity", "navigate_to"}
    }
    roles = frame.get("semantic_roles") or {}
    referenced_role = roles.get("theme") or roles.get("target")
    runtime_index = {
        item.get("entity_id"): item for item in session.get("runtime_objects", [])
        if item.get("entity_id")
    }
    for episode in reversed(session.get("episodic_fact_memory", [])):
        if requested_operators and episode.get("operator") not in requested_operators:
            continue
        participants = episode.get("participants") or {}
        theme_ref = participants.get("theme") or participants.get("target")
        if referenced_role and not _entity_matches_semantic_role(runtime_index.get(theme_ref), referenced_role):
            continue
        source_support_ref = participants.get("source_support")
        if not source_support_ref:
            source_support_ref = next(
                (
                    fact.get("object")
                    for fact in episode.get("before_facts", [])
                    if fact.get("predicate") == "supported_by"
                    and (not theme_ref or fact.get("subject") == theme_ref)
                    and fact.get("object")
                ),
                None,
            )
        destination_support_ref = participants.get("destination")
        if not destination_support_ref:
            destination_support_ref = next(
                (
                    fact.get("object")
                    for fact in episode.get("produces", [])
                    if fact.get("predicate") == "supported_by"
                    and (not theme_ref or fact.get("subject") == theme_ref)
                    and fact.get("object")
                ),
                None,
            )
        related_support_ref = (
            source_support_ref
            if episode.get("operator") == "grasp_object"
            else destination_support_ref
            if episode.get("operator") == "place_object"
            else source_support_ref or destination_support_ref
        )
        return {
            "episode_id": episode.get("episode_id"),
            "episode_operator": episode.get("operator"),
            "theme_entity_ref": theme_ref,
            "source_support_ref": source_support_ref,
            "destination_support_ref": destination_support_ref,
            "related_support_ref": related_support_ref,
            "episode_world_revision": episode.get("world_revision"),
            "resolution_basis": "most_recent_matching_verified_episode",
            "historical_fact_reused_as_current": False,
        }
    return None


def _process_slot_evidence_bindings(
    session: dict[str, Any], analysis: dict[str, Any]
) -> list[dict[str, Any]]:
    """Expose evidence selected by semantic policy without asserting a new physical fact."""
    evidence = deepcopy(session.get("confirmed_visual_bindings", []))
    frame = analysis.get("canonical_frame") or {}
    roles = analysis.get("role_bindings") or {}
    if "place_object" in frame.get("operators", []) and not roles.get("destination"):
        held_refs = [ref for ref in _holding_by_effector(session).values() if ref]
        if len(set(held_refs)) == 1:
            held = next(
                (item for item in session.get("runtime_objects", []) if item.get("entity_id") == held_refs[0]),
                None,
            )
            previous_support_ref = (held or {}).get("last_support_ref")
            if previous_support_ref:
                evidence.append({
                    "entity_ref": previous_support_ref,
                    "world_revision": session["world_revision"],
                    "binding_source": "implicit_previous_verified_support",
                    "evidence_strength": 475,
                    "runtime_fact_committed": False,
                })
            else:
                supports = [
                    item for item in session.get("runtime_objects", [])
                    if item.get("active") is not False and item.get("kind") == "operation_surface"
                ]
                executor_position = session.get("state", {}).get("executor_position") or [0.0, 0.0]
                ranked = sorted(
                    supports,
                    key=lambda item: math.dist(executor_position, item.get("position") or executor_position),
                )
                if ranked and (
                    len(ranked) == 1
                    or math.dist(executor_position, ranked[0]["position"])
                    < math.dist(executor_position, ranked[1]["position"])
                ):
                    evidence.append({
                        "entity_ref": ranked[0]["entity_id"],
                        "world_revision": session["world_revision"],
                        "binding_source": "implicit_nearest_compatible_support_candidate",
                        "evidence_strength": 300,
                        "runtime_fact_committed": False,
                    })
    if frame.get("destination_binding_policy") != "most_recent_verified_support_relation":
        return evidence
    theme = (analysis.get("role_bindings") or {}).get("theme") or {}
    compatible_kinds = set(theme.get("compatible_kinds", []))
    candidates = [
        item for item in session.get("runtime_objects", [])
        if item.get("active") is not False
        and (not compatible_kinds or item.get("kind") in compatible_kinds)
    ]
    current_relational = [
        item for item in candidates
        if session.get("state", {}).get("holding") == item.get("entity_id") or item.get("received_by")
    ]
    theme_candidates = current_relational or candidates
    if len(theme_candidates) != 1:
        return evidence
    support_episode = _query_recent_support_episode(session, theme_candidates[0]["entity_id"])
    destination_ref = (support_episode or {}).get("destination_ref") or theme_candidates[0].get("last_support_ref")
    if not destination_ref:
        return evidence
    evidence.append({
        "entity_ref": destination_ref,
        "world_revision": session["world_revision"],
        "binding_source": "semantically_requested_verified_historical_relation",
        "evidence_strength": 475,
        "episode_id": (support_episode or {}).get("episode_id"),
        "runtime_fact_committed": False,
    })
    return evidence


def _historical_support_reference_candidate(
    session: dict[str, Any], utterance: str, analysis: dict[str, Any]
) -> dict[str, Any] | None:
    """Resolve only the candidate referent; human confirmation supplies semantics, not physical truth."""
    normalized = re.sub(r"[，。！？、,.!?\s]+", "", utterance)
    if not any(marker in normalized for marker in ("刚才", "之前", "先前", "上次")):
        return None
    if not any(item.get("operator") == "place_object" for item in analysis.get("event_candidates", [])):
        return None
    theme = analysis.get("role_bindings", {}).get("theme") or {}
    theme_concept_id = theme.get("concept_id")
    reference_mentions = [
        item for item in analysis.get("entity_mentions", [])
        if item.get("concept_id") != theme_concept_id
        and "graspable" in item.get("functional_affordances", [])
    ]
    if len(reference_mentions) != 1:
        return None
    reference_concept = reference_mentions[0]
    reference_entities = [
        item for item in session["runtime_objects"]
        if item.get("active") is not False and item.get("kind") in reference_concept.get("compatible_kinds", [])
    ]
    if len(reference_entities) != 1:
        return None
    reference = reference_entities[0]
    support_episode = _query_recent_support_episode(session, reference["entity_id"])
    destination_ref = (support_episode or {}).get("destination_ref")
    evidence_source = (support_episode or {}).get("evidence_source") or "support_relation_not_found"
    if not destination_ref and reference.get("support_ref"):
        destination_ref = reference["support_ref"]
        evidence_source = "current_verified_support_relation_without_matching_recent_event"
    if not destination_ref and reference.get("last_support_ref"):
        destination_ref = reference["last_support_ref"]
        evidence_source = "historical_support_candidate_without_matching_recent_event"
    destination = next(
        (item for item in session["runtime_objects"] if item.get("entity_id") == destination_ref),
        None,
    )
    theme_name = theme.get("matched_alias") or theme.get("label") or theme.get("display_name")
    if not theme_name:
        return None
    if destination and destination.get("kind") != "operation_surface":
        destination = None
    canonical = f"把{theme_name}放到{destination['label']}" if destination else None
    candidate_analysis = deepcopy(analysis)
    candidate_analysis["canonical_utterance"] = canonical
    candidate_analysis["unresolved_slots"] = ["historical_support_reference_requires_human_confirmation"]
    candidate_analysis["decision"] = "request_minimum_semantic_clarification"
    candidate_analysis["historical_reference_candidate"] = {
        "theme_label": theme_name,
        "reference_entity_ref": reference["entity_id"],
        "reference_label": reference["label"],
        "relation": "previously_supported_by",
        "destination_entity_ref": destination["entity_id"] if destination else None,
        "destination_label": destination["label"] if destination else None,
        "evidence_source": evidence_source,
        "episode_id": (support_episode or {}).get("episode_id"),
        "episode_operator": (support_episode or {}).get("operator"),
        "semantic_confirmation_required": True,
        "physical_fact_committed": False,
    }
    return candidate_analysis


def _continue_historical_reference_explanation(
    session: dict[str, Any], pending: dict[str, Any], utterance: str
) -> dict[str, Any] | None:
    analysis = pending.get("language_analysis") or {}
    candidate = analysis.get("historical_reference_candidate") or {}
    reference_ref = candidate.get("reference_entity_ref")
    if not reference_ref:
        return None
    reference = next((item for item in session["runtime_objects"] if item.get("entity_id") == reference_ref), None)
    if not reference:
        return None
    normalized = re.sub(r"[，。！？、,.!?\s]+", "", utterance)
    concepts = load_object_concepts()["concepts"]
    reference_aliases = {
        alias for concept in concepts
        if reference.get("kind") in concept.get("compatible_kinds", [])
        for alias in concept.get("aliases", [])
    }
    mentions_reference = any(alias and alias in normalized for alias in reference_aliases) or reference.get("label") in normalized
    describes_support_history = any(token in normalized for token in ("从", "拿起", "拿过", "取过", "抓过", "原来在", "之前在", "放在"))
    if not mentions_reference or not describes_support_history:
        return None
    support_entities = [item for item in session["runtime_objects"] if item.get("kind") == "operation_surface" and item.get("active") is not False]
    explicit = [item for item in support_entities if str(item.get("label") or "") in normalized]
    destination = explicit[0] if len(explicit) == 1 else next(
        (item for item in support_entities if item.get("entity_id") == candidate.get("destination_entity_ref")),
        None,
    )
    support_aliases = {
        alias for concept in concepts
        if "support_object" in concept.get("functional_affordances", [])
        for alias in concept.get("aliases", [])
    }
    if not destination and len(support_entities) == 1 and any(alias and alias in normalized for alias in support_aliases):
        destination = support_entities[0]
    if not destination:
        return None
    canonical = f"把{candidate['theme_label']}放到{destination['label']}"
    session["pending_confirmation"] = None
    session["relational_reference_dialogue"] = None
    session["language_interpretation_history"].append({
        "utterance": pending.get("original_utterance"),
        "clarification": utterance,
        "decision": "historical_relation_resolved_from_human_explanation_and_episodic_evidence",
        "canonical_utterance": canonical,
        "destination_entity_ref": destination["entity_id"],
        "episodic_evidence_ref": candidate.get("episode_id"),
        "world_revision": session["world_revision"],
        "physical_fact_committed": False,
    })
    resumed = begin_motion_command(session["session_id"], canonical)
    resolution = {
        "status": "historical_reference_resolved",
        "theme": candidate["theme_label"],
        "destination_entity_ref": destination["entity_id"],
        "destination_label": destination["label"],
        "evidence_source": candidate.get("evidence_source"),
        "human_explanation": utterance,
        "physical_fact_committed": False,
    }
    resumed["historical_reference_resolution"] = deepcopy(resolution)
    if resumed.get("immediate_result"):
        resumed["immediate_result"]["historical_reference_resolution"] = deepcopy(resolution)
        resumed["immediate_result"]["prompt"] = (
            f"我已根据你的解释把历史关系中的承载面解析为{destination['label']}；仍会按当前物理状态重新观察和验真。"
            + resumed["immediate_result"].get("prompt", "")
        )
    return resumed


def _start_role_clarification(
    session: dict[str, Any],
    *,
    source_utterance: str,
    role: str,
    concept_id: str | None,
    options: list[dict[str, Any]],
    evidence_source: str,
) -> dict[str, Any]:
    dialogue = {
        "status": "awaiting_role_value",
        "source_utterance": source_utterance,
        "role": role,
        "concept_id": concept_id,
        "candidate_options": deepcopy(options),
        "evidence_source": evidence_source,
        "world_revision": session["world_revision"],
        "policy_revision": session["policy_revision"],
    }
    session["role_clarification_dialogue"] = dialogue
    return dialogue


def _start_evidence_gap_clarification(
    session: dict[str, Any],
    *,
    source_utterance: str,
    task_perception: dict[str, Any],
) -> dict[str, Any]:
    grounding = task_perception.get("concept_grounding", {})
    dialogue = {
        "status": "awaiting_evidence_gap_resolution",
        "source_utterance": source_utterance,
        "goal": deepcopy(task_perception.get("causal_preview", {})),
        "target_concept_id": task_perception.get("task_perception_frame", {}).get("target_concept_id"),
        "requested_constraints": deepcopy(task_perception.get("task_perception_frame", {}).get("target_constraints", {})),
        "constraint_mentions": deepcopy(task_perception.get("task_perception_frame", {}).get("target_constraint_mentions", [])),
        "candidate_options": deepcopy(grounding.get("constraint_rejections", [])),
        "evidence_source": "bounded_multi_view_constraint_difference",
        "world_revision": session["world_revision"],
        "policy_revision": session["policy_revision"],
    }
    session["evidence_gap_dialogue"] = dialogue
    return dialogue


def _continue_evidence_gap_clarification(session: dict[str, Any], utterance: str) -> dict[str, Any] | None:
    dialogue = session.get("evidence_gap_dialogue")
    if not dialogue or dialogue.get("status") != "awaiting_evidence_gap_resolution":
        return None
    if dialogue.get("world_revision") != session["world_revision"] or dialogue.get("policy_revision") != session["policy_revision"]:
        session["evidence_gap_dialogue"] = None
        return None
    normalized = re.sub(r"[\s，。！？、,.!?]+", "", utterance.strip().lower())
    options = dialogue.get("candidate_options", [])
    polarity = _context_confirmation_value(utterance)
    if polarity is False:
        session["evidence_gap_dialogue"] = None
        return {
            "status": "evidence_gap_alternative_rejected",
            "immediate_result": {
                "status": "evidence_gap_alternative_rejected",
                "reason": "human_rejected_observed_substitute",
                "prompt": "好的，我不会替换目标。当前仍缺少符合原约束的对象；请补充它的位置、其他可观察特征，或告诉我等待该对象出现。",
                "known_goal": deepcopy(dialogue.get("goal")),
                "requested_constraints": deepcopy(dialogue.get("requested_constraints")),
                "candidate_only": True,
                "runtime_fact_committed": False,
                "session": get_session(session["session_id"]),
            },
            "session": get_session(session["session_id"]),
        }
    selected = options[0] if polarity is True and len(options) == 1 else None
    if selected is None:
        matches = []
        for option in options:
            label = str(option.get("label_hint") or "")
            observed = option.get("observed_attributes", {})
            values = {label}
            color = observed.get("color")
            if color:
                values.update(COLOR_ALIASES.get(color, []))
                values.add(COLOR_NAMES.get(color, color))
            if any(value and value in normalized for value in values):
                matches.append(option)
        if len(matches) == 1:
            selected = matches[0]
    if selected is None:
        labels = []
        for option in options:
            color = option.get("observed_attributes", {}).get("color")
            label = str(option.get("label_hint") or "目标对象")
            display = label if not color or COLOR_NAMES.get(color, color) in label else f"{COLOR_NAMES.get(color, color)}{label}"
            if display not in labels:
                labels.append(display)
        return {
            "status": "evidence_gap_clarification_required",
            "immediate_result": {
                "status": "evidence_gap_clarification_required",
                "reason": "observed_substitute_not_unique_or_not_confirmed",
                "prompt": f"原目标约束仍未满足；当前可验证的同类候选是：{'、'.join(labels)}。请确认其中一个，或补充目标的位置和可观察特征。",
                "known_goal": deepcopy(dialogue.get("goal")),
                "requested_constraints": deepcopy(dialogue.get("requested_constraints")),
                "candidate_options": deepcopy(options),
                "candidate_only": True,
                "runtime_fact_committed": False,
                "session": get_session(session["session_id"]),
            },
            "session": get_session(session["session_id"]),
        }
    resolved_utterance = dialogue["source_utterance"]
    for mention in dialogue.get("constraint_mentions", []):
        observed_value = selected.get("observed_attributes", {}).get(mention.get("attribute"))
        surface = mention.get("surface")
        if not observed_value or not surface:
            continue
        replacement = COLOR_NAMES.get(observed_value, str(observed_value)) if mention.get("attribute") == "color" else str(observed_value)
        resolved_utterance = resolved_utterance.replace(surface, replacement, 1)
    session["evidence_gap_dialogue"] = None
    resumed = begin_motion_command(session["session_id"], resolved_utterance)
    resolution = {
        "status": "evidence_gap_resolved",
        "source_utterance": dialogue["source_utterance"],
        "resolved_utterance": resolved_utterance,
        "requested_constraints": deepcopy(dialogue.get("requested_constraints")),
        "accepted_observed_attributes": deepcopy(selected.get("observed_attributes", {})),
        "entity_ref": selected.get("entity_ref"),
        "human_confirmed_substitution": True,
        "physical_fact_committed": False,
    }
    resumed["evidence_gap_resolution"] = deepcopy(resolution)
    if resumed.get("immediate_result"):
        resumed["immediate_result"]["evidence_gap_resolution"] = deepcopy(resolution)
        resumed["immediate_result"]["prompt"] = (
            "已用你确认的可观察替代补齐目标绑定；原任务目标保持不变，我会按最新世界状态继续求解。"
            + resumed["immediate_result"].get("prompt", "")
        )
    return resumed


def _start_process_gap_dialogue(
    session: dict[str, Any],
    *,
    source_utterance: str,
    language_analysis: dict[str, Any],
    resolution: dict[str, Any],
) -> dict[str, Any]:
    phase = "awaiting_template_confirmation" if resolution.get("status") == "template_confirmation_required" else "awaiting_slot_value"
    dialogue = {
        "status": "collecting_process_template_contract",
        "phase": phase,
        "source_utterance": source_utterance,
        "source_language_analysis": deepcopy(language_analysis),
        "template_id": resolution.get("template_id"),
        "binding_overrides": {},
        "resolution": deepcopy(resolution),
        "world_revision": session["world_revision"],
        "policy_revision": session["policy_revision"],
    }
    session["process_gap_dialogue"] = dialogue
    grounding_gap = (resolution.get("next_gap") or {}).get("kind") == "grounding_evidence_slot"
    return {
        "status": (
            "process_template_confirmation_required" if phase == "awaiting_template_confirmation"
            else "process_grounding_clarification_required" if grounding_gap
            else "process_slot_clarification_required"
        ),
        "reason": (
            "process_template_candidate_requires_human_confirmation" if phase == "awaiting_template_confirmation"
            else "required_process_slot_lacks_current_grounding_evidence" if grounding_gap
            else "required_process_slot_not_uniquely_bound"
        ),
        "prompt": resolution.get("question"),
        "process_template_resolution": deepcopy(resolution),
        "known_goal": resolution.get("goal_fact"),
        "pending_slot": (resolution.get("next_gap") or {}).get("slot_id"),
        "candidate_only": True,
        "runtime_fact_committed": False,
        "direct_execution_allowed": False,
        "session": get_session(session["session_id"]),
    }


def _continue_process_gap_dialogue(session: dict[str, Any], utterance: str) -> dict[str, Any] | None:
    dialogue = session.get("process_gap_dialogue")
    if not dialogue or dialogue.get("status") != "collecting_process_template_contract":
        return None
    if dialogue.get("world_revision") != session["world_revision"] or dialogue.get("policy_revision") != session["policy_revision"]:
        session["process_gap_dialogue"] = None
        return None
    resolution = dialogue.get("resolution") or {}
    if dialogue.get("phase") == "awaiting_template_confirmation":
        polarity = _context_confirmation_value(utterance)
        if polarity is None:
            return {
                "status": "process_template_confirmation_required",
                "immediate_result": {
                    "status": "process_template_confirmation_required",
                    "reason": "template_mapping_confirmation_not_resolved",
                    "prompt": resolution.get("question"),
                    "process_template_resolution": deepcopy(resolution),
                    "candidate_only": True,
                    "runtime_fact_committed": False,
                    "session": get_session(session["session_id"]),
                },
                "session": get_session(session["session_id"]),
            }
        if polarity is False:
            session["process_gap_dialogue"] = None
            return {
                "status": "process_template_candidate_rejected",
                "immediate_result": {
                    "status": "process_template_candidate_rejected",
                    "prompt": "好的，我不会采用这个过程解释。请告诉我你期望对象最终处于什么状态或关系。",
                    "candidate_only": True,
                    "runtime_fact_committed": False,
                    "session": get_session(session["session_id"]),
                },
                "session": get_session(session["session_id"]),
            }
        candidate = resolution.get("template_candidate") or {}
        novel_surface = candidate.get("novel_surface")
        concept_by_template = {
            "grasp_object": ("factory_event_grasp", "grasp_object", "拿起"),
            "place_object": ("factory_event_place", "place_object", "放到"),
            "handover_object": ("factory_event_handover", "handover_object", "递给"),
            "transport_object": ("factory_event_transport", "transport_object", "带到"),
        }
        learned_adapter = None
        if novel_surface and dialogue.get("template_id") in concept_by_template:
            concept_id, operator, canonical_surface = concept_by_template[dialogue["template_id"]]
            adapter_seed = f"{novel_surface}|{concept_id}|{operator}"
            learned_adapter = {
                "adapter_id": "language_adapter_" + hashlib.sha1(adapter_seed.encode("utf-8")).hexdigest()[:12],
                "surface_form": novel_surface,
                "concept_id": concept_id,
                "operator": operator,
                "canonical_surface": canonical_surface,
                "status": "session_confirmed",
                "scope": "current_executor_session",
                "confirmation_count": 1,
                "negative_confirmation_count": 0,
                "source": "process_template_structural_candidate_confirmed_by_human",
                "modifies_concept_kernel": False,
                "runtime_fact_committed": False,
            }
            existing = next((item for item in session["language_adapters"] if item.get("adapter_id") == learned_adapter["adapter_id"]), None)
            if existing:
                existing["confirmation_count"] = int(existing.get("confirmation_count", 0)) + 1
                learned_adapter = deepcopy(existing)
            else:
                session["language_adapters"].append(deepcopy(learned_adapter))
        canonical = resolution.get("canonical_utterance")
        session["process_gap_dialogue"] = None
        if not canonical:
            return None
        resumed = begin_motion_command(session["session_id"], canonical)
        resumed["process_template_mapping_learned"] = deepcopy(learned_adapter)
        if resumed.get("immediate_result"):
            resumed["immediate_result"]["process_template_mapping_learned"] = deepcopy(learned_adapter)
            resumed["immediate_result"]["prompt"] = (
                f"已确认“{novel_surface}”在当前会话中激活{dialogue['template_id']}过程模板；"
                "我只保存语言入口，现在按最新世界状态继续原目标。"
                + resumed["immediate_result"].get("prompt", "")
            )
        return resumed

    gap = resolution.get("next_gap") or {}
    candidates = gap.get("candidates", [])
    normalized = re.sub(r"[\s，。！？、,.!?]+", "", utterance)
    matches = [item for item in candidates if item.get("label") and item["label"] in normalized]
    if len(matches) != 1 and len(candidates) == 1 and _context_confirmation_value(utterance) is True:
        matches = [candidates[0]]
    historical_evidence = None
    if len(matches) != 1 and gap.get("slot_id") == "destination":
        historical_choice = _historical_destination_role_choice(
            session,
            {
                "role": "destination",
                "source_utterance": dialogue.get("source_utterance"),
                "candidate_options": [
                    {"entity_ref": item.get("value_ref"), "label": item.get("label")}
                    for item in candidates
                ],
            },
            utterance,
        )
        if historical_choice:
            choice, historical_evidence = historical_choice
            matches = [item for item in candidates if item.get("value_ref") == choice.get("entity_ref")]
    if len(matches) != 1:
        return {
            "status": "process_slot_clarification_required",
            "immediate_result": {
                "status": "process_slot_clarification_required",
                "reason": "slot_answer_not_unique",
                "prompt": resolution.get("question"),
                "pending_slot": gap.get("slot_id"),
                "candidate_options": deepcopy(candidates),
                "candidate_only": True,
                "runtime_fact_committed": False,
                "session": get_session(session["session_id"]),
            },
            "session": get_session(session["session_id"]),
        }
    dialogue.setdefault("binding_overrides", {})[gap["slot_id"]] = matches[0]["value_ref"]
    source_analysis = deepcopy(dialogue["source_language_analysis"])
    updated = resolve_process_request(
        dialogue["source_utterance"],
        source_analysis,
        runtime_objects=session.get("runtime_objects", []),
        runtime_state=session.get("state", {}),
        semantic_regions=_scene_for_session(session).get("semantic_regions", []),
        executor_profile=session.get("executor_profile", {}),
        world_revision=session["world_revision"],
        binding_overrides=dialogue["binding_overrides"],
        evidence_bindings=_process_slot_evidence_bindings(session, source_analysis),
    )
    if not updated:
        session["process_gap_dialogue"] = None
        return None
    dialogue["resolution"] = deepcopy(updated)
    if updated.get("status") in {"clarification_required", "unsafe_switch"}:
        dialogue["phase"] = "awaiting_slot_value"
        session["process_gap_dialogue"] = dialogue
        return {
            "status": "process_slot_clarification_required",
            "immediate_result": {
                "status": "process_slot_clarification_required",
                "reason": "next_required_process_slot_not_uniquely_bound",
                "prompt": updated.get("question"),
                "process_template_resolution": deepcopy(updated),
                "pending_slot": (updated.get("next_gap") or {}).get("slot_id"),
                "candidate_only": True,
                "runtime_fact_committed": False,
                "session": get_session(session["session_id"]),
            },
            "session": get_session(session["session_id"]),
        }
    if updated.get("status") == "template_confirmation_required":
        dialogue["phase"] = "awaiting_template_confirmation"
        session["process_gap_dialogue"] = dialogue
        return {
            "status": "process_template_confirmation_required",
            "immediate_result": {
                "status": "process_template_confirmation_required",
                "prompt": updated.get("question"),
                "process_template_resolution": deepcopy(updated),
                "candidate_only": True,
                "runtime_fact_committed": False,
                "session": get_session(session["session_id"]),
            },
            "session": get_session(session["session_id"]),
        }
    session["process_gap_dialogue"] = None
    canonical = updated.get("canonical_utterance")
    resumed = begin_motion_command(session["session_id"], canonical) if canonical else None
    if resumed is not None and (historical_evidence or matches[0].get("constraint_mismatch")):
        gap_resolution = {
            "slot_id": gap.get("slot_id"),
            "value_ref": matches[0].get("value_ref"),
            "evidence": deepcopy(historical_evidence) if historical_evidence else {
                "kind": "human_authorized_observed_constraint_substitute",
                "constraint_mismatch": deepcopy(matches[0].get("constraint_mismatch")),
                "observed_attributes": deepcopy(matches[0].get("observed_attributes", {})),
            },
            "human_confirmed_substitution": bool(matches[0].get("constraint_mismatch")),
            "physical_fact_committed": False,
        }
        resumed["process_gap_resolution"] = deepcopy(gap_resolution)
        if resumed.get("immediate_result"):
            resumed["immediate_result"]["process_gap_resolution"] = deepcopy(gap_resolution)
    return resumed


def _replace_last_alias(text: str, aliases: list[str], replacement: str) -> str:
    matches = [(text.rfind(alias), alias) for alias in aliases if alias and text.rfind(alias) >= 0]
    if not matches:
        return text
    position, alias = max(matches, key=lambda item: item[0])
    return text[:position] + replacement + text[position + len(alias):]


def _historical_destination_role_choice(
    session: dict[str, Any], dialogue: dict[str, Any], utterance: str
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    if dialogue.get("role") != "destination":
        return None
    normalized = re.sub(r"[\s，。！？、,.!?]+", "", utterance)
    if not any(marker in normalized for marker in ("原来的位置", "原来位置", "原处", "放回", "刚才", "刚刚", "之前", "先前")):
        return None
    source_analysis = _compose_session_language(session, dialogue.get("source_utterance", ""))
    theme_role = source_analysis.get("role_bindings", {}).get("theme") or source_analysis.get("role_bindings", {}).get("target") or {}
    theme_concept = next(
        (item for item in load_object_concepts()["concepts"] if item.get("concept_id") == theme_role.get("concept_id")),
        None,
    )
    theme_candidates = [
        item for item in session.get("runtime_objects", [])
        if theme_concept and item.get("kind") in theme_concept.get("compatible_kinds", [])
    ]
    held_refs = {ref for ref in _holding_by_effector(session).values() if ref}
    focused = [
        item for item in theme_candidates
        if item.get("entity_id") in held_refs or item.get("received_by") or item.get("last_support_ref")
    ]
    if len(focused) == 1:
        theme_candidates = focused
    if len(theme_candidates) != 1:
        return None
    theme = theme_candidates[0]
    support_ref = theme.get("last_support_ref")
    evidence_ref = None
    for episode in reversed(session.get("episodic_fact_memory", [])):
        participants = episode.get("participants", {})
        if participants.get("theme") != theme.get("entity_id"):
            continue
        episode_support = participants.get("source_support")
        if not episode_support:
            episode_support = next(
                (
                    fact.get("object")
                    for fact in episode.get("before_facts", [])
                    if fact.get("predicate") == "supported_by" and fact.get("subject") == theme.get("entity_id")
                ),
                None,
            )
        if episode_support:
            support_ref = episode_support
            evidence_ref = episode.get("episode_id")
            break
    choice = next(
        (item for item in dialogue.get("candidate_options", []) if item.get("entity_ref") == support_ref),
        None,
    )
    if not choice:
        return None
    return choice, {
        "kind": "most_recent_verified_source_support",
        "theme_entity_ref": theme.get("entity_id"),
        "support_entity_ref": support_ref,
        "episode_ref": evidence_ref,
        "temporal_expression": utterance,
    }


def _resume_role_clarification_choice(
    session: dict[str, Any],
    dialogue: dict[str, Any],
    choice: dict[str, Any],
    *,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    label = choice.get("label") or choice.get("label_hint")
    concept = next(
        (item for item in load_object_concepts()["concepts"] if item.get("concept_id") == dialogue.get("concept_id")),
        None,
    )
    aliases = list((concept or {}).get("aliases", []))
    resolved_utterance = _replace_last_alias(dialogue["source_utterance"], aliases, label)
    if dialogue.get("role") == "theme" and dialogue.get("evidence_source") == "current_world_container_candidates":
        session["pending_water_container_ref"] = choice.get("entity_ref")
        # Preserve the original service-goal expression and append the selected
        # slot value. Replacing the generic classifier in "一杯水" would destroy
        # the already recognized water-delivery relation.
        resolved_utterance = f"{dialogue['source_utterance']}，用{label}"
    session["role_clarification_dialogue"] = None
    if dialogue.get("role") == "theme" and dialogue.get("evidence_source") == "current_world_container_candidates":
        # The human-selected entity is a structured binding. Resume the
        # already understood service goal without reparsing it as a new task.
        intent = _create_water_delivery_intent(session, dialogue["source_utterance"])
        if intent:
            resumed = _prepare_long_intent_stage(session, intent)
            resumed["session"] = get_session(session["session_id"])
        else:
            # Some clients keep an active service intent while presenting the
            # slot answer. Rebind that intent directly; otherwise the answer
            # would fall through to fresh lexical parsing and reopen ambiguity.
            active = (session.get("long_horizon_intents") or {}).get(session.get("active_intent_id"))
            entity_ref = choice.get("entity_ref")
            if (
                active
                and active.get("goal_fact") == "human_received_filled_container"
                and entity_ref
                and any(item.get("entity_id") == entity_ref for item in session.get("runtime_objects", []))
            ):
                active.setdefault("role_bindings", {})["theme"] = entity_ref
                active.setdefault("task_level_authorization", {}).setdefault("role_bindings", {})["theme"] = entity_ref
                session.pop("pending_water_container_ref", None)
                resumed = _prepare_long_intent_stage(session, active)
                resumed["session"] = get_session(session["session_id"])
            else:
                resumed = begin_motion_command(session["session_id"], resolved_utterance)
    else:
        resumed = begin_motion_command(session["session_id"], resolved_utterance)
    resolution = {
        "status": "role_clarification_resolved",
        "role": dialogue["role"],
        "entity_ref": choice.get("entity_ref"),
        "label": label,
        "source_utterance": dialogue["source_utterance"],
        "resolved_utterance": resolved_utterance,
        "evidence": deepcopy(evidence),
        "physical_fact_committed": False,
    }
    resumed["role_clarification_resolution"] = deepcopy(resolution)
    if resumed.get("immediate_result"):
        resumed["immediate_result"]["role_clarification_resolution"] = deepcopy(resolution)
        evidence_prompt = (
            f"我根据对象最近一次已验真的来源承载关系，把你说的原来位置解析为“{label}”；"
            if evidence else f"已将你回答的“{label}”填入上一轮的{dialogue['role']}角色；"
        )
        resumed["immediate_result"]["prompt"] = (
            evidence_prompt + "我会继续按当前物理状态规划。" + resumed["immediate_result"].get("prompt", "")
        )
    return resumed


def _continue_role_clarification(session: dict[str, Any], utterance: str) -> dict[str, Any] | None:
    dialogue = session.get("role_clarification_dialogue")
    if not dialogue or dialogue.get("status") != "awaiting_role_value":
        return None
    if dialogue.get("world_revision") != session["world_revision"] or dialogue.get("policy_revision") != session["policy_revision"]:
        session["role_clarification_dialogue"] = None
        return None
    normalized = re.sub(r"[，。！？、,.!?\s]+", "", utterance)
    options = dialogue.get("candidate_options", [])
    selected = [
        item for item in options
        if item.get("label") == normalized
        or item.get("label_hint") == normalized
        or (item.get("label") and item.get("label") in normalized)
        or (item.get("label_hint") and item.get("label_hint") in normalized)
    ]
    if len(selected) == 1:
        return _resume_role_clarification_choice(session, dialogue, selected[0])
    # Attribute-only answers such as "白色杯子" are valid role choices when
    # exactly one candidate carries that attribute; do not require the full
    # canonical label to be repeated by the user.
    color_tokens = ("白色", "黑色", "透明", "红色", "绿色", "蓝色", "黄色", "灰色", "棕色")
    attribute_selected = [
        item for item in options
        if any(token in normalized and token in str(item.get("label") or item.get("label_hint") or "") for token in color_tokens)
    ]
    if len(attribute_selected) == 1:
        return _resume_role_clarification_choice(session, dialogue, attribute_selected[0])
    historical_choice = _historical_destination_role_choice(session, dialogue, utterance)
    if historical_choice:
        choice, evidence = historical_choice
        return _resume_role_clarification_choice(session, dialogue, choice, evidence=evidence)
    if find_factory_event_concepts_by_text(_normalize_factory_text(utterance)):
        session["role_clarification_dialogue"] = None
        return None
    concept = next(
        (item for item in load_object_concepts()["concepts"] if item.get("concept_id") == dialogue.get("concept_id")),
        None,
    )
    if concept and any(alias and alias in normalized for alias in concept.get("aliases", [])):
        labels = [item.get("label") or item.get("label_hint") for item in options]
        return {
            "status": "role_clarification_required",
            "immediate_result": {
                "status": "role_clarification_required",
                "reason": "role_value_still_not_unique",
                "prompt": f"“{normalized}”仍然对应多个候选：{'、'.join(labels)}。请说其中一个具体名称。",
                "known_task": dialogue["source_utterance"],
                "pending_role": dialogue["role"],
                "candidate_options": deepcopy(options),
                "candidate_only": True,
                "runtime_fact_committed": False,
                "session": get_session(session["session_id"]),
            },
            "session": get_session(session["session_id"]),
        }
    if any(marker in normalized for marker in ("不是", "不对", "是刚才", "原来的", "原处", "之前", "先前")):
        labels = [item.get("label") or item.get("label_hint") for item in options]
        return {
            "status": "role_clarification_required",
            "immediate_result": {
                "status": "role_clarification_required",
                "reason": "correction_retained_in_current_question_under_discussion",
                "prompt": (
                    f"我理解你正在纠正上一轮的{dialogue['role']}，没有把它当成新任务。"
                    f"但当前说明还不能唯一对应这些候选：{'、'.join(labels)}；请再补充一个可观察名称、位置或与刚才事件的关系。"
                ),
                "known_task": dialogue["source_utterance"],
                "pending_role": dialogue["role"],
                "candidate_options": deepcopy(options),
                "candidate_only": True,
                "runtime_fact_committed": False,
                "session": get_session(session["session_id"]),
            },
            "session": get_session(session["session_id"]),
        }
    return None


def _create_language_confirmation(
    session: dict[str, Any],
    analysis: dict[str, Any],
    *,
    resume_utterance: str | None = None,
) -> dict[str, Any]:
    seed = "|".join([
        session["session_id"],
        analysis.get("normalized_utterance", ""),
        str(session["world_revision"]),
        str(session["policy_revision"]),
    ])
    pending = {
        "confirmation_id": "confirm_language_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12],
        "kind": "language_interpretation",
        "status": "pending",
        "utterance": analysis.get("canonical_utterance") or analysis.get("utterance"),
        "original_utterance": analysis.get("utterance"),
        "resume_utterance": resume_utterance,
        "language_analysis": deepcopy(analysis),
        "command_hash": _command_hash(analysis.get("canonical_utterance") or analysis.get("utterance", "")),
        "scope": "single_semantic_interpretation_confirmation",
        "authorized_world_revision": session["world_revision"],
        "policy_binding": _policy_binding(session),
        "revocation_conditions": ["world_revision_changed", "policy_changed", "interpretation_rejected"],
    }
    session["pending_confirmation"] = pending
    return pending


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


def _is_support_inventory_state_query(text: str, analysis: dict[str, Any]) -> bool:
    if analysis.get("speech_act") != "state_query":
        return False
    roles = (analysis.get("situated_event_frame") or {}).get("semantic_roles") or analysis.get("role_bindings") or {}
    support_role = next(
        (
            role for role in roles.values()
            if "support_object" in (role or {}).get("functional_affordances", [])
        ),
        None,
    )
    if not support_role:
        return False
    normalized = re.sub(r"[\s，。！？、,.!?]+", "", text)
    return re.search(r"(?:上|上面)(?:都|还)?(?:有|放着|摆着)(?:什么|哪些|啥)", normalized) is not None


def _support_role_from_analysis(analysis: dict[str, Any]) -> dict[str, Any] | None:
    roles = (analysis.get("situated_event_frame") or {}).get("semantic_roles") or analysis.get("role_bindings") or {}
    return next(
        (
            role for role in roles.values()
            if "support_object" in (role or {}).get("functional_affordances", [])
        ),
        None,
    )


def _answer_support_inventory_state_query(
    session: dict[str, Any], text: str, analysis: dict[str, Any]
) -> dict[str, Any]:
    """Read current supported-by facts; episodic memory may select a support but cannot supply its contents."""
    analysis = deepcopy(analysis)
    support_surface = (_support_role_from_analysis(analysis) or {}).get("matched_alias") or "承载面"
    analysis["query_type"] = "support_inventory"
    analysis["canonical_utterance"] = f"查看{support_surface}上的当前对象"
    analysis["unresolved_slots"] = [
        slot for slot in analysis.get("unresolved_slots", []) if slot != "query_relation_not_resolved"
    ]
    analysis["confidence"] = max(float(analysis.get("confidence") or 0.0), 0.92)
    analysis["confidence_band"] = "high"
    analysis["decision"] = "route_resolved_state_query"
    analysis.setdefault("canonical_frame", {})["query_type"] = "support_inventory"
    analysis["canonical_frame"]["operators"] = ["observe_entity"]
    frame = analysis.get("situated_event_frame") or {}
    support_role = _support_role_from_analysis(analysis) or {}
    observation_evidence = _current_observation_evidence(
        session,
        source="support_inventory_active_observation",
        persist=True,
    )
    runtime_objects = [item for item in session.get("runtime_objects", []) if item.get("active") is not False]
    runtime_index = {item.get("entity_id"): item for item in runtime_objects}
    historical = frame.get("temporal_scope") in {"most_recent_verified_past", "verified_past"}
    event_reference = _resolve_recent_verified_event_referent(session, analysis) if historical else None

    if historical:
        support_ref = (event_reference or {}).get("related_support_ref")
        support = runtime_index.get(support_ref)
        if not event_reference or not support_ref:
            return {
                "status": "historical_support_reference_not_resolved",
                "query_type": "support_inventory",
                "prompt": "我没有找到与这句话匹配的最近一次已验真事件，因此不能确定你说的那个承载面。请补充是哪次动作或哪个位置。",
                "historical_reference": deepcopy(event_reference),
                "runtime_fact_committed": False,
                "task_context_preserved": True,
                "language_understanding": _language_understanding_view(analysis),
                "session": get_session(session["session_id"]),
            }
        if not support or not _entity_matches_semantic_role(support, support_role):
            return {
                "status": "historical_support_not_currently_grounded",
                "query_type": "support_inventory",
                "prompt": "我找到了历史事件中的承载面指代，但它没有在当前任务期世界快照中重新落地，所以不能用旧记录回答现在上面有什么。",
                "historical_reference": deepcopy(event_reference),
                "support_entity_ref": support_ref,
                "runtime_fact_committed": False,
                "task_context_preserved": True,
                "language_understanding": _language_understanding_view(analysis),
                "session": get_session(session["session_id"]),
            }
        supports = [support]
    else:
        compatible_kinds = set(support_role.get("compatible_kinds") or [])
        supports = [
            item for item in runtime_objects
            if not compatible_kinds or item.get("kind") in compatible_kinds
        ]
        explicitly_named = [item for item in supports if str(item.get("label") or "") in text]
        if explicitly_named:
            supports = explicitly_named

    current_facts = facts_from_runtime_state(
        session.get("runtime_objects", []), session.get("state", {}), session.get("world_revision", 0)
    )
    supported_by = [fact for fact in current_facts if fact.get("predicate") == "supported_by"]
    groups = []
    for support in supports:
        entity_refs = [
            fact.get("subject") for fact in supported_by
            if fact.get("object") == support.get("entity_id") and fact.get("subject") in runtime_index
        ]
        entities = [runtime_index[entity_ref] for entity_ref in entity_refs]
        groups.append({
            "support_entity_ref": support.get("entity_id"),
            "support_label": support.get("label") or support.get("entity_id"),
            "entity_refs": entity_refs,
            "labels": [item.get("label") or item.get("entity_id") for item in entities],
        })

    if not groups:
        prompt = "当前任务期世界快照中没有与所述承载面概念匹配的实体，因此我不能回答其上方物品清单。"
    else:
        summaries = [
            f"{group['support_label']}上有{'、'.join(group['labels'])}"
            if group["labels"] else f"{group['support_label']}上当前没有已验真的承载物"
            for group in groups
        ]
        prefix = "我把历史事件中的来源位置解析为当前的" if historical else "按当前任务期世界快照，"
        prompt = prefix + "；".join(summaries) + "。"
    return {
        "status": "support_inventory_state_answered",
        "query_type": "support_inventory",
        "prompt": prompt,
        "inventory_groups": groups,
        "historical_reference": deepcopy(event_reference),
        "state_evidence": {
            "source": "current_task_period_world_snapshot",
            "predicate": "supported_by",
            "world_revision": session.get("world_revision"),
            "observation_evidence_set_id": observation_evidence.get("evidence_set_id"),
            "epistemic_evidence_refreshed_without_task_control_side_effect": True,
            "historical_event_selects_referent_only": historical,
            "historical_facts_used_as_current_state": False,
        },
        "runtime_fact_committed": False,
        "task_context_preserved": True,
        "preserved_pending_confirmation_id": (session.get("pending_confirmation") or {}).get("confirmation_id"),
        "preserved_active_intent_id": session.get("active_intent_id"),
        "language_understanding": _language_understanding_view(analysis),
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
    for evidence in session.get("observation_evidence_ledger", []):
        if evidence.get("current_use_status", "current") == "current":
            evidence["current_use_status"] = "stale"
            evidence["invalidation_reason"] = reason
    session["current_observation_evidence"] = None


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
    water_delivery_teaching = _water_delivery_goal_semantics(session, goal_utterance)["goal_fact"] == "human_received_filled_container"
    contract_target = (source_contract or {}).get("semantic_roles", {}).get("target", {})
    perception_utterance = (
        "拿" + str(contract_target.get("surface_form") or "目标对象")
        if source_contract
        else "拿杯子" if water_delivery_teaching else goal_utterance
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
    service_role_bindings = None
    if water_delivery_teaching:
        sources = [item for item in session["runtime_objects"] if item.get("kind") == "water_source" and item.get("active") is not False]
        recipients = [item for item in session["runtime_objects"] if item.get("kind") == "human_recipient" and item.get("active") is not False]
        if len(sources) != 1 or len(recipients) != 1:
            return {
                "status": "teaching_service_role_grounding_required",
                "reason": "water_source_or_recipient_not_uniquely_grounded",
                "prompt": "请先保证当前空间只有一个可用水源和一个明确接收人。",
                "session": get_session(session_id),
            }
        service_role_bindings = {"theme": target["entity_ref"], "source": sources[0]["entity_id"], "recipient": recipients[0]["entity_id"]}
    session["teaching_session"] = {
        "teaching_id": teaching_id,
        "status": "human_control_active",
        "goal_utterance": goal_utterance,
        "goal_fact": "human_received_filled_container" if water_delivery_teaching else ((source_contract or {}).get("effect_contract", {}).get("canonical_goal_fact", {}).get("fact") or "target_object_in_gripper"),
        "teaching_task_type": "verified_water_delivery" if water_delivery_teaching else "object_acquisition",
        "service_role_bindings": service_role_bindings,
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
    if control in {"fill", "handover"}:
        roles = teaching.get("service_role_bindings") or {}
        if control == "fill":
            result = _apply_verified_fill(session, roles.get("theme"), roles.get("source"), "human_teleoperation")
            action_class = "fill_container"
            requires = ["container_in_effector", "executor_at_water_source", "outlet_available"]
            produces = ["container_filled"]
        else:
            result = _apply_verified_handover(session, roles.get("theme"), roles.get("recipient"), "human_teleoperation")
            action_class = "handover_filled_container"
            requires = ["container_filled", "executor_at_recipient", "recipient_ready"]
            produces = ["human_received_filled_container"]
        verified = result.get("status") == "fact_established"
        teaching["demonstrated_actions"].append({
            "action_class": action_class,
            "verified": verified,
            "requires": requires,
            "produces": produces,
            "destroys": ["container_empty"] if control == "fill" else ["container_in_effector"],
            "verification": deepcopy(result.get("verification_evidence", {})),
            "failure_reason": result.get("reason"),
        })
        _append_teaching_event(
            teaching,
            "teaching_action_verified" if verified else "teaching_action_failed",
            ("接水" if control == "fill" else "交付") + ("动作已执行并通过物理验真" if verified else "动作未通过当前物理前提"),
            stage="teaching",
            status="physical_fact_verified" if verified else "candidate_failure_evidence",
            world_revision=session["world_revision"],
            evidence={"action_class": action_class, "terminal_fact": result.get("terminal_fact"), "reason": result.get("reason")},
        )
        result["teaching_session"] = deepcopy(teaching)
        result["session"] = get_session(session_id)
        return {"status": result["status"], "immediate_result": result, "session": get_session(session_id)}
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
    goal_fact = teaching.get("goal_fact")
    target = next((item for item in session["runtime_objects"] if item.get("entity_id") == teaching.get("target_entity_ref")), None)
    goal_verified = (
        _is_held(session, teaching.get("target_entity_ref"))
        if goal_fact == "target_object_in_gripper"
        else bool(
            goal_fact == "human_received_filled_container"
            and target
            and target.get("liquid_state") == "filled"
            and target.get("received_by") == (teaching.get("service_role_bindings") or {}).get("recipient")
        )
    )
    if not goal_verified:
        return {
            "status": "teaching_goal_not_verified",
            "reason": "teaching_terminal_fact_not_established",
            "prompt": f"当前还没有验真教学终止事实 {goal_fact}，不能把未完成操作保存成经验。",
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
        source_concept_contract=teaching.get("source_concept_contract") or (
            {"effect_contract": {"canonical_goal_fact": {"fact": teaching["goal_fact"]}}}
            if teaching.get("teaching_task_type") == "verified_water_delivery" else None
        ),
    )
    if teaching.get("service_role_bindings"):
        experience["role_binding_contract"] = {
            "demonstration_bindings": deepcopy(teaching["service_role_bindings"]),
            "runtime_rebinding_required": True,
            "binding_slots": ["graspable_container", "water_source", "human_recipient"],
            "absolute_entity_ids_are_not_portable_experience": True,
        }
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
    previous_recipient_ref = target.pop("received_by", None)
    if previous_support_ref:
        target["last_support_ref"] = previous_support_ref
    if previous_recipient_ref:
        previous_recipient = next(
            (item for item in session["runtime_objects"] if item.get("entity_id") == previous_recipient_ref),
            None,
        )
        if previous_recipient:
            previous_recipient["received_object_refs"] = [
                ref for ref in previous_recipient.get("received_object_refs", []) if ref != target_ref
            ]
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
    _append_verified_episode(
        session,
        operator="grasp_object",
        participants={"theme": target_ref, "effector": effector, "source_support": previous_support_ref},
        before_facts=(
            ([{"predicate": "supported_by", "subject": target_ref, "object": previous_support_ref}] if previous_support_ref else [])
            + ([{"predicate": "received_by", "subject": target_ref, "object": previous_recipient_ref}] if previous_recipient_ref else [])
        ),
        produces=[{"predicate": "held_by", "subject": target_ref, "object": effector}],
        destroys=(
            ([{"predicate": "supported_by", "subject": target_ref, "object": previous_support_ref}] if previous_support_ref else [])
            + ([{"predicate": "received_by", "subject": target_ref, "object": previous_recipient_ref}] if previous_recipient_ref else [])
        ),
        verification_basis="gripper_contact_plus_visual_target_follows_effector",
    )
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


def _placement_space_evidence(
    destination: dict[str, Any], held_object: dict[str, Any], occupied: list[dict[str, Any]]
) -> dict[str, Any]:
    """Measure the usable support footprint after subtracting occupied projections."""
    margin_x = (float(destination["size"][0]) - float(held_object["size"][0])) / 2
    margin_y = (float(destination["size"][1]) - float(held_object["size"][1])) / 2
    if margin_x <= 0 or margin_y <= 0:
        return {
            "available_footprint_m2": 0.0,
            "required_footprint_m2": round(float(held_object["size"][0]) * float(held_object["size"][1]), 6),
            "valid_center_region_m2": 0.0,
            "occupied_projection_refs": [item["entity_id"] for item in occupied],
        }
    center_x, center_y = map(float, destination["position"])
    x_min, x_max = center_x - margin_x, center_x + margin_x
    y_min, y_max = center_y - margin_y, center_y + margin_y
    expanded = []
    for item in occupied:
        half_x = (float(held_object["size"][0]) + float(item["size"][0])) / 2 + 0.03
        half_y = (float(held_object["size"][1]) + float(item["size"][1])) / 2 + 0.03
        left, right = max(x_min, float(item["position"][0]) - half_x), min(x_max, float(item["position"][0]) + half_x)
        bottom, top = max(y_min, float(item["position"][1]) - half_y), min(y_max, float(item["position"][1]) + half_y)
        if left < right and bottom < top:
            expanded.append((left, right, bottom, top))
    x_edges = sorted({x_min, x_max, *[edge for rect in expanded for edge in rect[:2]]})
    occupied_area = 0.0
    for left, right in zip(x_edges, x_edges[1:]):
        if right <= left:
            continue
        x = (left + right) / 2
        y_intervals = sorted((bottom, top) for l, r, bottom, top in expanded if l <= x <= r)
        covered_y = 0.0
        current_bottom = current_top = None
        for bottom, top in y_intervals:
            if current_bottom is None:
                current_bottom, current_top = bottom, top
            elif bottom > current_top:
                covered_y += current_top - current_bottom
                current_bottom, current_top = bottom, top
            else:
                current_top = max(current_top, top)
        if current_bottom is not None:
            covered_y += current_top - current_bottom
        occupied_area += (right - left) * covered_y
    valid_area = (x_max - x_min) * (y_max - y_min)
    return {
        "available_footprint_m2": round(max(0.0, valid_area - occupied_area), 6),
        "required_footprint_m2": round(float(held_object["size"][0]) * float(held_object["size"][1]), 6),
        "valid_center_region_m2": round(valid_area, 6),
        "occupied_projection_refs": [item["entity_id"] for item in occupied],
        "occupied_projection_m2": round(occupied_area, 6),
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
    # Add a geometry-derived interior lattice. The first candidates preserve
    # the existing preference order; the lattice prevents a finite hand-picked
    # set from mistaking a usable footprint for a full surface.
    for index in range(1, 6):
        ratio = index / 6
        placement_candidates.extend([
            [center_x - margin_x + 2 * margin_x * ratio, center_y - margin_y + 2 * margin_y * other / 6]
            for other in range(1, 6)
        ])
    placement_candidates = list({
        (round(candidate[0], 6), round(candidate[1], 6)): candidate
        for candidate in placement_candidates
    }.values())
    manipulation_reach = (
        float(session["executor_profile"]["body_envelope"]["radius_m"])
        + float(session["executor_profile"]["arm_reach_m"])
    )
    placement_candidates = [
        candidate for candidate in placement_candidates
        if math.dist(executor_position, candidate) <= manipulation_reach
    ]
    placement_candidates.sort(
        key=lambda candidate: (
            -min((math.dist(candidate, item["position"]) for item in occupied), default=0.0),
            math.dist(executor_position, candidate),
        )
    )
    placement_space = _placement_space_evidence(destination, held_object, occupied)
    if not placement_candidates:
        return {
            "status": "placement_blocked",
            "reason": "no_stable_support_pose_within_current_effector_workspace",
            "prompt": "当前虽能接近承载面，但没有同时满足稳定支撑和执行器可达的放置位姿。",
            "manipulation_reach_m": round(manipulation_reach, 3),
            "placement_space": placement_space,
            "frames": [],
        }
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
        occupied_labels = [item.get("label") or item.get("entity_id") for item in occupied]
        return {
            "status": "placement_blocked",
            "reason": "destination_has_no_non_overlapping_placement_pose",
            "prompt": (
                f"{destination.get('label', '目标承载面')}没有可供{held_object.get('label', '当前物体')}稳定放置且不与已有物体重叠的位置。"
                + (f"当前占用物是：{'、'.join(occupied_labels)}。" if occupied_labels else "")
                + "可以先移开占用物、改用其他承载面，或调整目标约束后继续。"
            ),
            "occupied_object_refs": [item["entity_id"] for item in occupied],
            "occupied_object_labels": occupied_labels,
            "placement_space": placement_space,
            "recovery_options": ["先移开当前占用物", "改用其他兼容承载面", "调整放置目标约束"],
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
    session["event_history"].append({
        "event_type": "verified_placement",
        "object_ref": object_ref,
        "destination_ref": destination_ref,
        "terminal_fact": "object_supported_at_destination",
        "world_revision": session["world_revision"],
    })
    _append_verified_episode(
        session,
        operator="place_object",
        participants={"theme": object_ref, "destination": destination_ref, "effector": effector},
        before_facts=[{"predicate": "held_by", "subject": object_ref, "object": effector}],
        produces=[{"predicate": "supported_by", "subject": object_ref, "object": destination_ref}],
        destroys=[{"predicate": "held_by", "subject": object_ref, "object": effector}],
        verification_basis="support_projection_contact_occupancy_plus_effector_release",
    )
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
            "support_occupancy": {"occupied_object_refs": [item["entity_id"] for item in occupied], "non_overlapping": non_overlapping, **placement_space},
        },
        "effect_contract_committed": {
            "produces": ["object_at_destination", "object_supported_at_destination", "gripper_empty"],
            "destroys": ["object_in_gripper"],
        },
        "control_source": source,
        "runtime_objects": deepcopy(session["runtime_objects"]),
        "frames": [],
    }


def _apply_verified_fill(session: dict[str, Any], container_ref: str, source_ref: str, control_source: str) -> dict[str, Any]:
    objects = {item["entity_id"]: item for item in session["runtime_objects"]}
    container, water_source = objects.get(container_ref), objects.get(source_ref)
    if not container or not water_source or water_source.get("kind") != "water_source":
        return {"status": "fill_blocked", "reason": "container_or_water_source_not_available", "frames": []}
    effector = _held_effector(session, container_ref)
    if not effector:
        return {"status": "fill_blocked", "reason": "container_is_not_currently_held", "frames": []}
    distance = _distance_to_object_footprint(session["state"]["executor_position"], water_source)
    if distance > float(session["executor_profile"]["arm_reach_m"]):
        return {"status": "fill_blocked", "reason": "water_source_outside_current_interaction_workspace", "frames": []}
    outlet_available = water_source.get("outlet_available", True)
    alignment_verified = outlet_available and container.get("kind") == "graspable_container"
    flow_verified = alignment_verified
    level_verified = flow_verified
    if not (alignment_verified and level_verified):
        return {"status": "fill_verification_failed", "reason": "container_fill_channels_not_established", "frames": []}
    container["liquid_state"] = "filled"
    container["fill_level"] = 0.8
    container["filled_from"] = source_ref
    return {
        "status": "fact_established",
        "reason": "verified_container_fill_completed",
        "prompt": f"已在{water_source['label']}处为{container['label']}接水，并由出水流量与杯内液位两个通道验真杯中已有水。",
        "terminal_fact": "container_filled",
        "terminal_fact_binding": {"container_ref": container_ref, "source_ref": source_ref},
        "verification_evidence": {
            "first_channel": {"source": "simulated_source_flow_and_outlet_alignment", "established": flow_verified},
            "second_channel": {"source": "simulated_visual_fill_level_change", "fill_level": 0.8, "established": level_verified},
            "final_fact": "container_filled", "final_fact_established": True,
            "verification_boundary": "P016_multi_channel_fact_verification",
        },
        "effect_contract_committed": {"produces": ["container_filled"], "destroys": ["container_empty"]},
        "control_source": control_source,
        "runtime_objects": deepcopy(session["runtime_objects"]),
        "frames": [],
    }


def _apply_verified_handover(
    session: dict[str, Any],
    object_ref: str,
    recipient_ref: str,
    control_source: str,
    *,
    require_filled_container: bool = True,
) -> dict[str, Any]:
    objects = {item["entity_id"]: item for item in session["runtime_objects"]}
    theme, recipient = objects.get(object_ref), objects.get(recipient_ref)
    if not theme or not recipient or recipient.get("kind") != "human_recipient":
        return {"status": "handover_blocked", "reason": "object_or_recipient_not_available", "frames": []}
    effector = _held_effector(session, object_ref)
    if not effector:
        return {"status": "handover_blocked", "reason": "object_is_not_currently_held", "frames": []}
    if require_filled_container and theme.get("liquid_state") != "filled":
        return {"status": "handover_blocked", "reason": "container_fill_fact_not_established", "frames": []}
    distance = _distance_to_object_footprint(session["state"]["executor_position"], recipient)
    if distance > float(session["executor_profile"]["arm_reach_m"]):
        return {"status": "handover_blocked", "reason": "recipient_outside_safe_handover_workspace", "frames": []}
    if recipient.get("handover_ready") is not True:
        return {"status": "handover_blocked", "reason": "recipient_readiness_not_established", "frames": []}
    received = recipient.setdefault("received_object_refs", [])
    if object_ref not in received:
        received.append(object_ref)
    _holding_by_effector(session)[effector] = None
    _sync_primary_holding(session)
    theme["attached_to_executor"] = False
    theme.pop("held_by_effector", None)
    theme["received_by"] = recipient_ref
    theme["position"] = [float(recipient["position"][0]) + 0.28, float(recipient["position"][1])]
    theme["elevation_m"] = 0.92
    _append_verified_episode(
        session,
        operator="handover_object",
        participants={"theme": object_ref, "recipient": recipient_ref, "effector": effector},
        before_facts=[{"predicate": "held_by", "subject": object_ref, "object": effector}],
        produces=[{"predicate": "received_by", "subject": object_ref, "object": recipient_ref}],
        destroys=[{"predicate": "held_by", "subject": object_ref, "object": effector}],
        verification_basis="effector_release_plus_recipient_possession_tracking",
    )
    terminal_fact = "human_received_filled_container" if require_filled_container else "object_received_by_recipient"
    return {
        "status": "fact_established",
        "reason": "verified_human_handover_completed",
        "prompt": (
            f"已把装水的{theme['label']}交给{recipient['label']}，并验真末端释放与接收方持有状态一致。"
            if require_filled_container
            else f"已把{theme['label']}递给{recipient['label']}，并验真末端释放与接收方持有状态一致。"
        ),
        "terminal_fact": terminal_fact,
        "terminal_fact_binding": {"object_ref": object_ref, "recipient_ref": recipient_ref},
        "verification_evidence": {
            "first_channel": {"source": "simulated_effector_release_and_transfer_contact", "effector": effector, "established": not _is_held(session, object_ref)},
            "second_channel": {"source": "simulated_recipient_possession_tracking", "established": object_ref in received},
            "final_fact": terminal_fact, "final_fact_established": True,
            "verification_boundary": "P016_multi_channel_fact_verification",
        },
        "effect_contract_committed": {"produces": [terminal_fact, "effector_empty"], "destroys": ["object_in_gripper"]},
        "control_source": control_source,
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
    if operator in {"grasp_object", "navigate_near"} and (support_binding or entity.get("support_ref")):
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
    projection_basis = entity["position"] if operator in {"grasp_object", "navigate_near"} else start
    projected_x = min(max(projection_basis[0], center_x - half_x), center_x + half_x)
    projected_y = min(max(projection_basis[1], center_y - half_y), center_y + half_y)
    # For a grasp over a support surface, the base pose must clear the
    # support's expanded AABB before the route planner can go around its
    # perimeter. The extra margin prevents a direct diagonal from entering
    # the furniture envelope at the first corner while keeping the end
    # effector within reach of the target.
    approach_clearance = clearance + (0.22 if operator == "grasp_object" else 0.0)
    side_candidates = [
        {"side": "left", "position": [center_x - half_x - approach_clearance, projected_y]},
        {"side": "right", "position": [center_x + half_x + approach_clearance, projected_y]},
        {"side": "bottom", "position": [projected_x, center_y - half_y - approach_clearance]},
        {"side": "top", "position": [projected_x, center_y + half_y + approach_clearance]},
    ]
    if operator == "avoid":
        # Without a downstream destination, "cleared" means leaving the obstacle's
        # longitudinal projection while retaining a collision-free body envelope.
        if abs(start[0] - center_x) >= abs(start[1] - center_y):
            side_candidates = [item for item in side_candidates if item["side"] in {"bottom", "top"}]
        else:
            side_candidates = [item for item in side_candidates if item["side"] in {"left", "right"}]

    interaction_reach_m = (
        float(session["executor_profile"]["body_envelope"]["radius_m"])
        + float(session["executor_profile"].get("arm_reach_m", 0.0))
    )
    required_terminal_distance_m = (
        interaction_reach_m
        if operator in {"grasp_object", "navigate_near", "place_object"}
        else clearance + 0.02
    )
    feasible: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for candidate in side_candidates:
        terminal_distance = _distance_to_object_footprint(candidate["position"], entity)
        if terminal_distance > required_terminal_distance_m:
            rejected.append({
                **candidate,
                "reason": "terminal_pose_outside_required_interaction_reach",
                "target_footprint_distance_m": round(terminal_distance, 3),
                "required_terminal_distance_m": round(required_terminal_distance_m, 3),
            })
            continue
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
            "maximum_near_distance_m": required_terminal_distance_m,
            "must_be_outside_longitudinal_projection": operator == "avoid",
        },
        "object_relative_motion": {
            "selected_side": selected["side"],
            "selected_terminal_position": terminal_position,
            "route_kind": selected["plan"]["route_kind"],
            "route_length_m": selected["route_length_m"],
            "planning_radius_m": planning_radius,
            "required_terminal_distance_m": required_terminal_distance_m,
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


def _execute_water_service_stage(
    session: dict[str, Any],
    intent: dict[str, Any],
    stage: dict[str, Any],
    scoped_authorization: dict[str, Any] | None,
) -> dict[str, Any]:
    bindings = intent["role_bindings"]
    action = stage["stage_id"]
    if action == "acquire_container":
        entity_ref = bindings["theme"]
        post_completion = {"action": "grasp", "target_entity_ref": entity_ref, "mode": "direct_task"}
        process = ["navigate_to_container", "align_end_effector", "grasp_container", "verify_container_in_effector"]
    elif action == "fill_container":
        entity_ref = bindings["source"]
        post_completion = {"action": "fill", "container_ref": bindings["theme"], "source_ref": bindings["source"], "mode": "direct_task"}
        process = ["navigate_to_water_source", "align_container_under_outlet", "activate_flow", "verify_container_filled"]
    elif action == "handover_to_recipient":
        entity_ref = bindings["recipient"]
        post_completion = {
            "action": "handover",
            "container_ref": bindings["theme"],
            "recipient_ref": bindings["recipient"],
            "require_filled_container": intent.get("intent_type") == "verified_water_delivery",
            "mode": "direct_task",
        }
        process = ["navigate_to_safe_handover_zone", "verify_recipient_readiness", "transfer_object", "verify_recipient_possession"]
    else:
        return {"status": "service_stage_not_supported", "reason": action, "frames": []}
    entity = next(item for item in session["runtime_objects"] if item["entity_id"] == entity_ref)
    result = _build_object_relative_motion(
        session,
        {
            "status": "contextual_affordance_available",
            "available": True,
            "entity_ref": entity_ref,
            "operator_candidate": "grasp_object" if action == "acquire_container" else "navigate_near",
            "task_context": stage["utterance"],
            "scoped_authorization_present": bool(scoped_authorization),
            "grounding_basis": {"source": "long_intent_role_binding", "binding_strength": "current_world_snapshot"},
        },
        perf_counter_ns(),
    )
    if result.get("status") != "fact_established":
        blocked = result.get("object_relative_motion") or {}
        rejected = blocked.get("rejected_candidates") or []
        reasons = ", ".join(
            f"{item.get('side')}:{item.get('reason')}" for item in rejected if item.get("side")
        )
        result["diagnostic"] = {
            "stage": action,
            "target_entity_ref": entity_ref,
            "blocking_reasons": reasons or result.get("reason"),
            "next_safe_actions": ["先移动到承载面边缘再继续", "移除阻挡物", "暂停任务等待人工调整"],
        }
        result["prompt"] = (
            f"当前阶段{action}无法执行：目标{entity.get('label', entity_ref)}没有通过本体净空验真。"
            + (f"候选方向结果：{reasons}。" if reasons else "")
            + "我会暂停当前阶段；可以先移动到承载面边缘、移除阻挡物，或等待你调整位置。"
        )
        return result
    result["post_completion"] = post_completion
    result["candidate_execution_plan"] = {
        "goal_fact": stage["target_fact"],
        "role_bindings": deepcopy(bindings),
        "required_facts": [stage["required_fact"], "current_role_bindings_grounded", "collision_free_current_route"],
        "candidate_process": process,
        "route_kind": result.get("object_relative_motion", {}).get("route_kind"),
        "route_length_m": result.get("object_relative_motion", {}).get("route_length_m"),
        "world_revision": session["world_revision"],
        "candidate_only": not bool(scoped_authorization),
        "direct_execution_allowed": bool(scoped_authorization),
    }
    if not scoped_authorization:
        pending = _create_pending_confirmation(session, stage["utterance"])
        result.update({
            "status": "requires_human_confirmation",
            "reason": "water_service_stage_requires_human_confirmation",
            "prompt": f"我已按当前空间重新绑定{entity['label']}并生成“{' → '.join(process)}”候选链；路径只用于本次执行。确认继续吗？",
            "pending_confirmation": deepcopy(pending),
            "frames": [],
        })
    return result


def _graph_role_refs(graph: dict[str, Any], role_name: str) -> list[str]:
    refs = (graph.get("roles") or {}).get(role_name)
    if isinstance(refs, list):
        return [str(ref) for ref in refs if ref]
    return [str(refs)] if refs else []


def _nested_graph_field(entity: dict[str, Any], path: str) -> Any:
    value: Any = entity
    for part in str(path or "").split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _set_nested_graph_field(entity: dict[str, Any], path: str, value: Any) -> None:
    parts = str(path or "").split(".")
    target = entity
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = deepcopy(value)


def _release_graph_entity_from_effector(session: dict[str, Any], entity_ref: str) -> None:
    for effector, held_ref in list(_holding_by_effector(session).items()):
        if held_ref == entity_ref:
            _holding_by_effector(session)[effector] = None
    _sync_primary_holding(session)


def _apply_causal_graph_node_effects(
    session: dict[str, Any], intent: dict[str, Any], node: dict[str, Any]
) -> dict[str, Any]:
    graph = intent.get("task_graph") or {}
    runtime = intent.get("causal_graph_runtime") or {}
    contract = node.get("execution_contract") or {}
    objects_before = deepcopy(session.get("runtime_objects", []))
    state_before = deepcopy(session.get("state", {}))
    objects = {item.get("entity_id"): item for item in session.get("runtime_objects", [])}
    effect_checks: list[dict[str, Any]] = []

    def role_entities(role: str) -> list[dict[str, Any]]:
        return [objects[ref] for ref in _graph_role_refs(graph, role) if ref in objects]

    try:
        for effect in contract.get("effects", []):
            operator = effect.get("operator")
            if operator == "move_role_members_to_container":
                themes = role_entities(effect["themes_role"])
                containers = role_entities(effect["container_role"])
                if not themes or len(containers) != 1:
                    raise ValueError("discard_roles_not_currently_grounded")
                container = containers[0]
                for index, theme in enumerate(themes):
                    _release_graph_entity_from_effector(session, theme["entity_id"])
                    theme.pop("support_ref", None)
                    theme.pop("received_by", None)
                    theme.pop("attached_to_executor", None)
                    theme.pop("held_by_effector", None)
                    theme["contained_by"] = container["entity_id"]
                    theme["position"] = [
                        float(container["position"][0]) + 0.02 * index,
                        float(container["position"][1]),
                    ]
                effect_checks.append({
                    "operator": operator,
                    "established": all(theme.get("contained_by") == container["entity_id"] and not theme.get("support_ref") for theme in themes),
                })
            elif operator == "decrement_role_inventory":
                entities = role_entities(effect["role"])
                if len(entities) != 1:
                    raise ValueError("inventory_role_not_currently_grounded")
                current = _nested_graph_field(entities[0], effect["field"])
                amount = int(effect.get("amount", 1))
                if current is None or int(current) < amount:
                    raise ValueError("inventory_amount_not_available")
                _set_nested_graph_field(entities[0], effect["field"], int(current) - amount)
                effect_checks.append({
                    "operator": operator,
                    "established": _nested_graph_field(entities[0], effect["field"]) == int(current) - amount,
                })
            elif operator == "set_role_fields":
                entities = role_entities(effect["role"])
                if not entities:
                    raise ValueError("field_target_role_not_currently_grounded")
                for entity in entities:
                    for field, value in (effect.get("fields") or {}).items():
                        _set_nested_graph_field(entity, field, value)
                effect_checks.append({
                    "operator": operator,
                    "established": all(
                        _nested_graph_field(entity, field) == value
                        for entity in entities
                        for field, value in (effect.get("fields") or {}).items()
                    ),
                })
            elif operator == "copy_role_field":
                sources = role_entities(effect["source_role"])
                targets = role_entities(effect["target_role"])
                if len(sources) != 1 or not targets:
                    raise ValueError("copy_field_roles_not_currently_grounded")
                value = _nested_graph_field(sources[0], effect["source_field"])
                for target in targets:
                    _set_nested_graph_field(target, effect["target_field"], value)
                effect_checks.append({
                    "operator": operator,
                    "established": all(_nested_graph_field(target, effect["target_field"]) == value for target in targets),
                })
            elif operator == "attach_role_to_available_effector":
                entities = role_entities(effect["role"])
                if len(entities) != 1:
                    raise ValueError("grasp_role_not_currently_grounded")
                grasp = _apply_verified_grasp(
                    session, entities[0]["entity_id"], "causal_graph_verified_node"
                )
                if grasp.get("status") != "fact_established":
                    raise ValueError(grasp.get("reason") or "graph_node_grasp_not_verified")
                effect_checks.append({"operator": operator, "established": _is_held(session, entities[0]["entity_id"])})
            elif operator == "support_roles_on_role":
                supports = role_entities(effect["support_role"])
                themes = [
                    entity
                    for role in effect.get("themes_roles", [])
                    for entity in role_entities(role)
                ]
                if len(supports) != 1 or not themes:
                    raise ValueError("support_loading_roles_not_currently_grounded")
                support = supports[0]
                offsets = [(-0.07, 0.0), (0.07, 0.0)]
                for index, theme in enumerate(themes):
                    _release_graph_entity_from_effector(session, theme["entity_id"])
                    theme.pop("received_by", None)
                    theme.pop("attached_to_executor", None)
                    theme.pop("held_by_effector", None)
                    theme["support_ref"] = support["entity_id"]
                    dx, dy = offsets[index] if index < len(offsets) else (0.0, 0.04 * index)
                    theme["position"] = [
                        float(support["position"][0]) + dx,
                        float(support["position"][1]) + dy,
                    ]
                effect_checks.append({
                    "operator": operator,
                    "established": all(theme.get("support_ref") == support["entity_id"] for theme in themes),
                })
            elif operator == "move_role_with_supported_payloads_to_executor":
                carriers = role_entities(effect["role"])
                if len(carriers) != 1 or not _is_held(session, carriers[0]["entity_id"]):
                    raise ValueError("carrier_not_verified_in_effector")
                carrier = carriers[0]
                carrier["position"] = deepcopy(session["state"]["executor_position"])
                payloads = [
                    item for item in session["runtime_objects"]
                    if item.get("support_ref") == carrier["entity_id"]
                ]
                for index, payload in enumerate(payloads):
                    payload["position"] = [
                        float(carrier["position"][0]) + (-0.07 if index == 0 else 0.07),
                        float(carrier["position"][1]),
                    ]
                effect_checks.append({
                    "operator": operator,
                    "established": _is_held(session, carrier["entity_id"]) and carrier.get("position") == session["state"]["executor_position"] and all(payload.get("support_ref") == carrier["entity_id"] for payload in payloads),
                })
            elif operator == "handover_role_to_role":
                themes = role_entities(effect["theme_role"])
                recipients = role_entities(effect["recipient_role"])
                if len(themes) != 1 or len(recipients) != 1:
                    raise ValueError("handover_roles_not_currently_grounded")
                theme, recipient = themes[0], recipients[0]
                if not _is_held(session, theme["entity_id"]) or not recipient.get("handover_ready"):
                    raise ValueError("handover_physical_precondition_not_verified")
                _release_graph_entity_from_effector(session, theme["entity_id"])
                theme.pop("attached_to_executor", None)
                theme.pop("held_by_effector", None)
                theme["received_by"] = recipient["entity_id"]
                theme["position"] = deepcopy(recipient["position"])
                recipient.setdefault("received_object_refs", [])
                if theme["entity_id"] not in recipient["received_object_refs"]:
                    recipient["received_object_refs"].append(theme["entity_id"])
                effect_checks.append({
                    "operator": operator,
                    "established": theme.get("received_by") == recipient["entity_id"] and not _is_held(session, theme["entity_id"]),
                })
            else:
                raise ValueError(f"unsupported_graph_effect_operator:{operator}")
        if not effect_checks or not all(check.get("established") for check in effect_checks):
            raise ValueError("declared_graph_effect_failed_postcondition_verification")
    except (KeyError, TypeError, ValueError) as exc:
        session["runtime_objects"] = objects_before
        session["state"] = state_before
        return {
            "status": "causal_graph_node_effect_failed",
            "reason": str(exc),
            "frames": [],
            "effect_contract_committed": False,
        }

    produces = list(node.get("produces", []))
    record_graph_facts(
        runtime,
        produces,
        source="causal_graph_node_terminal_verification",
        node_id=node["node_id"],
        world_revision=session["world_revision"],
        physical_verification=True,
    )
    runtime["active_node_id"] = None
    runtime["node_states"][node["node_id"]]["status"] = "completed"
    runtime["node_states"][node["node_id"]]["last_reason"] = None
    if node["node_id"] not in runtime["completed_node_order"]:
        runtime["completed_node_order"].append(node["node_id"])
    return {
        "status": "fact_established",
        "reason": "causal_graph_node_effects_physically_verified",
        "prompt": f"任务图节点“{node.get('label', node['node_id'])}”已通过末态验真。",
        "terminal_fact": produces[-1] if produces else None,
        "established_facts": produces,
        "graph_node_id": node["node_id"],
        "effect_contract_committed": True,
        "verification_evidence": {
            "node_id": node["node_id"],
            "verification_contract": deepcopy(node.get("verification", [])),
            "world_revision": session["world_revision"],
            "all_declared_effects_applied": True,
            "effect_checks": deepcopy(effect_checks),
        },
        "runtime_objects": deepcopy(session["runtime_objects"]),
        "frames": [],
    }


def _execute_causal_graph_stage(
    session: dict[str, Any],
    intent: dict[str, Any],
    stage: dict[str, Any],
    scoped_authorization: dict[str, Any] | None,
) -> dict[str, Any]:
    graph = intent.get("task_graph") or {}
    contract = stage.get("execution_contract") or {}
    target_refs = _graph_role_refs(graph, str(contract.get("target_role") or ""))
    target_ref = target_refs[0] if target_refs else None
    target = next(
        (item for item in session.get("runtime_objects", []) if item.get("entity_id") == target_ref),
        None,
    )
    if contract.get("mode") != "motion_effect" or not target:
        return {
            "status": "causal_graph_node_not_executable",
            "reason": "execution_contract_or_target_role_not_grounded",
            "graph_node_id": stage.get("graph_node_id"),
            "frames": [],
        }
    route_refs = [
        ref
        for role_name in contract.get("route_roles", [contract.get("target_role")])
        for ref in _graph_role_refs(graph, str(role_name or ""))
    ]
    planning_session = deepcopy(session)
    all_frames: list[dict[str, Any]] = []
    route_segments = []
    result: dict[str, Any] = {}
    for route_ref in route_refs:
        route_entity = next(
            (item for item in planning_session.get("runtime_objects", []) if item.get("entity_id") == route_ref),
            None,
        )
        if not route_entity:
            return {
                "status": "causal_graph_node_not_executable",
                "reason": "route_role_not_grounded_in_current_world",
                "missing_entity_ref": route_ref,
                "frames": [],
            }
        result = _build_object_relative_motion(
            planning_session,
            {
                "status": "contextual_affordance_available",
                "available": True,
                "entity_ref": route_ref,
                "operator_candidate": "navigate_near",
                "task_context": stage["utterance"],
                "scoped_authorization_present": bool(scoped_authorization),
                "grounding_basis": {
                    "source": "causal_graph_role_binding_revalidated_in_current_world",
                    "binding_strength": "current_world_snapshot",
                },
            },
            perf_counter_ns(),
        )
        if result.get("status") != "fact_established":
            result["failed_route_entity_ref"] = route_ref
            result["completed_route_segments"] = deepcopy(route_segments)
            return result
        segment_frames = deepcopy(result.get("frames", []))
        all_frames.extend(segment_frames)
        if segment_frames:
            planning_session["state"]["executor_position"] = deepcopy(segment_frames[-1]["position"])
            if segment_frames[-1].get("yaw_deg") is not None:
                planning_session["state"]["executor_yaw_deg"] = segment_frames[-1]["yaw_deg"]
        route_segments.append({
            "entity_ref": route_ref,
            "route_kind": (result.get("object_relative_motion") or {}).get("route_kind"),
            "frame_count": len(segment_frames),
            "terminal_pose_preverified": True,
        })
    result["frames"] = all_frames
    result["causal_graph_route_segments"] = route_segments
    if not result.get("frames"):
        result["frames"] = [{
            "position": deepcopy(session["state"]["executor_position"]),
            "yaw_deg": session["state"].get("executor_yaw_deg", 0.0),
            "duration_s": 0.05,
        }]
    result["post_completion"] = {
        "action": "causal_graph_node",
        "intent_id": intent["intent_id"],
        "node_id": stage["graph_node_id"],
    }
    result["candidate_execution_plan"] = {
        "goal_fact": stage.get("target_fact"),
        "produces_facts": deepcopy(stage.get("produces_facts", [])),
        "role_bindings": deepcopy(graph.get("roles", {})),
        "candidate_process": deepcopy(contract.get("process_chain", [])),
        "route_segments": deepcopy(route_segments),
        "process_template": contract.get("process_template"),
        "world_revision": session["world_revision"],
        "candidate_only": not bool(scoped_authorization),
        "direct_execution_allowed": bool(scoped_authorization),
    }
    return result


def _execute_transport_region_stage(
    session: dict[str, Any],
    intent: dict[str, Any],
    stage: dict[str, Any],
    scoped_authorization: dict[str, Any] | None,
) -> dict[str, Any]:
    region_ref = intent.get("role_bindings", {}).get("target_region")
    region = next((item for item in _scene_for_session(session)["semantic_regions"] if item.get("region_id") == region_ref), None)
    theme_ref = intent.get("role_bindings", {}).get("theme")
    if not region or not theme_ref or not _is_held(session, theme_ref):
        return {"status": "transport_stage_blocked", "reason": "target_region_or_holding_fact_not_established", "frames": []}
    start = list(session["state"]["executor_position"])
    target = list(region["center"])
    envelope = build_effective_execution_envelope(session["executor_profile"], session.get("protection_policy_overlay"))
    planning_radius = envelope["effective_constraints"]["body_radius_m"] + envelope["effective_constraints"]["minimum_avoidance_distance_m"]
    plan = _plan_verified_motion(session, start, target, planning_radius)
    if plan.get("outcome") != "verified":
        return {
            "status": "transport_stage_blocked",
            "reason": "no_verified_route_to_target_region",
            "target_region": region_ref,
            "route_evidence": deepcopy(plan),
            "frames": [],
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
    _apply_speed_timing(frames, envelope["effective_constraints"]["max_linear_speed_mps"])
    return {
        "status": "fact_established",
        "reason": "verified_object_transport_region_candidate",
        "prompt": f"已生成保持当前持物并进入{region['label']}的当前地图路径；执行末帧将重新验真本体与对象均位于目标区域。",
        "frames": frames,
        "terminal_fact": "object_at_target_region",
        "terminal_fact_binding": {"object_ref": theme_ref, "target_region_ref": region_ref},
        "candidate_execution_plan": {
            "goal_fact": "object_at_target_region",
            "role_bindings": deepcopy(intent.get("role_bindings", {})),
            "candidate_process": ["retain_verified_holding", "navigate_current_map_to_region", "verify_executor_and_object_inside_region"],
            "route_kind": plan.get("route_kind"),
            "world_revision": session["world_revision"],
            "candidate_only": not bool(scoped_authorization),
            "direct_execution_allowed": bool(scoped_authorization),
        },
        "route_evidence": deepcopy(plan.get("safety_contract")),
        "effective_execution_envelope": envelope,
    }


def execute_command(
    session_id: str,
    utterance: str,
    scoped_authorization: dict[str, Any] | None = None,
    language_analysis: dict[str, Any] | None = None,
    grounded_role_bindings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision_started_ns = perf_counter_ns()
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    original_text = utterance.strip()
    language_analysis = language_analysis or _compose_session_language(session, original_text)
    language_view = _language_understanding_view(language_analysis)
    gap_dialogue_collecting = (session.get("concept_gap_dialogue") or {}).get("status") == "collecting_minimum_causal_contract"
    definition = language_analysis.get("definition_candidate")
    if definition and not scoped_authorization:
        active_gap = session.get("concept_gap_dialogue") or {}
        pending = _create_language_confirmation(
            session,
            language_analysis,
            resume_utterance=active_gap.get("source_utterance") if active_gap.get("status") == "collecting_minimum_causal_contract" else None,
        )
        return {
            "status": "language_adapter_confirmation_required",
            "reason": "human_definition_compiled_as_scoped_language_adapter_candidate",
            "prompt": (
                f"我理解你在说明“{definition['surface_form']}”表示“{definition['canonical_surface']}”这一事件概念。"
                "请确认这个理解是否正确；确认后只保存语言入口，不会直接修改概念核或写入物理事实。"
            ),
            "language_understanding": language_view,
            "language_adapter_candidate": deepcopy(definition),
            "pending_confirmation": deepcopy(pending),
            "candidate_only": True,
            "runtime_fact_committed": False,
            "direct_execution_allowed": False,
            "session": get_session(session_id),
        }
    if language_analysis.get("speech_act") == "prohibition":
        session["language_interpretation_history"].append({
            "utterance": original_text,
            "decision": "prohibition_understood_no_execution",
            "world_revision": session["world_revision"],
        })
        return {
            "status": "prohibition_understood",
            "reason": "negated_event_must_not_be_converted_to_positive_execution",
            "prompt": "我理解这是禁止或撤销该动作，而不是让我执行它。我不会生成对应的正向动作命令。",
            "language_understanding": language_view,
            "candidate_only": False,
            "runtime_fact_committed": False,
            "direct_execution_allowed": False,
            "session": get_session(session_id),
        }
    if _is_restore_request(original_text):
        restore_gap = _answer_restore_destination_gap(session)
        if restore_gap:
            restore_gap["language_understanding"] = language_view
            return restore_gap
    if (
        language_analysis.get("decision") == "request_minimum_semantic_clarification"
        and language_analysis.get("canonical_utterance")
        and not gap_dialogue_collecting
        and not scoped_authorization
    ):
        pending = _create_language_confirmation(session, language_analysis)
        return {
            "status": "language_interpretation_confirmation_required",
            "reason": "compositional_semantics_has_unresolved_scope",
            "prompt": (
                f"我暂时把这句话理解为“{language_analysis['canonical_utterance']}”，但还不确定："
                f"{'、'.join(language_analysis.get('unresolved_slots', [])) or '表达作用域'}。这个理解对吗？"
            ),
            "language_understanding": language_view,
            "pending_confirmation": deepcopy(pending),
            "candidate_only": True,
            "runtime_fact_committed": False,
            "direct_execution_allowed": False,
            "session": get_session(session_id),
        }
    text = (
        language_analysis.get("canonical_utterance")
        if language_analysis.get("decision") == "route_canonical_semantics" and language_analysis.get("canonical_utterance")
        else original_text
    )
    if _is_holding_state_query(text):
        result = _answer_holding_state_query(session)
        result["language_understanding"] = language_view
        return result
    if _is_restore_request(text):
        restore_gap = _answer_restore_destination_gap(session)
        if restore_gap:
            return restore_gap
    if _is_object_location_query(text):
        result = _answer_object_location_query(session, text)
        result["language_understanding"] = language_view
        return result
    if _is_object_presence_query(text):
        observation = _answer_object_presence_query(session, text)
        session["open_world_observation"] = deepcopy(observation)
        observation["session"] = get_session(session_id)
        observation["language_understanding"] = language_view
        return observation
    if _is_open_world_observation_query(text):
        observation = _answer_observation_query(session, text)
        session["open_world_observation"] = deepcopy(observation)
        observation["session"] = get_session(session_id)
        observation["language_understanding"] = language_view
        return observation
    active_gap_dialogue = session.get("concept_gap_dialogue") or {}
    if active_gap_dialogue.get("status") == "collecting_minimum_causal_contract":
        continued = continue_concept_gap_dialogue(
            active_gap_dialogue,
            answer=original_text,
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
            "language_understanding": language_view,
            "session": get_session(session_id),
        }
    relocation_preview = _build_observed_relocation_preview(session, text)
    if relocation_preview:
        return relocation_preview
    role_grounding_context = grounded_role_bindings or (scoped_authorization or {}).get("role_bindings") or {}
    task_perception = build_task_perception_result(
        _scene_for_session(session), session, text, grounded_role_bindings=role_grounding_context
    )
    if task_perception and scoped_authorization:
        bound_ref = (scoped_authorization.get("role_bindings") or {}).get("theme")
        if bound_ref:
            grounding = task_perception.setdefault("concept_grounding", {})
            bound = next(
                (item for item in grounding.get("candidate_bindings", []) if item.get("entity_ref") == bound_ref),
                None,
            )
            if bound:
                # Internal execution is already authorized against a resolved
                # role. Collapse perception to that entity and preserve the
                # physical observation as evidence, rather than reopening the
                # user-facing ambiguity.
                grounding["candidate_bindings"] = [deepcopy(bound)]
                grounding["grounding_status"] = "spatially_grounded"
                grounding["ambiguity_reason"] = None
                grounding["target_entity_ref"] = bound_ref
    perception_bindings = (
        task_perception.get("concept_grounding", {}).get("candidate_bindings", [])
        if task_perception else []
    )
    if not perception_bindings and role_grounding_context:
        runtime_index = {item.get("entity_id"): item for item in session.get("runtime_objects", [])}
        for role_name, binding_role in (("target", "theme"), ("support", "destination")):
            entity = runtime_index.get(role_grounding_context.get(binding_role))
            if not entity:
                continue
            perception_bindings.append({
                "role": role_name,
                "entity_ref": entity.get("entity_id"),
                "label_hint": entity.get("label"),
                "binding_strength": "current_task_role_revalidated_in_world_snapshot",
                "evidence_ref": f"world_revision:{session['world_revision']}:{binding_role}_role",
                "state": "runtime_revalidated",
                "estimated_position": deepcopy(entity.get("position")),
                "observed_attributes": observed_perceptual_attributes(entity),
            })
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
        normalized_gap = normalize_perception_gap(
            language_analysis.get("process_template_resolution"),
            task_perception,
        )
        if normalized_gap and not scoped_authorization:
            immediate = _start_process_gap_dialogue(
                session,
                source_utterance=original_text,
                language_analysis=language_analysis,
                resolution=normalized_gap,
            )
            immediate.update({
                "status": "process_grounding_clarification_required",
                "reason": "required_process_slot_lacks_current_grounding_evidence",
                "task_perception": deepcopy(task_perception),
                "grounding_gap": deepcopy(normalized_gap.get("grounding_gap")),
            })
            return immediate
        ambiguity_reason = task_perception.get("concept_grounding", {}).get("ambiguity_reason")
        if ambiguity_reason == "target_not_observed" and task_perception.get("concept_grounding", {}).get("constraint_rejections"):
            _start_evidence_gap_clarification(
                session,
                source_utterance=original_text,
                task_perception=task_perception,
            )
        if ambiguity_reason in {"multiple_target_candidates", "multiple_support_candidates"} and not scoped_authorization:
            role = "destination" if ambiguity_reason == "multiple_support_candidates" else "theme"
            option_key = "support_candidate_options" if role == "destination" else "candidate_options"
            concept_key = "support_concept_id" if role == "destination" else "target_concept_id"
            _start_role_clarification(
                session,
                source_utterance=original_text,
                role=role,
                concept_id=task_perception.get("task_perception_frame", {}).get(concept_key),
                options=task_perception.get("concept_grounding", {}).get(option_key, []),
                evidence_source="bounded_multi_view_task_perception",
            )
        task_perception["session"] = get_session(session_id)
        task_perception["language_understanding"] = language_view
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
        role_binding_evidence=(scoped_authorization or {}).get("role_binding_evidence") or role_grounding_context.get("_evidence"),
    )
    if contextual_affordance:
        if task_perception:
            contextual_affordance["task_perception"] = task_perception
        if contextual_affordance.get("status") == "contextual_affordance_disambiguation_required":
            candidate_concept_id = next(
                (
                    concept.get("concept_id")
                    for concept in load_object_concepts()["concepts"]
                    if any(
                        option.get("kind") in concept.get("compatible_kinds", [])
                        for option in contextual_affordance.get("candidate_options", [])
                    )
                ),
                None,
            )
            _start_role_clarification(
                session,
                source_utterance=original_text,
                role="destination" if contextual_affordance.get("operator_candidate") == "navigate_near" else contextual_affordance.get("active_role", "target"),
                concept_id=candidate_concept_id,
                options=contextual_affordance.get("candidate_options", []),
                evidence_source="current_runtime_role_candidates",
            )
        if contextual_affordance["available"] and contextual_affordance["operator_candidate"] in {"navigate_near", "avoid", "grasp_object", "place_object"}:
            result = _build_object_relative_motion(session, contextual_affordance, decision_started_ns)
            result["language_understanding"] = language_view
            return result
        return {
            **contextual_affordance,
            "prompt": contextual_affordance["explanation"],
            "language_understanding": language_view,
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
            result = _build_factory_response(session, text, concept, perception_result, decision_started_ns)
            result["language_understanding"] = language_view
            return result
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
        perception_result["language_understanding"] = language_view
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
            "language_understanding": language_view,
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
    result["language_understanding"] = language_view
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


def _is_historical_return_navigation_request(analysis: dict[str, Any]) -> bool:
    frame = analysis.get("situated_event_frame") or {}
    return bool(
        analysis.get("speech_act") == "task_request"
        and frame.get("temporal_scope") in {"most_recent_verified_past", "verified_past"}
        and "navigate_to" in frame.get("operators", [])
    )


def _build_historical_return_navigation(
    session: dict[str, Any], text: str, analysis: dict[str, Any]
) -> dict[str, Any] | None:
    if not _is_historical_return_navigation_request(analysis):
        return None
    reference = _resolve_recent_verified_event_referent(session, analysis)
    support_ref = (reference or {}).get("related_support_ref")
    if not reference or not support_ref:
        return {
            "status": "historical_navigation_reference_not_resolved",
            "reason": "matching_verified_event_has_no_source_support",
            "prompt": "我理解你要返回某次已验真动作的来源位置，但事件记录中没有可解析的来源承载面。请指出是哪次动作或哪个地方。",
            "frames": [],
            "historical_reference": deepcopy(reference),
            "language_understanding": _language_understanding_view(analysis),
            "runtime_fact_committed": False,
        }
    support = next(
        (
            item for item in session.get("runtime_objects", [])
            if item.get("entity_id") == support_ref and item.get("active") is not False
        ),
        None,
    )
    if not support:
        return {
            "status": "historical_navigation_target_not_currently_grounded",
            "reason": "historical_referent_absent_from_current_world_snapshot",
            "prompt": "我找到了历史事件中的来源位置，但该实体没有在当前任务期世界快照中重新落地，因此不能沿用旧位置或旧路径导航。",
            "frames": [],
            "historical_reference": deepcopy(reference),
            "language_understanding": _language_understanding_view(analysis),
            "runtime_fact_committed": False,
        }
    result = _build_object_relative_motion(
        session,
        {
            "status": "contextual_affordance_available",
            "available": True,
            "entity_ref": support_ref,
            "operator_candidate": "navigate_near",
            "task_context": text,
            "scoped_authorization_present": False,
            "grounding_basis": {
                "source": "recent_verified_event_referent_revalidated_in_current_snapshot",
                "binding_strength": "current_world_snapshot",
                "episode_id": reference.get("episode_id"),
            },
        },
        perf_counter_ns(),
    )
    result["historical_reference"] = deepcopy(reference)
    result["historical_reference"]["current_target_revalidated"] = True
    result["historical_reference"]["old_trajectory_reused"] = False
    result["language_understanding"] = _language_understanding_view(analysis)
    if result.get("frames"):
        result["prompt"] = (
            f"我已从最近一次匹配的已验真事件中解析出来源位置是{support.get('label', support_ref)}；"
            "目标已在当前世界快照中重新验真，路线按当前几何重新生成，没有复用旧轨迹。"
        )
    return result


def _finalize_motion_result(
    session_id: str,
    text: str,
    before: dict[str, Any],
    result: dict[str, Any],
    scoped_authorization: dict[str, Any] | None,
) -> dict[str, Any]:
    live = SESSIONS[session_id]
    pending_confirmation = deepcopy(live.get("pending_confirmation"))
    perception_history = deepcopy(live.get("perception_history", []))
    concept_gap_dialogue = deepcopy(live.get("concept_gap_dialogue"))
    role_clarification_dialogue = deepcopy(live.get("role_clarification_dialogue"))
    evidence_gap_dialogue = deepcopy(live.get("evidence_gap_dialogue"))
    process_gap_dialogue = deepcopy(live.get("process_gap_dialogue"))
    SESSIONS[session_id] = before
    frames = result.get("frames", [])
    if not frames:
        if pending_confirmation:
            SESSIONS[session_id]["pending_confirmation"] = pending_confirmation
        if result.get("task_perception_frame"):
            SESSIONS[session_id]["perception_history"] = perception_history
        if concept_gap_dialogue:
            SESSIONS[session_id]["concept_gap_dialogue"] = concept_gap_dialogue
        if role_clarification_dialogue:
            SESSIONS[session_id]["role_clarification_dialogue"] = role_clarification_dialogue
        if evidence_gap_dialogue:
            SESSIONS[session_id]["evidence_gap_dialogue"] = evidence_gap_dialogue
        if process_gap_dialogue:
            SESSIONS[session_id]["process_gap_dialogue"] = process_gap_dialogue
        result["session"] = get_session(session_id)
        return {"status": result.get("status"), "immediate_result": result, "session": get_session(session_id)}
    job_id = "motion_" + hashlib.sha1(f"{session_id}|{len(MOTION_JOBS) + 1}".encode()).hexdigest()[:12]
    job = {
        "job_id": job_id,
        "session_id": session_id,
        "utterance": text,
        "status": "running",
        "planned_world_revision": before["world_revision"],
        "planned_policy_revision": before["policy_revision"],
        "frames": frames,
        "next_frame_index": 0,
        "terminal_result": result,
        "post_completion": deepcopy(result.get("post_completion")),
        "execution_intent": _post_completion_signature(result.get("post_completion")),
        "continuation_authorized": _authorization_is_current(before, text, scoped_authorization),
        "replan_state_history": [],
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
        "historical_reference": deepcopy(result.get("historical_reference")),
        "session": get_session(session_id),
    }


def _continue_causal_graph_clarification(
    session: dict[str, Any],
    answer: str,
    language_analysis: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    dialogue = session.get("causal_graph_clarification")
    if not dialogue:
        return None
    intent = (session.get("long_horizon_intents") or {}).get(dialogue.get("intent_id"))
    if not intent or intent.get("causal_graph_runtime") is None:
        session["causal_graph_clarification"] = None
        return None
    resolved = apply_condition_answer(
        intent.get("task_graph") or {},
        intent["causal_graph_runtime"],
        answer,
        world_revision=session["world_revision"],
    )
    if resolved.get("status") == "condition_answer_not_resolved":
        # A complete new task is not an answer to an older graph slot. Release
        # the old task-period snapshot and let normal arbitration create a new
        # task from the current physical world.
        if (
            (language_analysis or {}).get("speech_act") == "task_request"
            and any(
                item.get("operator")
                for item in (language_analysis or {}).get("event_candidates", [])
            )
        ):
            intent["lifecycle"] = "superseded"
            intent["current_stage"] = None
            _archive_and_release_task_context(
                session,
                intent,
                lifecycle="superseded",
                release_reason="new_goal_directed_task_superseded_pending_condition",
                archive_key="released_intent_archive",
            )
            session.get("long_horizon_intents", {}).pop(intent["intent_id"], None)
            if session.get("active_intent_id") == intent["intent_id"]:
                session["active_intent_id"] = None
                session["intent_activation_stack"] = []
            session["causal_graph_clarification"] = None
            return None
        return {
            "status": "causal_graph_clarification_required",
            "reason": "answer_did_not_resolve_pending_causal_condition",
            "prompt": resolved.get("prompt") or dialogue.get("question"),
            "pending_condition": deepcopy(intent["causal_graph_runtime"].get("pending_condition")),
            "long_horizon_intent": _long_intent_view(intent),
            "session": get_session(session["session_id"]),
        }
    if resolved.get("status") == "condition_world_change_required":
        intent["lifecycle"] = "awaiting_correction"
        return {
            **resolved,
            "long_horizon_intent": _long_intent_view(intent),
            "session": get_session(session["session_id"]),
        }
    session["causal_graph_clarification"] = None
    intent["lifecycle"] = "active"
    prepared = _prepare_long_intent_stage(session, intent)
    prepared["condition_resolution"] = deepcopy(resolved)
    prepared["session"] = get_session(session["session_id"])
    return prepared


def begin_motion_command(
    session_id: str,
    utterance: str,
    scoped_authorization: dict[str, Any] | None = None,
    internal_stage: bool = False,
    grounded_role_bindings: dict[str, Any] | None = None,
    compound_dispatch: bool = False,
) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "embodied_session_not_found", "session_id": session_id}
    text = utterance.strip()
    if not internal_stage and not scoped_authorization and not compound_dispatch:
        session["interaction_turn"] = int(session.get("interaction_turn", 0)) + 1
        if len(session.get("event_history", [])) > 32:
            del session["event_history"][:-32]
    _debug_runtime(
        "input_received",
        session,
        utterance=text,
        internal_stage=internal_stage,
        scoped_authorization=bool(scoped_authorization),
        compound_dispatch=compound_dispatch,
    )
    count_match = re.search(r"(?:有|看到|当前有)?\s*(?:几个|多少个)\s*(杯子|杯|容器|人|客人|桌子|台子)", text)
    if count_match:
        noun = count_match.group(1)
        kind_map = {
            "杯子": "graspable_container", "杯": "graspable_container", "容器": "graspable_container",
            "人": "human_recipient", "客人": "human_recipient",
            "桌子": "operation_surface", "台子": "operation_surface",
        }
        kind = kind_map[noun]
        candidates = [item for item in session.get("runtime_objects", []) if item.get("active") is not False and item.get("kind") == kind]
        labels = [item.get("label") or item.get("entity_id") for item in candidates]
        return {
            "status": "state_query_answered",
            "query_type": "count_entities",
            "prompt": f"当前空间中有{len(candidates)}个{noun}：{'、'.join(labels)}。",
            "answer": {"count": len(candidates), "entity_refs": [item.get("entity_id") for item in candidates], "labels": labels},
            "runtime_fact_committed": False,
            "session": get_session(session_id),
        }
    if text in {"你遇到了什么问题", "遇到什么问题", "为什么停了", "为什么停止", "怎么了", "发生了什么"}:
        diagnostic = deepcopy(session.get("last_runtime_diagnostic"))
        if diagnostic:
            return {
                "status": "runtime_diagnostic_report",
                "prompt": (
                    f"我在{diagnostic.get('stage') or '当前阶段'}遇到问题：{diagnostic.get('reason')}。"
                    f"根因类别是{diagnostic.get('category')}。"
                    f"下一步可以：{'；'.join(diagnostic.get('recovery_options') or [])}。"
                ),
                "runtime_diagnostic": diagnostic,
                "session": get_session(session_id),
            }
        return {
            "status": "runtime_diagnostic_unavailable",
            "prompt": "当前没有可供总结的最近一次停止诊断。",
            "session": get_session(session_id),
        }
    if text in {"暂停当前任务", "暂停任务", "先别做了"}:
        suspended = _suspend_active_intent(session)
        if suspended:
            return {"status": suspended["status"], "immediate_result": suspended, "session": suspended["session"]}
    if text in {"继续当前任务", "继续任务", "恢复任务"}:
        resumed = _resume_active_intent(session)
        if resumed:
            resumed["immediate_result"]["session"] = get_session(session_id)
            return resumed
    # P018 input arbitration precedes every pending task/dialogue state. Run
    # semantic analysis on a copy so a read-only query cannot mutate focus,
    # pending slots, intent lifecycle, or the task-period world snapshot.
    early_analysis = None
    if not internal_stage and not scoped_authorization:
        early_analysis = _compose_session_language(deepcopy(session), text)
        if _is_support_inventory_state_query(text, early_analysis):
            return _answer_support_inventory_state_query(session, text, early_analysis)
        if _is_historical_return_navigation_request(early_analysis):
            if session.get("pending_confirmation"):
                _revoke_pending_confirmation(session, "superseded_by_historical_navigation_task_control")
            before_historical_navigation = deepcopy(session)
            # Rebuild after the revocation snapshot so only planning-side
            # mutations are rolled back while the task-control decision stays.
            historical_navigation = _build_historical_return_navigation(session, text, early_analysis)
            return _finalize_motion_result(
                session_id, text, before_historical_navigation, historical_navigation, None
            )
        graph_clarification = _continue_causal_graph_clarification(
            session, text, early_analysis
        )
        if graph_clarification:
            return graph_clarification
    pending = session.get("pending_confirmation")
    confirmation_value = _context_confirmation_value(utterance)
    if pending and confirmation_value is not None and not scoped_authorization:
        confirmed = confirm_pending_motion(session_id, pending["confirmation_id"], confirmation_value)
        if confirmed.get("status") == "observation_candidate_confirmed":
            return {"status": confirmed["status"], "immediate_result": confirmed, "session": confirmed.get("session")}
        return confirmed
    if pending and pending.get("kind") == "language_interpretation" and not scoped_authorization:
        explained = _continue_historical_reference_explanation(session, pending, utterance)
        if explained:
            return explained
    process_gap_resolution = _continue_process_gap_dialogue(session, utterance)
    if process_gap_resolution:
        return process_gap_resolution
    relational_dialogue = session.get("relational_reference_dialogue")
    if relational_dialogue and not scoped_authorization:
        explained = _continue_historical_reference_explanation(
            session,
            {
                "original_utterance": relational_dialogue.get("source_utterance"),
                "language_analysis": relational_dialogue.get("language_analysis"),
            },
            utterance,
        )
        if explained:
            return explained
    # A repeated goal request is not an answer to a stale role dialogue. Once
    # an active water intent owns the theme binding, only a candidate label may
    # resolve that dialogue; otherwise discard it and resume the active goal.
    stale_role_dialogue = session.get("role_clarification_dialogue")
    active_for_dialogue = (session.get("long_horizon_intents") or {}).get(session.get("active_intent_id"))
    if (
        stale_role_dialogue
        and active_for_dialogue
        and active_for_dialogue.get("goal_fact") == "human_received_filled_container"
        and (active_for_dialogue.get("current_stage") or {}).get("stage_id") == "fill_container"
    ):
        session["role_clarification_dialogue"] = None
        stale_role_dialogue = None
    if (
        stale_role_dialogue
        and active_for_dialogue
        and active_for_dialogue.get("goal_fact") == "human_received_filled_container"
        and (active_for_dialogue.get("role_bindings") or {}).get("theme")
        and stale_role_dialogue.get("evidence_source") == "current_world_container_candidates"
        and not any(
            str(option.get("label") or option.get("label_hint") or "") in utterance
            for option in stale_role_dialogue.get("candidate_options", [])
        )
    ):
        session["role_clarification_dialogue"] = None
    # Input arbitration happens before any pending role dialogue. Read-only
    # state queries must never consume clarification slots or alter the task.
    if (
        _is_holding_state_query(text)
        or _is_object_location_query(text)
        or _is_object_presence_query(text)
        or _is_open_world_observation_query(text)
    ):
        query_result = execute_command(session_id, text, None, None)
        return {
            "status": query_result.get("status"),
            "immediate_result": query_result,
            "session": get_session(session_id),
        }
    # Central recovery gate: every non-query retry/confirmation path must
    # prune from the active intent's verified facts before role dialogue,
    # experience replay, or fresh process search can run.
    active_recovery = (session.get("long_horizon_intents") or {}).get(session.get("active_intent_id"))
    if (
        active_recovery
        and active_recovery.get("intent_type") == "verified_water_delivery"
        and active_recovery.get("lifecycle") in {"active", "awaiting_correction", "suspended"}
        and "container_in_effector" in active_recovery.get("verified_facts", [])
        and "container_filled" not in active_recovery.get("verified_facts", [])
        and not internal_stage
        and not scoped_authorization
    ):
        session["role_clarification_dialogue"] = None
        resumed = _prepare_long_intent_stage(session, active_recovery)
        resumed["recovery_pruned_from_verified_facts"] = True
        resumed["session"] = get_session(session_id)
        return resumed
    role_clarification = _continue_role_clarification(session, utterance)
    if role_clarification:
        return role_clarification
    evidence_gap_resolution = _continue_evidence_gap_clarification(session, utterance)
    if evidence_gap_resolution:
        return evidence_gap_resolution
    language_analysis = _compose_session_language(session, text)
    if not internal_stage and not scoped_authorization and not compound_dispatch:
        compound_started = _start_compound_command_sequence(
            session, text, language_analysis
        )
        if compound_started:
            return compound_started
    hospitality_intent = None
    if not internal_stage and not scoped_authorization and session.get("scene_id") == "hospitality_guest":
        existing_hospitality = (session.get("long_horizon_intents") or {}).get(session.get("active_intent_id"))
        if existing_hospitality and existing_hospitality.get("intent_type") == "hospitality_guest_service":
            hospitality_intent = existing_hospitality
        else:
            hospitality_intent = _create_hospitality_intent(
                session, text, language_analysis
            )
    if hospitality_intent:
        prepared = _prepare_long_intent_stage(session, hospitality_intent)
        prepared["task_graph"] = deepcopy(hospitality_intent.get("task_graph"))
        prepared["task_graph_evaluation"] = deepcopy(hospitality_intent.get("task_graph_evaluation"))
        prepared["session"] = get_session(session_id)
        return prepared
    composite_water_goal = _water_delivery_goal_semantics(
        session, text, language_analysis
    ).get("goal_fact") in {
        "human_received_filled_container", "filled_container_supported_at_destination"
    }
    active_water_intent = (session.get("long_horizon_intents") or {}).get(session.get("active_intent_id"))
    active_water_binding = bool(
        active_water_intent
        and active_water_intent.get("lifecycle") in {"active", "awaiting_correction"}
        and active_water_intent.get("goal_fact") == "human_received_filled_container"
        and (active_water_intent.get("role_bindings") or {}).get("theme")
    )
    if active_water_binding and not internal_stage and not scoped_authorization:
        # An active long-horizon goal owns its resolved roles. A repeated
        # request must resume the current causal stage even if this utterance
        # is lexically under-parsed; only an explicit goal change may replace it.
        resumed = _prepare_long_intent_stage(session, active_water_intent)
        resumed["reused_active_water_intent"] = True
        resumed["session"] = get_session(session_id)
        return resumed
    if composite_water_goal and not internal_stage and not scoped_authorization:
        water_containers = [
            item for item in session["runtime_objects"]
            if item.get("active") is not False
            and item.get("kind") == "graspable_container"
        ]
        container_resolution = _resolve_current_role_binding(
            session,
            text,
            water_containers,
            role="theme",
            language_analysis=language_analysis,
            confirmed_entity_ref=session.get("pending_water_container_ref"),
        )
        if container_resolution.get("status") != "resolved" and len(water_containers) > 1 and not active_water_binding:
            container_concept = next(
                (
                    concept for concept in load_object_concepts()["concepts"]
                    if "graspable_container" in concept.get("compatible_kinds", [])
                ),
                None,
            )
            options = [
                {
                    "entity_ref": item["entity_id"],
                    "value_ref": item["entity_id"],
                    "label": item.get("label") or item["entity_id"],
                    "label_hint": item.get("label") or item["entity_id"],
                    "value_type": "graspable_container",
                    "evidence": "current_world_snapshot",
                }
                for item in water_containers
            ]
            _start_role_clarification(
                session,
                source_utterance=text,
                role="theme",
                concept_id=(container_concept or {}).get("concept_id"),
                options=options,
                evidence_source="current_world_container_candidates",
            )
            return {
                "status": "role_clarification_required",
                "reason": "water_delivery_container_not_uniquely_bound",
                "prompt": f"接水需要选择一个容器。当前候选是：{'、'.join(item['label'] for item in options)}。你要用哪一个？",
                "known_goal": "human_received_filled_container",
                "pending_role": "theme",
                "candidate_options": deepcopy(options),
                "candidate_only": True,
                "runtime_fact_committed": False,
                "session": get_session(session_id),
            }
    process_resolution = language_analysis.get("process_template_resolution") or {}
    historical_reference = None if internal_stage or scoped_authorization else _historical_support_reference_candidate(
        session, text, language_analysis
    )
    if (
        not internal_stage
        and not scoped_authorization
        and not composite_water_goal
        and not historical_reference
        and language_analysis.get("speech_act") not in {"language_teaching", "prohibition", "state_query"}
        and process_resolution.get("status") in {"template_confirmation_required", "clarification_required", "unsafe_switch"}
    ):
        immediate = _start_process_gap_dialogue(
            session,
            source_utterance=text,
            language_analysis=language_analysis,
            resolution=process_resolution,
        )
        return {"status": immediate["status"], "immediate_result": immediate, "session": get_session(session_id)}
    if historical_reference:
        candidate = historical_reference["historical_reference_candidate"]
        if not candidate.get("destination_entity_ref"):
            session["relational_reference_dialogue"] = {
                "status": "collecting_missing_historical_relation",
                "source_utterance": text,
                "language_analysis": deepcopy(historical_reference),
                "missing_slot": "destination_entity_ref",
                "known_roles": {"theme": candidate["theme_label"], "operator": "place_object", "reference": candidate["reference_label"]},
            }
            immediate = {
                "status": "relational_reference_clarification_required",
                "reason": "historical_support_relation_not_found",
                "prompt": (
                    f"我已理解对象是{candidate['theme_label']}、动作是放置；但记忆中没有找到{candidate['reference_label']}"
                    "最近由哪个承载面支撑。请告诉我它当时在哪个桌面，或你是从哪个桌面拿起它的。"
                ),
                "known_roles": deepcopy(session["relational_reference_dialogue"]["known_roles"]),
                "missing_role": "destination",
                "historical_relation_query": {
                    "subject": candidate["reference_entity_ref"],
                    "predicate": "supported_by",
                    "temporal_scope": "recent_verified_runtime_past",
                },
                "language_understanding": _language_understanding_view(historical_reference),
                "candidate_only": True,
                "runtime_fact_committed": False,
                "direct_execution_allowed": False,
                "session": get_session(session_id),
            }
            return {"status": immediate["status"], "immediate_result": immediate, "session": get_session(session_id)}
        pending = _create_language_confirmation(session, historical_reference)
        evidence_note = (
            "我找到了与该关系对应的近期验真事件"
            if str(candidate["evidence_source"]).startswith("recent_verified_")
            else "我只有杯子的当前或历史承载关系，没有与“刚才放杯子”完全对应的动作记录"
        )
        immediate = {
            "status": "language_interpretation_confirmation_required",
            "reason": "historical_relational_reference_requires_minimum_confirmation",
            "prompt": (
                f"我理解你要把{candidate['theme_label']}放到一个承载面；其中历史关系描述可能指{candidate['destination_label']}。"
                f"{evidence_note}。你指的是{candidate['destination_label']}吗？"
            ),
            "language_understanding": _language_understanding_view(historical_reference),
            "historical_reference_candidate": deepcopy(candidate),
            "pending_confirmation": deepcopy(pending),
            "candidate_only": True,
            "runtime_fact_committed": False,
            "direct_execution_allowed": False,
            "session": get_session(session_id),
        }
        return {"status": immediate["status"], "immediate_result": immediate, "session": get_session(session_id)}
    gap_dialogue_collecting = (session.get("concept_gap_dialogue") or {}).get("status") == "collecting_minimum_causal_contract"
    if (
        not internal_stage
        and not scoped_authorization
        and (
            language_analysis.get("speech_act") in {"language_teaching", "prohibition"}
            or (
                language_analysis.get("decision") == "request_minimum_semantic_clarification"
                and language_analysis.get("canonical_utterance")
                and not gap_dialogue_collecting
                and not composite_water_goal
            )
        )
    ):
        immediate = execute_command(session_id, text, scoped_authorization, language_analysis)
        return {"status": immediate.get("status"), "immediate_result": immediate, "session": get_session(session_id)}
    if (
        not internal_stage
        and not scoped_authorization
        and not composite_water_goal
        and not gap_dialogue_collecting
        and language_analysis.get("decision") == "route_canonical_semantics"
        and language_analysis.get("canonical_utterance")
    ):
        text = language_analysis["canonical_utterance"]
    # A repeated request after a placement blockage is a continuation of the
    # same causal gap, not a new acquire task. Reuse only when the terminal
    # goal and both grounded roles match the active intent.
    active_intent = (session.get("long_horizon_intents") or {}).get(session.get("active_intent_id"))
    active_stage = (active_intent or {}).get("current_stage") or {}
    process_bindings = process_resolution.get("bindings") or {}
    same_blocked_place = bool(
        active_intent
        and not internal_stage
        and not scoped_authorization
        and active_intent.get("lifecycle") == "awaiting_correction"
        and active_stage.get("stage_id") == "place_at_destination"
        and active_intent.get("goal_fact") == process_resolution.get("goal_fact") == "object_supported_at_destination"
        and (process_bindings.get("theme") or {}).get("value_ref") == active_intent.get("role_bindings", {}).get("theme")
        and (process_bindings.get("destination") or {}).get("value_ref") == active_intent.get("role_bindings", {}).get("destination")
    )
    if same_blocked_place:
        active_intent["lifecycle"] = "active"
        active_intent["resume_envelope"] = None
        prepared = _prepare_long_intent_stage(session, active_intent)
        if prepared.get("immediate_result"):
            prepared["immediate_result"]["repeat_request_reused_active_gap"] = True
        prepared["session"] = get_session(session_id)
        return prepared
    same_failed_fill = bool(
        active_intent
        and not internal_stage
        and not scoped_authorization
        and active_intent.get("lifecycle") in {"awaiting_correction", "active"}
        and active_stage.get("stage_id") == "fill_container"
        and active_intent.get("goal_fact") == "human_received_filled_container"
        and "target_object_in_gripper" in active_intent.get("verified_facts", [])
        and "container_filled" not in active_intent.get("verified_facts", [])
    )
    if same_failed_fill:
        active_intent["lifecycle"] = "active"
        active_intent["resume_envelope"] = None
        prepared = _prepare_long_intent_stage(session, active_intent)
        if prepared.get("immediate_result"):
            prepared["immediate_result"]["resumed_failed_fill"] = True
        prepared["session"] = get_session(session_id)
        return prepared
    long_intent = None if internal_stage or scoped_authorization else (
        _create_water_delivery_intent(session, text, language_analysis)
        or _create_water_placement_intent(session, text, language_analysis)
        or _create_object_handover_intent(session, text, language_analysis)
        or _create_transport_intent(session, text, language_analysis)
        or _create_transfer_intent(session, text, language_analysis)
    )
    if long_intent:
        prepared = _prepare_long_intent_stage(session, long_intent)
        if prepared.get("immediate_result"):
            prepared["immediate_result"]["session"] = get_session(session_id)
        prepared["session"] = get_session(session_id)
        return prepared
    factory_groundable_task = activate_task_perception(text) is not None
    if (
        not factory_groundable_task
        and not session.get("process_gap_dialogue")
        and process_resolution.get("status") not in {"clarification_required", "unsafe_switch", "template_confirmation_required"}
        and not (session.get("concept_gap_dialogue") or {}).get("status") == "collecting_minimum_causal_contract"
    ):
        recalled = _recall_trusted_experience(text)
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
    active_intent = (session.get("long_horizon_intents") or {}).get(session.get("active_intent_id"))
    active_stage = (active_intent or {}).get("current_stage") or {}
    authorized_internal_stage = bool(
        internal_stage
        and scoped_authorization
        and scoped_authorization.get("long_intent_id") == (active_intent or {}).get("intent_id")
        and scoped_authorization.get("long_stage_id") == active_stage.get("stage_id")
    )
    service_stage_matches = bool(
        active_intent
        and active_intent.get("intent_type") in {"verified_water_delivery", "verified_water_placement", "verified_object_handover"}
        and (active_stage.get("utterance") == text or authorized_internal_stage)
        and active_stage.get("stage_id") in {"acquire_container", "fill_container", "handover_to_recipient"}
    )
    transport_region_stage_matches = bool(
        active_intent
        and active_intent.get("intent_type") == "verified_object_transport"
        and authorized_internal_stage
        and active_stage.get("stage_id") == "transport_to_region"
    )
    causal_graph_stage_matches = bool(
        active_intent
        and active_intent.get("causal_graph_runtime") is not None
        and authorized_internal_stage
        and active_stage.get("graph_node_id")
        and (active_stage.get("execution_contract") or {}).get("mode") == "motion_effect"
    )
    if internal_stage and active_intent and active_intent.get("causal_graph_runtime") is not None:
        _debug_runtime(
            "causal_graph_stage_dispatch",
            session,
            authorized_internal_stage=authorized_internal_stage,
            causal_graph_stage_matches=causal_graph_stage_matches,
            authorization_intent=(scoped_authorization or {}).get("long_intent_id"),
            authorization_stage=(scoped_authorization or {}).get("long_stage_id"),
            active_stage=active_stage.get("stage_id"),
            execution_mode=(active_stage.get("execution_contract") or {}).get("mode"),
        )
    result = (
        _execute_causal_graph_stage(session, active_intent, active_stage, scoped_authorization)
        if causal_graph_stage_matches
        else _execute_transport_region_stage(session, active_intent, active_stage, scoped_authorization)
        if transport_region_stage_matches
        else _execute_water_service_stage(session, active_intent, active_stage, scoped_authorization)
        if service_stage_matches else execute_command(
            session_id, text, scoped_authorization, language_analysis, grounded_role_bindings
        )
    )
    return _finalize_motion_result(session_id, text, before, result, scoped_authorization)


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
    if pending.get("kind") == "language_interpretation":
        if pending.get("authorized_world_revision") != session["world_revision"] or pending.get("policy_binding") != _policy_binding(session):
            _revoke_pending_confirmation(session, "language_interpretation_context_changed")
            return {
                "status": "confirmation_not_current",
                "reason": "world_or_policy_context_changed_before_language_confirmation",
                "prompt": "环境或策略已经变化，这个语言解释需要结合当前上下文重新判断。",
                "session": get_session(session_id),
            }
        analysis = deepcopy(pending.get("language_analysis") or {})
        if not approved:
            session["language_interpretation_history"].append({
                "utterance": pending.get("original_utterance"),
                "decision": "human_rejected_language_interpretation",
                "world_revision": session["world_revision"],
            })
            session["pending_confirmation"] = None
            return {
                "status": "language_interpretation_rejected",
                "reason": "human_rejected_compositional_candidate",
                "prompt": "好的，我不会采用这个解释。请指出我理解错的是动作、对象、位置还是目标结果。",
                "language_understanding": _language_understanding_view(analysis),
                "session": get_session(session_id),
            }

        definition = analysis.get("definition_candidate")
        resume_utterance = pending.get("resume_utterance")
        canonical_utterance = pending.get("utterance")
        session["pending_confirmation"] = None
        session["language_interpretation_history"].append({
            "utterance": pending.get("original_utterance"),
            "decision": "human_confirmed_language_interpretation",
            "canonical_utterance": canonical_utterance,
            "world_revision": session["world_revision"],
        })
        learned_adapter = None
        if definition:
            adapter_seed = "|".join([definition["surface_form"], definition["concept_id"], definition["operator"]])
            learned_adapter = {
                "adapter_id": "language_adapter_" + hashlib.sha1(adapter_seed.encode("utf-8")).hexdigest()[:12],
                "surface_form": definition["surface_form"],
                "concept_id": definition["concept_id"],
                "operator": definition["operator"],
                "canonical_surface": definition["canonical_surface"],
                "status": "session_confirmed",
                "scope": "current_executor_session",
                "confirmation_count": 1,
                "negative_confirmation_count": 0,
                "source": "explicit_human_language_definition",
                "modifies_concept_kernel": False,
                "runtime_fact_committed": False,
            }
            existing = next(
                (item for item in session["language_adapters"] if item.get("adapter_id") == learned_adapter["adapter_id"]),
                None,
            )
            if existing:
                existing["confirmation_count"] = int(existing.get("confirmation_count", 0)) + 1
                learned_adapter = deepcopy(existing)
            else:
                session["language_adapters"].append(deepcopy(learned_adapter))
            session["concept_gap_dialogue"] = None
        if resume_utterance:
            resumed = begin_motion_command(session_id, resume_utterance)
            resumed["language_adapter_learned"] = deepcopy(learned_adapter)
            if resumed.get("immediate_result"):
                resumed["immediate_result"]["language_adapter_learned"] = deepcopy(learned_adapter)
                resumed["immediate_result"]["prompt"] = (
                    f"我已经把“{definition['surface_form']}”作为“{definition['canonical_surface']}”的当前会话语言入口。"
                    + resumed["immediate_result"].get("prompt", "")
                )
            return resumed
        if definition:
            return {
                "status": "language_adapter_learned",
                "prompt": (
                    f"已确认：“{definition['surface_form']}”在当前教学上下文中表示“{definition['canonical_surface']}”。"
                    "它现在可以触发同一个概念核；具体执行仍要重新检查世界状态、能力和经验。"
                ),
                "language_adapter_learned": deepcopy(learned_adapter),
                "runtime_fact_committed": False,
                "session": get_session(session_id),
            }
        return begin_motion_command(session_id, canonical_utterance)
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
    if action == "fill":
        return {"action": action, "container_ref": post_completion.get("container_ref"), "source_ref": post_completion.get("source_ref")}
    if action == "handover":
        return {
            "action": action,
            "container_ref": post_completion.get("container_ref"),
            "recipient_ref": post_completion.get("recipient_ref"),
            "require_filled_container": post_completion.get("require_filled_container", True),
        }
    if action == "causal_graph_node":
        return {
            "action": action,
            "intent_id": post_completion.get("intent_id"),
            "node_id": post_completion.get("node_id"),
        }
    return {"action": action}


def _replan_state_fingerprint(
    job: dict[str, Any], session: dict[str, Any], reason: str, obstacle: dict[str, Any] | None
) -> str:
    payload = {
        "reason": reason,
        "obstacle_ref": (obstacle or {}).get("entity_id"),
        "world_revision": session.get("world_revision"),
        "policy_revision": session.get("policy_revision"),
        "executor_position": [round(float(value), 3) for value in session.get("state", {}).get("executor_position", [])],
        "execution_intent": job.get("execution_intent") or _post_completion_signature(job.get("post_completion")),
    }
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _replan_stalled_result(
    job: dict[str, Any], session: dict[str, Any], obstacle: dict[str, Any] | None, fingerprint: str
) -> dict[str, Any]:
    intent = (session.get("long_horizon_intents") or {}).get(job.get("long_intent_id"))
    if intent:
        intent["lifecycle"] = "awaiting_correction"
        intent["resume_envelope"] = {
            "reason": "identical_replan_state_recurred_without_new_information",
            "world_revision": session["world_revision"],
            "current_stage": deepcopy(intent.get("current_stage")),
            "old_path_discarded": True,
        }
    result = {
        "status": "replanning_stalled_by_persistent_constraint",
        "reason": "identical_replan_state_recurred_without_new_information",
        "prompt": (
            f"我在同一世界状态和同一位置反复遇到{(obstacle or {}).get('label') or '相同约束'}；"
            "继续重新规划不会产生新路径。我已保留整体目标并停止局部运动，请移除障碍、改变目标约束，或告诉我是否改走其他区域。"
        ),
        "blocking_obstacle": deepcopy(obstacle),
        "original_execution_intent": deepcopy(job.get("execution_intent")),
        "replan_convergence": {
            "fingerprint": fingerprint,
            "identical_state_count": 3,
            "new_world_information_observed": False,
            "trajectory_persisted": False,
            "intent_preserved": bool(intent),
        },
        "long_horizon_intent": _long_intent_view(intent) if intent else None,
        "frames": [],
        "session": get_session(job["session_id"]),
    }
    return {"status": "motion_completed", "job_id": job["job_id"], "result": result, "session": result["session"]}


def _resume_after_local_path_change(job: dict[str, Any], session: dict[str, Any], reason: str, obstacle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Replan geometry while preserving a verified task intent, never a stale trajectory."""
    original_intent = deepcopy(job.get("execution_intent") or _post_completion_signature(job.get("post_completion")))
    fingerprint = _replan_state_fingerprint(job, session, reason, obstacle)
    replan_history = list(job.get("replan_state_history", [])) + [fingerprint]
    if len(replan_history) >= 3 and len(set(replan_history[-3:])) == 1:
        return _replan_stalled_result(job, session, obstacle, fingerprint)
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
        # A route is disposable, but its membership in a verified long-horizon
        # stage is not. Preserve only symbolic ownership; no stale geometry or
        # frame is copied into the replacement job.
        for context_key in ("long_intent_id", "long_stage_id"):
            if job.get(context_key):
                replacement_job[context_key] = job[context_key]
        replacement_job["replan_state_history"] = replan_history[-8:]
        replacement["continuation_status"] = "same_intent_reobserved_and_replanned"
        replacement["preserved_execution_intent"] = original_intent
        replacement["preserved_long_horizon_context"] = {
            "long_intent_id": replacement_job.get("long_intent_id"),
            "long_stage_id": replacement_job.get("long_stage_id"),
            "trajectory_preserved": False,
        }
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
    post_completion = job.get("post_completion") or {}
    terminal_relation_failed = result.get("status") == "terminal_fact_verification_failed"
    if terminal_relation_failed and post_completion.get("action"):
        result["effect_contract_committed"] = False
        result["effect_commit_blocked_reason"] = "terminal_spatial_relation_not_verified"
    elif post_completion.get("action") == "grasp" and post_completion.get("mode") == "direct_task":
        grasp = _apply_verified_grasp(session, job["post_completion"]["target_entity_ref"], "human_confirmed_candidate_task")
        if grasp.get("status") == "fact_established":
            result.update(grasp)
            result["status"] = "fact_established"
            result["execution_chain"] = ["confirmed_target_binding", "route_replanned_from_current_state", "executor_within_grasp_reach", "grasp_physically_verified"]
        else:
            result = grasp
    elif post_completion.get("action") == "place" and post_completion.get("mode") == "direct_task":
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
    elif post_completion.get("action") == "fill":
        fill = _apply_verified_fill(
            session,
            job["post_completion"]["container_ref"],
            job["post_completion"]["source_ref"],
            "human_confirmed_water_service_stage",
        )
        result.update(fill)
    elif post_completion.get("action") == "handover":
        handover = _apply_verified_handover(
            session,
            job["post_completion"]["container_ref"],
            job["post_completion"]["recipient_ref"],
            "human_confirmed_water_service_stage",
            require_filled_container=job["post_completion"].get("require_filled_container", True),
        )
        result.update(handover)
    elif post_completion.get("action") == "causal_graph_node":
        graph_intent = (session.get("long_horizon_intents") or {}).get(
            post_completion.get("intent_id")
        )
        graph_node = next(
            (
                node for node in (graph_intent or {}).get("task_graph", {}).get("nodes", [])
                if node.get("node_id") == post_completion.get("node_id")
            ),
            None,
        )
        if not graph_intent or not graph_node:
            result.update({
                "status": "causal_graph_node_effect_failed",
                "reason": "active_graph_intent_or_node_not_found_at_commit_time",
                "effect_contract_committed": False,
            })
        else:
            result.update(_apply_causal_graph_node_effects(session, graph_intent, graph_node))
    elif post_completion.get("action") == "grasp":
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
            terminal_fact = result.get("terminal_fact")
            established_facts = list(result.get("established_facts", []))
            if terminal_fact:
                established_facts.append(terminal_fact)
            for established_fact in dict.fromkeys(established_facts):
                if established_fact and established_fact not in intent["verified_facts"]:
                    intent["verified_facts"].append(established_fact)
            graph = intent.get("hierarchical_intent_graph")
            stage_target_fact = (intent.get("current_stage") or {}).get("target_fact")
            if stage_target_fact and stage_target_fact not in intent["verified_facts"]:
                # The executor may report a lower-level physical fact (for
                # example object_supported_at_destination) while the active
                # stage names the composed goal fact. Promote both into the
                # current task ledger before deriving the next stage.
                intent["verified_facts"].append(stage_target_fact)
            if graph:
                if terminal_fact:
                    record_intent_verified_fact(graph, terminal_fact)
                if stage_target_fact:
                    record_intent_verified_fact(graph, stage_target_fact)
            stage_outcome = (
                _prepare_long_intent_stage(session, intent)
                if result.get("status") not in {"terminal_fact_verification_failed", "awaiting_correction", "failed"}
                else {
                    "status": "awaiting_correction",
                    "long_horizon_intent": _long_intent_view(intent),
                    "immediate_result": None,
                }
            )
            result["long_horizon_intent"] = stage_outcome.get("long_horizon_intent", _long_intent_view(intent))
            if stage_outcome.get("status") == "long_intent_completed":
                result.pop("candidate_execution_plan", None)
                result.pop("next_stage_candidate", None)
                result.pop("pending_confirmation", None)
                result["execution_plan_state"] = "released_on_task_completion"
                result["prompt"] = "当前阶段已验真，长程目标的终止事实也已成立。"
                compound_next = stage_outcome.get("compound_next_started") or {}
                if compound_next.get("job_id"):
                    result["next_stage_started"] = {
                        "status": compound_next.get("status"),
                        "job_id": compound_next["job_id"],
                        "frame_count": compound_next.get("frame_count"),
                        "long_stage": deepcopy(compound_next.get("long_stage")),
                        "long_horizon_intent": deepcopy(compound_next.get("long_horizon_intent")),
                        "candidate_execution_plan": deepcopy(compound_next.get("candidate_execution_plan")),
                        "compound_command_sequence": deepcopy(compound_next.get("compound_command_sequence")),
                    }
                    result["long_horizon_intent"] = deepcopy(
                        compound_next.get("long_horizon_intent")
                    ) or result["long_horizon_intent"]
                    result["candidate_execution_plan"] = deepcopy(
                        compound_next.get("candidate_execution_plan")
                    )
                    result["compound_command_sequence"] = deepcopy(
                        compound_next.get("compound_command_sequence")
                    )
                    result["prompt"] = (
                        "前一子目标已通过物理验真；我已释放它的执行细节，"
                        "并按最新世界状态开始复合任务的下一子目标。"
                    )
                elif compound_next:
                    result["compound_command_sequence"] = deepcopy(
                        compound_next.get("compound_command_sequence")
                    )
                    immediate_next = compound_next.get("immediate_result")
                    if immediate_next:
                        result["next_stage_candidate"] = deepcopy(immediate_next)
                        result["prompt"] = immediate_next.get("prompt") or result["prompt"]
            elif stage_outcome.get("job_id"):
                next_stage_plan = deepcopy(stage_outcome.get("candidate_execution_plan"))
                result["next_stage_started"] = {
                    "status": stage_outcome.get("status"),
                    "job_id": stage_outcome["job_id"],
                    "frame_count": stage_outcome.get("frame_count"),
                    "long_stage": deepcopy(stage_outcome.get("long_stage")),
                    "long_horizon_intent": deepcopy(stage_outcome.get("long_horizon_intent")),
                    "candidate_execution_plan": next_stage_plan,
                }
                if next_stage_plan:
                    result["candidate_execution_plan"] = next_stage_plan
                result["prompt"] = (
                    "当前阶段已通过物理验真；原任务级授权仍然有效，我已按最新世界状态直接开始下一阶段。"
                )
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
    if (result.get("long_horizon_intent") or {}).get("lifecycle") != "completed":
        session["event_history"].append({"utterance": job["utterance"], "result": result.get("status"), "route_kind": result.get("route_kind")})
    return {"status": "motion_completed", "job_id": job_id, "frame": frame, "result": result, "session": get_session(job["session_id"])}


def _first_collision(
    session: dict[str, Any], start: list[float], target: list[float], radius: float, scene: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    scene = scene or _scene_for_session(session)
    distance = math.dist(start, target)
    analytic_contacts: list[tuple[float, dict[str, Any]]] = []
    for item in scene["objects"]:
        if not item.get("fixed"):
            continue
        ox, oy = map(float, item["position"])
        sx, sy = map(float, item["size"][:2])
        entry = _segment_aabb_entry_fraction(
            start,
            target,
            ox - sx / 2 - radius,
            ox + sx / 2 + radius,
            oy - sy / 2 - radius,
            oy + sy / 2 + radius,
        )
        if entry is not None:
            analytic_contacts.append((entry, {**deepcopy(item), "obstacle_class": "fixed_furniture", "fixed": True}))
    for obstacle in session["active_obstacles"]:
        entry = _segment_circle_entry_fraction(
            start,
            target,
            list(map(float, obstacle["position"])),
            radius + 0.38,
        )
        if entry is not None:
            analytic_contacts.append((entry, {**deepcopy(obstacle), "label": "凳子", "obstacle_class": "movable_obstacle", "fixed": False}))
    if analytic_contacts:
        entry, obstacle = min(analytic_contacts, key=lambda value: value[0])
        clearance_fraction = min(entry, 0.003 / max(distance, 0.003))
        safe_ratio = max(0.0, entry - clearance_fraction)
        contact_position = [
            start[0] + (target[0] - start[0]) * entry,
            start[1] + (target[1] - start[1]) * entry,
        ]
        safe_position = [
            start[0] + (target[0] - start[0]) * safe_ratio,
            start[1] + (target[1] - start[1]) * safe_ratio,
        ]
        return {
            "obstacle": obstacle,
            "contact_position": contact_position,
            "safe_position": safe_position,
            "detector": "analytic_segment_expanded_aabb_intersection",
        }
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


def _segment_aabb_entry_fraction(
    start: list[float],
    target: list[float],
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
) -> float | None:
    """Return the first segment fraction entering an axis-aligned box."""
    entry, exit_fraction = 0.0, 1.0
    for origin, delta, lower, upper in (
        (float(start[0]), float(target[0]) - float(start[0]), min_x, max_x),
        (float(start[1]), float(target[1]) - float(start[1]), min_y, max_y),
    ):
        if abs(delta) < 1e-12:
            if origin < lower or origin > upper:
                return None
            continue
        first = (lower - origin) / delta
        second = (upper - origin) / delta
        if first > second:
            first, second = second, first
        entry = max(entry, first)
        exit_fraction = min(exit_fraction, second)
        if entry > exit_fraction:
            return None
    if exit_fraction < 0.0 or entry > 1.0:
        return None
    return max(0.0, entry)


def _segment_circle_entry_fraction(
    start: list[float], target: list[float], center: list[float], radius: float
) -> float | None:
    dx = float(target[0]) - float(start[0])
    dy = float(target[1]) - float(start[1])
    fx = float(start[0]) - float(center[0])
    fy = float(start[1]) - float(center[1])
    a = dx * dx + dy * dy
    c = fx * fx + fy * fy - radius * radius
    if c <= 0.0:
        return 0.0
    if a <= 1e-18:
        return None
    b = 2.0 * (fx * dx + fy * dy)
    discriminant = b * b - 4.0 * a * c
    if discriminant < 0.0:
        return None
    root = math.sqrt(discriminant)
    entry = (-b - root) / (2.0 * a)
    exit_fraction = (-b + root) / (2.0 * a)
    if exit_fraction < 0.0 or entry > 1.0:
        return None
    return max(0.0, entry)


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
    if obstacle.get("obstacle_class") == "scene_boundary" or obstacle.get("mode") == "narrow":
        return {"outcome": "blocked", "route_kind": "none", "blocking_collision": direct_collision, "safety_contract": safety_contract}
    if obstacle.get("obstacle_class") == "fixed_furniture":
        global_route = _global_collision_free_route(session, start, target, radius)
        if global_route:
            safety_contract["terminal_pose_verified"] = True
            return {
                "outcome": "verified", "route_kind": "current_map_shortest_path", "waypoints": global_route,
                "blocking_collision": direct_collision, "safety_contract": safety_contract,
            }
        return {"outcome": "blocked", "route_kind": "none", "blocking_collision": direct_collision, "safety_contract": safety_contract}
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for side_name, side_sign in (("left", 1.0), ("right", -1.0)):
        template_waypoints = _detour_candidate(start, target, obstacle, radius, side_sign, preserve_terminal_goal)
        waypoints = _simplify_collision_free_waypoints(session, start, template_waypoints, radius)
        if not waypoints:
            rejected.append({"side": side_name, "reason": "no_collision_free_bridge_to_detour_waypoints"})
            continue
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
        candidates.append({
            "side": side_name,
            "waypoints": waypoints,
            "route_length": route_length,
            "template_waypoint_count": len(template_waypoints),
            "simplified_waypoint_count": len(waypoints),
        })
    if not candidates:
        global_route = _global_collision_free_route(session, start, target, radius)
        if global_route:
            safety_contract["terminal_pose_verified"] = True
            return {
                "outcome": "verified", "route_kind": "current_map_shortest_path", "waypoints": global_route,
                "blocking_collision": direct_collision, "rejected_alternatives": rejected, "safety_contract": safety_contract,
            }
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
        "template_waypoint_count": selected["template_waypoint_count"],
        "simplified_waypoint_count": selected["simplified_waypoint_count"],
        "rejected_alternatives": rejected,
        "blocking_collision": direct_collision,
        "safety_contract": safety_contract,
    }


def _global_collision_free_route(
    session: dict[str, Any], start: list[float], target: list[float], radius: float, resolution: float = 0.18
) -> list[list[float]] | None:
    """Plan over the current collision map; the resulting geometry is transient."""
    min_x, max_x = -5.0 + radius, 5.0 - radius
    min_y, max_y = -2.3 + radius, 2.3 - radius
    cols = int((max_x - min_x) / resolution) + 1
    rows = int((max_y - min_y) / resolution) + 1

    def point(node: tuple[int, int]) -> list[float]:
        return [min_x + node[0] * resolution, min_y + node[1] * resolution]

    scene = _scene_for_session(session)
    clear_nodes = {
        (ix, iy)
        for ix in range(cols)
        for iy in range(rows)
        if _collider_at(point((ix, iy)), radius, session, scene) is None
    }
    start_candidates = sorted(clear_nodes, key=lambda node: math.dist(start, point(node)))
    goal_candidates = sorted(clear_nodes, key=lambda node: math.dist(target, point(node)))
    start_node = next((node for node in start_candidates[:20] if _first_collision(session, start, point(node), radius, scene) is None), None)
    goal_nodes = {
        node for node in goal_candidates[:32]
        if math.dist(target, point(node)) <= resolution * 2.2 and _first_collision(session, point(node), target, radius, scene) is None
    }
    if start_node is None or not goal_nodes:
        return None
    frontier: list[tuple[float, float, tuple[int, int]]] = [(0.0, 0.0, start_node)]
    cost = {start_node: 0.0}
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    reached = None
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
    while frontier:
        _, current_cost, current = heapq.heappop(frontier)
        if current_cost > cost.get(current, math.inf):
            continue
        if current in goal_nodes:
            reached = current
            break
        current_point = point(current)
        for dx, dy in directions:
            neighbor = (current[0] + dx, current[1] + dy)
            if neighbor not in clear_nodes:
                continue
            neighbor_point = point(neighbor)
            if _first_collision(session, current_point, neighbor_point, radius, scene):
                continue
            step_cost = math.hypot(dx, dy) * resolution
            new_cost = current_cost + step_cost
            if new_cost >= cost.get(neighbor, math.inf):
                continue
            cost[neighbor] = new_cost
            came_from[neighbor] = current
            heuristic = min(math.dist(neighbor_point, point(goal)) for goal in goal_nodes)
            heapq.heappush(frontier, (new_cost + heuristic, new_cost, neighbor))
    if reached is None:
        return None
    nodes = [reached]
    while nodes[-1] != start_node:
        nodes.append(came_from[nodes[-1]])
    nodes.reverse()
    # Keep the verified bridge from the continuous start pose onto the grid.
    # Omitting start_node can make the first returned grid neighbor unreachable
    # even though A* itself found a valid route from start_node onward.
    raw = [point(start_node)] + [point(node) for node in nodes[1:]] + [list(target)]
    simplified = _simplify_collision_free_waypoints(session, start, raw, radius)
    if not simplified:
        return None
    segment_start = start
    for waypoint in simplified:
        if _first_collision(session, segment_start, waypoint, radius, scene):
            return None
        segment_start = waypoint
    return simplified


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
                **deepcopy(item),
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


def _simplify_collision_free_waypoints(
    session: dict[str, Any],
    start: list[float],
    template_waypoints: list[list[float]],
    radius: float,
) -> list[list[float]]:
    """Retain only detour corners that cannot be replaced by a direct safe segment."""
    simplified: list[list[float]] = []
    anchor = list(start)
    index = 0
    while index < len(template_waypoints):
        furthest = None
        for candidate_index in range(len(template_waypoints) - 1, index - 1, -1):
            candidate = template_waypoints[candidate_index]
            if _first_collision(session, anchor, candidate, radius) is None:
                furthest = candidate_index
                break
        if furthest is None:
            return []
        waypoint = list(template_waypoints[furthest])
        simplified.append(waypoint)
        anchor = waypoint
        index = furthest + 1
    return simplified


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
