from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from embodied_scene import SESSIONS, _compose_session_language, begin_motion_command, start_session
from runtime_core import run_simulated_runtime_sample
from concept_core.relative_spatial_planning import build_relative_spatial_plan_contract
from validate_failure_recovery_architecture import (
    validate_conflicting_language_correction_requires_observation,
    validate_failure_rebuilds_from_authoritative_world,
    validate_human_possession_preserves_language_role_span,
    validate_language_correction_enters_evidence_gate,
    validate_new_task_retires_recovery_contract,
)
from validate_water_delivery_loop import drain_service


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmarks" / "p020_natural_language_benchmark_v1.json"
OUTPUT = ROOT / "demo_runtime" / "output" / "rell_sample" / "p020_natural_language_benchmark"
DATA = ROOT / "demo_runtime" / "rell_sample" / "data"


def _operators(analysis: dict[str, Any]) -> list[str]:
    return list((analysis.get("canonical_frame") or {}).get("operators", []))


def _result_view(result: dict[str, Any]) -> dict[str, Any]:
    immediate = result.get("immediate_result") or result
    intent = result.get("long_horizon_intent") or immediate.get("long_horizon_intent") or {}
    language = result.get("language_understanding") or immediate.get("language_understanding") or {}
    role_bindings = intent.get("role_bindings") or language.get("role_bindings") or {}
    process_resolution = (
        result.get("process_template_resolution")
        or immediate.get("process_template_resolution")
        or language.get("process_template_resolution")
        or {}
    )
    return {
        "status": result.get("status") or immediate.get("status"),
        "operators": language.get("operators", []),
        "speech_act": language.get("speech_act"),
        "theme_entity_ref": role_bindings.get("theme") if isinstance(role_bindings.get("theme"), str) else (role_bindings.get("theme") or {}).get("entity_ref"),
        "destination_entity_ref": role_bindings.get("destination") if isinstance(role_bindings.get("destination"), str) else (role_bindings.get("destination") or {}).get("entity_ref"),
        "runtime_fact_committed": bool(result.get("runtime_fact_committed") or immediate.get("runtime_fact_committed")),
        "pending_role": result.get("pending_role") or immediate.get("pending_role"),
        "template_id": process_resolution.get("template_id"),
        "reported_event_types": [
            item.get("reported_event_type") or item.get("event_type")
            for item in (language.get("situated_event_frame") or {}).get(
                "reported_state_candidates", []
            )
            if item.get("reported_event_type") or item.get("event_type")
        ],
    }


def _matches(view: dict[str, Any], expected: dict[str, Any], analysis: dict[str, Any] | None = None) -> tuple[bool, list[str]]:
    failures: list[str] = []
    operators = view.get("operators", [])
    if "operators" in expected and operators != expected["operators"]:
        failures.append(f"operators={operators!r}")
    if "operators_include" in expected and expected["operators_include"] not in operators:
        failures.append(f"missing_operator={expected['operators_include']!r}")
    for field in ("status", "speech_act", "theme_entity_ref", "destination_entity_ref", "pending_role", "template_id"):
        if field in expected and view.get(field) != expected[field]:
            failures.append(f"{field}={view.get(field)!r}")
    if expected.get("event_frame_count") is not None and len((analysis or {}).get("event_frames", [])) != expected["event_frame_count"]:
        failures.append("event_frame_count_mismatch")
    if expected.get("reported_event_type") and expected["reported_event_type"] not in view.get("reported_event_types", []):
        failures.append("reported_event_type_missing")
    if expected.get("runtime_fact_committed") is not None and view.get("runtime_fact_committed") != expected["runtime_fact_committed"]:
        failures.append("runtime_fact_commit_boundary")
    if expected.get("not_motion_started") and view.get("status") == "motion_started":
        failures.append("unexpected_motion_started")
    if expected.get("spatial_relation") and analysis:
        semantic_roles = (
            (analysis.get("semantic_constraint_frame") or {}).get("roles") or {}
        )
        relations = [
            role.get("spatial_relation")
            for role in [
                *(analysis.get("role_bindings") or {}).values(),
                *semantic_roles.values(),
            ]
            if isinstance(role, dict)
        ]
        workset = (
            ((analysis.get("rcir") or {}).get("grounded_causal_graph") or {}).get(
                "relation_hypothesis_workset"
            )
            or {}
        )
        relations.extend(
            item.get("name")
            for item in workset.get("candidates", [])
            if item.get("predicate_id") == workset.get("selected_predicate_ref")
        )
        if expected["spatial_relation"] not in relations:
            failures.append("spatial_relation_missing")
    if expected.get("temporal_scope") and analysis:
        frame = analysis.get("situated_event_frame") or {}
        if frame.get("temporal_scope") != expected["temporal_scope"]:
            failures.append(f"temporal_scope={frame.get('temporal_scope')!r}")
    return not failures, failures


def _category(case: dict[str, Any]) -> str:
    case_id = case["id"]
    if "historical" in case_id or "return" in case_id:
        return "指代和历史省略"
    if "compound" in case_id or "connector" in case_id:
        return "复合任务与语篇"
    if any(token in case_id for token in ("surface", "tray", "support", "human_relative", "landmark_")):
        return "空间关系"
    if "reported" in case_id:
        return "报告与事实区分"
    if "ambiguous" in case_id or "unknown_process" in case_id:
        return "询问与澄清"
    if "unknown_concept" in case_id:
        return "新概念与未知动词"
    return "角色落地"


def _expand_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand only paraphrase families already covered by independent regressions."""
    expanded = list(cases)
    connectors = [
        "把杯子放到桌面，然后用高脚杯接水给我",
        "把杯子放到桌面，接着用高脚杯接水给我",
        "把杯子放到桌面，随后用高脚杯接水给我",
        "把杯子放到桌面，再然后用高脚杯接水给我",
        "把杯子放到桌面之后用高脚杯接水给我",
        "把杯子放到桌面以后用高脚杯接水给我",
        "把杯子放到桌面而后用高脚杯接水给我",
        "先把杯子放到桌面再用高脚杯接水给我",
    ]
    for index, utterance in enumerate(connectors, 1):
        expanded.append({
            "id": f"generated_connector_{index:02d}",
            "layer": "semantic",
            "utterance": utterance,
            "expected": {"operators": ["place_object", "fill_container"], "event_frame_count": 2},
        })
    markers = ("刚才", "刚刚", "之前", "先前", "上次", "上回", "方才", "此前")
    verbs = ("拿", "拿起", "取")
    supports = ("桌子", "桌面", "台面")
    forms = (
        lambda marker, verb, support: f"把杯子放到{marker}你{verb}过杯子的{support}",
        lambda marker, verb, support: f"把杯子放到{marker}你{verb}过它的{support}",
        lambda marker, verb, support: f"把杯子放到{marker}你{verb}过的{support}",
    )
    index = 0
    for marker in markers:
        for verb in verbs:
            for support in supports:
                for build in forms:
                    index += 1
                    expanded.append({
                        "id": f"generated_historical_{index:03d}",
                        "layer": "semantic",
                        "utterance": build(marker, verb, support),
                        "expected": {"operators_include": "place_object"},
                    })
    return expanded


def _physical_fixture_results() -> list[dict[str, Any]]:
    expected = {
        "simulated_success": ("completed", "completed", "established"),
        "simulated_no_water": ("requires_human_confirmation", "awaiting_human_confirmation", None),
        "simulated_channel_conflict": ("requires_human_confirmation", "awaiting_human_confirmation", "conflicted"),
    }
    results = []
    for scenario, (outcome, runtime_state, fact_state) in expected.items():
        result = run_simulated_runtime_sample(DATA, scenario)
        audit = result["audit_summary"]
        state = result["stage_runtime_state"]
        facts = {item["fact_id"]: item["state"] for item in audit["fact_summary"]}
        passed = audit["outcome"] == outcome and state["runtime_state"] == runtime_state
        if fact_state is not None:
            passed = passed and facts.get("cup_has_water") == fact_state
        results.append({
            "id": f"physical_{scenario}",
            "category": "P016物理验真",
            "layer": "physical",
            "passed": passed,
            "failures": [] if passed else ["physical_outcome_mismatch"],
            "observed": {
                "scenario": scenario,
                "outcome": audit["outcome"],
                "runtime_state": state["runtime_state"],
                "cup_has_water": facts.get("cup_has_water"),
                "goal_established": facts.get("cup_has_water") == "established",
                "runtime_fact_committed": facts.get("cup_has_water") == "established",
            },
            "diagnostics": {
                "semantic_parse_correct": None,
                "role_grounding_correct": None,
                "inquiry_correct": None,
                "planning_success": None,
                "physical_verification_passed": passed,
                "safe_rejection": passed if scenario != "simulated_success" else None,
            },
        })
    return results


def _recovery_fixture_results() -> list[dict[str, Any]]:
    fixtures = (
        ("human_possession_role_span", validate_human_possession_preserves_language_role_span),
        ("authoritative_world_rebuild", validate_failure_rebuilds_from_authoritative_world),
        ("new_task_retires_old_recovery", validate_new_task_retires_recovery_contract),
        ("matching_report_enters_evidence_gate", validate_language_correction_enters_evidence_gate),
        ("conflicting_report_requires_observation", validate_conflicting_language_correction_requires_observation),
    )
    results = []
    for fixture_id, fixture in fixtures:
        failures = []
        try:
            fixture()
        except AssertionError as error:
            failures.append(str(error))
        passed = not failures
        results.append({
            "id": f"recovery_{fixture_id}",
            "category": "结构化恢复",
            "layer": "recovery",
            "passed": passed,
            "failures": failures,
            "observed": {
                "fixture": fixture_id,
                "current_fact_pruning_reentered": passed,
                "surface_text_reparsed": False if passed else None,
                "old_motion_path_reused": False if passed else None,
                "runtime_fact_committed": False,
            },
            "diagnostics": {
                "semantic_parse_correct": None,
                "role_grounding_correct": None,
                "inquiry_correct": None,
                "structured_recovery_success": passed,
                "planning_success": None,
                "physical_verification_passed": None,
                "safe_rejection": passed if "conflicting" in fixture_id else None,
            },
        })
    return results


def _planning_contract_fixture_results() -> list[dict[str, Any]]:
    fixtures = (
        ("near_human", "站到我身边", "navigate_to_relative_human_zone"),
        ("in_front_of", "站到我前面", "navigate_to_front_region"),
        ("behind", "站到我后面", "navigate_to_rear_region"),
        ("facing", "面向我", "orient_toward_reference"),
        ("beside", "走到操作台A旁边", "navigate_to_lateral_relation"),
        ("between", "站到操作台A和操作台B之间", "navigate_to_between_region"),
    )
    results = []
    for relation, utterance, expected_process in fixtures:
        started = start_session("home_humanoid", "hospitality_guest")
        analysis = _compose_session_language(SESSIONS[started["session_id"]], utterance)
        plan = build_relative_spatial_plan_contract(analysis)
        passed = bool(
            plan
            and plan.get("relation") == relation
            and plan.get("process_contract") == expected_process
            and plan.get("control_gateway") == "P018"
            and plan.get("verification_gateway") == "P016"
            and plan.get("direct_execution_allowed") is False
        )
        results.append({
            "id": f"planning_contract_{relation}",
            "category": "规划合同编译",
            "layer": "planning_contract",
            "passed": passed,
            "failures": [] if passed else ["planning_contract_mismatch"],
            "observed": {
                "relation": relation,
                "process_contract": (plan or {}).get("process_contract"),
                "verification_contract": (plan or {}).get("verification_contract"),
                "candidate_only": True,
                "runtime_fact_committed": False,
            },
            "diagnostics": {
                "semantic_parse_correct": None,
                "role_grounding_correct": None,
                "historical_context_correct": None,
                "inquiry_correct": None,
                "structured_recovery_success": None,
                "planning_contract_compiled": passed,
                "planning_success": None,
                "physical_verification_passed": None,
                "safe_rejection": None,
            },
        })
    return results


def _runtime_planning_fixture_results() -> list[dict[str, Any]]:
    fixtures = (
        ("refill_explicit_mug", "用白色马克杯给我接水", "motion_started"),
        ("navigate_near_human", "站到我身边", "motion_started"),
        ("place_requires_confirmation", "把白色马克杯放到操作台B", "requires_human_confirmation"),
        ("grasp_requires_confirmation", "拿起白色马克杯", ("requires_human_confirmation", "process_grounding_clarification_required")),
        ("beside_executor_contract", "走到操作台A旁边", "motion_started"),
        ("facing_executor_contract", "面向我", "motion_started"),
        ("front_region_blocked_by_current_clearance", "站到我前面", "contextual_spatial_motion_blocked"),
        ("rear_region_blocked_by_current_clearance", "站到我后面", "contextual_spatial_motion_blocked"),
        ("between_executor_contract", "站到操作台A和操作台B之间", "motion_started"),
    )
    results = []
    for fixture_id, utterance, expected_status in fixtures:
        started = start_session("home_humanoid", "hospitality_guest")
        result = begin_motion_command(started["session_id"], utterance)
        immediate = result.get("immediate_result") or result
        status = result.get("status") or immediate.get("status")
        expected_statuses = (expected_status,) if isinstance(expected_status, str) else expected_status
        passed = status in expected_statuses
        results.append({
            "id": f"runtime_planning_{fixture_id}",
            "category": "运行时规划决策",
            "layer": "runtime_planning",
            "passed": passed,
            "failures": [] if passed else [f"status={status!r}"],
            "observed": {
                "status": status,
                "expected_status": expected_statuses[0] if len(expected_statuses) == 1 else None,
                "expected_statuses": list(expected_statuses),
                "motion_started": status == "motion_started",
                "safe_block": status in {"factory_concept_recognized_execution_gap", "concept_gap_clarification_required", "contextual_spatial_motion_blocked"},
                "runtime_fact_committed": bool(result.get("runtime_fact_committed") or immediate.get("runtime_fact_committed")),
            },
            "diagnostics": {
                "semantic_parse_correct": None,
                "role_grounding_correct": None,
                "historical_context_correct": None,
                "inquiry_correct": None,
                "structured_recovery_success": None,
                "planning_contract_compiled": None,
                "runtime_planning_decision_correct": passed,
                "planning_success": passed if expected_statuses == ("motion_started",) else None,
                "physical_verification_passed": None,
                "safe_rejection": passed if set(expected_statuses).intersection({"factory_concept_recognized_execution_gap", "concept_gap_clarification_required", "contextual_spatial_motion_blocked"}) else None,
            },
        })
    return results


def _runtime_execution_fixture_results() -> list[dict[str, Any]]:
    fixtures = (
        (
            "water_service_complete",
            "用白色马克杯给我接水",
            ["target_object_in_gripper", "container_filled", "human_received_filled_container"],
        ),
        (
            "near_human_navigation_complete",
            "站到我身边",
            ["executor_near_object"],
        ),
        (
            "beside_navigation_complete",
            "走到操作台A旁边",
            ["executor_beside_object"],
        ),
        (
            "facing_orientation_complete",
            "面向我",
            ["executor_facing_reference"],
        ),
        (
            "between_navigation_complete",
            "站到操作台A和操作台B之间",
            ["executor_between_references"],
        ),
    )
    results = []
    for fixture_id, utterance, expected_facts in fixtures:
        started = start_session("home_humanoid", "hospitality_guest")
        command = begin_motion_command(started["session_id"], utterance)
        failures = []
        outcomes = []
        try:
            outcomes = drain_service(command)
        except AssertionError as error:
            failures.append(str(error))
        terminal_facts = [item.get("terminal_fact") for item in outcomes]
        passed = not failures and terminal_facts == expected_facts and all(item.get("status") == "fact_established" for item in outcomes)
        results.append({
            "id": f"runtime_execution_{fixture_id}",
            "category": "运行时执行闭环",
            "layer": "runtime_execution",
            "passed": passed,
            "failures": failures or ([] if passed else [f"terminal_facts={terminal_facts!r}"]),
            "observed": {
                "initial_status": command.get("status"),
                "terminal_facts": terminal_facts,
                "expected_terminal_facts": expected_facts,
                "all_terminal_facts_verified": all(item.get("status") == "fact_established" for item in outcomes),
                "execution_completed": passed,
                "runtime_fact_committed": passed,
            },
            "diagnostics": {
                "semantic_parse_correct": None,
                "role_grounding_correct": None,
                "historical_context_correct": None,
                "inquiry_correct": None,
                "structured_recovery_success": None,
                "planning_contract_compiled": None,
                "runtime_planning_decision_correct": None,
                "planning_success": command.get("status") == "motion_started",
                "execution_completion": passed,
                "physical_verification_passed": passed,
                "safe_rejection": None,
            },
        })
    return results


def run() -> dict[str, Any]:
    benchmark = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    cases = _expand_cases(benchmark["cases"])
    results = []
    for case in cases:
        session_info = start_session("home_humanoid", "hospitality_guest")
        session_id = session_info["session_id"]
        session = SESSIONS[session_id]
        if case["layer"] == "semantic":
            analysis = _compose_session_language(session, case["utterance"])
            view = _result_view({"language_understanding": {
                "operators": _operators(analysis),
                "speech_act": analysis.get("speech_act"),
                "role_bindings": analysis.get("role_bindings", {}),
                "situated_event_frame": analysis.get("situated_event_frame", {}),
            }, "runtime_fact_committed": False})
            matched, failures = _matches(view, case["expected"], analysis)
        else:
            result = begin_motion_command(session_id, case["utterance"])
            view = _result_view(result)
            matched, failures = _matches(view, case["expected"])
        inquiry_statuses = {"role_clarification_required", "contextual_affordance_disambiguation_required", "process_slot_clarification_required"}
        results.append({
            "id": case["id"],
            "category": _category(case),
            "layer": case["layer"],
            "passed": matched,
            "failures": failures,
            "observed": view,
            "diagnostics": {
                "semantic_parse_correct": matched if case["layer"] == "semantic" else None,
                "role_grounding_correct": matched if case["layer"] == "semantic" and any(key in case["expected"] for key in ("theme_entity_ref", "destination_entity_ref", "spatial_relation")) else None,
                "historical_context_correct": matched if _category(case) == "指代和历史省略" else None,
                "inquiry_correct": matched if view.get("status") in inquiry_statuses else None,
                "planning_success": view.get("status") == "motion_started" if case["layer"] == "interaction" else None,
                "physical_verification_passed": view.get("runtime_fact_committed") if view.get("runtime_fact_committed") else None,
                "safe_rejection": matched if case["expected"].get("not_motion_started") else None,
            },
        })
    results.extend(_physical_fixture_results())
    results.extend(_recovery_fixture_results())
    results.extend(_planning_contract_fixture_results())
    results.extend(_runtime_planning_fixture_results())
    results.extend(_runtime_execution_fixture_results())
    totals = {"cases": len(results), "passed": sum(item["passed"] for item in results)}
    applicable = {
        "semantic_parse": [item for item in results if item["layer"] == "semantic"],
        "role_grounding": [item for item in results if item["diagnostics"].get("role_grounding_correct") is not None],
        "historical_context": [item for item in results if item["diagnostics"].get("historical_context_correct") is not None],
        "inquiry_correctness": [item for item in results if item["layer"] == "interaction" and item["observed"].get("status") in {"role_clarification_required", "contextual_affordance_disambiguation_required", "process_slot_clarification_required"}],
        "planning_contract_compilation": [item for item in results if item["layer"] == "planning_contract"],
        "runtime_planning_decision": [item for item in results if item["layer"] == "runtime_planning"],
        "runtime_motion_started": [item for item in results if item["layer"] == "runtime_planning" and item["observed"].get("expected_statuses") == ["motion_started"]],
        "runtime_execution_completion": [item for item in results if item["layer"] == "runtime_execution"],
        "terminal_fact_verification": [item for item in results if item["layer"] == "runtime_execution"],
        "planning_success": [item for item in results if item["layer"] == "interaction" and item["observed"].get("status") == "motion_started"],
        "structured_recovery": [item for item in results if item["layer"] == "recovery"],
        "physical_verification": [item for item in results if item["layer"] == "physical"],
        "safe_rejection": [item for item in results if item["diagnostics"].get("safe_rejection") is not None],
    }
    layered_statistics = {}
    for name, items in applicable.items():
        layered_statistics[name] = {
            "applicable_cases": len(items),
            "passed": sum(item["passed"] for item in items),
            "pass_rate": (sum(item["passed"] for item in items) / len(items)) if items else None,
            "status": "measured" if items else "not_applicable_in_current_fixture",
        }
    physical_items = applicable["physical_verification"]
    layered_statistics["physical_goal_establishment"] = {
        "applicable_cases": len(physical_items),
        "passed": sum(bool(item["observed"].get("goal_established")) for item in physical_items),
        "pass_rate": (sum(bool(item["observed"].get("goal_established")) for item in physical_items) / len(physical_items)) if physical_items else None,
        "status": "measured" if physical_items else "not_applicable_in_current_fixture",
        "note": "Failure fixtures are expected to reject safely; this metric is not outcome-classification accuracy.",
    }
    category_statistics = {}
    for category in sorted({item["category"] for item in results}):
        items = [item for item in results if item["category"] == category]
        category_statistics[category] = {
            "cases": len(items),
            "passed": sum(item["passed"] for item in items),
            "pass_rate": sum(item["passed"] for item in items) / len(items),
        }
    report = {"schema_version": "1.7.0", "benchmark_id": "p020_natural_language_benchmark_v1", "totals": totals, "pass_rate": totals["passed"] / totals["cases"] if totals["cases"] else 0.0, "layered_statistics": layered_statistics, "category_statistics": category_statistics, "results": results}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    report = run()
    print(json.dumps(report["totals"] | {"pass_rate": report["pass_rate"]}, ensure_ascii=False))
    raise SystemExit(0 if report["totals"]["passed"] == report["totals"]["cases"] else 1)
