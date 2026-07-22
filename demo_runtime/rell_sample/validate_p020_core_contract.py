from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "p020_rell_core_contract_v1.json"


def main() -> None:
    contract = json.loads(SCHEMA.read_text(encoding="utf-8"))
    required_types = {
        "EntityRef", "Predicate", "Event", "EvidenceEnvelope",
        "WorldFact", "Goal", "Constraint",
    }
    assert set(contract["basic_types"]) == required_types
    authority = contract["authority"]
    assert authority == {
        "semantic_admission": "DictionaryAuthorityAdmission",
        "fact_ledger": "WorldFactLedger",
        "control_gateway": "P018",
        "verification_gateway": "P016",
    }
    invariants = set(contract["invariants"])
    assert "language_does_not_commit_physical_fact" in invariants
    assert "perception_candidate_is_not_runtime_fact" in invariants
    assert "downstream_does_not_reparse_surface_text" in invariants
    assert "ambiguous_binding_never_silently_becomes_unique" in invariants
    assert "p016_is_only_runtime_fact_write_gateway" in invariants
    assert "p018_is_only_control_gateway" in invariants
    policy = contract["extension_policy"]
    assert "schema_extension" in policy["allowed"]
    assert "second_fact_source" in policy["forbidden"]
    assert "control_bypass" in policy["forbidden"]
    print("P020/RELL 核心合同校验通过：七类基本类型、四个权威边界和扩展不变量已冻结。")


if __name__ == "__main__":
    main()
