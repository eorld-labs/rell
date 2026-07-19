from __future__ import annotations

from concept_core.context_projection import build_context_projection, compact_intent_capsule


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    objects = [
        {"entity_id": "vessel_x", "kind": "unfamiliar_vessel", "active": True},
        {"entity_id": "holder_x", "kind": "human_recipient", "active": True},
        {"entity_id": "unrelated_x", "kind": "unrelated_asset", "active": True},
    ]
    current_facts = [
        {"predicate": "received_by", "subject": "vessel_x", "object": "holder_x", "evidence": "runtime_verified", "world_revision": 7},
        {"predicate": "supported_by", "subject": "unrelated_x", "object": "surface_x", "evidence": "runtime_verified", "world_revision": 7},
        {"predicate": "executor_in_region", "subject": "executor", "object": "room_x", "evidence": "runtime_verified", "world_revision": 7},
    ]
    language = {
        "speech_act": "task_request",
        "event_candidates": [{"operator": "grasp_object"}],
        "role_bindings": {
            "theme": {"entity_ref": "vessel_x", "compatible_kinds": ["unfamiliar_vessel"]}
        },
        "discourse_roles": {
            "source_holder": {"reference": "human_speaker"}
        },
        "entity_mentions": [],
    }
    intent = {
        "intent_id": "intent_x",
        "intent_type": "unfamiliar_delivery",
        "goal_fact": "holder_received_vessel",
        "lifecycle": "active",
        "role_bindings": {"theme": "vessel_x", "recipient": "holder_x"},
        "verified_facts": ["vessel_grounded"],
        "current_stage": {"stage_id": "acquire", "target_fact": "vessel_in_effector", "candidate_plan": ["raw_step"]},
        "hierarchical_intent_graph": {"nodes": {"raw": {}}},
        "candidate_execution_plan": ["raw_step"],
    }
    episodes = [
        {
            "episode_id": "episode_irrelevant",
            "operator": "place_object",
            "participants": {"theme": "unrelated_x"},
            "before_facts": [],
            "produces": [{"predicate": "supported_by", "subject": "unrelated_x", "object": "surface_x"}],
            "destroys": [],
            "world_revision": 6,
            "raw_trajectory": [[0, 0], [1, 1]],
        },
        {
            "episode_id": "episode_relevant",
            "operator": "grasp_object",
            "participants": {"theme": "vessel_x", "source_holder": "holder_x"},
            "before_facts": [{"predicate": "received_by", "subject": "vessel_x", "object": "holder_x"}],
            "produces": [{"predicate": "held_by", "subject": "vessel_x", "object": "left_hand"}],
            "destroys": [{"predicate": "received_by", "subject": "vessel_x", "object": "holder_x"}],
            "world_revision": 6,
            "verification_basis": "contact_plus_following",
            "raw_trajectory": [[0, 0], [1, 1]],
        },
    ]
    projection = build_context_projection(
        language,
        runtime_objects=objects,
        current_facts=current_facts,
        active_intent=intent,
        recent_episodes=episodes,
        recent_intent_capsules=[],
        interaction_role_bindings={"human_speaker": "holder_x"},
        dialogue_focus_entities=[
            {"entity_ref": "unrelated_x", "world_revision": 7, "expires_after_turn": 2}
        ],
        world_revision=7,
        current_turn=5,
    )
    require(any(item["predicate"] == "received_by" for item in projection["current_world_facts"]), f"current relation was omitted: {projection}")
    require(not any(item.get("subject") == "unrelated_x" for item in projection["current_world_facts"]), f"unrelated world detail leaked into projection: {projection}")
    require([item["episode_id"] for item in projection["recent_episode_capsules"]] == ["episode_relevant"], f"episode relevance projection failed: {projection}")
    require("raw_trajectory" not in projection["recent_episode_capsules"][0], f"raw episode detail survived compaction: {projection}")
    require(projection["active_task_summary"]["candidate_plan_included"] is False and "hierarchical_intent_graph" not in projection["active_task_summary"], f"active task summary retained mechanics: {projection}")
    require(projection["dialogue_focus_refs"] == [], f"expired discourse focus remained active: {projection}")
    require(projection.get("relational_role_candidates", {}).get("theme", [])[0].get("entity_ref") == "vessel_x", f"current holder relation did not produce a generic role candidate: {projection}")

    repeat_projection = build_context_projection(
        {
            "normalized_utterance": "再处理一个",
            "role_bindings": {},
            "entity_mentions": [],
            "event_candidates": [],
        },
        runtime_objects=objects,
        current_facts=current_facts,
        active_intent=None,
        recent_episodes=episodes,
        recent_intent_capsules=[{
            "intent_id": "completed_x",
            "intent_type": "unfamiliar_delivery",
            "goal_fact": "holder_received_vessel",
            "role_bindings": {"theme": "stale_object_x"},
            "verified_facts": ["stale_terminal_fact"],
            "lifecycle": "completed",
            "closed_world_revision": 6,
        }],
        interaction_role_bindings={"human_speaker": "holder_x"},
        dialogue_focus_entities=[],
        world_revision=7,
        current_turn=6,
    )
    repeated_goal = repeat_projection["recent_goal_capsules"][0]
    require(repeated_goal["goal_fact"] == "holder_received_vessel", f"recent goal schema was not projected for ellipsis: {repeat_projection}")
    require("role_bindings" not in repeated_goal and "verified_facts" not in repeated_goal, f"recent goal projection reused stale task details: {repeat_projection}")
    require(repeated_goal["prior_role_bindings_reused"] is False and repeated_goal["prior_verified_facts_reused"] is False, f"goal-schema reuse boundary missing: {repeat_projection}")

    capsule = compact_intent_capsule(
        intent,
        world_revision=7,
        lifecycle="completed",
        release_reason="goal_verified",
    )
    require(capsule["stage_graph_retained"] is False and capsule["task_verified_fact_ledger_retained"] is False, f"intent mechanics survived release: {capsule}")
    require("verified_facts" not in capsule and "hierarchical_intent_graph" not in capsule and "candidate_execution_plan" not in capsule, f"released intent capsule retained detailed state: {capsule}")
    print({
        "status": "passed",
        "current_fact_count": len(projection["current_world_facts"]),
        "episode_capsules": [item["episode_id"] for item in projection["recent_episode_capsules"]],
        "recent_goal_schema": repeated_goal["goal_fact"],
        "task_snapshot_released": True,
    })


if __name__ == "__main__":
    main()
