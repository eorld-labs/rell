from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from api_server import (
    CONCEPT_LIBRARY_FILE,
    EXPERIENCE_LIBRARY_FILE,
    PREFERENCE_LIBRARY_FILE,
    attach_preference_to_runtime_task,
    load_concept_library,
    load_experience_library,
    load_preference_library,
    migrate_experience,
    query_runtime_world_state,
    record_preference,
)
from runtime_core import write_json


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT.parent / "output" / "rell_sample" / "p015_preference_alignment"
UTTERANCE = "到水源处接一杯水"
PREFERENCE_QUESTION = "当前偏好约束是什么"


EVIDENCE_INDEX = [
    {
        "file": "01_preference_library_baseline.json",
        "technical_feature": "人类偏好以独立偏好记录库形式持久化，而不是直接写入经验模型参数",
        "claim_step": "将当前情境、动作和人类偏好指示作为偏好记录存储",
        "key_fields": [
            "preference_library.preference_records",
            "preference_library.preference_records[].preference_id",
            "preference_library.preference_records[].enforcement_policy",
        ],
        "code_sources": [
            "api_server.py::load_preference_library",
            "api_server.py::save_preference_library",
        ],
    },
    {
        "file": "02_runtime_snapshot_preference_loading.json",
        "technical_feature": "当前任务期运行时世界状态快照会加载与任务上下文匹配的人类偏好记录",
        "claim_step": "在后续动作确定时基于当前情境调取匹配的人类偏好指示",
        "key_fields": [
            "migration.runtime_world_state_snapshot.active_preferences",
            "migration.runtime_world_state_snapshot.preference_context",
            "migration.execution_feasibility.preference_advisories",
        ],
        "code_sources": [
            "api_server.py::resolve_preferences_for_intent",
            "api_server.py::migrate_experience",
        ],
    },
    {
        "file": "03_runtime_preference_query.json",
        "technical_feature": "状态问答链仅从当前任务期快照读取偏好约束，而不回退到长期经验推理",
        "claim_step": "基于当前情境与当前任务状态读取适用的人类偏好指示",
        "key_fields": [
            "preference_query.answer",
            "preference_query.evidence.active_preferences",
            "preference_query.source",
        ],
        "code_sources": [
            "api_server.py::parse_runtime_query",
            "api_server.py::query_runtime_world_state",
        ],
    },
    {
        "file": "04_preference_record_and_attachment.json",
        "technical_feature": "新增偏好记录后，可即时附着到当前任务期快照供后续判断读取",
        "claim_step": "获取人类反馈并形成新的偏好记录",
        "key_fields": [
            "recorded_preference.preference_record",
            "attachment.active_preferences",
            "runtime_query_after_attachment.evidence.active_preferences",
        ],
        "code_sources": [
            "api_server.py::record_preference",
            "api_server.py::attach_preference_to_runtime_task",
            "api_server.py::query_runtime_world_state",
        ],
    },
    {
        "file": "05_preference_constrained_feasibility.json",
        "technical_feature": "偏好约束先限制约束可行集合，再将违反偏好的步骤标记为部分不可执行",
        "claim_step": "基于约束可行性判断对候选动作进行可行性限定",
        "key_fields": [
            "constrained_migration.execution_feasibility.result",
            "constrained_migration.execution_feasibility.infeasible_reasons",
            "constrained_migration.experience_gap_record.preference_refs",
        ],
        "code_sources": [
            "api_server.py::evaluate_preference_constraints",
            "api_server.py::build_execution_feasibility",
            "api_server.py::build_experience_gap_record",
        ],
    },
    {
        "file": "06_preference_non_rewrite_boundary.json",
        "technical_feature": "偏好层作为独立运行时约束读入，不直接改写经验层或概念层持久化内容",
        "claim_step": "偏好记录独立于经验层和概念层存储并参与后续动作确定",
        "key_fields": [
            "before_hashes.experience_library_sha1",
            "after_hashes.experience_library_sha1",
            "before_hashes.concept_library_sha1",
            "after_hashes.concept_library_sha1",
        ],
        "code_sources": [
            "api_server.py::record_preference",
            "api_server.py::migrate_experience",
            "api_server.py::load_experience_library",
            "api_server.py::load_concept_library",
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


def sha1_of_payload(payload: Any) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(data).hexdigest()


def main() -> None:
    original_preference_library = backup_text(PREFERENCE_LIBRARY_FILE)
    original_experience_library = backup_text(EXPERIENCE_LIBRARY_FILE)
    original_concept_library = backup_text(CONCEPT_LIBRARY_FILE)

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    try:
        baseline_preference_library = load_preference_library()
        baseline_experience_library = load_experience_library()
        baseline_concept_library = load_concept_library()

        baseline = evidence(
            "人类偏好以独立偏好记录库形式持久化，而不是直接写入经验模型参数",
            "将当前情境、动作和人类偏好指示作为偏好记录存储",
            {
                "preference_library": baseline_preference_library,
            },
        )
        write_json(OUTPUT / "01_preference_library_baseline.json", baseline)

        migration = migrate_experience(UTTERANCE)
        runtime_snapshot = evidence(
            "当前任务期运行时世界状态快照会加载与任务上下文匹配的人类偏好记录",
            "在后续动作确定时基于当前情境调取匹配的人类偏好指示",
            {
                "migration": {
                    "migration_task_id": migration.get("migration_task_id"),
                    "runtime_world_state_snapshot": migration.get("runtime_world_state_snapshot"),
                    "execution_feasibility": migration.get("execution_feasibility"),
                },
            },
        )
        write_json(OUTPUT / "02_runtime_snapshot_preference_loading.json", runtime_snapshot)

        preference_query = query_runtime_world_state(migration["migration_task_id"], PREFERENCE_QUESTION)
        query_evidence = evidence(
            "状态问答链仅从当前任务期快照读取偏好约束，而不回退到长期经验推理",
            "基于当前情境与当前任务状态读取适用的人类偏好指示",
            {
                "preference_query": preference_query,
            },
        )
        write_json(OUTPUT / "03_runtime_preference_query.json", query_evidence)

        recorded_preference = record_preference(
            context_ref="home_a_kitchen",
            preference_signal="forbid",
            human_feedback="不要自动拿起杯子，先请求我确认。",
            applies_to=["step:pick_up_cup", "object:object_cup_white_mug"],
            enforcement_policy="blocking",
        )
        attachment = attach_preference_to_runtime_task(migration["migration_task_id"], recorded_preference["preference_record"])
        runtime_query_after_attachment = query_runtime_world_state(migration["migration_task_id"], PREFERENCE_QUESTION)
        record_and_attachment = evidence(
            "新增偏好记录后，可即时附着到当前任务期快照供后续判断读取",
            "获取人类反馈并形成新的偏好记录",
            {
                "recorded_preference": recorded_preference,
                "attachment": attachment,
                "runtime_query_after_attachment": runtime_query_after_attachment,
            },
        )
        write_json(OUTPUT / "04_preference_record_and_attachment.json", record_and_attachment)

        constrained_migration = migrate_experience(UTTERANCE)
        constrained = evidence(
            "偏好约束先限制约束可行集合，再将违反偏好的步骤标记为部分不可执行",
            "基于约束可行性判断对候选动作进行可行性限定",
            {
                "constrained_migration": {
                    "migration_task_id": constrained_migration.get("migration_task_id"),
                    "execution_feasibility": constrained_migration.get("execution_feasibility"),
                    "experience_gap_record": constrained_migration.get("experience_gap_record"),
                    "runtime_world_state_snapshot": constrained_migration.get("runtime_world_state_snapshot"),
                },
            },
        )
        write_json(OUTPUT / "05_preference_constrained_feasibility.json", constrained)

        after_experience_library = load_experience_library()
        after_concept_library = load_concept_library()
        non_rewrite = evidence(
            "偏好层作为独立运行时约束读入，不直接改写经验层或概念层持久化内容",
            "偏好记录独立于经验层和概念层存储并参与后续动作确定",
            {
                "before_hashes": {
                    "experience_library_sha1": sha1_of_payload(baseline_experience_library),
                    "concept_library_sha1": sha1_of_payload(baseline_concept_library),
                },
                "after_hashes": {
                    "experience_library_sha1": sha1_of_payload(after_experience_library),
                    "concept_library_sha1": sha1_of_payload(after_concept_library),
                },
                "preference_library_sha1_before": sha1_of_payload(baseline_preference_library),
                "preference_library_sha1_after": sha1_of_payload(load_preference_library()),
            },
        )
        write_json(OUTPUT / "06_preference_non_rewrite_boundary.json", non_rewrite)

        active_preferences = migration.get("runtime_world_state_snapshot", {}).get("active_preferences", [])
        advisory_ids = {
            item.get("preference_id")
            for item in migration.get("execution_feasibility", {}).get("preference_advisories", [])
        }
        attachment_ids = {
            item.get("preference_id")
            for item in attachment.get("active_preferences", [])
        }
        constrained_reasons = constrained_migration.get("execution_feasibility", {}).get("infeasible_reasons", [])
        constrained_reason_ids = {
            item.get("preference_id")
            for item in constrained_reasons
            if item.get("reason") == "human_preference_blocked_step"
        }

        assert_true(bool(baseline_preference_library.get("preference_records")), "preference library must expose baseline preference records")
        assert_true(bool(active_preferences), "runtime snapshot must load active preferences")
        assert_true(any(item.get("preference_id") == "pref_full_cup_default" for item in active_preferences), "default preference must be loaded into runtime snapshot")
        assert_true(bool(advisory_ids), "preference advisories must be present for executable path")

        assert_true(preference_query.get("query_type") == "preference_summary", "runtime query must route to preference summary")
        assert_true(preference_query.get("source") == "runtime_world_state_snapshot_only", "preference query must only read runtime snapshot")
        assert_true(bool(preference_query.get("evidence", {}).get("active_preferences")), "preference query must expose active preferences from runtime snapshot")

        assert_true(recorded_preference.get("preference_record", {}).get("preference_signal") == "forbid", "recorded preference must retain human signal")
        assert_true(recorded_preference.get("preference_record", {}).get("enforcement_policy") == "blocking", "recorded preference must retain blocking policy")
        assert_true(recorded_preference["preference_record"]["preference_id"] in attachment_ids, "new preference must attach to current runtime snapshot")
        assert_true(
            recorded_preference["preference_record"]["preference_id"]
            in {
                item.get("preference_id")
                for item in runtime_query_after_attachment.get("evidence", {}).get("active_preferences", [])
            },
            "attached preference must be visible in runtime preference query",
        )

        assert_true(constrained_migration.get("execution_feasibility", {}).get("result") == "partially_inexecutable", "blocking preference must constrain later migration feasibility")
        assert_true(recorded_preference["preference_record"]["preference_id"] in constrained_reason_ids, "blocking preference id must appear in infeasible reasons")
        assert_true(
            recorded_preference["preference_record"]["preference_id"]
            in constrained_migration.get("experience_gap_record", {}).get("preference_refs", []),
            "experience gap record must retain blocking preference reference",
        )
        assert_true("pick_up_cup" in constrained_migration.get("execution_feasibility", {}).get("blocked_steps", []), "blocked step must reflect preference-constrained action")

        assert_true(
            sha1_of_payload(baseline_experience_library) == sha1_of_payload(after_experience_library),
            "preference operations must not rewrite experience library",
        )
        assert_true(
            sha1_of_payload(baseline_concept_library) == sha1_of_payload(after_concept_library),
            "preference operations must not rewrite concept library",
        )

        summary = {
            "schema_version": "1.0.0",
            "technical_feature": "P015 人类偏好最小工程证据闭环",
            "utterance": UTTERANCE,
            "output_dir": str(OUTPUT),
            "evidence_files": [
                "evidence_index.json",
                "01_preference_library_baseline.json",
                "02_runtime_snapshot_preference_loading.json",
                "03_runtime_preference_query.json",
                "04_preference_record_and_attachment.json",
                "05_preference_constrained_feasibility.json",
                "06_preference_non_rewrite_boundary.json",
            ],
        }
        evidence_index = {
            "schema_version": "1.0.0",
            "title": "P015 人类偏好工程证据索引",
            "summary": "本索引用于将 P015 从偏好记录独立存储、运行时快照加载、状态查询、即时附着到可行性约束和经验层非改写边界的最小工程闭环，与输出文件、关键字段和代码来源建立一一对应关系。",
            "validation_command": "python demo_runtime\\rell_sample\\validate_p015_preference_alignment.py",
            "output_dir": str(OUTPUT),
            "evidence_items": EVIDENCE_INDEX,
        }
        write_json(OUTPUT / "evidence_index.json", evidence_index)
        write_json(OUTPUT / "00_summary.json", summary)
        print("P015 preference alignment validation passed.")
        print(f"Output: {OUTPUT}")
    finally:
        restore_text(PREFERENCE_LIBRARY_FILE, original_preference_library)
        restore_text(EXPERIENCE_LIBRARY_FILE, original_experience_library)
        restore_text(CONCEPT_LIBRARY_FILE, original_concept_library)


if __name__ == "__main__":
    main()
