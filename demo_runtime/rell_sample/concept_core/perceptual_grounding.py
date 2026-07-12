from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any


CONCEPT_FILE = Path(__file__).resolve().parents[1] / "data" / "embodied_object_concepts.json"


def load_object_concepts() -> dict[str, Any]:
    return json.loads(CONCEPT_FILE.read_text(encoding="utf-8"))


def activate_task_perception(utterance: str) -> dict[str, Any] | None:
    text = utterance.strip()
    library = load_object_concepts()
    pickup_requested = any(token in text for token in ("拿", "取", "抓"))
    matched = []
    for concept in library["concepts"]:
        aliases = [alias for alias in concept["aliases"] if alias in text]
        if aliases:
            matched.append({**deepcopy(concept), "activation_reason": "explicit_task_mention", "matched_aliases": aliases})
    target_candidates = [item for item in matched if "graspable" in item.get("functional_affordances", [])]
    if not pickup_requested or not target_candidates:
        return None
    target = target_candidates[0]
    supports = [item for item in matched if "support_object" in item.get("functional_affordances", [])]
    support = supports[0] if supports else None
    activated = [target] + ([support] if support else [])
    return {
        "task_utterance": text,
        "action_concept": "concept_pick_up_object",
        "target_concept_id": target["concept_id"],
        "support_concept_id": support["concept_id"] if support else None,
        "activated_concepts": activated,
        "requested_relations": ["target_on_top_of_support"] if support else [],
        "safety_channels_always_on": deepcopy(library["safety_channels_always_on"]),
        "candidate_only": True,
        "direct_execution_allowed": False,
        "must_reenter_orchestration_layer": True,
    }


def simulate_task_conditioned_observation(
    scene: dict[str, Any],
    session: dict[str, Any],
    activation: dict[str, Any],
) -> dict[str, Any]:
    """Simulate a sensor adapter. Only its DTO is allowed into concept grounding."""
    concepts = {item["concept_id"]: item for item in activation["activated_concepts"]}
    requested_kinds = {
        kind
        for concept in concepts.values()
        for kind in concept.get("compatible_kinds", [])
    }
    session_state = session["state"]
    executor_position = session_state["executor_position"]
    yaw = math.radians(float(session_state["executor_yaw_deg"]))
    sensor_range_m = 8.5
    half_fov_rad = math.radians(70.0)
    raw_tracks = []
    semantically_suppressed = []
    for item in scene["objects"]:
        if item.get("active") is False:
            continue
        dx = item["position"][0] - executor_position[0]
        dy = item["position"][1] - executor_position[1]
        distance = math.hypot(dx, dy)
        angle = abs(math.atan2(math.sin(math.atan2(dy, dx) - yaw), math.cos(math.atan2(dy, dx) - yaw)))
        raw_visible = distance <= sensor_range_m and angle <= half_fov_rad
        if not raw_visible:
            continue
        if item["kind"] not in requested_kinds:
            semantically_suppressed.append({"track_id": _track_id(item["entity_id"]), "reason": "not_required_by_active_task_concepts"})
            continue
        compatible = [
            concept
            for concept in concepts.values()
            if item["kind"] in concept.get("compatible_kinds", [])
        ]
        if not compatible:
            continue
        concept = compatible[0]
        raw_tracks.append(
            {
                "track_id": _track_id(item["entity_id"]),
                "spatial_entity_candidate_ref": item["entity_id"],
                "label_hint": item["label"],
                "candidate_concept_id": concept["concept_id"],
                "classification_confidence": 0.94,
                "estimated_position": deepcopy(item["position"]),
                "estimated_base_elevation_m": float(item.get("elevation_m", 0.0)),
                "estimated_size": deepcopy(item["size"]),
                "observed_invariants": deepcopy(concept["perceptual_invariants"]),
                "observation_source": "simulated_rgbd_adapter_without_reasoner_scene_access",
            }
        )
    relations = _estimate_support_relations(raw_tracks)
    safety_observations = [
        {
            "entity_candidate_ref": item["entity_id"],
            "kind": "dynamic_obstacle",
            "estimated_position": deepcopy(item["position"]),
            "semantic_task_relevance": "safety_always_on",
        }
        for item in session.get("active_obstacles", [])
        if math.dist(executor_position, item["position"]) <= sensor_range_m
    ]
    return {
        "observation_id": "obs_" + hashlib.sha1(
            f"{activation['task_utterance']}|{executor_position}|{session_state['executor_yaw_deg']}|{session['world_revision']}".encode("utf-8")
        ).hexdigest()[:12],
        "sensor_contract": {
            "sensor_type": "simulated_rgbd",
            "range_m": sensor_range_m,
            "horizontal_fov_deg": 140.0,
            "reasoner_scene_truth_access": False,
        },
        "semantic_candidates": raw_tracks,
        "relation_candidates": relations,
        "semantically_suppressed_tracks": semantically_suppressed,
        "safety_observations": safety_observations,
        "safety_channels_always_on": deepcopy(activation["safety_channels_always_on"]),
    }


def ground_task_observations(activation: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    """Ground only from the sensor DTO and concept contract; scene truth is unavailable here."""
    by_concept: dict[str, list[dict[str, Any]]] = {}
    for item in observation["semantic_candidates"]:
        by_concept.setdefault(item["candidate_concept_id"], []).append(item)
    target_candidates = by_concept.get(activation["target_concept_id"], [])
    support_candidates = by_concept.get(activation.get("support_concept_id"), []) if activation.get("support_concept_id") else []
    support_required = bool(activation.get("support_concept_id"))
    ambiguity = len(target_candidates) != 1 or (support_required and len(support_candidates) != 1)
    relation_evidence = None
    if not ambiguity and support_candidates:
        target_track = target_candidates[0]["track_id"]
        support_track = support_candidates[0]["track_id"]
        relation_evidence = next(
            (
                item
                for item in observation["relation_candidates"]
                if item["subject_track_id"] == target_track
                and item["object_track_id"] == support_track
                and item["relation"] == "on_top_of"
            ),
            None,
        )
    relation_satisfied = not activation["requested_relations"] or relation_evidence is not None
    grounded = bool(not ambiguity and target_candidates and relation_satisfied)
    bindings = []
    if grounded:
        bindings.append(_binding("target", target_candidates[0], observation["observation_id"]))
        if support_candidates:
            bindings.append(_binding("support", support_candidates[0], observation["observation_id"]))
    return {
        "grounding_status": "spatially_grounded" if grounded else "perceptual_candidate",
        "candidate_bindings": bindings,
        "relation_evidence": relation_evidence,
        "ambiguity": ambiguity,
        "candidate_only": True,
        "direct_execution_allowed": False,
        "must_reenter_orchestration_layer": True,
        "runtime_fact_committed": False,
        "fallback": None if grounded else "active_observation_or_human_disambiguation",
    }


def build_task_perception_result(scene: dict[str, Any], session: dict[str, Any], utterance: str) -> dict[str, Any] | None:
    activation = activate_task_perception(utterance)
    if not activation:
        return None
    observation = simulate_task_conditioned_observation(scene, session, activation)
    grounding = ground_task_observations(activation, observation)
    grounded = grounding["grounding_status"] == "spatially_grounded"
    target = next((item for item in grounding["candidate_bindings"] if item["role"] == "target"), None)
    support = next((item for item in grounding["candidate_bindings"] if item["role"] == "support"), None)
    prompt = (
        f"我观察到{support['label_hint']}上的{target['label_hint']}，空间关系已经落地为候选；"
        "接下来仍需编排导航和抓取，并在执行后验真。"
        if grounded and target and support
        else "我已经按任务概念观察环境，但当前候选不足或不唯一，需要继续观察或请你确认。"
    )
    return {
        "status": "perception_grounded_candidate" if grounded else "active_perception_required",
        "reason": "task_conditioned_concept_perception_grounding",
        "prompt": prompt,
        "task_perception_frame": activation,
        "perception_observation": observation,
        "concept_grounding": grounding,
        "causal_preview": {
            "goal_fact": "target_object_in_gripper",
            "required_facts": ["target_object_spatially_grounded", "executor_at_target_support", "target_object_within_reach"],
            "candidate_process": ["navigate_to_support", "align_end_effector", "grasp_target", "verify_target_in_gripper"],
            "planning_is_established_fact": False,
        },
        "frames": [],
    }


def _binding(role: str, candidate: dict[str, Any], observation_id: str) -> dict[str, Any]:
    return {
        "role": role,
        "entity_ref": candidate["spatial_entity_candidate_ref"],
        "concept_id": candidate["candidate_concept_id"],
        "label_hint": candidate["label_hint"],
        "binding_strength": "observation_and_spatial_relation",
        "evidence_ref": observation_id,
        "state": "spatially_grounded",
    }


def _track_id(entity_id: str) -> str:
    return "track_" + hashlib.sha1(entity_id.encode("utf-8")).hexdigest()[:10]


def _estimate_support_relations(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    relations = []
    for subject in tracks:
        sx, sy = subject["estimated_position"]
        subject_bottom = subject["estimated_base_elevation_m"]
        for support in tracks:
            if subject is support or support["candidate_concept_id"] != "concept_support_surface":
                continue
            ox, oy = support["estimated_position"]
            width, depth, height = support["estimated_size"]
            support_top = support["estimated_base_elevation_m"] + height
            within_surface = abs(sx - ox) <= width / 2 and abs(sy - oy) <= depth / 2
            height_aligned = abs(subject_bottom - support_top) <= 0.08
            if within_surface and height_aligned:
                relations.append(
                    {
                        "subject_track_id": subject["track_id"],
                        "relation": "on_top_of",
                        "object_track_id": support["track_id"],
                        "confidence": 0.96,
                        "basis": ["projected_footprint_overlap", "support_height_alignment"],
                    }
                )
    return relations
