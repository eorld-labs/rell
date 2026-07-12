from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any


def _stable_id(prefix: str, parts: list[Any]) -> str:
    seed = "|".join(str(part or "") for part in parts)
    return prefix + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def record_concept_reuse(
    store: dict[str, dict[str, Any]],
    evidence_packets: list[dict[str, Any]],
    *,
    resolution_id: str,
    task_id: str | None,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for packet in evidence_packets:
        concept_id = str(packet.get("concept_id") or "unknown_concept")
        record = store.setdefault(
            concept_id,
            {
                "concept_id": concept_id,
                "concept_type": packet.get("concept_type"),
                "formation_source": "local_concept_definition_with_evidence",
                "reuse_count": 0,
                "successful_reuse_count": 0,
                "last_resolution_id": None,
                "last_task_id": None,
                "last_runtime_world_state_snapshot_id": None,
            },
        )
        event_type = "concept_formed" if record["reuse_count"] == 0 else "concept_reused"
        record["reuse_count"] += 1
        record["successful_reuse_count"] += 1
        record["last_resolution_id"] = resolution_id
        record["last_task_id"] = task_id
        record["last_runtime_world_state_snapshot_id"] = (
            packet.get("runtime_binding", {}).get("runtime_world_state_snapshot_id")
        )
        events.append(
            {
                "event_id": _stable_id("concept_lifecycle_", [resolution_id, concept_id, record["reuse_count"]]),
                "event_type": event_type,
                "concept_id": concept_id,
                "reuse_ordinal": record["reuse_count"],
                "evidence_id": packet.get("evidence_id"),
                "candidate_only": True,
                "direct_execution_allowed": False,
                "must_reenter_orchestration_layer": True,
            }
        )
    return {
        "events": events,
        "formed_count": sum(item["event_type"] == "concept_formed" for item in events),
        "reused_count": sum(item["event_type"] == "concept_reused" for item in events),
    }


def record_concept_fallback(
    fallback_store: dict[str, dict[str, Any]],
    gap_evidence: dict[str, Any],
    *,
    packet_id: str,
    cloud_recall_requested: bool,
) -> dict[str, Any]:
    event_id = _stable_id("concept_fallback_", [packet_id, gap_evidence.get("evidence_id")])
    event = {
        "event_id": event_id,
        "event_type": "local_concept_reuse_failed",
        "source_packet_id": packet_id,
        "gap_evidence_id": gap_evidence.get("evidence_id"),
        "gap_reasons": gap_evidence.get("gap_reasons", []),
        "fallback_target": "cloud_candidate_or_human_clarification" if cloud_recall_requested else "local_concepts_sufficient",
        "cloud_recall_requested": cloud_recall_requested,
        "candidate_only": True,
        "direct_execution_allowed": False,
        "must_reenter_orchestration_layer": True,
    }
    if cloud_recall_requested:
        fallback_store[event_id] = event
    return event


def build_concept_lifecycle_view(
    store: dict[str, dict[str, Any]],
    fallback_store: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "concept_records": deepcopy(list(store.values())),
        "fallback_events": deepcopy(list(fallback_store.values())),
        "policy": {
            "candidate_only": True,
            "direct_execution_allowed": False,
            "must_reenter_orchestration_layer": True,
        },
    }
