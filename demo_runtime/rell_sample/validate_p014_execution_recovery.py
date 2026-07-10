from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from api_server import (
    EXPERIENCE_LIBRARY_FILE,
    RECOVERY_LIBRARY_FILE,
    dispatch_execution_loop_payload,
    get_audit,
    get_readaptation,
    get_recovery_record,
    get_recovery_records_for_task,
    get_runtime_world_state,
    inject_runtime_perturbation,
    load_recovery_library,
    migrate_experience,
    readapt_runtime_conflict,
    run_process,
)
from runtime_core import write_json


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT.parent / "output" / "rell_sample" / "p014_execution_recovery"
MIGRATION_UTTERANCE = "到水源处接一杯水"


EVIDENCE_INDEX = [
    {
        "file": "01_recovery_library_baseline.json",
        "technical_feature": "恢复记录以独立恢复记录库形式持久化存储，而不是仅停留在运行期内存或审计文本中",
        "claim_step": "将恢复经验记录为可查询的结构化补救记录",
        "key_fields": [
            "recovery_library.recovery_records",
            "recovery_library.schema_version",
        ],
        "code_sources": [
            "api_server.py::load_recovery_library",
            "api_server.py::save_recovery_library",
        ],
    },
    {
        "file": "02_conflict_recovery_record.json",
        "technical_feature": "执行过程中发生双通道验真冲突时，系统生成结构化恢复记录而不是仅返回失败状态",
        "claim_step": "执行目标动作过程中检测偏离并形成候选补救动作",
        "key_fields": [
            "conflict_run.audit_summary.outcome",
            "conflict_run.recovery_record.deviation_context",
            "conflict_run.recovery_record.recovery_action",
            "conflict_run.recovery_record.recovery_outcome",
        ],
        "code_sources": [
            "api_server.py::run_process",
            "api_server.py::build_recovery_record_for_task",
            "api_server.py::persist_recovery_record",
        ],
    },
    {
        "file": "03_recovery_query_and_audit_linkage.json",
        "technical_feature": "恢复记录能够按单条标识和按任务维度查询，并与审计链路关联",
        "claim_step": "对执行中途偏离形成的恢复记录进行结构化存储和关联",
        "key_fields": [
            "recovery_lookup.recovery_id",
            "task_recoveries.recovery_records",
            "audit_lookup.recovery_record_ids",
        ],
        "code_sources": [
            "api_server.py::get_recovery_record",
            "api_server.py::get_recovery_records_for_task",
            "api_server.py::attach_recovery_record_to_context",
            "api_server.py::get_audit",
        ],
    },
    {
        "file": "04_runtime_conflict_readaptation.json",
        "technical_feature": "运行时事实冲突会触发再适配，并生成指向再适配流程的恢复记录",
        "claim_step": "基于偏离和当前执行上下文确定补救动作并切入恢复流程",
        "key_fields": [
            "readaptation.runtime_conflicts",
            "readaptation.execution_feasibility.result",
            "readaptation.recovery_record.recovery_action.action_type",
            "readaptation.recovery_record.source_refs.runtime_conflicts",
        ],
        "code_sources": [
            "api_server.py::readapt_runtime_conflict",
            "api_server.py::build_runtime_conflict_items",
            "api_server.py::build_recovery_record_for_task",
        ],
    },
    {
        "file": "05_stepwise_blocked_recovery.json",
        "technical_feature": "执行闭环中途遇到硬阻断时，系统在不中断整体任务语义的情况下触发步骤级恢复和再适配",
        "claim_step": "在执行过程中基于当前偏离切换至候选补救动作或恢复流程",
        "key_fields": [
            "dispatch.outcome",
            "dispatch.fact_feedback",
            "dispatch.stepwise_readaptation.readaptation_id",
            "dispatch.recovery_record.recovery_action.action_type",
            "runtime_state_after_dispatch.runtime_world_state_snapshot.recovery_record_ids",
        ],
        "code_sources": [
            "api_server.py::inject_runtime_perturbation",
            "api_server.py::evaluate_runtime_step_preflight",
            "api_server.py::build_stepwise_readaptation",
            "api_server.py::dispatch_execution_loop_payload",
        ],
    },
    {
        "file": "06_recovery_library_snapshot.json",
        "technical_feature": "恢复层以独立恢复记录库沉淀多类恢复事件，支持后续复核和工程举证",
        "claim_step": "补救记录独立于单次执行返回结果而持续留存在恢复记录库中",
        "key_fields": [
            "recovery_library.recovery_records",
            "recovery_ids",
            "recovery_action_types",
            "recovery_task_ids",
        ],
        "code_sources": [
            "api_server.py::persist_recovery_record",
            "api_server.py::load_recovery_library",
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
    original_recovery_library = backup_text(RECOVERY_LIBRARY_FILE)

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    EXPERIENCE_LIBRARY_FILE.write_text(
        json.dumps({"schema_version": "1.0.0", "experiences": []}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    RECOVERY_LIBRARY_FILE.write_text(
        json.dumps({"schema_version": "1.0.0", "recovery_records": []}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    try:
        baseline_recovery_library = load_recovery_library()
        baseline = evidence(
            "恢复记录以独立恢复记录库形式持久化存储，而不是仅停留在运行期内存或审计文本中",
            "将恢复经验记录为可查询的结构化补救记录",
            {
                "recovery_library": baseline_recovery_library,
            },
        )
        write_json(OUTPUT / "01_recovery_library_baseline.json", baseline)

        conflict_run = run_process("channel_conflict")
        conflict_recovery = conflict_run.get("recovery_record")
        conflict_evidence = evidence(
            "执行过程中发生双通道验真冲突时，系统生成结构化恢复记录而不是仅返回失败状态",
            "执行目标动作过程中检测偏离并形成候选补救动作",
            {
                "conflict_run": {
                    "task_id": conflict_run.get("task_id"),
                    "scenario": conflict_run.get("scenario"),
                    "audit_summary": conflict_run.get("audit_summary"),
                    "recovery_record": conflict_recovery,
                    "stage_runtime_state": conflict_run.get("stage_runtime_state"),
                },
            },
        )
        write_json(OUTPUT / "02_conflict_recovery_record.json", conflict_evidence)

        recovery_lookup = get_recovery_record(conflict_recovery["recovery_id"])
        task_recoveries = get_recovery_records_for_task(conflict_run["task_id"])
        audit_lookup = get_audit(conflict_run["task_id"])
        query_and_linkage = evidence(
            "恢复记录能够按单条标识和按任务维度查询，并与审计链路关联",
            "对执行中途偏离形成的恢复记录进行结构化存储和关联",
            {
                "recovery_lookup": recovery_lookup,
                "task_recoveries": task_recoveries,
                "audit_lookup": audit_lookup,
            },
        )
        write_json(OUTPUT / "03_recovery_query_and_audit_linkage.json", query_and_linkage)

        readaptation = readapt_runtime_conflict(conflict_run["task_id"], MIGRATION_UTTERANCE)
        readaptation_lookup = get_readaptation(readaptation["readaptation_id"])
        readaptation_evidence = evidence(
            "运行时事实冲突会触发再适配，并生成指向再适配流程的恢复记录",
            "基于偏离和当前执行上下文确定补救动作并切入恢复流程",
            {
                "readaptation": readaptation,
                "readaptation_lookup": readaptation_lookup,
            },
        )
        write_json(OUTPUT / "04_runtime_conflict_readaptation.json", readaptation_evidence)

        migration = migrate_experience(MIGRATION_UTTERANCE)
        perturbation = inject_runtime_perturbation(
            migration["migration_task_id"],
            {"kind": "water_source_door_closed"},
            "move_to_water_source",
        )
        dispatch = dispatch_execution_loop_payload(migration["execution_loop_payload"], "robot_sdk")
        runtime_state_after_dispatch = get_runtime_world_state(migration["migration_task_id"])
        stepwise_recovery_evidence = evidence(
            "执行闭环中途遇到硬阻断时，系统在不中断整体任务语义的情况下触发步骤级恢复和再适配",
            "在执行过程中基于当前偏离切换至候选补救动作或恢复流程",
            {
                "migration": {
                    "migration_task_id": migration.get("migration_task_id"),
                    "execution_feasibility": migration.get("execution_feasibility"),
                    "execution_loop_payload": migration.get("execution_loop_payload"),
                },
                "perturbation": perturbation,
                "dispatch": dispatch,
                "runtime_state_after_dispatch": runtime_state_after_dispatch,
            },
        )
        write_json(OUTPUT / "05_stepwise_blocked_recovery.json", stepwise_recovery_evidence)

        recovery_library_snapshot = load_recovery_library()
        recovery_ids = [item.get("recovery_id") for item in recovery_library_snapshot.get("recovery_records", [])]
        recovery_action_types = [
            item.get("recovery_action", {}).get("action_type")
            for item in recovery_library_snapshot.get("recovery_records", [])
        ]
        recovery_task_ids = [item.get("task_id") for item in recovery_library_snapshot.get("recovery_records", [])]
        library_snapshot = evidence(
            "恢复层以独立恢复记录库沉淀多类恢复事件，支持后续复核和工程举证",
            "补救记录独立于单次执行返回结果而持续留存在恢复记录库中",
            {
                "recovery_library": recovery_library_snapshot,
                "recovery_ids": recovery_ids,
                "recovery_action_types": recovery_action_types,
                "recovery_task_ids": recovery_task_ids,
            },
        )
        write_json(OUTPUT / "06_recovery_library_snapshot.json", library_snapshot)

        assert_true(baseline_recovery_library.get("recovery_records") == [], "recovery library must start empty")

        assert_true(
            conflict_run.get("audit_summary", {}).get("outcome") == "requires_human_confirmation",
            "channel conflict must require human confirmation",
        )
        assert_true(conflict_recovery is not None, "channel conflict must create recovery record")
        assert_true(
            conflict_recovery.get("recovery_action", {}).get("action_type") == "request_human_confirmation",
            "channel conflict recovery must request human confirmation",
        )
        assert_true(
            conflict_recovery.get("recovery_outcome", {}).get("outcome_type") == "escalated",
            "channel conflict recovery outcome must be escalated",
        )

        assert_true(
            recovery_lookup.get("recovery_id") == conflict_recovery.get("recovery_id"),
            "recovery record must be queryable by id",
        )
        assert_true(
            any(item.get("recovery_id") == conflict_recovery.get("recovery_id") for item in task_recoveries.get("recovery_records", [])),
            "recovery record must be queryable by task",
        )
        assert_true(
            conflict_recovery.get("recovery_id") in audit_lookup.get("recovery_record_ids", []),
            "audit record must retain recovery record reference",
        )

        readaptation_recovery = readaptation.get("recovery_record")
        assert_true(bool(readaptation.get("runtime_conflicts")), "readaptation must expose runtime conflicts")
        assert_true(readaptation_recovery is not None, "readaptation must create recovery record")
        assert_true(
            readaptation_recovery.get("recovery_action", {}).get("action_type") == "trigger_readaptation",
            "readaptation recovery must point to readaptation flow",
        )
        assert_true(
            readaptation_lookup.get("readaptation_id") == readaptation.get("readaptation_id"),
            "readaptation record must be queryable",
        )

        dispatch_recovery = dispatch.get("recovery_record")
        feedback_items = dispatch.get("fact_feedback", [])
        blocked_feedback = next((item for item in feedback_items if item.get("preflight_result") == "blocked"), None)
        runtime_snapshot_after_dispatch = runtime_state_after_dispatch.get("runtime_world_state_snapshot", {})
        assert_true(
            dispatch.get("outcome") == "readaptation_required",
            "hard perturbation must trigger readaptation_required",
        )
        assert_true(dispatch_recovery is not None, "blocked dispatch must create recovery record")
        assert_true(blocked_feedback is not None, "blocked dispatch must expose blocked preflight feedback")
        assert_true(
            dispatch_recovery.get("recovery_action", {}).get("action_type") == "trigger_readaptation",
            "blocked dispatch recovery must trigger readaptation",
        )
        assert_true(
            dispatch.get("stepwise_readaptation", {}).get("readaptation_id") is not None,
            "blocked dispatch must persist stepwise readaptation",
        )
        assert_true(
            dispatch_recovery.get("recovery_id") in runtime_snapshot_after_dispatch.get("recovery_record_ids", []),
            "runtime snapshot must retain blocked dispatch recovery reference",
        )

        assert_true(len(recovery_library_snapshot.get("recovery_records", [])) >= 3, "recovery library must persist multiple recovery records")
        assert_true(conflict_recovery.get("recovery_id") in recovery_ids, "library must retain conflict recovery id")
        assert_true(readaptation_recovery.get("recovery_id") in recovery_ids, "library must retain readaptation recovery id")
        assert_true(dispatch_recovery.get("recovery_id") in recovery_ids, "library must retain dispatch recovery id")

        summary = {
            "schema_version": "1.0.0",
            "technical_feature": "P014 执行恢复最小工程证据闭环",
            "migration_utterance": MIGRATION_UTTERANCE,
            "output_dir": str(OUTPUT),
            "evidence_files": [
                "evidence_index.json",
                "01_recovery_library_baseline.json",
                "02_conflict_recovery_record.json",
                "03_recovery_query_and_audit_linkage.json",
                "04_runtime_conflict_readaptation.json",
                "05_stepwise_blocked_recovery.json",
                "06_recovery_library_snapshot.json",
            ],
        }
        evidence_index = {
            "schema_version": "1.0.0",
            "title": "P014 执行恢复工程证据索引",
            "summary": "本索引用于将 P014 从恢复记录独立存储、冲突生成恢复记录、按任务和按标识查询、运行时再适配以及执行中途阻断恢复的最小工程闭环，与输出文件、关键字段和代码来源建立一一对应关系。",
            "validation_command": "python demo_runtime\\rell_sample\\validate_p014_execution_recovery.py",
            "output_dir": str(OUTPUT),
            "evidence_items": EVIDENCE_INDEX,
        }
        write_json(OUTPUT / "evidence_index.json", evidence_index)
        write_json(OUTPUT / "00_summary.json", summary)
        print("P014 execution recovery validation passed.")
        print(f"Output: {OUTPUT}")
    finally:
        restore_text(EXPERIENCE_LIBRARY_FILE, original_experience_library)
        restore_text(RECOVERY_LIBRARY_FILE, original_recovery_library)


if __name__ == "__main__":
    main()
