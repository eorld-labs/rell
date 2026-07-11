from __future__ import annotations

import json

from api_server import (
    AUDIT_STORE,
    CONCEPT_CANDIDATE_LIBRARY_FILE,
    CONCEPT_LIBRARY_FILE,
    EXPERIENCE_LIBRARY_FILE,
    PREFERENCE_LIBRARY_FILE,
    RECOVERY_LIBRARY_FILE,
    admit_process,
    build_runtime_explanation_view,
    build_llm_context_view,
    build_llm_prompt_contract,
    build_semantic_request_frame,
    confirm_concept_promotion_candidate,
    dispatch_execution_loop_payload,
    execute_teaching_session_step,
    finish_teaching_session,
    get_audit,
    get_cognitive_model,
    get_execution_dispatch,
    get_experience_gap,
    get_recovery_record,
    get_recovery_records_for_task,
    get_readaptation,
    get_runtime_world_state,
    get_space_prior,
    get_teaching_session,
    handle_agent_query,
    inject_runtime_perturbation,
    load_concept_candidate_library,
    load_concept_library,
    load_experience_library,
    load_preference_library,
    load_recovery_library,
    migrate_experience,
    query_runtime_world_state,
    record_preference,
    readapt_runtime_conflict,
    release_runtime_world_state,
    resolve_concepts_for_intent,
    run_process,
    start_teaching_session,
    teach_experience,
    teach_experience_from_dialogue,
    validate_llm_candidate_output,
)


def main() -> None:
    original_experience_library = EXPERIENCE_LIBRARY_FILE.read_text(encoding="utf-8") if EXPERIENCE_LIBRARY_FILE.exists() else None
    original_concept_library = CONCEPT_LIBRARY_FILE.read_text(encoding="utf-8") if CONCEPT_LIBRARY_FILE.exists() else None
    original_candidate_library = CONCEPT_CANDIDATE_LIBRARY_FILE.read_text(encoding="utf-8") if CONCEPT_CANDIDATE_LIBRARY_FILE.exists() else None
    original_preference_library = PREFERENCE_LIBRARY_FILE.read_text(encoding="utf-8") if PREFERENCE_LIBRARY_FILE.exists() else None
    original_recovery_library = RECOVERY_LIBRARY_FILE.read_text(encoding="utf-8") if RECOVERY_LIBRARY_FILE.exists() else None

    EXPERIENCE_LIBRARY_FILE.write_text(
        json.dumps({"schema_version": "1.0.0", "experiences": []}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    CONCEPT_CANDIDATE_LIBRARY_FILE.unlink(missing_ok=True)
    RECOVERY_LIBRARY_FILE.unlink(missing_ok=True)

    try:
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
        expected_long_chain = [
            "move_to_counter",
            "pick_up_cup",
            "move_to_water_source",
            "fill_cup_at_water_source",
            "move_to_counter",
            "pour_water",
        ]
        if process_chain["audit_summary"]["outcome"] != "completed":
            raise AssertionError(f"process chain must be solved through causal planning: {process_chain}")
        if process_chain["intent_translation"].get("task_type") != "causal_process_chain":
            raise AssertionError(f"process chain must be translated as causal_process_chain: {process_chain['intent_translation']}")
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
        if not taught.get("concept_promotion_candidates"):
            raise AssertionError(f"teaching must generate concept promotion candidates: {taught}")

        candidate_library = load_concept_candidate_library()
        if not candidate_library.get("concept_candidates"):
            raise AssertionError(f"concept candidate library must persist generated candidates: {candidate_library}")
        promoted_candidate = next(
            (item for item in taught["concept_promotion_candidates"] if item.get("proposal_type") == "create_promoted_concept_unit"),
            None,
        )
        if not promoted_candidate:
            raise AssertionError(f"teaching must provide a promoted task concept candidate: {taught}")
        promoted_result = confirm_concept_promotion_candidate(promoted_candidate["candidate_id"], confirmed_by="validate_api_sample")
        if promoted_result.get("status") != "promoted":
            raise AssertionError(f"concept candidate confirmation must promote a concept: {promoted_result}")
        updated_concept_library = load_concept_library()
        updated_concept_ids = [item.get("concept_id") for item in updated_concept_library.get("concept_units", [])]
        if promoted_result.get("promoted_concept_id") not in updated_concept_ids:
            raise AssertionError(f"confirmed concept must enter concept library: {updated_concept_library}")
        promoted_resolution = resolve_concepts_for_intent("走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水")
        if promoted_result.get("promoted_concept_id") not in [item.get("concept_id") for item in promoted_resolution.get("resolved_concepts", [])]:
            raise AssertionError(f"confirmed promoted concept must be reusable in later concept resolution: {promoted_resolution}")

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

        stepwise_blocked = start_teaching_session("到水源处接一杯水")
        blocked_feedback = execute_teaching_session_step(stepwise_blocked["session_id"], "拿起杯子")
        first_blocked_item = blocked_feedback["step_feedback"][0]
        if first_blocked_item.get("status") != "needs_more_teaching" or first_blocked_item.get("executed"):
            raise AssertionError(f"stepwise teaching must not execute when prerequisites are missing: {blocked_feedback}")
        if "executor_at_counter" not in first_blocked_item.get("missing_before_step", []):
            raise AssertionError(f"stepwise teaching must expose missing prerequisite facts: {blocked_feedback}")

        stepwise = start_teaching_session("到水源处接一杯水")
        for text in ["走向操作台", "拿起杯子", "到水源处", "接一杯水"]:
            step_result = execute_teaching_session_step(stepwise["session_id"], text)
            if not step_result["step_feedback"][0].get("executed"):
                raise AssertionError(f"stepwise teaching step should execute after prerequisites are met: {step_result}")
        fetched_session = get_teaching_session(stepwise["session_id"])
        if fetched_session.get("status") != "goal_achieved_pending_confirmation":
            raise AssertionError(f"stepwise teaching must reach goal fact before finish: {fetched_session}")
        if "cup_contains_water" not in fetched_session.get("runtime_world_state_snapshot", {}).get("established_facts", []):
            raise AssertionError(f"stepwise teaching must update runtime world facts: {fetched_session}")
        finished_session = finish_teaching_session(stepwise["session_id"])
        if finished_session.get("status") != "experience_saved":
            raise AssertionError(f"stepwise teaching must save experience after goal achieved: {finished_session}")
        if finished_session.get("experience_result", {}).get("experience", {}).get("context", {}).get("human_intent_ref") != "stepwise_teaching_session":
            raise AssertionError(f"stepwise teaching must mark experience source: {finished_session}")
        if finished_session.get("release_result", {}).get("release_status") != "released":
            raise AssertionError(f"stepwise teaching must release runtime world state: {finished_session}")
        if not finished_session.get("experience_result", {}).get("concept_promotion_candidates"):
            raise AssertionError(f"stepwise teaching finish must also generate concept promotion candidates: {finished_session}")

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
        reasoning_sources = [item.get("source") for item in causal_taught_run["intent_translation"].get("causal_plan", {}).get("reasoning", [])]
        if "experience_library" not in reasoning_sources:
            raise AssertionError(f"causal solver must use taught experience signature: {causal_taught_run['intent_translation']}")

        short_run = run_process("auto", "到水源处接一杯水")
        expected_short_chain = ["move_to_counter", "pick_up_cup", "move_to_water_source", "fill_cup_at_water_source"]
        if short_run["audit_summary"]["outcome"] != "completed":
            raise AssertionError(f"short goal must run through causal precondition search: {short_run}")
        if short_run["intent_translation"].get("candidate_process_chain") != expected_short_chain:
            raise AssertionError(f"short goal must infer cup preconditions from causal layer: {short_run['intent_translation']}")
        if "pour_water" in short_run["intent_translation"].get("candidate_process_chain", []):
            raise AssertionError(f"short goal must not include pouring step: {short_run['intent_translation']}")

        routed_teaching = teach_experience_from_dialogue(
            "走到门旁边，再走到服务位，再去操作台拿杯子，去水源处倒杯水",
            "教你：走到门旁边，再走到服务位，再去操作台拿杯子，去水源处倒杯水",
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
        routed_run = run_process("auto", "走到门旁边，再走到服务位，再去操作台拿杯子，去水源处倒杯水")
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

        semantic_model = get_cognitive_model()
        semantic_state = build_semantic_request_frame("当前杯子有没有水", semantic_model, task_id=success["task_id"])
        if semantic_state.get("request_type") != "state_query":
            raise AssertionError(f"semantic router must classify state query: {semantic_state}")
        semantic_teaching = build_semantic_request_frame("教你：走向操作台，然后拿起杯子", semantic_model)
        if semantic_teaching.get("request_type") != "teaching":
            raise AssertionError(f"semantic router must classify teaching input: {semantic_teaching}")
        semantic_clarification = build_semantic_request_frame("为什么不能执行", semantic_model)
        if semantic_clarification.get("request_type") != "clarification":
            raise AssertionError(f"semantic router must classify clarification input: {semantic_clarification}")
        semantic_execution = build_semantic_request_frame("到水源处接一杯水", semantic_model)
        if semantic_execution.get("request_type") != "task_execution":
            raise AssertionError(f"semantic router must classify task execution input: {semantic_execution}")
        if semantic_execution.get("intent_confidence", 0) < 0.7 or semantic_execution.get("clarification_needed"):
            raise AssertionError(f"clear execution utterance should keep high confidence without clarification: {semantic_execution}")
        ambiguous_execution = build_semantic_request_frame("把那个给我弄一下", semantic_model)
        if ambiguous_execution.get("request_type") != "task_execution":
            raise AssertionError(f"ambiguous utterance should still stay in task_execution candidate lane: {ambiguous_execution}")
        if not ambiguous_execution.get("clarification_needed") or ambiguous_execution.get("intent_confidence", 1) >= semantic_execution.get("intent_confidence", 0):
            raise AssertionError(f"ambiguous utterance must trigger clarification and lower confidence: {ambiguous_execution}")

        migration = migrate_experience("到水源处接一杯水")
        if migration["execution_feasibility"]["result"] != "executable":
            raise AssertionError(f"P017 migration must produce executable feasibility: {migration}")
        if not migration.get("binding_candidate", {}).get("step_bindings"):
            raise AssertionError(f"P017 migration must generate binding candidates: {migration}")
        if not migration.get("runtime_world_state_snapshot", {}).get("active_preferences"):
            raise AssertionError(f"P015 preference records must be loaded into current runtime snapshot: {migration}")
        payload = migration.get("execution_loop_payload")
        if not payload or not payload.get("runtime_world_state_snapshot_id"):
            raise AssertionError(f"P017 migration must generate open execution loop payload: {migration}")
        migration_state = get_runtime_world_state(migration["migration_task_id"])
        if migration_state.get("release_status") != "not_released":
            raise AssertionError(f"runtime world state should be queryable before release: {migration_state}")
        runtime_explanation_before = build_runtime_explanation_view(migration["migration_task_id"])
        if runtime_explanation_before.get("status_answers", {}).get("next_step", {}).get("answer") != "move_to_counter":
            raise AssertionError(f"runtime explanation view must expose first planned step before dispatch: {runtime_explanation_before}")
        before_query = query_runtime_world_state(migration["migration_task_id"], "当前杯子有没有水")
        if before_query.get("answer") != "false" or before_query.get("source") != "runtime_world_state_snapshot_only":
            raise AssertionError(f"runtime world state query must answer from current snapshot before fill: {before_query}")
        preference_query = query_runtime_world_state(migration["migration_task_id"], "当前偏好约束是什么")
        if preference_query.get("query_type") != "preference_summary" or not preference_query.get("evidence", {}).get("active_preferences"):
            raise AssertionError(f"runtime world state must answer preference summary from current snapshot: {preference_query}")
        dispatch = dispatch_execution_loop_payload(payload, "robot_sdk")
        if dispatch.get("outcome") != "fact_established":
            raise AssertionError(f"open execution loop dispatch must establish target fact: {dispatch}")
        if "cup_contains_water" not in dispatch.get("runtime_world_state_snapshot", {}).get("established_facts", []):
            raise AssertionError(f"dispatch must update runtime world state facts: {dispatch}")
        after_query = query_runtime_world_state(migration["migration_task_id"], "当前杯子有没有水")
        if after_query.get("answer") != "true":
            raise AssertionError(f"runtime world state query must answer true after fill: {after_query}")
        runtime_explanation = build_runtime_explanation_view(migration["migration_task_id"])
        if runtime_explanation.get("status_answers", {}).get("current_action", {}).get("answer") != "fill_cup_at_water_source":
            raise AssertionError(f"runtime explanation view must expose current action from snapshot: {runtime_explanation}")
        if runtime_explanation.get("status_answers", {}).get("goal_fact", {}).get("answer") != "cup_contains_water":
            raise AssertionError(f"runtime explanation view must retain current task goal fact: {runtime_explanation}")

        detour_migration = migrate_experience(migration["intent_translation"]["utterance"])
        detour_injection = inject_runtime_perturbation(
            detour_migration["migration_task_id"],
            {"kind": "stool_in_walkway_detourable"},
            apply_before_step="move_to_water_source",
        )
        if detour_injection.get("injected_perturbation", {}).get("status") != "scheduled":
            raise AssertionError(f"detour perturbation must be schedulable before a later step: {detour_injection}")
        detour_dispatch = dispatch_execution_loop_payload(detour_migration["execution_loop_payload"], "robot_sdk")
        if detour_dispatch.get("outcome") != "fact_established":
            raise AssertionError(f"detour perturbation should still allow execution to complete: {detour_dispatch}")
        detour_feedback = next(
            (item for item in detour_dispatch.get("fact_feedback", []) if item.get("step") == "move_to_water_source"),
            None,
        )
        if not detour_feedback or detour_feedback.get("preflight_result") != "detour":
            raise AssertionError(f"mid-run stool perturbation must trigger detour preflight on move step: {detour_dispatch}")
        if not detour_feedback.get("route_adjustment", {}).get("preserved_process_chain"):
            raise AssertionError(f"detour should preserve the process chain and only adjust local route: {detour_feedback}")

        blocked_migration = migrate_experience(migration["intent_translation"]["utterance"])
        blocked_injection = inject_runtime_perturbation(
            blocked_migration["migration_task_id"],
            {"kind": "cup_guard_door_closed"},
            apply_before_step="pick_up_cup",
        )
        if blocked_injection.get("injected_perturbation", {}).get("status") != "scheduled":
            raise AssertionError(f"door perturbation must be schedulable before blocked pickup: {blocked_injection}")
        blocked_dispatch = dispatch_execution_loop_payload(blocked_migration["execution_loop_payload"], "robot_sdk")
        if blocked_dispatch.get("outcome") != "readaptation_required":
            raise AssertionError(f"closed access door must trigger stepwise readaptation instead of blind continuation: {blocked_dispatch}")
        blocked_feedback = next(
            (item for item in blocked_dispatch.get("fact_feedback", []) if item.get("step") == "pick_up_cup"),
            None,
        )
        if not blocked_feedback or blocked_feedback.get("preflight_result") != "blocked":
            raise AssertionError(f"blocked pickup must be stopped by current runtime snapshot preflight: {blocked_dispatch}")
        stepwise_readaptation = blocked_dispatch.get("stepwise_readaptation", {})
        if stepwise_readaptation.get("execution_feasibility", {}).get("result") not in {"partially_inexecutable", "infeasible"}:
            raise AssertionError(f"stepwise readaptation must expose refreshed feasibility after the door closes: {blocked_dispatch}")
        if not any(
            item.get("reason") == "dynamic_environment_blocker"
            for item in stepwise_readaptation.get("execution_feasibility", {}).get("infeasible_reasons", [])
        ):
            raise AssertionError(f"stepwise readaptation must explain the block using current runtime environment: {blocked_dispatch}")

        llm_context_view = build_llm_context_view(migration["migration_task_id"])
        if not llm_context_view.get("usable_as_current_world_state") or llm_context_view.get("source_policy") != "runtime_world_state_snapshot_only":
            raise AssertionError(f"llm context view must be derived only from current runtime snapshot: {llm_context_view}")
        if "cup_contains_water" not in llm_context_view.get("established_facts", []):
            raise AssertionError(f"llm context view must expose current established facts without mutating them: {llm_context_view}")

        concept_library = load_concept_library()
        if not any(item.get("concept_id") == "concept_spatial_region_navigation" for item in concept_library.get("concept_units", [])):
            raise AssertionError(f"concept library must expose reusable concept units: {concept_library}")
        concept_resolution = resolve_concepts_for_intent("走到门旁边，再去操作台拿杯子，到水源处接一杯水", migration["migration_task_id"])
        resolved_concept_ids = [item.get("concept_id") for item in concept_resolution.get("resolved_concepts", [])]
        for expected_concept in ["concept_spatial_region_navigation", "concept_interactive_object_acquisition", "concept_fillable_container", "concept_water_resource_zone"]:
            if expected_concept not in resolved_concept_ids:
                raise AssertionError(f"concept resolution must expose reusable semantic units for the utterance: {concept_resolution}")
        if concept_resolution.get("concept_resolution_policy", {}).get("direct_execution_allowed"):
            raise AssertionError(f"concept resolution must stay above execution and require orchestration: {concept_resolution}")

        llm_prompt_contract = build_llm_prompt_contract("到水源处接一杯水", migration["migration_task_id"])
        if llm_prompt_contract.get("handoff_contract", {}).get("validator_endpoint") != "/llm/candidate/validate":
            raise AssertionError(f"llm prompt contract must point to deterministic validator handoff: {llm_prompt_contract}")
        if llm_prompt_contract.get("handoff_contract", {}).get("direct_execution_allowed"):
            raise AssertionError(f"llm prompt contract must forbid direct execution: {llm_prompt_contract}")

        llm_candidate_intent = handle_agent_query("到水源处接一杯水")
        if llm_candidate_intent.get("semantic_request", {}).get("request_type") != "task_execution":
            raise AssertionError(f"agent query must route task execution input: {llm_candidate_intent}")
        route_result = llm_candidate_intent.get("route_result", {})
        if route_result.get("intent_translation", {}).get("goal_fact") != "cup_contains_water":
            raise AssertionError(f"agent query preview must keep intent translation inside unified route: {llm_candidate_intent}")
        if route_result.get("space_admission", {}).get("decision") != "allowed":
            raise AssertionError(f"agent query preview must expose admission inside unified route: {llm_candidate_intent}")

        valid_llm_candidate = validate_llm_candidate_output(
            {
                "candidate_type": "candidate_plan",
                "goal_fact": "cup_contains_water",
                "candidate_process_chain": ["move_to_counter", "pick_up_cup", "move_to_water_source", "fill_cup_at_water_source"],
                "references_to_facts": ["cup_at_counter", "water_source_available"],
                "confidence": 0.82,
            },
            migration["migration_task_id"],
        )
        if not valid_llm_candidate.get("accepted_structure") or valid_llm_candidate.get("direct_execution_allowed"):
            raise AssertionError(f"llm candidate validator must accept safe structure but still block direct execution: {valid_llm_candidate}")
        invalid_llm_candidate = validate_llm_candidate_output(
            {
                "candidate_type": "candidate_plan",
                "candidate_process_chain": ["move_to_counter", "unknown_step"],
                "established_facts": ["cup_contains_water"],
            },
            migration["migration_task_id"],
        )
        if invalid_llm_candidate.get("accepted_structure"):
            raise AssertionError(f"llm candidate validator must reject runtime-fact writes and unknown steps: {invalid_llm_candidate}")

        location_query = query_runtime_world_state(migration["migration_task_id"], "我现在在哪")
        if location_query.get("answer") != "region_water_source" or location_query.get("query_type") != "executor_location":
            raise AssertionError(f"runtime world state location question must resolve from current snapshot: {location_query}")
        current_action_query = query_runtime_world_state(migration["migration_task_id"], "\u4f60\u73b0\u5728\u5728\u505a\u4ec0\u4e48")
        if current_action_query.get("query_type") != "current_action" or current_action_query.get("answer") != "fill_cup_at_water_source":
            raise AssertionError(f"runtime world state current-action question must resolve from explanation view: {current_action_query}")
        next_step_query = query_runtime_world_state(migration["migration_task_id"], "\u4e0b\u4e00\u6b65\u505a\u4ec0\u4e48")
        if next_step_query.get("query_type") != "next_step" or next_step_query.get("answer") != "none":
            raise AssertionError(f"runtime world state next-step question must expose goal-achieved idle state: {next_step_query}")
        if "\u76ee\u6807\u5df2\u8fbe\u6210" not in (next_step_query.get("reason") or ""):
            raise AssertionError(f"runtime world state next-step reason must explain why there is no further step: {next_step_query}")
        agent_state_query = handle_agent_query("当前杯子有没有水", task_id=migration["migration_task_id"])
        if agent_state_query.get("semantic_request", {}).get("request_type") != "state_query":
            raise AssertionError(f"agent query must route state question: {agent_state_query}")
        if agent_state_query.get("route_result", {}).get("answer") != "true":
            raise AssertionError(f"agent query must answer state question from current snapshot: {agent_state_query}")
        state_explanation = agent_state_query.get("route_result", {}).get("runtime_explanation_view", {})
        if state_explanation.get("status_answers", {}).get("current_action", {}).get("answer") != "fill_cup_at_water_source":
            raise AssertionError(f"agent query state answer must attach runtime explanation view: {agent_state_query}")
        agent_execution_run = handle_agent_query("到水源处接一杯水", scenario="auto", auto_execute=True)
        if agent_execution_run.get("route_result", {}).get("audit_summary", {}).get("outcome") != "completed":
            raise AssertionError(f"agent query auto_execute must run through unified execution path: {agent_execution_run}")
        agent_teaching_query = handle_agent_query("教你：走向操作台，然后拿起杯子")
        if agent_teaching_query.get("route_result", {}).get("decision") != "routed_to_teaching":
            raise AssertionError(f"agent query must route teaching input: {agent_teaching_query}")
        if "走向操作台" not in (agent_teaching_query.get("route_result", {}).get("teaching_feedback", {}).get("acknowledgement") or ""):
            raise AssertionError(f"teaching route must acknowledge parsed teaching steps: {agent_teaching_query}")
        agent_clarification_needed = handle_agent_query("把那个给我弄一下", auto_execute=False)
        if agent_clarification_needed.get("route_result", {}).get("decision") != "clarification_required":
            raise AssertionError(f"ambiguous execution request must require clarification before execution: {agent_clarification_needed}")
        if not agent_clarification_needed.get("route_result", {}).get("clarification_prompt"):
            raise AssertionError(f"clarification-required result must contain clarification prompt: {agent_clarification_needed}")

        fetched_dispatch = get_execution_dispatch(dispatch["dispatch_id"])
        if fetched_dispatch.get("dispatch_id") != dispatch["dispatch_id"]:
            raise AssertionError(f"execution dispatch record must be queryable: {fetched_dispatch}")
        release = release_runtime_world_state(migration["migration_task_id"], "validation_finished")
        if release.get("release_status") != "released" or not release.get("release_token"):
            raise AssertionError(f"runtime world state release must issue token: {release}")
        released_state = get_runtime_world_state(migration["migration_task_id"])
        if released_state.get("runtime_world_state_snapshot", {}).get("snapshot_lifecycle_state") != "released":
            raise AssertionError(f"released runtime world state must be marked released: {released_state}")
        released_llm_context = build_llm_context_view(migration["migration_task_id"])
        if released_llm_context.get("context_status") != "snapshot_released" or released_llm_context.get("usable_as_current_world_state"):
            raise AssertionError(f"released snapshot must not remain usable as llm current-world context: {released_llm_context}")
        released_query = query_runtime_world_state(migration["migration_task_id"], "当前杯子有没有水")
        if released_query.get("answer") != "unknown" or released_query.get("status") != "snapshot_released":
            raise AssertionError(f"released snapshot must not answer as current world state: {released_query}")

        preference_library_before = load_preference_library()
        if not preference_library_before.get("preference_records"):
            raise AssertionError(f"P015 preference library must expose default human preferences: {preference_library_before}")
        recorded_preference = record_preference(
            context_ref="home_a_kitchen",
            preference_signal="forbid",
            human_feedback="不要自动拿起杯子，先请求我确认。",
            applies_to=["step:pick_up_cup", "object:object_cup_white_mug"],
            strength=1.0,
            enforcement_policy="blocking",
        )
        if recorded_preference.get("error"):
            raise AssertionError(f"preference record creation must succeed: {recorded_preference}")
        preference_migration = migrate_experience("到水源处接一杯水")
        if preference_migration.get("execution_feasibility", {}).get("result") != "partially_inexecutable":
            raise AssertionError(f"blocking human preference must constrain later migration feasibility: {preference_migration}")
        if not any(
            item.get("reason") == "human_preference_blocked_step"
            for item in preference_migration.get("execution_feasibility", {}).get("infeasible_reasons", [])
        ):
            raise AssertionError(f"preference-constrained migration must expose P015 reason in infeasible_reasons: {preference_migration}")
        if recorded_preference["preference_record"]["preference_id"] not in preference_migration.get("experience_gap_record", {}).get("preference_refs", []):
            raise AssertionError(f"experience gap must retain blocking preference reference: {preference_migration}")

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
        if not conflict.get("recovery_record"):
            raise AssertionError(f"conflict API run must create a recovery record: {conflict}")
        conflict_recovery = get_recovery_record(conflict["recovery_record"]["recovery_id"])
        if conflict_recovery.get("recovery_id") != conflict["recovery_record"]["recovery_id"]:
            raise AssertionError(f"recovery record must be queryable by id: {conflict_recovery}")
        task_recoveries = get_recovery_records_for_task(conflict["task_id"])
        if not any(item.get("recovery_id") == conflict["recovery_record"]["recovery_id"] for item in task_recoveries.get("recovery_records", [])):
            raise AssertionError(f"recovery records must be queryable by task: {task_recoveries}")
        readaptation = readapt_runtime_conflict(conflict["task_id"], "到水源处接一杯水")
        if readaptation.get("execution_feasibility", {}).get("result") != "requires_human_confirmation":
            raise AssertionError(f"runtime conflict must produce human-confirmation readaptation: {readaptation}")
        if not readaptation.get("runtime_world_state_snapshot", {}).get("runtime_conflicts"):
            raise AssertionError(f"readaptation snapshot must carry runtime conflicts: {readaptation}")
        if not readaptation.get("recovery_record"):
            raise AssertionError(f"readaptation must create a recovery record: {readaptation}")
        if not load_recovery_library().get("recovery_records"):
            raise AssertionError("recovery library must persist generated recovery records")
        agent_clarification = handle_agent_query("为什么不能执行", task_id=readaptation["readaptation_id"])
        if agent_clarification.get("semantic_request", {}).get("request_type") != "clarification":
            raise AssertionError(f"agent query must route clarification input: {agent_clarification}")
        if agent_clarification.get("route_result", {}).get("status") not in {"resolved_from_experience_gap", "resolved_from_execution_feasibility", "resolved_from_audit"}:
            raise AssertionError(f"agent clarification must explain from current runtime context: {agent_clarification}")
        fetched_readaptation = get_readaptation(readaptation["readaptation_id"])
        if fetched_readaptation.get("readaptation_id") != readaptation["readaptation_id"]:
            raise AssertionError(f"readaptation record must be queryable: {fetched_readaptation}")

        simulated = run_process("simulated_success")
        if simulated["audit_summary"]["outcome"] != "completed":
            raise AssertionError("simulated success API run must complete")
        if not any("adapter=simulated_pouring_robot" in event.get("payload_summary", "") for event in simulated["execution_trace"]["events"]):
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
        print("Validated: admit, run success, teach experience, dialogue teaching, concept promotion, stepwise teaching, natural-language causal teaching, explicit route teaching, causal chain solving, causal short-goal solving, P017 migration adaptation, llm context view, llm candidate validation, runtime world release, run channel_conflict, run simulated_success, get audit, get space.")
    finally:
        if original_experience_library is None:
            EXPERIENCE_LIBRARY_FILE.unlink(missing_ok=True)
        else:
            EXPERIENCE_LIBRARY_FILE.write_text(original_experience_library, encoding="utf-8")
        if original_concept_library is None:
            CONCEPT_LIBRARY_FILE.unlink(missing_ok=True)
        else:
            CONCEPT_LIBRARY_FILE.write_text(original_concept_library, encoding="utf-8")
        if original_candidate_library is None:
            CONCEPT_CANDIDATE_LIBRARY_FILE.unlink(missing_ok=True)
        else:
            CONCEPT_CANDIDATE_LIBRARY_FILE.write_text(original_candidate_library, encoding="utf-8")
        if original_preference_library is None:
            PREFERENCE_LIBRARY_FILE.unlink(missing_ok=True)
        else:
            PREFERENCE_LIBRARY_FILE.write_text(original_preference_library, encoding="utf-8")
        if original_recovery_library is None:
            RECOVERY_LIBRARY_FILE.unlink(missing_ok=True)
        else:
            RECOVERY_LIBRARY_FILE.write_text(original_recovery_library, encoding="utf-8")


if __name__ == "__main__":
    main()
