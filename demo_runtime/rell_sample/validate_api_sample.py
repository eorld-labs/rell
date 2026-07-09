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
    if process_chain["audit_summary"]["outcome"] != "completed":
        raise AssertionError(f"process chain must be solved through causal planning: {process_chain}")
    if process_chain["intent_translation"].get("task_type") != "causal_process_chain":
        raise AssertionError(f"process chain must be translated as causal_process_chain: {process_chain['intent_translation']}")
    expected_long_chain = [
        "move_to_counter",
        "pick_up_cup",
        "move_to_water_source",
        "fill_cup_at_water_source",
        "move_to_counter",
        "pour_water",
    ]
    if process_chain["intent_translation"].get("candidate_process_chain") != expected_long_chain:
        raise AssertionError(f"process chain must be derived from causal preconditions: {process_chain['intent_translation']}")

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
    if learned_run["intent_translation"]["task_type"] != "causal_process_chain":
        raise AssertionError(f"causal planner must take priority over exact phrase enumeration: {learned_run['intent_translation']}")
    if learned_run["intent_translation"].get("goal_fact") != "water_poured":
        raise AssertionError(f"learned long task must retain target fact: {learned_run['intent_translation']}")

    dialogue_taught = teach_experience_from_dialogue(
        "走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水",
        "教你：走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水",
    )
    if dialogue_taught.get("decision") != "experience_created":
        raise AssertionError(f"dialogue teaching must create an experience: {dialogue_taught}")
    if dialogue_taught["experience"]["context"]["human_intent_ref"] != "dialogue_teaching":
        raise AssertionError(f"dialogue teaching must mark source: {dialogue_taught}")

    causal_taught = teach_experience_from_dialogue(
        "",
        "教你一个技能：接一杯水需要先拿杯子，再去水源处接水。接完以后杯子里有水。",
    )
    if causal_taught.get("decision") != "experience_created":
        raise AssertionError(f"natural language causal teaching must create an experience: {causal_taught}")
    signature = causal_taught["experience"].get("causal_signature", {})
    if signature.get("produces_fact") != "cup_contains_water":
        raise AssertionError(f"causal teaching must produce cup_contains_water: {causal_taught}")
    if not signature.get("solver_enabled"):
        raise AssertionError(f"causal teaching must be available to the causal solver: {causal_taught}")
    if "executor_at_counter" not in signature.get("requires_facts", []):
        raise AssertionError(f"causal signature must expose external preconditions: {signature}")
    causal_taught_run = run_process("auto", "帮我接水")
    if causal_taught_run["audit_summary"]["outcome"] != "completed":
        raise AssertionError(f"taught causal process must run from a different utterance: {causal_taught_run}")
    reasoning_sources = [
        item.get("source")
        for item in causal_taught_run["intent_translation"].get("causal_plan", {}).get("reasoning", [])
    ]
    if "experience_library" not in reasoning_sources:
        raise AssertionError(f"causal solver must use taught experience signature: {causal_taught_run['intent_translation']}")

    short_run = run_process("auto", "到水源处接一杯水")
    if short_run["audit_summary"]["outcome"] != "completed":
        raise AssertionError(f"short goal must run through causal precondition search: {short_run}")
    expected_short_chain = ["move_to_counter", "pick_up_cup", "move_to_water_source", "fill_cup_at_water_source"]
    if short_run["intent_translation"].get("candidate_process_chain") != expected_short_chain:
        raise AssertionError(f"short goal must infer cup preconditions from causal layer: {short_run['intent_translation']}")
    if "pour_water" in short_run["intent_translation"].get("candidate_process_chain", []):
        raise AssertionError(f"short goal must not include pouring step: {short_run['intent_translation']}")

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
    print("Validated: admit, run success, teach experience, dialogue teaching, natural-language causal teaching, causal chain solving, causal short-goal solving, run channel_conflict, run simulated_success, get audit, get space.")


if __name__ == "__main__":
    main()
