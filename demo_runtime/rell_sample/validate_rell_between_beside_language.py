from __future__ import annotations

from embodied_scene import SESSIONS, _compose_session_language, start_session
from concept_core.relative_spatial_planning import build_relative_spatial_plan_contract


def compose(utterance: str) -> dict:
    started = start_session("home_humanoid", "hospitality_guest")
    return _compose_session_language(SESSIONS[started["session_id"]], utterance)


def main() -> None:
    beside = compose("走到操作台A旁边")
    beside_roles = beside.get("role_bindings") or {}
    assert (beside.get("canonical_frame") or {}).get("operators") == ["navigate_to"], beside
    assert (beside_roles.get("destination") or {}).get("spatial_relation") == "beside", beside_roles
    beside_plan = build_relative_spatial_plan_contract(beside)
    assert beside_plan and beside_plan["process_contract"] == "navigate_to_lateral_relation"

    near = compose("走到操作台A附近")
    near_destination = (near.get("role_bindings") or {}).get("destination") or {}
    assert near_destination.get("spatial_relation") == "near_landmark", near_destination
    assert build_relative_spatial_plan_contract(near) is None

    between = compose("站到操作台A和操作台B之间")
    between_roles = between.get("role_bindings") or {}
    destination = between_roles.get("destination") or {}
    assert (between.get("canonical_frame") or {}).get("operators") == ["navigate_to"], between
    assert destination.get("spatial_relation") == "between", between_roles
    assert between_roles.get("between_reference_a") and between_roles.get("between_reference_b")
    between_plan = build_relative_spatial_plan_contract(between)
    assert between_plan and between_plan["process_contract"] == "navigate_to_between_region"
    assert between_plan["reference_roles"] == ["between_reference_a", "between_reference_b"]
    assert between_plan["direct_execution_allowed"] is False
    assert between.get("runtime_fact_committed") is False
    print("RELL beside/near/between 校验通过：侧向、宽松邻近和双参考区域保持独立语义。")


if __name__ == "__main__":
    main()
