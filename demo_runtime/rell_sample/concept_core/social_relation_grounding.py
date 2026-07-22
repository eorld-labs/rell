from __future__ import annotations

from typing import Any


SOCIAL_RELATION_RULES = {
    "source_holder": {
        "predicate": "held_by",
        "evidence_class": "possession_contact",
        "required_evidence": ["qualified_multimodal_observation", "p016_physical_verification"],
    },
    "ownership_claim": {
        "predicate": "owned_by",
        "evidence_class": "social_context",
        "required_evidence": ["social_ownership_record", "human_confirmation_with_context"],
    },
    "accessibility_claim": {
        "predicate": "accessible_to",
        "evidence_class": "reachability_and_permission",
        "required_evidence": ["current_reachability_verification", "permission_policy_verification"],
    },
}


def project_social_relation_candidates(analysis: dict[str, Any], *, world_revision: int) -> list[dict[str, Any]]:
    discourse_roles = dict(analysis.get("discourse_roles") or {})
    if "source_holder" not in discourse_roles and any(
        item.get("event_type") == "possession_state_report"
        for item in analysis.get("reported_event_candidates", [])
    ):
        discourse_roles["source_holder"] = {
            "reference": "human_speaker",
            "source": "structured_possession_state_report",
        }
    candidates = []
    for role_name, rule in SOCIAL_RELATION_RULES.items():
        role = discourse_roles.get(role_name)
        if not role:
            continue
        candidates.append({
            "schema_version": "1.0.0",
            "status": "candidate",
            "role": role_name,
            "predicate": rule["predicate"],
            "subject_ref": "language_theme_candidate",
            "object_ref": role.get("reference"),
            "evidence_class": rule["evidence_class"],
            "required_evidence": list(rule["required_evidence"]),
            "world_revision": world_revision,
            "source": role.get("source"),
            "fact_commit_eligible": False,
            "runtime_fact_committed": False,
            "fact_authority": "WorldFactLedger",
            "verification_gateway": "P016",
            "direct_execution_allowed": False,
        })
    return candidates
