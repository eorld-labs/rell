from __future__ import annotations

from api_server import AUDIT_STORE, admit_process, get_audit, get_cognitive_model, get_space_prior, run_process


def main() -> None:
    admission = admit_process()
    if not admission["allowed"]:
        raise AssertionError(f"admission expected allowed, got {admission}")

    success = run_process("success")
    if success["audit_summary"]["outcome"] != "completed":
        raise AssertionError("success API run must complete")
    if success["intent_translation"]["task_type"] != "pour_water":
        raise AssertionError(f"success API run must expose intent translation: {success.get('intent_translation')}")
    if success["space_admission"]["decision"] != "allowed":
        raise AssertionError(f"success API run must pass space admission: {success.get('space_admission')}")
    if success["space_context"]["space_id"] != "home_a_kitchen":
        raise AssertionError(f"success API run must expose digital space context: {success.get('space_context')}")

    auto = run_process("auto", "给客人倒一杯水")
    if auto["scenario"] != "simulated_success" or auto["audit_summary"]["outcome"] != "completed":
        raise AssertionError(f"auto API run must translate and choose simulated_success: {auto}")

    unsupported = run_process("auto", "去楼下拿个快递")
    if unsupported["audit_summary"]["outcome"] != "cannot_do":
        raise AssertionError(f"unsupported task must return cannot_do: {unsupported}")

    process_chain = run_process("auto", "走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水")
    if process_chain["audit_summary"]["outcome"] != "cannot_do":
        raise AssertionError(f"process chain must not collapse into pour_water: {process_chain}")
    if process_chain["intent_translation"].get("task_type") != "process_chain":
        raise AssertionError(f"process chain must be identified before execution: {process_chain['intent_translation']}")
    if "fill_cup_at_water_source" not in process_chain["intent_translation"].get("candidate_process_chain", []):
        raise AssertionError(f"process chain must retain water-source filling step: {process_chain['intent_translation']}")

    conflict = run_process("channel_conflict")
    if conflict["audit_summary"]["outcome"] != "requires_human_confirmation":
        raise AssertionError("conflict API run must require human confirmation")

    simulated = run_process("simulated_success")
    if simulated["audit_summary"]["outcome"] != "completed":
        raise AssertionError("simulated success API run must complete")
    if not any(
        "adapter=simulated_pouring_robot" in event.get("payload_summary", "")
        for event in simulated["execution_trace"]["events"]
    ):
        raise AssertionError("simulated API run must expose simulated adapter trace payloads")

    task_id = success["task_id"]
    audit = get_audit(task_id)
    if audit.get("task_id") != task_id:
        raise AssertionError("GET audit must return stored audit")

    if task_id not in AUDIT_STORE:
        raise AssertionError("audit store must contain latest task_id")

    prior = get_space_prior()
    model = get_cognitive_model()
    if prior["prior_id"] != model["prior_ref"]:
        raise AssertionError("space cognitive model must reference semantic prior")

    print("API sample validation passed.")
    print("Validated: admit, run success, run channel_conflict, run simulated_success, get audit, get space.")


if __name__ == "__main__":
    main()
