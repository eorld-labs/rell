from __future__ import annotations

from copy import deepcopy
from typing import Any

from .machine_dictionary import dictionary_index


OPERATOR_PHRASES = {
    "observe_entity": "观察{theme}",
    "navigate_to": "接近{destination}",
    "grasp_object": "拿起{theme}",
    "fill_container": "给{theme}盛装液体",
    "place_object": "把{theme}放到{destination}",
    "handover_object": "把{theme}交给{recipient}",
    "transport_object": "把{theme}带到{destination}",
    "relocate_object": "移开{theme}",
    "release_object": "释放{theme}",
}

ROLE_NAMES = {
    "theme": "操作对象",
    "target": "目标对象",
    "destination": "目标位置",
    "recipient": "接收者",
    "source": "来源",
}

QUERY_PHRASES = {
    "holding_state": "机器人当前持有什么",
    "object_location": "目标对象当前在哪里",
    "object_visibility": "当前是否能观察到目标对象",
    "object_presence": "当前空间是否存在目标对象",
    "support_inventory": "目标承载面上当前有哪些对象",
    "region_inventory": "当前区域里有哪些对象",
    "current_action": "机器人当前正在执行什么",
    "next_step": "当前任务下一步是什么",
}


def _resolved_roles(bundle: dict[str, Any]) -> dict[str, str]:
    return {
        role: binding["entity_ref"]
        for role, binding in (
            (bundle.get("grounded_causal_graph") or {}).get("role_bindings") or {}
        ).items()
        if binding.get("status") == "resolved" and binding.get("entity_ref")
    }


def _label(ref: str | None, labels: dict[str, str], fallback: str) -> str:
    return labels.get(str(ref), fallback) if ref else fallback


def _event_plan(
    bundle: dict[str, Any], roles: dict[str, str], labels: dict[str, str]
) -> list[str]:
    situated = bundle.get("situated_event_graph") or {}
    scopes = [
        scope
        for scope in situated.get("event_scopes", [])
        if scope.get("discourse_polarity", "asserted") != "rejected"
    ]
    operators = (
        [operator for scope in scopes for operator in scope.get("operators", [])]
        if scopes
        else [item.get("operator") for item in situated.get("events", [])]
    )
    values = {
        "theme": _label(roles.get("theme"), labels, "当前对象"),
        "destination": _label(roles.get("destination"), labels, "目标位置"),
        "recipient": _label(roles.get("recipient"), labels, "接收者"),
        "source": _label(roles.get("source"), labels, "来源"),
    }
    phrases = []
    for operator in operators:
        template = OPERATOR_PHRASES.get(operator)
        phrase = template.format(**values) if template else f"执行{operator}"
        if phrase not in phrases:
            phrases.append(phrase)
    return phrases


def _goal_phrase(
    goal_relation: str | None,
    roles: dict[str, str],
    labels: dict[str, str],
) -> str:
    theme = _label(roles.get("theme"), labels, "目标对象")
    destination = _label(roles.get("destination"), labels, "目标位置")
    recipient = _label(roles.get("recipient"), labels, "接收者")
    return {
        "object_supported_at_destination": f"{theme}由{destination}稳定承载",
        "filled_container_supported_at_destination": (
            f"{theme}装有液体并由{destination}稳定承载"
        ),
        "human_received_filled_container": f"{recipient}收到已经装好液体的{theme}",
        "object_received_by_recipient": f"{recipient}收到{theme}",
        "recipient_received_payload_carrier_retained": (
            f"{recipient}收到载荷，承载体仍由机器人保留"
        ),
        "container_filled": f"{theme}达到目标盛装状态",
        "object_in_gripper": f"{theme}进入执行器夹持状态",
        "object_at_target_region": f"{theme}到达{destination}",
    }.get(goal_relation, f"建立目标关系 {goal_relation}" if goal_relation else "完成当前请求")


def realize_rcir_dialogue(
    bundle: dict[str, Any],
    *,
    entity_labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Project the authoritative machine representation into human language."""
    labels = entity_labels or {}
    situated = bundle.get("situated_event_graph") or {}
    grounded = bundle.get("grounded_causal_graph") or {}
    ledger = bundle.get("world_fact_ledger") or {}
    roles = _resolved_roles(bundle)
    goal_relation = grounded.get("goal_relation") or (
        situated.get("goal") or {}
    ).get("goal_relation")
    query_type = (situated.get("query") or {}).get("query_type")
    dictionary = dictionary_index()
    speech_act = situated.get("speech_act")
    communication_contracts = situated.get("communication_contracts") or {}
    speech_act_ref = communication_contracts.get("speech_act_ref")
    query_contract_ref = communication_contracts.get("query_contract_ref")
    if speech_act_ref and (
        (dictionary.get(speech_act_ref) or {}).get("semantic_value")
        != speech_act
    ):
        raise AssertionError("reverse_dialogue_speech_act_ref_mismatch")
    if query_contract_ref and (
        (dictionary.get(query_contract_ref) or {}).get("semantic_value")
        != query_type
    ):
        raise AssertionError("reverse_dialogue_query_contract_ref_mismatch")
    response_act_ref = (
        "speech_act.inform" if "speech_act.inform" in dictionary else None
    )
    plan = _event_plan(bundle, roles, labels)
    unresolved_roles = [
        item.get("role")
        for item in grounded.get("open_conditions", [])
        if item.get("kind") == "unresolved_role" and item.get("role")
    ]
    goal_phrase = _goal_phrase(goal_relation, roles, labels)
    if situated.get("speech_act") == "state_query" and query_type:
        query_phrase = QUERY_PHRASES.get(
            query_type, f"当前状态中的 {query_type}"
        )
        response = (
            f"我理解你在询问：{query_phrase}。"
            "回答只读取当前世界状态与观察证据，不会把查询当成动作任务。"
        )
    elif unresolved_roles:
        missing = "、".join(
            ROLE_NAMES.get(role, str(role)) for role in unresolved_roles
        )
        response = f"我理解的目标是：{goal_phrase}。还需要确定：{missing}。"
    elif plan:
        response = (
            f"我理解的目标是：{goal_phrase}。"
            f"当前步骤是：{'，然后'.join(plan)}；每一步仍按当前世界状态验真。"
        )
    else:
        response = f"我理解的目标是：{goal_phrase}；结果仍需按当前世界状态验真。"
    return {
        "schema_version": "1.0.0",
        "source_bundle_ref": bundle.get("bundle_id"),
        "situated_graph_ref": situated.get("graph_id"),
        "grounded_graph_ref": grounded.get("graph_id"),
        "fact_authority_ref": ledger.get("ledger_id"),
        "world_revision": bundle.get("world_revision"),
        "semantic_authority_ref": (
            bundle.get("semantic_authority") or {}
        ).get("admission_id"),
        "semantic_source_kind": (
            bundle.get("semantic_authority") or {}
        ).get("authoritative_semantic_source"),
        "goal_relation": goal_relation,
        "speech_act_ref": speech_act_ref,
        "query_type": query_type,
        "query_contract_ref": query_contract_ref,
        "response_act_ref": response_act_ref,
        "resolved_entity_refs": deepcopy(roles),
        "event_plan": plan,
        "unresolved_roles": unresolved_roles,
        "human_response": response,
        "generated_from_rcir_only": True,
        "generated_from_shared_dictionary_entries": True,
        "dictionary_refs_reused_without_reinterpretation": True,
        "surface_text_reparsed": False,
        "runtime_fact_committed": False,
        "direct_execution_allowed": False,
    }


__all__ = ["realize_rcir_dialogue"]
