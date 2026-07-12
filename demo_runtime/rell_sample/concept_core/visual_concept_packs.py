from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


PACK_DIR = Path(__file__).resolve().parents[1] / "data" / "visual_concept_packs"


def load_visual_concept_packs(*, include_on_demand: bool = False) -> list[dict[str, Any]]:
    packs = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(PACK_DIR.glob("*.json"))]
    if include_on_demand:
        return packs
    return [item for item in packs if item.get("load_policy") == "factory_resident"]


def match_visual_concept_candidates(
    observed_track: dict[str, Any],
    packs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    observed_features = set(observed_track.get("observed_visual_features", []))
    observed_color = observed_track.get("observed_color_family")
    candidates = []
    for pack in packs:
        adapter = pack.get("recognition_adapter", {})
        required = set(adapter.get("required_observed_features", []))
        if not required:
            continue
        feature_score = len(required.intersection(observed_features)) / len(required)
        color_families = set(adapter.get("supporting_color_families", []))
        color_support = 1.0 if observed_color and observed_color in color_families else 0.0
        score = round(feature_score * 0.88 + color_support * 0.12, 4)
        if score < float(adapter.get("minimum_match_score", 1.0)):
            continue
        candidates.append({
            "concept_id": pack["concept_id"],
            "visual_pack_id": pack["pack_id"],
            "confidence": score,
            "matched_features": sorted(required.intersection(observed_features)),
            "reference_sample_count": len(pack.get("reference_samples", [])),
            "candidate_only": True,
            "direct_execution_allowed": False,
        })
    return sorted(candidates, key=lambda item: item["confidence"], reverse=True)


def build_visual_pack_catalog() -> dict[str, Any]:
    packs = load_visual_concept_packs(include_on_demand=True)
    return {
        "schema_version": "1.0.0",
        "packs": deepcopy(packs),
        "resident_pack_ids": [item["pack_id"] for item in packs if item.get("load_policy") == "factory_resident"],
        "boundary": {
            "visual_pack_is_not_action_experience": True,
            "visual_pack_does_not_replace_object_concept_kernel": True,
            "unmatched_observation_remains_unknown_candidate": True,
            "direct_execution_allowed": False,
        },
    }
