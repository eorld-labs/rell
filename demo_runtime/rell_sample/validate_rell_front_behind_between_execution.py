from __future__ import annotations

from embodied_scene import begin_motion_command, start_session
from validate_water_delivery_loop import drain_service


def main() -> None:
    for utterance, relation in (("站到我前面", "in_front_of"), ("站到我后面", "behind")):
        session = start_session("home_humanoid", "hospitality_guest")
        blocked = begin_motion_command(session["session_id"], utterance)
        immediate = blocked.get("immediate_result") or blocked
        assert blocked.get("status") == "contextual_spatial_motion_blocked", blocked
        assert immediate.get("reason") == "no_verified_route_to_relative_spatial_region", immediate
        contract = immediate.get("relative_spatial_execution_contract") or {}
        assert contract.get("relation") == relation
        assert contract.get("control_gateway") == "P018" and contract.get("verification_gateway") == "P016"
        assert immediate.get("frames") == []

    session = start_session("home_humanoid", "hospitality_guest")
    started = begin_motion_command(session["session_id"], "站到操作台A和操作台B之间")
    assert started.get("status") == "motion_started", started
    outcomes = drain_service(started)
    assert len(outcomes) == 1
    result = outcomes[0]
    assert result.get("terminal_fact") == "executor_between_references", result
    assert (result.get("terminal_verification_evidence") or {}).get("relation_verified") is True
    print("RELL 前后/双参考执行校验通过：前后关系按当前净空安全阻断，between 完成 P016 验真。")


if __name__ == "__main__":
    main()
