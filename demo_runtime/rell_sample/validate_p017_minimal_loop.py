from __future__ import annotations

import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

from api_server import (
    AUDIT_STORE,
    build_causal_signature,
    build_invariant_contract,
    bind_portable_invariant_contract,
    dispatch_execution_loop_payload,
    get_process_chain_for_intent,
    get_runtime_world_state,
    migrate_experience,
    release_runtime_world_state,
    validate_experience_portability,
)
from runtime_core import write_json


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT.parent / "output" / "rell_sample" / "p017_minimal_loop"
UTTERANCE = "到水源处接一杯水"


EVIDENCE_INDEX = [
    {
        "file": "01_experience_record.json",
        "technical_feature": "经验记录包含目标因果事实、过程链或过程模板引用以及经验不变量契约",
        "claim_1_step": "获取待迁移的经验记录",
        "key_fields": [
            "experience_record.target_causal_fact",
            "experience_record.process_chain",
            "experience_record.causal_signature",
            "experience_record.experience_invariant_contract",
        ],
        "code_sources": [
            "api_server.py::build_causal_signature",
            "api_server.py::build_invariant_contract",
            "validate_p017_minimal_loop.py::main",
        ],
        "examination_use": "用于说明本方案复用的是历史真实经验中的可迁移不变量契约，而不是绝对坐标、固定轨迹或普通任务模板。",
    },
    {
        "file": "02_migration_context.json",
        "technical_feature": "当前迁移上下文包含当前空间语义数据、本体能力画像和任务意图",
        "claim_1_step": "获取当前迁移上下文",
        "key_fields": [
            "intent_translation",
            "current_space_semantic_data",
            "body_capability_profile",
        ],
        "code_sources": [
            "api_server.py::migrate_experience",
            "api_server.py::build_space_context",
            "api_server.py::build_default_body_capability_profile",
        ],
        "examination_use": "用于说明迁移判断同时受当前空间语义和执行本体能力约束，不是离线符号规划或静态规则匹配。",
    },
    {
        "file": "03_runtime_world_state_snapshot.json",
        "technical_feature": "任务期运行时世界状态快照用于当前任务期间的事实对齐和状态隔离",
        "claim_1_step": "基于当前迁移上下文生成任务期运行时世界状态快照",
        "key_fields": [
            "runtime_world_state_snapshot.runtime_world_state_snapshot_id",
            "runtime_world_state_snapshot.lifecycle",
            "runtime_world_state_snapshot.release_status",
            "runtime_world_state_snapshot.established_facts",
        ],
        "code_sources": [
            "api_server.py::build_initial_runtime_world_state",
            "api_server.py::get_runtime_world_state",
        ],
        "examination_use": "用于说明任务期快照是执行安全和状态隔离结构，不是普通长期世界模型或普通内存变量。",
    },
    {
        "file": "04_binding_and_feasibility.json",
        "technical_feature": "基于经验不变量契约、当前空间语义数据、本体能力画像和任务期快照生成绑定候选以及执行可行性结果",
        "claim_1_step": "对经验步骤进行跨空间跨本体适配",
        "key_fields": [
            "binding_candidate.generation_basis",
            "binding_candidate.step_bindings",
            "execution_feasibility.result",
            "execution_loop_payload.runtime_world_state_snapshot_id",
        ],
        "code_sources": [
            "api_server.py::build_binding_candidates",
            "api_server.py::build_execution_feasibility",
            "api_server.py::build_execution_loop_payload",
            "api_server.py::migrate_experience",
        ],
        "examination_use": "用于说明本方案不是直接规划求解动作，而是对既有经验步骤进行跨空间、跨本体的绑定和准入判断。",
    },
    {
        "file": "04b_alternate_space_binding.json",
        "technical_feature": "同一规范经验契约在第二空间和不同执行体上重新绑定并完成执行",
        "claim_1_step": "对经验步骤进行跨空间跨本体适配",
        "key_fields": [
            "alternate_space_semantic_data.space_id",
            "alternate_binding_candidate.step_bindings",
            "alternate_execution_feasibility.result",
            "alternate_execution_dispatch.runtime_world_state_snapshot.executor",
        ],
        "code_sources": [
            "api_server.py::migrate_experience",
            "api_server.py::build_binding_candidates",
            "api_server.py::dispatch_execution_loop_payload",
        ],
        "examination_use": "用于直接证明规范契约不依赖来源厨房实体，可绑定走廊饮水区中的不同容器、水源和执行主体。",
    },
    {
        "file": "05_execution_fact_feedback.json",
        "technical_feature": "开放执行闭环返回因果产出事实和因果销毁事实并回写任务期快照",
        "claim_1_step": "在可执行情况下调用执行闭环并依据事实回传更新快照",
        "key_fields": [
            "execution_dispatch.executor_type",
            "execution_dispatch.fact_feedback",
            "execution_dispatch.runtime_world_state_snapshot.established_facts",
            "execution_dispatch.outcome",
        ],
        "code_sources": [
            "api_server.py::dispatch_execution_loop_payload",
            "api_server.py::apply_step_to_runtime_world_state",
        ],
        "examination_use": "用于说明底层执行器可通过开放接口回传结构化事实状态，事实回传可以来自 SDK、ROS、仿真或数字执行体接口。",
    },
    {
        "file": "06_release_and_audit.json",
        "technical_feature": "任务结束后释放任务期运行时世界状态快照并写入审计记录",
        "claim_1_step": "任务结束后删除或释放任务期运行时世界状态快照并写入审计记录",
        "key_fields": [
            "release.release_status",
            "release.release_token",
            "audit_record.release_status",
            "runtime_world_state_after_release.runtime_world_state_snapshot.snapshot_lifecycle_state",
        ],
        "code_sources": [
            "api_server.py::release_runtime_world_state",
            "api_server.py::get_runtime_world_state",
        ],
        "examination_use": "用于说明快照释放是防状态污染的任务安全控制，并通过释放令牌和审计记录留下可验证证据。",
    },
    {
        "file": "07_portability_compilation.json",
        "technical_feature": "经验入库前编译可迁移不变量契约，并基于类型化槽位完成跨空间跨主体重绑定",
        "claim_1_step": "基于经验不变量契约对经验进行迁移适配",
        "key_fields": [
            "portability_validation.accepted_for_public_experience_library",
            "source_space_and_executor_binding.bound_slots",
            "alternate_space_and_executor_binding.bound_slots",
            "contaminated_experience_validation.violations",
        ],
        "code_sources": [
            "api_server.py::validate_experience_portability",
            "api_server.py::bind_portable_invariant_contract",
            "api_server.py::build_portable_binding_slot",
        ],
        "examination_use": "用于证明公共经验库保存的是可重新绑定的规范契约而非来源环境对象、绝对坐标或机器人专用控制参数。",
    },
]


def evidence(feature: str, claim_step: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "technical_feature": feature,
        "claim_1_step": claim_step,
        **payload,
    }


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    migration = migrate_experience(UTTERANCE)
    alternate_profile = {
        "executor_id": "site_b_mobile_manipulator",
        "executor_type": "simulated_robot",
        "body_profile": "wheeled_arm",
        "supported_actions": ["navigate_to_region", "grasp_object", "fill_container", "pour_container"],
    }
    alternate_migration = migrate_experience(UTTERANCE, alternate_profile, "site_b_corridor")
    intent = migration["intent_translation"]
    process_chain = get_process_chain_for_intent(intent)
    causal_signature = build_causal_signature(process_chain)
    invariant_contract = build_invariant_contract(process_chain)

    experience_record = evidence(
        "经验记录包含目标因果事实、过程链或过程模板引用以及经验不变量契约",
        "获取待迁移的经验记录",
        {
            "experience_record": {
                "experience_id": "p017_minimal_loop_experience",
                "source": "fixed_engineering_evidence",
                "source_utterance": UTTERANCE,
                "target_causal_fact": causal_signature["produces_fact"],
                "process_chain": process_chain,
                "process_template_ref": "rell_sample_cup_contains_water_chain",
                "causal_signature": causal_signature,
                "experience_invariant_contract": invariant_contract,
            }
        },
    )
    write_json(OUTPUT / "01_experience_record.json", experience_record)

    migration_context = evidence(
        "当前迁移上下文包含当前空间语义数据、本体能力画像和任务意图",
        "获取当前迁移上下文",
        {
            "migration_task_id": migration["migration_task_id"],
            "intent_translation": intent,
            "current_space_semantic_data": migration["current_space_semantic_data"],
            "body_capability_profile": migration["body_capability_profile"],
        },
    )
    write_json(OUTPUT / "02_migration_context.json", migration_context)

    runtime_snapshot_before = get_runtime_world_state(migration["migration_task_id"])
    runtime_world_state_snapshot = evidence(
        "任务期运行时世界状态快照用于当前任务期间的事实对齐和状态隔离",
        "基于当前迁移上下文生成任务期运行时世界状态快照",
        {
            "migration_task_id": migration["migration_task_id"],
            "runtime_world_state_snapshot": runtime_snapshot_before["runtime_world_state_snapshot"],
        },
    )
    write_json(OUTPUT / "03_runtime_world_state_snapshot.json", runtime_world_state_snapshot)

    binding_and_feasibility = evidence(
        "基于经验不变量契约、当前空间语义数据、本体能力画像和任务期快照生成绑定候选以及执行可行性结果",
        "对经验步骤进行跨空间跨本体适配",
        {
            "migration_task_id": migration["migration_task_id"],
            "binding_candidate": migration["binding_candidate"],
            "execution_feasibility": migration["execution_feasibility"],
            "execution_loop_payload": migration["execution_loop_payload"],
        },
    )
    write_json(OUTPUT / "04_binding_and_feasibility.json", binding_and_feasibility)
    alternate_dispatch = dispatch_execution_loop_payload(alternate_migration["execution_loop_payload"], "robot_sdk")
    write_json(
        OUTPUT / "04b_alternate_space_binding.json",
        evidence(
            "同一经验不变量契约在第二数字空间和另一执行体上生成新的实体绑定与执行可行性结果",
            "对经验步骤进行跨空间跨本体适配",
            {
                "source_space_binding": migration["binding_candidate"],
                "alternate_space_semantic_data": alternate_migration["current_space_semantic_data"],
                "alternate_executor_profile": alternate_migration["body_capability_profile"],
                "alternate_binding_candidate": alternate_migration["binding_candidate"],
                "alternate_execution_feasibility": alternate_migration["execution_feasibility"],
                "alternate_execution_dispatch": alternate_dispatch,
            },
        ),
    )

    dispatch = dispatch_execution_loop_payload(migration["execution_loop_payload"], "robot_sdk")
    execution_fact_feedback = evidence(
        "开放执行闭环返回因果产出事实和因果销毁事实并回写任务期快照",
        "在可执行情况下调用执行闭环并依据事实回传更新快照",
        {
            "migration_task_id": migration["migration_task_id"],
            "execution_dispatch": dispatch,
        },
    )
    write_json(OUTPUT / "05_execution_fact_feedback.json", execution_fact_feedback)

    release = release_runtime_world_state(migration["migration_task_id"], "p017_minimal_loop_finished")
    audit_record = AUDIT_STORE.get(release["audit_record_id"], {})
    release_and_audit = evidence(
        "任务结束后释放任务期运行时世界状态快照并写入审计记录",
        "任务结束后删除或释放任务期运行时世界状态快照并写入审计记录",
        {
            "migration_task_id": migration["migration_task_id"],
            "release": release,
            "audit_record": audit_record,
            "runtime_world_state_after_release": get_runtime_world_state(migration["migration_task_id"]),
        },
    )
    write_json(OUTPUT / "06_release_and_audit.json", release_and_audit)

    portable_experience = {
        "process_chain": process_chain,
        "causal_signature": causal_signature,
        "invariant_contract": invariant_contract,
        "action": {
            "action_type": "process_chain",
            "target_slots": [item["slot_id"] for item in invariant_contract.get("binding_slots", [])],
        },
    }
    portability_validation = validate_experience_portability(portable_experience)
    source_space_bindings = {
        item["slot_id"]: item["source_entity_ref"]
        for item in invariant_contract.get("source_binding_evidence", [])
    }
    alternate_space_bindings = {
        "TARGET_OPERATION_REGION": "site_b_preparation_surface",
        "TARGET_GRASPABLE_CONTAINER": "site_b_reusable_tumbler",
        "TARGET_LIQUID_SOURCE_REGION": "site_b_corridor_dispenser_zone",
        "SOURCE_LIQUID_RESOURCE_REGION": "site_b_corridor_dispenser_zone",
    }
    required_capabilities = sorted({item.get("required_capability") for item in invariant_contract.get("binding_slots", []) if item.get("required_capability")})
    source_executor = {"executor_id": "simulated_robot_a", "supported_actions": required_capabilities}
    alternate_executor = {"executor_id": "mobile_manipulator_b", "supported_actions": required_capabilities}
    source_binding = bind_portable_invariant_contract(invariant_contract, source_space_bindings, source_executor)
    alternate_binding = bind_portable_invariant_contract(invariant_contract, alternate_space_bindings, alternate_executor)
    contaminated_experience = deepcopy(portable_experience)
    contaminated_experience["action"]["joint_angles"] = [0.1, 0.2, 0.3]
    contaminated_validation = validate_experience_portability(contaminated_experience)
    portability_compilation = evidence(
        "经验入库前编译为类型化绑定槽并拒绝不可迁移执行细节，同一规范契约可在不同空间和主体上重新绑定",
        "基于经验不变量契约完成跨空间跨主体适配",
        {
            "portability_validation": portability_validation,
            "source_space_and_executor_binding": source_binding,
            "alternate_space_and_executor_binding": alternate_binding,
            "contaminated_experience_validation": contaminated_validation,
            "normative_contract": {key: value for key, value in invariant_contract.items() if key != "source_binding_evidence"},
        },
    )
    write_json(OUTPUT / "07_portability_compilation.json", portability_compilation)

    assert_true(process_chain, "experience record must include process steps")
    assert_true(causal_signature["produces_fact"] == "cup_contains_water", "target causal fact must be cup_contains_water")
    assert_true(invariant_contract.get("forbidden_storage"), "invariant contract must exclude non-transferable parameters")
    assert_true(portability_validation.get("accepted_for_public_experience_library"), "portable contract must pass public-library admission")
    assert_true(source_binding.get("accepted") and alternate_binding.get("accepted"), "same contract must bind across source and alternate spaces/executors")
    assert_true(not contaminated_validation.get("accepted_for_public_experience_library"), "joint-angle contamination must be rejected")
    assert_true(any("joint_angles" in item for item in contaminated_validation.get("violations", [])), "rejection must locate joint-angle field")
    normative_text = str(portability_compilation["normative_contract"])
    for source_ref in source_space_bindings.values():
        assert_true(source_ref not in normative_text, f"normative contract must not depend on source entity {source_ref}")
    assert_true(runtime_snapshot_before["release_status"] == "not_released", "runtime world snapshot must be active before release")
    assert_true(migration["binding_candidate"]["step_bindings"], "binding candidate must contain step bindings")
    assert_true(alternate_migration["execution_feasibility"]["result"] == "executable", "same experience must migrate into site_b corridor")
    alternate_bound_refs = {
        binding.get("space_binding", {}).get("target_ref") or binding.get("object_binding", {}).get("target_ref")
        for binding in alternate_migration["binding_candidate"].get("step_bindings", [])
    }
    assert_true("site_b_reusable_tumbler" in alternate_bound_refs, "alternate migration must bind the site_b container")
    assert_true("site_b_corridor_dispenser_zone" in alternate_bound_refs, "alternate migration must bind the site_b water source")
    assert_true(not alternate_migration["binding_candidate"].get("missing_targets"), "alternate migration must resolve all typed slots")
    assert_true(alternate_dispatch.get("outcome") == "fact_established", "alternate-space execution must establish the same target fact")
    alternate_final_state = alternate_dispatch.get("runtime_world_state_snapshot", {})
    assert_true("site_b_reusable_tumbler" in alternate_final_state.get("executor", {}).get("holding", []), "alternate execution must hold the rebound container")
    assert_true(alternate_final_state.get("executor", {}).get("location_ref") == "site_b_corridor_dispenser_zone", "alternate execution must end at the rebound water source")
    assert_true(migration["execution_feasibility"]["result"] == "executable", "minimal loop must be executable")
    assert_true(dispatch["outcome"] == "fact_established", "dispatch must establish target fact")
    assert_true(
        "cup_contains_water" in dispatch["runtime_world_state_snapshot"].get("established_facts", []),
        "runtime world snapshot must contain returned target fact",
    )
    assert_true(release["release_status"] == "released" and release["release_token"], "release must produce release token")
    assert_true(audit_record.get("release_status") == "released", "audit record must include release status")

    summary = {
        "schema_version": "1.0.0",
        "technical_feature": "P017 六段最小特征闭环工程证据汇总",
        "utterance": UTTERANCE,
        "migration_task_id": migration["migration_task_id"],
        "output_dir": str(OUTPUT),
        "evidence_files": [
            "evidence_index.json",
            "01_experience_record.json",
            "02_migration_context.json",
            "03_runtime_world_state_snapshot.json",
            "04_binding_and_feasibility.json",
            "04b_alternate_space_binding.json",
            "05_execution_fact_feedback.json",
            "06_release_and_audit.json",
            "07_portability_compilation.json",
        ],
        "closed_loop_checks": {
            "experience_record": True,
            "migration_context": True,
            "runtime_world_state_snapshot": True,
            "binding_and_feasibility": True,
            "execution_fact_feedback": True,
            "release_and_audit": True,
        },
    }
    evidence_index = {
        "schema_version": "1.0.0",
        "title": "P017 最小特征闭环工程证据索引",
        "summary": "本索引用于将 P017 跨空间跨本体真实经验迁移执行的六段最小闭环，与工程输出文件、关键字段、代码来源和审查答复用途建立对应关系。",
        "validation_command": "python demo_runtime\\rell_sample\\validate_p017_minimal_loop.py",
        "output_dir": str(OUTPUT),
        "evidence_items": EVIDENCE_INDEX,
    }
    write_json(OUTPUT / "evidence_index.json", evidence_index)
    write_json(OUTPUT / "00_summary.json", summary)
    print("P017 minimal loop validation passed.")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
