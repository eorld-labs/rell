from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


EVENT_LEXICAL_PRIMITIVES: tuple[dict[str, Any], ...] = (
    {"operator": "observe_entity", "concept_id": "factory_event_observe", "heads": ("观察", "瞧", "看", "找"), "canonical": "观察"},
    {"operator": "navigate_to", "concept_id": "factory_event_navigate", "heads": ("前往", "靠近", "走", "去"), "canonical": "走到"},
    {"operator": "orient_executor", "concept_id": "factory_event_orient", "heads": ("转向", "面向", "朝向", "转"), "canonical": "转向"},
    {"operator": "grasp_object", "concept_id": "factory_event_grasp", "heads": ("捡", "拾", "抓", "取", "拿"), "canonical": "拿起"},
    {"operator": "release_object", "concept_id": "factory_event_release", "heads": ("释放", "撒手", "松开", "放开"), "canonical": "放开"},
    {"operator": "place_object", "concept_id": "factory_event_place", "heads": ("放回", "搁", "摆", "放"), "canonical": "放到"},
    {"operator": "handover_object", "concept_id": "factory_event_handover", "heads": ("递给", "交给", "拿给", "送给", "递过去", "交过去"), "canonical": "递给"},
    {"operator": "transport_object", "concept_id": "factory_event_transport", "heads": ("带到", "拿到", "送到", "端到", "带走", "拿来"), "canonical": "带到"},
    {"operator": "apply_directional_force", "concept_id": "factory_event_push_pull", "heads": ("拖", "挪", "推", "拉"), "canonical": "推动"},
    {"operator": "change_open_state", "concept_id": "factory_event_open_close", "heads": ("打开", "关上", "关闭", "合上"), "canonical": "打开"},
    {"operator": "change_device_activation", "concept_id": "factory_event_activate_deactivate", "heads": ("启动", "开启", "关掉", "开机", "关机"), "canonical": "启动"},
    {"operator": "transfer_material", "concept_id": "factory_event_transfer", "heads": ("倒入", "倒进", "倒出", "装入", "装进", "取出"), "canonical": "转移"},
    {"operator": "remove_surface_contaminant", "concept_id": "factory_event_clean", "heads": ("打扫", "清洁", "清理", "擦"), "canonical": "清洁"},
    {"operator": "stop_current_activity", "concept_id": "factory_event_stop", "heads": ("停止", "停下", "取消"), "canonical": "停止"},
    {"operator": "wait_until", "concept_id": "factory_event_wait", "heads": ("等待", "等等", "等"), "canonical": "等待"},
)

QUESTION_MARKERS = ("吗", "么", "呢", "没有", "没", "是否", "有无", "有没有", "哪里", "哪儿", "什么", "为何", "为什么", "怎么")
PRONOUNS = ("它们", "他们", "她们", "那个", "这个", "它", "他", "她", "那里", "那边", "这里", "这边")
FUNCTION_WORDS = (
    "请", "麻烦", "帮我", "帮忙", "你", "我", "一下", "一个", "一件", "把", "给", "去", "来", "过来", "现在", "上", "里", "中",
    "起来", "的", "得", "地", "了", "着", "过", "起", "下", "能", "可以", "可不可以", "能不能", "是否", "吗", "么", "呢", "呀", "啊",
)

# These markers order discourse stages but do not contribute an event, object,
# or causal role of their own.
FUNCTION_WORDS += ("再", "然后", "接着")
FUNCTION_WORDS += ("人类", "家人", "主人", "用户", "接收人")


def normalize_language_text(text: str) -> str:
    return re.sub(r"[\s，。！？、,.!?；;：:]+", "", (text or "").strip().lower())


def _longest_non_overlapping_mentions(text: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    for candidate in sorted(candidates, key=lambda item: (-(item["end"] - item["start"]), item["start"])):
        if any(candidate["start"] < end and candidate["end"] > start for start, end in occupied):
            continue
        selected.append(candidate)
        occupied.append((candidate["start"], candidate["end"]))
    return sorted(selected, key=lambda item: item["start"])


def _object_mentions(text: str, object_concepts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for concept in object_concepts:
        for alias in concept.get("aliases", []):
            if not alias:
                continue
            for match in re.finditer(re.escape(alias), text):
                candidates.append({
                    "concept_id": concept.get("concept_id"),
                    "display_name": concept.get("display_name"),
                    "matched_alias": alias,
                    "start": match.start(),
                    "end": match.end(),
                    "compatible_kinds": deepcopy(concept.get("compatible_kinds", [])),
                    "functional_affordances": deepcopy(concept.get("functional_affordances", [])),
                    "source": "object_concept_language_adapter",
                })
    return _longest_non_overlapping_mentions(text, candidates)


def _event_mentions(
    text: str,
    event_concepts: list[dict[str, Any]],
    learned_adapters: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    concept_index = {item.get("concept_id"): item for item in event_concepts}
    primitive_index = {item["concept_id"]: item for item in EVENT_LEXICAL_PRIMITIVES}

    for adapter in learned_adapters:
        if adapter.get("status") not in {"session_confirmed", "trusted"}:
            continue
        trigger = normalize_language_text(str(adapter.get("surface_form") or ""))
        if not trigger:
            continue
        for match in re.finditer(re.escape(trigger), text):
            concept_id = adapter.get("concept_id")
            primitive = primitive_index.get(concept_id, {})
            candidates.append({
                "concept_id": concept_id,
                "operator": adapter.get("operator") or primitive.get("operator"),
                "matched_surface": trigger,
                "canonical_surface": primitive.get("canonical", trigger),
                "start": match.start(),
                "end": match.end(),
                "source": "human_confirmed_language_adapter",
            })

    for primitive in EVENT_LEXICAL_PRIMITIVES:
        concept = concept_index.get(primitive["concept_id"], {})
        surfaces = set(primitive["heads"])
        surfaces.update(normalize_language_text(alias) for alias in concept.get("aliases", []) if alias)
        for surface in sorted(surfaces, key=len, reverse=True):
            for match in re.finditer(re.escape(surface), text):
                if primitive["operator"] == "navigate_to" and surface == "去" and match.start() > 0 and text[match.start() - 1] in "回过上下进出":
                    continue
                candidates.append({
                    "concept_id": primitive["concept_id"],
                    "operator": primitive["operator"],
                    "matched_surface": surface,
                    "canonical_surface": primitive["canonical"],
                    "start": match.start(),
                    "end": match.end(),
                    "source": "factory_lexical_primitive",
                })
    mentions = _longest_non_overlapping_mentions(text, candidates)
    deduplicated: list[dict[str, Any]] = []
    for mention in mentions:
        if deduplicated and mention["operator"] == deduplicated[-1]["operator"] and mention["start"] <= deduplicated[-1]["end"] + 1:
            continue
        deduplicated.append(mention)
    return deduplicated


def _definition_candidate(text: str, event_concepts: list[dict[str, Any]]) -> dict[str, Any] | None:
    patterns = (
        r"[‘'\"“]?([^‘’'\"“”]{1,10})[’'\"”]?(?:就是|意思是|等于)([^，。！？,.!?]{1,14})",
        r"[‘'\"“]?([^‘’'\"“”]{1,10})[’'\"”]?和([^，。！？,.!?]{1,14})(?:一样|是一个意思)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        surface = normalize_language_text(match.group(1))
        explanation = normalize_language_text(match.group(2))
        if not surface or not explanation or surface == explanation:
            continue
        known = _event_mentions(explanation, event_concepts, [])
        if len(known) == 1:
            return {
                "surface_form": surface,
                "target_surface": explanation,
                "concept_id": known[0]["concept_id"],
                "operator": known[0]["operator"],
                "canonical_surface": known[0]["canonical_surface"],
                "candidate_only": True,
                "requires_human_confirmation": True,
            }
    return None


def _speech_act(text: str, events: list[dict[str, Any]], definition: dict[str, Any] | None) -> str:
    if definition:
        return "language_teaching"
    if any(marker in text for marker in ("不要", "别", "不许", "禁止")) and events:
        return "prohibition"
    if any(marker in text for marker in QUESTION_MARKERS) or text.endswith(("吗", "么", "呢")):
        return "state_query"
    if events:
        return "task_request"
    return "unknown"


def _query_type(text: str, events: list[dict[str, Any]], objects: list[dict[str, Any]]) -> str | None:
    operators = {item["operator"] for item in events}
    if any(marker in text for marker in ("手里", "手上", "拿着什么", "握着什么", "持有什么")):
        return "holding_state"
    if objects and any(marker in text for marker in ("在哪里", "在哪", "哪儿", "什么位置", "哪个区域")):
        return "object_location"
    if objects and "observe_entity" in operators:
        return "object_visibility"
    if objects and any(marker in text for marker in ("有没有", "有无", "是否有", "存在吗", "在不在")):
        return "object_presence"
    if any(marker in text for marker in ("下一步", "接下来")):
        return "next_step"
    if any(marker in text for marker in ("现在做什么", "正在做什么", "当前动作")):
        return "current_action"
    return None


def _resolve_pronouns(text: str, objects: list[dict[str, Any]], context_entities: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    present = [pronoun for pronoun in PRONOUNS if pronoun in text]
    if not present or objects:
        return objects, []
    unique = {str(item.get("entity_ref") or item.get("concept_id") or item.get("label")): item for item in context_entities}
    if len(unique) == 1:
        entity = deepcopy(next(iter(unique.values())))
        entity.update({
            "matched_alias": present[0],
            "source": "dialogue_focus_binding",
            "start": text.find(present[0]),
            "end": text.find(present[0]) + len(present[0]),
        })
        return [entity], []
    return objects, ["pronoun_reference_not_unique"]


def _roles(
    events: list[dict[str, Any]],
    objects: list[dict[str, Any]],
    context_entities: list[dict[str, Any]],
    text: str,
) -> dict[str, Any]:
    movable = [item for item in objects if any(token in set(item.get("functional_affordances", [])) for token in ("graspable", "movable", "graspable_candidate"))]
    supports = [item for item in objects if any(token in set(item.get("functional_affordances", [])) for token in ("support_object", "receive_object", "receive_liquid"))]
    held = [item for item in context_entities if item.get("focus_source") == "verified_holding_fact"]
    place_event = next((item for item in events if item["operator"] == "place_object"), None)
    handover_event = next((item for item in events if item["operator"] == "handover_object"), None)
    placing = place_event is not None
    roles: dict[str, Any] = {}
    if placing:
        surface = str(place_event.get("matched_surface") or "")
        has_destination_connector = any(marker in surface for marker in ("到", "在"))
        restores_prior_relation = "回" in surface
        before = [item for item in objects if item.get("end", 0) <= place_event["start"]]
        after = [item for item in objects if item.get("start", 0) >= place_event["end"]]
        if (has_destination_connector or restores_prior_relation) and after:
            roles["destination"] = deepcopy(after[-1])
            if before:
                roles["theme"] = deepcopy(before[-1])
        elif surface == "放下" and after:
            roles["theme"] = deepcopy(after[0])
        elif movable:
            roles["theme"] = deepcopy(movable[0])
        if "theme" not in roles and len(held) == 1:
            roles["theme"] = {**deepcopy(held[0]), "binding_source": "implicit_unique_verified_holding_fact"}
    else:
        if movable:
            roles["theme"] = deepcopy(movable[0])
        if supports:
            roles["destination"] = deepcopy(supports[-1])
        elif len(objects) > 1:
            roles["destination"] = deepcopy(objects[-1])
    if objects and "theme" not in roles and not placing:
        roles["target"] = deepcopy(objects[0])
    if any(item["operator"] == "navigate_to" for item in events) and objects:
        roles["destination"] = deepcopy(objects[-1])
    if handover_event:
        if movable:
            roles["theme"] = deepcopy(movable[0])
        recipient_surface = next(
            (marker for marker in ("接收人", "人类", "家人", "主人", "用户") if marker in text),
            None,
        )
        if not recipient_surface and any(marker in text for marker in ("给我", "递给我", "交给我", "送给我", "拿给我")):
            recipient_surface = "我"
        if recipient_surface:
            roles["recipient"] = {
                "matched_alias": recipient_surface,
                "entity_type": "human_recipient",
                "reference": "human_speaker" if recipient_surface == "我" else "current_human_recipient_role",
                "source": "human_recipient_relational_language",
            }
    return roles


def _canonical_utterance(speech_act: str, query_type: str | None, events: list[dict[str, Any]], roles: dict[str, Any]) -> str | None:
    target = roles.get("theme") or roles.get("target") or roles.get("destination") or {}
    destination = roles.get("destination") or {}
    recipient = roles.get("recipient") or {}
    target_name = target.get("matched_alias") or target.get("label") or target.get("display_name")
    destination_name = destination.get("matched_alias") or destination.get("display_name")
    recipient_name = recipient.get("matched_alias") or recipient.get("label") or recipient.get("display_name")
    if speech_act == "state_query":
        if query_type == "object_visibility" and target_name:
            return f"看得到{target_name}吗"
        if query_type == "object_presence" and target_name:
            return f"有没有{target_name}"
        if query_type == "object_location" and target_name:
            return f"{target_name}在哪里"
        return None
    if speech_act == "prohibition":
        return None
    parts: list[str] = []
    for event in events:
        operator = event["operator"]
        if operator == "grasp_object" and target_name:
            part = f"拿起{target_name}"
        elif operator == "place_object":
            placement_surface = "放回" if "回" in str(event.get("matched_surface") or "") else "放到"
            part = f"把{target_name}{placement_surface}{destination_name}" if target_name and destination_name else (f"放下{target_name}" if target_name else None)
        elif operator == "handover_object":
            part = f"把{target_name}递给{recipient_name}" if target_name and recipient_name else None
        elif operator == "navigate_to" and destination_name:
            part = f"走到{destination_name}"
        elif operator == "observe_entity" and target_name:
            part = f"观察{target_name}"
        else:
            part = event.get("canonical_surface")
            if part and target_name and len(events) == 1:
                part += target_name
        if part and part not in parts:
            parts.append(part)
    return "然后".join(parts) or None


def _unknown_surface(text: str, events: list[dict[str, Any]], objects: list[dict[str, Any]]) -> str | None:
    residual = text
    spans = [(item["start"], item["end"]) for item in [*events, *objects] if isinstance(item.get("start"), int)]
    for start, end in sorted(spans, reverse=True):
        residual = residual[:start] + (" " * (end - start)) + residual[end:]
    for word in sorted(FUNCTION_WORDS, key=len, reverse=True):
        residual = residual.replace(word, "")
    residual = re.sub(r"[\s，。！？、,.!?；;：:]+", "", residual)
    return residual or None


def compose_language_concepts(
    utterance: str,
    *,
    event_concepts: list[dict[str, Any]],
    object_concepts: list[dict[str, Any]],
    context_entities: list[dict[str, Any]] | None = None,
    learned_adapters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = normalize_language_text(utterance)
    definition = _definition_candidate(normalized, event_concepts)
    objects = _object_mentions(normalized, object_concepts)
    events = _event_mentions(normalized, event_concepts, learned_adapters or [])
    objects, unresolved = _resolve_pronouns(normalized, objects, context_entities or [])
    speech_act = _speech_act(normalized, events, definition)
    query_type = _query_type(normalized, events, objects) if speech_act == "state_query" else None
    context_entities = context_entities or []
    roles = _roles(events, objects, context_entities, normalized)
    relative_direction = next(
        (direction for direction, markers in {
            "forward": ("往前", "向前", "前进"),
            "backward": ("往后", "向后", "后退"),
            "left": ("向左", "往左", "左转"),
            "right": ("向右", "往右", "右转"),
        }.items() if any(marker in normalized for marker in markers)),
        None,
    )
    if not relative_direction:
        relative_match = re.search(r"(?:往|向)?(?:你|机器人|自己)?(?:的)?(前|后|左|右)(?:边|方)?", normalized)
        if relative_match:
            relative_direction = {"前": "forward", "后": "backward", "左": "left", "右": "right"}[relative_match.group(1)]
    if relative_direction:
        roles["direction"] = {"reference": "executor_body_frame", "value": relative_direction, "source": "body_relative_language"}

    if speech_act == "unknown":
        unresolved.append("event_or_query_concept_not_resolved")
    if speech_act == "state_query" and query_type is None:
        unresolved.append("query_relation_not_resolved")
    if speech_act == "task_request" and not events:
        unresolved.append("event_operator_not_resolved")
    requires_object = any(item["operator"] in {
        "observe_entity", "grasp_object", "release_object", "place_object",
        "handover_object",
        "transport_object",
        "apply_directional_force", "change_open_state", "change_device_activation", "remove_surface_contaminant",
    } for item in events) or (any(item["operator"] == "navigate_to" for item in events) and not relative_direction)
    if requires_object and not objects:
        unresolved.append("required_object_role_not_grounded")
    if any(item["operator"] == "place_object" for item in events):
        if not roles.get("theme"):
            unresolved.append("held_theme_not_grounded")
        place_surface = str(next(item for item in events if item["operator"] == "place_object").get("matched_surface") or "")
        if not roles.get("destination") and place_surface != "放下":
            unresolved.append("placement_destination_not_grounded")
    if any(item["operator"] == "handover_object" for item in events):
        if not roles.get("theme"):
            unresolved.append("handover_theme_not_grounded")
        if not roles.get("recipient"):
            unresolved.append("handover_recipient_not_grounded")

    unknown_surface = _unknown_surface(normalized, events, objects)
    confidence = 0.15
    if speech_act != "unknown":
        confidence += 0.18
    if events or query_type is not None:
        confidence += 0.28
    if objects or (not requires_object and speech_act not in {"unknown", "state_query"}):
        confidence += 0.22
    if not unresolved:
        confidence += 0.17
    if unknown_surface and speech_act not in {"language_teaching", "prohibition"}:
        confidence -= 0.08
    confidence = round(max(0.05, min(confidence, 0.99)), 2)
    confidence_band = "high" if confidence >= 0.78 else ("medium" if confidence >= 0.5 else "low")
    canonical = _canonical_utterance(speech_act, query_type, events, roles)

    if definition:
        confidence = 0.9
        confidence_band = "high"
    decision = (
        "request_language_adapter_confirmation" if definition
        else "route_original_with_partial_semantics" if relative_direction
        else "route_original_with_partial_semantics" if confidence_band == "high" and not unresolved and unknown_surface
        else "route_canonical_semantics" if confidence_band == "high" and not unresolved
        else "request_minimum_semantic_clarification" if canonical
        else "report_known_and_unknown_language_parts"
    )
    return {
        "schema_version": "1.0.0",
        "utterance": utterance,
        "normalized_utterance": normalized,
        "speech_act": speech_act,
        "query_type": query_type,
        "event_candidates": deepcopy(events),
        "entity_mentions": deepcopy(objects),
        "role_bindings": deepcopy(roles),
        "modifiers": {
            "negated": speech_act == "prohibition",
            "ability_or_possibility": any(marker in normalized for marker in ("能", "可以", "得见", "得到", "能不能", "可不可以")),
            "completed_or_resultative": any(marker in normalized for marker in ("到了", "看见", "看到", "完成", "已经")),
            "current_scope": not any(marker in normalized for marker in ("昨天", "以前", "曾经")),
            "body_relative_direction": relative_direction,
            "restore_prior_relation": any(
                item.get("operator") == "place_object" and "回" in str(item.get("matched_surface") or "")
                for item in events
            ),
        },
        "canonical_utterance": canonical,
        "canonical_frame": {
            "speech_act": speech_act,
            "operators": [item["operator"] for item in events],
            "query_type": query_type,
            "roles": deepcopy(roles),
            "goal_relation": "object_supported_at_destination" if any(item["operator"] == "place_object" for item in events) else (
                "object_received_by_recipient" if any(item["operator"] == "handover_object" for item in events) else (
                    "object_at_target_region" if any(item["operator"] == "transport_object" for item in events) else (
                        "object_in_gripper" if any(item["operator"] == "grasp_object" for item in events) else None
                    )
                )
            ),
            "world_scope": "current_world_revision",
            "destination_binding_policy": (
                "most_recent_verified_support_relation"
                if any(
                    item.get("operator") == "place_object" and "回" in str(item.get("matched_surface") or "")
                    for item in events
                )
                else "current_spatial_relation"
            ),
        },
        "definition_candidate": deepcopy(definition),
        "unknown_surface": unknown_surface,
        "unresolved_slots": list(dict.fromkeys(unresolved)),
        "confidence": confidence,
        "confidence_band": confidence_band,
        "decision": decision,
        "candidate_only": True,
        "runtime_fact_committed": False,
        "direct_execution_allowed": False,
    }
