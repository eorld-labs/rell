from __future__ import annotations

from copy import deepcopy

from embodied_scene import (
    SESSIONS,
    _finalize_motion_result,
    begin_motion_command,
    start_session,
)
from evaluate_natural_language_variants import setup_human_held_cup


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def immediate(result: dict) -> dict:
    return result.get("immediate_result") or result


def prepared_session() -> str:
    session = start_session("home_humanoid", "hospitality_guest")
    setup = setup_human_held_cup(session["session_id"])
    require(setup["completed"], str(setup))
    return session["session_id"]


def validate_human_possession_preserves_language_role_span() -> None:
    session_id = prepared_session()
    result = begin_motion_command(
        session_id, "把我手上的白色杯子放到操作台A"
    )
    view = immediate(result)
    roles = (view.get("long_horizon_intent") or {}).get("role_bindings") or {}
    require(
        roles.get("theme") == "mug_white"
        and roles.get("source_holder") == "guest"
        and roles.get("destination") == "hospitality_counter_a",
        f"human-possession role span drifted: {result}",
    )
    require(
        view.get("status") in {"requires_human_confirmation", "motion_started"},
        f"human-held placement did not compile: {result}",
    )


def validate_failure_rebuilds_from_authoritative_world() -> str:
    session_id = prepared_session()
    session = SESSIONS[session_id]
    before = deepcopy(session)
    session["process_gap_dialogue"] = {"status": "stale_destination_question"}
    session["role_clarification_dialogue"] = {"status": "stale_theme_question"}
    session["relation_hypothesis_dialogue"] = {"status": "stale_relation_question"}
    session["dialogue_focus_entities"] = [{"entity_ref": "glass_tall"}]
    failure = {
        "status": "execution_precondition_failed",
        "reason": "no_object_currently_held",
        "runtime_diagnostic": {
            "stage": "place_at_destination",
            "reason": "no_object_currently_held",
            "category": "world_state_precondition_mismatch",
            "recovery_options": ["重新读取当前持有关系"],
        },
        "frames": [],
    }
    finalized = _finalize_motion_result(
        session_id, "把杯子放到操作台A", before, failure, None
    )
    recovered = SESSIONS[session_id]
    contract = recovered.get("failure_recovery_contract") or {}
    require(finalized.get("status") == "execution_precondition_failed", str(finalized))
    require(contract.get("fact_authority_ref"), f"ledger authority absent: {contract}")
    require(
        contract.get("current_verified_state", {}).get("held_by_human")
        == [{"entity_ref": "mug_white", "holder_ref": "guest"}],
        f"verified human possession was not reconstructed: {contract}",
    )
    require(
        contract.get("human_report_commits_physical_fact") is False,
        f"human report was allowed to commit a physical fact: {contract}",
    )
    require(
        not recovered.get("process_gap_dialogue")
        and not recovered.get("role_clarification_dialogue")
        and not recovered.get("relation_hypothesis_dialogue")
        and recovered.get("dialogue_focus_entities") == [],
        f"stale control state survived failure: {recovered}",
    )
    require(
        contract.get("released_task_state", {}).get("old_motion_path_discarded")
        and contract.get("released_task_state", {}).get("stale_dialogue_slots_discarded"),
        f"release contract incomplete: {contract}",
    )
    return session_id


def validate_new_task_retires_recovery_contract() -> None:
    session_id = validate_failure_rebuilds_from_authoritative_world()
    result = begin_motion_command(
        session_id, "把我手上的白色杯子放到操作台A"
    )
    view = immediate(result)
    roles = (view.get("long_horizon_intent") or {}).get("role_bindings") or {}
    session = SESSIONS[session_id]
    require(session.get("failure_recovery_contract") is None, str(session))
    require(
        (session.get("failure_recovery_history") or [])[-1].get("status") == "retired",
        f"recovery contract was not archived: {session.get('failure_recovery_history')}",
    )
    require(
        roles.get("theme") == "mug_white"
        and roles.get("destination") == "hospitality_counter_a",
        f"new task reused stale bindings instead of recompiling: {result}",
    )


def validate_language_correction_enters_evidence_gate() -> None:
    session_id = validate_failure_rebuilds_from_authoritative_world()
    result = begin_motion_command(session_id, "杯子还在我手上")
    view = immediate(result)
    require(
        view.get("status") == "failure_recovery_state_report_already_verified",
        f"state correction did not enter recovery evidence gate: {result}",
    )
    require(
        view.get("runtime_fact_committed") is False
        and view.get("matched_verified_fact") is True,
        f"human report crossed the physical-fact boundary: {result}",
    )
    require(
        SESSIONS[session_id].get("failure_recovery_contract") is not None,
        "a state report incorrectly replaced the recovery contract",
    )


def validate_conflicting_language_correction_requires_observation() -> None:
    session = start_session("home_humanoid", "hospitality_guest")
    session_id = session["session_id"]
    before = deepcopy(SESSIONS[session_id])
    failure = {
        "status": "execution_precondition_failed",
        "reason": "no_object_currently_held",
        "runtime_diagnostic": {
            "stage": "place_at_destination",
            "reason": "no_object_currently_held",
            "category": "world_state_precondition_mismatch",
            "recovery_options": ["重新观察对象和手部关系"],
        },
        "frames": [],
    }
    _finalize_motion_result(
        session_id, "把杯子放到操作台A", before, failure, None
    )
    result = begin_motion_command(session_id, "白色杯子还在我手上")
    view = immediate(result)
    require(
        view.get("status") == "failure_recovery_observation_required"
        and view.get("runtime_fact_committed") is False
        and view.get("matched_verified_fact") is False,
        f"conflicting report bypassed observation evidence: {result}",
    )
    require(
        view.get("required_evidence")
        == "qualified_multimodal_observation_or_p016_verification",
        f"recovery observation contract omitted its evidence gate: {result}",
    )


if __name__ == "__main__":
    validate_human_possession_preserves_language_role_span()
    validate_failure_rebuilds_from_authoritative_world()
    validate_new_task_retires_recovery_contract()
    validate_language_correction_enters_evidence_gate()
    validate_conflicting_language_correction_requires_observation()
    print("failure recovery architecture checks passed")
