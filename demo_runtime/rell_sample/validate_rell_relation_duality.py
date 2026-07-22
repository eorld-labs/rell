from __future__ import annotations

from concept_core.relation_duality import project_inverse_candidate, relation_duality_contract


def main() -> None:
    contract = relation_duality_contract()
    assert contract["status"] == "candidate_contract"
    assert len(contract["relations"]) == 5
    assert "inverse_projection_does_not_create_new_fact" in contract["rules"]
    assert "social_relation_requires_social_evidence" in contract["rules"]
    assert "physical_relation_requires_p016_verification" in contract["rules"]
    expected = {
        "inside": ("contained_in", "contains", "physical_boundary"),
        "contains": ("contained_in", "contains", "physical_boundary"),
        "supports": ("supported_by", "supports", "physical_contact"),
        "held_by": ("held_by", "holds", "possession_contact"),
        "owned_by": ("owned_by", "owns", "social_context"),
        "accessible_to": ("accessible_to", "can_be_accessed_by", "reachability_and_permission"),
    }
    for relation, (canonical, inverse, evidence_class) in expected.items():
        candidate = project_inverse_candidate(relation, world_revision=7)
        assert candidate
        assert (candidate["canonical"], candidate["inverse"], candidate["evidence_class"]) == (canonical, inverse, evidence_class)
        assert candidate["inverse_projection_is_new_fact"] is False
        assert candidate["direct_execution_allowed"] is False
        assert candidate["verification_gateway"] == "P016"
    assert project_inverse_candidate("unknown_relation", world_revision=7) is None
    print("RELL 关系正反合同校验通过：物理、持有、社会和可达关系均保持候选与证据边界。")


if __name__ == "__main__":
    main()
