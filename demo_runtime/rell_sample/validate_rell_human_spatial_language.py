from __future__ import annotations

from embodied_scene import SESSIONS, _compose_session_language, start_session


def main() -> None:
    started = start_session("home_humanoid", "hospitality_guest")
    analysis = _compose_session_language(SESSIONS[started["session_id"]], "站到我身边")
    operators = (analysis.get("canonical_frame") or {}).get("operators") or []
    destination = (analysis.get("role_bindings") or {}).get("destination") or {}
    assert operators == ["navigate_to"], analysis
    assert destination.get("reference") == "human_speaker", destination
    assert destination.get("spatial_relation") == "near_human", destination
    assert analysis.get("runtime_fact_committed") is False
    admission = analysis.get("dictionary_authority_admission") or {}
    assert admission.get("can_control_execution") is False
    print("RELL 人体参照空间语言校验通过：‘站到我身边’映射为 near_human 候选关系。")


if __name__ == "__main__":
    main()
