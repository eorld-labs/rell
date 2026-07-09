from __future__ import annotations

from api_server import AUDIT_STORE, admit_process, get_audit, get_cognitive_model, get_space_prior, run_process


def main() -> None:
    admission = admit_process()
    if not admission["allowed"]:
        raise AssertionError(f"admission expected allowed, got {admission}")

    success = run_process("success")
    if success["audit_summary"]["outcome"] != "completed":
        raise AssertionError("success API run must complete")
    if success["space_context"]["space_id"] != "home_a_kitchen":
        raise AssertionError(f"success API run must expose digital space context: {success.get('space_context')}")

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
