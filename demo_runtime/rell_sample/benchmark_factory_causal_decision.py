from __future__ import annotations

import json
import os
from pathlib import Path
from statistics import mean

from embodied_scene import SESSIONS, execute_command, start_session


OUTPUT = Path(__file__).resolve().parents[1] / "output" / "rell_sample" / "factory_causal_benchmark.json"
SCENARIOS = [
    "把杯子放到苹果上",
    "擦操作台",
    "打开冰箱",
    "拿起苹果",
]


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "mean_ms": round(mean(values), 4),
        "p50_ms": round(percentile(values, 0.50), 4),
        "p95_ms": round(percentile(values, 0.95), 4),
        "p99_ms": round(percentile(values, 0.99), 4),
        "max_ms": round(max(values), 4),
    }


def main() -> None:
    iterations = int(os.environ.get("RELL_CAUSAL_BENCHMARK_ITERATIONS", "500"))
    report = {
        "schema_version": "1.0.0",
        "benchmark": "factory_contract_compiled_causal_decision",
        "iterations_per_scenario": iterations,
        "clock": "perf_counter_ns_monotonic",
        "scope": "single_process_warm_python_runtime_without_network_or_gpu",
        "scenarios": {},
    }
    for utterance in SCENARIOS:
        total_values = []
        solver_values = []
        registry_values = []
        search_values = []
        latest = None
        cache_hits = 0
        for _ in range(iterations):
            session = start_session()
            SESSIONS[session["session_id"]]["available_local_experiences"] = []
            latest = execute_command(session["session_id"], utterance)
            candidate = latest["causal_candidate"]
            total_values.append(candidate["decision_latency"]["input_to_candidate_decision_ms"])
            solver_values.append(candidate["search_metrics"]["total_solver_ms"])
            registry_values.append(candidate["search_metrics"]["registry_compile_ms"])
            search_values.append(candidate["search_metrics"]["backward_search_ms"])
            cache_hits += int(candidate["search_metrics"]["registry_cache_hit"])
        report["scenarios"][utterance] = {
            "candidate_process_chain": latest["causal_candidate"]["candidate_process_chain"],
            "candidate_status": latest["causal_candidate"]["candidate_status"],
            "input_to_candidate_decision": summarize(total_values),
            "causal_solver": summarize(solver_values),
            "registry_compile": summarize(registry_values),
            "backward_search": summarize(search_values),
            "registry_cache_hit_rate": round(cache_hits / iterations, 4),
        }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
