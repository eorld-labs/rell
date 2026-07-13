from __future__ import annotations

from concept_core.concept_pack_registry import load_concept_pack_registry
from concept_core.concept_teaching_station import (
    assess_concept_invariants,
    attach_concept_observation,
    finish_concept_teaching_session,
    get_concept_teaching_catalog,
    reset_concept_teaching_sessions_for_validation,
    start_concept_teaching_session,
)


EXPECTED_CONCEPTS = {
    "concept_openable_door",
    "concept_refrigerator",
    "concept_portable_bottle",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    reset_concept_teaching_sessions_for_validation()
    registry_before = load_concept_pack_registry(active_domains=("home",), include_on_demand=True)
    catalog = get_concept_teaching_catalog()
    concepts = {item["concept_id"]: item for item in catalog["concepts"]}
    require(set(concepts) == EXPECTED_CONCEPTS, "teaching catalog must expose the three trial concepts")
    require(catalog["boundary"]["direct_execution_allowed"] is False, "catalog must deny execution authority")

    unknown = start_concept_teaching_session("concept_unknown")
    require(unknown.get("error") == "concept_not_supported_by_teaching_station", "unknown concept must be rejected")

    for concept_id, concept in concepts.items():
        session = start_concept_teaching_session(concept_id)
        session_id = session["session_id"]

        synthetic = attach_concept_observation(
            session_id,
            observation_ref=f"synthetic://{concept_id}/sample-1",
            source_type="generated_synthetic_image",
            identity_confirmed=True,
        )
        require(synthetic.get("error") == "observation_source_not_admissible_as_real_evidence", "synthetic evidence must be rejected")

        pending_identity = attach_concept_observation(
            session_id,
            observation_ref=f"evidence://real-home/{concept_id}/observation-1",
            source_type="user_provided_real_image",
            identity_confirmed=False,
        )
        require(pending_identity["status"] == "awaiting_identity_confirmation", "identity confirmation must be explicit")
        blocked_assessment = assess_concept_invariants(session_id, [{
            "feature": concept["visual_pack"]["required_observed_features"][0],
            "status": "observed",
        }])
        require(blocked_assessment.get("error") == "identity_confirmation_required_before_assessment", "unconfirmed identity must block assessment")

        session = attach_concept_observation(
            session_id,
            observation_ref=f"evidence://real-home/{concept_id}/observation-1",
            source_type="user_provided_real_image",
            identity_confirmed=True,
        )
        features = concept["visual_pack"]["required_observed_features"]
        unknown_feature = assess_concept_invariants(session_id, [{"feature": "not_a_real_invariant", "status": "observed"}])
        require(unknown_feature.get("error") == "unknown_visual_invariant", "unknown invariant must be rejected")
        invalid_status = assess_concept_invariants(session_id, [{"feature": features[0], "status": "assumed"}])
        require(invalid_status.get("error") == "unsupported_invariant_status", "unsupported assessment status must be rejected")
        partial = assess_concept_invariants(session_id, [
            {"feature": feature, "status": "observed" if index else "uncertain_or_occluded"}
            for index, feature in enumerate(features)
        ])
        require(partial["status"] == "assessing_visual_invariants", "uncertain invariant must keep session open")
        blocked = finish_concept_teaching_session(session_id)
        require(blocked.get("error") == "concept_observation_candidate_not_ready", "uncertain invariant must block compilation")

        complete = assess_concept_invariants(session_id, [
            {"feature": feature, "status": "observed"} for feature in features
        ])
        require(complete["status"] == "ready_to_compile", "all observed invariants must make candidate ready")
        candidate = finish_concept_teaching_session(session_id)
        require(candidate["status"] == "concept_observation_candidate_compiled", "candidate must compile")
        require(candidate["functional_facts_physically_verified"] is False, "appearance must not verify function")
        require(candidate["runtime_visible"] is False, "candidate must remain invisible to runtime")
        require(candidate["runtime_fact_committed"] is False, "candidate must not commit runtime facts")
        require(candidate["concept_registry_mutated"] is False, "candidate must not mutate concept registry")
        require(candidate["direct_execution_allowed"] is False, "candidate must not grant execution authority")
        require(all(item["status"] == "unverified" for item in candidate["functional_claims"]), "functional claims must remain unverified")

    registry_after = load_concept_pack_registry(active_domains=("home",), include_on_demand=True)
    require(registry_after == registry_before, "teaching sessions must not alter the household concept registry")
    malformed = assess_concept_invariants("missing", [{"feature": "x", "status": "observed"}])
    require(malformed.get("error") == "concept_teaching_session_not_found", "missing session must be rejected")
    print("concept teaching station validation passed")


if __name__ == "__main__":
    main()
