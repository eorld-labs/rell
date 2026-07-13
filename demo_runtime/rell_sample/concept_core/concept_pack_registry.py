from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REGISTRY_FILE = DATA_DIR / "concept_packs" / "registry.json"
RESIDENT_LOAD_POLICIES = {"core_resident", "domain_resident"}
REQUIRED_CONCEPT_FIELDS = {
    "concept_id",
    "display_name",
    "aliases",
    "compatible_kinds",
    "perceptual_invariants",
    "variable_features",
    "functional_affordances",
    "physical_properties",
    "expected_relations",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_concept_pack_registry(
    *, active_domains: tuple[str, ...] = ("home",), include_on_demand: bool = False
) -> dict[str, Any]:
    return deepcopy(_load_compiled_registry(tuple(active_domains), include_on_demand))


@lru_cache(maxsize=8)
def _load_compiled_registry(active_domains: tuple[str, ...], include_on_demand: bool) -> dict[str, Any]:
    """Validate and compile once; runtime callers receive isolated snapshots."""
    registry = _read_json(REGISTRY_FILE)
    concepts: list[dict[str, Any]] = []
    loaded_packs: list[dict[str, Any]] = []
    shared_grounding_policy: dict[str, Any] = {}
    safety_channels: list[str] = []

    for relative_path in registry.get("core_pack_files", []):
        path = REGISTRY_FILE.parent / relative_path
        payload = _read_json(path)
        loaded_packs.append({"pack_id": payload["pack_id"], "path": relative_path, "scope": "core"})
        shared_grounding_policy.update(deepcopy(payload.get("shared_grounding_policy", {})))
        safety_channels.extend(payload.get("safety_channels_always_on", []))
        concepts.extend(_select_concepts(payload.get("concepts", []), include_on_demand))

    for domain in registry.get("domain_packs", []):
        if domain.get("domain_id") not in active_domains:
            continue
        manifest_path = REGISTRY_FILE.parent / domain["manifest"]
        manifest = _read_json(manifest_path)
        for category in manifest.get("categories", []):
            category_path = manifest_path.parent / category["file"]
            payload = _read_json(category_path)
            loaded_packs.append({
                "pack_id": payload["pack_id"],
                "path": str(category_path.relative_to(REGISTRY_FILE.parent)).replace("\\", "/"),
                "scope": domain["domain_id"],
                "category": payload["category"],
            })
            concepts.extend(_select_concepts(payload.get("concepts", []), include_on_demand))

    result = {
        "schema_version": registry["schema_version"],
        "registry_id": registry["registry_id"],
        "active_domains": list(active_domains),
        "concepts": concepts,
        "shared_grounding_policy": shared_grounding_policy,
        "safety_channels_always_on": sorted(set(safety_channels)),
        "loaded_packs": loaded_packs,
        "storage_boundary": deepcopy(registry.get("storage_boundary", {})),
    }
    validate_concept_pack_registry(result)
    return result


def _select_concepts(concepts: list[dict[str, Any]], include_on_demand: bool) -> list[dict[str, Any]]:
    selected = []
    for concept in concepts:
        load_policy = concept.get("load_policy", "domain_resident")
        if not include_on_demand and load_policy not in RESIDENT_LOAD_POLICIES:
            continue
        selected.append(deepcopy(concept))
    return selected


def validate_concept_pack_registry(registry: dict[str, Any]) -> dict[str, Any]:
    concept_ids: set[str] = set()
    errors: list[dict[str, Any]] = []
    for concept in registry.get("concepts", []):
        concept_id = concept.get("concept_id")
        missing = sorted(REQUIRED_CONCEPT_FIELDS - set(concept))
        if missing:
            errors.append({"concept_id": concept_id, "reason": "required_fields_missing", "fields": missing})
        if concept_id in concept_ids:
            errors.append({"concept_id": concept_id, "reason": "duplicate_concept_id"})
        concept_ids.add(str(concept_id))
        if concept.get("load_policy") not in {"core_resident", "domain_resident", "on_demand"}:
            errors.append({"concept_id": concept_id, "reason": "unsupported_load_policy"})
        if concept.get("direct_execution_allowed") is not False:
            errors.append({"concept_id": concept_id, "reason": "concept_bypasses_orchestration"})
        if not concept.get("aliases") or not concept.get("compatible_kinds"):
            errors.append({"concept_id": concept_id, "reason": "identity_or_grounding_adapter_missing"})
    if not registry.get("shared_grounding_policy") or not registry.get("safety_channels_always_on"):
        errors.append({"reason": "shared_grounding_or_safety_policy_missing"})
    if errors:
        raise ValueError({"error": "concept_pack_registry_invalid", "details": errors})
    return {
        "status": "concept_pack_registry_valid",
        "concept_count": len(concept_ids),
        "loaded_pack_count": len(registry.get("loaded_packs", [])),
        "active_domains": deepcopy(registry.get("active_domains", [])),
        "direct_execution_allowed": False,
    }
