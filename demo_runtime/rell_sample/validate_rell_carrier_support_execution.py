from __future__ import annotations

from embodied_scene import SESSIONS, _compose_session_language, begin_motion_command, start_session
from validate_water_delivery_loop import drain_service_with_confirmations


def main() -> None:
    session = start_session("home_humanoid", "hospitality_guest")
    session_id = session["session_id"]
    utterance = "把高脚杯放进托盘"

    analysis = _compose_session_language(SESSIONS[session_id], utterance)
    roles = analysis.get("role_bindings") or {}
    assert (roles.get("theme") or {}).get("entity_ref") == "glass_tall", roles
    assert (roles.get("destination") or {}).get("entity_ref") == "wooden_tray", roles
    assert (roles.get("destination") or {}).get("spatial_relation") == "inside_container", roles

    workset = (
        ((analysis.get("rcir") or {}).get("grounded_causal_graph") or {}).get(
            "relation_hypothesis_workset"
        )
        or {}
    )
    assert workset.get("status") == "resolved_unique_candidate", workset
    candidates = workset.get("candidates") or []
    assert len(candidates) == 1 and candidates[0].get("name") == "supported_by", candidates
    assert (
        (candidates[0].get("provenance") or {}).get("inference_rule")
        == "inside_region_language_normalized_by_carrier_affordance"
    ), candidates[0]
    assert analysis.get("runtime_fact_committed") is False

    outcomes = drain_service_with_confirmations(
        session_id, begin_motion_command(session_id, utterance)
    )
    assert [item.get("terminal_fact") for item in outcomes] == [
        "target_object_in_gripper",
        "object_supported_at_destination",
    ], outcomes
    assert all(item.get("status") == "fact_established" for item in outcomes), outcomes

    live = SESSIONS[session_id]
    objects = {item["entity_id"]: item for item in live["runtime_objects"]}
    assert objects["glass_tall"].get("support_ref") == "wooden_tray", objects["glass_tall"]
    facts = [
        fact
        for fact in live["world_fact_ledger"]["facts"]
        if fact.get("subject") == "glass_tall"
        and fact.get("object") == "wooden_tray"
    ]
    assert len(facts) == 1 and facts[0].get("predicate") == "supported_by", facts
    assert not any(fact.get("predicate") == "contained_in" for fact in facts), facts
    evidence = next(
        item
        for item in live["world_fact_ledger"]["evidence"]
        if item.get("envelope_id") == facts[0].get("evidence_ref")
    )
    assert evidence.get("source_type") == "p016_physical_verification", evidence
    assert (evidence.get("qualification") or {}).get("verifier") == "P016", evidence

    query = begin_motion_command(session_id, "托盘上有什么")
    answer = query.get("immediate_result") or query
    assert answer.get("status") == "support_inventory_state_answered", answer
    groups = answer.get("inventory_groups") or []
    assert len(groups) == 1 and groups[0].get("support_entity_ref") == "wooden_tray", groups
    assert groups[0].get("entity_refs") == ["glass_tall"], groups
    assert (answer.get("state_evidence") or {}).get("predicate") == "supported_by", answer
    assert not any(
        fact.get("predicate") == "supports"
        for fact in live["world_fact_ledger"]["facts"]
    ), "inverse query must not create a second fact source"

    print(
        "RELL 承载关系执行校验通过：放进托盘按可供性正规化为 supported_by，"
        "经 P018 执行、P016 回写，并由同一事实逆向回答 supports 查询。"
    )


if __name__ == "__main__":
    main()
