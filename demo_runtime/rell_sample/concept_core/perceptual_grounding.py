from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any

from concept_core.visual_concept_packs import load_visual_concept_packs, match_visual_concept_candidates


CONCEPT_FILE = Path(__file__).resolve().parents[1] / "data" / "embodied_object_concepts.json"
COLOR_ALIASES = {
    "white": ["白色", "白的"],
    "light_blue": ["浅蓝色", "浅蓝", "蓝色", "蓝的"],
}


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
    color_constraint = next(
        (color for color, aliases in COLOR_ALIASES.items() if any(alias in text for alias in aliases)),
        None,
    )
    return {
        "task_utterance": text,
        "action_concept": "concept_pick_up_object",
        "target_concept_id": target["concept_id"],
        "support_concept_id": support["concept_id"] if support else None,
        "activated_concepts": activated,
        "requested_relations": ["target_on_top_of_support"] if support else [],
        "target_constraints": {"color": color_constraint} if color_constraint else {},
        "safety_channels_always_on": deepcopy(library["safety_channels_always_on"]),
        "candidate_only": True,
        "direct_execution_allowed": False,
        "must_reenter_orchestration_layer": True,
    }


def simulate_task_conditioned_observation(
    scene: dict[str, Any],
    session: dict[str, Any],
    activation: dict[str, Any],
    viewpoint: dict[str, Any] | None = None,
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
    viewpoint = viewpoint or {"viewpoint_id": "head_center", "yaw_offset_deg": 0.0}
    yaw = math.radians(float(session_state["executor_yaw_deg"]) + float(viewpoint.get("yaw_offset_deg", 0.0)))
    sensor_range_m = 8.5
    half_fov_rad = math.radians(70.0)
    raw_tracks = []
    occluded_candidates = []
    semantically_suppressed = []
    for item in session.get("runtime_objects", scene["objects"]):
        if item.get("active") is False:
            continue
        dx = item["position"][0] - executor_position[0]
        dy = item["position"][1] - executor_position[1]
        distance = math.hypot(dx, dy)
        angle = abs(math.atan2(math.sin(math.atan2(dy, dx) - yaw), math.cos(math.atan2(dy, dx) - yaw)))
        raw_visible = distance <= sensor_range_m and angle <= half_fov_rad
        if not raw_visible:
            continue
        compatible = [
            concept
            for concept in concepts.values()
            if item["kind"] in concept.get("compatible_kinds", [])
        ]
        if compatible and viewpoint["viewpoint_id"] in item.get("occluded_from_viewpoints", []):
            occluded_candidates.append(
                {
                    "spatial_entity_candidate_ref": item["entity_id"],
                    "candidate_concept_id": compatible[0]["concept_id"],
                    "viewpoint_id": viewpoint["viewpoint_id"],
                    "reason": "line_of_sight_occluded",
                }
            )
            continue
        if item["kind"] not in requested_kinds:
            semantically_suppressed.append({"track_id": _track_id(item["entity_id"]), "reason": "not_required_by_active_task_concepts"})
            continue
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
                "observed_attributes": deepcopy(item.get("perceptual_attributes", {})),
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
            f"{activation['task_utterance']}|{executor_position}|{session_state['executor_yaw_deg']}|{session['world_revision']}|{viewpoint['viewpoint_id']}".encode("utf-8")
        ).hexdigest()[:12],
        "sensor_contract": {
            "sensor_type": "simulated_rgbd",
            "range_m": sensor_range_m,
            "horizontal_fov_deg": 140.0,
            "reasoner_scene_truth_access": False,
            "sensor_frame": "head_rgbd",
            "viewpoint": deepcopy(viewpoint),
        },
        "semantic_candidates": raw_tracks,
        "occluded_candidates": occluded_candidates,
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
    raw_target_candidates = by_concept.get(activation["target_concept_id"], [])
    target_constraints = activation.get("target_constraints", {})
    target_candidates = [
        item
        for item in raw_target_candidates
        if all(item.get("observed_attributes", {}).get(key) == value for key, value in target_constraints.items())
    ]
    support_candidates = by_concept.get(activation.get("support_concept_id"), []) if activation.get("support_concept_id") else []
    support_required = bool(activation.get("support_concept_id"))
    ambiguity = len(target_candidates) != 1 or (support_required and len(support_candidates) != 1)
    if len(target_candidates) > 1:
        ambiguity_reason = "multiple_target_candidates"
    elif not target_candidates:
        ambiguity_reason = "target_not_observed"
    elif support_required and len(support_candidates) > 1:
        ambiguity_reason = "multiple_support_candidates"
    elif support_required and not support_candidates:
        ambiguity_reason = "support_not_observed"
    else:
        ambiguity_reason = None
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
        "ambiguity_reason": ambiguity_reason,
        "candidate_summary": {
            "detected_target_count": len(raw_target_candidates),
            "target_count": len(target_candidates),
            "support_count": len(support_candidates),
        },
        "candidate_options": [
            {
                "entity_ref": item["spatial_entity_candidate_ref"],
                "label_hint": item["label_hint"],
                "estimated_position": deepcopy(item["estimated_position"]),
                "classification_confidence": item["classification_confidence"],
                "observed_attributes": deepcopy(item.get("observed_attributes", {})),
            }
            for item in target_candidates
        ],
        "constraint_rejections": [
            {
                "entity_ref": item["spatial_entity_candidate_ref"],
                "observed_attributes": deepcopy(item.get("observed_attributes", {})),
                "reason": "target_attribute_constraint_not_satisfied",
            }
            for item in raw_target_candidates
            if item not in target_candidates
        ],
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
    observations = [observation]
    grounding = ground_task_observations(activation, observation)
    active_perception_trace = [
        {
            "viewpoint": deepcopy(observation["sensor_contract"]["viewpoint"]),
            "observation_id": observation["observation_id"],
            "grounding_status": grounding["grounding_status"],
            "ambiguity_reason": grounding["ambiguity_reason"],
        }
    ]
    occluded_target = any(
        item["candidate_concept_id"] == activation["target_concept_id"]
        for item in observation.get("occluded_candidates", [])
    )
    if grounding["ambiguity_reason"] == "target_not_observed" and occluded_target:
        sensor_profile = session.get("executor_profile", {}).get("sensor_frames", {}).get("head_rgbd", {})
        for viewpoint in sensor_profile.get("active_scan_viewpoints", []):
            observation = simulate_task_conditioned_observation(scene, session, activation, viewpoint)
            observations.append(observation)
            grounding = ground_task_observations(activation, observation)
            active_perception_trace.append(
                {
                    "viewpoint": deepcopy(viewpoint),
                    "observation_id": observation["observation_id"],
                    "grounding_status": grounding["grounding_status"],
                    "ambiguity_reason": grounding["ambiguity_reason"],
                }
            )
            if grounding["grounding_status"] == "spatially_grounded":
                break
    grounded = grounding["grounding_status"] == "spatially_grounded"
    target = next((item for item in grounding["candidate_bindings"] if item["role"] == "target"), None)
    support = next((item for item in grounding["candidate_bindings"] if item["role"] == "support"), None)
    if grounded and target and support and len(active_perception_trace) > 1:
        prompt = (
            f"正面视角中的{target['label_hint']}被遮挡，我转动头部换了观察角度；"
            f"现在已观察到{support['label_hint']}上的{target['label_hint']}。这仍是候选，执行后还要验真。"
        )
    elif grounded and target and support:
        prompt = (
            f"我观察到{support['label_hint']}上的{target['label_hint']}，空间关系已经落地为候选；"
            "接下来仍需编排导航和抓取，并在执行后验真。"
        )
    elif grounded and target:
        color_names = {"white": "白色", "light_blue": "浅蓝色"}
        color = activation.get("target_constraints", {}).get("color")
        prompt = (
            f"我根据{color_names.get(color, '当前')}特征把目标重新落地为{target['label_hint']}候选；"
            "没有擅自沿用上一轮歧义结果，执行前仍需编排和验真。"
        )
    elif grounding["ambiguity_reason"] == "multiple_target_candidates":
        option_labels = [
            {"white": "白色杯子", "light_blue": "浅蓝色杯子"}.get(item.get("observed_attributes", {}).get("color"), item["label_hint"])
            for item in grounding["candidate_options"]
        ]
        prompt = (
            f"我观察到{grounding['candidate_summary']['target_count']}个都符合杯子概念的对象："
            f"{'、'.join(option_labels)}。我不能擅自选择，请按可观察特征确认。"
        )
    else:
        prompt = "我已经按任务概念观察环境，但当前候选或空间关系证据不足，需要继续观察或请你确认。"
    status = "perception_grounded_candidate" if grounded else (
        "perception_disambiguation_required"
        if grounding["ambiguity_reason"] in {"multiple_target_candidates", "multiple_support_candidates"}
        else "active_perception_required"
    )
    return {
        "status": status,
        "reason": "task_conditioned_concept_perception_grounding",
        "prompt": prompt,
        "task_perception_frame": activation,
        "perception_observation": observation,
        "perception_observations": observations,
        "active_perception_trace": active_perception_trace,
        "concept_grounding": grounding,
        "causal_preview": {
            "goal_fact": "target_object_in_gripper",
            "required_facts": [
                "target_object_spatially_grounded",
                "executor_at_target_support" if support else "executor_at_bound_target",
                "target_object_within_reach",
            ],
            "candidate_process": [
                "navigate_to_support" if support else "navigate_to_bound_target",
                "align_end_effector",
                "grasp_target",
                "verify_target_in_gripper",
            ],
            "planning_is_established_fact": False,
        },
        "frames": [],
    }


def build_open_world_observation(scene: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    executor_position = session["state"]["executor_position"]
    base_yaw = float(session["state"]["executor_yaw_deg"])
    sensor_range_m = 8.5
    viewpoints = [
        {"viewpoint_id": "open_scan_center", "yaw_offset_deg": 0.0},
        {"viewpoint_id": "open_scan_left", "yaw_offset_deg": 55.0},
        {"viewpoint_id": "open_scan_right", "yaw_offset_deg": -55.0},
    ]
    observed: dict[str, dict[str, Any]] = {}
    for viewpoint in viewpoints:
        yaw = math.radians(base_yaw + viewpoint["yaw_offset_deg"])
        for entity in session.get("runtime_objects", scene["objects"]):
            if entity.get("active") is False:
                continue
            dx = entity["position"][0] - executor_position[0]
            dy = entity["position"][1] - executor_position[1]
            distance = math.hypot(dx, dy)
            angle = abs(math.atan2(math.sin(math.atan2(dy, dx) - yaw), math.cos(math.atan2(dy, dx) - yaw)))
            if distance > sensor_range_m or angle > math.radians(70.0):
                continue
            signature = entity.get("visual_observation_signature", {})
            observed.setdefault(entity["entity_id"], {
                "track_id": _track_id(entity["entity_id"]),
                "spatial_entity_candidate_ref": entity["entity_id"],
                "estimated_position": deepcopy(entity["position"]),
                "estimated_base_elevation_m": float(entity.get("elevation_m", 0.0)),
                "estimated_size": deepcopy(entity["size"]),
                "observed_visual_features": deepcopy(signature.get("features", [])),
                "observed_color_family": signature.get("color_family"),
                "viewpoint_ids": [],
                "observation_source": "simulated_rgbd_adapter_without_semantic_label_access",
            })["viewpoint_ids"].append(viewpoint["viewpoint_id"])

    packs = load_visual_concept_packs()
    object_concepts = {item["concept_id"]: item for item in load_object_concepts()["concepts"]}
    recognized = []
    unknown = []
    for track in observed.values():
        matches = match_visual_concept_candidates(track, packs)
        if not matches:
            unknown.append({**deepcopy(track), "recognition_status": "unknown_object_candidate"})
            continue
        match = matches[0]
        concept = object_concepts[match["concept_id"]]
        relation = "on_ground_candidate" if track["estimated_base_elevation_m"] <= 0.05 else "elevated_or_supported_candidate"
        recognized.append({
            **deepcopy(track),
            "recognition_status": "visual_concept_candidate",
            "concept_id": match["concept_id"],
            "concept_label": concept["display_name"],
            "confidence": match["confidence"],
            "visual_pack_id": match["visual_pack_id"],
            "spatial_relation_candidate": relation,
            "functional_role_proven": False,
            "candidate_only": True,
        })
    observation_id = "open_obs_" + hashlib.sha1(
        f"{session['session_id']}|{session['world_revision']}|{sorted(observed)}".encode("utf-8")
    ).hexdigest()[:12]
    labels = [item["concept_label"] for item in recognized]
    answer = "我当前识别到" + "、".join(labels) if labels else "我当前没有识别出已加载的对象概念"
    if unknown:
        answer += f"；另外看到{len(unknown)}个尚未识别的对象候选"
    return {
        "status": "open_world_observation_completed",
        "observation_id": observation_id,
        "world_revision": session["world_revision"],
        "prompt": answer + "。这些是当前观测候选，不等于已验真的功能事实。",
        "recognized_object_candidates": recognized,
        "unknown_object_candidates": unknown,
        "scan_viewpoints": viewpoints,
        "visual_pack_ids": [item["pack_id"] for item in packs],
        "runtime_fact_candidates": [
            {
                "fact": f"{item['concept_id']}:{item['spatial_relation_candidate']}",
                "entity_ref": item["spatial_entity_candidate_ref"],
                "evidence_ref": observation_id,
                "world_revision": session["world_revision"],
                "candidate_only": True,
            }
            for item in recognized
        ],
        "candidate_only": True,
        "direct_execution_allowed": False,
        "runtime_fact_committed": False,
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
        "estimated_position": deepcopy(candidate["estimated_position"]),
        "observed_attributes": deepcopy(candidate.get("observed_attributes", {})),
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
