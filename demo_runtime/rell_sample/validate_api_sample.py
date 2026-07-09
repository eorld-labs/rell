from __future__ import annotations

import json

from api_server import (
    EXPERIENCE_LIBRARY_FILE,
    AUDIT_STORE,
    admit_process,
    get_audit,
    get_cognitive_model,
    get_space_prior,
    load_experience_library,
    run_process,
    teach_experience,
    teach_experience_from_dialogue,
)


def main() -> None:
    original_library = EXPERIENCE_LIBRARY_FILE.read_text(encoding="utf-8") if EXPERIENCE_LIBRARY_FILE.exists() else None
    EXPERIENCE_LIBRARY_FILE.write_text(json.dumps({"schema_version": "1.0.0", "experiences": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

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

    taught = teach_experience(
        "走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水",
        "走向操作台\n拿起杯子\n到水源处\n接一杯水\n倒水",
    )
    if taught.get("decision") != "experience_created":
        raise AssertionError(f"teaching must create an experience: {taught}")
    if not load_experience_library().get("experiences"):
        raise AssertionError("experience library must persist taught experience")
    learned_run = run_process("auto", "走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水")
    if learned_run["audit_summary"]["outcome"] != "completed":
        raise AssertionError(f"learned process chain must run in digital space: {learned_run}")
    if learned_run["intent_translation"]["task_type"] != "learned_process_chain":
        raise AssertionError(f"learned task must be translated as learned_process_chain: {learned_run['intent_translation']}")
    if learned_run.get("experience_ref") != taught["experience"]["experience_id"]:
        raise AssertionError(f"learned run must reference taught experience: {learned_run}")

    dialogue_taught = teach_experience_from_dialogue(
        "走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水",
        "教你：走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水",
    )
    if dialogue_taught.get("decision") != "experience_created":
        raise AssertionError(f"dialogue teaching must create an experience: {dialogue_taught}")
    if dialogue_taught["experience"]["context"]["human_intent_ref"] != "dialogue_teaching":
        raise AssertionError(f"dialogue teaching must mark source: {dialogue_taught}")

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

    if original_library is None:
        EXPERIENCE_LIBRARY_FILE.unlink(missing_ok=True)
    else:
        EXPERIENCE_LIBRARY_FILE.write_text(original_library, encoding="utf-8")

    print("API sample validation passed.")
    print("Validated: admit, run success, teach experience, dialogue teaching, run learned chain, run channel_conflict, run simulated_success, get audit, get space.")


if __name__ == "__main__":
    main()
