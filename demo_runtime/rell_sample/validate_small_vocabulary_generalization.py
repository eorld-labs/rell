from __future__ import annotations

import json
import math
from pathlib import Path
from time import perf_counter_ns
from typing import Any, Callable

from concept_core.concept_gap_dialogue import continue_concept_gap_dialogue, start_concept_gap_dialogue
from concept_core.perceptual_grounding import load_object_concepts
from embodied_scene import execute_command, load_scene, start_session


OUTPUT = Path(__file__).resolve().parents[1] / "output" / "rell_sample" / "small_vocabulary_generalization.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def percentile(values: list[float], percentage: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * percentage) - 1)
    return round(ordered[index], 4)


def main() -> None:
    scene = load_scene()
    runtime_objects = scene["objects"]
    object_concepts = load_object_concepts()["concepts"]
    results: list[dict[str, Any]] = []
    latencies_ms: list[float] = []

    def start(utterance: str) -> dict[str, Any]:
        started_ns = perf_counter_ns()
        result = start_concept_gap_dialogue(
            utterance=utterance,
            runtime_objects=runtime_objects,
            object_concepts=object_concepts,
            world_revision=1,
        )
        latencies_ms.append((perf_counter_ns() - started_ns) / 1_000_000)
        return result

    def record(name: str, runner: Callable[[], None]) -> None:
        try:
            runner()
        except AssertionError as error:
            results.append({"case": name, "passed": False, "error": str(error)})
        else:
            results.append({"case": name, "passed": True})

    def assert_safe_contract(result: dict[str, Any]) -> dict[str, Any]:
        contract = result.get("compiled_contract")
        require(bool(contract), f"expected compiled contract: {result}")
        require(contract["candidate_only"], f"candidate boundary missing: {contract}")
        require(not contract["direct_execution_allowed"], f"temporary concept gained execution authority: {contract}")
        require(contract["must_reenter_orchestration_layer"], f"temporary concept bypassed orchestration: {contract}")
        require(contract["knowledge_boundary"]["requires_embodied_teaching"], f"unknown mechanism skipped teaching: {contract}")
        return contract

    complete_cases = [
        (
            "explicit_if_make_verify",
            "如果水果散落，就归整苹果，让苹果和其他水果都在收纳区，看到所有水果都在收纳区就算完成",
            "苹果和其他水果都在收纳区",
            "看到所有水果都在收纳区",
            "水果散落",
        ),
        (
            "result_and_success_standard",
            "归拢苹果，结果是苹果位于收纳区，以视觉确认苹果位于收纳区为成功标准",
            "苹果位于收纳区",
            "视觉确认苹果位于收纳区",
            None,
        ),
        (
            "until_as_goal_boundary",
            "整理苹果，直到苹果进入收纳区为止",
            "苹果进入收纳区",
            "苹果进入收纳区",
            None,
        ),
        (
            "unique_pronoun_reference",
            "码齐苹果，让它和其他水果在一起，检测到全部水果位于同一区域才算成功",
            "苹果和其他水果在一起",
            "检测到全部水果位于同一区域",
            None,
        ),
    ]

    for name, utterance, postcondition, verification, precondition in complete_cases:
        def run_complete(
            utterance: str = utterance,
            postcondition: str = postcondition,
            verification: str = verification,
            precondition: str | None = precondition,
        ) -> None:
            result = start(utterance)
            contract = assert_safe_contract(result)
            effect = contract["effect_contract"]
            require(effect["human_readable_postcondition"] == postcondition, f"wrong postcondition: {effect}")
            require(effect["verification"] == ["human_described_verification:" + verification], f"wrong verification: {effect}")
            if precondition:
                require("human_described_precondition:" + precondition in effect["requires"], f"precondition missing: {effect}")
            require(contract["semantic_roles"]["target"]["entity_ref"] == "apple_a", f"wrong target: {contract}")

        record(name, run_complete)

    def missing_target() -> None:
        result = start("请归整一下")
        require(result["dialogue"]["pending_slot"] == "target_entity", f"target was guessed: {result}")
        require(result.get("compiled_contract") is None, f"ungrounded target compiled: {result}")

    record("missing_target_asks_only_target", missing_target)

    def missing_result() -> None:
        result = start("请归整苹果")
        require(result["dialogue"]["pending_slot"] == "desired_postcondition", f"wrong first missing slot: {result}")
        require(result["analysis"]["unknown"] == ["desired_postcondition", "verification_condition"], f"unknown slots incorrect: {result}")
        report = result["knowledge_self_report"]
        require(report["known"][0]["value"] == "苹果", f"self-report lost known target: {report}")
        require([item["kind"] for item in report["unknown"]] == ["desired_postcondition", "verification_condition"], f"self-report unknown boundary incorrect: {report}")
        require(report["requested_human_input"] == result["prompt"] and not report["direct_execution_allowed"], f"self-report did not request minimum input safely: {report}")

    record("missing_result_asks_result", missing_result)

    def missing_verification() -> None:
        result = start("归整苹果，让苹果进入收纳区")
        require(result["dialogue"]["pending_slot"] == "verification_condition", f"verification gap missed: {result}")
        require(result["dialogue"]["slots"]["desired_postcondition"] == "苹果进入收纳区", f"goal was lost: {result}")

    record("missing_verification_asks_verification", missing_verification)

    def ordinary_observation_is_not_terminal() -> None:
        result = start("归整苹果，让苹果进入收纳区，看到操作台")
        require(result["dialogue"]["pending_slot"] == "verification_condition", f"context object obscured the action target: {result}")
        require(result["dialogue"]["slots"]["target_entity"]["entity_ref"] == "apple_a", f"wrong action target: {result}")
        require(result["dialogue"]["slots"]["verification_condition"] is None, f"ordinary observation became verification: {result}")

    record("ordinary_observation_not_verification", ordinary_observation_is_not_terminal)

    def conditional_object_is_not_action_target() -> None:
        result = start("如果杯子在操作台上，就归整苹果，让苹果进入收纳区，看到苹果在收纳区就算完成")
        contract = assert_safe_contract(result)
        require(contract["semantic_roles"]["target"]["entity_ref"] == "apple_a", f"condition object displaced action target: {contract}")
        require("human_described_precondition:杯子在操作台上" in contract["effect_contract"]["requires"], f"condition fact was lost: {contract}")

    record("condition_object_does_not_displace_target", conditional_object_is_not_action_target)

    def multiple_objects_are_ambiguous() -> None:
        result = start("归整苹果和杯子，让它们进入收纳区，看到它们都在收纳区就算完成")
        require(result["dialogue"]["pending_slot"] == "target_entity", f"multi-object target was guessed: {result}")
        require(result.get("compiled_contract") is None, f"ambiguous target compiled: {result}")

    record("multiple_objects_require_grounding", multiple_objects_are_ambiguous)

    def dialogue_compiles_with_minimum_turns() -> None:
        first = start("归置苹果")
        require(first["dialogue"]["pending_slot"] == "desired_postcondition", f"wrong initial slot: {first}")
        second = continue_concept_gap_dialogue(
            first["dialogue"],
            answer="让它和其他水果在一起",
            runtime_objects=runtime_objects,
            object_concepts=object_concepts,
            current_world_revision=1,
        )
        require(second["dialogue"]["pending_slot"] == "verification_condition", f"goal answer did not advance: {second}")
        third = continue_concept_gap_dialogue(
            second["dialogue"],
            answer="视觉确认所有水果位于同一区域",
            runtime_objects=runtime_objects,
            object_concepts=object_concepts,
            current_world_revision=1,
        )
        contract = assert_safe_contract(third)
        require(contract["effect_contract"]["human_readable_postcondition"] == "苹果和其他水果在一起", f"pronoun answer lost target: {contract}")
        report = third["knowledge_self_report"]
        require([item["kind"] for item in report["unknown"]] == ["operator_mechanism", "embodied_process"], f"compiled self-report overclaimed knowing how: {report}")
        require(report["next_safe_route"] == "offer_embodied_teaching", f"compiled self-report did not route to teaching: {report}")

    record("two_clarifications_compile_contract", dialogue_compiles_with_minimum_turns)

    def fixed_asset_rejected_before_teaching() -> None:
        session = start_session()
        result = execute_command(session["session_id"], "拿起饮水机")
        require(result["status"] == "factory_concept_recognized_execution_gap", f"fixed asset fell into unknown teaching: {result}")
        require(result["factory_concept"]["reason_code"] == "entity_not_compatible_with_semantic_role", f"fixed asset reason missing: {result}")
        require(not result["post_action"]["teaching_available"], f"impossible role offered teaching: {result}")

    record("fixed_asset_uses_functional_rejection", fixed_asset_rejected_before_teaching)

    def unknown_does_not_mutate_factory_library() -> None:
        before = json.dumps(load_object_concepts(), ensure_ascii=False, sort_keys=True)
        result = start("归整苹果，让苹果进入收纳区，看到苹果在收纳区就算完成")
        assert_safe_contract(result)
        after = json.dumps(load_object_concepts(), ensure_ascii=False, sort_keys=True)
        require(before == after, "temporary concept mutated factory object library")

    record("unknown_concept_does_not_mutate_factory_library", unknown_does_not_mutate_factory_library)

    latency_samples = [
        "归整苹果",
        "归拢苹果，让苹果位于收纳区",
        "码齐苹果，直到苹果进入收纳区为止",
        "如果水果散落，就整理苹果，让苹果位于收纳区，检测到苹果位于收纳区才算完成",
    ]
    for _ in range(50):
        for sample in latency_samples:
            start(sample)

    passed = sum(1 for item in results if item["passed"])
    report = {
        "benchmark": "small_vocabulary_large_generalization",
        "case_count": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "success_rate": round(passed / len(results), 4),
        "clarification_policy": {
            "maximum_minimum_causal_clarifications": 3,
            "known_unique_target_typical_clarifications": 2,
            "explicit_complete_sentence_clarifications": 0,
        },
        "latency_ms": {
            "sample_count": len(latencies_ms),
            "average": round(sum(latencies_ms) / len(latencies_ms), 4),
            "p50": percentile(latencies_ms, 0.50),
            "p95": percentile(latencies_ms, 0.95),
            "maximum": round(max(latencies_ms), 4),
        },
        "results": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    require(report["failed"] == 0, json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("[ok] small-vocabulary generalization pressure")


if __name__ == "__main__":
    main()
