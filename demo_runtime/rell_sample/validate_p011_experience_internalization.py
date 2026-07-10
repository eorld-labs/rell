from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from api_server import (
    CONCEPT_CANDIDATE_LIBRARY_FILE,
    CONCEPT_LIBRARY_FILE,
    EXPERIENCE_LIBRARY_FILE,
    execute_teaching_session_step,
    finish_teaching_session,
    load_concept_candidate_library,
    load_experience_library,
    run_process,
    start_teaching_session,
    teach_experience_from_dialogue,
)
from runtime_core import write_json


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT.parent / "output" / "rell_sample" / "p011_experience_internalization"

TEACHING_MESSAGE = "教你一个技能：接一杯水需要先拿杯子，再去水源处接水。接完以后杯子里有水。"
REUSE_UTTERANCE = "帮我接水"
SESSION_UTTERANCE = "到水源处接一杯水"


EVIDENCE_INDEX = [
    {
        "file": "01_experience_triplet_structure.json",
        "technical_feature": "经验记录以情境、动作、后果三元结构沉淀，并保留因果签名与经验不变量契约",
        "claim_step": "获取基于真实交互积累的经验模型记录",
        "key_fields": [
            "dialogue_experience.context",
            "dialogue_experience.action",
            "dialogue_experience.outcome",
            "dialogue_experience.causal_signature",
            "dialogue_experience.invariant_contract",
        ],
        "code_sources": [
            "api_server.py::teach_experience",
            "api_server.py::teach_experience_from_dialogue",
            "validate_p011_experience_internalization.py::main",
        ],
    },
    {
        "file": "02_dialogue_teaching_creation.json",
        "technical_feature": "对话教学可将真实教学输入转化为结构化经验记录并写入经验库",
        "claim_step": "将本次情境、目标动作和实际后果作为新记录反馈入经验模型",
        "key_fields": [
            "dialogue_teaching.decision",
            "dialogue_teaching.experience.context.human_intent_ref",
            "dialogue_teaching.experience.action.parameters.source",
            "dialogue_teaching.experience.outcome.outcome_type",
        ],
        "code_sources": [
            "api_server.py::teach_experience_from_dialogue",
            "api_server.py::load_experience_library",
        ],
    },
    {
        "file": "03_stepwise_teaching_feedback.json",
        "technical_feature": "边教边动过程中，系统依据当前任务期状态给出缺失前提反馈，并在成功后固化经验",
        "claim_step": "执行目标动作并将真实交互结果反馈入经验模型",
        "key_fields": [
            "blocked_step.step_feedback",
            "executed_steps.step_feedback",
            "finished_session.experience_result.experience.process_chain",
            "finished_session.release_result.release_status",
        ],
        "code_sources": [
            "api_server.py::start_teaching_session",
            "api_server.py::execute_teaching_session_step",
            "api_server.py::finish_teaching_session",
        ],
    },
    {
        "file": "04_experience_reuse_reasoning.json",
        "technical_feature": "后续任务可优先复用经验库中的历史经验，并基于经验记录完成后果预测与过程链复用",
        "claim_step": "基于经验模型对候选动作在当前情境下的预期后果进行预测",
        "key_fields": [
            "reused_run.intent_translation.causal_plan.reasoning",
            "reused_run.intent_translation.candidate_process_chain",
            "reused_run.audit_summary.outcome",
        ],
        "code_sources": [
            "api_server.py::build_process_registry",
            "api_server.py::solve_causal_process_chain",
            "api_server.py::run_process",
        ],
    },
    {
        "file": "05_non_transferable_field_stripping.json",
        "technical_feature": "经验库仅保留可迁移经验约束，不把绝对坐标、关节角或固定时长作为必要复用内容",
        "claim_step": "经验模型中的记录区别可迁移经验约束与不可迁移执行细节",
        "key_fields": [
            "dialogue_experience.invariant_contract.storage_policy",
            "dialogue_experience.invariant_contract.forbidden_storage",
            "dialogue_experience.invariant_contract.invariant_dimensions",
        ],
        "code_sources": [
            "api_server.py::build_invariant_contract",
            "validate_p011_experience_internalization.py::main",
        ],
    },
    {
        "file": "06_experience_library_snapshot.json",
        "technical_feature": "经验库保留多条可复用经验记录，并伴随概念候选等后续内化线索",
        "claim_step": "更新后的经验模型可供后续任务检索使用",
        "key_fields": [
            "experience_library.experiences",
            "concept_candidate_library.concept_candidates",
            "latest_dialogue_experience.experience_id",
            "latest_stepwise_experience.experience_id",
        ],
        "code_sources": [
            "api_server.py::save_experience_library",
            "api_server.py::load_experience_library",
            "api_server.py::upsert_concept_promotion_candidates",
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
        dialogue_teaching = teach_experience_from_dialogue("", TEACHING_MESSAGE)
        dialogue_experience = dialogue_teaching["experience"]

        triplet_structure = evidence(
            "经验记录以情境、动作、后果三元结构沉淀，并保留因果签名与经验不变量契约",
            "获取基于真实交互积累的经验模型记录",
            {
                "dialogue_experience": dialogue_experience,
            },
        )
        write_json(OUTPUT / "01_experience_triplet_structure.json", triplet_structure)

        dialogue_creation = evidence(
            "对话教学可将真实教学输入转化为结构化经验记录并写入经验库",
            "将本次情境、目标动作和实际后果作为新记录反馈入经验模型",
            {
                "dialogue_teaching": dialogue_teaching,
            },
        )
        write_json(OUTPUT / "02_dialogue_teaching_creation.json", dialogue_creation)

        blocked_session = start_teaching_session(SESSION_UTTERANCE)
        blocked_step = execute_teaching_session_step(blocked_session["session_id"], "拿起杯子")

        executed_session = start_teaching_session(SESSION_UTTERANCE)
        executed_steps = []
        for step_text in ["走向操作台", "拿起杯子", "到水源处", "接一杯水"]:
            executed_steps.append(execute_teaching_session_step(executed_session["session_id"], step_text))
        finished_session = finish_teaching_session(executed_session["session_id"])
        latest_stepwise_experience = finished_session.get("experience_result", {}).get("experience")

        stepwise_feedback = evidence(
            "边教边动过程中，系统依据当前任务期状态给出缺失前提反馈，并在成功后固化经验",
            "执行目标动作并将真实交互结果反馈入经验模型",
            {
                "blocked_step": blocked_step,
                "executed_steps": executed_steps,
                "finished_session": finished_session,
            },
        )
        write_json(OUTPUT / "03_stepwise_teaching_feedback.json", stepwise_feedback)

        reused_run = run_process("auto", REUSE_UTTERANCE)
        experience_reuse = evidence(
            "后续任务可优先复用经验库中的历史经验，并基于经验记录完成后果预测与过程链复用",
            "基于经验模型对候选动作在当前情境下的预期后果进行预测",
            {
                "utterance": REUSE_UTTERANCE,
                "reused_run": {
                    "intent_translation": reused_run.get("intent_translation"),
                    "audit_summary": reused_run.get("audit_summary"),
                    "runtime_world_state": reused_run.get("runtime_world_state"),
                },
            },
        )
        write_json(OUTPUT / "04_experience_reuse_reasoning.json", experience_reuse)

        non_transferable = evidence(
            "经验库仅保留可迁移经验约束，不把绝对坐标、关节角或固定时长作为必要复用内容",
            "经验模型中的记录区别可迁移经验约束与不可迁移执行细节",
            {
                "dialogue_experience": {
                    "experience_id": dialogue_experience.get("experience_id"),
                    "invariant_contract": dialogue_experience.get("invariant_contract"),
                },
            },
        )
        write_json(OUTPUT / "05_non_transferable_field_stripping.json", non_transferable)

        experience_library = load_experience_library()
        concept_candidate_library = load_concept_candidate_library()
        library_snapshot = evidence(
            "经验库保留多条可复用经验记录，并伴随概念候选等后续内化线索",
            "更新后的经验模型可供后续任务检索使用",
            {
                "experience_library": experience_library,
                "concept_candidate_library": concept_candidate_library,
                "latest_dialogue_experience": dialogue_experience,
                "latest_stepwise_experience": latest_stepwise_experience,
            },
        )
        write_json(OUTPUT / "06_experience_library_snapshot.json", library_snapshot)

        reasoning_sources = [
            item.get("source")
            for item in reused_run.get("intent_translation", {}).get("causal_plan", {}).get("reasoning", [])
        ]
        blocked_feedback = blocked_step.get("step_feedback", [{}])[0]
        first_executed_feedback = executed_steps[0].get("step_feedback", [{}])[0]
        experiences = experience_library.get("experiences", [])
        forbidden_storage = dialogue_experience.get("invariant_contract", {}).get("forbidden_storage", [])

        assert_true(dialogue_teaching.get("decision") == "experience_created", "dialogue teaching must create an experience")
        assert_true(dialogue_experience.get("context", {}).get("human_intent_ref") == "dialogue_teaching", "dialogue teaching source must be retained")
        assert_true(dialogue_experience.get("action", {}).get("parameters", {}).get("source") == "dialogue_teaching", "dialogue teaching action source must be retained")
        assert_true({"context", "action", "outcome"}.issubset(dialogue_experience.keys()), "experience must contain context, action, outcome")
        assert_true(dialogue_experience.get("outcome", {}).get("outcome_type") == "candidate_created", "experience outcome type must be structured")
        assert_true(bool(dialogue_experience.get("outcome", {}).get("state_delta")), "experience outcome must contain state delta")
        assert_true(dialogue_experience.get("causal_signature", {}).get("produces_fact") == "cup_contains_water", "dialogue teaching must form target causal fact")

        assert_true(blocked_feedback.get("status") == "needs_more_teaching", "stepwise teaching must expose missing prerequisites")
        assert_true("executor_at_counter" in blocked_feedback.get("missing_before_step", []), "stepwise missing prerequisite must be explicit")
        assert_true(first_executed_feedback.get("status") == "executed", "guided teaching step must execute after correct prerequisite")
        assert_true(finished_session.get("status") == "experience_saved", "finished teaching session must save experience")
        assert_true(finished_session.get("release_result", {}).get("release_status") == "released", "teaching session must release runtime snapshot")
        assert_true(latest_stepwise_experience.get("context", {}).get("human_intent_ref") == "stepwise_teaching_session", "stepwise teaching source must be retained")

        experience_reasoning = next(
            (
                item
                for item in reused_run.get("intent_translation", {}).get("causal_plan", {}).get("reasoning", [])
                if item.get("source") == "experience_library"
            ),
            None,
        )
        assert_true("experience_library" in reasoning_sources, "experience reuse must reference experience library")
        assert_true(reused_run.get("audit_summary", {}).get("outcome") == "completed", "reused task must execute successfully")
        assert_true(
            experience_reasoning is not None
            and experience_reasoning.get("expanded_process_chain") == ["pick_up_cup", "move_to_water_source", "fill_cup_at_water_source"],
            "experience reuse must expand the taught process chain from the experience library",
        )

        for field_name in [
            "absolute_coordinates",
            "robot_specific_joint_angles",
            "fixed_execution_duration",
            "single_body_trajectory_without_binding_slots",
        ]:
            assert_true(field_name in forbidden_storage, f"invariant contract must forbid {field_name}")

        assert_true(len(experiences) >= 2, "experience library must contain dialogue and stepwise experiences")
        assert_true(any(item.get("experience_id") == dialogue_experience.get("experience_id") for item in experiences), "dialogue experience must persist in library")
        assert_true(any(item.get("experience_id") == latest_stepwise_experience.get("experience_id") for item in experiences), "stepwise experience must persist in library")
        assert_true(bool(concept_candidate_library.get("concept_candidates")), "experience internalization must also produce concept candidates")

        summary = {
            "schema_version": "1.0.0",
            "technical_feature": "P011 物理经验内化最小工程证据闭环",
            "utterances": {
                "dialogue_teaching": TEACHING_MESSAGE,
                "stepwise_teaching": SESSION_UTTERANCE,
                "experience_reuse": REUSE_UTTERANCE,
            },
            "output_dir": str(OUTPUT),
            "evidence_files": [
                "evidence_index.json",
                "01_experience_triplet_structure.json",
                "02_dialogue_teaching_creation.json",
                "03_stepwise_teaching_feedback.json",
                "04_experience_reuse_reasoning.json",
                "05_non_transferable_field_stripping.json",
                "06_experience_library_snapshot.json",
            ],
        }
        evidence_index = {
            "schema_version": "1.0.0",
            "title": "P011 物理经验内化工程证据索引",
            "summary": "本索引用于将 P011 从经验三元结构形成、对话教学入库、边教边动反馈、经验复用推理到经验库持续沉淀的最小工程闭环，与输出文件、关键字段和代码来源建立一一对应关系。",
            "validation_command": "python demo_runtime\\rell_sample\\validate_p011_experience_internalization.py",
            "output_dir": str(OUTPUT),
            "evidence_items": EVIDENCE_INDEX,
        }
        write_json(OUTPUT / "evidence_index.json", evidence_index)
        write_json(OUTPUT / "00_summary.json", summary)
        print("P011 experience internalization validation passed.")
        print(f"Output: {OUTPUT}")
    finally:
        restore_text(EXPERIENCE_LIBRARY_FILE, original_experience_library)
        restore_text(CONCEPT_LIBRARY_FILE, original_concept_library)
        restore_text(CONCEPT_CANDIDATE_LIBRARY_FILE, original_candidate_library)


if __name__ == "__main__":
    main()
