from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "schemas" / "rell_relation_duality_contract_v1.json"


def relation_duality_contract() -> dict[str, Any]:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def project_inverse_candidate(relation: str, *, world_revision: int) -> dict[str, Any] | None:
    for item in relation_duality_contract()["relations"]:
        if relation in {item["canonical"], item["language_positive"], item["inverse"]}:
            return {
                "schema_version": "1.0.0",
                "status": "candidate",
                "canonical": item["canonical"],
                "inverse": item["inverse"],
                "evidence_class": item["evidence_class"],
                "verification": item["verification"],
                "world_revision": world_revision,
                "inverse_projection_is_new_fact": False,
                "fact_authority": "WorldFactLedger",
                "verification_gateway": "P016",
                "direct_execution_allowed": False,
            }
    return None
