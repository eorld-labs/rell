from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "rell_spatial_social_primitive_candidates_v1.json"


def main() -> None:
    registry = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert registry["status"] == "candidate_only"
    assert registry["authority"]["fact_source"] == "WorldFactLedger"
    assert registry["authority"]["verification_gateway"] == "P016"
    assert registry["authority"]["control_gateway"] == "P018"
    primitives = registry["primitives"]
    assert len(primitives) == 12
    required = {"id", "aliases", "arity", "grounding", "planner_contract", "verification"}
    ids = set()
    for primitive in primitives:
        assert required <= set(primitive)
        assert primitive["id"] not in ids
        assert primitive["aliases"]
        assert primitive["arity"] in {2, 3}
        ids.add(primitive["id"])
    assert {"near_human", "beside", "in_front_of", "behind", "facing", "between"} <= ids
    assert {"inside", "contains", "supports", "held_by", "owned_by", "accessible_to"} <= ids
    assert registry["promotion_policy"] == [
        "candidate_concept", "minimal_causal_contract", "active_observation",
        "new_instance_verification", "promote_or_reject", "language_adapter_generation",
    ]
    print(f"RELL 空间/社会关系候选原语校验通过：{len(primitives)} 个原语保持候选态，未进入事实源。")


if __name__ == "__main__":
    main()
