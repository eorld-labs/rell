from __future__ import annotations

from api_server import AUDIT_STORE, admit_process, get_audit, run_process


def main() -> None:
    admission = admit_process()
    if not admission["allowed"]:
        raise AssertionError(f"admission expected allowed, got {admission}")

    success = run_process("success")
    if success["audit_summary"]["outcome"] != "completed":
        raise AssertionError("success API run must complete")

    conflict = run_process("channel_conflict")
    if conflict["audit_summary"]["outcome"] != "requires_human_confirmation":
        raise AssertionError("conflict API run must require human confirmation")

    task_id = success["task_id"]
    audit = get_audit(task_id)
    if audit.get("task_id") != task_id:
        raise AssertionError("GET audit must return stored audit")

    if task_id not in AUDIT_STORE:
        raise AssertionError("audit store must contain latest task_id")

    print("API sample validation passed.")
    print("Validated: admit, run success, run channel_conflict, get audit.")


if __name__ == "__main__":
    main()
