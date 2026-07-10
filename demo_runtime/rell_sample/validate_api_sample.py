from __future__ import annotations

import json

from api_server import (
    EXPERIENCE_LIBRARY_FILE,
    AUDIT_STORE,
    admit_process,
    dispatch_execution_loop_payload,
    get_audit,
    get_cognitive_model,
    get_experience_gap,
    get_execution_dispatch,
    get_readaptation,
    get_space_prior,
    load_experience_library,
    readapt_runtime_conflict,
    run_process,
    teach_experience,
    teach_experience_from_dialogue,
    get_runtime_world_state,
    migrate_experience,
    release_runtime_world_state,
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
    taught_contract = taught["experience"].get("invariant_contract", {})
    if taught_contract.get("storage_policy") != "store_invariants_not_concrete_parameters":
        raise AssertionError(f"experience must store invariant contract, not concrete parameters: {taught_contract}")
    for forbidden in ["absolute_coordinates", "robot_specific_joint_angles", "fixed_execution_duration"]:
        if forbidden not in taught_contract.get("forbidden_storage", []):
            raise AssertionError(f"invariant contract must forbid {forbidden}: {taught_contract}")
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

    routed_teaching = teach_experience_from_dialogue(
        "走到门旁边，再走到服务为，再去操作台拿杯子，去水源处倒杯水",
        "教你：走到门旁边，再走到服务为，再去操作台拿杯子，去水源处倒杯水",
    )
    expected_routed_chain = [
        "move_to_doorway",
        "move_to_service_position",
        "move_to_counter",
        "pick_up_cup",
        "move_to_water_source",
        "fill_cup_at_water_source",
    ]
    if routed_teaching.get("experience", {}).get("process_chain") != expected_routed_chain:
        raise AssertionError(f"routed teaching must preserve explicit semantic waypoints: {routed_teaching}")
    routed_contract = routed_teaching.get("experience", {}).get("invariant_contract", {})
    if len(routed_contract.get("topology_invariants", [])) != len(expected_routed_chain):
        raise AssertionError(f"routed teaching must produce topology invariants for each step: {routed_contract}")
    if not all(item.get("terminate_when", "").endswith("== established") for item in routed_contract.get("termination_conditions", [])):
        raise AssertionError(f"all invariant termination conditions must be fact-based: {routed_contract}")
    routed_run = run_process("auto", "走到门旁边，再走到服务为，再去操作台拿杯子，去水源处倒杯水")
    if routed_run["intent_translation"].get("candidate_process_chain") != expected_routed_chain:
        raise AssertionError(f"explicit route must survive causal planning: {routed_run['intent_translation']}")
    if routed_run["intent_translation"].get("goal_fact") != "cup_contains_water":
        raise AssertionError(f"water-source pouring phrase must mean filling cup, not final pour_water: {routed_run['intent_translation']}")
    routed_frame = routed_run["intent_translation"].get("intent_frame", {})
    routed_regions = [item.get("region_ref") for item in routed_frame.get("spatial_constraints", [])]
    for expected_region in ["region_doorway", "region_service_position", "region_counter_operation", "region_water_source"]:
        if expected_region not in routed_regions:
            raise AssertionError(f"P012 intent frame must preserve spatial semantic target {expected_region}: {routed_frame}")
    routed_concepts = [item.get("concept_id") for item in routed_frame.get("concept_matches", [])]
    for expected_concept in ["concept_spatial_region_navigation", "concept_fillable_container", "concept_water_resource_zone"]:
        if expected_concept not in routed_concepts:
            raise AssertionError(f"P012 intent frame must expose concept bridge {expected_concept}: {routed_frame}")
    if routed_frame.get("planning_policy", {}).get("llm_role") is None:
        raise AssertionError(f"intent frame must constrain LLM to semantic translation instead of direct action planning: {routed_frame}")
    runtime_world = routed_run.get("runtime_world_state", {})
    if runtime_world.get("lifecycle") != "ephemeral_task_memory":
        raise AssertionError(f"runtime world state must be ephemeral task memory: {runtime_world}")
    if runtime_world.get("executor", {}).get("location_ref") != "region_water_source":
        raise AssertionError(f"runtime world state must track final executor location: {runtime_world}")
    if "object_cup_white_mug" not in runtime_world.get("executor", {}).get("holding", []):
        raise AssertionError(f"runtime world state must track held cup after pickup: {runtime_world}")
    if "cup_contains_water" not in runtime_world.get("established_facts", []):
        raise AssertionError(f"runtime world state must establish target fact after fill step: {runtime_world}")
    if "长期世界数据库" not in routed_run.get("execution_trace", {}).get("runtime_world_state_policy", ""):
        raise AssertionError(f"execution trace must document non-persistent runtime world policy: {routed_run.get('execution_trace')}")

    migration = migrate_experience("到水源处接一杯水")
    if migration["execution_feasibility"]["result"] != "executable":
        raise AssertionError(f"P017 migration must produce executable feasibility: {migration}")
    if not migration.get("binding_candidate", {}).get("step_bindings"):
        raise AssertionError(f"P017 migration must generate binding candidates: {migration}")
    payload = migration.get("execution_loop_payload")
    if not payload or not payload.get("runtime_world_state_snapshot_id"):
        raise AssertionError(f"P017 migration must generate open execution loop payload: {migration}")
    migration_state = get_runtime_world_state(migration["migration_task_id"])
    if migration_state.get("release_status") != "not_released":
        raise AssertionError(f"runtime world state should be queryable before release: {migration_state}")
    dispatch = dispatch_execution_loop_payload(payload, "robot_sdk")
    if dispatch.get("outcome") != "fact_established":
        raise AssertionError(f"open execution loop dispatch must establish target fact: {dispatch}")
    if "cup_contains_water" not in dispatch.get("runtime_world_state_snapshot", {}).get("established_facts", []):
        raise AssertionError(f"dispatch must update runtime world state facts: {dispatch}")
    fetched_dispatch = get_execution_dispatch(dispatch["dispatch_id"])
    if fetched_dispatch.get("dispatch_id") != dispatch["dispatch_id"]:
        raise AssertionError(f"execution dispatch record must be queryable: {fetched_dispatch}")
    release = release_runtime_world_state(migration["migration_task_id"], "validation_finished")
    if release.get("release_status") != "released" or not release.get("release_token"):
        raise AssertionError(f"runtime world state release must issue token: {release}")
    released_state = get_runtime_world_state(migration["migration_task_id"])
    if released_state.get("runtime_world_state_snapshot", {}).get("snapshot_lifecycle_state") != "released":
        raise AssertionError(f"released runtime world state must be marked released: {released_state}")

    weak_profile = dict(migration["body_capability_profile"])
    weak_profile["supported_actions"] = ["navigate_to_region"]
    partial = migrate_experience("到水源处接一杯水", weak_profile)
    if partial["execution_feasibility"]["result"] not in {"partially_inexecutable", "infeasible"}:
        raise AssertionError(f"weak body capability profile must produce infeasible or partial result: {partial}")
    if not partial["execution_feasibility"]["infeasible_reasons"]:
        raise AssertionError(f"infeasible migration must expose reasons: {partial}")
    gap_record = partial.get("experience_gap_record")
    if not gap_record or not gap_record.get("teaching_request"):
        raise AssertionError(f"infeasible migration must create an experience gap record: {partial}")
    fetched_gap = get_experience_gap(gap_record["gap_record_id"])
    if fetched_gap.get("gap_record_id") != gap_record["gap_record_id"]:
        raise AssertionError(f"experience gap record must be queryable: {fetched_gap}")

    conflict = run_process("channel_conflict")
    if conflict["audit_summary"]["outcome"] != "requires_human_confirmation":
        raise AssertionError("conflict API run must require human confirmation")
    readaptation = readapt_runtime_conflict(conflict["task_id"], "到水源处接一杯水")
    if readaptation.get("execution_feasibility", {}).get("result") != "requires_human_confirmation":
        raise AssertionError(f"runtime conflict must produce human-confirmation readaptation: {readaptation}")
    if not readaptation.get("runtime_world_state_snapshot", {}).get("runtime_conflicts"):
        raise AssertionError(f"readaptation snapshot must carry runtime conflicts: {readaptation}")
    fetched_readaptation = get_readaptation(readaptation["readaptation_id"])
    if fetched_readaptation.get("readaptation_id") != readaptation["readaptation_id"]:
        raise AssertionError(f"readaptation record must be queryable: {fetched_readaptation}")

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
    print("Validated: admit, run success, teach experience, dialogue teaching, natural-language causal teaching, explicit route teaching, causal chain solving, causal short-goal solving, P017 migration adaptation, runtime world release, run channel_conflict, run simulated_success, get audit, get space.")


if __name__ == "__main__":
    main()
