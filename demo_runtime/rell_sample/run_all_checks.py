from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
API_URL = "http://127.0.0.1:8876"


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_python(script: str) -> None:
    print(f"[check] {script}")
    subprocess.run([sys.executable, str(ROOT / script)], cwd=REPO, check=True)


def run_physics_python(script: str) -> None:
    configured = os.environ.get("RELL_PHYSICS_PYTHON")
    default = Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python310" / "python.exe"
    executable = Path(configured) if configured else default
    if not executable.exists():
        raise RuntimeError("MuJoCo validation requires Python 3.10; set RELL_PHYSICS_PYTHON to its executable")
    print(f"[check:physics] {script}")
    subprocess.run([str(executable), str(ROOT / script)], cwd=REPO, check=True)


def post_json(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        f"{API_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(path: str) -> dict:
    with urlopen(f"{API_URL}{path}", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def get_text(path: str) -> str:
    with urlopen(f"{API_URL}{path}", timeout=5) as response:
        return response.read().decode("utf-8")


def run_http_smoke() -> None:
    global API_URL
    print("[check] api_server HTTP smoke")
    port = find_free_port()
    API_URL = f"http://127.0.0.1:{port}"
    env = {**os.environ, "RELL_SAMPLE_PORT": str(port)}
    experience_library_file = ROOT / "data" / "experience_library.json"
    concept_library_file = ROOT / "data" / "concept_library.json"
    concept_candidate_library_file = ROOT / "data" / "concept_candidate_library.json"
    preference_library_file = ROOT / "data" / "preference_record_library.json"
    recovery_library_file = ROOT / "data" / "recovery_record_library.json"
    original_library = experience_library_file.read_text(encoding="utf-8") if experience_library_file.exists() else None
    original_concept_library = concept_library_file.read_text(encoding="utf-8") if concept_library_file.exists() else None
    original_candidate_library = concept_candidate_library_file.read_text(encoding="utf-8") if concept_candidate_library_file.exists() else None
    original_preference_library = preference_library_file.read_text(encoding="utf-8") if preference_library_file.exists() else None
    original_recovery_library = recovery_library_file.read_text(encoding="utf-8") if recovery_library_file.exists() else None
    recovery_library_file.write_text(
        json.dumps({"schema_version": "1.0.0", "recovery_records": []}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "api_server.py")],
        cwd=REPO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.8)
        page = get_text("/")
        health = get_json("/health")
        cognitive_model = get_json("/space/cognitive-model")
        concept_library = get_json("/concept/library")
        preference_library = get_json("/preference/library")
        recovery_library_before = get_json("/recovery/library")
        p017_loop = get_json("/p017/minimal-loop")
        semantic_route = post_json("/semantic/route", {"utterance": "当前杯子有没有水"})
        agent_execution_preview = post_json("/agent/query", {"utterance": "到水源处接一杯水"})
        admit = post_json("/process/admit", {})
        migration = post_json("/experience/migrate", {"utterance": "到水源处接一杯水"})
        corridor_migration = post_json(
            "/experience/migrate",
            {
                "utterance": "到水源处接一杯水",
                "space_id": "site_b_corridor",
                "body_capability_profile": {
                    "executor_id": "http_site_b_mobile_manipulator",
                    "supported_actions": ["navigate_to_region", "grasp_object", "fill_container", "pour_container"],
                },
            },
        )
        corridor_dispatch = post_json(
            "/execution/dispatch",
            {"execution_loop_payload": corridor_migration["execution_loop_payload"], "executor_type": "robot_sdk"},
        )
        migration_state = get_json(f"/runtime_world_state/{migration['migration_task_id']}")
        llm_context_view = post_json("/llm/context-view", {"task_id": migration["migration_task_id"]})
        llm_prompt_contract = post_json(
            "/llm/prompt-contract",
            {"task_id": migration["migration_task_id"], "utterance": "到水源处接一杯水"},
        )
        llm_candidate_intent = post_json(
            "/llm/candidate-intent",
            {"task_id": migration["migration_task_id"], "utterance": "到水源处接一杯水"},
        )
        concept_resolution = post_json(
            "/concept/resolve",
            {"task_id": migration["migration_task_id"], "utterance": "走到门旁边，再去操作台拿杯子，到水源处接一杯水"},
        )
        taught_experience = post_json(
            "/experience/teach",
            {
                "utterance": "走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水",
                "steps": "走向操作台\n拿起杯子\n到水源处\n接一杯水\n倒水",
            },
        )
        concept_candidates = get_json("/concept/candidates")
        promoted_candidate = next(
            (item for item in taught_experience.get("concept_promotion_candidates", []) if item.get("proposal_type") == "create_promoted_concept_unit"),
            None,
        )
        confirmed_candidate = post_json(
            "/concept/candidates/confirm",
            {"candidate_id": promoted_candidate["candidate_id"], "confirmed_by": "http_smoke"},
        ) if promoted_candidate else {"error": "missing_promoted_candidate"}
        promoted_resolution = post_json(
            "/concept/resolve",
            {"task_id": migration["migration_task_id"], "utterance": "给客人倒一杯水"},
        ) if confirmed_candidate.get("promoted_concept_id") else {"resolved_concepts": []}
        llm_candidate_validation = post_json(
            "/llm/candidate/validate",
            {
                "task_id": migration["migration_task_id"],
                "candidate": {
                    "candidate_type": "candidate_plan",
                    "goal_fact": "cup_contains_water",
                    "candidate_process_chain": ["move_to_counter", "pick_up_cup", "move_to_water_source", "fill_cup_at_water_source"],
                    "confidence": 0.77,
                },
            },
        )
        migration_query_before = post_json(
            "/runtime_world_state/query",
            {"task_id": migration["migration_task_id"], "question": "当前杯子有没有水"},
        )
        preference_query_before = post_json(
            "/runtime_world_state/query",
            {"task_id": migration["migration_task_id"], "question": "当前偏好约束是什么"},
        )
        agent_state_query_before = post_json(
            "/agent/query",
            {"task_id": migration["migration_task_id"], "utterance": "当前杯子有没有水"},
        )
        dispatch = post_json(
            "/execution/dispatch",
            {"execution_loop_payload": migration["execution_loop_payload"], "executor_type": "robot_sdk"},
        )
        dispatch_lookup = get_json(f"/execution/dispatch/{dispatch['dispatch_id']}")
        perturb_migration = post_json(
            "/experience/migrate",
            {"utterance": migration.get("intent_translation", {}).get("utterance", "鍒版按婧愬鎺ヤ竴鏉按")},
        )
        perturb = post_json(
            "/runtime_world_state/perturb",
            {
                "task_id": perturb_migration["migration_task_id"],
                "perturbation": {"kind": "stool_in_walkway_detourable"},
                "apply_before_step": "move_to_water_source",
            },
        )
        perturb_dispatch = post_json(
            "/execution/dispatch",
            {"execution_loop_payload": perturb_migration["execution_loop_payload"], "executor_type": "robot_sdk"},
        )
        migration_query_after = post_json(
            "/runtime_world_state/query",
            {"task_id": migration["migration_task_id"], "question": "当前杯子有没有水"},
        )
        migration_location_query = post_json(
            "/runtime_world_state/query",
            {"task_id": migration["migration_task_id"], "question": "我现在在哪"},
        )
        agent_teaching_route = post_json(
            "/agent/query",
            {"utterance": "教你：走向操作台，然后拿起杯子"},
        )
        agent_execution_run = post_json(
            "/agent/query",
            {"utterance": "到水源处接一杯水", "auto_execute": True, "scenario": "auto"},
        )
        teaching_session = post_json("/teaching/session/start", {"utterance": "到水源处接一杯水"})
        teaching_step = post_json(
            "/teaching/session/step",
            {"session_id": teaching_session["session_id"], "teaching_input": "走向操作台"},
        )
        teaching_lookup = get_json(f"/teaching/session/{teaching_session['session_id']}")
        for step_text in ["拿起杯子", "到水源处", "接一杯水"]:
            teaching_step = post_json(
                "/teaching/session/step",
                {"session_id": teaching_session["session_id"], "teaching_input": step_text},
            )
        teaching_finish = post_json(
            "/teaching/session/finish",
            {"session_id": teaching_session["session_id"], "success_confirmed": True},
        )
        release = post_json(
            "/runtime_world_state/release",
            {"task_id": migration["migration_task_id"], "release_reason": "http_smoke_finished"},
        )
        migration_query_released = post_json(
            "/runtime_world_state/query",
            {"task_id": migration["migration_task_id"], "question": "当前杯子有没有水"},
        )
        run_result = post_json(
            "/process/run",
            {"scenario": "channel_conflict", "utterance": "执行倒水冲突演示"},
        )
        simulated_conflict_run = post_json(
            "/process/run",
            {"scenario": "simulated_channel_conflict", "utterance": "执行倒水冲突演示"},
        )
        readaptation = post_json(
            "/runtime_world_state/readapt",
            {"task_id": run_result["task_id"], "utterance": "到水源处接一杯水"},
        )
        readaptation_lookup = get_json(f"/runtime_readaptation/{readaptation['readaptation_id']}")
        recovery_library_after = get_json("/recovery/library")
        recovery_task_lookup = get_json(f"/recovery/task/{run_result['task_id']}")
        recovery_lookup = (
            get_json(f"/recovery/{run_result['recovery_record']['recovery_id']}")
            if run_result.get("recovery_record", {}).get("recovery_id")
            else {"error": "missing_recovery_record"}
        )
        gap_lookup = None
        if readaptation.get("experience_gap_record"):
            gap_lookup = get_json(f"/experience/gap/{readaptation['experience_gap_record']['gap_record_id']}")
        recorded_preference = post_json(
            "/preference/record",
            {
                "context_ref": "home_a_kitchen",
                "preference_signal": "forbid",
                "human_feedback": "不要自动拿起杯子，先请求我确认。",
                "applies_to": ["step:pick_up_cup", "object:object_cup_white_mug"],
                "enforcement_policy": "blocking",
                "strength": 1.0,
            },
        )
        preference_constrained_migration = post_json(
            "/experience/migrate",
            {"utterance": "到水源处接一杯水"},
        )
        audit = get_json(f"/audit/{run_result['task_id']}")
        if "RELL 真实世界经验引擎样品" not in page:
            raise AssertionError("demo page did not render")
        if "mapCupItem" not in page or "updateLearnedStepScene" not in page:
            raise AssertionError("demo page did not include learned experience animation mapping")
        if "dialogueTeachButton" not in page:
            raise AssertionError("demo page did not include dialogue teaching entry")
        if "renderSemanticSignalRows" not in page or "renderRuntimeExplanationRows" not in page:
            raise AssertionError("demo page did not include interaction-layer explanation renderers")
        if "交互判定" not in page or "意图置信度" not in page or "云脑补给" not in page:
            raise AssertionError("demo page did not include interaction-layer visible labels")
        if "p017Button" not in page:
            raise AssertionError("demo page did not include P017 minimal loop entry")
        if "conceptCandidatesButton" not in page or "confirmConceptCandidateButton" not in page:
            raise AssertionError("demo page did not include concept promotion actions")
        if "startTeachingSessionButton" not in page or "stepTeachingSessionButton" not in page:
            raise AssertionError("demo page did not include stepwise teaching entries")
        if health.get("status") != "ok":
            raise AssertionError(f"health failed: {health}")
        if cognitive_model.get("prior_ref") != "semantic_prior_home_a_kitchen_v1":
            raise AssertionError(f"space cognitive model failed: {cognitive_model}")
        if not p017_loop.get("evidence_index") or len(p017_loop.get("evidence_files", [])) < 6:
            raise AssertionError(f"P017 minimal loop endpoint must expose evidence index and segmented files: {p017_loop}")
        if not any(item.get("concept_id") == "concept_spatial_region_navigation" for item in concept_library.get("concept_units", [])):
            raise AssertionError(f"concept library failed: {concept_library}")
        if not preference_library.get("preference_records"):
            raise AssertionError(f"preference library failed: {preference_library}")
        if recovery_library_before.get("recovery_records") not in ([], None):
            raise AssertionError(f"recovery library should start empty in smoke test: {recovery_library_before}")
        if not p017_loop.get("evidence_index") or len(p017_loop.get("evidence_files", {})) != 8:
            raise AssertionError(f"P017 minimal loop endpoint failed: {p017_loop}")
        if semantic_route.get("request_type") != "state_query":
            raise AssertionError(f"semantic route failed: {semantic_route}")
        if agent_execution_preview.get("semantic_request", {}).get("request_type") != "task_execution":
            raise AssertionError(f"agent execution preview route failed: {agent_execution_preview}")
        if agent_execution_preview.get("route_result", {}).get("space_admission", {}).get("decision") != "allowed":
            raise AssertionError(f"agent execution preview admission failed: {agent_execution_preview}")
        if admit.get("decision") != "allowed":
            raise AssertionError(f"admit failed: {admit}")
        if migration.get("execution_feasibility", {}).get("result") != "executable":
            raise AssertionError(f"migration failed: {migration}")
        if corridor_migration.get("current_space_semantic_data", {}).get("space_id") != "site_b_corridor":
            raise AssertionError(f"alternate-space migration failed: {corridor_migration}")
        corridor_refs = {
            item.get("space_binding", {}).get("target_ref") or item.get("object_binding", {}).get("target_ref")
            for item in corridor_migration.get("binding_candidate", {}).get("step_bindings", [])
        }
        if "site_b_reusable_tumbler" not in corridor_refs or "site_b_corridor_dispenser_zone" not in corridor_refs:
            raise AssertionError(f"alternate-space migration did not rebind contract slots: {corridor_migration}")
        if corridor_dispatch.get("outcome") != "fact_established":
            raise AssertionError(f"alternate-space dispatch failed: {corridor_dispatch}")
        if migration_state.get("release_status") != "not_released":
            raise AssertionError(f"runtime world state query failed: {migration_state}")
        if not llm_context_view.get("usable_as_current_world_state"):
            raise AssertionError(f"llm context view failed: {llm_context_view}")
        if llm_prompt_contract.get("handoff_contract", {}).get("validator_endpoint") != "/llm/candidate/validate":
            raise AssertionError(f"llm prompt contract failed: {llm_prompt_contract}")
        if llm_candidate_intent.get("llm_input_contract", {}).get("next_endpoint") != "/llm/candidate/validate":
            raise AssertionError(f"llm candidate intent failed: {llm_candidate_intent}")
        if not any(item.get("concept_id") == "concept_fillable_container" for item in concept_resolution.get("resolved_concepts", [])):
            raise AssertionError(f"concept resolution failed: {concept_resolution}")
        if not taught_experience.get("concept_promotion_candidates"):
            raise AssertionError(f"teaching must expose concept promotion candidates: {taught_experience}")
        if not concept_candidates.get("concept_candidates"):
            raise AssertionError(f"concept candidates endpoint failed: {concept_candidates}")
        if confirmed_candidate.get("status") != "promoted":
            raise AssertionError(f"concept candidate confirm failed: {confirmed_candidate}")
        if confirmed_candidate.get("promoted_concept_id") not in [
            item.get("concept_id") for item in promoted_resolution.get("resolved_concepts", [])
        ]:
            raise AssertionError(f"promoted concept should be reusable in concept resolution: {promoted_resolution}")
        if not llm_candidate_validation.get("accepted_structure") or llm_candidate_validation.get("direct_execution_allowed"):
            raise AssertionError(f"llm candidate validation failed: {llm_candidate_validation}")
        if migration_query_before.get("answer") != "false":
            raise AssertionError(f"runtime world state question should answer false before fill: {migration_query_before}")
        if preference_query_before.get("query_type") != "preference_summary" or not preference_query_before.get("evidence", {}).get("active_preferences"):
            raise AssertionError(f"runtime world state should answer preference summary from snapshot: {preference_query_before}")
        if agent_state_query_before.get("semantic_request", {}).get("request_type") != "state_query":
            raise AssertionError(f"agent state route failed: {agent_state_query_before}")
        if dispatch.get("outcome") != "fact_established":
            raise AssertionError(f"execution dispatch failed: {dispatch}")
        if dispatch_lookup.get("dispatch_id") != dispatch["dispatch_id"]:
            raise AssertionError(f"execution dispatch lookup failed: {dispatch_lookup}")
        if perturb.get("injected_perturbation", {}).get("status") != "scheduled":
            raise AssertionError(f"runtime perturbation endpoint failed: {perturb}")
        detour_feedback = next(
            (item for item in perturb_dispatch.get("fact_feedback", []) if item.get("step") == "move_to_water_source"),
            None,
        )
        if perturb_dispatch.get("outcome") != "fact_established" or not detour_feedback or detour_feedback.get("preflight_result") != "detour":
            raise AssertionError(f"runtime perturbation detour flow failed: {perturb_dispatch}")
        if migration_query_after.get("answer") != "true":
            raise AssertionError(f"runtime world state question should answer true after fill: {migration_query_after}")
        if migration_location_query.get("answer") != "region_water_source":
            raise AssertionError(f"runtime world state should answer current location from snapshot: {migration_location_query}")
        if agent_teaching_route.get("route_result", {}).get("decision") != "routed_to_teaching":
            raise AssertionError(f"agent teaching route failed: {agent_teaching_route}")
        if agent_execution_run.get("route_result", {}).get("audit_summary", {}).get("outcome") != "completed":
            raise AssertionError(f"agent execution run failed: {agent_execution_run}")
        if teaching_session.get("status") != "teaching_in_progress":
            raise AssertionError(f"stepwise teaching start failed: {teaching_session}")
        if not teaching_step.get("step_feedback") or teaching_step["step_feedback"][0].get("status") != "executed":
            raise AssertionError(f"stepwise teaching step failed: {teaching_step}")
        if teaching_lookup.get("session_id") != teaching_session["session_id"]:
            raise AssertionError(f"stepwise teaching lookup failed: {teaching_lookup}")
        if teaching_finish.get("status") != "experience_saved":
            raise AssertionError(f"stepwise teaching finish failed: {teaching_finish}")
        if teaching_finish.get("release_result", {}).get("release_status") != "released":
            raise AssertionError(f"stepwise teaching release failed: {teaching_finish}")
        if release.get("release_status") != "released" or not release.get("release_token"):
            raise AssertionError(f"runtime world state release failed: {release}")
        if migration_query_released.get("answer") != "unknown" or migration_query_released.get("status") != "snapshot_released":
            raise AssertionError(f"released runtime world state should not answer as current state: {migration_query_released}")
        if run_result["audit_summary"]["outcome"] != "requires_human_confirmation":
            raise AssertionError(f"run failed: {run_result}")
        if not run_result.get("recovery_record"):
            raise AssertionError(f"recovery record must be returned for conflict run: {run_result}")
        if recovery_lookup.get("recovery_id") != run_result["recovery_record"]["recovery_id"]:
            raise AssertionError(f"recovery lookup failed: {recovery_lookup}")
        if not any(item.get("recovery_id") == run_result["recovery_record"]["recovery_id"] for item in recovery_task_lookup.get("recovery_records", [])):
            raise AssertionError(f"task recovery lookup failed: {recovery_task_lookup}")
        if readaptation.get("execution_feasibility", {}).get("result") != "requires_human_confirmation":
            raise AssertionError(f"runtime readaptation failed: {readaptation}")
        if readaptation_lookup.get("readaptation_id") != readaptation["readaptation_id"]:
            raise AssertionError(f"runtime readaptation lookup failed: {readaptation_lookup}")
        if not readaptation.get("recovery_record"):
            raise AssertionError(f"readaptation must create recovery record: {readaptation}")
        if len(recovery_library_after.get("recovery_records", [])) < 2:
            raise AssertionError(f"recovery library must contain runtime and readaptation records: {recovery_library_after}")
        if gap_lookup and gap_lookup.get("gap_record_id") != readaptation["experience_gap_record"]["gap_record_id"]:
            raise AssertionError(f"experience gap lookup failed: {gap_lookup}")
        if recorded_preference.get("preference_record", {}).get("preference_signal") != "forbid":
            raise AssertionError(f"preference record endpoint failed: {recorded_preference}")
        if preference_constrained_migration.get("execution_feasibility", {}).get("result") != "partially_inexecutable":
            raise AssertionError(f"preference-constrained migration failed: {preference_constrained_migration}")
        if not any(
            item.get("reason") == "human_preference_blocked_step"
            for item in preference_constrained_migration.get("execution_feasibility", {}).get("infeasible_reasons", [])
        ):
            raise AssertionError(f"preference-constrained migration must expose P015 reason: {preference_constrained_migration}")
        if not any(
            "adapter=simulated_pouring_robot" in event.get("payload_summary", "")
            for event in simulated_conflict_run["execution_trace"]["events"]
        ):
            raise AssertionError("HTTP smoke did not use simulated adapter")
        if audit.get("outcome") != "requires_human_confirmation":
            raise AssertionError(f"audit failed: {audit}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
        if original_library is None:
            experience_library_file.unlink(missing_ok=True)
        else:
            experience_library_file.write_text(original_library, encoding="utf-8")
        if original_concept_library is None:
            concept_library_file.unlink(missing_ok=True)
        else:
            concept_library_file.write_text(original_concept_library, encoding="utf-8")
        if original_candidate_library is None:
            concept_candidate_library_file.unlink(missing_ok=True)
        else:
            concept_candidate_library_file.write_text(original_candidate_library, encoding="utf-8")
        if original_preference_library is None:
            preference_library_file.unlink(missing_ok=True)
        else:
            preference_library_file.write_text(original_preference_library, encoding="utf-8")
        if original_recovery_library is None:
            recovery_library_file.unlink(missing_ok=True)
        else:
            recovery_library_file.write_text(original_recovery_library, encoding="utf-8")
    print("[ok] api_server HTTP smoke")


def main() -> None:
    run_python("validate_stage_zero.py")
    run_python("validate_digital_space.py")
    run_python("validate_adapter_contract.py")
    run_python("validate_runtime_sample.py")
    run_python("validate_simulated_robot_sample.py")
    run_python("validate_api_sample.py")
    run_python("validate_p011_experience_internalization.py")
    run_python("validate_p013_task_semantics.py")
    run_python("validate_p014_execution_recovery.py")
    run_python("validate_p015_preference_alignment.py")
    run_python("validate_p017_minimal_loop.py")
    run_python("validate_p017_generalization_pressure.py")
    run_python("validate_p019_behavior_scenarios.py")
    run_physics_python("validate_p020_minimal_physics.py")
    run_http_smoke()
    print("All RELL sample checks passed.")


if __name__ == "__main__":
    main()
