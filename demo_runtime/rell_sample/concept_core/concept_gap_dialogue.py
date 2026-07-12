from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from time import perf_counter_ns
from typing import Any


SLOT_PRIORITY = ["target_entity", "desired_postcondition", "verification_condition"]


def _action_focus_text(text: str) -> str:
    focused = text.strip()
    conditional_prefix = re.match(r"^(?:如果|当).+?(?:时[，,]?|[，,](?:就|则)?|就|则)", focused)
    if conditional_prefix:
        focused = focused[conditional_prefix.end():]
    return re.split(
        r"[，,；;。]|让|使得?|变成|变为|直到|看到|观察到|检测到|确认|完成后|结果是|目标是|以.+?(?:为验真条件|为成功标准|为准)",
        focused,
        maxsplit=1,
    )[0]


def extract_compositional_semantics(text: str) -> dict[str, Any]:
    normalized = text.strip(" ，。！？,.!?；;：:")
    preconditions: list[str] = []
    precondition_match = re.search(r"(?:如果|当|需要)(.+?)(?:时|，|,|就|则)", normalized)
    if precondition_match:
        preconditions.append(precondition_match.group(1).strip())

    verification = None
    verification_patterns = [
        r"((?:看到|观察到|检测到|确认到?).+?)(?:就算|才算|算作|视为)(?:完成|成功|成立)",
        r"(?:直到)(.+?)(?:为止|才停止|才算完成)",
        r"(?:以)(.+?)(?:为验真条件|为成功标准|为准)",
    ]
    for pattern in verification_patterns:
        match = re.search(pattern, normalized)
        if match:
            verification = match.group(1).strip(" ，,；;")
            break

    postcondition = None
    postcondition_match = re.search(
        r"(?:让|使|使得|变成|变为)(.+?)(?=，|,|；|;|直到|看到|观察到|检测到|确认|$)",
        normalized,
    )
    if postcondition_match:
        postcondition = postcondition_match.group(1).strip()
    elif re.search(r"(?:完成后|结果是|目标是)(.+?)(?=，|,|；|;|看到|观察到|检测到|确认|$)", normalized):
        postcondition = re.search(
            r"(?:完成后|结果是|目标是)(.+?)(?=，|,|；|;|看到|观察到|检测到|确认|$)",
            normalized,
        ).group(1).strip()
    if not postcondition and verification and ("直到" in normalized or re.search(r"以.+?(?:为成功标准|为准)", normalized)):
        postcondition = verification

    relation_markers = []
    for marker, relation in [
        ("在", "spatial_membership_or_support"),
        ("里面", "containment"),
        ("上面", "support"),
        ("一起", "co_location"),
        ("同一个", "shared_region_or_group"),
        ("达到", "threshold_or_target_state"),
    ]:
        if marker in normalized:
            relation_markers.append(relation)
    return {
        "precondition_descriptions": preconditions,
        "desired_postcondition": postcondition,
        "verification_condition": verification,
        "relation_candidates": list(dict.fromkeys(relation_markers)),
        "parser_policy": "explicit_connectors_only_candidate_semantics",
    }


def _resolve_local_pronouns(value: str | None, target: dict[str, Any] | None) -> str | None:
    if not value or not target:
        return value
    label = target["label"]
    return re.sub(r"(?<!其)(它|这个对象|该对象)", label, value)


def _known_entity_mentions(
    text: str,
    runtime_objects: list[dict[str, Any]],
    object_concepts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mentions = []
    for entity in runtime_objects:
        matching_concepts = [item for item in object_concepts if entity.get("kind") in item.get("compatible_kinds", [])]
        forms = [entity.get("label", ""), *[alias for item in matching_concepts for alias in item.get("aliases", [])]]
        matched = [(text.find(form), form) for form in forms if form and form in text]
        if matched:
            position, surface = min(matched)
            mentions.append({"entity_ref": entity["entity_id"], "label": entity["label"], "surface_form": surface, "position": position})
    return sorted(mentions, key=lambda item: item["position"])


def _extract_unknown_action_surface(text: str, entity_mentions: list[dict[str, Any]]) -> str:
    action_clause = _action_focus_text(text)
    residual = action_clause
    for mention in sorted(entity_mentions, key=lambda item: len(item["surface_form"]), reverse=True):
        residual = residual.replace(mention["surface_form"], "")
    for token in ["请", "你", "帮我", "把", "将", "一下", "给我", "去", "这个", "那个"]:
        residual = residual.replace(token, "")
    return residual.strip(" ，。！？,.!?；;：:") or "unknown_action"


def _next_missing_slot(slots: dict[str, Any]) -> str | None:
    return next((slot for slot in SLOT_PRIORITY if not slots.get(slot)), None)


def _question_for(slot: str, session: dict[str, Any]) -> str:
    slots = session["slots"]
    target = (slots.get("target_entity") or {}).get("label", "这个任务对象")
    action = session.get("unknown_action_surface") or "这个动作"
    if slot == "target_entity":
        return f"我还没确定“{action}”要改变哪个对象。请指出对象名称或当前空间中的对象。"
    if slot == "desired_postcondition":
        return f"我识别到对象是{target}，但“{action}”不是出厂事件概念。请只告诉我：完成后，{target}的什么状态或关系应当发生变化？"
    return f"目标结果暂记为“{slots['desired_postcondition']}”。我还需要知道：看到或测到什么，才算这个结果真的成立？"


def start_concept_gap_dialogue(
    *,
    utterance: str,
    runtime_objects: list[dict[str, Any]],
    object_concepts: list[dict[str, Any]],
    world_revision: int,
) -> dict[str, Any]:
    started_ns = perf_counter_ns()
    mentions = _known_entity_mentions(utterance, runtime_objects, object_concepts)
    action_mentions = _known_entity_mentions(_action_focus_text(utterance), runtime_objects, object_concepts)
    target = action_mentions[0] if len(action_mentions) == 1 else None
    composition = extract_compositional_semantics(utterance)
    composition["desired_postcondition"] = _resolve_local_pronouns(composition["desired_postcondition"], target)
    composition["verification_condition"] = _resolve_local_pronouns(composition["verification_condition"], target)
    dialogue_id = "gap_dialogue_" + hashlib.sha1(f"{utterance}|{world_revision}".encode("utf-8")).hexdigest()[:12]
    dialogue = {
        "dialogue_id": dialogue_id,
        "status": "collecting_minimum_causal_contract",
        "source_utterance": utterance,
        "unknown_action_surface": _extract_unknown_action_surface(utterance, mentions),
        "slots": {
            "target_entity": deepcopy(target),
            "desired_postcondition": composition["desired_postcondition"],
            "verification_condition": composition["verification_condition"],
            "precondition_descriptions": composition["precondition_descriptions"],
        },
        "candidate_entities": deepcopy(mentions),
        "action_target_candidates": deepcopy(action_mentions),
        "turns": [{"speaker": "human", "text": utterance, "slot": "source_utterance"}],
        "world_revision_at_start": world_revision,
        "candidate_only": True,
        "direct_execution_allowed": False,
        "compositional_analysis": composition,
    }
    missing_slot = _next_missing_slot(dialogue["slots"])
    if missing_slot is None:
        dialogue["pending_slot"] = None
        compiled = _compile_temporary_contract(dialogue, world_revision)
        return {
            "dialogue": compiled["dialogue"],
            "prompt": compiled["prompt"],
            "compiled_contract": compiled["compiled_contract"],
            "analysis": {
                "recognized_entities": deepcopy(mentions),
                "unknown_action_surface": dialogue["unknown_action_surface"],
                "known": SLOT_PRIORITY,
                "unknown": [],
                "compositional_analysis": composition,
                "question_selection_policy": "no_question_all_minimum_causal_slots_explicit",
                "analysis_ms": round((perf_counter_ns() - started_ns) / 1_000_000, 4),
            },
        }
    question = _question_for(missing_slot, dialogue)
    dialogue["pending_slot"] = missing_slot
    dialogue["turns"].append({"speaker": "robot", "text": question, "slot": missing_slot})
    elapsed_ms = round((perf_counter_ns() - started_ns) / 1_000_000, 4)
    return {
        "dialogue": dialogue,
        "prompt": question,
        "analysis": {
            "recognized_entities": deepcopy(mentions),
            "unknown_action_surface": dialogue["unknown_action_surface"],
            "known": ["target_entity"] if target else [],
            "unknown": [slot for slot in SLOT_PRIORITY if not dialogue["slots"].get(slot)],
            "compositional_analysis": composition,
            "question_selection_policy": "ask_highest_priority_missing_causal_slot",
            "analysis_ms": elapsed_ms,
        },
    }


def continue_concept_gap_dialogue(
    dialogue: dict[str, Any],
    *,
    answer: str,
    runtime_objects: list[dict[str, Any]],
    object_concepts: list[dict[str, Any]],
    current_world_revision: int,
) -> dict[str, Any]:
    started_ns = perf_counter_ns()
    updated = deepcopy(dialogue)
    pending_slot = updated.get("pending_slot")
    updated["turns"].append({"speaker": "human", "text": answer, "slot": pending_slot})
    if pending_slot == "target_entity":
        mentions = _known_entity_mentions(answer, runtime_objects, object_concepts)
        if len(mentions) == 1:
            updated["slots"]["target_entity"] = mentions[0]
            updated["slots"]["desired_postcondition"] = _resolve_local_pronouns(updated["slots"].get("desired_postcondition"), mentions[0])
            updated["slots"]["verification_condition"] = _resolve_local_pronouns(updated["slots"].get("verification_condition"), mentions[0])
        else:
            question = "这条回答仍未唯一对应当前空间中的一个对象。请直接说对象名称，例如苹果、杯子或操作台。"
            updated["turns"].append({"speaker": "robot", "text": question, "slot": pending_slot})
            return {"dialogue": updated, "prompt": question, "compiled_contract": None}
    elif pending_slot in {"desired_postcondition", "verification_condition"}:
        normalized = answer.strip(" ，。！？,.!?；;：:")
        if not normalized:
            question = _question_for(pending_slot, updated)
            return {"dialogue": updated, "prompt": question, "compiled_contract": None}
        composition = extract_compositional_semantics(normalized)
        if pending_slot == "desired_postcondition":
            target = updated["slots"].get("target_entity")
            updated["slots"]["desired_postcondition"] = _resolve_local_pronouns(composition["desired_postcondition"] or normalized, target)
            if composition["verification_condition"]:
                updated["slots"]["verification_condition"] = _resolve_local_pronouns(composition["verification_condition"], target)
            updated["slots"]["precondition_descriptions"] = list(dict.fromkeys(
                updated["slots"].get("precondition_descriptions", []) + composition["precondition_descriptions"]
            ))
        else:
            updated["slots"][pending_slot] = _resolve_local_pronouns(
                composition["verification_condition"] or normalized,
                updated["slots"].get("target_entity"),
            )

    next_slot = _next_missing_slot(updated["slots"])
    if next_slot:
        question = _question_for(next_slot, updated)
        updated["pending_slot"] = next_slot
        updated["turns"].append({"speaker": "robot", "text": question, "slot": next_slot})
        return {
            "dialogue": updated,
            "prompt": question,
            "compiled_contract": None,
            "analysis_ms": round((perf_counter_ns() - started_ns) / 1_000_000, 4),
        }

    compiled = _compile_temporary_contract(updated, current_world_revision)
    compiled["analysis_ms"] = round((perf_counter_ns() - started_ns) / 1_000_000, 4)
    return compiled


def _compile_temporary_contract(dialogue: dict[str, Any], current_world_revision: int) -> dict[str, Any]:
    updated = deepcopy(dialogue)
    target = updated["slots"]["target_entity"]
    fact_digest = hashlib.sha1(updated["slots"]["desired_postcondition"].encode("utf-8")).hexdigest()[:10]
    operator_digest = hashlib.sha1(updated["unknown_action_surface"].encode("utf-8")).hexdigest()[:10]
    contract = {
        "schema_version": "1.0.0",
        "concept_id": "temporary_concept_" + operator_digest,
        "operator": "temporary_operator_" + operator_digest,
        "language_trigger": updated["unknown_action_surface"],
        "semantic_roles": {
            "target": {
                "role": "target",
                "entity_ref": target["entity_ref"],
                "surface_form": target["surface_form"],
                "binding_scope": "current_dialogue_and_world_revision_only",
            },
        },
        "effect_contract": {
            "requires": ["target_grounded"] + [
                "human_described_precondition:" + item
                for item in updated["slots"].get("precondition_descriptions", [])
            ],
            "produces": ["temporary_goal_fact_" + fact_digest],
            "destroys": [],
            "verification": ["human_described_verification:" + updated["slots"]["verification_condition"]],
            "human_readable_postcondition": updated["slots"]["desired_postcondition"],
        },
        "knowledge_boundary": {
            "operator_mechanism_known": False,
            "goal_and_verification_understood": True,
            "execution_experience_available": False,
            "requires_embodied_teaching": True,
            "not_promoted_to_factory_library": True,
        },
        "world_revision": current_world_revision,
        "candidate_only": True,
        "direct_execution_allowed": False,
        "must_reenter_orchestration_layer": True,
    }
    updated["status"] = "temporary_effect_contract_compiled"
    updated["pending_slot"] = None
    updated["compiled_contract"] = deepcopy(contract)
    prompt = (
        f"我现在理解了目标：{target['label']}需要达到“{updated['slots']['desired_postcondition']}”，"
        f"并以“{updated['slots']['verification_condition']}”验真；但我仍不知道实现这一跃迁的物理机制和当前本体过程。"
        "这个临时契约不会直接执行，也不会写入出厂库。你现在可以进入真人教学，让我观察一次并自主复做。"
    )
    updated["turns"].append({"speaker": "robot", "text": prompt, "slot": "contract_summary"})
    return {
        "dialogue": updated,
        "prompt": prompt,
        "compiled_contract": contract,
    }
