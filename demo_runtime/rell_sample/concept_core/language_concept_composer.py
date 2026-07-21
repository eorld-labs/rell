from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .modifier_composer import compile_modifier_contract, modifiers_for_event
from .reference_resolution import (
    reference_resolution_referents,
    resolve_references,
    resolved_reference_mentions,
)
from .semantic_grounding import load_semantic_attribute_concepts


EVENT_LEXICAL_PRIMITIVES: tuple[dict[str, Any], ...] = (
    {"operator": "observe_entity", "concept_id": "factory_event_observe", "heads": ("观察", "瞧", "看", "找"), "canonical": "观察"},
    {"operator": "navigate_to", "concept_id": "factory_event_navigate", "heads": ("返回到", "回到", "返回", "前往", "靠近", "站过来", "站到", "站在", "走", "去"), "canonical": "走到"},
    {"operator": "orient_executor", "concept_id": "factory_event_orient", "heads": ("转向", "面向", "朝向", "转"), "canonical": "转向"},
    {"operator": "grasp_object", "concept_id": "factory_event_grasp", "heads": ("捡", "拾", "抓", "取", "拿"), "canonical": "拿起"},
    {"operator": "release_object", "concept_id": "factory_event_release", "heads": ("释放", "撒手", "松开", "放开"), "canonical": "放开"},
    {"operator": "fill_container", "concept_id": "factory_event_fill_container", "heads": ("接一杯水", "取一杯水", "接杯水", "取杯水", "接好水", "装满水", "盛点水", "盛水", "续满", "续水", "接水", "取水", "装水", "倒一杯水", "倒杯水"), "canonical": "接水"},
    {"operator": "place_object", "concept_id": "factory_event_place", "heads": ("放回", "送回", "搁回", "摆回", "归还", "搁", "摆", "放"), "canonical": "放到"},
    {"operator": "handover_object", "concept_id": "factory_event_handover", "heads": ("递回来", "交回来", "递给", "交给", "拿给", "送给", "递过去", "交过去", "递回", "交回"), "canonical": "递给"},
    {"operator": "transport_object", "concept_id": "factory_event_transport", "heads": ("拿过来", "带过来", "送过来", "端过来", "带到", "拿到", "送到", "端到", "带走", "拿来", "送来", "端来"), "canonical": "带到"},
    {"operator": "relocate_object", "concept_id": "factory_event_relocate", "heads": ("移开", "移走", "挪开", "搬开", "搬走", "拿开", "清走"), "canonical": "移开"},
    {"operator": "apply_directional_force", "concept_id": "factory_event_push_pull", "heads": ("拖", "挪", "推", "拉"), "canonical": "推动"},
    {"operator": "change_open_state", "concept_id": "factory_event_open_close", "heads": ("打开", "关上", "关闭", "合上"), "canonical": "打开"},
    {"operator": "change_device_activation", "concept_id": "factory_event_activate_deactivate", "heads": ("启动", "开启", "关掉", "开机", "关机"), "canonical": "启动"},
    {"operator": "transfer_material", "concept_id": "factory_event_transfer", "heads": ("倒入", "倒进", "倒出", "装入", "装进", "取出"), "canonical": "转移"},
    {"operator": "remove_surface_contaminant", "concept_id": "factory_event_clean", "heads": ("打扫", "清洁", "清理", "擦"), "canonical": "清洁"},
    {"operator": "stop_current_activity", "concept_id": "factory_event_stop", "heads": ("停止", "停下", "取消"), "canonical": "停止"},
    {"operator": "wait_until", "concept_id": "factory_event_wait", "heads": ("等待", "等等", "等"), "canonical": "等待"},
)

QUESTION_MARKERS = ("吗", "么", "呢", "没有", "没", "是否", "有无", "有没有", "哪里", "哪儿", "什么", "哪些", "啥", "为何", "为什么", "怎么")
PRONOUNS = ("它们", "他们", "她们", "那个", "这个", "它", "他", "她", "那里", "那边", "这里", "这边")
FUNCTION_WORDS = (
    "请", "麻烦", "帮我", "帮忙", "你", "我", "一下", "一个", "一件", "把", "给", "去", "来", "过来", "现在", "上", "里", "中",
    "起来", "的", "得", "地", "了", "着", "过", "起", "下", "能", "可以", "可不可以", "能不能", "是否", "吗", "么", "呢", "呀", "啊",
)

# These markers order discourse stages but do not contribute an event, object,
# or causal role of their own.
FUNCTION_WORDS += ("再", "然后", "接着")
FUNCTION_WORDS += ("人类", "家人", "主人", "用户", "接收人")
# Discourse acknowledgements can frame a task request, but they do not fill
# any event, entity, temporal, spatial, or causal slot in that request.
FUNCTION_WORDS += ("嗯嗯", "嗯", "好的", "好")


def _bounded_closed_class_query_normalization(
    text: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Repair one-edit interrogatives only inside an explicit state-query slot."""
    audit: list[dict[str, Any]] = []
    query_words = ("什么", "哪些")

    def replace(match: re.Match[str]) -> str:
        predicate, token = match.group(1), match.group(2)
        if token == "这么":
            return match.group(0)
        candidates = [
            word
            for word in query_words
            if len(word) == len(token)
            and sum(left != right for left, right in zip(word, token)) == 1
        ]
        if len(candidates) != 1:
            return match.group(0)
        canonical = candidates[0]
        audit.append(
            {
                "surface": token,
                "canonical": canonical,
                "token_class": "closed_class_interrogative",
                "basis": "single_edit_within_explicit_state_predicate_slot",
                "open_class_entity_rewritten": False,
            }
        )
        return predicate + canonical

    normalized = re.sub(
        r"(有|看到|看见|放着|摆着)([\u4e00-\u9fff]{2})(?=$|东西|物体)",
        replace,
        text,
    )
    return normalized, audit


def _normalize_language_text_with_audit(
    text: str,
) -> tuple[str, list[dict[str, Any]]]:
    compact = re.sub(
        r"[\s，。！？、,.!?；;：:]+", "", (text or "").strip().lower()
    )
    return _bounded_closed_class_query_normalization(compact)


def normalize_language_text(text: str) -> str:
    return _normalize_language_text_with_audit(text)[0]


def _discourse_clause_specs(utterance: str) -> list[dict[str, Any]]:
    """Split clauses and preserve their typed discourse relation."""
    correction = re.match(
        r"^(?:我的意思是)?(?:不是|并不是)(?P<rejected>.+?)[，,]?(?:而是|是要)(?P<replacement>.+)$",
        (utterance or "").strip(),
    )
    if not correction:
        correction = re.match(
            r"^(?:别|不要)(?P<rejected>.+?)[，,]?(?:改成|换成)(?P<replacement>.+)$",
            (utterance or "").strip(),
        )
    if correction:
        return [
            {
                "surface": correction.group("rejected").strip(),
                "incoming_relation": None,
                "discourse_polarity": "rejected",
            },
            {
                "surface": correction.group("replacement").strip(),
                "incoming_relation": "correction",
                "discourse_polarity": "asserted",
            },
        ]
    prepared = re.sub(
        r"((?:接好|装好|盛好|续满|填满|加满)(?:了)?(?:水|饮料))后(?=(?:把|将|搁|放|摆|端|拿|送|递|交))",
        r"\1，",
        utterance or "",
    )
    prepared = re.sub(
        r"(?:以后|之后|而后)(?=(?:把|将|用|换|拿|取|搁|放|摆|端|送|递|交|高脚|白色|透明|杯|托盘))",
        "，",
        prepared,
    )
    prepared = re.sub(
        r"后(?=(?:把|将|用|换|拿|取|搁|放|摆|端|送|递|交|高脚|白色|透明|杯|托盘))",
        "，",
        prepared,
    )
    connector_pattern = re.compile(
        r"([，,；;。！？!?]+|再然后|然后|接着|随后|同时|并同时|而是|再(?=(?:把|将|用|换|拿|取|搁|放|摆|端|送|递|交|高脚|白色|透明|杯|托盘)))"
    )
    pieces = connector_pattern.split(prepared)
    specs: list[dict[str, Any]] = []
    pending_relation = "sequence"
    for piece in pieces:
        if not piece:
            continue
        if connector_pattern.fullmatch(piece):
            pending_relation = (
                "parallel"
                if "同时" in piece
                else "correction"
                if piece == "而是"
                else "sequence"
            )
            continue
        surface = re.sub(r"^(?:先|再先)", "", piece.strip())
        if not surface:
            continue
        specs.append(
            {
                "surface": surface,
                "incoming_relation": None if not specs else pending_relation,
                "discourse_polarity": "asserted",
            }
        )
        pending_relation = "sequence"
    return specs if len(specs) > 1 else []


def _event_clause_surfaces(utterance: str) -> list[str]:
    return [item["surface"] for item in _discourse_clause_specs(utterance)]


def _propagate_event_frame_roles(
    frames: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve local ellipsis by typed event-role flow, never by text rewriting."""
    previous_theme: dict[str, Any] | None = None
    for index, frame in enumerate(frames):
        roles = frame.setdefault("role_bindings", {})
        operators = set((frame.get("canonical_frame") or {}).get("operators", []))
        current_theme = roles.get("theme") or roles.get("target")
        if (
            not current_theme
            and previous_theme
            and frame.get("incoming_discourse_relation") in {"sequence", "parallel"}
            and operators.intersection(
                {
                    "fill_container",
                    "place_object",
                    "handover_object",
                    "transport_object",
                    "release_object",
                }
            )
        ):
            inherited = deepcopy(previous_theme)
            inherited["binding_source"] = "typed_prior_event_theme_flow"
            inherited["inherited_from_frame_id"] = frames[index - 1].get("frame_id")
            inherited["physical_fact_committed"] = False
            roles["theme"] = inherited
            frame.setdefault("canonical_frame", {}).setdefault("roles", {})[
                "theme"
            ] = deepcopy(inherited)
            frame["unresolved_slots"] = [
                item
                for item in frame.get("unresolved_slots", [])
                if item
                not in {
                    "required_object_role_not_grounded",
                    "held_theme_not_grounded",
                    "handover_theme_not_grounded",
                }
            ]
            current_theme = inherited
        if current_theme and frame.get("discourse_polarity") != "rejected":
            previous_theme = deepcopy(current_theme)
    return frames


def _build_discourse_event_graph(frames: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = [
        {
            "frame_ref": frame.get("frame_id"),
            "clause_index": frame.get("clause_index"),
            "operators": deepcopy(
                (frame.get("canonical_frame") or {}).get("operators", [])
            ),
            "goal_relation": (frame.get("canonical_frame") or {}).get(
                "goal_relation"
            ),
            "role_keys": sorted((frame.get("role_bindings") or {}).keys()),
            "discourse_polarity": frame.get("discourse_polarity", "asserted"),
            "candidate_only": True,
        }
        for frame in frames
    ]
    edges = []
    for index, frame in enumerate(frames[1:], start=1):
        inherited_roles = [
            role
            for role, value in (frame.get("role_bindings") or {}).items()
            if isinstance(value, dict)
            and value.get("binding_source") == "typed_prior_event_theme_flow"
        ]
        edges.append(
            {
                "from_frame_ref": frames[index - 1].get("frame_id"),
                "to_frame_ref": frame.get("frame_id"),
                "relation": frame.get("incoming_discourse_relation") or "sequence",
                "inherited_roles": inherited_roles,
                "prior_effect_reused_as_current_fact": False,
            }
        )
    return {
        "nodes": nodes,
        "edges": edges,
        "raw_text_included": False,
        "candidate_only": True,
        "runtime_fact_committed": False,
    }


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
                mention_start = match.start()
                quantity_constraint = None
                classifiers = [
                    str(item)
                    for item in concept.get("classifiers", [])
                    if item
                ]
                if classifiers:
                    prefix = text[:match.start()]
                    quantifier = re.search(
                        rf"(?P<number>[一二两三四五六七八九十\d]+)"
                        rf"(?P<classifier>{'|'.join(map(re.escape, classifiers))})$",
                        prefix,
                    )
                    if quantifier:
                        number_surface = quantifier.group("number")
                        number_values = {
                            "一": 1,
                            "二": 2,
                            "两": 2,
                            "三": 3,
                            "四": 4,
                            "五": 5,
                            "六": 6,
                            "七": 7,
                            "八": 8,
                            "九": 9,
                            "十": 10,
                        }
                        quantity = (
                            int(number_surface)
                            if number_surface.isdigit()
                            else number_values.get(number_surface)
                        )
                        if quantity is not None:
                            mention_start = quantifier.start()
                            quantity_constraint = {
                                "quantity": quantity,
                                "classifier": quantifier.group("classifier"),
                                "surface": quantifier.group(0) + alias,
                                "selection_quantifier": "existential",
                                "human_specific_instance_required": False,
                            }
                candidates.append({
                    "concept_id": concept.get("concept_id"),
                    "display_name": concept.get("display_name"),
                    "matched_alias": alias,
                    "start": mention_start,
                    "end": match.end(),
                    "compatible_kinds": deepcopy(concept.get("compatible_kinds", [])),
                    "functional_affordances": deepcopy(concept.get("functional_affordances", [])),
                    "source": "object_concept_language_adapter",
                    **(
                        {
                            "quantity_constraint": quantity_constraint,
                            "quantity": quantity_constraint["quantity"],
                            "classifier": quantity_constraint["classifier"],
                            "selection_quantifier": quantity_constraint[
                                "selection_quantifier"
                            ],
                        }
                        if quantity_constraint
                        else {}
                    ),
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


def _infer_argument_order_events(
    text: str,
    events: list[dict[str, Any]],
    objects: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Infer known events from argument-predicate order, independent of word order."""
    patterns = (
        r"(?:把)?(?:水|饮料)接(?:了|好|满)?",
        r"(?:杯子|容器)接(?:好|满)?(?:水|饮料)",
        r"(?:取|打)(?:一)?杯水",
        r"(?:杯子|容器)?(?:接好|装好|装满|盛好|盛|续满|续上)(?:点|些|一杯)?(?:常温|热|凉)?(?:水|饮料)",
    )
    inferred = list(events)
    if not any(item.get("operator") == "fill_container" for item in inferred):
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            inferred.append({
                "concept_id": "factory_event_fill_container",
                "operator": "fill_container",
                "matched_surface": match.group(0),
                "canonical_surface": "接水",
                "start": match.start(),
                "end": match.end(),
                "source": "argument_predicate_composition",
            })
            break
    inferred_operators = {
        item.get("operator") for item in inferred if item.get("operator")
    }
    if (
        "handover_object" not in inferred_operators
        and (
            not inferred_operators
            or inferred_operators.issubset({"grasp_object", "navigate_to"})
        )
    ):
        result_head = (
            r"(?:拿|取)"
            if inferred_operators
            else r"(?:把|将|拿|取)"
        )
        handover = re.search(
            result_head + r".+?(?:给我|交到我手(?:里|上|中))", text
        )
        if handover:
            inferred.append(
                {
                    "concept_id": "factory_event_handover",
                    "operator": "handover_object",
                    "matched_surface": handover.group(0),
                    "canonical_surface": "递给",
                    "start": handover.start(),
                    "end": handover.end(),
                    "source": "argument_result_relation_composition",
                }
            )
    if not inferred and objects and re.match(
        r"^(?:请|麻烦)?给(?:我|人类|家人|主人|用户|接收人)", text
    ):
        inferred.append(
            {
                "concept_id": "factory_event_handover",
                "operator": "handover_object",
                "matched_surface": "给",
                "canonical_surface": "递给",
                "start": 0,
                "end": len(text),
                "source": "recipient_result_construction",
            }
        )
    return sorted(inferred, key=lambda item: (item.get("start", 0), item.get("end", 0)))


def _definition_candidate(text: str, event_concepts: list[dict[str, Any]]) -> dict[str, Any] | None:
    if re.match(r"^(?:我|你|他|她|我们|你们|他们)(?:的)?意思(?:就)?是", text):
        return None
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
    if (
        any(marker in text for marker in ("不要", "别", "不许", "禁止"))
        and not any(marker in text for marker in ("而是", "改成", "换成"))
        and events
    ):
        return "prohibition"
    if any(marker in text for marker in QUESTION_MARKERS) or text.endswith(("吗", "么", "呢")):
        return "state_query"
    if events:
        return "task_request"
    return "unknown"


def _query_type(
    text: str,
    events: list[dict[str, Any]],
    objects: list[dict[str, Any]],
    region_mentions: list[dict[str, Any]] | None = None,
) -> str | None:
    operators = {item["operator"] for item in events}
    inventory_tail = r"(?:都|还)?(?:有|放着|摆着)(?:什么|哪些|啥)"
    support_mentioned = any(
        {"support_object", "receive_object"}.intersection(
            item.get("functional_affordances", [])
        )
        for item in objects
    )
    if support_mentioned and re.search(
        rf"(?:上|上面)?{inventory_tail}$", text
    ):
        return "support_inventory"
    if re.search(
        rf"(?:房间|屋里|屋内|这里|当前空间|这个空间|周围)(?:里|内)?{inventory_tail}",
        text,
    ):
        return "region_inventory"
    if region_mentions and re.search(rf"(?:里|内)?{inventory_tail}", text):
        return "region_inventory"
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


def _discourse_roles(text: str) -> dict[str, dict[str, Any]]:
    roles: dict[str, dict[str, Any]] = {}
    if any(marker in text for marker in ("我的意思是", "我是说", "我说的是", "不是这个意思", "而是", "改成")):
        roles["task_correction"] = {
            "reference": "current_or_recent_task_outcome",
            "relation": "revises_delivery_or_ownership_goal",
            "source": "explicit_discourse_repair_marker",
        }
    if any(marker in text for marker in ("帮我", "替我", "为我")):
        roles["beneficiary"] = {
            "reference": "human_speaker",
            "relation": "benefits_from_requested_outcome",
            "source": "deictic_service_role",
        }
    if re.search(
        r"(?:站|走|到|靠近).{0,8}(?:我这边|我这里|我身边|我旁边|我的旁边)",
        text,
    ):
        roles["navigation_landmark"] = {
            "reference": "human_speaker",
            "relation": "near_landmark",
            "source": "deictic_human_proximity_language",
        }
    recipient_result_relation = bool(
        re.search(
            r"(?:送|递|交|拿|端|带)(?:回|过)?(?:来|到)?我(?:的)?手(?:里|上|中)",
            text,
        )
    )
    deictic_delivery = any(
        marker in text
        for marker in ("送过来", "递过来", "拿过来", "端过来", "送来", "递回来")
    )
    if any(marker in text for marker in ("给我", "交给我", "递给我", "送给我", "拿给我")) or recipient_result_relation or deictic_delivery:
        roles["recipient"] = {
            "reference": "human_speaker",
            "relation": "receives_requested_theme",
            "source": "deictic_service_role",
        }
    possession_source = bool(
        re.search(
            r"(?:拿|取|从)我(?:的)?手(?:里|上|中)(?:的|这|那)?|我手(?:里|上|中)(?:的|这只|这个)",
            text,
        )
    )
    if re.search(r"我(?:已经)?(?:喝|饮用)(?:完|光|好)", text) or possession_source:
        roles["source_holder"] = {
            "reference": "human_speaker",
            "relation": "holds_reported_consumed_container_candidate",
            "source": "deictic_reported_event_role",
            "physical_state_change_committed": False,
        }
    if any(
        re.search(pattern, text)
        for pattern in (
            r"(?:你|机器人)(?:继续|还|就)?(?:拿着|端着|托着|留着|保持拿着)",
            r"(?:拿着|端着|托着|留着)(?:就行|即可|不要给我)?$",
            r"托盘.*(?:留在|留给|保持在)(?:你|机器人)(?:的)?手(?:里|上|中)",
        )
    ):
        roles["executor_retention"] = {
            "reference": "executor",
            "relation": "retains_explicitly_contrasted_theme",
            "source": "explicit_possession_contrast",
        }
    return roles


def _reported_events(text: str) -> list[dict[str, Any]]:
    """Represent human-reported state changes without committing physical facts."""
    candidates: list[dict[str, Any]] = []
    for surface in (
        "喝完了", "喝光了", "喝好了", "饮用完了",
        "喝完", "喝光", "喝好", "饮用完",
    ):
        for match in re.finditer(re.escape(surface), text):
            candidates.append({
                "event_type": "consumption_completed",
                "operator": "report_consumption_completed",
                "matched_surface": surface,
                "start": match.start(),
                "end": match.end(),
                "candidate_postcondition": "previously_received_container_empty",
                "evidence_source": "human_report",
                "physical_state_change_committed": False,
            })
    return _longest_non_overlapping_mentions(text, candidates)


def _resolve_serial_event_dependencies(
    text: str,
    events: list[dict[str, Any]],
    objects: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Collapse bare motion auxiliaries into the following executable event."""
    retained: list[dict[str, Any]] = []
    dependencies: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        if event.get("operator") != "navigate_to" or event.get("matched_surface") not in {"去", "走"}:
            retained.append(event)
            continue
        following = next(
            (candidate for candidate in events[index + 1:] if candidate.get("operator") != "navigate_to"),
            None,
        )
        if not following:
            retained.append(event)
            continue
        intervening_objects = [
            item for item in objects
            if int(item.get("start", -1)) >= int(event.get("end", 0))
            and int(item.get("end", -1)) <= int(following.get("start", 0))
        ]
        explicit_destination_mentions = [
            item for item in intervening_objects
            if not text[
                int(event.get("end", 0)):int(item.get("start", 0))
            ].endswith(("把", "将", "用"))
        ]
        intervening = text[int(event.get("end", 0)):int(following.get("start", 0))]
        residual = intervening
        for item in intervening_objects:
            residual = residual.replace(str(item.get("matched_alias") or ""), "")
        for marker in ("再", "然后", "接着", "随后", "帮我", "去帮我", "把", "将", "用"):
            residual = residual.replace(marker, "")
        if not explicit_destination_mentions and not residual:
            dependencies.append({
                "operator": "navigate_to",
                "surface": event.get("matched_surface"),
                "relation": "execution_prerequisite_internal_to_following_event",
                "governing_operator": following.get("operator"),
                "requires_independent_destination_role": False,
            })
            continue
        retained.append(event)
    return retained, dependencies


def _extract_historical_event_constraints(
    text: str,
    events: list[dict[str, Any]],
    objects: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate events inside temporal relative clauses from current commands."""
    retained: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    temporal_markers = (
        "刚才",
        "刚刚",
        "之前",
        "先前",
        "原先",
        "原来",
        "上次",
        "上回",
        "方才",
        "此前",
    )
    for event in events:
        event_start = int(event.get("start", -1))
        event_end = int(event.get("end", -1))
        marker_matches = [
            (marker, text.rfind(marker, 0, event_start + 1))
            for marker in temporal_markers
        ]
        marker, marker_start = max(marker_matches, key=lambda item: item[1])
        possessive_end = text.find("的", event_end)
        if marker_start < 0 or possessive_end < 0:
            retained.append(event)
            continue
        if any(
            punctuation in text[marker_start:possessive_end]
            for punctuation in "，。！？、,.!?；;"
        ):
            retained.append(event)
            continue
        event_themes = [
            item
            for item in objects
            if int(item.get("start", -1)) >= event_end
            and int(item.get("end", -1)) <= possessive_end
            and "graspable" in item.get("functional_affordances", [])
        ]
        theme_resolution = "explicit_inside_temporal_relative_clause"
        if not event_themes and any(
            pronoun in text[event_end:possessive_end]
            for pronoun in ("它", "这个", "那个")
        ):
            preceding_themes = [
                item
                for item in objects
                if int(item.get("end", -1)) <= marker_start
                and "graspable" in item.get("functional_affordances", [])
            ]
            if preceding_themes:
                event_themes = [preceding_themes[-1]]
                theme_resolution = "pronoun_resolved_to_preceding_matrix_theme"
        if not event_themes and event.get("operator") == "grasp_object":
            # In a placement request such as "place the cup on the table
            # [it was] just picked up from", Chinese may omit the grasped
            # object inside the temporal relative clause. The unique matrix
            # theme can fill that event role; no category-wide guess is made.
            matrix_themes = [
                item
                for item in objects
                if int(item.get("end", -1)) <= marker_start
                and "graspable" in item.get("functional_affordances", [])
            ]
            matrix_place_events = [
                item
                for item in events
                if item.get("operator") == "place_object"
                and int(item.get("start", -1)) < marker_start
            ]
            if len(matrix_themes) == 1 and matrix_place_events:
                event_themes = [matrix_themes[0]]
                theme_resolution = (
                    "elliptical_temporal_event_theme_from_unique_matrix_role"
                )
        heads = [
            item
            for item in objects
            if int(item.get("start", -1)) > possessive_end
            and "support_object" in item.get("functional_affordances", [])
        ]
        if len(event_themes) != 1 or not heads:
            retained.append(event)
            continue
        head = min(heads, key=lambda item: int(item.get("start", 0)))
        relation = (
            "source_support_of_verified_event"
            if event.get("operator") == "grasp_object"
            else "location_of_verified_event"
        )
        constraints.append({
            "operator": event.get("operator"),
            "matched_surface": event.get("matched_surface"),
            "event_start": event_start,
            "event_end": event_end,
            "constraint_start": marker_start,
            "constraint_end": int(head.get("end", possessive_end + 1)),
            "temporal_marker": marker,
            "temporal_scope": "recent_verified_runtime_past",
            "actor_reference": (
                "executor" if "你" in text[marker_start:event_start] else None
            ),
            "theme": deepcopy(event_themes[0]),
            "theme_resolution": theme_resolution,
            "head": deepcopy(head),
            "head_role": "destination",
            "relation": relation,
            "source": "temporal_relative_clause_composition",
            "physical_fact_committed": False,
        })
    return retained, constraints


def _ellipsis_candidates(text: str) -> list[dict[str, Any]]:
    candidates = []
    match = re.search(r"(?P<event>接|取|倒|装|来)(?:一)?杯(?!子|水|茶|咖啡|饮料)", text)
    if match:
        candidates.append({
            "slot": "theme_content",
            "classifier": "杯",
            "governing_event_surface": match.group("event"),
            "status": "omitted_head_requires_contextual_goal_schema",
            "does_not_commit_concept": True,
        })
    return candidates


def _resolve_pronouns(text: str, objects: list[dict[str, Any]], context_entities: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    present = [pronoun for pronoun in PRONOUNS if pronoun in text]
    if not present:
        return objects, []
    pronoun = present[0]
    pronoun_start = text.find(pronoun)
    preceding = [
        item
        for item in objects
        if int(item.get("end", -1)) <= pronoun_start
        and "graspable" in item.get("functional_affordances", [])
    ]
    if preceding:
        entity = deepcopy(preceding[-1])
        entity.update(
            {
                "matched_alias": pronoun,
                "source": "intra_turn_role_coreference",
                "start": pronoun_start,
                "end": pronoun_start + len(pronoun),
            }
        )
        return [*objects, entity], []
    unique = {str(item.get("entity_ref") or item.get("concept_id") or item.get("label")): item for item in context_entities}
    if len(unique) == 1:
        entity = deepcopy(next(iter(unique.values())))
        entity.update({
            "matched_alias": pronoun,
            "source": "dialogue_focus_binding",
            "start": pronoun_start,
            "end": pronoun_start + len(pronoun),
        })
        return [*objects, entity], []
    return objects, ["pronoun_reference_not_unique"]


def _destination_relation_modifier(
    text: str,
    objects: list[dict[str, Any]],
    destination: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Extract the object in a relational noun phrase such as 'the table holding X'."""
    if not destination:
        return None
    destination_affordances = set(destination.get("functional_affordances", []))
    if not {"support_object", "receive_object"}.intersection(destination_affordances):
        return None
    destination_start = destination.get("start")
    if not isinstance(destination_start, int):
        return None
    possessive = text.rfind("的", 0, destination_start)
    if possessive < 0 or destination_start - possessive > 2:
        return None
    relation_markers = ("上面有", "上有", "放着", "摆着", "有")
    marker_matches = [
        (text.rfind(marker, 0, possessive), marker)
        for marker in relation_markers
        if text.rfind(marker, 0, possessive) >= 0
    ]
    if not marker_matches:
        return None
    marker_start, marker = max(marker_matches, key=lambda item: item[0])
    modifier_start = marker_start + len(marker)
    candidates = [
        item for item in objects
        if item is not destination
        and isinstance(item.get("start"), int)
        and isinstance(item.get("end"), int)
        and modifier_start <= item["start"]
        and item["end"] <= possessive
    ]
    if not candidates:
        return None
    modifier = deepcopy(candidates[-1])
    modifier.update({
        "relation_predicate": "supported_by",
        "relation_target_role": "destination",
        "relation_surface": text[marker_start:destination_start + len(str(destination.get("matched_alias") or ""))],
        "relation_span_start": marker_start,
        "relation_span_end": destination_start,
        "source": "relational_noun_phrase",
    })
    return modifier


def _roles(
    events: list[dict[str, Any]],
    objects: list[dict[str, Any]],
    context_entities: list[dict[str, Any]],
    text: str,
) -> dict[str, Any]:
    movable = [item for item in objects if any(token in set(item.get("functional_affordances", [])) for token in ("graspable", "movable", "graspable_candidate"))]
    supports = [item for item in objects if any(token in set(item.get("functional_affordances", [])) for token in ("support_object", "receive_object"))]
    held = [item for item in context_entities if item.get("focus_source") == "verified_holding_fact"]
    human_held = [
        item
        for item in context_entities
        if item.get("focus_source") == "verified_human_possession_fact"
    ]
    place_event = next((item for item in events if item["operator"] == "place_object"), None)
    handover_event = next((item for item in events if item["operator"] == "handover_object"), None)
    transport_event = next((item for item in events if item["operator"] == "transport_object"), None)
    placing = place_event is not None
    roles: dict[str, Any] = {}
    if placing:
        surface = str(place_event.get("matched_surface") or "")
        has_destination_connector = any(marker in surface for marker in ("到", "在"))
        restores_prior_relation = (
            "回" in surface
            or "归还" in surface
            or any(
                marker in text
                for marker in ("原桌", "原台面", "原先", "原来", "原处")
            )
        )
        before = [item for item in objects if item.get("end", 0) <= place_event["start"]]
        after = [item for item in objects if item.get("start", 0) >= place_event["end"]]
        destination_candidate = after[-1] if after else None
        destination_relation_object = _destination_relation_modifier(
            text, after, destination_candidate
        )
        movable_themes = [
            item for item in movable
            if not destination_relation_object
            or item.get("start") != destination_relation_object.get("start")
            or item.get("end") != destination_relation_object.get("end")
        ]
        prior_acquisition = next(
            (
                item for item in reversed(events)
                if item.get("start", 0) < place_event["start"]
                and item.get("operator") in {"grasp_object", "transport_object"}
            ),
            None,
        )
        acquired_theme = None
        if prior_acquisition:
            event_index = events.index(prior_acquisition)
            previous_event_end = events[event_index - 1]["end"] if event_index > 0 else 0
            following_event_start = events[event_index + 1]["start"] if event_index + 1 < len(events) else len(text)
            local_before = [
                item for item in movable
                if item.get("end", 0) <= prior_acquisition["start"]
                and item.get("start", 0) >= previous_event_end
            ]
            local_after = [
                item for item in movable
                if item.get("start", 0) >= prior_acquisition["end"]
                and item.get("end", len(text)) <= following_event_start
            ]
            acquisition_prefix = text[previous_event_end:prior_acquisition["start"]]
            if local_before and "把" in acquisition_prefix:
                acquired_theme = local_before[-1]
            elif local_after:
                acquired_theme = local_after[0]
            elif local_before:
                acquired_theme = local_before[-1]

        companion_mentions = []
        for item in before:
            if item is acquired_theme:
                continue
            start, end = int(item.get("start", 0)), int(item.get("end", 0))
            relation_prefix = text[max(0, start - 2):start]
            relation_suffix = text[end:place_event["start"]]
            if relation_prefix.endswith(("和", "与", "同")) and "一起" in relation_suffix:
                companion_mentions.append(item)
        if (has_destination_connector or restores_prior_relation) and after:
            roles["destination"] = deepcopy(destination_candidate)
            if destination_relation_object:
                roles["destination_relation_object"] = destination_relation_object
            if acquired_theme:
                roles["theme"] = deepcopy(acquired_theme)
            elif before:
                primary_before = [item for item in before if item not in companion_mentions]
                roles["theme"] = deepcopy((primary_before or before)[-1])
        elif surface == "放下" and after:
            roles["theme"] = deepcopy(after[0])
        elif movable_themes:
            roles["theme"] = deepcopy(acquired_theme or movable_themes[0])
        if companion_mentions:
            roles["companion"] = deepcopy(companion_mentions[0])
            roles["companion"]["semantic_relation"] = "co_located_with_theme_at_destination"
        if "theme" not in roles and len(held) == 1:
            roles["theme"] = {**deepcopy(held[0]), "binding_source": "implicit_unique_verified_holding_fact"}
        destination = roles.get("destination")
        if destination and isinstance(destination.get("start"), int):
            relation_scope = text[int(destination["start"]):]
            relation_scope = re.split(
                r"(?:然后|随后|之后|再|并且|同时|，|。|；)",
                relation_scope,
                maxsplit=1,
            )[0][:16]
            explicit_relation = next(
                (
                    relation
                    for markers, relation in (
                        (("上面", "上边", "上"), "on_support_surface"),
                        (("里面", "内部", "里"), "inside_container"),
                        (("旁边", "附近", "旁"), "near_landmark"),
                    )
                    if any(marker in relation_scope for marker in markers)
                ),
                None,
            )
            if explicit_relation:
                destination["spatial_relation"] = explicit_relation
                destination["spatial_relation_basis"] = "explicit_spatial_marker"
    else:
        if movable:
            roles["theme"] = deepcopy(movable[0])
        if supports:
            roles["destination"] = deepcopy(supports[-1])
    if objects and "theme" not in roles and not placing:
        roles["target"] = deepcopy(objects[0])
    navigation = next((item for item in events if item["operator"] == "navigate_to"), None)
    if navigation and objects:
        following = next(
            (item for item in events if item.get("start", 0) >= navigation.get("end", 0) and item is not navigation),
            None,
        )
        explicit_navigation_objects = [
            item for item in objects
            if item.get("start", -1) >= navigation.get("end", 0)
            and (not following or item.get("end", -1) <= following.get("start", 0))
        ]
        if explicit_navigation_objects:
            roles["destination"] = deepcopy(explicit_navigation_objects[-1])
        elif len(events) == 1:
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
    if transport_event:
        destination = roles.get("destination")
        if destination:
            alias = str(destination.get("matched_alias") or "")
            suffix = text[int(destination.get("end", 0)):] if isinstance(destination.get("end"), int) else ""
            if alias and suffix.startswith(("上", "上面", "上边")):
                destination["spatial_relation"] = "on_support_surface"
                destination["spatial_relation_basis"] = "explicit_spatial_marker"
            elif alias and suffix.startswith(("旁", "旁边", "附近")):
                destination["spatial_relation"] = "near_landmark"
                destination["spatial_relation_basis"] = "explicit_spatial_marker"
            elif alias and suffix.startswith(("里", "里面", "内部")):
                destination["spatial_relation"] = "inside_container"
                destination["spatial_relation_basis"] = "explicit_spatial_marker"
        else:
            complement = text[transport_event["end"]:]
            complement = re.sub(r"(?:里面|内部|附近|旁边|上面|上边|上|里|去)$", "", complement)
            if complement:
                roles["target_region"] = {
                    "matched_alias": complement,
                    "entity_type": "semantic_region",
                    "spatial_relation": "inside_semantic_region",
                    "source": "transport_result_complement",
                }
    source_possession_requested = bool(
        re.search(
            r"(?:拿|取|从)我(?:的)?手(?:里|上|中)|我手(?:里|上|中)(?:的|这只|这个)",
            text,
        )
    )
    if source_possession_requested and len(human_held) == 1:
        language_theme = deepcopy(roles.get("theme") or {})
        roles["theme"] = {
            **language_theme,
            **deepcopy(human_held[0]),
            "binding_source": "explicit_human_possession_language_plus_verified_relation",
        }
    return roles


def _restores_prior_relation(text: str, events: list[dict[str, Any]]) -> bool:
    return bool(
        any(
            item.get("operator") == "place_object"
            and any(
                marker in str(item.get("matched_surface") or "")
                for marker in ("回", "归还")
            )
            for item in events
        )
        or any(marker in text for marker in ("原先", "原来", "原处", "原桌", "原台面"))
    )


def _canonical_utterance(speech_act: str, query_type: str | None, events: list[dict[str, Any]], roles: dict[str, Any]) -> str | None:
    target = roles.get("theme") or roles.get("target") or roles.get("destination") or {}
    destination = roles.get("destination") or {}
    target_region = roles.get("target_region") or {}
    recipient = roles.get("recipient") or {}
    target_name = target.get("matched_alias") or target.get("label") or target.get("display_name")
    destination_name = destination.get("matched_alias") or destination.get("display_name")
    target_region_name = target_region.get("matched_alias") or target_region.get("display_name")
    recipient_name = recipient.get("matched_alias") or recipient.get("label") or recipient.get("display_name")
    if speech_act == "state_query":
        if query_type == "support_inventory" and target_name:
            return f"查看{target_name}上的当前对象"
        if query_type == "region_inventory":
            return f"查看{target_region_name or '当前区域'}中的对象"
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
        elif operator == "transport_object":
            transport_destination = destination_name or target_region_name
            if target_name and transport_destination and destination.get("spatial_relation") == "on_support_surface":
                part = f"把{target_name}放到{transport_destination}"
            elif target_name and transport_destination:
                part = f"把{target_name}带到{transport_destination}"
            else:
                part = None
        elif operator == "relocate_object":
            part = f"移开{target_name}" if target_name else "移开占用物"
        elif operator == "navigate_to" and destination_name:
            part = f"走到{destination_name}"
        elif operator == "observe_entity" and target_name:
            part = f"观察{target_name}"
        elif operator == "fill_container":
            part = f"给{target_name}接水" if target_name else "接水"
        else:
            part = event.get("canonical_surface")
            if part and target_name and len(events) == 1:
                part += target_name
        if part and part not in parts:
            parts.append(part)
    return "然后".join(parts) or None


def _unknown_surface(
    text: str,
    events: list[dict[str, Any]],
    objects: list[dict[str, Any]],
    reported_events: list[dict[str, Any]],
    historical_event_constraints: list[dict[str, Any]] | None = None,
    modifiers: list[dict[str, Any]] | None = None,
    semantic_attributes: list[dict[str, Any]] | None = None,
) -> str | None:
    residual = text
    spans = [
        (
            item.get("start", (item.get("span") or [None, None])[0]),
            item.get("end", (item.get("span") or [None, None])[1]),
        )
        for item in [
            *events,
            *objects,
            *reported_events,
            *(modifiers or []),
            *(semantic_attributes or []),
            *(
                {
                    "start": item.get("constraint_start"),
                    "end": item.get("constraint_end"),
                }
                for item in (historical_event_constraints or [])
            ),
        ]
        if isinstance(
            item.get("start", (item.get("span") or [None, None])[0]), int
        )
    ]
    for start, end in sorted(spans, reverse=True):
        residual = residual[:start] + (" " * (end - start)) + residual[end:]
    for word in sorted(FUNCTION_WORDS, key=len, reverse=True):
        residual = residual.replace(word, "")
    residual = re.sub(r"[\s，。！？、,.!?；;：:]+", "", residual)
    return residual or None


def _semantic_attribute_mentions(text: str) -> list[dict[str, Any]]:
    """Expose registered attribute spans without grounding them as facts."""
    candidates: list[dict[str, Any]] = []
    for concept in load_semantic_attribute_concepts().get(
        "attribute_concepts", []
    ):
        for value, aliases in concept.get("values", {}).items():
            for alias in sorted(aliases, key=len, reverse=True):
                for match in re.finditer(re.escape(alias), text):
                    candidates.append(
                        {
                            "concept_id": concept.get("concept_id"),
                            "value": value,
                            "start": match.start(),
                            "end": match.end(),
                            "candidate_only": True,
                            "runtime_fact_committed": False,
                        }
                    )
    return candidates


def compose_language_concepts(
    utterance: str,
    *,
    event_concepts: list[dict[str, Any]],
    object_concepts: list[dict[str, Any]],
    context_entities: list[dict[str, Any]] | None = None,
    learned_adapters: list[dict[str, Any]] | None = None,
    semantic_regions: list[dict[str, Any]] | None = None,
    _build_event_frames: bool = True,
) -> dict[str, Any]:
    normalized, input_normalizations = _normalize_language_text_with_audit(
        utterance
    )
    definition = _definition_candidate(normalized, event_concepts)
    objects = _object_mentions(normalized, object_concepts)
    region_mentions = [
        {
            "entity_ref": region.get("region_id"),
            "value_ref": region.get("region_id"),
            "entity_type": "semantic_region",
            "display_name": region.get("label") or region.get("region_id"),
            "matched_alias": alias,
            "source": "semantic_region_registry_match",
        }
        for region in (semantic_regions or [])
        for alias in [str(region.get("label") or "")]
        if alias and alias in normalized
    ]
    events = _infer_argument_order_events(
        normalized,
        _event_mentions(normalized, event_concepts, learned_adapters or []),
        objects,
    )
    reference_resolution = resolve_references(
        normalized,
        objects,
        context_entities or [],
        events,
    )
    structured_reference_mentions = resolved_reference_mentions(
        reference_resolution, context_entities or []
    )
    for mention in structured_reference_mentions:
        if not any(
            item.get("start") == mention.get("start")
            and item.get("end") == mention.get("end")
            for item in objects
        ):
            objects.append(mention)
    structured_reference_records = [
        *reference_resolution.get("resolved_references", []),
        *reference_resolution.get("unresolved", []),
    ]
    if structured_reference_records:
        unresolved = []
        unresolved_references = reference_resolution.get("unresolved", [])
        if unresolved_references:
            fallback_objects, fallback_unresolved = _resolve_pronouns(
                normalized, objects, context_entities or []
            )
            appended = fallback_objects[len(objects) :]
            if appended and not fallback_unresolved:
                objects = fallback_objects
                resolved_record = deepcopy(unresolved_references[0])
                resolved_record.update(
                    {
                        "selected": None,
                        "selected_concept_id": appended[0].get("concept_id"),
                        "unique": True,
                        "requires_confirmation": False,
                        "binding_kind": "intra_turn_concept_coreference",
                        "grounding_required": True,
                    }
                )
                reference_resolution.setdefault(
                    "resolved_references", []
                ).append(resolved_record)
                reference_resolution["unresolved"] = []
                reference_resolution["inquiry_contracts"] = []
            else:
                unresolved = ["pronoun_reference_not_unique"]
    else:
        # Compatibility fallback for expressions outside the structured
        # resolver. Never run both resolvers over the same span: duplicate
        # theme mentions corrupt temporal relative-clause cardinality.
        objects, unresolved = _resolve_pronouns(
            normalized, objects, context_entities or []
        )
    reference_resolution["referent_expressions"] = reference_resolution_referents(
        reference_resolution, context_entities or []
    )
    events, event_dependencies = _resolve_serial_event_dependencies(normalized, events, objects)
    events, historical_event_constraints = _extract_historical_event_constraints(
        normalized, events, objects
    )
    discourse_roles = _discourse_roles(normalized)
    if discourse_roles.get("navigation_landmark"):
        unresolved = [
            slot for slot in unresolved if slot != "pronoun_reference_not_unique"
        ]
    reported_events = _reported_events(normalized)
    ellipsis_candidates = _ellipsis_candidates(normalized)
    speech_act = _speech_act(normalized, events, definition)
    if (
        speech_act == "unknown"
        and discourse_roles.get("beneficiary")
        and ellipsis_candidates
    ):
        speech_act = "task_request"
    query_type = (
        _query_type(normalized, events, objects, region_mentions)
        if speech_act == "state_query"
        else None
    )
    if query_type in {"support_inventory", "region_inventory"}:
        events = [
            {
                "operator": "observe_entity",
                "concept_id": "factory_event_observe",
                "matched_surface": normalized,
                "canonical_surface": "观察",
                "start": 0,
                "end": len(normalized),
                "source": "state_query_operator_inference",
            }
        ]
        event_dependencies = []
        unresolved = [
            slot
            for slot in unresolved
            if slot != "pronoun_reference_not_unique"
        ]
    context_entities = context_entities or []
    roles = _roles(events, objects, context_entities, normalized)
    if (
        discourse_roles.get("navigation_landmark")
        and any(item.get("operator") == "navigate_to" for item in events)
    ):
        roles["destination"] = {
            "matched_alias": "我这边",
            "entity_type": "human_recipient",
            "reference": "human_speaker",
            "spatial_relation": "near_landmark",
            "spatial_relation_basis": "explicit_deictic_human_proximity",
            "source": "discourse_navigation_landmark",
        }
    if query_type == "region_inventory":
        roles["target_region"] = deepcopy(region_mentions[0]) if len(
            region_mentions
        ) == 1 else {
            "reference": "current_executor_region",
            "entity_type": "semantic_region",
            "source": "deictic_current_region_query",
        }
    if (
        discourse_roles.get("recipient")
        and not roles.get("recipient")
        and any(
            item.get("operator")
            in {"fill_container", "handover_object", "transport_object"}
            for item in events
        )
    ):
        roles["recipient"] = {
            "matched_alias": "我",
            "entity_type": "human_recipient",
            "reference": discourse_roles["recipient"].get("reference"),
            "source": "deictic_discourse_recipient_role",
        }
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
        direction_scope = normalized
        for discourse_marker in ("随后", "然后", "之后", "以后", "而后", "先后"):
            direction_scope = direction_scope.replace(discourse_marker, "")
        relative_match = re.search(r"(?:往|向)?(?:你|机器人|自己)?(?:的)?(前|后|左|右)(?:边|方)?", direction_scope)
        if relative_match:
            relative_direction = {"前": "forward", "后": "backward", "左": "left", "右": "right"}[relative_match.group(1)]
    if relative_direction:
        roles["direction"] = {"reference": "executor_body_frame", "value": relative_direction, "source": "body_relative_language"}

    modifier_contract = compile_modifier_contract(normalized, events)
    semantic_attribute_mentions = _semantic_attribute_mentions(normalized)

    if speech_act == "unknown":
        unresolved.append("event_or_query_concept_not_resolved")
    if speech_act == "state_query" and query_type is None:
        unresolved.append("query_relation_not_resolved")
    if speech_act == "task_request" and not events:
        unresolved.append("event_operator_not_resolved")
    requires_object = query_type != "region_inventory" and any(item["operator"] in {
        "observe_entity", "grasp_object", "release_object", "place_object",
        "fill_container",
        "handover_object",
        "transport_object",
        "relocate_object",
        "apply_directional_force", "change_open_state", "change_device_activation", "remove_surface_contaminant",
    } for item in events) or (any(item["operator"] == "navigate_to" for item in events) and not relative_direction)
    navigation_destination_grounded = bool(
        any(item["operator"] == "navigate_to" for item in events)
        and roles.get("destination")
    )
    if (
        requires_object
        and not objects
        and not (roles.get("theme") or roles.get("target"))
        and not navigation_destination_grounded
    ):
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

    unknown_surface = _unknown_surface(
        normalized,
        events,
        objects,
        reported_events,
        historical_event_constraints,
        modifier_contract.get("modifiers", []),
        semantic_attribute_mentions,
    )
    if (
        discourse_roles.get("navigation_landmark")
        and unknown_surface in {"这", "我这", "这边", "这里", "身边", "旁边"}
    ):
        unknown_surface = None
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
    result = {
        "schema_version": "1.0.0",
        "utterance": utterance,
        "normalized_utterance": normalized,
        "input_normalizations": deepcopy(input_normalizations),
        "speech_act": speech_act,
        "query_type": query_type,
        "event_candidates": deepcopy(events),
        "entity_mentions": deepcopy(objects),
        "semantic_region_mentions": deepcopy(region_mentions),
        "role_bindings": deepcopy(roles),
        "discourse_roles": discourse_roles,
        "reported_event_candidates": deepcopy(reported_events),
        "event_dependencies": deepcopy(event_dependencies),
        "historical_event_constraints": deepcopy(historical_event_constraints),
        "ellipsis_candidates": ellipsis_candidates,
        "reference_resolution": deepcopy(reference_resolution),
        "salience_projection": deepcopy(
            reference_resolution.get("salience_projection")
        ),
        "modifier_contract": deepcopy(modifier_contract),
        "semantic_attribute_mentions": deepcopy(semantic_attribute_mentions),
        "modifiers": {
            "negated": speech_act == "prohibition",
            "ability_or_possibility": any(marker in normalized for marker in ("能", "可以", "得见", "得到", "能不能", "可不可以")),
            "completed_or_resultative": any(marker in normalized for marker in ("到了", "看见", "看到", "完成", "已经")),
            "current_scope": not any(marker in normalized for marker in ("昨天", "以前", "曾经")),
            "body_relative_direction": relative_direction,
            "restore_prior_relation": _restores_prior_relation(normalized, events),
        },
        "canonical_utterance": canonical,
        "canonical_frame": {
            "speech_act": speech_act,
            "operators": [item["operator"] for item in events],
            "query_type": query_type,
            "roles": deepcopy(roles),
            "goal_relation": "human_received_filled_container" if (
                any(item["operator"] == "fill_container" for item in events)
                and roles.get("recipient")
            ) else "object_supported_at_destination" if (
                any(item["operator"] == "place_object" for item in events)
                or (
                    any(item["operator"] == "transport_object" for item in events)
                    and roles.get("destination", {}).get("spatial_relation") == "on_support_surface"
                )
            ) else (
                "object_received_by_recipient" if any(item["operator"] == "handover_object" for item in events) else (
                    "object_at_target_region" if any(item["operator"] == "transport_object" for item in events) else (
                        "container_filled" if any(item["operator"] == "fill_container" for item in events) else (
                            "object_in_gripper" if any(item["operator"] == "grasp_object" for item in events) else None
                        )
                    )
                )
            ),
            "world_scope": "current_world_revision",
            "destination_binding_policy": (
                "most_recent_verified_support_relation"
                if _restores_prior_relation(normalized, events)
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
    result["event_frames"] = []
    result["discourse_event_graph"] = {
        "nodes": [],
        "edges": [],
        "raw_text_included": False,
        "candidate_only": True,
        "runtime_fact_committed": False,
    }
    if _build_event_frames:
        clause_frames = []
        for clause_spec in _discourse_clause_specs(utterance):
            clause = clause_spec["surface"]
            frame = compose_language_concepts(
                clause,
                event_concepts=event_concepts,
                object_concepts=object_concepts,
                context_entities=context_entities,
                learned_adapters=learned_adapters,
                semantic_regions=semantic_regions,
                _build_event_frames=False,
            )
            if frame.get("speech_act") != "task_request" or not frame.get("event_candidates"):
                continue
            frame["frame_id"] = f"event_frame_{len(clause_frames)}"
            frame["clause_index"] = len(clause_frames)
            frame["incoming_discourse_relation"] = clause_spec[
                "incoming_relation"
            ]
            frame["discourse_polarity"] = clause_spec.get(
                "discourse_polarity", "asserted"
            )
            clause_frames.append(frame)
        if len(clause_frames) > 1:
            result["event_frames"] = _propagate_event_frame_roles(clause_frames)
            result["discourse_event_graph"] = _build_discourse_event_graph(
                result["event_frames"]
            )
    result["modifier_contract"] = compile_modifier_contract(
        normalized,
        result.get("event_candidates", []),
        discourse_graph=result.get("discourse_event_graph"),
    )
    for index, event in enumerate(result.get("event_candidates", [])):
        event["modifiers"] = modifiers_for_event(
            result["modifier_contract"], index
        )
    result["canonical_frame"]["modifiers"] = deepcopy(
        result["modifier_contract"]
    )
    return result
