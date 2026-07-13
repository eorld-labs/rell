from __future__ import annotations

import hashlib
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .concept_pack_registry import load_concept_pack_registry
from .visual_concept_packs import load_visual_concept_packs


SUPPORTED_CONCEPT_IDS = {
    "concept_openable_door",
    "concept_refrigerator",
    "concept_portable_bottle",
}
REAL_OBSERVATION_SOURCES = {
    "user_provided_real_image",
    "current_robot_camera_verified_crop",
    "licensed_dataset_sample",
}
ASSESSMENT_STATUSES = {"observed", "uncertain_or_occluded", "contradicted"}
CONCEPT_CATEGORIES = {
    "concept_openable_door": "spatial_structures",
    "concept_refrigerator": "appliances_resources",
    "concept_portable_bottle": "containers_tableware",
}

_SESSIONS: dict[str, dict[str, Any]] = {}
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _catalog_entries() -> list[dict[str, Any]]:
    registry = load_concept_pack_registry(active_domains=("home",), include_on_demand=True)
    visual_packs = {
        item["concept_id"]: item
        for item in load_visual_concept_packs(include_on_demand=True)
        if item.get("concept_id") in SUPPORTED_CONCEPT_IDS
    }
    entries = []
    for concept in registry["concepts"]:
        concept_id = concept["concept_id"]
        if concept_id not in SUPPORTED_CONCEPT_IDS:
            continue
        visual_pack = visual_packs.get(concept_id)
        if not visual_pack:
            continue
        invariants = list(concept["perceptual_invariants"])
        required_features = list(visual_pack["recognition_adapter"]["required_observed_features"])
        entries.append({
            "concept_id": concept_id,
            "display_name": concept["display_name"],
            "aliases": deepcopy(concept["aliases"]),
            "domain_id": "home",
            "category": CONCEPT_CATEGORIES[concept_id],
            "load_policy": concept.get("load_policy", "domain_resident"),
            "concept_kernel": {
                "compatible_kinds": deepcopy(concept["compatible_kinds"]),
                "perceptual_invariants": invariants,
                "variable_features": deepcopy(concept["variable_features"]),
                "expected_relations": deepcopy(concept["expected_relations"]),
            },
            "visual_pack": {
                "pack_id": visual_pack["pack_id"],
                "required_observed_features": required_features,
                "minimum_match_score": visual_pack["recognition_adapter"]["minimum_match_score"],
                "accepted_sources": deepcopy(visual_pack["reference_sample_policy"]["accepted_sources"]),
            },
            "functional_claims": [
                {
                    "claim": claim,
                    "status": "unverified",
                    "required_evidence": "independent_runtime_or_physical_verification",
                }
                for claim in concept["functional_affordances"]
            ],
            "direct_execution_allowed": False,
        })
    return sorted(entries, key=lambda item: item["concept_id"])


def get_concept_teaching_catalog() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "station_id": "home_object_concept_teaching_station_v1",
        "concepts": _catalog_entries(),
        "workflow": [
            "inspect_existing_concept_kernel",
            "attach_real_observation_reference",
            "confirm_observed_identity",
            "assess_each_visual_invariant",
            "compile_observation_candidate",
        ],
        "boundary": {
            "candidate_does_not_mutate_concept_registry": True,
            "candidate_does_not_commit_runtime_fact": True,
            "visual_evidence_does_not_verify_function": True,
            "direct_execution_allowed": False,
        },
    }


def _entry_for(concept_id: str) -> dict[str, Any] | None:
    return next((item for item in _catalog_entries() if item["concept_id"] == concept_id), None)


def _audit(session: dict[str, Any], event: str, detail: dict[str, Any] | None = None) -> None:
    session["audit_timeline"].append({"at": _now(), "event": event, "detail": deepcopy(detail or {})})
    session["updated_at"] = _now()


def start_concept_teaching_session(concept_id: str) -> dict[str, Any]:
    entry = _entry_for(concept_id)
    if not entry:
        return {"error": "concept_not_supported_by_teaching_station", "concept_id": concept_id}
    session_id = f"concept_teach_{uuid.uuid4().hex[:12]}"
    now = _now()
    session = {
        "schema_version": "1.0.0",
        "session_id": session_id,
        "concept_id": concept_id,
        "concept_snapshot": entry,
        "status": "awaiting_real_observation",
        "observation": None,
        "identity_confirmation": "pending",
        "invariant_assessments": {
            feature: "pending" for feature in entry["visual_pack"]["required_observed_features"]
        },
        "functional_claims": deepcopy(entry["functional_claims"]),
        "compiled_candidate": None,
        "runtime_visible": False,
        "direct_execution_allowed": False,
        "created_at": now,
        "updated_at": now,
        "audit_timeline": [],
    }
    _audit(session, "session_started", {"concept_id": concept_id})
    with _LOCK:
        _SESSIONS[session_id] = session
    return deepcopy(session)


def get_concept_teaching_session(session_id: str) -> dict[str, Any]:
    with _LOCK:
        session = _SESSIONS.get(session_id)
        return deepcopy(session) if session else {"error": "concept_teaching_session_not_found", "session_id": session_id}


def attach_concept_observation(
    session_id: str,
    *,
    observation_ref: str,
    source_type: str,
    identity_confirmed: bool,
) -> dict[str, Any]:
    with _LOCK:
        session = _SESSIONS.get(session_id)
        if not session:
            return {"error": "concept_teaching_session_not_found", "session_id": session_id}
        if session["compiled_candidate"]:
            return {"error": "concept_teaching_session_already_compiled", "session_id": session_id}
        if source_type not in REAL_OBSERVATION_SOURCES:
            return {
                "error": "observation_source_not_admissible_as_real_evidence",
                "accepted_sources": sorted(REAL_OBSERVATION_SOURCES),
            }
        if not observation_ref.strip():
            return {"error": "observation_ref_required"}
        session["observation"] = {
            "observation_ref": observation_ref.strip(),
            "observation_ref_digest": hashlib.sha256(observation_ref.strip().encode("utf-8")).hexdigest(),
            "source_type": source_type,
            "evidence_scope": "appearance_and_identity_candidate_only",
            "image_bytes_ingested": False,
        }
        session["identity_confirmation"] = "confirmed" if identity_confirmed else "pending"
        session["status"] = "assessing_visual_invariants" if identity_confirmed else "awaiting_identity_confirmation"
        _audit(session, "real_observation_attached", {
            "source_type": source_type,
            "identity_confirmed": identity_confirmed,
            "image_bytes_ingested": False,
        })
        return deepcopy(session)


def assess_concept_invariants(session_id: str, assessments: list[dict[str, str]]) -> dict[str, Any]:
    with _LOCK:
        session = _SESSIONS.get(session_id)
        if not session:
            return {"error": "concept_teaching_session_not_found", "session_id": session_id}
        if not session["observation"]:
            return {"error": "real_observation_required_before_assessment"}
        if session["identity_confirmation"] != "confirmed":
            return {"error": "identity_confirmation_required_before_assessment"}
        if not isinstance(assessments, list) or not assessments:
            return {"error": "invariant_assessments_required"}
        allowed_features = set(session["invariant_assessments"])
        normalized: list[dict[str, str]] = []
        for assessment in assessments:
            if not isinstance(assessment, dict):
                return {"error": "invalid_invariant_assessment"}
            feature = str(assessment.get("feature", ""))
            status = str(assessment.get("status", ""))
            if feature not in allowed_features:
                return {"error": "unknown_visual_invariant", "feature": feature}
            if status not in ASSESSMENT_STATUSES:
                return {"error": "unsupported_invariant_status", "status": status}
            normalized.append({"feature": feature, "status": status})
        for assessment in normalized:
            session["invariant_assessments"][assessment["feature"]] = assessment["status"]
        values = set(session["invariant_assessments"].values())
        session["status"] = "ready_to_compile" if values == {"observed"} else "assessing_visual_invariants"
        _audit(session, "visual_invariants_assessed", {"assessments": normalized})
        return deepcopy(session)


def finish_concept_teaching_session(session_id: str) -> dict[str, Any]:
    with _LOCK:
        session = _SESSIONS.get(session_id)
        if not session:
            return {"error": "concept_teaching_session_not_found", "session_id": session_id}
        if session["compiled_candidate"]:
            return deepcopy(session["compiled_candidate"])
        blockers = []
        if not session["observation"]:
            blockers.append("real_observation_missing")
        if session["identity_confirmation"] != "confirmed":
            blockers.append("identity_not_confirmed")
        incomplete = {
            feature: status
            for feature, status in session["invariant_assessments"].items()
            if status != "observed"
        }
        if incomplete:
            blockers.append("visual_invariants_not_fully_observed")
        if blockers:
            return {
                "error": "concept_observation_candidate_not_ready",
                "blockers": blockers,
                "incomplete_invariants": incomplete,
                "runtime_visible": False,
                "direct_execution_allowed": False,
            }
        candidate = {
            "schema_version": "1.0.0",
            "candidate_id": f"concept_obs_{uuid.uuid4().hex[:12]}",
            "session_id": session_id,
            "concept_id": session["concept_id"],
            "status": "concept_observation_candidate_compiled",
            "identity_confirmed": True,
            "visual_invariants_observed": True,
            "functional_facts_physically_verified": False,
            "invariant_assessments": deepcopy(session["invariant_assessments"]),
            "observation_provenance": deepcopy(session["observation"]),
            "functional_claims": deepcopy(session["functional_claims"]),
            "deployment_status": "awaiting_controlled_review",
            "runtime_visible": False,
            "runtime_fact_committed": False,
            "concept_registry_mutated": False,
            "direct_execution_allowed": False,
            "compiled_at": _now(),
        }
        session["compiled_candidate"] = candidate
        session["status"] = "candidate_compiled"
        _audit(session, "observation_candidate_compiled", {"candidate_id": candidate["candidate_id"]})
        return deepcopy(candidate)


def reset_concept_teaching_sessions_for_validation() -> None:
    with _LOCK:
        _SESSIONS.clear()
