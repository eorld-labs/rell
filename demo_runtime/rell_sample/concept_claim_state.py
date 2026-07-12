from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any


def build_claim_evidence_states(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    claims = [_claim("object_identity", proposal["concept_id"], "identity_candidate")]
    claims.extend(_claim("perceptual_invariant", item, "hypothesis") for item in proposal["perceptual_invariants"])
    claims.extend(
        _claim("functional_affordance", item, "requires_physical_verification")
        for item in proposal["functional_role_contract"]["affordances"]
    )
    claims.extend(
        _claim("physical_boundary", item, "requires_physical_verification")
        for item in proposal["physical_properties_and_boundaries"]["safety_boundaries"]
    )
    claims.extend(_claim("expected_relation", item, "hypothesis") for item in proposal.get("expected_relations", []))
    return claims


def apply_real_observation_to_claims(
    claims: list[dict[str, Any]],
    *,
    evidence_ref: str,
    identity_confirmed: bool,
    matched_features: list[str],
    uncertain_features: list[str],
) -> list[dict[str, Any]]:
    updated = deepcopy(claims)
    matched = set(matched_features)
    uncertain = set(uncertain_features)
    for claim in updated:
        claim_type = claim["claim_type"]
        claim_value = claim["claim"]
        if claim_type == "object_identity" and identity_confirmed:
            _record(claim, "identity_confirmed", evidence_ref)
        elif claim_type == "perceptual_invariant" and claim_value in matched:
            _record(claim, "observed", evidence_ref)
        elif claim_type == "perceptual_invariant" and claim_value in uncertain:
            _record(claim, "uncertain_observed", evidence_ref)
    return updated


def summarize_claim_readiness(claims: list[dict[str, Any]]) -> dict[str, Any]:
    identity = [item for item in claims if item["claim_type"] == "object_identity"]
    perceptual = [item for item in claims if item["claim_type"] == "perceptual_invariant"]
    unresolved = [item["claim"] for item in perceptual if item["status"] != "observed"]
    return {
        "identity_confirmed": bool(identity and all(item["status"] == "identity_confirmed" for item in identity)),
        "perceptual_invariants_observed": not unresolved,
        "unresolved_perceptual_invariants": unresolved,
        "functional_claims_physically_verified": all(
            item["status"] == "physically_verified"
            for item in claims
            if item["claim_type"] in {"functional_affordance", "physical_boundary"}
        ),
    }


def compile_observation_assessment(
    claims: list[dict[str, Any]],
    assessments: list[dict[str, Any]],
    *,
    evidence_ref: str,
    identity_confirmed: bool,
) -> dict[str, Any]:
    known = {item["claim"] for item in claims if item["claim_type"] == "perceptual_invariant"}
    observed = []
    uncertain = []
    rejected = []
    evidence_details = []
    for assessment in assessments:
        invariant = str(assessment.get("invariant") or "")
        status = str(assessment.get("status") or "")
        if invariant not in known or status not in {"observed", "uncertain_occluded", "not_observed"}:
            rejected.append({"invariant": invariant, "reason": "unknown_invariant_or_status"})
            continue
        evidence_details.append({
            "invariant": invariant,
            "status": status,
            "visual_basis": str(assessment.get("visual_basis") or ""),
            "image_region": str(assessment.get("image_region") or ""),
        })
        if status == "observed":
            observed.append(invariant)
        else:
            uncertain.append(invariant)
    updated = apply_real_observation_to_claims(
        claims,
        evidence_ref=evidence_ref,
        identity_confirmed=identity_confirmed,
        matched_features=observed,
        uncertain_features=uncertain,
    )
    readiness = summarize_claim_readiness(updated)
    return {
        "claim_evidence_states": updated,
        "claim_readiness": readiness,
        "matched_features": sorted(set(observed)),
        "uncertain_features": sorted(set(uncertain)),
        "assessment_evidence": evidence_details,
        "rejected_assessments": rejected,
        "next_evidence_request": _next_evidence_request(readiness),
    }


def _claim(claim_type: str, value: str, status: str) -> dict[str, Any]:
    seed = f"{claim_type}|{value}"
    return {
        "claim_id": "concept_claim_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12],
        "claim": value,
        "claim_type": claim_type,
        "status": status,
        "evidence_refs": [],
        "candidate_only": True,
    }


def _record(claim: dict[str, Any], status: str, evidence_ref: str) -> None:
    claim["status"] = status
    if evidence_ref not in claim["evidence_refs"]:
        claim["evidence_refs"].append(evidence_ref)


def _next_evidence_request(readiness: dict[str, Any]) -> dict[str, Any] | None:
    unresolved = readiness["unresolved_perceptual_invariants"]
    if unresolved:
        return {
            "target_claims": unresolved,
            "requested_evidence": "new_viewpoint_or_additional_sensor_observation",
            "reason": "required_perceptual_invariants_unresolved",
        }
    if not readiness["identity_confirmed"]:
        return {
            "target_claims": ["object_identity"],
            "requested_evidence": "human_or_multi_source_identity_confirmation",
            "reason": "object_identity_unconfirmed",
        }
    return None
