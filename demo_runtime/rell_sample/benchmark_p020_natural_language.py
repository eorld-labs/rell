from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from embodied_scene import SESSIONS, _compose_session_language, begin_motion_command, start_session


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmarks" / "p020_natural_language_benchmark_v1.json"
OUTPUT = ROOT / "demo_runtime" / "output" / "rell_sample" / "p020_natural_language_benchmark"


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


def run() -> dict[str, Any]:
    cases = json.loads(BENCHMARK.read_text(encoding="utf-8"))["cases"]
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
        results.append({"id": case["id"], "layer": case["layer"], "passed": matched, "failures": failures, "observed": view})
    totals = {"cases": len(results), "passed": sum(item["passed"] for item in results)}
    report = {"schema_version": "1.0.0", "benchmark_id": "p020_natural_language_benchmark_v1", "totals": totals, "pass_rate": totals["passed"] / totals["cases"] if totals["cases"] else 0.0, "results": results}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    report = run()
    print(json.dumps(report["totals"] | {"pass_rate": report["pass_rate"]}, ensure_ascii=False))
    raise SystemExit(0 if report["totals"]["passed"] == report["totals"]["cases"] else 1)
