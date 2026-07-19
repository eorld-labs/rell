from __future__ import annotations

from copy import deepcopy
from typing import Any


EVIDENCE_PRECEDENCE = [
    "current_physically_verified_relation",
    "explicit_current_language_constraint",
    "active_task_role_binding",
    "recent_verified_episode_capsule",
    "persistent_concept_or_preference",
    "unconstrained_category_candidate",
]


def compact_intent_capsule(
    intent: dict[str, Any],
    *,
    world_revision: int,
    lifecycle: str,
    release_reason: str,
) -> dict[str, Any]:
    """Retain a goal-level episode without retaining short-task machinery."""
    return {
        "schema_version": "1.0.0",
        "intent_id": intent.get("intent_id"),
        "intent_type": intent.get("intent_type"),
        "goal_fact": intent.get("goal_fact"),
        "role_bindings": deepcopy(intent.get("role_bindings", {})),
        "lifecycle": lifecycle,
        "closed_world_revision": world_revision,
        "release_reason": release_reason,
        "arbitration_eligible": False,
        "snapshot_state": "released_from_active_arbitration",
        "trajectory_persisted": False,
        "candidate_plans_retained": False,
        "stage_graph_retained": False,
        "task_verified_fact_ledger_retained": False,
        "physical_effects_remain_in_current_world": True,
        "usable_as_current_world_state": False,
        "reference_scope": "current_world_session_only",
        "invalid_after_world_revision_change": True,
    }


def compact_episode_capsule(episode: dict[str, Any]) -> dict[str, Any]:
    transitions = []
    for phase in ("before_facts", "produces", "destroys"):
        for fact in episode.get(phase, []):
            transitions.append({
                "phase": phase,
                "predicate": fact.get("predicate"),
                "subject": fact.get("subject"),
                "object": fact.get("object"),
            })
    return {
        "episode_id": episode.get("episode_id"),
        "operator": episode.get("operator"),
        "participants": deepcopy(episode.get("participants", {})),
        "transitions": transitions,
        "world_revision": episode.get("world_revision"),
        "verification_basis": episode.get("verification_basis"),
        "usable_as_current_world_state": False,
        "raw_trajectory_persisted": False,
    }


def build_context_projection(
    language_analysis: dict[str, Any],
    *,
    runtime_objects: list[dict[str, Any]],
    current_facts: list[dict[str, Any]],
    active_intent: dict[str, Any] | None,
    recent_episodes: list[dict[str, Any]],
    dialogue_focus_entities: list[dict[str, Any]],
    world_revision: int,
    current_turn: int,
    maximum_current_facts: int = 24,
    maximum_episode_capsules: int = 4,
) -> dict[str, Any]:
    """Compile the smallest evidence-ranked context needed by one input."""
    runtime_index = {
        item.get("entity_id"): item
        for item in runtime_objects
        if item.get("entity_id") and item.get("active") is not False
    }
    roles = language_analysis.get("role_bindings") or {}
    semantic_items = [
        item
        for item in [*roles.values(), *language_analysis.get("entity_mentions", [])]
        if isinstance(item, dict)
    ]
    mentioned_refs = {
        item.get("entity_ref") for item in semantic_items if item.get("entity_ref")
    }
    compatible_kinds = {
        kind
        for item in semantic_items
        for kind in item.get("compatible_kinds", [])
    }
    active_roles = list((active_intent or {}).get("role_bindings", {}).values())
    active_refs = {ref for ref in active_roles if isinstance(ref, str)}
    focus_refs = {
        item.get("entity_ref")
        for item in dialogue_focus_entities
        if item.get("entity_ref")
        and int(item.get("expires_after_turn", current_turn)) >= current_turn
        and item.get("world_revision", world_revision) == world_revision
    }
    relevant_refs = set(mentioned_refs) | active_refs | focus_refs
    relevant_refs.update({
        ref
        for ref, entity in runtime_index.items()
        if compatible_kinds and entity.get("kind") in compatible_kinds
    })

    projected_facts = []
    for fact in current_facts:
        subject = fact.get("subject")
        obj = fact.get("object")
        if (
            subject == "executor"
            or not relevant_refs
            or subject in relevant_refs
            or obj in relevant_refs
            or (
                fact.get("predicate") in {"held_by", "received_by"}
                and subject in runtime_index
                and (not compatible_kinds or runtime_index[subject].get("kind") in compatible_kinds)
            )
        ):
            projected_facts.append(deepcopy(fact))
    projected_facts = projected_facts[:maximum_current_facts]

    requested_operators = {
        item.get("operator")
        for item in language_analysis.get("event_candidates", [])
        if item.get("operator")
    }
    relevant_episodes = []
    for episode in reversed(recent_episodes):
        participant_refs = {
            ref
            for value in (episode.get("participants") or {}).values()
            for ref in (value if isinstance(value, list) else [value])
            if isinstance(ref, str)
        }
        fact_refs = {
            value
            for phase in ("before_facts", "produces", "destroys")
            for fact in episode.get(phase, [])
            for value in (fact.get("subject"), fact.get("object"))
            if isinstance(value, str)
        }
        if (
            episode.get("operator") in requested_operators
            or bool((participant_refs | fact_refs) & relevant_refs)
        ):
            relevant_episodes.append(compact_episode_capsule(episode))
        if len(relevant_episodes) >= maximum_episode_capsules:
            break
    relevant_episodes.reverse()

    active_task_summary = None
    if active_intent and active_intent.get("lifecycle") in {
        "active", "awaiting_correction", "suspended", "awaiting_rebinding"
    }:
        stage = active_intent.get("current_stage") or {}
        active_task_summary = {
            "intent_id": active_intent.get("intent_id"),
            "intent_type": active_intent.get("intent_type"),
            "goal_fact": active_intent.get("goal_fact"),
            "lifecycle": active_intent.get("lifecycle"),
            "role_bindings": deepcopy(active_intent.get("role_bindings", {})),
            "verified_facts": list(active_intent.get("verified_facts", [])),
            "current_stage": {
                "stage_id": stage.get("stage_id"),
                "target_fact": stage.get("target_fact"),
            } if stage else None,
            "candidate_plan_included": False,
            "trajectory_included": False,
        }

    return {
        "schema_version": "1.0.0",
        "world_revision": world_revision,
        "interaction_turn": current_turn,
        "evidence_precedence": list(EVIDENCE_PRECEDENCE),
        "current_world_facts": projected_facts,
        "active_task_summary": active_task_summary,
        "recent_episode_capsules": relevant_episodes,
        "dialogue_focus_refs": sorted(ref for ref in focus_refs if ref),
        "retention_contract": {
            "current_world_relations_are_authoritative": True,
            "episode_capsules_are_not_current_facts": True,
            "completed_task_snapshots_are_not_projected": True,
            "raw_transcript_included": False,
            "candidate_plans_included": False,
            "trajectories_included": False,
        },
    }


__all__ = [
    "EVIDENCE_PRECEDENCE",
    "build_context_projection",
    "compact_episode_capsule",
    "compact_intent_capsule",
]
