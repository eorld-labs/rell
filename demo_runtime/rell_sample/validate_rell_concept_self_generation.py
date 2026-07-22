from __future__ import annotations

from concept_core.cognitive_inquiry import run_concept_validation_loop


def validate_case(prediction_confirmed: bool) -> None:
    loop = run_concept_validation_loop(prediction_confirmed=prediction_confirmed)
    candidate = loop["candidate"]
    causal = candidate["minimal_causal_contract"]
    applicability = candidate["applicability_contract"]
    decision = loop["decision"]
    adapter = loop["language_adapter_candidate"]
    assert causal["observable_features"]
    assert causal["functional_affordances"]
    assert causal["participating_relations"]
    assert causal["preconditions"]
    assert causal["effects"]
    assert causal["p016_verification_conditions"]
    assert applicability["scope"] and applicability["counterexamples"]
    assert applicability["new_instance_required"] is True
    assert decision["basis"] == "new_instance_p016_verification"
    assert decision["execution_authority_granted"] is False
    assert adapter["core_dictionary_write_allowed"] is False
    assert adapter["requires_dictionary_authority_admission"] is True
    assert loop["new_instance_probe_receipt"]["independent_channels"] == 2
    if prediction_confirmed:
        assert candidate["lifecycle_status"] == "trusted"
        assert decision["decision"] == "promoted"
        assert adapter["status"] == "candidate_generated"
    else:
        assert candidate["lifecycle_status"] == "rejected"
        assert decision["decision"] == "rejected"
        assert adapter["status"] == "withheld_after_rejection"


def main() -> None:
    validate_case(True)
    validate_case(False)
    print("RELL 概念自生成闭环校验通过：因果合同、主动验真、晋级/否决和词条候选均受权威边界约束。")


if __name__ == "__main__":
    main()
