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


__all__ = [
    "dictionary_architecture_summary",
    "dictionary_index",
    "load_machine_dictionary",
    "lookup_surface_candidates",
    "realize_dictionary_entry",
    "validate_machine_dictionary",
]
