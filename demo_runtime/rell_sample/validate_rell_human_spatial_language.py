from __future__ import annotations

from embodied_scene import SESSIONS, _compose_session_language, start_session
from concept_core.relative_spatial_planning import build_relative_spatial_plan_contract


def main() -> None:
    cases = (
        ("站到我身边", "navigate_to", "destination", "near_human"),
        ("站到我前面", "navigate_to", "destination", "in_front_of"),
        ("站到我后面", "navigate_to", "destination", "behind"),
        ("面向我", "orient_executor", "direction", "facing"),
    )
    for utterance, operator, role_name, relation in cases:
        started = start_session("home_humanoid", "hospitality_guest")
        analysis = _compose_session_language(SESSIONS[started["session_id"]], utterance)
        operators = (analysis.get("canonical_frame") or {}).get("operators") or []
        role = (analysis.get("role_bindings") or {}).get(role_name) or {}
        assert operators == [operator], analysis
        assert role.get("reference") == "human_speaker", role
        assert role.get("spatial_relation") == relation, role
        assert analysis.get("runtime_fact_committed") is False
        admission = analysis.get("dictionary_authority_admission") or {}
        assert admission.get("can_control_execution") is False
        plan = build_relative_spatial_plan_contract(analysis)
        assert plan and plan["relation"] == relation
        assert plan["control_gateway"] == "P018"
        assert plan["verification_gateway"] == "P016"
        assert plan["direct_execution_allowed"] is False
    print("RELL 人体参照空间语言校验通过：邻近、前后方与朝向均形成结构化候选关系。")


if __name__ == "__main__":
    main()
