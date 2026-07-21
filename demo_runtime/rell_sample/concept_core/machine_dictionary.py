from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any


DICTIONARY_SCHEMA_VERSION = "1.0.0"
DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "rell_machine_dictionary.json"

ENTRY_KINDS = {
    "primitive_predicate",
    "primitive_operator",
    "modifier",
    "operator_contract",
    "process_template",
    "domain_pack_entry",
}
CORE_ENTRY_KINDS = {"primitive_predicate", "primitive_operator", "modifier"}

_MIGRATION_CLASSIFICATION = {
    "observe_entity": "primitive_operator",
    "navigate_to": "primitive_operator",
    "orient_executor": "primitive_operator",
    "grasp_object": "primitive_operator",
    "release_object": "primitive_operator",
    "fill_container": "operator_contract",
    "place_object": "primitive_operator",
    "handover_object": "operator_contract",
    "transport_object": "operator_contract",
    "relocate_object": "operator_contract",
    "apply_directional_force": "primitive_operator",
    "change_open_state": "operator_contract",
    "change_device_activation": "operator_contract",
    "transfer_material": "operator_contract",
    "remove_surface_contaminant": "operator_contract",
    "stop_current_activity": "primitive_operator",
    "wait_until": "primitive_operator",
}


def _stable_id(prefix: str, value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return prefix + "_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


@lru_cache(maxsize=1)
def load_machine_dictionary() -> dict[str, Any]:
    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    validate_machine_dictionary(payload)
    return payload


def validate_machine_dictionary(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != DICTIONARY_SCHEMA_VERSION:
        raise ValueError("unsupported machine dictionary schema version")
    entries = payload.get("entries") or []
    ids = [item.get("entry_id") for item in entries]
    if not ids or len(ids) != len(set(ids)) or any(not item for item in ids):
        raise ValueError("dictionary entry ids must be present and unique")
    index = {item["entry_id"]: item for item in entries}
    for item in entries:
        kind = item.get("entry_kind")
        if kind not in ENTRY_KINDS:
            raise ValueError(f"unsupported dictionary entry kind: {kind}")
        components = item.get("components") or []
        if kind in CORE_ENTRY_KINDS:
            if item.get("irreducible") is not True or components:
                raise ValueError(f"core glyph must be irreducible: {item['entry_id']}")
        elif item.get("irreducible") is not False or not components:
            raise ValueError(f"compound entry must declare components: {item['entry_id']}")
        missing = [ref for ref in components if ref not in index]
        if missing:
            raise ValueError(f"entry {item['entry_id']} has missing components: {missing}")
        if kind in {"primitive_operator", "operator_contract", "process_template", "domain_pack_entry"}:
            contract = item.get("causal_contract") or {}
            if not all(key in contract for key in ("requires", "projects", "verification")):
                raise ValueError(f"executable entry lacks causal contract: {item['entry_id']}")
        if item.get("fact_commit_authority") not in {"none", "P016_via_WorldFactLedger_only"}:
            raise ValueError(f"invalid fact authority: {item['entry_id']}")
        if kind == "modifier":
            if not all(item.get(key) for key in ("modifier_dimension", "modifier_value", "default_scope")):
                raise ValueError(f"modifier lacks typed composition metadata: {item['entry_id']}")
            if item.get("default_scope") not in {"event", "global"}:
                raise ValueError(f"invalid modifier scope: {item['entry_id']}")


def dictionary_index(payload: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    source = payload or load_machine_dictionary()
    return {item["entry_id"]: deepcopy(item) for item in source.get("entries", [])}


def lookup_surface_candidates(
    surface: str,
    *,
    language: str = "zh",
    host_classification: str | None = None,
    syntactic_position: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = payload or load_machine_dictionary()
    candidates = []
    for entry in source.get("entries", []):
        for adapter in entry.get("language_adapters", {}).get(language, []):
            if adapter.get("surface") != surface:
                continue
            constraints = adapter.get("selection_constraints") or {}
            host_values = set(constraints.get("host_classifications") or [])
            positions = set(constraints.get("syntactic_positions") or [])
            compatible = bool(
                (not host_classification or not host_values or host_classification in host_values)
                and (not syntactic_position or not positions or syntactic_position in positions)
            )
            candidates.append(
                {
                    "entry_ref": entry["entry_id"],
                    "entry_kind": entry["entry_kind"],
                    "semantic_value": entry.get("semantic_value"),
                    "selection_constraints": deepcopy(constraints),
                    "compatible_with_supplied_context": compatible,
                    "candidate_only": True,
                    "runtime_fact_committed": False,
                }
            )
    compatible = [item for item in candidates if item["compatible_with_supplied_context"]]
    status = "not_found" if not candidates else "unique" if len(compatible) == 1 else "ambiguous"
    result = {
        "lookup_id": _stable_id(
            "dictionary_lookup",
            [surface, language, host_classification, syntactic_position, candidates],
        ),
        "surface_ref": "sha256:" + hashlib.sha256(surface.encode("utf-8")).hexdigest(),
        "language": language,
        "status": status,
        "candidates": candidates,
        "selected_entry_ref": compatible[0]["entry_ref"] if status == "unique" else None,
        "inquiry_required": status == "ambiguous",
        "surface_text_forwarded_downstream": False,
        "runtime_fact_committed": False,
    }
    return result


def realize_dictionary_entry(
    entry_ref: str, *, language: str = "zh", payload: dict[str, Any] | None = None
) -> str | None:
    entry = dictionary_index(payload).get(entry_ref) or {}
    adapters = entry.get("language_adapters", {}).get(language, [])
    canonical = next((item for item in adapters if item.get("canonical")), None)
    return (canonical or (adapters[0] if adapters else {})).get("surface")


def scan_surface_candidate_groups(
    text: str,
    *,
    language: str = "zh",
    payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    source = payload or load_machine_dictionary()
    surfaces = sorted(
        {
            adapter.get("surface")
            for entry in source.get("entries", [])
            for adapter in entry.get("language_adapters", {}).get(language, [])
            if adapter.get("surface")
        },
        key=lambda value: (-len(str(value)), str(value)),
    )
    groups = []
    for surface in surfaces:
        start = text.find(surface)
        while start >= 0:
            lookup = lookup_surface_candidates(
                surface, language=language, payload=source
            )
            groups.append(
                {
                    "surface_ref": lookup["surface_ref"],
                    "span": [start, start + len(surface)],
                    "candidate_entry_refs": [
                        item["entry_ref"] for item in lookup["candidates"]
                    ],
                    "status": lookup["status"],
                    "selected_entry_ref": lookup["selected_entry_ref"],
                    "candidate_only": True,
                    "runtime_fact_committed": False,
                }
            )
            start = text.find(surface, start + 1)
    return sorted(groups, key=lambda item: (item["span"][0], -(item["span"][1] - item["span"][0])))


def dictionary_architecture_summary(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    source = payload or load_machine_dictionary()
    counts = {
        kind: sum(1 for item in source.get("entries", []) if item.get("entry_kind") == kind)
        for kind in sorted(ENTRY_KINDS)
    }
    return {
        "dictionary_id": source.get("dictionary_id"),
        "schema_version": source.get("schema_version"),
        "entry_counts": counts,
        "core_is_finite": True,
        "compounds_are_compositional": True,
        "language_adapters_have_no_fact_authority": True,
    }


def dictionary_modifier_lexicon(
    payload: dict[str, Any] | None = None, *, language: str = "zh"
) -> list[dict[str, Any]]:
    source = payload or load_machine_dictionary()
    records = []
    for entry in source.get("entries", []):
        if entry.get("entry_kind") != "modifier":
            continue
        surfaces = [
            item.get("surface")
            for item in entry.get("language_adapters", {}).get(language, [])
            if item.get("surface")
        ]
        if not surfaces:
            continue
        records.append(
            {
                "entry_ref": entry["entry_id"],
                "dimension": entry["modifier_dimension"],
                "value": entry["modifier_value"],
                "scope": entry["default_scope"],
                "surfaces": surfaces,
                "adapters": [
                    deepcopy(item)
                    for item in entry.get("language_adapters", {}).get(language, [])
                    if item.get("surface")
                ],
                "selection_constraints": [
                    deepcopy(item.get("selection_constraints") or {})
                    for item in entry.get("language_adapters", {}).get(language, [])
                    if item.get("surface")
                ],
                "candidate_only": True,
                "runtime_fact_committed": False,
            }
        )
    return records


def audit_event_concept_dictionary_coverage(
    event_concepts: list[dict[str, Any]],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = payload or load_machine_dictionary()
    semantic_index: dict[str, list[dict[str, Any]]] = {}
    for entry in source.get("entries", []):
        if entry.get("entry_kind") in {
            "primitive_operator",
            "operator_contract",
            "process_template",
            "domain_pack_entry",
        }:
            semantic_index.setdefault(str(entry.get("semantic_value")), []).append(entry)
    records = []
    for concept in event_concepts:
        kernel = concept.get("concept_kernel") or {}
        operator = str(kernel.get("operator") or "")
        matches = semantic_index.get(operator, [])
        status = "covered" if len(matches) == 1 else "conflict" if len(matches) > 1 else "missing"
        records.append(
            {
                "concept_id": concept.get("concept_id"),
                "operator": operator,
                "status": status,
                "entry_refs": [item["entry_id"] for item in matches],
                "recommended_entry_kind": _MIGRATION_CLASSIFICATION.get(
                    operator, "domain_pack_entry"
                ),
                "classification_basis": "irreducibility_and_causal_contract_boundary",
            }
        )
    covered = [item for item in records if item["status"] == "covered"]
    missing = [item for item in records if item["status"] == "missing"]
    conflicts = [item for item in records if item["status"] == "conflict"]
    return {
        "audit_kind": "MachineDictionaryCoverageAudit",
        "dictionary_ref": source.get("dictionary_id"),
        "source_registry": "FACTORY_EVENT_CONCEPT_UNITS",
        "total": len(records),
        "covered_count": len(covered),
        "missing_count": len(missing),
        "conflict_count": len(conflicts),
        "coverage_ratio": round(len(covered) / len(records), 6) if records else 1.0,
        "records": records,
        "migration_ready": not missing and not conflicts,
        "can_control_execution": False,
        "runtime_fact_committed": False,
    }
__all__ = [
    "audit_event_concept_dictionary_coverage",
    "dictionary_architecture_summary",
    "dictionary_index",
    "dictionary_modifier_lexicon",
    "load_machine_dictionary",
    "lookup_surface_candidates",
    "realize_dictionary_entry",
    "scan_surface_candidate_groups",
    "validate_machine_dictionary",
]
