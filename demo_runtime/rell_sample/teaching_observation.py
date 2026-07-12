from __future__ import annotations

import hashlib
import time
from copy import deepcopy
from typing import Any


def build_live_first_person_observation_packet(
    *,
    teaching_id: str,
    goal_utterance: str,
    world_revision: int,
    perception: dict[str, Any],
    pedagogical_signals: dict[str, Any],
) -> dict[str, Any]:
    started_at = time.time()
    perception_observations = perception.get("perception_observations", [])
    observation_ids = [item.get("observation_id") for item in perception_observations if item.get("observation_id")]
    sensor_frames = list(
        dict.fromkeys(
            item.get("sensor_contract", {}).get("sensor_frame")
            for item in perception_observations
            if item.get("sensor_contract", {}).get("sensor_frame")
        )
    )
    packet_id = "teach_obs_" + hashlib.sha1(
        f"{teaching_id}|{world_revision}|{'|'.join(observation_ids)}".encode("utf-8")
    ).hexdigest()[:12]
    grounding = perception.get("concept_grounding", {})
    return {
        "schema_version": "1.0.0",
        "observation_packet_id": packet_id,
        "source": {
            "source_type": "live_first_person_embodied_teaching",
            "source_identity": teaching_id,
            "provenance_chain": ["human_teacher", "task_conditioned_rgbd_adapter"],
            "authorization_scope": "current_teaching_session_only",
        },
        "time_window": {
            "start": started_at,
            "end": None,
            "clock_quality": "single_runtime_clock",
        },
        "reference_frames": {
            "world_frame": "current_runtime_world_revision",
            "body_frame": "executor_body_frame",
            "sensor_frames": sensor_frames,
        },
        "pedagogical_signals": deepcopy(pedagogical_signals),
        "evidence": {
            "level": "L2",
            "proof_scope": "candidate_generation_only",
            "world_revision": world_revision,
            "observation_ids": observation_ids,
            "uncertainty": {
                "grounding_status": grounding.get("grounding_status"),
                "ambiguity_reason": grounding.get("ambiguity_reason"),
            },
        },
        "temporal_alignment": {
            "mode": "session_window_alignment",
            "language_event": {
                "text": goal_utterance,
                "time_range": [started_at, started_at],
                "confidence": 1.0,
            },
            "observation_event_refs": observation_ids,
            "frame_level_audio_alignment_implemented": False,
        },
        "observations": {
            "task_perception_frame": deepcopy(perception.get("task_perception_frame", {})),
            "concept_grounding": deepcopy(grounding),
            "active_perception_trace": deepcopy(perception.get("active_perception_trace", [])),
        },
        "candidate_only": True,
        "runtime_fact_committed": False,
    }


def finalize_observation_packet(
    packet: dict[str, Any],
    *,
    pedagogical_signals: dict[str, Any],
) -> dict[str, Any]:
    finalized = deepcopy(packet)
    finalized["time_window"]["end"] = time.time()
    finalized["pedagogical_signals"] = deepcopy(pedagogical_signals)
    return finalized


def build_portable_teaching_evidence_summary(packet: dict[str, Any]) -> dict[str, Any]:
    temporal = packet.get("temporal_alignment", {})
    evidence = packet.get("evidence", {})
    return {
        "observation_packet_id": packet.get("observation_packet_id"),
        "source_type": packet.get("source", {}).get("source_type"),
        "evidence_level": evidence.get("level"),
        "proof_scope": evidence.get("proof_scope"),
        "source_world_revision": evidence.get("world_revision"),
        "observation_count": len(evidence.get("observation_ids", [])),
        "temporal_alignment": {
            "mode": temporal.get("mode"),
            "frame_level_audio_alignment_implemented": bool(
                temporal.get("frame_level_audio_alignment_implemented", False)
            ),
        },
        "raw_observations_persisted": False,
        "source_identity_persisted": False,
    }
