from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from api_server import (
    CONCEPT_CANDIDATE_LIBRARY_FILE,
    CONCEPT_LIBRARY_FILE,
    EXPERIENCE_LIBRARY_FILE,
    build_llm_prompt_contract,
    build_semantic_request_frame,
    execute_teaching_session_step,
    finish_teaching_session,
    get_cognitive_model,
    handle_agent_query,
    load_concept_candidate_library,
    load_concept_library,
    load_experience_library,
    resolve_concepts_for_intent,
    run_process,
    start_teaching_session,
    teach_experience_from_dialogue,
    translate_intent,
)
from runtime_core import write_json


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT.parent / "output" / "rell_sample" / "p013_task_semantics"

SHORT_UTTERANCE = "到水源处接一杯水"
LONG_UTTERANCE = "走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水"
ROUTED_UTTERANCE = "走到门旁边，再走到服务位，再去操作台拿杯子，去水源处倒杯水"
CAUSAL_TEACHING_MESSAGE = "教你一个技能：接一杯水需要先拿杯子，再去水源处接水。接完以后杯子里有水。"


EVIDENCE_INDEX = [
    {
        "file": "01_semantic_request_entry.json",
        "technical_feature": "统一语义入口将自然语言请求结构化为语义请求和意图帧",
        "claim_step": "S1 获取与待执行任务相关联的人类意图信息以及目标空间的情境信息",
        "key_fields": [
            "task_execution.semantic_request.request_type",
            "task_execution.semantic_request.intent_frame.goal_fact",
            "state_query.semantic_request.request_type",
            "teaching.semantic_request.teaching_plan",
        ],
        "code_sources": [
            "api_server.py::build_semantic_request_frame",
            "api_server.py::build_intent_frame",
            "validate_p013_task_semantics.py::main",
        ],
    },
    {
        "file": "02_goal_fact_and_plan.json",
        "technical_feature": "任务语义翻译层将人类意图映射为目标因果事实和可执行过程链",
        "claim_step": "S2 基于人类意图信息和目标空间情境信息形成包含多个可执行步骤的任务计划",
        "key_fields": [
            "short_intent.goal_fact",
            "short_intent.candidate_process_chain",
            "long_run.intent_translation.causal_plan.process_chain",
            "long_run.intent_translation.reason",
        ],
        "code_sources": [
            "api_server.py::translate_intent",
            "api_server.py::infer_goal_fact",
            "api_server.py::solve_causal_process_chain",
            "api_server.py::run_process",
        ],
    },
    {
        "file": "03_explicit_route_preservation.json",
        "technical_feature": "显式教学路线可在因果成立时被保留，并与空间语义约束和概念匹配共同进入计划形成",
        "claim_step": "S2 基于人类意图信息和目标空间情境信息形成包含多个可执行步骤的任务计划",
        "key_fields": [
            "routed_run.intent_translation.candidate_process_chain",
            "routed_run.intent_translation.intent_frame.spatial_constraints",
            "routed_run.intent_translation.intent_frame.concept_matches",
            "routed_run.runtime_world_state.established_facts",
        ],
        "code_sources": [
            "api_server.py::build_explicit_causal_plan",
            "api_server.py::extract_spatial_constraints",
            "api_server.py::build_concept_matches",
            "api_server.py::run_process",
        ],
    },
    {
        "file": "04_teaching_feedback_and_experience.json",
        "technical_feature": "对话教学与边教边动会话可形成任务经验记录，并在后续任务计划形成中被复用",
        "claim_step": "S3 执行任务计划；S4 将人类意图、任务计划、执行结果和人类反馈作为任务经验记录存储",
        "key_fields": [
            "dialogue_teaching.experience.causal_signature",
            "reused_run.intent_translation.causal_plan.reasoning",
            "blocked_stepwise.step_feedback",
            "finished_stepwise.experience_result.experience.process_chain",
        ],
        "code_sources": [
            "api_server.py::teach_experience_from_dialogue",
            "api_server.py::start_teaching_session",
            "api_server.py::execute_teaching_session_step",
            "api_server.py::finish_teaching_session",
            "api_server.py::run_process",
        ],
    },
    {
        "file": "05_unified_entry_and_llm_boundary.json",
        "technical_feature": "统一任务入口、概念解析和提示词契约共同约束语言模型只参与语义理解而不直接下发执行",
        "claim_step": "S2 基于人类意图信息和目标空间情境信息形成任务计划",
        "key_fields": [
            "agent_preview.semantic_request.request_type",
            "agent_preview.route_result.intent_translation.goal_fact",
            "concept_resolution.resolved_concepts",
            "llm_prompt_contract.handoff_contract.direct_execution_allowed",
        ],
        "code_sources": [
            "api_server.py::handle_agent_query",
            "api_server.py::resolve_concepts_for_intent",
            "api_server.py::build_llm_prompt_contract",
        ],
    },
    {
        "file": "06_task_experience_library.json",
        "technical_feature": "任务经验库保留人类意图、计划、执行来源和反馈来源的结构化记录",
        "claim_step": "S4 将人类意图信息、任务计划、执行结果和人类反馈作为任务经验记录存储",
        "key_fields": [
            "experience_library.experiences",
            "latest_dialogue_experience.context.human_intent_ref",
            "latest_stepwise_experience.context.human_intent_ref",
            "concept_candidate_library.concept_candidates",
        ],
        "code_sources": [
            "api_server.py::teach_experience_from_dialogue",
            "api_server.py::finish_teaching_session",
            "api_server.py::load_experience_library",
            "api_server.py::load_concept_candidate_library",
        ],
    },
]


def evidence(feature: str, claim_step: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "technical_feature": feature,
        "claim_step": claim_step,
        **payload,
    }


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def backup_text(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.exists() else None


def restore_text(path: Path, content: str | None) -> None:
    if content is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(content, encoding="utf-8")


def main() -> None:
    original_experience_library = backup_text(EXPERIENCE_LIBRARY_FILE)
    original_concept_library = backup_text(CONCEPT_LIBRARY_FILE)
    original_candidate_library = backup_text(CONCEPT_CANDIDATE_LIBRARY_FILE)

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    EXPERIENCE_LIBRARY_FILE.write_text(
        json.dumps({"schema_version": "1.0.0", "experiences": []}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    CONCEPT_CANDIDATE_LIBRARY_FILE.unlink(missing_ok=True)

    try:
        cognitive_model = get_cognitive_model()

        semantic_task = build_semantic_request_frame(SHORT_UTTERANCE, cognitive_model)
        semantic_state = build_semantic_request_frame("当前杯子有没有水", cognitive_model, task_id="p013_probe_task")
        semantic_teaching = build_semantic_request_frame("教你：走向操作台，然后拿起杯子", cognitive_model)
        semantic_clarification = build_semantic_request_frame("为什么不能执行", cognitive_model, task_id="p013_probe_task")

        semantic_request_entry = evidence(
            "统一语义入口将自然语言请求结构化为语义请求和意图帧",
            "S1 获取与待执行任务相关联的人类意图信息以及目标空间的情境信息",
            {
                "task_execution": {"utterance": SHORT_UTTERANCE, "semantic_request": semantic_task},
                "state_query": {"utterance": "当前杯子有没有水", "semantic_request": semantic_state},
                "teaching": {"utterance": "教你：走向操作台，然后拿起杯子", "semantic_request": semantic_teaching},
                "clarification": {"utterance": "为什么不能执行", "semantic_request": semantic_clarification},
            },
        )
        write_json(OUTPUT / "01_semantic_request_entry.json", semantic_request_entry)

        short_intent = translate_intent(SHORT_UTTERANCE)
        long_run = run_process("auto", LONG_UTTERANCE)

        goal_fact_and_plan = evidence(
            "任务语义翻译层将人类意图映射为目标因果事实和可执行过程链",
            "S2 基于人类意图信息和目标空间情境信息形成包含多个可执行步骤的任务计划",
            {
                "short_intent": short_intent,
                "long_run": {
                    "scenario": long_run.get("scenario"),
                    "intent_translation": long_run.get("intent_translation"),
                    "audit_summary": long_run.get("audit_summary"),
                },
            },
        )
        write_json(OUTPUT / "02_goal_fact_and_plan.json", goal_fact_and_plan)

        routed_run = run_process("auto", ROUTED_UTTERANCE)
        explicit_route_preservation = evidence(
            "显式教学路线可在因果成立时被保留，并与空间语义约束和概念匹配共同进入计划形成",
            "S2 基于人类意图信息和目标空间情境信息形成包含多个可执行步骤的任务计划",
            {
                "utterance": ROUTED_UTTERANCE,
                "routed_run": {
                    "intent_translation": routed_run.get("intent_translation"),
                    "runtime_world_state": routed_run.get("runtime_world_state"),
                    "audit_summary": routed_run.get("audit_summary"),
                },
            },
        )
        write_json(OUTPUT / "03_explicit_route_preservation.json", explicit_route_preservation)

        dialogue_teaching = teach_experience_from_dialogue("", CAUSAL_TEACHING_MESSAGE)
        reused_run = run_process("auto", "帮我接水")

        blocked_stepwise = start_teaching_session(SHORT_UTTERANCE)
        blocked_feedback = execute_teaching_session_step(blocked_stepwise["session_id"], "拿起杯子")

        finished_stepwise_start = start_teaching_session(SHORT_UTTERANCE)
        for step_text in ["走向操作台", "拿起杯子", "到水源处", "接一杯水"]:
            execute_teaching_session_step(finished_stepwise_start["session_id"], step_text)
        finished_stepwise = finish_teaching_session(finished_stepwise_start["session_id"])

        teaching_feedback_and_experience = evidence(
            "对话教学与边教边动会话可形成任务经验记录，并在后续任务计划形成中被复用",
            "S3 执行任务计划；S4 将人类意图、任务计划、执行结果和人类反馈作为任务经验记录存储",
            {
                "dialogue_teaching": dialogue_teaching,
                "reused_run": {
                    "intent_translation": reused_run.get("intent_translation"),
                    "audit_summary": reused_run.get("audit_summary"),
                },
                "blocked_stepwise": blocked_feedback,
                "finished_stepwise": finished_stepwise,
            },
        )
        write_json(OUTPUT / "04_teaching_feedback_and_experience.json", teaching_feedback_and_experience)

        agent_preview = handle_agent_query(SHORT_UTTERANCE)
        concept_resolution = resolve_concepts_for_intent(ROUTED_UTTERANCE)
        llm_prompt_contract = build_llm_prompt_contract(SHORT_UTTERANCE)

        unified_entry_and_llm_boundary = evidence(
            "统一任务入口、概念解析和提示词契约共同约束语言模型只参与语义理解而不直接下发执行",
            "S2 基于人类意图信息和目标空间情境信息形成任务计划",
            {
                "agent_preview": agent_preview,
                "concept_resolution": concept_resolution,
                "llm_prompt_contract": llm_prompt_contract,
            },
        )
        write_json(OUTPUT / "05_unified_entry_and_llm_boundary.json", unified_entry_and_llm_boundary)

        experience_library = load_experience_library()
        concept_candidate_library = load_concept_candidate_library()
        task_experience_library = evidence(
            "任务经验库保留人类意图、计划、执行来源和反馈来源的结构化记录",
            "S4 将人类意图信息、任务计划、执行结果和人类反馈作为任务经验记录存储",
            {
                "experience_library": experience_library,
                "latest_dialogue_experience": dialogue_teaching.get("experience"),
                "latest_stepwise_experience": finished_stepwise.get("experience_result", {}).get("experience"),
                "concept_candidate_library": concept_candidate_library,
            },
        )
        write_json(OUTPUT / "06_task_experience_library.json", task_experience_library)

        expected_short_chain = ["move_to_counter", "pick_up_cup", "move_to_water_source", "fill_cup_at_water_source"]
        expected_long_chain = [
            "move_to_counter",
            "pick_up_cup",
            "move_to_water_source",
            "fill_cup_at_water_source",
            "move_to_counter",
            "pour_water",
        ]
        expected_routed_chain = [
            "move_to_doorway",
            "move_to_service_position",
            "move_to_counter",
            "pick_up_cup",
            "move_to_water_source",
            "fill_cup_at_water_source",
        ]

        assert_true(semantic_task.get("request_type") == "task_execution", "task utterance must route to task_execution")
        assert_true(semantic_state.get("request_type") == "state_query", "state question must route to state_query")
        assert_true(semantic_teaching.get("request_type") == "teaching", "teaching utterance must route to teaching")
        assert_true(semantic_clarification.get("request_type") == "clarification", "clarification utterance must route to clarification")

        assert_true(short_intent.get("goal_fact") == "cup_contains_water", "short utterance must resolve to cup_contains_water")
        assert_true(short_intent.get("candidate_process_chain") == expected_short_chain, "short utterance must infer cup preconditions")
        assert_true(long_run.get("audit_summary", {}).get("outcome") == "completed", "long utterance must execute successfully")
        assert_true(long_run.get("intent_translation", {}).get("candidate_process_chain") == expected_long_chain, "long utterance must produce full causal chain")

        routed_intent = routed_run.get("intent_translation", {})
        routed_frame = routed_intent.get("intent_frame", {})
        routed_regions = [item.get("region_ref") for item in routed_frame.get("spatial_constraints", [])]
        routed_concepts = [item.get("concept_id") for item in routed_frame.get("concept_matches", [])]
        assert_true(routed_intent.get("candidate_process_chain") == expected_routed_chain, "explicit route must be preserved")
        for expected_region in ["region_doorway", "region_service_position", "region_counter_operation", "region_water_source"]:
            assert_true(expected_region in routed_regions, f"route must preserve spatial region {expected_region}")
        for expected_concept in ["concept_spatial_region_navigation", "concept_fillable_container", "concept_water_resource_zone"]:
            assert_true(expected_concept in routed_concepts, f"route must expose concept {expected_concept}")
        assert_true("cup_contains_water" in routed_run.get("runtime_world_state", {}).get("established_facts", []), "routed execution must establish target fact")

        signature = dialogue_teaching.get("experience", {}).get("causal_signature", {})
        reasoning_sources = [item.get("source") for item in reused_run.get("intent_translation", {}).get("causal_plan", {}).get("reasoning", [])]
        assert_true(dialogue_teaching.get("decision") == "experience_created", "dialogue teaching must create experience")
        assert_true(signature.get("produces_fact") == "cup_contains_water", "dialogue teaching must create causal signature for cup_contains_water")
        assert_true("experience_library" in reasoning_sources, "reused run must reference experience library reasoning")
        first_blocked = blocked_feedback.get("step_feedback", [{}])[0]
        assert_true(first_blocked.get("status") == "needs_more_teaching", "blocked stepwise teaching must expose missing prerequisites")
        assert_true("executor_at_counter" in first_blocked.get("missing_before_step", []), "blocked stepwise teaching must expose executor_at_counter prerequisite")
        assert_true(finished_stepwise.get("status") == "experience_saved", "stepwise teaching finish must save experience")
        assert_true(finished_stepwise.get("release_result", {}).get("release_status") == "released", "stepwise teaching finish must release snapshot")

        assert_true(agent_preview.get("semantic_request", {}).get("request_type") == "task_execution", "agent preview must use unified task entry")
        assert_true(agent_preview.get("route_result", {}).get("intent_translation", {}).get("goal_fact") == "cup_contains_water", "agent preview must preserve goal fact")
        resolved_concepts = [item.get("concept_id") for item in concept_resolution.get("resolved_concepts", [])]
        for expected_concept in ["concept_spatial_region_navigation", "concept_interactive_object_acquisition", "concept_fillable_container", "concept_water_resource_zone"]:
            assert_true(expected_concept in resolved_concepts, f"concept resolution must include {expected_concept}")
        assert_true(not concept_resolution.get("concept_resolution_policy", {}).get("direct_execution_allowed"), "concept layer must not execute directly")
        assert_true(llm_prompt_contract.get("handoff_contract", {}).get("validator_endpoint") == "/llm/candidate/validate", "LLM handoff must go through validator")
        assert_true(not llm_prompt_contract.get("handoff_contract", {}).get("direct_execution_allowed"), "LLM contract must forbid direct execution")

        experiences = experience_library.get("experiences", [])
        assert_true(len(experiences) >= 2, "experience library must retain dialogue and stepwise task experiences")
        assert_true(dialogue_teaching.get("experience", {}).get("context", {}).get("human_intent_ref") == "dialogue_teaching", "dialogue teaching source must be retained")
        assert_true(finished_stepwise.get("experience_result", {}).get("experience", {}).get("context", {}).get("human_intent_ref") == "stepwise_teaching_session", "stepwise teaching source must be retained")
        assert_true(bool(concept_candidate_library.get("concept_candidates")), "task experience creation must also produce concept candidates")

        summary = {
            "schema_version": "1.0.0",
            "technical_feature": "P013 任务语义翻译最小工程证据闭环汇总",
            "utterances": {
                "short": SHORT_UTTERANCE,
                "long": LONG_UTTERANCE,
                "routed": ROUTED_UTTERANCE,
            },
            "output_dir": str(OUTPUT),
            "evidence_files": [
                "evidence_index.json",
                "01_semantic_request_entry.json",
                "02_goal_fact_and_plan.json",
                "03_explicit_route_preservation.json",
                "04_teaching_feedback_and_experience.json",
                "05_unified_entry_and_llm_boundary.json",
                "06_task_experience_library.json",
            ],
        }
        evidence_index = {
            "schema_version": "1.0.0",
            "title": "P013 任务语义翻译工程证据索引",
            "summary": "本索引用于将 P013 从统一语义入口、目标事实翻译、因果计划形成、显式路线保留、教学反馈闭环到任务经验记录存储的最小工程证据，与输出文件、关键字段和代码来源建立一一对应关系。",
            "validation_command": "python demo_runtime\\rell_sample\\validate_p013_task_semantics.py",
            "output_dir": str(OUTPUT),
            "evidence_items": EVIDENCE_INDEX,
        }
        write_json(OUTPUT / "evidence_index.json", evidence_index)
        write_json(OUTPUT / "00_summary.json", summary)
        print("P013 task semantics validation passed.")
        print(f"Output: {OUTPUT}")
    finally:
        restore_text(EXPERIENCE_LIBRARY_FILE, original_experience_library)
        restore_text(CONCEPT_LIBRARY_FILE, original_concept_library)
        restore_text(CONCEPT_CANDIDATE_LIBRARY_FILE, original_candidate_library)


if __name__ == "__main__":
    main()
