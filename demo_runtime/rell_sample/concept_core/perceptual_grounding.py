from __future__ import annotations

import hashlib
import math
from copy import deepcopy
from typing import Any

from concept_core.concept_pack_registry import load_concept_pack_registry
from concept_core.visual_concept_packs import load_visual_concept_packs, match_visual_concept_candidates


COLOR_ALIASES = {
    "white": ["白色", "白的"],
    "black": ["黑色", "黑的"],
    "light_blue": ["浅蓝色", "浅蓝"],
    "blue": ["蓝色", "蓝的"],
    "red": ["红色", "红的"],
    "green": ["绿色", "绿的"],
    "yellow": ["黄色", "黄的"],
    "gray": ["灰色", "灰的"],
    "brown": ["棕色", "褐色", "棕的"],
}

COLOR_NAMES = {
    "white": "白色",
    "black": "黑色",
    "light_blue": "蓝色",
    "blue": "蓝色",
    "red": "红色",
    "green": "绿色",
    "yellow": "黄色",
    "gray": "灰色",
    "brown": "棕色",
}


def load_object_concepts() -> dict[str, Any]:
    return load_concept_pack_registry(active_domains=("home",))


def activate_task_perception(utterance: str) -> dict[str, Any] | None:
    text = utterance.strip()
    library = load_object_concepts()
    pickup_requested = any(token in text for token in ("拿", "取", "抓"))
    placement_requested = any(token in text for token in ("放到", "放在", "摆到", "摆在"))
    matched = []
    for concept in library["concepts"]:
        aliases = [alias for alias in concept["aliases"] if alias in text]
        if aliases:
            matched.append({**deepcopy(concept), "activation_reason": "explicit_task_mention", "matched_aliases": aliases})
    target_candidates = [item for item in matched if "graspable" in item.get("functional_affordances", [])]
    if not (pickup_requested or placement_requested) or not target_candidates:
        return None
    target = target_candidates[0]
    supports = [item for item in matched if "support_object" in item.get("functional_affordances", [])]
    explicit_support = supports[0] if supports else None
    support = explicit_support or next(
        (item for item in library["concepts"] if "support_object" in item.get("functional_affordances", [])),
        None,
    )
    activated = [target] + ([support] if support and support["concept_id"] != target["concept_id"] else [])
    color_constraint = next(
        (color for color, aliases in COLOR_ALIASES.items() if any(alias in text for alias in aliases)),
        None,
    )
    color_surface = next(
        (alias for alias in COLOR_ALIASES.get(color_constraint, []) if alias in text),
        None,
    )
    return {
        "task_utterance": text,
        "action_concept": "concept_relocate_object" if placement_requested else "concept_pick_up_object",
        "target_concept_id": target["concept_id"],
        "support_concept_id": support["concept_id"] if support else None,
        # A mentioned support in a transfer request is the destination role,
        # not evidence that the theme is already on that support.
        "support_binding_mode": (
            "explicit_destination" if explicit_support and placement_requested
            else "explicit_constraint" if explicit_support
            else "infer_from_observed_relation"
        ),
        "activated_concepts": activated,
        "requested_relations": ["target_on_top_of_support"] if explicit_support and not placement_requested else [],
        "target_constraints": {"color": color_constraint} if color_constraint else {},
        "target_constraint_mentions": (
            [{"attribute": "color", "requested_value": color_constraint, "surface": color_surface}]
            if color_constraint else []
        ),
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
    verified_target = activation.get("verified_target_binding")
    raw_target_candidates = by_concept.get(activation["target_concept_id"], [])
    target_constraints = activation.get("target_constraints", {})
    target_candidates = [
        item
        for item in raw_target_candidates
        if all(item.get("observed_attributes", {}).get(key) == value for key, value in target_constraints.items())
    ]
    support_candidates = by_concept.get(activation.get("support_concept_id"), []) if activation.get("support_concept_id") else []
    support_binding_mode = activation.get("support_binding_mode")
    support_required = support_binding_mode in {"explicit_constraint", "explicit_destination"}
    related_supports: list[tuple[dict[str, Any], dict[str, Any]]] = []
    if len(target_candidates) == 1 and not verified_target:
        target_track = target_candidates[0]["track_id"]
        support_by_track = {item["track_id"]: item for item in support_candidates}
        for relation in observation["relation_candidates"]:
            support_candidate = support_by_track.get(relation.get("object_track_id"))
            if (
                relation.get("subject_track_id") == target_track
                and relation.get("relation") == "on_top_of"
                and support_candidate
            ):
                related_supports.append((support_candidate, relation))
    if support_binding_mode == "explicit_destination" and len(support_candidates) == 1:
        related_supports = [(support_candidates[0], {
            "relation": "destination_binding",
            "subject_track_id": target_candidates[0]["track_id"] if target_candidates else None,
            "object_track_id": support_candidates[0]["track_id"],
            "evidence_scope": "verified_held_theme_plus_current_visual_destination" if verified_target else "current_visual_candidate",
        })]
    target_grounded = bool(verified_target or len(target_candidates) == 1)
    ambiguity = not target_grounded or (support_required and len(related_supports) != 1)
    if not verified_target and len(target_candidates) > 1:
        ambiguity_reason = "multiple_target_candidates"
    elif not target_grounded:
        ambiguity_reason = "target_not_observed"
    elif support_binding_mode == "explicit_destination" and len(support_candidates) > 1:
        ambiguity_reason = "multiple_support_candidates"
    elif support_required and len(related_supports) > 1:
        ambiguity_reason = "multiple_support_candidates"
    elif support_required and not related_supports:
        ambiguity_reason = "support_not_observed"
    else:
        ambiguity_reason = None
    relation_evidence = None
    selected_support = related_supports[0][0] if len(related_supports) == 1 else None
    if not ambiguity and selected_support:
        relation_evidence = related_supports[0][1]
    relation_satisfied = not activation["requested_relations"] or relation_evidence is not None
    grounded = bool(not ambiguity and target_grounded and relation_satisfied)
    bindings = []
    if grounded:
        bindings.append(deepcopy(verified_target) if verified_target else _binding("target", target_candidates[0], observation["observation_id"]))
        if selected_support:
            bindings.append(_binding("support", selected_support, observation["observation_id"]))
    return {
        "grounding_status": "spatially_grounded" if grounded else "perceptual_candidate",
        "candidate_bindings": bindings,
        "relation_evidence": relation_evidence,
        "ambiguity": ambiguity,
        "ambiguity_reason": ambiguity_reason,
        "candidate_summary": {
            "detected_target_count": len(raw_target_candidates),
            "target_count": 1 if verified_target else len(target_candidates),
            "support_count": len(support_candidates),
            "related_support_count": len(related_supports),
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
        "support_candidate_options": [
            {
                "entity_ref": item["spatial_entity_candidate_ref"],
                "label_hint": item["label_hint"],
                "estimated_position": deepcopy(item["estimated_position"]),
                "classification_confidence": item["classification_confidence"],
            }
            for item in support_candidates
        ],
        "constraint_rejections": [
            {
                "entity_ref": item["spatial_entity_candidate_ref"],
                "label_hint": item["label_hint"],
                "observed_attributes": deepcopy(item.get("observed_attributes", {})),
                "requested_attributes": deepcopy(target_constraints),
                "mismatched_attributes": [
                    {
                        "attribute": key,
                        "requested_value": value,
                        "observed_value": item.get("observed_attributes", {}).get(key),
                    }
                    for key, value in target_constraints.items()
                    if item.get("observed_attributes", {}).get(key) != value
                ],
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
    if activation["action_concept"] == "concept_relocate_object":
        held_refs = [ref for ref in session.get("state", {}).get("holding_by_effector", {}).values() if ref]
        if not held_refs and session.get("state", {}).get("holding"):
            held_refs = [session["state"]["holding"]]
        held_refs = list(dict.fromkeys(held_refs))
        if len(held_refs) == 1:
            held = next((item for item in session.get("runtime_objects", []) if item.get("entity_id") == held_refs[0]), None)
            target_concept = next(
                (item for item in activation["activated_concepts"] if item.get("concept_id") == activation["target_concept_id"]),
                None,
            )
            if held and target_concept and held.get("kind") in target_concept.get("compatible_kinds", []):
                activation["verified_target_binding"] = {
                    "role": "target",
                    "entity_ref": held["entity_id"],
                    "concept_id": activation["target_concept_id"],
                    "label_hint": held["label"],
                    "binding_strength": "verified_holding_fact",
                    "evidence_ref": f"world_revision:{session['world_revision']}:holding",
                    "state": "runtime_verified",
                    "estimated_position": deepcopy(held["position"]),
                    "observed_attributes": deepcopy(held.get("perceptual_attributes", {})),
                }
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
    if grounding["ambiguity_reason"] in {"target_not_observed", "support_not_observed"}:
        sensor_profile = session.get("executor_profile", {}).get("sensor_frames", {}).get("head_rgbd", {})
        scan_viewpoints = list(sensor_profile.get("active_scan_viewpoints", []))
        pan_range = sensor_profile.get("pan_range_deg", [])
        if len(pan_range) == 2:
            scan_viewpoints.extend([
                {"viewpoint_id": "head_pan_left_limit", "yaw_offset_deg": float(pan_range[1])},
                {"viewpoint_id": "head_pan_right_limit", "yaw_offset_deg": float(pan_range[0])},
            ])
        # A task target can be outside the head pan range. Candidate generation
        # therefore plans body-and-head coverage before claiming it is absent.
        scan_viewpoints.extend([
            {"viewpoint_id": "body_scan_left", "yaw_offset_deg": 110.0},
            {"viewpoint_id": "body_scan_right", "yaw_offset_deg": -110.0},
            {"viewpoint_id": "body_scan_rear", "yaw_offset_deg": 180.0},
        ])
        seen_offsets: set[float] = set()
        for viewpoint in scan_viewpoints:
            offset = float(viewpoint.get("yaw_offset_deg", 0.0))
            if offset in seen_offsets:
                continue
            seen_offsets.add(offset)
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
    if grounding["grounding_status"] != "spatially_grounded" and len(observations) > 1:
        # Roles in a multi-stage task need not coexist in one camera frame.
        # Merge object tracks across the bounded active scan while preserving
        # each track's sensor evidence; execution still requires later checks.
        merged_candidates: dict[str, dict[str, Any]] = {}
        merged_relations: dict[tuple[Any, ...], dict[str, Any]] = {}
        for item in observations:
            for candidate in item["semantic_candidates"]:
                merged_candidates.setdefault(candidate["track_id"], candidate)
            for relation in item["relation_candidates"]:
                key = (relation.get("subject_track_id"), relation.get("relation"), relation.get("object_track_id"))
                merged_relations.setdefault(key, relation)
        aggregate_observation = {
            "observation_id": "obs_aggregate_" + hashlib.sha1(
                "|".join(item["observation_id"] for item in observations).encode("utf-8")
            ).hexdigest()[:12],
            "sensor_contract": {
                "sensor_type": "bounded_multi_view_rgbd_aggregate",
                "source_observation_ids": [item["observation_id"] for item in observations],
                "reasoner_scene_truth_access": False,
            },
            "semantic_candidates": list(merged_candidates.values()),
            "occluded_candidates": [candidate for item in observations for candidate in item["occluded_candidates"]],
            "relation_candidates": list(merged_relations.values()),
            "semantically_suppressed_tracks": [],
            "safety_observations": [candidate for item in observations for candidate in item["safety_observations"]],
            "safety_channels_always_on": deepcopy(activation["safety_channels_always_on"]),
        }
        aggregate_grounding = ground_task_observations(activation, aggregate_observation)
        observations.append(aggregate_observation)
        active_perception_trace.append({
            "viewpoint": {"viewpoint_id": "bounded_multi_view_aggregate", "yaw_offset_deg": None},
            "observation_id": aggregate_observation["observation_id"],
            "grounding_status": aggregate_grounding["grounding_status"],
            "ambiguity_reason": aggregate_grounding["ambiguity_reason"],
        })
        observation = aggregate_observation
        grounding = aggregate_grounding
    grounded = grounding["grounding_status"] == "spatially_grounded"
    target = next((item for item in grounding["candidate_bindings"] if item["role"] == "target"), None)
    support = next((item for item in grounding["candidate_bindings"] if item["role"] == "support"), None)
    destination_bound = activation.get("support_binding_mode") == "explicit_destination"
    if grounded and target and support and destination_bound and target.get("binding_strength") == "verified_holding_fact":
        prompt = (
            f"我以当前已验真的持有事实将{target['label_hint']}绑定为被放置对象，"
            f"并通过主动观察把{support['label_hint']}绑定为放置目的地。"
            "下一步将按本体能力生成移动、放置和末态验真的候选计划。"
        )
    elif grounded and target and support and destination_bound:
        prompt = (
            f"我已通过主动观察找到{target['label_hint']}，并把{support['label_hint']}绑定为放置目的地。"
            "当前只建立候选角色绑定；下一步将按抓取、移动、放置和验真编排。"
        )
    elif grounded and target and support and len(active_perception_trace) > 1:
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
        color = activation.get("target_constraints", {}).get("color")
        prompt = (
            f"我根据{COLOR_NAMES.get(color, '当前')}特征把目标重新落地为{target['label_hint']}候选；"
            "没有擅自沿用上一轮歧义结果，执行前仍需编排和验真。"
        )
    elif grounding["ambiguity_reason"] == "multiple_target_candidates":
        option_labels = [
            COLOR_NAMES.get(item.get("observed_attributes", {}).get("color"), item["label_hint"]) + "杯子"
            for item in grounding["candidate_options"]
        ]
        prompt = (
            f"我观察到{grounding['candidate_summary']['target_count']}个都符合杯子概念的对象："
            f"{'、'.join(option_labels)}。我不能擅自选择，请按可观察特征确认。"
        )
    elif grounding["ambiguity_reason"] == "multiple_support_candidates":
        support_concept_id = activation.get("support_concept_id")
        support_labels = sorted({
            candidate.get("label_hint")
            for item in observations
            for candidate in item.get("semantic_candidates", [])
            if candidate.get("candidate_concept_id") == support_concept_id and candidate.get("label_hint")
        })
        prompt = (
            f"我已分别观察到任务对象和{len(support_labels)}个可承担目标承载面的候选：{'、'.join(support_labels)}。"
            "对象和目的地不需要出现在同一画面，但我不能替你选择目标桌面；请说具体名称。"
        )
    elif grounding["ambiguity_reason"] == "target_not_observed" and grounding["constraint_rejections"]:
        requested = activation.get("target_constraints", {})
        alternatives = []
        for item in grounding["constraint_rejections"]:
            color = item.get("observed_attributes", {}).get("color")
            label = item.get("label_hint") or "目标对象"
            display = label if not color or COLOR_NAMES.get(color, color) in label else f"{COLOR_NAMES.get(color, color)}{label}"
            if display not in alternatives:
                alternatives.append(display)
        requested_text = "、".join(
            COLOR_NAMES.get(value, str(value)) if key == "color" else f"{key}={value}"
            for key, value in requested.items()
        )
        if len(alternatives) == 1:
            prompt = (
                f"我按当前空间完成了有界观察，没有发现符合“{requested_text}”约束的目标；"
                f"但发现了{alternatives[0]}。你是否要我把它作为本次任务对象，继续完成原任务？"
            )
        else:
            prompt = (
                f"我按当前空间完成了有界观察，没有发现符合“{requested_text}”约束的目标；"
                f"但发现了这些同类候选：{'、'.join(alternatives)}。请指出其中哪一个可以替代，或补充新的可观察特征。"
            )
    else:
        prompt = "我已经按任务概念观察环境，但当前候选或空间关系证据不足，需要继续观察或请你确认。"
    status = "perception_grounded_candidate" if grounded else (
        "perception_disambiguation_required"
        if grounding["ambiguity_reason"] in {"multiple_target_candidates", "multiple_support_candidates"}
        else "evidence_gap_clarification_required"
        if grounding["ambiguity_reason"] == "target_not_observed" and grounding["constraint_rejections"]
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
            *(
                ["navigate_to_target", "align_end_effector", "grasp_target", "verify_target_in_gripper", "navigate_to_destination", "place_target", "verify_target_supported"]
                if destination_bound else
                ["navigate_to_support" if support else "navigate_to_bound_target", "align_end_effector", "grasp_target", "verify_target_in_gripper"]
            ),
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
    support_relations = []
    for subject in recognized:
        for support in recognized:
            if subject is support or support.get("concept_id") != "concept_support_surface":
                continue
            sx, sy = subject["estimated_position"]
            ox, oy = support["estimated_position"]
            width, depth, height = support["estimated_size"]
            support_top = float(support.get("estimated_base_elevation_m", 0.0)) + float(height)
            within_surface = abs(float(sx) - float(ox)) <= float(width) / 2 and abs(float(sy) - float(oy)) <= float(depth) / 2
            height_aligned = abs(float(subject.get("estimated_base_elevation_m", 0.0)) - support_top) <= 0.08
            if within_surface and height_aligned:
                support_relations.append({
                    "subject_entity_ref": subject["spatial_entity_candidate_ref"],
                    "relation": "on_top_of",
                    "support_entity_ref": support["spatial_entity_candidate_ref"],
                    "confidence": 0.96,
                    "basis": ["projected_footprint_overlap", "support_height_alignment"],
                    "evidence_kind": "visual_topological_candidate",
                })
    return {
        "status": "open_world_observation_completed",
        "observation_id": observation_id,
        "world_revision": session["world_revision"],
        "prompt": answer + "。这些是当前观测候选，不等于已验真的功能事实。",
        "recognized_object_candidates": recognized,
        "spatial_relation_candidates": support_relations,
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
