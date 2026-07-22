from __future__ import annotations

from embodied_scene import begin_motion_command, start_session
from validate_water_delivery_loop import drain_service


def validate(utterance: str, terminal_fact: str) -> None:
    session = start_session("home_humanoid", "hospitality_guest")
    started = begin_motion_command(session["session_id"], utterance)
    assert started.get("status") == "motion_started", started
    outcomes = drain_service(started)
    assert len(outcomes) == 1, outcomes
    result = outcomes[0]
    assert result.get("status") == "fact_established", result
    assert result.get("terminal_fact") == terminal_fact, result
    evidence = result.get("terminal_verification_evidence") or {}
    assert evidence.get("relation_verified") is True, evidence
    contract = result.get("relative_spatial_execution_contract") or {}
    assert contract.get("control_gateway") == "P018", contract
    assert contract.get("verification_gateway") == "P016", contract


def main() -> None:
    validate("走到操作台A旁边", "executor_beside_object")
    validate("面向我", "executor_facing_reference")
    print("RELL 相对空间执行校验通过：beside 与 facing 均完成 P018 执行和 P016 末态验真。")


if __name__ == "__main__":
    main()
