from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from concept_core import (
    CognitiveAuthorityLedger,
    run_concept_validation_loop,
    run_quality_profile_drift_loop,
    run_recovery_boundary_probe_loop,
)
from runtime_core import run_simulated_runtime_sample


SCENARIOS = {
    "quality_profile_drift": {
        "label": "质量档案漂移",
        "loop": "多假设 -> 主动观察 -> 自主关闭",
    },
    "recovery_boundary_probe": {
        "label": "恢复边界探测",
        "loop": "重复恢复 -> 安全试验 -> P016 验真",
    },
    "concept_promote": {
        "label": "候选概念晋级",
        "loop": "重复模式 -> 新实例验证 -> 晋级",
    },
    "concept_reject": {
        "label": "候选概念否决",
        "loop": "重复模式 -> 新实例验证 -> 否决",
    },
}


def get_cognitive_inquiry_catalog() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "scenarios": [
            {"scenario": scenario, **definition}
            for scenario, definition in SCENARIOS.items()
        ],
        "fact_authority": "session_world_fact_ledger",
        "control_gateway": "P018",
        "verification_gateway": "P016",
        "direct_execution_allowed": False,
    }


def _authority_from_context(context: dict[str, Any]) -> CognitiveAuthorityLedger:
    ledger = context.get("world_fact_ledger") or {}
    authority_ref = ledger.get("ledger_id")
    if not authority_ref:
        raise ValueError("session_world_fact_ledger_missing")
    authority = CognitiveAuthorityLedger(
        int(context.get("world_revision", 0)), authority_ref=authority_ref
    )
    for envelope in ledger.get("evidence", []):
        authority.add_evidence(envelope)
    return authority


def run_cognitive_inquiry(
    context: dict[str, Any], scenario: str, *, data_dir: Path
) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        return {
            "error": "cognitive_inquiry_scenario_not_found",
            "scenario": scenario,
            "available_scenarios": sorted(SCENARIOS),
        }
    authority = _authority_from_context(context)
    base_evidence_refs = set(authority.evidence)
    scope_ref = (
        f"inquiry_scope:{context.get('session_id')}:{scenario}:"
        f"{int(context.get('history_count', 0)) + 1}"
    )
    if scenario == "quality_profile_drift":
        loop = run_quality_profile_drift_loop(
            authority=authority, inquiry_scope_ref=scope_ref
        )
    elif scenario == "recovery_boundary_probe":
        p016_result = run_simulated_runtime_sample(data_dir, "simulated_success")
        loop = run_recovery_boundary_probe_loop(
            p016_result=p016_result,
            authority=authority,
            inquiry_scope_ref=scope_ref,
        )
    else:
        loop = run_concept_validation_loop(
            prediction_confirmed=scenario == "concept_promote",
            authority=authority,
            inquiry_scope_ref=scope_ref,
        )

    inquiry = loop["closure"]["inquiry"]
    arbitration = loop["action"]["arbitration_receipt"]
    planning = loop["planning_view"]
    explanation = loop["explanation_view"]
    authority_extension = deepcopy(loop["authority_snapshot"])
    authority_extension["evidence"] = {
        ref: envelope
        for ref, envelope in authority_extension["evidence"].items()
        if ref not in base_evidence_refs
    }
    return {
        "schema_version": "1.0.0",
        "status": "cognitive_inquiry_closed",
        "scenario": scenario,
        "scenario_label": SCENARIOS[scenario]["label"],
        "session_id": context.get("session_id"),
        "world_revision": context.get("world_revision"),
        "fact_authority_ref": authority.ledger_id,
        "inquiry_id": inquiry["inquiry_id"],
        "inquiry_status": inquiry["status"],
        "signal_evidence_refs": inquiry["trigger_evidence_refs"],
        "diagnostic_summary": deepcopy(
            loop.get("trigger")
            or loop.get("recovery_cluster")
            or {"pattern_episode_count": loop.get("pattern_episode_count")}
        ),
        "observation_or_probe_receipt": deepcopy(
            loop.get("observation_receipt")
            or loop.get("new_instance_probe_receipt")
        ),
        "competing_hypotheses": inquiry["candidate_hypotheses"],
        "selected_hypothesis": inquiry["selected_hypothesis"],
        "transition_log": loop["transition_log"],
        "p018_arbitration": deepcopy(arbitration),
        "p016_verification_ref": inquiry["verification_ref"],
        "p016_runtime_receipt": deepcopy(loop.get("p016_runtime_receipt")),
        "event_ref": loop["closure"]["event_ref"],
        "predicate_ref": loop["closure"]["predicate_ref"],
        "evidence_ref": loop["closure"]["evidence_ref"],
        "planning_view": deepcopy(planning),
        "explanation_view": deepcopy(explanation),
        "concept_decision": deepcopy(loop.get("decision")),
        "concept_candidate": deepcopy(loop.get("candidate")),
        "authority_extension": authority_extension,
        "shared_readback": {
            "same_fact_authority": planning["fact_authority_ref"]
            == explanation["fact_authority_ref"]
            == authority.ledger_id,
            "same_predicate_ref": planning["predicate_ref"]
            == explanation["predicate_ref"],
            "same_evidence_refs": planning["evidence_refs"]
            == explanation["evidence_refs"],
        },
        "control_gateway": "P018",
        "verification_gateway": "P016",
        "direct_execution_allowed": False,
        "runtime_fact_committed_by_inquiry": False,
    }


__all__ = ["get_cognitive_inquiry_catalog", "run_cognitive_inquiry"]
